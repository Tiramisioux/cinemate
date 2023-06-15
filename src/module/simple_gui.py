import os
import time
import threading
from PIL import Image, ImageDraw, ImageFont
import os
import time
import threading
from PIL import Image, ImageDraw, ImageFont
import psutil
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

        # Frame buffer coordinates
        self.fill_color = "black"

        # Initialize CameraControls and Monitor
        self.controller = controller
        self.monitor = monitor
        self.monitor.register_connection_callback(self.drive_status_changed)

        self.iso = None
        self.shutter_a = None
        self.fps = None
        self.is_recording = None

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
        drive_mounted = False
        min_left = None

        if self.drive_connected:
            drive_mounted = True
            free_bytes = self.monitor.get_remaining_space()
            if free_bytes is not None:
                if self.controller.get_control_value('height') == "1080":
                    file_size = 3.2
                elif self.controller.get_control_value('height') == "1520":
                    file_size = 4.8
                else:
                    file_size = 0.0

                min_left = int((free_bytes / 1000000) / (file_size * int(self.controller.get_control_value('fps')) * 60))
        else:
            min_left = 0  # Set to 0 when the drive is not connected

        return drive_mounted, min_left


    def get_values(self):
        self.iso = self.controller.get_control_value('iso')
        self.shutter_a = self.controller.get_control_value('shutter_a')
        self.fps = self.controller.get_control_value('fps')
        self.is_recording = self.controller.get_recording_status()

    def get_system_stats(self):
        cpu_load = str(psutil.cpu_percent()) + '%'
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

            # Get the latest values from the monitor object
            last_subfolder = self.monitor.last_created_folder
            last_wav = self.monitor.last_created_wav_file
            last_frame_count = self.monitor.last_folder_file_count

            if last_subfolder is None:
                last_subfolder = "N/A"
            elif isinstance(last_subfolder, str):
                last_subfolder = last_subfolder[11:]  # Exclude the first 12 characters

            if last_wav is None:
                last_wav = "N/A"
            elif isinstance(last_wav, str):
                if last_subfolder[:22] == last_wav[:22]:
                    last_wav = "+ WAV"
                else:
                    last_wav = "N/A"
                    
            if last_frame_count is None:
                last_frame_count = "N/A"
            # elif isinstance(last_frame_count, str):
            #     last_frame_count = str(last_frame_count)

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
            draw.text((1325, 1051), f"{last_wav}", font=font, align="left", fill="white")
            draw.text((1525, 1051), f"{last_frame_count}", font=font, align="left", fill="white")
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
