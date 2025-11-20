import pyudev
import logging
import traceback
import threading
import re

import subprocess
import time
import shlex

from collections import deque
from typing import Optional


class Event:
    def __init__(self):
        self._listeners = []

    def subscribe(self, listener):
        self._listeners.append(listener)

    def emit(self, *args):
        for listener in self._listeners:
            try:
                listener(*args)
            except Exception as e:
                logging.error(f"Error while invoking listener: {e}")
                traceback.print_exc()  # Print the traceback for better debugging


class USBDriveMonitor:
    def __init__(self, ssd_monitor):
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem='block')
        self.ssd_monitor = ssd_monitor
        self.device_processing_lock = threading.Lock()
        self.processed_devices = {}  # Tracks devices and their last processed time
        
        self.usb_mic_level = 0
    

        self.check_mounted_devices_on_startup()  # Check for already mounted devices

    def is_usb_mounted_at(self, path):
        try:
            output = subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', path], stderr=subprocess.STDOUT).decode().strip()
            if '/dev/sd' in output:
                self.ssd_monitor.disk_mounted = True
                return True
        except subprocess.CalledProcessError:
            self.ssd_monitor.disk_mounted = False

        return False

    def device_key(self, device):
        return (device.get('ID_MODEL', 'Unknown'), device.get('ID_SERIAL_SHORT', 'Unknown'))

    def is_within_cooldown(self, device_key):
        current_time = time.time()
        with self.device_processing_lock:
            last_processed = self.processed_devices.get(device_key, 0)
            return current_time - last_processed < 5

    def mark_device_processed(self, device_key):
        with self.device_processing_lock:
            self.processed_devices[device_key] = time.time()

    def check_mounted_devices_on_startup(self):
        for device in self.context.list_devices(subsystem='block'):
            if self.is_usb_mounted_at('/media/RAW'):
                device_key = self.device_key(device)
                logging.info(f"SSD already mounted at startup: Model={device_key[0]}, Serial={device_key[1]}")
                self.ssd_monitor.update_on_add(device_key[0], device_key[1])
                break

    def start_monitoring(self):
        for device in iter(self.monitor.poll, None):
            device_key = self.device_key(device)

            if device.action == 'add':
                if self.is_within_cooldown(device_key):
                    logging.debug(f"Device {device_key} within cooldown period, skipping detection.")
                    continue

                self.mark_device_processed(device_key)
                logging.info(f"USB device connected: Model={device_key[0]}, Serial={device_key[1]}")

                for _ in range(10):
                    if self.is_usb_mounted_at('/media/RAW'):
                        self.ssd_monitor.update_on_add(device_key[0], device_key[1])
                        break
                    time.sleep(1)
            elif device.action == 'remove':
                self.ssd_monitor.update_on_remove("Detected USB disconnection.")
                self.ssd_monitor.on_ssd_removed()

class AudioMonitor:
    def __init__(self):
        self.format: Optional[str] = None
        self.channels: Optional[int] = None
        self.sample_rate: Optional[int] = None
        self.bit_depth: Optional[int] = None
        self.device_name: Optional[str] = None
        self.card: Optional[str] = None
        self.device: Optional[str] = None
        self.device_alias: Optional[str] = None
        self.model = None
        self.serial = None
        self.vu_levels = []
        self.running = False
        self.thread = None
        self.vu_history = deque(maxlen=10)
        self.audio_sample_rate = 48000
        self.can_record_audio = False

    def set_model_info(self, model, serial):
        self.model = model.strip().lower() if model else "unknown"
        self.serial = serial

    @staticmethod
    def run_with_stderr_capture(cmd: str) -> tuple[int, str]:
        """Run a shell command, merging stderr into stdout and return the exit code and first line."""
        logging.debug("Executing command with stderr capture: %s", cmd)
        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            logging.error("Failed to launch '%s': %s", cmd, exc)
            return -1, ""

        output, _ = process.communicate()
        rc = process.returncode if process.returncode is not None else -1
        first_line = output.splitlines()[0] if output else ""
        return rc, first_line

    def detect_recording_devices(self) -> bool:
        try:
            output = subprocess.check_output([
                "arecord", "-l"
            ], stderr=subprocess.DEVNULL, text=True)
        except FileNotFoundError:
            logging.error("arecord not found; cannot detect recording devices.")
            self.can_record_audio = False
            return False
        except subprocess.CalledProcessError:
            logging.exception("arecord failed during detection.")
            self.can_record_audio = False
            return False

        if "card " not in output:
            logging.error("No recording devices detected!")
            self.can_record_audio = False
        else:
            self.can_record_audio = True
        logging.debug("Audio device present: %s", "yes" if self.can_record_audio else "no")
        return self.can_record_audio

    def try_audio_config(self, device_alias: str, fmt: str, channels: int, rate: int) -> bool:
        cmd = (
            f"arecord -D {shlex.quote(device_alias)}"
            f" -f {fmt} -c {channels} -r {rate} -d 1 -t raw"
        )
        rc, first_line = self.run_with_stderr_capture(cmd)
        exit_code = rc if rc is not None else -1
        if exit_code == 0:
            logging.info(
                "Probe OK: %s (fmt %s, ch %s, %s Hz)",
                device_alias,
                fmt,
                channels,
                rate,
            )
            return True

        logging.debug(
            "Probe FAILED rc=%s : %s | %s",
            exit_code,
            cmd,
            first_line,
        )
        return False

    def parse_hardware_params(self) -> None:
        self.sample_rate = self.audio_sample_rate
        if self.try_audio_config("mic_24bit", "S24_3LE", 2, self.sample_rate):
            self.format = "S24_3LE"
            self.channels = 2
            self.device_alias = "mic_24bit"
            self.can_record_audio = True
            self.bit_depth = 24
            logging.info("parse_hardware_params(): using mic_24bit")
        elif self.try_audio_config("mic_16bit", "S16_LE", 1, self.sample_rate):
            self.format = "S16_LE"
            self.channels = 1
            self.device_alias = "mic_16bit"
            self.can_record_audio = True
            self.bit_depth = 16
            logging.info("parse_hardware_params(): using mic_16bit")
        else:
            for device_alias in self.find_hw_device_aliases():
                for channels in (1, 2):
                    if self.try_audio_config(device_alias, "S16_LE", channels, self.sample_rate):
                        self.format = "S16_LE"
                        self.channels = channels
                        self.device_alias = device_alias
                        self.can_record_audio = True
                        self.bit_depth = 16
                        logging.info(
                            "parse_hardware_params(): using fallback alias %s (%s ch)",
                            device_alias,
                            channels,
                        )
                        break
                if self.can_record_audio:
                    break

        if not self.can_record_audio:
            self.format = None
            self.device_alias = None
            self.channels = None
            self.sample_rate = None
            self.can_record_audio = False
            self.bit_depth = None
            logging.error("parse_hardware_params(): no usable mic_* alias found")

        if self.can_record_audio:
            self.publish_mic_selection()

    def publish_mic_selection(self) -> None:
        if not self.can_record_audio or not self.device_alias:
            return
        try:
            import redis  # type: ignore

            client = redis.StrictRedis(host="localhost", port=6379, db=0)
            client.mset({
                "MIC_PCM_ALIAS": self.device_alias,
                "MIC_FORMAT": self.format or "",
                "MIC_CHANNELS": str(self.channels or ""),
                "MIC_RATE": str(self.sample_rate or ""),
            })
            logging.debug("Published MIC_* to Redis")
        except ModuleNotFoundError:
            logging.debug("Redis module not available; skipping MIC_* publish.")
        except Exception as exc:  # pragma: no cover - redis optional
            logging.debug("Failed to publish MIC_* to Redis: %s", exc)

    def vu_monitor_loop(self):
        if not self.device_alias or not self.format or not self.channels or not self.sample_rate:
            logging.warning("VU monitor loop requested without a valid audio configuration.")
            return

        cmd = [
            'arecord', '-D', f'{self.device_alias}',
            '--format', self.format, '--channels', str(self.channels), '--rate', str(self.sample_rate),
            '-vvv', '/dev/null'
        ]

        self.vu_levels = []
        logging.info(f"Starting VU monitor: arecord -D {self.device_alias} -f {self.format} -c {self.channels} -r {self.sample_rate} -vvv /dev/null")

        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True)

        try:
            for line in process.stderr:
                if not self.running:
                    break

                logging.debug(f"[VU MONITOR] stderr: {line.strip()}")
                matches = re.findall(r'(\d+)%', line)
                if matches:
                    self.vu_levels = list(map(int, matches[:6]))
                    if len(self.vu_levels) == 1:
                        self.vu_levels *= 2
                    self.vu_history.append(self.vu_levels.copy())

                    logging.debug(f"VU Levels: {self.vu_levels}")
                    
                else:
                    logging.debug("No VU matches in this line.")

        finally:
            process.terminate()

    def start(self):
        if self.running:
            return False

        if not self.detect_recording_devices():
            logging.warning("AudioMonitor start aborted: no recording device present.")
            return False

        self.parse_hardware_params()
        if not self.can_record_audio:
            logging.warning("AudioMonitor start aborted: unable to determine usable mic alias.")
            return False

        self.running = True
        self.thread = threading.Thread(target=self.vu_monitor_loop, daemon=True)
        self.thread.start()
        logging.info("AudioMonitor started.")
        return True

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
            self.vu_levels = []
            logging.info("AudioMonitor stopped.")

    def get_vu_levels(self):
        return self.vu_levels[0], self.vu_levels[1] if len(self.vu_levels) >= 2 else 0

class USBMonitor():
    def __init__(self, ssd_monitor):
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)

        self.ssd_monitor = ssd_monitor

        self.temp_sound_devices = []
        self.sound_timer = None
        self.mic_processed = False

        self.card_device_found = False
        self.monitor.filter_by(subsystem='sound')
        self.monitor.filter_by(subsystem='usb')

        self.usb_mic = None
        self.usb_mic_path = None
        self.usb_keyboard = None
        self.usb_hd = None
        self.keyboard_handler = None
        self.usb_event = Event()

        self.connected_devices = []
        self.recently_processed = []
        
        self.current_mic_id = None
        
        self.audio_monitor = AudioMonitor()
        
        self.monitor.filter_by(subsystem='usb_storage')
        self.monitor_devices()

    def filter_sound_device(self, devices_list):
        sound_devices = [dev[0].device_path for dev in devices_list if re.search(r'/sound/card\\d+', dev[0].device_path)]

        for s_dev in sound_devices:
            for other_dev in sound_devices:
                if s_dev != other_dev and s_dev in other_dev:
                    return s_dev
        return None

    def process_sound_devices(self, trigger_event=True):

        if not self.temp_sound_devices:
            self.sound_timer = None
            return

        chosen_device = next(
            (device for device in self.temp_sound_devices if 'card' in device.device_path),
            self.temp_sound_devices[0]
        )

        self.usb_mic = chosen_device
        self.usb_mic_path = chosen_device.device_path

        raw_model = chosen_device.get('ID_MODEL', '') or "Unknown"
        serial = chosen_device.get('ID_SERIAL', '') or "Unknown"
        model = raw_model.replace('_', ' ').strip() or "Unknown"
        
        # Do not start here – we may replace audio_monitor below. Start only after finalising selection.

        # Always initialize to prevent UnboundLocalError
        card_name = "Unknown"
        card_match = re.search(r'card(\d+)', chosen_device.device_path)
        if card_match:
            card_num = card_match.group(1)
            card_name = self.get_card_name_from_arecord(card_num).strip()

        # Optional fallback: use card_name if model is empty/unknown
        if not model or model == "Unknown":
            model = card_name

        mic_id = f"{model}:{serial}"
        mic_has_changed = not self.current_mic_id or mic_id != self.current_mic_id

        if mic_has_changed:
            logging.info(f"Microphone changed from {self.current_mic_id} → {mic_id}")
            # Stop old monitor and create a fresh one bound to this mic
            try:
                self.audio_monitor.stop()
            except Exception:
                pass
            self.audio_monitor = AudioMonitor()
            self.audio_monitor.set_model_info(model, serial)
            self.current_mic_id = mic_id
            # Let ALSA settle briefly, then start the *current* monitor
            threading.Timer(0.5, self.audio_monitor.start).start()
            if trigger_event:
                self.usb_event.emit('mic_changed', chosen_device, model, serial, card_name)
        else:
            # First detection or unchanged mic: ensure monitor is running
            if not self.audio_monitor.running:
                self.audio_monitor.set_model_info(model, serial)
                threading.Timer(0.5, self.audio_monitor.start).start()

        logging.info(f'USB Microphone connected: Model={model}, Serial={serial}, Name={card_name}')
        self.usb_event.emit('add', chosen_device, model, serial, card_name)

        self.temp_sound_devices.clear()
        self.sound_timer = None


    def reset_mic_processed_flag(self):
        self.mic_processed = False

    def device_event(self, action, device):
        logging.debug(f"Action: {action}, Device Path: {device.device_path}, Model: {device.get('ID_MODEL', '')}, Serial: {device.get('ID_SERIAL', '')}")

        model = device.get('ID_MODEL', '')
        serial = device.get('ID_SERIAL', '')
        vendor_id = device.get('ID_VENDOR_ID', None)
        product_id = device.get('ID_MODEL_ID', None)
        model_upper = model.upper()
        device_id = device.device_path

        logging.debug(f"Searching for device with path {device_id} in connected_devices")

        matching_entry = next((entry for entry in self.connected_devices if entry[0].device_path == device_id), None)

        if action == 'add':
            if device in self.recently_processed:
                return
            self.recently_processed.append(device)
            threading.Timer(5.0, lambda: self.recently_processed.remove(device) if device in self.recently_processed else None).start()


            if not matching_entry:
                device_data = [device, model, serial]
                self.connected_devices.append(device_data)

            if 'SOUND' in device.subsystem.upper():
                if self.mic_processed:
                    return
                self.mic_processed = True
                threading.Timer(10.0, self.reset_mic_processed_flag).start()
                self.temp_sound_devices.append(device)
                if self.sound_timer is None:
                    self.sound_timer = threading.Timer(5.0, self.process_sound_devices)
                    self.sound_timer.start()

            elif 'KEYBOARD' in model_upper:
                self.usb_keyboard = device
                logging.info(f'USB Keyboard connected: Model={model}, Serial={serial}')
                self.usb_event.emit(action, device, model, serial)

        elif action == 'remove':
            if matching_entry:
                _, model, serial = matching_entry
                self.connected_devices.remove(matching_entry)
            else:
                model = device.get('ID_MODEL', 'Unknown')
                serial = device.get('ID_SERIAL', 'Unknown')

            if self.usb_mic_path and device.device_path.startswith(self.usb_mic_path):
                model = getattr(self, 'last_mic_model', 'Unknown')
                serial = getattr(self, 'last_mic_serial', 'Unknown')
                logging.info(f'USB Microphone disconnected: Model={model}, Serial={serial}')
                self.usb_mic = None
                self.usb_mic_path = None
                self.current_mic_id = None
                self.usb_event.emit('mic_removed', device, model, serial)  # <-- Added this line
                self.audio_monitor.stop()


            elif self.usb_keyboard and self.usb_keyboard == device:
                logging.info(f'USB Keyboard disconnected: Model={model}, Serial={serial}')
                self.usb_keyboard = None
                self.usb_event.emit(action, device, model, serial)

    def check_initial_devices(self):
        usb_detected_mics = set()

        for device in self.context.list_devices(subsystem='usb'):
            model = device.get('ID_MODEL', '')
            serial = device.get('ID_SERIAL', '')
            device_data = [device, model, serial]
            self.connected_devices.append(device_data)
            logging.debug(f"Adding device to connected_devices with Path: {device.device_path}, Model: {model}, Serial: {serial}")

            model_upper = model.upper()

            if 'SOUND' in device.subsystem.upper():
                usb_detected_mics.add(device.device_path)
                logging.info(f'USB Microphone connected at init: Model={model}, Serial={serial}')
                self.usb_event.emit('add', device, model, serial)

            elif 'KEYBOARD' in model_upper:
                self.usb_keyboard = device
                logging.info(f'USB Keyboard connected at init: Model={model}, Serial={serial}')
                self.usb_event.emit('add', device, model, serial)

        for device in self.context.list_devices(subsystem='sound'):
            general_path = device.device_path.split('/sound/')[0]

            if general_path in usb_detected_mics:
                continue

            model = device.get('ID_MODEL', '').replace('_', ' ').strip()
            serial = device.get('ID_SERIAL', '').strip()

            if not serial or 'controlC' in device.device_path or 'pcmC' in device.device_path:
                continue

            device_data = [device, model, serial]
            self.connected_devices.append(device_data)
            logging.debug(f"Adding sound device to connected_devices with Path: {device.device_path}, Model: {model}, Serial: {serial}")

            self.usb_mic = device
            self.usb_mic_path = device.device_path
            # logging.info(f'USB Microphone connected at init: Model={model}, Serial={serial}')
            self.usb_event.emit('add', device, model, serial)

            self.temp_sound_devices.append(device)

        if self.temp_sound_devices:
            logging.info("Processing pre-connected sound devices...")
            self.process_sound_devices(trigger_event=False)



    def get_card_name_from_arecord(self, card_num):
        try:
            output = subprocess.check_output(['arecord', '-l']).decode()
            pattern = rf"card {card_num}: [^\[]+\[(.+?)\]"
            match = re.search(pattern, output)
            if match:
                return match.group(1).strip()
        except Exception as e:
            logging.error(f"Failed to get card name from arecord: {e}")
        return "Unknown"

    def find_hw_device_aliases(self) -> list[str]:
        """Return ALSA device aliases derived from arecord -l output, prioritizing the current mic."""

        aliases: list[tuple[int, str]] = []
        try:
            output = subprocess.check_output(
                ["arecord", "-l"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except FileNotFoundError:
            logging.error("arecord not found; cannot inspect hardware devices.")
            return []
        except subprocess.CalledProcessError:
            logging.error("arecord -l failed while inspecting hardware devices.")
            return []

        pattern = re.compile(r"card (\d+): [^\[]+\[([^\]]+)\], device (\d+): [^\[]+\[([^\]]+)\]")
        for card_num, card_name, device_num, device_name in pattern.findall(output):
            alias = f"plughw:{card_num},{device_num}"
            score = 0
            card_name_lower = card_name.lower()
            device_name_lower = device_name.lower()

            if self.model and (self.model in card_name_lower or self.model in device_name_lower):
                score += 2
            if "usb" in card_name_lower or "usb" in device_name_lower:
                score += 1

            aliases.append((score, alias))

        aliases.sort(key=lambda entry: entry[0], reverse=True)
        return [alias for _, alias in aliases]

    def monitor_devices(self):
        observer = pyudev.MonitorObserver(self.monitor, self.device_event)
        observer.start()
