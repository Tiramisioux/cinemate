import subprocess
import redis
import threading
import time
import signal
import os
from os import path
from gpiozero import CPUTemperature
import shutil
from shutil import disk_usage
import psutil
from PIL import Image, ImageDraw, ImageFont
from module.framebuffer import Framebuffer
from module.adc import ADC
import RPi.GPIO as GPIO
from pathlib import Path
import glob


r = redis.Redis(host='localhost', port=6379, db=0)

class CinePi:
    _instance = None  # Singleton instance
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.r = redis.Redis(host='localhost', port=6379, db=0)
        self.process = subprocess.Popen(['cinepi-raw'], stdout=subprocess.PIPE)
        self.is_recording = threading.Event()
        self.thread = threading.Thread(target=self._listen)
        self.thread.start()
        self.audio_recorder = AudioRecorder()

    def _listen(self):
        for line in iter(self.process.stdout.readline, b''):
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

class CinePiController:
    def __init__(self):
        self.r = redis.Redis(host='localhost', port=6379, db=0)
        self.cinepi = CinePi()  # Get singleton instance of CinePi

    def start_recording(self):
        self.r.set('is_recording', 1)
        self.r.publish('cp_controls', 'is_recording')

    def stop_recording(self):
        self.r.set('is_recording', 0)
        self.r.publish('cp_controls', 'is_recording')
    
    def get_control_value(self, control):
        res = r.get(control)
        return res.decode() if res is not None else None

    def set_control_value(self, control, value):
        r.set(control, value)
        r.publish("cp_controls", control)
        return True
    
    def get_recording_status(self):
        return self.cinepi.is_recording
    
    def get_latest_folder(self):
        directory = "/media/RAW"  # Specify the directory path where the folders are stored
        folders = glob.glob(os.path.join(directory, "*"))
        folders = sorted(folders, key=os.path.getctime, reverse=True)
        for folder in folders:
            if os.path.isdir(folder):
                return os.path.basename(folder)
        return None

    def get_latest_wav_file(self):
        directory = "/media/RAW"  # Specify the directory path where the WAV files are stored
        wav_files = glob.glob(os.path.join(directory, "*.wav"))
        wav_files = sorted(wav_files, key=os.path.getctime, reverse=True)
        for wav_file in wav_files:
            if os.path.isfile(wav_file):
                return os.path.basename(wav_file)
        return None

class AudioRecorder:
    def __init__(self):
        self.directory = "/media/RAW"
        self.process = None

    def start_recording(self):
        # Check if the directory exists
        if not os.path.exists(self.directory):
            print(f"Directory {self.directory} does not exist. Please attach the drive.")
            return

        # Check if a USB microphone is connected
        usb_microphone = self.get_usb_microphone()
        if not usb_microphone:
            print("No USB microphone detected. Recording cannot be started.")
            return

        # Start recording
        file_name = f"CINEPI_{time.strftime('%y-%m-%d_%H%M%S')}_AUDIO_SCRATCH.wav"
        self.file_path = os.path.join(self.directory, file_name)
        command = f"arecord -D plughw:{usb_microphone} -f cd -c 1 -t wav {self.file_path}"

        try:
            self.process = subprocess.Popen(command, shell=True, preexec_fn=os.setsid, stderr=subprocess.DEVNULL)
            print(f"Audio recording started and will be saved to {self.file_path}")
        except Exception as e:
            print(f"Failed to start recording. Error: {str(e)}")

    def stop_recording(self):
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                print(f"Audio recording stopped. File saved at {self.file_path}")
            except Exception as e:
                print(f"Failed to stop recording. Error: {str(e)}")
        else:
            print("No audio recording to stop.")

    def get_usb_microphone(self):
        try:
            # Get a list of connected USB audio devices
            devices = subprocess.check_output("arecord -l | grep card", shell=True).decode("utf-8")

            # Find the USB microphone device number
            for device in devices.split("\n"):
                if "USB" in device:
                    device_number = device.split(":")[0][-1]
                    return device_number
        except subprocess.CalledProcessError:
            print("Failed to retrieve USB microphone. Continuing without USB microphone.")

class SimpleGUI(threading.Thread):
    def __init__(self, camera):
        threading.Thread.__init__(self)

        # Frame buffer coordinates
        self.fb = Framebuffer(0)
        self.cx = self.fb.size[0] // 2
        self.cy = self.fb.size[1] // 2

        self.fill_color = "black"

        # Initialize CameraControls
        self.camera_params = camera

        self.iso = None
        self.shutter_a = None
        self.fps = None
        self.is_recording = None
        self.resolution = None


        # Get initial values
        self.get_values()
        self.resolution = int(self.resolution)

        self.file_size = 3.3
        if self.resolution == 1080: 
            self.file_size = 3.3
        if self.resolution == 1520: 
            self.file_size = 4.8
        self.drive_mounted, self.min_left = self.check_drive_mounted()

        # Get cpu statistics
        self.cpu_load, self.cpu_temp = self.get_system_stats()
        
        self.start()
        
    def get_latest_folder(self):
        latest_folder = self.camera_params.get_latest_folder()
        return latest_folder

    def check_drive_mounted(self):
        mount_point = "/media/RAW"
        if os.path.ismount(mount_point):
            total_bytes, used_bytes, free_bytes = disk_usage(path.realpath('/media/RAW'))
            drive_mounted = 1
            if self.camera_params.get_control_value('height') == "1080": self.file_size = 3.2
            if self.camera_params.get_control_value('height') == "1520": self.file_size = 4.8
            min_left = int((free_bytes / 1000000) / (self.file_size * int(self.fps) * 60))
        else:
            drive_mounted = 0
            min_left = None
        return drive_mounted, min_left
    
    def get_latest_folder(self):
        directory = "/media/RAW"  # Specify the directory path where the folders are stored
        folders = glob.glob(os.path.join(directory, "*"))
        folders = sorted(folders, key=os.path.getctime, reverse=True)
        for folder in folders:
            if os.path.isdir(folder):
                return os.path.basename(folder)
        return None

    def get_values(self):
        self.iso = self.camera_params.get_control_value('iso')
        self.shutter_a = self.camera_params.get_control_value('shutter_a')
        self.fps = self.camera_params.get_control_value('fps')
        self.is_recording =  self.camera_params.get_recording_status()
        self.resolution = self.camera_params.get_control_value('height')

    def get_system_stats(self):
        cpu_load = str(psutil.cpu_percent()) + '%'
        cpu_temp = ('{}\u00B0'.format(int(CPUTemperature().temperature)))
        return cpu_load, cpu_temp
    
    def get_latest_folder(self):
        latest_folder = self.get_latest_folder()
        return latest_folder

    def get_latest_wav_file(self):
        latest_wav_file = self.get_latest_wav_file()
        return latest_wav_file

    def draw_display(self):
        if self.is_recording.is_set():
            self.fill_color = "red"
        else:
            self.fill_color = "black"
        image = Image.new("RGBA", self.fb.size)
        draw = ImageDraw.Draw(image)
        draw.rectangle(((0, 0), self.fb.size), fill=self.fill_color)
        font = ImageFont.truetype('/home/pi/cinemate2/fonts/smallest_pixel-7.ttf', 33)
        font2 = ImageFont.truetype('/home/pi/cinemate2/fonts/smallest_pixel-7.ttf', 233)  

        # GUI Upper line
        draw.text((10, -0), str(self.iso), font = font, align ="left", fill="white")
        draw.text((110, 0), str(self.shutter_a), font = font, align ="left", fill="white")
        draw.text((190, 0), str(self.fps), font = font, align ="left", fill="white")
        draw.text((1760, 0), str(self.cpu_load), font = font, align ="left", fill="white")
        draw.text((1860, 0), str(self.cpu_temp), font = font, align ="left", fill="white")
        # GUI Middle logo
        draw.text((400, 400), "cinepi-raw", font = font2, align ="left", fill="white")
        # GUI Lower line
        if self.drive_mounted:
            draw.text((10, 1051), str((str(self.min_left)) + " min"), font = font, align ="left", fill="white")
            
        else:
            draw.text((10, 1051), "no disk", font = font, align ="left", fill="white")

        self.fb.show(image)

    def run(self):
        try:
            self.draw_display()
            while True:
                self.get_values()
                self.cpu_load, self.cpu_temp = self.get_system_stats()
                self.drive_mounted, self.min_left = self.check_drive_mounted()
                self.draw_display()
                time.sleep(0.02)
        except Exception as e:
            print(f"Error occurred in GUI run loop: {e}")

class ManualControls(threading.Thread):
    iso_steps = [100, 200, 400, 500, 640, 800, 1000, 1200, 2000, 2500, 3200]
    shutter_angle_steps = [*range(0, 361, 1)]
    shutter_angle_steps[0] = 1
    fps_steps = [*range(0, 51, 1)]
    fps_steps[0] = 1

    def __init__(self, camera, rec_pin=None, iso_pot=0, shutter_angle_pot=2, fps_pot=4,
                 iso_inc_pin=None, iso_dec_pin=None, shu_lock_pin=None, fps_lock_pin=None, fps_switch_pin1=None, fps_switch_pin2=None, res_button_pin=None):
        threading.Thread.__init__(self)

        self.camera = camera
        self.recording = False
        self.adc = ADC()

        GPIO.setwarnings(False)  # Ignore warning for now
        GPIO.setmode(GPIO.BCM)  # Use GPIO pin numbering

        pin_configurations = [
            (rec_pin, GPIO.BOTH, self.gpio_callback),
            (iso_inc_pin, GPIO.BOTH, self.iso_inc_callback),
            (iso_dec_pin, GPIO.RISING, self.iso_dec_callback),
            (shu_lock_pin, GPIO.BOTH, self.shu_lock_callback),
            (fps_lock_pin, GPIO.BOTH, self.fps_lock_callback),
            (res_button_pin, GPIO.FALLING, self.res_button_callback),
            (fps_switch_pin1, GPIO.BOTH, self.fps_switch_callback),
            (fps_switch_pin2, GPIO.BOTH, self.fps_switch_callback)
        ]

        for pin, edge, callback in pin_configurations:
            if pin is not None:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                GPIO.add_event_detect(pin, edge, callback=callback, bouncetime=300)

        self.rec_pin = rec_pin
        
        self.iso_inc_pin = iso_inc_pin
        self.iso_dec_pin = iso_dec_pin
        
        self.shu_lock_pin = shu_lock_pin
        self.fps_lock_pin = fps_lock_pin
        
        self.fps_switch_pin1 = fps_switch_pin1
        self.fps_switch_pin2 = fps_switch_pin2
        self.res_button_pin = res_button_pin
        self.iso_pot = iso_pot
        self.shutter_angle_pot = shutter_angle_pot
        self.fps_pot = fps_pot

        self.last_iso = self.calculate_iso(self.adc.read(self.iso_pot))
        self.last_shutter_angle = self.calculate_shutter_angle(self.adc.read(self.shutter_angle_pot))
        self.last_fps = self.calculate_fps(self.adc.read(self.fps_pot))

        self.shutter_angle_locked = False
        self.fps_locked = False
        self.fps_multiplier = 1

        self.start()

    def gpio_callback(self, channel):
        if channel == self.rec_pin and GPIO.input(channel) == GPIO.HIGH:
            if not self.camera.get_recording_status().is_set():
                self.camera.start_recording()
            else:
                self.camera.stop_recording()

    def shu_lock_callback(self, channel):
        if channel == self.shu_lock_pin and GPIO.input(channel) == GPIO.HIGH:
            self.shutter_angle_locked = not self.shutter_angle_locked

    def fps_lock_callback(self, channel):
        if channel == self.fps_lock_pin and GPIO.input(channel) == GPIO.HIGH:
            self.fps_locked = not self.fps_locked

    def fps_switch_callback(self, channel):
        if GPIO.input(self.fps_switch_pin1) == GPIO.HIGH and GPIO.input(self.fps_switch_pin2) == GPIO.HIGH:
            self.fps_multiplier = 1
        elif GPIO.input(self.fps_switch_pin1) == GPIO.LOW and GPIO.input(self.fps_switch_pin2) == GPIO.HIGH:
            self.fps_multiplier = 0.5
        elif GPIO.input(self.fps_switch_pin1) == GPIO.HIGH and GPIO.input(self.fps_switch_pin2) == GPIO.LOW:
            self.fps_multiplier = 2

    def res_button_callback(self, channel):
        if channel == self.res_button_pin:
            if self.camera.get_control_value('height') == '1080':
                self.camera.set_control_value('height', '1520')
            elif self.camera.get_control_value('height') == '1520':
                self.camera.set_control_value('height', '1080')
                
    def calculate_iso_index(self, iso_value):
        iso_steps = ManualControls.iso_steps
        return iso_steps.index(iso_value)
            
    def iso_inc_callback(self, channel):
        if GPIO.input(self.iso_inc_pin) == GPIO.HIGH:
            iso_current = self.camera.get_control_value('iso')
            if iso_current is not None:
                iso_current = int(iso_current)
                iso_index = self.calculate_iso_index(iso_current)
                if iso_index < len(ManualControls.iso_steps) - 1:
                    iso_new = ManualControls.iso_steps[iso_index + 1]
                    self.camera.set_control_value('iso', iso_new)
                    self.last_iso = iso_new

    def iso_dec_callback(self, channel):
        if GPIO.input(self.iso_dec_pin) == GPIO.HIGH:
            iso_current = self.camera.get_control_value('iso')
            if iso_current is not None:
                iso_current = int(iso_current)
                iso_index = self.calculate_iso_index(iso_current)
                if iso_index > 0:
                    iso_new = ManualControls.iso_steps[iso_index - 1]
                    self.camera.set_control_value('iso', iso_new)
                    self.last_iso = iso_new

                    
    def update_parameters(self):
        iso_read = self.adc.read(self.iso_pot)
        shutter_angle_read = self.adc.read(self.shutter_angle_pot)
        fps_read = self.adc.read(self.fps_pot)

        iso_new = self.calculate_iso(iso_read)
        shutter_angle_new = self.calculate_shutter_angle(shutter_angle_read)
        fps_new = self.calculate_fps(fps_read)

        if not self.shutter_angle_locked and shutter_angle_new != self.last_shutter_angle:
            self.camera.set_control_value('shutter_a', shutter_angle_new)
            self.last_shutter_angle = shutter_angle_new
        if not self.fps_locked and fps_new != self.last_fps:
            fps_new *= self.fps_multiplier
            self.camera.set_control_value('fps', fps_new)
            self.last_fps = fps_new

        if iso_new != self.last_iso:
            self.camera.set_control_value('iso', iso_new)
            self.last_iso = iso_new

    @staticmethod
    def calculate_iso(value):
        index = round((len(ManualControls.iso_steps) - 1) * value / 999)
        return ManualControls.iso_steps[index]

    @staticmethod
    def calculate_shutter_angle(value):
        index = round((len(ManualControls.shutter_angle_steps) - 1) * value / 1000)
        return ManualControls.shutter_angle_steps[index]

    @staticmethod
    def calculate_fps(value):
        index = round((len(ManualControls.fps_steps) - 1) * value / 999)
        return ManualControls.fps_steps[index]

    def run(self):
        try:
            while True:
                self.update_parameters()
                time.sleep(0.02)
        except Exception as e:
            print(f"Error occurred in ManualControls run loop: {e}")







