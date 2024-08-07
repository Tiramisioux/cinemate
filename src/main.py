import logging
import sys
import traceback
import threading
import RPi.GPIO
from signal import pause
import json
import argparse
import subprocess
import time
import signal

RPi.GPIO.setwarnings(False)
RPi.GPIO.setmode(RPi.GPIO.BCM)

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
# from module.serial_handler import SerialHandler
from module.logger import configure_logging
from module.sensor_detect import SensorDetect
from module.mediator import Mediator
from module.dmesg_monitor import DmesgMonitor
from module.redis_listener import RedisListener
from module.gpio_input import ComponentInitializer
from module.battery_monitor import BatteryMonitor
from module.app import create_app
from module.analog_controls import AnalogControls
from module.PWMcontroller import PWMController

MODULES_OUTPUT_TO_SERIAL = ['cinepi_controller']

def get_raspberry_pi_model():
    try:
        with open('/proc/device-tree/model', 'r') as f:
            model = f.read()
            if 'Raspberry Pi 5' in model:
                return 'pi5'
            elif 'Raspberry Pi 4' in model:
                return 'pi4'
            else:
                return 'other'
    except FileNotFoundError:
        return 'unknown'
    
def check_hotspot_status():
    result = subprocess.run(['nmcli', 'con', 'show', '--active'], capture_output=True, text=True)
    return any('wifi' in line and 'Hotspot' in line for line in result.stdout.split('\n'))

def load_settings(filename):
    with open(filename, 'r') as file:
        original_settings = json.load(file)
        settings = {}

        if 'gpio_output' in original_settings:
            settings['gpio_output'] = original_settings['gpio_output']

        if 'arrays' in original_settings:
            arrays_settings = original_settings['arrays']
            fps_steps = arrays_settings.get('fps_steps', list(range(1, 51)))
            settings['arrays'] = {
                'iso_steps': arrays_settings.get('iso_steps', []),
                'shutter_a_steps': arrays_settings.get('shutter_a_steps', []),
                'fps_steps': fps_steps,
                'wb_steps': arrays_settings.get('wb_steps', [])  # Correct key usage
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

        if 'quad_rotary_encoders' in original_settings:
            settings['quad_rotary_encoders'] = original_settings['quad_rotary_encoders']

        if 'settings' in original_settings:
            settings['settings'] = original_settings['settings']
        else:
            settings['settings'] = {"light_hz": 50}  # Default value if not found

        return settings

def handle_exit(signal, frame):
    logging.info("Graceful shutdown initiated.")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the CinePi application.")
    parser.add_argument("-debug", action="store_true", help="Enable debug logging level.")
    args = parser.parse_args()
    logging_level = logging.DEBUG if args.debug else logging.INFO

    logger, log_queue = configure_logging(MODULES_OUTPUT_TO_SERIAL, logging_level)
    settings = load_settings('/home/pi/cinemate/src/settings.json')

    redis_controller = RedisController()
    

    sensor_detect = SensorDetect()
    # Update the retrieval of sensor_mode
    sensor_mode_value = redis_controller.get_value('sensor_mode')
    sensor_mode = int(sensor_mode_value) if sensor_mode_value is not None else 0

    pwm_controller = PWMController(sensor_detect, PWM_pin=19)

    cinepi = CinePi(redis_controller, sensor_detect)

    # Set log level (optional)
    cinepi.set_log_level('INFO')
    
    # Set active filters (optional)
    cinepi.set_active_filters([
                              #  'frame', 
                              #  'agc', 
                              #  'ccm'
                                ])

    ssd_monitor = SSDMonitor()
    usb_monitor = USBMonitor(ssd_monitor)    
    gpio_output = GPIOOutput(rec_out_pins=settings['gpio_output']['rec_out_pin'])

    dmesg_monitor = DmesgMonitor()
    dmesg_monitor.start()

    cinepi_controller = CinePiController(cinepi,
                                         redis_controller,
                                         pwm_controller,
                                         ssd_monitor,
                                         sensor_detect,
                                         iso_steps=settings['arrays']['iso_steps'],
                                         shutter_a_steps=settings['arrays']['shutter_a_steps'],
                                         fps_steps=settings['arrays']['fps_steps'],
                                         wb_steps=settings['arrays']['wb_steps'],
                                         light_hz=settings['settings']['light_hz'],
                                         )

    gpio_input = ComponentInitializer(cinepi_controller, settings)

    command_executor = CommandExecutor(cinepi_controller, cinepi)
    command_executor.start()
    redis_listener = RedisListener(redis_controller)
    battery_monitor = BatteryMonitor()
    # serial_handler = SerialHandler(command_executor.handle_received_data, 9600, log_queue=log_queue)
    # serial_handler.start()

    simple_gui = SimpleGUI(redis_controller, 
                           cinepi_controller,  
                           ssd_monitor, 
                           dmesg_monitor,
                           battery_monitor,
                           sensor_detect,
                           redis_listener,
                           None)
    stream = None
    
    if check_hotspot_status():
        app, socketio = create_app(redis_controller, cinepi_controller, simple_gui, sensor_detect)
        simple_gui.socketio = socketio
        
        stream = threading.Thread(target=socketio.run, args=(app,), kwargs={'host': '0.0.0.0', 'port': 5000})
        stream.start()
        logging.info(f"Stream module loaded")
    else:
        logging.error("Didn't find Wi-Fi hotspot. Stream module not loaded")

    mediator = Mediator(cinepi, redis_listener, pwm_controller, redis_controller, ssd_monitor, gpio_output, stream)
    time.sleep(1)
    
    usb_monitor.check_initial_devices()
    
        
    # Extract analog control settings
    analog_settings = settings.get('analog_controls', {})
    array_settings = settings.get('arrays', {})

    # Convert "None" string to actual None type
    def convert_none_string(value):
        return None if value == "None" else value

    # Retrieve values for each potentiometer
    iso_pot = convert_none_string(analog_settings.get('iso_pot'))
    shutter_a_pot = convert_none_string(analog_settings.get('shutter_a_pot'))
    fps_pot = convert_none_string(analog_settings.get('fps_pot'))
    wb_pot = convert_none_string(analog_settings.get('wb_pot'))

    # Retrieve step values for debounce mechanism
    iso_steps = array_settings.get('iso_steps', [])
    shutter_a_steps = array_settings.get('shutter_a_steps', [])
    fps_steps = array_settings.get('fps_steps', [])
    wb_steps = array_settings.get('wb_steps', [])
    
    logging.info(f"Loaded WB steps: {wb_steps}")

    analog_controls = AnalogControls(
        cinepi_controller=cinepi_controller,
        redis_controller=redis_controller,
        iso_pot=iso_pot,
        shutter_a_pot=shutter_a_pot,
        fps_pot=fps_pot,
        wb_pot=wb_pot,
        iso_steps=settings['arrays']['iso_steps'],
        shutter_a_steps=settings['arrays']['shutter_a_steps'],
        fps_steps=settings['arrays']['fps_steps'],
        wb_steps=settings['arrays']['wb_steps']
    )


        
    # Get the trigger_mode value from Redis
    trigger_mode_value = redis_controller.get_value('trigger_mode')

    if trigger_mode_value is not None:
        try:
            # Convert trigger_mode_value to an integer
            trigger_mode = int(trigger_mode_value)
            
            # Use the cinepi_controller to set the trigger mode
            cinepi_controller.set_trigger_mode(trigger_mode)
            
            logging.info(f"Trigger mode set to {trigger_mode} using cinepi_controller.")
        except ValueError:
            logging.error(f"Invalid trigger_mode value retrieved: {trigger_mode_value}")
    else:
        logging.error("trigger_mode value is not set in Redis.")
        
    # Additional logging to verify the content of wb_steps
    logging.info(f"Initialized WB steps: {settings['arrays']['wb_steps']}")
        
    # Get the wb_user value from Redis
    wb_user_value = redis_controller.get_value('wb_user')

    if wb_user_value is not None:
        try:
            # Convert wb_user_value to an integer
            kelvin_temperature = int(wb_user_value)
            
            # Use the cinepi_controller to set the white balance
            cinepi_controller.set_wb(kelvin_temperature)
            
            #logging.info(f"White balance set using cinepi_controller for {kelvin_temperature}K")
        except ValueError:
            logging.error(f"Invalid wb_user value retrieved: {wb_user_value}")
    else:
        logging.error("wb_user value is not set in Redis.")
    
    #cinepi_controller.set_pwm_mode(1)

    logging.info(f"--- initialization complete")

    try:    
        pause()
    except Exception:
        logging.error("An unexpected error occurred:\n" + traceback.format_exc())
        sys.exit(1)
    finally:
        redis_controller.set_value('is_recording', 0)
        redis_controller.set_value('is_writing', 0)
        current_shutter_angle = float(redis_controller.get_value('shutter_a'))
        redis_controller.set_value('shutter_a_nom', int(current_shutter_angle))
        fps_last = int(float(redis_controller.get_value('fps')))
        redis_controller.set_value('fps_last', fps_last )
        #cinepi_controller.set_pwm_mode(0)
        #cinepi_controller.set_trigger_mode(0)
        redis_controller.set_value('cg_rb', '2.5,2.0')
        redis_listener.reset_framecount()
        pwm_controller.stop_pwm()
        dmesg_monitor.join()
        command_executor.join()
        RPi.GPIO.cleanup()

