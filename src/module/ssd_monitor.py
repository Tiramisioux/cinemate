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
        self._dmesg_thread = None
        self._stop_event = threading.Event()

        # Define events
        self.mount_event = Event()
        self.unmount_event = Event()
        self.space_update_event = Event()

        self.report_current_mounts()
        self.start()

    def start(self):
        """Start the SSD monitoring."""
        # Initial check for already connected RAW drives
        self._initial_check_for_raw_drive()

        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._run)
            self._monitor_thread.start()
            logging.info("SSD monitoring thread started.")

        if self._dmesg_thread is None or not self._dmesg_thread.is_alive():
            self._dmesg_thread = threading.Thread(target=self._monitor_dmesg)
            self._dmesg_thread.start()
            logging.info("dmesg monitoring thread started.")

    def stop(self):
        """Stop the SSD monitoring."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join()
        if self._dmesg_thread:
            self._dmesg_thread.join()
        logging.info("SSD monitoring stopped.")

    def _initial_check_for_raw_drive(self):
        """Check for RAW drives already connected at startup."""
        try:
            blkid_output = subprocess.check_output(['blkid'], text=True)
            for line in blkid_output.splitlines():
                if 'LABEL="RAW"' in line:
                    device_info = line.split(':')[0]
                    fstype = subprocess.check_output(['blkid', '-o', 'value', '-s', 'TYPE', device_info], text=True).strip()
                    if fstype in ['ntfs', 'ext4']:
                        self.device_name = os.path.basename(device_info)
                        self._mount_drive(self.device_name, fstype)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error during initial RAW drive check: {e}")
            
    def _run(self):
        """Continuous monitoring of the drive status and space left."""
        while not self._stop_event.is_set():
            if self.is_mounted:
                # Check if the drive is still mounted
                if not os.path.ismount(self.mount_path):
                    logging.info(f"Drive at {self.mount_path} is no longer mounted.")
                    self.is_mounted = False
                    self.space_left = None
                    self.device_name = None
                    self.unmount_event.emit(self.mount_path)
                else:
                    # Update space left
                    self._update_space_left()
            else:
                # If not mounted, check if it has become mounted
                if os.path.ismount(self.mount_path):
                    self.is_mounted = True
                    logging.info(f"Drive at {self.mount_path} is now mounted.")
                    self._update_space_left()
                    self.mount_event.emit(self.mount_path)
            
            time.sleep(1)  # Adjust sleep duration as needed

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
                self.space_left = None  # Reset space left on error

    def _monitor_dmesg(self):
        """Monitor dmesg for drive connect/disconnect events."""
        logging.info("Starting to monitor dmesg for drive events.")
        process = subprocess.Popen(['dmesg', '-w'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        try:
            while not self._stop_event.is_set():
                line = process.stdout.readline()
                if line:
                    logging.debug(f"dmesg output: {line.strip()}")

                    if 'sd' in line:
                        if 'Attached SCSI disk' in line or 'removable' in line:
                            logging.info(f"Detected a new SCSI disk event: {line.strip()}")
                            self._check_and_mount_raw_drive(line)
                        elif 'offline' in line or 'Detached SCSI disk' in line:
                            logging.info(f"Detected a disk detach event: {line.strip()}")
                            self._check_detach_raw_drive(line)
                        else:
                            logging.debug(f"Ignored non-relevant sd event: {line.strip()}")
                    else:
                        logging.debug(f"Ignored non-sd dmesg line: {line.strip()}")
        except Exception as e:
            logging.error(f"Error while monitoring dmesg: {e}")
        finally:
            process.terminate()
            logging.info("Stopped monitoring dmesg.")

    def _check_and_mount_raw_drive(self, dmesg_line):
        """Check if a connected drive is named RAW and mount it."""
        device_name = None
        if 'sd' in dmesg_line:
            parts = dmesg_line.split()
            for part in parts:
                if part.startswith("sd") and part[-1].isdigit():
                    device_name = part
                    break

        if device_name:
            device_path = f'/dev/{device_name}'
            try:
                if self._is_already_mounted(device_path):
                    logging.info(f"Device '{device_name}' is already mounted. Skipping mount.")
                    return

                blkid_output = subprocess.check_output(['blkid', '-o', 'value', '-s', 'LABEL', device_path], text=True).strip()
                if blkid_output == 'RAW':
                    fstype = subprocess.check_output(['blkid', '-o', 'value', '-s', 'TYPE', device_path], text=True).strip()
                    if fstype in ['ntfs', 'ext4']:
                        self.device_name = device_name
                        self._mount_drive(device_name, fstype)
            except subprocess.CalledProcessError as e:
                logging.error(f"Error checking or mounting drive '{device_name}': {e}")

    def _is_already_mounted(self, device_path):
        """Check if the device is already mounted."""
        try:
            with open('/proc/mounts', 'r') as mounts_file:
                mounts = mounts_file.read()
            return device_path in mounts
        except Exception as e:
            logging.error(f"Error checking if '{device_path}' is already mounted: {e}")
            return False

    def _mount_drive(self, device_name, fstype):
        """Mount the drive and start monitoring."""
        try:
            os.makedirs(self.mount_path, exist_ok=True)
            if not self._is_already_mounted(f'/dev/{device_name}'):
                subprocess.run(['mount', '-t', fstype, f'/dev/{device_name}', self.mount_path], check=True)
                self.is_mounted = True
                self._update_space_left()
                logging.info(f"Drive '{device_name}' mounted at {self.mount_path} with {fstype} filesystem")
                self.mount_event.emit(self.mount_path)
            else:
                logging.info(f"Drive '{device_name}' is already mounted.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to mount drive '{device_name}': {e}")

    def _check_detach_raw_drive(self, dmesg_line):
        """Check if the RAW drive was detached."""
        if self.device_name and self.device_name in dmesg_line:
            self.unmount_drive()

    def _check_mount(self):
        """Check if the SSD is still mounted."""
        if not os.path.ismount(self.mount_path) and self.is_mounted:
            logging.info(f"SSD at {self.mount_path} is no longer mounted.")
            self.is_mounted = False
            self.space_left = None
            self.device_name = None
            self.unmount_event.emit(self.mount_path)

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
                self.space_left = None  # Reset space left on error

    def get_mount_status(self):
        """Get the current mount status."""
        return self.is_mounted

    def get_space_left(self):
        """Get the current space left on the SSD."""
        return self.space_left
    
    def unmount_drive(self):
        """Unmount the SSD and stop monitoring."""
        try:
            subprocess.run(["umount", self.mount_path], check=True)
            logging.info(f"SSD unmounted from {self.mount_path}")
            self.unmount_event.emit(self.mount_path)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to unmount SSD: {e}")
        finally:
            self.is_mounted = False
            self.device_name = None
            self.space_left = None
            logging.info("Drive monitoring stopped.")

    def report_current_mounts(self):
        """Check and report all currently mounted drives named RAW under /media."""
        logging.info("Checking currently mounted drives named 'RAW'...")
        found_raw = False
        raw_mounts = []

        for entry in os.listdir('/media'):
            if "RAW" in entry:
                found_raw = True
                mount_point = os.path.join('/media', entry)
                if os.path.ismount(mount_point):
                    try:
                        stat = os.statvfs(mount_point)
                        space_left = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)  # Convert to GB
                        message = f"Drive '{entry}' mounted at {mount_point} with {space_left:.2f} GB free"
                        logging.info(message)
                        print(message)
                        raw_mounts.append((entry, space_left))
                    except OSError as e:
                        logging.error(f"Error checking space on {mount_point}: {e}")
                else:
                    message = f"Drive '{entry}' found but not mounted."
                    logging.info(message)
                    print(message)
                    raw_mounts.append((entry, None))
        
        if not found_raw:
            logging.info("No drives named 'RAW' found.")
            print("No drives named 'RAW' found.")
        
        return raw_mounts

