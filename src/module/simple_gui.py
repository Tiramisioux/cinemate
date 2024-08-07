import os
import threading
import time
from PIL import Image, ImageDraw, ImageFont
import psutil
from gpiozero import CPUTemperature
from module.framebuffer import Framebuffer  # Assuming this is a custom module
import subprocess
import logging
from sugarpie import pisugar

class SimpleGUI(threading.Thread):
    def __init__(self, pwm_controller, redis_controller, cinepi_controller, usb_monitor, ssd_monitor, serial_handler, dmesg_monitor, battery_monitor):
        threading.Thread.__init__(self)
        self.setup_resources()
        self.check_display()
        self.color_mode = "normal"  # Can be changed to "inverse" as needed
        
        self.pwm_controller = pwm_controller
        self.redis_controller = redis_controller
        self.cinepi_controller = cinepi_controller
        self.usb_monitor = usb_monitor
        self.ssd_monitor = ssd_monitor
        self.serial_handler = serial_handler
        self.dmesg_monitor = dmesg_monitor
        self.battery_monitor = battery_monitor
        
        self.start()

    def check_display(self):
        fb_path = "/dev/fb0"
        if os.path.exists(fb_path):
            self.fb = Framebuffer(0)
            self.disp_width, self.disp_height = self.fb.size
            logging.info(f"HDMI display found. {self.disp_width, self.disp_height}")
            self.scaling_width = self.disp_width / 1920
            self.scaling_height = self.disp_height / 1080
        else:
            logging.info("No HDMI display found")
        
    def setup_resources(self):
        self.current_directory = os.path.dirname(os.path.abspath(__file__))
        self.font_path = os.path.join(self.current_directory, '../../resources/fonts/SFCompactRounded.ttf')

        # Define two layouts
        self.layouts = {
            0: {  # Layout 0
                "iso": {"position": (10, -7), "font_size": 34},
                "shutter_speed": {"position": (110, -7), "font_size": 34},
                "fps": {"position": (205, -7), "font_size": 34},
                
                "exposure_time": {"position": (1210, -7), "font_size": 34},
                "pwm_mode": {"position": (1323, -2), "font_size": 26},
                "shutter_a_sync": {"position": (1425, -2), "font_size": 26},
                "lock": {"position": (1610, -2), "font_size": 26},
                "low_voltage": {"position": (1700, -2), "font_size": 26},
                
                "cpu_load": {"position": (1780, -2), "font_size": 26},
                "cpu_temp": {"position": (1860, -2), "font_size": 26},
                
                "disk_space": {"position": (10, 1044), "font_size": 34},
                
                "mic": {"position": (160, 1050), "font_size": 26},
                "key": {"position": (250, 1050), "font_size": 26},
                "serial": {"position": (345, 1050), "font_size": 26},
                
                "battery_level": {"position": (1830, 1044), "font_size": 34},
                # Additional elements as needed for layout 0
            },
            1: {  # Layout 1
                "iso": {"position": (0, -7), "font_size": 51},
                "shutter_speed": {"position": (10, 80), "font_size": 51},
                "fps": {"position": (10, 167), "font_size": 51},
                
                "exposure_time": {"position": (10, 340), "font_size": 34},
                "pwm_mode": {"position": (10, 427), "font_size": 34},
                "shutter_a_sync": {"position": (10, 495), "font_size": 34},
                "lock": {"position": (10, 650), "font_size": 34},
                "low_voltage": {"position": (10, 710), "font_size": 34},
                
                "cpu_load": {"position": (1780, -2), "font_size": 26},
                "cpu_temp": {"position": (1860, -2), "font_size": 26},
                "disk_space": {"position": (10, 1044), "font_size": 34},
                
                "mic": {"position": (10, 880), "font_size": 26},
                "key": {"position": (10, 928), "font_size": 26},
                "serial": {"position": (10, 976), "font_size": 26},
                
                "battery_level": {"position": (1830, 1044), "font_size": 34},
                # Additional elements as needed for layout 1
            }
        }

        self.colors = {
            "iso": {
                "normal": "white",
                "inverse": "black"
            },
            "shutter_speed": {
                "normal": "white",
                "inverse": "black"
            },
            "fps": {
                "normal": "white",
                "inverse": "black"
            },
            "exposure_time": {
                "normal": "white",
                "inverse": "black"
            },
            "pwm_mode": {
                "normal": "lightgreen",
                "inverse": "black"
            },
            "shutter_a_sync": {
                "normal": "white",
                "inverse": "black"
            },
            "lock": {
                "normal": (255,0,0,255),
                "inverse": "black"
            },
            "low_voltage": {
                "normal": "yellow",
                "inverse": "black"
            },
            "cpu_load": {
                "normal": "white",
                "inverse": "black"
            },
            "cpu_temp": {
                "normal": "white",
                "inverse": "black"
            },
            "disk_space": {
                "normal": "white",
                "inverse": "black"
            },
            "mic": {
                "normal": "white",
                "inverse": "black"
            },
            "key": {
                "normal": "white",
                "inverse": "black"
            },
            "serial": {
                "normal": "white",
                "inverse": "black"
            },
            "battery_level": {
                "normal": "white",
                "inverse": "black"
            },
        }
        
        self.fb = None
        self.disp_width = self.disp_height = 0
        self.current_layout = 0  # Default layout; can be changed dynamically

    def populate_values(self):
        values = {
            "iso": self.redis_controller.get_value("iso"),
            "shutter_speed": str(self.redis_controller.get_value('shutter_a')).replace('.0', ''),
            "fps": int(self.cinepi_controller.fps_actual),
            
            "exposure_time": str(self.cinepi_controller.exposure_time_fractions),
            
            "cpu_load": str(psutil.cpu_percent()) + '%',
            "cpu_temp": ('{}\u00B0C'.format(int(CPUTemperature().temperature))),
            
        }
        
        if self.cinepi_controller.fps_double == True:
            self.colors["fps"]["normal"] = "lightgreen"
        elif self.cinepi_controller.fps_double == False:
            self.colors["fps"]["normal"] = "white"
            
        if self.cinepi_controller.pwm_mode == True:
            values["pwm_mode"] = "PWM"
            self.colors["shutter_speed"]["normal"] = "lightgreen"
            self.colors["fps"]["normal"] = "lightgreen"
        elif self.cinepi_controller.pwm_mode == False:
            self.colors["shutter_speed"]["normal"] = "white"
            self.colors["fps"]["normal"] = "white"
            
        if self.cinepi_controller.shutter_a_sync == True:
            if self.cinepi_controller.gui_layout == 0:
                values["shutter_a_sync"] = f"SYNC   /  {self.cinepi_controller.shutter_a_nom}"
            elif self.cinepi_controller.gui_layout == 1:
                values["shutter_a_sync"] = f"SYNC/\n{self.cinepi_controller.shutter_a_nom}"
        elif self.cinepi_controller.shutter_a_sync == False:
            values["shutter_a_sync"] = ""
            
        if self.cinepi_controller.parameters_lock == True:
            values["lock"] = "LOCK"
        elif self.cinepi_controller.parameters_lock == False:
            values["lock"] = ""
            
        if self.dmesg_monitor.undervoltage_flag == True:
            values["low_voltage"] = "VOLTAGE"
        elif self.dmesg_monitor.undervoltage_flag == False:
            values["low_voltage"] = ""
            
        if self.usb_monitor.usb_mic:
            values["mic"] = "MIC" 
        else:
            values["mic"] = ""
            
        if self.usb_monitor.usb_keyboard:
            values["key"] = "KEY" 
        else:
            values["key"] = ""  
        
        if '/dev/ttyACM0' in self.serial_handler.current_ports:
            values["serial"] = "SER"
        else:
            values["serial"] = ""  
            
            # values["mic"] = "MIC" 
            # values["key"] = "KEY" 
            # values["serial"] = "SER"

            
        if self.battery_monitor.battery_level != None:
            values["battery_level"] = str(self.battery_monitor.battery_level) + '%'
        elif self.battery_monitor.battery_level == None:
            values["battery_level"] = ''
            
        if self.battery_monitor.charging == True:
            self.colors["battery_level"]["normal"] = "lightgreen"
        elif self.battery_monitor.charging == False:
            self.colors["battery_level"]["normal"] = "white"
        
        if self.ssd_monitor.last_space_left and self.ssd_monitor.disk_mounted:
            min_left = round(int((self.ssd_monitor.last_space_left * 1000) / (self.cinepi_controller.file_size * float(self.cinepi_controller.fps_actual) * 60)), 0)
            values["disk_space"] = f"{min_left} MIN"
        else:
            values["disk_space"] = "NO DISK"
        return values
    

    def draw_gui(self, values):
        if not self.fb:
            return  # Exit if there is no display
        
        if int(self.redis_controller.get_value('is_writing_buf')) == 1:
            self.fill_color = "red"
            self.color_mode = "inverse"
        else:
            self.fill_color = "black"
            self.color_mode = "normal"
        
        image = Image.new("RGBA", self.fb.size)
        draw = ImageDraw.Draw(image)
        draw.rectangle(((0, 0), self.fb.size), fill=self.fill_color)
        
    # Determine the current layout
        gui_layout_key = self.cinepi_controller.gui_layout
        if gui_layout_key not in self.layouts:
            logging.warning(f"Invalid gui_layout '{gui_layout_key}'")
            gui_layout_key = 0  # Fallback to a default layout

        current_layout = self.layouts[gui_layout_key]
        
        # Map elements to their corresponding lock variables in cinepi_controller
        lock_mapping = {
            "iso": "iso_lock",
            "shutter_speed": "shutter_a_nom_lock",
            "fps": "fps_lock",
            "exposure_time": "shutter_a_sync"
            }

        # For dynamic boxes around specific elements
        for element, info in current_layout.items():
            if values.get(element) is None:  # Skip elements with None value
                continue
            position = info["position"]
            position = (int(position[0] * self.scaling_width), int(position[1] * self.scaling_height))
            font_size = int(info["font_size"] * self.scaling_height)
            font = ImageFont.truetype(os.path.realpath(self.font_path), font_size)
            # Ensure value is a string
            value = str(values.get(element, ''))
            # Assuming self.color_mode contains either "normal" or "inverse"
            color_mode = self.color_mode  # This should be set to either 'normal' or 'inverse'

            # Retrieve the color for the element based on the current color mode
            color = self.colors.get(element, {}).get(color_mode, "white")
            inverse_color = self.colors.get(element, {}).get(color_mode, "white")

            draw.text(position, value, font=font, fill=color)

            # Check if the corresponding _lock variable for the element is True
            if element in lock_mapping and getattr(self.cinepi_controller, lock_mapping[element]):
                self.draw_rounded_box(draw, value, position, font_size, 5, "black", "white", image)
                
            
            #draw.text(600, -7, str(pisugar.get_battery_level()), font=font, fill=color)
        
        self.fb.show(image)
        
    def draw_rounded_box(self, draw, text, position, font_size, padding, text_color, fill_color, image):
        # Load font
        font = ImageFont.truetype(os.path.realpath(self.font_path), font_size)
        # Calculate text size
        text_width, text_height = draw.textsize(text, font=font)

        # Adjust upper left position of the box based on padding, so text position is unaffected
        upper_left = (position[0] - padding, position[1] - padding)
        bottom_right = (upper_left[0] + text_width + 2 * padding, upper_left[1] + text_height + 2 * padding)

        # Corner radius for rounded edges
        radius = 10

        # Pre-calculate for efficiency
        radius_2x = radius * 2

        # Use a mask for rounded corners
        mask = Image.new('L', (radius_2x, radius_2x), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, radius_2x, radius_2x), fill=255)

        # Top-left corner
        image.paste(fill_color, (upper_left[0], upper_left[1]), mask)
        # Top-right corner
        image.paste(fill_color, (upper_left[0] + text_width + padding * 2 - radius_2x, upper_left[1]), mask)
        # Bottom-left corner
        image.paste(fill_color, (upper_left[0], upper_left[1] + text_height + padding * 2 - radius_2x), mask)
        # Bottom-right corner
        image.paste(fill_color, (upper_left[0] + text_width + padding * 2 - radius_2x, upper_left[1] + text_height + padding * 2 - radius_2x), mask)

        # Fill the rectangles to connect corners
        # Top
        draw.rectangle([upper_left[0] + radius, upper_left[1], upper_left[0] + text_width + padding * 2 - radius, upper_left[1] + radius], fill=fill_color)
        # Bottom
        draw.rectangle([upper_left[0] + radius, upper_left[1] + text_height + padding * 2 - radius, upper_left[0] + text_width + padding * 2 - radius, upper_left[1] + text_height + padding * 2], fill=fill_color)
        # Left
        draw.rectangle([upper_left[0], upper_left[1] + radius, upper_left[0] + radius, upper_left[1] + text_height + padding * 2 - radius], fill=fill_color)
        # Right
        draw.rectangle([upper_left[0] + text_width + padding * 2 - radius, upper_left[1] + radius, upper_left[0] + text_width + padding * 2, upper_left[1] + text_height + padding * 2 - radius], fill=fill_color)
        # Center
        draw.rectangle([upper_left[0] + radius, upper_left[1] + radius, upper_left[0] + text_width + padding * 2 - radius, upper_left[1] + text_height + padding * 2 - radius], fill=fill_color)

        # Draw the text in the specified position, not affected by padding
        draw.text(position, text, font=font, fill=text_color)

    def run(self):
        while True:
            values = self.populate_values()
            self.draw_gui(values)
            time.sleep(0.1)

