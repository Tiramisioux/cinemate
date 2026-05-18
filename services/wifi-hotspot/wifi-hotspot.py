#!/usr/bin/env python3
"""Keep the Cinemate hotspot alive outside the main app process."""

import logging
import sys
import time

sys.path.insert(0, "/home/pi/cinemate/src")

from module.wifi_hotspot import WiFiHotspotManager


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [wifi-hotspot] %(levelname)s: %(message)s",
    )

    while True:
        mgr = WiFiHotspotManager()
        if mgr.enabled and not mgr.is_hotspot_active():
            mgr.create_hotspot()
        time.sleep(60)


if __name__ == "__main__":
    main()
