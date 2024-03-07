import os
import time
import threading
from PIL import Image, ImageDraw, ImageFont
import psutil   
import subprocess
from gpiozero import CPUTemperature
from module.framebuffer import Framebuffer  # pytorinox
import traceback
import logging

class SimpleGUI(threading.Thread):
    def __init__(self, pwm_controller, redis_controller, cinepi_controller, usb_monitor, ssd_monitor, serial_handler, dmesg_monitor
                 ):
        threading.Thread.__init__(self)

        self.pwm_controller = pwm_controller
        self.redis_controller = redis_controller
        self.cinepi_controller = cinepi_controller
        self.usb_monitor = usb_monitor
        self.ssd_monitor = ssd_monitor
        self.serial_handler = serial_handler
        self.dmesg_monitor = dmesg_monitor
        
        # Get the directory of the current script
        self.current_directory = os.path.dirname(os.path.abspath(__file__))

        # Create a relative path from the current script to the font file
        self.relative_path_to_font = os.path.join(self.current_directory, '../../resources/fonts/SFCompactRounded.ttf')
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
        
        # Check if /dev/fb0 exists
        fb_path = "/dev/fb0"
        if os.path.exists(fb_path):
            self.fb = Framebuffer(0)
            self.disp_width, self.disp_height = self.fb.size
        else:
            logging.info(f"No HDMI display found")    

        self.start()
        
        logging.info(f"Simple GUI instantiated. HDMI {self.fb.size}")

    def get_values(self):
        self.iso = self.redis_controller.get_value("iso")
        self.shutter_a = (str(self.redis_controller.get_value('shutter_a')).replace('.0', ''))
        self.shutter_a_nom = (str(self.redis_controller.get_value('shutter_a_nom')).replace('.0', ''))
        self.fps = int(self.cinepi_controller.fps_actual)
        self.is_recording = int(self.redis_controller.get_value('is_writing_buf'))
        self.latest_frame = False
        
        self.min_left = None
        
        self.file_size = self.cinepi_controller.file_size
        
        if self.ssd_monitor.last_space_left and self.ssd_monitor.disk_mounted:
            self.min_left = round(int((self.ssd_monitor.last_space_left * 1000) / (self.file_size * float(self.cinepi_controller.fps_actual) * 60)),0)

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
            if self.is_recording == 1:
                self.fill_color = "red"
            else:
                self.fill_color = "black"
            image = Image.new("RGBA", self.fb.size)
            draw = ImageDraw.Draw(image)
            draw.rectangle(((0, 0), self.fb.size), fill=self.fill_color)
            font = ImageFont.truetype(os.path.realpath(self.relative_path_to_font), 34)
            font2 = ImageFont.truetype(os.path.realpath(self.relative_path_to_font), 51)
            font3 = ImageFont.truetype(os.path.realpath(self.relative_path_to_font), 28)
            font4 = ImageFont.truetype(os.path.realpath(self.relative_path_to_font), 26)
            font5 = ImageFont.truetype(os.path.realpath(self.relative_path_to_font), 16)

            self.exposure_time = int((float(self.shutter_a)/360)*(1/float(self.fps))*1000000)

            if self.cinepi_controller.gui_layout == 0:

                # GUI Upper line
                
                # if self.cinepi_controller.iso_lock == False:
                #     # Draw a grey box around the ISO text
                #     iso_box_coords = (0, -5, 92, 34)  # Adjust these coordinates as needed
                #     draw.rectangle(iso_box_coords, fill=(100,100,100,255))
                
                draw.text((10, -7), str(self.iso), font=font, fill="white")

                if self.cinepi_controller.pwm_mode == False:
                    draw.text((110, -7), str(self.shutter_a), font=font, fill="white")
                    draw.text((205, -7), str(self.fps), font=font, fill="white")
                elif self.cinepi_controller.pwm_mode == True:
                    draw.text((110, -7), str(self.pwm_controller.shutter_angle), font=font, fill="lightgreen")
                    draw.text((205, -7), str(int(round(float(self.pwm_controller.fps),0))), font=font, fill="lightgreen")
                    
                if self.cinepi_controller.fps_double == True:
                    draw.text((205, -7), str(self.fps), font=font, fill="lightgreen")
                    draw.text((1090, -2), 'FPS SW', font=font4, fill="lightgreen")
                
                draw.text((1210, -7), str(self.cinepi_controller.exposure_time_fractions), font=font, fill="white")
                if self.cinepi_controller.pwm_mode == True:
                    draw.text((1323, -2), 'PWM', font=font4, fill="lightgreen")
                
                if self.cinepi_controller.shutter_a_sync == True:
                    draw.text((1425, -2), 'SYNC   /', font=font4, fill="white")
                    draw.text((1525, -2), str(self.shutter_a_nom), font=font4, fill="white")
                    
                if self.cinepi_controller.parameters_lock == True:
                    draw.text((1610, -2), 'LOCK', font=font4, fill=(255,0,0,255))

                if self.dmesg_monitor.undervoltage_flag:
                    if self.is_recording:
                        draw.text((1700, -2), str('VOLT'), font=font4, fill="black")
                    else:                        
                        draw.text((1700, -2), str('VOLT'), font=font4, fill="yellow")
                
                draw.text((1790, -2), str(self.cpu_load), font=font4, fill="white")
                draw.text((1875, -2), str(self.cpu_temp), font=font4, fill="white")
            
                # GUI Lower line
                if self.min_left:
                    draw.text((10, 1044), str(self.min_left) + " MIN", font=font, fill="white")
                else:
                    draw.text((10, 1044), 'NO DISK', font=font, fill="white")
                    
                if self.usb_monitor.usb_mic:
                    draw.text((160, 1050), 'MIC', font=font4, fill="white")
                    
                if self.usb_monitor.usb_keyboard:
                    draw.text((225, 1050), 'KEY', font=font4, fill="white")

                if '/dev/ttyACM0' in self.serial_handler.current_ports:
                    draw.text((290, 1050), 'SER', font=font4, fill="white")

                if self.wav_recorded:
                    draw.text((1445, 1050), ' |   WAV', font=font4, fill="white")
                
            if self.cinepi_controller.gui_layout == 1:
                
                # GUI Upper line
                draw.text((0, -7), str(self.iso), font=font2, fill=("white"))
                if self.cinepi_controller.pwm_mode == False:
                    draw.text((10, 80), str(self.shutter_a), font=font2, fill="white")
                    draw.text((10, 167), str(self.fps), font=font2, fill="white")
                elif self.cinepi_controller.pwm_mode == True:
                    draw.text((10, 80), str(self.pwm_controller.shutter_angle), font=font2, fill="lightgreen")
                    draw.text((10, 167), str(int(round(float(self.pwm_controller.fps),0))), font=font2, fill="lightgreen")
                    
                if self.cinepi_controller.fps_double == True:
                    draw.text((10, 260), 'FPS SW', font=font, fill="lightgreen")
                    draw.text((10, 167), str(self.fps), font=font2, fill="lightgreen")
                
                draw.text((10, 340), str(self.cinepi_controller.exposure_time_fractions), font=font2, fill="white")

                if self.cinepi_controller.pwm_mode == True:
                    draw.text((10, 427), 'PWM', font=font, fill="lightgreen")

                if self.cinepi_controller.shutter_a_sync == True:
                    draw.text((10, 495), 'SYNC', font=font, fill="white")
                    draw.text((10, 540), str(self.shutter_a_nom), font=font, fill="white")
                    
                if self.cinepi_controller.parameters_lock == True:
                    draw.text((10, 610), 'LOCK', font=font, fill=(255,0,0,255))
                
                if self.dmesg_monitor.undervoltage_flag:
                    if self.is_recording:
                        draw.text((10, 680), str('VOLTAGE'), font=font, fill="black")
                    else:
                        draw.text((10, 680), str('VOLTAGE'), font=font, fill="yellow")   
                    

                draw.text((1740, -7), str(self.cpu_load), font=font, fill="white")
                draw.text((1860, -7), str(self.cpu_temp), font=font, fill="white")
                
                # GUI Lower line
                if self.min_left:
                    draw.text((10, 1044), str(self.min_left) + " MIN", font=font, fill="white")
                else:
                    draw.text((10, 1044), 'NO DISK', font=font, fill="white")
                    
                if self.usb_monitor.usb_mic:
                    draw.text((10, 910), 'MIC', font=font4, fill="white")
                    
                if self.usb_monitor.usb_keyboard:
                    draw.text((10, 950), 'KEY', font=font4, fill="white")

                if '/dev/ttyACM0' in self.serial_handler.current_ports:
                    draw.text((10, 990), 'SER', font=font4, fill="white")

            # if self.cinepi_controller.gui_layout == 2:
                
            #     # GUI Upper line
            #     draw.text((-3, -7), str(self.iso), font=font, fill=("white"))
            #     if self.cinepi_controller.pwm_mode == False:
            #         draw.text((-3, 80), str(self.shutter_a), font=font, fill="white")
            #         draw.text((-3, 167), str(self.fps), font=font, fill="white")
            #     elif self.cinepi_controller.pwm_mode == True:
            #         draw.text((-3, 80), str(self.pwm_controller.shutter_angle), font=font, fill="lightgreen")
            #         draw.text((-3, 167), str(int(round(float(self.pwm_controller.fps),0))), font=font, fill="lightgreen")
                    
            #     if self.cinepi_controller.fps_double == True:
            #         draw.text((-3, 260), 'FPS SW', font=font, fill="lightgreen")
            #         draw.text((-3, 167), str(self.fps), font=font, fill="lightgreen")
                
            #     draw.text((-3, 340), str(self.cinepi_controller.exposure_time_fractions), font=font, fill="white")

            #     if self.cinepi_controller.pwm_mode == True:
            #         draw.text((-3, 427), 'PWM', font=font3, fill="lightgreen")

            #     if self.cinepi_controller.shutter_a_sync == True:
            #         draw.text((-3, 495), 'SYNC', font=font3, fill="white")
            #         draw.text((-3, 540), str(self.shutter_a_nom), font=font, fill="white")
                    
            #     if self.cinepi_controller.parameters_lock == True:
            #         draw.text((-3, 610), 'LOCK', font=font3, fill=(255,0,0,255))
                
            #     if self.dmesg_monitor.undervoltage_flag:
            #         if self.is_recording:
            #             draw.text((-3, 680), str('VOLTAGE'), font=font, fill="black")
            #         else:
            #             draw.text((-3, 680), str('VOLTAGE'), font=font, fill="yellow")   

            #     draw.text((1862, -7), str(self.cpu_load), font=font4, fill="white")
            #     draw.text((1862, 21), str(self.cpu_temp), font=font4, fill="white")
                
            #     # GUI Lower line
            #     if self.min_left:
            #         draw.text((-3, 1044), str(self.min_left) + " MIN", font=font4, fill="white")
            #     else:
            #         draw.text((-3, 1044), 'NO DISK', font=font4, fill="white")
                    
            #     if self.usb_monitor.usb_mic:
            #         draw.text((-3, 910), 'MIC', font=font4, fill="white")
                    
            #     if self.usb_monitor.usb_keyboard:
            #         draw.text((-3, 950), 'KEY', font=font4, fill="white")

            #     if '/dev/ttyACM0' in self.serial_handler.current_ports:
            #         draw.text((-3, 990), 'SER', font=font4, fill="white")

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

# Here is the complete script with detailed implementation, including dummy placeholders
# for external module references and methods that need to be filled with actual logic.

# import os
# import time
# import threading
# from PIL import Image, ImageDraw, ImageFont
# import subprocess
# import logging

# import logging
# import traceback

# # Setting up basic logging configuration
# logging.basicConfig(level=logging.INFO, filename='simple_gui.log', filemode='a',
#                     format='%(asctime)s - %(levelname)s - %(message)s')


# # Placeholder for the Framebuffer class and other external modules not defined here
# class Framebuffer:
#     def __init__(self, index):
#         self.size = (1920, 1080)  # Default resolution
#     def show(self, image):
#         pass  # Placeholder for displaying an image on the framebuffer

# class SimpleGUI(threading.Thread):
#     def __init__(self, pwm_controller, redis_controller, cinepi_controller, usb_monitor, ssd_monitor, serial_handler, dmesg_monitor):
#         threading.Thread.__init__(self)

#         # Controllers and monitors
#         self.pwm_controller = pwm_controller
#         self.redis_controller = redis_controller
#         self.cinepi_controller = cinepi_controller
#         self.usb_monitor = usb_monitor
#         self.ssd_monitor = ssd_monitor
#         self.serial_handler = serial_handler
#         self.dmesg_monitor = dmesg_monitor

#         # Paths
#         self.current_directory = os.path.dirname(os.path.abspath(__file__))
#         self.relative_path_to_font = os.path.join(self.current_directory, '../../resources/fonts/SFCompactRounded.ttf')

#         # Framebuffer
#         self.fb = Framebuffer(0)
#         self.disp_width, self.disp_height = self.fb.size

#         # Initial values
#         self.init_values()

#         # Hide the cursor and start GUI
#         self.hide_cursor()
#         self.check_fb_existence()
#         self.start()
        
#         logging.info(f"Simple GUI instantiated. HDMI {self.fb.size}")

#     def init_values(self):
#         """Initialize or reset GUI values."""
#         self.iso = "100"
#         self.shutter_a = "1/50"
#         self.fps = 24
#         self.is_recording = False
#         self.min_left = 120
#         self.cpu_load = "5%"
#         self.cpu_temp = "60°C"

#     def get_values(self):
#         """Fetch and update GUI values."""
#         # Example fetching method, needs implementation
#         # This is where you would update the properties like self.iso, self.shutter_a, etc.
#         pass

#     def hide_cursor(self):
#         """Hide the cursor in the framebuffer display."""
#         try:
#             subprocess.call(["sudo", "sh", "-c", "echo 0 > /sys/class/graphics/fbcon/cursor_blink"])
#         except Exception as e:
#             print(f"Error occurred while hiding cursor: {e}")

#     def check_fb_existence(self):
#         """Check framebuffer device existence and log if not found."""
#         fb_path = "/dev/fb0"
#         if not os.path.exists(fb_path):
#             logging.info("No HDMI display found")

#     def draw_objects(self, layout_id):
#         try:
#             """Draw GUI elements based on the layout and actual values."""
#             layout = self.define_layouts()[layout_id]
#             actual_values = self.populate_values()

#             # if self.is_recording == 1:
#             #     self.fill_color = "red"
#             # else:
#             self.fill_color = "black"
#             image = Image.new("RGBA", self.fb.size)
#             draw = ImageDraw.Draw(image)
#             draw.rectangle(((0, 0), self.fb.size), fill=self.fill_color)

#             for key, value in layout.items():
#                 coords = value['coords']
#                 font_size = value['font_size']
#                 color = value.get('color', 'white')  # Default to white if color is not specified
#                 text = str(actual_values.get(key, ''))  # Default to empty string if key not found

#                 font = ImageFont.truetype(os.path.realpath(self.relative_path_to_font), font_size)
#                 draw.text(coords, text, font=font, fill=color)

#             self.fb.show(image)
#         except OSError as e:
#             print(f"Error occurred in draw_display: {e}")

#     def define_layouts(self):
#         """Define GUI layouts with their properties."""
#         return {
#             0: {
#                 'iso': {'coords': (10, -7), 'font_size': 24, 'color': 'white'},
#                 'shutter_speed': {'coords': (10, 40), 'font_size': 24, 'color': 'white'},
#                 'fps': {'coords': (10, 70), 'font_size': 24, 'color': 'white'},
#                 'cpu_load': {'coords': (10, 100), 'font_size': 24, 'color': 'white'},
#                 'cpu_temp': {'coords': (10, 130), 'font_size': 24, 'color': 'white'},
#             },
#             1: {
#                 # Different layout for demonstration
#             },
#             2: {
#                 # Different layout for demonstration
#             },
#         }

#     def populate_values(self):
#         """Populate a dictionary with actual values for GUI elements."""
#         #self.get_values()  # Ensure values are updated
#         return {
#             'iso': self.iso,
#             'shutter_speed': self.shutter_a,
#             'fps': self.fps,
#             'cpu_load': self.cpu_load,
#             'cpu_temp': self.cpu_temp,
#         }

#     def run(self):
#         """Main GUI loop."""

#         try:
#             while True:
#                 self.draw_objects(self.cinepi_controller.gui_layout)
#                 time.sleep(0.2)

#         except Exception as e:
#             error_msg = f"Error occurred in 'run' loop of SimpleGUI: {e}\n"
#             error_msg += "Exception type: " + str(type(e)) + "\n"
#             error_msg += "Exception args: " + str(e.args) + "\n"
#             error_msg += "Traceback: "
#             error_msg += ''.join(traceback.format_tb(e.__traceback__))
#             print(error_msg)