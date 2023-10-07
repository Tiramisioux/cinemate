import logging
import threading
import os

class CinePiController:
    def __init__(self, 
                 redis_controller,
                 usb_monitor,
                 ssd_monitor,
                 audio_recorder,
                 iso_steps,
                 shutter_a_steps,
                 fps_steps):
        
        self.parameters_lock_obj = threading.Lock()
        
        self.redis_controller = redis_controller
        self.ssd_monitor = ssd_monitor
        self.usb_monitor = usb_monitor
        self.audio_recorder = audio_recorder
        
        self.iso_steps = iso_steps
        self.shutter_a_steps = shutter_a_steps
        self.fps_steps = fps_steps
        
        self.parameters_lock = False
        
        self.fps_multiplier = 1
    
    def rec_button_pushed(self):

        logging.info(f"rec button pushed")
        if self.redis_controller.get_value('is_recording') == "0":
            self.start_recording()
        elif self.redis_controller.get_value('is_recording') == "1":
            self.stop_recording()
            
    def start_recording(self):

        if self.ssd_monitor.disk_mounted:
            self.redis_controller.set_value('is_recording', 1)
            if self.usb_monitor.usb_mic:
                self.audio_recorder.start_recording()
            logging.info(f"Started recording")
        elif not self.ssd_monitor.disk_mounted:
            logging.info(f"No disk mounted.")
            
    def stop_recording(self):

        self.redis_controller.set_value('is_recording', 0)
        self.audio_recorder.stop_recording()
        logging.info(f"Stopped recording")

    def set_resolution(self, value):
        try:
            if value not in [1080, 1520]:
                raise ValueError("Invalid resolution. Only 1080 and 1520 are allowed.")

            with self.parameters_lock_obj:
                self.redis_controller.set_value('height', value)
                self.redis_controller.set_value('cam_init', 1)
                logging.info(f"Setting resolution to {value}")
        except ValueError as error:
            logging.error(f"Error setting resolution: {error}")
        
    def switch_resolution(self):
        with self.parameters_lock_obj:
            if self.redis_controller.get_value('height') == '1080':
                resolution_new = 1520
            elif self.redis_controller.get_value('height') == '1520':
                resolution_new = 1080
            self.set_resolution(resolution_new)
            logging.info(f"Switching resolution to {resolution_new}")
        
    def set_iso(self, value):
        with self.parameters_lock_obj:
            safe_value = max(min(value, max(self.iso_steps)), min(self.iso_steps))
            self.redis_controller.set_value('iso', safe_value)
            logging.info(f"Setting iso to {safe_value}")

    def set_shutter_a(self, value):
        with self.parameters_lock_obj:
            safe_value = max(min(value, max(self.shutter_a_steps)), min(self.shutter_a_steps))
            self.redis_controller.set_value('shutter_a', safe_value)
            logging.info(f"Setting shutter_a to {safe_value}")
            
    def set_shutter_a_free(self, value):
        with self.parameters_lock_obj:
            safe_value = safe_value = max(1, min(value, 360))
            self.redis_controller.set_value('shutter_a', safe_value)
            logging.info(f"Setting shutter_a to {safe_value}")

    def set_fps(self, value):
        with self.parameters_lock_obj:
            safe_value = max(min(value, max(self.fps_steps)), min(self.fps_steps))
            self.redis_controller.set_value('fps', safe_value)
            logging.info(f"Setting fps to {safe_value}")
        
    def set_parameters_lock(self, value):
        with self.parameters_lock_obj:
            self.parameters_lock = value
            logging.info(f"Parameters lock {self.parameters_lock}")
        
    def set_fps_multiplier(self, value):
        with self.parameters_lock_obj:
            self.fps_multiplier = value
            logging.info(f"FPS multiplier {self.fps_multiplier}")
                
    def get_setting(self, key):
        value = self.redis_controller.get_value(key)
        return value
        
    def safe_shutdown(self):
        # First, stop any ongoing operations, like recording
        if self.redis_controller.get_value('is_recording') == "1":
            self.stop_recording()
        
        # Now, initiate safe shutdown
        logging.info("Initiating safe system shutdown.")
        os.system("sudo shutdown -h now")
        
    def unmount_ssd(self):
        # You can delegate this task to the SSDMonitor's unmount_ssd method
        self.ssd_monitor.unmount_ssd()
            
    def increment_setting(self, setting_name, steps):
        current_value = float(self.get_setting(setting_name))
        try:
            idx = steps.index(current_value)
        except ValueError:
            idx = max(i for i, value in enumerate(steps) if value < current_value)

        idx = min(idx + 1, len(steps) - 1)

        # Using getattr to call the correct method based on setting_name
        getattr(self, f"set_{setting_name}")(steps[idx])

        logging.info(f"Increasing {setting_name} to {steps[idx]}")

    def decrement_setting(self, setting_name, steps):
        current_value = float(self.get_setting(setting_name))
        try:
            idx = steps.index(current_value)
        except ValueError:
            idx = min(i for i, value in enumerate(steps) if value > current_value)

        idx = max(idx - 1, 0)

        # Using getattr to call the correct method based on setting_name
        getattr(self, f"set_{setting_name}")(steps[idx])

        logging.info(f"Decreasing {setting_name} to {steps[idx]}")
    
    def inc_iso(self):
        self.increment_setting('iso', self.iso_steps)

    def dec_iso(self):
        self.decrement_setting('iso', self.iso_steps)

    def inc_shutter_a(self):
        self.increment_setting('shutter_a', self.shutter_a_steps)

    def dec_shutter_a(self):
        self.decrement_setting('shutter_a', self.shutter_a_steps)

    def inc_fps(self):
        self.increment_setting('fps', self.fps_steps)

    def dec_fps(self):
        self.decrement_setting('fps', self.fps_steps)
        
    def print_settings(self):
        iso = self.get_setting('iso')
        shutter_a = self.get_setting('shutter_a')
        fps = self.get_setting('fps')
        height = self.get_setting('height')
        
        print()
        print(f"{'ISO':<20}{iso:<20}{str(self.iso_steps):<20}")
        print(f"{'Shutter Speed':<20}{shutter_a:<20}{str(self.shutter_a_steps):<20}")
        print(f"{'FPS':<20}{fps:<20}{str(self.fps_steps):<20}")
        print(f"{'Resolution':<20}{height:<20}")
        print(f"{'Parameters Lock':<20}{str(self.parameters_lock):<20}")
        print(f"{'FPS Multiplier':<20}{str(self.fps_multiplier):<20}")


