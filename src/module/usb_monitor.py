import pyudev
import logging
import traceback
import threading
import re

import subprocess
import time

from collections import deque

class AudioMonitor:
    def __init__(self):
        ...
        self.vu_history = deque(maxlen=5)  # ~0.2s if updates ~25ms apart


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
        self.format = None
        self.channels = None
        self.sample_rate = None
        self.bit_depth = None
        self.device_name = None
        self.card = None
        self.device = None
        self.device_alias = None
        self.model = None
        self.serial = None
        self.vu_levels = []
        self.running = False
        self.thread = None
        self.vu_history = deque(maxlen=5)  # ~0.2s if updates ~25ms apart


    def set_model_info(self, model, serial):
        self.model = model.strip().lower() if model else "unknown"
        self.serial = serial

    def detect_device(self):
        try:
            output = subprocess.check_output("arecord -l", shell=True).decode()
            match = re.search(r'card (\d+):.*?device (\d+):.*?\[(.*?)\]', output, re.DOTALL)
            if match:
                self.card, self.device, self.device_name = match.groups()

                # Hardcoded handling for known models
                model_lc = self.model.lower()
                if "videomic" in model_lc or "rode" in model_lc:
                    self.device_alias = "mic_24bit"
                    self.format = "S24_3LE"
                    self.channels = 2
                    self.sample_rate = 48000
                    logging.info("Hardcoded config for RØDE VideoMic NTG → mic_24bit")
                    return True
                elif "pnp" in model_lc or "c-media" in model_lc:
                    self.device_alias = "mic_16bit"
                    self.format = "S16_LE"
                    self.channels = 1
                    self.sample_rate = 48000
                    logging.info("Hardcoded config for USB PnP mic → mic_16bit")
                    return True

                # Derive bit depth from format
                if self.format == "S24_3LE":
                    self.bit_depth = 24
                elif self.format == "S16_LE":
                    self.bit_depth = 16
                else:
                    self.bit_depth = None

                logging.warning("No hardcoded match for model '%s', skipping detection.", self.model)
                return False
        except subprocess.CalledProcessError:
            logging.exception("arecord failed during detection.")
            return False

    def try_audio_config(self, fmt, channels, rate):
        cmd = [
            'arecord', '-D', f'{self.device_alias}',
            '--format', fmt, '--channels', str(channels), '--rate', str(rate),
            '-d', '1', '-t', 'raw', '/dev/null'
        ]
        try:
            subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError:
            return False

    def vu_monitor_loop(self):
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

                    logging.info(f"VU Levels: {self.vu_levels}")
                    
                else:
                    logging.debug("No VU matches in this line.")

        finally:
            process.terminate()

    def start(self):
        if self.running:
            return False
        if not self.detect_device():
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
        
        threading.Timer(3.0, lambda: (self.audio_monitor.set_model_info(model, serial), self.audio_monitor.start())).start()

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
            self.audio_monitor.stop()
            self.audio_monitor = AudioMonitor()
            self.audio_monitor.set_model_info(model, serial)

            # started = self.audio_monitor.start()

            # if started:
            #     logging.info("Audio monitor restarted for new mic.")
            # else:
            #     logging.error("Audio monitor failed to restart for new mic.")

            # if trigger_event:
            #     self.usb_event.emit('mic_changed', chosen_device, model, serial, card_name)
            
            self.current_mic_id = mic_id

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

    def monitor_devices(self):
        observer = pyudev.MonitorObserver(self.monitor, self.device_event)
        observer.start()
