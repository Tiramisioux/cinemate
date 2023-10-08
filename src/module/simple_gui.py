import os
import time
import threading
from PIL import Image, ImageDraw, ImageFont
import psutil   
import subprocess
from gpiozero import CPUTemperature
from module.framebuffer import Framebuffer  # pytorinox
import traceback

class SimpleGUI(threading.Thread):
    def __init__(self, redis_controller, usb_monitor, ssd_monitor, serial_handler):
        threading.Thread.__init__(self)

        self.redis_controller = redis_controller
        self.usb_monitor = usb_monitor
        self.ssd_monitor = ssd_monitor
        self.serial_handler = serial_handler
        
        # Get the directory of the current script
        self.current_directory = os.path.dirname(os.path.abspath(__file__))

        # Create a relative path from the current script to the font file
        self.relative_path_to_font = os.path.join(self.current_directory, '../../resources/fonts/Arial.ttf')
        self.relative_path_to_font2 = os.path.join(self.current_directory, '../../resources/fonts/smallest_pixel-7.ttf')
        self.relative_path_to_font3 = os.path.join(self.current_directory, '../../resources/fonts/smallest_pixel-7.ttf')

        # Frame buffer coordinates
        self.fb = Framebuffer(0)
        self.cx = self.fb.size[0] // 2
        self.cy = self.fb.size[1] // 2

        # Frame buffer coordinates
        self.fill_color = "black"

        #Inital values
        self.iso = None
        self.shutter_a = None
        self.fps = None

        self.drive_connected = False
        self.min_left = None

        self.cpu_load = None
        self.cpu_temp = None
        
        self.mic_connected = None
        
        self.last_created_dng = None
        self.last_created_wav = None
        
        self.wav_recorded = False
        
        self.height_value = None
        
        self.latest_frame = None
            
        self.latest_wav = None  
        
         # Hide the cursor
        self.hide_cursor() 

        self.start()

    def get_values(self):
        self.iso = self.redis_controller.get_value("iso")
        self.shutter_a = self.redis_controller.get_value('shutter_a')
        self.fps = self.redis_controller.get_value('fps')
        self.is_recording = False
        self.latest_frame = None
        
        # This check prevents 'NoneType' object has no attribute 'writing_to_drive' error.
        if hasattr(self.ssd_monitor.directory_watcher, 'writing_to_drive'):
            self.is_recording = self.ssd_monitor.directory_watcher.writing_to_drive
            self.latest_frame = self.ssd_monitor.directory_watcher.last_dng_file_added
            self.latest_wav = self.ssd_monitor.directory_watcher.last_wav_file_added
        
        if self.latest_frame is not None:
            self.latest_frame = self.latest_frame[-43:]
            
        if self.latest_wav is not None:   
            self.latest_wav = self.latest_wav[-40:]
            
        if self.latest_frame and self.latest_wav and self.latest_frame[:22] == self.latest_wav[:22]:
            self.wav_recorded = True
        else:
            self.wav_recorded = False
        
        self.min_left = None
        
        self.height_value = self.redis_controller.get_value('height')
        if self.height_value == "1080":
            self.file_size = 3.2
        elif self.height_value == "1520":
            self.file_size = 4.8
        
        fps_value = self.redis_controller.get_value('fps')
        if self.ssd_monitor.last_space_left is not None and self.file_size is not None and fps_value is not None:
            self.min_left = int((self.ssd_monitor.last_space_left * 1000) / (self.file_size * int(fps_value) * 60))
        else:
            self.min_left = None

        # Get CPU statistics
        self.cpu_load = str(psutil.cpu_percent()) + '%'
        self.cpu_temp = ('{}\u00B0'.format(int(CPUTemperature().temperature)))

    def hide_cursor(self):
        try:
            subprocess.call(["sudo", "sh", "-c", "echo 0 > /sys/class/graphics/fbcon/cursor_blink"])  # Execute command to hide cursor
        except Exception as e:
            print(f"Error occurred while hiding cursor: {e}")

    def draw_display(self):
        try:
            if self.is_recording:
                self.fill_color = "red"
            else:
                self.fill_color = "black"
            image = Image.new("RGBA", self.fb.size)
            draw = ImageDraw.Draw(image)
            draw.rectangle(((0, 0), self.fb.size), fill=self.fill_color)
            font = ImageFont.truetype(os.path.realpath(self.relative_path_to_font), 30)
            font2 = ImageFont.truetype(os.path.realpath(self.relative_path_to_font2), 233)
            font3 = ImageFont.truetype(os.path.realpath(self.relative_path_to_font3), 63)
            font4 = ImageFont.truetype(os.path.realpath(self.relative_path_to_font), 26)

            # GUI Upper line
            draw.text((10, -2), str(self.iso), font=font, fill="white")
            draw.text((110, -2), str(self.shutter_a), font=font, fill="white")
            draw.text((205, -2), str(self.fps), font=font, fill="white")
            draw.text((1740, -2), str(self.cpu_load), font=font, fill="white")
            draw.text((1860, -2), str(self.cpu_temp), font=font, fill="white")
            # GUI Middle logo
            draw.text((410, 400), "cinepi-raw", font=font2, fill="white")
            draw.text((760, 640), "by Csaba Nagy", font=font3, fill="white")
            
            if self.height_value == "1080":
            
                # GUI Lower line
                if self.ssd_monitor.disk_mounted and self.ssd_monitor.last_space_left:
                    draw.text((10, 1051), str(self.min_left) + " MIN", font=font, fill="white")
                else:
                    draw.text((10, 1051), 'NO DISK', font=font, fill="white")
                    
                if self.usb_monitor.usb_mic:
                    draw.text((160, 1051), 'MIC', font=font, fill="white")
                    
                if self.usb_monitor.usb_keyboard:
                    draw.text((250, 1051), 'KEY', font=font, fill="white")

                if '/dev/ttyACM0' in self.serial_handler.current_ports:
                    draw.text((345, 1051), 'SER', font=font, fill="white")

                if self.latest_frame is not None:
                    draw.text((600, 1051), str(self.latest_frame), font=font, fill="white")

                if self.wav_recorded:
                    draw.text((1345, 1051), ' |   WAV', font=font, fill="white")
                
            elif self.height_value == "1520":
                
                # GUI Lower line
                if self.ssd_monitor.disk_mounted and self.ssd_monitor.last_space_left:
                    draw.text((10, 1051), str(self.min_left) + " MIN", font=font, fill="white")
                else:
                    draw.text((10, 1051), 'NO DISK', font=font, fill="white")
                    
                if self.usb_monitor.usb_mic:
                    draw.text((10, 850), 'MIC', font=font, fill="grey")
                    
                if self.usb_monitor.usb_keyboard:
                    draw.text((10, 910), 'KEY', font=font, fill="grey")

                if '/dev/ttyACM0' in self.serial_handler.current_ports:
                    draw.text((10, 970), 'SER', font=font, fill="grey")

                if self.latest_frame:
                    text = str(self.latest_frame)
                    words = text.split('_')
                    lines = []
                    max_width_in_words = 1  # Approximate number of words you expect per line. Adjust as needed.
                    
                    while words:
                        line = ' '.join(words[:max_width_in_words])
                        lines.append(line)
                        words = words[max_width_in_words:]

                    y_position = 500
                    line_height = 30 + 8  # Assuming 5 pixels of padding between lines

                    for line in lines:
                        draw.text((10, y_position), line, font=font, fill="grey")
                        y_position += line_height

                if self.wav_recorded:
                    draw.text((10, 705), 'WAV', font=font, fill="grey")


            self.fb.show(image)
        except OSError as e:
            print(f"Error occurred in draw_display: {e}")
            
    def wrap_text(self, text, font, max_width):
        """
        Wrap the text based on the given font and max_width.
        Returns a list of text lines.
        """
        lines = []
        words = text.split()
        while words:
            line = ''
            while words and font.getsize(line + words[0])[0] <= max_width:
                line += (words.pop(0) + ' ')
            lines.append(line)
        return lines

    def run(self):
        try:
            while True:
                self.get_values()
                self.draw_display()
                time.sleep(0.1)
        except Exception as e:
            error_msg = f"Error occurred in 'run' loop of SimpleGUI: {e}\n"
            error_msg += "Exception type: " + str(type(e)) + "\n"
            error_msg += "Exception args: " + str(e.args) + "\n"
            error_msg += "Traceback: "
            error_msg += ''.join(traceback.format_tb(e.__traceback__))
            print(error_msg)
