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
from flask_socketio import SocketIO

class SimpleGUI(threading.Thread):
    def __init__(self, pwm_controller, redis_controller, cinepi_controller, usb_monitor, ssd_monitor, serial_handler, dmesg_monitor, battery_monitor, sensor_detect, redis_listener, socketio: SocketIO):
        threading.Thread.__init__(self)
        self.setup_resources()
        self.check_display()
        self.hide_cursor()  # Hide the cursor when initializing the GUI
        self.color_mode = "normal"  # Can be changed to "inverse" as needed

        self.pwm_controller = pwm_controller
        self.redis_controller = redis_controller
        self.cinepi_controller = cinepi_controller
        self.usb_monitor = usb_monitor
        self.ssd_monitor = ssd_monitor
        self.serial_handler = serial_handler
        self.dmesg_monitor = dmesg_monitor
        self.battery_monitor = battery_monitor
        self.sensor_detect = sensor_detect
        self.redis_listener = redis_listener

        self.socketio = socketio  # Add socketio reference

        self.background_color_changed = False

        self.start()

        # Initialize current background color
        self.current_background_color = "black"  # Default background color

    # Method to set the current background color
    def set_background_color(self, color):
        self.current_background_color = color

    # Method to fetch the current background color
    def get_background_color(self):
        return self.current_background_color

    def emit_background_color_change(self):
        self.socketio.emit('background_color_change', {'background_color': self.current_background_color})

    def hide_cursor(self):
        os.system("setterm -cursor off")

    def show_cursor(self):
        os.system("setterm -cursor on")

    def check_display(self):
        fb_path = "/dev/fb0"
        if os.path.exists(fb_path):
            self.fb = Framebuffer(0)
            self.disp_width, self.disp_height = self.fb.size
            logging.info(f"HDMI display found. {self.disp_width, self.disp_height}")
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
                "sensor": {"position": (505, -7), "font_size": 34},
                "width": {"position": (630, -7), "font_size": 34},
                "height": {"position": (730, -7), "font_size": 34},
                "bit_depth": {"position": (822, -7), "font_size": 34},
                "color_temp": {"position": (950, -7), "font_size": 34},
                "exposure_time": {"position": (1110, -7), "font_size": 34},
                "pwm_mode": {"position": (1243, -2), "font_size": 26},
                "shutter_a_sync": {"position": (1345, -2), "font_size": 26},
                "lock": {"position": (1530, -2), "font_size": 26},
                "low_voltage": {"position": (1620, -2), "font_size": 26},
                "ram_load": {"position": (1700, -2), "font_size": 26},
                "cpu_load": {"position": (1780, -2), "font_size": 26},
                "cpu_temp": {"position": (1860, -2), "font_size": 26},
                "disk_space": {"position": (10, 1044), "font_size": 34},
                "mic": {"position": (160, 1050), "font_size": 26},
                "key": {"position": (250, 1050), "font_size": 26},
                "serial": {"position": (345, 1050), "font_size": 26},
                "last_dng_added": {"position": (610, 1044), "font_size": 34},
                "battery_level": {"position": (1830, 1044), "font_size": 34},
            },
            1: {  # Layout 1
                "iso": {"position": (0, -7), "font_size": 51},
                "shutter_speed": {"position": (10, 80), "font_size": 51},
                "fps": {"position": (10, 167), "font_size": 51},
                "exposure_time": {"position": (10, 340), "font_size": 34},
                "pwm_mode": {"position": (10, 427), "font_size": 34},
                "shutter_a_sync": {"position": (10, 495), "font_size": 34},
                "lock": {"position": (10, 619), "font_size": 34},
                "low_voltage": {"position": (10, 680), "font_size": 34},
                "cpu_load": {"position": (1780, -2), "font_size": 26},
                "cpu_temp": {"position": (1860, -2), "font_size": 26},
                "disk_space": {"position": (10, 1044), "font_size": 34},
                "mic": {"position": (10, 880), "font_size": 26},
                "key": {"position": (10, 928), "font_size": 26},
                "serial": {"position": (10, 976), "font_size": 26},
                "battery_level": {"position": (1830, 1044), "font_size": 34},
            }
        }

        self.colors = {
            "iso": {"normal": "white", "inverse": "black"},
            "shutter_speed": {"normal": "white", "inverse": "black"},
            "fps": {"normal": "white", "inverse": "black"},
            "exposure_time": {"normal": "white", "inverse": "black"},
            "sensor": {"normal": "grey", "inverse": "black"},
            "height": {"normal": "white", "inverse": "black"},
            "width": {"normal": "white", "inverse": "black"},
            "bit_depth": {"normal": "white", "inverse": "black"},
            "color_temp": {"normal": "white", "inverse": "black"},
            "pwm_mode": {"normal": "lightgreen", "inverse": "black"},
            "shutter_a_sync": {"normal": "white", "inverse": "black"},
            "lock": {"normal": (255, 0, 0, 255), "inverse": "black"},
            "low_voltage": {"normal": "yellow", "inverse": "black"},
            "ram_load": {"normal": "white", "inverse": "black"},
            "cpu_load": {"normal": "white", "inverse": "black"},
            "cpu_temp": {"normal": "white", "inverse": "black"},
            "disk_space": {"normal": "white", "inverse": "black"},
            "mic": {"normal": "white", "inverse": "black"},
            "key": {"normal": "white", "inverse": "black"},
            "serial": {"normal": "white", "inverse": "black"},
            "last_dng_added": {"normal": "white", "inverse": "black"},
            "battery_level": {"normal": "white", "inverse": "black"},
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
            "sensor": str.upper(self.redis_controller.get_value("sensor")),
            "width": str(self.redis_controller.get_value("width") + " : "),
            "height": str(self.redis_controller.get_value("height") + " : "),
            "bit_depth": str(self.redis_controller.get_value("bit_depth") + "b"),
            "color_temp": (str(self.redis_listener.colorTemp) + "K"),
            "ram_load": f"{100 - psutil.virtual_memory().available / psutil.virtual_memory().total * 100:.0f}%",
            "cpu_load": str(int(psutil.cpu_percent())) + '%',
            "cpu_temp": ('{}\u00B0C'.format(int(CPUTemperature().temperature))),
        }

        if self.cinepi_controller.fps_double:
            self.colors["fps"]["normal"] = "lightgreen"
        else:
            self.colors["fps"]["normal"] = "white"

        if self.cinepi_controller.pwm_mode:
            values["pwm_mode"] = "PWM"
            self.colors["shutter_speed"]["normal"] = "lightgreen"
            self.colors["fps"]["normal"] = "lightgreen"
        else:
            self.colors["shutter_speed"]["normal"] = "white"
            self.colors["fps"]["normal"] = "white"

        if self.cinepi_controller.shutter_a_sync:
            values["shutter_a_sync"] = f"SYNC   /  {self.cinepi_controller.shutter_a_nom}"
        else:
            values["shutter_a_sync"] = ""

        if self.cinepi_controller.parameters_lock:
            values["lock"] = "LOCK"
        else:
            values["lock"] = ""

        if self.dmesg_monitor.undervoltage_flag:
            values["low_voltage"] = "VOLTAGE"
        else:
            values["low_voltage"] = ""

        values["mic"] = "MIC" if self.usb_monitor.usb_mic else ""
        values["key"] = "KEY" if self.usb_monitor.usb_keyboard else ""
        values["serial"] = "SER" if '/dev/ttyACM0' in self.serial_handler.current_ports else ""

        if self.ssd_monitor and self.ssd_monitor.directory_watcher and self.ssd_monitor.directory_watcher.last_dng_file_added:
            values["last_dng_added"] = str(self.ssd_monitor.directory_watcher.last_dng_file_added)[41:80]
        else:
            values["last_dng_added"] = ""

        if self.battery_monitor.battery_level is not None:
            values["battery_level"] = str(self.battery_monitor.battery_level) + '%'
        else:
            values["battery_level"] = ''

        self.colors["battery_level"]["normal"] = "lightgreen" if self.battery_monitor.charging else "white"

        if self.ssd_monitor.last_space_left and self.ssd_monitor.disk_mounted:
            min_left = round(int((self.ssd_monitor.last_space_left * 1000) / (self.cinepi_controller.file_size * float(self.cinepi_controller.fps_actual) * 60)), 0)
            values["disk_space"] = f"{min_left} MIN"
        else:
            values["disk_space"] = "NO DISK"
        return values

    def draw_gui(self, values):
        previous_background_color = self.current_background_color  # Store the previous background color

        # Determine background color based on conditions, prioritizing red over green
        if int(values["ram_load"].rstrip('%')) > 95:
            self.current_background_color = "yellow"
            self.color_mode = "inverse"
            self.cinepi_controller.rec()
            logging.info("RAM full")
        elif int(self.redis_controller.get_value('is_writing_buf')) == 1:
            self.current_background_color = "red"
            self.color_mode = "inverse"
        elif self.redis_listener.bufferSize != 0:
            self.current_background_color = "green"
            self.color_mode = "inverse"
        else:
            self.current_background_color = "black"
            self.color_mode = "normal"

        # If conditions for both red and green are met, prioritize red
        if self.current_background_color == "green" and int(self.redis_controller.get_value('is_writing_buf')) == 1:
            self.current_background_color = "red"
            self.color_mode = "inverse"

        # Check if the background color has changed
        if self.current_background_color != previous_background_color:
            self.background_color_changed = True  # Set flag to indicate background color change
        else:
            self.background_color_changed = False  # No background color change

        if self.background_color_changed:
            self.emit_background_color_change()  # Emit event if the background color changes

        if not self.fb:
            return

        image = Image.new("RGBA", self.fb.size)
        draw = ImageDraw.Draw(image)
        draw.rectangle(((0, 0), self.fb.size), fill=self.current_background_color)

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
            font_size = info["font_size"]
            font = ImageFont.truetype(os.path.realpath(self.font_path), font_size)
            value = str(values.get(element, ''))  # Ensure value is a string
            color_mode = self.color_mode
            color = self.colors.get(element, {}).get(color_mode, "white")

            draw.text(position, value, font=font, fill=color)

            if element in lock_mapping and getattr(self.cinepi_controller, lock_mapping[element]):
                self.draw_rounded_box(draw, value, position, font_size, 5, "black", "white", image)

        self.fb.show(image)

    def draw_rounded_box(self, draw, text, position, font_size, padding, text_color, fill_color, image):
        font = ImageFont.truetype(os.path.realpath(self.font_path), font_size)
        text_width, text_height = draw.textsize(text, font=font)
        upper_left = (position[0] - padding, position[1] - padding)
        bottom_right = (upper_left[0] + text_width + 2 * padding, upper_left[1] + text_height + 2 * padding)
        radius = 10
        radius_2x = radius * 2

        mask = Image.new('L', (radius_2x, radius_2x), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, radius_2x, radius_2x), fill=255)

        image.paste(fill_color, (upper_left[0], upper_left[1]), mask)
        image.paste(fill_color, (upper_left[0] + text_width + padding * 2 - radius_2x, upper_left[1]), mask)
        image.paste(fill_color, (upper_left[0], upper_left[1] + text_height + padding * 2 - radius_2x), mask)
        image.paste(fill_color, (upper_left[0] + text_width + padding * 2 - radius_2x, upper_left[1] + text_height + padding * 2 - radius_2x), mask)

        draw.rectangle([upper_left[0] + radius, upper_left[1], upper_left[0] + text_width + padding * 2 - radius, upper_left[1] + radius], fill=fill_color)
        draw.rectangle([upper_left[0] + radius, upper_left[1] + text_height + padding * 2 - radius, upper_left[0] + text_width + padding * 2 - radius, upper_left[1] + text_height + padding * 2], fill=fill_color)
        draw.rectangle([upper_left[0], upper_left[1] + radius, upper_left[0] + radius, upper_left[1] + text_height + padding * 2 - radius], fill=fill_color)
        draw.rectangle([upper_left[0] + text_width + padding * 2 - radius, upper_left[1] + radius, upper_left[0] + text_width + padding * 2, upper_left[1] + text_height + padding * 2 - radius], fill=fill_color)
        draw.rectangle([upper_left[0] + radius, upper_left[1] + radius, upper_left[0] + text_width + padding * 2 - radius, upper_left[1] + text_height + padding * 2 - radius], fill=fill_color)
        draw.text(position, text, font=font, fill=text_color)

    def run(self):
        try:
            while True:
                values = self.populate_values()
                self.draw_gui(values)
                time.sleep(0.1)
        finally:
            self.show_cursor()
