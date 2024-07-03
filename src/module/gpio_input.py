# component_module.py
from gpiozero import Button, RotaryEncoder
import threading
import logging
import shlex  # Add this import

import board
import busio
import digitalio
import adafruit_seesaw.seesaw
import adafruit_seesaw.rotaryio
import adafruit_seesaw.digitalio
import adafruit_seesaw.neopixel
import warnings
import logging
import time
    
class ComponentInitializer:
    def __init__(self, cinepi_controller, settings):
        self.cinepi_controller = cinepi_controller
        self.settings = settings
        self.logger = logging.getLogger('ComponentInitializer')
        
        self.smart_buttons_list = []
        
        self.initialize_components()
        self.initialize_quad_rotary_encoder()  # Initialize Quad Rotary Encoder
        
    def initialize_components(self):
        combined_actions = self.settings.get('combined_actions', [])
        
        # Initialize Buttons
        for button_config in self.settings.get('buttons', []):
            press_action_method = self.extract_action_method(button_config.get('press_action'))
            single_click_action_method = self.extract_action_method(button_config.get('single_click_action'))
            double_click_action_method = self.extract_action_method(button_config.get('double_click_action'))
            triple_click_action_method = self.extract_action_method(button_config.get('triple_click_action'))
            hold_action_method = self.extract_action_method(button_config.get('hold_action'))
            
            self.logger.info(f"Button on pin {button_config['pin']}:")
            if press_action_method is not None: self.logger.info(f"  Press: {press_action_method}")
            if single_click_action_method is not None: self.logger.info(f"  Single Click: {single_click_action_method}")
            if double_click_action_method is not None: self.logger.info(f"  Double Click: {double_click_action_method}")
            if triple_click_action_method is not None: self.logger.info(f"  Triple Click: {triple_click_action_method}")
            if hold_action_method is not None: self.logger.info(f"  Hold: {hold_action_method}")

            # Create and store SmartButton instance
            smart_button = SmartButton(
                cinepi_controller=self.cinepi_controller,
                pin=button_config['pin'],
                pull_up=bool(button_config['pull_up']),
                debounce_time=float(button_config['debounce_time']),
                actions=button_config,
                identifier=str(button_config['pin']),
                combined_actions=combined_actions
            )
            
            self.smart_buttons_list.append(smart_button)  # Store SmartButton instance
        
        # Initialize Two-Way Switches
        for switch_config in self.settings.get('two_way_switches', []):
            state_on_action_method = self.extract_action_method(switch_config.get('state_on_action'))
            state_off_action_method = self.extract_action_method(switch_config.get('state_off_action'))
            
            self.logger.info(f"Two-way switch on pin {switch_config['pin']}:")
            if not "None" in str(state_on_action_method): self.logger.info(f"  State ON action: {state_on_action_method}")
            if not "None" in str(state_off_action_method): self.logger.info(f"  State OFF action: {state_off_action_method}")

            SimpleSwitch(cinepi_controller=self.cinepi_controller,
                         pin=switch_config['pin'],
                         actions=switch_config)
        
        # Initialize Rotary Encoders with Buttons
        for encoder_config in self.settings.get('rotary_encoders', []):
            button_actions = encoder_config.get('button_actions', {})
            press_action_method = self.extract_action_method(button_actions.get('press_action'))
            single_click_action_method = self.extract_action_method(button_actions.get('single_click_action'))
            double_click_action_method = self.extract_action_method(button_actions.get('double_click_action'))
            triple_click_action_method = self.extract_action_method(button_actions.get('triple_click_action'))
            hold_action_method = self.extract_action_method(button_actions.get('hold_action'))
            
            encoder_actions = encoder_config.get('encoder_actions', {})
            rotate_cw_action_method = self.extract_action_method(encoder_actions.get('rotate_clockwise'))
            rotate_ccw_action_method = self.extract_action_method(encoder_actions.get('rotate_counterclockwise'))
            
            self.logger.info(f"Rotary Encoder with Button on CLK pin: {encoder_config['clk_pin']}, DT pin: {encoder_config['dt_pin']}")
            if not "None" in str(rotate_cw_action_method): self.logger.info(f"  Rotate Clockwise: {rotate_cw_action_method}")
            if not "None" in str(rotate_ccw_action_method): self.logger.info(f"  Rotate CounterClockwise: {rotate_ccw_action_method}")
            if not "None" in str(press_action_method): self.logger.info(f"  Press: {press_action_method}")
            if not "None" in str(single_click_action_method): self.logger.info(f"  Single Click: {single_click_action_method}")
            if not "None" in str(double_click_action_method): self.logger.info(f"  Double Click: {double_click_action_method}")
            if not "None" in str(triple_click_action_method): self.logger.info(f"  Triple Click: {triple_click_action_method}")
            if not "None" in str(hold_action_method): self.logger.info(f"  Hold: {hold_action_method}")

            RotaryEncoderWithButton(cinepi_controller=self.cinepi_controller,
                                    clk_pin=encoder_config['clk_pin'],
                                    dt_pin=encoder_config['dt_pin'],
                                    button_pin=encoder_config['button_pin'],
                                    pull_up=bool(encoder_config['pull_up']),
                                    debounce_time=float(encoder_config['debounce_time']),
                                    actions=encoder_config,
                                    button_identifier=str(encoder_config['button_pin']))
        
    def initialize_quad_rotary_encoder(self):
        quad_rotary_settings = self.settings.get('quad_rotary_encoders', {})
        
        self.quad_rotary_encoder = QuadRotaryEncoder(
            self.cinepi_controller,
            quad_rotary_settings,
            self,
            self.smart_buttons_list  # Pass the list of smart buttons
        )


    def get_smart_button_by_pin(self, pin):
        for button in self.smart_buttons_list:
            if button.identifier == str(pin):
                return button
        return None  # Or handle the case where button with 'pin' is not found

    def extract_action_method(self, action_config):
        if action_config == "None":
            return None
        elif isinstance(action_config, str):
            return action_config
        elif isinstance(action_config, dict):
            return action_config.get('method')
        else:
            return None

            
    def _describe_actions(self, config):
        """
        Generate a string description of the actions assigned to a component.
        """
        actions = []
        for action_type, action_details in config.items():
            if isinstance(action_details, dict) and 'method' in action_details:
                method = action_details['method']
                args = action_details.get('args', [])
                actions.append(f"{action_type}: {method}({', '.join(map(str, args))})")
            elif isinstance(action_details, str) and action_details != 'none':
                actions.append(f"{action_type}: {action_details}")

        return "; ".join(actions)

class SmartButton:
    # Class-level dictionary to track button instances
    buttons = {}  # Dictionary to hold button instances by identifier (e.g., pin number)
    predefined_combined_actions = []  # Combined actions defined in your settings
    logger = logging.getLogger('ButtonManager')
    _currently_held = None
    
    def __init__(self, cinepi_controller, pin, pull_up, debounce_time, actions, identifier, inverse=False, combined_actions=[]):
        self.logger = logging.getLogger(f"SmartButton{pin}")
        self.button = Button(pin, pull_up=pull_up, bounce_time=debounce_time)
        self.actions = actions
        self.identifier = identifier
        self.inverse = inverse
        self.cinepi_controller = cinepi_controller
        
        self.click_count = 0
        self.click_timer = None
        self.click_timer2 = None
        self.hold_timer = None
        self.is_held = False
        self.state = 'released'  # Default state
        self.button_states = {}
        # Register this button instance
        SmartButton.buttons[identifier] = self  
        self.lock = threading.Lock()
        self.is_long_press = False
        self.combined_actions = combined_actions  # Store combined actions relevant to this button
        self.last_state = 'released'  # Default state
        
        self.button.when_pressed = self.on_press
        self.button.when_released = self.on_release
        
        self.check_initial_state()

        self.button.when_pressed = self.on_press if not self.inverse else self.on_release
        self.button.when_released = self.on_release if not self.inverse else self.on_press

        # Removed parse_action method
        self.logger.debug(f"Initialized with actions: {actions}, inverse={self.inverse}")

    def check_initial_state(self):
        # Assuming the button is not pressed during initialization,
        # check if the initial state is high (1), indicating an inverse button.
        if self.button.is_pressed:  # This actually checks the current state; True if pressed
            self.inverse = True  # Update the inverse attribute based on the initial state
            self.logger.info(f"Button {self.identifier} detected as inverse.")

    def trigger_hold_action(self):
        with self.lock:
            action_dict = self.actions.get('hold_action')
            
            # Check if action_dict is a dictionary, log an error if not
            if not isinstance(action_dict, dict):
                self.logger.error(f"Expected a dictionary for hold_action, but got: {type(action_dict)}. Action: {action_dict}")
                return
            
            action_method = action_dict.get('method')
            action_args = action_dict.get('args', [])
            if action_method:  # Ensure action_method is not None or empty
                method = getattr(self.cinepi_controller, action_method, None)
                if method:  # Ensure the method exists
                    self.logger.debug(f"Executing hold action: {action_method} with args: {action_args}")
                    method(*action_args)  # Call the method with unpacked arguments
                else:
                    self.logger.error(f"Method {action_method} not found in cinepi_controller.")
            else:
                self.logger.error("Hold action method name is not specified.")


    def on_press(self):
        self.button_states[self.identifier] = {"state": "pressed", "is_held": True}
        logging.debug(f"Button {self.identifier} pressed. Updated state: {self.button_states[self.identifier]}")
        
        with self.lock:
                
            self.is_held = True
            self.state = 'pressed'
            SmartButton.buttons[self.identifier] = self

            if SmartButton._currently_held is None:
                    SmartButton._currently_held = self.identifier

            logging.info(f"Button {self.identifier} pressed")

            # # Start a second timer to track long presses (0.5 sec)
            # self.click_timer2 = threading.Timer(0.5, self.evaluate_long_press)
            # self.click_timer2.start()

            self.is_held = True
            self.last_state = 'pressed'
            
            self.trigger_action(self.actions.get('press_action'))
            
            # Start hold timer to check for hold action
            if self.hold_timer is not None:
                self.hold_timer.cancel()
            self.hold_timer = threading.Timer(3, self.trigger_hold_action)
            self.hold_timer.start()

            # Evaluate combined actions upon button press
            self.evaluate_combined_actions()

    def on_release(self):
        self.button_states[self.identifier] = {"state": "released", "is_held": False}
        self.logger.info(f"Button {self.identifier} released")
        with self.lock:
            self.is_held = False
            self.state = 'released'

            if SmartButton._currently_held == self.identifier:
                SmartButton._currently_held = None
            elif SmartButton._currently_held is None:
                logging.info(f"Attempted to release button {self.identifier}, but no button was held.")

            # Cancel the long press timer
            if self.click_timer2 is not None:
                self.click_timer2.cancel()

            # Increment click count if not a long press
            if not self.is_long_press:
                self.click_count += 1

            # Reset long press flag
            self.is_long_press = False
            self.last_state = 'released'

            # Start a timer to evaluate clicks after release
            if self.click_timer is not None:
                self.click_timer.cancel()
            self.click_timer = threading.Timer(0.5, self.evaluate_clicks)
            self.click_timer.start()

            # Cancel the hold timer if the button is released before it triggers
            if self.hold_timer is not None:
                self.hold_timer.cancel()

            # Evaluate combined actions upon button release
            self.evaluate_combined_actions()

    def evaluate_long_press(self):
        self.logger.debug(f"Long press detected for button {self.identifier}")
        with self.lock:
            self.is_long_press = True
            # Reset click count for long press
            self.click_count = 0
    
    def get_button_state(self):
            # Returns the current state of the button, including 'is_held' and other relevant information
            return {"state": self.state, "is_held": self.is_held}
    
    def evaluate_combined_actions(self):
        # Log the entry into the method
        self.logger.debug(f"Starting to evaluate combined actions for button {self.identifier}")

        # Check if there are any combined actions defined
        if not self.combined_actions:
            self.logger.debug(f"No combined actions defined for button {self.identifier}")
            return

        # Iterate through each combined action relevant to this button
        for ca in self.combined_actions:
            self.logger.debug(f"Evaluating combined action: {ca} for button {self.identifier}")

            # Attempt to retrieve the hold and action button states
            try:
                hold_button = SmartButton.buttons[str(ca['hold_button_pin'])]
                action_button = SmartButton.buttons[str(ca['action_button_pin'])]
                hold_button_state = hold_button.get_button_state()
                action_button_state = action_button.get_button_state()
            except KeyError as e:
                self.logger.error(f"KeyError accessing button states: {e}")
                continue  # Skip this combined action if there's a KeyError

            # Log the retrieved states
            self.logger.debug(f"Hold Button State: {hold_button_state}, Action Button State: {action_button_state}")

            # Determine if the action condition is met
            action_met = False
            if ca['action_type'] == 'press' and action_button_state['is_held']:
                action_met = True
            elif ca['action_type'] == 'release' and not action_button_state['is_held']:
                action_met = True

            # Log whether the action condition was met
            if action_met:
                self.logger.debug("Action condition met for combined action.")
            else:
                self.logger.debug("Action condition not met for combined action.")

            # If the conditions for the combined action are met, execute the associated action
            if action_met and hold_button_state['is_held']:
                action_method_details = ca['action']
                method_name = action_method_details['method']
                args = action_method_details.get('args', [])
                method = getattr(self.cinepi_controller, method_name, None)
                if method:
                    self.logger.debug(f"Executing combined action: {method_name} with args: {args}")
                    try:
                        method(*args)
                    except Exception as e:
                        self.logger.error(f"Error executing combined action {method_name} with args {args}: {e}")
                else:
                    self.logger.error(f"Method {method_name} not found in cinepi_controller.")
            else:
                self.logger.debug(f"Combined action conditions not met or hold button not held for action: {ca}")




    def parse_action(self, action_str):
        """Parse an action string into a method name and its arguments."""
        if action_str == "none":
            return None
        parts = shlex.split(action_str)  # Use shlex to correctly handle spaces
        action = {"method": parts[0], "args": parts[1:]}
        return action

    def evaluate_clicks(self):
        logging.info('Evaluating clicks ...')
        with self.lock:
            action_dict = None
            # Determine the correct action based on click count
            if self.click_count == 1:
                action_dict = self.actions.get('single_click_action')
                logging.info('Single click detected.')
            elif self.click_count == 2:
                action_dict = self.actions.get('double_click_action')
                logging.info('Double click detected.')
            elif self.click_count >= 3:
                action_dict = self.actions.get('triple_click_action')
                logging.info('Triple click detected.')
            
            if action_dict and isinstance(action_dict, dict):
                self.logger.debug(f"Action dict before accessing 'method': {action_dict}")
                action_method = action_dict.get('method')
                action_args = action_dict.get('args', [])
                if action_method:
                    self.trigger_action(action_dict)  # Assuming you have this method implemented
                else:
                    self.logger.error("Action method name is not specified.")
            else:
                self.logger.debug("No action to execute or action_dict is not properly formatted.")

            self.click_count = 0  # Reset click count after evaluation

    def trigger_action(self, action):
        if SmartButton._currently_held == self.identifier or SmartButton._currently_held == None:
        # Handle 'none' or missing action as a no-operation
            if not action or action == "none":
                self.logger.debug("No action defined or action marked as 'none'.")
                return

            # Check if action is a string and not 'none', then convert to expected dictionary format
            if isinstance(action, str):
                action = {"method": action, "args": []}

            # Extract method name and args with defaults
            method_name = action.get('method')
            args = action.get('args', [])

            # Ensure that 'none' is handled even in dictionary format
            if method_name == "none":
                self.logger.debug("Action method marked as 'none', skipping execution.")
                return

            # Retrieve the method from cinepi_controller using getattr
            method = getattr(self.cinepi_controller, method_name, None)

            if method:
                # Call the method with unpacked arguments
                try:
                    method(*args)
                    self.logger.debug(f"Executing action: {method_name} with args: {args}")
                except TypeError:
                    self.logger.error(f"Method {method_name} does not support the provided args: {args}")
            else:
                self.logger.error(f"Method {method_name} not found in cinepi_controller.")
                
        else:
            logging.info(f"Button {self.identifier} individual action ignored. Button {SmartButton._currently_held} is currently held.")

class SimpleSwitch:
    def __init__(self, cinepi_controller, pin, actions, debounce_time=0.1):
        self.logger = logging.getLogger(f"SimpleSwitch{pin}")
        # For an external pull-up resistor and active-low configuration
        self.switch = Button(pin, pull_up=None, active_state=False, bounce_time=debounce_time)
        self.pin = pin
        self.actions = actions
        self.switch.when_pressed = self.on_switch_on
        self.switch.when_released = self.on_switch_off
        
        self.cinepi_controller = cinepi_controller
        
        # Check initial state of the switch and perform the connected method
        if self.switch.is_pressed:
            self.on_switch_on()
        else:
            self.on_switch_off()

    # Assuming action_name is actually a dictionary like {"method": "methodName", "args": ["arg1", "arg2"]}
    def on_switch_on(self):
        action = self.actions.get('state_on_action')
        if action:
            method_name = action.get('method')
            args = action.get('args', [])
            method = getattr(self.cinepi_controller, method_name, None)
            if method:
                method(*args)
                self.logger.info(f"Two-way switch {self.pin} calling method {method_name}.")
            else:
                self.logger.error(f"Method {method_name} not found in cinepi_controller.")

    def on_switch_off(self):
        action = self.actions.get('state_off_action')
        if action:
            method_name = action.get('method')
            args = action.get('args', [])
            method = getattr(self.cinepi_controller, method_name, None)
            if method:
                method(*args)
                self.logger.info(f"Two-way switch {self.switch} calling method {method_name} {args}.")
            else:
                self.logger.error(f"Method {method_name} not found in cinepi_controller.")

class RotaryEncoderWithButton:
    def __init__(self, cinepi_controller, clk_pin, dt_pin, button_pin, pull_up, debounce_time, actions, button_identifier):
        self.logger = logging.getLogger(f"RotaryEncoder{clk_pin}_{dt_pin}")
        self.encoder = RotaryEncoder(clk_pin, dt_pin)
        # Within RotaryEncoderWithButton.__init__ in component_module.py
        if button_pin != "None":
            self.button = SmartButton(cinepi_controller=cinepi_controller, 
                            pin=button_pin, 
                            pull_up=pull_up,
                            debounce_time=debounce_time,
                            actions=actions['button_actions'], 
                            identifier=button_identifier, 
                            inverse=False, # Assume default value, adjust as needed
                            combined_actions=[]) # Adjust as per your logic for combined actions

        self.actions = actions
        self.cinepi_controller = cinepi_controller

        self.encoder.when_rotated_clockwise = self.on_rotated_clockwise
        self.encoder.when_rotated_counter_clockwise = self.on_rotated_counter_clockwise

    def on_rotated_clockwise(self):
        action = self.actions['encoder_actions'].get('rotate_clockwise')
        if action:
            method_name = action.get('method')
            args = action.get('args', [])
            method = getattr(self.cinepi_controller, method_name, None)
            if method:
                method(*args)
                self.logger.info(f"Rotary encoder {self.encoder} calling method {method_name} {args}.") 
            else:
                self.logger.error(f"Method {method_name} not found in cinepi_controller.")

    def on_rotated_counter_clockwise(self):
        action = self.actions['encoder_actions'].get('rotate_counterclockwise')
        if action:
            method_name = action.get('method')
            args = action.get('args', [])
            method = getattr(self.cinepi_controller, method_name, None)
            if method:
                method(*args)
                self.logger.info(f"Rotary encoder {self.encoder} calling method {method_name} {args}.")
            else:
                self.logger.error(f"Method {method_name} not found in cinepi_controller.")

# Suppress specific warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="adafruit_blinka.microcontroller.generic_linux.i2c")

class QuadRotaryEncoder:
    def __init__(self, cinepi_controller, settings_mapping, component_initializer, smart_buttons):
        self.i2c = busio.I2C(board.SCL, board.SDA, frequency=50000)
        self.cinepi_controller = cinepi_controller
        self.settings_mapping = settings_mapping
        self.component_initializer = component_initializer
        self.smart_buttons = smart_buttons  # Store the list of SmartButton instances

        self.encoders = []
        self.switches = []
        self.pixels = None
        self.colors = [0, 0, 0, 0]
        self.last_positions = [0, 0, 0, 0]  # Initialized to zero for relative changes
        self.settings = {settings_mapping[key]['setting_name']: 100 for key in settings_mapping}
        self.debounced_time = 0.1  # Example debounce time in seconds
        self.button_states = [False] * len(settings_mapping)

        try:
            self.seesaw = adafruit_seesaw.seesaw.Seesaw(self.i2c, 0x49)
            self.encoders = [adafruit_seesaw.rotaryio.IncrementalEncoder(self.seesaw, n) for n in range(4)]
            self.switches = [adafruit_seesaw.digitalio.DigitalIO(self.seesaw, pin) for pin in (12, 14, 17, 9)]
            for switch in self.switches:
                switch.switch_to_input(digitalio.Pull.UP)

            self.pixels = adafruit_seesaw.neopixel.NeoPixel(self.seesaw, 18, 4)
            self.pixels.brightness = 0.5
            logging.info("Quad Rotary Encoder found and initialized")
            self.start()
        except ValueError:
            logging.warning("No I2C device found at address: 0x49. Quad Rotary Encoder not initialized.")

    def start(self):
        if self.encoders:
            thread = threading.Thread(target=self.run, daemon=True)
            thread.start()

    def update(self):
        if not self.encoders:
            return

        positions = [encoder.position for encoder in self.encoders]

        for n, rotary_pos in enumerate(positions):
            if str(n) not in self.settings_mapping:
                logging.warning(f"No setting mapped for encoder index {n}")
                continue

            if rotary_pos != self.last_positions[n]:
                change = rotary_pos - self.last_positions[n]
                self.last_positions[n] = rotary_pos

                setting_name = self.settings_mapping[str(n)].get('setting_name')
                if setting_name is not None:
                    if change > 0:
                        self.settings[setting_name] += change
                    else:
                        self.settings[setting_name] += change
                    self.settings[setting_name] = max(0, self.settings[setting_name])
                    self.update_setting(n, change)
                    logging.info(f"Quad Rotary #{n}: {rotary_pos}")
                else:
                    logging.info(f"No setting mapped for encoder index {n}")

                if not self.switches[n].value:
                    self.pixels[n] = 0xFFFFFF
                else:
                    self.pixels[n] = self.colorwheel(self.colors[n])

            # Handle button press and hold
            if not self.switches[n].value:  # Button pressed
                if not self.button_states[n]:  # First detection of press
                    self.button_states[n] = True
                    self.handle_button_press(n)
            else:
                if self.button_states[n]:  # Button released
                    self.button_states[n] = False
                    self.handle_button_release(n)

    def handle_button_press(self, encoder_index):
        button_pin = self.settings_mapping[str(encoder_index)].get('gpio_pin')
        if button_pin is not None:
            smart_button = self.component_initializer.get_smart_button_by_pin(button_pin)
            if smart_button is not None:
                smart_button.on_press()
            else:
                logging.error(f"No SmartButton found for pin {button_pin}")
        else:
            logging.error(f"No button pin mapped for encoder index {encoder_index}")

    def handle_button_release(self, encoder_index):
        button_pin = self.settings_mapping[str(encoder_index)].get('gpio_pin')
        if button_pin is not None:
            smart_button = self.component_initializer.get_smart_button_by_pin(button_pin)
            if smart_button is not None:
                smart_button.on_release()
            else:
                logging.error(f"No SmartButton found for pin {button_pin}")
        else:
            logging.error(f"No button pin mapped for encoder index {encoder_index}")

    def update_setting(self, encoder_index, change):
        setting_name = self.settings_mapping[str(encoder_index)].get('setting_name')
        if setting_name is not None:
            try:
                inc_func_name = f"inc_{setting_name}"
                dec_func_name = f"dec_{setting_name}"

                if hasattr(self.cinepi_controller, inc_func_name) and hasattr(self.cinepi_controller, dec_func_name):
                    if change > 0:
                        getattr(self.cinepi_controller, inc_func_name)()
                        self.colors[encoder_index] = (self.colors[encoder_index] + 8) % 256
                    elif change < 0:
                        getattr(self.cinepi_controller, dec_func_name)()
                        self.colors[encoder_index] = (self.colors[encoder_index] - 8) % 256
                else:
                    raise AttributeError(f"{self.cinepi_controller.__class__.__name__} module does not have functions for {setting_name}.")
            except KeyError:
                raise ValueError(f"Invalid setting_name: {setting_name}.")
        else:
            logging.info(f"Encoder index {encoder_index} is out of range of settings_mapping.")

    def run(self):
        while True:
            self.update()
            time.sleep(0.1)

    @staticmethod
    def colorwheel(pos):
        if pos < 85:
            return (255 - pos * 3, pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return (0, 255 - pos * 3, pos * 3)
        else:
            pos -= 170
            return (pos * 3, 0, 255 - pos * 3)
        
    def clone_smart_button_behavior(self, existing_button):
        logging.info(f"Cloning behavior of SmartButton {existing_button} for Quad Rotary Encoder.")
        existing_button.on_press()  # Or trigger the required behavior



