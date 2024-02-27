import logging
import threading
import os
import time
from fractions import Fraction
import math

class CinePiController:
    def __init__(self,
                 pwm_controller, 
                 redis_controller,
                 usb_monitor,
                 ssd_monitor,
                 sensor_detect,
                 #audio_recorder,
                 iso_steps,
                 shutter_a_steps,
                 fps_steps):
        
        self.parameters_lock_obj = threading.Lock()
        
        self.pwm_controller = pwm_controller
        self.redis_controller = redis_controller
        self.ssd_monitor = ssd_monitor
        self.usb_monitor = usb_monitor
        self.sensor_detect = sensor_detect
        
        self.iso_steps = iso_steps
        self.shutter_a_steps = shutter_a_steps
        
        self.parameters_lock = False
        self.lock_override = False
        
        self.exposure_time_seconds = None
        self.exposure_time_fractions = None
        
        self.fps_multiplier = 1
        self.pwm_mode = False
        
        self.fps_button_state = False
        
        self.fps_temp = 24
        self.fps_temp_old = 24
        
        self.shutter_a_sync = True
        self.shutter_a_nom = 180
        
        self.fps_saved = float(self.redis_controller.get_value('fps_actual'))
        self.fps_double = False
        self.fps_actual = 24
        
        self.exposure_time_saved = 1/24
        
        self.current_sensor = self.sensor_detect.camera_model
        #logging.info(f"{self.current_sensor}")
        
        self.sensor_mode = int(self.redis_controller.get_value('sensor_mode'))
        
        self.set_resolution(self.sensor_mode)
        #logging.info(f"{self.current_sensor_mode}")
        self.fps_max = int(self.sensor_detect.get_fps_max(self.current_sensor, self.sensor_mode))
        #logging.info(f"{self.fps_max}")
        self.gui_layout = (self.sensor_detect.get_gui_layout(self.current_sensor, self.sensor_mode))
        #logging.info(f"{self.gui_layout}")
        
        self.exposure_time_s = float(self.redis_controller.get_value('shutter_a'))/360 * 1/self.fps_actual
        self.exposure_time_saved = self.exposure_time_s
        
        self.file_size = self.sensor_detect.get_file_size(self.current_sensor, self.sensor_mode)
        
        #Set fps array if not defined in 
        if not fps_steps: self.fps_steps=list(range(1, (self.fps_max + 1)))
        
    # def check_resolution_match(self):
    #     current_width = int(self.redis_controller.get_value('width'))
    #     current_height = int(self.redis_controller.get_value('height'))

    #     for mode, resolution_info in self.sensor_detect.res_modes.items():
    #         width = resolution_info.get('width', None)
    #         height = resolution_info.get('height', None)
    #         if width == current_width and height == current_height:
    #             # Resolution match found, no action needed
    #             logging.info(f"Resolution match found for sensor mode {mode}")
    #             return
    #     # No resolution match found, set sensor mode to the first available mode (mode 0)
    #     logging.info("No resolution match found. Setting sensor mode to 0.")
    #     self.set_resolution(0)
        
    def rec_button_pushed(self):
        logging.info(f"rec button pushed")
        if self.redis_controller.get_value('is_recording') == "0":
            self.start_recording()
        elif self.redis_controller.get_value('is_recording') == "1":
            self.stop_recording()
            
    def start_recording(self):
        if self.ssd_monitor.last_space_left:
            self.redis_controller.set_value('is_recording', 1)
            # if self.usb_monitor.usb_mic:
            #     self.audio_recorder.start_recording()
            logging.info(f"Started recording")
        elif not self.ssd_monitor.last_space_left:
            logging.info(f"No disk.")
            
    def stop_recording(self):
        self.redis_controller.set_value('is_recording', 0)
        # self.audio_recorder.stop_recording()
        logging.info(f"Stopped recording")

    def switch_resolution(self):
        try:
            current_sensor_mode = int(self.redis_controller.get_value('sensor_mode'))
            sensor_modes = list(self.sensor_detect.res_modes.keys())
            num_sensor_modes = len(sensor_modes)

            if num_sensor_modes <= 1:
                logging.info("Only one sensor mode available. Cannot switch resolution.")
                return

            current_index = sensor_modes.index(current_sensor_mode)
            next_index = (current_index + 1) % num_sensor_modes
            next_sensor_mode = sensor_modes[next_index]

            self.set_resolution(next_sensor_mode)

        except ValueError as error:
            logging.error(f"Error switching resolution: {error}")

    def set_resolution(self, sensor_mode):
        try:
            if sensor_mode not in self.sensor_detect.res_modes:
                raise ValueError("Invalid sensor mode.")

            resolution_info = self.sensor_detect.res_modes[sensor_mode]
            height_value = resolution_info.get('height', None)
            width_value = resolution_info.get('width', None)
            gui_layout_value = resolution_info.get('gui_layout', None)

            if height_value is None or width_value is None or gui_layout_value is None:
                raise ValueError("Invalid height, width, or gui_layout value.")

            # Set height, width, and gui_layout in Redis
            self.redis_controller.set_value('height', str(height_value))
            self.redis_controller.set_value('width', str(width_value))
            self.redis_controller.set_value('sensor_mode', str(sensor_mode))
            self.redis_controller.set_value('gui_layout', str(gui_layout_value))
            self.redis_controller.set_value('cam_init', 1)

            # Update local attributes
            self.gui_layout = gui_layout_value

            logging.info(f"Resolution set to mode {sensor_mode}, height: {height_value}, width: {width_value}, gui_layout: {gui_layout_value}")

        except ValueError as error:
            logging.error(f"Error setting resolution: {error}")

    def get_current_sensor_mode(self):
        current_height = int(self.redis_controller.get_value('height'))

        for mode, height_dict in self.sensor_detect.res_modes.items():
            if height_dict.get('height') == current_height:
                # Update fps_max based on the current sensor mode
                fps_max_value = height_dict.get('fps_max', None)
                self.redis_controller.set_value('fps_max', fps_max_value)

                # Update sensor_mode in Redis
                self.redis_controller.set_value('sensor_mode', mode)
                
                # # Update width in Redis
                # width = self.sensor_detect.get_width()
                # self.redis_controller.set_value('width', width)

                return mode

        return None  # Return None if no matching sensor mode is found

    def set_iso(self, value):
        with self.parameters_lock_obj:
            safe_value = max(min(value, max(self.iso_steps)), min(self.iso_steps))
            self.redis_controller.set_value('iso', safe_value)
            logging.info(f"Setting iso to {safe_value}")

    def set_shutter_a(self, value):
        
        with self.parameters_lock_obj:
            
            #safe_value = max(1, min(value, 360))
            
            self.redis_controller.set_value('shutter_a', value)
            self.exposure_time_seconds = (float(self.redis_controller.get_value('shutter_a'))/360) / 1/self.fps_actual
            self.exposure_time_fractions = self.seconds_to_fraction_text(self.exposure_time_seconds)
 
            logging.info(f"Setting shutter_a to {value}")
            #logging.info(f"shutter_a_nom {self.redis_controller.get_value('shutter_a_nom')}")
            # Update the PWM duty cycle based on the new shutter angle
            if self.pwm_mode == True:
                self.pwm_controller.set_pwm(shutter_angle = value)
                
        self.exposure_time_s = float(self.redis_controller.get_value('shutter_a'))/360 * 1/self.fps_actual
            
    def set_shutter_a_nom(self, value):
        
        with self.parameters_lock_obj:
            
            safe_value = max(1, min(value, 360))
            #safe_value = max(min(value, max(self.shutter_a_steps)), min(self.shutter_a_steps))
            self.redis_controller.set_value('shutter_a_nom', value)
            self.exposure_time_seconds = (float(self.redis_controller.get_value('shutter_a'))/360) / 1/self.fps_actual
            self.exposure_time_fractions = self.seconds_to_fraction_text(self.exposure_time_seconds)
 
            logging.info(f"Setting shutter_a_nom to {value}")
            
        if self.shutter_a_sync == True:
            
            # Update the shutter angle
            nominal_shutter_angle = float(self.redis_controller.get_value('shutter_a_nom'))
            exposure_time_desired = (nominal_shutter_angle / 360) * (1/ self.fps_actual)

            synced_shutter_angle = (exposure_time_desired / (1/ self.fps_actual)) * 360
            # Round the new shutter angle to one decimal place
            synced_shutter_angle = round(synced_shutter_angle, 1)

            # If the new shutter angle is a whole number, convert it to an integer
            if isinstance(synced_shutter_angle, float) and synced_shutter_angle.is_integer():
                synced_shutter_angle = int(synced_shutter_angle)
                
            self.set_shutter_a(synced_shutter_angle)
            
        elif self.shutter_a_sync == False:
            self.set_shutter_a(value)
            
        self.exposure_time_s = float(self.redis_controller.get_value('shutter_a'))/360 * 1/self.fps_actual

    def set_fps(self, value):
        # Determine max fps from resolution
        max_fps = self.fps_max
        
        safe_value = value
        
        if self.fps_double == True:
            safe_value = value * 2
        
        # Cap the value to the range [1, max_fps]
        safe_value = max(1, min(safe_value, max_fps))

        if not self.parameters_lock or self.lock_override == True:
            if self.pwm_mode == False and self.shutter_a_sync == False:
                self.redis_controller.set_value('fps', safe_value)
                self.fps_actual = float(self.redis_controller.get_value('fps'))
                logging.info(f"Setting fps to {safe_value}")

            elif self.pwm_mode == False and self.shutter_a_sync == True:
                self.redis_controller.set_value('fps', safe_value)
                nominal_shutter_angle = float(self.get_setting('shutter_a_nom'))
                new_shutter_angle = self.exposure_time_saved / (1 / safe_value) * 360
                new_shutter_angle = max(min(new_shutter_angle, 360), 1)
                new_shutter_angle = round(new_shutter_angle, 1)
                if isinstance(new_shutter_angle, float) and new_shutter_angle.is_integer():
                    new_shutter_angle = int(new_shutter_angle)
                self.set_shutter_a(new_shutter_angle)
                self.fps_actual = safe_value
                logging.info(f"Setting fps to {safe_value}")

            elif self.pwm_mode == True and self.shutter_a_sync == True:
                # safe_value = int(round(max(min(value, self.fps_max), 0)))
                nominal_shutter_angle = float(self.get_setting('shutter_a_nom'))
                new_shutter_angle = self.exposure_time_saved / (1 / safe_value) * 360
                new_shutter_angle = max(min(new_shutter_angle, 360), 1)
                new_shutter_angle = round(new_shutter_angle, 1)
                if isinstance(new_shutter_angle, float) and new_shutter_angle.is_integer():
                    new_shutter_angle = int(new_shutter_angle)
                self.set_shutter_a(new_shutter_angle)
                self.fps_actual = safe_value
                self.pwm_controller.set_pwm(fps=safe_value, shutter_angle=new_shutter_angle)
                logging.info(f"Setting fps to {safe_value} and shutter angle to {new_shutter_angle}")

            elif self.pwm_mode == True and self.shutter_a_sync == False:
                # safe_value = int(round(max(min(value, self.fps_max), 0)))
                new_shutter_angle = float(self.get_setting('shutter_a'))
                self.pwm_controller.set_pwm(fps=safe_value, shutter_angle=new_shutter_angle)
                self.fps_actual = safe_value
                logging.info(f"Setting fps to {safe_value}")

            self.exposure_time_s = (float(self.redis_controller.get_value('shutter_a')) / 360) / self.fps_actual
            # self.exposure_time_saved = self.exposure_time_s
            self.exposure_time_fractions = self.seconds_to_fraction_text(self.exposure_time_s)
            self.redis_controller.set_value('fps_actual', self.fps_actual)

        
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
        
    def unmount_drive(self):
        self.ssd_monitor.unmount_drive()
                
    def increment_setting(self, setting_name, steps):
        if self.pwm_mode == False:
            current_value = float(self.get_setting(setting_name))
            idx = steps.index(current_value)
            idx = min(idx + 1, len(steps) - 1)
            getattr(self, f"set_{setting_name}")(steps[idx])
            logging.info(f"Increasing {setting_name} to {self.get_setting(setting_name)}")
        elif self.pwm_mode == True and setting_name == 'fps':
            # self.fps_temp_old = self.fps_temp
            self.set_fps(self.fps_actual + 1)

    def decrement_setting(self, setting_name, steps):
        if self.pwm_mode == False:
            current_value = float(self.get_setting(setting_name))
            idx = steps.index(current_value)
            idx = max(idx - 1, 0)
            getattr(self, f"set_{setting_name}")(steps[idx])
            logging.info(f"Decreasing {setting_name} to {self.get_setting(setting_name)}")
        elif self.pwm_mode == True and setting_name == 'fps':
            # self.fps_temp_old = self.fps_temp
            self.set_fps(self.fps_actual - 1)
    
    def inc_iso(self):
        self.increment_setting('iso', self.iso_steps)

    def dec_iso(self):
        self.decrement_setting('iso', self.iso_steps)

    def inc_shutter_a(self):
        self.increment_setting('shutter_a', self.shutter_a_steps)

    def dec_shutter_a(self):
        self.decrement_setting('shutter_a', self.shutter_a_steps)
        
    def inc_shutter_a_nom(self):
        self.increment_setting('shutter_a_nom', self.shutter_a_steps)

    def dec_shutter_a_nom(self):
        self.decrement_setting('shutter_a_nom', self.shutter_a_steps)

    def inc_fps(self):
        self.increment_setting('fps', self.fps_steps)

    def dec_fps(self):
        self.decrement_setting('fps', self.fps_steps)
        
    def set_pwm_mode(self, pwm_mode):

        if self.current_sensor != 'imx477':
            logging.info(f"Current sensor {self.current_sensor}. PWM mode not availabe")
        else:
                
            if self.pwm_mode == False:
                self.fps_saved = float(self.get_setting('fps_actual'))

            #self.pwm_controller.pwm_mode(pwm_mode)
            self.pwm_mode = pwm_mode
            logging.info(f"Setting pwm mode mode to {pwm_mode}")
            #self.shutter_a_nom = float(self.get_setting('shutter_a_nom'))


            if pwm_mode == False:            
                # Stop PWM
                self.pwm_controller.stop_pwm()
                self.set_fps(self.fps_saved)
                # self.fps_steps = self.fps_steps = list(range(1, 51))  # Assuming original_fps_steps is defined
                # self.shutter_a_steps = self.original_shutter_a  # Assuming original_shutter_a is defined
                
            elif pwm_mode == True:
                self.fps_saved = float(self.get_setting('fps_actual'))
                shutter_a_current = float(self.get_setting('shutter_a_nom'))
                self.redis_controller.set_value('fps', 50)
                # self.fps_steps = list(range(1, 51))  # Whole numbers from 1 to 50
                # self.shutter_a_steps = list(range(1, 361))  # Whole numbers from 1 to 360
                self.pwm_controller.start_pwm(int(self.fps_saved), shutter_a_current, 2)

            time.sleep(1)
            self.redis_controller.set_value('cam_init', 1)
            logging.info(f"Restarting camera")
        
    def set_shutter_a_sync(self, shutter_a_sync):
        if shutter_a_sync == True:
            self.shutter_a_sync = True
            self.exposure_time_saved = self.exposure_time_s
            self.set_shutter_a_nom(float(self.redis_controller.get_value('shutter_a_nom')))
        elif shutter_a_sync == False:
            self.shutter_a_sync = False
            self.exposure_time_saved = self.exposure_time_s
            self.set_shutter_a_nom(float(self.redis_controller.get_value('shutter_a_nom')))
        
        logging.info(f"Shutter sync {self.shutter_a_sync}")
        
    def switch_fps(self):
        if self.fps_double == False:
            self.fps_saved = self.fps_actual
            self.fps_double = True
            self.set_fps(int(self.fps_actual))
            
        elif self.fps_double == True:
            self.fps_double = False
            self.set_fps(int(self.fps_saved))
        
    def print_settings(self):
        iso = self.get_setting('iso')
        shutter_a = self.get_setting('shutter_a')
        fps = self.get_setting('fps')
        height = self.get_setting('height')
        
        print()
        print(f"{'iso':<20}{iso:<20}{str(self.iso_steps):<20}")
        print(f"{'Shutter angle':<20}{shutter_a:<20}{str(self.shutter_a_steps):<20}")
        print(f"{'Shutter angle nom':<20}{self.shutter_a_nom:<20}{str(self.shutter_a_steps):<20}")
        print(f"{'FPS':<20}{fps:<20}{str(self.fps_steps):<20}")
        print(f"{'Resolution':<20}{height:<20}")
        print()
        print(f"{'Parameters Lock':<20}{str(self.parameters_lock):<20}")
        print()
        print(f"{'FPS Multiplier':<20}{str(self.fps_multiplier):<20}")
        print()
        print(f"{'Shutter sync':<20}{str(self.shutter_a_sync):<20}")
        print()
        print(f"{'PWM mode':<20}{str(self.pwm_mode):<20}")
        print(f"{'PWM freq':<20}{str(self.pwm_controller.freq):<20}")
        print(f"{'PWM shutter angle':<20}{str(self.pwm_controller.shutter_angle):<20}")
        print()
        print(f"{'GUI layout':<20}{str(self.gui_layout):<20}")
        
    def seconds_to_fraction_text(self, exposure_time_seconds):
        if exposure_time_seconds:
            denominator = 1/exposure_time_seconds
            
            exposure_fraction_text = "1"+"/"+ str(int(denominator))
            
            return exposure_fraction_text
        else:
            return 0



