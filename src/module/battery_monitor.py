import threading
import logging
import socket
import time
from sugarpie import pisugar

class BatteryMonitor:
    def __init__(self):
        self.battery_level = None
        self.charging = False
        self.pisugar_detected = False
        self._stop_event = threading.Event()
        self._init_battery_monitor()

    def send_battery_command_tcp(self, command, host='127.0.0.1', port=8423, timeout=5):
        """Send TCP command to the server and get the response."""
        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                sock.sendall(f"{command}\n".encode())
                response = sock.recv(1024)
            return response.decode().strip()
        except socket.timeout:
            logging.error("Timeout: No response received from the server.")
            return None
        except socket.error as e:
            logging.error(f"Socket error: {e}")
            return None
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            return None

    def _update_battery_status(self):
        """Fetch the current battery level and charging status using TCP commands."""
        try:
            battery_command = 'get battery'
            power_plugged_command = 'get battery_power_plugged'

            battery_response = self.send_battery_command_tcp(battery_command)
            if battery_response:
                self.battery_level = battery_response.split()[1].split('.')[0]

            power_plugged_response = self.send_battery_command_tcp(power_plugged_command)
            self.charging = power_plugged_response == 'battery_power_plugged: true'
            if self.battery_level is not None:
                self.pisugar_detected = True
        except Exception as e:
            logging.error(f"Error updating battery status: {e}")

    def _start_periodic_check(self):
        """Start the background thread to periodically check battery status."""
        thread = threading.Thread(target=self._periodic_check, daemon=True)
        thread.start()

    def _periodic_check(self):
        """Periodically check the battery status every 5 seconds and log the information."""
        while not self._stop_event.is_set():
            self._update_battery_status()
            logging.info(f" Battery level: {self.battery_level}")
            logging.info(f" Battery charging: {self.charging}")
            time.sleep(5)

    def _init_battery_monitor(self):
        """Initialize battery monitoring by fetching the initial battery level and setting up periodic checks."""
        self._update_battery_status()
        if self.pisugar_detected:
            logging.info("pisugar detected successfully.")
            self._start_periodic_check()

    def stop(self):
        """Stop the periodic check."""
        self._stop_event.set()
