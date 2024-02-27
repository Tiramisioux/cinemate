import pyudev
import logging
import traceback
import threading
import re

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


class USBMonitor():
    def __init__(self, ssd_monitor):
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        
        self.ssd_monitor = ssd_monitor
        
        self.temp_sound_devices = []
        self.sound_timer = None
        self.mic_processed = False

        self.card_device_found = False  # Add this line to the initializer
        # Filter for sound devices specifically
        self.monitor.filter_by(subsystem='sound')
        
        self.monitor.filter_by(subsystem='usb')
        self.usb_mic = None
        self.usb_mic_path = None
        self.usb_keyboard = None
        self.usb_hd = None
        self.keyboard_handler = None
        self.usb_event = Event()
        
        # List to store details of currently connected USB devices
        self.connected_devices = []
        
        self.recently_processed = []
        
        # Add filter for USB storage devices
        self.monitor.filter_by(subsystem='usb_storage')

        # Start monitoring for new device events
        self.monitor_devices()
        

        
    def filter_sound_device(self, devices_list):
        """
        Filters sound devices and returns the most relevant device path.
        """
        sound_devices = [dev[0].device_path for dev in devices_list if re.search(r'/sound/card\d+', dev[0].device_path)]

        for s_dev in sound_devices:
            for other_dev in sound_devices:
                if s_dev != other_dev and s_dev in other_dev:
                    return s_dev
        return None
        
    def process_sound_devices(self):
        # If there are no sound devices, there's nothing to do
        if not self.temp_sound_devices:
            self.sound_timer = None
            return

        # If the usb_mic already has a path with "card" in it, just clear the temp list and return
        if self.usb_mic and 'card' in self.usb_mic.device_path:
            self.temp_sound_devices.clear()
            return

        # Find a device path that contains the word "card"
        card_device = next((device for device in self.temp_sound_devices if 'card' in device.device_path), None)

        if card_device:
            chosen_device = card_device
        else:
            # If no device with 'card' is found, then default to the first device
            chosen_device = self.temp_sound_devices[0]

        self.usb_mic = chosen_device
        self.usb_mic_path = chosen_device.device_path

        logging.info(f'USB Microphone connected')
        logging.info(f'usb_mic: {self.usb_mic}')

        # Clear the list and timer for future use
        self.temp_sound_devices.clear()
        self.sound_timer = None

    def reset_mic_processed_flag(self):
        self.mic_processed = False

    def device_event(self, action, device):
        # Print debugging information
        logging.debug(f"Action: {action}, Device Path: {device.device_path}, Model: {device.get('ID_MODEL', '')}, Serial: {device.get('ID_SERIAL', '')}")

        # Safely fetch model, serial, vendor_id, and product_id
        model = device.get('ID_MODEL', '')
        serial = device.get('ID_SERIAL', '')
        vendor_id = device.get('ID_VENDOR_ID', None)
        product_id = device.get('ID_MODEL_ID', None)
        model_upper = model.upper()

        # Use device's unique device path as an identifier
        device_id = device.device_path

        logging.debug(f"Searching for device with path {device_id} in connected_devices")

        # Find an entry in connected_devices by matching device_id
        matching_entry = next((entry for entry in self.connected_devices if entry[0].device_path == device_id), None)

        if action == 'add':
            if device in self.recently_processed:
                return
            self.recently_processed.append(device)
            threading.Timer(5.0, self.recently_processed.remove, args=[device]).start()

            if not matching_entry:
                device_data = [device, model, serial]
                self.connected_devices.append(device_data)

            if 'USB_PNP_SOUND_DEVICE' in model_upper:
                # If a mic was processed recently, don't process again
                if self.mic_processed:
                    return
                self.mic_processed = True
                threading.Timer(10.0, self.reset_mic_processed_flag).start()  # Reset after 10 seconds
                self.temp_sound_devices.append(device)
                if self.sound_timer is None:
                    self.sound_timer = threading.Timer(5.0, self.process_sound_devices)
                    self.sound_timer.start()

                if self.usb_mic_path:
                    self.usb_mic = device
                    logging.info(f'USB Microphone connected')
                    logging.info(f'usb_mic: {self.usb_mic}')
                else:
                    # It's the shorter path, search for the longer path
                    for sound_device in self.context.list_devices(subsystem='sound'):
                        if sound_device.device_path.startswith(device.device_path):
                            self.usb_mic = sound_device
                            self.usb_mic_path = sound_device.device_path
                            logging.info(f'USB Microphone connected')
                            self.usb_event.emit(action, sound_device, model, serial)
                            #logging.info(f'usb_mic: {self.usb_mic}')
                            break

            elif 'KEYBOARD' in model_upper:
                self.usb_keyboard = device
                logging.info(f'USB Keyboard connected')
                self.usb_event.emit(action, device, model, serial)

            #elif self.is_ssd_drive(device):
            elif 'SSD' in model_upper:
                self.usb_hd = device
                logging.info(f'USB SSD connected')
                self.usb_event.emit('add', device, model, serial)

        elif action == 'remove':
            if matching_entry:
                # Extract the model and serial from the stored data
                _, model, serial = matching_entry
                self.connected_devices.remove(matching_entry)
            else:
                logging.warning(f"No stored information for device at {device_id}. Using available data.")

            if self.usb_mic_path is not None and device.device_path.startswith(self.usb_mic_path):
                self.usb_mic = None  # <-- Also reset the usb_mic to None
                self.usb_mic_path = None
                self.card_device_found = False
                logging.info(f'USB Microphone disconnected')
                self.usb_event.emit(action, device, model, serial)
                logging.info(f'usb_mic: {self.usb_mic}')

            elif self.usb_keyboard and self.usb_keyboard == device:
                self.usb_keyboard = None
                logging.info(f'USB Keyboard disconnected')
                self.usb_event.emit(action, device, model, serial)

            elif self.usb_hd and self.usb_hd == device:
                self.usb_hd = None
                logging.info(f'USB SSD disconnected')
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

            if 'USB_PNP_SOUND_DEVICE' in model_upper:
                usb_detected_mics.add(device.device_path)
                self.usb_event.emit('add', device, model, serial)
                #logging.info(f'usb_mic: {self.usb_mic}')

            elif 'KEYBOARD' in model_upper:
                self.usb_keyboard = device
                logging.info(f'USB Keyboard connected')
                self.usb_event.emit('add', device, model, serial)

            elif 'SSD' in model_upper:
                self.usb_hd = device
                logging.info(f'USB SSD connected')
                self.usb_event.emit('add', device, model, serial)


        for device in self.context.list_devices(subsystem='sound'):
            general_path = device.device_path.split('/sound/')[0]
            
            if general_path in usb_detected_mics:
                continue  # Skip processing if already detected in the 'usb' loop

            model = device.get('ID_MODEL', '')
            serial = device.get('ID_SERIAL', '')
            device_data = [device, model, serial]
            self.connected_devices.append(device_data)
            logging.debug(f"Adding sound device to connected_devices with Path: {device.device_path}, Model: {model}, Serial: {serial}")
            
            if 'USB_PNP_SOUND_DEVICE' in model.upper():
                # if not already detected in the usb loop
                if 'controlC' not in device.device_path:
                    self.usb_mic = device
                    self.usb_mic_path = device.device_path
                    logging.info(f'USB Microphone connected')  # This is the place where the log is created
                    self.usb_event.emit('add', device, model, serial)
                    #logging.info(f'usb_mic: {self.usb_mic}')
                

    def monitor_devices(self):
        observer = pyudev.MonitorObserver(self.monitor, self.device_event)
        observer.start()



# import pyudev
# import logging
# import traceback
# import threading
# import re

# class Event:
#     def __init__(self):
#         self._listeners = []

#     def subscribe(self, listener):
#         self._listeners.append(listener)

#     def emit(self, *args):
#         for listener in self._listeners:
#             try:
#                 listener(*args)
#             except Exception as e:
#                 logging.error(f"Error while invoking listener: {e}")
#                 traceback.print_exc()  # Print the traceback for better debugging

# class Event:
#     def __init__(self):
#         self._listeners = []

#     def subscribe(self, listener):
#         self._listeners.append(listener)

#     def emit(self, *args):
#         for listener in self._listeners:
#             try:
#                 listener(*args)
#             except Exception as e:
#                 logging.error(f"Error while invoking listener: {e}")


# class USBMonitor():
#     def __init__(self):
#         self.context = pyudev.Context()
#         self.monitor = pyudev.Monitor.from_netlink(self.context)
        
        
#         self.temp_sound_devices = []
#         self.sound_timer = None
#         self.mic_processed = False

#         self.card_device_found = False  # Add this line to the initializer
#         # Filter for sound devices specifically
#         self.monitor.filter_by(subsystem='sound')
        
#         self.monitor.filter_by(subsystem='usb')
#         self.usb_mic = None
#         self.usb_mic_path = None
#         self.usb_keyboard = None
#         self.usb_hd = None
#         self.keyboard_handler = None
#         self.usb_event = Event()
        
#         # List to store details of currently connected USB devices
#         self.connected_devices = []
        
#         self.recently_processed = []
        
#         # Add filter for USB storage devices
#         self.monitor.filter_by(subsystem='usb_storage')

#         # Start monitoring for new device events
#         self.monitor_devices()
        

        
#     def filter_sound_device(self, devices_list):
#         """
#         Filters sound devices and returns the most relevant device path.
#         """
#         sound_devices = [dev[0].device_path for dev in devices_list if re.search(r'/sound/card\d+', dev[0].device_path)]

#         for s_dev in sound_devices:
#             for other_dev in sound_devices:
#                 if s_dev != other_dev and s_dev in other_dev:
#                     return s_dev
#         return None
        
#     def process_sound_devices(self):
#         # If there are no sound devices, there's nothing to do
#         if not self.temp_sound_devices:
#             self.sound_timer = None
#             return

#         # If the usb_mic already has a path with "card" in it, just clear the temp list and return
#         if self.usb_mic and 'card' in self.usb_mic.device_path:
#             self.temp_sound_devices.clear()
#             return

#         # Find a device path that contains the word "card"
#         card_device = next((device for device in self.temp_sound_devices if 'card' in device.device_path), None)

#         if card_device:
#             chosen_device = card_device
#         else:
#             # If no device with 'card' is found, then default to the first device
#             chosen_device = self.temp_sound_devices[0]

#         self.usb_mic = chosen_device
#         self.usb_mic_path = chosen_device.device_path

#         logging.info(f'USB Microphone connected')
#         logging.info(f'usb_mic: {self.usb_mic}')

#         # Clear the list and timer for future use
#         self.temp_sound_devices.clear()
#         self.sound_timer = None

#     def reset_mic_processed_flag(self):
#         self.mic_processed = False

#     def device_event(self, action, device):
#         # Print debugging information
#         logging.debug(f"Action: {action}, Device Path: {device.device_path}, Model: {device.get('ID_MODEL', '')}, Serial: {device.get('ID_SERIAL', '')}")

#         # Safely fetch model, serial, vendor_id, and product_id
#         model = device.get('ID_MODEL', '')
#         serial = device.get('ID_SERIAL', '')
#         vendor_id = device.get('ID_VENDOR_ID', None)
#         product_id = device.get('ID_MODEL_ID', None)
#         model_upper = model.upper()

#         # Use device's unique device path as an identifier
#         device_id = device.device_path

#         logging.debug(f"Searching for device with path {device_id} in connected_devices")

#         # Find an entry in connected_devices by matching device_id
#         matching_entry = next((entry for entry in self.connected_devices if entry[0].device_path == device_id), None)

#         if action == 'add':
#             if device in self.recently_processed:
#                 return
#             self.recently_processed.append(device)
#             threading.Timer(5.0, self.recently_processed.remove, args=[device]).start()

#             if not matching_entry:
#                 device_data = [device, model, serial]
#                 self.connected_devices.append(device_data)

#             if 'USB_PNP_SOUND_DEVICE' in model_upper:
#                 # If a mic was processed recently, don't process again
#                 if self.mic_processed:
#                     return
#                 self.mic_processed = True
#                 threading.Timer(10.0, self.reset_mic_processed_flag).start()  # Reset after 10 seconds
#                 self.temp_sound_devices.append(device)
#                 if self.sound_timer is None:
#                     self.sound_timer = threading.Timer(5.0, self.process_sound_devices)
#                     self.sound_timer.start()

#                 if self.usb_mic_path:
#                     self.usb_mic = device
#                     logging.info(f'USB Microphone connected')
#                     logging.info(f'usb_mic: {self.usb_mic}')
#                 else:
#                     # It's the shorter path, search for the longer path
#                     for sound_device in self.context.list_devices(subsystem='sound'):
#                         if sound_device.device_path.startswith(device.device_path):
#                             self.usb_mic = sound_device
#                             self.usb_mic_path = sound_device.device_path
#                             logging.info(f'USB Microphone connected')
#                             self.usb_event.emit(action, sound_device, model, serial)
#                             #logging.info(f'usb_mic: {self.usb_mic}')
#                             break

#             elif 'KEYBOARD' in model_upper:
#                 self.usb_keyboard = device
#                 logging.info(f'USB Keyboard connected')
#                 self.usb_event.emit(action, device, model, serial)

#             #elif self.is_ssd_drive(device):
#             elif 'SSD' in model_upper:
#                 self.usb_hd = device
#                 logging.info(f'USB SSD connected')
#                 self.usb_event.emit('add', device, model, serial)

#         elif action == 'remove':
#             if matching_entry:
#                 # Extract the model and serial from the stored data
#                 _, model, serial = matching_entry
#                 self.connected_devices.remove(matching_entry)
#             else:
#                 logging.warning(f"No stored information for device at {device_id}. Using available data.")

#             if self.usb_mic_path is not None and device.device_path.startswith(self.usb_mic_path):
#                 self.usb_mic = None  # <-- Also reset the usb_mic to None
#                 self.usb_mic_path = None
#                 self.card_device_found = False
#                 logging.info(f'USB Microphone disconnected')
#                 self.usb_event.emit(action, device, model, serial)
#                 logging.info(f'usb_mic: {self.usb_mic}')

#             elif self.usb_keyboard and self.usb_keyboard == device:
#                 self.usb_keyboard = None
#                 logging.info(f'USB Keyboard disconnected')
#                 self.usb_event.emit(action, device, model, serial)

#             elif self.usb_hd and self.usb_hd == device:
#                 self.usb_hd = None
#                 logging.info(f'USB SSD disconnected')
#                 self.usb_event.emit(action, device, model, serial)

#     def check_initial_devices(self):
#         usb_detected_mics = set()

#         for device in self.context.list_devices(subsystem='usb'):
#             model = device.get('ID_MODEL', '')
#             serial = device.get('ID_SERIAL', '')
#             device_data = [device, model, serial]
#             self.connected_devices.append(device_data)
#             logging.debug(f"Adding device to connected_devices with Path: {device.device_path}, Model: {model}, Serial: {serial}")

#             model_upper = model.upper()

#             if 'USB_PNP_SOUND_DEVICE' in model_upper:
#                 usb_detected_mics.add(device.device_path)
#                 self.usb_event.emit('add', device, model, serial)
#                 #logging.info(f'usb_mic: {self.usb_mic}')

#             elif 'KEYBOARD' in model_upper:
#                 self.usb_keyboard = device
#                 logging.info(f'USB Keyboard connected')
#                 self.usb_event.emit('add', device, model, serial)

#             elif 'SSD' in model_upper:
#                 self.usb_hd = device
#                 logging.info(f'USB SSD connected')
#                 self.usb_event.emit('add', device, model, serial)


#         for device in self.context.list_devices(subsystem='sound'):
#             general_path = device.device_path.split('/sound/')[0]
            
#             if general_path in usb_detected_mics:
#                 continue  # Skip processing if already detected in the 'usb' loop

#             model = device.get('ID_MODEL', '')
#             serial = device.get('ID_SERIAL', '')
#             device_data = [device, model, serial]
#             self.connected_devices.append(device_data)
#             logging.debug(f"Adding sound device to connected_devices with Path: {device.device_path}, Model: {model}, Serial: {serial}")
            
#             if 'USB_PNP_SOUND_DEVICE' in model.upper():
#                 # if not already detected in the usb loop
#                 if 'controlC' not in device.device_path:
#                     self.usb_mic = device
#                     self.usb_mic_path = device.device_path
#                     logging.info(f'USB Microphone connected')  # This is the place where the log is created
#                     self.usb_event.emit('add', device, model, serial)
#                     #logging.info(f'usb_mic: {self.usb_mic}')
                

#     def monitor_devices(self):
#         observer = pyudev.MonitorObserver(self.monitor, self.device_event)
#         observer.start()
