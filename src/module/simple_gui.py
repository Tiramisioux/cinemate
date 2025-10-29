import os
import threading
import time
from PIL import Image, ImageDraw, ImageFont
from module.framebuffer import Framebuffer  # Assuming this is a custom module
import subprocess
import logging
from sugarpie import pisugar
from flask_socketio import SocketIO
import re
from statistics import mean
from module.utils import Utils
from module.redis_controller import ParameterKey
import json
import re


def _to_bool(value) -> bool:
    """Return *value* as bool, accepting common string variants."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)

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
                socketio: SocketIO = None,
                usb_monitor=None,
                serial_handler=None,
                settings=None):
        threading.Thread.__init__(self)
        
        self.daemon = True          # die if the parent dies
        self._running = True        # quit flag
        
        self.current_background_color = "black"
        self.color_mode = "normal"
        
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
        
        self.vu_smoothed = []
        self.vu_peaks = []

        self.vu_smoothing_alpha = 0.4  # Rise factor (0.0–1.0, higher = faster)
        self.vu_decay_factor = 0.1     # Fall factor (0.0–1.0, lower = slower)

        self.socketio = socketio  # Add socketio reference
        
        self.usb_monitor = usb_monitor
        
        self.serial_handler = serial_handler

        # Buffer VU meter and hatch line toggles from settings
        if settings is not None:
            hdmi_cfg = settings.get("hdmi_gui", {})
            self.show_buffer_vu = _to_bool(hdmi_cfg.get("buffer_vu_meter", True))
            self.vu_meter_hatch_lines = _to_bool(hdmi_cfg.get("vu_meter_hatch_lines", True))
        else:
            self.show_buffer_vu = True
            self.vu_meter_hatch_lines = True

        self.background_color_changed = False
        
        # Load sensor values from Redis upon instantiation
        self.load_sensor_values_from_redis()

        self.start()

    # ───────────────── helper: do we have two non-empty clip names? ────────────────
    def _has_two_clips(self, values) -> bool:
        return bool(values.get("clip_name") and values.get("clip_name_cam1"))

    # ───────────────── helper: tweak GUI layout for clip lines ────────────────────
    def _adjust_clip_layout(self, two_clips: bool):
        """Shrink/enlarge the font & Y-positions of the clip-name fields."""
        if two_clips:
            new_size = 24               # ↓ from 41 → 24 px
            y_base   = 1053
            self.layout["clip_name"]["size"]        = new_size
            self.layout["clip_name_cam1"]["size"]   = new_size
            self.layout["clip_name"]["pos"]         = (700, y_base)       # lower line
            self.layout["clip_name_cam1"]["pos"]    = (700, y_base-19)    # 19 px up
        else:
            # Fall back to the original settings
            self.layout["clip_name"]["size"]        = 24
            self.layout["clip_name_cam1"]["size"]   = 24
            self.layout["clip_name"]["pos"]         = (700, 1041)
            self.layout["clip_name_cam1"]["pos"]    = (700, 998)


    def load_sensor_values_from_redis(self):
        """
        Load current sensor values (width, height, bit depth) from Redis.
        """
        try:
            self.width = int(self.redis_controller.get_value(ParameterKey.WIDTH.value) or 1920)
            self.height = int(self.redis_controller.get_value(ParameterKey.HEIGHT.value) or 1080)
            self.bit_depth = int(self.redis_controller.get_value(ParameterKey.BIT_DEPTH.value) or 10)
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

        # Define layout directly as a dict (not nested in another dict)
        self.layout = {
            # column 0
            "fps_label":      {"pos": (  90,   4), "size": 30, "font": "regular"},
            "fps":            {"pos": ( 155,   3), "size": 41, "font": "bold"},

            # column 1
            "shutter_label":  {"pos": ( 313,   4), "size": 30, "font": "regular"},
            "shutter_speed":  {"pos": ( 448,   3), "size": 41, "font": "bold"},

            # NEW COLUMN for EXP
            "exposure_label": {"pos": ( 678,   4), "size": 30, "font": "regular"},
            "exposure_time":  {"pos": ( 740,   3), "size": 41, "font": "bold"},

            # column 3
            "iso_label":      {"pos": (944,   4), "size": 30, "font": "regular"},
            "iso":            {"pos": (983,   3), "size": 41, "font": "bold"},

            # column 4
            "wb_label":       {"pos": (1173,   4), "size": 30, "font": "regular"},
            "color_temp":     {"pos": (1233,   3), "size": 41, "font": "bold"},

            # column 5
            "res_label":      {"pos": (1473,   4), "size": 30, "font": "regular"},
            "res":            {"pos": (1540,   3), "size": 41, "font": "bold"},


            # Bottom row
            "media_label": {"pos": (98, 1050), "size": 30, "font": "regular"},
            "disk_space": {"pos": (192, 1041), "size": 41, "font": "bold"},
            "write_speed": {"pos": (360, 1041), "size": 41, "font": "bold"},

            "recording_time": {"pos": (580, 1041), "size": 41, "font": "bold"},
            
            "clip_label": {"pos": (510, 1050), "size": 30, "font": "regular"},
            "clip_name": {"pos": (640, 1041), "size": 24, "font": "bold"},
            "clip_name_cam1": {"pos": (640, 998), "size": 24, "font": "bold"},

            
            "battery_level": {"pos": (600, 1041), "size": 41, "font": "bold"},
            "cpu_label": {"pos": (1285, 1050), "size": 30, "font": "regular"},
            "cpu_load": {"pos": (1355, 1041), "size": 41, "font": "bold"},
            "cpu_temp_label": {"pos": (1468, 1050), "size": 31, "font": "regular"},
            "cpu_temp": {"pos": (1552, 1041), "size": 41, "font": "bold"},
            "ram_label": {"pos": (1673, 1050), "size": 30, "font": "regular"},
            "ram_load": {"pos": (1741, 1041), "size": 41, "font": "bold"},
        }

        self.colors = {
            "iso_label": {"normal": (136,136,136), "inverse": "black"},
            "iso": {"normal": (249,249,249), "inverse": "black"},
            "shutter_label": {"normal": (136,136,136), "inverse": "black"},
            "shutter_speed": {"normal": (249,249,249), "inverse": "black"},
            "fps_label": {"normal": (136,136,136), "inverse": "black"},
            "fps": {"normal": (249,249,249), "inverse": "black"},
            "fps_actual": {"normal": (136,136,136), "inverse": "black"} ,
            
            "exposure_label": {"normal": (136, 136, 136), "inverse": "black"},
            "exposure_time":  {"normal": (249, 249, 249), "inverse": "black"},
            "zoom_factor":      {"normal": "black", "inverse": "black"},
            "anamorphic_factor": {"normal": "black", "inverse": "black"},
            "sensor": {"normal": (136,136,136), "inverse": "black"},
            "height": {"normal": (249,249,249), "inverse": "black"},
            "width": {"normal": (249,249,249), "inverse": "black"},
            "bit_depth": {"normal": (249,249,249), "inverse": "black"},
            
            "wb_label": {"normal": (136,136,136), "inverse": "black"},
            "color_temp": {"normal": (249,249,249), "inverse": "black"},
            
            "res_label": {"normal": (136,136,136), "inverse": "black"},
            "res": {"normal": (249, 249, 249), "inverse": "black"},
            
            "label": {"normal": (249, 249, 249), "inverse": "black"},
            
            "sensor_cam1":     {"normal": (136,136,136), "inverse": "black"},
            "resolution_cam1": {"normal": (249,249,249), "inverse": "black"},
            "aspect_cam1":     {"normal": (249,249,249), "inverse": "black"},
            "bit_depth_cam1":  {"normal": (249,249,249), "inverse": "black"},

            
            "resolution": {"normal": "black", "inverse": "black"},
            "aspect": {"normal": "black", "inverse": "black"},
            "color_temp_libcamera": {"normal": (136,136,136), "inverse": "black"},
            # "shutter_a_sync_mode": {"normal": "white", "inverse": "black"},
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
            "write_speed": {"normal": (136,136,136), "inverse": "black"},
            "frame_count": {"normal": (136,136,136), "inverse": "black"},
            "recording_time": {"normal": (249,249,249), "inverse": "black"},
            
            "clip_label": {"normal": (136,136,136), "inverse": "black"},
            "clip_name": {"normal": (249,249,249), "inverse": "black"},
            
            "battery_level": {"normal": (249,249,249), "inverse": "black"},
        }

        self.colors["clip_name_cam1"] = self.colors["clip_name"]


        self.fb = None
        self.disp_width = self.disp_height = 0
        self.current_layout = 0  # Default layout; can be changed dynamically
        
        self.left_section_layout = [
            {
                "label": "CAM",
                "items": [
                    {"key": "sensor", "text": lambda v: v.get("sensor", "").upper()},
                    # {"key": "resolution", "text": lambda v: v.get("resolution", "")},
                    {"key": "aspect", "text": lambda v: v.get("aspect", "")},
                    # {"key": "bit_depth", "text": lambda v: str(v.get("bit_depth", "")).replace("b", "") + "b"},
                    # {"key": "exposure_time", "text": lambda v: v.get("exposure_time", "")},
                ]
            },
            {
                "label": "MON",
                "items": [
                    # show zoom only when it isn’t 1.0 ×
                    {"key": "zoom_factor", "text": lambda v: v.get("zoom_factor", "")},
                    {"key": "anamorphic_factor", "text": lambda v: v.get("anamorphic_factor", "")}
                ]
            }
        ]
        
        # ───────────── right side column (mirrors left) ──────────────
        self.right_section_layout = [
            {   # this label will be replaced by _update_cam_section_labels()
                "label": "CAM1",
                "items": [
                    {"key": "sensor_cam1",     "text": lambda v: v.get("sensor_cam1", "").upper()},
                    # {"key": "resolution_cam1", "text": lambda v: v.get("resolution_cam1", "")},
                    {"key": "aspect_cam1",     "text": lambda v: v.get("aspect_cam1", "")},
                    # {"key": "bit_depth_cam1",  "text": lambda v: str(v.get("bit_depth_cam1", "")).replace("b", "") + "b"},
                    {"key": "exposure_time",   "text": lambda v: v.get("exposure_time", "")},   # same shutter sync box
                ]
            },
        ]

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
    
    def _update_cam_section_labels(self):
        """
        Look at the CAMERAS json stored by CinePiManager and set the
        column headers (CAM0 / CAM1 / MON) and which layouts to draw.
        """
        cams_json = self.redis_controller.get_value(ParameterKey.CAMERAS.value) or '[]'
        try:
            cams = json.loads(cams_json)
        except (ValueError, TypeError):
            cams = []

        # defaults (no camera data yet)
        l_lbl, r_lbl = "CAM", "MON"
        self.draw_right_col = False

        if cams:
            cams.sort(key=lambda c: c.get('port', ''))
            l_lbl = cams[0]['port'].upper()        # "CAM0"
            if len(cams) >= 2:
                r_lbl           = cams[1]['port'].upper()   # "CAM1"
                self.draw_right_col = True                  # we have a second column

        # write labels back
        self.left_section_layout[0]["label"]  = l_lbl
        self.right_section_layout[0]["label"] = r_lbl

    def populate_values(self):
        # update section headers first
        self._update_cam_section_labels()
        self.load_sensor_values_from_redis()
        resolution_value = self.estimate_resolution_in_k()

        # ── read CAMERAS json ─────────────────────────────────────
        cams_json = self.redis_controller.get_value(ParameterKey.CAMERAS.value) or "[]"
        try:
            cam_list = json.loads(cams_json)
        except (ValueError, TypeError):
            cam_list = []

        sensor_left  = ""   
        sensor_right = ""
        cam1         = None

        if cam_list:
            cam_list.sort(key=lambda c: c.get("port", ""))
            cam0 = cam_list[0]
            sensor_left = self._format_sensor_name(cam0["model"], cam0["mono"])
            if len(cam_list) > 1:
                cam1 = cam_list[1]
                sensor_right = self._format_sensor_name(cam1["model"], cam1["mono"])

        # ── generic numbers ───────────────────────────────────────
        width  = self.redis_controller.get_value(ParameterKey.WIDTH.value)
        height = self.redis_controller.get_value(ParameterKey.HEIGHT.value)
        try:
            w_int, h_int = int(width), int(height)
            aspect_ratio = round(w_int / h_int, 2) if h_int else "N/A"
        except (TypeError, ValueError):
            aspect_ratio = "N/A"

        # ───────────── build shutter_speed display value ─────────────
        actual_angle = self.redis_controller.get_value(ParameterKey.SHUTTER_A_ACTUAL.value)
        try:
            actual_angle_f = float(actual_angle)
            actual_str = f"{actual_angle_f:.1f}°"
        except (TypeError, ValueError):
            actual_str = str(actual_angle)

        shutter_speed = actual_str

        # if self.cinepi_controller.shutter_a_sync_mode == 1:
        #     extras = []

            # # Nominal angle
            # nom_angle = self.cinepi_controller.shutter_angle_nom
            # if nom_angle is not None:
            #     try:
            #         nom_angle_f = float(nom_angle)
            #         nom_str = f"/ {nom_angle_f:.1f}°"
            #     except (TypeError, ValueError):
            #         nom_str = f"/ {nom_angle}"
            #     extras.append(nom_str)

            # Exposure fraction
            # exposure_fraction = getattr(self.cinepi_controller, "exposure_time_fractions", None)
            # if exposure_fraction:
            #     extras.append(f" / {exposure_fraction}")

            # if extras:
            #     shutter_speed += " (" + ", ".join(extras) + ")"



        values = {
            # top-row stuff
            "resolution":     resolution_value,
            "iso_label":      "EI",
            "iso":            self.redis_controller.get_value(ParameterKey.ISO.value),
            "shutter_label":  "SHUTTER",
            "shutter_speed":  shutter_speed,
            "fps_label":      "FPS",
            "fps":            round(float(self.redis_controller.get_value(ParameterKey.FPS_USER.value))),
            "wb_label":       "WB",
            "color_temp":     f"{self.redis_controller.get_value(ParameterKey.WB_USER.value)} K",
            "color_temp_libcamera": f"/ {self.redis_listener.colorTemp}K",
            "res_label":      "RES",
            "res":            f"{self.width}×{self.height} :{self.bit_depth}b",

            # left column (CAM0)
            "sensor":         sensor_left,
            "aspect":         str(aspect_ratio),
            "exposure_label": "EXP",
            "exposure_time":  str(self.cinepi_controller.exposure_time_fractions),

            # misc labels / live data
            "zoom_factor": "",   # will be filled below if ≠ 1.0
            "anamorphic_factor": f"{self.redis_controller.get_value(ParameterKey.ANAMORPHIC_FACTOR.value)}X",
            "ram_load":       Utils.memory_usage(),
            "cpu_load":       Utils.cpu_load(),
            "cpu_temp":       Utils.cpu_temp(),
            "disk_label":     (self.ssd_monitor.device_name or "").upper()[:4],
            "usb_connected":  bool(self.serial_handler.serial_connected),
            "mic_connected":  self.usb_monitor.usb_mic is not None,
            "keyboard_connected": bool(self.usb_monitor and self.usb_monitor.usb_keyboard),
            "storage_type":   self.redis_controller.get_value(ParameterKey.STORAGE_TYPE.value),
            "write_speed":    self.redis_controller.get_value(ParameterKey.WRITE_SPEED_TO_DRIVE.value) or "0 MB/s",

            # "clip_label": "CLIP",
            "clip_name":    self.redis_controller.get_value(ParameterKey.LAST_DNG_CAM1.value) or "N/A",

            # static captions
            "cam": "CAM", "raw": "RAW", "ram_label": "RAM",
            "cpu_label": "CPU", "cpu_temp_label": "TEMP",
            "media_label": "MEDIA", "mon": "MON",
            
        }
        # ── Zoom factor (preview punch-in) ────────────────────────────────
        try:
            z = float(self.redis_controller.get_value(ParameterKey.ZOOM.value) or 1.0)
        except (TypeError, ValueError):
            z = 1.0
        if abs(z - 1.0) > 1e-3:                    # only show when ≠ 1.0
            values["zoom_factor"] = f"{z:.1f}"

        # ─── recording time ───
        raw_rt = self.redis_controller.get_value(ParameterKey.RECORDING_TIME.value)

        if raw_rt is not None:
            s = str(raw_rt).strip()

            # Only proceed if Redis value is not exactly "0" or 0.0
            try:
                if float(s) == 0:
                    pass  # skip drawing
                else:
                    # 1) Try numeric seconds
                    total = None
                    try:
                        total = int(float(s))
                    except ValueError:
                        # 2) Fallback: parse "HH:MM:SS" or "MM:SS"
                        parts = s.split(":")
                        try:
                            if len(parts) >= 3:
                                h = int(parts[0]); m = int(parts[1]); sec = int(parts[2])
                                total = h * 3600 + m * 60 + sec
                            elif len(parts) == 2:
                                m = int(parts[0]); sec = int(parts[1])
                                total = m * 60 + sec
                            elif len(parts) == 1 and parts[0].isdigit():
                                total = int(parts[0])
                        except (TypeError, ValueError):
                            total = None

                    # format if we have a valid total
                    if total is not None:
                        if total >= 3600:
                            h = total // 3600
                            rem = total % 3600
                            m = rem // 60
                            sec = rem % 60
                            values["recording_time"] = f"{h}:{m}:{sec:02d}"
                        else:
                            m = total // 60
                            sec = total % 60
                            values["recording_time"] = f"{m}:{sec:02d}"
            except ValueError:
                pass  # skip if float conversion fails

        # ───────────────── CLIP / LAST-DNG display ───────────────
        last_cam1_full = self.redis_controller.get_value(ParameterKey.LAST_DNG_CAM1.value)
        last_cam0_full = self.redis_controller.get_value(ParameterKey.LAST_DNG_CAM0.value)

        clip_cam1 = self._format_last_dng(last_cam1_full)
        clip_cam0 = self._format_last_dng(last_cam0_full)

        if clip_cam0 and clip_cam1:
            # two cameras – show CAM1 on the upper line, CAM0 on the baseline
            values["clip_name_cam1"] = clip_cam1
            values["clip_name"]      = clip_cam0
        else:
            pass
            #only one camera – keep it on the baseline row
            values["clip_name"] = clip_cam0 or clip_cam1 or ""
            

        # ── add right-column data when CAM1 exists ────────────────
        if sensor_right and cam1:
            sensor_mode = int(self.redis_controller.get_value(ParameterKey.SENSOR_MODE.value) or 0)
            pk   = cam1["model"] + ("_mono" if cam1["mono"] else "")
            res1 = self.sensor_detect.get_resolution_info(pk, sensor_mode)
            w1   = res1.get("width", 1920)
            h1   = res1.get("height", 1080)
            bd1  = res1.get("bit_depth", 12)

            values.update({
                "sensor_cam1":     sensor_right,
                "resolution_cam1": self.estimate_resolution_in_k(),
                "aspect_cam1":     round(w1 / h1, 2),
                "bit_depth_cam1":  f"{bd1}b",
            })

        # ── housekeeping tweaks (unchanged) ───────────────────────
        frame_count = f"{self.redis_controller.get_value(ParameterKey.FRAMECOUNT.value)} / " \
                    f"{self.redis_controller.get_value(ParameterKey.BUFFER.value)}"
        values["frame_count"] = re.sub(r"[^0-9 /]", "", frame_count)

        values["buffer_used"] = str(
            self.redis_controller.get_value(ParameterKey.BUFFER.value) or "0")
        values["buffer_size"] = str(
            self.redis_controller.get_value(ParameterKey.BUFFER_SIZE.value) or "0")

        # if values["fps"] != int(float(self.redis_controller.get_value(ParameterKey.FPS_USER.value))):
        #     self.colors["fps"]["normal"] = "yellow"
        if self.cinepi_controller.shutter_a_sync_mode != 0:
            self.colors["shutter_speed"]["normal"] = "lightgreen"
            self.colors["fps"]["normal"] = "lightgreen"
        else:
            self.colors["shutter_speed"]["normal"] = (249,249,249)
            self.colors["fps"]["normal"] = (249,249,249)

        values["lock"]        = "LOCK"    if self.cinepi_controller.parameters_lock else ""
        values["low_voltage"] = "VOLTAGE" if self.dmesg_monitor.undervoltage_flag  else ""

        if self.battery_monitor.battery_level is not None:
            values["battery_level"] = f"{self.battery_monitor.battery_level}%"
        self.colors["battery_level"]["normal"] = "lightgreen" if self.battery_monitor.charging else "white"

        if self.ssd_monitor.space_left and self.ssd_monitor.is_mounted:
            mins = (self.ssd_monitor.space_left * 1000) / (self.cinepi_controller.file_size *
                                                        float(self.cinepi_controller.fps) * 60)
            values["disk_space"] = f"{round(mins)} MIN"
            values["write_speed"] = f"{self.ssd_monitor.write_speed_mb_s:.0f} MB/s"
        else:
            values["disk_space"] = "NO DISK"
            values["write_speed"] = ""
        
        if self.ssd_monitor.write_speed_mb_s > 0:
            values["write_speed"] = f"{self.ssd_monitor.write_speed_mb_s:.0f} MB/s"
        
        return values

    def _format_sensor_name(self, name: str, is_mono: bool) -> str:
        """
        Turn 'imx585' or 'IMX585_MONO' into:
            '585'            (colour)
            '585\\nMONO'     (mono)
        """
        if not name:
            return ""

        # upper-case and trim the usual prefixes/suffixes
        n = name.upper()
        if n.startswith("IMX"):
            n = n[3:]
        n = n.replace("_MONO", "").replace("-MONO", "")

        return f"{n}\nMONO" if is_mono else n
    
    def _format_last_dng(self, path: str):
        """
        Turn a full DNG path stored in Redis into the short clip name used
        in the GUI.

        Example
        -------
        /media/RAW/CINEPI_25-07-01_220547_F10_C00000_cam1/
        CINEPI_25-07-01_220547_F10_C00000_000000009.dng
                 ───────────────────────────────┬─────────────────
                 becomes:   CINEPI_25-07-01_220547_F10_C00000

        • Removes the trailing frame counter (“_000000009”)
        • Removes the camera suffix (“_cam0” / “_cam1”)
        • Returns **None** if the input is falsy _or_ literally contains
          the string “None”.
        """
        if not path or "None" in str(path):
            return None

        import os, re

        stem = os.path.splitext(os.path.basename(path))[0]  # filename w/out .dng

        # Strip “…_000000009”
        #stem = re.sub(r'_\d+$', '', stem)

        # Strip camera suffix “…_cam0 / …_cam1”
        stem = re.sub(r'_cam[01]$', '', stem, flags=re.IGNORECASE)

        return stem

    def update_smoothed_vu_levels(self):
        if not self.usb_monitor or not hasattr(self.usb_monitor, "audio_monitor"):
            return

        audio_monitor = self.usb_monitor.audio_monitor
        vu_history = getattr(audio_monitor, "vu_history", None)
        if not vu_history:
            return

        # Transpose history to group per-channel values: [(L1, L2, ...), (R1, R2, ...)]
        vu_transposed = list(zip(*vu_history))

        # Initialize smoothed and peak lists if needed
        if len(vu_transposed) != len(self.vu_smoothed):
            self.vu_smoothed = [0.0] * len(vu_transposed)
            self.vu_peaks = [0.0] * len(vu_transposed)

        for i, channel_history in enumerate(vu_transposed):
            max_level = max(channel_history)
            # Decay smoothing: keep some inertia when values drop
            if max_level < self.vu_smoothed[i]:
                self.vu_smoothed[i] *= (1 - self.vu_decay_factor)
            else:
                self.vu_smoothed[i] = max_level

            # Peak hold
            self.vu_peaks[i] = max(self.vu_peaks[i] * 0.98, self.vu_smoothed[i])

    # ─────────────────────────────────────────────────────────────
    # LEFT-HAND COLUMN  (CAM / MON / SYS …)
    # ─────────────────────────────────────────────────────────────
    def draw_left_sections(self, draw, values):
        label_font = ImageFont.truetype(self.regular_font_path, 26)
        box_font   = ImageFont.truetype(self.bold_font_path,     26)

        BOX_H, BOX_W  = 40, 60
        BOX_COLOR     = (136, 136, 136)
        TEXT_COLOR    = (0,   0,   0)

        label_x       = 19
        box_x         = 15
        y             = 97
        LABEL_SPACING = -4
        BOX_GAP       = 14
        SECTION_GAP   = 60

        # ── CAM / MON sections ───────────────────────────────────
        for section in self.left_section_layout:
            # centre the label over the column
            lbl_w  = draw.textbbox((0,0), section["label"], font=label_font)[2]
            lbl_x  = box_x + (BOX_W - lbl_w)//2
            draw.text((lbl_x, y), section["label"],
                      font=label_font,
                      fill=self.colors["label"][self.color_mode])
            y += BOX_H + LABEL_SPACING

            for item in section["items"]:
                val = item["text"](values)
                if not val:
                    continue

                for part in str(val).split('\n'):
                    # choose box colour depending on item
                    if item["key"] == "zoom_factor":
                        box_fill = (249, 249, 249)   # white box
                    else:
                        box_fill = BOX_COLOR         # default grey
                    draw.rectangle([box_x, y, box_x + BOX_W, y + BOX_H],
                                   fill=box_fill)

                    if item["key"] in ("aspect", "anamorphic_factor"):
                        m = 2
                        inner = [box_x + m, y + m,
                                 box_x + BOX_W - m, y + BOX_H - m]
                        draw.rectangle(inner, outline=(0, 0, 0), width=2)

                    tw, th = draw.textbbox((0,0), part, font=box_font)[2:]
                    tx = box_x + (BOX_W - tw)//2
                    ty = y     + (BOX_H - th)//2
                    draw.text((tx, ty), part, font=box_font, fill=TEXT_COLOR)

                    y += BOX_H + BOX_GAP

            y += SECTION_GAP

        # ── SYS section (USB / MIC / KEY / storage) ──────────────
        show_sys = any([
            values.get("usb_connected"),
            values.get("mic_connected"),
            values.get("keyboard_connected"),
            values.get("storage_type") not in [None, "", "none"]
        ])

        if show_sys:
            draw.text((label_x + 1, y), "SYS",
                      font=label_font,
                      fill=self.colors["label"][self.color_mode])
            y += BOX_H + LABEL_SPACING

            for key, lbl in [("usb_connected", "SER"),
                             ("mic_connected", "MIC"),
                             ("keyboard_connected", "KEY")]:
                if not values.get(key):
                    continue
                draw.rectangle([box_x, y, box_x + BOX_W, y + BOX_H],
                               fill=BOX_COLOR)
                tw, th = draw.textbbox((0, 0), lbl, font=box_font)[2:]
                tx = box_x + (BOX_W - tw) // 2
                ty = y      + (BOX_H - th) // 2
                draw.text((tx, ty), lbl, font=box_font, fill=TEXT_COLOR)
                y += BOX_H + BOX_GAP

            storage = str(values.get("storage_type", "")).upper()
            if storage and storage != "NONE":
                draw.rectangle([box_x, y, box_x + BOX_W, y + BOX_H],
                               fill=BOX_COLOR)
                tw, th = draw.textbbox((0, 0), storage, font=box_font)[2:]
                tx = box_x + (BOX_W - tw) // 2
                ty = y      + (BOX_H - th) // 2
                draw.text((tx, ty), storage, font=box_font, fill=TEXT_COLOR)
                y += BOX_H + BOX_GAP
            
            # write_speed = values.get("write_speed", "")
            # if write_speed:
            #     text = write_speed.split()[0]
            #     draw.rectangle([box_x, y, box_x + BOX_W, y + BOX_H],
            #                  fill=BOX_COLOR)
            #     tw, th = draw.textbbox((0, 0), text, font=box_font)[2:]
            #     tx = box_x + (BOX_W - tw) // 2
            #     ty = y      + (BOX_H - th) // 2
            #     draw.text((tx, ty), text, font=box_font, fill=TEXT_COLOR)
            #     y += BOX_H + BOX_GAP


    # ─────────────────────────────────────────────────────────────
    # RIGHT-HAND MIRROR COLUMN
    # ─────────────────────────────────────────────────────────────
    def draw_right_sections(self, draw, values):
        label_font = ImageFont.truetype(self.regular_font_path, 26)
        box_font   = ImageFont.truetype(self.bold_font_path,     24)

        BOX_H, BOX_W  = 40, 60
        BOX_COLOR     = (136, 136, 136)
        TEXT_COLOR    = (0,   0,   0)

        box_pad_x     = self.disp_width - 15 - BOX_W
        y             = 97
        LABEL_SPACING = -4
        BOX_GAP       = 14
        SECTION_GAP   = 60

        for section in self.right_section_layout:
            lbl_w = draw.textbbox((0,0), section["label"], font=label_font)[2]
            lbl_x = box_pad_x + (BOX_W - lbl_w)//2      # centred
            draw.text((lbl_x, y), section["label"],
                      font=label_font,
                      fill=self.colors["label"][self.color_mode])
            y += BOX_H + LABEL_SPACING

            for item in section["items"]:
                val = item["text"](values)
                if not val:
                    continue
                for part in str(val).split('\n'):
                    draw.rectangle([box_pad_x, y,
                                    box_pad_x + BOX_W, y + BOX_H],
                                   fill=BOX_COLOR)
                    tw, th = draw.textbbox((0,0), part, font=box_font)[2:]
                    tx = box_pad_x + (BOX_W - tw)//2
                    ty = y         + (BOX_H - th)//2
                    draw.text((tx, ty), part, font=box_font, fill=TEXT_COLOR)
                    y += BOX_H + BOX_GAP
            y += SECTION_GAP

    def draw_right_vu_meter(self, draw, amplification_factor=4):
        if not self.usb_monitor or not hasattr(self.usb_monitor, "audio_monitor"):
            return

        monitor = self.usb_monitor.audio_monitor
        vu_levels = self.vu_smoothed
        vu_peaks = self.vu_peaks

        if not monitor.running or not vu_levels:
            return

        n_channels = len(vu_levels)
        bar_width = 10
        spacing = 8
        margin_right = 32
        bar_height = 200
        margin_bottom = 80

        base_y = self.disp_height - margin_bottom - bar_height
        total_width = n_channels * bar_width + (n_channels - 1) * spacing
        base_x = self.disp_width - margin_right - total_width

        def level_to_height(level):
            import math
            amplified_level = min(level * amplification_factor, 100)
            scaled = math.log10(1 + 9 * (amplified_level / 100))
            return int(scaled * bar_height)

        def draw_bar(x, width, level, peak):
            h = level_to_height(level)
            peak_h = level_to_height(peak)
            draw.rectangle([x, base_y, x + width, base_y + bar_height], fill=(50, 50, 50))
            color = (0, 255, 0) if level < 60 else (255, 255, 0) if level < 85 else (255, 0, 0)
            draw.rectangle([x, base_y + bar_height - h, x + width, base_y + bar_height], fill=color)
            draw.rectangle([x, base_y + bar_height - peak_h - 2, x + width, base_y + bar_height - peak_h], fill=(255, 255, 255))

        for i in range(n_channels):
            x = base_x + i * (bar_width + spacing)
            draw_bar(x, bar_width, vu_levels[i], vu_peaks[i])

        # Optional: Draw channel labels
        label_font = ImageFont.truetype(self.regular_font_path, 16)
        labels = ["L", "R"] if n_channels == 2 else [str(i+1) for i in range(n_channels)]
        for i, label in enumerate(labels):
            text_bbox = draw.textbbox((0, 0), label, font=label_font)
            text_x = base_x + i * (bar_width + spacing) + (bar_width - (text_bbox[2] - text_bbox[0])) // 2
            text_y = base_y + bar_height + 5
            draw.text((text_x, text_y), label, font=label_font, fill=(249,249,249))

    # ─────────────────────────────────────────────────────────────
    # FRAME-BUFFER “VU”  (queued frames vs. capacity)
    # ─────────────────────────────────────────────────────────────
    def draw_framebuffer_vu_meter(self, draw):
        """
        Visualises the RAM-buffer usage:
            • height  = used / total
            • colour  = green <70 %, yellow <90 %, red ≥90 %
            • ticks   = 25 / 50 / 75 / 100 %
            • caption = “used / total”
        """
        # ── fetch numbers from Redis safely ─────────────────────────────
        try:
            raw_used  = self.redis_controller.get_value(ParameterKey.BUFFER.value)
            used = int(raw_used) if raw_used is not None else 0
        except (TypeError, ValueError):
            used = 0

        try:
            raw_total = self.redis_controller.get_value(ParameterKey.BUFFER_SIZE.value)
            total = int(raw_total) if raw_total is not None else 0
        except (TypeError, ValueError):
            total = 0

        # avoid zero‐division
        if total <= 0:
            total = 1

        # clamp between 0.0 and 1.0
        usage = max(0.0, min(used / total, 1.0))

        # ── colour code by utilisation ────────────────────────────────
        if   usage < 0.70: fill_colour = (  0, 255,   0)
        elif usage < 0.90: fill_colour = (255, 255,   0)
        else:              fill_colour = (255,   0,   0)

        # ── geometry constants (match existing GUI) ───────────────────
        BAR_H      = 200
        BAR_W      = 28
        BASE_X     = 30
        GAP_BOTTOM = 80

        base_y = self.disp_height - GAP_BOTTOM - BAR_H
        base_x = BASE_X

        rec         = int(self.redis_controller.get_value(ParameterKey.REC.value) or 0)
        border_col  = (50, 50, 50) if rec else (249, 249, 249)
        back_col    = (50, 50, 50)

        # ── erase & redraw the pillar ────────────────────────────────
        draw.rectangle([base_x, base_y, base_x + BAR_W, base_y + BAR_H],
                    fill=self.current_background_color)
        draw.rectangle([base_x, base_y, base_x + BAR_W, base_y + BAR_H],
                    fill=back_col)

        filled_h = int(BAR_H * usage)
        if filled_h:
            draw.rectangle([base_x,
                            base_y + (BAR_H - filled_h),
                            base_x + BAR_W,
                            base_y + BAR_H],
                        fill=fill_colour)
        # ── optional hatch lines ───────────────────────────────────
        if self.vu_meter_hatch_lines:
            for dy in range(0, filled_h, 2):
                y = base_y + BAR_H - 1 - dy
                draw.line([(base_x, y), (base_x + BAR_W, y)], fill=border_col)

        # ── tick marks at 25/50/75/100 % (unchanged) ────────────────
        for frac in (0.25, 0.50, 0.75, 1.00):
            y = base_y + BAR_H - int(BAR_H * frac)
            draw.line([(base_x, y), (base_x + BAR_W, y)], fill=(136,136,136))


    def draw_gui(self, values):
        
        # ── shrink clip-name text when two cameras are active ─────────────────────────
        self._adjust_clip_layout(self._has_two_clips(values))

        previous_background_color = self.get_background_color()

        # ─── choose background colour & colour-mode ────────────────────
        prev_bg = self.get_background_color()      # ← fixed () call
        
        try:
            preroll_active = int(
                self.redis_controller.get_value(
                    ParameterKey.STORAGE_PREROLL_ACTIVE.value
                )
                or 0
            )
        except (TypeError, ValueError):
            preroll_active = 0

        if preroll_active:
            self.current_background_color = "blue"
            self.color_mode = "inverse"

        elif int(self.redis_controller.get_value(ParameterKey.REC.value)) and self.redis_listener.drop_frame == 1:
            # at least one camera is actively recording
            self.current_background_color = "purple"
            self.color_mode = "inverse"

        if not preroll_active:
            if int(self.redis_controller.get_value(ParameterKey.REC.value)) == 1:
                # at least one camera is actively recording
                self.current_background_color = "red"
                self.color_mode = "inverse"

            elif int(self.redis_controller.get_value(ParameterKey.IS_WRITING_BUF.value) or 0):
                # recording has stopped but buffer still flushing to disk
                self.current_background_color = "green"
                self.color_mode = "inverse"

            elif int(self.redis_controller.get_value(ParameterKey.IS_BUFFERING.value) or 0):
                # cameras are building up the RAM buffer
                self.current_background_color = "green"
                self.color_mode = "inverse"

            elif int(values["ram_load"].rstrip('%')) > 95:
                # safety: RAM nearly full – warn & auto-stop
                self.current_background_color = "yellow"
                self.color_mode = "inverse"
                self.cinepi_controller.rec()        # stop recording

            else:
                # idle
                self.current_background_color = "black"
                self.color_mode = "normal"
            
        if self.current_background_color != previous_background_color:
            self.background_color_changed = True
            try:
                self.emit_background_color_change()
            except Exception as e:
                logging.error(f"Error emitting background color change: {e}")
        else:
            self.background_color_changed = False

        current_values = values
        if hasattr(self, 'previous_values'):
            changed_data = {}
            for key, value in current_values.items():
                if value != self.previous_values.get(key):
                    changed_data[key] = value
            if changed_data:
                try:
                    self.emit_gui_data_change(changed_data)
                except Exception:
                    pass
        self.previous_values = current_values.copy()

        if not self.fb:
            return

        image = Image.new("RGBA", self.fb.size)
        draw = ImageDraw.Draw(image)
        draw.rectangle(((0, 0), self.fb.size), fill=self.current_background_color)

        # Draw left-hand labels and boxes dynamically
        self.draw_left_sections(draw, values)

        # Get sensor resolution
        self.width = int(self.redis_controller.get_value(ParameterKey.WIDTH.value))
        self.height = int(self.redis_controller.get_value(ParameterKey.HEIGHT.value))
        self.aspect_ratio = self.width / self.height
        self.anamorphic_factor = float(self.redis_controller.get_value(ParameterKey.ANAMORPHIC_FACTOR.value))
        lores_width = int(self.redis_controller.get_value(ParameterKey.LORES_WIDTH.value))
        lores_height = int(self.redis_controller.get_value(ParameterKey.LORES_HEIGHT.value))

        frame_width = 1920
        frame_height = 1080
        padding_x = 92
        padding_y = 46
        max_draw_width = frame_width - (2 * padding_x)
        max_draw_height = frame_height - (2 * padding_y)

        adjusted_lores_width = lores_width * self.anamorphic_factor
        adjusted_lores_height = lores_height * self.anamorphic_factor
        adjusted_aspect_ratio = adjusted_lores_width / adjusted_lores_height

        if adjusted_aspect_ratio >= 1:
            preview_w = max_draw_width
            preview_h = int(preview_w / adjusted_aspect_ratio)
            if preview_h > max_draw_height:
                preview_h = max_draw_height
                preview_w = int(preview_h * adjusted_aspect_ratio)
        else:
            preview_h = max_draw_height
            preview_w = int(preview_h * adjusted_aspect_ratio)
            if preview_w > max_draw_width:
                preview_w = max_draw_width
                preview_h = int(preview_w / adjusted_aspect_ratio)

        preview_x = (frame_width - preview_w) // 2
        preview_y = (frame_height - preview_h) // 2

        line_color = (249, 249, 249)

        draw.rectangle(
            [preview_x, preview_y, preview_x + preview_w, preview_y + preview_h],
            outline=line_color,
            width=2
        )

        current_layout = self.layout

        lock_mapping = {
            "iso": "iso_lock",
            "shutter_speed": "shutter_a_nom_lock",
            "fps": "fps_lock",
            "exposure_time": "shutter_a_nom_lock",

        }

        for element, info in current_layout.items():
            if values.get(element) is None:
                continue
            position = info["pos"]
            font_size = info.get("size", 12)  # 12 is the default font size
            font = ImageFont.truetype(
                os.path.realpath(self.bold_font_path if info.get("font", "bold") == "bold" else self.regular_font_path),
                font_size
            )
            value = str(values.get(element, ''))
            color_mode = self.color_mode
            color = self.colors.get(element, {}).get(color_mode, "white")

            if element == "sensor" and info.get("align") == "right":
                text_bbox = draw.textbbox((0, 0), value, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                x = position[0] + info["width"] - text_width
                position = (x, position[1])

            if element in lock_mapping and getattr(self.cinepi_controller, lock_mapping[element]):
                # Only draw inside the box
                self.draw_rounded_box(draw, value, position, font_size, 5, "black", "white", image)
            else:
                draw.text(position, value, font=font, fill=color)
                
        self.update_smoothed_vu_levels()
        self.draw_right_vu_meter(draw)
        if self.show_buffer_vu:
            self.draw_framebuffer_vu_meter(draw)

        vu = self.vu_smoothed  # Or .usb_monitor.audio_monitor.vu_levels if you want raw
        # if vu:
        #     levels = " | ".join([f"Ch{i+1}={v:.1f}%" for i, v in enumerate(vu)])
        #     logging.info(f"Mic levels: {levels}")
        # else:
        #     logging.info("Mic level: No VU data available.")

        if self.draw_right_col:
            self.draw_right_sections(draw, values)


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

    def clear_framebuffer(self):
        if self.fb:
            blank_image = Image.new("RGBA", self.fb.size, "black")
            self.fb.show(blank_image)
            
    def stop(self):
        """Ask the GUI thread to exit, wait for it, then blank fb0."""
        self._running = False
        self.join()                     # wait for run() to finish
        self.clear_framebuffer()        # black screen


    def run(self):
        try:
            self.vu_left_peak = 0
            self.vu_right_peak = 0
            self.vu_left_smoothed = 0
            self.vu_right_smoothed = 0
            self.vu_decay_factor = 0.2

            while self._running:
                values = self.populate_values()
                self.update_smoothed_vu_levels()
                self.draw_gui(values)
                time.sleep(0.2)
        finally:
            pass

    # def emit_gui_data_change(self, changed_data):
    #     self.socketio.emit('gui_data_change', changed_data)
        
#         fsck = redis.get_value("FSCK_STATUS", "")
# if fsck.startswith("FAIL"):
#     show_red_icon(fsck)
# elif fsck.startswith("OK"):
#     show_green_icon(fsck)
# else:
#     show_gray_icon("no data")
