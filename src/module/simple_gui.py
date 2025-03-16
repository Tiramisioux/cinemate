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
        
        # Load sensor values from Redis upon instantiation
        self.load_sensor_values_from_redis()

        self.start()

        # Initialize current background color
        self.current_background_color = "black"  # Default background color
        
    def load_sensor_values_from_redis(self):
        """
        Load current sensor values (width, height, bit depth) from Redis.
        """
        try:
            self.width = int(self.redis_controller.get_value('width') or 1920)
            self.height = int(self.redis_controller.get_value('height') or 1080)
            self.bit_depth = int(self.redis_controller.get_value('bit_depth') or 10)
            #logging.info(f"Loaded sensor values from Redis: width={self.width}, height={self.height}, bit_depth={self.bit_depth}")
        except ValueError:
            logging.error("Failed to load sensor values from Redis, using default values.")
            self.width = 1920
            self.height = 1080
            self.bit_depth = 12

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
        self.regular_font_path = os.path.join(self.current_directory, '../../resources/fonts/DIN2014-Regular.ttf')
        self.bold_font_path = os.path.join(self.current_directory, '../../resources/fonts/DIN2014-Bold.ttf')  # Add bold font path
        self.font_path = os.path.join(self.current_directory, '../../resources/fonts/DIN2014-Bold.ttf')

        # Define two layouts
        self.layouts = {
            0: {  # Layout 0
                # upper row
                "fps_label": {"position": (98, 4), "font_size": 30, "font": "regular"},
                "fps_actual": {"position": (159, 3), "font_size": 41, "font": "bold"},
                "shutter_label": {"position": (555, 4), "font_size": 30, "font": "regular"},
                "shutter_speed": {"position": (690, 3), "font_size": 41, "font": "bold"},
                "iso_label": {"position": (1194, 3), "font_size": 30, "font": "regular"},
                "iso": {"position": (1232, 4), "font_size": 41, "font": "bold"},
                "wb_label": {"position": (1641, 4), "font_size": 30, "font": "regular"},
                "color_temp": {"position": (1695, 3), "font_size": 41, "font": "bold"},
                
                #left side
                "cam": {"position": (21, 97), "font_size": 26, "font": "regular"},
                "resolution": {"position": (34, 140), "font_size": 20, "font": "bold"},
                "aspect": {"position": (26, 191), "font_size": 20, "font": "bold", "align": "center"},
                "raw": {"position": (25, 240), "font_size": 20, "font": "bold"},
                "exposure_time": {"position": (25, 291), "font_size": 20, "font": "bold"},
                
                "mon": {"position": (21, 362), "font_size": 26, "font": "regular"},
                "anamorphic_factor": {"position": (25, 405), "font_size": 20, "font": "bold"},
                
                
                #"fps": {"position": (375, -7), "font_size": 34},
                #"sensor": {"position": (435, -1), "font_size": 18, "align": "right", "width": 175},
                #"width": {"position": (620, -7), "font_size": 34},
                #"height": {"position": (720, -7), "font_size": 34},
                #"bit_depth": {"position": (812, -7), "font_size": 34},
                #"color_temp_libcamera": {"position": (1083, -7), "font_size": 34},                
                #"exposure_label": {"position": (1280, -1), "font_size": 18},
                
                #"pwm_mode": {"position": (1273, -2), "font_size": 26},
                # NEJ "shutter_a_sync": {"position": (1345, -2), "font_size": 26},
                # "lock": {"position": (1530, -2), "font_size": 26},
                # "low_voltage": {"position": (1550, -2), "font_size": 26},
                
                # lower row
                "media_label": {"position": (98, 1050), "font_size": 30, "font": "regular"},
                "disk_space": {"position": (192, 1041), "font_size": 41, "font": "bold"},
                #"frame_count": {"position": (335, 1044), "font_size": 34},
                #"last_dng_added": {"position": (600, 1044), "font_size": 34},
                "battery_level": {"position": (600, 1041), "font_size": 41, "font": "bold"},
                "cpu_label": {"position": (1260, 1050), "font_size": 30, "font": "regular"},
                "cpu_load": {"position": (1330, 1041), "font_size": 41, "font": "bold"},
                "cpu_temp_label": {"position": (1458, 1050), "font_size": 31, "font": "regular"},
                "cpu_temp": {"position": (1542, 1041), "font_size": 41, "font": "bold"},
                "ram_label": {"position": (1673, 1050), "font_size": 30, "font": "regular"},
                "ram_load": {"position": (1741, 1041), "font_size": 41, "font": "bold"},
            }
        }

        self.colors = {
            "iso_label": {"normal": (136,136,136), "inverse": "black"},
            "iso": {"normal": (249,249,249), "inverse": "black"},
            "shutter_label": {"normal": (136,136,136), "inverse": "black"},
            "shutter_speed": {"normal": (249,249,249), "inverse": "black"},
            "fps_label": {"normal": (136,136,136), "inverse": "black"},
            "fps": {"normal": (249,249,249), "inverse": "black"},
            "fps_actual": {"normal": (249,249,249), "inverse": "black"},
            "exposure_label": {"normal": (136,136,136), "inverse": "black"},
            "exposure_time": {"normal": "black", "inverse": (249,249,249)},
            "anamorphic_factor": {"normal": "black", "inverse": (249,249,249)},
            "sensor": {"normal": (136,136,136), "inverse": "black"},
            "height": {"normal": (249,249,249), "inverse": "black"},
            "width": {"normal": (249,249,249), "inverse": "black"},
            "bit_depth": {"normal": (249,249,249), "inverse": "black"},
            "wb_label": {"normal": (136,136,136), "inverse": "black"},
            "color_temp": {"normal": (249,249,249), "inverse": "black"},
            "cam": {"normal": (249,249,249), "inverse": "black"},
            "resolution": {"normal": "black"},
            "aspect": {"normal": "black"},
            "raw": {"normal": "black"},
            "color_temp_libcamera": {"normal": (136,136,136), "inverse": "black"},
            "pwm_mode": {"normal": (97,171,49), "inverse": "black"},
            # "shutter_a_sync": {"normal": "white", "inverse": "black"},
            "lock": {"normal": (255, 0, 0, 255), "inverse": "black"},
            "low_voltage": {"normal": (218,149,77), "inverse": "black"},
            "ram_label": {"normal": (136,136,136), "inverse": "black"},
            "ram_load": {"normal": (249,249,249), "inverse": "black"},
            "cpu_label": {"normal": (136,136,136), "inverse": "black"},
            "cpu_load": {"normal": (249,249,249), "inverse": "black"},
            "cpu_temp_label": {"normal": (136,136,136), "inverse": "black"},
            "cpu_temp": {"normal": (249,249,249), "inverse": "black"},
            "media_label": {"normal": (136,136,136), "inverse": "black"},            
            "disk_label": {"normal": (136,136,136), "inverse": "black"},
            "disk_space": {"normal": (249,249,249), "inverse": "black"},
            "frame_count": {"normal": (136,136,136), "inverse": "black"},
            "last_dng_added": {"normal": (249,249,249), "inverse": "black"},
            "battery_level": {"normal": (249,249,249), "inverse": "black"},
        }

        self.fb = None
        self.disp_width = self.disp_height = 0
        self.current_layout = 0  # Default layout; can be changed dynamically

    def estimate_resolution_in_k(self):
        """
        Estimate the current resolution in K.
        """
        try:
            if self.width >= 3840:
                resolution_value = "4K"
            elif self.width >= 2560:
                resolution_value = "2.5K"
            elif self.width >= 1920:
                resolution_value = "2K"
            elif self.width >= 1280:
                resolution_value = "1.3K"
            else:
                resolution_value = "1K"
        except (TypeError, ValueError):
            resolution_value = "N/A"
        return resolution_value

    def populate_values(self):

        width = self.redis_controller.get_value("width")

        self.load_sensor_values_from_redis()
        resolution_value = self.estimate_resolution_in_k()

        width = self.redis_controller.get_value("width")
        height = self.redis_controller.get_value("height")

        # Ensure width and height are valid numbers before calculation
        try:
            width = int(width)
            height = int(height)
            aspect_ratio = round(width / height, 2) if height != 0 else "N/A"
        except (TypeError, ValueError):
            aspect_ratio = "N/A"
        
        values = {
            "resolution": resolution_value,
            "iso_label": "EI",
            "iso": self.redis_controller.get_value("iso"),
            "shutter_label": "SHUTTER",
            "shutter_speed": str(self.redis_controller.get_value('shutter_a')),
            "fps_label": "FPS",
            "fps": round(float(self.redis_controller.get_value('fps'))),
            "fps_actual": f"{float(self.redis_listener.current_framerate):.3f}" if self.redis_listener.current_framerate is not None else "/ N/A",
            "exposure_label": "EXP",
            "exposure_time": str(self.cinepi_controller.exposure_time_fractions),
            
            "sensor": str.upper(self.redis_controller.get_value("sensor")),
            "width": str(self.redis_controller.get_value("width") + " : "),
            "height": str(self.redis_controller.get_value("height") + " : "),
            "bit_depth": str(self.redis_controller.get_value("bit_depth") + "b"),
            "wb_label": "WB",
            "color_temp": (str(self.redis_controller.get_value('wb_user')) + " K"),
            "color_temp_libcamera": ("/ " + str(self.redis_listener.colorTemp) + "K"),
            "cam": 'CAM',
            "aspect": str(aspect_ratio),  # Use computed aspect ratio
            "raw": 'RAW',
            "ram_label": 'RAM',
            "mon": 'MON',
            "anamorphic_factor": (str(self.redis_controller.get_value('anamorphic_factor')) + "X"),
            "ram_load": f"{100 - psutil.virtual_memory().available / psutil.virtual_memory().total * 100:.0f}%",
            "cpu_label": 'CPU',
            "cpu_load": str(int(psutil.cpu_percent())) + '%',
            "cpu_temp_label": 'TEMP',
            "cpu_temp": ('{}\u00B0C'.format(int(CPUTemperature().temperature))),
             "media_label": "MEDIA",
            "disk_label": str(self.ssd_monitor.device_name).upper()[:4] if self.ssd_monitor.device_name else "", #str(self.ssd_monitor.file_system_format).upper() if self.ssd_monitor.file_system_format else "",
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
            self.colors["fps"]["normal"] = "lightgreen"
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

        # if self.ssd_monitor.last_dng_file:
        #     values["last_dng_added"] = str(self.ssd_monitor.last_dng_file).upper()
        # else:
        #      values["last_dng_added"] = ""

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
        if self.redis_listener.drop_frame == 1 and int(self.redis_controller.get_value('rec')) == 1:
            self.current_background_color = "purple"
            self.color_mode = "inverse"
        elif int(values["ram_load"].rstrip('%')) > 95:
            self.current_background_color = "yellow"
            self.color_mode = "inverse"
            self.cinepi_controller.rec()
            logging.info("RAM full")
        elif int(self.redis_controller.get_value('rec')) == 1:
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

        # Update previous_values with the current values for the next comparison
        self.previous_values = current_values.copy()

        if not self.fb:
            return

        image = Image.new("RGBA", self.fb.size)
        draw = ImageDraw.Draw(image)
        draw.rectangle(((0, 0), self.fb.size), fill=self.current_background_color)

        # Define colors
        gray_color = (136, 136, 136)
        black_color = (0, 0, 0)
        white_color = (249, 249, 249)

        # Resolution box
        draw.rectangle([15, 128, 75, 168], fill=gray_color)

        # Aspect ratio box
        draw.rectangle([15, 178, 75, 218], fill=gray_color)

        # Raw box
        draw.rectangle([15, 228, 75, 268], fill=gray_color)

        # Shutter sync box
        if self.cinepi_controller.shutter_a_sync_mode == 1:
            draw.rectangle([15, 280, 75, 320], fill=white_color)
        else:
            draw.rectangle([15, 280, 75, 320], fill=gray_color)

        # Anamorphic factor box
        mon_heading_y = 362  # Y-position of the "MON" heading
        mon_box_start_y = mon_heading_y + (128 - 97)  # Match the distance between "CAM" and the resolution box
        draw.rectangle([15, mon_box_start_y, 75, mon_box_start_y + 40], fill=gray_color)

        # Get sensor resolution
        self.width = int(self.redis_controller.get_value("width"))
        self.height = int(self.redis_controller.get_value("height"))
        self.aspect_ratio = self.width / self.height

        # Get anamorphic factor from Redis
        self.anamorphic_factor = float(self.redis_controller.get_value('anamorphic_factor'))

        # Get lores resolution from Redis
        lores_width = int(self.redis_controller.get_value("lores_width"))
        lores_height = int(self.redis_controller.get_value("lores_height"))

        # Define the HD frame dimensions
        frame_width = 1920
        frame_height = 1080

        # Padding values
        padding_x = 92  # Horizontal padding
        padding_y = 46  # Vertical padding

        # Calculate the maximum available drawing area within the HD frame
        max_draw_width = frame_width - (2 * padding_x)
        max_draw_height = frame_height - (2 * padding_y)

        # **Fix: Adjust height instead of shrinking it**
        adjusted_lores_width = lores_width * self.anamorphic_factor  # Stretched width
        adjusted_lores_height = lores_height * self.anamorphic_factor  # Stretched height
        adjusted_aspect_ratio = adjusted_lores_width / adjusted_lores_height  # Corrected aspect ratio


        # Calculate the preview size while maintaining the adjusted aspect ratio
        if adjusted_aspect_ratio >= 1:  # Landscape or square sensor
            preview_w = max_draw_width
            preview_h = int(preview_w / adjusted_aspect_ratio)
            if preview_h > max_draw_height:
                preview_h = max_draw_height
                preview_w = int(preview_h * adjusted_aspect_ratio)
        else:  # Portrait sensor
            preview_h = max_draw_height
            preview_w = int(preview_h * adjusted_aspect_ratio)
            if preview_w > max_draw_width:
                preview_w = max_draw_width
                preview_h = int(preview_w / adjusted_aspect_ratio)

        # Center the preview within the HD frame considering padding
        preview_x = (frame_width - preview_w) // 2
        preview_y = (frame_height - preview_h) // 2

        # Determine outline color based on recording state
        if int(self.redis_controller.get_value('rec')) == 1:
            line_color = (255, 0, 0)  # Red outline (Recording)
        else:
            line_color = (249, 249, 249)  # White outline (Idle)

        # Draw the preview outline
        draw.rectangle(
            [preview_x, preview_y, preview_x + preview_w, preview_y + preview_h], 
            outline=line_color, 
            width=2
        )


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
            "fps_actual": "fps_lock",
            "exposure_time": "shutter_a_sync"
        }

        # Draw the GUI elements
        for element, info in current_layout.items():
            if values.get(element) is None:  # Skip elements with None value
                continue
            position = info["position"]
            font_size = info["font_size"]

            # Select font based on the layout setting (bold or regular)
            if info["font"] == "bold":
                font = ImageFont.truetype(os.path.realpath(self.bold_font_path), font_size)
            else:
                font = ImageFont.truetype(os.path.realpath(self.regular_font_path), font_size)

            value = str(values.get(element, ''))  # Ensure value is a string
            color_mode = self.color_mode
            color = self.colors.get(element, {}).get(color_mode, "white")

            # Handle right alignment for sensor
            if element == "sensor" and info.get("align") == "right":
                text_bbox = draw.textbbox((0, 0), value, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                x = position[0] + info["width"] - text_width
                position = (x, position[1])

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
        upper_left = ((position[0] - padding), position[1] - (padding - reduce_top)-6) 
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
        self.hide_cursor()  # Hide the cursor when initializing the GUI
        try:
            while True:
                values = self.populate_values()
                self.draw_gui(values)
                time.sleep(0.1)
        finally:
            self.show_cursor()

    def emit_gui_data_change(self, changed_data):
        self.socketio.emit('gui_data_change', changed_data)