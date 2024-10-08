import os
import logging
import threading
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class DNGFileHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith('.dng'):
            self.callback(event.src_path)

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
        self.file_system_format = None
        self.last_dng_file = None
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._observer = None

        # Define events
        self.mount_event = Event()
        self.unmount_event = Event()
        self.space_update_event = Event()
        self.new_dng_event = Event()

        self.start()

    def start(self):
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._run)
            self._monitor_thread.start()
            logging.info("SSD monitoring thread started.")

    def stop(self):
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join()
        if self._observer:
            self._observer.stop()
            self._observer.join()
        logging.info("SSD monitoring stopped.")

    def _run(self):
        while not self._stop_event.is_set():
            self._check_mount_status()
            time.sleep(1)

    def _check_mount_status(self):
        is_currently_mounted = os.path.ismount(self.mount_path)

        if is_currently_mounted and not self.is_mounted:
            self.is_mounted = True
            self.device_name = self._get_device_name()
            self.file_system_format = self._get_file_system_format()
            logging.info(f"RAW drive mounted at {self.mount_path}")
            logging.info(f"File system format: {self.file_system_format}")
            self._update_space_left()
            self._find_latest_dng_file()  # New method call
            self._start_file_monitoring()
            self.mount_event.emit(self.mount_path)
        elif not is_currently_mounted and self.is_mounted:
            logging.info(f"RAW drive unmounted from {self.mount_path}")
            self.is_mounted = False
            self.space_left = None
            self.device_name = None
            self.file_system_format = None
            self.last_dng_file = None
            self._stop_file_monitoring()
            self.unmount_event.emit(self.mount_path)
        elif self.is_mounted:
            self._update_space_left()

    def _find_latest_dng_file(self):
        """Find the most recently created DNG file in the mounted drive."""
        try:
            dng_files = []
            for root, dirs, files in os.walk(self.mount_path):
                for file in files:
                    if file.lower().endswith('.dng'):
                        full_path = os.path.join(root, file)
                        dng_files.append((full_path, os.path.getmtime(full_path)))
            
            if dng_files:
                latest_dng = max(dng_files, key=lambda x: x[1])
                self.last_dng_file = os.path.basename(latest_dng[0])
                logging.info(f"Found latest DNG file: {self.last_dng_file}")
                self.new_dng_event.emit(self.last_dng_file)
            else:
                logging.info("No DNG files found on the mounted drive.")
                self.last_dng_file = None
        except Exception as e:
            logging.error(f"Error while searching for DNG files: {e}")
            self.last_dng_file = None

    def _start_file_monitoring(self):
        if self._observer is None:
            self._observer = Observer()
            event_handler = DNGFileHandler(self._on_dng_created)
            self._observer.schedule(event_handler, self.mount_path, recursive=True)
            self._observer.start()
            logging.info(f"Started monitoring for DNG files in {self.mount_path}")

    def _stop_file_monitoring(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logging.info("Stopped monitoring for DNG files")

    def _on_dng_created(self, file_path):
        self.last_dng_file = os.path.basename(file_path)
        logging.info(f"New DNG file detected: {self.last_dng_file}")
        self.new_dng_event.emit(self.last_dng_file)

    def get_last_dng_file(self):
        return self.last_dng_file
            
    def _get_file_system_format(self):
        """Get the file system format of the mounted drive."""
        try:
            output = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE', self.mount_path], text=True).strip()
            return output
        except subprocess.CalledProcessError:
            logging.error(f"Failed to get file system format for {self.mount_path}")
            return None

    def get_file_system_format(self):
        """Get the current file system format of the SSD."""
        return self.file_system_format

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
                fs_format = self.get_file_system_format()
                message = f"Drive 'RAW' mounted at {self.mount_path} with {space_left:.2f} GB free, format: {fs_format}"
                logging.info(message)
                raw_mounts.append(('RAW', space_left, fs_format))
            except OSError as e:
                logging.error(f"Error checking space on {self.mount_path}: {e}")
        
        if not found_raw:
            logging.info("No drives named 'RAW' found.")
        
        return raw_mounts

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