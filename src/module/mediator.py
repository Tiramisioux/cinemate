import logging
import threading
import json

import RPi

class Mediator:
    def __init__(self, cinepi_app, redis_controller, usb_monitor, ssd_monitor, gpio_output):
        self.cinepi_app = cinepi_app
        self.redis_controller = redis_controller
        self.usb_monitor = usb_monitor
        self.ssd_monitor = ssd_monitor
        self.gpio_output = gpio_output
        
        # # Load recognized SSD models from the settings file
        # self.recognized_ssds = self.load_ssd_settings("/home/pi/cinemate/src/module/ssd_settings.json")
        
        self.cinepi_app.message.subscribe(self.handle_cinepi_message)
        # self.usb_monitor.usb_event.subscribe(self.handle_usb_event)
        self.ssd_monitor.write_status_changed_event.subscribe(self.handle_write_status_change)

        # Subscribe to the "is_recording" key changes
        self.redis_controller.redis_parameter_changed.subscribe(self.handle_redis_event)
        
        self.stop_recording_timer = None
        self.stop_recording_timeout = 2
        
         # Subscribe to the "fps_actual" key changes
        self.redis_controller.redis_parameter_changed.subscribe(self.handle_fps_actual_change)
        
         # Subscribe to SSD unmount events
        self.ssd_monitor.unmount_event.subscribe(self.handle_ssd_unmount)
        
        self.ssd_monitor.ssd_event.subscribe(self.handle_ssd_event)
        
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
    
    # def handle_usb_event(self, action, device, device_model, device_serial):
    #     """Handle USB events with SSD recognition based on the settings file."""
    #     model_upper = device_model.upper()
    #     if any(ssd_model.upper() in model_upper for ssd_model in self.recognized_ssds):
    #         # The device is recognized as an SSD from the settings file
    #         logging.info(f"Recognized SSD connected: {device_model}")
    #         logging.info(f"SSD device serial: {device_serial}")
    #         self.ssd_monitor.update(action, device_model, device_serial)
    #         self.ssd_monitor.usb_hd_serial = device_serial  # Set the serial number

    #     # Add else condition if needed to handle non-SSD USB events

    def handle_ssd_event(self, action, message):
        # Handle SSD events
        logging.info(f"SSDMonitor says: {action} {message}")
        self.ssd_monitor.get_ssd_space_left()
        space_left = self.ssd_monitor.last_space_left
        logging.info('Space left:', space_left)
        
    def handle_ssd_unmount(self):
        logging.info("SSD unmounted.")
        self.recording_stop()

    def recording_stop(self):
        self.redis_controller.set_value('is_recording', 0)
        self.redis_controller.set_value('is_writing', 0)
        self.gpio_output.set_recording(0)        

    def handle_write_status_change(self, status):
        self.redis_controller.set_value('is_writing', status)
        
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
        if data['key'] == 'is_recording':
            is_recording = int(data['value'])
            self.redis_controller.set_value('is_writing_buf', is_recording)
            # Perform your action or method here based on the is_recording value
            if is_recording:
                #logging.info("Recording started!")
                self.gpio_output.set_recording(1)
                # Cancel the stop_recording_timer if it's running
                if self.stop_recording_timer is not None and self.stop_recording_timer.is_alive():
                    self.stop_recording_timer.cancel()
            else:
                #logging.info("Recording stopped!")
                self.redis_controller.set_value('is_writing', 0)
                #self.gpio_output.set_recording(0)
        
        # Handle "is_writing" key changes        
        elif data['key'] == 'is_writing':
            is_writing = int(data['value'])
            if is_writing:
                pass
            else:
                self.gpio_output.set_recording(0)    

    def handle_stop_recording_timeout(self):
        """Handle the timeout event when recording should be stopped."""
        self.redis_controller.set_value('is_writing_buf', 0)
        self.redis_controller.set_value('is_recording', 0)
        self.redis_controller.set_value('is_writing', 0)
        self.gpio_output.set_recording(0) 
        
        logging.info("Stop recording timeout reached. Stopping recording...")

    def handle_fps_actual_change(self, data):
        # Handle "fps_actual" key changes
        if data['key'] == 'fps_actual':
            try:
                fps_actual = float(data['value'])
                if fps_actual > 0:
                    self.stop_recording_timeout = 2
                    #logging.info(f"fps_actual changed to {fps_actual}. Updated stop_recording_timeout to {self.stop_recording_timeout} seconds.")
            except ValueError:
                logging.warning("Invalid value for fps_actual. Could not update stop_recording_timeout.")