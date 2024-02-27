import logging
import evdev
import threading

class Keyboard:
    def __init__(self, controller, usb_monitor):
        self.controller = controller
        self.usb_monitor = usb_monitor
        self.device = None
        self.listener_running = threading.Event()
        self.listener_thread = None

        # Subscribe to USBMonitor events
        self.usb_monitor.usb_event.subscribe(self.handle_usb_event)

        # Check if a keyboard device is already connected at startup
        self.device = self.find_keyboard_device()
        if self.device:
            self.start_listener()

    def find_keyboard_device(self):
        devices = [evdev.InputDevice(fn) for fn in evdev.list_devices()]
        for device in devices:
            if 'KEYBOARD' in device.name.upper():
                return device
        return None

    def handle_keyboard_event(self, event):
        if event.type == evdev.ecodes.EV_KEY:
            key_code = event.code
            if key_code in self.key_callbacks:
                action, log_message = self.key_callbacks[key_code]
                action()
                logging.info(log_message)

    def listen_for_keys(self):
        if not self.device:
            logging.info("No keyboard found.")
            return

        self.listener_running.set()
        logging.info(f"Listening to keyboard: {self.device.name}")
        while self.listener_running.is_set():
            try:
                for event in self.device.read_loop():
                    if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                        self.handle_keyboard_event(event)
            except OSError:
                # If the device is disconnected, this exception will be caught.
                logging.error("Device disconnected unexpectedly.")
                break

    def start_listener(self):
        if not self.listener_running.is_set():
            self.setup_callbacks()
            self.listener_thread = threading.Thread(target=self.listen_for_keys)
            self.listener_thread.start()

    def stop_listener(self):
        self.listener_running.clear()
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_thread.join()

    def setup_callbacks(self):
        self.key_callbacks = {
            evdev.ecodes.KEY_1: (self.controller.dec_iso, "1 - dec_iso triggered"),
            evdev.ecodes.KEY_2: (self.controller.inc_iso, "2 - inc_iso triggered"),
            evdev.ecodes.KEY_3: (self.controller.dec_shutter_a, "3 - dec_shutter_a triggered"),
            evdev.ecodes.KEY_4: (self.controller.inc_shutter_a, "4 - inc_shutter_a triggered"),
            evdev.ecodes.KEY_5: (self.controller.dec_fps, "5 - dec_fps triggered"),
            evdev.ecodes.KEY_6: (self.controller.inc_fps, "6 - inc_fps triggered"),
            evdev.ecodes.KEY_8: (self.controller.switch_resolution, "8 - switch_resolution triggered"),
            evdev.ecodes.KEY_9: (self.controller.unmount_drive, "9 - unmount_drive triggered"),
            evdev.ecodes.KEY_0: (self.controller.rec_button_pushed, "0 - rec_button_pushed triggered"),
        }

    def handle_zero_key(self):
        # Implement your '0' key handling logic here
        pass

    def handle_usb_event(self, action, device, model, serial):
        if action == 'add' and 'KEYBOARD' in model.upper():
            self.device = self.find_keyboard_device()  # This line is updated to re-initialize the device.
            if self.device:
                self.start_listener()
        elif action == 'remove' and 'KEYBOARD' in model.upper():
            self.stop_listener()
            self.device = None  # Set device to None after stopping the listener