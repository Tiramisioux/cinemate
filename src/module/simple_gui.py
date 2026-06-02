import os
import threading
import time
import wave
from PIL import Image, ImageDraw, ImageFont
from module.console_display import claim_console_for_framebuffer, release_console_to_text
from module.framebuffer import Framebuffer, acquire_framebuffer
from module.config_loader import load_settings
import subprocess
import logging
from sugarpie import pisugar
from flask_socketio import SocketIO
import re
from statistics import mean
from module.utils import Utils
from module.redis_controller import ParameterKey
from module.dynamic_resolution import dynamic_resolution_indicator_active
import json
import re

RECORDER_VU_REDIS_KEY    = "audio_vu"
AUDIO_RESAMPLING_REDIS_KEY = "audio_resampling"
WAV_RESAMPLING_COLOR     = (190, 190, 190)   # lighter grey while WAV is being post-processed
DROP_WARNING_COLOR = (120, 40, 180)
SYNC_WARNING_COLOR = (255, 0, 255)
SYNC_FLASH_COLOR = "magenta"
RESOLUTION_SWITCHING_COLOR = (176, 176, 176)
PREVIEW_PADDING_X = 94
PREVIEW_PADDING_Y = 50
PREVIEW_GUIDE_OUTLINE_WIDTH = 2


def _to_bool(value) -> bool:
    """Return *value* as bool, accepting common string variants."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _to_int(value, default=None):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _calculate_preview_guide_rect(
    frame_width,
    frame_height,
    sensor_width,
    sensor_height,
    anamorphic_factor=1.0,
    outline_width=PREVIEW_GUIDE_OUTLINE_WIDTH,
):
    window_aspect_ratio = sensor_width / sensor_height
    max_draw_width = frame_width - (2 * PREVIEW_PADDING_X)
    max_draw_height = frame_height - (2 * PREVIEW_PADDING_Y)

    if (max_draw_width / max_draw_height) > window_aspect_ratio:
        window_h = max_draw_height
        window_w = int(window_h * window_aspect_ratio)
    else:
        window_w = max_draw_width
        window_h = int(window_w / window_aspect_ratio)

    window_x = (frame_width - window_w) // 2
    window_y = (frame_height - window_h) // 2

    stream_h = min(720, max_draw_height)
    stream_w = int(stream_h * window_aspect_ratio * anamorphic_factor)
    if stream_w > max_draw_width:
        stream_w = max_draw_width
        stream_h = int(round(max_draw_width / (window_aspect_ratio * anamorphic_factor)))
    stream_w -= stream_w % 2
    stream_h -= stream_h % 2

    image_x_offset = 0
    image_y_offset = 0
    image_w = window_w
    image_h = window_h
    if stream_w * window_h > window_w * stream_h:
        image_h = window_w * stream_h // stream_w
        image_y_offset = (window_h - image_h) // 2
    else:
        image_w = window_h * stream_w // stream_h
        image_x_offset = (window_w - image_w) // 2

    preview_x = window_x + image_x_offset
    preview_y = window_y + image_y_offset

    return [
        max(0, preview_x - outline_width),
        max(0, preview_y - outline_width),
        min(frame_width - 1, preview_x + image_w + outline_width - 1),
        min(frame_height - 1, preview_y + image_h + outline_width - 1),
    ]


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
        
        # Load settings, not sure when the settings will be None so left the code here
        self.settings = settings or load_settings("/home/pi/cinemate/src/settings.json")
        
        self.setup_resources()
        self.display_poll_interval = 1.0
        self._last_display_probe_ts = 0.0
        self.display_restart_cooldown = 5.0
        self._display_probe_count = 0
        self._preview_restart_on_attach = False
        self._pending_display_camera_restart = False
        self._restart_waiting_logged = False
        self._last_display_restart_ts = 0.0
        self.check_display(force=True)

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
        self._socketio_deferred_events = set()
        
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
        self.target_fps = 12
        self.min_frame_interval = 1 / self.target_fps
        self.slow_refresh_interval = 1.0
        self._redraw_event = threading.Event()
        self._fast_dirty = True
        self._slow_dirty = True
        self._last_draw_ts = 0.0
        self._last_slow_refresh_ts = 0.0
        self._font_cache = {}
        self._cached_cams_json = None
        self._cached_cams = []
        self._slow_values = {}
        self._clear_framebuffer_on_exit = False
        self._release_console_on_exit = False
        self._display_teardown_done = False
        self._stop_lock = threading.Lock()
        self._frames_off_sync_prev = False
        self._sync_flash_until = 0.0
        
        # Load sensor values from Redis upon instantiation
        self.load_sensor_values_from_redis()
        self.redis_controller.redis_parameter_changed.subscribe(self._handle_redis_change)

        self.start()

    # ───────────────── helper: do we have two non-empty clip names? ────────────────
    def _has_two_clips(self, values) -> bool:
        return bool(values.get("clip_name") and values.get("clip_name_cam1"))

    def _dynamic_resolution_indicator_active(self) -> bool:
        controller = self.cinepi_controller
        return dynamic_resolution_indicator_active(
            enabled=self.redis_controller.get_value(
                ParameterKey.DYNAMIC_RESOLUTION_ENABLED.value,
                getattr(controller, "dynamic_resolution_enabled", False),
            ),
            active=self.redis_controller.get_value(
                ParameterKey.DYNAMIC_RESOLUTION_ACTIVE.value,
                getattr(controller, "dynamic_resolution_active", False),
            ),
            current_mode=self.redis_controller.get_value(
                ParameterKey.SENSOR_MODE.value,
                getattr(controller, "sensor_mode", None),
            ),
            desired_mode=self.redis_controller.get_value(
                ParameterKey.DYNAMIC_RESOLUTION_DESIRED_MODE.value,
                getattr(controller, "dynamic_resolution_desired_mode", None),
            ),
            sensor_modes=getattr(self.sensor_detect, "res_modes", None),
        )

    # ───────────────── helper: tweak GUI layout for clip lines ────────────────────
    def _adjust_clip_layout(self, two_clips: bool):
        """Shrink/enlarge the font & Y-positions of the clip-name fields."""
        if two_clips:
            new_size = 20               # ↓ from 41 → 24 px
            y_base   = 1053
            self.layout["clip_name"]["size"]        = new_size
            self.layout["clip_name_cam1"]["size"]   = new_size
            self.layout["clip_name"]["pos"]         = (720, y_base)       # lower line
            self.layout["clip_name_cam1"]["pos"]    = (720, y_base-19)    # 19 px up
        else:
            # Fall back to the original settings
            self.layout["clip_name"]["size"]        = 20
            self.layout["clip_name_cam1"]["size"]   = 20
            self.layout["clip_name"]["pos"]         = (720, 1050)
            self.layout["clip_name_cam1"]["pos"]    = (720, 1050)


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

    def set_socketio(self, socketio: SocketIO):
        self.socketio = socketio
        self._socketio_deferred_events.clear()

    def _emit_socketio_event(self, event_name, payload):
        if self.socketio is None:
            if event_name not in self._socketio_deferred_events:
                logging.debug("SocketIO not initialized; skipping %s until stream startup.", event_name)
                self._socketio_deferred_events.add(event_name)
            return False

        self.socketio.emit(event_name, payload)
        return True

    def emit_background_color_change(self):
        return self._emit_socketio_event(
            'background_color_change',
            {'background_color': self.current_background_color},
        )

    def emit_gui_data_change(self, changed_data):
        return self._emit_socketio_event('gui_data_change', changed_data)

    def _configured_display_size(self, fb: Framebuffer):
        hdmi_config = self.settings.get("hdmi_display", {})

        try:
            width = int(hdmi_config.get("width") or fb.size[0])
        except (TypeError, ValueError):
            width = fb.size[0]

        try:
            height = int(hdmi_config.get("height") or fb.size[1])
        except (TypeError, ValueError):
            height = fb.size[1]

        if fb.size[0] > 0 and fb.size[1] > 0:
            width = min(width, fb.size[0])
            height = min(height, fb.size[1])

        return width, height

    def check_display(self, force=False):
        now = time.monotonic()
        if not force and (now - self._last_display_probe_ts) < self.display_poll_interval:
            return False

        self._last_display_probe_ts = now
        initial_probe = self._display_probe_count == 0
        self._display_probe_count += 1
        had_display = self.fb is not None
        fb = acquire_framebuffer(0)

        if fb is None:
            if initial_probe or had_display:
                self._preview_restart_on_attach = True
                self._pending_display_camera_restart = False
                self._restart_waiting_logged = False
            if had_display:
                logging.info("HDMI framebuffer unavailable; switching GUI to headless mode")
                self.fb = None
                self.disp_width = 0
                self.disp_height = 0
                return True
            return False

        disp_width, disp_height = self._configured_display_size(fb)
        display_changed = (
            self.fb is None
            or self.fb.size != fb.size
            or self.fb.bits_per_pixel != fb.bits_per_pixel
            or self.disp_width != disp_width
            or self.disp_height != disp_height
        )

        self.fb = fb
        self.disp_width = disp_width
        self.disp_height = disp_height

        if display_changed:
            requested_width = self.settings.get("hdmi_display", {}).get("width", fb.size[0])
            requested_height = self.settings.get("hdmi_display", {}).get("height", fb.size[1])
            claim_console_for_framebuffer()
            logging.info(
                "HDMI framebuffer ready. fb0=%sx%s (%sbpp), GUI=%sx%s",
                fb.size[0],
                fb.size[1],
                fb.bits_per_pixel,
                self.disp_width,
                self.disp_height,
            )
            if (self.disp_width, self.disp_height) != (requested_width, requested_height):
                logging.warning(
                    "Configured HDMI canvas %sx%s exceeds active framebuffer %sx%s; using the active framebuffer size",
                    requested_width,
                    requested_height,
                    fb.size[0],
                    fb.size[1],
                )
            if not had_display and self._preview_restart_on_attach:
                self._pending_display_camera_restart = True
                self._restart_waiting_logged = False
                logging.info(
                    "HDMI connected after headless start/loss; camera restart queued for preview recovery"
                )

        return display_changed

    def _display_restart_allowed(self) -> bool:
        return not (
            _to_bool(self.redis_controller.get_value(ParameterKey.IS_RECORDING.value) or 0)
            or _to_bool(self.redis_controller.get_value(ParameterKey.IS_WRITING.value) or 0)
        )

    def _maybe_restart_camera_for_display_attach(self):
        if not self._pending_display_camera_restart:
            return

        now = time.monotonic()
        if (now - self._last_display_restart_ts) < self.display_restart_cooldown:
            return

        if not self._display_restart_allowed():
            if not self._restart_waiting_logged:
                logging.info("HDMI preview restart deferred until recording and disk writes finish")
                self._restart_waiting_logged = True
            return

        self._last_display_restart_ts = now
        self._pending_display_camera_restart = False
        self._preview_restart_on_attach = False
        self._restart_waiting_logged = False

        try:
            logging.info("Restarting cinepi-raw after HDMI attach so preview binds to the active display")
            self.cinepi_controller.restart_camera()
            self._fast_dirty = True
            self._slow_dirty = True
        except Exception as exc:
            self._pending_display_camera_restart = True
            self._preview_restart_on_attach = True
            logging.warning("Failed to restart camera after HDMI attach: %s", exc)

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
            "clip_name": {"pos": (640, 1041), "size": 18, "font": "bold"},
            "clip_name_cam1": {"pos": (640, 998), "size": 18, "font": "bold"},

            
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
            },
            {
                "label": "AUD",
                "condition": lambda v: bool(v.get("mic_connected")),
                "items": [
                    {"key": "mic_sample_rate", "text": lambda v: v.get("mic_sample_rate", "")},
                    {"key": "mic_bit_depth", "text": lambda v: v.get("mic_bit_depth", "")},
                    {"key": "mic_wav_saved", "text": lambda v: "WAV" if v.get("mic_wav_saved") else ""},

                    # {"key": "frames_in_sync", "text": lambda v: "SYNC" if v.get("frames_in_sync") else ""},
                ],
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
    
    def _update_cam_section_labels(self, cams=None):
        """
        Look at the CAMERAS json stored by CinePiManager and set the
        column headers (CAM0 / CAM1 / MON) and which layouts to draw.
        """
        cams = cams or []

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

    def _get_camera_list(self):
        cams_json = self.redis_controller.get_value(ParameterKey.CAMERAS.value) or "[]"
        if cams_json != self._cached_cams_json:
            try:
                cams = json.loads(cams_json)
            except (ValueError, TypeError):
                cams = []
            if cams:
                cams.sort(key=lambda c: c.get("port", ""))
            self._cached_cams_json = cams_json
            self._cached_cams = cams
        return self._cached_cams

    def _refresh_slow_values(self):
        latest_recording_info = self._slow_values.get("latest_recording_info", (None, 0, 0, -1))
        wav_duration_valid = False
        cpu_load = self._slow_values.get("cpu_load", "0%")
        cpu_temp = self._slow_values.get("cpu_temp", "--")

        try:
            cpu_load = Utils.cpu_load()
        except Exception:
            pass

        try:
            cpu_temp = Utils.cpu_temp()
        except Exception:
            pass

        if self.ssd_monitor:
            try:
                latest_recording_info = self.ssd_monitor.get_latest_recording_info()
            except Exception:
                pass

        try:
            folder_path = latest_recording_info[0] if latest_recording_info else None
            max_frame_idx = latest_recording_info[3] if latest_recording_info and len(latest_recording_info) > 3 else -1
            fps = float(self.redis_controller.get_value(ParameterKey.FPS.value) or 0)
            wav_duration_valid = self._validate_wav_length(folder_path, max_frame_idx, fps)
        except Exception:
            wav_duration_valid = False

        self._slow_values.update({
            "cpu_load": cpu_load,
            "cpu_temp": cpu_temp,
            "latest_recording_info": latest_recording_info,
            "wav_duration_valid": wav_duration_valid,
        })
        self._last_slow_refresh_ts = time.monotonic()

    def _maybe_refresh_slow_values(self):
        if (
            not self._slow_values
            or (time.monotonic() - self._last_slow_refresh_ts) >= self.slow_refresh_interval
        ):
            self._refresh_slow_values()

    def _handle_redis_change(self, _data):
        self._fast_dirty = True
        self._redraw_event.set()

    def _vu_active(self):
        return self._get_recorder_vu_levels() is not None

    def _get_font(self, kind: str, size):
        font_size = max(1, int(round(size)))
        key = (kind, font_size)
        font = self._font_cache.get(key)
        if font is None:
            path = self.bold_font_path if kind == "bold" else self.regular_font_path
            font = ImageFont.truetype(os.path.realpath(path), font_size)
            self._font_cache[key] = font
        return font

    def populate_values(self):
        # update section headers first
        cam_list = self._get_camera_list()
        self._update_cam_section_labels(cam_list)
        self._maybe_refresh_slow_values()
        self.load_sensor_values_from_redis()
        resolution_value = self.estimate_resolution_in_k()
        resolution_switching = _to_bool(
            self.redis_controller.get_value(ParameterKey.RESOLUTION_SWITCHING.value, 0)
        )
        display_width = self.width
        display_height = self.height
        display_bit_depth = self.bit_depth
        if resolution_switching:
            display_width = _to_int(
                self.redis_controller.get_value(ParameterKey.RESOLUTION_TARGET_WIDTH.value),
                display_width,
            )
            display_height = _to_int(
                self.redis_controller.get_value(ParameterKey.RESOLUTION_TARGET_HEIGHT.value),
                display_height,
            )
            display_bit_depth = _to_int(
                self.redis_controller.get_value(ParameterKey.RESOLUTION_TARGET_BIT_DEPTH.value),
                display_bit_depth,
            )

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
            "res":            f"{display_width}×{display_height} :{display_bit_depth}b",
            "resolution_switching": resolution_switching,

            # left column (CAM0)
            "sensor":         sensor_left,
            "aspect":         str(aspect_ratio),
            "exposure_label": "EXP",
            "exposure_time":  str(self.cinepi_controller.exposure_time_fractions),

            # misc labels / live data
            "zoom_factor": "",   # will be filled below
            "zoom_is_default": True,
            "anamorphic_factor": f"{self.redis_controller.get_value(ParameterKey.ANAMORPHIC_FACTOR.value)}X",
            "ram_load":       Utils.memory_usage(),
            "cpu_load":       self._slow_values.get("cpu_load", "0%"),
            "cpu_temp":       self._slow_values.get("cpu_temp", "--"),
            "disk_label":     (self.ssd_monitor.device_name or "").upper()[:4],
            "usb_connected":  bool(self.serial_handler.serial_connected),
            "mic_connected":  self.usb_monitor.usb_mic is not None,
            "mic_wav_saved":  False,
            "keyboard_connected": bool(self.usb_monitor and self.usb_monitor.usb_keyboard),
            "storage_type":   self.redis_controller.get_value(ParameterKey.STORAGE_TYPE.value),
            "write_speed":    self.redis_controller.get_value(ParameterKey.WRITE_SPEED_TO_DRIVE.value) or "0 MB/s",

            # "clip_label": "CLIP",
            "clip_name":    self.redis_controller.get_value(ParameterKey.LAST_DNG_CAM1.value) or "N/A",

            # static captions
            "cam": "CAM", "raw": "RAW", "ram_label": "RAM",
            "cpu_label": "CPU", "cpu_temp_label": "TEMP",
            "media_label": "MEDIA", "mon": "MON",
            "drop_frame_live": int(self.redis_controller.get_value(ParameterKey.DROP_FRAME.value) or 0) == 1,
            "drop_frame_count": int(self.redis_controller.get_value(ParameterKey.DROP_FRAME_COUNT.value) or 0),
            "drop_frame_during_last_take": int(self.redis_controller.get_value(ParameterKey.DROP_FRAME_DURING_LAST_TAKE.value) or 0) == 1,
            "tc_hole_count": int(self.redis_controller.get_value(ParameterKey.TC_HOLE_COUNT.value) or 0),
            "missing_frame_count": int(self.redis_controller.get_value(ParameterKey.MISSING_FRAME_COUNT.value) or 0),

        }
        # drop_frame_latched drives the persistent UI warning overlay.
        # Option 1: live drop_frame pulse = TC hole advisory (flashes during recording).
        # Option 2: drop_frame_during_last_take = only set when files are genuinely
        #           missing, so a complete take never latches the post-take indicator.
        # Option 3: missing_frame_count is the authoritative shortfall count;
        #           tc_hole_count is available for display but does not latch on its own.
        values["drop_frame_latched"] = (
            values["drop_frame_live"]             # real-time TC hole pulse (advisory)
            or values["drop_frame_during_last_take"]  # genuine missing files last take
        )
        try:
            values["frames_in_sync"] = int(self.redis_controller.get_value(ParameterKey.FRAMES_IN_SYNC.value) or 1) == 1
        except (TypeError, ValueError):
            values["frames_in_sync"] = True
        values["frames_off_sync"] = not values["frames_in_sync"]

        # ── audio stats ─────────────────────────────────────────────────
        if values["mic_connected"]:
            monitor = getattr(self.usb_monitor, "audio_monitor", None)
            bit_depth = getattr(monitor, "bit_depth", None)
            if bit_depth:
                values["mic_bit_depth"] = f"{bit_depth}"

            sample_rate = getattr(monitor, "sample_rate", None) or getattr(monitor, "audio_sample_rate", None)
            if sample_rate:
                try:
                    sr_khz = sample_rate / 1000
                    if abs(round(sr_khz) - sr_khz) < 1e-3:
                        values["mic_sample_rate"] = f"{int(round(sr_khz))}"
                    else:
                        values["mic_sample_rate"] = f"{sr_khz:.1f}".rstrip("0").rstrip(".")
                except (TypeError, ValueError):
                    pass

            if self.ssd_monitor:
                try:
                    rec_active = any([
                        int(self.redis_controller.get_value(ParameterKey.REC.value) or 0) == 1,
                        int(self.redis_controller.get_value(ParameterKey.IS_WRITING_BUF.value) or 0) == 1,
                        int(self.redis_controller.get_value(ParameterKey.IS_BUFFERING.value) or 0) == 1,
                    ])
                    if rec_active:
                        values["mic_wav_saved"] = False
                    else:
                        _, dng_count, wav_count, *_ = self._slow_values.get(
                            "latest_recording_info",
                            (None, 0, 0, -1),
                        )
                        values["mic_wav_saved"] = (
                            dng_count > 0
                            and self._slow_values.get("wav_duration_valid", False)
                        )
                except (TypeError, ValueError):
                    values["mic_wav_saved"] = False

            values["mic_wav_resampling"] = (
                self.redis_controller.get_value(AUDIO_RESAMPLING_REDIS_KEY) == "1"
            )

        # ── Zoom factor (preview punch-in) ────────────────────────────────
        default_zoom = float(self.settings.get("preview", {}).get("default_zoom", 1.0))
        try:
            z = float(self.redis_controller.get_value(ParameterKey.ZOOM.value) or 1.0)
        except (TypeError, ValueError):
            z = 1.0
        values["zoom_is_default"] = abs(z - default_zoom) <= 1e-3
        values["zoom_factor"] = f"{z:.1f}"

        try:
            preroll_active = int(
                self.redis_controller.get_value(
                    ParameterKey.STORAGE_PREROLL_ACTIVE.value
                )
                or 0
            ) == 1
        except (TypeError, ValueError):
            preroll_active = False

        # ─── recording time ───
        raw_rt = None if preroll_active else self.redis_controller.get_value(
            ParameterKey.RECORDING_TIME.value
        )

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

        clip_cam1 = "" if preroll_active else self._format_last_dng(last_cam1_full)
        clip_cam0 = "" if preroll_active else self._format_last_dng(last_cam0_full)

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

        if values["resolution_switching"]:
            self.colors["res"]["normal"] = RESOLUTION_SWITCHING_COLOR
        elif self._dynamic_resolution_indicator_active():
            self.colors["res"]["normal"] = "lightgreen"
        else:
            self.colors["res"]["normal"] = (249, 249, 249)

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

    def _validate_wav_length(self, folder_path, max_frame_idx, fps, tolerance=0.15) -> bool:
        if not folder_path or max_frame_idx < 0 or fps <= 0:
            return False
        from pathlib import Path
        folder = Path(folder_path)
        wav_files = list(folder.glob("*.wav"))
        if not wav_files:
            return False
        try:
            with wave.open(str(wav_files[0]), "rb") as wf:
                n_frames = wf.getnframes()
                frame_rate = wf.getframerate()
            if frame_rate <= 0:
                return False
            wav_duration = n_frames / frame_rate
        except Exception:
            return False
        expected_duration = (max_frame_idx + 1) / fps
        if expected_duration <= 0:
            return False
        return abs(wav_duration - expected_duration) / expected_duration < tolerance

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

    def _normalise_vu_levels(self, levels):
        cleaned = []
        for level in levels:
            try:
                cleaned.append(max(0, min(100, int(round(float(level))))))
            except (TypeError, ValueError):
                continue

        if not cleaned:
            return None

        if len(cleaned) >= 4 and cleaned[:2] == cleaned[2:4]:
            cleaned = cleaned[:2]
        elif len(cleaned) > 2:
            cleaned = cleaned[:2]
        elif len(cleaned) == 1:
            cleaned *= 2

        return cleaned

    def _get_recorder_vu_levels(self):
        client = getattr(self.redis_controller, "r", None)
        if client is None:
            return None

        try:
            raw = client.get(RECORDER_VU_REDIS_KEY)
        except Exception:
            return None

        if raw in (None, b"", ""):
            return None

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        return self._normalise_vu_levels(str(raw).split("|"))

    def update_smoothed_vu_levels(self):
        levels = self._get_recorder_vu_levels()
        if not levels:
            self.vu_smoothed = []
            self.vu_peaks = []
            return

        if len(levels) != len(self.vu_smoothed):
            self.vu_smoothed = [0.0] * len(levels)
            self.vu_peaks = [0.0] * len(levels)

        for i, level in enumerate(levels):
            if level < self.vu_smoothed[i]:
                self.vu_smoothed[i] *= (1 - self.vu_decay_factor)
            else:
                self.vu_smoothed[i] = level

            self.vu_peaks[i] = max(self.vu_peaks[i] * 0.98, self.vu_smoothed[i])

    # ─────────────────────────────────────────────────────────────
    # LEFT-HAND COLUMN  (CAM / MON / SYS …)
    # ─────────────────────────────────────────────────────────────
    def _draw_status_box(self, draw, box, text, fill, font, text_color, *, crossed=False):
        x0, y0, x1, y1 = box
        draw.rectangle(box, fill=fill)
        text_font = font
        tw, th = draw.textbbox((0, 0), text, font=text_font)[2:]
        if tw > (x1 - x0 - 4):
            text_font = self._get_font("bold", 20)
            tw, th = draw.textbbox((0, 0), text, font=text_font)[2:]
        tx = x0 + ((x1 - x0) - tw) // 2
        ty = y0 + ((y1 - y0) - th) // 2
        draw.text((tx, ty), text, font=text_font, fill=text_color)
        if crossed:
            draw.line([(x0 + 5, y0 + 5), (x1 - 5, y1 - 5)], fill=text_color, width=3)

    def draw_left_sections(self, draw, values):
        label_font = self._get_font("regular", 26)
        box_font   = self._get_font("bold", 26)

        BOX_H, BOX_W  = 40, 60
        BOX_COLOR     = (136, 136, 136)
        ZOOM_HIGHLIGHT_COLOR = (255, 221, 0)
        TEXT_COLOR    = (0,   0,   0)

        label_x       = 19
        box_x         = 15
        y             = 97
        LABEL_SPACING = -4
        BOX_GAP       = 14
        SECTION_GAP   = 60

        # ── CAM / MON sections ───────────────────────────────────
        for section in self.left_section_layout:
            if section.get("condition") and not section["condition"](values):
                continue
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
                        box_fill = BOX_COLOR if values.get("zoom_is_default") else ZOOM_HIGHLIGHT_COLOR
                    elif item["key"] == "mic_wav_saved" and values.get("mic_wav_resampling"):
                        box_fill = WAV_RESAMPLING_COLOR   # light grey while WAV is being resampled
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

            if section == self.left_section_layout[0] and values.get("drop_frame_latched"):
                self._draw_status_box(
                    draw,
                    [box_x, y, box_x + BOX_W, y + BOX_H],
                    "DROP",
                    DROP_WARNING_COLOR,
                    box_font,
                    TEXT_COLOR,
                )
                y += BOX_H + BOX_GAP

            if section == self.left_section_layout[0] and values.get("frames_off_sync"):
                self._draw_status_box(
                    draw,
                    [box_x, y, box_x + BOX_W, y + BOX_H],
                    "SYNC",
                    SYNC_WARNING_COLOR,
                    box_font,
                    TEXT_COLOR,
                    crossed=True,
                )
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
        label_font = self._get_font("regular", 26)
        box_font   = self._get_font("bold", 24)

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
                    if item["key"] == "mic_wav_saved" and values.get("mic_wav_resampling"):
                        _box_fill = WAV_RESAMPLING_COLOR
                    else:
                        _box_fill = BOX_COLOR
                    draw.rectangle([box_pad_x, y,
                                    box_pad_x + BOX_W, y + BOX_H],
                                   fill=_box_fill)
                    tw, th = draw.textbbox((0,0), part, font=box_font)[2:]
                    tx = box_pad_x + (BOX_W - tw)//2
                    ty = y         + (BOX_H - th)//2
                    draw.text((tx, ty), part, font=box_font, fill=TEXT_COLOR)
                    y += BOX_H + BOX_GAP

            if values.get("drop_frame_latched"):
                self._draw_status_box(
                    draw,
                    [box_pad_x, y, box_pad_x + BOX_W, y + BOX_H],
                    "DROP",
                    DROP_WARNING_COLOR,
                    box_font,
                    TEXT_COLOR,
                )
                y += BOX_H + BOX_GAP

            if values.get("frames_off_sync"):
                self._draw_status_box(
                    draw,
                    [box_pad_x, y, box_pad_x + BOX_W, y + BOX_H],
                    "SYNC",
                    SYNC_WARNING_COLOR,
                    box_font,
                    TEXT_COLOR,
                    crossed=True,
                )
                y += BOX_H + BOX_GAP
            y += SECTION_GAP

    def draw_right_vu_meter(self, draw):
        if self._get_recorder_vu_levels() is None:
            return
        vu_levels = self.vu_smoothed
        vu_peaks = self.vu_peaks

        if not vu_levels:
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
            clamped_level = max(0.0, min(100.0, float(level)))
            return int((clamped_level / 100.0) * bar_height)

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
        label_font = self._get_font("regular", 16)
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

        drop_frame_live = int(self.redis_controller.get_value(ParameterKey.DROP_FRAME.value) or 0) == 1
        frames_off_sync = bool(values.get("frames_off_sync"))
        now = time.time()
        if frames_off_sync and not self._frames_off_sync_prev:
            self._sync_flash_until = now + 0.6
        self._frames_off_sync_prev = frames_off_sync
        sync_flash_live = now < self._sync_flash_until

        if sync_flash_live:
            self.current_background_color = SYNC_FLASH_COLOR
            self.color_mode = "inverse"
        elif drop_frame_live:
            self.current_background_color = "purple"
            self.color_mode = "inverse"
        elif preroll_active:
            self.current_background_color = "blue"
            self.color_mode = "inverse"

        if not preroll_active and not drop_frame_live and not sync_flash_live:
            if int(self.redis_controller.get_value(ParameterKey.IS_WRITING.value) or 0) == 1:
                # at least one camera is actively writing frames to disk
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

        fb = self.fb
        if not fb:
            return

        disp_width = self.disp_width or fb.size[0]
        disp_height = self.disp_height or fb.size[1]

        image = Image.new("RGBA", fb.size)
        draw = ImageDraw.Draw(image)
        draw.rectangle(((0, 0), fb.size), fill=self.current_background_color)

        # Draw left-hand labels and boxes dynamically
        self.draw_left_sections(draw, values)

        # Get sensor resolution
        self.width = int(self.redis_controller.get_value(ParameterKey.WIDTH.value))
        self.height = int(self.redis_controller.get_value(ParameterKey.HEIGHT.value))
        try:
            anamorphic_factor = float(
                self.redis_controller.get_value(ParameterKey.ANAMORPHIC_FACTOR.value) or 1.0
            )
        except (TypeError, ValueError):
            anamorphic_factor = 1.0

        frame_width = disp_width
        frame_height = disp_height
        shrink_x = disp_width / 1920
        shrink_y = disp_height / 1080
        
        line_color = (249, 249, 249) if values.get("zoom_is_default", True) else (255, 221, 0)

        # Match CinePi._build_args() and DrmPreview::Show(): place the preview
        # window from the raw aspect, then fit the visible lores/anamorphic
        # stream inside it. Redis lores dimensions can be briefly stale during
        # a mode switch, so calculate them here from the same source values.
        outline_rect = _calculate_preview_guide_rect(
            frame_width,
            frame_height,
            self.width,
            self.height,
            anamorphic_factor,
        )
        draw.rectangle(outline_rect, outline=line_color, width=PREVIEW_GUIDE_OUTLINE_WIDTH)

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
            position = [info["pos"][0] * shrink_x, info["pos"][1] * shrink_y]
            font_size = info.get("size", 12) * min(min(shrink_x, shrink_y), 1) 
            # 12 is the default font size, min with 1 makes sure the font stays same in bigger displays
            font = self._get_font(info.get("font", "bold"), font_size)
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


        try:
            fb.show(image)
        except (OSError, RuntimeError, ValueError) as exc:
            logging.warning("Framebuffer write failed; detaching HDMI GUI until it returns: %s", exc)
            if self.fb is fb:
                self.fb = None
                self.disp_width = 0
                self.disp_height = 0
        
    def draw_rounded_box(self, draw, text, position, font_size, padding, text_color, fill_color, image, extra_height=-17, reduce_top=12):
        font = self._get_font("bold", font_size)
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
            try:
                self.fb.show(blank_image)
            except (OSError, RuntimeError, ValueError) as exc:
                logging.warning("Failed to blank framebuffer cleanly: %s", exc)
                self.fb = None
                self.disp_width = 0
                self.disp_height = 0
            
    def _teardown_display(self, clear_framebuffer=False, release_console=False):
        with self._stop_lock:
            if self._display_teardown_done:
                return
            self._display_teardown_done = True

        fb = self.fb
        self.fb = None
        self.disp_width = 0
        self.disp_height = 0

        released_console = False
        if release_console:
            try:
                release_console_to_text()
                released_console = True
            except Exception as exc:
                logging.warning("Failed to release console to text during GUI shutdown: %s", exc)

        if clear_framebuffer and not released_console and fb:
            blank_image = Image.new("RGBA", fb.size, "black")
            try:
                fb.show(blank_image)
            except (OSError, RuntimeError, ValueError) as exc:
                logging.warning("Failed to blank framebuffer cleanly during GUI shutdown: %s", exc)

    def request_stop(self, clear_framebuffer=False, release_console=False):
        """Ask the GUI thread to exit without waiting for teardown."""
        with self._stop_lock:
            self._running = False
            self._clear_framebuffer_on_exit = self._clear_framebuffer_on_exit or clear_framebuffer
            self._release_console_on_exit = self._release_console_on_exit or release_console
        self._redraw_event.set()

    def stop(
        self,
        clear_framebuffer=True,
        release_console=False,
        join_timeout=2.0,
        teardown_before_join=False,
    ):
        """Ask the GUI thread to exit, wait for it, and optionally restore tty1."""
        self.request_stop(
            clear_framebuffer=clear_framebuffer,
            release_console=release_console,
        )
        if teardown_before_join:
            self._teardown_display(
                clear_framebuffer=clear_framebuffer,
                release_console=release_console,
            )
        if self.is_alive():
            self.join(timeout=join_timeout)
            if self.is_alive():
                logging.warning(
                    "SimpleGUI thread did not stop within %.1fs; display teardown will be deferred",
                    join_timeout,
                )
                return False
        self._teardown_display(
            clear_framebuffer=clear_framebuffer,
            release_console=release_console,
        )
        return True


    def run(self):
        try:
            self.vu_left_peak = 0
            self.vu_right_peak = 0
            self.vu_left_smoothed = 0
            self.vu_right_smoothed = 0
            self.vu_decay_factor = 0.2

            while self._running:
                now = time.monotonic()
                if self.check_display():
                    self._fast_dirty = True
                self._maybe_restart_camera_for_display_attach()

                if (
                    not self._slow_values
                    or (now - self._last_slow_refresh_ts) >= self.slow_refresh_interval
                ):
                    self._slow_dirty = True

                has_work = self._fast_dirty or self._slow_dirty or self._vu_active()
                if not has_work:
                    self._redraw_event.wait(timeout=0.1)
                    self._redraw_event.clear()
                    continue

                due_in = max(0.0, self.min_frame_interval - (now - self._last_draw_ts))
                if due_in > 0:
                    self._redraw_event.wait(timeout=due_in)
                    self._redraw_event.clear()
                    continue

                if self._slow_dirty:
                    self._refresh_slow_values()

                self.update_smoothed_vu_levels()
                values = self.populate_values()
                self.draw_gui(values)
                self._fast_dirty = False
                self._slow_dirty = False
                self._last_draw_ts = time.monotonic()
        finally:
            self._teardown_display(
                clear_framebuffer=self._clear_framebuffer_on_exit,
                release_console=self._release_console_on_exit,
            )
 
    # def emit_gui_data_change(self, changed_data):
    #     self.socketio.emit('gui_data_change', changed_data)
        
#         fsck = redis.get_value("FSCK_STATUS", "")
# if fsck.startswith("FAIL"):
#     show_red_icon(fsck)
# elif fsck.startswith("OK"):
#     show_green_icon(fsck)
# else:
#     show_gray_icon("no data")
