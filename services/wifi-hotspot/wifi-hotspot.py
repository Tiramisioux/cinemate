#!/usr/bin/env python3
"""Simple watchdog service for a Wi-Fi hotspot.

This script keeps a NetworkManager hotspot active even when the main
``cinemate`` application is not running.  The SSID and password are
read from ``/home/pi/cinemate/src/settings.json`` so multiple cameras
can use different networks.
"""
import json
import logging
import subprocess
import time
from pathlib import Path

SETTINGS_PATH = Path("/home/pi/cinemate/src/settings.json")
DEFAULT_SSID = "CinePi"
DEFAULT_PASS = "11111111"  # nmcli minimum


def load_credentials(path: Path = SETTINGS_PATH) -> tuple[str, str]:
    """Return (ssid, password) from *settings.json* with fallbacks."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        wifi_cfg = cfg.get("system", {}).get("wifi_hotspot", {})
        ssid = wifi_cfg.get("name", DEFAULT_SSID) or DEFAULT_SSID
        pw = wifi_cfg.get("password", DEFAULT_PASS) or DEFAULT_PASS
        if len(pw) < 8:
            logging.warning("Password in settings <8 chars – using default")
            pw = DEFAULT_PASS
        return ssid, pw
    except Exception as exc:  # pragma: no cover - best effort
        logging.error("Failed to load %s: %s", path, exc)
        return DEFAULT_SSID, DEFAULT_PASS


def is_hotspot_active() -> bool:
    """Return ``True`` if an nmcli hotspot connection is active."""
    try:
        res = subprocess.run(
            ["nmcli", "con", "show", "--active"],
            capture_output=True, text=True, check=True
        )
        return any(
            "wifi" in line and "Hotspot" in line
            for line in res.stdout.splitlines()
        )
    except subprocess.CalledProcessError as exc:
        logging.error("Error checking hotspot status: %s", exc)
        return False


def create_hotspot(ssid: str, password: str, iface: str = "wlan0") -> None:
    """Create a Wi‑Fi hotspot via ``nmcli``."""
    cmd = [
        "nmcli", "device", "wifi", "hotspot",
        "ifname", iface,
        "ssid", ssid,
        "password", password,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logging.info("Hotspot '%s' started on %s", ssid, iface)
    except subprocess.CalledProcessError as exc:
        logging.error("Failed to create hotspot: %s", exc)
        if exc.stderr:
            logging.error("nmcli stderr: %s", exc.stderr.strip())


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [wifi-hotspot] %(levelname)s: %(message)s",
    )

    while True:
        ssid, pw = load_credentials()
        if not is_hotspot_active():
            create_hotspot(ssid, pw)
        time.sleep(60)


if __name__ == "__main__":
    main()
