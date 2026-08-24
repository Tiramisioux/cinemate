#!/usr/bin/env python3
"""wifi_hotspot.py
~~~~~~~~~~~~~~~~~~~

Utility class around **nmcli** for managing a Raspberry Pi Wi‑Fi hotspot.

Key points
==========
* Graceful fallback to **CinePi / 11111111** if:
  - the JSON file is missing/corrupt (when *settings* is *None*),
  - the keys are absent, **or**
  - the caller passes *None* / an empty string as override.
* Enforces the NetworkManager minimum (≥ 8 char password).

"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, NamedTuple, Optional

from module.config_loader import SettingsLoadError, load_settings

logger = logging.getLogger(__name__)

__all__ = [
    "WiFiHotspotManager",
    "Credentials",
    "resolve_credentials",
    "hotspot_service_active",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_SSID:  Final[str] = "CinePi"
DEFAULT_PASS:  Final[str] = "11111111"  # 8 chars → nmcli minimum
SETTINGS_PATH: Final[Path] = Path("/home/pi/cinemate/settings.jsonc")
READY_STATES: Final[set[str]] = {"connected", "connected (externally)", "disconnected"}

#: Root-owned runtime state. Created by the installer and, failing that, by the
#: watchdog on its first pass. Everything that touches it degrades to a no-op
#: when it is absent or unwritable -- a unit that predates this directory must
#: still bring its hotspot up.
STATE_DIR:      Final[Path] = Path("/var/lib/cinemate")
LAST_GOOD_PATH: Final[Path] = STATE_DIR / "hotspot.last-good.json"
STATE_PATH:     Final[Path] = STATE_DIR / "hotspot.state"

#: Credential ladder rungs, in the order they are attempted.
RUNG_SETTINGS: Final[int] = 1
RUNG_CACHE:    Final[int] = 2
RUNG_DEFAULTS: Final[int] = 3
RUNG_NAMES: Final[dict[int, str]] = {
    RUNG_SETTINGS: "settings",
    RUNG_CACHE:    "cache",
    RUNG_DEFAULTS: "defaults",
}

#: settings.jsonc probe outcomes. "absent" and "unparseable" are deliberately
#: distinct: both fall through to the cache, but only one of them means the
#: operator broke something, and the state file has to say which.
SETTINGS_OK:          Final[str] = "ok"
SETTINGS_ABSENT:      Final[str] = "absent"
SETTINGS_UNPARSEABLE: Final[str] = "unparseable"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class SettingsProbe(NamedTuple):
    """Outcome of reading settings.jsonc, with *why* it failed preserved."""

    status: str            # SETTINGS_OK | SETTINGS_ABSENT | SETTINGS_UNPARSEABLE
    data: dict             # {} unless status is SETTINGS_OK
    detail: str | None     # operator-facing reason, None when status is OK


def probe_settings(path: Path = SETTINGS_PATH) -> SettingsProbe:
    """Read settings.jsonc, distinguishing *absent* from *unparseable*.

    The old behaviour collapsed both to ``{}``, which is why a single stray
    comma renamed the operator's network to ``CinePi`` with no explanation
    (docs/hotspot-logic.md). Delegates to config_loader.load_settings() so
    the reason reported here is the *same text* main.py prints on tty1.
    """
    if not path.exists():
        return SettingsProbe(SETTINGS_ABSENT, {}, f"{path} does not exist")

    try:
        return SettingsProbe(SETTINGS_OK, load_settings(path), None)
    except SettingsLoadError as exc:
        return SettingsProbe(SETTINGS_UNPARSEABLE, {}, f"{exc.summary}: {exc.detail}")
    except Exception as exc:  # defensive: never let the hotspot die on this
        return SettingsProbe(SETTINGS_UNPARSEABLE, {}, f"{type(exc).__name__}: {exc}")


def _load_settings(path: Path = SETTINGS_PATH) -> dict:
    """Return settings as dict; empty dict on any error.

    Retained for callers that only want the data. Prefer probe_settings(),
    which also tells you whether an empty result means "no file" or "the
    file is broken".
    """
    return probe_settings(path).data


def _extract_credentials(cfg: dict | None) -> tuple[str, str, bool]:
    """Extract SSID, password and ``enabled`` flag from settings.

    Returns safe defaults when cfg is *None* or keys are missing.
    """
    wifi_cfg = (cfg or {}).get("system", {}).get("wifi_hotspot", {})
    ssid = wifi_cfg.get("name", DEFAULT_SSID) or DEFAULT_SSID
    pw = wifi_cfg.get("password", DEFAULT_PASS) or DEFAULT_PASS
    enabled = bool(wifi_cfg.get("enabled", True))

    if len(pw) < 8:
        logger.warning("Password from settings < 8 chars – using default.")
        pw = DEFAULT_PASS
    return ssid, pw, enabled


# ---------------------------------------------------------------------------
# Durable state: atomic writes, the last-good cache, the state file
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_bytes(path: Path, data: bytes, *, mode: int = 0o644) -> None:
    """Write *data* to *path* so a reader never sees a half-written file.

    Temp file in the same directory, flush, fsync, os.replace, then fsync the
    directory itself -- the last step is what makes the rename survive power
    loss, which is the failure mode that matters on a camera with no shutdown
    button. Raises on failure; callers that must not die wrap it.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
        tmp_name = None
    finally:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass

    # fsync the directory so the rename itself is durable.
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def read_last_good(path: Path = LAST_GOOD_PATH) -> tuple[str, str, bool] | None:
    """Return cached (ssid, password, enabled), or None if unusable.

    A cache that is missing, unreadable, malformed, or carries a password
    NetworkManager would reject is treated as absent -- the ladder must fall
    through to the compiled-in defaults rather than to a broken rung.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("No usable hotspot cache at %s: %s", path, exc)
        return None

    if not isinstance(raw, dict):
        return None
    ssid = raw.get("ssid")
    pw = raw.get("password")
    if not isinstance(ssid, str) or not ssid:
        return None
    if not isinstance(pw, str) or len(pw) < 8:
        return None
    return ssid, pw, bool(raw.get("enabled", True))


def write_last_good(
    ssid: str, password: str, enabled: bool, path: Path = LAST_GOOD_PATH
) -> bool:
    """Cache the credentials settings.jsonc just gave us. Best effort.

    Mode 0600: this file holds the pre-shared key.
    """
    payload = {
        "ssid": ssid,
        "password": password,
        "enabled": enabled,
        "updated": _utc_now(),
    }
    try:
        atomic_write_bytes(
            Path(path),
            (json.dumps(payload, indent=2) + "\n").encode("utf-8"),
            mode=0o600,
        )
        return True
    except OSError as exc:
        logger.debug("Could not cache hotspot credentials at %s: %s", path, exc)
        return False


def write_state(creds: "Credentials", path: Path = STATE_PATH) -> bool:
    """Publish the active rung for the recovery console. Best effort.

    Never contains the password: this is read by an unauthenticated route.
    """
    payload = {
        "rung": creds.rung,
        "rung_name": RUNG_NAMES.get(creds.rung, "unknown"),
        "reason": creds.reason,
        "ssid": creds.ssid,
        "enabled": creds.enabled,
        "settings_status": creds.settings_status,
        "updated": _utc_now(),
    }
    try:
        atomic_write_bytes(
            Path(path), (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        )
        return True
    except OSError as exc:
        logger.debug("Could not write hotspot state to %s: %s", path, exc)
        return False


# ---------------------------------------------------------------------------
# The credential ladder (docs/hotspot-logic.md)
# ---------------------------------------------------------------------------

class Credentials(NamedTuple):
    """Resolved hotspot credentials plus the provenance of that decision."""

    ssid: str
    password: str
    enabled: bool
    rung: int
    reason: str
    settings_status: str


def resolve_credentials(
    settings_path: Path = SETTINGS_PATH,
    cache_path: Path = LAST_GOOD_PATH,
    *,
    persist: bool = True,
) -> Credentials:
    """Resolve hotspot credentials through the three-rung ladder.

    1. settings.jsonc parses  -> use it, and refresh the last-good cache
    2. it does not parse      -> use the last-good cache
    3. no usable cache        -> compiled-in CinePi / 11111111

    An *absent* settings.jsonc falls through the same way an unparseable one
    does -- last-good beats CinePi in both cases -- but the reason recorded
    distinguishes them.

    Args:
        persist: False skips writing the cache. Used by callers that only
                 want to know the answer (and by the tests).
    """
    probe = probe_settings(settings_path)

    if probe.status == SETTINGS_OK:
        ssid, pw, enabled = _extract_credentials(probe.data)
        if persist:
            write_last_good(ssid, pw, enabled, cache_path)
        return Credentials(
            ssid, pw, enabled, RUNG_SETTINGS, "settings.jsonc parsed", probe.status
        )

    cached = read_last_good(cache_path)
    if cached is not None:
        ssid, pw, enabled = cached
        return Credentials(
            ssid,
            pw,
            enabled,
            RUNG_CACHE,
            f"{probe.detail}; using last-good credentials",
            probe.status,
        )

    return Credentials(
        DEFAULT_SSID,
        DEFAULT_PASS,
        True,
        RUNG_DEFAULTS,
        f"{probe.detail}; no usable last-good cache; using built-in defaults",
        probe.status,
    )


def hotspot_service_active(
    service: str = "wifi-hotspot.service", runner=subprocess.run
) -> bool:
    """True when wifi-hotspot.service owns the hotspot.

    main.py uses this to stand down, so there is exactly one owner (F5).
    Any failure answers False, which keeps in-app creation working on an
    install where the service was never enabled.
    """
    try:
        res = runner(
            ["systemctl", "is-active", "--quiet", service],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0
    except Exception as exc:
        logger.debug("Could not query %s: %s", service, exc)
        return False


# ---------------------------------------------------------------------------
# nmcli terse-output parsing
# ---------------------------------------------------------------------------

def split_terse(line: str) -> list[str]:
    """Split one ``nmcli -t`` line, honouring its backslash escaping.

    nmcli escapes a literal ':' inside a field as '\\:', so a naive
    ``line.split(':')`` corrupts any SSID containing a colon.
    """
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def terse_value(line: str) -> tuple[str, str]:
    """Split a ``nmcli -t -f <field> con show`` line into (field, value)."""
    fields = split_terse(line)
    if len(fields) < 2:
        return (fields[0] if fields else ""), ""
    return fields[0], ":".join(fields[1:])


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class WiFiHotspotManager:
    """Thin wrapper around *nmcli* to control the hotspot."""

    def __init__(
        self,
        *,
        iface: str = "wlan0",
        settings: Optional[dict] = None,
        settings_path: Path = SETTINGS_PATH,
        cache_path: Path = LAST_GOOD_PATH,
        state_path: Path = STATE_PATH,
        persist: bool = True,
    ) -> None:
        """Create a manager.

        Args:
            iface:       Network interface (usually *wlan0*).
            settings:    An already-loaded *settings.jsonc* dict. When *None*,
                         credentials are resolved through the ladder instead.
            settings_path: Where to look for *settings.jsonc* when *settings*
                         is *None*.
            cache_path:  Last-good credential cache (ladder rung 2).
            state_path:  Where the active rung is published for the recovery
                         console.
            persist:     False suppresses cache writes -- for callers that only
                         want to read the current answer.
        """
        self.iface = iface
        self.settings_path = Path(settings_path)
        self.cache_path = Path(cache_path)
        self.state_path = Path(state_path)

        if settings is not None:  # caller already did the JSON I/O
            ssid, pw, enabled = _extract_credentials(settings)
            self.credentials = Credentials(
                ssid, pw, enabled, RUNG_SETTINGS, "settings supplied by caller", SETTINGS_OK
            )
        else:  # self-contained usage -- resolve through the ladder
            self.credentials = resolve_credentials(
                self.settings_path, self.cache_path, persist=persist
            )

        self._ssid_cfg = self.credentials.ssid
        self._pw_cfg = self.credentials.password
        self.enabled = self.credentials.enabled

    def _sudo_prefix(self) -> list[str]:
        """Run privileged commands directly when already root, otherwise via sudo."""
        return [] if os.geteuid() == 0 else ["sudo"]

    def _run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a command with the right privilege prefix."""
        full_cmd = self._sudo_prefix() + cmd
        return subprocess.run(
            full_cmd,
            capture_output=capture_output,
            text=True,
            check=check,
        )

    def _device_state(self) -> str | None:
        """Return the current nmcli state string for the Wi-Fi interface."""
        try:
            res = self._run(
                ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"]
            )
        except subprocess.CalledProcessError as exc:
            logger.error("Error checking Wi-Fi device state: %s", exc)
            return None

        for line in res.stdout.splitlines():
            parts = line.split(":", 2)
            if len(parts) != 3:
                continue
            device, devtype, state = parts
            if device == self.iface and devtype == "wifi":
                return state
        return None

    def ensure_wifi_ready(self, timeout_s: float = 20.0) -> bool:
        """Best-effort unblocks Wi-Fi and waits for the interface to become usable."""
        commands = (
            ["rfkill", "unblock", "wifi"],
            ["nmcli", "radio", "wifi", "on"],
            ["nmcli", "general", "reload"],
            ["nmcli", "device", "set", self.iface, "managed", "yes"],
            ["ip", "link", "set", self.iface, "up"],
        )

        deadline = time.monotonic() + timeout_s
        last_prep = 0.0
        last_state = None
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now - last_prep >= 5.0:
                for cmd in commands:
                    try:
                        self._run(cmd)
                    except subprocess.CalledProcessError as exc:
                        logger.warning("Wi-Fi prep command failed (%s): %s", " ".join(cmd), exc)
                        if exc.stderr:
                            logger.warning("Command stderr: %s", exc.stderr.strip())
                last_prep = now

            state = self._device_state()
            if state in READY_STATES:
                if state != last_state:
                    logger.info("Wi-Fi interface %s is %s", self.iface, state)
                return True
            last_state = state
            time.sleep(1)

        logger.error(
            "Wi-Fi interface %s did not become ready within %.0fs (last state: %s)",
            self.iface,
            timeout_s,
            last_state or "unknown",
        )
        return False

    # ------------------------------------------------------------------ utils

    def is_hotspot_active(self) -> bool:
        """Return *True* if an nmcli hotspot connection is already active."""
        try:
            res = subprocess.run(
                ["nmcli", "con", "show", "--active"],
                capture_output=True, text=True, check=True,
            )
            return any(
                "wifi" in line and "Hotspot" in line
                for line in res.stdout.splitlines()
            )
        except subprocess.CalledProcessError as exc:
            logger.error("Error checking hotspot status: %s", exc)
            return False

    # ------------------------------------------------------------- operations

    def create_hotspot(
        self,
        *,
        ssid: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """Start a hotspot (idempotent).

        Args:
            ssid:      Optional override for SSID.
            password:  Optional override for password.
        """
        if not self.enabled:
            logger.info("Wi-Fi hotspot creation disabled in settings")
            return

        if self.is_hotspot_active():
            logger.info("Wi‑Fi hotspot already active – skipping creation.")
            return

        # cascade: explicit arg → settings → hard‑coded default
        ssid_final = ssid or self._ssid_cfg or DEFAULT_SSID
        pw_final = password or self._pw_cfg or DEFAULT_PASS

        if len(pw_final) < 8:
            logger.warning("Provided password < 8 chars – using default.")
            pw_final = DEFAULT_PASS

        if not self.ensure_wifi_ready():
            logger.error("Wi-Fi interface %s is not ready for hotspot creation", self.iface)
            return

        cmd = [
            "nmcli", "d", "wifi", "hotspot",
            "ifname", self.iface,
            "ssid", ssid_final,
            "password", pw_final,
        ]

        try:
            res = self._run(cmd)
            # The pre-shared key is deliberately not logged: the journal is
            # readable by the recovery console and by anyone with the SD card.
            logger.info("Wi-Fi hotspot '%s' created on %s", ssid_final, self.iface)
            if res.stderr.strip():
                logger.debug("nmcli stderr: %s", res.stderr.strip())
        except subprocess.CalledProcessError as exc:
            logger.error("Failed to create hotspot: %s", exc)
            if exc.stderr:
                logger.error("nmcli stderr: %s", exc.stderr.strip())

    # -------------------------------------------------------- AP profile ops

    def _wifi_profile_names(self) -> list[str]:
        """Names of every saved Wi-Fi connection profile."""
        try:
            res = self._run(["nmcli", "-t", "-f", "NAME,TYPE", "con", "show"])
        except subprocess.CalledProcessError as exc:
            logger.error("Could not list connection profiles: %s", exc)
            return []

        names = []
        for line in res.stdout.splitlines():
            fields = split_terse(line)
            if len(fields) >= 2 and fields[-1] == "802-11-wireless":
                names.append(":".join(fields[:-1]))
        return names

    def ap_profile_name(self) -> str | None:
        """Name of the AP-mode profile bound to our interface, if any.

        Found by inspection rather than assuming ``Hotspot``: nmcli appends a
        suffix when that name is taken, and an install that has been through a
        rename would otherwise get a second, competing profile.
        """
        for name in self._wifi_profile_names():
            try:
                res = self._run(
                    [
                        "nmcli", "-t", "-f",
                        "802-11-wireless.mode,connection.interface-name",
                        "con", "show", name,
                    ]
                )
            except subprocess.CalledProcessError:
                continue

            mode = iface = ""
            for line in res.stdout.splitlines():
                key, value = terse_value(line)
                if key == "802-11-wireless.mode":
                    mode = value
                elif key == "connection.interface-name":
                    iface = value
            if mode == "ap" and iface in ("", "--", self.iface):
                return name
        return None

    def profile_credentials(self, profile: str) -> tuple[str | None, str | None]:
        """Return the (ssid, psk) currently stored in *profile*."""
        try:
            res = self._run(
                [
                    "nmcli", "-s", "-t", "-f",
                    "802-11-wireless.ssid,802-11-wireless-security.psk",
                    "con", "show", profile,
                ]
            )
        except subprocess.CalledProcessError as exc:
            logger.debug("Could not read credentials from profile %s: %s", profile, exc)
            return None, None

        ssid = psk = None
        for line in res.stdout.splitlines():
            key, value = terse_value(line)
            if key == "802-11-wireless.ssid":
                ssid = value
            elif key == "802-11-wireless-security.psk":
                psk = value
        return ssid, psk

    def set_autoconnect(self, profile: str, enabled: bool) -> bool:
        """Make the AP profile come up on its own at boot, or stop it doing so.

        This is what gives the fallback ladder a rung *below* Python. The
        profile ships with ``autoconnect=false``, so before this the AP existed
        only for as long as some Python process had run; if both the watchdog
        and main.py were down there was no hotspot at all. The stored PSK is
        system-owned (``psk-flags=0``), so NetworkManager can raise the AP with
        no agent, no login session and no Cinemate.

        Tracks ``system.wifi_hotspot.enabled`` -- otherwise turning the hotspot
        off in settings would be undone by NetworkManager at the next boot.
        """
        try:
            self._run(
                [
                    "nmcli", "con", "modify", profile,
                    "connection.autoconnect", "yes" if enabled else "no",
                ]
            )
            return True
        except subprocess.CalledProcessError as exc:
            logger.warning("Could not set autoconnect on %s: %s", profile, exc)
            return False

    def apply_credentials(self, profile: str, ssid: str, password: str) -> bool:
        """Rewrite an existing AP profile in place and bring it back up."""
        try:
            self._run(
                [
                    "nmcli", "con", "modify", profile,
                    "802-11-wireless.ssid", ssid,
                    "802-11-wireless-security.psk", password,
                ]
            )
            self._run(["nmcli", "con", "up", profile])
            logger.info("Hotspot profile '%s' updated to SSID '%s'", profile, ssid)
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("Could not update hotspot profile %s: %s", profile, exc)
            if exc.stderr:
                logger.error("nmcli stderr: %s", exc.stderr.strip())
            return False

    # ---------------------------------------------------------- reconciliation

    def reconcile(self) -> Credentials:
        """Make the live AP match the resolved credentials. Idempotent.

        Called every pass by wifi-hotspot.service. Unlike create_hotspot(),
        which skips as soon as *any* hotspot is up, this notices that the live
        SSID no longer matches settings.jsonc and corrects it -- so editing the
        hotspot name now takes effect without a reboot.
        """
        creds = resolve_credentials(self.settings_path, self.cache_path)
        self.credentials = creds
        self._ssid_cfg, self._pw_cfg, self.enabled = (
            creds.ssid, creds.password, creds.enabled,
        )

        if creds.rung != RUNG_SETTINGS:
            logger.warning(
                "Hotspot credentials from rung %d (%s): %s",
                creds.rung, RUNG_NAMES.get(creds.rung, "?"), creds.reason,
            )

        profile = self.ap_profile_name()

        if not creds.enabled:
            # Leave a running AP alone -- tearing it down could strand an
            # operator who is connected over it right now -- but stop it
            # returning at the next boot.
            if profile:
                self.set_autoconnect(profile, False)
            logger.info("Wi-Fi hotspot disabled in settings")
            write_state(creds, self.state_path)
            return creds

        if profile is None or not self.is_hotspot_active():
            self.create_hotspot(ssid=creds.ssid, password=creds.password)
            profile = self.ap_profile_name()
        else:
            live_ssid, live_psk = self.profile_credentials(profile)
            if live_ssid != creds.ssid or (live_psk is not None and live_psk != creds.password):
                logger.info(
                    "Hotspot SSID drifted ('%s' -> '%s'); reconciling",
                    live_ssid, creds.ssid,
                )
                self.apply_credentials(profile, creds.ssid, creds.password)

        if profile:
            self.set_autoconnect(profile, True)

        write_state(creds, self.state_path)
        return creds


# ---------------------------------------------------------------------------
# Stand-alone usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    mgr = WiFiHotspotManager()  # self-contained - reads settings.jsonc
    mgr.reconcile()             # honours the ladder, publishes hotspot.state
