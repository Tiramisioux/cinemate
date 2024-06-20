# https://pimylifeup.com/raspberry-pi-wireless-access-point/

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
            self.logging.error(f"Error: Failed to create Wi-Fi hotspot. {e}")            
            

