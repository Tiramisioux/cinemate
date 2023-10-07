import threading
import logging
import time
from gpiozero import Button

class GPIOControls():

    def __init__(self, cinepi_controller, iso_inc_pin=None, iso_dec_pin=None, pot_lock_pin=None, 
                 res_button_pin=None, rec_pin=None, fps_mult_pin1=None, fps_mult_pin2=None):
        
        self.cinepi_controller = cinepi_controller
        
        self.buttons = []  # Store all buttons for future references or cleanups

        self.setup_button(iso_inc_pin, self.iso_inc_callback)
        self.setup_button(iso_dec_pin, self.iso_dec_callback)
        self.setup_button(pot_lock_pin, self.pot_lock_callback, "pot_lock_pin", react_to_both=True)
        self.setup_button(res_button_pin, self.res_button_callback, "res_button_pin")
        self.setup_button(fps_mult_pin1, self.fps_mult_callback, "fps_mult_pin1", react_to_release=True)
        self.setup_button(fps_mult_pin2, self.fps_mult_callback, "fps_mult_pin2", react_to_release=True)
        
        self.prev_fps_mult_pin1_state = self.fps_mult_pin1.is_pressed
        self.prev_fps_mult_pin2_state = self.fps_mult_pin2.is_pressed

        if rec_pin is not None:
            if isinstance(rec_pin, list):
                for pin in rec_pin:
                    self.setup_button(pin, self.recording_callback)
            else:
                self.setup_button(rec_pin, self.recording_callback)

        self.last_click_time = 0
        self.click_count = 0
        self.click_timer = None
        
         # Check the status of pot_lock_pin on startup
        if hasattr(self, 'pot_lock_pin'):
            if self.pot_lock_pin.is_pressed:
                logging.info(f"pot_lock switch is OFF at startup")
                self.cinepi_controller.set_parameters_lock(False)
            else:
                logging.info(f"pot_lock switch is ON at startup")
                self.cinepi_controller.set_parameters_lock(True)
                
        # Check the status of fps_mult_pin1 and fps_mult_pin2 on startup
        if hasattr(self, 'fps_mult_pin1') and hasattr(self, 'fps_mult_pin2'):
            if self.fps_mult_pin1.is_pressed and not self.fps_mult_pin2.is_pressed:
                logging.info(f"three-way switch is in DOWN position at startup.")
                fps_multiplier = 1
                # You can also call a corresponding action here if required.
            elif not self.fps_mult_pin1.is_pressed and self.fps_mult_pin2.is_pressed:
                logging.info(f"three-way switch is in the UP position at startup.")
                fps_multiplier = 0.5
                # You can also call a corresponding action here if required.
            elif not self.fps_mult_pin1.is_pressed and not self.fps_mult_pin2.is_pressed:
                logging.info(f"three-way switch is in the MIDDLE position at startup.")
                fps_multiplier = 2


    def setup_button(self, pin, callback, attribute_name=None, react_to_release=False, react_to_both=False):
        if pin:
            if isinstance(pin, list):
                for p in pin:
                    self._create_button(p, callback, react_to_release, react_to_both)
            else:
                self._create_button(pin, callback, attribute_name, react_to_release, react_to_both)


    def _create_button(self, pin, callback, attribute_name=None, react_to_release=False, react_to_both=False):
        btn = Button(pin)
        
        if react_to_both:
            btn.when_pressed = callback
            btn.when_released = callback
        elif react_to_release:
            btn.when_released = callback
        else:
            btn.when_pressed = callback
            
        self.buttons.append(btn)
        
        function = callback.__name__.replace("_callback", "")
        
        logging.info(f"{function} button instantiated on pin {pin}.")
        
        if attribute_name:
            setattr(self, attribute_name, btn)
            #logging.info(f"Button attribute set as {attribute_name} for pin {pin}.")

    def recording_callback(self):
        self.cinepi_controller.rec_button_pushed()
        logging.info(f"Record button pressed")

    def pot_lock_callback(self, event_type="release"):
        state = self.pot_lock_pin.is_pressed
        #logging.info(f"Pot lock callback triggered on {event_type}. Is pressed: {state}")
        if event_type == "press":
            # If you want some logic to run when the button is pressed
            pass
        elif event_type == "release":
            if not state:
                self.cinepi_controller.set_parameters_lock(True)
                logging.info(f"Pot lock switch activated")
            else:
                self.cinepi_controller.set_parameters_lock(False)
                logging.info(f"Pot lock switch deactivated")

    def res_button_callback(self):
        self.cinepi_controller.switch_resolution()

    def fps_mult_callback(self):
        # To imitate a delay for a more accurate read (as previously done with time.sleep(0.1))
        time.sleep(0.2)
        
        # Using is_pressed for a boolean check if the button is pressed
        final_state1 = self.fps_mult_pin1.is_pressed
        final_state2 = self.fps_mult_pin2.is_pressed
        
        # Determine the transition
        if not self.prev_fps_mult_pin1_state and final_state1:  # From not pressed to pressed
            transition = 'from MIDDLE to DOWN'
            fps_multiplier = 2
        elif self.prev_fps_mult_pin1_state and not final_state1:  # From pressed to not pressed
            transition = 'from DOWN to MIDDLE'
            fps_multiplier = 0.5
        elif not self.prev_fps_mult_pin2_state and final_state2:  # From not pressed to pressed
            transition = 'from MIDDLE to UP'
            fps_multiplier = 0.5
        elif self.prev_fps_mult_pin2_state and not final_state2:  # From pressed to not pressed
            transition = 'from UP to MIDDLE'
            fps_multiplier = 2
        else:
            # If no valid transition detected
            transition = 'unknown'
            fps_multiplier = 1  # Or any default value you see fit
            
        fps = int(self.cinepi_controller.redis_controller.get_value('fps'))
        fps_new = int(fps*fps_multiplier)

        logging.info(f"FPS multiplier switch transitioned: {transition}.")
        self.cinepi_controller.set_fps_multiplier(fps_multiplier)
        self.cinepi_controller.set_fps(fps_new)

        # Update the previous states
        self.prev_fps_mult_pin1_state = final_state1
        self.prev_fps_mult_pin2_state = final_state2

    def iso_inc_callback(self):
        pass

    def iso_dec_callback(self):
        pass
