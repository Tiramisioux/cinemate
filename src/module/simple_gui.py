import os
import time
import threading
from PIL import Image, ImageDraw, ImageFont
import os
import time
import threading
from PIL import Image, ImageDraw, ImageFont
from psutil import cpu_percent
from shutil import disk_usage
import pathlib
import subprocess
from gpiozero import CPUTemperature
from module.framebuffer import Framebuffer  # pytorinox

class SimpleGUI(threading.Thread):
    def __init__(self, controller, monitor):
        threading.Thread.__init__(self)

        # Frame buffer coordinates
        self.fb = Framebuffer(0)
        self.cx = self.fb.size[0] // 2
        self.cy = self.fb.size[1] // 2

        self.fill_color = "black"

        # Initialize CameraControls and Monitor
        self.controller = controller
        self.monitor = monitor
        self.monitor.register_connection_callback(self.drive_status_changed)
        self.check_drive_mounted()

        self.iso = None
        self.shutter_a = None
        self.fps = None
        self.is_recording = None
        self.resolution = None

        # Get initial values
        self.get_values()
        
        self.drive_connected = self.monitor.is_drive_connected()    

        self.drive_mounted, self.min_left = self.check_drive_mounted()

        # Get cpu statistics
        self.cpu_load, self.cpu_temp = self.get_system_stats()
        
        self.hide_cursor()  # Hide the cursor
        
        self.start()
    
    def hide_cursor(self):
        try:
            subprocess.call(["sudo", "sh", "-c", "echo 0 > /sys/class/graphics/fbcon/cursor_blink"])  # Execute command to hide cursor
        except Exception as e:
            print(f"Error occurred while hiding cursor: {e}")
        
    def drive_status_changed(self):
        self.drive_mounted, self.min_left = self.check_drive_mounted()

    def check_drive_mounted(self):
        drive_mounted = 0  # Default to 0
        min_left = None  # Default to None
    
        if self.monitor.is_drive_connected():
            free_bytes = self.monitor.get_remaining_space()
            drive_mounted = 1
            if self.controller.get_control_value('height') == "1080":
                self.file_size = 3.2
            if self.controller.get_control_value('height') == "1520":
                self.file_size = 4.8
            
            min_left = int((free_bytes / 1000000) / (self.file_size * int(self.controller.get_control_value('fps')) * 60))
        else:
            self.drive_mounted = 0
            self.min_left = None
        return drive_mounted, min_left
    
    def get_values(self):
        self.iso = self.controller.get_control_value('iso')
        self.shutter_a = self.controller.get_control_value('shutter_a')
        self.fps = self.controller.get_control_value('fps')
        self.is_recording = self.controller.get_recording_status()
        self.resolution = self.controller.get_control_value('height')

    def get_system_stats(self):
        cpu_load = str(cpu_percent()) + '%'
        cpu_temp = ('{}\u00B0'.format(int(CPUTemperature().temperature)))
        return cpu_load, cpu_temp
    
    def draw_display(self):
        try:
            if self.is_recording:
                self.fill_color = "red"
            else:
                self.fill_color = "black"
            image = Image.new("RGBA", self.fb.size)
            draw = ImageDraw.Draw(image)
            draw.rectangle(((0, 0), self.fb.size), fill=self.fill_color)
            font = ImageFont.truetype('/home/pi/cinemate2/resources/fonts/smallest_pixel-7.ttf', 33)
            font2 = ImageFont.truetype('/home/pi/cinemate2/resources/fonts/smallest_pixel-7.ttf', 233)  

            # Get the latest values from the monitor
            last_subfolder = self.monitor.get_last_created_folder()
            # scratch_track_recorded = self.monitor.scratch_track_recorded()
            last_folder_file_count = self.monitor.get_file_count_of_last_created_folder()

            if last_subfolder is None:
                last_subfolder = "N/A"
            elif isinstance(last_subfolder, str):
                last_subfolder = last_subfolder[11:]  # Exclude the first 12 characters

            #     last_wav_file = "WAVE"
            # else:
            #     last_wav_file = "N/A"
            if last_folder_file_count is None:
                last_folder_file_count = "N/A"

            # GUI Upper line
            draw.text((10, -0), str(self.iso), font=font, align="left", fill="white")
            draw.text((110, 0), str(self.shutter_a), font=font, align="left", fill="white")
            draw.text((190, 0), str(self.fps), font=font, align="left", fill="white")
            draw.text((1760, 0), str(self.cpu_load), font=font, align="left", fill="white")
            draw.text((1860, 0), str(self.cpu_temp), font=font, align="left", fill="white")
            # GUI Middle logo
            draw.text((400, 400), "cinepi-raw", font=font2, align="left", fill="white")
            # GUI Lower line
            if self.drive_mounted:
                draw.text((10, 1051), str((str(self.min_left)) + " min"), font=font, align="left", fill="white")
            else:
                draw.text((10, 1051), "no disk", font=font, align="left", fill="white")
                
            draw.text((725, 1051), f"{last_subfolder}", font=font, align="left", fill="white")
            # draw.text((1325, 1051), last_wav_file, font=font, align="left", fill="white")
            draw.text((1525, 1051), f"{last_folder_file_count}", font=font, align="left", fill="white")

            self.fb.show(image)
        except OSError as e:
            print(f"Error occurred in draw_display: {e}")

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