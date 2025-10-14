"""Timekeeper module for keeping frame count aligned with target FPS.
This helper monitors the recorded frame count in Redis during a take and
compares it to the number of frames that *should* have been captured based on
elapsed wall-clock time and the user-selected frame rate.  When drift is
observed it applies gentle corrections to the active FPS so that the running
frame count stays in sync with expectations.
"""
from __future__ import annotations
import logging
import threading
import time
from typing import Optional
from module.redis_controller import ParameterKey
class Timekeeper:
    """Background helper that nudges the recording FPS toward the target."""
    def __init__(
        self,
        redis_controller,
        cinepi_controller,
        *,
        check_interval: float = 0.5,
        correction_gain: float = 0.22,
        max_adjustment: float = 0.25,
        frame_tolerance: float = 0.75,
        max_deviation: float = 0.3,
        max_interval: float = 2.5,
    ) -> None:
        self.redis_controller = redis_controller
        self.cinepi_controller = cinepi_controller
        self.check_interval = max(0.1, check_interval)
        self.correction_gain = max(0.0, correction_gain)
        self.max_adjustment = max(0.0, max_adjustment)
        self.frame_tolerance = max(0.0, frame_tolerance)
        self.max_deviation = max(0.0, max_deviation)
        self.max_interval = max(self.check_interval, max_interval)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="Timekeeper", daemon=True)
        self._recording_lock = threading.Lock()
        self._recording_active = False
        self._take_start_time: Optional[float] = None
        self._take_start_frame: Optional[int] = None
        self._last_sample_time: Optional[float] = None
        self._last_framecount: Optional[int] = None
        # React to Redis events (recording state + fps adjustments)
        self.redis_controller.redis_parameter_changed.subscribe(self._handle_redis_event)
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the monitoring thread."""
        if self._thread.is_alive():
            return
        # Prime the state if recording is already active when we boot.
        current_rec = self.redis_controller.get_value(ParameterKey.REC.value)
        if self._is_truthy(current_rec):
            self._set_recording_active(True)
        logging.info("Timekeeper module started")
        self._thread.start()
    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Stop the monitoring thread."""
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logging.info("Timekeeper module stopped")
    # ------------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop_event.is_set():
            if not self._is_recording():
                self._stop_event.wait(self.check_interval)
                continue
            # Wait for the sampling interval or until we are asked to stop.
            if self._stop_event.wait(self.check_interval):
                break
            try:
                self._apply_correction()
            except Exception:  # pragma: no cover - defensive guard
                logging.exception("Timekeeper adjustment failed")
    # ------------------------------------------------------------------
    def _handle_redis_event(self, data: dict) -> None:
        key = data.get("key")
        if key == ParameterKey.REC.value:
            self._set_recording_active(self._is_truthy(data.get("value")))
        elif key in (ParameterKey.FPS.value, ParameterKey.FPS_USER.value):
            # Reset baselines whenever the target fps changes to avoid stale drift
            self._arm_take()
    # ------------------------------------------------------------------
    def _set_recording_active(self, active: bool) -> None:
        with self._recording_lock:
            self._recording_active = active
            if not active:
                self._take_start_time = None
                self._take_start_frame = None
                self._last_sample_time = None
                self._last_framecount = None
        if active:
            logging.debug("Timekeeper armed for active take")
            self._arm_take()
        else:
            logging.debug("Timekeeper idling – recording inactive")
            self._restore_user_fps()
    # ------------------------------------------------------------------
    def _is_recording(self) -> bool:
        with self._recording_lock:
            return self._recording_active
    # ------------------------------------------------------------------
    def _arm_take(self) -> None:
        if not self._is_recording():
            return
        framecount = self._get_framecount()
        timestamp = time.monotonic()
        with self._recording_lock:
            self._take_start_time = timestamp
            self._take_start_frame = framecount
            self._last_framecount = framecount
            self._last_sample_time = timestamp
        logging.debug("Timekeeper baseline reset at frame %s", framecount)
    # ------------------------------------------------------------------
    def _apply_correction(self) -> None:
        if self._user_is_changing_fps():
            logging.debug("Skipping timekeeper adjustment while user changes FPS")
            self._arm_take()
            return
        user_fps = self._get_user_fps()
        if user_fps is None or user_fps <= 0:
            logging.debug("Timekeeper has no valid user FPS; skipping adjustment")
            return
        framecount = self._get_framecount()
        now = time.monotonic()
        with self._recording_lock:
            start_time = self._take_start_time
            start_frame = self._take_start_frame
            last_time = self._last_sample_time
        if start_time is None or start_frame is None:
            self._arm_take()
            return
        if framecount < start_frame:
            logging.debug("Framecount reset detected; re-arming timekeeper")
            self._arm_take()
            return
        elapsed = now - start_time
        if elapsed <= 0:
            return
        if last_time is not None and (now - last_time) > self.max_interval:
            logging.debug(
                "Timekeeper interval too large (%.2fs); resetting baseline", now - last_time
            )
            self._arm_take()
            return
        actual_frames = framecount - start_frame
        expected_frames = user_fps * elapsed
        error_frames = expected_frames - actual_frames
        if abs(error_frames) <= self.frame_tolerance:
            with self._recording_lock:
                self._last_sample_time = now
                self._last_framecount = framecount
            return
        # Convert the accumulated frame error into an FPS delta.  The longer the
        # take has been running, the gentler the correction becomes so that we
        # nudge the system back on track instead of oscillating.
        error_rate = error_frames / max(elapsed, self.check_interval)
        adjustment = error_rate * self.correction_gain
        adjustment = max(-self.max_adjustment, min(self.max_adjustment, adjustment))
        target_fps = user_fps + adjustment
        target_fps = max(user_fps - self.max_deviation, min(user_fps + self.max_deviation, target_fps))
        fps_max = self._safe_float(self.redis_controller.get_value(ParameterKey.FPS_MAX.value))
        if fps_max is not None:
            target_fps = min(target_fps, fps_max)
        target_fps = max(1.0, target_fps)
        current_fps = self._safe_float(self.redis_controller.get_value(ParameterKey.FPS.value))
        if current_fps is None:
            current_fps = target_fps
        if abs(target_fps - current_fps) < 1e-3:
            logging.debug(
                "Timekeeper adjustment %.4ffps too small; skipping",
                target_fps - current_fps,
            )
            with self._recording_lock:
                self._last_sample_time = now
                self._last_framecount = framecount
            return
        logging.info(
            "Timekeeper correcting FPS from %.4f to %.4f (error %.3f frames over %.2fs)",
            current_fps,
            target_fps,
            error_frames,
            elapsed,
        )
        self.cinepi_controller.update_fps(round(target_fps, 6))
        with self._recording_lock:
            self._last_sample_time = now
            self._last_framecount = framecount
    # ------------------------------------------------------------------
    def _restore_user_fps(self) -> None:
        user_fps = self._safe_float(self.redis_controller.get_value(ParameterKey.FPS_USER.value))
        if user_fps is None or user_fps <= 0:
            return
        current_fps = self._safe_float(self.redis_controller.get_value(ParameterKey.FPS.value))
        if current_fps is None:
            current_fps = user_fps
        if abs(current_fps - user_fps) < 1e-3:
            return
        logging.info(
            "Timekeeper restoring FPS to user target %.4f after take (was %.4f)",
            user_fps,
            current_fps,
        )
        self.cinepi_controller.update_fps(round(user_fps, 6))
    # ------------------------------------------------------------------
    def _get_framecount(self) -> int:
        value = self.redis_controller.get_value(ParameterKey.FRAMECOUNT.value, 0)
        try:
            return int(float(value))
        except (TypeError, ValueError):
            logging.debug("Invalid framecount value %r – defaulting to 0", value)
            return 0
    # ------------------------------------------------------------------
    def _get_user_fps(self) -> Optional[float]:
        user_value = self.redis_controller.get_value(ParameterKey.FPS_USER.value)
        fps = self._safe_float(user_value)
        if fps is None:
            fps = self._safe_float(self.redis_controller.get_value(ParameterKey.FPS.value))
        return fps
    # ------------------------------------------------------------------
    def _user_is_changing_fps(self) -> bool:
        flag = self.redis_controller.get_value("user_changing_fps", "0")
        return self._is_truthy(flag)
    # ------------------------------------------------------------------
    @staticmethod
    def _is_truthy(value) -> bool:
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip() not in {"", "0", "false", "False"}
        return bool(value)
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_float(value) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            logging.debug("Invalid float value %r", value)
            return None
