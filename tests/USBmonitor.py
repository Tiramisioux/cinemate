import pyudev
from signal import pause
import subprocess
import logging
import time
# Set up the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class USBMonitor:
    def __init__(self):
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem='usb')
        self.usb_mic = None
        self.usb_keyboard = None
        self.usb_hd = None
        self.check_initial_devices()

    def device_event(self, monitor, device):
        if device.action == 'add':
            if 'USB_PNP_SOUND_DEVICE' in device.get('ID_MODEL', '').upper():
                self.usb_mic = device
                print(f'USB Microphone connected: {device}')
            elif 'KEYBOARD' in device.get('ID_MODEL', '').upper():
                self.usb_keyboard = device
                print(f'USB Keyboard connected: {device}')
            elif 'SSD' in device.get('ID_MODEL', '').upper():
                self.usb_hd = device
                print(f'USB SSD connected: {device}')
        elif device.action == 'remove':
            if self.usb_mic is not None and self.usb_mic == device:
                self.usb_mic = None
                print(f'USB Microphone disconnected: {device}')
            elif self.usb_keyboard is not None and self.usb_keyboard == device:
                self.usb_keyboard = None
                print(f'USB Keyboard disconnected: {device}')
            elif self.usb_hd is not None and self.usb_hd == device:
                self.usb_hd = None
                print(f'USB SSD disconnected: {device}')

    def check_initial_devices(self):
        for device in self.context.list_devices(subsystem='usb'):
            if 'USB_PNP_SOUND_DEVICE' in device.get('ID_MODEL', '').upper():
                self.usb_mic = device
                print(f'USB Microphone connected: {device}')
            elif 'KEYBOARD' in device.get('ID_MODEL', '').upper():
                self.usb_keyboard = device
                print(f'USB Keyboard connected: {device}')
            elif 'SSD' in device.get('ID_MODEL', '').upper():
                self.usb_hd = device
                print(f'USB SSD connected: {device}')

    def monitor_devices(self):
        observer = pyudev.MonitorObserver(self.monitor, self.device_event)
        observer.start()

if __name__ == "__main__":
    monitor = USBMonitor()
    monitor.monitor_devices()


    pause()
