import os
import time
import pyudev
import threading
import shutil
import RPi.GPIO as GPIO
import subprocess

class DriveMonitor:
    def __init__(self, path, rec_out_pins=None, button_pins=None):  # Change button_pin to button_pins
        self.path = path
        self.connection_status = self.is_drive_connected()
        self.rec_out_pins = rec_out_pins if rec_out_pins else []
        self.button_pins = button_pins if button_pins else []  # Change button_pin to button_pins
        self.last_free_space = 0
        self.last_change_time = time.time()
        self.led_status = False
        self.disk_ready = False
        
        GPIO.setmode(GPIO.BCM)

        # Set up each pin in rec_out_pins list
        for pin in self.rec_out_pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

        # Set up each pin in button_pins list and spawn threads for each button
        for pin in self.button_pins:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            threading.Thread(target=self.monitor_button, args=(pin,)).start()

        print('SSD', 'connected!' if self.connection_status else 'disconnected')

        self.monitor_thread = threading.Thread(target=self.monitor_drive)
        self.monitor_thread.start()
        
    def is_drive_connected(self):
        """Check if the drive is connected and return True or False"""
        if os.path.exists(self.path) and os.path.ismount(self.path):
            self.disk_ready = True
        else:
            self.disk_ready = False
        return self.disk_ready

    def get_remaining_space(self):
        """Check the free space of the drive and print it"""

        if self.disk_ready:
            total, used, free = shutil.disk_usage(self.path)
            #print(f'\rFree space: {free / (1024**3):.10f} GB', end='', flush=True)
            if not all(self.is_output(pin) for pin in self.rec_out_pins):
                for pin in self.rec_out_pins:
                    GPIO.setup(pin, GPIO.OUT)
            GPIO.setmode(GPIO.BCM)
            if self.rec_out_pins is not None and self.last_free_space is not None:
                if free < self.last_free_space:
                    GPIO.output(self.rec_out_pins, GPIO.HIGH)
                    self.last_change_time = time.time()
                    self.led_status = True  # LED is on, set flag to True
                else:
                    if time.time() - self.last_change_time < 0.5:
                        GPIO.output(self.rec_out_pins, GPIO.HIGH)
                    else:
                        GPIO.output(self.rec_out_pins, GPIO.LOW)
                        self.led_status = False  # LED is off, set flag to False

            self.last_free_space = free
        else:
            self.last_free_space = None
        print(f"\rSpace left: {self.last_free_space}", end="", flush=True)

    def handle_event(self, device):
        """Handle the connect/disconnect event"""
        if 'DEVNAME' in device:
            if 'sda1' in device.get('DEVNAME'):
                old_status = self.connection_status
                if device.action == 'add':
                    time.sleep(5)
                    self.connection_status = self.is_drive_connected()
                    if self.connection_status and self.connection_status != old_status:
                        print('SSD connected')
                        self.get_remaining_space()
                elif device.action == 'remove':
                    self.connection_status = False
                    if self.connection_status != old_status:
                        print('SSD disconnected')
                        self.get_remaining_space()
                        self.is_drive_connected()

    def monitor_drive(self):
        """Monitor the drive connect/disconnect events"""
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem='block', device_type='partition')

        observer = pyudev.MonitorObserver(monitor, callback=self.handle_event, name='monitor-observer')

        observer.start()
        
    def monitor_button(self, button_pin):
        """Monitor the button press"""
        GPIO.setmode(GPIO.BCM)  # Set GPIO mode before using GPIO functions
        while True:
            GPIO.wait_for_edge(button_pin, GPIO.FALLING)
            start_time = time.time()
            drive_dismounted = False
            
            while GPIO.input(button_pin) == GPIO.LOW:
                elapsed_time = time.time() - start_time
                if 2 <= elapsed_time < 6 and not drive_dismounted:
                    self.dismount_drive()
                    self.flash_led(5)
                    drive_dismounted = True
                
                if elapsed_time >= 6:
                    self.safe_shutdown()
                    
                time.sleep(0.1)

    def dismount_drive(self):
        """Dismount the drive"""
        print("Dismounting the drive...")
        subprocess.run(["umount", self.path])
        self.last_free_space = None
        self.is_drive_connected()

    def flash_led(self, flash_count):
        """Flash the LED a given number of times"""
        # Flash all LEDs in rec_out_pins list
        for _ in range(flash_count):
            for pin in self.rec_out_pins:
                GPIO.output(pin, GPIO.HIGH)
            time.sleep(0.2)
            for pin in self.rec_out_pins:
                GPIO.output(pin, GPIO.LOW)
            time.sleep(0.2)

    def safe_shutdown(self):
        """Perform a safe shutdown"""
        print("Performing a safe shutdown...")
        subprocess.run(["sudo", "shutdown", "-h", "now"])
        
    def is_output(self, pin):
        GPIO.setmode(GPIO.BCM)  # Set GPIO mode before using GPIO functions
        return GPIO.gpio_function(pin) == GPIO.OUT

    def start_space_monitoring(self, interval):
        """Monitor the free space on the drive at the specified interval"""
        self.last_free_space = 0

        while True:
            self.get_remaining_space()
            time.sleep(interval)
