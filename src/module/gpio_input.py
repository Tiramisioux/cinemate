from gpiozero import Button
from gpiozero import RotaryEncoder as GPIOZeroRotaryEncoder
import threading
import logging
import shlex  # Add this import

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
            
        # Initialize three-way switches
        self.three_way_switches = []
        for switch_config in self.settings.get('three_way_switches', []):
            pins = switch_config['pins']
            self.logger.info(f"Three-way switch on pins {pins}:")
            for i in range(3):
                action_method_name = switch_config.get(f"state_{i}_action")
                if action_method_name:
                    self.logger.info(f"  State {i} action: {action_method_name}")

            three_way_switch = ThreeWaySwitch(cinepi_controller=self.cinepi_controller,
                                              pins=pins,
                                              actions=switch_config)
            self.three_way_switches.append(three_way_switch)
        
        # Initialize Rotary Encoders with Buttons
        for encoder_config in self.settings.get('rotary_encoders', []):
            encoder_actions = encoder_config.get('encoder_actions', {})
            rotate_cw_action_method = self.extract_action_method(encoder_actions.get('rotate_clockwise'))
            rotate_ccw_action_method = self.extract_action_method(encoder_actions.get('rotate_counterclockwise'))
            detents_per_pulse = self._normalize_detents_per_pulse(encoder_config.get('detents_per_pulse'))
            
            self.logger.info(f"Rotary Encoder with Button on CLK pin: {encoder_config['clk_pin']}, DT pin: {encoder_config['dt_pin']}")
            if not "None" in str(rotate_cw_action_method): self.logger.info(f"  Rotate Clockwise: {rotate_cw_action_method}")
            if not "None" in str(rotate_ccw_action_method): self.logger.info(f"  Rotate CounterClockwise: {rotate_ccw_action_method}")
            if detents_per_pulse > 1:
                self.logger.info(f"  Detents per pulse: {detents_per_pulse}")
            RotaryEncoder(
                cinepi_controller=self.cinepi_controller,
                clk_pin=encoder_config['clk_pin'],
                dt_pin=encoder_config['dt_pin'],
                actions=encoder_config['encoder_actions'],
                detents_per_pulse=detents_per_pulse
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

    @staticmethod
    def _normalize_detents_per_pulse(value):
        try:
            return max(1, int(value or 1))
        except (TypeError, ValueError):
            return 1

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

            # Start a second timer to track long presses (0.5 sec)
            self.click_timer2 = threading.Timer(0.5, self.evaluate_long_press)
            self.click_timer2.start()

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
        #logging.info('Evaluating clicks')
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
    def __init__(self, cinepi_controller, pin, actions, pull_up=True, debounce_time=0.1):
        """
        A reliable two-way switch handler with proper startup state detection.

        :param cinepi_controller: The main controller handling actions.
        :param pin: GPIO pin number for the switch.
        :param actions: Dictionary containing 'state_on_action' and 'state_off_action'.
        :param pull_up: Whether to use an internal pull-up resistor (default: True).
        :param debounce_time: Debounce time in seconds (default: 0.1).
        """
        self.logger = logging.getLogger(f"SimpleSwitch[{pin}]")
        self.cinepi_controller = cinepi_controller
        self.pin = pin
        self.actions = actions
        self.debounce_time = debounce_time
        self.state = None  # Track switch state
        self.lock = threading.Lock()

        # Initialize the switch with gpiozero
        self.switch = Button(pin, pull_up=pull_up, bounce_time=debounce_time)

        # Delay startup to allow GPIO state stabilization
        time.sleep(0.5)

        # Detect and apply initial state
        self.detect_and_apply_initial_state()

        # Attach event handlers **after** detecting the initial state
        self.switch.when_pressed = self.on_switch_on
        self.switch.when_released = self.on_switch_off

        self.logger.info(f"Initialized SimpleSwitch on pin {pin} (pull_up={pull_up}, debounce={debounce_time}s)")

    def detect_and_apply_initial_state(self):
        """Detects the switch state at startup and applies the corresponding action."""
        initial_state = "on" if self.switch.is_pressed else "off"

        self.logger.info(f"Detected initial state: {initial_state} for switch on pin {self.pin}")

        # Only execute the action if the detected state is different from the default (None)
        if self.state is None or self.state != initial_state:
            self.state = initial_state
            if initial_state == "on":
                self.execute_action(self.actions.get('state_on_action'))
            else:
                self.execute_action(self.actions.get('state_off_action'))

    def execute_action(self, action):
        """Executes the assigned method from cinepi_controller."""
        if action:
            method_name = action.get('method')
            args = action.get('args', [])

            if method_name:
                method = getattr(self.cinepi_controller, method_name, None)
                if method:
                    try:
                        method(*args)
                        self.logger.info(f"Executed action {method_name}({', '.join(map(str, args))})")
                    except Exception as e:
                        self.logger.error(f"Error executing {method_name}: {e}")
                else:
                    self.logger.error(f"Method {method_name} not found in cinepi_controller.")
            else:
                self.logger.warning(f"No method name specified in action {action}")

    def on_switch_on(self):
        """Handles the event when the switch is turned ON."""
        with self.lock:
            if self.state != "on":  # Avoid redundant actions
                self.state = "on"
                self.logger.info(f"Switch {self.pin} turned ON")
                self.execute_action(self.actions.get('state_on_action'))

    def on_switch_off(self):
        """Handles the event when the switch is turned OFF."""
        with self.lock:
            if self.state != "off":  # Avoid redundant actions
                self.state = "off"
                self.logger.info(f"Switch {self.pin} turned OFF")
                self.execute_action(self.actions.get('state_off_action'))
                
class ThreeWaySwitch:
    def __init__(self, cinepi_controller, pins, actions, debounce_time=0.1):
        self.logger = logging.getLogger(f"ThreeWaySwitch{pins}")
        self.pins = pins
        self.actions = actions
        self.cinepi_controller = cinepi_controller
        
        # Initialize buttons for each pin
        self.switches = [Button(pin, pull_up=None, active_state=False, bounce_time=debounce_time) for pin in pins]
        
        for switch in self.switches:
            switch.when_pressed = self.on_switch_change
        
        # Check initial state of the switch and perform the connected method
        self.on_switch_change()

    def on_switch_change(self):
        position = self.get_switch_position()
        action = self.actions.get(f'state_{position}_action')
        if action:
            method_name = action.get('method')
            args = action.get('args', [])
            method = getattr(self.cinepi_controller, method_name, None)
            if method:
                method(*args)
                self.logger.info(f"Three-way switch {self.pins} calling method {method_name} with args {args}.")
            else:
                self.logger.error(f"Method {method_name} not found in cinepi_controller.")
        else:
            self.logger.warning(f"No action defined for position {position}.")

    def get_switch_position(self):
        for index, switch in enumerate(self.switches):
            if switch.is_pressed:
                return index
        return -1  # Undefined position
    
class RotaryEncoder:
    def __init__(self, cinepi_controller, clk_pin, dt_pin, actions, detents_per_pulse=1):
        self.logger = logging.getLogger(f"RotaryEncoder{clk_pin}_{dt_pin}")
        
        # Correct initialization with gpiozero's RotaryEncoder using a and b for pin names
        self.encoder = GPIOZeroRotaryEncoder(a=clk_pin, b=dt_pin)
        
        self.actions = actions
        self.cinepi_controller = cinepi_controller
        self.detents_per_pulse = ComponentInitializer._normalize_detents_per_pulse(detents_per_pulse)

        # Set up event handlers
        self.encoder.when_rotated_clockwise = self.on_rotated_clockwise
        self.encoder.when_rotated_counter_clockwise = self.on_rotated_counter_clockwise

    def on_rotated_clockwise(self):
        action = self.actions.get('rotate_clockwise')
        if action:
            self._trigger_action(action, direction="clockwise")

    def on_rotated_counter_clockwise(self):
        action = self.actions.get('rotate_counterclockwise')
        if action:
            self._trigger_action(action, direction="counterclockwise")

    def _trigger_action(self, action, direction):
        method_name = action.get('method')
        args = action.get('args', [])
        method = getattr(self.cinepi_controller, method_name, None)
        if method:
            for _ in range(self.detents_per_pulse):
                method(*args)
            self.logger.info(
                "Rotary encoder rotated %s, calling method %s with args %s (%sx)",
                direction,
                method_name,
                args,
                self.detents_per_pulse,
            )
        else:
            self.logger.error(f"Method {method_name} not found in cinepi_controller.")


# Suppress specific warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="adafruit_blinka.microcontroller.generic_linux.i2c")
