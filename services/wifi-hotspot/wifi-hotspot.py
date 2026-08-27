#!/usr/bin/env python3
"""Keep the Cinemate hotspot alive outside the main app process.

Runs under system python3, not the venv, and imports only stdlib plus
module.wifi_hotspot / module.config_loader (which are themselves stdlib-only).
A broken venv, a dead redis or a crashed Cinemate must not be able to take the
hotspot down -- that is the whole point of this service.

Each pass reconciles rather than merely creates: it resolves credentials
through the ladder in docs/hotspot-logic.md, corrects a drifted SSID, ensures
the NetworkManager profile autoconnects at boot, and publishes the active rung
to /var/lib/cinemate/hotspot.state for the recovery console to display.
"""

import logging
import sys
import time

sys.path.insert(0, "/home/pi/cinemate/src")

from module.wifi_hotspot import RUNG_NAMES, WiFiHotspotManager

RECONCILE_INTERVAL_S = 60


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [wifi-hotspot] %(levelname)s: %(message)s",
    )

    last_rung = None
    while True:
        try:
            creds = WiFiHotspotManager().reconcile()
            # Log the rung only when it changes, so a stable install does not
            # fill the journal with one identical line every minute.
            if creds.rung != last_rung:
                logging.info(
                    "Hotspot credentials rung %d (%s): %s",
                    creds.rung, RUNG_NAMES.get(creds.rung, "?"), creds.reason,
                )
                last_rung = creds.rung
        except Exception:
            # Never exit the loop. Restart=always would bring us back, but a
            # crash loop would also stop reconciling for RestartSec each time.
            logging.exception("Hotspot reconcile pass failed; retrying")

        time.sleep(RECONCILE_INTERVAL_S)


if __name__ == "__main__":
    main()
