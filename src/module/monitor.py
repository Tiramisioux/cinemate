import pyudev
import threading
import os
import psutil
import glob
import time

class DriveMonitor:
    def __init__(self, path):
        self.path = path
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem='block', device_type='partition')
        self.observer = pyudev.MonitorObserver(self.monitor, callback=self.on_event)
        self.connection_callbacks = []  # Callbacks to be called on drive connection change
        self.check_initial_status()
        self.start_monitoring()

        # Additional variables for monitoring
        self.last_created_folder = None
        self.last_created_wav_file = None
        self.last_folder_file_count = None
        self.remaining_space = None
        self.update_parameters()

    def check_initial_status(self):
        if os.path.ismount(self.path):
            print('Drive is connected at startup')
        else:
            print('Drive is not connected at startup')

    def on_event(self, device):
        if device.action == 'add':
            self.wait_until(lambda: os.path.ismount(self.path), timeout=2.0)
            if os.path.ismount(self.path):
                print('Drive connected')
                self.update_parameters()
                self.notify_drive_status_change()
            else:
                print('Drive disconnected')
                self.last_created_folder = None
                self.last_created_wav_file = None
                self.last_folder_file_count = None
                self.notify_drive_status_change()
        elif device.action == 'remove':
            self.wait_until(lambda: not os.path.ismount(self.path), timeout=2.0)
            if os.path.ismount(self.path):
                print('Drive connected')
            else:
                print('Drive disconnected')
                self.last_created_folder = None
                self.last_created_wav_file = None
                self.last_folder_file_count = None
                self.notify_drive_status_change()

    def wait_until(self, condition_func, timeout=2.0, interval=0.1):
        end_time = time.time() + timeout
        while time.time() < end_time:
            if condition_func():
                return True
            time.sleep(interval)
        return False

    def register_connection_callback(self, callback):
        self.connection_callbacks.append(callback)

    def notify_drive_status_change(self):
        for callback in self.connection_callbacks:
            callback()

    def start_monitoring(self):
        self.observer.start()

    def is_drive_connected(self):
        try:
            return os.path.ismount(self.path)
        except (OSError, IOError) as e:
            print(f"Error occurred in checking drive connection: {e}")
            return False

    def update_parameters(self):
        if self.is_drive_connected():
            self.last_created_folder = self.get_last_created_folder()
            self.last_created_wav_file = self.get_last_created_wav_file()
            self.last_folder_file_count = self.get_file_count_of_last_created_folder()
        else:
            self.last_created_folder = None
            self.last_created_wav_file = None
            self.last_folder_file_count = None

        threading.Timer(1.0, self.update_parameters).start()  # Schedule the next update after 1 second

    def get_remaining_space(self):
        if not self.is_drive_connected():
            return None
        usage = psutil.disk_usage(self.path)
        return usage.free

    def get_last_created_folder(self):
        if not self.is_drive_connected():
            return None
        folders = [os.path.join(self.path, d) for d in os.listdir(self.path) if os.path.isdir(os.path.join(self.path, d))]
        return max(folders, key=os.path.getctime) if folders else None

    def get_last_created_wav_file(self):
        if not self.is_drive_connected():
            return None
        wav_directory = self.path  # Assuming the WAV files are directly in the drive path
        if not os.path.isdir(wav_directory):
            print(f"Directory {wav_directory} does not exist.")
            return None

        wavs = glob.glob(wav_directory + '/**/*.wav', recursive=True)
        wavs += glob.glob(wav_directory + '/**/*.WAV', recursive=True)

        if not wavs:
            return None

        # Sort the files lexicographically and return the last one
        wavs.sort()
        return os.path.basename(wavs[-1])

    def get_file_count_of_last_created_folder(self):
        folder = self.last_created_folder
        if folder is None:
            return None
        return len([name for name in os.listdir(folder) if os.path.isfile(os.path.join(folder, name))])
