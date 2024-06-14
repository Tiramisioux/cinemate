import logging
import sys
import traceback
import threading
import RPi.GPIO as GPIO
from signal import pause
import json
import argparse

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

from module.redis_controller import RedisController
from module.cinepi_app import CinePi
from module.usb_monitor import USBMonitor, USBDriveMonitor
from module.ssd_monitor import SSDMonitor
from module.gpio_output import GPIOOutput
from module.cinepi_controller import CinePiController
from module.simple_gui import SimpleGUI
from module.analog_controls import AnalogControls
from module.grove_base_hat_adc import ADC
from module.keyboard import Keyboard
from module.cli_commands import CommandExecutor
from module.serial_handler import SerialHandler
from module.logger import configure_logging
from module.rotary_encoder import SimpleRotaryEncoder
from module.PWMcontroller import PWMController
from module.sensor_detect import SensorDetect
from module.mediator import Mediator
from module.dmesg_monitor import DmesgMonitor
from module.redis_listener import RedisListener
from module.gpio_input import ComponentInitializer
from module.battery_monitor import BatteryMonitor


MODULES_OUTPUT_TO_SERIAL = ['cinepi_controller']

fps_steps = None

def load_settings(filename):
    with open(filename, 'r') as file:
        original_settings = json.load(file)

        # Initialize an empty settings dictionary
        settings = {}

        # Dynamically load settings based on what's available in the JSON file
        if 'gpio_output' in original_settings:
            settings['gpio_output'] = original_settings['gpio_output']

        if 'arrays' in original_settings:
            arrays_settings = original_settings['arrays']
            fps_steps = arrays_settings.get('fps_steps', list(range(1, 51)))
            # Ensure fps_steps is a list if it's null in the JSON
            fps_steps = fps_steps if fps_steps is not None else list(range(1, 51))

            settings['arrays'] = {
                'iso_steps': arrays_settings.get('iso_steps', []),
                'shutter_a_steps': sorted(set(range(1, 361)).union(arrays_settings.get('additional_shutter_a_steps', []))),
                'fps_steps': fps_steps
            }

        if 'analog_controls' in original_settings:
            settings['analog_controls'] = original_settings['analog_controls']

        if 'buttons' in original_settings:
            settings['buttons'] = original_settings['buttons']

        if 'two_way_switches' in original_settings:
            settings['two_way_switches'] = original_settings['two_way_switches']

        if 'rotary_encoders' in original_settings:
            settings['rotary_encoders'] = original_settings['rotary_encoders']

        if 'combined_actions' in original_settings:
            settings['combined_actions'] = original_settings['combined_actions']

        return settings
    
if __name__ == "__main__":
    
    # Create the argument parser
    parser = argparse.ArgumentParser(description="Run the CinePi application.")

    # Add the debug argument
    parser.add_argument("-debug", action="store_true", help="Enable debug logging level.")

    # Parse the arguments
    args = parser.parse_args()

    # Determine the logging level based on the presence of the -debug flag
    logging_level = logging.DEBUG if args.debug else logging.INFO

    logger, log_queue = configure_logging(MODULES_OUTPUT_TO_SERIAL, logging_level)

    settings = load_settings('/home/pi/cinemate/src/settings.json')

    # Detect sensor
    sensor_detect = SensorDetect()
    
    # Instantiate the CinePi instance
    cinepi_app = CinePi(
        '--mode', '2736:1824:12:U',
        '--width', '1920',
        '--height', '1080',
        '--lores-width', '1280',
        '--lores-height', '720',
        '-p', '0,27,1920,1026'
    )

    # Instantiate other necessary components
    redis_controller = RedisController()
    ssd_monitor = SSDMonitor()
    usb_monitor = USBMonitor(ssd_monitor)
    
    usb_drive_monitor = USBDriveMonitor(ssd_monitor=ssd_monitor)
    threading.Thread(target=usb_drive_monitor.start_monitoring, daemon=True).start()
    
    gpio_output = GPIOOutput(rec_out_pins=settings['gpio_output']['rec_out_pin'])  # Use rec_out_pins
    
    pwm_controller = PWMController(sensor_detect, PWM_pin=settings['gpio_output']['pwm_pin'])
     
    dmesg_monitor = DmesgMonitor()
    dmesg_monitor.start()

    # Instantiate the CinePiController with all necessary components and settings
    cinepi_controller = CinePiController(pwm_controller,
                                        redis_controller,
                                        usb_monitor, 
                                        ssd_monitor,
                                        sensor_detect,
                                        iso_steps=settings['arrays']['iso_steps'],
                                        shutter_a_steps=settings['arrays']['shutter_a_steps'],
                                        fps_steps=fps_steps
                                        )
    
    #gpio_input = ComponentInitializer(cinepi_controller, settings)

    analog_controls = AnalogControls(
        cinepi_controller,
        iso_pot=settings['analog_controls']['iso_pot'],
        shutter_a_pot=settings['analog_controls']['shutter_a_pot'],
        fps_pot=settings['analog_controls']['fps_pot']
    )
    # Instantiate the Mediator and pass the components to it
    mediator = Mediator(cinepi_app, redis_controller, usb_monitor, ssd_monitor, gpio_output)

    # Only after the mediator has been set up and subscribed to the events,
    # we can trigger methods that may cause the events to fire.
    usb_monitor.check_initial_devices()
    
    keyboard = Keyboard(cinepi_controller, usb_monitor)
    
    # Instantiate the CommandExecutor with all necessary components and settings
    command_executor = CommandExecutor(cinepi_controller, cinepi_app)

    # Start the CommandExecutor thread
    command_executor.start()
    
    serial_handler = SerialHandler(command_executor.handle_received_data, 9600, log_queue=log_queue)
    serial_handler.start()
    
    redis_listener = RedisListener(redis_controller)
    
    battery_monitor = BatteryMonitor()
    
    simple_gui = SimpleGUI(pwm_controller, 
                           redis_controller, 
                           cinepi_controller, 
                           usb_monitor, 
                           ssd_monitor, 
                           serial_handler,
                           dmesg_monitor,
                           battery_monitor,
                           sensor_detect
                           )

    # Log initialization complete message
    logging.info(f"--- initialization complete")

    try:
        redis_controller.set_value('is_recording', 0)
        redis_controller.set_value('is_writing', 0)
        # Pause program execution, keeping it running until interrupted
        pause()
    except Exception:
        logging.error("An unexpected error occurred:\n" + traceback.format_exc())
        sys.exit(1)
    finally:
        # Reset trigger mode to deafult 0
        pwm_controller.stop_pwm()
        pwm_controller.set_trigger_mode(0)
        # Reset redis values to default
        redis_controller.set_value('fps', 24)
        redis_controller.set_value('is_recording', 0)
        redis_controller.set_value('is_writing', 0)
        
        # Set recording status to 0  
        #gpio_output.set_recording(0)
        
        dmesg_monitor.join()
        serial_handler.join()
        command_executor.join()
        
        # Cleanup GPIO pins
        GPIO.cleanup()
