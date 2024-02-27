from gpiozero import Button
import time
import threading
import logging
import os
import signal
import sys

class SystemButton:
    def __init__(self, cinepi_controller, redis_controller, ssd_monitor, system_button_pin=None):
        self.system_button_pin = system_button_pin
        self.system_button = None
        
        if self.system_button_pin is not None:
            self.system_button = Button(self.system_button_pin, pull_up=False, hold_time=3)
            self.system_button.when_held = self.system_button_held
            self.system_button.when_pressed = self.system_button_pressed
            self.system_button.when_released = self.system_button_released

        self.cinepi_controller = cinepi_controller
        self.redis_controller = redis_controller
        self.ssd_monitor = ssd_monitor

        self.last_press_time = 0
        self.click_count = 0
        self.click_timer = None
        
        self.click_was_held = False

        # Set up the signal handler for SIGINT (Ctrl+C)
        signal.signal(signal.SIGINT, self.cleanup)

    def system_button_held(self):
        logging.info("System button held for 3 seconds.")
        #if self.ssd_monitor.disk_mounted == True:
        self.unmount_drive()
        # Add your action here
        self.click_count = 0  # Reset the click count after a hold
        self.click_was_held = True

    def system_button_pressed(self):
        current_time = time.time()

        if current_time - self.last_press_time < 1.5:
            self.click_count += 1
        else:
            self.click_count = 1

        self.last_press_time = current_time

    def system_button_released(self):
        if self.click_count > 0:
            # If there were consecutive clicks, start the timer for handling clicks
            if self.click_timer:
                self.click_timer.cancel()

            self.click_timer = threading.Timer(1.5, self.handle_clicks)
            self.click_timer.start()
        self.click_was_held = False

    def handle_clicks(self):
        if self.click_count == 1 and not self.click_was_held:
            logging.info("System button clicked once.")
            self.cinepi_controller.switch_resolution()
        elif self.click_count == 2:
            logging.info("System button double-clicked.")
            self.restart_camera()
        elif self.click_count == 3:
            logging.info("System button triple-clicked.")
            self.system_restart()
        elif self.click_count == 4:
            logging.info("System button quadruple-clicked.")
            self.safe_shutdown()
        elif self.click_count > 4:
            logging.info(f"System button clicked {self.click_count} times.")

        self.click_count = 0
        self.click_was_held = False

    def unmount_drive(self):
        self.ssd_monitor.unmount_drive()

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
            
    def restart_camera(self):
        self.redis_controller.set_value('cam_init', 1)

    def cleanup(self, signum, frame):
        # Handle cleanup actions here
        logging.info("Cleaning up and exiting...")
        sys.exit(0)

    def run(self):
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.cleanup(signal.SIGINT, None)