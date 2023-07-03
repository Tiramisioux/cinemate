import subprocess
import threading
import time
import signal
import os
import logging
import pathlib
from queue import Queue, Empty
from threading import Thread
import pyudev
import keyboard

# Set up the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        queue.put(line)
    out.close()

class Config:
    # Configurations for the application
    REDIS_HOST = 'localhost'
    REDIS_PORT = 6379
    REDIS_DB = 0
    DIRECTORY = "/media/RAW"
    CINEPI_CMD = ['cinepi-raw']
    EXTERNAL_DRIVE_PATH = "/media/RAW"

class CinePi:
    _instance = None  # Singleton instance
    LINES_THRESHOLD = 20  # The number of lines to check

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, r, monitor):
        if not hasattr(self, 'initialized'):  # only initialize once
            self.r = r
            self.suppress_output = False
            self.process = subprocess.Popen(['cinepi-raw'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            self.out_queue = Queue()
            self.err_queue = Queue()
            self.out_thread = Thread(target=enqueue_output, args=(self.process.stdout, self.out_queue))
            self.err_thread = Thread(target=enqueue_output, args=(self.process.stderr, self.err_queue))
            self.out_thread.daemon = True
            self.err_thread.daemon = True
            self.out_thread.start()
            self.err_thread.start()
            
            self.is_recording = threading.Event()
            self._lock = threading.Lock() 
            self.thread = threading.Thread(target=self._listen)
            self.last_lines = []  # Keep track of the last lines
            self.lines_counter = 0  # Counter for lines read
            self.thread.start()
            
            self.monitor = monitor
            self.controller = CinePiController(self, self.r, self.monitor)  # Instantiate the controller here
            
            # Initialize USBMonitor with the controller
            self.USBMonitor = USBMonitor(self.controller)
            self.USBMonitor.monitor_devices()
            
            self.audio_recorder = AudioRecorder(self.r, self.USBMonitor) 

            self.initialized = True  # indicate that the instance has been initialized


    def _listen(self):
            while True:
                # read line without blocking
                try:  
                    line = self.out_queue.get_nowait() # or q.get(timeout=.1)
                except Empty:
                    pass
                else: # got line
                    line = line.rstrip().decode('utf-8')
                    print(line)  # print the line to console
                    if line == 'is_recording from: cp_controls':
                        is_recording = self.r.get('is_recording')
                        is_recording_int = int(is_recording.decode('utf-8'))
                        if is_recording_int == 1:
                            self.is_recording.set()
                            if self.USBMonitor.usb_mic:
                                self.audio_recorder.start_recording()  # Start audio recording
                        elif is_recording_int == 0:
                            self.is_recording.clear()
                            if self.USBMonitor.usb_mic:
                                self.audio_recorder.stop_recording()  # Stop audio recording

    def get_recording_status(self):
        with self._lock:
            return self.is_recording.is_set()
        
class CinePiController:
    def __init__(self, cinepi, r, monitor):
        self.r = r
        self.cinepi = cinepi
        self.monitor = monitor
        self.drive_mounted = self.monitor.is_drive_connected()
        
    def get_recording_status(self):
        return self.cinepi.get_recording_status()

    def start_recording(self):
        drive_mounted = self.monitor.is_drive_connected()
        if drive_mounted:
            self.r.set('is_recording', 1)
            self.r.publish('cp_controls', 'is_recording')
            logger.info("Recording started")
        else:
            print("Drive is not attached. Cannot start recording.")

    def stop_recording(self):
        self.r.set('is_recording', 0)
        self.r.publish('cp_controls', 'is_recording')
        logger.info("Recording stopped")
        
    def get_control_value(self, control):
        res = self.r.get(control)
        return res.decode() if res is not None else None

    def set_control_value(self, control, value):
        
        if control == 'fps':
            value = max(1,min(50, value))
        
        self.r.set(control, value)        
        self.r.publish("cp_controls", control)
        
        if control == 'height':
            self.r.set("cam_init", 1)
            self.r.publish("cp_controls", "cam_init")

        return True

class AudioRecorder:

    def __init__(self, r, USBMonitor):
        self.r = r
        self.USBMonitor = USBMonitor
        self.directory = Config.DIRECTORY
        self.process = None
        self.usb_mic = None

    def start_recording(self):
        try:
            file_name = f"CINEPI_{time.strftime('%y-%m-%d_%H%M%S')}_AUDIO_SCRATCH.wav"
            self.file_path = os.path.join(self.directory, file_name)
            command = f"arecord -D plughw:{self.USBMonitor.usb_mic} -f cd -c 1 -t wav {self.file_path}"
            self.process = subprocess.Popen(command, shell=True, preexec_fn=os.setsid, stderr=subprocess.DEVNULL)
            logger.info(f"Audio recording started and will be saved to {self.file_path}")
        except Exception as e:
            logger.error(f"Failed to start recording. Error: {str(e)}")

    def stop_recording(self):
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                logger.info(f"Audio recording stopped. File saved at {self.file_path}")
            except OSError as e:
                if e.errno == 19:  # No such device
                    logger.info("Microphone was disconnected. Stopping recording.")
                else:
                    raise e
            except Exception as e:
                logger.error(f"Failed to stop recording. Error: {str(e)}")
        else:
            logger.info("No audio recording to stop.")


class USBMonitor:
    def __init__(self, controller):
        self.controller = controller
        self.context = pyudev.Context()
        self.monitor = pyudev.Monitor.from_netlink(self.context)
        self.monitor.filter_by(subsystem='usb')
        self.usb_mic = None
        self.usb_mic_path = None
        self.usb_keyboard = None
        self.usb_hd = None
        self.keyboard_handler = None
        self.check_initial_devices()


    def device_event(self, monitor, device):
        if device.action == 'add':
            if 'USB_PNP_SOUND_DEVICE' in device.get('ID_MODEL', '').upper():
                self.usb_mic_path = device.device_path
                print(f'USB Microphone connected: {device}')
                self.get_usb_microphone()
            
            elif 'KEYBOARD' in device.get('ID_MODEL', '').upper():
                self.usb_keyboard = device
                print(f'USB Keyboard connected: {device}')
                
                # Initialize the keyboard class
                self.keyboard = Keyboard(self.controller)  # Instantiate the keyboard handler
                self.keyboard_thread = threading.Thread(target=self.keyboard.start)  # Create a thread for the keyboard listener
                self.keyboard_thread.daemon = True  # Set the thread as a daemon thread to automatically exit when the main program ends
                self.keyboard_thread.start()  # Start the keyboard listener thread
            
            elif 'SSD' in device.get('ID_MODEL', '').upper():
                self.usb_hd = device
                print(f'USB SSD connected: {device}')
        elif device.action == 'remove':
            print(f'Device disconnected: {device}')
            if self.usb_mic_path is not None and self.usb_mic_path == device.device_path:

                self.usb_mic_path = None
                print(f'USB Microphone disconnected: {device}')
                self.get_usb_microphone()
            elif self.usb_keyboard is not None and self.usb_keyboard == device:
                self.usb_keyboard = None
                print(f'USB Keyboard disconnected: {device}')
                # Stop the keyboard listener here
                if self.keyboard_thread and self.keyboard_thread.is_alive():
                    keyboard.unhook_all()  # Unhook all the keyboard listeners
                    print("Keyboard listener stopped")
            elif self.usb_hd is not None and self.usb_hd == device:
                self.usb_hd = None
                print(f'USB SSD disconnected: {device}')


    def check_initial_devices(self):
        for device in self.context.list_devices(subsystem='usb'):
            if 'USB_PNP_SOUND_DEVICE' in device.get('ID_MODEL', '').upper():
                self.usb_mic_serial = device.get('ID_SERIAL')
                print(f'USB Microphone connected: {device}')
                self.get_usb_microphone()
            elif 'KEYBOARD' in device.get('ID_MODEL', '').upper():
                self.usb_keyboard = device
                print(f'USB Keyboard connected: {device}')
                
                # Initialize the keyboard class here
                self.keyboard = Keyboard(self.controller)  # Instantiate the keyboard handler
                self.keyboard_thread = threading.Thread(target=self.keyboard.start)  # Create a thread for the keyboard listener
                self.keyboard_thread.daemon = True  # Set the thread as a daemon thread to automatically exit when the main program ends
                self.keyboard_thread.start()  # Start the keyboard listener thread
            elif 'SSD' in device.get('ID_MODEL', '').upper():
                self.usb_hd = device
                print(f'USB SSD connected: {device}')

                
    def get_usb_microphone(self):
        try:
            # Get a list of connected USB audio devices
            devices = subprocess.check_output("arecord -l | grep card", shell=True).decode("utf-8")
            
            # Find the USB microphone device number
            for device in devices.split("\n"):
                if "USB" in device:
                    device_number = device.split(":")[0][-1]
                    self.usb_mic = device_number
 
                    # return device_number
            print(self.usb_mic)    
        except subprocess.CalledProcessError:
            logger.error("Failed to retrieve USB microphone. Continuing without USB microphone.")
            self.usb_mic = None


    def monitor_devices(self):
        observer = pyudev.MonitorObserver(self.monitor, self.device_event)
        observer.start()
        
class Keyboard:
    def __init__(self, controller):
        self.controller = controller

    def start(self):
        keyboard.on_press_key("r", self.handle_key_event)
        keyboard.on_press_key("h", self.handle_key_event)
        keyboard.wait("esc")  # Wait for the "esc" key to exit the event loop

    def handle_key_event(self, event):
        if event.name == "r":
            # Start/stop recording
            if self.controller.get_recording_status():
                self.controller.stop_recording()
                print("Recording stopped")
            else:
                self.controller.start_recording()
                print("Recording started")
        # Add more key handling code as needed
        if event.name == "h":
            if self.controller.get_control_value('height') == '1080':
                self.controller.set_control_value('height', 1520)
            elif self.controller.get_control_value('height') == '1520':
                self.controller.set_control_value('height', 1080)

