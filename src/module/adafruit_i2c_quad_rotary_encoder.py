import board
import busio
import digitalio
import adafruit_seesaw.seesaw
import adafruit_seesaw.rotaryio
import adafruit_seesaw.digitalio
import adafruit_seesaw.neopixel
import RPi
import warnings
import logging
import time

# Suppress specific warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="adafruit_blinka.microcontroller.generic_linux.i2c")

class QuadRotaryEncoder:
    def __init__(self, cinepi_controller, settings_mapping):
        # Initialize I2C and Seesaw
        self.i2c = busio.I2C(board.SCL, board.SDA, frequency=50000)
        self.seesaw = adafruit_seesaw.seesaw.Seesaw(self.i2c, 0x49)
        self.cinepi_controller = cinepi_controller

        # Initialize encoders and switches
        self.encoders = [adafruit_seesaw.rotaryio.IncrementalEncoder(self.seesaw, n) for n in range(4)]
        self.switches = [adafruit_seesaw.digitalio.DigitalIO(self.seesaw, pin) for pin in (12, 14, 17, 9)]
        for switch in self.switches:
            switch.switch_to_input(digitalio.Pull.UP)  # input & pullup!

        # Initialize NeoPixels
        self.pixels = adafruit_seesaw.neopixel.NeoPixel(self.seesaw, 18, 4)
        self.pixels.brightness = 0.5

        # Initialize colors for all encoders to the same starting value (e.g., red)
        self.colors = [0, 0, 0, 0]  # Adjust the initial color value as needed

        # Initialize variables for tracking positions and settings
        self.last_positions = [-1, -1, -1, -1]

        # Store settings mapping internally
        self.settings_mapping = settings_mapping

        # Create settings dictionary based on settings_mapping
        self.settings = {settings_mapping[key]['setting_name']: 100 for key in settings_mapping}

        # Start the main loop
        self.run()

    def init_gpio_pins(self):
        # Initialize GPIO pins based on settings_mapping
        self.gpio_pins = {}
        for encoder_index, settings in self.settings_mapping.items():
            gpio_pin = settings.get('gpio_pin')
            if gpio_pin is not None:
                RPi.GPIO.setup(gpio_pin, RPi.GPIO.IN, pull_up_down=RPi.GPIO.PUD_UP)
                self.gpio_pins[encoder_index] = gpio_pin

    def update(self):
        # Update encoder positions
        positions = [encoder.position for encoder in self.encoders]
        
        for n, rotary_pos in enumerate(positions):
            if rotary_pos != self.last_positions[n]:
                if self.switches[n].value:  # Check if the switch is not pressed
                    setting_name = self.settings_mapping[n].get('setting_name')
                    if setting_name is not None:
                        # Check if the movement is significant (not just initialization)
                        if self.last_positions[n] != -1:  # Assuming -1 is an invalid initial position
                            if rotary_pos > self.last_positions[n]:
                                self.settings[setting_name] += 1  # Increment setting
                            else:
                                self.settings[setting_name] -= 1  # Decrement setting
                            self.settings[setting_name] = max(0, self.settings[setting_name])  # Ensure non-negative
                            self.update_setting(n)  # Update setting based on encoder index
                            logging.info(f"Rotary #{n}: {rotary_pos}")
                    else:
                        logging.info(f"No setting mapped for encoder index {n}")
                
                # Update NeoPixel color based on switch state
                if not self.switches[n].value:
                    self.pixels[n] = 0xFFFFFF  # White if switch is pressed
                else:
                    self.pixels[n] = self.colorwheel(self.colors[n])  # Color based on stored value

                self.last_positions[n] = rotary_pos
            else:
                if not self.switches[n].value:
                    self.pixels[n] = 0xFFFFFF  # Set to white if switch is pressed
                    logging.info(f"Rotary button #{n}: pressed")
                    gpio_pin = self.settings_mapping[n]['gpio_pin']
                    RPi.GPIO.output(gpio_pin, RPi.GPIO.LOW)  # Simulate button press
                    time.sleep(0.1)  # Simulate debounce or hold time if needed
                    RPi.GPIO.output(gpio_pin, RPi.GPIO.HIGH)  # Return to idle state
                else:
                    pass
                    #logging.info(f"Rotary button #{n}: not pressed")

    def update_setting(self, encoder_index):
        setting_name = self.settings_mapping[encoder_index].get('setting_name')
        if setting_name is not None:
            try:
                inc_func_name = f"inc_{setting_name}"
                dec_func_name = f"dec_{setting_name}"

                if hasattr(self.cinepi_controller, inc_func_name) and hasattr(self.cinepi_controller, dec_func_name):
                    # Determine the change in encoder position
                    current_position = self.encoders[encoder_index].position
                    last_position = self.last_positions[encoder_index]

                    if current_position > last_position:
                        getattr(self.cinepi_controller, inc_func_name)()
                        self.colors[encoder_index] = (self.colors[encoder_index] + 8) % 256  # Advance color
                    elif current_position < last_position:
                        getattr(self.cinepi_controller, dec_func_name)()
                        self.colors[encoder_index] = (self.colors[encoder_index] - 8) % 256  # Reverse color

                    # Update last position
                    self.last_positions[encoder_index] = current_position

                else:
                    raise AttributeError(f"{self.cinepi_controller.__name__} module does not have functions for {setting_name}.")
            except KeyError:
                raise ValueError(f"Invalid setting_name: {setting_name}.")
        else:
            logging.info(f"Encoder index {encoder_index} is out of range of settings_mapping.")

    def run(self):
        while True:
            self.update()

    @staticmethod
    def colorwheel(pos):
        # Function to map a position (0 to 255) to a color wheel (red to blue to green)
        if pos < 85:
            return (255 - pos * 3, pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return (0, 255 - pos * 3, pos * 3)
        else:
            pos -= 170
            return (pos * 3, 0, 255 - pos * 3)
