import threading
import logging
import time
from sugarpie import pisugar

class BatteryMonitor:
    def __init__(self):
        self.battery_level = None
        self.charging = False
        self.pisugar_detected = False
        self._stop_event = threading.Event()
        self._init_battery_monitor()

    def _init_battery_monitor(self):
        """Initialize battery monitoring by fetching the initial battery level and setting up periodic checks."""
        try:
            # Attempt to get the initial battery level
            self._update_battery_status()
            if self.battery_level is not None:
                self.pisugar_detected = True
                logging.info("Pisugar detected.")
                # Start the background thread for periodic battery checks
                self._start_periodic_check()
        except Exception as e:
            logging.error(f"Failed to initialize battery monitor: {e}")

    def _update_battery_status(self):
        """Fetch the current battery level and charging status."""
        try:
            self.battery_level = pisugar.battery_level()  # Assuming this is the method to get battery level
            self.charging = pisugar.is_charging()  # Assuming this is the method to check if charging
        except Exception as e:
            logging.error(f"Error updating battery status: {e}")

    def _start_periodic_check(self):
        """Start the background thread to periodically check battery status."""
        thread = threading.Thread(target=self._periodic_check, daemon=True)
        thread.start()

    def _periodic_check(self):
        """Periodically check the battery status every 5 seconds."""
        while not self._stop_event.is_set():
            self._update_battery_status()
            logging.info(f" Battery level: {self.battery_level}")
            logging.info(f" Battery charging: {self.charging}")
            time.sleep(5)

    def stop(self):
        """Stop the periodic check."""
        self._stop_event.set()
