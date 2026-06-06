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

from module.config_loader import SettingsLoadError, auto_storage_preroll_enabled, load_settings
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
    get_console_tty_path,
    hide_cursor,
    release_console_to_text,
)
from module.framebuffer import acquire_framebuffer

# Constants
MODULES_OUTPUT_TO_SERIAL = ['cinepi_controller']
SETTINGS_FILE = "/home/pi/cinemate/src/settings.json"
STARTUP_MESSAGE_MIN_DURATION = 3.0
CLI_COLOR_RED = "\033[1;31m"
CLI_COLOR_YELLOW = "\033[1;33m"
CLI_COLOR_RESET = "\033[0m"
LOCAL_FAILURE_TTY_PATHS = ("/dev/tty1", "/dev/console")
LOCAL_FAILURE_HOLD_SECONDS = 12.0
STARTUP_LOG_TAIL_LINES = 40
STARTUP_FAILURE_FILE = os.environ.get(
    "CINEMATE_STARTUP_FAILURE_FILE",
    "/home/pi/.cache/cinemate/startup-failure.ansi",
)
STARTUP_READY_SENT = False
APP_RUNTIME_READY = False
SYSTEM_SHUTDOWN_TARGETS = frozenset(
    {
        "halt.target",
        "kexec.target",
        "poweroff.target",
        "reboot.target",
        "shutdown.target",
    }
)
CINEMATE_LOCKFILE = "/tmp/cinemate.lock"


def _release_run_lock() -> None:
    try:
        os.remove(CINEMATE_LOCKFILE)
    except OSError:
        pass


def _acquire_run_lock() -> None:
    """Stop any running cinemate instance, then acquire the startup lock."""
    existing_pid: int | None = None
    if os.path.exists(CINEMATE_LOCKFILE):
        try:
            with open(CINEMATE_LOCKFILE) as fh:
                existing_pid = int(fh.read().strip())
        except (OSError, ValueError):
            existing_pid = None

    if existing_pid is not None and existing_pid != os.getpid():
        alive = False
        try:
            os.kill(existing_pid, 0)
            alive = True
        except ProcessLookupError:
            pass  # stale lock — process already gone
        except PermissionError:
            alive = True  # process exists but owned by another user

        if alive:
            logging.info("Stopping existing cinemate instance (PID %d) ...", existing_pid)
            try:
                os.kill(existing_pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            else:
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    try:
                        os.kill(existing_pid, 0)
                    except ProcessLookupError:
                        break
                    time.sleep(0.1)
                else:
                    logging.warning(
                        "PID %d did not exit after SIGTERM; sending SIGKILL", existing_pid
                    )
                    try:
                        os.kill(existing_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    time.sleep(0.5)
            logging.info("Previous cinemate instance stopped.")

    try:
        with open(CINEMATE_LOCKFILE, "w") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass  # non-fatal if /tmp is not writable

    atexit.register(_release_run_lock)


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
    global STARTUP_READY_SENT
    notified = _systemd_notify(f"READY=1\nSTATUS={status}")
    if notified:
        STARTUP_READY_SENT = True
    return notified


def mark_runtime_ready(status: str = "Cinemate running") -> bool:
    global APP_RUNTIME_READY
    APP_RUNTIME_READY = True
    if STARTUP_READY_SENT:
        return systemd_status(status)
    return systemd_ready(status)


def render_startup_failure_block(title: str, body: str, log_lines: list[str] | None = None) -> str:
    separator = f"{CLI_COLOR_YELLOW}{'=' * 78}{CLI_COLOR_RESET}"
    sections = [
        "",
        separator,
        f"{CLI_COLOR_RED}{title}{CLI_COLOR_RESET}",
        separator,
        body,
    ]
    if log_lines:
        sections.extend(
            [
                "",
                f"{CLI_COLOR_YELLOW}Startup sequence:{CLI_COLOR_RESET}",
                *log_lines,
            ]
        )
    sections.extend(["", ""])
    return "\n".join(sections)


def print_startup_failure_block(title: str, body: str, log_lines: list[str] | None = None) -> None:
    sys.stderr.write(render_startup_failure_block(title, body, log_lines))
    sys.stderr.flush()


def clear_persisted_startup_failure() -> None:
    try:
        os.remove(STARTUP_FAILURE_FILE)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logging.debug("Failed to clear persisted startup failure at %s: %s", STARTUP_FAILURE_FILE, exc)


def persist_startup_failure(title: str, body: str, log_lines: list[str] | None = None) -> bool:
    if APP_RUNTIME_READY or not running_under_systemd_service():
        return False

    payload = render_startup_failure_block(title, body, log_lines)
    try:
        os.makedirs(os.path.dirname(STARTUP_FAILURE_FILE), exist_ok=True)
        with open(STARTUP_FAILURE_FILE, "w", encoding="utf-8", errors="replace") as handle:
            handle.write(payload)
        return True
    except OSError as exc:
        logging.warning("Failed to persist startup failure for tty replay: %s", exc)
        return False


def get_recent_log_lines(log_queue, limit: int = STARTUP_LOG_TAIL_LINES) -> list[str]:
    if log_queue is None:
        return []
    with log_queue.mutex:
        return list(log_queue.queue)[-limit:]


def running_under_systemd_service() -> bool:
    return bool(os.environ.get("NOTIFY_SOCKET") or os.environ.get("INVOCATION_ID"))


def current_stderr_tty_path() -> str | None:
    try:
        return os.ttyname(sys.stderr.fileno())
    except OSError:
        return None


def restore_local_console_prompt() -> bool:
    """Restore a visible tty1 prompt after Cinemate stop (SSH or local launch)."""
    systemctl = shutil.which("systemctl")
    if systemctl:
        # Restart getty@tty1 to ensure it's running and rendering
        commands = []
        sudo = shutil.which("sudo")
        if sudo:
            commands.append(
                [sudo, "-n", systemctl, "--no-block", "--no-ask-password", "restart", "getty@tty1.service"]
            )
        commands.append(
            [systemctl, "--no-block", "--no-ask-password", "restart", "getty@tty1.service"]
        )

        for command in commands:
            try:
                result = subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except OSError as exc:
                logging.debug("Failed to run %s during console restore: %s", command[0], exc)
                continue
            if result.returncode == 0:
                time.sleep(1.2)
                break

    # Nudge getty by writing to tty1 to trigger prompt rendering
    for tty_path in LOCAL_FAILURE_TTY_PATHS:
        try:
            with open(tty_path, "w", encoding="utf-8", errors="replace") as tty:
                # Write newlines with delays to ensure getty detects input
                for _ in range(5):
                    tty.write("\r\n")
                    tty.flush()
                    time.sleep(0.1)
            # Final delay to let getty fully render before cleanup completes
            time.sleep(0.5)
            return True
        except OSError:
            continue
    return False


def should_mirror_failure_to_local_console() -> bool:
    if APP_RUNTIME_READY:
        return False
    return current_stderr_tty_path() not in LOCAL_FAILURE_TTY_PATHS


def handoff_plymouth_for_failure() -> None:
    if not plymouth_is_running():
        return

    plymouth = shutil.which("plymouth")
    if plymouth:
        try:
            subprocess.run(
                [plymouth, "quit"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError as exc:
            logging.warning("Failed to quit Plymouth for startup failure display: %s", exc)
    wait_for_plymouth_to_quit(timeout=2.0, poll_interval=0.1)


def mirror_failure_to_local_console(title: str, body: str, log_lines: list[str] | None = None) -> bool:
    if not should_mirror_failure_to_local_console():
        return False

    try:
        release_console_to_text()
    except Exception as exc:
        logging.debug("Failed to release console to text before failure display: %s", exc)

    handoff_plymouth_for_failure()
    payload = "\033[2J\033[H" + render_startup_failure_block(title, body, log_lines)

    for tty_path in LOCAL_FAILURE_TTY_PATHS:
        try:
            with open(tty_path, "w", encoding="utf-8", errors="replace") as tty:
                tty.write(payload)
                tty.flush()
            return True
        except OSError:
            continue
    return False


def report_startup_failure(title: str, body: str, log_lines: list[str] | None = None) -> None:
    print_startup_failure_block(title, body, log_lines)
    if running_under_systemd_service():
        persist_startup_failure(title, body, log_lines)
        return

    if mirror_failure_to_local_console(title, body, log_lines):
        if running_under_systemd_service():
            time.sleep(LOCAL_FAILURE_HOLD_SECONDS)


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


def systemd_manager_state() -> str | None:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return None

    try:
        result = subprocess.run(
            [systemctl, "is-system-running"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logging.debug("Failed to inspect systemd manager state: %s", exc)
        return None

    state = result.stdout.strip()
    return state or None


def system_shutdown_in_progress() -> bool:
    state = systemd_manager_state()
    if state in {"stopping", "offline"}:
        return True

    systemctl = shutil.which("systemctl")
    if not systemctl:
        return False

    try:
        result = subprocess.run(
            [systemctl, "list-jobs", "--no-legend", "--no-pager"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logging.debug("Failed to inspect systemd jobs during shutdown detection: %s", exc)
        return False

    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] in SYSTEM_SHUTDOWN_TARGETS:
            return True

    return False

def start_splash(text="THIS IS A COOL MACHINE"):
    stop_event = threading.Event()
    tty_path = get_console_tty_path()
    if tty_path is None:
        logging.info("No writable console TTY available; skipping text splash")
        return None, None

    big_font = "Lat15-TerminusBold16x32"        # ← choose from your list
    setfont  = shutil.which("setfont")          # /usr/bin/setfont (None if missing)

    # Backup current font so we can restore it later
    backup = "/tmp/cinemate.oldfont"
    if setfont:
        subprocess.run([setfont, "-O", backup], check=False)
        subprocess.run([setfont, big_font],      check=False)  # load larger font

    def _draw_centered_line(tty, row: int, text_line: str, columns: int) -> None:
        col = max(1, ((columns - len(text_line)) // 2) + 1)
        tty.write(f"\033[{row};{col}H{text_line}")

    def _animate():
        frame = 0
        try:
            with open(tty_path, "w") as tty:
                try:
                    rows, columns = os.get_terminal_size(tty.fileno())
                except OSError:
                    rows, columns = (24, 80)

                title_row = max(1, rows // 2 - 1)
                status_row = min(rows, title_row + 2)
                status_template = "Starting CineMate ..."

                tty.write("\033[2J\033[H")          # clear screen
                _draw_centered_line(tty, title_row, text, columns)
                tty.flush()

                while not stop_event.is_set():
                    dots = "." * (frame % 4)
                    _draw_centered_line(tty, status_row, f"{' ' * len(status_template)}", columns)
                    _draw_centered_line(tty, status_row, f"Starting CineMate {dots:<3}", columns)
                    tty.flush()
                    frame += 1
                    time.sleep(0.4)
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

    claim_console_for_framebuffer()

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
    usb_monitor = USBMonitor(ssd_monitor, settings=settings)

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

def run_application(args, log_queue):
    settings = load_settings(SETTINGS_FILE)
    
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
    restart_camera_after_startup_handoff = plymouth_active_at_startup
    if defer_startup_message_until_after_plymouth:
        logging.info("Deferring startup message until after Plymouth quits")

    fb_splash = None
    if show_welcome_message and not defer_startup_message_until_after_plymouth:
        fb_splash = graphic_splash(welcome_text, welcome_image)
        if fb_splash is None:
            splash_thread, splash_stop = start_splash(welcome_text)
            if splash_thread is not None:
                systemd_status("Cinemate text splash active")
        else:
            systemd_status("Cinemate splash active")
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
    _audio_cfg = settings.get("audio", {})
    redis_controller.set_value(
        ParameterKey.AUDIO_CAPTURE_GAIN_DB.value,
        (_audio_cfg.get("16bit") or {}).get("capture_gain_db",
            _audio_cfg.get("capture_gain_db", 0.0)),
    )
    
    # Default zoom factor
    redis_controller.set_value(
        ParameterKey.ZOOM.value,
        settings.get("preview", {}).get("default_zoom", 1.0)
)

    # Reset recording time
    redis_controller.set_value(ParameterKey.RECORDING_TIME.value, 0)

    # Detect already-mounted RAW media before cinepi-raw is launched so the
    # recorder starts with the filesystem-specific storage profile.
    ssd_monitor.refresh()
    
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
        auto_enabled=auto_storage_preroll_enabled(settings),
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

    if restart_camera_after_startup_handoff and not defer_startup_message_until_after_plymouth:
        wait_for_plymouth_to_quit()

    if defer_startup_message_until_after_plymouth:
        wait_for_plymouth_to_quit()
        logging.info("Showing startup message after Plymouth handoff")
        fb_splash = graphic_splash(welcome_text, welcome_image)
        if fb_splash is None:
            splash_thread, splash_stop = start_splash(welcome_text)
        splash_visible_started_at = time.monotonic()
        remaining_splash_time = STARTUP_MESSAGE_MIN_DURATION - (time.monotonic() - splash_visible_started_at)
        if remaining_splash_time > 0:
            time.sleep(remaining_splash_time)

    # Stop any text-based splash. Keep the framebuffer welcome message visible
    # until the GUI paints over it so the handoff stays seamless.
    if splash_stop:
        splash_stop.set()
        splash_thread.join()
        claim_console_for_framebuffer()

    if restart_camera_after_startup_handoff:
        logging.info("Restarting cinepi-raw after startup handoff so preview binds above Cinemate")
        cinepi_controller.restart_camera(preview_enabled=True)

    settings_cfg = settings.get("settings", {})
    redis_listener = RedisListener(
        redis_controller,
        ssd_monitor,
        live_sync_warning_tolerance_frames=settings_cfg.get("live_sync_warning_tolerance_frames", 5),
        live_sync_startup_guard_frames=settings_cfg.get("live_sync_startup_guard_frames", 10),
        final_sync_analysis_tolerance_frames=settings_cfg.get("final_sync_analysis_tolerance_frames", 1),
        tc_drop_jitter_tolerance_frames=settings_cfg.get("tc_drop_jitter_tolerance_frames", 1),
    )
    redis_listener.set_recording_stop_callback(cinepi_controller.stop_recording)
    cinepi_controller.attach_redis_listener(redis_listener)
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
        stream = threading.Thread(target=socketio.run, args=(app,), kwargs={'host': '0.0.0.0', 'port': 5000, 'allow_unsafe_werkzeug': True})
        stream.start()
        logging.info("Stream module loaded")
    else:
        logging.error("No network connection found. Stream module not loaded")

    mediator = Mediator(cinepi, cinepi_controller, redis_listener, redis_controller, ssd_monitor, gpio_output, stream, usb_monitor)

    # Wait until the welcome-message/Plymouth handoff and preview rebind are
    # finished before warming the storage media.
    storage_preroll.mark_startup_ready()
    mark_runtime_ready("Cinemate running")
    
    # Ensure system cleanup on exit
    cleanup_called = False

    # Ensure system cleanup on exit
    def cleanup():
        nonlocal cleanup_called
        if cleanup_called:
            return
        cleanup_called = True
        logging.info("Shutting down components...")
        shutdown_in_progress = system_shutdown_in_progress()
        join_timeout = 0.25 if not shutdown_in_progress else 2.0
        if shutdown_in_progress:
            logging.info("System shutdown detected; skipping CLI handoff on tty1")

        def join_thread(thread, name, timeout=join_timeout):
            if not thread:
                return True
            thread.join(timeout=timeout)
            if thread.is_alive():
                logging.warning("%s did not stop within %.1fs", name, timeout)
                return False
            return True

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
        gui_stopped = False
        if simple_gui:
            gui_stopped = simple_gui.stop(
                clear_framebuffer=shutdown_in_progress,
                release_console=not shutdown_in_progress,
                join_timeout=join_timeout,
                teardown_before_join=not shutdown_in_progress,
            )
        if not shutdown_in_progress:
            restore_local_console_prompt()
        join_thread(dmesg_monitor, "DmesgMonitor")
        join_thread(command_executor, "CommandExecutor")
        if hasattr(cinepi, "shutdown"):
            cinepi.shutdown()
        if hasattr(serial_handler, "stop"):
            serial_handler.stop()
        else:
            serial_handler.running = False
        join_thread(serial_handler, "SerialHandler")

        if i2c_oled:
            if hasattr(i2c_oled, "stop"):
                i2c_oled.stop()
            join_thread(i2c_oled, "I2cOled")
        if quad_rotary:
            if hasattr(quad_rotary, "stop"):
                quad_rotary.stop()
            join_thread(quad_rotary, "QuadRotaryController")

        if fb_splash:
            if not shutdown_in_progress:
                blank_framebuffer(fb_splash)
        elif splash_stop:
            splash_stop.set()
            splash_thread.join()
            
        if timekeeper and hasattr(timekeeper, "stop"):
            timekeeper.stop()

        if not shutdown_in_progress and not gui_stopped:
            release_console_to_text()
        
    atexit.register(cleanup)
    
    def handle_exit(sig, frame):
        logging.info("Graceful shutdown initiated.")
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        cleanup()                 # stop your threads, join them if you like
        os.kill(os.getpid(), sig)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)


    from signal import pause
    pause()
    return 0


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the CinePi application.")
    parser.add_argument("-debug", action="store_true", help="Enable debug logging level.")
    args = parser.parse_args()

    _, log_queue = setup_logging(args.debug)
    _acquire_run_lock()
    clear_persisted_startup_failure()

    try:
        return run_application(args, log_queue)
    except SettingsLoadError as exc:
        systemd_status("Cinemate startup failed: invalid settings.json")
        logging.error("Cinemate startup aborted: %s", exc.detail)
        report_startup_failure("Cinemate could not start", exc.format_for_cli())
        return 1
    except Exception as exc:
        systemd_status("Cinemate startup failed before ready")
        logging.exception("Cinemate crashed during startup")
        report_startup_failure(
            "Cinemate crashed during startup",
            "\n".join(
                [
                    "Problem: Cinemate exited before the GUI finished starting.",
                    f"Reason: {exc.__class__.__name__}: {exc}",
                    "",
                    "Recommended fix: Review the startup sequence below, then retry from SSH if you need the full traceback in the shell.",
                ]
            ),
            log_lines=get_recent_log_lines(log_queue),
        )
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
