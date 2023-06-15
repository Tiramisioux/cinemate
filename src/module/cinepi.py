import subprocess
import threading
import time
import signal
import os
import logging
import pathlib

# Set up the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Config:
    # Configurations for the application
    REDIS_HOST = 'localhost'
    REDIS_PORT = 6379
    REDIS_DB = 0
    DIRECTORY = "/media/RAW"
    CINEPI_CMD = ['cinepi-raw']
    EXTERNAL_DRIVE_PATH = "/media/RAW"

import threading
import subprocess
import os

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
            self.process = subprocess.Popen(['cinepi-raw'], 
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE)
            self.is_recording = threading.Event()
            self._lock = threading.Lock() 
            self.thread = threading.Thread(target=self._listen)
            self.last_lines = []  # Keep track of the last lines
            self.lines_counter = 0  # Counter for lines read
            self.thread.start()
            self.monitor = monitor
            self.controller = CinePiController(self, self.r, self.monitor)  # Instantiate the controller here
            self.audio_recorder = AudioRecorder(self.r)
            self.initialized = True  # indicate that the instance has been initialized

    def _listen(self):
        for line in iter(self.process.stdout.readline, b''):
            with self._lock:
                line = line.rstrip().decode('utf-8')

                if line == 'is_recording from: cp_controls':
                    is_recording = self.r.get('is_recording')
                    is_recording_int = int(is_recording.decode('utf-8'))
                    if is_recording_int == 1:
                        self.is_recording.set()
                        self.audio_recorder.start_recording()  # Start audio recording
                    elif is_recording_int == 0:
                        self.is_recording.clear()
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
        self.r.set(control, value)
        self.r.publish("cp_controls", control)
        if control == 'height':
            self.r.set("cam_init", 1)
            self.r.publish("cp_controls", "cam_init")

        return True


class AudioRecorder:

    # Class for managing audio recording.
    def __init__(self, r):
        self.r = r
        self.directory = Config.DIRECTORY
        self.process = None

    def start_recording(self):

        # Start recording.

        # Check if the directory exists
        if not os.path.exists(self.directory):
            logger.warning(f"Directory {self.directory} does not exist. Please attach the drive.")
            return

        # Check if a USB microphone is connected
        usb_microphone = self.get_usb_microphone()
        if not usb_microphone:
            logger.warning("No USB microphone detected. Recording of audio cannot be started.")
            return

        # Start recording
        file_name = f"CINEPI_{time.strftime('%y-%m-%d_%H%M%S')}_AUDIO_SCRATCH.wav"
        self.file_path = os.path.join(self.directory, file_name)
        command = f"arecord -D plughw:{usb_microphone} -f cd -c 1 -t wav {self.file_path}"

        try:
            self.process = subprocess.Popen(command, shell=True, preexec_fn=os.setsid, stderr=subprocess.DEVNULL)
            logger.info(f"Audio recording started and will be saved to {self.file_path}")
        except Exception as e:
            logger.error(f"Failed to start recording. Error: {str(e)}")

    def stop_recording(self):

        # Stop recording.

        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                logger.info(f"Audio recording stopped. File saved at {self.file_path}")
            except Exception as e:
                logger.error(f"Failed to stop recording. Error: {str(e)}")
        else:
            logger.info("No audio recording to stop.")

    def get_usb_microphone(self):

        # Get the device number of the USB microphone.

        try:
            # Get a list of connected USB audio devices
            devices = subprocess.check_output("arecord -l | grep card", shell=True).decode("utf-8")

            # Find the USB microphone device number
            for device in devices.split("\n"):
                if "USB" in device:
                    device_number = device.split(":")[0][-1]
                    return device_number
        except subprocess.CalledProcessError:
            logger.error("Failed to retrieve USB microphone. Continuing without USB microphone.")
