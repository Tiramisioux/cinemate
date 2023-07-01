import os
import time
import pyudev
import threading
import shutil
import RPi.GPIO as GPIO

class DriveMonitor:
    def __init__(self, path, gpio_pin=None):
        self.path = path
        self.connection_status = self.check_drive_status()
        self.gpio_pin = gpio_pin
        self.space_decreasing = False
        self.last_free_space = 0
        self.last_change_time = time.time()
        self.led_status = False  # Flag indicating LED status

        GPIO.setmode(GPIO.BCM)

        if self.gpio_pins is not None:
            GPIO.setup(self.gpio_pins, GPIO.OUT, initial=GPIO.LOW)

        print('Initial connection status:', 'Connected' if self.connection_status else 'Disconnected')

        self.monitor_thread = threading.Thread(target=self.monitor_drive)
        self.monitor_thread.start()

    def check_drive_status(self):
        """Check if the drive is connected and return True or False"""
        return os.path.exists(self.path)

    def check_drive_space(self):
        """Check the free space of the drive and print it"""
        if self.connection_status:
            total, used, free = shutil.disk_usage(self.path)
            print(f'\rFree space: {free / (1024**3):.10f} GB', end='', flush=True)

            if self.gpio_pin is not None:
                if free < self.last_free_space:
                    GPIO.output(self.gpio_pin, GPIO.HIGH)
                    self.last_change_time = time.time()
                    self.led_status = True  # LED is on, set flag to True
                else:
                    if time.time() - self.last_change_time < 0.5:
                        GPIO.output(self.gpio_pin, GPIO.HIGH)
                    else:
                        GPIO.output(self.gpio_pin, GPIO.LOW)
                        self.led_status = False  # LED is off, set flag to False

            self.last_free_space = free

    def handle_event(self, device):
        """Handle the connect/disconnect event"""
        if 'DEVNAME' in device:
            if 'sda1' in device.get('DEVNAME'):
                old_status = self.connection_status
                if device.action == 'add':
                    time.sleep(5)
                    self.connection_status = self.check_drive_status()
                    if self.connection_status and self.connection_status != old_status:
                        print('Drive connected')
                        self.check_drive_space()
                elif device.action == 'remove':
                    self.connection_status = False
                    if self.connection_status != old_status:
                        print('Drive disconnected')

    def monitor_drive(self):
        """Monitor the drive connect/disconnect events"""
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem='block', device_type='partition')

        observer = pyudev.MonitorObserver(monitor, callback=self.handle_event, name='monitor-observer')

        observer.start()

    def start_space_monitoring(self, interval):
        """Monitor the free space on the drive at the specified interval"""
        self.last_free_space = 0

        while True:
            self.check_drive_space()
            time.sleep(interval)
