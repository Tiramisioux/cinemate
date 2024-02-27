import threading
import logging
import time
from gpiozero import Button

class GPIOInput():

    def __init__(self, cinepi_controller, redis_controller, 
                rec_button=None,
                rec_button_inv=False,
                
                iso_inc_button=None,
                iso_inc_button_inv=False,
                
                iso_dec_button=None,
                iso_dec_button_inv=False,
                
                res_switch=None,
                res_switch_inv = False,
                
                pwm_switch=None, 
                pwm_switch_inv=False,
                
                shutter_a_sync_switch=None, 
                shutter_a_sync_switch_inv=False, 
                
                fps_button=None,
                fps_button_inv=False,
                
                fps_switch=None,
                fps_switch_inv=False,
                
                pot_lock_switch=None,
                pot_lock_switch_inv=False
                ):
        
        self.cinepi_controller = cinepi_controller
        self.redis_controller = redis_controller
        
        self.buttons = []  # Store all buttons for future references or cleanups

        self.fps_button_inverse = False
        
        self.fps_original = self.cinepi_controller.get_setting('fps')
        
        self.fps_temp = 24
        
        self.fps_double = False
        
        self.ramp_up_speed = 0.1
        self.ramp_down_speed = 0.1

        self.setup_button(iso_inc_button, self.iso_inc_callback, "iso_inc_button")
        self.setup_button(iso_dec_button, self.iso_dec_callback, "iso_dec_pin")
        self.setup_button(res_switch, self.res_switch_callback, "res_switch", react_to_both=True)
        self.setup_button(pwm_switch, self.pwm_switch_callback, "pwm_switch", react_to_both=True)
        self.setup_button(shutter_a_sync_switch, self.sync_switch_callback, "shutter_a_sync_switch", react_to_both=True)
        self.setup_button(fps_button, self.fps_button_callback, "fps_button", react_to_both=True, inverse_control=True)
        self.setup_button(fps_switch, self.fps_switch_callback, "fps_switch", react_to_both=True)
        self.setup_button(pot_lock_switch, self.pot_lock_switch_callback, "pot_lock_switch", react_to_both=True)

        if rec_button is not None:
            if isinstance(rec_button, list):
                for pin in rec_button:
                    self.setup_button(pin, self.recording_callback, "rec_button")
            else:
                self.setup_button(rec_button, self.recording_callback, "rec_button")
        
        # Check the status of res_switch on startup
        if self.res_switch is not None and hasattr(self, 'res_switch'):
            if self.res_switch.is_pressed:
                self.cinepi_controller.set_resolution(1080)
            else:
                self.cinepi_controller.set_resolution(1520)
            logging.info(f"res_switch {self.res_switch.is_active}") 
        
        # Check the status of pwm_switch on startup
        if self.pwm_switch is not None and hasattr(self, 'pwm_switch'):
            if self.pwm_switch.is_pressed:
                pwm_mode = True        
            else:
                pwm_mode = False
            self.pwm_switch_callback()
            logging.info(f"pwm_switch {self.pwm_switch.is_active}")
            
        # Check the status of shutter_a_sync_switch on startup
        if self.shutter_a_sync_switch is not None and hasattr(self, 'shutter_a_sync_switch'):
            if self.shutter_a_sync_switch.is_pressed:
                shutter_a_sync = True
            else:
                shutter_a_sync = False
            self.sync_switch_callback()
            logging.info(f"shutter_a_sync_switch {self.shutter_a_sync_switch.is_active}") 
                
        # Check the status of fps_mult_switch on startup
        if self.fps_switch is not None and hasattr(self, 'fps_switch'):
            if not self.fps_switch.is_pressed:
                self.fps_double = False
                #logging.info(f"fps_switch {self.fps_switch.is_active}")
            else:
                self.cinepi_controller.fps_double = False
                self.cinepi_controller.switch_fps()
            logging.info(f"fps_switch {self.fps_switch.is_active}")

        # Check the status of fps_button on startup
        if self.fps_button is not None and hasattr(self, 'fps_button'):
            logging.info(f"fps_button {self.fps_button.is_active}")

        # Check the status of pot_lock_switch on startup
        if self.pot_lock_switch is not None and hasattr(self, 'pot_lock_switch'):
            if self.pot_lock_switch.is_pressed:
                self.cinepi_controller.set_parameters_lock(True)
            else:
                self.cinepi_controller.set_parameters_lock(False)
            logging.info(f"pot_lock switch {self.pot_lock_switch.is_active}")
    
    def _inverse_control(self, inverse_control, default_value):
        return not inverse_control if inverse_control is not None else default_value

    def setup_button(self, pins, callback, attribute_name, react_to_release=False, react_to_both=False, inverse_control=False):
        if not isinstance(pins, list):
            pins = [pins]
        for i, pin in enumerate(pins):
            if len(pins) > 1:
                name = f"{attribute_name}{i+1}"
            else:
                name = attribute_name
            if pin is not None:
                self._create_button(pin, callback, name, react_to_release, react_to_both, inverse_control)
            else:
                setattr(self, name, None)


    def _create_button(self, pin, callback, attribute_name=None, react_to_release=False, react_to_both=False, inverse_control=False):
        if pin is None:
            return
        
        # Set pull_up parameter to True to invert the button behavior
        btn = Button(pin, pull_up=self._inverse_control(inverse_control, True))


        if react_to_both:
            btn.when_pressed = callback
            btn.when_released = callback
        elif react_to_release:
            btn.when_released = callback
        else:
            btn.when_pressed = callback
            
        self.buttons.append(btn)
        
        function = callback.__name__.replace("_callback", "")
        
        logging.info(f"{attribute_name} instantiated on pin {pin}.")
        
        if attribute_name:
            setattr(self, attribute_name, btn)
            #logging.info(f"Button attribute set as {attribute_name} for pin {pin}.")


    def recording_callback(self):
        self.cinepi_controller.rec_button_pushed()
        #logging.info(f"Record button pressed")

    def pot_lock_switch_callback(self):
        if self.pot_lock_switch.is_pressed:
            self.cinepi_controller.set_parameters_lock(True)
        else:
            self.cinepi_controller.set_parameters_lock(False)
        logging.info(f"pot_lock_switch state {self.pot_lock_switch.is_active}")

    def res_switch_callback(self):
        if self.res_switch.is_pressed:
            self.cinepi_controller.switch_resolution()
        else:
            self.cinepi_controller.switch_resolution()
            #logging.info(f"res_switch state {self.res_switch.is_active}") 

    def fps_switch_callback(self):
        if self.fps_switch.is_pressed:
            self.cinepi_controller.fps_double = False
            self.cinepi_controller.switch_fps()
        else:
            self.cinepi_controller.fps_double = True
            self.cinepi_controller.switch_fps()
        logging.info(f"fps_switch state {self.fps_switch.is_active}")
        
    def fps_button_callback(self):
        fps_button_state_old = self.cinepi_controller.fps_button_state
        self.cinepi_controller.lock_override = True

        if self.fps_button.is_pressed:
            if self.fps_button_inverse:
                self.cinepi_controller.fps_button_state = False
            else:
                self.cinepi_controller.fps_button_state = True
        else:
            if self.fps_button_inverse:
                self.cinepi_controller.fps_button_state = True
            else:
                self.cinepi_controller.fps_button_state = False

            if fps_button_state_old and fps_button_state_old != self.cinepi_controller.fps_button_state:

                if self.cinepi_controller.pwm_mode == False:

                    #logging.info('fps button change from 0 to 1, switching frame rate')

                    # Toggle between doubling and restoring FPS value
                    if not self.fps_double:
                        # Store the current fps
                        self.fps_temp = float(self.redis_controller.get_value('fps_actual'))
                        
                        # Set fps_new to double the current temp value
                        fps_new = self.fps_temp * 2
                        # Retrieve the current fps_max from Redis
                        fps_max = float(self.redis_controller.get_value('fps_max', default=50))
                        # Cap fps_new to the current fps_max
                        fps_new = min(fps_new, fps_max)
                        self.cinepi_controller.set_fps(fps_new)
                        self.fps_double = True
                    else:
                        # Restore FPS value to the stored temp value
                        self.cinepi_controller.set_fps(self.fps_temp)
                        self.fps_double = False
                        
                elif self.cinepi_controller.pwm_mode == True:

                    if not self.fps_double:
                        # Ramp up
                        
                        # Store the current fps
                        self.fps_temp = float(self.redis_controller.get_value('fps_actual'))
                        
                        # Set fps_new to double the current temp value
                        fps_target = self.fps_temp * 2
                        # Retrieve the current fps_max from Redis
                        fps_max = float(self.redis_controller.get_value('fps_max', default=50))
                        # Cap fps_new to the current fps_max
                        fps_target = min(fps_target, fps_max)

                        while float((self.redis_controller.get_value('fps_actual'))) < int(float(self.redis_controller.get_value('fps_max'))):
                            logging.info('ramping up')
                            fps_current = float(self.redis_controller.get_value('fps_actual'))
                            fps_next = fps_current + 1
                            self.cinepi_controller.set_fps(int(fps_next))
                            time.sleep(self.ramp_up_speed)
                        self.fps_double = True
                        
                    elif self.fps_double:
                        # Ramp down

                        while float((self.redis_controller.get_value('fps_actual'))) > self.fps_temp:
                            logging.info('ramping down')
                            fps_current = float(self.redis_controller.get_value('fps_actual'))
                            fps_next = fps_current - 1
                            self.cinepi_controller.set_fps(int(fps_next))
                            time.sleep(self.ramp_down_speed)
                        self.fps_double = False                        

                logging.info(f"fps_button state {self.cinepi_controller.fps_button_state}")

                fps_button_state_old = self.cinepi_controller.fps_button_state
        
        self.cinepi_controller.lock_override = False

    def iso_inc_callback(self):
        pass

    def iso_dec_callback(self):
        pass
    
    def pwm_switch_callback(self):
        if self.cinepi_controller.pwm_controller.PWM_pin in [None, 18, 19]:
            if self.pwm_switch.is_pressed:
                pwm_mode = True
            elif not self.pwm_switch.is_pressed:
                pwm_mode = False
            #logging.info(f"pwm_switch {self.pwm_switch.is_active}.")
            self.cinepi_controller.set_pwm_mode(pwm_mode)
                 
    def sync_switch_callback(self):
        if self.shutter_a_sync_switch is not None and self.shutter_a_sync_switch.is_pressed:
            shutter_a_sync = True
                #logging.info(f"shutter_a_sync_switch {self.shutter_a_sync_switch.is_active}.")
        elif self.shutter_a_sync_switch is not None and not self.shutter_a_sync_switch.is_pressed:
            shutter_a_sync = False
                #logging.info(f"shutter_a_sync_switch {self.shutter_a_sync_switch.is_active}.")
            
        self.cinepi_controller.set_shutter_a_sync(shutter_a_sync)
        
        
