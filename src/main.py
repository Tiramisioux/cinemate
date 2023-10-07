import logging
from signal import pause
import logging
import sys
import traceback

from module.redis_controller import RedisController
from module.cinepi_app import CinePi
from module.usb_monitor import USBMonitor
from module.ssd_monitor import SSDMonitor
from module.gpio_output import GPIOOutput
from module.cinepi_controller import CinePiController
from module.simple_gui import SimpleGUI
from module.gpio_controls import GPIOControls
from module.analog_controls import AnalogControls
from module.grove_base_hat_adc import ADC
from module.audio_recorder import AudioRecorder
from module.keyboard import Keyboard
from module.system_button import SystemButton
from module.cli_commands import CommandExecutor
from module.serial_handler import SerialHandler
from module.logging import configure_logging

MODULES_OUTPUT_TO_SERIAL = ['cinepi_controller'] 

class Mediator:
    def __init__(self, cinepi_app, usb_monitor, ssd_monitor, gpio_output):
        self.cinepi_app = cinepi_app
        self.usb_monitor = usb_monitor
        self.ssd_monitor = ssd_monitor
        self.gpio_output = gpio_output
        
        self.cinepi_app.message.subscribe(self.handle_cinepi_message)
        self.usb_monitor.usb_event.subscribe(self.handle_usb_event)
        self.ssd_monitor.write_status_changed_event.subscribe(self.handle_write_status_change)

    def handle_cinepi_message(self, message):
        # Handle CinePi app messages (currently not logging)
        pass  
    
    def handle_usb_event(self, action, device, device_model, device_serial):
        # Handle USB events
        if 'SSD' in device_model.upper():
            self.ssd_monitor.update(action, device_model, device_serial)

    def handle_ssd_event(self, message):
        # Handle SSD events
        print(f"SSDMonitor says: {message}")
        self.ssd_monitor.get_ssd_space_left()
        space_left = self.ssd_monitor.last_space_left
        print('Space left:', space_left)
        
    def handle_write_status_change(self, status):
        """Change the rec_pin based on the SSD write status."""
        self.gpio_output.set_recording(status)

def main():
    logger, log_queue = configure_logging(MODULES_OUTPUT_TO_SERIAL)
    # Instantiate the CinePi instance
    cinepi_app = CinePi()

    # Instantiate other necessary components
    redis_controller = RedisController()
    usb_monitor = USBMonitor()
    ssd_monitor = SSDMonitor()
    system_button = SystemButton(redis_controller, ssd_monitor, system_button_pin=26)
    gpio_output = GPIOOutput(rec_out_pin=5)
    audio_recorder = AudioRecorder(usb_monitor, gain = 8)

    # Instantiate the CinePiController with all necessary components and settings
    cinepi_controller = CinePiController(redis_controller,
                                        usb_monitor, 
                                        ssd_monitor,
                                        audio_recorder, 
                                        iso_steps=[100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],    # Array for selectable ISO values (100-3200)
                                        shutter_a_steps=[45, 90, 135, 172.8, 180, 225, 270, 315, 346.6, 360],       # Array for selectable shutter angle values (0-360 degrees in increments of 2 degrees)
                                        fps_steps=[1,2,4,8,16,18,24,25,33,48,50])      # Array for selectable fps values (1-50). To create an array of all frame rates from 1 - 50, replace the array with "list(range(1, 50))"")

    # Instantiate the AnalogControls component
    analog_controls = AnalogControls(cinepi_controller, iso_pot=0, shutter_a_pot=2, fps_pot=4)

    # Instantiate the GPIOControls component
    gpio_controls = GPIOControls(cinepi_controller,
                                iso_inc_pin=23,              # GPIO pin for button for increasing ISO
                                iso_dec_pin=25,              # GPIO pin for button for decreasing ISO
                                pot_lock_pin=16,             # GPIO pin for attaching shutter angle and fps potentiometer lock switch
                                res_button_pin=[13, 24],     # GPIO resolution button - switches between 1080 (cropped) and 1520 (full frame)
                                fps_mult_pin1=18,            # Flip switch for 50% frame rate
                                fps_mult_pin2=19,            # Flip switch for 200% frame rate (up to 50 fps)
                                rec_pin=[4, 6, 22])          # GPIO recording pins        



    # Instantiate the Mediator and pass the components to it
    mediator = Mediator(cinepi_app, usb_monitor, ssd_monitor, gpio_output)

    # Only after the mediator has been set up and subscribed to the events,
    # we can trigger methods that may cause the events to fire.
    usb_monitor.check_initial_devices()

    keyboard = Keyboard(cinepi_controller, usb_monitor)
    
    # Instantiate the CommandExecutor with all necessary components and settings
    command_executor = CommandExecutor(cinepi_controller, system_button)

    # Start the CommandExecutor thread
    command_executor.start()
    
    serial_handler = SerialHandler(command_executor.handle_received_data, 9600, log_queue=log_queue)
    serial_handler.start()
    
    simple_gui = SimpleGUI(redis_controller, usb_monitor, ssd_monitor, serial_handler)

    # Log initialization complete message
    logging.info(f"--- initialization complete")

    # Pause program execution, keeping it running until interrupted
    pause()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.error("An unexpected error occurred:\n" + traceback.format_exc())
        sys.exit(1)
        
        #, '/dev/serial0', '/dev/ttyS0']
