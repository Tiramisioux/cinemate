import logging
import re
import threading
import os
import time
import json
from fractions import Fraction
import math
import subprocess
from threading import Thread, Timer
import psutil
import math
import sys

from module.redis_controller import ParameterKey
from module.ir_filter import IRFilter
from module.config_loader import load_settings as _load_settings
from module.storage_profiles import recorder_profile_name_for_filesystem
from module.dynamic_resolution import (
    DEFAULT_MATCH_TOLERANCE_PX,
    choose_resolution,
    dynamic_resolution_is_lower_substitute,
    load_profile_rows,
    max_fps_for_context,
)

SETTINGS_FILE = "/home/pi/cinemate/src/settings.json"
GUI_RESOLUTION_PREVIEW_DELAY_SECONDS = 0.12
GUI_RESOLUTION_SWITCHING_HOLD_SECONDS = 2.5
RAW_STREAM_READY_RE = re.compile(r"\bRaw stream:\s*(\d+)x(\d+)\b", re.IGNORECASE)


def _safe_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class CinePiController:
    def __init__(self,
                 cinepi,
                 redis_controller,
                 ssd_monitor,
                 sensor_detect,
                 iso_steps,
                 shutter_a_steps,
                 fps_steps,
                 wb_steps,   # Use this directly
                 light_hz,
                 anamorphic_steps,
                 default_anamorphic_factor
                 ):

        self.parameters_lock_obj = threading.Lock()
        self.cinepi = cinepi
        self.redis_controller = redis_controller
        self.ssd_monitor = ssd_monitor
        self.sensor_detect = sensor_detect
        
        self.iso_steps = iso_steps
        self.iso_steps_dynamic = list(iso_steps)

        self.shutter_a_steps = shutter_a_steps
        self.shutter_a_steps_dynamic = list(shutter_a_steps)

        self.fps_steps = fps_steps
        self.fps_steps_dynamic = list(fps_steps)

        self.wb_steps = wb_steps
        self.wb_steps_dynamic = list(wb_steps)

        self.light_hz = light_hz
        
        self.anamorphic_steps = anamorphic_steps
        self.default_anamorphic_factor = default_anamorphic_factor
        self.settings = self.load_settings()

        # Frame-rate phase lock: apply the per-camera `phase_lock` setting (default
        # True) to the shared cinepi-raw `fps_phase_lock` flag. Reads the primary
        # camera (cam0, then cam1). set_value publishes on cp_controls so cinepi-raw
        # picks it up live; the value also persists for cinepi-raw to read at start.
        # Safe to leave True for dual --sync genlock rigs: cinepi-raw infers its role
        # from --sync and only disciplines the master (--sync off/server) to the Pi
        # clock; the --sync client self-suppresses the lock and lets rpi.sync own its
        # VBLANK. So the same shared flag is correct for both single and dual.
        try:
            _cam_cfg = (self.settings.get("camera") or {})
            _phase_lock = True
            for _port in ("cam0", "cam1"):
                _c = _cam_cfg.get(_port)
                if isinstance(_c, dict):
                    _phase_lock = bool(_c.get("phase_lock", True))
                    break
            self.redis_controller.set_value(
                ParameterKey.FPS_PHASE_LOCK.value, 1 if _phase_lock else 0
            )
            logging.info(
                "Frame-rate phase lock %s (cinepi-raw fps_phase_lock)",
                "enabled" if _phase_lock else "disabled",
            )
        except Exception as exc:
            logging.warning("Could not apply phase_lock setting: %s", exc)

        dynamic_resolution_cfg = self.settings.get("dynamic_resolution", {})
        self.dynamic_resolution_cfg = dynamic_resolution_cfg
        self.dynamic_resolution_enabled = self._as_bool(dynamic_resolution_cfg.get("enabled", False))
        self.dynamic_resolution_match_tolerance_px = int(
            dynamic_resolution_cfg.get("match_tolerance_px", DEFAULT_MATCH_TOLERANCE_PX)
            or DEFAULT_MATCH_TOLERANCE_PX
        )
        self.dynamic_resolution_policy = str(
            dynamic_resolution_cfg.get("policy", "highest_sustainable_resolution")
        )
        self.dynamic_resolution_safety_margin_fps = float(
            dynamic_resolution_cfg.get("safety_margin_fps", 0) or 0
        )
        self.dynamic_resolution_table = load_profile_rows(
            dynamic_resolution_cfg,
            settings_file=SETTINGS_FILE,
        )
        self.dynamic_resolution_desired_mode = None
        self.dynamic_resolution_active = False
        self.dynamic_resolution_suspended = False
        
        self.wb_cg_rb_array = {}  # Initialize as an empty dictionary
        
        self.fps = int(round(float(self.redis_controller.get_value(ParameterKey.FPS_LAST.value))))
        self.current_fps = float(self.redis_controller.get_value(ParameterKey.FPS_USER.value))
        
        self.shutter_a_steps_dynamic = self.calculate_dynamic_shutter_angles(self.fps)

        self.shutter_a_sync_mode = 0  # 0: normal mode, 1: exposure-sync mode
        self.shutter_angle_nom = 180.0  # User-defined nominal shutter angle
        self.shutter_angle_actual = 180.0  # Actual shutter angle (after calculation)
        self.exposure_time_nominal = None  # Stored exposure time when sync mode is activated
        self.shutter_angle_steps = []  # Steps array
        self.is_shutter_angle_transient = False  # Transient flag for GUI updates
        
        self._rec_thread        = None
        self._rec_thread_stop   = threading.Event()
        self._preroll_active    = threading.Event()
        self._timed_rec_timer   = None
        self._timed_rec_description = None
        self.redis_listener = None
        self._storage_profile_restart_lock = threading.Lock()
        self._storage_profile_restart_active = False
        self._resolution_change_callbacks = []
        self._resolution_change_pace_lock = threading.Lock()
        self._last_resolution_change_started_at = 0.0
        self._resolution_change_min_interval_s = 0.25
        self._recording_resolution_change_min_interval_s = 2.0
        self._resolution_switching_timer = None
        self._storage_profile_restart_pending = False
        self._active_storage_recorder_profile = self._current_storage_recorder_profile()
        try:
            self.ssd_monitor.mount_event.subscribe(self._handle_storage_mount_event)
            self.redis_controller.redis_parameter_changed.subscribe(
                self._handle_storage_restart_redis_event
            )
        except Exception as exc:
            logging.warning("Unable to subscribe to storage profile changes: %s", exc)
        
        # Set startup flag
        self.startup = True
        
        self.parameters_lock = False
        self.iso_lock = False
        self.shutter_a_nom_lock = False
        self.fps_lock = False
        
        # Dictionary to store calculated values for different fps
        self.calculated_values = {}
        
        self.all_lock = False
        self.lock_override = False
        self.exposure_time_seconds = None
        self.exposure_time_fractions = None
        self.fps_multiplier = 1
        self.fps_saved = float(self.redis_controller.get_value(ParameterKey.FPS.value))
        self.fps_double = False
        self.ramp_up_speed = 0.2
        self.ramp_down_speed = 0.2
        self.fps_button_state = False
        self.fps_temp = 24
        self.fps_temp_old = 24

        self.shutter_a_nom = 180
        self.exposure_time_saved = 1/24
        self.current_sensor = self.sensor_detect.camera_model
        self.redis_controller.set_value(ParameterKey.SENSOR.value, self.sensor_detect.camera_model)
        
        self.sensor_mode = self._get_startup_sensor_mode()
        self.sensor_mode_saved = self.sensor_mode
        self.dynamic_resolution_desired_mode = self._get_startup_dynamic_resolution_desired_mode()
        stored_dynamic_resolution_active = self._as_bool(
            self.redis_controller.get_value(
                ParameterKey.DYNAMIC_RESOLUTION_ACTIVE.value,
                0,
            )
        )
        self.dynamic_resolution_active = False
        if (
            self.dynamic_resolution_enabled
            and stored_dynamic_resolution_active
            and self.sensor_mode != self.dynamic_resolution_desired_mode
        ):
            logging.info(
                "Clearing stored dynamic resolution active flag at startup "
                "(sensor mode %s, desired mode %s)",
                self.sensor_mode,
                self.dynamic_resolution_desired_mode,
            )
        if (
            self.dynamic_resolution_enabled
            and not self.dynamic_resolution_active
            and self.dynamic_resolution_desired_mode != self.sensor_mode
        ):
            logging.info(
                "Dynamic resolution desired mode reset to startup mode %s "
                "(stored desired mode %s was not active)",
                self.sensor_mode,
                self.dynamic_resolution_desired_mode,
            )
            self.dynamic_resolution_desired_mode = self.sensor_mode
        self.fps_max = self._refresh_fps_max()
        self.gui_layout = self.sensor_detect.get_gui_layout(self.current_sensor, self.sensor_mode)
        self.exposure_time_s = float(self.redis_controller.get_value(ParameterKey.SHUTTER_A.value)) / 360 * (1 / self.fps) 
        self.exposure_time_saved = self.exposure_time_s
        self.file_size = self.sensor_detect.get_file_size(self.current_sensor, self.sensor_mode)
        
        self._publish_dynamic_resolution_state()
        
        # ── put default zoom into Redis if nothing stored yet ─────────────
        if self.redis_controller.get_value(ParameterKey.ZOOM.value) is None:
            default_zoom = self.settings.get('preview', {}).get('default_zoom', 1.0)
            self.redis_controller.set_value(ParameterKey.ZOOM.value, default_zoom)

        
        self.initialize_fps_steps(self.fps_steps)
        self.initialize_shutter_angle_steps()

        free_mode = self.settings.get('free_mode', {})
        self.iso_free = free_mode.get('iso_free', False)
        self.shutter_a_free = free_mode.get('shutter_a_free', False)
        self.fps_free = free_mode.get('fps_free', False)
        self.wb_free = free_mode.get('wb_free', False)
        
        self.RAM_LIMIT_PERCENT = 80
        # Stop recording when the cinepi-raw RAM frame buffer is this full
        # (used slots / total slots). This is the direct "about to drop
        # frames" signal; the system-RAM limit above is a coarser backstop.
        self.BUFFER_LIMIT_PERCENT = 90

        self.update_steps()
        self.initialize_wb_cg_rb_array()  # Initialize after free-mode expands WB steps.

        # Set a timer to clear the startup flag after a short period
        threading.Timer(5.0, self.clear_startup_flag).start()

        # Communicate the initial fps without changing resolution. Storage
        # pre-roll should stress the selected mode before dynamic resolution
        # restores the user's FPS and chooses a sustainable mode.
        prev_dynamic_suspended = self.dynamic_resolution_suspended
        self.dynamic_resolution_suspended = True
        try:
            self.set_fps(self.fps)
        finally:
            self.dynamic_resolution_suspended = prev_dynamic_suspended
        logging.info(f"Initialized fps: {self.fps}")
        
    def _get_startup_sensor_mode(self) -> int:
        value = self.redis_controller.get_value(ParameterKey.SENSOR_MODE.value)
        try:
            return int(value)
        except (TypeError, ValueError):
            self.redis_controller.set_value(ParameterKey.SENSOR_MODE.value, 0)
            return 0

    def _get_startup_dynamic_resolution_desired_mode(self) -> int:
        value = self.redis_controller.get_value(
            ParameterKey.DYNAMIC_RESOLUTION_DESIRED_MODE.value
        )
        try:
            desired_mode = int(value)
        except (TypeError, ValueError):
            return self.sensor_mode
        if desired_mode not in self.sensor_detect.res_modes:
            return self.sensor_mode
        return desired_mode

    def _publish_dynamic_resolution_state(self):
        self.redis_controller.set_value(
            ParameterKey.DYNAMIC_RESOLUTION_ENABLED.value,
            1 if self.dynamic_resolution_enabled else 0,
        )
        self.redis_controller.set_value(
            ParameterKey.DYNAMIC_RESOLUTION_ACTIVE.value,
            1 if self.dynamic_resolution_active else 0,
        )
        if self.dynamic_resolution_desired_mode is not None:
            self.redis_controller.set_value(
                ParameterKey.DYNAMIC_RESOLUTION_DESIRED_MODE.value,
                self.dynamic_resolution_desired_mode,
            )

    def _current_user_fps_value(self):
        value = self.redis_controller.get_value(ParameterKey.FPS_USER.value)
        if value is None:
            value = self.redis_controller.get_value(ParameterKey.FPS.value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_bool(value):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _sensor_readout_fps_max(self, mode=None):
        mode = self.sensor_mode if mode is None else mode
        try:
            return int(self.sensor_detect.get_fps_max(self.current_sensor, mode))
        except (TypeError, ValueError):
            return 1

    def _dynamic_context_fps_max(self):
        if not self.dynamic_resolution_enabled:
            return None
        storage_type = self.redis_controller.get_value(ParameterKey.STORAGE_TYPE.value, "none")
        filesystem = self.redis_controller.get_value(ParameterKey.STORAGE_FILESYSTEM.value, "none")
        if str(storage_type or "").strip().lower() in ("", "none", "unknown"):
            return None
        if str(filesystem or "").strip().lower() in ("", "none", "unknown"):
            return None
        return max_fps_for_context(
            sensor_modes=self.sensor_detect.res_modes,
            sensor=self.current_sensor,
            storage_type=storage_type,
            filesystem=filesystem,
            performance_table=self.dynamic_resolution_table,
            desired_mode=self.dynamic_resolution_desired_mode,
            tolerance_px=self.dynamic_resolution_match_tolerance_px,
            safety_margin_fps=self.dynamic_resolution_safety_margin_fps,
            policy=self.dynamic_resolution_policy,
        )

    def _refresh_fps_max(self):
        sensor_max = self._sensor_readout_fps_max()
        dynamic_max = self._dynamic_context_fps_max()
        fps_max = int(dynamic_max) if dynamic_max is not None else sensor_max
        self.fps_max = max(1, fps_max)
        self.redis_controller.set_value(ParameterKey.FPS_MAX.value, self.fps_max)
        return self.fps_max

    def _dynamic_resolution_choice_for_fps(self, requested_user_fps):
        if not self.dynamic_resolution_enabled:
            self.dynamic_resolution_active = False
            self._publish_dynamic_resolution_state()
            return None
        if self.dynamic_resolution_suspended:
            return None

        if self.dynamic_resolution_desired_mode is None:
            self.dynamic_resolution_desired_mode = self.sensor_mode

        storage_type = self.redis_controller.get_value(ParameterKey.STORAGE_TYPE.value, "none")
        filesystem = self.redis_controller.get_value(ParameterKey.STORAGE_FILESYSTEM.value, "none")
        if str(storage_type or "").strip().lower() in ("", "none", "unknown"):
            return None
        if str(filesystem or "").strip().lower() in ("", "none", "unknown"):
            return None

        return choose_resolution(
            sensor_modes=self.sensor_detect.res_modes,
            desired_mode=self.dynamic_resolution_desired_mode,
            requested_fps=requested_user_fps,
            sensor=self.current_sensor,
            storage_type=storage_type,
            filesystem=filesystem,
            performance_table=self.dynamic_resolution_table,
            tolerance_px=self.dynamic_resolution_match_tolerance_px,
            safety_margin_fps=self.dynamic_resolution_safety_margin_fps,
            policy=self.dynamic_resolution_policy,
        )

    def _maybe_apply_dynamic_resolution_for_fps(self, requested_user_fps):
        choice = self._dynamic_resolution_choice_for_fps(requested_user_fps)
        if choice is None:
            self.dynamic_resolution_active = False
            self._publish_dynamic_resolution_state()
            return False

        self.dynamic_resolution_active = choice.dynamic_active
        self._publish_dynamic_resolution_state()

        if choice.mode == self.sensor_mode:
            return False

        logging.info(
            "Dynamic resolution selecting mode %s for %.3ffps "
            "(desired mode %s supports %.3ffps on measured %sx%s)",
            choice.mode,
            float(requested_user_fps),
            choice.desired_mode,
            choice.desired_row.max_fps,
            choice.desired_row.width,
            choice.desired_row.height,
        )
        return self._apply_resolution_mode(choice.mode, restore_user_fps=None)
        
    # ─── step-table helpers ────────────────────────────────────────────────
    def _rebuild_iso_steps(self):
        self.iso_steps = (list(range(100, 3201, 50))
                        if self.iso_free
                        else list(self.settings['arrays']['iso_steps']))

    def _rebuild_shutter_steps(self):
        self.shutter_a_steps = ([round(i * 0.1, 1) for i in range(10, 3601)]
                                if self.shutter_a_free
                                else list(self.settings['arrays']['shutter_a_steps']))
        # keep the flicker-free additions in sync
        self.shutter_a_steps_dynamic = self.calculate_dynamic_shutter_angles(
            self.current_fps)

    def _rebuild_fps_steps(self):
        if self.fps_free:
            self.fps_steps = list(range(1, self.fps_max + 1))
        else:
            self.fps_steps = list(self.settings['arrays']['fps_steps'])
        self.fps_steps_dynamic = self._fps_steps_capped_at_max(self.fps_steps)

    def _fps_steps_capped_at_max(self, fps_steps):
        """Return configured FPS steps, replacing above-max choices with fps_max."""
        values = []
        has_above_max = False
        for fps in fps_steps:
            try:
                value = float(fps)
            except (TypeError, ValueError):
                continue
            if value <= self.fps_max:
                values.append(value)
            else:
                has_above_max = True

        if has_above_max or not values:
            values.append(float(self.fps_max))

        return [
            int(value) if value.is_integer() else value
            for value in sorted(set(values))
        ]

    def _rebuild_wb_steps(self):
        self.wb_steps = (list(range(2800, 6501, 100))
                        if self.wb_free
                        else list(self.settings['arrays']['wb_steps']))
    
    # ─── main public call ──────────────────────────────────────────────────
    def update_steps(self):
        """Re-calculate all step tables after a ‘*_free’ flag or fps_max changes."""
        self._rebuild_iso_steps()
        self._rebuild_shutter_steps()
        self._rebuild_fps_steps()
        self._rebuild_wb_steps()
        logging.info(f"Step tables rebuilt "
                    f"(iso {len(self.iso_steps)}, "
                    f"shutter {len(self.shutter_a_steps_dynamic)}, "
                    f"fps {len(self.fps_steps_dynamic)}, "
                    f"wb {len(self.wb_steps)})")
    
    def set_anamorphic_factor(self, value=None):
        """
        Set or toggle the anamorphic factor.
        - If `value` is provided, set it directly in Redis if valid.
        - If `value` is None, toggle to the next value in the anamorphic_steps array.
        """
        if value is not None:
            # Validate the incoming value
            if value in self.anamorphic_steps:
                self.redis_controller.set_value(ParameterKey.ANAMORPHIC_FACTOR.value, value)
                logging.info(f"Anamorphic factor set to: {value}")
            else:
                logging.error(f"Invalid anamorphic factor: {value}. Valid options are: {self.anamorphic_steps}")
        else:
            # Get the current anamorphic factor from Redis
            current_value = float(self.redis_controller.get_value(ParameterKey.ANAMORPHIC_FACTOR.value))
            if current_value not in self.anamorphic_steps:
                logging.error(f"Current anamorphic factor {current_value} is not in the valid steps: {self.anamorphic_steps}")
                return

            # Find the next value in the array
            current_index = self.anamorphic_steps.index(current_value)
            next_index = (current_index + 1) % len(self.anamorphic_steps)
            next_value = self.anamorphic_steps[next_index]

            # Set the next value in Redis
            self.redis_controller.set_value(ParameterKey.ANAMORPHIC_FACTOR.value, next_value)
            logging.info(f"Anamorphic factor toggled to: {next_value}")

        self.cinepi.restart()

    # ── imx585 ClearHDR ──────────────────────────────────────────────────
    # Live knobs (threshold / blend / gain adder) are plain sensor controls:
    # setting the Redis key publishes on cp_controls and cinepi-raw applies
    # them to the sensor while streaming. Toggling ClearHDR itself
    # (wide_dynamic_range) changes the sensor's mode list, so profiles flip
    # the control, re-detect modes and restart cinepi-raw with --hdr sensor.

    def _load_hdr_profiles(self):
        """Return the profile list from resources/HDR_profiles.json ([] on error)."""
        path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "resources", "HDR_profiles.json")
        )
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logging.error(f"HDR profiles unavailable ({path}): {exc}")
            return []
        profiles = data.get("profiles", [])
        return profiles if isinstance(profiles, list) else []

    def _set_wide_dynamic_range(self, enable: bool) -> bool:
        """Set wide_dynamic_range on every sensor subdev that accepts it.

        Returns True when at least one subdev took the control. The control
        changes the sensor's mode list, so callers must re-detect modes and
        restart cinepi-raw afterwards.
        """
        value = 1 if enable else 0
        applied = False
        for idx in range(16):
            dev = f"/dev/v4l-subdev{idx}"
            if not os.path.exists(dev):
                continue
            probe = subprocess.run(
                ["v4l2-ctl", "-d", dev, "--set-ctrl", f"wide_dynamic_range={value}"],
                capture_output=True, text=True,
            )
            if probe.returncode == 0:
                logging.info(f"wide_dynamic_range={value} set on {dev}")
                applied = True
        if not applied:
            logging.warning("No sensor subdev accepted wide_dynamic_range (imx585 ClearHDR)")
        return applied

    def set_hdr_threshold(self, low, high=None):
        """Set the ClearHDR data-selection thresholds (0–4095 each).

        Accepts two ints or a single "low,high" string. Applied live.
        """
        if high is None:
            try:
                low, high = str(low).replace(" ", "").split(",")
            except ValueError:
                logging.error("hdr threshold expects 'low,high' (each 0..4095)")
                return
        try:
            low_i = max(0, min(4095, int(low)))
            high_i = max(0, min(4095, int(high)))
        except (TypeError, ValueError):
            logging.error("hdr threshold expects integers 0..4095")
            return
        self.redis_controller.set_value(ParameterKey.HDR_THRESHOLD.value, f"{low_i},{high_i}")
        logging.info(f"ClearHDR data-selection threshold set to {low_i},{high_i}")

    def set_hdr_blend(self, value):
        """Set the ClearHDR blending mode (driver menu index 0–8). Applied live."""
        try:
            v = max(0, min(8, int(value)))
        except (TypeError, ValueError):
            logging.error("hdr blend expects an integer 0..8")
            return
        self.redis_controller.set_value(ParameterKey.HDR_BLEND.value, v)
        logging.info(f"ClearHDR blending mode set to {v}")

    def set_hdr_gain_adder(self, value):
        """Set the ClearHDR gain adder (driver menu index 0–5, 2 = +12 dB). Applied live."""
        try:
            v = max(0, min(5, int(value)))
        except (TypeError, ValueError):
            logging.error("hdr gain adder expects an integer 0..5")
            return
        self.redis_controller.set_value(ParameterKey.HDR_GAIN_ADDER.value, v)
        logging.info(f"ClearHDR gain adder set to menu index {v}")

    def hdr_profile(self, index=None):
        """Apply a profile from resources/HDR_profiles.json and restart the camera.

        ``set hdr profile 1`` applies profile 1; a bare ``set hdr profile``
        cycles to the next one.
        """
        profiles = self._load_hdr_profiles()
        if not profiles:
            logging.error("No HDR profiles found (resources/HDR_profiles.json)")
            return

        if index is None:
            try:
                current = int(self.redis_controller.get_value(ParameterKey.HDR_PROFILE.value))
            except (TypeError, ValueError):
                current = -1
            index = (current + 1) % len(profiles)
        index = int(index)
        if not 0 <= index < len(profiles):
            logging.error(f"HDR profile {index} out of range (0..{len(profiles) - 1})")
            return

        profile = profiles[index]
        name = profile.get("name", str(index))
        hdr_on = bool(profile.get("hdr", False))

        # Order matters: flip the sensor control first, publish the knob keys
        # (cinepi-raw also re-applies them from Redis at startup), then restart
        # cinepi-raw with or without --hdr sensor (read from the hdr key at
        # launch). The mode table already carries both the plain and the HDR
        # modes (SensorDetect probes --list-cameras with and without --hdr
        # sensor), so no re-detection is needed here — and re-detecting now,
        # with wide_dynamic_range flipped on, would mislabel the HDR modes.
        self._set_wide_dynamic_range(hdr_on)
        self.redis_controller.set_value(ParameterKey.HDR.value, 1 if hdr_on else 0)

        threshold = profile.get("threshold")
        if isinstance(threshold, (list, tuple)) and len(threshold) == 2:
            self.set_hdr_threshold(threshold[0], threshold[1])
        if "blend_mode" in profile:
            self.set_hdr_blend(profile["blend_mode"])
        if "gain_adder" in profile:
            self.set_hdr_gain_adder(profile["gain_adder"])
        self.redis_controller.set_value(ParameterKey.HDR_PROFILE.value, index)

        logging.info(
            f"HDR profile {index} ('{name}') applied — restarting camera "
            f"(hdr={'on' if hdr_on else 'off'})"
        )
        self.cinepi.restart()

    def initialize_shutter_angle_steps(self):
        base_steps = self.settings['arrays']['shutter_a_steps']
        self.shutter_angle_steps = sorted(base_steps.copy())

        # Add flicker-free steps if 50Hz/60Hz defined
        for hz in self.settings.get('settings', {}).get('light_hz', []):
            flicker_free_steps = self.calculate_flicker_free_steps(hz)
            self.shutter_angle_steps += flicker_free_steps
        
        self.shutter_angle_steps = sorted(set(self.shutter_angle_steps))

    def calculate_flicker_free_steps(self, hz):
        flicker_free_angles = []
        frame_interval = 1 / self.current_fps
        flicker_period = 1 / hz
        multiples = int(frame_interval // flicker_period)
        for multiple in range(1, multiples + 1):
            angle = (multiple * flicker_period / frame_interval) * 360
            if 1.0 <= angle <= 360.0:
                flicker_free_angles.append(round(angle, 1))
        return flicker_free_angles
                                
    def set_shutter_a_sync_mode(self, value=None):
        if value is not None:
            if value in (0, False):
                self.shutter_a_sync_mode = 0
            elif value in (1, True):
                self.shutter_a_sync_mode = 1
            else:
                raise ValueError("Invalid value. Please provide either 0, 1, True, or False.")
        else:
            self.shutter_a_sync_mode = 0 if self.shutter_a_sync_mode else 1

        if self.shutter_a_sync_mode == 1:
            self.exposure_time_nominal = (self.shutter_angle_nom / 360) / self.current_fps
            self.shutter_angle_steps = [round(x * 0.1, 1) for x in range(10, 3601)]
        else:
            self.initialize_shutter_angle_steps()

        self.redis_controller.set_value(ParameterKey.SHUTTER_A_SYNC_MODE.value, self.shutter_a_sync_mode)
        logging.info(f"Shutter angle sync mode {self.shutter_a_sync_mode}")

    def calculate_exposure(self):
        fps = self.redis_controller.get_value(ParameterKey.FPS.value)
        shutter_a_nom = self.redis_controller.get_value(ParameterKey.SHUTTER_A.value)
        return float(shutter_a_nom) / 360.0 / float(fps)

    def set_iso_free(self, value=None):
        if value is None:
            self.iso_free = not self.iso_free
        else:
            self.iso_free = value
        self.update_steps()
        logging.info(f"ISO Free Mode set to {self.iso_free}")

    def set_shutter_a_free(self, value=None):
        if value is None:
            self.shutter_a_free = not self.shutter_a_free
        else:
            self.shutter_a_free = value
        self.update_steps()
        logging.info(f"Shutter Angle Free Mode set to {self.shutter_a_free}")

    def set_fps_free(self, value=None):
        if value is None:
            self.fps_free = not self.fps_free
        else:
            self.fps_free = value
        self.update_steps()
        logging.info(f"FPS Free Mode set to {self.fps_free}")

    def set_wb_free(self, value=None):
        if value is None:
            self.wb_free = not self.wb_free
        else:
            self.wb_free = value
        self.update_steps()
        self.initialize_wb_cg_rb_array()
        logging.info(f"WB Free Mode set to {self.wb_free}")

    def load_settings(self):
        try:
            settings = _load_settings(SETTINGS_FILE)
            logging.info("Settings loaded successfully.")
            return settings
        except Exception as e:
            logging.error(f"Error loading settings: {e}")
            return {}

    def clear_startup_flag(self):
        self.startup = False
        # Communicate the current fps to the web app after the startup phase
        #self.redis_controller.set_value(ParameterKey.FPS.value, self.fps)

    def load_wb_steps(self):
        try:
            wb_steps = self.settings.get('arrays', {}).get('wb_steps', [])
            logging.info(f"WB steps loaded: {wb_steps}")
            return wb_steps
        except Exception as e:
            logging.error(f"Error loading WB steps: {e}")
            return []

    def initialize_fps_steps(self, fps_steps):
        self.fps_max = int(self.redis_controller.get_value(ParameterKey.FPS_MAX.value))
        
        self.redis_controller.set_value(ParameterKey.FPS_MAX.value, self.fps_max)

        """Initialize fps_steps based on the provided list and capped by fps_max."""
        self.fps_steps_dynamic = self._fps_steps_capped_at_max(fps_steps)
        logging.info(f"Initialized fps_steps: {self.fps_steps_dynamic}")

    def set_free_mode(self, iso_free, shutter_a_free, fps_free, wb_free):
        self.settings['free_mode']['iso_free'] = iso_free
        self.settings['free_mode']['shutter_a_free'] = shutter_a_free
        self.settings['free_mode']['fps_free'] = fps_free
        self.settings['free_mode']['wb_free'] = wb_free
        self.iso_free = iso_free
        self.shutter_a_free = shutter_a_free
        self.fps_free = fps_free
        self.wb_free = wb_free
        self.redis_controller.mset({
            'iso_free': iso_free,
            'shutter_a_free': shutter_a_free,
            'fps_free': fps_free,
            'wb_free': wb_free
        })
        self.update_steps()
        self.initialize_wb_cg_rb_array()

        # Update shutter angle steps immediately if changed
        if shutter_a_free:
            self.shutter_angle_steps = [round(x * 0.1, 1) for x in range(10, 3601)]
        else:
            self.initialize_shutter_angle_steps()


    def update_shutter_angle_for_fps(self):
        if self.current_fps <= 0:
            logging.error("fps must be greater than zero.")
            return

        # Calculate the closest legal shutter angle for the new fps
        current_shutter_angle = float(self.redis_controller.get_value(ParameterKey.SHUTTER_A.value))
        self.shutter_a_steps_dynamic = self.calculate_dynamic_shutter_angles(self.current_fps)
        
        closest_shutter_angle = min(self.shutter_a_steps_dynamic, key=lambda x: abs(x - current_shutter_angle))
        
        logging.info(f"Updating shutter angle to the closest legal value: {closest_shutter_angle}")
        self.set_shutter_a(closest_shutter_angle)

        
    def update_shutter_angle_nom(self, new_angle):
        self.shutter_angle_nom = new_angle
        self.redis_controller.set_value(ParameterKey.SHUTTER_A_NOM.value, new_angle)

        if self.shutter_a_sync_mode == 1:
            self.exposure_time_nominal = (new_angle / 360) / self.current_fps
            self.shutter_angle_actual = new_angle
            self.is_shutter_angle_transient = True
            self.redis_controller.set_value(ParameterKey.SHUTTER_A_TRANSIENT.value, 1)

            threading.Timer(0.5, self.end_shutter_angle_transient).start()
        else:
            self.shutter_angle_actual = min(self.shutter_angle_steps, key=lambda x: abs(x - new_angle))
        
        self.redis_controller.set_value(ParameterKey.SHUTTER_A_ACTUAL.value, self.shutter_angle_actual)


    def end_shutter_angle_transient(self):
        self.is_shutter_angle_transient = False
        self.redis_controller.set_value(ParameterKey.SHUTTER_A_TRANSIENT.value, 0)

        if self.shutter_a_sync_mode == 1:
            adjusted_fps = (self.shutter_angle_nom / 360) / self.exposure_time_nominal
            self.update_fps(round(adjusted_fps, 1))

    def set_fps(self, value, update_user_target=True):
        """
        Apply a new FPS, observing:
            • hardware limit (fps_max)
            • fps_free flag
            • shutter-sync flag
            • optional locks
        """
        requested_user_fps = float(value)
        if self.fps_lock and not self.lock_override:
            logging.debug("FPS locked – request ignored")
            return

        # Give the UI immediate feedback for the operator's requested FPS.
        # The actual stream may still need a resolution reconfigure before the
        # corrected hardware FPS can be applied.
        self.user_fps = requested_user_fps
        self.redis_controller.set_value(ParameterKey.FPS_USER.value, self.user_fps)

        self._maybe_apply_dynamic_resolution_for_fps(requested_user_fps)

        # No per-sensor fps correction factor: the cinepi-raw phase lock drives the
        # recorded cadence onto the nominal fps, so the hardware fps == the user fps.
        fps_max = int(float(self.redis_controller.get_value(ParameterKey.FPS_MAX.value)))

        # ── choose the final fps value ──────────────────────────────────────
        if self.shutter_a_sync_mode == 1 or self.fps_free:
            safe_value = max(1, min(fps_max, requested_user_fps))   # “free”
            safe_user_fps = safe_value
        else:
            # make sure the table is current (free-mode may be toggled at run-time)
            self._rebuild_fps_steps()
            snapped_user_fps = min(self.fps_steps_dynamic,
                                   key=lambda x: abs(x - requested_user_fps))
            safe_user_fps = snapped_user_fps
            safe_value = snapped_user_fps

        self.user_fps = safe_user_fps
        # Always reconcile the operator-facing fps_user when the request had to be
        # clamped DOWN (e.g. restoring 25 fps into a 4k mode whose fps_max is 16).
        # Without this the GUI keeps showing the stale higher number even though
        # the actual recording fps was correctly clamped. The upward "remember the
        # user's target" intent is preserved: we only force-write on a downward clamp.
        if update_user_target or safe_user_fps < requested_user_fps:
            self.redis_controller.set_value(ParameterKey.FPS_USER.value, self.user_fps)

        self.current_fps = safe_value
        self.redis_controller.set_value(ParameterKey.FPS.value, safe_value)

        # ── shutter angle handling ─────────────────────────────────────────
        if self.shutter_a_sync_mode == 0:
            # keep motion-blur constant
            self.initialize_shutter_angle_steps()
            self.shutter_angle_actual = min(
                self.shutter_a_steps_dynamic,
                key=lambda x: abs(x - self.shutter_angle_actual))
        else:
            # keep exposure-time constant
            self.shutter_angle_actual = round(
                self.exposure_time_nominal * self.current_fps * 360, 1)
            self.shutter_angle_actual = min(360.0,
                                            max(1.0, self.shutter_angle_actual))

        self.redis_controller.set_value(ParameterKey.SHUTTER_A_ACTUAL.value,
                                        self.shutter_angle_actual)

        # update exposure display
        self.exposure_time_s = (self.shutter_angle_actual / 360.0) / self.current_fps
        self.exposure_time_fractions = self.seconds_to_fraction_text(
            self.exposure_time_s)
        self.redis_controller.set_value(ParameterKey.EXPOSURE_TIME.value,
                                        self.exposure_time_s)

        self.fps = int(round(self.current_fps))
        logging.info(f"FPS set to {self.current_fps} "
                    f"(user {self.user_fps}, free={self.fps_free}, "
                    f"sync={self.shutter_a_sync_mode})")


    def set_iso_lock(self, value=None):
        if value is not None:
            if value in (0, False):
                self.iso_lock = False
            elif value in (1, True):
                self.iso_lock = True
            else:
                raise ValueError("Invalid value. Please provide either 0, 1, True, or False.")
        else:
            self.iso_lock = not self.iso_lock
        logging.info(f"ISO lock {self.iso_lock}")

    def set_shutter_a_nom_lock(self, value=None):
        if value is not None:
            if value in (0, False):
                self.shutter_a_nom_lock = False
            elif value in (1, True):
                self.shutter_a_nom_lock = True
            else:
                raise ValueError("Invalid value. Please provide either 0, 1, True, or False.")
        else:
            self.shutter_a_nom_lock = not self.shutter_a_nom_lock
        logging.info(f"Shutter angle lock {self.shutter_a_nom_lock}")

    def set_fps_lock(self, value=None):
        if value is not None:
            if value in (0, False):
                self.fps_lock = False
            elif value in (1, True):
                self.fps_lock = True
            else:
                raise ValueError("Invalid value. Please provide either 0, 1, True, or False.")
        else:
            self.fps_lock = not self.fps_lock
        logging.info(f"FPS lock {self.fps_lock}")

    def _cancel_timed_recording_stop(self):
        if self._timed_rec_timer:
            self._timed_rec_timer.cancel()
            self._timed_rec_timer = None
            if self._timed_rec_description:
                logging.info(f"Cancelled scheduled recording stop ({self._timed_rec_description}).")
            self._timed_rec_description = None

    def _timed_recording_timeout(self):
        description = self._timed_rec_description or "timed recording"
        self._timed_rec_timer = None
        self._timed_rec_description = None
        logging.info(f"Timed recording limit reached ({description}); stopping.")
        if self.redis_controller.get_value(ParameterKey.IS_RECORDING.value) == "1":
            self.stop_recording()

    def _schedule_timed_recording_stop(self, seconds: float, description: str) -> None:
        self._cancel_timed_recording_stop()
        self._timed_rec_description = description
        self._timed_rec_timer = Timer(seconds, self._timed_recording_timeout)
        self._timed_rec_timer.start()
        logging.info(f"Recording will stop in {seconds:.3f}s ({description}).")

    def attach_redis_listener(self, redis_listener) -> None:
        self.redis_listener = redis_listener

    def add_resolution_change_callback(self, callback) -> None:
        if not callable(callback):
            logging.warning("Ignoring non-callable resolution change callback.")
            return
        self._resolution_change_callbacks.append(callback)

    def _notify_resolution_change(self, sensor_mode) -> None:
        for callback in list(self._resolution_change_callbacks):
            try:
                callback(sensor_mode)
            except Exception:
                logging.exception("Resolution change callback failed.")

    def _pace_resolution_change(self, recording: bool) -> None:
        min_interval = (
            self._recording_resolution_change_min_interval_s
            if recording
            else self._resolution_change_min_interval_s
        )

        with self._resolution_change_pace_lock:
            now = time.monotonic()
            elapsed = now - self._last_resolution_change_started_at
            wait_time = min_interval - elapsed
            if wait_time > 0:
                logging.info(
                    "Waiting %.2fs for the previous resolution reconfigure to settle.",
                    wait_time,
                )
                time.sleep(wait_time)
                now = time.monotonic()
            self._last_resolution_change_started_at = now

    def _clear_frame_limited_recording_stop(self) -> None:
        if self.redis_listener and hasattr(self.redis_listener, "disarm_frame_limited_stop"):
            self.redis_listener.disarm_frame_limited_stop()

    def _arm_frame_limited_recording_stop(self, frames_target: int, *, fresh_take: bool = False) -> bool:
        if not self.redis_listener or not hasattr(self.redis_listener, "arm_frame_limited_stop"):
            logging.warning("RedisListener unavailable; cannot arm exact frame-limited recording.")
            return False

        self.redis_listener.arm_frame_limited_stop(frames_target, fresh_take=fresh_take)
        return True

    def _get_current_fps(self) -> float:
        candidates = [
            self.redis_controller.get_value(ParameterKey.FPS_ACTUAL.value),
            self.redis_controller.get_value(ParameterKey.FPS.value),
            self.redis_controller.get_value(ParameterKey.FPS_LAST.value),
            self.current_fps,
            self.fps,
        ]
        for value in candidates:
            if value is None:
                continue
            try:
                fps = float(value)
            except (TypeError, ValueError):
                continue
            if fps > 0:
                return fps
        return 0.0

    def rec(self, mode=None, amount=None, record_override=None):
        logging.info(f"rec command received (mode={mode}, amount={amount}, record_override={record_override})")
        if self.is_preroll_active():
            logging.info("rec request ignored – storage pre-roll in progress")
            return

        if mode is None:
            if self.redis_controller.get_value(ParameterKey.IS_RECORDING.value) == "0":
                self.start_recording(record_override=record_override)
            elif self.redis_controller.get_value(ParameterKey.IS_RECORDING.value) == "1":
                self.stop_recording()
            else:
                logging.warning("Unknown recording state received from Redis.")
            return

        if isinstance(mode, str):
            mode_key = mode.lower()
        else:
            mode_key = str(mode).lower()

        seconds_aliases = {"s", "sec", "secs", "second", "seconds"}
        frames_aliases = {"f", "frame", "frames"}

        if mode_key in seconds_aliases:
            try:
                duration_seconds = float(amount)
            except (TypeError, ValueError):
                logging.warning("Invalid seconds value provided for timed recording.")
                return
            if duration_seconds <= 0:
                logging.warning("Timed recording duration must be greater than zero seconds.")
                return

            recording_state = self.redis_controller.get_value(ParameterKey.IS_RECORDING.value)
            is_recording = str(recording_state) == "1"
            if not is_recording:
                self.start_recording(record_override=record_override)
                is_recording = str(self.redis_controller.get_value(ParameterKey.IS_RECORDING.value)) == "1"
                if not is_recording:
                    logging.warning("Unable to start recording; timed stop not scheduled.")
                    return

            self._clear_frame_limited_recording_stop()
            self._schedule_timed_recording_stop(duration_seconds, f"{duration_seconds:.3f} seconds")
            return

        if mode_key in frames_aliases:
            try:
                frames_target = int(amount)
            except (TypeError, ValueError):
                logging.warning("Invalid frame count provided for timed recording.")
                return
            if frames_target <= 0:
                logging.warning("Timed recording frame count must be greater than zero.")
                return

            recording_state = self.redis_controller.get_value(ParameterKey.IS_RECORDING.value)
            is_recording = str(recording_state) == "1"
            started_fresh = not is_recording
            if not is_recording:
                self.start_recording(record_override=record_override)
                is_recording = str(self.redis_controller.get_value(ParameterKey.IS_RECORDING.value)) == "1"
                if not is_recording:
                    logging.warning("Unable to start recording; frame-limited stop not scheduled.")
                    return

            self._cancel_timed_recording_stop()
            if self._arm_frame_limited_recording_stop(frames_target, fresh_take=started_fresh):
                logging.info(
                    "Recording will stop after %d frame slots (counting dropped frames toward the limit).",
                    frames_target,
                )
            return

        logging.warning(f"Unknown recording mode '{mode}'. Expected 's' for seconds or 'f' for frames.")

    def set_preroll_active(self, active: bool) -> None:
        if active:
            self._preroll_active.set()
        else:
            self._preroll_active.clear()

    def is_preroll_active(self) -> bool:
        return self._preroll_active.is_set()

    def _current_storage_recorder_profile(self) -> str:
        filesystem = self.redis_controller.get_value(
            ParameterKey.STORAGE_FILESYSTEM.value,
            "none",
        )
        return recorder_profile_name_for_filesystem(filesystem)

    def _storage_profile_restart_allowed(self) -> bool:
        if str(self.redis_controller.get_value(ParameterKey.IS_RECORDING.value)) == "1":
            return False
        if str(self.redis_controller.get_value(ParameterKey.STORAGE_PREROLL_ACTIVE.value)) == "1":
            return False
        return not self.is_preroll_active()

    def _handle_storage_mount_event(self, *_args) -> None:
        self._refresh_fps_max()
        self.update_steps()
        self._maybe_schedule_storage_profile_restart("storage mount")

    def _handle_storage_restart_redis_event(self, data=None) -> None:
        if not isinstance(data, dict):
            return
        key = data.get("key")
        if key not in (
            ParameterKey.IS_RECORDING.value,
            ParameterKey.STORAGE_PREROLL_ACTIVE.value,
        ):
            return
        if self._storage_profile_restart_pending and self._storage_profile_restart_allowed():
            self._maybe_schedule_storage_profile_restart("deferred storage profile change")

    def _maybe_schedule_storage_profile_restart(self, reason: str) -> None:
        target_profile = self._current_storage_recorder_profile()
        with self._storage_profile_restart_lock:
            if target_profile == self._active_storage_recorder_profile:
                self._storage_profile_restart_pending = False
                return

            if not self._storage_profile_restart_allowed():
                self._storage_profile_restart_pending = True
                logging.info(
                    "Deferring cinepi-raw restart for storage profile %s -> %s (%s)",
                    self._active_storage_recorder_profile,
                    target_profile,
                    reason,
                )
                return

            if self._storage_profile_restart_active:
                self._storage_profile_restart_pending = True
                return

            self._storage_profile_restart_active = True
            self._storage_profile_restart_pending = False

        thread = threading.Thread(
            target=self._restart_camera_for_storage_profile,
            args=(target_profile, reason),
            name="StorageProfileRestart",
            daemon=True,
        )
        thread.start()

    def _restart_camera_for_storage_profile(self, target_profile: str, reason: str) -> None:
        try:
            if not self._storage_profile_restart_allowed():
                with self._storage_profile_restart_lock:
                    self._storage_profile_restart_pending = True
                return

            logging.info(
                "Restarting cinepi-raw for storage profile change %s -> %s (%s)",
                self._active_storage_recorder_profile,
                target_profile,
                reason,
            )
            self.restart_camera(preview_enabled=True)
            with self._storage_profile_restart_lock:
                self._active_storage_recorder_profile = target_profile
        finally:
            rerun = False
            with self._storage_profile_restart_lock:
                self._storage_profile_restart_active = False
                rerun = self._storage_profile_restart_pending
            if rerun and self._storage_profile_restart_allowed():
                self._maybe_schedule_storage_profile_restart("queued storage profile change")

    def _buffered_frames_flushing(self) -> bool:
        """True while cinepi-raw is still draining buffered frames to disk after
        a take — the green ``is_writing_buf`` state. Mirrors the keys the GUI
        paints green on and that ssd_monitor gates erase/format on."""
        for key in (ParameterKey.IS_WRITING_BUF.value, ParameterKey.IS_BUFFERING.value):
            if str(self.redis_controller.get_value(key) or "0").strip() == "1":
                return True
        return False

    # Preview-source token → the sensor that is "mainly" shown. `both` has no
    # single main (both are equal). Pip modes are named after their main sensor.
    _PREVIEW_MAIN = {
        "cam0": "cam0", "cam1": "cam1",
        "pip_cam0": "cam0", "pip_cam1": "cam1",
    }

    def _present_cam_ports(self):
        """Ports of the sensors cinepi-raw actually discovered, e.g.
        ['cam0', 'cam1']. Falls back to ['cam0'] if the list is unavailable."""
        try:
            raw = self.redis_controller.get_value(ParameterKey.CAMERAS.value)
            cams = json.loads(raw) if raw else []
            ports = sorted({c.get("port") for c in cams if c.get("port")})
            return ports or ["cam0"]
        except (TypeError, ValueError, json.JSONDecodeError):
            return ["cam0"]

    def _resolve_record_cams(self, override=None):
        """Decide which sensor(s) record the next take, returned as a
        ``record_cams`` token (``cam0+cam1`` | ``cam0`` | ``cam1``) for
        cinepi-raw's per-camera record gate.

        Rule (single sensor is a no-op — only its own port ever records):
          • explicit ``rec cam0/cam1/both`` override wins;
          • else record both when the preview is side-by-side ``both`` OR
            settings ``lock_dual_recording`` is true (force dual);
          • else record the preview's main sensor (fullscreen or pip main).
        Always clamped to the sensors actually present.
        """
        ports = self._present_cam_ports()
        both = "cam0+cam1"

        # Single sensor: nothing to gate.
        if len(ports) < 2:
            return ports[0]

        # Explicit per-take override wins.
        if override in ("both", "dual", "cam0+cam1"):
            return both
        if override in ("cam0", "cam1"):
            return override if override in ports else ports[0]

        preview = str(
            self.redis_controller.get_value(ParameterKey.HDMI_PREVIEW_SOURCE.value)
            or "both"
        ).strip().lower()

        lock_dual = bool(self.settings.get("lock_dual_recording", False))

        # Side-by-side always records both (both are equally shown); the lock
        # forces dual even in a single-sensor preview mode.
        if preview == "both" or lock_dual:
            return both

        main = self._PREVIEW_MAIN.get(preview, "cam0")
        return main if main in ports else ports[0]

    @staticmethod
    def _union_gate(a, b, ports):
        """Union two ``record_cams`` tokens into one, clamped to present ports.
        Tokens may be ``cam0``, ``cam1``, ``cam0+cam1`` or the ``both`` alias."""
        def cams(tok):
            tok = str(tok or "").strip().lower()
            if tok in ("both", "cam0+cam1", "dual"):
                return {"cam0", "cam1"}
            return {c for c in ("cam0", "cam1") if c in tok}

        selected = (cams(a) | cams(b)) & set(ports)
        if not selected:
            return ""
        if selected >= {"cam0", "cam1"}:
            return "cam0+cam1"
        return next(iter(selected))

    def _extend_record_gate_for_preview(self, preview):
        """Join-only live record-gate update for a preview switch during a take.

        Recompute the preview-derived gate and UNION it with what is already
        recording, so switching to the dual view starts the second sensor
        without ever stopping a sensor that is mid-clip. cinepi-raw picks the
        new ``record_cams`` up live and the sitting-out sensor joins back-to-back.
        No-op on single-sensor rigs and when the gate does not grow.
        """
        ports = self._present_cam_ports()
        if len(ports) < 2:
            return
        desired = self._resolve_record_cams()          # preview-aware target
        current = str(
            self.redis_controller.get_value(ParameterKey.RECORD_CAMS.value) or ""
        )
        merged = self._union_gate(current, desired, ports)
        if merged and merged != current:
            self.redis_controller.set_value(ParameterKey.RECORD_CAMS.value, merged)
            logging.info("Live record gate extended: %s → %s (preview %s)",
                         current or "—", merged, preview)

    def start_recording(self, record_override=None):
        # Safety: refuse to start a new take while the previous take's frames are
        # still flushing from RAM to disk (the green is_writing_buf state). Letting
        # the buffer finish means no recorded frame is lost; the operator presses
        # rec again once the flush completes and green clears. Storage pre-roll is
        # exempt — it primes the disk and waits out its own flush.
        if not self.is_preroll_active() and self._buffered_frames_flushing():
            logging.info(
                "rec ignored – previous take's buffered frames are still flushing to disk")
            return
        self._cancel_timed_recording_stop()
        self._clear_frame_limited_recording_stop()
        self.redis_controller.set_value(ParameterKey.MEMORY_ALERT.value, 0)
        if self.ssd_monitor.is_mounted == True and self.ssd_monitor.get_space_left:
            # Publish which sensor(s) record this take BEFORE is_recording flips,
            # so each cinepi-raw sees the gate value when it acts on the edge.
            record_cams = self._resolve_record_cams(record_override)
            self.redis_controller.set_value(ParameterKey.RECORD_CAMS.value, record_cams)
            logging.info("Recording target: %s", record_cams)
            self.redis_controller.set_value(ParameterKey.IS_RECORDING.value, 1)
            logging.info(f"Started recording")
            # Arm the RAM-buffer / system-RAM watchdog so a full buffer auto-stops
            # the take instead of stalling the clock with the GUI stuck on red.
            self.start_recording_worker()
        else:
            logging.info(f"No disk.")

    def stop_recording(self):
        self._cancel_timed_recording_stop()
        # Do not disarm the frame limit here: analyze_frames() needs
        # frame_limit_requested_slots to compute the correct expected count.
        # _clear_post_recording_state() clears it after analysis; start_recording()
        # clears it before the next take begins.
        self.stop_recording_worker()
        self.redis_controller.set_value(ParameterKey.IS_RECORDING.value, 0)
        logging.info(f"Stopped recording")

    def _is_recording(self) -> bool:
        return str(self.redis_controller.get_value(ParameterKey.IS_RECORDING.value)) == "1"

    def _mode_string(self, info: dict, packing: str | None = None) -> str:
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        bit_depth = int(info.get("bit_depth") or 12)
        # Prefer an explicit platform-aware packing token; fall back to the
        # mode's default only when none is supplied.
        packing = str(packing or info.get("packing") or "U").upper()[0]
        return f"{width}:{height}:{bit_depth}:{packing}"

    def _select_resolution_mode_for_fps(self, target_fps: float):
        candidates = []
        for mode, info in self.sensor_detect.res_modes.items():
            try:
                fps_max = float(info.get("fps_max") or 0)
                area = int(info.get("width") or 0) * int(info.get("height") or 0)
            except (TypeError, ValueError):
                continue
            if fps_max >= target_fps:
                candidates.append((area, mode))

        if not candidates:
            return self.sensor_mode

        candidates.sort(reverse=True)
        return candidates[0][1]

    def switch_resolution(self):
        try:
            sensor_modes = sorted(
                self.sensor_detect.res_modes.keys(),
                key=lambda mode: int(mode),
            )
            num_sensor_modes = len(sensor_modes)

            if num_sensor_modes <= 1:
                logging.info("Only one sensor mode available. Cannot switch resolution.")
                return False

            current_sensor_mode = (
                self.dynamic_resolution_desired_mode
                if self.dynamic_resolution_enabled
                and self.dynamic_resolution_desired_mode is not None
                else self.redis_controller.get_value(ParameterKey.SENSOR_MODE.value)
            )
            if current_sensor_mode is None:
                current_sensor_mode = self.sensor_mode

            try:
                current_sensor_mode = int(current_sensor_mode)
            except (TypeError, ValueError):
                current_sensor_mode = self.sensor_mode

            current_index = next(
                (
                    index
                    for index, sensor_mode in enumerate(sensor_modes)
                    if int(sensor_mode) == int(current_sensor_mode)
                ),
                None,
            )

            if current_index is None:
                logging.warning(
                    "Current sensor mode %s not found in available modes %s. Switching to first mode.",
                    current_sensor_mode,
                    sensor_modes,
                )
                next_sensor_mode = sensor_modes[0]
            else:
                next_index = (current_index + 1) % num_sensor_modes
                next_sensor_mode = sensor_modes[next_index]

            logging.info("Switching resolution from mode %s to mode %s", current_sensor_mode, next_sensor_mode)
            return self.set_resolution(next_sensor_mode)

        except (TypeError, ValueError) as error:
            logging.error(f"Error switching resolution: {error}")
            return False

    def _normalize_sensor_mode_value(self, value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 0
        if value not in self.sensor_detect.res_modes:
            logging.info(f"Couldn't find sensor mode {value}. Trying with sensor_mode 0.")
            value = 0
        return value

    def _publish_resolution_gui_state(self, value, resolution_info):
        self.sensor_mode = int(value)
        height_new = resolution_info.get('height', None)
        width_new = resolution_info.get('width', None)
        bit_depth_new = resolution_info.get('bit_depth', None)
        # Platform-aware packing (data-driven from sensors.json) so the GUI/HUD
        # report the same P/U token that cinepi-raw is actually launched with.
        packing_new = self.sensor_detect.get_packing_for_platform(self.current_sensor, int(value))
        gui_layout_new = resolution_info.get('gui_layout', None)
        file_size_new = resolution_info.get('file_size', None)

        if height_new is None or width_new is None or gui_layout_new is None:
            raise ValueError("Invalid height, width, or gui_layout value.")

        self.gui_layout = gui_layout_new
        self.file_size = file_size_new

        self.redis_controller.set_value(ParameterKey.SENSOR_MODE.value, str(value))
        self.redis_controller.set_value(ParameterKey.HEIGHT.value, str(height_new))
        self.redis_controller.set_value(ParameterKey.WIDTH.value, str(width_new))
        self.redis_controller.set_value(ParameterKey.BIT_DEPTH.value, str(bit_depth_new))
        # ClearHDR (imx585): the mode carries the HDR flag, so selecting a
        # 12-bit-HDR or 16-bit-HDR mode turns the hdr key on and cinepi-raw
        # launches with --hdr sensor; a plain mode turns it back off.
        hdr_new = bool(resolution_info.get('hdr', False))
        self.redis_controller.set_value(ParameterKey.HDR.value, 1 if hdr_new else 0)
        self.redis_controller.set_value(ParameterKey.PACKING.value, str(packing_new))
        self.redis_controller.set_value(ParameterKey.GUI_LAYOUT.value, str(gui_layout_new))
        self.redis_controller.set_value(ParameterKey.FILE_SIZE.value, str(file_size_new))
        self.redis_controller.set_value(
            ParameterKey.LORES_WIDTH.value,
            str(self.sensor_detect.get_lores_width(self.current_sensor, self.sensor_mode)),
        )
        self.redis_controller.set_value(
            ParameterKey.LORES_HEIGHT.value,
            str(self.sensor_detect.get_lores_height(self.current_sensor, self.sensor_mode)),
        )
        self.redis_controller.set_value(ParameterKey.MODE.value, self._mode_string(resolution_info, packing_new))
        self.redis_controller.set_value(ParameterKey.SENSOR.value, self.sensor_detect.camera_model)
        self.fps_max = self._refresh_fps_max()
        self.dynamic_resolution_active = (
            self.dynamic_resolution_enabled
            and dynamic_resolution_is_lower_substitute(
                sensor_modes=self.sensor_detect.res_modes,
                current_mode=self.sensor_mode,
                desired_mode=self.dynamic_resolution_desired_mode,
            )
        )
        self._publish_dynamic_resolution_state()

        logging.info(
            "Resolution GUI state set to mode %s, height: %s, width: %s, gui_layout: %s",
            value,
            height_new,
            width_new,
            gui_layout_new,
        )

    def _publish_resolution_target_state(self, value, resolution_info, *, switching):
        self.redis_controller.set_value(ParameterKey.RESOLUTION_TARGET_MODE.value, str(value))
        self.redis_controller.set_value(
            ParameterKey.RESOLUTION_TARGET_WIDTH.value,
            str(resolution_info.get('width')),
        )
        self.redis_controller.set_value(
            ParameterKey.RESOLUTION_TARGET_HEIGHT.value,
            str(resolution_info.get('height')),
        )
        self.redis_controller.set_value(
            ParameterKey.RESOLUTION_TARGET_BIT_DEPTH.value,
            str(resolution_info.get('bit_depth')),
        )
        self.redis_controller.set_value(
            ParameterKey.RESOLUTION_SWITCHING.value,
            1 if switching else 0,
        )

    def _cancel_resolution_switching_timer(self):
        timer = getattr(self, "_resolution_switching_timer", None)
        if timer is not None:
            timer.cancel()
            self._resolution_switching_timer = None

    def _schedule_resolution_switch_complete(self, value, resolution_info):
        self._cancel_resolution_switching_timer()

        def complete():
            try:
                self._publish_resolution_target_state(
                    value,
                    resolution_info,
                    switching=False,
                )
            except Exception:
                logging.exception("Failed to clear resolution switching state.")

        timer = threading.Timer(GUI_RESOLUTION_SWITCHING_HOLD_SECONDS, complete)
        timer.daemon = True
        self._resolution_switching_timer = timer
        timer.start()

    def handle_cinepi_raw_message(self, message):
        if not isinstance(message, str):
            return

        match = RAW_STREAM_READY_RE.search(message)
        if not match:
            return

        target_width = _safe_int(
            self.redis_controller.get_value(ParameterKey.RESOLUTION_TARGET_WIDTH.value)
        )
        target_height = _safe_int(
            self.redis_controller.get_value(ParameterKey.RESOLUTION_TARGET_HEIGHT.value)
        )
        if target_width is None or target_height is None:
            return

        raw_width = int(match.group(1))
        raw_height = int(match.group(2))
        if raw_width != target_width or raw_height != target_height:
            return

        self._cancel_resolution_switching_timer()
        self.redis_controller.set_value(ParameterKey.RESOLUTION_SWITCHING.value, 0)

    def _apply_resolution_mode(self, value, restore_user_fps=None, *, restart_process=False):
        try:
            value = self._normalize_sensor_mode_value(value)
            resolution_info = self.sensor_detect.res_modes[value]
            recording = self._is_recording()
            if recording:
                logging.warning(
                    "Resolution change requested while recording. "
                    "cinepi-raw will split the recording around the camera reconfigure."
                )

            # Dynamic FPS changes should update the operator-facing resolution
            # selection immediately, even while preview reconfigure is pending.
            self._cancel_resolution_switching_timer()
            self._publish_resolution_target_state(
                value,
                resolution_info,
                switching=True,
            )
            self._publish_resolution_gui_state(value, resolution_info)
            self._pace_resolution_change(recording)
            time.sleep(GUI_RESOLUTION_PREVIEW_DELAY_SECONDS)

            self.redis_controller.set_value(ParameterKey.CAM_INIT.value, str(time.time_ns()))

            logging.info(
                "Resolution set to mode %s, height: %s, width: %s, gui_layout: %s",
                value,
                resolution_info.get('height'),
                resolution_info.get('width'),
                resolution_info.get('gui_layout'),
            )

            if restart_process:
                self.cinepi.restart()
                time.sleep(0.5)

            # Initialize fps_steps based on the provided list and capped by fps_max
            self.initialize_fps_steps(self.fps_steps)
            self.shutter_a_steps_dynamic = self.calculate_dynamic_shutter_angles(self.current_fps)

            self.fps_max = self._refresh_fps_max()
            if self.fps_free:
                self.fps_steps = list(range(1, self.fps_max + 1))

            self.update_steps()

            if restore_user_fps is not None:
                self.set_fps(float(restore_user_fps), update_user_target=False)

            self._notify_resolution_change(value)
            self._schedule_resolution_switch_complete(value, resolution_info)
            return True

        except ValueError as error:
            self.redis_controller.set_value(ParameterKey.RESOLUTION_SWITCHING.value, 0)
            logging.error(f"Error setting resolution: {error}")
            return False

    @staticmethod
    def _aspect_ratio(width, height):
        try:
            w = float(width)
            h = float(height)
        except (TypeError, ValueError):
            return None
        return (w / h) if h > 0 else None

    def _resolution_change_needs_restart(self, target_mode):
        """Whether switching to *target_mode* must relaunch cinepi-raw.

        A live "record-through" reconfigure can only change things cinepi-raw
        re-reads on the fly; several launch args it cannot:

        * **Aspect ratio** — the preview window (-p) and lores geometry are
          baked in from the mode's aspect ratio, so a same-aspect change stays
          correct but a different-aspect one leaves the preview letterboxed
          until a restart.
        * **Bit depth** — part of ``--mode``. Switching between the imx585
          12-bit and 16-bit ClearHDR modes (same aspect) otherwise keeps
          recording 12-bit DNGs because the sensor format never changes.
        * **ClearHDR** — ``--hdr sensor`` is a launch flag; toggling it needs a
          relaunch for wide_dynamic_range to take effect.

        So a change to aspect ratio, bit depth or the HDR flag needs a restart.
        Recording is deliberately left seamless: we never split a running take,
        so such a change applies on the next launch instead.
        """
        if self._is_recording():
            return False
        try:
            target_info = self.sensor_detect.res_modes.get(int(target_mode), {})
        except (TypeError, ValueError):
            return False

        new_ar = self._aspect_ratio(target_info.get("width"), target_info.get("height"))
        cur_ar = self._aspect_ratio(
            self.redis_controller.get_value(ParameterKey.WIDTH.value),
            self.redis_controller.get_value(ParameterKey.HEIGHT.value),
        )
        if new_ar is not None and cur_ar is not None and abs(new_ar - cur_ar) > 0.01:
            return True

        # Bit depth is part of --mode; a live reconfigure cannot change the
        # sensor's bit depth, so a 12-bit → 16-bit switch needs a relaunch.
        # (All imx585 modes share one aspect ratio, so without this the switch
        # would never restart and 16-bit modes would keep writing 12-bit DNGs.)
        try:
            new_bd = int(target_info.get("bit_depth"))
            cur_bd = int(self.redis_controller.get_value(ParameterKey.BIT_DEPTH.value))
            if new_bd != cur_bd:
                return True
        except (TypeError, ValueError):
            pass

        # ClearHDR is the --hdr sensor launch flag.
        new_hdr = 1 if bool(target_info.get("hdr")) else 0
        cur_hdr = 1 if str(self.redis_controller.get_value(ParameterKey.HDR.value) or "0") == "1" else 0
        if new_hdr != cur_hdr:
            return True

        return False

    def set_resolution(self, value=None, *, restart_process=False):
        if value is not None:
            value = self._normalize_sensor_mode_value(value)
            if self.dynamic_resolution_enabled:
                self.dynamic_resolution_desired_mode = value
                self._publish_dynamic_resolution_state()
                current_user_fps = self._current_user_fps_value()
                if current_user_fps is not None:
                    choice = self._dynamic_resolution_choice_for_fps(
                        current_user_fps,
                    )
                    if choice is not None:
                        value = choice.mode

            # Relaunch cinepi-raw when the aspect ratio changes so the preview
            # window is rebuilt for the new shape; same-aspect changes stay
            # seamless (record-through). See _resolution_change_needs_restart.
            if not restart_process and self._resolution_change_needs_restart(value):
                restart_process = True

            restore_user_fps = self._current_user_fps_value()
            return self._apply_resolution_mode(
                value,
                restore_user_fps=restore_user_fps,
                restart_process=restart_process,
            )

        else:
            return self.switch_resolution()
        
    def get_current_sensor_mode(self):
        current_height = int(self.redis_controller.get_value(ParameterKey.HEIGHT.value))
        try:
            current_bd = int(self.redis_controller.get_value(ParameterKey.BIT_DEPTH.value))
        except (TypeError, ValueError):
            current_bd = None
        current_hdr = str(self.redis_controller.get_value(ParameterKey.HDR.value) or "0") == "1"

        # Height alone is ambiguous on the imx585: the 12-bit HDR modes share
        # dimensions with the plain 12-bit ones (and with the 16-bit HDR
        # modes), so a height-only match used to select the SDR sibling of a
        # chosen HDR mode. Match bit depth and the HDR flag as well.
        for mode, info in self.sensor_detect.res_modes.items():
            if info.get('height') != current_height:
                continue
            if current_bd is not None and info.get('bit_depth') not in (None, current_bd):
                continue
            if bool(info.get('hdr', False)) != current_hdr:
                continue

            fps_max_value = info.get('fps_max', None)
            self.redis_controller.set_value(ParameterKey.FPS_MAX.value, fps_max_value)
            self.redis_controller.set_value(ParameterKey.SENSOR_MODE.value, mode)
            return mode

        return None  # Return None if no matching sensor mode is found

    def set_iso(self, value):
        if not self.iso_lock:
            with self.parameters_lock_obj:
                safe_value = max(min(value, max(self.iso_steps)), min(self.iso_steps))
                self.redis_controller.set_value(ParameterKey.ISO.value, safe_value)
                logging.info(f"Setting iso to {safe_value}")

    def set_shutter_a(self, value):
        logging.info(f"Entering set_shutter_a() with value: {value}")
        with self.parameters_lock_obj:
            # Only clamp when we're NOT in sync mode and NOT in free-mode
            if self.shutter_a_sync_mode == 0 and not self.shutter_a_free:
                # rebuild flicker-free + user array based on the current self.fps
                self.shutter_a_steps_dynamic = self.calculate_dynamic_shutter_angles(self.current_fps)
                if value in self.shutter_a_steps_dynamic:
                    safe_value = value
                else:
                    safe_value = min(
                        self.shutter_a_steps_dynamic,
                        key=lambda x: abs(x - value)
                    )
                    logging.info(f"Snapping shutter_a to {safe_value}° (nearest valid angle)")
            else:
                # In sync mode, or free-mode, just accept it verbatim
                safe_value = value
                logging.info(f"Accepted shutter_a as {safe_value}° (free or sync mode)")

        # Commit the final value outside the lock
        self.redis_controller.set_value(ParameterKey.SHUTTER_A.value, safe_value)
        
        # also update the "actual" key so GUI reflects CLI changes
        self.redis_controller.set_value(ParameterKey.SHUTTER_A_ACTUAL.value, safe_value)
        # keep nominal angle in sync when not using sync mode

        if self.shutter_a_sync_mode == 0:
            self.shutter_angle_nom = safe_value
        
        self.exposure_time_seconds = (safe_value / 360.0) / self.current_fps

        self.exposure_time_fractions = self.seconds_to_fraction_text(
            self.exposure_time_seconds
        )
        logging.info(f"Shutter angle set to {safe_value}°, exposure time: {self.exposure_time_seconds:.6f}s ({self.exposure_time_fractions})")


    def set_shutter_a_nom(self, value):
        logging.info(f"Entering set_shutter_a_nom() with value: {value}")
        # Always rebuild the flicker-free array before snapping
        self.shutter_a_steps_dynamic = self.calculate_dynamic_shutter_angles(self.current_fps)

        if not self.shutter_a_nom_lock:
            with self.parameters_lock_obj:
                # Snap to nearest legal step only if not in sync mode
                if self.shutter_a_sync_mode == 0 and not self.shutter_a_free:
                    if value in self.shutter_a_steps_dynamic:
                        safe_value = value
                    else:
                        safe_value = min(
                            self.shutter_a_steps_dynamic,
                            key=lambda x: abs(x - value)
                        )
                    logging.info(f"Snapped shutter_a_nom to {safe_value}° (nearest valid angle)")
                else:
                    # In sync mode or free mode, just accept it verbatim
                    safe_value = value
                    logging.info(f"Accepted shutter_a_nom as {safe_value}° (free or sync mode)")

                # Save nominal shutter angle
                self.shutter_angle_nom = safe_value
                self.redis_controller.set_value(
                    ParameterKey.SHUTTER_A_NOM.value, safe_value
                )

                # Compute nominal exposure time
                self.exposure_time_seconds = (safe_value / 360.0) / self.current_fps
                self.exposure_time_fractions = self.seconds_to_fraction_text(
                    self.exposure_time_seconds
                )
                logging.info(
                    f"Nominal exposure time updated to {self.exposure_time_seconds:.6f}s "
                    f"({self.exposure_time_fractions})"
                )

                if self.shutter_a_sync_mode == 1:
                    # Sync mode: update nominal exposure time and recompute actual shutter angle
                    self.exposure_time_nominal = self.exposure_time_seconds
                    self.shutter_angle_actual = safe_value
                    self.redis_controller.set_value(
                        ParameterKey.SHUTTER_A_ACTUAL.value, safe_value
                    )
                    logging.info(
                        f"Sync mode: shutter angle actual set to {safe_value}° "
                        f"to preserve nominal exposure time."
                    )
                else:
                    # In normal mode, directly set actual shutter angle
                    self.shutter_angle_actual = safe_value
                    self.redis_controller.set_value(
                        ParameterKey.SHUTTER_A_ACTUAL.value, safe_value
                    )
                    logging.info(
                        f"Normal mode: shutter angle actual set to {safe_value}°"
                )
                    
                # ensure main shutter_a value is updated for preview and web UI
                self.redis_controller.set_value(ParameterKey.SHUTTER_A.value, safe_value)

    def set_shu_fps_lock(self, value=None):
        if value is not None:
            if value in (0, False):
                self.shutter_a_nom_lock = False
                self.fps_lock = False
            elif value in (1, True):
                self.shutter_a_nom_lock = True
                self.fps_lock = True
            else:
                raise ValueError("Invalid value. Please provide either 0, 1, True, or False.")
        else:
            self.shutter_a_nom_lock = not self.shutter_a_nom_lock
            self.fps_lock = not self.fps_lock
        logging.info(f"Shutter angle lock {self.shutter_a_nom_lock}")
        logging.info(f"FPS lock {self.fps_lock}")
        
    def set_all_lock(self, value=None):
        if value is not None:
            if value in (0, False):
                self.all_lock = False
                self.iso_lock = False
                self.shutter_a_nom_lock = False
                self.fps_lock = False
            elif value in (1, True):
                self.all_lock = True
                self.iso_lock = True
                self.shutter_a_nom_lock = True
                self.fps_lock = True
            else:
                raise ValueError("Invalid value. Please provide either 0, 1, True, or False.")
        else:
            self.all_lock = not self.all_lock
            self.iso_lock = not self.iso_lock
            self.shutter_a_nom_lock = not self.shutter_a_nom_lock
            self.fps_lock = not self.fps_lock
            
        logging.info(f"ISO lock {self.iso_lock}")  
        logging.info(f"Shutter angle lock {self.shutter_a_nom_lock}")
        logging.info(f"FPS lock {self.fps_lock}")
        
    def set_fps_multiplier(self, value):
        with self.parameters_lock_obj:
            self.fps_multiplier = value
            logging.info(f"FPS multiplier {self.fps_multiplier}")
                
    def get_setting(self, key):
        value = self.redis_controller.get_value(key)
        return value
    
    def reboot(self):
        if self.redis_controller.get_value(ParameterKey.IS_RECORDING.value) == "1":
            self.stop_recording()
        logging.info("Initiating safe system shutdown.")
        os.system("sudo reboot")
        
    def safe_shutdown(self):
        if self.redis_controller.get_value(ParameterKey.IS_RECORDING.value) == "1":
            self.stop_recording()
        logging.info("Initiating safe system shutdown.")
        os.system("sudo shutdown -h now")
    
    def mount(self):
        self.ssd_monitor.mount_drive()

    def unmount(self):
        # if self.ssd_monitor.is_mounted:
        self.ssd_monitor.unmount_drive()
        # else:
        #     if self.ssd_monitor.cfe_hat_present:
        #         logging.info("No drive currently mounted. CFE HAT detected — attempting to mount CFE...")
        #         self.ssd_monitor.mount_cfe()
        #     else:
        #         logging.info("No drive currently mounted and no CFE HAT present. Nothing to do.")

    def toggle_mount(self):
        self.ssd_monitor.toggle_mount_drive()

    def erase_drive(self):
        self.ssd_monitor.erase_drive()

    def format_drive(self, filesystem=None):
        self.ssd_monitor.format_drive(filesystem or "exfat")
    
    def calculate_dynamic_shutter_angles(self, fps):
        if fps <= 0:
            fps = 1  # Prevent division by zero

        dynamic_steps = set(self.shutter_a_steps)  # Start with user-defined shutter angles

        # Add flicker-free shutter angles for each frequency in light_hz
        for hz in self.light_hz:
            flicker_free_angles = self.calculate_flicker_free_shutter_angles(fps, hz)
            dynamic_steps.update(flicker_free_angles)  # Add unique flicker-free values

        self.shutter_a_steps_dynamic = sorted(dynamic_steps)
        logging.info(f"Updated shutter angles (user-defined + flicker-free): {self.shutter_a_steps_dynamic}")

        return self.shutter_a_steps_dynamic

    def calculate_flicker_free_shutter_angles(self, fps, hz):
        if fps <= 0:
            raise ValueError("FPS must be greater than zero.")

        flicker_free_angles = []
        
        for multiple in range(1, 10):  # Generate up to 10 harmonics
            angle = (hz / (fps * multiple)) * 360  # Calculate flicker-free shutter angle   
            if 1 <= angle <= 360:  # Ensure the angle is valid
                flicker_free_angles.append(round(angle, 1))

        logging.info(f"Generated flicker-free shutter angles for fps={fps}, hz={hz}: {flicker_free_angles}")
        
        return flicker_free_angles

    def update_fps(self, new_fps):
        self.current_fps = new_fps
        self.redis_controller.set_value(ParameterKey.FPS.value, new_fps)

        if self.shutter_a_sync_mode == 0:
            self.initialize_shutter_angle_steps()
            self.shutter_angle_actual = self.shutter_angle_nom
        else:
            self.shutter_angle_actual = min(
                360.0,
                max(1.0, round(self.exposure_time_nominal * new_fps * 360, 1))
            )

        self.redis_controller.set_value(ParameterKey.SHUTTER_A_ACTUAL.value, self.shutter_angle_actual)

        # Add this exposure update:
        self.exposure_time_s = (self.shutter_angle_actual / 360.0) / new_fps
        self.exposure_time_fractions = self.seconds_to_fraction_text(self.exposure_time_s)
        self.redis_controller.set_value(ParameterKey.EXPOSURE_TIME.value, self.exposure_time_s)


    def increment_setting(self, setting_name, steps, fps=None):
        current_value = float(self.get_setting(setting_name))
        
        if setting_name == 'shutter_a':
            dynamic_steps = self.calculate_dynamic_shutter_angles(self.current_fps)
        else:
            dynamic_steps = steps
        
        if setting_name == 'fps':
            current_value = int(round(float(self.get_setting(setting_name))))
        
        if current_value in dynamic_steps:
            idx = dynamic_steps.index(current_value)
            idx = min(idx + 1, len(dynamic_steps) - 1)
        else:
            idx = 0

        new_value = dynamic_steps[idx]
        
        # NEW: if we are changing FPS and sync mode is active,
        # sync shutter angle as well
        if setting_name == 'fps' and self.shutter_a_sync_mode == 1:
            self.set_fps(new_value)
            # this triggers shutter angle updates
        elif setting_name == 'shutter_a_nom' and self.shutter_a_sync_mode == 1:
            self.update_shutter_angle_nom(new_value)
            # this triggers sync logic
        else:
            getattr(self, f"set_{setting_name}")(new_value)

        logging.info(f"Increasing {setting_name} to {self.get_setting(setting_name)}")


    def decrement_setting(self, setting_name, steps, fps=None):
        current_value = float(self.get_setting(setting_name))

        if setting_name == 'shutter_a':
            dynamic_steps = self.calculate_dynamic_shutter_angles(self.current_fps)
        else:
            dynamic_steps = steps

        if setting_name == 'fps':
            current_value = int(round(float(self.get_setting(setting_name))))

        if current_value in dynamic_steps:
            idx = dynamic_steps.index(current_value)
            idx = max(idx - 1, 0)
        else:
            idx = 0

        new_value = dynamic_steps[idx]

        # NEW: sync updates if needed
        if setting_name == 'fps' and self.shutter_a_sync_mode == 1:
            self.set_fps(new_value)
        elif setting_name == 'shutter_a_nom' and self.shutter_a_sync_mode == 1:
            self.update_shutter_angle_nom(new_value)
        else:
            getattr(self, f"set_{setting_name}")(new_value)

        logging.info(f"Decreasing {setting_name} to {self.get_setting(setting_name)}")

    def inc_shutter_a(self):
        self.increment_setting('shutter_a', self.shutter_a_steps, fps=self.fps)

    def dec_shutter_a(self):
        self.decrement_setting('shutter_a', self.shutter_a_steps, fps=self.fps)
    
    def inc_iso(self):
        self.increment_setting('iso', self.iso_steps)

    def dec_iso(self):
        self.decrement_setting('iso', self.iso_steps)
        
    def inc_shutter_a_nom(self):
        self.increment_setting('shutter_a_nom', self.shutter_a_steps)

    def dec_shutter_a_nom(self):
        self.decrement_setting('shutter_a_nom', self.shutter_a_steps)

    def inc_fps(self):
        self.increment_setting('fps', self.fps_steps)

    def dec_fps(self):
        self.decrement_setting('fps', self.fps_steps)
        
    def initialize_wb_cg_rb_array(self):
        """Initialize the white balance cg_rb array based on the sensor model."""
        sensor_key = self.current_sensor.replace('_mono', '')

        if sensor_key == 'imx283':
            default_ct_curve = [
                    2213.0, 0.9607, 0.2593,
                    2255.0, 0.9309, 0.2521,
                    2259.0, 0.9257, 0.2508,
                    5313.0, 0.4822, 0.5909,
                    6237.0, 0.4726, 0.6376
                ]
        elif sensor_key == 'imx585':
            default_ct_curve = [
                    2187.0, 1.1114, 0.1026,
                    2258.0, 1.1063, 0.1147,
                    5225.0, 0.6631, 0.5507,
                    5289.0, 0.5769, 0.5731,
                    6532.0, 0.5259, 0.5801
                ]
        else:                
            default_ct_curve = [
                2000.0, 0.6331025775790707, 0.27424225990946915,
                2200.0, 0.5696117366212947, 0.3116091368689487,
                2400.0, 0.5204264653110015, 0.34892179554105873,
                2600.0, 0.48148675531667223, 0.38565229719076793,
                2800.0, 0.450085403501908, 0.42145684622485047,
                3000.0, 0.42436130159169017, 0.45611835670028816,
                3200.0, 0.40300023695527337, 0.48950766215198593,
                3400.0, 0.3850520052612984, 0.5215567075837261,
                3600.0, 0.36981508088230314, 0.5522397906415475,
                4100.0, 0.333468007836758, 0.5909770465167908,
                4600.0, 0.31196097364221376, 0.6515706327327178,
                5100.0, 0.2961860409294588, 0.7068178946570284,
                5600.0, 0.2842607232745885, 0.7564837749584288,
                6100.0, 0.2750265787051251, 0.8006183524920533,
                6600.0, 0.2677057225584924, 0.8398879225373039,
                7100.0, 0.2617955199757274, 0.8746456080032436,
                7600.0, 0.25693714288250125, 0.905569559506562,
                8100.0, 0.25287531441063316, 0.9331696750390895,
                8600.0, 0.24946601483331993, 0.9576820904825795
            ]

        self.wb_cg_rb_array = {}  # Ensuring it is initialized as a dictionary

        try:
            tuning_file_path = (
                f"/home/pi/libcamera/src/ipa/rpi/pisp/data/"
                f"{self.current_sensor.replace('_mono', '')}.json"
            )
            logging.info(f"Loading tuning file from: {tuning_file_path}")

            with open(tuning_file_path, 'r') as file:
                data = json.load(file)
                logging.info("Tuning data loaded successfully.")

            awb_data = next((algo['rpi.awb'] for algo in data['algorithms'] if 'rpi.awb' in algo), None)
            if not awb_data:
                logging.warning("'rpi.awb' algorithm data not found, using default ct_curve.")
                ct_curve = default_ct_curve
            else:
                logging.info(f"'rpi.awb' data found: {awb_data}")
                ct_curve = awb_data.get('ct_curve', None)
                if not ct_curve:
                    logging.warning("'ct_curve' not found in 'rpi.awb' data, using default ct_curve.")
                    ct_curve = default_ct_curve
                else:
                    logging.info(f"Retrieved ct_curve: {ct_curve}")

            temperatures = ct_curve[0::3]
            r_values = ct_curve[1::3]
            b_values = ct_curve[2::3]
            logging.info(f"Parsed temperatures: {temperatures}")
            logging.info(f"Parsed r_values: {r_values}")
            logging.info(f"Parsed b_values: {b_values}")

            for wb in self.wb_steps:
                if wb <= temperatures[0]:
                    lower_idx = upper_idx = 0
                elif wb >= temperatures[-1]:
                    lower_idx = upper_idx = len(temperatures) - 1
                else:
                    lower_idx = max(i for i, temp in enumerate(temperatures) if temp <= wb)
                    upper_idx = min(i for i, temp in enumerate(temperatures) if temp >= wb)

                logging.info(f"Interpolating for wb step: {wb}K, lower index: {lower_idx}, upper index: {upper_idx}")

                if lower_idx == upper_idx:
                    r_interp = r_values[lower_idx]
                    b_interp = b_values[lower_idx]
                    logging.info(f"Exact match found at index {lower_idx}, r_interp: {r_interp}, b_interp: {b_interp}")
                else:
                    r_interp = self.interpolate(temperatures[lower_idx], r_values[lower_idx],
                                                temperatures[upper_idx], r_values[upper_idx], wb)
                    b_interp = self.interpolate(temperatures[lower_idx], b_values[lower_idx],
                                                temperatures[upper_idx], b_values[upper_idx], wb)
                    logging.info(f"Interpolated values for {wb}K - r_interp: {r_interp}, b_interp: {b_interp}")

                self.wb_cg_rb_array[wb] = (round(1/r_interp, 1), round(1/b_interp, 1))
                logging.info(f"Calculated reciprocal cg_rb for {wb}K: {self.wb_cg_rb_array[wb]}")

            logging.info(f"Initialized wb_cg_rb_array: {self.wb_cg_rb_array}")
        except KeyError as e:
            logging.error(f"Key error in initializing wb_cg_rb_array: {e}")
            self.wb_cg_rb_array = {}
        except Exception as e:
            logging.error(f"Failed to initialize wb_cg_rb_array: {e}")
            self.wb_cg_rb_array = {}


    def interpolate(self, x1, y1, x2, y2, x):
        """Perform linear interpolation."""
        logging.debug(f"Interpolating with points ({x1}, {y1}) and ({x2}, {y2}) for x = {x}")
        result = y1 + (y2 - y1) * (x - x1) / (x2 - x1)
        logging.debug(f"Interpolated result: {result}")
        return result

    def set_wb(self, kelvin_temperature=None, direction='next'):
        """Set white balance based on the Kelvin temperature or direction."""
        logging.debug(f"WB steps available: {self.wb_steps}")
        
        if not self.wb_steps:
            logging.error("WB steps are not defined or empty.")
            return  # Exit if wb_steps is empty to prevent further errors
        
        if kelvin_temperature is None:
            current_kelvin = self.redis_controller.get_value(ParameterKey.WB_USER.value)
            if current_kelvin:
                try:
                    current_kelvin = int(current_kelvin)
                    logging.info(f"Parsed current wb_user value: {current_kelvin}")
                except ValueError:
                    current_kelvin = None
                    logging.error(f"Error parsing current wb_user value from Redis: {self.redis_controller.get_value(ParameterKey.WB_USER.value)}")

            found_index = None
            if current_kelvin in self.wb_steps:
                found_index = self.wb_steps.index(current_kelvin)

            if found_index is not None:
                if direction == 'next':
                    next_index = (found_index + 1) % len(self.wb_steps)
                elif direction == 'prev':
                    next_index = (found_index - 1) % len(self.wb_steps)
            else:
                next_index = 0

            kelvin_temperature = self.wb_steps[next_index]
        else:
            closest_temperature = min(self.wb_steps, key=lambda t: abs(t - kelvin_temperature))
            kelvin_temperature = closest_temperature

        cg_rb_value = self.wb_cg_rb_array.get(kelvin_temperature, None)
        if cg_rb_value:
            self.redis_controller.set_value(ParameterKey.CG_RB.value, f"{cg_rb_value[0]},{cg_rb_value[1]}")
            self.redis_controller.set_value(ParameterKey.WB_USER.value, str(kelvin_temperature))
            logging.info(f"Set white balance for {kelvin_temperature}K: {cg_rb_value}")
        else:
            logging.error(f"White balance value not found for {kelvin_temperature}K")

    def inc_wb(self):
        self.set_wb(direction='next')

    def dec_wb(self):
        self.set_wb(direction='prev')
        
    def inc_zoom(self):
        self.set_zoom(direction='next')

    def dec_zoom(self):
        self.set_zoom(direction='prev')

        
    def restart_camera(self, preview_enabled=None):
        self.cinepi.restart(preview_enabled=preview_enabled)
        self._active_storage_recorder_profile = self._current_storage_recorder_profile()

    def restart_cinemate(self):
        """Restart the entire CineMate application."""
        logging.info("Restarting CineMate application")
        python = sys.executable
        os.execl(python, python, *sys.argv)
        

    def set_fps_double(self, value=None):
        target_double_state = not self.fps_double if value is None else value in (1, True)
        was_recording = self._is_recording()

        if target_double_state:
            if not self.fps_double:
                self.fps_saved = self.fps
                self.sensor_mode_saved = self.sensor_mode
                target_fps = self.fps * 2
                target_mode = self._select_resolution_mode_for_fps(target_fps)
                if target_mode != self.sensor_mode:
                    if was_recording:
                        logging.warning(
                            "FPS double needs sensor mode %s, but resolution changes are disabled while recording.",
                            target_mode,
                        )
                        return
                    logging.info(
                        "FPS double requested %.3f fps above current mode limit %s; switching to sensor mode %s.",
                        target_fps,
                        self.fps_max,
                        target_mode,
                    )
                    if not self.set_resolution(target_mode, restart_process=False):
                        return
                    self.fps_max = int(self.redis_controller.get_value(ParameterKey.FPS_MAX.value))
                target_fps = min(target_fps, self.fps_max)
                self.set_fps(target_fps)
        else:
            if self.fps_double:
                if self.sensor_mode_saved != self.sensor_mode:
                    if was_recording:
                        logging.warning(
                            "FPS double restore needs sensor mode %s, but resolution changes are disabled while recording.",
                            self.sensor_mode_saved,
                        )
                        return
                    if not self.set_resolution(self.sensor_mode_saved, restart_process=False):
                        return
                self.set_fps(self.fps_saved)
        
        self.fps_double = target_double_state

        logging.info(f"FPS double mode is {'enabled' if self.fps_double else 'disabled'}, Current FPS: {self.fps}")

    def _ramp_fps(self, target_double_state):
        if target_double_state and not self.fps_double:
            self.fps_saved = self.fps
            target_fps = min(self.fps_temp * 2, self.fps_max)

            while self.fps < target_fps:
                logging.info('Ramping up')
                self.fps += 1
                self.set_fps(self.fps)
                time.sleep(self.ramp_up_speed)
        elif not target_double_state and self.fps_double:
            while self.fps > self.fps_saved:
                logging.info('Ramping down')
                self.fps -= 1
                self.set_fps(self.fps)
                time.sleep(self.ramp_down_speed)

        self.fps_double = target_double_state
        
    def print_settings(self):
        """Display all Redis keys with their current values."""
        print()
        print(f"{'Parameter':<25}Value")
        for key in ParameterKey:
            value = self.redis_controller.get_value(key.value)
            print(f"{key.value:<25}{value}")
        
    def seconds_to_fraction_text(self, exposure_time_seconds):
        if exposure_time_seconds and exposure_time_seconds > 0:
            denominator = 1/exposure_time_seconds
            exposure_fraction_text = "1"+"/"+ str(int(denominator))
            return exposure_fraction_text
        else:
            return 0
    
    def set_filter(self, value=None):
        """Toggle the StarlightEye IR filter via the :class:`IRFilter` helper."""
        if 'imx585' not in str(self.current_sensor):
             return "IR Filter is not supported for this sensor."

        irf = IRFilter(self.redis_controller)
        if value == 1:
            logging.info("Enabling IR Filter")
            irf.set_state(True)
        elif value == 0:
            logging.info("Disabling IR Filter")
            irf.set_state(False)
        else:
            return "Invalid value provided."
         
     # ─── Zoom control ─────────────────────────────────────────────────────────
    def set_zoom(self, value=None, direction="next"):
        """
        Change the live-view digital-zoom factor.

        • Pass an explicit *value* (float) → set that value.
        • Omit *value*                    → step through preview.zoom_steps.
        Use *direction="prev"* to step backwards.
        """
        preview_cfg  = self.settings.get("preview", {})
        zoom_steps   = preview_cfg.get("zoom_steps",   [0.5, 1.0, 1.5, 2.0])
        default_zoom = preview_cfg.get("default_zoom", 1.0)

        # Make sure the default is part of the list *before* we look up indices
        if default_zoom not in zoom_steps:
            zoom_steps.append(default_zoom)
            zoom_steps.sort()

        if value is None:
            # Redis may return None or a bytes/str → coerce to float safely
            raw = self.redis_controller.get_value(ParameterKey.ZOOM.value)
            current = float(raw) if raw is not None else default_zoom

            if current in zoom_steps:
                idx = zoom_steps.index(current)
                step = 1 if direction == "next" else -1
                idx = (idx + step) % len(zoom_steps)
            else:
                idx = 0                      # unknown value → start from first step

            value = zoom_steps[idx]

        # Clamp to the configured range
        value = max(min(float(value), max(zoom_steps)), min(zoom_steps))

        # Persist & notify
        self.redis_controller.set_value(ParameterKey.ZOOM.value, value)
        self.redis_controller.r.publish("cp_controls", ParameterKey.ZOOM.value)

        logging.info("Zoom factor set to %.2f×", value)

    def set_preview_source(self, value=None):
        """Select what the on-camera HDMI monitor shows in a dual-sensor rig.
        Handled live by cinepi-raw's dualHdmiPreview stage — no restart.

        Five sources, cycled in this order when the argument is omitted:
          ``both`` (side-by-side) → ``cam0`` → ``cam1`` →
          ``pip_cam0`` (cam0 main, cam1 inset) → ``pip_cam1`` (cam1 main, cam0
          inset) → back to ``both``.

        • Pass an explicit value to set it directly: ``cam0`` / ``cam1`` /
          ``both`` (``cam0+cam1`` alias) / ``pip_cam0`` (``pip``/``pip0``) /
          ``pip_cam1`` (``pip1``).
        Has no visible effect with a single sensor.
        """
        order = ["both", "cam0", "cam1", "pip_cam0", "pip_cam1"]
        aliases = {
            "both": "both", "cam0+cam1": "both", "2": "both",
            "cam0": "cam0", "0": "cam0", "a": "cam0",
            "cam1": "cam1", "1": "cam1", "b": "cam1",
            "pip_cam0": "pip_cam0", "pip0": "pip_cam0", "pip": "pip_cam0", "pipa": "pip_cam0",
            "pip_cam1": "pip_cam1", "pip1": "pip_cam1", "pipb": "pip_cam1",
        }

        if value is None:
            current = self.redis_controller.get_value(ParameterKey.HDMI_PREVIEW_SOURCE.value)
            current = aliases.get(str(current).strip().lower(), "both")
            target = order[(order.index(current) + 1) % len(order)]
        else:
            key = str(value).strip().lower()
            if key not in aliases:
                logging.warning(
                    "Unknown preview source %r (use both, cam0, cam1, pip_cam0 or pip_cam1)",
                    value,
                )
                return
            target = aliases[key]

        self.redis_controller.set_value(ParameterKey.HDMI_PREVIEW_SOURCE.value, target)
        self.redis_controller.r.publish("cp_controls", ParameterKey.HDMI_PREVIEW_SOURCE.value)
        logging.info("HDMI preview source set to %s", target)

        # Policy B (join-only): if a take is already rolling, a preview switch may
        # ADD sensors to the live record gate but never drop one. Switching to the
        # side-by-side/dual view mid-take makes the second sensor join back-to-back
        # (cinepi-raw re-reads record_cams live in triggerRec()); switching back to
        # a single/pip view leaves the already-recording sensors running.
        if self._is_recording():
            self._extend_record_gate_for_preview(target)



# ────────────────────────── recording helper thread ────────────────────
    def _buffer_fill_percent(self):
        """Return the cinepi-raw RAM buffer fill as a percent (used/total),
        or None when the capacity has not been published yet."""
        try:
            total = int(self.redis_controller.get_value(ParameterKey.BUFFER_SIZE.value) or 0)
            if total <= 0:
                return None
            used = int(self.redis_controller.get_value(ParameterKey.BUFFER.value) or 0)
        except (TypeError, ValueError):
            return None
        return max(0.0, (used / total) * 100.0)

    def _recording_worker(self):
        logging.info("CinePiController worker thread started")
        try:
            while not self._rec_thread_stop.is_set():
                # safety-belt – quit if some other part already stopped recording
                if self.redis_controller.get_value(ParameterKey.IS_RECORDING.value) == "0":
                    break

                # ─── Primary: watch the cinepi-raw RAM frame buffer ──────────
                # This is the real "backlog about to overflow → frames will
                # drop" signal. When it trips we stop so the buffer can flush.
                buffer_pct = self._buffer_fill_percent()
                if buffer_pct is not None and buffer_pct >= self.BUFFER_LIMIT_PERCENT:
                    logging.warning(
                        f"RAM frame buffer {buffer_pct:.0f}% ≥ "
                        f"{self.BUFFER_LIMIT_PERCENT}%! Stopping recording.")
                    self._auto_stop_recording(int(buffer_pct))
                    break

                # ─── Backstop: watch overall system RAM ──────────────────────
                ram_pct = psutil.virtual_memory().percent
                if ram_pct >= self.RAM_LIMIT_PERCENT:
                    logging.warning(f"RAM {ram_pct:.1f}% ≥ {self.RAM_LIMIT_PERCENT}%! "
                                    "Stopping recording.")
                    self._auto_stop_recording(int(ram_pct))
                    break

                time.sleep(0.25)   # 4 Hz polling is plenty
        finally:
            logging.info("CinePiController worker thread exiting")

    def _auto_stop_recording(self, alert_value):
        """Stop recording from inside the watchdog thread.

        We must not call stop_recording() here: it calls stop_recording_worker()
        which joins this very thread (RuntimeError: cannot join current thread).
        Instead replicate the cleanup and flip is_recording directly – the redis
        publish drives the mediator (clears the red write state) and the
        redis_listener (raises is_writing_buf for the green buffer flush), and
        the rec light / GPIO follow automatically.
        """
        # tell the UI / mediator how full we were when we tripped
        self.redis_controller.set_value(ParameterKey.MEMORY_ALERT.value, alert_value)
        self._cancel_timed_recording_stop()
        self._clear_frame_limited_recording_stop()
        # flip the master flag – everything else reacts automatically
        self.redis_controller.set_value(ParameterKey.IS_RECORDING.value, 0)
        logging.info("Stopped recording")

    def start_recording_worker(self):
        if self._rec_thread and self._rec_thread.is_alive():
            return                                          # already running
        self._rec_thread_stop.clear()
        self._rec_thread = threading.Thread(
            target=self._recording_worker, daemon=True)
        self._rec_thread.start()

    def stop_recording_worker(self):
        self._rec_thread_stop.set()
        if self._rec_thread and self._rec_thread is not threading.current_thread():
            self._rec_thread.join(timeout=2)                # be gentle
            self._rec_thread = None
