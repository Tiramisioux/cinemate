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
from module.timekeeper import TimeKeeper

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
            fps_steps = fps_steps if fps_steps is not None else list(range(1, 51))

            settings['arrays'] = {
                'iso_steps': arrays_settings.get('iso_steps', []),
                'shutter_a_steps': arrays_settings.get('shutter_a_steps', []),
                'fps_steps': fps_steps,
                'awb_steps': arrays_settings.get('awb_steps', list(range(0, 8)))
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
    pwm_controller.stop_pwm()
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
    sensor_mode = int(redis_controller.get_value('sensor_mode'))
    
    pwm_controller = PWMController(sensor_detect, PWM_pin=settings['gpio_output']['pwm_pin'])

    cinepi = CinePi(redis_controller, sensor_detect)

    
    # Set log level (optional)
    cinepi.set_log_level('INFO')
    
    # Set active filters (optional)
    cinepi.set_active_filters(['frame', 'agc', 'ccm'])

    ssd_monitor = SSDMonitor()
    
    gpio_output = GPIOOutput(rec_out_pins=settings['gpio_output']['rec_out_pin'])
    dmesg_monitor = DmesgMonitor()
    dmesg_monitor.start()

    cinepi_controller = CinePiController(cinepi,
                                         pwm_controller,
                                         redis_controller,
                                         ssd_monitor,
                                         sensor_detect,
                                         iso_steps=settings['arrays']['iso_steps'],
                                         shutter_a_steps=settings['arrays']['shutter_a_steps'],
                                         fps_steps=settings['arrays']['fps_steps'],
                                         awb_steps=settings['arrays']['awb_steps'],
                                         light_hz=settings['settings']['light_hz'],
                                         )

    cinepi_controller.set_pwm_mode(1)
    time.sleep(2)
    cinepi.start_cinepi_process()
    gpio_input = ComponentInitializer(cinepi_controller, settings)
    
    timekeeper = TimeKeeper(redis_controller, pwm_controller, window_size=1, kp=0.13200, ki=0.01800, kd=0.06)

    command_executor = CommandExecutor(cinepi_controller, cinepi)
    command_executor.start()
    redis_listener = RedisListener(redis_controller)
    battery_monitor = BatteryMonitor()

    simple_gui = SimpleGUI(pwm_controller, 
                           redis_controller, 
                           cinepi_controller,  
                           ssd_monitor, 
                           dmesg_monitor,
                           battery_monitor,
                           sensor_detect,
                           redis_listener,
                           #timekeeper,
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

    mediator = Mediator(cinepi, redis_controller, ssd_monitor, gpio_output, stream)
    time.sleep(1)
    
    fps_current = redis_controller.get_value('fps_actual')
    cinepi_controller.set_fps(fps_current)
    
    shutter_a_current = redis_controller.get_value('shutter_a')
    cinepi_controller.set_shutter_a(shutter_a_current)
    
    cinepi.restart()
        
    logging.info(f"--- initialization complete")

    try:    
        pause()
    except Exception:
        logging.error("An unexpected error occurred:\n" + traceback.format_exc())
        sys.exit(1)
    finally:
        redis_controller.set_value('is_recording', 0)
        redis_controller.set_value('is_writing', 0)
        # timekeeper.stop()
        current_shutter_angle = redis_controller.get_value('shutter_a')
        redis_controller.set_value('shutter_a_nom', int(current_shutter_angle))
        fps_last = int(float(redis_controller.get_value('fps')))
        redis_controller.set_value('fps_last', fps_last )
        
        dmesg_monitor.join()
        command_executor.join()
        RPi.GPIO.cleanup()
