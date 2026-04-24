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
import socket
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
from module.storage_preroll import StoragePreroll
from module.dmesg_monitor import DmesgMonitor
from module.app import create_app
from module.analog_controls import AnalogControls
from module.mediator import Mediator
from module.serial_handler import SerialHandler
from module.cinepi_multi import CinePiManager as CinePi
from module.i2c.i2c_oled import I2cOled
from module.i2c.quad_rotary_controller import QuadRotaryController
from module.console_display import (
    claim_console_for_framebuffer,
    hide_cursor,
    release_console_to_text,
)
from module.framebuffer import acquire_framebuffer

# Constants
MODULES_OUTPUT_TO_SERIAL = ['cinepi_controller']
SETTINGS_FILE = "/home/pi/cinemate/src/settings.json"
STARTUP_MESSAGE_MIN_DURATION = 3.0


def _systemd_notify(message: str) -> bool:
    notify_socket = os.environ.get("NOTIFY_SOCKET")
    if not notify_socket:
        return False

    if notify_socket.startswith("@"):
        notify_socket = "\0" + notify_socket[1:]

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM | socket.SOCK_CLOEXEC) as sock:
            sock.connect(notify_socket)
            sock.sendall(message.encode("utf-8"))
        return True
    except OSError as exc:
        logging.warning("Failed to notify systemd: %s", exc)
        return False


def systemd_status(status: str) -> bool:
    return _systemd_notify(f"STATUS={status}")


def systemd_ready(status: str) -> bool:
    return _systemd_notify(f"READY=1\nSTATUS={status}")


def plymouth_is_running() -> bool:
    if os.path.exists("/run/plymouth/pid"):
        return True

    plymouth = shutil.which("plymouth")
    if not plymouth:
        return False

    try:
        result = subprocess.run(
            [plymouth, "--ping"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError as exc:
        logging.warning("Failed to check Plymouth status: %s", exc)
        return False

    return result.returncode == 0


def wait_for_plymouth_to_quit(timeout: float = 5.0, poll_interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not plymouth_is_running():
            return True
        time.sleep(poll_interval)

    logging.warning("Timed out waiting for Plymouth to quit")
    return False

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
    fb = acquire_framebuffer(0)
    if fb is None:
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

    try:
        fb.show(img)
    except (OSError, RuntimeError, ValueError) as exc:
        logging.warning(f"Failed to draw graphic splash: {exc}")
        return None
    return fb        # keep it so you can blank later


def blank_framebuffer(fb):
    if fb is None:
        return

    try:
        fb.show(Image.new("RGB", fb.size, "black"))
    except (OSError, RuntimeError, ValueError) as exc:
        logging.warning(f"Failed to blank framebuffer cleanly: {exc}")

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

def initialize_system(settings, pi_model="unknown"):
    """Initialize core system components."""
    conf_rate = settings.get("settings", {}).get("conform_frame_rate", 24)
    redis_controller = RedisController(conform_frame_rate=conf_rate)
    sensor_detect = SensorDetect(settings)
    ssd_monitor = SSDMonitor(redis_controller=redis_controller)
    usb_monitor = USBMonitor(ssd_monitor)

    gpio_cfg = settings["gpio_output"]
    rec_tone_pins = gpio_cfg.get("rec_tone_pin")
    if rec_tone_pins in (None, []):
        # Backward compatibility: if no explicit rec_tone_pin is configured,
        # fall back to pwm_pin for REC sync tone output.
        rec_tone_pins = gpio_cfg.get("pwm_pin")

    gpio_output = GPIOOutput(
        rec_out_pins=gpio_cfg["rec_out_pin"],
        rec_tone_pins=rec_tone_pins,
        rec_tone_frequency_hz=gpio_cfg.get("rec_tone_frequency_hz", 1000),
        rec_tone_duty_cycle=gpio_cfg.get("rec_tone_duty_cycle", 50),
        rec_tone_relay_drop_frames=gpio_cfg.get("rec_tone_relay_drop_frames", False),
        pi_model=pi_model,
    )
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
    splash_visible_started_at = None
    startup_ready_notified = False
    timekeeper = None

    welcome_text = settings.get("welcome_message", "THIS IS A COOL MACHINE")
    show_welcome_message = bool(
        settings.get("show_welcome_message", settings.get("show_startup_message", True))
    )
    welcome_image = settings.get("welcome_image")
    plymouth_active_at_startup = plymouth_is_running()
    defer_startup_message_until_after_plymouth = show_welcome_message and plymouth_active_at_startup
    restart_camera_after_plymouth_handoff = plymouth_active_at_startup
    if defer_startup_message_until_after_plymouth:
        logging.info("Deferring startup message until after Plymouth quits")

    fb_splash = None
    if show_welcome_message and not defer_startup_message_until_after_plymouth:
        fb_splash = graphic_splash(welcome_text, welcome_image)
        if fb_splash is None:
            splash_thread, splash_stop = start_splash(welcome_text)
            systemd_ready("Cinemate text splash active")
        else:
            claim_console_for_framebuffer()
            systemd_ready("Cinemate splash active")
        splash_visible_started_at = time.monotonic()
        startup_ready_notified = True

    # Detect Raspberry Pi model
    pi_model = get_raspberry_pi_model()
    logging.info(f"Detected Raspberry Pi model: {pi_model}")
    set

    # Start WiFi hotspot if configured
    start_hotspot(settings)

    # Initialize system components
    redis_controller, sensor_detect, ssd_monitor, usb_monitor, gpio_output, dmesg_monitor = initialize_system(
        settings,
        pi_model=pi_model,
    )
    
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

    storage_preroll = StoragePreroll(
        cinepi_controller=cinepi_controller,
        redis_controller=redis_controller,
        ssd_monitor=ssd_monitor,
        sensor_detect=sensor_detect,
    )

    gpio_cfg = settings.get("gpio_output", {})
    rec_tone_pins = gpio_cfg.get("rec_tone_pin")
    if rec_tone_pins in (None, []):
        rec_tone_pins = gpio_cfg.get("pwm_pin")

    reserved_output_pins = set(gpio_cfg.get("rec_out_pin", []))
    if rec_tone_pins is not None:
        if isinstance(rec_tone_pins, int):
            reserved_output_pins.add(rec_tone_pins)
        else:
            reserved_output_pins.update(int(pin) for pin in rec_tone_pins)

    gpio_input = ComponentInitializer(
        cinepi_controller,
        settings,
        reserved_output_pins=reserved_output_pins,
    )

    # Create CommandExecutor (for both CLI and Serial)
    command_executor = CommandExecutor(
        cinepi_controller, cinepi, storage_preroll=storage_preroll
    )
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

    if splash_visible_started_at is not None and not defer_startup_message_until_after_plymouth:
        remaining_splash_time = STARTUP_MESSAGE_MIN_DURATION - (time.monotonic() - splash_visible_started_at)
        if remaining_splash_time > 0:
            time.sleep(remaining_splash_time)

    if startup_ready_notified:
        systemd_status("Cinemate GUI starting")
    else:
        systemd_ready("Cinemate GUI starting")
        startup_ready_notified = True

    if restart_camera_after_plymouth_handoff and not defer_startup_message_until_after_plymouth:
        wait_for_plymouth_to_quit()

    if defer_startup_message_until_after_plymouth:
        wait_for_plymouth_to_quit()
        logging.info("Showing startup message after Plymouth handoff")
        fb_splash = graphic_splash(welcome_text, welcome_image)
        if fb_splash is None:
            splash_thread, splash_stop = start_splash(welcome_text)
        else:
            claim_console_for_framebuffer()
        splash_visible_started_at = time.monotonic()
        remaining_splash_time = STARTUP_MESSAGE_MIN_DURATION - (time.monotonic() - splash_visible_started_at)
        if remaining_splash_time > 0:
            time.sleep(remaining_splash_time)

    # Stop splash screen and clear framebuffer/tty
    if fb_splash:
        blank_framebuffer(fb_splash)
    elif splash_stop:
        splash_stop.set()
        splash_thread.join()
    claim_console_for_framebuffer()

    if restart_camera_after_plymouth_handoff:
        logging.info("Restarting cinepi-raw after Plymouth handoff so preview binds above Cinemate")
        cinepi_controller.restart_camera()

    redis_listener = RedisListener(redis_controller, ssd_monitor)
    battery_monitor = BatteryMonitor()
    i2c_oled = None

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

    # Wait until the welcome-message/Plymouth handoff and preview rebind are
    # finished before warming the storage media.
    storage_preroll.mark_startup_ready()
    
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
        if hasattr(cinepi, "shutdown"):
            cinepi.shutdown()
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
            blank_framebuffer(fb_splash)
        elif splash_stop:
            splash_stop.set()
            splash_thread.join()
            
        if timekeeper and hasattr(timekeeper, "stop"):
            timekeeper.stop()

        release_console_to_text()
        
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
