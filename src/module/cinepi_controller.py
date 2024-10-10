import logging
import threading
import os
import time
import json
from fractions import Fraction
import math
import subprocess
from threading import Thread

# Import RedisListener
from module.redis_listener import RedisListener

class CinePiController:
    def __init__(self,
                 cinepi,
                 redis_controller,
                 pwm_controller,
                 ssd_monitor,
                 sensor_detect,
                 iso_steps,
                 shutter_a_steps,
                 fps_steps,
                 wb_steps,   # Use this directly
                 light_hz,
                 ):
        
        self.parameters_lock_obj = threading.Lock()
        self.cinepi = cinepi
        self.pwm_controller = pwm_controller
        self.redis_controller = redis_controller
        self.ssd_monitor = ssd_monitor
        self.sensor_detect = sensor_detect
        
        self.iso_steps = iso_steps
        self.shutter_a_steps = shutter_a_steps
        self.fps_steps = fps_steps
        self.wb_steps = wb_steps  # Use the provided wb_steps
        self.light_hz = light_hz
        
        self.wb_cg_rb_array = {}  # Initialize as an empty dictionary
        
        self.redis_listener = RedisListener(redis_controller)
        self.fps = int(round(float(self.redis_controller.get_value('fps_last'))))
        
        # Set startup flag
        self.startup = True
        
        self.parameters_lock = False
        self.iso_lock = False
        self.shutter_a_nom_lock = False
        self.fps_lock = False
        
        # Dictionary to store calculated values for different fps
        self.calculated_values = {}
        
        self.all_lock = False
        self.lock_override = False
        self.exposure_time_seconds = None
        self.exposure_time_fractions = None
        self.fps_multiplier = 1
        self.pwm_mode = False
        self.trigger_mode = 0
        self.fps_correction_factor = 1 #0.99798 # 0.9980 for imx585 mono
        self.fps_saved = float(self.redis_controller.get_value('fps'))
        self.fps_double = False
        self.ramp_up_speed = 0.2
        self.ramp_down_speed = 0.2
        self.fps_button_state = False
        self.fps_temp = 24
        self.fps_temp_old = 24
        self.shutter_a_sync = False
        self.shutter_a_nom = 180
        self.exposure_time_saved = 1/24
        self.current_sensor = self.sensor_detect.camera_model
        self.redis_controller.set_value('sensor', self.sensor_detect.camera_model)
        
        self.sensor_mode = int(self.redis_controller.get_value('sensor_mode'))
        self.fps_max = int(self.sensor_detect.get_fps_max(self.current_sensor, self.sensor_mode))
        self.redis_controller.set_value('fps_max', self.fps_max)
        self.gui_layout = self.sensor_detect.get_gui_layout(self.current_sensor, self.sensor_mode)
        self.exposure_time_s = float(self.redis_controller.get_value('shutter_a')) / 360 * (1 / self.fps) 
        self.exposure_time_saved = self.exposure_time_s
        self.file_size = self.sensor_detect.get_file_size(self.current_sensor, self.sensor_mode)
        
        self.settings = self.load_settings()  # Load other settings, if needed
        
        self.initialize_fps_steps(self.fps_steps)
        self.initialize_shutter_a_steps(self.shutter_a_steps)
        self.initialize_wb_cg_rb_array()  # Initialize the white balance array

        settings = self.load_settings()

        self.iso_free = settings['free_mode'].get('iso_free', False)
        self.shutter_a_free = settings['free_mode'].get('shutter_a_free', False)
        self.fps_free = settings['free_mode'].get('fps_free', False)
        self.wb_free = settings['free_mode'].get('wb_free', False)
        
        self.shutter_a_sync_mode = 0
        self.initial_exposure = None
        self.initial_motion_blur = None
        self.initial_shutter_a = None
        
        self.update_steps()

        # Set a timer to clear the startup flag after a short period
        threading.Timer(5.0, self.clear_startup_flag).start()

        # Communicate the initial fps to the web app
        self.set_fps(self.fps)
        logging.info(f"Initialized fps: {self.fps}")
        
        self.set_resolution(int(self.redis_controller.get_value('sensor_mode')))
        
    def set_shutter_a_sync_mode(self, mode=None):
        if mode is None:
            # Toggle the mode if no argument is provided
            mode = 1 if self.shutter_a_sync_mode == 0 else 0

        self.shutter_a_sync_mode = mode

        if mode == 0:
            # Deactivate shutter sync mode
            self.initial_exposure = None
            self.initial_motion_blur = None
            self.initial_shutter_a = None
            logging.info("Shutter Sync Mode deactivated")
        elif mode == 1:
            # Activate exposure constant mode
            self.initial_exposure = self.calculate_exposure()
            self.initial_shutter_a = self.redis_controller.get_value('shutter_a_nom')
            logging.info(f"Exposure constant mode activated with initial exposure: {self.initial_exposure} seconds")
            self.set_shutter_a_nom(float(self.redis_controller.get_value('shutter_a_nom')))

        logging.info(f"Shutter sync {'enabled' if self.shutter_a_sync_mode else 'disabled'}")

    def calculate_exposure(self):
        fps = self.redis_controller.get_value('fps')
        shutter_a_nom = self.redis_controller.get_value('shutter_a')
        return float(shutter_a_nom) / 360.0 / float(fps)

    def adjust_shutter_a_sync(self, fps=None, shutter_a_nom=None):
        if self.shutter_a_sync_mode == 1:
            if fps:
                # Calculate new shutter angle to maintain the constant exposure
                new_shutter_a_nom = self.initial_exposure * 360.0 * float(fps)
                new_shutter_a_nom = max(min(new_shutter_a_nom, 360), 1)  # Ensure within 1-360 degrees
                self.redis_controller.set_value('shutter_a_nom', new_shutter_a_nom)
                self.redis_controller.set_value('shutter_a', new_shutter_a_nom)
                logging.info(f"Exposure constant: Adjusting shutter_a_nom to {new_shutter_a_nom} degrees due to fps change to {fps}")
            elif shutter_a_nom:
                self.initial_exposure = float(shutter_a_nom) / 360.0 / float(self.redis_controller.get_value('fps'))
                self.redis_controller.set_value('shutter_a', shutter_a_nom)
                logging.info(f"Exposure constant: Updated stored exposure to {self.initial_exposure} seconds based on new shutter_a_nom {shutter_a_nom}")

    def update_steps(self):
        if self.iso_free:
            self.iso_steps = list(range(100, 3201, 50))
        if self.shutter_a_free:
            self.shutter_a_steps = [round(i * 0.1, 1) for i in range(10, 3601)]
        if self.fps_free:
            self.fps_steps = list(range(1, self.fps_max + 1))
        if self.wb_free:
            self.wb_steps = list(range(1, 6501, 100))
        
    def set_iso_free(self, value=None):
        if value is None:
            self.iso_free = not self.iso_free
        else:
            self.iso_free = value
        self.update_steps()
        logging.info(f"ISO Free Mode set to {self.iso_free}")

    def set_shutter_a_free(self, value=None):
        if value is None:
            self.shutter_a_free = not self.shutter_a_free
        else:
            self.shutter_a_free = value
        self.update_steps()
        logging.info(f"Shutter Angle Free Mode set to {self.shutter_a_free}")

    def set_fps_free(self, value=None):
        if value is None:
            self.fps_free = not self.fps_free
        else:
            self.fps_free = value
        self.update_steps()
        logging.info(f"FPS Free Mode set to {self.fps_free}")

    def set_wb_free(self, value=None):
        if value is None:
            self.wb_free = not self.wb_free
        else:
            self.wb_free = value
        self.update_steps()
        logging.info(f"WB Free Mode set to {self.wb_free}")

    def load_settings(self):
        try:
            with open('/home/pi/cinemate/src/settings.json', 'r') as file:
                settings = json.load(file)
                logging.info("Settings loaded successfully.")
                return settings
        except Exception as e:
            logging.error(f"Error loading settings: {e}")
            return {}

    def clear_startup_flag(self):
        self.startup = False
        # Communicate the current fps to the web app after the startup phase
        #self.redis_controller.set_value('fps', self.fps)

    def load_wb_steps(self):
        try:
            wb_steps = self.settings.get('arrays', {}).get('wb_steps', [])
            logging.info(f"WB steps loaded: {wb_steps}")
            return wb_steps
        except Exception as e:
            logging.error(f"Error loading WB steps: {e}")
            return []

    def initialize_fps_steps(self, fps_steps):
        self.fps_max = int(self.redis_controller.get_value('fps_max'))
        
        self.redis_controller.set_value('fps_max', self.fps_max)

        """Initialize fps_steps based on the provided list and capped by fps_max."""
        self.fps_steps_dynamic = [fps for fps in self.fps_steps if fps <= self.fps_max]
        logging.info(f"Initialized fps_steps: {self.fps_steps_dynamic}")

    def initialize_shutter_a_steps(self, shutter_a_steps):
        """Initialize shutter_a_steps based on the provided list and capped by 360."""
        self.shutter_a_steps_dynamic = [angle for angle in shutter_a_steps if angle <= 360]
        if not self.shutter_a_steps_dynamic:
            self.shutter_a_steps_dynamic = [45, 90, 135, 172.8, 180, 225, 270, 315, 360]
        logging.info(f"Initialized shutter_a_steps: {self.shutter_a_steps_dynamic}")

    def update_shutter_angle_for_fps(self):
        if self.fps <= 0:
            logging.error("fps must be greater than zero.")
            return

        # Calculate the closest legal shutter angle for the new fps
        current_shutter_angle = float(self.redis_controller.get_value('shutter_a'))
        self.shutter_a_steps_dynamic = self.calculate_dynamic_shutter_angles(self.fps)
        
        closest_shutter_angle = min(self.shutter_a_steps_dynamic, key=lambda x: abs(x - current_shutter_angle))
        
        logging.info(f"Updating shutter angle to the closest legal value: {closest_shutter_angle}")
        self.set_shutter_a(closest_shutter_angle)

    def set_fps(self, value):
        value = float(value) * self.fps_correction_factor #0.9980
        logging.info(f"Received set_fps call with value: {value}")
        
        

        if not self.fps_lock:
            max_fps = int(self.redis_controller.get_value('fps_max'))
            logging.info(f"Retrieved max_fps from Redis: {max_fps}")
            
            safe_value = max(1, min(value, max_fps))
            logging.info(f"Calculated safe_value: {safe_value}")
            
            if self.shutter_a_sync_mode:
                self.adjust_shutter_a_sync(fps=safe_value)

            if not self.parameters_lock or self.lock_override:
                if self.pwm_mode == False and self.shutter_a_sync == False:
                    self.redis_controller.set_value('fps', safe_value)
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
                    logging.info(f"Setting fps to {safe_value}")

                elif self.pwm_mode == True and self.shutter_a_sync == True:
                    self.redis_controller.set_value('fps', safe_value)
                    nominal_shutter_angle = float(self.get_setting('shutter_a_nom'))
                    new_shutter_angle = self.exposure_time_saved / (1 / safe_value) * 360
                    new_shutter_angle = max(min(new_shutter_angle, 360), 1)
                    new_shutter_angle = round(new_shutter_angle, 1)
                    if isinstance(new_shutter_angle, float) and new_shutter_angle.is_integer():
                        new_shutter_angle = int(new_shutter_angle)
                    self.set_shutter_a(new_shutter_angle)
                    logging.info(f"Setting fps to {safe_value} and shutter angle to {new_shutter_angle}")

                elif self.pwm_mode == True and self.shutter_a_sync == False:
                    self.redis_controller.set_value('fps', safe_value)
                    new_shutter_angle = float(self.get_setting('shutter_a'))
                    logging.info(f"Setting fps to {safe_value}")

            self.exposure_time_s = (float(self.redis_controller.get_value('shutter_a')) / 360) / float(self.redis_controller.get_value('fps'))
            self.exposure_time_fractions = self.seconds_to_fraction_text(self.exposure_time_s)
            
            self.update_fps_and_shutter_angles(safe_value)

    def set_iso_lock(self, value=None):
        if value is not None:
            if value in (0, False):
                self.iso_lock = False
            elif value in (1, True):
                self.iso_lock = True
            else:
                raise ValueError("Invalid value. Please provide either 0, 1, True, or False.")
        else:
            self.iso_lock = not self.iso_lock
        logging.info(f"ISO lock {self.iso_lock}")

    def set_shutter_a_nom_lock(self, value=None):
        if value is not None:
            if value in (0, False):
                self.shutter_a_nom_lock = False
            elif value in (1, True):
                self.shutter_a_nom_lock = True
            else:
                raise ValueError("Invalid value. Please provide either 0, 1, True, or False.")
        else:
            self.shutter_a_nom_lock = not self.shutter_a_nom_lock
        logging.info(f"Shutter angle lock {self.shutter_a_nom_lock}")

    def set_fps_lock(self, value=None):
        if value is not None:
            if value in (0, False):
                self.fps_lock = False
            elif value in (1, True):
                self.fps_lock = True
            else:
                raise ValueError("Invalid value. Please provide either 0, 1, True, or False.")
        else:
            self.fps_lock = not self.fps_lock
        logging.info(f"FPS lock {self.fps_lock}")
 
    def rec(self):
        logging.info(f"rec button pushed")
        if self.redis_controller.get_value('is_recording') == "0":
            self.start_recording()
        elif self.redis_controller.get_value('is_recording') == "1":
            self.stop_recording()
            
    def start_recording(self):
        if self.ssd_monitor.is_mounted == True and self.ssd_monitor.get_space_left:
            self.redis_controller.set_value('is_recording', 1)
            logging.info(f"Started recording")
        else:
            logging.info(f"No disk.")
            
    def stop_recording(self):
        self.redis_controller.set_value('is_recording', 0)
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

    def set_resolution(self, value=None):
        if value is not None:
            try:
                self.redis_controller.set_value('fps_last', self.redis_controller.get_value('fps'))
                if value not in self.sensor_detect.res_modes:
                    logging.info(f"Couldn't find sensor mode {value}. Trying with sensor_mode 0.")
                    value = 0
                
                self.redis_controller.set_value('sensor_mode', str(value))
                
                resolution_info = self.sensor_detect.res_modes[value]
                height_new = resolution_info.get('height', None)
                width_new = resolution_info.get('width', None)
                bit_depth_new = resolution_info.get('bit_depth', None)
                fps_max_new = resolution_info.get('fps_max', None)
                gui_layout_new = resolution_info.get('gui_layout', None)
                file_size_new = resolution_info.get('file_size', None)
                
                if height_new is None or width_new is None or gui_layout_new is None:
                    raise ValueError("Invalid height, width, or gui_layout value.")
                
                self.redis_controller.set_value('height', str(height_new))
                self.redis_controller.set_value('width', str(width_new))
                self.redis_controller.set_value('bit_depth', str(bit_depth_new))
                self.redis_controller.set_value('fps_max', str(fps_max_new))
                self.redis_controller.set_value('gui_layout', str(gui_layout_new))
                self.redis_controller.set_value('file_size', str(file_size_new))

                self.redis_controller.set_value('cam_init', 1)
                
                self.gui_layout = gui_layout_new
                
                logging.info(f"Resolution set to mode {value}, height: {height_new}, width: {width_new}, gui_layout: {gui_layout_new}")
                
                fps_current = int(float(self.redis_controller.get_value('fps')))
                time.sleep(0.5)
                
                self.cinepi.restart()
                
                self.set_fps(int(self.redis_controller.get_value('fps_last')))
                
                self.file_size = file_size_new
                
                # Initialize fps_steps based on the provided list and capped by fps_max
                self.initialize_fps_steps(self.fps_steps)
                self.shutter_a_steps_dynamic = self.calculate_dynamic_shutter_angles(self.fps)
                
                self.fps_max = int(self.redis_controller.get_value('fps_max'))
                if self.fps_free:
                    self.fps_steps = list(range(1, self.fps_max + 1))
                
                self.update_steps()
                
                self.redis_controller.set_value('sensor', self.sensor_detect.camera_model)

            except ValueError as error:
                logging.error(f"Error setting resolution: {error}")

        else:
            self.switch_resolution()
        
    def get_current_sensor_mode(self):
        current_height = int(self.redis_controller.get_value('height'))

        for mode, height_dict in self.sensor_detect.res_modes.items():
            if height_dict.get('height') == current_height:
                # Update fps_max based on the current sensor mode
                fps_max_value = height_dict.get('fps_max', None)
                self.redis_controller.set_value('fps_max', fps_max_value)

                # Update sensor_mode in Redis
                self.redis_controller.set_value('sensor_mode', mode)

                return mode

        return None  # Return None if no matching sensor mode is found

    def set_iso(self, value):
        if not self.iso_lock:
            with self.parameters_lock_obj:
                safe_value = max(min(value, max(self.iso_steps)), min(self.iso_steps))
                self.redis_controller.set_value('iso', safe_value)
                logging.info(f"Setting iso to {safe_value}")

    def set_shutter_a(self, value):
        with self.parameters_lock_obj:
            safe_value = max(1, min(value, 360))  # Ensure the value is between 1 and 360 degrees
            self.redis_controller.set_value('shutter_a', safe_value)
            self.exposure_time_seconds = (safe_value / 360.0) / self.fps
            self.exposure_time_fractions = self.seconds_to_fraction_text(self.exposure_time_seconds)
            logging.info(f"Setting shutter_a to {safe_value} degrees")
            if self.shutter_a_sync_mode:
                self.adjust_shutter_a_sync(shutter_a_nom=safe_value)  # Ensure only correct argument is passed

    def set_shutter_a_nom(self, value):
        if not self.shutter_a_nom_lock:
            with self.parameters_lock_obj:
                safe_value = max(1, min(value, 360))
                self.redis_controller.set_value('shutter_a_nom', safe_value)
                self.exposure_time_seconds = (safe_value / 360.0) / self.fps
                self.exposure_time_fractions = self.seconds_to_fraction_text(self.exposure_time_seconds)
                logging.info(f"Setting shutter_a_nom to {value}")
                
            if self.shutter_a_sync:
                nominal_shutter_angle = float(self.redis_controller.get_value('shutter_a_nom'))
                exposure_time_desired = (nominal_shutter_angle / 360) * (1 / self.fps)
                synced_shutter_angle = (exposure_time_desired / (1 / self.fps)) * 360
                synced_shutter_angle = round(synced_shutter_angle, 1)
                if isinstance(synced_shutter_angle, float) and synced_shutter_angle.is_integer():
                    synced_shutter_angle = int(synced_shutter_angle)
                self.set_shutter_a(synced_shutter_angle)
            else:
                self.set_shutter_a(safe_value)
                
            if self.shutter_a_sync_mode:
                self.adjust_shutter_a_sync(shutter_a_nom=value)

    def set_shu_fps_lock(self, value=None):
        if value is not None:
            if value in (0, False):
                self.shutter_a_nom_lock = False
                self.fps_lock = False
            elif value in (1, True):
                self.shutter_a_nom_lock = True
                self.fps_lock = True
            else:
                raise ValueError("Invalid value. Please provide either 0, 1, True, or False.")
        else:
            self.shutter_a_nom_lock = not self.shutter_a_nom_lock
            self.fps_lock = not self.fps_lock
        logging.info(f"Shutter angle lock {self.shutter_a_nom_lock}")
        logging.info(f"FPS lock {self.fps_lock}")
        
    def set_all_lock(self, value=None):
        if value is not None:
            if value in (0, False):
                self.all_lock = False
                self.iso_lock = False
                self.shutter_a_nom_lock = False
                self.fps_lock = False
            elif value in (1, True):
                self.all_lock = True
                self.iso_lock = True
                self.shutter_a_nom_lock = True
                self.fps_lock = True
            else:
                raise ValueError("Invalid value. Please provide either 0, 1, True, or False.")
        else:
            self.all_lock = not self.all_lock
            self.iso_lock = not self.iso_lock
            self.shutter_a_nom_lock = not self.shutter_a_nom_lock
            self.fps_lock = not self.fps_lock
            
        logging.info(f"ISO lock {self.iso_lock}")  
        logging.info(f"Shutter angle lock {self.shutter_a_nom_lock}")
        logging.info(f"FPS lock {self.fps_lock}")
        
    def set_fps_multiplier(self, value):
        with self.parameters_lock_obj:
            self.fps_multiplier = value
            logging.info(f"FPS multiplier {self.fps_multiplier}")
                
    def get_setting(self, key):
        value = self.redis_controller.get_value(key)
        return value
    
    def reboot(self):
        if self.redis_controller.get_value('is_recording') == "1":
            self.stop_recording()
        logging.info("Initiating safe system shutdown.")
        os.system("sudo reboot")
        
    def safe_shutdown(self):
        if self.redis_controller.get_value('is_recording') == "1":
            self.stop_recording()
        logging.info("Initiating safe system shutdown.")
        os.system("sudo shutdown -h now")
        
    def unmount(self):
        self.ssd_monitor.unmount_drive()
    
    def calculate_dynamic_shutter_angles(self, fps):
        if fps <= 0:
            fps = 1 
            #raise ValueError("FPS must be greater than zero.")

        dynamic_steps = self.shutter_a_steps.copy()  # Start with normal shutter angle values
        for hz in self.light_hz:
            flicker_free_angles = self.calculate_flicker_free_shutter_angles(fps, hz)
            dynamic_steps.extend(flicker_free_angles)
        dynamic_steps = sorted(set(dynamic_steps))  # Remove duplicates and sort
        logging.info(dynamic_steps)
        return dynamic_steps

    def calculate_flicker_free_shutter_angles(self, fps, hz):
        if fps <= 0:
            raise ValueError("FPS must be greater than zero.")
        
        flicker_free_angles = []
        for multiple in range(1, int(hz / fps) + 1):
            angle = 360 / multiple
            flicker_free_angles.append(angle)
        return flicker_free_angles

    def update_fps_and_shutter_angles(self, fps):
        if fps <= 0:
            logging.error("FPS must be greater than zero.")
            return

        self.fps = int(fps)
        self.shutter_a_steps_dynamic = self.calculate_dynamic_shutter_angles(fps)

    def increment_setting(self, setting_name, steps, fps=None):
        if self.pwm_mode == False:
            current_value = float(self.get_setting(setting_name))
            if setting_name == 'shutter_a':
                dynamic_steps = self.calculate_dynamic_shutter_angles(self.fps)
                self.shutter_a_steps_dynamic = dynamic_steps
            else:
                dynamic_steps = steps
            if setting_name == 'fps':
                current_value = int(round(float(self.get_setting(setting_name))))
            if current_value in dynamic_steps:
                idx = dynamic_steps.index(current_value)
                idx = min(idx + 1, len(dynamic_steps) - 1)
            else:
                idx = 0
            getattr(self, f"set_{setting_name}")(dynamic_steps[idx])
            logging.info(f"Increasing {setting_name} to {self.get_setting(setting_name)}")
        elif self.pwm_mode == True and setting_name == 'fps':
            self.set_fps(int(self.fps) + 1)

    def decrement_setting(self, setting_name, steps, fps=None):
        if self.pwm_mode == False:
            current_value = float(self.get_setting(setting_name))
            if setting_name == 'shutter_a':
                dynamic_steps = self.calculate_dynamic_shutter_angles(self.fps)
                self.shutter_a_steps_dynamic = dynamic_steps
            else:
                dynamic_steps = steps
            if setting_name == 'fps':
                current_value = int(round(float(self.get_setting(setting_name))))
            if current_value in dynamic_steps:
                idx = dynamic_steps.index(current_value)
                idx = max(idx - 1, 0)
            else:
                idx = 0
            getattr(self, f"set_{setting_name}")(dynamic_steps[idx])
            logging.info(f"Decreasing {setting_name} to {self.get_setting(setting_name)}")
        elif self.pwm_mode == True and setting_name == 'fps':
            self.set_fps(int(self.fps) - 1)
    def inc_shutter_a(self):
        self.increment_setting('shutter_a', self.shutter_a_steps, fps=self.fps)

    def dec_shutter_a(self):
        self.decrement_setting('shutter_a', self.shutter_a_steps, fps=self.fps)
    
    def inc_iso(self):
        self.increment_setting('iso', self.iso_steps)

    def dec_iso(self):
        self.decrement_setting('iso', self.iso_steps)
        
    def inc_shutter_a_nom(self):
        self.increment_setting('shutter_a_nom', self.shutter_a_steps)

    def dec_shutter_a_nom(self):
        self.decrement_setting('shutter_a_nom', self.shutter_a_steps)

    def inc_fps(self):
        self.increment_setting('fps', self.fps_steps)

    def dec_fps(self):
        self.decrement_setting('fps', self.fps_steps)
        
    def initialize_wb_cg_rb_array(self):
        """Initialize the white balance cg_rb array based on the sensor model."""
        if self.current_sensor == 'imx283':
            default_ct_curve =  [
                    2213.0, 0.9607, 0.2593,
                    2255.0, 0.9309, 0.2521,
                    2259.0, 0.9257, 0.2508,
                    5313.0, 0.4822, 0.5909,
                    6237.0, 0.4726, 0.6376
                ]
        else:                
            default_ct_curve = [
                2000.0, 0.6331025775790707, 0.27424225990946915,
                2200.0, 0.5696117366212947, 0.3116091368689487,
                2400.0, 0.5204264653110015, 0.34892179554105873,
                2600.0, 0.48148675531667223, 0.38565229719076793,
                2800.0, 0.450085403501908, 0.42145684622485047,
                3000.0, 0.42436130159169017, 0.45611835670028816,
                3200.0, 0.40300023695527337, 0.48950766215198593,
                3400.0, 0.3850520052612984, 0.5215567075837261,
                3600.0, 0.36981508088230314, 0.5522397906415475,
                4100.0, 0.333468007836758, 0.5909770465167908,
                4600.0, 0.31196097364221376, 0.6515706327327178,
                5100.0, 0.2961860409294588, 0.7068178946570284,
                5600.0, 0.2842607232745885, 0.7564837749584288,
                6100.0, 0.2750265787051251, 0.8006183524920533,
                6600.0, 0.2677057225584924, 0.8398879225373039,
                7100.0, 0.2617955199757274, 0.8746456080032436,
                7600.0, 0.25693714288250125, 0.905569559506562,
                8100.0, 0.25287531441063316, 0.9331696750390895,
                8600.0, 0.24946601483331993, 0.9576820904825795
            ]

        self.wb_cg_rb_array = {}  # Ensuring it is initialized as a dictionary

        try:
            tuning_file_path = f"/home/pi/cinemate/resources/tuning_files/{self.current_sensor}.json"
            logging.info(f"Loading tuning file from: {tuning_file_path}")

            with open(tuning_file_path, 'r') as file:
                data = json.load(file)
                logging.info("Tuning data loaded successfully.")

            awb_data = next((algo['rpi.awb'] for algo in data['algorithms'] if 'rpi.awb' in algo), None)
            if not awb_data:
                logging.warning("'rpi.awb' algorithm data not found, using default ct_curve.")
                ct_curve = default_ct_curve
            else:
                logging.info(f"'rpi.awb' data found: {awb_data}")
                ct_curve = awb_data.get('ct_curve', None)
                if not ct_curve:
                    logging.warning("'ct_curve' not found in 'rpi.awb' data, using default ct_curve.")
                    ct_curve = default_ct_curve
                else:
                    logging.info(f"Retrieved ct_curve: {ct_curve}")

            temperatures = ct_curve[0::3]
            r_values = ct_curve[1::3]
            b_values = ct_curve[2::3]
            logging.info(f"Parsed temperatures: {temperatures}")
            logging.info(f"Parsed r_values: {r_values}")
            logging.info(f"Parsed b_values: {b_values}")

            for wb in self.wb_steps:
                lower_idx = max(i for i, temp in enumerate(temperatures) if temp <= wb)
                upper_idx = min(i for i, temp in enumerate(temperatures) if temp >= wb)

                logging.info(f"Interpolating for wb step: {wb}K, lower index: {lower_idx}, upper index: {upper_idx}")

                if lower_idx == upper_idx:
                    r_interp = r_values[lower_idx]
                    b_interp = b_values[lower_idx]
                    logging.info(f"Exact match found at index {lower_idx}, r_interp: {r_interp}, b_interp: {b_interp}")
                else:
                    r_interp = self.interpolate(temperatures[lower_idx], r_values[lower_idx],
                                                temperatures[upper_idx], r_values[upper_idx], wb)
                    b_interp = self.interpolate(temperatures[lower_idx], b_values[lower_idx],
                                                temperatures[upper_idx], b_values[upper_idx], wb)
                    logging.info(f"Interpolated values for {wb}K - r_interp: {r_interp}, b_interp: {b_interp}")

                self.wb_cg_rb_array[wb] = (round(1/r_interp, 1), round(1/b_interp, 1))
                logging.info(f"Calculated reciprocal cg_rb for {wb}K: {self.wb_cg_rb_array[wb]}")

            logging.info(f"Initialized wb_cg_rb_array: {self.wb_cg_rb_array}")
        except KeyError as e:
            logging.error(f"Key error in initializing wb_cg_rb_array: {e}")
            self.wb_cg_rb_array = {}
        except Exception as e:
            logging.error(f"Failed to initialize wb_cg_rb_array: {e}")
            self.wb_cg_rb_array = {}


    def interpolate(self, x1, y1, x2, y2, x):
        """Perform linear interpolation."""
        logging.debug(f"Interpolating with points ({x1}, {y1}) and ({x2}, {y2}) for x = {x}")
        result = y1 + (y2 - y1) * (x - x1) / (x2 - x1)
        logging.debug(f"Interpolated result: {result}")
        return result

    def set_wb(self, kelvin_temperature=None, direction='next'):
        """Set white balance based on the Kelvin temperature or direction."""
        logging.debug(f"WB steps available: {self.wb_steps}")
        
        if not self.wb_steps:
            logging.error("WB steps are not defined or empty.")
            return  # Exit if wb_steps is empty to prevent further errors
        
        if kelvin_temperature is None:
            current_kelvin = self.redis_controller.get_value('wb_user')
            if current_kelvin:
                try:
                    current_kelvin = int(current_kelvin)
                    logging.info(f"Parsed current wb_user value: {current_kelvin}")
                except ValueError:
                    current_kelvin = None
                    logging.error(f"Error parsing current wb_user value from Redis: {self.redis_controller.get_value('wb_user')}")

            found_index = None
            if current_kelvin in self.wb_steps:
                found_index = self.wb_steps.index(current_kelvin)

            if found_index is not None:
                if direction == 'next':
                    next_index = (found_index + 1) % len(self.wb_steps)
                elif direction == 'prev':
                    next_index = (found_index - 1) % len(self.wb_steps)
            else:
                next_index = 0

            kelvin_temperature = self.wb_steps[next_index]
        else:
            closest_temperature = min(self.wb_steps, key=lambda t: abs(t - kelvin_temperature))
            kelvin_temperature = closest_temperature

        cg_rb_value = self.wb_cg_rb_array.get(kelvin_temperature, None)
        if cg_rb_value:
            self.redis_controller.set_value('cg_rb', f"{cg_rb_value[0]},{cg_rb_value[1]}")
            self.redis_controller.set_value('wb_user', str(kelvin_temperature))
            logging.info(f"Set white balance for {kelvin_temperature}K: {cg_rb_value}")
        else:
            logging.error(f"White balance value not found for {kelvin_temperature}K")

    def inc_wb(self):
        self.set_wb(direction='next')

    def dec_wb(self):
        self.set_wb(direction='prev')
        
    def set_pwm_mode(self, value=None):
        if self.current_sensor != 'imx477':
            logging.info(f"Current sensor {self.current_sensor}. PWM mode not availabe")
        else:
            if self.pwm_mode == False:
                self.fps_saved = float(self.get_setting('fps'))

            if value is not None:
                self.pwm_mode = value
            else:
                value = not self.pwm_mode
            
            logging.info(f"Setting pwm mode mode to {value}")

            if value== False:

                self.set_fps(self.fps_saved)
            elif value == True:
                self.fps_saved = float(self.get_setting('fps'))
                shutter_a_current = float(self.get_setting('shutter_a_nom'))
            
    def set_trigger_mode(self, value=None):
        # Define the mapping for string arguments
        mode_map = {
            'default': 0,
            'source': 1 if self.sensor_detect.camera_model == 'imx477' else 2,
            'sink': 2 if self.sensor_detect.camera_model == 'imx477' else 1,
        }

        # Retrieve current mode from Redis
        current_mode = int(self.redis_controller.get_value('trigger_mode', 0))

        if value is None:
            # Toggle to the next mode
            value = (current_mode + 1) % 3
        elif isinstance(value, str):
            # Convert string arguments to corresponding numeric values
            if value in mode_map:
                value = mode_map[value]
            else:
                raise ValueError("Invalid string argument. Must be 'default', 'source', or 'sink'.")
        elif value not in [0, 1, 2]:
            raise ValueError("Invalid argument: must be 0, 1, 2, 'default', 'source', or 'sink'.")

        # Determine the command based on the value and camera model
        if self.sensor_detect.camera_model == 'imx477':
            command = f'echo {value} > /sys/module/imx477/parameters/trigger_mode'
        elif self.sensor_detect.camera_model == 'imx296':
            if value == 2: value = 1  # Adjust for imx296 sensor
            elif value == 1: value = 2  # Adjust for imx296 sensor
            command = f'echo {value} > /sys/module/imx296/parameters/trigger_mode'
        else:
            raise ValueError("Unsupported camera model.")

        # Execute the command to set the trigger mode
        full_command = ['sudo', 'su', '-c', command]
        subprocess.run(full_command, check=True)
        logging.info(f"Trigger mode set to {value}")

        # Update the trigger mode in Redis and instance variable
        self.trigger_mode = value
        self.redis_controller.set_value('trigger_mode', str(value))

        # Restart the cinepi process to apply the changes
        self.restart_camera()
        
    def restart_camera(self):
        self.cinepi.restart()

    def set_shutter_a(self, value):
        with self.parameters_lock_obj:
            safe_value = max(1, min(value, 360))  # Ensure the value is between 1 and 360 degrees
            self.redis_controller.set_value('shutter_a', safe_value)
            self.exposure_time_seconds = (safe_value / 360.0) / self.fps
            self.exposure_time_fractions = self.seconds_to_fraction_text(self.exposure_time_seconds)
            logging.info(f"Setting shutter_a to {safe_value} degrees")
            if self.shutter_a_sync_mode:
                self.adjust_shutter_a_sync(shutter_a=safe_value)


    def set_fps_double(self, value=None):
        target_double_state = not self.fps_double if value is None else value in (1, True)

        if self.pwm_mode:
            self._ramp_fps(target_double_state)
        else:
            if target_double_state:
                if not self.fps_double:
                    self.fps_saved = self.fps
                    target_fps = min(self.fps * 2, self.fps_max)
                    self.set_fps(target_fps)
            else:
                if self.fps_double:
                    self.set_fps(self.fps_saved)
            
            self.fps_double = target_double_state

        logging.info(f"FPS double mode is {'enabled' if self.fps_double else 'disabled'}, Current FPS: {self.fps}")

    def _ramp_fps(self, target_double_state):
        if target_double_state and not self.fps_double:
            self.fps_saved = self.fps
            target_fps = min(self.fps_temp * 2, self.fps_max)

            while self.fps < target_fps:
                logging.info('Ramping up')
                self.fps += 1
                self.set_fps(self.fps)
                time.sleep(self.ramp_up_speed)
        elif not target_double_state and self.fps_double:
            while self.fps > self.fps_saved:
                logging.info('Ramping down')
                self.fps -= 1
                self.set_fps(self.fps)
                time.sleep(self.ramp_down_speed)

        self.fps_double = target_double_state
        
    def print_settings(self):
        iso = self.get_setting('iso')
        shutter_a = self.get_setting('shutter_a')
        fps = self.get_setting('fps')
        height = self.get_setting('height')
        
        print()
        print(f"{'iso':<20}{iso:<20}{str(self.iso_steps):<20}")
        print(f"{'Shutter angle':<20}{shutter_a:<20}{str(self.shutter_a_steps_dynamic):<20}")
        print(f"{'Shutter angle nom':<20}{self.shutter_a_nom:<20}{str(self.shutter_a_steps):<20}")
        print(f"{'FPS':<20}{fps:<20}{str(self.fps_steps_dynamic):<20}")
        print(f"{'Resolution':<20}{height:<20}")
        print()
        print(f"{'Parameters Lock':<20}{str(self.parameters_lock):<20}")
        print()
        print(f"{'FPS Multiplier':<20}{str(self.fps_multiplier):<20}")
        print()
        print(f"{'Shutter sync':<20}{str(self.shutter_a_sync):<20}")
        print()
        print(f"{'PWM mode':<20}{str(self.pwm_mode):<20}")
        print()
        print(f"{'GUI layout':<20}{str(self.gui_layout):<20}")
        
    def seconds_to_fraction_text(self, exposure_time_seconds):
        if exposure_time_seconds:
            denominator = 1/exposure_time_seconds
            exposure_fraction_text = "1"+"/"+ str(int(denominator))
            return exposure_fraction_text
        else:
            return 0
    
    def set_filter(self, value=None):
        if 'imx585' in self.current_sensor:
            if value == 1:
                logging.info("Enabling IR Filter")
                result = os.system("IRFilter --enable")
                self.redis_controller.set_value('ir_filter', 1)
            elif value == 0:
                logging.info("Disabling IR Filter")
                result = os.system("IRFilter --disable")
                self.redis_controller.set_value('ir_filter', 0)
            else:
                return "Invalid value provided."
        else:
            return "IR Filter is not supported for this sensor."
