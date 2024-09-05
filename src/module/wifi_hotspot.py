#!/usr/bin/env python3
import subprocess
import logging

class WiFiHotspotManager:
    def __init__(self, iface='wlan0'):
        self.iface = iface

    def is_hotspot_active(self):
        try:
            result = subprocess.run(['nmcli', 'con', 'show', '--active'], 
                                    capture_output=True, text=True, check=True)
            return any('wifi' in line and 'Hotspot' in line for line in result.stdout.split('\n'))
        except subprocess.CalledProcessError as e:
            logging.error(f"Error checking hotspot status: {e}")
            return False

    def create_hotspot(self, ssid, password):
        if self.is_hotspot_active():
            logging.info("WiFi hotspot is already active. Skipping creation.")
            return

        try:
            # Command to create Wi-Fi hotspot using nmcli
            cmd = ['nmcli', 'd', 'wifi', 'hotspot', 'ifname', self.iface, 'ssid', ssid, 'password', password]
            # Execute the command
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
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