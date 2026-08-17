#!/usr/bin/env python3
"""Cinemate recovery console -- diagnose and repair a camera that will not start.

A deliberately ugly, deliberately dependency-free web console on :8080, run by
its own root systemd service. When Cinemate fails to start, the operator can
still reach this from a phone over the camera's hotspot (http://10.42.0.1:8080)
to see *why* it failed, edit settings.jsonc and config.txt, and restart it --
with no laptop and no SSH.

  Operator docs: docs/recovery-console.md

THE ONE RULE
============
STANDARD LIBRARY ONLY, plus the vendored jsonc.py sibling. No flask, no jinja,
no redis, and nothing from src/module/. "The venv is broken" and "redis is
down" are supported failure modes that this console exists to survive; every
import it makes is another way for it to die exactly when it is needed.

The unit deliberately has no Wants= or After= on cinemate-autostart. That
coupling is the bug being fixed, not an oversight.

Everything degrades. Each configuration and validation step is a ladder whose
last rung still produces a usable answer -- see load_config() and
validate_settings_text(). A fallback that only fires when something else is
already broken is still tested; see _test/test_recovery_console.py.
"""

from __future__ import annotations

import argparse
import hmac
import html
import http.server
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, NamedTuple
from urllib.parse import parse_qs, urlparse

# The vendored JSONC stripper. Optional on purpose: if it is missing or broken,
# the settings-validation ladder must still reach its fail-open rung rather
# than take the whole console down.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import jsonc as _jsonc
except Exception:  # pragma: no cover - exercised by passing jsonc_module=None
    _jsonc = None

log = logging.getLogger("cinemate-recovery")

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

SETTINGS_PATH  = Path("/home/pi/cinemate/settings.jsonc")
CONF_PATH      = Path("/etc/cinemate-recovery.conf")
STATE_DIR      = Path("/var/lib/cinemate")
BACKUP_DIR     = STATE_DIR / "backups"
PENDING_PATH   = STATE_DIR / "config-pending.json"
HOTSPOT_STATE  = STATE_DIR / "hotspot.state"
FAILURE_FILE   = Path("/home/pi/.cache/cinemate/startup-failure.ansi")
CONFIG_TXT     = Path("/boot/firmware/config.txt")
VENV_PYTHON    = Path("/home/pi/.cinemate-env/bin/python3")
CINEMATE_SRC   = Path("/home/pi/cinemate/src")

#: Compiled-in defaults. A missing system.recovery block behaves exactly as
#: these -- requiring an edit to settings.jsonc to get a working recovery
#: console would be circular.
DEFAULTS = {
    "enabled": True,
    "port": 8080,
    "token": "",
    "allow_config_txt": False,
    "config_confirm_timeout_s": 300,
}

#: No free-form service name ever reaches subprocess.
ALLOWED_SERVICES = ("cinemate-autostart", "wifi-hotspot", "storage-automount")
ALLOWED_ACTIONS = ("start", "stop", "restart")

#: The AP must never be stopped from here -- that is the operator's only way
#: back in. It may only be restarted, behind the re-arm timer below.
PROTECTED_SERVICES = ("wifi-hotspot",)
HOTSPOT_REARM_S = 60

MAX_LOG_LINES = 2000
DEFAULT_LOG_LINES = 200
BACKUP_KEEP = 10

CONFIG_RUNG_SETTINGS, CONFIG_RUNG_CONF, CONFIG_RUNG_DEFAULTS = 1, 2, 3
VALIDATE_RUNG_VENV, VALIDATE_RUNG_STDLIB, VALIDATE_RUNG_NONE = 1, 2, 3


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------------------
# 4.3 Recovery console config ladder
# ---------------------------------------------------------------------------

class ConsoleConfig(NamedTuple):
    enabled: bool
    port: int
    token: str
    allow_config_txt: bool
    config_confirm_timeout_s: int
    rung: int
    reason: str


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off"):
            return False
    return default


def _as_int(value, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _merge(raw: dict, rung: int, reason: str) -> ConsoleConfig:
    """Coerce a raw mapping over DEFAULTS. Tolerates all-string values so the
    flat /etc/cinemate-recovery.conf rung shares this code path."""
    raw = raw if isinstance(raw, dict) else {}
    return ConsoleConfig(
        enabled=_as_bool(raw.get("enabled"), DEFAULTS["enabled"]),
        port=_as_int(raw.get("port"), DEFAULTS["port"]),
        token=str(raw.get("token", DEFAULTS["token"]) or ""),
        allow_config_txt=_as_bool(
            raw.get("allow_config_txt"), DEFAULTS["allow_config_txt"]
        ),
        config_confirm_timeout_s=_as_int(
            raw.get("config_confirm_timeout_s"), DEFAULTS["config_confirm_timeout_s"]
        ),
        rung=rung,
        reason=reason,
    )


def parse_conf(text: str) -> dict:
    """Parse the flat key=value fallback file. '#' comments, blank lines ok."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def load_config(
    settings_path: Path = SETTINGS_PATH,
    conf_path: Path = CONF_PATH,
    jsonc_module=_jsonc,
) -> ConsoleConfig:
    """Resolve console configuration through the three-rung ladder.

    1. settings.jsonc parses -> system.recovery
    2. it does not parse     -> /etc/cinemate-recovery.conf (installer-written)
    3. that is missing too   -> compiled-in DEFAULTS

    The bootstrap paradox this solves: "settings.jsonc is unparseable" is the
    console's primary use case, so it cannot read its own configuration only
    from there.
    """
    # -- rung 1 ------------------------------------------------------------
    try:
        text = Path(settings_path).read_text(encoding="utf-8")
        stripped = jsonc_module.strip_jsonc(text) if jsonc_module else text
        data = json.loads(stripped)
        if not isinstance(data, dict):
            raise ValueError("top level is not an object")
        block = data.get("system", {}).get("recovery", {})
        if not isinstance(block, dict):
            block = {}
        reason = (
            "settings.jsonc parsed"
            if block
            else "settings.jsonc parsed; no system.recovery block, using defaults"
        )
        return _merge(block, CONFIG_RUNG_SETTINGS, reason)
    except Exception as exc:
        settings_error = f"{type(exc).__name__}: {exc}"

    # -- rung 2 ------------------------------------------------------------
    try:
        raw = parse_conf(Path(conf_path).read_text(encoding="utf-8"))
        return _merge(
            raw,
            CONFIG_RUNG_CONF,
            f"settings.jsonc unusable ({settings_error}); using {conf_path}",
        )
    except Exception as exc:
        conf_error = f"{type(exc).__name__}: {exc}"

    # -- rung 3 ------------------------------------------------------------
    return _merge(
        {},
        CONFIG_RUNG_DEFAULTS,
        f"settings.jsonc unusable ({settings_error}); "
        f"{conf_path} unusable ({conf_error}); using built-in defaults",
    )


# ---------------------------------------------------------------------------
# 4.5 Write discipline
# ---------------------------------------------------------------------------

def atomic_write_bytes(path: Path, data: bytes, *, mode: int = 0o644) -> None:
    """Temp file in the same directory, fsync, os.replace, fsync the directory.

    The directory fsync is what makes the rename durable across power loss --
    the normal way this camera is switched off.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_name = None
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


def backup_paths(name: str, backup_dir: Path = BACKUP_DIR) -> list[Path]:
    """Existing backups for *name*, oldest first."""
    try:
        found = [
            p for p in Path(backup_dir).iterdir()
            if p.name.startswith(f"{name}.") and p.name.endswith(".bak")
        ]
    except OSError:
        return []
    return sorted(found, key=lambda p: p.name)


def prune_backups(name: str, backup_dir: Path = BACKUP_DIR, keep: int = BACKUP_KEEP):
    """Keep at most *keep* backups, and never the oldest one.

    The oldest backup is the pristine pre-Cinemate original -- the thing an
    operator wants after ten bad edits in a row. So retention is "the oldest,
    plus the keep-1 most recent"; pruning happens in the middle.
    """
    existing = backup_paths(name, backup_dir)
    if len(existing) <= keep:
        return []

    oldest, rest = existing[0], existing[1:]
    survivors = rest[-(keep - 1):] if keep > 1 else []
    doomed = [p for p in rest if p not in survivors]

    removed = []
    for path in doomed:
        try:
            path.unlink()
            removed.append(path)
        except OSError as exc:
            log.warning("Could not prune backup %s: %s", path, exc)
    log.info("Pruned %d backup(s) of %s, kept oldest %s", len(removed), name, oldest.name)
    return removed


def backup_file(
    path: Path, backup_dir: Path = BACKUP_DIR, keep: int = BACKUP_KEEP
) -> Path | None:
    """Copy *path* into the backup directory. Returns the backup path.

    Returns None when the source does not exist -- writing a file that was
    never there is legitimate and must not be blocked by a failed backup.
    """
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        log.info("No backup taken for %s: %s", path, exc)
        return None

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = utc_stamp()
    target = backup_dir / f"{path.name}.{stamp}.bak"
    counter = 1
    while target.exists():  # two writes inside one second
        target = backup_dir / f"{path.name}.{stamp}-{counter}.bak"
        counter += 1

    atomic_write_bytes(target, data, mode=0o600)
    prune_backups(path.name, backup_dir, keep)
    return target


def write_config_file(
    path: Path, text: str, backup_dir: Path = BACKUP_DIR, keep: int = BACKUP_KEEP
) -> Path | None:
    """Back up, then atomically replace. The order is not negotiable."""
    backup = backup_file(path, backup_dir, keep)
    atomic_write_bytes(Path(path), text.encode("utf-8"))
    return backup


# ---------------------------------------------------------------------------
# 4.4 Settings validation ladder
# ---------------------------------------------------------------------------

class Validation(NamedTuple):
    ok: bool
    rung: int
    message: str
    validated: bool   # False => rung 3 fired; the write is unverified


_VENV_VALIDATOR = """
import sys
sys.path.insert(0, sys.argv[1])
from module.config_loader import SettingsLoadError, load_settings
try:
    load_settings(sys.argv[2])
except SettingsLoadError as exc:
    sys.stdout.write(exc.format_for_cli(use_color=False))
    sys.exit(2)
except Exception as exc:
    sys.stdout.write("%s: %s" % (type(exc).__name__, exc))
    sys.exit(3)
sys.exit(0)
"""


def validate_settings_text(
    text: str,
    *,
    venv_python: Path = VENV_PYTHON,
    src_dir: Path = CINEMATE_SRC,
    jsonc_module=_jsonc,
    runner: Callable = subprocess.run,
) -> Validation:
    """Validate candidate settings.jsonc content through the three-rung ladder.

    1. venv python + module.config_loader.load_settings -> the EXACT error the
       operator would see on tty1, with line, column and context. No duplicated
       parsing logic.
    2. venv missing or import fails -> vendored jsonc.py + json.loads, which
       gives a generic parse error.
    3. neither available -> allow the write, labelled "unvalidated".

    Rung 3 is deliberately fail-OPEN. The file being edited is already broken;
    refusing to write it would strand the operator with no way to fix it.
    Safety comes from the backup, not from the refusal.
    """
    # -- rung 1 ------------------------------------------------------------
    if Path(venv_python).exists() and Path(src_dir).exists():
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".jsonc", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(text)
                tmp_path = tmp.name
            proc = runner(
                [str(venv_python), "-c", _VENV_VALIDATOR, str(src_dir), tmp_path],
                capture_output=True, text=True, timeout=20, check=False,
            )
            if proc.returncode == 0:
                return Validation(True, VALIDATE_RUNG_VENV, "Valid.", True)
            if proc.returncode == 2:
                return Validation(
                    False, VALIDATE_RUNG_VENV, proc.stdout.strip() or "Invalid.", True
                )
            # returncode 3 or anything else: the validator itself failed, so
            # fall through rather than reporting a bogus verdict.
            log.warning("venv validator unusable (rc=%s): %s",
                        proc.returncode, (proc.stderr or proc.stdout)[:400])
        except Exception as exc:
            log.warning("venv validation rung unavailable: %s", exc)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # -- rung 2 ------------------------------------------------------------
    if jsonc_module is not None:
        try:
            json.loads(jsonc_module.strip_jsonc(text))
            return Validation(
                True, VALIDATE_RUNG_STDLIB,
                "Valid (checked without the Cinemate venv -- syntax only).", True,
            )
        except Exception as exc:
            return Validation(
                False, VALIDATE_RUNG_STDLIB,
                f"{type(exc).__name__}: {exc}", True,
            )

    # -- rung 3: fail open --------------------------------------------------
    return Validation(
        True, VALIDATE_RUNG_NONE,
        "UNVALIDATED: no working validator on this system. The file was written "
        "as given and has NOT been checked. A backup of the previous content was "
        "taken first.",
        False,
    )


# ---------------------------------------------------------------------------
# 4.6 config.txt confirm-or-revert
# ---------------------------------------------------------------------------

class Pending(NamedTuple):
    backup: str
    target: str
    armed_at: float
    timeout_s: int


def read_pending(path: Path | None = None) -> Pending | None:
    # Resolved at call time, not bound at def time, so the module constant
    # stays overridable (tests, and any future relocation of the state dir).
    path = Path(path) if path is not None else PENDING_PATH
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return Pending(
            backup=str(raw["backup"]),
            target=str(raw["target"]),
            armed_at=float(raw["armed_at"]),
            timeout_s=int(raw["timeout_s"]),
        )
    except Exception:
        return None


def arm_pending(
    backup: Path, target: Path, timeout_s: int,
    path: Path = PENDING_PATH, *, now: Callable[[], float] = time.time,
) -> Pending:
    """Record that a config.txt write is awaiting confirmation."""
    pending = Pending(str(backup), str(target), float(now()), int(timeout_s))
    atomic_write_bytes(
        Path(path), (json.dumps(pending._asdict(), indent=2) + "\n").encode("utf-8")
    )
    log.warning("config.txt change armed; confirm within %ss or it reverts", timeout_s)
    return pending


def clear_pending(path: Path = PENDING_PATH) -> bool:
    try:
        Path(path).unlink()
        log.info("config.txt change confirmed; pending marker cleared")
        return True
    except OSError:
        return False


def pending_remaining(pending: Pending, *, now: Callable[[], float] = time.time) -> float:
    return max(0.0, pending.armed_at + pending.timeout_s - now())


def revert_pending(
    pending: Pending,
    path: Path = PENDING_PATH,
    *,
    copy: Callable = shutil.copyfile,
    reboot: Callable = None,
    clear: Callable = None,
) -> bool:
    """Restore the backup, clear the marker, reboot.

    This recovers a boot that *succeeds but is broken* -- no camera, no HDMI,
    no network. It cannot recover a Pi that never reaches userspace; for that
    the only fallback is pulling the SD card (docs/recovery-console.md).
    """
    clear = clear or (lambda: clear_pending(path))
    reboot = reboot or (lambda: subprocess.run(["reboot"], check=False))

    restored = False
    try:
        copy(pending.backup, pending.target)
        restored = True
        log.error("config.txt was not confirmed in time; restored %s", pending.backup)
    except Exception as exc:
        log.error("Could not restore %s over %s: %s",
                  pending.backup, pending.target, exc)
    clear()
    reboot()
    return restored


# ---------------------------------------------------------------------------
# Service control
# ---------------------------------------------------------------------------

class ServiceError(ValueError):
    pass


def systemctl(
    action: str, service: str, *, runner: Callable = subprocess.run
) -> subprocess.CompletedProcess:
    """Run one allowlisted systemctl action. Never interpolates free-form input."""
    if service not in ALLOWED_SERVICES:
        raise ServiceError(f"service not allowed: {service!r}")
    if action not in ALLOWED_ACTIONS:
        raise ServiceError(f"action not allowed: {action!r}")
    if action == "stop" and service in PROTECTED_SERVICES:
        raise ServiceError(
            f"{service} may not be stopped from the recovery console -- "
            "it is the operator's only way back in"
        )
    cmd = ["systemctl", action, f"{service}.service"]
    try:
        return runner(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        # No systemd (or it is unreachable). Report it as a failed command
        # rather than a 500: the operator still needs the rest of the page.
        return subprocess.CompletedProcess(cmd, 127, "", f"{type(exc).__name__}: {exc}")


def service_state(service: str, *, runner: Callable = subprocess.run) -> str:
    if service not in ALLOWED_SERVICES:
        raise ServiceError(f"service not allowed: {service!r}")
    try:
        proc = runner(
            ["systemctl", "is-active", f"{service}.service"],
            capture_output=True, text=True, check=False,
        )
        return (proc.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"


def journal_tail(
    service: str, lines: int = DEFAULT_LOG_LINES, *, runner: Callable = subprocess.run
) -> str:
    if service not in ALLOWED_SERVICES:
        raise ServiceError(f"service not allowed: {service!r}")
    lines = max(1, min(int(lines), MAX_LOG_LINES))
    try:
        proc = runner(
            ["journalctl", "-u", f"{service}.service", "-n", str(lines), "--no-pager"],
            capture_output=True, text=True, check=False,
        )
        return proc.stdout or proc.stderr or "(no output)"
    except Exception as exc:
        return f"(journalctl unavailable: {exc})"


# ---------------------------------------------------------------------------
# ANSI -> HTML
# ---------------------------------------------------------------------------

_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")
_SGR_COLORS = {
    30: "#000000", 31: "#cc0000", 32: "#4e9a06", 33: "#c4a000",
    34: "#3465a4", 35: "#75507b", 36: "#06989a", 37: "#d3d7cf",
    90: "#555753", 91: "#ef2929", 92: "#8ae234", 93: "#fce94f",
    94: "#729fcf", 95: "#ad7fa8", 96: "#34e2e2", 97: "#eeeeec",
}


def ansi_to_html(text: str) -> str:
    """Render the tty1 startup-failure block as HTML, colours intact.

    main.py writes that block with SGR escapes (config_loader.ANSI_RED etc).
    Showing it verbatim is the point of /why: the operator sees the same text
    the camera would have shown on the monitor it is not connected to.
    """
    out: list[str] = []
    open_spans = 0
    pos = 0

    for match in _SGR_RE.finditer(text):
        out.append(html.escape(text[pos:match.start()]))
        pos = match.end()

        codes = [int(c) for c in match.group(1).split(";") if c.isdigit()]
        if not codes or 0 in codes:
            out.append("</span>" * open_spans)
            open_spans = 0
            codes = [c for c in codes if c != 0]
            if not codes:
                continue

        styles = []
        for code in codes:
            if code == 1:
                styles.append("font-weight:bold")
            elif code in _SGR_COLORS:
                styles.append(f"color:{_SGR_COLORS[code]}")
        if styles:
            out.append(f'<span style="{";".join(styles)}">')
            open_spans += 1

    out.append(html.escape(text[pos:]))
    out.append("</span>" * open_spans)
    return "".join(out)


# ---------------------------------------------------------------------------
# System facts for the dashboard
# ---------------------------------------------------------------------------

def read_hotspot_state(path: Path | None = None) -> dict | None:
    path = Path(path) if path is not None else HOTSPOT_STATE
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def read_uptime(path: str = "/proc/uptime") -> str:
    try:
        seconds = float(Path(path).read_text().split()[0])
    except Exception:
        return "unknown"
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def read_disk_free(path: str = "/") -> str:
    try:
        usage = shutil.disk_usage(path)
    except Exception:
        return "unknown"
    free_gb = usage.free / (1024 ** 3)
    pct = 100.0 * usage.free / usage.total if usage.total else 0.0
    return f"{free_gb:.1f} GB free ({pct:.0f}%)"


def read_failure_block(path: Path | None = None) -> str | None:
    """The persisted tty1 failure block, or None when Cinemate started clean."""
    path = Path(path) if path is not None else FAILURE_FILE
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, system-ui, sans-serif; margin: 0;
       padding: 1rem; line-height: 1.45; max-width: 60rem; }
h1 { font-size: 1.3rem; margin: 0 0 .2rem; }
h2 { font-size: 1.05rem; margin: 1.5rem 0 .4rem; }
nav a { display: inline-block; margin-right: .9rem; padding: .35rem 0; }
table { border-collapse: collapse; width: 100%; margin: .4rem 0; }
td, th { text-align: left; padding: .35rem .5rem; border-bottom: 1px solid #8884; }
pre { background: #8881; padding: .7rem; overflow-x: auto; font-size: .8rem;
      white-space: pre-wrap; word-break: break-word; }
textarea { width: 100%; min-height: 24rem; font-family: ui-monospace, monospace;
           font-size: .8rem; }
button { font-size: 1rem; padding: .5rem 1rem; margin: .2rem .3rem .2rem 0; }
.banner { padding: .8rem; margin: .5rem 0; border-radius: 4px; }
.red { background: #cc000022; border: 2px solid #cc0000; }
.amber { background: #c4a00022; border: 1px solid #c4a000; }
.green { background: #4e9a0622; border: 1px solid #4e9a06; }
.ok { color: #4e9a06; font-weight: bold; }
.bad { color: #cc0000; font-weight: bold; }
.muted { opacity: .7; font-size: .85rem; }
"""


def page(title: str, body: str, *, banner: str = "") -> bytes:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>"
        f"<h1>Cinemate recovery console</h1>"
        "<nav><a href='/'>Status</a><a href='/why'>Why it failed</a>"
        "<a href='/log'>Log</a><a href='/edit/settings'>settings.jsonc</a></nav>"
        f"{banner}{body}"
        f"<p class='muted'>{html.escape(utc_now())} &middot; "
        "recovery console, stdlib only</p>"
        "</body></html>"
    ).encode("utf-8")


def token_field(cfg: ConsoleConfig) -> str:
    if not cfg.token:
        return ""
    return ("<p><label>Access token "
            "<input type='password' name='token' autocomplete='current-password'>"
            "</label></p>")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class RecoveryHandler(http.server.BaseHTTPRequestHandler):
    server_version = "cinemate-recovery"
    protocol_version = "HTTP/1.1"

    # Injected by make_server()
    config: ConsoleConfig = None
    # staticmethod, not a bare assignment: a plain function stored on a class
    # is a descriptor, so `self.runner(cmd)` would silently pass the handler
    # as subprocess.run's first argument. Found by the live smoke test, not
    # by the unit tests -- those call the module functions directly.
    runner = staticmethod(subprocess.run)

    # -- plumbing ----------------------------------------------------------

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    def _send(self, body: bytes, status: int = 200, ctype="text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_form(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return {}
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    def _authorised(self, form: dict, query: dict) -> bool:
        """Mutating routes only. Read-only routes stay open so a locked-out
        operator can always still diagnose (plan section 8)."""
        expected = self.config.token
        if not expected:
            return True
        supplied = (
            form.get("token")
            or query.get("token", [""])[0]
            or self.headers.get("X-Auth-Token", "")
        )
        return hmac.compare_digest(str(supplied), str(expected))

    def _audit(self, what: str):
        log.warning("ACTION %s from %s", what, self.client_address[0])

    def _banner(self) -> str:
        pending = read_pending()
        if not pending:
            return ""
        left = int(pending_remaining(pending))
        return (
            "<div class='banner red'><strong>config.txt change awaiting "
            f"confirmation.</strong><br>Reverting in {left}s and rebooting "
            "unless you confirm."
            "<form method='post' action='/confirm-config'>"
            f"{token_field(self.config)}"
            "<button type='submit'>KEEP THIS CONFIG</button></form></div>"
        )

    # -- routing -----------------------------------------------------------

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        route = url.path.rstrip("/") or "/"
        try:
            if route == "/health":
                return self._send(b"ok\n", ctype="text/plain; charset=utf-8")
            if route == "/":
                return self._send(self.view_status())
            if route == "/why":
                return self._send(self.view_why())
            if route == "/log":
                return self._send(self.view_log(query))
            if route == "/edit/settings":
                return self._send(self.view_edit_settings())
            if route == "/edit/config":
                return self._send(self.view_edit_config())
            return self._send(page("Not found", "<p>No such page.</p>"), 404)
        except Exception:
            log.exception("GET %s failed", self.path)
            return self._send(page("Error", "<p>Internal error; see journal.</p>"), 500)

    def do_POST(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        form = self._read_form()
        route = url.path.rstrip("/") or "/"

        if not self._authorised(form, query):
            self._audit(f"DENIED {route} (bad token)")
            return self._send(page("Denied", "<p>Invalid access token.</p>"), 403)

        try:
            if route.startswith("/service/"):
                return self._send(self.act_service(route))
            if route == "/edit/settings":
                return self._send(self.act_edit_settings(form))
            if route == "/edit/config":
                return self._send(self.act_edit_config(form))
            if route == "/confirm-config":
                return self._send(self.act_confirm_config())
            return self._send(page("Not found", "<p>No such action.</p>"), 404)
        except ServiceError as exc:
            self._audit(f"REFUSED {route}: {exc}")
            return self._send(page("Refused", f"<p>{html.escape(str(exc))}</p>"), 400)
        except Exception:
            log.exception("POST %s failed", self.path)
            return self._send(page("Error", "<p>Internal error; see journal.</p>"), 500)

    # -- views -------------------------------------------------------------

    def view_status(self) -> bytes:
        rows = []
        for svc in ALLOWED_SERVICES:
            state = service_state(svc, runner=self.runner)
            css = "ok" if state == "active" else "bad"
            stop = ("" if svc in PROTECTED_SERVICES
                    else "<button name='a' value='stop'>Stop</button>")
            rows.append(
                f"<tr><td>{html.escape(svc)}</td>"
                f"<td class='{css}'>{html.escape(state)}</td><td>"
                f"<form method='post' action='/service/{svc}/restart' "
                "style='display:inline'>"
                f"{token_field(self.config)}"
                "<button type='submit'>Restart</button></form></td></tr>"
            )

        hotspot = read_hotspot_state()
        if hotspot:
            rung = hotspot.get("rung")
            css = "green" if rung == 1 else "amber"
            hot = (
                f"<div class='banner {css}'>Hotspot SSID "
                f"<strong>{html.escape(str(hotspot.get('ssid', '?')))}</strong> "
                f"from rung {html.escape(str(rung))} "
                f"({html.escape(str(hotspot.get('rung_name', '?')))})<br>"
                f"<span class='muted'>{html.escape(str(hotspot.get('reason', '')))}"
                "</span></div>"
            )
        else:
            hot = ("<p class='muted'>No hotspot state file yet "
                   "(wifi-hotspot.service writes it on its first pass).</p>")

        failure = read_failure_block()
        why = ("<p><a href='/why'>Cinemate recorded a startup failure &rarr;</a></p>"
               if failure else
               "<p class='muted'>No recorded startup failure.</p>")

        body = (
            f"{hot}"
            "<h2>Services</h2>"
            f"<table><tr><th>Service</th><th>State</th><th></th></tr>"
            f"{''.join(rows)}</table>"
            f"{why}"
            "<h2>System</h2><table>"
            f"<tr><td>Uptime</td><td>{html.escape(read_uptime())}</td></tr>"
            f"<tr><td>Disk</td><td>{html.escape(read_disk_free())}</td></tr>"
            f"<tr><td>Config rung</td><td>{self.config.rung} "
            f"<span class='muted'>{html.escape(self.config.reason)}</span></td></tr>"
            "</table>"
        )
        if self.config.allow_config_txt:
            body += "<p><a href='/edit/config'>Edit config.txt &rarr;</a></p>"
        return page("Status", body, banner=self._banner())

    def view_why(self) -> bytes:
        block = read_failure_block()
        if block is None:
            body = ("<p>No startup failure recorded. Cinemate either started "
                    "cleanly or has not run since the file was last cleared.</p>")
        else:
            body = f"<pre>{ansi_to_html(block)}</pre>"
        return page("Why it failed", body, banner=self._banner())

    def view_log(self, query: dict) -> bytes:
        service = query.get("service", ["cinemate-autostart"])[0]
        if service not in ALLOWED_SERVICES:
            service = "cinemate-autostart"
        try:
            lines = int(query.get("n", [DEFAULT_LOG_LINES])[0])
        except ValueError:
            lines = DEFAULT_LOG_LINES
        text = journal_tail(service, lines, runner=self.runner)
        links = " ".join(
            f"<a href='/log?service={s}'>{html.escape(s)}</a>" for s in ALLOWED_SERVICES
        )
        body = (f"<p>{links}</p><pre>{html.escape(text)}</pre>")
        return page(f"Log: {service}", body, banner=self._banner())

    def view_edit_settings(self, message: str = "") -> bytes:
        try:
            text = SETTINGS_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            text = ""
            message += f"<div class='banner amber'>Could not read {SETTINGS_PATH}: {html.escape(str(exc))}</div>"
        body = (
            f"{message}"
            "<form method='post' action='/edit/settings'>"
            f"<textarea name='content' spellcheck='false'>{html.escape(text)}</textarea>"
            f"{token_field(self.config)}"
            "<button type='submit'>Save</button>"
            "<button type='submit' name='restart' value='1'>Save and restart Cinemate</button>"
            "</form>"
        )
        return page("Edit settings.jsonc", body, banner=self._banner())

    def view_edit_config(self, message: str = "") -> bytes:
        if not self.config.allow_config_txt:
            return page(
                "Disabled",
                "<p>config.txt editing is disabled. Set "
                "<code>system.recovery.allow_config_txt</code> to true in "
                "settings.jsonc to enable it.</p>",
            )
        try:
            text = CONFIG_TXT.read_text(encoding="utf-8")
        except OSError as exc:
            text = ""
            message += f"<div class='banner amber'>Could not read {CONFIG_TXT}: {html.escape(str(exc))}</div>"
        body = (
            "<div class='banner red'><strong>A bad config.txt can make this Pi "
            "unbootable, and nothing running on the Pi can recover that.</strong>"
            "<br>If it will not boot: power off, pull the SD card, mount the FAT "
            "boot partition on any Mac or Windows machine, and restore config.txt "
            f"from a <code>.bak</code> in <code>{BACKUP_DIR}</code>.<br>"
            f"After saving you have {self.config.config_confirm_timeout_s}s to "
            "confirm, or the change reverts and the Pi reboots.</div>"
            f"{message}"
            "<form method='post' action='/edit/config'>"
            f"<textarea name='content' spellcheck='false'>{html.escape(text)}</textarea>"
            f"{token_field(self.config)}"
            "<button type='submit'>Save and arm revert</button></form>"
        )
        return page("Edit config.txt", body, banner=self._banner())

    # -- actions -----------------------------------------------------------

    def act_service(self, route: str) -> bytes:
        parts = [p for p in route.split("/") if p]
        if len(parts) != 3:
            raise ServiceError("malformed service action")
        _, service, action = parts
        self._audit(f"systemctl {action} {service}")
        proc = systemctl(action, service, runner=self.runner)

        if service == "wifi-hotspot" and action == "restart":
            self._arm_hotspot_rearm()

        detail = (proc.stderr or proc.stdout or "").strip()
        css = "green" if proc.returncode == 0 else "red"
        body = (
            f"<div class='banner {css}'>systemctl {html.escape(action)} "
            f"{html.escape(service)} &rarr; exit {proc.returncode}</div>"
            + (f"<pre>{html.escape(detail)}</pre>" if detail else "")
            + "<p><a href='/'>Back to status</a></p>"
        )
        return page("Service", body, banner=self._banner())

    def _arm_hotspot_rearm(self):
        """Restore the AP if a hotspot restart does not bring it back (4.7)."""
        def rearm():
            time.sleep(HOTSPOT_REARM_S)
            state = service_state("wifi-hotspot", runner=self.runner)
            if state != "active":
                log.error("Hotspot did not return after restart; re-arming")
                systemctl("start", "wifi-hotspot", runner=self.runner)

        threading.Thread(target=rearm, daemon=True).start()

    def act_edit_settings(self, form: dict) -> bytes:
        content = form.get("content", "")
        result = validate_settings_text(content, runner=self.runner)

        if not result.ok:
            msg = (f"<div class='banner red'><strong>Not saved.</strong> "
                   f"Rung {result.rung} validation failed:"
                   f"<pre>{html.escape(result.message)}</pre></div>")
            return self.view_edit_settings(msg)

        self._audit(f"write {SETTINGS_PATH} (rung {result.rung})")
        backup = write_config_file(SETTINGS_PATH, content)
        css = "green" if result.validated else "amber"
        msg = (f"<div class='banner {css}'>Saved. {html.escape(result.message)}<br>"
               f"<span class='muted'>Backup: {html.escape(str(backup))}</span></div>")

        if form.get("restart"):
            self._audit("systemctl restart cinemate-autostart (after settings save)")
            proc = systemctl("restart", "cinemate-autostart", runner=self.runner)
            msg += (f"<div class='banner green'>Restart requested &rarr; exit "
                    f"{proc.returncode}</div>")
        return self.view_edit_settings(msg)

    def act_edit_config(self, form: dict) -> bytes:
        if not self.config.allow_config_txt:
            raise ServiceError("config.txt editing is disabled")

        content = form.get("content", "")
        self._audit(f"write {CONFIG_TXT}")
        backup = write_config_file(CONFIG_TXT, content)
        if backup is None:
            return self.view_edit_config(
                "<div class='banner red'>Refused: could not back up config.txt "
                "first, and this edit is not safe without a backup.</div>"
            )
        arm_pending(backup, CONFIG_TXT, self.config.config_confirm_timeout_s)
        start_revert_watchdog(self.config)
        return self.view_edit_config(
            f"<div class='banner amber'>Saved and armed. Backup: "
            f"{html.escape(str(backup))}. Reboot to apply, then confirm.</div>"
        )

    def act_confirm_config(self) -> bytes:
        self._audit("confirm config.txt")
        cleared = clear_pending()
        body = ("<div class='banner green'>Configuration kept.</div>"
                if cleared else
                "<div class='banner amber'>Nothing was pending.</div>")
        return page("Confirmed", body + "<p><a href='/'>Back to status</a></p>")


# ---------------------------------------------------------------------------
# Revert watchdog
# ---------------------------------------------------------------------------

_watchdog_started = threading.Event()


def start_revert_watchdog(cfg: ConsoleConfig, *, path: Path = PENDING_PATH):
    """Countdown for an unconfirmed config.txt change.

    Deliberately NOT a second systemd unit (plan section 7): it lives in this
    process and inherits its Restart=always, so a crash re-reads the marker on
    the way back up and the countdown resumes.
    """
    if _watchdog_started.is_set():
        return
    pending = read_pending(path)
    if not pending:
        return
    _watchdog_started.set()

    def watch():
        try:
            while True:
                current = read_pending(path)
                if current is None:
                    log.info("config.txt change confirmed; watchdog standing down")
                    return
                if pending_remaining(current) <= 0:
                    revert_pending(current, path)
                    return
                time.sleep(1)
        finally:
            _watchdog_started.clear()

    threading.Thread(target=watch, daemon=True).start()
    log.warning("config.txt revert watchdog armed (%ss)", pending.timeout_s)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def make_server(cfg: ConsoleConfig, *, bind: str = "0.0.0.0"):
    handler = type("BoundRecoveryHandler", (RecoveryHandler,), {"config": cfg})
    server = http.server.ThreadingHTTPServer((bind, cfg.port), handler)
    server.daemon_threads = True
    return server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Cinemate recovery console")
    parser.add_argument("--port", type=int, help="override the configured port")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--check", action="store_true",
                        help="resolve config, print it, and exit")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, stream=sys.stdout,
        format="%(asctime)s [recovery] %(levelname)s: %(message)s",
    )

    cfg = load_config()
    if args.port:
        cfg = cfg._replace(port=args.port)

    if args.check:
        print(json.dumps(cfg._asdict(), indent=2))
        return 0

    log.info("Config rung %d: %s", cfg.rung, cfg.reason)
    if not cfg.enabled:
        log.warning("Recovery console disabled in configuration; idling")
        # Idle rather than exit: exiting under Restart=always is a crash loop,
        # and the operator may re-enable it by editing settings.jsonc.
        while True:
            time.sleep(3600)

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("Could not create %s: %s", STATE_DIR, exc)

    start_revert_watchdog(cfg)

    server = make_server(cfg, bind=args.bind)
    log.info("Listening on %s:%d (token %s, config.txt editing %s)",
             args.bind, cfg.port,
             "required" if cfg.token else "not set",
             "enabled" if cfg.allow_config_txt else "disabled")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
