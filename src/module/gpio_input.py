# component_module.py
from gpiozero import Button, RotaryEncoder
import threading
import logging
import shlex  # Add this import
    
class ComponentInitializer:
    def __init__(self, cinepi_controller, settings):
        self.cinepi_controller = cinepi_controller
        self.settings = settings
        self.logger = logging.getLogger('ComponentInitializer')
        
        self.initialize_components()
        
    def initialize_components(self):
        self.logger.info("Initializing components based on loaded settings")
        combined_actions = self.settings.get('combined_actions', [])
        
        # Initialize Buttons
        for button_config in self.settings.get('buttons', []):
            self.logger.info(f"Initializing button on pin {button_config['pin']}")
            actions_desc = self._describe_actions(button_config)
            # self.logger.info(f"Initializing button on pin {button_config['pin']} with actions: {actions_desc}")
            SmartButton(cinepi_controller=self.cinepi_controller,
                        pin=button_config['pin'],
                        actions=button_config,
                        identifier=str(button_config['pin']),
                        combined_actions=combined_actions)
        
        # Initialize Two-Way Switches
        for switch_config in self.settings.get('two_way_switches', []):
            self.logger.info(f"Initializing two-way switch on pin {switch_config['pin']}")
            actions_desc = self._describe_actions(button_config)
            # self.logger.info(f"Initializing button on pin {button_config['pin']} with actions: {actions_desc}")
            SimpleSwitch(cinepi_controller=self.cinepi_controller,
                         pin=switch_config['pin'],
                         actions=switch_config)
        
        # Initialize Rotary Encoders with Buttons
        for encoder_config in self.settings.get('rotary_encoders', []):
            actions_desc = self._describe_actions(button_config)
            # self.logger.info(f"Initializing button on pin {button_config['pin']} with actions: {actions_desc}")
            self.logger.info(f"Initializing rotary encoder with button on pins {encoder_config['pin_a']}, {encoder_config['pin_b']}")
            RotaryEncoderWithButton(cinepi_controller=self.cinepi_controller,
                                    pin_a=encoder_config['pin_a'],
                                    pin_b=encoder_config['pin_b'],
                                    button_pin=encoder_config['button_pin'],
                                    actions=encoder_config,
                                    button_identifier=str(encoder_config['button_pin']))
            
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
    
    def __init__(self, cinepi_controller, pin, actions, identifier, inverse=False, combined_actions=[], debounce_time=0.01):
        self.logger = logging.getLogger(f"SmartButton{pin}")
        self.button = Button(pin, bounce_time=debounce_time)
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
            self.logger.debug(f"Button {self.identifier} detected as inverse.")

    def trigger_hold_action(self):
        with self.lock:
            action_dict = self.actions.get('hold_action')  # This will be a dictionary now
            if action_dict:
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
            else:
                self.logger.error("Hold action is not defined.")

            # Indicate that the button was held and evaluate combined actions if needed
            self.is_held = True
            self.evaluate_combined_actions()

    def on_press(self):
        self.button_states[self.identifier] = {"state": "pressed", "is_held": True}
        logging.debug(f"Button {self.identifier} pressed. Updated state: {self.button_states[self.identifier]}")
        
        with self.lock:
                
            self.is_held = True
            self.state = 'pressed'
            SmartButton.buttons[self.identifier] = self

            # # Update the button's state in the class-level dictionary
            # SmartButton.buttons[self.identifier]['state'] = self.state
            # SmartButton.buttons[self.identifier]['is_held'] = self.is_held
            # Check for combined actions after updating state
            self.evaluate_combined_actions()
            self.logger.debug(f"Button {self.identifier} pressed")

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
        self.logger.debug(f"Button {self.identifier} released")
        with self.lock:
            self.is_held = False
            self.state = 'released'

            SmartButton.buttons[self.identifier] = self

            # Similar update and check as in on_press
            # SmartButton.buttons[self.identifier]['state'] = self.state
            # SmartButton.buttons[self.identifier]['is_held'] = self.is_held
            self.evaluate_combined_actions()

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
                hold_button_state = SmartButton.buttons[str(ca['hold_button_pin'])].get_button_state()
                action_button_state = SmartButton.buttons[str(ca['action_button_pin'])].get_button_state()
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
        with self.lock:
            action_dict = None
            # Determine the correct action based on click count
            if self.click_count == 1:
                action_dict = self.actions.get('single_click_action')
            elif self.click_count == 2:
                action_dict = self.actions.get('double_click_action')
            elif self.click_count >= 3:
                action_dict = self.actions.get('triple_click_action')
            
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

class SimpleSwitch:
    def __init__(self, cinepi_controller, pin, actions, debounce_time=0.1):
        self.logger = logging.getLogger(f"SimpleSwitch{pin}")
        # For an external pull-up resistor and active-low configuration
        self.switch = Button(pin, pull_up=None, active_state=False, bounce_time=debounce_time)
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
                self.logger.info(f"Two-way switch {self.switch} calling method {method_name}.")
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
    def __init__(self, cinepi_controller, pin_a, pin_b, button_pin, actions, button_identifier):
        self.logger = logging.getLogger(f"RotaryEncoder{pin_a}_{pin_b}")
        self.encoder = RotaryEncoder(pin_a, pin_b)
        # Within RotaryEncoderWithButton.__init__ in component_module.py
        self.button = SmartButton(cinepi_controller=cinepi_controller, 
                          pin=button_pin, 
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
