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
from module.serial_handler import SerialHandler
from module.logger import configure_logging
from module.PWMcontroller import PWMController
from module.sensor_detect import SensorDetect
from module.mediator import Mediator
from module.dmesg_monitor import DmesgMonitor
from module.redis_listener import RedisListener
from module.gpio_input import ComponentInitializer
from module.battery_monitor import BatteryMonitor
from module.app import create_app

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


MODULES_OUTPUT_TO_SERIAL = ['cinepi_controller']

fps_steps = None

def load_settings(filename):
    with open(filename, 'r') as file:
        original_settings = json.load(file)

        settings = {}

        if 'gpio_output' in original_settings:
            settings['gpio_output'] = original_settings['gpio_output']

        if 'arrays' in original_settings:
            arrays_settings = original_settings['arrays']
            fps_steps = arrays_settings.get('fps_steps', list(range(1, 51)))
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

        # if 'quad_rotary_encoders' in original_settings:
        #     settings['quad_rotary_encoders'] = original_settings['quad_rotary_encoders']
            
        settings['quad_rotary_encoders'] =  {
        0: {'setting_name': 'iso', 'gpio_pin': 26},
        1: {'setting_name': 'shutter_a', 'gpio_pin': 5},
        2: {'setting_name': 'fps', 'gpio_pin': 4},
        3: {'setting_name': 'shutter_a', 'gpio_pin': 5},  # Adjust as needed
    }

        return settings

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the CinePi application.")
    parser.add_argument("-debug", action="store_true", help="Enable debug logging level.")
    args = parser.parse_args()
    logging_level = logging.DEBUG if args.debug else logging.INFO

    logger, log_queue = configure_logging(MODULES_OUTPUT_TO_SERIAL, logging_level)
    settings = load_settings('/home/pi/cinemate/src/settings.json')

    redis_controller = RedisController()

    sensor_detect = SensorDetect()
    sensor_mode = int(redis_controller.get_value('sensor_mode'))

    cinepi_app = CinePi(
        '--mode', f"{sensor_detect.get_width(sensor_detect.camera_model, sensor_mode)}:{sensor_detect.get_height(sensor_detect.camera_model, sensor_mode)}:{sensor_mode}:U",
        '--width', str(sensor_detect.get_width(sensor_detect.camera_model, sensor_mode)),
        '--height', str(sensor_detect.get_height(sensor_detect.camera_model, sensor_mode)),
        '--lores-width', str(sensor_detect.get_lores_width(sensor_detect.camera_model, sensor_mode)),
        '--lores-height', str(sensor_detect.get_lores_height(sensor_detect.camera_model, sensor_mode)),
        '-p', '0,30,1920,1020',
        '--post-process-file', 'home/pi/post-processing.json',
    )

    ssd_monitor = SSDMonitor()
    usb_monitor = USBMonitor(ssd_monitor)
    usb_drive_monitor = USBDriveMonitor(ssd_monitor=ssd_monitor)
    threading.Thread(target=usb_drive_monitor.start_monitoring, daemon=True).start()
    gpio_output = GPIOOutput(rec_out_pins=settings['gpio_output']['rec_out_pin'])
    pwm_controller = PWMController(sensor_detect, PWM_pin=settings['gpio_output']['pwm_pin'])
    dmesg_monitor = DmesgMonitor()
    dmesg_monitor.start()

    cinepi_controller = CinePiController(cinepi_app,
                                         pwm_controller,
                                         redis_controller,
                                         usb_monitor, 
                                         ssd_monitor,
                                         sensor_detect,
                                         iso_steps=settings['arrays']['iso_steps'],
                                         shutter_a_steps=settings['arrays']['shutter_a_steps'],
                                         fps_steps=settings['arrays']['fps_steps'],
                                         )

    gpio_input = ComponentInitializer(cinepi_controller, settings)
    
    cinepi_controller.set_resolution(int(redis_controller.get_value('sensor_mode')))

    usb_monitor.check_initial_devices()
    keyboard = Keyboard(cinepi_controller, usb_monitor)
    command_executor = CommandExecutor(cinepi_controller, cinepi_app)
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

    mediator = Mediator(cinepi_app, redis_controller, usb_monitor, ssd_monitor, gpio_output, stream)
    time.sleep(1)
    
    fps_current = redis_controller.get_value('fps')
    cinepi_controller.set_fps(fps_current)
        
    logging.info(f"--- initialization complete")

    try:    
        pause()
    except Exception:
        logging.error("An unexpected error occurred:\n" + traceback.format_exc())
        sys.exit(1)
    finally:
        redis_controller.set_value('is_recording', 0)
        redis_controller.set_value('is_writing', 0)
        current_shutter_angle = redis_controller.get_value('shutter_a')
        redis_controller.set_value('shutter_a_nom', int(current_shutter_angle))
        dmesg_monitor.join()
        serial_handler.join()
        command_executor.join()
        RPi.GPIO.cleanup()