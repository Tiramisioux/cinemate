import logging
import threading
import os
import time
from fractions import Fraction
import math
import subprocess
from threading import Thread

# Import RedisListener
from module.redis_listener import RedisListener

class CinePiController:
    def __init__(self,
                 cinepi,
                 pwm_controller, 
                 redis_controller,
                 ssd_monitor,
                 sensor_detect,
                 iso_steps,
                 shutter_a_steps,
                 fps_steps,
                 awb_steps,
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
        self.awb_steps = awb_steps
        self.light_hz = light_hz
        
        self.redis_listener = RedisListener(redis_controller, self.update_fps_actual)
        self.fps_actual = self.redis_listener.framerate if self.redis_listener.framerate else 1
        
        # Set startup flag
        self.startup = True
        
        self.parameters_lock = False
        self.iso_lock = False
        self.shutter_a_nom_lock = False
        self.fps_lock = False
        self.all_lock = False
        self.lock_override = False
        self.exposure_time_seconds = None
        self.exposure_time_fractions = None
        self.fps_multiplier = 1
        self.pwm_mode = False
        self.fps_saved = float(self.redis_controller.get_value('fps_actual'))
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
        self.sensor_mode = int(self.redis_controller.get_value('sensor_mode'))
        self.fps_max = int(self.sensor_detect.get_fps_max(self.current_sensor, self.sensor_mode))
        self.redis_controller.set_value('fps_max', self.fps_max)
        self.gui_layout = self.sensor_detect.get_gui_layout(self.current_sensor, self.sensor_mode)
        self.exposure_time_s = float(self.redis_controller.get_value('shutter_a')) / 360 * 1 / self.fps_actual
        self.exposure_time_saved = self.exposure_time_s
        self.file_size = self.sensor_detect.get_file_size(self.current_sensor, self.sensor_mode)
        
        self.initialize_fps_steps(self.fps_steps)
        self.initialize_shutter_a_steps(self.shutter_a_steps)

        # Set a timer to clear the startup flag after a short period
        threading.Timer(5.0, self.clear_startup_flag).start()

        # Communicate the initial fps_actual to the web app
        self.redis_controller.set_value('fps_actual', self.fps_actual)

    def clear_startup_flag(self):
        self.startup = False
        # Communicate the current fps_actual to the web app after the startup phase
        self.redis_controller.set_value('fps_actual', self.fps_actual)

    def initialize_fps_steps(self, fps_steps):
        self.fps_max = int(self.redis_controller.get_value('fps_max'))
        
        self.redis_controller.set_value('fps_max', self.fps_max)
        
        print(self.fps_max)
        """Initialize fps_steps based on the provided list and capped by fps_max."""
        self.fps_steps_dynamic = [fps for fps in self.fps_steps if fps <= self.fps_max]
        logging.info(f"Initialized fps_steps: {self.fps_steps_dynamic}")

    def initialize_shutter_a_steps(self, shutter_a_steps):
        """Initialize shutter_a_steps based on the provided list and capped by 360."""
        self.shutter_a_steps_dynamic = [angle for angle in shutter_a_steps if angle <= 360]
        if not self.shutter_a_steps_dynamic:
            self.shutter_a_steps_dynamic = [45, 90, 135, 172.8, 180, 225, 270, 315, 360]
        logging.info(f"Initialized shutter_a_steps: {self.shutter_a_steps_dynamic}")

    def update_fps_actual(self, new_framerate):
        new_framerate_rounded = round(new_framerate)
        if new_framerate_rounded == 0:
            logging.error(f"Received invalid fps_actual value: {new_framerate_rounded}, fps_actual remains unchanged.")
            return

        # Ignore updates during startup phase
        if self.startup:
            #logging.info(f"Ignoring fps_actual update to {new_framerate_rounded} during startup phase.")
            return

        # Allow setting fps_actual to 29 manually and check for redundancy
        if new_framerate_rounded != round(self.fps_actual) or new_framerate_rounded == 29:
            if new_framerate_rounded == round(self.fps_actual) and self.redis_controller.get_value('fps_actual') == str(new_framerate_rounded):
                # Skip redundant updates
                return
            
            self.fps_actual = new_framerate_rounded
            logging.info(f"Updated fps_actual to {new_framerate_rounded}")
            self.redis_controller.set_value('fps_actual', new_framerate_rounded)
            self.update_shutter_angle_for_fps()

    def update_shutter_angle_for_fps(self):
        if self.fps_actual <= 0:
            logging.error("fps_actual must be greater than zero.")
            return

        # Calculate the closest legal shutter angle for the new fps_actual
        current_shutter_angle = float(self.redis_controller.get_value('shutter_a'))
        self.shutter_a_steps_dynamic = self.calculate_dynamic_shutter_angles(self.fps_actual)
        
        closest_shutter_angle = min(self.shutter_a_steps_dynamic, key=lambda x: abs(x - current_shutter_angle))
        
        logging.info(f"Updating shutter angle to the closest legal value: {closest_shutter_angle}")
        self.set_shutter_a(closest_shutter_angle)

    def set_fps(self, value):
        value = int(float(value))
        logging.info(f"Received set_fps call with value: {value}")

        if not self.fps_lock:
            max_fps = int(self.redis_controller.get_value('fps_max'))
            logging.info(f"Retrieved max_fps from Redis: {max_fps}")
            
            safe_value = max(1, min(value, max_fps))
            logging.info(f"Calculated safe_value: {safe_value}")

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
                    nominal_shutter_angle = float(self.get_setting('shutter_a_nom'))
                    new_shutter_angle = self.exposure_time_saved / (1 / safe_value) * 360
                    new_shutter_angle = max(min(new_shutter_angle, 360), 1)
                    new_shutter_angle = round(new_shutter_angle, 1)
                    if isinstance(new_shutter_angle, float) and new_shutter_angle.is_integer():
                        new_shutter_angle = int(new_shutter_angle)
                    self.set_shutter_a(new_shutter_angle)
                    self.pwm_controller.set_pwm(fps=int(safe_value), shutter_angle=new_shutter_angle)
                    logging.info(f"Setting fps to {safe_value} and shutter angle to {new_shutter_angle}")

                elif self.pwm_mode == True and self.shutter_a_sync == False:
                    new_shutter_angle = float(self.get_setting('shutter_a'))
                    self.pwm_controller.set_pwm(fps=float(safe_value), shutter_angle=new_shutter_angle)
                    logging.info(f"Setting fps to {safe_value}")

                self.exposure_time_s = (float(self.redis_controller.get_value('shutter_a')) / 360) / self.fps_actual
                self.exposure_time_fractions = self.seconds_to_fraction_text(self.exposure_time_s)
                logging.info(f"Updating fps_actual to: {safe_value}")
                self.redis_controller.set_value('fps_actual', safe_value)
                
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
                self.redis_controller.set_value('fps_last', self.redis_controller.get_value('fps_actual'))
                if value not in self.sensor_detect.res_modes:
                    logging.info(f"Couldn't find sensor mode {value}. Trying with sensor_mode 0.")
                    value = 0
                
                resolution_info = self.sensor_detect.res_modes[value]
                height_value = resolution_info.get('height', None)
                width_value = resolution_info.get('width', None)
                bit_depth_value = resolution_info.get('bit_depth', None)
                fps_max_value = resolution_info.get('fps_max', None)
                gui_layout_value = resolution_info.get('gui_layout', None)
                file_size_value = resolution_info.get('file_size', None)
                
                if height_value is None or width_value is None or gui_layout_value is None:
                    raise ValueError("Invalid height, width, or gui_layout value.")
                
                self.redis_controller.set_value('sensor', str(self.sensor_detect.camera_model))
                self.redis_controller.set_value('height', str(height_value))
                self.redis_controller.set_value('width', str(width_value))
                self.redis_controller.set_value('bit_depth', str(bit_depth_value))
                self.redis_controller.set_value('fps_max', str(fps_max_value))
                self.redis_controller.set_value('gui_layout', str(gui_layout_value))
                self.redis_controller.set_value('file_size', str(file_size_value))
                self.redis_controller.set_value('sensor_mode', str(value))
                self.redis_controller.set_value('cam_init', 1)
                
                self.gui_layout = gui_layout_value
                
                logging.info(f"Resolution set to mode {value}, height: {height_value}, width: {width_value}, gui_layout: {gui_layout_value}")

                fps_current = int(float(self.redis_controller.get_value('fps_last')))
                
                self.cinepi.restart()
                
                time.sleep(2)
                self.set_fps(int(self.redis_controller.get_value('fps_last')))
                
                self.file_size = file_size_value
                
                # Initialize fps_steps based on the provided list and capped by fps_max
                self.initialize_fps_steps(self.fps_steps)
                self.shutter_a_steps_dynamic = self.calculate_dynamic_shutter_angles(self.fps_actual)

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
            self.redis_controller.set_value('shutter_a', value)
            self.exposure_time_seconds = (float(self.redis_controller.get_value('shutter_a'))/360) / 1/self.fps_actual
            self.exposure_time_fractions = self.seconds_to_fraction_text(self.exposure_time_seconds)
            logging.info(f"Setting shutter_a to {value}")
            if self.pwm_mode:
                self.pwm_controller.set_pwm(shutter_angle=value)
                
        self.exposure_time_s = float(self.redis_controller.get_value('shutter_a'))/360 * 1/self.fps_actual

    def set_shutter_a_nom(self, value):
        if not self.shutter_a_nom_lock:
            with self.parameters_lock_obj:
                safe_value = max(1, min(value, 360))
                self.redis_controller.set_value('shutter_a_nom', safe_value)
                self.exposure_time_seconds = (float(self.redis_controller.get_value('shutter_a'))/360) / 1/self.fps_actual
                self.exposure_time_fractions = self.seconds_to_fraction_text(self.exposure_time_seconds)
                logging.info(f"Setting shutter_a_nom to {value}")
                
            if self.shutter_a_sync:
                nominal_shutter_angle = float(self.redis_controller.get_value('shutter_a_nom'))
                exposure_time_desired = (nominal_shutter_angle / 360) * (1 / self.fps_actual)
                synced_shutter_angle = (exposure_time_desired / (1 / self.fps_actual)) * 360
                synced_shutter_angle = round(synced_shutter_angle, 1)
                if isinstance(synced_shutter_angle, float) and synced_shutter_angle.is_integer():
                    synced_shutter_angle = int(synced_shutter_angle)
                self.set_shutter_a(synced_shutter_angle)
            else:
                self.set_shutter_a(safe_value)
                
            self.exposure_time_s = float(self.redis_controller.get_value('shutter_a'))/360 * 1/self.fps_actual

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
            raise ValueError("FPS must be greater than zero.")

        dynamic_steps = self.shutter_a_steps.copy()  # Start with normal shutter angle values
        for hz in self.light_hz:
            flicker_free_angles = self.calculate_flicker_free_shutter_angles(fps, hz)
            dynamic_steps.extend(flicker_free_angles)
        dynamic_steps = sorted(set(dynamic_steps))  # Remove duplicates and sort
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
        self.fps_actual = int(fps)
        self.shutter_a_steps_dynamic = self.calculate_dynamic_shutter_angles(fps)

    def set_awb(self, value):
        value = int(value)
        if 0 <= value <= 7:
            self.redis_controller.set_value('awb', value)
            logging.info(f"Setting AWB to {value}")
            self.cinepi.restart()
            time.sleep(2)
            self.set_fps(int(self.redis_controller.get_value('fps_last')))
        else:
            logging.error("Invalid AWB value. It should be between 0 and 7.")

    def inc_awb(self):
        current_value = int(self.redis_controller.get_value('awb'))
        new_value = (current_value + 1) % 8
        self.set_awb(new_value)

    def dec_awb(self):
        current_value = int(self.redis_controller.get_value('awb'))
        new_value = (current_value - 1) % 8
        self.set_awb(new_value)

    def increment_setting(self, setting_name, steps, fps=None):
        if setting_name == 'awb':
            current_value = int(self.get_setting(setting_name))
            dynamic_steps = self.awb_steps  # AWB steps from settings
            if current_value in dynamic_steps:
                idx = dynamic_steps.index(current_value)
                idx = min(idx + 1, len(dynamic_steps) - 1)
            else:
                idx = 0
            getattr(self, f"set_{setting_name}")(dynamic_steps[idx])
            logging.info(f"Increasing {setting_name} to {self.get_setting(setting_name)}")
        else:
            if self.pwm_mode == False:
                current_value = float(self.get_setting(setting_name))
                if setting_name == 'shutter_a':
                    dynamic_steps = self.calculate_dynamic_shutter_angles(self.fps_actual)
                    self.shutter_a_steps_dynamic = dynamic_steps
                else:
                    dynamic_steps = steps
                if current_value in dynamic_steps:
                    idx = dynamic_steps.index(current_value)
                    idx = min(idx + 1, len(dynamic_steps) - 1)
                else:
                    idx = 0
                getattr(self, f"set_{setting_name}")(dynamic_steps[idx])
                logging.info(f"Increasing {setting_name} to {self.get_setting(setting_name)}")
            elif self.pwm_mode == True and setting_name == 'fps':
                self.set_fps(int(self.fps_actual) + 1)

    def decrement_setting(self, setting_name, steps, fps=None):
        if setting_name == 'awb':
            current_value = int(self.get_setting(setting_name))
            dynamic_steps = self.awb_steps  # AWB steps from settings
            if current_value in dynamic_steps:
                idx = dynamic_steps.index(current_value)
                idx = max(idx - 1, 0)
            else:
                idx = 0
            getattr(self, f"set_{setting_name}")(dynamic_steps[idx])
            logging.info(f"Decreasing {setting_name} to {self.get_setting(setting_name)}")
        else:
            if self.pwm_mode == False:
                current_value = float(self.get_setting(setting_name))
                if setting_name == 'shutter_a':
                    dynamic_steps = self.calculate_dynamic_shutter_angles(self.fps_actual)
                    self.shutter_a_steps_dynamic = dynamic_steps
                else:
                    dynamic_steps = steps
                if current_value in dynamic_steps:
                    idx = dynamic_steps.index(current_value)
                    idx = max(idx - 1, 0)
                else:
                    idx = 0
                getattr(self, f"set_{setting_name}")(dynamic_steps[idx])
                logging.info(f"Decreasing {setting_name} to {self.get_setting(setting_name)}")
            elif self.pwm_mode == True and setting_name == 'fps':
                self.set_fps(int(self.fps_actual) - 1)
    def inc_shutter_a(self):
        self.increment_setting('shutter_a', self.shutter_a_steps, fps=self.fps_actual)

    def dec_shutter_a(self):
        self.decrement_setting('shutter_a', self.shutter_a_steps, fps=self.fps_actual)
    
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
        
    def set_pwm_mode(self, value=None):
        if self.current_sensor != 'imx477':
            logging.info(f"Current sensor {self.current_sensor}. PWM mode not availabe")
        else:
            if self.pwm_mode == False:
                self.fps_saved = float(self.get_setting('fps_actual'))

            if value is not None:
                self.pwm_mode = value
            else:
                value = not self.pwm_mode
            
            logging.info(f"Setting pwm mode mode to {value}")

            if value== False:
                self.pwm_controller.stop_pwm()
                self.set_fps(self.fps_saved)
            elif value == True:
                self.fps_saved = float(self.get_setting('fps'))
                shutter_a_current = float(self.get_setting('shutter_a_nom'))
                self.redis_controller.set_value('fps', 50)
                self.pwm_controller.start_pwm(int(self.fps_saved), shutter_a_current, 2)

            time.sleep(1)
            self.cinepi.restart()
            logging.info(f"Restarting camera")
        
    def set_shutter_a_sync(self, value=None):
        if value is None:
            self.shutter_a_sync = not self.shutter_a_sync
        else:
            if value in (0, False):
                self.shutter_a_sync = False
            elif value in (1, True):
                self.shutter_a_sync = True
            else:
                raise ValueError("Invalid value. Please provide either 0, 1, True, or False.")

        self.exposure_time_saved = self.exposure_time_s
        self.set_shutter_a_nom(float(self.redis_controller.get_value('shutter_a_nom')))
    
        logging.info(f"Shutter sync {'enabled' if self.shutter_a_sync else 'disabled'}")

    def set_fps_double(self, value=None):
        target_double_state = not self.fps_double if value is None else value in (1, True)

        if self.pwm_mode:
            self._ramp_fps(target_double_state)
        else:
            if target_double_state:
                if not self.fps_double:
                    self.fps_saved = self.fps_actual
                    target_fps = min(self.fps_actual * 2, self.fps_max)
                    self.set_fps(target_fps)
            else:
                if self.fps_double:
                    self.set_fps(self.fps_saved)
            
            self.fps_double = target_double_state

        logging.info(f"FPS double mode is {'enabled' if self.fps_double else 'disabled'}, Current FPS: {self.fps_actual}")

    def _ramp_fps(self, target_double_state):
        if target_double_state and not self.fps_double:
            self.fps_saved = self.fps_actual
            target_fps = min(self.fps_temp * 2, self.fps_max)

            while self.fps_actual < target_fps:
                logging.info('Ramping up')
                self.fps_actual += 1
                self.set_fps(self.fps_actual)
                time.sleep(self.ramp_up_speed)
        elif not target_double_state and self.fps_double:
            while self.fps_actual > self.fps_saved:
                logging.info('Ramping down')
                self.fps_actual -= 1
                self.set_fps(self.fps_actual)
                time.sleep(self.ramp_down_speed)

        self.fps_double = target_double_state
        
    def print_settings(self):
        iso = self.get_setting('iso')
        shutter_a = self.get_setting('shutter_a')
        fps = self.get_setting('fps_actual')
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
