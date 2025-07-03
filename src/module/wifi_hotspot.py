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
import subprocess
from pathlib import Path
from typing import Final, Optional

logger = logging.getLogger(__name__)

__all__ = ["WiFiHotspotManager"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_SSID:  Final[str] = "CinePi"
DEFAULT_PASS:  Final[str] = "11111111"  # 8 chars → nmcli minimum
SETTINGS_PATH: Final[Path] = Path("/home/pi/cinemate/src/settings.json")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_settings(path: Path = SETTINGS_PATH) -> dict:
    """Return settings as dict; empty dict on any error."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # pragma: no‑cover – broad OK for util
        logger.debug("Could not parse %s: %s", path, exc)
        return {}


def _extract_credentials(cfg: dict | None) -> tuple[str, str]:
    """Extract SSID & password from an already‑loaded *settings* dict.

    Returns the safe defaults when cfg is *None* or keys are missing.
    """
    wifi_cfg = (cfg or {}).get("system", {}).get("wifi_hotspot", {})
    ssid = wifi_cfg.get("name", DEFAULT_SSID) or DEFAULT_SSID
    pw = wifi_cfg.get("password", DEFAULT_PASS) or DEFAULT_PASS

    if len(pw) < 8:
        logger.warning("Password from settings < 8 chars – using default.")
        pw = DEFAULT_PASS
    return ssid, pw

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
    ) -> None:
        """Create a manager.

        Args:
            iface:       Network interface (usually *wlan0*).
            settings:    An already‑loaded *settings.json* dict. When *None*,
                         the file at *settings_path* is parsed internally.
            settings_path: Where to look for *settings.json* when *settings*
                         is *None*.
        """
        self.iface = iface

        if settings is not None:  # caller already did the JSON I/O
            self._ssid_cfg, self._pw_cfg = _extract_credentials(settings)
        else:  # self‑contained usage – read from disk
            self._ssid_cfg, self._pw_cfg = _extract_credentials(
                _load_settings(settings_path)
            )

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
        if self.is_hotspot_active():
            logger.info("Wi‑Fi hotspot already active – skipping creation.")
            return

        # cascade: explicit arg → settings → hard‑coded default
        ssid_final = ssid or self._ssid_cfg or DEFAULT_SSID
        pw_final = password or self._pw_cfg or DEFAULT_PASS

        if len(pw_final) < 8:
            logger.warning("Provided password < 8 chars – using default.")
            pw_final = DEFAULT_PASS

        cmd = [
            "sudo", "nmcli", "d", "wifi", "hotspot",
            "ifname", self.iface,
            "ssid", ssid_final,
            "password", pw_final,
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(
                "Wi‑Fi hotspot '%s' created on %s (pwd: %s)",
                ssid_final, self.iface, pw_final,
            )
            if res.stderr.strip():
                logger.debug("nmcli stderr: %s", res.stderr.strip())
        except subprocess.CalledProcessError as exc:
            logger.error("Failed to create hotspot: %s", exc)
            if exc.stderr:
                logger.error("nmcli stderr: %s", exc.stderr.strip())

# ---------------------------------------------------------------------------
# Stand‑alone usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    mgr = WiFiHotspotManager()  # self‑contained – reads settings.json
    mgr.create_hotspot()        # honours settings or falls back
