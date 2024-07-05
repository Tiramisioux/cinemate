import os
import time
import threading
import logging

class Event:
    def __init__(self):
        self._listeners = []

    def subscribe(self, listener):
        self._listeners.append(listener)

    def emit(self, *args):
        for listener in self._listeners:
            try:
                listener(*args)
            except Exception as e:
                logging.error(f"Error while invoking listener: {e}")

class SSDMonitor:
    def __init__(self):
        self.mount_path = '/media/RAW'
        self.is_mounted = False
        self.space_left = None
        self._monitor_thread = None
        self._stop_event = threading.Event()

        # Define events
        self.mount_event = Event()
        self.unmount_event = Event()
        self.space_update_event = Event()

        # Start monitoring upon initialization
        self.start()

    def start(self):
        """Start the SSD monitoring."""
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._run)
            self._monitor_thread.start()
            logging.info("SSD monitoring started.")

    def stop(self):
        """Stop the SSD monitoring."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join()
        logging.info("SSD monitoring stopped.")

    def _run(self):
        """Main monitoring loop."""
        while not self._stop_event.is_set():
            if not self.is_mounted:
                self._check_mount()
            else:
                self._update_space_left()
            time.sleep(1)  # Check every second

    def _check_mount(self):
        """Check if the SSD is mounted."""
        if os.path.ismount(self.mount_path):
            if not self.is_mounted:  # This means the drive was just connected
                self.is_mounted = True
                logging.info(f"SSD connected and mounted at {self.mount_path}")
                self._update_space_left()
                self.mount_event.emit(self.mount_path)
                if self.space_left is not None:
                    logging.info(f"Initial space left on connected SSD: {self.space_left:.2f} GB")

    def _update_space_left(self):
        """Update the space left on the SSD."""
        try:
            stat = os.statvfs(self.mount_path)
            new_space_left = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)  # Convert to GB
            if new_space_left != self.space_left:
                self.space_left = new_space_left
                logging.info(f"Updated space left on SSD: {self.space_left:.2f} GB")
                self.space_update_event.emit(self.space_left)
        except OSError as e:
            if self.is_mounted:  # This means the drive was just disconnected
                logging.info(f"SSD disconnected from {self.mount_path}")
                self.is_mounted = False
                self.space_left = None
                self.unmount_event.emit(self.mount_path)

    def get_mount_status(self):
        """Get the current mount status."""
        return self.is_mounted

    def get_space_left(self):
        """Get the current space left on the SSD."""
        return self.space_left

# Usage example:
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    monitor = SSDMonitor()

    # Example event handlers
    def on_mount(mount_path):
        print(f"SSD mounted at {mount_path}")

    def on_unmount(mount_path):
        print(f"SSD unmounted from {mount_path}")

    def on_space_update(space_left):
        print(f"Space left on SSD: {space_left:.2f} GB")

    # Subscribe to events
    monitor.mount_event.subscribe(on_mount)
    monitor.unmount_event.subscribe(on_unmount)
    monitor.space_update_event.subscribe(on_space_update)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping monitoring...")
        monitor.stop()
