import logging
import sys
import threading
import time
import signal
import atexit
import subprocess
import traceback
import os

from module.config_loader import load_settings
from module.logger import configure_logging
from module.redis_controller import RedisController
from module.cinepi_app import CinePi
from module.ssd_monitor import SSDMonitor
from module.usb_monitor import USBMonitor
from module.gpio_output import GPIOOutput
from module.cinepi_controller import CinePiController
from module.simple_gui import SimpleGUI
from module.sensor_detect import SensorDetect
from module.redis_listener import RedisListener
from module.gpio_input import ComponentInitializer
from module.battery_monitor import BatteryMonitor
from module.PWMcontroller import PWMController
from module.wifi_hotspot import WiFiHotspotManager
from module.cli_commands import CommandExecutor
from module.dmesg_monitor import DmesgMonitor
from module.app import create_app
from module.analog_controls import AnalogControls
from module.mediator import Mediator

# Constants
MODULES_OUTPUT_TO_SERIAL = ['cinepi_controller']
SETTINGS_FILE = "/home/pi/cinemate/src/settings.json"

# Graceful exit handler
def handle_exit(signal, frame):
    logging.info("Graceful shutdown initiated.")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

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

def setup_logging(debug_mode):
    logging_level = logging.DEBUG if debug_mode else logging.INFO

    # Ensure logs directory exists
    log_dir = '/home/pi/cinemate/src/logs'
    os.makedirs(log_dir, exist_ok=True)

    return configure_logging(MODULES_OUTPUT_TO_SERIAL, logging_level)


def start_hotspot():
    wifi_manager = WiFiHotspotManager()
    try:
        wifi_manager.create_hotspot('CinePi', '11111111')
    except Exception as e:
        logging.error(f"Failed to start WiFi hotspot: {e}")

def initialize_system(settings):
    """Initialize core system components."""
    redis_controller = RedisController()
    sensor_detect = SensorDetect()
    pwm_controller = PWMController(sensor_detect, PWM_pin=settings["gpio_output"]["pwm_pin"])
    ssd_monitor = SSDMonitor()
    usb_monitor = USBMonitor(ssd_monitor)
    gpio_output = GPIOOutput(rec_out_pins=settings["gpio_output"]["rec_out_pin"])
    dmesg_monitor = DmesgMonitor()
    dmesg_monitor.start()

    return redis_controller, sensor_detect, pwm_controller, ssd_monitor, usb_monitor, gpio_output, dmesg_monitor

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the CinePi application.")
    parser.add_argument("-debug", action="store_true", help="Enable debug logging level.")
    args = parser.parse_args()

    # Load settings
    settings = load_settings(SETTINGS_FILE)

    # Setup logging
    logger, log_queue = setup_logging(args.debug)

    # Detect Raspberry Pi model
    pi_model = get_raspberry_pi_model()
    logging.info(f"Detected Raspberry Pi model: {pi_model}")

    # Start WiFi hotspot if available
    start_hotspot()

    # Initialize system components
    redis_controller, sensor_detect, pwm_controller, ssd_monitor, usb_monitor, gpio_output, dmesg_monitor = initialize_system(settings)
    
    # Store Pi model in Redis
    redis_controller.set_value('pi_model', pi_model)
    
    # Set redis anamorphic factor to default value
    redis_controller.set_value('anamorphic_factor', settings["anamorphic_preview"]["default_anamorphic_factor"])

    # Initialize CinePi application
    cinepi = CinePi(redis_controller, sensor_detect)
    cinepi.set_log_level('INFO')

    cinepi_controller = CinePiController(
        cinepi, redis_controller, pwm_controller, ssd_monitor, sensor_detect,
        iso_steps=settings["arrays"]["iso_steps"],
        shutter_a_steps=settings["arrays"]["shutter_a_steps"],
        fps_steps=settings["arrays"]["fps_steps"],
        wb_steps=settings["arrays"]["wb_steps"],
        light_hz=settings["settings"]["light_hz"],
        anamorphic_steps=settings["anamorphic_preview"]["anamorphic_steps"],
        default_anamorphic_factor=settings["anamorphic_preview"]["default_anamorphic_factor"]
    )

    gpio_input = ComponentInitializer(cinepi_controller, settings)
    command_executor = CommandExecutor(cinepi_controller, cinepi)
    command_executor.start()
    redis_listener = RedisListener(redis_controller)
    battery_monitor = BatteryMonitor()

    simple_gui = SimpleGUI(redis_controller, cinepi_controller, ssd_monitor, dmesg_monitor, battery_monitor, sensor_detect, redis_listener, None)

    # Start Streaming if hotspot is available
    stream = None
    if check_hotspot_status():
        app, socketio = create_app(redis_controller, cinepi_controller, simple_gui, sensor_detect)
        simple_gui.socketio = socketio
        stream = threading.Thread(target=socketio.run, args=(app,), kwargs={'host': '0.0.0.0', 'port': 5000, 'allow_unsafe_werkzeug': True})
        stream.start()
        logging.info("Stream module loaded")
    else:
        logging.error("Didn't find Wi-Fi hotspot. Stream module not loaded")

    mediator = Mediator(cinepi, redis_listener, pwm_controller, redis_controller, ssd_monitor, gpio_output, stream)
    
    # Initialize USB monitoring
    usb_monitor.check_initial_devices()

    # Setup Analog Controls
    analog_controls = AnalogControls(
        cinepi_controller, redis_controller,
        settings["analog_controls"]["iso_pot"],
        settings["analog_controls"]["shutter_a_pot"],
        settings["analog_controls"]["fps_pot"],
        settings["analog_controls"]["wb_pot"],
        settings["arrays"]["iso_steps"],
        settings["arrays"]["shutter_a_steps"],
        settings["arrays"]["fps_steps"],
        settings["arrays"]["wb_steps"]
    )

    logging.info("--- Initialization Complete ---")

    # Ensure system cleanup on exit
    def cleanup():
        logging.info("Shutting down components...")
        redis_controller.set_value('is_recording', 0)
        redis_controller.set_value('is_writing', 0)
        pwm_controller.stop_pwm()
        dmesg_monitor.join()
        command_executor.join()
    
    atexit.register(cleanup)

    try:
        from signal import pause
        pause()
    except Exception:
        logging.error("An unexpected error occurred:\n" + traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
