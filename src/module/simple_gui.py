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
import re

class SimpleGUI(threading.Thread):
    def __init__(self, 
                 redis_controller, 
                 cinepi_controller, 
                 ssd_monitor, 
                 dmesg_monitor, 
                 battery_monitor, 
                 sensor_detect, 
                 redis_listener, 
                 #timekeeper, 
                 socketio: SocketIO = None):
        threading.Thread.__init__(self)
        self.setup_resources()
        self.check_display()
        self.hide_cursor()  # Hide the cursor when initializing the GUI
        self.color_mode = "normal"  # Can be changed to "inverse" as needed

        self.redis_controller = redis_controller
        self.cinepi_controller = cinepi_controller
        self.ssd_monitor = ssd_monitor
        self.dmesg_monitor = dmesg_monitor
        self.battery_monitor = battery_monitor
        self.sensor_detect = sensor_detect
        self.redis_listener = redis_listener
        
        #self.timekeeper = timekeeper

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
        if self.socketio is not None:
            self.socketio.emit('background_color_change', {'background_color': self.current_background_color})
        else:
            logging.warning("SocketIO not initialized. Unable to emit background_color_change.")

    def emit_gui_data_change(self, changed_data):
        if self.socketio is not None:
            self.socketio.emit('gui_data_change', changed_data)
        else:
            logging.warning("SocketIO not initialized. Unable to emit gui_data_change.")

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
                # "shutter_a_sync": {"position": (1345, -2), "font_size": 26},
                "lock": {"position": (1530, -2), "font_size": 26},
                "low_voltage": {"position": (1620, -2), "font_size": 26},
                "ram_load": {"position": (1700, -2), "font_size": 26},
                "cpu_load": {"position": (1780, -2), "font_size": 26},
                "cpu_temp": {"position": (1860, -2), "font_size": 26},
                "disk_space": {"position": (10, 1044), "font_size": 34},
                "frame_count": {"position": (205, 1044), "font_size": 34},
                    #"last_dng_added": {"position": (610, 1044), "font_size": 34},
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
            # "shutter_a_sync": {"normal": "white", "inverse": "black"},
            "lock": {"normal": (255, 0, 0, 255), "inverse": "black"},
            "low_voltage": {"normal": "yellow", "inverse": "black"},
            "ram_load": {"normal": "white", "inverse": "black"},
            "cpu_load": {"normal": "white", "inverse": "black"},
            "cpu_temp": {"normal": "white", "inverse": "black"},
            "disk_space": {"normal": "white", "inverse": "black"},
            "frame_count": {"normal": "white", "inverse": "black"},
           # "last_dng_added": {"normal": "white", "inverse": "black"},
            "battery_level": {"normal": "white", "inverse": "black"},
        }

        self.fb = None
        self.disp_width = self.disp_height = 0
        self.current_layout = 0  # Default layout; can be changed dynamically

    def populate_values(self):
        values = {
            "iso": self.redis_controller.get_value("iso"),
            "shutter_speed": str(self.redis_controller.get_value('shutter_a')).replace('.0', ''),
            "fps": round(float(self.redis_controller.get_value('fps'))),
            #"sync_effort_level": self.timekeeper.get_effort_level(),
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
        
        # Construct the frame count string
        frame_count_string = str(self.redis_controller.get_value("framecount")) + " / " + str(self.redis_controller.get_value("buffer"))

        # Clean the string to only keep digits, blank spaces, and the / sign
        cleaned_frame_count_string = re.sub(r"[^0-9 /]", "", frame_count_string)
        values["frame_count"]= frame_count_string

        if values["fps"] != int(float(self.redis_controller.get_value('fps_user'))):
            self.colors["fps"]["normal"] = "yellow"
        
        elif self.cinepi_controller.trigger_mode != 0:
            values["pwm_mode"] = "PWM"
            self.colors["shutter_speed"]["normal"] = "lightgreen"
            self.colors["fps"]["normal"] = "lightgreen"
        
        else:
            self.colors["shutter_speed"]["normal"] = "white"
            self.colors["fps"]["normal"] = "white"

        if self.cinepi_controller.fps_double:
            self.colors["fps"]["normal"] = "yellow"
        else:
            self.colors["fps"]["normal"] = "white"

        # if self.cinepi_controller.shutter_a_sync_mode != 0:
                
        #     values["shutter_a_sync"] = f"SHUTTER SYNC"
        # else:
        #     values["shutter_a_sync"] = ""
    
        if self.cinepi_controller.parameters_lock:
            values["lock"] = "LOCK"
        else:
            values["lock"] = ""

        if self.dmesg_monitor.undervoltage_flag:
            values["low_voltage"] = "VOLTAGE"
        else:
            values["low_voltage"] = ""

        # if self.ssd_monitor and self.ssd_monitor.directory_watcher and self.ssd_monitor.directory_watcher.last_dng_file_added:
        #     values["last_dng_added"] = str(self.ssd_monitor.directory_watcher.last_dng_file_added)[41:80]
        # else:
        #     values["last_dng_added"] = ""

        if self.battery_monitor.battery_level is not None:
            values["battery_level"] = str(self.battery_monitor.battery_level) + '%'
        else:
            values["battery_level"] = ''

        self.colors["battery_level"]["normal"] = "lightgreen" if self.battery_monitor.charging else "white"

        if self.ssd_monitor.space_left and self.ssd_monitor.is_mounted:
            min_left = round(int((self.ssd_monitor.space_left * 1000) / (self.cinepi_controller.file_size * float(self.cinepi_controller.fps) * 60)), 0)
            values["disk_space"] = f"{min_left} MIN"
        else:
            values["disk_space"] = "NO DISK"

        return values

    def draw_gui(self, values):
        previous_background_color = self.current_background_color  # Store the previous background color

        # Determine background color based on conditions, prioritizing red over green
        if self.redis_listener.drop_frame == 1:
            self.current_background_color = "purple"
            self.color_mode = "inverse"
        
        elif int(values["ram_load"].rstrip('%')) > 95:
            self.current_background_color = "yellow"
            self.color_mode = "inverse"
            self.cinepi_controller.rec()
            logging.info("RAM full")
        elif int(self.redis_controller.get_value('is_writing_buf')) == 1:
            self.current_background_color = "red"
            self.color_mode = "inverse"
        elif int(self.redis_controller.get_value('is_buffering')) == 1:
            self.current_background_color = "green"
            self.color_mode = "inverse"
        else:
            self.current_background_color = "black"
            self.color_mode = "normal"

        # Check if the background color has changed
        if self.current_background_color != previous_background_color:
            self.background_color_changed = True  # Set flag to indicate background color change
        else:
            self.background_color_changed = False  # No background color change

        if self.background_color_changed:
            try:
                self.emit_background_color_change()
            except Exception as e:
                logging.error(f"Error emitting background color change: {e}")

        current_values = values

        if hasattr(self, 'previous_values'):
            changed_data = {}
            for key, value in current_values.items():
                if value != self.previous_values.get(key):
                    changed_data[key] = value

            if changed_data:
                try:
                    self.emit_gui_data_change(changed_data)
                except Exception as e:
                    pass
                    #logging.error(f"Error emitting GUI data change: {e}")

                # Log the changed data after emitting changes
                # logging.info(f"Changed data: {changed_data}")

        # Update previous_values with the current values for the next comparison
        self.previous_values = current_values.copy()

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

        # Draw the GUI elements
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

            # Draw rounded box behind locked elements
            if element in lock_mapping and getattr(self.cinepi_controller, lock_mapping[element]):
                self.draw_rounded_box(draw, value, position, font_size, 5, "black", "white", image)

            # **New Addition: Draw rounded box behind the exposure time if shutter sync is enabled**
            if element == "exposure_time" and self.cinepi_controller.shutter_a_sync_mode == 1:
                self.draw_rounded_box(draw, value, position, font_size, 5, "black", "white", image)

        self.fb.show(image)

        
    def draw_rounded_box(self, draw, text, position, font_size, padding, text_color, fill_color, image, extra_height=-17, reduce_top=12):
        font = ImageFont.truetype(os.path.realpath(self.font_path), font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1] + extra_height  # Increase height by extra_height

        # Reduce the top padding by reduce_top and increase the bottom by the same amount
        upper_left = (position[0] - padding, position[1] - (padding - reduce_top))
        bottom_right = (upper_left[0] + text_width + 2 * padding, upper_left[1] + text_height + 2 * padding + reduce_top)
        radius = 5
        radius_2x = radius * 2

        mask = Image.new('L', (radius_2x, radius_2x), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, radius_2x, radius_2x), fill=255)

        # Top-left corner
        image.paste(fill_color, (upper_left[0], upper_left[1]), mask)
        # Top-right corner
        image.paste(fill_color, (upper_left[0] + text_width + padding * 2 - radius_2x, upper_left[1]), mask)
        # Bottom-left corner
        image.paste(fill_color, (upper_left[0], upper_left[1] + text_height + padding * 2 - radius_2x + reduce_top), mask)
        # Bottom-right corner
        image.paste(fill_color, (upper_left[0] + text_width + padding * 2 - radius_2x, upper_left[1] + text_height + padding * 2 - radius_2x + reduce_top), mask)

        # Top side
        draw.rectangle([upper_left[0] + radius, upper_left[1], upper_left[0] + text_width + padding * 2 - radius, upper_left[1] + radius], fill=fill_color)
        # Bottom side
        draw.rectangle([upper_left[0] + radius, upper_left[1] + text_height + padding * 2 - radius + reduce_top, upper_left[0] + text_width + padding * 2 - radius, upper_left[1] + text_height + padding * 2 + reduce_top], fill=fill_color)
        # Left side
        draw.rectangle([upper_left[0], upper_left[1] + radius, upper_left[0] + radius, upper_left[1] + text_height + padding * 2 - radius + reduce_top], fill=fill_color)
        # Right side
        draw.rectangle([upper_left[0] + text_width + padding * 2 - radius, upper_left[1] + radius, upper_left[0] + text_width + padding * 2, upper_left[1] + text_height + padding * 2 - radius + reduce_top], fill=fill_color)
        # Center box
        draw.rectangle([upper_left[0] + radius, upper_left[1] + radius, upper_left[0] + text_width + padding * 2 - radius, upper_left[1] + text_height + padding * 2 - radius + reduce_top], fill=fill_color)

        draw.text(position, text, font=font, fill=text_color)



    def run(self):
        try:
            while True:
                values = self.populate_values()
                self.draw_gui(values)
                time.sleep(0.1)
        finally:
            self.show_cursor()

    def emit_gui_data_change(self, changed_data):
        self.socketio.emit('gui_data_change', changed_data)