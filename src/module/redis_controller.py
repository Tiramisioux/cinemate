# redis_controller.py – enhanced logging, suppress standalone BUFFER lines (2025‑06‑25)
"""Centralised Redis access + pub‑sub relay for CinePi.

What’s new in this revision
---------------------------
* Stand‑alone `buffer` updates are **never** logged anymore – independent
  of whether the caller uses the Enum or the raw string key.
* The “BUFFER+RAM” suffix still accompanies every `last_dng_cam*` line so
  you keep full context while the camera is writing.
"""

from __future__ import annotations
import logging, threading, redis, psutil
from enum import Enum

# ───────────────────────── parameter keys ────────────────────────────
class ParameterKey(Enum):
    ANAMORPHIC_FACTOR = "anamorphic_factor"
    BIT_DEPTH         = "bit_depth"
    BUFFER            = "buffer"
    CAM_INIT          = "cam_init"
    CAMERAS           = "cameras"
    CG_RB             = "cg_rb"
    FILE_SIZE         = "file_size"
    FPS               = "fps"
    FPS_ACTUAL        = "fps_actual"
    FPS_LAST          = "fps_last"
    FPS_MAX           = "fps_max"
    FPS_USER          = "fps_user"
    FRAMECOUNT        = "framecount"
    GUI_LAYOUT        = "gui_layout"
    HEIGHT            = "height"
    IR_FILTER         = "ir_filter"
    IS_BUFFERING      = "is_buffering"
    IS_MOUNTED        = "is_mounted"
    IS_RECORDING      = "is_recording"
    IS_WRITING        = "is_writing"
    IS_WRITING_BUF    = "is_writing_buf"
    ISO               = "iso"
    LORES_HEIGHT      = "lores_height"
    LORES_WIDTH       = "lores_width"
    PI_MODEL          = "pi_model"
    REC               = "rec"
    SENSOR            = "sensor"
    SENSOR_MODE       = "sensor_mode"
    SHUTTER_A         = "shutter_a"

    SPACE_LEFT        = "space_left"
    STORAGE_TYPE      = "storage_type"
    TRIGGER_MODE      = "trigger_mode"
    WB                = "wb"
    WB_USER           = "wb_user"
    WIDTH             = "width"
    MEMORY_ALERT      = "memory_alert"
    SHUTTER_A_SYNC_MODE = 'shutter_a_sync_mode'
    SHUTTER_A_NOM       = 'shutter_angle_nom'
    SHUTTER_A_ACTUAL    = 'shutter_angle_actual'
    SHUTTER_A_TRANSIENT = 'shutter_angle_transient'
    EXPOSURE_TIME       = 'exposure_time'
    LAST_DNG_CAM1       = "last_dng_cam1"
    LAST_DNG_CAM0       = "last_dng_cam0"


# ────────────────────────── tiny pub‑sub helper ──────────────────────
class Event:
    def __init__(self):
        self._handlers = []
    def subscribe(self, fn):
        self._handlers.append(fn)
    def emit(self, data=None):
        for fn in self._handlers:
            fn(data)

# ────────────────────────── main controller class ────────────────────
class RedisController:

    def __init__(self, host="localhost", port=6379, db=0, channel="cp_controls"):
        self.r      = redis.StrictRedis(host=host, port=port, db=db)
        self.ps     = self.r.pubsub(); self.ps.subscribe(channel)
        self.lock   = threading.Lock()
        self.cache  = {}
        self.local_updates: set[str] = set()

        self.redis_parameter_changed = Event()

        self._prime_cache()
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    # ─────────────────────── initial cache fill ─────────────────────
    def _prime_cache(self):
        for key in self.r.keys("*"):
            val = self.r.get(key) or b""
            self.cache[key.decode()] = val.decode(errors="replace")
        logging.info("RedisController cache primed with %d keys", len(self.cache))

    # ─────────────────────── background listener ────────────────────
    def _listen(self):
        for msg in self.ps.listen():
            if msg["type"] != "message":
                continue
            key = msg["data"].decode()
            with self.lock:
                # suppress echo of own writes
                if key in self.local_updates:
                    self.local_updates.remove(key)
                value = (self.r.get(key) or b"").decode()
                self.cache[key] = value
            # notify subscribers – no log spam here
            if key != ParameterKey.FPS_ACTUAL.value:
                self.redis_parameter_changed.emit({"key": key, "value": value})

    # ───────────────────────── public helpers ───────────────────────
    def get_value(self, key, default=None):
        with self.lock:
            return self.cache.get(key, default)

    def set_value(self, key, value):
        """Write key, publish, update cache, emit single consolidated log."""
        # normalise key to plain string for comparisons / logging
        key_name = key.value if isinstance(key, ParameterKey) else str(key)

        with self.lock:
            if str(self.cache.get(key_name)) == str(value):
                return  # unchanged
            self.r.set(key_name, value)
            self.r.publish("cp_controls", key_name)
            self.cache[key_name] = str(value)
            self.local_updates.add(key_name)

        # ─── enhanced logging ───────────────────────────────────────
        if key_name.startswith("last_dng_cam"):
            ram = psutil.virtual_memory().percent
            logging.info(
                f"Changed value: {key_name} = {value} ┃RAM: {ram:.0f}%"
            )
        elif key_name not in (ParameterKey.FPS_ACTUAL.value, ParameterKey.BUFFER.value):
            # skip standalone BUFFER, & FPS_ACTUAL noise
            logging.info(f"Changed value: {key_name} = {value}")

        # immediate local notification
        self.redis_parameter_changed.emit({"key": key_name, "value": str(value)})

    # optional helper -------------------------------------------------
    def stop_listener(self):
        self.ps.unsubscribe(); self.ps.close(); self._thread.join(timeout=1)
