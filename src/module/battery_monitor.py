import threading
import logging
import socket
import time
import sys

class BatteryMonitor:
    def __init__(self):
        self.battery_level = None
        self.charging = False
        self.pisugar_detected = False
        self._stop_event = threading.Event()

    def send_battery_command_tcp(self, command, host='127.0.0.1', port=8423, timeout=5):
        """Send TCP command to the server and get the response."""
        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                sock.sendall(f"{command}\n".encode())
                response = sock.recv(1024)
            return response.decode().strip()
        except socket.timeout:
            print(f"Timeout: No response received for command '{command}'")
            return None
        except socket.error as e:
            print(f"Socket error for command '{command}': {e}")
            return None
        except Exception as e:
            print(f"An error occurred for command '{command}': {e}")
            return None

    def detect_pisugar(self):
        """Perform multiple checks to detect if PiSugar is actually connected and functioning."""
        print("Detecting PiSugar...")
        checks = [
            ('get model', lambda x: x.startswith('model:'), "Checking PiSugar model"),
            ('get battery', lambda x: x.startswith('battery:') and float(x.split()[1]) > 0, "Checking battery level"),
            ('get battery_power_plugged', lambda x: x in ['battery_power_plugged: true', 'battery_power_plugged: false'], "Checking power status")
        ]

        for command, check_func, message in checks:
            print(message + "...")
            response = self.send_battery_command_tcp(command)
            if not response or not check_func(response):
                print(f"PiSugar detection failed: {message}")
                return False
            print(f"Success: {response}")
        
        print("PiSugar detected successfully.")
        return True

    def _update_battery_status(self):
        """Fetch the current battery level and charging status using TCP commands."""
        try:
            battery_response = self.send_battery_command_tcp('get battery')
            if battery_response:
                self.battery_level = battery_response.split()[1].split('.')[0]
                
            power_plugged_response = self.send_battery_command_tcp('get battery_power_plugged')
            self.charging = power_plugged_response == 'battery_power_plugged: true'
        except Exception as e:
            print(f"Error updating battery status: {e}")

    def _start_periodic_check(self):
        """Start the background thread to periodically check battery status."""
        thread = threading.Thread(target=self._periodic_check, daemon=True)
        thread.start()

    def _periodic_check(self):
        """Periodically check the battery status every 5 seconds and log the information."""
        while not self._stop_event.is_set():
            self._update_battery_status()
            print(f"Battery level: {self.battery_level}%")
            print(f"Battery charging: {'Yes' if self.charging else 'No'}")
            time.sleep(5)

    def start(self):
        """Initialize battery monitoring by detecting PiSugar and setting up periodic checks if detected."""
        print("Starting PiSugar Battery Monitor...")
        self.pisugar_detected = self.detect_pisugar()
        if self.pisugar_detected:
            print("Starting periodic battery checks...")
            self._start_periodic_check()
            return True
        else:
            print("PiSugar not detected. Monitoring process will not start.")
            return False

    def stop(self):
        """Stop the periodic check."""
        self._stop_event.set()
        print("Stopping battery monitor...")

if __name__ == "__main__":
    monitor = BatteryMonitor()
    
    if not monitor.start():
        print("Exiting due to PiSugar not being detected.")
        sys.exit(1)
    
    print("Battery monitor is running. Press Ctrl+C to stop.")
    try:
        # Keep the script running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()
        print("Battery monitor stopped.")
        sys.exit(0)