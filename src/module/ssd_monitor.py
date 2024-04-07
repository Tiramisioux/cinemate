import threading
import subprocess
import logging
import time
import os
import json
from inotify_simple import INotify, flags

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

class SSDMonitor():
    def __init__(self):
        self.active_watches = set()
        self.usb_hd = None
        self.usb_hd_serial = None  # Initialize the attribute
        self.path = '/media/RAW'
        self.disk_mounted = False

        self.last_space_left = None
        self.space_decreasing = False
        self.ssd_event = Event()
        self.space_decreasing_event = Event()
        self.space_was_decreasing = False
        self.space_stable_event = Event()
        self._ssd_thread_stop_event = threading.Event()
        
        self.unmount_event = Event()
        
        # Initialize new events
        self.write_status_changed_event = Event()
        self.new_file_created_event = Event()
        
        # Add an attribute to store the DirectoryWatcher instance
        self.directory_watcher = None
        
    def is_usb_mounted_at(self, path):
        try:
            output = subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', path], stderr=subprocess.STDOUT).decode().strip()
            if '/dev/sd' in output:
                self.disk_mounted = True
                return True
        except subprocess.CalledProcessError:
            self.disk_mounted = False
        
        return False
    
    def update_on_add(self, device_name, serial):
        if self.is_usb_mounted_at(self.path):
            logging.info(f"Device '{device_name}' with serial '{serial}' mounted as 'RAW'.")
            self.disk_mounted = True
            self.ssd_event.emit('add', self.path)
            self.on_ssd_added()
        else:
            logging.info(f"Device '{device_name}' with serial '{serial}' mounted as 'RAW'.")

    def update_on_remove(self, message):
        if not self.is_usb_mounted_at(self.path) and self.disk_mounted:
            logging.info("RAW USB drive unmounted: " + message)
            self.disk_mounted = False
            self.on_ssd_removed()
            self.unmount_event.emit()
            self.last_space_left = None
        
    def get_mount_point(self, device_path):
        """Get the mount point of the device if mounted, otherwise return None."""
        with open('/proc/mounts', 'r') as f:
            for line in f.readlines():
                parts = line.split()
                if parts[0] == device_path:
                    return parts[1]
        return None

    def on_ssd_added(self):
        # Start a thread to perform continuous actions on SSD connection
        self._ssd_thread_stop_event.clear()  # Ensure the stop event is clear
        self._ssd_thread = threading.Thread(target=self._ssd_actions)
        self._ssd_thread.start()
        
        # Initialize and start the DirectoryWatcher
        self.directory_watcher = DirectoryWatcher(self.path)
        self.directory_watcher.write_status_changed_event.subscribe(self.handle_write_status_change)
        self.directory_watcher.new_file_created_event.subscribe(self.handle_new_file_creation)

    def on_ssd_removed(self):
        logging.info("SSD removed.")

        # Stop the SSD thread actions
        if self._ssd_thread and self._ssd_thread.is_alive():
            logging.info("Setting SSD thread stop event...")
            self._ssd_thread_stop_event.set()
            self._ssd_thread.join()
            logging.info("SSD thread stopped.")

        # Stop the directory watcher
        if self.directory_watcher:
            self.directory_watcher.stop()
            self.directory_watcher = None

        logging.info("Dismounting the drive...")
        subprocess.run(["umount", self.path])
        self.is_drive_mounted = False
        logging.info("SSD is unmounted!")
        self.last_space_left = None
        self.unmount_event.emit()
        
            
    def handle_write_status_change(self, status):
        """Emit event when writing status changes."""
        
        #self.write_status_changed_event.emit(status)

    def handle_new_file_creation(self, file_path):
        """Emit event when a new file/folder is created."""
        self.new_file_created_event.emit(file_path)

    def _ssd_actions(self):
        while True:
            current_space = self.get_ssd_space_left()

            # If last_space_left has been set previously
            if self.last_space_left is not None:
                # Check if space is decreasing
                if current_space < self.last_space_left:
                    if not self.space_was_decreasing:  # This is the start of a decrease
                        self.space_decreasing_event.emit(current_space)
                        self.space_was_decreasing = True
                # Check if space was decreasing but has now stopped/stabilized
                elif self.space_was_decreasing and current_space >= self.last_space_left:
                    self.space_stable_event.emit(current_space)
                    self.space_was_decreasing = False

            # Update the last_space_left attribute
            self.last_space_left = current_space

            if self._ssd_thread_stop_event.wait(1):  # Check every 10 seconds or choose another interval
                break

    def get_ssd_space_left(self):
        """Get available space left on the SSD."""
        stat = os.statvfs(self.path)
        # Get available space in GB
        space_left = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        self.last_space_left = space_left
        return space_left
    
    def output_ssd_space_left(self):
        self.last_space_left = self.get_ssd_space_left()
        logging.info(f"Space left: {self.last_space_left}.")
    
    def unmount_drive(self):
        # Stop the SSD thread actions
        if self._ssd_thread and self._ssd_thread.is_alive():
            logging.info("Setting SSD thread stop event...")
            self._ssd_thread_stop_event.set()
            self._ssd_thread.join()
            logging.info("SSD thread stopped.")

        # Stop the directory watcher
        if self.directory_watcher:
            self.directory_watcher.stop()
            self.directory_watcher = None

        logging.info("Dismounting the drive...")
        subprocess.run(["umount", self.path])
        self.last_space_left = None
        self.disk_mounted = False
        logging.info("SSD is unmounted!")
        self.unmount_event.emit()
        
    def stop_threads(self):
        # Stop the SSD thread actions
        if self._ssd_thread and self._ssd_thread.is_alive():
            logging.info("Setting SSD thread stop event...")
            self._ssd_thread_stop_event.set()
            self._ssd_thread.join()
            logging.info("SSD thread stopped.")

        # Stop the directory watcher thread
        if self.directory_watcher:
            self.directory_watcher.stop()
            self.directory_watcher = None 
            
class DirectoryWatcher:
    def __init__(self, watch_path):
        self.inotify = INotify()
        self.watches = {}
        self.active = True  # Active flag indicating whether the watcher is active
        
        self.last_dng_file_added = None  # Initialize the attribute for the last .dng file
        self.last_wav_file_added = None  # Initialize the attribute for the last .wav file
        
        self.last_subfolder_wd = None
        # Initialize the set before calling recursively_watch_directory
        self.active_watches = set()  
        self.new_files = set()
        self.writing_to_drive = False
        self.last_write_time = 0  # Initialize to a value far in the past
        self.buffer_time = 0.1
        self.last_file_added = None  # Initialize the attribute here
        self.write_status_changed_event = Event()
        self.new_file_created_event = Event()
        
        self.lock = threading.Lock()
        
        # This method will now correctly use active_watches set
        self.add_watch_for_directory(watch_path) 
        
        self.write_status_thread = threading.Thread(target=self.monitor_write_status, daemon=True)
        self.event_thread = threading.Thread(target=self.run, daemon=True)
        self.write_status_thread.start()
        self.event_thread.start()

    
    def add_watch_for_directory(self, directory_path):
        with self.lock:
            # Remove the watcher for the previously created subfolder, if it exists and it's not '/media/RAW'
            if self.last_subfolder_wd and self.watches.get(self.last_subfolder_wd) != '/media/RAW':
                try:
                    self.inotify.rm_watch(self.last_subfolder_wd)
                    logging.info(f"Removed watch descriptor {self.last_subfolder_wd} for previous subfolder.")
                    del self.watches[self.last_subfolder_wd]  # Remove it from the dictionary
                    self.active_watches.remove(self.last_subfolder_wd)  # Remove the descriptor from active watches
                except OSError as e:
                    logging.error(f"Error removing watch descriptor {self.last_subfolder_wd}: {e}")
                self.last_subfolder_wd = None  # Reset the attribute

            # Now add a watcher for the new subfolder
            wd = self.inotify.add_watch(directory_path, flags.CREATE)
            #logging.info(f"Added watch descriptor {wd} for path {directory_path}.")
            self.watches[wd] = directory_path
            self.active_watches.add(wd)
            
            # Update the last_subfolder_wd attribute with the new descriptor
            self.last_subfolder_wd = wd
            
        directories = [os.path.join(directory_path, d) for d in os.listdir(directory_path) if os.path.isdir(os.path.join(directory_path, d))]
        if not directories:
            return

        # Sort directories by creation time
        latest_directory = max(directories, key=os.path.getctime)

        self.add_watch_for_directory(latest_directory)
                
    def handle_event(self):
        for event in self.inotify.read():
            with self.lock:
                try:
                    watched_path = self.watches[event.wd]
                except KeyError:
                    # Only log a warning if the watcher is still active
                    if self.active:
                        logging.warning(f"Descriptor {event.wd} not found in the watches.")
                    continue

            full_path = os.path.join(watched_path, event.name)

            if os.path.isdir(full_path):
                self.add_watch_for_directory(full_path)
            elif os.path.isfile(full_path):
                logging.info(f"New file created: {full_path}")
                with self.lock:
                    self.new_files.add(full_path)
                self.last_write_time = time.time()
                self.writing_to_drive = True  # Set the flag to True

                # Update the last .dng or .wav file created attributes
                if event.name.lower().endswith('.dng'):
                    self.last_dng_file_added = full_path
                elif event.name.lower().endswith('.wav'):
                    self.last_wav_file_added = full_path

    def monitor_write_status(self):
        last_status = self.writing_to_drive  # Use the initial status of self.writing_to_drive for comparison
        #logging.info(f"Initial writing to drive status: {last_status}")  # Log the initial status
        while True:
            time.sleep(self.buffer_time)
            current_time = time.time()
            if current_time - self.last_write_time > self.buffer_time:
                self.writing_to_drive = False

            if self.writing_to_drive != last_status:
                #logging.info(f"Writing to drive status: {self.writing_to_drive}")
                
                # Emit the event here
                self.write_status_changed_event.emit(self.writing_to_drive)
                
                last_status = self.writing_to_drive

    def run(self):
        try:
            while True:
                self.handle_event()
                #logging.info(f"Writing to drive: {self.writing_to_drive} | {', '.join(self.new_files)} ", end='\r')
                if self.new_files:
                    self.new_files.clear()
        except KeyboardInterrupt:
            self.stop()

    def start(self):
        if not self.write_status_thread.is_alive():
            self.write_status_thread = threading.Thread(target=self.monitor_write_status, daemon=True)
            self.write_status_thread.start()
        if not self.event_thread.is_alive():
            self.event_thread = threading.Thread(target=self.run, daemon=True)
            self.event_thread.start()

    def stop(self):
        self.active = False  # Set the active flag to False when stopping
        with self.lock:
            # Create a copy of the watch keys to iterate over, 
            # so we're not modifying a dictionary while iterating over it.
            for wd in list(self.watches.keys()):  
                try:
                    self.inotify.rm_watch(wd)
                    logging.info(f"Attempting to remove watch descriptor {wd}...")
                    del self.watches[wd]  # Remove it from the dictionary
                    if wd in self.active_watches:  # Check if wd is in active_watches before trying to remove it
                        self.active_watches.remove(wd)  # Remove the descriptor from active watches
                        logging.info(f"Successfully removed watch descriptor {wd}.")
                    else:
                        logging.warning(f"Descriptor {wd} not found in the active watches.")
                except OSError as e:
                    logging.error(f"Error removing watch descriptor {wd}: {e}")

# import threading
# import subprocess
# import logging
# import time
# import os
# import json
# from inotify_simple import INotify, flags

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

# class SSDMonitor():
#     def __init__(self):
#         self.active_watches = set()
#         self.usb_hd = None
#         self.usb_hd_serial = None  # Initialize the attribute
#         self.path = '/media/RAW'
#         self.disk_mounted = False
#         self.last_space_left = None
#         self.space_decreasing = False
#         self.ssd_event = Event()
#         self.space_decreasing_event = Event()
#         self.space_was_decreasing = False
#         self.space_stable_event = Event()
#         self._ssd_thread_stop_event = threading.Event()
        
#         self.unmount_event = Event()
        
#         # Initialize new events
#         self.write_status_changed_event = Event()
#         self.new_file_created_event = Event()
        
#         # Add an attribute to store the DirectoryWatcher instance
#         self.directory_watcher = None
        
#         # Load recognized SSD models from the settings file
#         self.recognized_ssds = self.load_ssd_settings("/home/pi/cinemate/src/module/ssd_settings.json")
        
#     def load_ssd_settings(self, settings_file):
#         """Load SSD settings from the specified JSON file."""
#         try:
#             with open(settings_file, 'r') as file:
#                 settings = json.load(file)
#                 return settings.get('recognized_ssds', [])
#         except Exception as e:
#             logging.error(f"Failed to load SSD settings: {e}")
#             return []
    
#     def update(self, action, device_model, device_serial):
#         model_upper = device_model.upper()
#         if action == 'add' and any(ssd_model.upper() in model_upper for ssd_model in self.recognized_ssds):
#             self.usb_hd_serial = device_serial
            
#             # Check for the existence of the path in a loop until it's mounted or a timeout occurs
#             timeout = 30  # Set a timeout value (adjust as needed)
#             start_time = time.time()
#             while time.time() - start_time < timeout:
#                 if os.path.exists(self.path) and os.path.ismount(self.path):
#                     self.disk_mounted = self.path
#                     self.last_space_left = self.get_ssd_space_left()
#                     logging.info(f"SSD mounted at {self.disk_mounted} with model: {device_model}")
#                     logging.info(f"Space left: {self.last_space_left} GB.")
#                     self.on_ssd_added()
#                     return  # Exit the loop if the path is mounted
#                 time.sleep(1)  # Sleep for 1 second before checking again

#             logging.info(f"SSD not mounted within the timeout period.")
            
#         elif action == 'remove' and self.usb_hd_serial and self.usb_hd_serial == device_serial:
            
#             logging.info(f"USB SSD disconnected: {device_model}")
#             self.on_ssd_removed()
        
#     def get_mount_point(self, device_path):
#         """Get the mount point of the device if mounted, otherwise return None."""
#         with open('/proc/mounts', 'r') as f:
#             for line in f.readlines():
#                 parts = line.split()
#                 if parts[0] == device_path:
#                     return parts[1]
#         return None

#     def is_drive_mounted(self):
#         """Check if the drive is mounted and return the mount point or None"""
#         if os.path.exists(self.path) and os.path.ismount(self.path):
#             self.disk_mounted = self.path
#         else:
#             self.disk_mounted = None
#         logging.info(f"SSD mount path {self.disk_mounted}")
#         return self.disk_mounted

#     def on_ssd_added(self):
#         # Start a thread to perform continuous actions on SSD connection
#         self._ssd_thread_stop_event.clear()  # Ensure the stop event is clear
#         self._ssd_thread = threading.Thread(target=self._ssd_actions)
#         self._ssd_thread.start()
        
#         # Initialize and start the DirectoryWatcher
#         self.directory_watcher = DirectoryWatcher(self.path)
#         self.directory_watcher.write_status_changed_event.subscribe(self.handle_write_status_change)
#         self.directory_watcher.new_file_created_event.subscribe(self.handle_new_file_creation)

#     def on_ssd_removed(self):
#         logging.info("SSD removed.")
        
#         self.unmount_event.emit()

#         # Stop the SSD thread actions
#         if self._ssd_thread and self._ssd_thread.is_alive():
#             logging.info("Setting SSD thread stop event...")
#             self._ssd_thread_stop_event.set()
#             self._ssd_thread.join()
#             logging.info("SSD thread stopped.")

#         # Stop the directory watcher
#         if self.directory_watcher:
#             self.directory_watcher.stop()
#             self.directory_watcher = None

#         logging.info("Dismounting the drive...")
#         subprocess.run(["umount", self.path])
#         self.is_drive_mounted()
#         logging.info("SSD is unmounted!")
        
            
#     def handle_write_status_change(self, status):
#         """Emit event when writing status changes."""
        
#         #self.write_status_changed_event.emit(status)

#     def handle_new_file_creation(self, file_path):
#         """Emit event when a new file/folder is created."""
#         self.new_file_created_event.emit(file_path)

#     def _ssd_actions(self):
#         while True:
#             current_space = self.get_ssd_space_left()

#             # If last_space_left has been set previously
#             if self.last_space_left is not None:
#                 # Check if space is decreasing
#                 if current_space < self.last_space_left:
#                     if not self.space_was_decreasing:  # This is the start of a decrease
#                         self.space_decreasing_event.emit(current_space)
#                         self.space_was_decreasing = True
#                 # Check if space was decreasing but has now stopped/stabilized
#                 elif self.space_was_decreasing and current_space >= self.last_space_left:
#                     self.space_stable_event.emit(current_space)
#                     self.space_was_decreasing = False

#             # Update the last_space_left attribute
#             self.last_space_left = current_space

#             if self._ssd_thread_stop_event.wait(1):  # Check every 10 seconds or choose another interval
#                 break

#     def get_ssd_space_left(self):
#         """Get available space left on the SSD."""
#         stat = os.statvfs(self.path)
#         # Get available space in GB
#         space_left = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
#         self.last_space_left = space_left
#         return space_left
    
#     def output_ssd_space_left(self):
#         self.last_space_left = self.get_ssd_space_left()
#         logging.info(f"Space left: {self.last_space_left}.")
    

#     def unmount_drive(self):

#         # Stop the SSD thread actions
#         if self._ssd_thread and self._ssd_thread.is_alive():
#             logging.info("Setting SSD thread stop event...")
#             self._ssd_thread_stop_event.set()
#             self._ssd_thread.join()
#             logging.info("SSD thread stopped.")

#         # Stop the directory watcher
#         if self.directory_watcher:
#             self.directory_watcher.stop()
#             self.directory_watcher = None

#         logging.info("Dismounting the drive...")
#         subprocess.run(["umount", self.path])
#         self.is_drive_mounted()
#         logging.info("SSD is unmounted!")
        
        
        
#     def stop_threads(self):
#         # Stop the SSD thread actions
#         if self._ssd_thread and self._ssd_thread.is_alive():
#             logging.info("Setting SSD thread stop event...")
#             self._ssd_thread_stop_event.set()
#             self._ssd_thread.join()
#             logging.info("SSD thread stopped.")

#         # Stop the directory watcher thread
#         if self.directory_watcher:
#             self.directory_watcher.stop()
#             self.directory_watcher = None

        
# class DirectoryWatcher:
#     def __init__(self, watch_path):
#         self.inotify = INotify()
#         self.watches = {}
#         self.active = True  # Active flag indicating whether the watcher is active
        
#         self.last_dng_file_added = None  # Initialize the attribute for the last .dng file
#         self.last_wav_file_added = None  # Initialize the attribute for the last .wav file
        
#         self.last_subfolder_wd = None
#         # Initialize the set before calling recursively_watch_directory
#         self.active_watches = set()  
#         self.new_files = set()
#         self.writing_to_drive = False
#         self.last_write_time = 0  # Initialize to a value far in the past
#         self.buffer_time = 0.1
#         self.last_file_added = None  # Initialize the attribute here
#         self.write_status_changed_event = Event()
#         self.new_file_created_event = Event()
        
#         self.lock = threading.Lock()
        
#         # This method will now correctly use active_watches set
#         self.add_watch_for_directory(watch_path) 
        
#         self.write_status_thread = threading.Thread(target=self.monitor_write_status, daemon=True)
#         self.event_thread = threading.Thread(target=self.run, daemon=True)
#         self.write_status_thread.start()
#         self.event_thread.start()

    
#     def add_watch_for_directory(self, directory_path):
#         with self.lock:
#             # Remove the watcher for the previously created subfolder, if it exists and it's not '/media/RAW'
#             if self.last_subfolder_wd and self.watches.get(self.last_subfolder_wd) != '/media/RAW':
#                 try:
#                     self.inotify.rm_watch(self.last_subfolder_wd)
#                     logging.info(f"Removed watch descriptor {self.last_subfolder_wd} for previous subfolder.")
#                     del self.watches[self.last_subfolder_wd]  # Remove it from the dictionary
#                     self.active_watches.remove(self.last_subfolder_wd)  # Remove the descriptor from active watches
#                 except OSError as e:
#                     logging.error(f"Error removing watch descriptor {self.last_subfolder_wd}: {e}")
#                 self.last_subfolder_wd = None  # Reset the attribute

#             # Now add a watcher for the new subfolder
#             wd = self.inotify.add_watch(directory_path, flags.CREATE)
#             #logging.info(f"Added watch descriptor {wd} for path {directory_path}.")
#             self.watches[wd] = directory_path
#             self.active_watches.add(wd)
            
#             # Update the last_subfolder_wd attribute with the new descriptor
#             self.last_subfolder_wd = wd
            
#         directories = [os.path.join(directory_path, d) for d in os.listdir(directory_path) if os.path.isdir(os.path.join(directory_path, d))]
#         if not directories:
#             return

#         # Sort directories by creation time
#         latest_directory = max(directories, key=os.path.getctime)

#         self.add_watch_for_directory(latest_directory)
                
#     def handle_event(self):
#         for event in self.inotify.read():
#             with self.lock:
#                 try:
#                     watched_path = self.watches[event.wd]
#                 except KeyError:
#                     # Only log a warning if the watcher is still active
#                     if self.active:
#                         logging.warning(f"Descriptor {event.wd} not found in the watches.")
#                     continue

#             full_path = os.path.join(watched_path, event.name)

#             if os.path.isdir(full_path):
#                 self.add_watch_for_directory(full_path)
#             elif os.path.isfile(full_path):
#                 logging.info(f"New file created: {full_path}")
#                 with self.lock:
#                     self.new_files.add(full_path)
#                 self.last_write_time = time.time()
#                 self.writing_to_drive = True  # Set the flag to True

#                 # Update the last .dng or .wav file created attributes
#                 if event.name.lower().endswith('.dng'):
#                     self.last_dng_file_added = full_path
#                 elif event.name.lower().endswith('.wav'):
#                     self.last_wav_file_added = full_path

#     def monitor_write_status(self):
#         last_status = self.writing_to_drive  # Use the initial status of self.writing_to_drive for comparison
#         #logging.info(f"Initial writing to drive status: {last_status}")  # Log the initial status
#         while True:
#             time.sleep(self.buffer_time)
#             current_time = time.time()
#             if current_time - self.last_write_time > self.buffer_time:
#                 self.writing_to_drive = False

#             if self.writing_to_drive != last_status:
#                 #logging.info(f"Writing to drive status: {self.writing_to_drive}")
                
#                 # Emit the event here
#                 self.write_status_changed_event.emit(self.writing_to_drive)
                
#                 last_status = self.writing_to_drive

#     def run(self):
#         try:
#             while True:
#                 self.handle_event()
#                 #logging.info(f"Writing to drive: {self.writing_to_drive} | {', '.join(self.new_files)} ", end='\r')
#                 if self.new_files:
#                     self.new_files.clear()
#         except KeyboardInterrupt:
#             self.stop()

#     def start(self):
#         if not self.write_status_thread.is_alive():
#             self.write_status_thread = threading.Thread(target=self.monitor_write_status, daemon=True)
#             self.write_status_thread.start()
#         if not self.event_thread.is_alive():
#             self.event_thread = threading.Thread(target=self.run, daemon=True)
#             self.event_thread.start()

#     def stop(self):
#         self.active = False  # Set the active flag to False when stopping
#         with self.lock:
#             # Create a copy of the watch keys to iterate over, 
#             # so we're not modifying a dictionary while iterating over it.
#             for wd in list(self.watches.keys()):  
#                 try:
#                     self.inotify.rm_watch(wd)
#                     logging.info(f"Attempting to remove watch descriptor {wd}...")
#                     del self.watches[wd]  # Remove it from the dictionary
#                     if wd in self.active_watches:  # Check if wd is in active_watches before trying to remove it
#                         self.active_watches.remove(wd)  # Remove the descriptor from active watches
#                         logging.info(f"Successfully removed watch descriptor {wd}.")
#                     else:
#                         logging.warning(f"Descriptor {wd} not found in the active watches.")
#                 except OSError as e:
#                     logging.error(f"Error removing watch descriptor {wd}: {e}")