import os
import logging
import threading
import time
import subprocess
import smbus

from module.redis_controller import ParameterKey

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
    def __init__(self, mount_path='/media/RAW', redis_controller=None):
        self.mount_path = mount_path
        self.is_mounted = False
        self.space_left = None
        self.device_name = None
        self.device_type = None  # 'USB', 'NVMe', or 'CFE'
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self.redis_controller = redis_controller

        # Define events
        self.mount_event = Event()
        self.unmount_event = Event()
        self.space_update_event = Event()

        self._detect_cfe_hat()
        self.start()

    def _detect_cfe_hat(self):
        self.cfe_hat_present = False
        try:
            bus = smbus.SMBus(1)
            if bus.read_byte(0x34) in range(0x00, 0xFF):
                logging.info("CFE HAT detected via I2C on address 0x34")
                self.cfe_hat_present = True
                self.mount_cfe()
        except Exception:
            logging.info("No CFE HAT detected on I2C")

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
            self.device_type = self._detect_device_type()
            if self.redis_controller:
                self.redis_controller.set_value(ParameterKey.STORAGE_TYPE.value, self.device_type.lower())
                self.redis_controller.set_value(ParameterKey.IS_MOUNTED.value, '1')
            logging.info(f"RAW drive mounted at {self.mount_path} ({self.device_type})")
            self._update_space_left()
            self.mount_event.emit(self.mount_path, self.device_type)
        elif not is_currently_mounted and not self.is_mounted:
            logging.info(f"RAW drive unmounted from {self.mount_path}")
            self.is_mounted = False
            self.space_left = None
            self.device_name = None
            self.device_type = None
            if self.redis_controller:
                self.redis_controller.set_value(ParameterKey.STORAGE_TYPE.value, 'none')
                self.redis_controller.set_value(ParameterKey.IS_MOUNTED.value, '0')
                self.redis_controller.set_value(ParameterKey.SPACE_LEFT.value, '0')
            self.unmount_event.emit(self.mount_path)
        elif self.is_mounted:
            self._update_space_left()

    def _get_device_name(self):
        try:
            output = subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', self.mount_path], text=True).strip()
            return os.path.basename(output)
        except subprocess.CalledProcessError:
            logging.error(f"Failed to get device name for {self.mount_path}")
            return None

    def _detect_device_type(self):
        if not self.device_name:
            return 'Unknown'

        try:
            path = f"/sys/class/block/{self.device_name}/device"
            real_path = os.path.realpath(path)

            if self.cfe_hat_present and 'platform/axi/1000110000.pcie' in real_path:
                return 'CFE'

            if '/usb' in real_path:
                return 'SSD'
            elif '/nvme' in real_path:
                return 'NVMe'
        except Exception as e:
            logging.error(f"Device type detection failed: {e}")

        return 'Unknown'

    def _update_space_left(self):
        if self.is_mounted:
            try:
                stat = os.statvfs(self.mount_path)
                new_space_left = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
                if new_space_left != self.space_left:
                    self.space_left = new_space_left
                    logging.info(f"Updated space left on SSD: {self.space_left:.2f} GB")
                    if self.redis_controller:
                        self.redis_controller.set_value(ParameterKey.SPACE_LEFT.value, f"{self.space_left:.2f}")
                    self.space_update_event.emit(self.space_left)
            except OSError as e:
                logging.error(f"Error updating space left: {e}")
                self.space_left = None
                if self.redis_controller:
                    self.redis_controller.set_value(ParameterKey.SPACE_LEFT.value, '0')

    def get_mount_status(self):
        return self.is_mounted

    def get_space_left(self):
        return self.space_left

    def get_device_type(self):
        return self.device_type

    def unmount_drive(self):
        if self.is_mounted:
            try:
                if self.device_type == 'CFE':
                    subprocess.run(["sudo", "cfe-hat-automount", "unmount"], check=True)
                else:
                    subprocess.run(["sudo", "umount", self.mount_path], check=True)
                logging.info(f"SSD unmounted from {self.mount_path}")
                self.is_mounted = False
                self.space_left = None
                self.device_name = None
                self.device_type = None
                if self.redis_controller:
                    self.redis_controller.set_value(ParameterKey.STORAGE_TYPE.value, 'none')
                    self.redis_controller.set_value(ParameterKey.IS_MOUNTED.value, '0')
                    self.redis_controller.set_value(ParameterKey.SPACE_LEFT.value, '0')
                self.unmount_event.emit(self.mount_path)
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to unmount SSD: {e}")

    def mount_cfe(self):
        try:
            subprocess.run(["sudo", "cfe-hat-automount", "mount"], check=True)
            logging.info("CFE mount triggered via CLI")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to mount CFE drive: {e}")

    def report_current_mounts(self):
        logging.info("Checking currently mounted drives named 'RAW'...")
        raw_mounts = []

        if os.path.ismount(self.mount_path):
            try:
                stat = os.statvfs(self.mount_path)
                space_left = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
                message = f"Drive 'RAW' mounted at {self.mount_path} with {space_left:.2f} GB free"
                logging.info(message)
                raw_mounts.append(('RAW', space_left, self.device_type))
            except OSError as e:
                logging.error(f"Error checking space on {self.mount_path}: {e}")
        else:
            logging.info("No drives named 'RAW' found.")

        return raw_mounts
