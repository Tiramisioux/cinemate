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
import glob

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
from module.i2c.i2c_oled import I2cOled
from module.i2c.quad_rotary_controller import QuadRotaryController
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

def start_splash(text="THIS IS A COOL MACHINE"):
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
                tty.write(text + "\n")
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

def graphic_splash(text="THIS IS A COOL MACHINE", image_path=None):
    fb_path = "/dev/fb0"
    if not os.path.exists(fb_path):
        logging.info("No HDMI framebuffer found. Skipping graphic splash")
        return None

    fb = Framebuffer(0)
    if fb.size == (0, 0):
        logging.info("Framebuffer not ready. Skipping graphic splash")
        return None

    W, H = fb.size

    img = Image.new("RGB", (W, H), "black")

    if image_path and os.path.exists(image_path):
        try:
            pic = Image.open(image_path).convert("RGB")
            pic = pic.resize((W, H))
            img.paste(pic)
        except Exception as e:
            logging.error(f"Failed to load splash image: {e}")
    else:
        font = ImageFont.truetype(
            "/home/pi/cinemate/resources/fonts/DIN2014-Regular.ttf",
            size=100,
        )
        draw = ImageDraw.Draw(img)
        tw, th = draw.textbbox((0, 0), text, font=font)[2:]
        draw.text(((W - tw) // 2, (H - th) // 2), text, font=font, fill="white")

    fb.show(img)
    return fb        # keep it so you can blank later

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
    """Return True if a Wi-Fi hotspot connection is active."""
    result = subprocess.run(
        ['nmcli', 'con', 'show', '--active'], capture_output=True, text=True
    )
    return any('wifi' in line and 'Hotspot' in line for line in result.stdout.split('\n'))

def interface_has_ip(iface: str) -> bool:
    """Return True if *iface* has an IPv4 address assigned."""
    try:
        res = subprocess.run(
            ['ip', '-4', 'addr', 'show', iface],
            capture_output=True, text=True, check=True
        )
        return any(
            line.strip().startswith('inet ')
            for line in res.stdout.splitlines()
        )
    except subprocess.CalledProcessError:
        return False

def network_available() -> bool:
    """Return True if wlan0 or eth0 has an IP address."""
    return interface_has_ip('wlan0') or interface_has_ip('eth0')

def setup_logging(debug_mode):
    """
    Configure logging:
    - Clears existing .log files on startup to prevent unbounded growth
    - Resets any existing root logger handlers to avoid duplicate console output
    """
    logging_level = logging.DEBUG if debug_mode else logging.INFO

    # Ensure logs directory exists
    log_dir = '/home/pi/cinemate/src/logs'
    os.makedirs(log_dir, exist_ok=True)

    # Clear existing log files
    pattern = os.path.join(log_dir, '*.log')
    for logfile in glob.glob(pattern):
        try:
            os.remove(logfile)
        except OSError as e:
            # Removal failures reported to stderr
            print(f"Warning: Failed to remove log file {logfile}: {e}")

    # Remove all existing handlers from the root logger to prevent duplicate messages
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Configure new logging handlers (file, serial, etc.)
    return configure_logging(MODULES_OUTPUT_TO_SERIAL, logging_level)

def start_hotspot(settings) -> None:
    """Start hotspot if enabled in *settings*."""
    wifi_mgr = WiFiHotspotManager(settings=settings)
    if not wifi_mgr.enabled:
        logging.info("Wi-Fi hotspot disabled in settings")
        return
    try:
        wifi_mgr.create_hotspot()
    except Exception as e:
        logging.error(f"Failed to start WiFi hotspot: {e}")

def initialize_system(settings):
    """Initialize core system components."""
    conf_rate = settings.get("settings", {}).get("conform_frame_rate", 24)
    redis_controller = RedisController(conform_frame_rate=conf_rate)
    sensor_detect = SensorDetect(settings)
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

    splash_thread = splash_stop = None

    welcome_text = settings.get("welcome_message", "THIS IS A COOL MACHINE")
    welcome_image = settings.get("welcome_image")

    fb_splash = graphic_splash(welcome_text, welcome_image)
    if fb_splash is None:
        splash_thread, splash_stop = start_splash(welcome_text)

    # Detect Raspberry Pi model
    pi_model = get_raspberry_pi_model()
    logging.info(f"Detected Raspberry Pi model: {pi_model}")
    set

    # Start WiFi hotspot if configured
    start_hotspot(settings)

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

    # Reset recording time
    redis_controller.set_value(ParameterKey.RECORDING_TIME.value, 0)
    
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
    
    def _relay_rec_over_serial(rc, sh, poll=0.05):
        last = rc.get_value(ParameterKey.IS_RECORDING.value)
        while True:
            cur = rc.get_value(ParameterKey.IS_RECORDING.value)
            if cur != last:
                sh.write_to_ports("rec" if str(cur) == "1" else "stop")
                last = cur
            time.sleep(poll)

    t = threading.Thread(target=_relay_rec_over_serial, args=(redis_controller, serial_handler), daemon=True)
    t.start()


    redis_listener = RedisListener(redis_controller, ssd_monitor)
    battery_monitor = BatteryMonitor()

    simple_gui = SimpleGUI(
        redis_controller,
        cinepi_controller,
        ssd_monitor,
        dmesg_monitor,
        battery_monitor,
        sensor_detect,
        redis_listener,
        None,
        usb_monitor=usb_monitor,
        serial_handler=serial_handler,
        settings=settings,
    )

    if settings.get("i2c_oled", {}).get("enabled", False):
        i2c_oled = I2cOled(settings, redis_controller)
        i2c_oled.start()

    quad_rotary = None
    qcfg = settings.get("quad_rotary_controller", {})
    if qcfg.get("enabled", False) and qcfg.get("encoders"):
        quad_rotary = QuadRotaryController(cinepi_controller, settings)
        quad_rotary.start()

    # Start Streaming if a network connection is available
    stream = None
    if network_available():
        app, socketio = create_app(redis_controller, cinepi_controller, simple_gui, sensor_detect)
        simple_gui.socketio = socketio
        stream = threading.Thread(target=socketio.run, args=(app,), kwargs={'host': '0.0.0.0', 'port': 5000, 'allow_unsafe_werkzeug': True})
        stream.start()
        logging.info("Stream module loaded")
    else:
        logging.error("No network connection found. Stream module not loaded")

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
    
    # Mount CFE card if not mounted
    cinepi_controller.mount()
    
    # Stop splash screen and clear framebuffer/tty
    if fb_splash:
        fb_splash.show(Image.new("RGB", fb_splash.size, "black"))
    elif splash_stop:
        splash_stop.set()
        splash_thread.join()
    clear_screen()
    
    # Ensure system cleanup on exit
    cleanup_called = False

    # Ensure system cleanup on exit
    def cleanup():
        nonlocal cleanup_called
        if cleanup_called:
            return
        cleanup_called = True
        logging.info("Shutting down components...")
        redis_controller.set_value(ParameterKey.IS_RECORDING.value, 0)
        redis_controller.set_value(ParameterKey.IS_WRITING.value, 0)
        redis_controller.set_value(
            ParameterKey.FPS_LAST.value,
            redis_controller.get_value(ParameterKey.FPS.value)
        )

        # Stop peripherals

        if hasattr(dmesg_monitor, "stop"):
            dmesg_monitor.stop() 
        if hasattr(command_executor, "stop"):
            command_executor.stop()
        dmesg_monitor.join()
        command_executor.join()
        cinepi_controller.stop()
        serial_handler.running = False
        serial_handler.join()

        if i2c_oled:
            i2c_oled.join()
        if quad_rotary:
            quad_rotary.join()

        if simple_gui:
            simple_gui.stop()              # <— new: quit the thread
            simple_gui.clear_framebuffer() # <— new: blank fb0

        if fb_splash:
            fb_splash.show(Image.new("RGB", fb_splash.size, "black"))
        elif splash_stop:
            splash_stop.set()
            splash_thread.join()
            
        if timekeeper:
            timekeeper.stop()


        clear_screen()                     # wipe tty1
        show_cursor()
        
    atexit.register(cleanup)
    
    def handle_exit(sig, frame):
        logging.info("Graceful shutdown initiated.")
        cleanup()                 # stop your threads, join them if you like
        # restore default handler and re-raise
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGINT)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)


    try:
        from signal import pause
        pause()
    except Exception:
        logging.error("An unexpected error occurred:\n" + traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
