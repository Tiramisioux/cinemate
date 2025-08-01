import logging
import threading
import json
import time
from module.redis_controller import ParameterKey

class Mediator:
    def __init__(self, cinepi_app, cinepi_controller, redis_listener, redis_controller, ssd_monitor, gpio_output, stream, usb_monitor):
        self.cinepi_app = cinepi_app
        self.cinepi_controller = cinepi_controller
        self.redis_listener = redis_listener
        self.redis_controller = redis_controller
        self.ssd_monitor = ssd_monitor
        self.gpio_output = gpio_output
        self.stream = stream
        self.usb_monitor = usb_monitor

        # Other event subscriptions
        self.cinepi_app.message.subscribe(self.handle_cinepi_message)
        self.redis_controller.redis_parameter_changed.subscribe(self.handle_redis_event)
        self.redis_controller.redis_parameter_changed.subscribe(self.handle_fps_change)
        self.redis_controller.redis_parameter_changed.subscribe(self.handle_shutter_a_change)

        self.stop_recording_timer = None
        self.stop_recording_timeout = 2

        logging.info("Mediator instantiated")
        
    def load_ssd_settings(self, settings_file):
        """Load SSD settings from the specified JSON file."""
        try:
            with open(settings_file, 'r') as file:
                settings = json.load(file)
                return settings.get('recognized_ssds', [])
        except Exception as e:
            logging.error(f"Failed to load SSD settings: {e}")
            return []
    
    def handle_cinepi_message(self, message):
        # Handle CinePi app messages (currently not logging)
        pass  

    def handle_ssd_event(self, action, message):
        # Handle SSD events
        logging.info(f"SSDMonitor says: {action} {message}")
        self.ssd_monitor.get_ssd_space_left()
        space_left = self.ssd_monitor.last_space_left
        logging.info(f'Space left: {space_left}')
        
    def handle_ssd_unmount(self):
        logging.info("SSD unmounted.")
        self.recording_stop()

    def recording_stop(self):
        self.redis_controller.set_value(ParameterKey.IS_RECORDING.value, 0)
        self.redis_controller.set_value(ParameterKey.IS_WRITING.value, 0)
        self.gpio_output.set_recording(0)        

    def handle_write_status_change(self, status):
        self.redis_controller.set_value(ParameterKey.IS_WRITING.value, status)

        # Start or reset the timer when recording stops (status = 0)        
        if status == 0:
            if self.stop_recording_timer is None or not self.stop_recording_timer.is_alive():
                self.stop_recording_timer = threading.Timer(self.stop_recording_timeout, self.handle_stop_recording_timeout)
                self.stop_recording_timer.start()
        # Reset the timer when recording starts (status = 1)
        elif status == 1:
            if self.stop_recording_timer and self.stop_recording_timer.is_alive():
                self.stop_recording_timer.cancel()        

    def handle_redis_event(self, data):
        # Handle "is_recording" key changes
        if data['key'] == ParameterKey.REC.value:
            is_recording = int(data['value'])
            if is_recording:
                logging.info("Recording started!")
                self.gpio_output.set_recording(1)
                
                # Cancel the stop_recording_timer if it's running
                if self.stop_recording_timer is not None and self.stop_recording_timer.is_alive():
                    self.stop_recording_timer.cancel()
            else:
                logging.info("Recording stopped!")
                self.gpio_output.set_recording(0)
        
        # Handle "is_writing" key changes        
        elif data['key'] == ParameterKey.IS_WRITING.value:
            is_writing = bool(int(data['value']))
            if is_writing:
                self.stream.toggle_background_color()
                self.gpio_output.set_drive_color("blue")
            else:
                self.gpio_output.set_drive_color(
                    "green" if self.redis_controller.get_value(ParameterKey.IS_MOUNTED.value) == "1" else "off")
                self.gpio_output.set_recording(0)

        elif data['key'] == ParameterKey.IS_MOUNTED.value:
            mounted = bool(int(data['value']))
            if not mounted:
                self.gpio_output.set_drive_color("off")
            else:
                self.gpio_output.set_drive_color("green")

    def handle_stop_recording_timeout(self):
        """Handle the timeout event when recording should be stopped."""
        self.redis_controller.set_value(ParameterKey.IS_WRITING_BUF.value, 0)
        self.redis_controller.set_value(ParameterKey.IS_RECORDING.value, 0)
        self.redis_controller.set_value(ParameterKey.IS_WRITING.value, 0)
        self.gpio_output.set_recording(0) 
        
        logging.info("Stop recording timeout reached. Stopping recording...")

    def handle_fps_change(self, data):
        # Handle "fps" key changes
            fps_new = self.redis_controller.get_value(ParameterKey.FPS.value)
            
    def handle_shutter_a_change(self, data):
        # Handle "shutter_a" key changes
        if data['key'] == ParameterKey.SHUTTER_A.value:
            shutter_a_new = self.redis_controller.get_value(ParameterKey.SHUTTER_A.value)