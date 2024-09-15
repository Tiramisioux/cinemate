import os
import logging
import threading
import time
import subprocess

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
    def __init__(self, mount_path='/media/RAW'):
        self.mount_path = mount_path
        self.is_mounted = False
        self.space_left = None
        self.device_name = None
        self._monitor_thread = None
        self._stop_event = threading.Event()

        # Define events
        self.mount_event = Event()
        self.unmount_event = Event()
        self.space_update_event = Event()

        self.start()

    def start(self):
        """Start the SSD monitoring."""
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._run)
            self._monitor_thread.start()
            logging.info("SSD monitoring thread started.")

    def stop(self):
        """Stop the SSD monitoring."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join()
        logging.info("SSD monitoring stopped.")

    def _run(self):
        """Continuous monitoring of the drive status and space left."""
        while not self._stop_event.is_set():
            self._check_mount_status()
            time.sleep(1)  # Check every second

    def _check_mount_status(self):
        """Check if the RAW drive is mounted and update status accordingly."""
        is_currently_mounted = os.path.ismount(self.mount_path)

        if is_currently_mounted and not self.is_mounted:
            # Drive was just mounted
            self.is_mounted = True
            self.device_name = self._get_device_name()
            logging.info(f"RAW drive mounted at {self.mount_path}")
            self._update_space_left()
            self.mount_event.emit(self.mount_path)
        elif not is_currently_mounted and self.is_mounted:
            # Drive was just unmounted
            logging.info(f"RAW drive unmounted from {self.mount_path}")
            self.is_mounted = False
            self.space_left = None
            self.device_name = None
            self.unmount_event.emit(self.mount_path)
        elif self.is_mounted:
            # Drive is still mounted, update space left
            self._update_space_left()

    def _get_device_name(self):
        """Get the device name of the mounted drive."""
        try:
            output = subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', self.mount_path], text=True).strip()
            return os.path.basename(output)
        except subprocess.CalledProcessError:
            logging.error(f"Failed to get device name for {self.mount_path}")
            return None

    def _update_space_left(self):
        """Update the space left on the SSD."""
        if self.is_mounted:
            try:
                stat = os.statvfs(self.mount_path)
                new_space_left = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)  # Convert to GB
                if new_space_left != self.space_left:
                    self.space_left = new_space_left
                    logging.info(f"Updated space left on SSD: {self.space_left:.2f} GB")
                    self.space_update_event.emit(self.space_left)
            except OSError as e:
                logging.error(f"Error updating space left: {e}")
                self.space_left = None

    def get_mount_status(self):
        """Get the current mount status."""
        return self.is_mounted

    def get_space_left(self):
        """Get the current space left on the SSD."""
        return self.space_left

    def unmount_drive(self):
        """Unmount the SSD."""
        if self.is_mounted:
            try:
                subprocess.run(["sudo", "umount", self.mount_path], check=True)
                logging.info(f"SSD unmounted from {self.mount_path}")
                self.is_mounted = False
                self.space_left = None
                self.device_name = None
                self.unmount_event.emit(self.mount_path)
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to unmount SSD: {e}")

    def report_current_mounts(self):
        """Check and report all currently mounted drives named RAW under /media."""
        logging.info("Checking currently mounted drives named 'RAW'...")
        found_raw = False
        raw_mounts = []

        if os.path.ismount(self.mount_path):
            found_raw = True
            try:
                stat = os.statvfs(self.mount_path)
                space_left = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)  # Convert to GB
                message = f"Drive 'RAW' mounted at {self.mount_path} with {space_left:.2f} GB free"
                logging.info(message)
                raw_mounts.append(('RAW', space_left))
            except OSError as e:
                logging.error(f"Error checking space on {self.mount_path}: {e}")
        
        if not found_raw:
            logging.info("No drives named 'RAW' found.")
        
        return raw_mounts