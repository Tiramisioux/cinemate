import logging
import sys
import threading
import time
import signal
import atexit
import subprocess
import traceback
import os
import json
import shutil
from PIL import Image, ImageDraw, ImageFont

from module.config_loader import load_settings
from module.logger import configure_logging
from module.redis_controller import RedisController, ParameterKey
from module.ssd_monitor import SSDMonitor
from module.usb_monitor import USBMonitor
from module.gpio_output import GPIOOutput
from module.cinepi_controller import CinePiController
from module.simple_gui import SimpleGUI
from module.sensor_detect import SensorDetect
from module.redis_listener import RedisListener
from module.gpio_input import ComponentInitializer
from module.battery_monitor import BatteryMonitor
from module.wifi_hotspot import WiFiHotspotManager
from module.cli_commands import CommandExecutor
from module.dmesg_monitor import DmesgMonitor
from module.app import create_app
from module.analog_controls import AnalogControls
from module.mediator import Mediator
from module.serial_handler import SerialHandler
from module.cinepi_multi import CinePiManager as CinePi
from module.i2c_oled import I2cOled
from module.framebuffer import Framebuffer   # the same wrapper SimpleGUI uses

# Constants
MODULES_OUTPUT_TO_SERIAL = ['cinepi_controller']
SETTINGS_FILE = "/home/pi/cinemate/src/settings.json"

def hide_cursor():
    try:
        with open('/dev/tty1', 'w') as tty:
            tty.write('\033[?25l')
            tty.flush()
    except Exception as e:
        logging.warning(f"Could not hide cursor: {e}")

def show_cursor():
    try:
        with open('/dev/tty1', 'w') as tty:
            tty.write('\033[?25h')
            tty.flush()
    except Exception as e:
        logging.warning(f"Could not show cursor: {e}")

def clear_screen():
    """Clear tty1 and move the cursor to the top-left corner."""
    try:
        with open('/dev/tty1', 'w') as tty:
            tty.write('\033[2J\033[H')       # CSI 2J = clear; CSI H = home
            tty.flush()
    except Exception as e:
        logging.warning(f"Could not clear screen: {e}")

def start_splash():
    stop_event = threading.Event()

    big_font = "Lat15-TerminusBold16x32"        # ← choose from your list
    setfont  = shutil.which("setfont")          # /usr/bin/setfont (None if missing)

    # Backup current font so we can restore it later
    backup = "/tmp/cinemate.oldfont"
    if setfont:
        subprocess.run([setfont, "-O", backup], check=False)
        subprocess.run([setfont, big_font],      check=False)  # load larger font

    def _animate():
        frame = 0
        try:
            with open("/dev/tty1", "w") as tty:
                tty.write("\033[2J\033[H")          # clear screen
                tty.write("\033#6")                 # double-WIDTH for this row
                tty.write("\033#3")                 # double-HEIGHT top half
                tty.flush()

                while not stop_event.is_set():
                    dots = "." * (frame % 4)
                    tty.write(f"\rStarting CineMate {dots:<3}")
                    tty.flush()
                    frame += 1
                    time.sleep(0.4)

                # back to normal size
                tty.write("\033#5")                 # single width/height
                tty.flush()
        finally:
            # restore the original console font
            if setfont and os.path.exists(backup):
                subprocess.run([setfont, backup], check=False)

    t = threading.Thread(target=_animate, daemon=True)
    t.start()
    return t, stop_event

def graphic_splash(text="THIS IS A COOL MACHINE"):
    fb = Framebuffer(0)              # open /dev/fb0
    W, H = fb.size

    # Pick any TTF you like and a big size
    font = ImageFont.truetype("/home/pi/cinemate/resources/fonts/DIN2014-Regular.ttf",
                              size=100)

    img  = Image.new("RGB", (W, H), "black")
    draw = ImageDraw.Draw(img)
    tw, th = draw.textbbox((0, 0), text, font=font)[2:]

    draw.text(((W - tw)//2, (H - th)//2),
              text, font=font, fill="white")

    fb.show(img)
    return fb        # keep it so you can blank later

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
        wifi_mgr = WiFiHotspotManager()
        wifi_mgr.create_hotspot() 
    except Exception as e:
        logging.error(f"Failed to start WiFi hotspot: {e}")

def initialize_system(settings):
    """Initialize core system components."""
    redis_controller = RedisController()
    sensor_detect = SensorDetect()
    ssd_monitor = SSDMonitor(redis_controller=redis_controller)
    usb_monitor = USBMonitor(ssd_monitor)
    gpio_output = GPIOOutput(rec_out_pins=settings["gpio_output"]["rec_out_pin"])
    dmesg_monitor = DmesgMonitor()
    dmesg_monitor.start()

    return redis_controller, sensor_detect, ssd_monitor, usb_monitor, gpio_output, dmesg_monitor

def handle_vu_output(line):
    if "[VU]" in line:
        try:
            vu_str = line.replace("[VU]", "").strip()
            vu_values = [int(val) for val in vu_str.split(",")]
            print("VU levels:", vu_values)  # <-- You can replace this with logging or Redis

            # # Example: push to Redis
            # self.redis_controller.set_value("vu_meter", json.dumps(vu_values))

        except Exception as e:
            logging.warning(f"Failed to parse VU line: {line} ({e})")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the CinePi application.")
    parser.add_argument("-debug", action="store_true", help="Enable debug logging level.")
    args = parser.parse_args()

    # Load settings
    settings = load_settings(SETTINGS_FILE)

    # Setup logging
    logger, log_queue = setup_logging(args.debug)
    
    # # Start animated splash on HDMI
    # splash_thread, splash_stop = start_splash()
    
    # Hide cursor
    hide_cursor()
    fb_splash = graphic_splash()

    # Detect Raspberry Pi model
    pi_model = get_raspberry_pi_model()
    logging.info(f"Detected Raspberry Pi model: {pi_model}")
    set

    # Start WiFi hotspot if available
    start_hotspot()

    # Initialize system components
    redis_controller, sensor_detect, ssd_monitor, usb_monitor, gpio_output, dmesg_monitor = initialize_system(settings)
    
    # Store Pi model in Redis
    redis_controller.set_value(ParameterKey.PI_MODEL.value, pi_model)

    # Set redis anamorphic factor to default value
    redis_controller.set_value(ParameterKey.ANAMORPHIC_FACTOR.value, settings["anamorphic_preview"]["default_anamorphic_factor"])
    
    # Default zoom factor
    redis_controller.set_value(
        ParameterKey.ZOOM.value,
        settings.get("preview", {}).get("default_zoom", 1.0)
)


    # Initialize CinePi application
    cinepi = CinePi(redis_controller, sensor_detect)
    
    cinepi.start_all()

    # cinepi.set_log_level('INFO')
    # cinepi.message.subscribe(handle_vu_output)

    cinepi_controller = CinePiController(
        cinepi, redis_controller, ssd_monitor, sensor_detect,
        iso_steps=settings["arrays"]["iso_steps"],
        shutter_a_steps=settings["arrays"]["shutter_a_steps"],
        fps_steps=settings["arrays"]["fps_steps"],  
        wb_steps=settings["arrays"]["wb_steps"],
        light_hz=settings["settings"]["light_hz"],
        anamorphic_steps=settings["anamorphic_preview"]["anamorphic_steps"],
        default_anamorphic_factor=settings["anamorphic_preview"]["default_anamorphic_factor"]
    )

    gpio_input = ComponentInitializer(cinepi_controller, settings)
    
    # Create CommandExecutor (for both CLI and Serial)
    command_executor = CommandExecutor(cinepi_controller, cinepi)
    command_executor.start()  # CLI thread

    # SerialHandler to receive serial commands and treat them as CLI
    serial_handler = SerialHandler(
        callback=command_executor.handle_received_data,
        baudrate=9600,
        timeout=1,
        log_queue=log_queue  # Optional: for future serial logging
    )
    serial_handler.start()


    redis_listener = RedisListener(redis_controller, ssd_monitor)
    battery_monitor = BatteryMonitor()

    simple_gui = SimpleGUI(redis_controller, cinepi_controller, ssd_monitor, dmesg_monitor,
                       battery_monitor, sensor_detect, redis_listener, None, usb_monitor=usb_monitor, serial_handler=serial_handler)

    if settings.get("i2c_oled", {}).get("enabled", False):
        i2c_oled = I2cOled(settings, redis_controller)
        i2c_oled.start()

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

    mediator = Mediator(cinepi, cinepi_controller, redis_listener, redis_controller, ssd_monitor, gpio_output, stream, usb_monitor)
    
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
    
    # # Stop splash and clear screen so the shell prompt is visible again
    # splash_stop.set()
    # splash_thread.join()
    fb_splash.show(Image.new("RGB", fb_splash.size, "black"))   # blank
    # fb_splash.close()        # optional
    clear_screen()

    # Ensure system cleanup on exit
    def cleanup():
        logging.info("Shutting down components...")
        redis_controller.set_value(ParameterKey.IS_RECORDING.value, 0)
        redis_controller.set_value(ParameterKey.IS_WRITING.value, 0)
        redis_controller.set_value(
            ParameterKey.FPS_LAST.value,
            redis_controller.get_value(ParameterKey.FPS.value)
        )

        # Stop peripherals
        dmesg_monitor.join()
        command_executor.join()
        serial_handler.running = False
        serial_handler.join()

        if i2c_oled:
            i2c_oled.join()

        if simple_gui:
            simple_gui.stop()              # <— new: quit the thread
            simple_gui.clear_framebuffer() # <— new: blank fb0

        clear_screen()                     # wipe tty1
        show_cursor()
        
    atexit.register(cleanup)

    try:
        from signal import pause
        pause()
    except Exception:
        logging.error("An unexpected error occurred:\n" + traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
