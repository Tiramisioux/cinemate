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
    def __init__(self, cinepi, controller, monitor):
        threading.Thread.__init__(self)

        # Frame buffer coordinates
        self.fb = Framebuffer(0)
        self.cx = self.fb.size[0] // 2
        self.cy = self.fb.size[1] // 2

        # Frame buffer coordinates
        self.fill_color = "black"

        self.cinepi = cinepi
        self.controller = controller
        self.monitor = monitor

        self.iso = None
        self.shutter_a = None
        self.fps = None
        self.is_recording = None

        self.drive_connected = False
        self.min_left = None

        self.cpu_load = None
        self.cpu_temp = None
        
        self.mic_connected = None

         # Hide the cursor
        self.hide_cursor() 

        self.start()

    def hide_cursor(self):
        try:
            subprocess.call(["sudo", "sh", "-c", "echo 0 > /sys/class/graphics/fbcon/cursor_blink"])  # Execute command to hide cursor
        except Exception as e:
            print(f"Error occurred while hiding cursor: {e}")

    def get_values(self):
        self.iso = self.controller.get_control_value('iso')
        self.shutter_a = self.controller.get_control_value('shutter_a')
        self.fps = self.controller.get_control_value('fps')
        self.is_recording = self.controller.get_recording_status()
        
        self.drive_connected = self.monitor.connection_status
        self.min_left = None

        if self.drive_connected:
            free_bytes = self.monitor.last_free_space
            if free_bytes is not None:
                if self.controller.get_control_value('height') == "1080":
                    file_size = 3.2
                elif self.controller.get_control_value('height') == "1520":
                    file_size = 4.8
                else:
                    file_size = 0.0

                self.min_left = int((free_bytes / 1000000) / (file_size * int(self.controller.get_control_value('fps')) * 60))
        
        else:
            self.min_left = 0  # Set to 0 when the drive is not connected
            
        if self.cinepi.USBMonitor.usb_mic:
            self.mic_connected = "MIC"
        else:
            self.mic_connected = ""
            
        if self.cinepi.USBMonitor.usb_keyboard:
            self.keyboard_connected = "KEYBOARD"
        else:
            self.keyboard_connected = ""
            

        # Get cpu statistics
        self.cpu_load = str(psutil.cpu_percent()) + '%'
        self.cpu_temp = ('{}\u00B0'.format(int(CPUTemperature().temperature)))

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
            font3 = ImageFont.truetype('/home/pi/cinemate2/resources/fonts/smallest_pixel-7.ttf', 63)

            # GUI Upper line
            draw.text((10, -0), str(self.iso), font=font, align="left", fill="white")
            draw.text((110, 0), str(self.shutter_a), font=font, align="left", fill="white")
            draw.text((190, 0), str(self.fps), font=font, align="left", fill="white")
            draw.text((1760, 0), str(self.cpu_load), font=font, align="left", fill="white")
            draw.text((1860, 0), str(self.cpu_temp), font=font, align="left", fill="white")
            # GUI Middle logo
            draw.text((410, 400), "cinepi-raw", font=font2, align="left", fill="white")
            draw.text((760, 640), "by Csaba Nagy", font=font3, align="left", fill="white")
            # GUI Lower line
            if self.drive_connected:
                draw.text((10, 1051), str((str(self.min_left)) + " min"), font=font, align="left", fill="white")
            else:
                draw.text((10, 1051), "no disk", font=font, align="left", fill="white")

            draw.text((335, 1051), f"{self.keyboard_connected}", font=font, align="left", fill="white")
            # draw.text((1325, 1051), f"{self.last_wav}", font=font, align="left", fill="white")
            draw.text((200, 1051), f"{self.mic_connected}", font=font, align="left", fill="white")
            self.fb.show(image)
        except OSError as e:
            print(f"Error occurred in draw_display: {e}")

    def run(self):
        try:
            while True:
                self.get_values()
                self.draw_display()
                time.sleep(0.05)
        except Exception as e:
            print(f"Error occurred in GUI run loop: {e}")