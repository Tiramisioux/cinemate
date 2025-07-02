#!/usr/bin/env python3
import subprocess
import logging
import time

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
        try:
            cmd = ['sudo', 'nmcli', 'device', 'wifi', 'hotspot', 'ifname', self.iface, 'ssid', ssid, 'password', password, 'channel', '1']
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logging.info(f"Wi-Fi hotspot '{ssid}' created successfully with password '{password}' on interface '{self.iface}'.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Error: Failed to create Wi-Fi hotspot. {e}")

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    manager = WiFiHotspotManager()
    
    while True:
        if not manager.is_hotspot_active():
            manager.create_hotspot('cinepi', '11111111')
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    main()