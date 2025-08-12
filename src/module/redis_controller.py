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
import logging, threading, redis, psutil, time
from enum import Enum
import time, math

# ───────────────────────── parameter keys ────────────────────────────
class ParameterKey(Enum):
    ANAMORPHIC_FACTOR = "anamorphic_factor"
    BIT_DEPTH         = "bit_depth"
    BUFFER            = "buffer"      # number of raw frames in RAM
    BUFFER_SIZE       = "buffer_size"  # RAM pool size for DNG encoder
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
    
    TC_CAM0           = "tc_cam0"
    TC_CAM1           = "tc_cam1"
    
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
    
    ZOOM                = "zoom"  # digital zoom factor for streams 0 & 2
    WRITE_SPEED_TO_DRIVE = "write_speed_to_drive"
    RECORDING_TIME         = "recording_time"      # elapsed-time in seconds   
    RECORDING_TC_REC     = "recording_tc_rec"    # elapsed-time time-code
    RECORDING_TC_TOD   = "recording_time_tod"    # time-of-day time-code


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

    def __init__(self, host="localhost", port=6379, db=0, channel="cp_controls", conform_frame_rate: int = 24):
        self.r      = redis.StrictRedis(host=host, port=port, db=db)
        self.ps     = self.r.pubsub(); self.ps.subscribe(channel)
        self.lock   = threading.Lock()
        self.cache  = {}
        self.local_updates: set[str] = set()

        self.redis_parameter_changed = Event()

        self.conform_frame_rate = conform_frame_rate
        self.recording_start_time: float | None = None
        self._rec_timer_stop = threading.Event()
        self._rec_timer_thread: threading.Thread | None = None

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

            if key == ParameterKey.REC.value:
                if value == "1":
                    self._start_recording_timer()
                else:
                    self._stop_recording_timer()
            # notify subscribers – no log spam here
            if key != ParameterKey.FPS_ACTUAL.value:
                self.redis_parameter_changed.emit({"key": key, "value": value})

    # ───────────────────────── public helpers ───────────────────────
    def get_value(self, key, default=None):
        with self.lock:
            return self.cache.get(key, default)

        # ────────────────────────── public helpers ───────────────────────
    def set_value(self, key, value):
        """Write key, publish, update cache, emit consolidated log output."""
        if value is None:
            logging.warning(f"Attempted to set Redis key '{key}' to None. Ignoring.")
            return

        key_name = key.value if isinstance(key, ParameterKey) else str(key)

        # ─── Redis write / publish / cache ───────────────────────────
        with self.lock:
            if str(self.cache.get(key_name)) == str(value):
                return                             # unchanged – nothing to do
            self.r.set(key_name, value)
            self.r.publish("cp_controls", key_name)
            self.cache[key_name] = str(value)
            self.local_updates.add(key_name)

        # ─── enhanced logging rules ─────────────────────────────────
        if key_name == ParameterKey.FRAMECOUNT.value:
            # Consolidated once-per-frame entry
            rec_secs = self.cache.get(ParameterKey.RECORDING_TIME.value, "0")
            rec_tc   = self.cache.get(ParameterKey.RECORDING_TC_REC.value, "00:00:00:00")
            tod_tc   = self.cache.get(ParameterKey.RECORDING_TC_TOD.value, "00:00:00:00")
            cam0_tc  = self.cache.get(ParameterKey.TC_CAM0.value,          "—")
            cam1_tc  = self.cache.get(ParameterKey.TC_CAM1.value,          "—")

            # format seconds nicely (fallback to raw string if not numeric)
            try:
                rec_secs_fmt = f"{float(rec_secs):.3f}"
            except ValueError:
                rec_secs_fmt = rec_secs

            logging.info(
                f"Frame {value} ┃rec={rec_secs_fmt}s "
                f"┃tc_rec={rec_tc} ┃tc_tod={tod_tc} "
                f"┃cam0={cam0_tc} ┃cam1={cam1_tc}"
            )

        elif key_name.startswith("last_dng_cam"):
            ram = psutil.virtual_memory().percent
            logging.info(
                f"Changed value: {key_name} = {value} ┃RAM: {ram:.0f}%"
            )

        elif key_name in (
            ParameterKey.RECORDING_TIME.value,
            ParameterKey.RECORDING_TC_REC.value,
            ParameterKey.RECORDING_TC_TOD.value,
            ParameterKey.TC_CAM0.value,
            ParameterKey.TC_CAM1.value,
            ParameterKey.FPS_ACTUAL.value,
            ParameterKey.BUFFER.value,
        ):
            # Suppress high-frequency keys
            pass

        else:
            logging.info(f"Changed value: {key_name} = {value}")

        # ─── immediate local notification to subscribers ─────────────
        self.redis_parameter_changed.emit({"key": key_name, "value": str(value)})



        # ─────────────────────── time-code helpers ────────────────────────
    def nanoseconds_to_timecode(self, ns: int, frame_rate: float | None = None) -> str:
        """
        Convert an **epoch** nanosecond timestamp to an SMPTE hh:mm:ss:ff TOD code.
        """
        # 1.  Epoch seconds (float)
        epoch_sec  = ns / 1_000_000_000

        # 2.  Local time-of-day → seconds since midnight (fractional!)
        lt         = time.localtime(epoch_sec)
        tod_sec    = (
            lt.tm_hour * 3600 +
            lt.tm_min  * 60   +
            lt.tm_sec        +
            (epoch_sec - math.floor(epoch_sec))    # sub-second fraction → frames
        )

        # 3.  Wrap exactly every 24 h so hh runs 00…23
        tod_sec %= 86_400

        # 4.  Format with existing helper
        return self._format_timecode(tod_sec, frame_rate)    
        
    def _format_timecode(
        self,
        seconds_total: float,
        frame_rate: float | None = None
    ) -> str:
        """
        Return SMPTE time-code hh:mm:ss:ff for any positive offset in seconds.
        """
        rate = frame_rate if frame_rate is not None else self.conform_frame_rate
        rate = int(round(rate))               # ensure integer fps

        total_frames  = int(round(seconds_total * rate))
        frames        = total_frames % rate               # 0 … rate-1  (int)
        whole_seconds = total_frames // rate

        secs   =  whole_seconds         % 60
        mins   = (whole_seconds // 60)  % 60
        hours  =  whole_seconds // 3600

        # now every field is guaranteed to be an int → safe with :02d
        return f"{hours:02d}:{mins:02d}:{secs:02d}:{frames:02d}"

    def _current_tod_timecode(self) -> str:
        """Time-of-day time-code (localtime) at *conform_frame_rate*."""
        now                  = time.time()
        lt                   = time.localtime(now)
        since_midnight_float = (
            lt.tm_hour * 3600
            + lt.tm_min  * 60
            + lt.tm_sec
            + (now - int(now))                 # fractional part for frames
        )
        return self._format_timecode(since_midnight_float)


    # ─────────────────────── recording timer loop ─────────────────────
    def _run_recording_timer(self) -> None:
        while not self._rec_timer_stop.is_set():
            if self.recording_start_time is None:
                break

            # elapsed time, in seconds (float)
            elapsed = time.time() - self.recording_start_time
            self.set_value(ParameterKey.RECORDING_TIME, elapsed)

            # elapsed time-code
            self.set_value(
                ParameterKey.RECORDING_TC_REC,
                self._format_timecode(elapsed)
            )

            # time-of-day time-code
            self.set_value(
                ParameterKey.RECORDING_TC_TOD,
                self._current_tod_timecode()
            )

            # wait just long enough to hit every frame edge
            self._rec_timer_stop.wait(1 / self.conform_frame_rate)

    # ─────────────────────── recording timer control ──────────────────
    def _start_recording_timer(self) -> None:
        self._stop_recording_timer()                 # safety first
        self.recording_start_time = time.time()

        # prime the three keys with deterministic values
        self.set_value(ParameterKey.RECORDING_TIME,      0.0)
        self.set_value(ParameterKey.RECORDING_TC_REC,    "00:00:00:00")
        self.set_value(ParameterKey.RECORDING_TC_TOD,    self._current_tod_timecode())

        self._rec_timer_stop.clear()
        self._rec_timer_thread = threading.Thread(
            target=self._run_recording_timer,
            daemon=True
        )
        self._rec_timer_thread.start()

    def _stop_recording_timer(self) -> None:
        self._rec_timer_stop.set()
        if self._rec_timer_thread and self._rec_timer_thread.is_alive():
            self._rec_timer_thread.join(timeout=0.5)
        self._rec_timer_thread = None


    # optional helper -------------------------------------------------
    def stop_listener(self):
        self.ps.unsubscribe(); self.ps.close(); self._thread.join(timeout=1)
