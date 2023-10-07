import threading
import logging
import time
from gpiozero import Button
import os
import RPi.GPIO as GPIO

class SystemButton(threading.Thread):
    """
    Threaded class to handle system button interactions.
    """

    def __init__(self, redis_controller, ssd_monitor, system_button_pin=26):
        super().__init__()

        self.redis_controller = redis_controller
        self.ssd_monitor = ssd_monitor
        self.system_button = Button(system_button_pin)
        self.system_button.when_pressed = self.system_button_callback
        logging.info(f"system_button instantiated on pin {system_button_pin}.")

        self.last_click_time = 0
        self.click_count = 0
        self.click_timer = None
        self.system_button_event = threading.Event()
        self.system_button_lock = threading.Lock()
        self.running = True  # Control variable for the run loop

    def run(self):
        """
        The main run loop. For now, it just keeps the thread alive. Adjust as necessary.
        """
        while self.running:
            time.sleep(0.5)

    def system_button_callback(self):
        logging.info("System button pushed")
        current_time = time.time()

        if current_time - self.last_click_time < 1.5:
            self.click_count += 1
        else:
            self.click_count = 1

        self.last_click_time = current_time

        if self.click_timer:
            self.click_timer.cancel()

        self.click_timer = threading.Timer(1.5, self.process_clicks)
        self.click_timer.start()

    def process_clicks(self):
        if self.click_count == 1:
            with self.system_button_lock:
                if not self.system_button_event.is_set():
                    self.system_button_event.set()
                    threading.Thread(target=self.monitor_system_button).start()
        elif self.click_count == 2:
            logging.info("Double click detected. Attempting system restart.")
            threading.Thread(target=self.system_restart).start()
        elif self.click_count == 3:
            logging.info("Triple click detected. Initiating system shutdown.")
            self.safe_shutdown()

        self.click_count = 0

    def monitor_system_button(self):
        time_held = 0.0
        button_pin = self.system_button.pin.number
        while GPIO.input(button_pin) == GPIO.LOW and time_held < 3:
            time.sleep(0.1)
            time_held += 0.1

        if time_held >= 3:
            logging.info("Button held for 3 seconds. Attempting to unmount SSD.")
            self.unmount_ssd()

        self.system_button_event.clear()

    def unmount_ssd(self):
        self.ssd_monitor.unmount_ssd()

    def safe_shutdown(self):
        if self.redis_controller.get_value('is_recording') == "1":
            self.stop_recording()

        logging.info("Initiating safe system shutdown.")
        os.system("sudo shutdown -h now")

    def system_restart(self):
        try:
            logging.info("Restarting system...")
            os.system('sudo reboot')
        except Exception as e:
            logging.error(f"Error restarting system: {e}")

    def stop(self):
        self.running = False
        self.cleanup()

    def cleanup(self):
        pass

