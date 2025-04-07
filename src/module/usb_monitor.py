import pyudev
import logging
import traceback
import threading
import re
import json
import subprocess
import time

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
        self.vu_thread = None
        self.vu_process = None


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

import subprocess
import threading
import re
import time
import logging

class AudioMonitor:
    def __init__(self):
        self.level_left = 0
        self.level_right = 0
        self.proc = None
        self.thread = None
        self.running = False

    def detect_device(self):
        try:
            output = subprocess.check_output(['arecord', '-l']).decode()
            match = re.search(r'card (\d+):\s+[^\[]+\[([^\]]+)\].*?device (\d+):', output, re.DOTALL)
            if match:
                card = match.group(1)
                name = match.group(2)
                device = match.group(3)
                logging.info(f"Found device: card {card}, device {device} — {name}")
                return card, device, name
        except Exception as e:
            logging.error(f"Failed to detect audio device: {e}")
        return None, None, None  # <— this ensures 3 values are always returned

    def try_format(self, card, device, fmt, channels, rate):
        try:
            subprocess.check_output([
                'arecord', '-D', f'hw:{card},{device}',
                '--format', fmt,
                '--channels', str(channels),
                '--rate', str(rate),
                '-d', '1', '-f', fmt, '-t', 'raw'
            ], stderr=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError:
            return False

    def find_working_config(self, card, device):
        test_configs = [
            ("S24_3LE", 2, 48000),
            ("S16_LE", 2, 48000),
            ("S16_LE", 1, 48000),
            ("S16_LE", 1, 44100),
        ]
        for fmt, ch, rate in test_configs:
            if self.try_format(card, device, fmt, ch, rate):
                logging.info(f"✔ Found working config: format={fmt}, channels={ch}, rate={rate}")
                return fmt, ch, rate
        return None, None, None

    def start(self):
        if self.running:
            return

        card, device, name = self.detect_device()
        if not card:
            logging.warning("No audio device found.")
            return

        fmt, channels, rate = self.find_working_config(card, device)
        if not fmt:
            logging.error("No compatible audio format found.")
            return

        logging.info(f"Starting VU monitor for mic '{name}' using format {fmt}, {channels} channel(s) at {rate} Hz")

        cmd = [
            'arecord',
            '-D', f'hw:{card},{device}',
            '--format', fmt,
            '--channels', str(channels),
            '--rate', str(rate),
            '-V', 'stereo',
            '-f', fmt,
            '-t', 'raw'
        ]
        logging.info(f"Running: {' '.join(cmd)}")

        self.running = True

        def vu_loop():
            try:
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
                for line in self.proc.stderr:
                    if not self.running:
                        break
                    line = line.strip()
                    vu = re.findall(r'(\d+)%', line)
                    if vu:
                        self.level_left = int(vu[0])
                        self.level_right = int(vu[1]) if len(vu) > 1 else self.level_left
                        #logging.info(f"Mic VU: L={self.level_left}% R={self.level_right}%")
                    if self.proc.poll() is not None:
                        break
                    time.sleep(0.05)
            except Exception as e:
                logging.error(f"Audio VU monitor error: {e}")
            finally:
                self.proc = None
                self.level_left = 0
                self.level_right = 0
                self.running = False

        self.thread = threading.Thread(target=vu_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=1)
            except Exception as e:
                logging.warning(f"Failed to stop audio monitor: {e}")
        self.proc = None
        self.level_left = 0
        self.level_right = 0

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

    def process_sound_devices(self):
        if not self.temp_sound_devices:
            self.sound_timer = None
            return

        if self.usb_mic and 'card' in self.usb_mic.device_path:
            self.temp_sound_devices.clear()
            return

        card_device = next((device for device in self.temp_sound_devices if 'card' in device.device_path), None)
        chosen_device = card_device if card_device else self.temp_sound_devices[0]

        self.usb_mic = chosen_device
        self.usb_mic_path = chosen_device.device_path

        raw_model = chosen_device.get('ID_MODEL', '')
        serial = chosen_device.get('ID_SERIAL', 'Unknown')

        # Normalize model (replace _ with space)
        model = raw_model.replace('_', ' ').strip()

        # Get card name and start audio monitor
        card_match = re.search(r'card(\d+)', chosen_device.device_path)
        if card_match:
            card_num = card_match.group(1)
            card_name = self.get_card_name_from_arecord(card_num).strip()
            self.audio_monitor.start()
        else:
            card_name = model if model else "Unknown"
            logging.warning("Could not determine card number, audio monitor not started.")
            device_string = None

        # Prefer the card_name if it looks more descriptive
        if card_name and card_name != "Unknown" and (not model or card_name.lower() not in model.lower()):
            model = card_name

        # Save fallback info
        self.last_mic_model = model
        self.last_mic_serial = serial

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
                self.card_device_found = False
                self.usb_event.emit(action, device, model, serial)
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
            logging.info(f'USB Microphone connected at init: Model={model}, Serial={serial}')
            self.usb_event.emit('add', device, model, serial)

            # ✅ Start audio monitor for already-connected mic
            self.audio_monitor.start()

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

    def start_vu_monitor(self, device_string="hw:0,0"):
        def monitor():
            try:
                cmd = [
                    "arecord",
                    "-D", device_string,
                    "--format=S24_3LE",
                    "--channels=2",
                    "--rate=48000",
                    "-V", "mono",
                    "-t", "raw",
                    "-f", "S24_3LE"
                ]
                self.vu_process = subprocess.Popen(
                    cmd,
                    stderr=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )

                for line in self.vu_process.stderr:
                    match = re.search(r"\[(\d+)%\]", line)
                    if match:
                        self.usb_mic_level = int(match.group(1))
                    if self.vu_process.poll() is not None:
                        break
                    time.sleep(0.05)
            except Exception as e:
                logging.error(f"VU monitor error: {e}")
            finally:
                self.usb_mic_level = 0
                self.vu_process = None

        self.vu_thread = threading.Thread(target=monitor, daemon=True)
        self.vu_thread.start()

    def stop_vu_monitor(self):
        if self.vu_process:
            try:
                self.vu_process.terminate()
                self.vu_process.wait(timeout=1)
            except Exception as e:
                logging.warning(f"Error stopping VU process: {e}")
        self.vu_process = None
        self.vu_thread = None
        self.usb_mic_level = 0



    def monitor_devices(self):
        observer = pyudev.MonitorObserver(self.monitor, self.device_event)
        observer.start()