#!/usr/bin/env python3

import subprocess
import logging

class WiFiHotspotManager:
    def __init__(self, iface='wlan0'):
        self.iface = iface

    def create_hotspot(self, ssid, password):
        try:
            # Command to create Wi-Fi hotspot using nmcli
            cmd = ['sudo', 'nmcli', 'd', 'wifi', 'hotspot', 'ifname', self.iface, 'ssid', ssid, 'password', password]

            # Execute the command
            result = subprocess.run(cmd, check=True, capture_output=False, text=True, stderr=subprocess.PIPE)

            # Log the activation info
            activation_info = result.stderr.strip()
            logging.info(f"Wi-Fi hotspot '{ssid}' created successfully with password '{password}' on interface '{self.iface}'.")
            logging.debug(f"Activation info: {activation_info}")
            
        except subprocess.CalledProcessError as e:
            logging.error(f"Error: Failed to create Wi-Fi hotspot. {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    manager = WiFiHotspotManager()
    manager.create_hotspot('CinePi', '11111111')
