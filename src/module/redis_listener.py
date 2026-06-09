import redis
import logging
import threading
import datetime
import json
from collections import deque
from module.redis_controller import ParameterKey

import os
import re
import time
import math
import statistics

class RedisListener:
    def __init__(
        self,
        redis_controller,
        ssd_monitor,
        framerate_callback=None,
        host='localhost',
        port=6379,
        db=0,
        *,
        live_sync_warning_tolerance_frames: int | float = 5,
        live_sync_startup_guard_frames: int | float = 10,
        final_sync_analysis_tolerance_frames: int | float = 1,
        tc_drop_jitter_tolerance_frames: int | float = 1,
    ):
        self.redis_client = redis.StrictRedis(host=host, port=port, db=db)
        
        self.pubsub_stats = self.redis_client.pubsub()
        self.pubsub_controls = self.redis_client.pubsub()
        self.channel_name_stats = "cp_stats"
        self.channel_name_controls = "cp_controls"

        self.stdev_threshold = 2.0
        self.lock = threading.Lock()
        self.is_recording = False
        self.framerate_values = []
        self.sensor_timestamps = deque(maxlen=100)
        
        self.recording_start_time = None
        self.recording_end_time = None
        
        self.redis_controller = redis_controller
        self.ssd_monitor = ssd_monitor
        self.framerate_callback = framerate_callback

        self.framerate = float(self.redis_controller.get_value('fps_actual', 0))
        self.framecount_last_update_time = datetime.datetime.now()
        self.framecount = 0
        self.frame_count = 0
        self.consecutive_non_increasing_counts = 0
        self.non_increasing_count_threshold = 3  # Allow 3 non-increasing counts before declaring frame count not increasing

        self.set_frame_count_increase_tolerance()
        
        self.bufferSize = 0
        self.colorTemp = 0
        self.focus = 0
        self.framecount = 0
        self.redis_controller.set_value('framecount', 0)
        
        self.last_non_increasing_time = None
        self.stable_hold_seconds = 0.1 
        
        self.last_is_recording_value = self.redis_controller.get_value('is_recording')
        
        self.allow_initial_zero = False
        
        self.sensor_counts = {}          # { 'CAM0': 0, 'CAM1': 0, … }
        self.all_sensors_ready = False       # True if all sensors are ready, False otherwise

        self.last_rise_time = None          # when frameCount last increased
        self.rec_hold_seconds = 0.3         # how long frameCount must stay flat before rec=0


        self.drop_frame = False
        self.drop_frame_timer = None
        self.drop_frame_count_current_take = 0
        self.drop_frame_relay_timer = None
        self.tc_frame_count: int | None = None
        self.hw_dropped_frames: int | None = None  # unbiased count from cinepi-raw droppedFrames
        self.hw_write_failures: int | None = None  # disk-write failures from cinepi-raw writeFailures
        self.write_failure_count_current_take = 0
        self.frames_off_sync_latched_current_take = False
        self.live_sync_suppressed_current_take = False
        self.live_sync_warning_tolerance_frames = self._coerce_frame_tolerance(
            live_sync_warning_tolerance_frames,
            default=2,
        )
        self.final_sync_analysis_tolerance_frames = self._coerce_frame_tolerance(
            final_sync_analysis_tolerance_frames,
            default=1,
        )
        # The cinepi-raw timecode counter (tcFrameCount) advances by rounding
        # each inter-frame µs delta with a +1 floor, so it can lead frameCount
        # by ~1 slot from ordinary timing jitter (a late frame followed by an
        # early one) without any frame actually being lost. Ignore a lead at or
        # below this tolerance so jitter does not raise a phantom drop alert.
        self.tc_drop_jitter_tolerance_frames = self._coerce_frame_tolerance(
            tc_drop_jitter_tolerance_frames,
            default=1,
        )
        # How many expected frames must have elapsed before the live sync check
        # activates. Covers cinepi-raw startup latency after is_recording=1.
        # At 25fps, 10 frames = 400ms. Configurable via live_sync_startup_guard_frames.
        self.live_sync_startup_guard_frames = max(1.0, float(live_sync_startup_guard_frames))


        self.cinepi_running = True

        self.framecount_changing = False
        self.last_framecount = 0
        self.last_framecount_check_time = datetime.datetime.now()
        self.framecount_check_interval = 1.0  # Default to 1 second, will be updated based on FPS

        self.redis_controller.set_value('rec', "0")

        self.active_sensor_labels: set[str] = set()
        self.redis_controller.set_value(ParameterKey.FRAMES_IN_SYNC.value, 1)
        self.redis_controller.set_value(ParameterKey.FPS_CORRECTION_SUGGESTION.value, 1.0)
        self.redis_controller.set_value(ParameterKey.DROP_FRAME.value, 0)
        self.redis_controller.set_value(ParameterKey.DROP_FRAME_DURING_LAST_TAKE.value, 0)
        self.redis_controller.set_value(ParameterKey.DROP_FRAME_COUNT.value, 0)
        self.redis_controller.set_value(ParameterKey.DROP_FRAME_RELAY.value, 0)
        
        self.max_fps_adjustment = 0.1  # Maximum adjustment per iteration
        self.min_fps_adjustment = 0.0001  # Minimum adjustment increment
        self.fps_adjustment_interval = 1.0  # Adjust every 1 second
        self.last_fps_adjustment_time = datetime.datetime.now()
        
        # ──  USER FPS TWEAK  ────────────────────────────────────────────────
        self.user_changing_fps = False          # True while the UI slider is moving
        self.last_fps_value     = float(self.redis_controller.get_value("fps") or 0)
        self.fps_change_timer   = None          # debounce timer


        self.current_framerate = None

        self.last_timestamp_single = None
        self.last_timestamp_cam0 = None
        self.last_timestamp_cam1 = None

        self.fps_at_rec_start = None
        self.fps_correction_factor_at_rec_start: float | None = None
        self.fps_timeline: list[tuple[datetime.datetime, float]] = []
        self.final_analysis_thread = None
        self.final_analysis_lock = threading.Lock()
        self.final_analysis_pending = False
        self.final_analysis_timeout_s = 30.0
        self.final_analysis_poll_s = 0.2
        self.take_sequence = 0
        self.final_analysis_sequence: int | None = None

        self.recording_was_preroll = False
        self.frame_limit_target_slots: int | None = None
        self.frame_limit_requested_slots: int | None = None
        self.frame_limit_anchor_time: datetime.datetime | None = None
        self.frame_limit_stop_requested = False
        self.awaiting_fresh_framecount = False
        self.initial_framecount_guard_seconds = 0.25
        self.fresh_framecount_guard_start_time: datetime.datetime | None = None
        self.recording_stop_callback = None
        self.raw_framecount_last: int | None = None
        self.framecount_segment_base = 0
        self.recording_reconfigure_pending = False
        self.recording_reconfigure_requested_at: datetime.datetime | None = None
        self.recording_reconfigure_grace_until: datetime.datetime | None = None
        self.recording_pause_intervals: list[tuple[datetime.datetime, datetime.datetime]] = []
        self.last_stats_message_time: datetime.datetime | None = None
        self.recording_folder_hints: list[str] = []
        self.recording_folder_hint_set: set[str] = set()


        self.start_listeners()

    def set_recording_stop_callback(self, callback) -> None:
        self.recording_stop_callback = callback

    def _filter_initial_recording_framecount(self, new_count: int | None) -> int | None:
        if new_count is None:
            return None

        try:
            normalized = int(new_count)
        except (TypeError, ValueError):
            return None

        if not self.awaiting_fresh_framecount:
            return normalized

        if normalized == 0:
            return 0

        age_seconds = 0.0
        guard_start_time = self.fresh_framecount_guard_start_time or self.recording_start_time
        if guard_start_time is not None:
            age_seconds = (datetime.datetime.now() - guard_start_time).total_seconds()

        fps_expected = self._determine_expected_fps()
        if fps_expected is not None and fps_expected > 0:
            max_plausible = max(2, int(math.ceil(age_seconds * fps_expected)) + 3)
        else:
            max_plausible = 1 if age_seconds < self.initial_framecount_guard_seconds else normalized

        # Right after is_recording=1, cinepi-raw can still publish one stale
        # frame counter from the previous take. Ignore values that are too far
        # ahead of what the new take could plausibly have produced.
        if normalized > max_plausible:
            logging.debug(
                "Ignoring stale initial framecount %d %.3fs after record start (max plausible %d)",
                normalized,
                age_seconds,
                max_plausible,
            )
            return None

        self.awaiting_fresh_framecount = False
        self.fresh_framecount_guard_start_time = None
        return normalized

    def disarm_frame_limited_stop(self) -> None:
        self.frame_limit_target_slots = None
        self.frame_limit_requested_slots = None
        self.frame_limit_stop_requested = False

    def arm_frame_limited_stop(self, frames_target: int, *, fresh_take: bool = False) -> None:
        if frames_target <= 0:
            raise ValueError("Frame-limited recording target must be greater than zero.")

        if fresh_take:
            baseline_slots = 0
            self.frame_limit_anchor_time = None
            self.frame_count = 0
            self.framecount = 0
            self.last_framecount = 0
            self.last_rise_time = None
            self.framecount_changing = False
            self.awaiting_fresh_framecount = True
            self.fresh_framecount_guard_start_time = datetime.datetime.now()
        else:
            baseline_slots = self._current_expected_frame_slots()
            if baseline_slots is None:
                baseline_slots = 0

        # By the time the Redis stop flag propagates, the capture/encode pipeline
        # has already accepted roughly two more frame slots. Stop a small
        # number of frame slots early so the on-disk DNG count lands on the
        # requested value.
        stop_lead_slots = min(2, max(frames_target - 1, 0))
        effective_slots = max(frames_target - stop_lead_slots, 1)

        self.frame_limit_requested_slots = baseline_slots + frames_target
        self.frame_limit_target_slots = baseline_slots + effective_slots
        self.frame_limit_stop_requested = False

        logging.info(
            "Armed exact frame-limited stop: %d additional frame slots "
            "(threshold slot %d, pipeline lead compensation %d).",
            frames_target,
            self.frame_limit_target_slots,
            stop_lead_slots,
        )

        self._maybe_stop_for_frame_limit()

    def start_listeners(self):
        self.pubsub_stats.subscribe(self.channel_name_stats)
        self.pubsub_controls.subscribe(self.channel_name_controls)

        self.listener_thread_stats = threading.Thread(target=self.listen_stats)
        self.listener_thread_stats.daemon = True
        self.listener_thread_stats.start()

        self.listener_thread_controls = threading.Thread(target=self.listen_controls)
        self.listener_thread_controls.daemon = True
        self.listener_thread_controls.start()

    @staticmethod
    def _coerce_float(value) -> float | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="ignore")
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @classmethod
    def _coerce_int(cls, value) -> int | None:
        number = cls._coerce_float(value)
        return int(number) if number is not None else None

    @classmethod
    def _coerce_frame_tolerance(cls, value, *, default: int | float) -> float:
        number = cls._coerce_float(value)
        if number is None:
            number = float(default)
        return max(0.0, number)

    @staticmethod
    def _seconds_between(start: datetime.datetime, end: datetime.datetime) -> float:
        if end < start:
            return 0.0
        return (end - start).total_seconds()

    def _pause_intervals_for_range(
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
    ) -> list[tuple[datetime.datetime, datetime.datetime]]:
        self._expire_recording_reconfigure_if_needed(end_time)
        intervals = list(self.recording_pause_intervals)
        if self.recording_reconfigure_pending:
            pause_start = (
                self.last_stats_message_time
                or self.recording_reconfigure_requested_at
                or start_time
            )
            intervals.append((pause_start, end_time))

        clipped: list[tuple[datetime.datetime, datetime.datetime]] = []
        for pause_start, pause_end in intervals:
            if pause_end <= start_time or pause_start >= end_time:
                continue
            clipped.append((max(pause_start, start_time), min(pause_end, end_time)))
        return clipped

    def _active_seconds_between(
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
    ) -> float:
        if end_time <= start_time:
            return 0.0

        active_seconds = self._seconds_between(start_time, end_time)
        for pause_start, pause_end in self._pause_intervals_for_range(start_time, end_time):
            active_seconds -= self._seconds_between(pause_start, pause_end)
        return max(0.0, active_seconds)

    def _recording_reconfigure_grace_active(
        self,
        now: datetime.datetime | None = None,
    ) -> bool:
        now = now or datetime.datetime.now()
        self._expire_recording_reconfigure_if_needed(now)
        if self.recording_reconfigure_pending:
            return True
        if self.recording_reconfigure_grace_until is None:
            return False
        return now <= self.recording_reconfigure_grace_until

    def _expire_recording_reconfigure_if_needed(self, now: datetime.datetime) -> None:
        if not self.recording_reconfigure_pending:
            return
        if self.recording_reconfigure_grace_until is None:
            return
        if now <= self.recording_reconfigure_grace_until:
            return

        logging.warning(
            "Recording reconfigure did not produce a framecount reset within the grace window; "
            "resuming frame sync/drop warnings."
        )
        self.recording_reconfigure_pending = False
        self.recording_reconfigure_requested_at = None
        self.recording_reconfigure_grace_until = None

    def _begin_recording_reconfigure(self) -> None:
        if not self.is_recording:
            return

        now = datetime.datetime.now()
        if not self.recording_reconfigure_pending:
            self.recording_reconfigure_requested_at = now
            logging.info("Recording resolution reconfigure started; suspending frame sync/drop warnings.")
        self.recording_reconfigure_pending = True
        self.recording_reconfigure_grace_until = now + datetime.timedelta(seconds=5)
        self.sensor_timestamps.clear()
        self.current_framerate = None

    def _finish_recording_reconfigure_split(self, raw_count: int, now: datetime.datetime) -> None:
        previous_raw = self.raw_framecount_last
        previous_logical = int(self.framecount or 0)
        previous_segment_end = self.framecount_segment_base + max(previous_raw or 0, 0)
        self.framecount_segment_base = max(
            self.framecount_segment_base,
            previous_logical,
            previous_segment_end,
        )

        pause_start = (
            self.last_stats_message_time
            or self.recording_reconfigure_requested_at
            or now
        )
        if pause_start < now:
            self.recording_pause_intervals.append((pause_start, now))

        self.recording_reconfigure_pending = False
        self.recording_reconfigure_requested_at = None
        self.recording_reconfigure_grace_until = now + datetime.timedelta(seconds=1)
        self.sensor_timestamps.clear()
        self.current_framerate = None
        self.last_framecount = self.framecount_segment_base + raw_count
        logging.info(
            "Recording continued in a new clip segment: raw framecount reset from %s to %s, "
            "logical framecount continues at %s.",
            previous_raw,
            raw_count,
            self.last_framecount,
        )

    def _logical_framecount_from_raw(
        self,
        raw_count: int | None,
        now: datetime.datetime,
    ) -> int | None:
        if raw_count is None:
            return None

        try:
            raw_count = int(raw_count)
        except (TypeError, ValueError):
            return None

        if not self.is_recording:
            self.raw_framecount_last = raw_count
            return raw_count

        if (
            self.recording_reconfigure_pending
            and self.raw_framecount_last is not None
            and (raw_count == 0 or raw_count < self.raw_framecount_last)
        ):
            self._finish_recording_reconfigure_split(raw_count, now)

        logical_count = self.framecount_segment_base + raw_count
        self.raw_framecount_last = raw_count
        return logical_count

    @staticmethod
    def _sensor_label_from_recording_label(label: str | None) -> str:
        text = str(label or "")
        match = re.search(r'(cam\d+)$', text, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return "cam0"

    def _remember_recording_folder_from_dng(self, dng_path: str | None) -> None:
        if not self.is_recording or not dng_path:
            return
        text = str(dng_path)
        if text.lower() == "none":
            return
        folder = os.path.dirname(text)
        if not folder:
            return
        key = os.path.abspath(folder) if os.path.isabs(folder) else folder
        if key in self.recording_folder_hint_set:
            return
        self.recording_folder_hint_set.add(key)
        self.recording_folder_hints.append(folder)
        logging.debug("Tracking recording segment folder for final analysis: %s", folder)

    def set_frame_count_increase_tolerance(self):
        if self.framerate > 0:
            frame_interval = 1 / self.framerate
            self.frame_count_increase_tolerance = 3 * frame_interval
        else:
            self.frame_count_increase_tolerance = 0.5

    def _maybe_publish_framecount(self, new_count: int | None):
            """
            Update the Redis key 'framecount' – but *never* lower it back down
            unless the encoder reports 0.  This eliminates flicker when two
            sensors finish a take a frame apart.
            """
            normalized_count = self._filter_initial_recording_framecount(new_count)
            if normalized_count is None:
                return

            # ── not recording → freeze counter ───────────────────────────────────
            if not self.is_recording:
                if normalized_count == 0 and self.framecount != 0:
                    self.framecount = 0
                    self.redis_controller.set_value("framecount", 0)
                return
            # ─────────────────────────────────────────────────────────────────────

            # one allowed 0 right after Record (CinePi resets its counter once)
            if normalized_count == 0 and self.allow_initial_zero:
                self.framecount = 0
                self.redis_controller.set_value("framecount", 0)
                self.allow_initial_zero = False
                return

            # ── 1) strictly higher → accept & publish ───────────────────────────
            if normalized_count > self.framecount:
                self.framecount = normalized_count
                self.redis_controller.set_value("framecount", normalized_count)
                return

            # ── 2) equal → nothing to do ────────────────────────────────────────
            if normalized_count == self.framecount:
                return

            # ── 3) lower but *non-zero*  → IGNORE  (mitigates flicker) ──────────
            #     Only a real zero (encoder reset) is considered significant.
            if normalized_count < self.framecount and normalized_count != 0:
                # keep the higher value; do not publish
                return

    def _update_active_sensors(self, stats_data: dict[str, object] | None) -> None:
        if not stats_data:
            return

        detected: set[str] = set()
        for key, value in stats_data.items():
            if value is None:
                continue
            if key.startswith('timestamp_cam'):
                detected.add(key[len('timestamp_'):])
            elif key.startswith('frameCount_cam'):
                detected.add(key[len('frameCount_'):])

        if not detected:
            if stats_data.get('timestamp') is not None or stats_data.get('sensorTimestamp') is not None:
                detected.add('cam0')

        if detected:
            self.active_sensor_labels.update(detected)

    def _current_sensor_count(self) -> int:
        if self.active_sensor_labels:
            return len(self.active_sensor_labels)

        try:
            cams_json = self.redis_controller.get_value(ParameterKey.CAMERAS.value)
            if not cams_json:
                return 1
            data = json.loads(cams_json)
            if isinstance(data, (list, tuple)):
                ready = [c for c in data if isinstance(c, dict) and c.get('ready')]
                if ready:
                    return len(ready)
                return len(data) or 1
        except Exception:
            pass

        return 1

    def _current_correction_factor(self) -> float | None:
        try:
            fps_user_raw = self.redis_controller.get_value(ParameterKey.FPS_USER.value)
            fps_effective_raw = self.redis_controller.get_value(ParameterKey.FPS.value)
            if fps_user_raw is None or fps_effective_raw is None:
                return None
            fps_user = float(fps_user_raw)
            fps_effective = float(fps_effective_raw)
        except (TypeError, ValueError):
            return None

        if fps_user == 0:
            return None

        return fps_effective / fps_user

    def _storage_preroll_active(self) -> bool:
        try:
            value = self.redis_controller.get_value(
                ParameterKey.STORAGE_PREROLL_ACTIVE.value
            )
        except Exception:
            return False

        if value is None:
            return False

        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True

        try:
            return bool(int(text))
        except (TypeError, ValueError):
            return False

    def _determine_expected_fps(self) -> float | None:
        if self.fps_at_rec_start is not None and self.fps_at_rec_start > 0:
            return self.fps_at_rec_start

        try:
            value = self.redis_controller.get_value('fps')
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _current_user_fps(self) -> float | None:
        for key in (ParameterKey.FPS_USER.value, ParameterKey.FPS.value):
            try:
                value = self.redis_controller.get_value(key)
                fps = float(value) if value is not None else None
            except (TypeError, ValueError):
                fps = None
            if fps is not None and fps > 0:
                return fps
        return None

    def _reset_fps_timeline(self) -> None:
        self.fps_timeline = []
        if not self.recording_start_time:
            return
        fps = self._current_user_fps()
        if fps is not None:
            self.fps_timeline.append((self.recording_start_time, fps))

    def _note_expected_fps_change(self, new_fps: float | None = None) -> None:
        if not self.is_recording or not self.recording_start_time:
            return
        fps = new_fps if new_fps and new_fps > 0 else self._current_user_fps()
        if fps is None or fps <= 0:
            return
        now = datetime.datetime.now()
        if not self.fps_timeline:
            self.fps_timeline.append((self.recording_start_time, fps))
            return
        last_time, last_fps = self.fps_timeline[-1]
        if abs(last_fps - fps) < 1e-6:
            return
        if now < last_time:
            now = last_time
        self.fps_timeline.append((now, fps))
        self._suppress_live_sync_for_current_take("FPS changed during recording")
        logging.info("Recording FPS segment changed to %.6f at %s", fps, now.isoformat())

    def _suppress_live_sync_for_current_take(self, reason: str) -> None:
        if not self.is_recording:
            return
        if not self.live_sync_suppressed_current_take:
            logging.info("Suppressing live frame-sync warning: %s", reason)
        self.live_sync_suppressed_current_take = True
        self.frames_off_sync_latched_current_take = False
        self.redis_controller.set_value(ParameterKey.FRAMES_IN_SYNC.value, 1)

    @staticmethod
    def _expected_frame_counts(fps_expected: float | None, duration: float, sensor_count: int) -> tuple[int, float]:
        if fps_expected is None or fps_expected <= 0 or duration <= 0:
            return 0, 0.0

        sensor_effective = max(1, sensor_count)
        expected_float = fps_expected * duration * sensor_effective
        expected_int = int(math.floor(expected_float + 1e-6))
        return expected_int, expected_float

    def _expected_frame_counts_for_recording(
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        sensor_count: int,
        honor_frame_limit: bool = True,
    ) -> tuple[int, float]:
        sensor_effective = max(1, sensor_count)

        if honor_frame_limit and self.frame_limit_requested_slots is not None:
            expected_float = float(self.frame_limit_requested_slots * sensor_effective)
            return int(self.frame_limit_requested_slots * sensor_effective), expected_float

        if end_time < start_time:
            end_time = start_time

        timeline = [
            (ts, fps)
            for ts, fps in self.fps_timeline
            if fps is not None and fps > 0 and ts <= end_time
        ]
        if not timeline:
            fps_expected = self._determine_expected_fps()
            duration = self._active_seconds_between(start_time, end_time)
            return self._expected_frame_counts(fps_expected, duration, sensor_effective)

        if timeline[0][0] > start_time:
            timeline.insert(0, (start_time, timeline[0][1]))
        elif timeline[0][0] < start_time:
            first_fps = timeline[0][1]
            for ts, fps in timeline:
                if ts <= start_time:
                    first_fps = fps
                else:
                    break
            timeline = [(start_time, first_fps)] + [(ts, fps) for ts, fps in timeline if ts > start_time]

        expected_float = 0.0
        for idx, (segment_start, fps) in enumerate(timeline):
            next_start = timeline[idx + 1][0] if idx + 1 < len(timeline) else end_time
            if next_start <= start_time:
                continue
            segment_start = max(segment_start, start_time)
            segment_end = min(next_start, end_time)
            if segment_end <= segment_start:
                continue
            expected_float += self._active_seconds_between(segment_start, segment_end) * fps * sensor_effective

        expected_int = int(math.floor(expected_float + 1e-6))
        return expected_int, expected_float

    def _update_live_frames_in_sync(self, now: datetime.datetime | None = None) -> None:
        if not self.is_recording:
            return
        if self.recording_was_preroll or self._storage_preroll_active():
            return
        if self.frames_off_sync_latched_current_take:
            return
        if self.live_sync_suppressed_current_take:
            return
        if self.awaiting_fresh_framecount or not self.recording_start_time:
            return

        now = now or datetime.datetime.now()
        if self._recording_reconfigure_grace_active(now):
            return

        expected_slots, expected_float = self._expected_frame_counts_for_recording(
            self.recording_start_time,
            now,
            1,
            honor_frame_limit=False,
        )

        # Avoid false warnings while the first frame slots are still
        # settling after record start. After that, drift beyond the configured
        # live tolerance latches.
        if expected_float < self.live_sync_startup_guard_frames:
            return

        recorded_slots = int(self.framecount or 0)
        # Drop compensation may only recover frames that are genuinely missing
        # from the recorded count. Clamping to the shortfall stops a phantom
        # (jitter-inflated) timecode drop count from pushing a complete take
        # past the tolerance and latching a false warning.
        shortfall = max(0, expected_slots - recorded_slots)
        drop_compensation = min(int(self.drop_frame_count_current_take), shortfall)
        sync_slots = recorded_slots + drop_compensation
        diff = expected_slots - sync_slots
        # Only warn on shortfall (diff > 0). When the sensor runs slightly fast
        # (diff < 0, recorded > expected), no data has been lost and a live
        # latch would be a false positive. The final analysis correctly handles
        # both directions once the take completes.
        if diff <= self.live_sync_warning_tolerance_frames:
            return

        self.frames_off_sync_latched_current_take = True
        self.redis_controller.set_value(ParameterKey.FRAMES_IN_SYNC.value, 0)
        logging.warning(
            "Live frame sync warning: %+d frame slot difference exceeds "
            "+/- %g frame tolerance "
            "(expected=%d, recorded=%d, dropped-hole compensation=%d).",
            diff,
            self.live_sync_warning_tolerance_frames,
            expected_slots,
            recorded_slots,
            drop_compensation,
        )

    def _update_frames_in_sync(self, stats_data: dict[str, object] | None = None) -> None:
        if stats_data is not None:
            self._update_active_sensors(stats_data)

        if self.is_recording or self.final_analysis_pending:
            return

        if not self.recording_start_time:
            # No reference point – assume healthy until a recording starts.
            self.redis_controller.set_value(ParameterKey.FRAMES_IN_SYNC.value, 1)
            return

        if self.recording_end_time:
            end_for_calc = self.recording_end_time
        else:
            # Recording hasn’t officially started or stopped; keep the last known value.
            return

        sensor_count = self._current_sensor_count()
        expected_int, _ = self._expected_frame_counts_for_recording(
            self.recording_start_time,
            end_for_calc,
            sensor_count,
        )
        recorded_frames = int(self.framecount or 0)
        # See _update_live_frames_in_sync: only credit dropped slots that
        # actually explain a shortfall vs expected, so a jitter-inflated
        # timecode drop count cannot flag a complete take as out of sync.
        raw_dropped_slots = self.drop_frame_count_current_take * max(1, sensor_count)
        shortfall = max(0, expected_int - recorded_frames)
        dropped_frame_slots = min(raw_dropped_slots, shortfall)

        in_sync = (
            abs(expected_int - (recorded_frames + dropped_frame_slots))
            <= self.final_sync_analysis_tolerance_frames
        )
        self.redis_controller.set_value(
            ParameterKey.FRAMES_IN_SYNC.value,
            1 if in_sync else 0,
        )

    def _current_expected_frame_slots(
        self, now: datetime.datetime | None = None
    ) -> int | None:
        if self.awaiting_fresh_framecount:
            return None

        try:
            if self.framecount is not None:
                frame_slots = int(self.framecount)
                if frame_slots >= 0:
                    return frame_slots + int(self.drop_frame_count_current_take)
        except (TypeError, ValueError):
            pass

        if self.frame_limit_anchor_time is None:
            return None

        fps_expected = self._determine_expected_fps()
        if fps_expected is None or fps_expected <= 0:
            return None

        if now is None:
            now = datetime.datetime.now()

        duration = (now - self.frame_limit_anchor_time).total_seconds()
        if duration < 0:
            duration = 0.0

        return 1 + math.floor(duration * fps_expected)

    def _maybe_stop_for_frame_limit(self, now: datetime.datetime | None = None) -> None:
        if self.frame_limit_target_slots is None or self.frame_limit_stop_requested:
            return
        if not self.is_recording:
            return

        current_slots = self._current_expected_frame_slots(now)
        if current_slots is None or current_slots < self.frame_limit_target_slots:
            return

        self.frame_limit_stop_requested = True
        logging.info(
            "Exact frame-limited stop reached: slot %d/%d; stopping recording.",
            current_slots,
            self.frame_limit_requested_slots or self.frame_limit_target_slots,
        )

        if self.recording_stop_callback is not None:
            self.recording_stop_callback()
        else:
            self.redis_controller.set_value(ParameterKey.IS_RECORDING.value, 0)

    def listen_stats(self):
        for message in self.pubsub_stats.listen():
            if message['type'] == 'message':
                message_data = message['data'].decode('utf-8').strip()
                if message_data.startswith("{") and message_data.endswith("}"):
                    try:
                        now = datetime.datetime.now()
                        stats_data = json.loads(message_data)
                        buffer_size = self._coerce_int(stats_data.get('bufferSize', None))
                        buffer_size_max = self._coerce_int(stats_data.get('bufferSizeMax', None))
                        raw_frame_count = self._coerce_int(stats_data.get('frameCount', None))
                        self.frame_count = self._logical_framecount_from_raw(raw_frame_count, now)
                        raw_tc_frame_count = self._coerce_int(stats_data.get('tcFrameCount', None))
                        if raw_tc_frame_count is not None:
                            self.tc_frame_count = raw_tc_frame_count
                        # droppedFrames: unbiased hole count from cinepi-raw.
                        # Guard against the startup race: cinepi-raw's
                        # resetFrameCount() is called during encoder setup, but
                        # the first process() call can fire before the reset
                        # completes and publish the *previous* clip's counter.
                        # Only accept the value once awaiting_fresh_framecount
                        # is cleared (i.e. the first valid frame count has
                        # been seen), by which point the reset has taken effect.
                        raw_dropped_frames = self._coerce_int(stats_data.get('droppedFrames', None))
                        if raw_dropped_frames is not None and not self.awaiting_fresh_framecount:
                            self.hw_dropped_frames = raw_dropped_frames
                        # writeFailures: frames that reached the disk writer but
                        # failed to write (open/write/close error or short write).
                        # Unlike droppedFrames (sensor-timing holes) a write
                        # failure has no inter-frame gap, so the timing-based drop
                        # tiers never see it — this is the only live signal that a
                        # storage device silently cannot keep up (e.g. NTFS under
                        # sustained 4K). Same startup-race guard as droppedFrames.
                        raw_write_failures = self._coerce_int(stats_data.get('writeFailures', None))
                        if raw_write_failures is not None and not self.awaiting_fresh_framecount:
                            self.hw_write_failures = raw_write_failures
                        color_temp = stats_data.get('colorTemp', None)
                        sensor_timestamp = stats_data.get('sensorTimestamp', None)
                        timestamp = stats_data.get('timestamp')
                        timestamp_cam0 = stats_data.get('timestamp_cam0')
                        timestamp_cam1 = stats_data.get('timestamp_cam1')
                        self.current_framerate = self._coerce_float(stats_data.get('framerate', None))

                        if color_temp:
                            self.colorTemp = color_temp

                        fps_user = float(
                            self.redis_controller.get_value(ParameterKey.FPS_USER.value) or 24
                        )

                        if timestamp is not None and timestamp != self.last_timestamp_cam0:
                            tc = self.redis_controller.nanoseconds_to_timecode(int(timestamp), fps_user)
                            self.redis_controller.set_value(ParameterKey.TC_CAM0.value, tc)
                            self.last_timestamp_cam0 = timestamp
                        if timestamp_cam0 is not None and timestamp_cam0 != self.last_timestamp_cam0:
                            tc0 = self.redis_controller.nanoseconds_to_timecode(int(timestamp_cam0), fps_user)
                            self.redis_controller.set_value(ParameterKey.TC_CAM0.value, tc0)
                            self.last_timestamp_cam0 = timestamp_cam0
                        if timestamp_cam1 is not None and timestamp_cam1 != self.last_timestamp_cam1:
                            tc1 = self.redis_controller.nanoseconds_to_timecode(int(timestamp_cam1), fps_user)
                            self.redis_controller.set_value(ParameterKey.TC_CAM1.value, tc1)
                            self.last_timestamp_cam1 = timestamp_cam1

                        # Update Redis key for current buffer size if changed.
                        # Drive the GUI buffer VU from the peak backlog
                        # (bufferSizeMax) cinepi-raw saw since the last stats
                        # message, so a transient disk-write spike between two
                        # delivered frames is visible instead of being missed by
                        # instantaneous sampling. Falls back to bufferSize when
                        # the running cinepi-raw build does not publish the peak.
                        if buffer_size is not None:
                            self.bufferSize = buffer_size
                            display_buffer = buffer_size
                            if buffer_size_max is not None and buffer_size_max > display_buffer:
                                display_buffer = buffer_size_max
                            current_buffer = self.redis_controller.get_value(ParameterKey.BUFFER.value)
                            # Redis returns bytes or None → normalise to int or None
                            current_buffer = self._coerce_int(current_buffer)

                            if current_buffer != display_buffer:
                                self.redis_controller.set_value(ParameterKey.BUFFER.value, display_buffer)
                                #logging.info(f"Buffer size changed to {display_buffer}")

                        # Update sensor timestamps
                        if sensor_timestamp is not None:
                            self.sensor_timestamps.append(int(sensor_timestamp))
                            self.calculate_average_framerate_last_100_frames()
                        
                        if len(self.sensor_timestamps) > 1:
                            self.calculate_current_framerate()

                        # Update framecount in Redis (only if it has changed, and doesnt report a lower number than before, except 0
                        self._maybe_publish_framecount(self.frame_count)
                        self._maybe_stop_for_frame_limit()

                        # Check and set buffering status if changed
                        is_buffering = buffer_size > 0 if buffer_size is not None else False
                        current_buffering_status = self.redis_controller.get_value('is_buffering')
                        new_buffering_status = 1 if is_buffering else 0
                        if current_buffering_status is None or int(current_buffering_status) != new_buffering_status:
                            logging.debug(f"Updating is_buffering to {new_buffering_status}")
                            self.redis_controller.set_value('is_buffering', new_buffering_status)

                        buffered_write_active = (
                            buffer_size is not None
                            and buffer_size > 0
                            and not self.is_recording
                        )
                        current_buf_write_status = self.redis_controller.get_value(
                            ParameterKey.IS_WRITING_BUF.value
                        )
                        current_buf_write_status = self._coerce_int(current_buf_write_status) or 0
                        new_buf_write_status = 1 if buffered_write_active else 0
                        if current_buf_write_status != new_buf_write_status:
                            logging.info(
                                "Buffered frame write status: %s (buffer=%s)",
                                "active" if new_buf_write_status else "idle",
                                buffer_size,
                            )
                            self.redis_controller.set_value(
                                ParameterKey.IS_WRITING_BUF.value,
                                new_buf_write_status,
                            )

                        # Add current framerate value to the list
                        if self.current_framerate is not None:
                            self.framerate_values.append(self.current_framerate)
                            
                        expected_fps = self._coerce_float(self.redis_controller.get_value('fps'))

                        drop_alerts_enabled = (
                            self.is_recording
                            and not self.awaiting_fresh_framecount
                            and not self.recording_was_preroll
                            and not self._storage_preroll_active()
                            and not self._recording_reconfigure_grace_active(now)
                            and not self.user_changing_fps
                        )

                        if drop_alerts_enabled:
                            if self.hw_dropped_frames is not None:
                                # Tier 1 – unbiased hw counter (cinepi-raw ≥ droppedFrames build).
                                # Each unit is exactly one frame that was not written to disk
                                # (inter-frame gap rounded to ≥2 frame periods). No jitter bias.
                                dropped_slots = self.hw_dropped_frames
                                if dropped_slots > self.drop_frame_count_current_take:
                                    new_slots = dropped_slots - self.drop_frame_count_current_take
                                    self.drop_frame_count_current_take = dropped_slots
                                    self.redis_controller.set_value(ParameterKey.DROP_FRAME_COUNT.value, dropped_slots)
                                    self._pulse_drop_frame_relay(expected_fps)
                                    if not self.drop_frame:
                                        self.drop_frame = True
                                        self.redis_controller.set_value(ParameterKey.DROP_FRAME.value, 1)
                                    logging.info(
                                        "Drop frame detected (hw): %d hole(s) (total this take: %d).",
                                        new_slots,
                                        dropped_slots,
                                    )
                                    if self.drop_frame_timer:
                                        self.drop_frame_timer.cancel()
                                    self.drop_frame_timer = threading.Timer(0.5, self.reset_drop_frame)
                                    self.drop_frame_timer.start()

                            elif self.tc_frame_count is not None and raw_frame_count is not None:
                                # Tier 2 – TC-diff fallback (firmware with tcFrameCount but not
                                # droppedFrames). The TC counter has a +1 floor bias; the deadband
                                # absorbs single-slot jitter so ordinary timing noise does not
                                # trigger a false drop alert.
                                dropped_slots = max(0, self.tc_frame_count - raw_frame_count)
                                if (
                                    dropped_slots > self.tc_drop_jitter_tolerance_frames
                                    and dropped_slots > self.drop_frame_count_current_take
                                ):
                                    new_slots = dropped_slots - self.drop_frame_count_current_take
                                    self.drop_frame_count_current_take = dropped_slots
                                    self.redis_controller.set_value(ParameterKey.DROP_FRAME_COUNT.value, dropped_slots)
                                    self._pulse_drop_frame_relay(expected_fps)
                                    if not self.drop_frame:
                                        self.drop_frame = True
                                        self.redis_controller.set_value(ParameterKey.DROP_FRAME.value, 1)
                                    logging.info(
                                        "Drop frame detected (tc-diff): %d slot(s) (total this take: %d).",
                                        new_slots,
                                        dropped_slots,
                                    )
                                    if self.drop_frame_timer:
                                        self.drop_frame_timer.cancel()
                                    self.drop_frame_timer = threading.Timer(0.5, self.reset_drop_frame)
                                    self.drop_frame_timer.start()

                            elif self.current_framerate is not None and expected_fps is not None:
                                # Tier 3 – FPS-deviation fallback (oldest firmware, no TC support).
                                if abs(self.current_framerate - expected_fps) > 1:
                                    self.drop_frame_count_current_take += 1
                                    self.redis_controller.set_value(ParameterKey.DROP_FRAME_COUNT.value, self.drop_frame_count_current_take)
                                    self._pulse_drop_frame_relay(expected_fps)
                                    if not self.drop_frame:
                                        self.drop_frame = True
                                        self.redis_controller.set_value(ParameterKey.DROP_FRAME.value, 1)
                                    logging.info("Drop frame detected (fps-dev fallback, count=%d).", self.drop_frame_count_current_take)
                                    if self.drop_frame_timer:
                                        self.drop_frame_timer.cancel()
                                    self.drop_frame_timer = threading.Timer(0.5, self.reset_drop_frame)
                                    self.drop_frame_timer.start()

                        # Disk-write-failure alert — independent of the timing-based
                        # drop tiers above. A write failure means a delivered, encoded
                        # frame never reached disk; there is no inter-frame gap, so the
                        # drop tiers never see it. Warn live so the operator knows the
                        # drive cannot keep up — otherwise the post-take file count is
                        # the first and only signal that frames were lost.
                        write_alerts_enabled = (
                            self.is_recording
                            and not self.awaiting_fresh_framecount
                            and not self._storage_preroll_active()
                        )
                        if write_alerts_enabled and self.hw_write_failures is not None:
                            if self.hw_write_failures > self.write_failure_count_current_take:
                                new_failures = self.hw_write_failures - self.write_failure_count_current_take
                                self.write_failure_count_current_take = self.hw_write_failures
                                logging.warning(
                                    "Disk write failure: %d frame(s) could not be written to disk "
                                    "(total this take: %d). The drive cannot keep up — frames are "
                                    "being lost. Use exFAT or ext4 for sustained recording.",
                                    new_failures,
                                    self.hw_write_failures,
                                )
                                if not self.drop_frame:
                                    self.drop_frame = True
                                    self.redis_controller.set_value(ParameterKey.DROP_FRAME.value, 1)
                                self._pulse_drop_frame_relay(expected_fps)
                                if self.drop_frame_timer:
                                    self.drop_frame_timer.cancel()
                                self.drop_frame_timer = threading.Timer(0.5, self.reset_drop_frame)
                                self.drop_frame_timer.start()

                        if self.current_framerate is not None and self.current_framerate > 0:
                            self.framecount_check_interval = max(0.5, 2 / self.current_framerate)
                        else:
                            self.framecount_check_interval = max(0.5, 2 / 1)

                        # Check if framecount is changing
                        self.check_framecount_changing()
                        self._update_live_frames_in_sync()
                        self.last_stats_message_time = now
                        
                        # # Calculate average framerate of last 100 frames
                        # avg_framerate = self.calculate_average_framerate_last_100_frames()

                        # # Adjust FPS if necessary
                        # current_time = datetime.datetime.now()
                        # if (current_time - self.last_fps_adjustment_time).total_seconds() >= self.fps_adjustment_interval:
                        #     self.adjust_fps(avg_framerate)
                        #     self.last_fps_adjustment_time = current_time


                    except json.JSONDecodeError as e:
                        logging.error(f"Failed to parse JSON data: {e}")
                    except (TypeError, ValueError) as e:
                        logging.error(f"Type error in stats data: {e}")
                else:
                    logging.warning(f"Received unexpected data format: {message_data}")
                    

    def _pulse_drop_frame_relay(self, expected_fps: float | None) -> None:
        """Emit a short drop-frame relay pulse for REC tone interruption."""
        frame_duration_s = 1 / expected_fps if expected_fps and expected_fps > 0 else (1 / 24)
        frame_duration_s = min(max(frame_duration_s, 0.005), 0.1)

        self.redis_controller.set_value(ParameterKey.DROP_FRAME_RELAY.value, 1)

        if self.drop_frame_relay_timer:
            self.drop_frame_relay_timer.cancel()
        self.drop_frame_relay_timer = threading.Timer(frame_duration_s, self.reset_drop_frame_relay)
        self.drop_frame_relay_timer.start()

    def reset_drop_frame_relay(self):
        self.redis_controller.set_value(ParameterKey.DROP_FRAME_RELAY.value, 0)

    def reset_drop_frame(self):
        self.drop_frame = False
        self.redis_controller.set_value(ParameterKey.DROP_FRAME.value, 0)
        logging.info("Drop frame flag reset")
        
    # ───────────────────  FPS-change handling  ──────────────────────────────
    def _reset_user_changing_fps(self):
        """Debounce-timer callback – clear the flag once the fps key
        has been stable for a while."""
        self.user_changing_fps = False
        self.redis_controller.set_value("user_changing_fps", 0)
        logging.debug("user_changing_fps → 0 (fps stable)")

    def _note_fps_change(self, new_fps: float):
        """Call every time the Redis key ‘fps’ is modified."""
        if new_fps == self.last_fps_value:
            return                                        # nothing really changed

        self.last_fps_value = new_fps
        self.user_changing_fps = True
        self.redis_controller.set_value("user_changing_fps", 1)
        logging.debug(f"fps changed to {new_fps} → user_changing_fps = 1")

        # leeway = max(0.5 s, two frame-intervals)
        leeway = max(0.5, 2 / new_fps) if new_fps else 0.5

        if self.fps_change_timer:
            self.fps_change_timer.cancel()
        self.fps_change_timer = threading.Timer(leeway, self._reset_user_changing_fps)
        self.fps_change_timer.start()

    def _storage_is_still_flushing(self) -> bool:
        keys = (
            ParameterKey.IS_WRITING_BUF.value,
            ParameterKey.IS_BUFFERING.value,
            ParameterKey.IS_WRITING.value,
        )
        for key in keys:
            try:
                if self._coerce_int(self.redis_controller.get_value(key)) == 1:
                    return True
            except Exception:
                pass
        return self.bufferSize > 0

    def _clear_frame_warning_state(self) -> None:
        self.drop_frame_count_current_take = 0
        self.tc_frame_count = None
        self.hw_dropped_frames = None
        self.hw_write_failures = None
        self.write_failure_count_current_take = 0
        self.drop_frame = False
        self.frames_off_sync_latched_current_take = False
        if self.drop_frame_timer:
            self.drop_frame_timer.cancel()
            self.drop_frame_timer = None
        if self.drop_frame_relay_timer:
            self.drop_frame_relay_timer.cancel()
            self.drop_frame_relay_timer = None
        self.redis_controller.set_value(ParameterKey.DROP_FRAME.value, 0)
        self.redis_controller.set_value(ParameterKey.DROP_FRAME_COUNT.value, 0)
        self.redis_controller.set_value(ParameterKey.DROP_FRAME_RELAY.value, 0)
        self.redis_controller.set_value(ParameterKey.DROP_FRAME_DURING_LAST_TAKE.value, 0)
        self.redis_controller.set_value(ParameterKey.FRAMES_IN_SYNC.value, 1)

    def _clear_post_recording_state(self) -> None:
        self.recording_was_preroll = False
        self.framerate_values = []
        self.frame_limit_target_slots = None
        self.frame_limit_requested_slots = None
        self.frame_limit_anchor_time = None
        self.frame_limit_stop_requested = False
        self.awaiting_fresh_framecount = False
        self.fresh_framecount_guard_start_time = None
        self.fps_correction_factor_at_rec_start = None
        self.fps_at_rec_start = None
        self.fps_timeline = []
        self.raw_framecount_last = None
        self.framecount_segment_base = 0
        self.recording_reconfigure_pending = False
        self.recording_reconfigure_requested_at = None
        self.recording_reconfigure_grace_until = None
        self.recording_pause_intervals = []
        self.last_stats_message_time = None
        self.recording_folder_hints = []
        self.recording_folder_hint_set.clear()
        with self.final_analysis_lock:
            self.final_analysis_pending = False
            self.final_analysis_sequence = None

    def _schedule_final_analysis(self) -> None:
        take_sequence = self.take_sequence
        with self.final_analysis_lock:
            self.final_analysis_pending = True
            if (
                self.final_analysis_thread
                and self.final_analysis_thread.is_alive()
                and self.final_analysis_sequence == take_sequence
            ):
                return

            self.final_analysis_sequence = take_sequence
            self.final_analysis_thread = threading.Thread(
                target=self._final_analysis_worker,
                args=(take_sequence,),
                name="FinalFrameAnalysis",
                daemon=True,
            )
            self.final_analysis_thread.start()

    def _final_analysis_worker(self, take_sequence: int) -> None:
        start_wait = time.time()
        logged_wait = False
        flush_timed_out = False
        while (time.time() - start_wait) < self.final_analysis_timeout_s:
            if take_sequence != self.take_sequence:
                with self.final_analysis_lock:
                    if self.final_analysis_sequence == take_sequence:
                        self.final_analysis_pending = False
                        self.final_analysis_sequence = None
                return
            if not self._storage_is_still_flushing():
                break
            if not logged_wait:
                logging.info("Waiting for buffered frames to finish writing before frame-sync analysis.")
                logged_wait = True
            time.sleep(self.final_analysis_poll_s)
        else:
            logging.warning(
                "Buffered frame flush did not go idle within %.1fs; analyzing with stable on-disk count.",
                self.final_analysis_timeout_s,
            )
            flush_timed_out = True

        if logged_wait and not flush_timed_out:
            logging.info("Buffered frame write complete; running final frame-sync analysis.")

        try:
            if take_sequence == self.take_sequence:
                self.analyze_frames()
        finally:
            if take_sequence == self.take_sequence:
                self._clear_post_recording_state()

        
    def check_framecount_changing(self):
        """
        Toggle Redis key 'rec':
            • rec=1  as soon as frameCount rises
            • rec=0  only after <rec_hold_seconds> of no rise, OR when frameCount hits 0
        Any lower-but-non-zero values are ignored entirely.
        """
        now = datetime.datetime.now()
        new = self._filter_initial_recording_framecount(self.frame_count)
        if new is None:
            return
        old = self._coerce_int(self.last_framecount)
        if old is None:
            old = 0                              # last *accepted* count

        # ----------------------------------------------------------- 1) reset to 0
        if new == 0:
            if self.framecount_changing:
                self.framecount_changing = False
                self.redis_controller.set_value("rec", "0")
                logging.info("Framecount reset to 0 → rec=0")
            self.last_rise_time = None
            self.last_framecount = 0
            return

        # ----------------------------------------------------------- 2) higher →
        if new > old:
            if not self.framecount_changing:
                self.framecount_changing = True
                self.redis_controller.set_value("rec", "1")
                logging.info("Framecount rising → rec=1")
                if self.frame_limit_anchor_time is None:
                    self.frame_limit_anchor_time = now

            self.last_rise_time = now             # remember when we last rose
            self.last_framecount = new
            self._maybe_stop_for_frame_limit(now)
            return

        # ----------------------------------------------------------- 3) equal →
        if new == old:
            if self.framecount_changing and self.last_rise_time:
                if (now - self.last_rise_time).total_seconds() >= self.rec_hold_seconds:
                    self.framecount_changing = False
                    self.redis_controller.set_value("rec", "0")
                    logging.info(f"Framecount flat for {self.rec_hold_seconds}s → rec=0")
            return

        # ----------------------------------------------------------- 4) lower-but-non-zero  → ignore
        # (do NOT update self.last_framecount – keep the higher baseline)
        logging.debug(
            f"Framecount dipped from {old} to {new} – ignored to avoid flicker."
        )

        
    def reset_framecount(self):
        self.framecount = 0
        self.frame_count = 0
        self.last_framecount = 0
        self.raw_framecount_last = None
        self.framecount_segment_base = 0
        self.last_rise_time = None
        self.framecount_changing = False
        self.bufferSize = 0
        self.frames_off_sync_latched_current_take = False
        self.redis_controller.set_value('framecount', 0)
        self.active_sensor_labels.clear()
        self.redis_controller.set_value(ParameterKey.FRAMES_IN_SYNC.value, 1)
        logging.info("Framecount reset to 0.")

    def listen_controls(self):
        for message in self.pubsub_controls.listen():
            if message["type"] != "message":
                continue

            changed_key = message["data"].decode('utf-8')
            with self.lock:
                value = self.redis_client.get(changed_key)
                if value is None:
                    continue
                value_str = value.decode('utf-8')

                # ✅ Skip if value hasn't changed
            if changed_key == 'is_recording':
                if value_str == self.last_is_recording_value:
                    continue
                self.last_is_recording_value = value_str

                if value_str == '1':
                    self.is_recording = True
                    self.take_sequence += 1
                    self.reset_framecount()
                    self.recording_start_time = datetime.datetime.now()
                    self.recording_pause_intervals = []
                    self.recording_reconfigure_pending = False
                    self.recording_reconfigure_requested_at = None
                    self.recording_reconfigure_grace_until = None
                    self.last_stats_message_time = None
                    self.recording_folder_hints = []
                    self.recording_folder_hint_set.clear()
                    self.awaiting_fresh_framecount = True
                    self.fresh_framecount_guard_start_time = self.recording_start_time
                    self.drop_frame_count_current_take = 0
                    self.frames_off_sync_latched_current_take = False
                    self.live_sync_suppressed_current_take = False
                    self.redis_controller.set_value(ParameterKey.DROP_FRAME_COUNT.value, 0)
                    self.redis_controller.set_value(ParameterKey.DROP_FRAME_RELAY.value, 0)
                    self.redis_controller.set_value(ParameterKey.DROP_FRAME_DURING_LAST_TAKE.value, 0)
                    self.redis_controller.set_value(ParameterKey.IS_WRITING_BUF.value, 0)
                    self.recording_end_time = None
                    with self.final_analysis_lock:
                        self.final_analysis_pending = False
                        self.final_analysis_sequence = None
                    logging.info(f"Recording started at: {self.recording_start_time}")

                    self.recording_was_preroll = self._storage_preroll_active()
                    # Preserve any freshly armed frame limit across the async
                    # is_recording transition. The controller may arm the stop
                    # immediately after setting is_recording=1.
                    self.frame_limit_anchor_time = None
                    self.frame_limit_stop_requested = False

                    self.fps_correction_factor_at_rec_start = self._current_correction_factor()
                    initial_correction = self.fps_correction_factor_at_rec_start or 1.0

                    self.redis_controller.set_value(
                        ParameterKey.FPS_CORRECTION_SUGGESTION.value,
                        f"{initial_correction:.6f}",
                    )

                    # Lock the FPS at start (configured value)
                    try:
                        self.fps_at_rec_start = float(self.redis_controller.get_value('fps_user'))
                    except (TypeError, ValueError):
                        self.fps_at_rec_start = None
                    self._reset_fps_timeline()

                    self.framerate = float(self.redis_controller.get_value('fps_user'))  # keep if you still use it elsewhere
                    self.allow_initial_zero = True

                    if self.drop_frame_timer:
                        self.drop_frame_timer.cancel()
                    if self.drop_frame_relay_timer:
                        self.drop_frame_relay_timer.cancel()
                    self.drop_frame = False
                    self.redis_controller.set_value(ParameterKey.DROP_FRAME.value, 0)
                    self.redis_controller.set_value(ParameterKey.DROP_FRAME_RELAY.value, 0)


                elif value_str == '0':
                    if self.is_recording:
                        self.is_recording = False
                        if self.recording_start_time:
                            self.recording_end_time = datetime.datetime.now()
                            logging.info(f"Recording stopped at: {self.recording_end_time}")
                            if self.bufferSize > 0:
                                self.redis_controller.set_value(ParameterKey.IS_WRITING_BUF.value, 1)
                            if self.recording_was_preroll:
                                logging.debug("Skipping frame-sync analysis for storage pre-roll.")
                                self._clear_frame_warning_state()
                                self._clear_post_recording_state()
                            else:
                                self._schedule_final_analysis()
                        else:
                            logging.warning("Recording stopped, but no recording start time was registered.")
                            self.recording_was_preroll = False
                    self.allow_initial_zero = True
                    
            elif changed_key == "fps":
                try:
                    self._note_fps_change(float(value_str))
                    self._note_expected_fps_change()
                except ValueError:
                    logging.warning(f"Ignoring invalid fps value {value_str!r}")
                continue
            elif changed_key == ParameterKey.FPS_USER.value:
                try:
                    self._note_expected_fps_change(float(value_str))
                except ValueError:
                    logging.warning(f"Ignoring invalid fps_user value {value_str!r}")
                continue
            elif changed_key == ParameterKey.CAM_INIT.value:
                self._begin_recording_reconfigure()
                continue
            elif changed_key in (
                ParameterKey.LAST_DNG_CAM0.value,
                ParameterKey.LAST_DNG_CAM1.value,
            ):
                self._remember_recording_folder_from_dng(value_str)
                continue
            elif changed_key in (
                ParameterKey.SENSOR_MODE.value,
                ParameterKey.WIDTH.value,
                ParameterKey.HEIGHT.value,
            ):
                self._suppress_live_sync_for_current_take(
                    f"{changed_key} changed during recording"
                )
                continue


    def calculate_current_framerate(self):
        if len(self.sensor_timestamps) > 1:
            timestamps_in_seconds = [ts / 1_000_000 for ts in self.sensor_timestamps]
            time_diffs = [t2 - t1 for t1, t2 in zip(timestamps_in_seconds, timestamps_in_seconds[1:])]
            
            if time_diffs:
                average_time_diff = sum(time_diffs) / len(time_diffs)
                logging.debug(f"Time differences between consecutive frames: {time_diffs}")
                logging.debug(f"Average time difference: {average_time_diff}")
                
                self.current_framerate = ((1.0 / average_time_diff) * 1000) if average_time_diff != 0 else 0
                logging.debug(f"Calculated current framerate: {self.current_framerate:.6f} FPS")
            else:
                logging.warning("Time differences calculation resulted in an empty list.")
                self.current_framerate = None
        else:
            self.current_framerate = None
        self.redis_controller.set_value('fps_actual', self.current_framerate)
        
    # ------------------------ DNG enumeration helpers ------------------------
    _DNG_SUFFIX = ('.dng', '.DNG')
    _IDX_RE = re.compile(r'_(\d+)\.dng$', re.IGNORECASE)

    def _resolve_folder_path(self, folder_hint: str | os.PathLike) -> str | None:
        """
        Try to turn a folder hint into an existing absolute directory.
        Strategy:
          1) If it's absolute and exists → use it.
          2) Try ssd_monitor roots if present (root_dir/base_path/mount_dir).
          3) Try common media roots (/media/RAW, /media).
          4) Try parent of last_dng_cam0/1 from Redis (exact path).
        Returns an absolute path or None.
        """
        # Normalize the hint
        if folder_hint is None:
            hint = None
        else:
            hint = str(folder_hint).strip()

        # short-circuit: absolute and exists
        if hint and os.path.isabs(hint) and os.path.isdir(hint):
            return hint

        # Collect candidate roots
        roots = []
        for attr in ("root_dir", "base_path", "mount_dir", "mount_point"):
            r = getattr(self.ssd_monitor, attr, None)
            if r:
                roots.append(str(r))
        roots += ["/media/RAW", "/media"]

        # If the hint is just a basename, try to place it under roots
        base = os.path.basename(hint) if hint else None
        for root in roots:
            if base:
                p = os.path.join(root, base)
                if os.path.isdir(p):
                    return os.path.abspath(p)

        # Fallback: derive from last_dng_cam0/1 parents (exact folder)
        for key in ("last_dng_cam0", "last_dng_cam1", "last_dng"):
            try:
                val = self.redis_controller.get_value(key)
                if not val:
                    continue
                d = os.path.dirname(str(val))
                if os.path.isdir(d):
                    # If no hint, use this; if we have a base, require suffix match
                    if not base or os.path.basename(d) == base:
                        return os.path.abspath(d)
            except Exception:
                pass

        # Last attempt: if hint is relative and exists from CWD
        if hint:
            abs_guess = os.path.abspath(hint)
            if os.path.isdir(abs_guess):
                return abs_guess

        return None

    def _scan_dngs_once(self, folder_path: str):
        """
        Single pass: count valid DNG files and find the highest frame index.
        Skips non-files and zero-length/in-flight files.
        Returns (count, last_idx:int|None, last_name:str|None, latest_mtime:float|None).
        """
        cnt = 0
        last_idx = None
        last_name = None
        latest_mtime = None

        try:
            with os.scandir(folder_path) as it:
                for e in it:
                    if not e.is_file():
                        continue
                    name = e.name
                    if not name.endswith(self._DNG_SUFFIX):
                        continue
                    try:
                        st = e.stat()
                    except FileNotFoundError:
                        continue
                    if st.st_size <= 0:
                        continue

                    cnt += 1
                    if (latest_mtime is None) or (st.st_mtime > latest_mtime):
                        latest_mtime = st.st_mtime

                    m = self._IDX_RE.search(name)
                    if m:
                        idx = int(m.group(1))
                        if last_idx is None or idx > last_idx:
                            last_idx = idx
                            last_name = name
        except FileNotFoundError:
            return 0, None, None, None

        return cnt, last_idx, last_name, latest_mtime

    def _stable_dng_count(self, folder_path: str, settle_s: float = 0.35, max_attempts: int = 4):
        """
        Repeat scans until the count is identical twice in a row AND the newest
        file's mtime is older than settle_s (no in-flight files).
        """
        last = None
        last_latest_mtime = None
        for _ in range(max_attempts):
            cnt, li, ln, latest_mtime = self._scan_dngs_once(folder_path)
            now = time.time()

            # Same count twice in a row?
            if last is not None and cnt == last:
                # Also require that the newest file is older than settle window
                if latest_mtime is None or (now - latest_mtime) >= settle_s:
                    return cnt, li, ln

            last = cnt
            last_latest_mtime = latest_mtime
            time.sleep(settle_s)

        # final return after attempts
        return last or 0, None, None


    def analyze_frames(self):
        """
        Compare the actual number of DNGs on disk with the theoretical count.
        Robust against path ambiguities, in-flight files, and off-by-one rounding.
        """
        if self.recording_was_preroll or self._storage_preroll_active():
            logging.debug("Skipping frame-sync analysis for storage pre-roll.")
            self._clear_frame_warning_state()
            return

        quiet_summary = self.recording_was_preroll

        # --------------------------- 1) collect candidate dirs -----------------
        folders = self.ssd_monitor.get_latest_recording_infos()
        per_sensor = []   # (label, fs_count|None, monitor_count|None, last_idx|None, last_name|None)
        seen_resolved: set[str] = set()
        segmented_recording = False
        segment_folder_count = 0
        segment_index_hole_frames_total = 0

        if folders:
            for info in folders:
                # Extract hint path and the monitor's own count if present
                hint_path = info[0] if isinstance(info, (list, tuple)) else info
                monitor_count = None
                if isinstance(info, (list, tuple)) and len(info) >= 2:
                    try:
                        monitor_count = int(info[1])
                    except Exception:
                        monitor_count = None

                resolved = self._resolve_folder_path(hint_path)
                label = os.path.basename(str(hint_path)) if hint_path else "(unknown)"

                fs_count = None
                last_idx = None
                last_name = None
                if resolved:
                    seen_resolved.add(os.path.abspath(resolved))
                    c, li, ln = self._stable_dng_count(resolved)
                    fs_count, last_idx, last_name = c, li, ln
                    if fs_count is None:
                        fs_count = 0

                per_sensor.append((label, fs_count, monitor_count, last_idx, last_name))

        for hint_path in self.recording_folder_hints:
            resolved = self._resolve_folder_path(hint_path)
            if not resolved:
                continue
            resolved_abs = os.path.abspath(resolved)
            if resolved_abs in seen_resolved:
                continue
            seen_resolved.add(resolved_abs)
            label = os.path.basename(resolved_abs)
            c, li, ln = self._stable_dng_count(resolved_abs)
            per_sensor.append((label, c, None, li, ln))

        # If we found nothing, also try the parents of last_dng_cam0/1 directly
        if not per_sensor:
            for key in ("last_dng_cam0", "last_dng_cam1"):
                val = self.redis_controller.get_value(key)
                if not val:
                    continue
                d = os.path.dirname(str(val))
                if not os.path.isdir(d):
                    continue
                label = os.path.basename(d)
                c, li, ln = self._stable_dng_count(d)
                per_sensor.append((label, c, None, li, ln))

        # ------------------------------ 2) totals ------------------------------
        if not per_sensor:
            if not quiet_summary:
                logging.warning("No recent recording folders found — falling back to RAM counter.")
            recorded_frames_total = int(self.framecount or 0)
            sensor_count_effective = 1 if recorded_frames_total > 0 else 0
        else:
            # Prefer filesystem counts; if fs_count == 0 because path couldn't be resolved
            # but the monitor reported a positive count, use the monitor's count as fallback.
            final_counts = []
            for label, fs_c, mon_c, li, ln in per_sensor:
                use_c = fs_c if (fs_c is not None and fs_c > 0) else (mon_c or 0)
                final_counts.append((label, use_c, li, ln))

            sensor_labels = {
                self._sensor_label_from_recording_label(label)
                for label, c, _, _ in final_counts
                if c > 0
            }
            sensor_folder_counts: dict[str, int] = {}
            for label, c, li, _ in final_counts:
                if c <= 0:
                    continue

                sensor_label = self._sensor_label_from_recording_label(label)
                sensor_folder_counts[sensor_label] = sensor_folder_counts.get(sensor_label, 0) + 1
                if li is not None and li + 1 > c:
                    segment_index_hole_frames_total += li + 1 - c

            segmented_recording = any(count > 1 for count in sensor_folder_counts.values())
            segment_folder_count = sum(sensor_folder_counts.values())
            sensor_count_effective = len(sensor_labels)
            recorded_frames_total = sum(c for _, c, _, _ in final_counts)

            # Diagnostics
            if not quiet_summary:
                for label, c, li, ln in final_counts:
                    if ln:
                        logging.info(f"{label}: {c} DNGs (last={ln}, idx={li})")
                    else:
                        logging.info(f"{label}: {c} DNGs")
                    if li is not None and c > 0 and li + 1 > c:
                        missing = li + 1 - c
                        logging.warning(
                            "%s appears to be missing %d DNG index slot(s) "
                            "(count=%d, last idx=%d).",
                            label,
                            missing,
                            c,
                            li,
                        )

                logging.info(f"Total frames on disk: {recorded_frames_total} from {sensor_count_effective} sensor(s)")

        # ------------------------------ duration ------------------------------
        if not (self.recording_start_time and self.recording_end_time):
            logging.warning("No start/end timestamps; cannot compute frame diff.")
            return

        # Prefer the timestamp of the last *accepted* frame rise (more accurate end)
        end_for_calc = self.recording_end_time

        if end_for_calc < self.recording_start_time:
            # guard against clock skew or odd ordering
            end_for_calc = self.recording_end_time

        duration = (end_for_calc - self.recording_start_time).total_seconds()
        if duration < 0:
            duration = 0.0
        if not quiet_summary:
            logging.info(f"Recording duration in seconds (start→end): {duration:.6f}")
            if segmented_recording:
                logging.info(
                    "Segmented recording detected (%d clip folder(s) across %d sensor(s)); "
                    "using on-disk segment totals for final sync analysis.",
                    segment_folder_count,
                    max(1, sensor_count_effective),
                )
            else:
                paused_seconds = duration - self._active_seconds_between(
                    self.recording_start_time,
                    end_for_calc,
                )
                if paused_seconds > 0:
                    logging.info(
                        "Excluded %.6fs of in-recording reconfigure pause time from frame-sync analysis.",
                        paused_seconds,
                    )

        drop_detected_this_take = (
            self.drop_frame_count_current_take > 0
            or segment_index_hole_frames_total > 0
        )
        live_drop_holes_total = (
            self.drop_frame_count_current_take * max(1, sensor_count_effective)
            if self.drop_frame_count_current_take > 0
            else 0
        )
        dropped_frame_slots_total = max(
            live_drop_holes_total,
            segment_index_hole_frames_total,
        )
        drop_frame_count_for_reporting = max(
            self.drop_frame_count_current_take,
            int(math.ceil(segment_index_hole_frames_total / max(1, sensor_count_effective))),
        )

        # ----------------------- expected frames (per sensor) -----------------
        # Exact frame-limited takes use the requested slot count. Free-running
        # takes integrate the user FPS timeline so speed ramps are counted.
        if segmented_recording and self.frame_limit_requested_slots is None:
            expected_frames_total = recorded_frames_total + dropped_frame_slots_total
            expected_frames_float = float(expected_frames_total)
            if not quiet_summary:
                logging.info("Using segmented on-disk frame total for expected-frame calculation.")
        elif self.frame_limit_requested_slots is not None:
            expected_frames_total, expected_frames_float = self._expected_frame_counts_for_recording(
                self.recording_start_time,
                end_for_calc,
                sensor_count_effective,
            )
            if not quiet_summary:
                logging.info(
                    "Using requested frame-limited target: %d frame slot(s) × %d sensor(s)",
                    self.frame_limit_requested_slots,
                    max(1, sensor_count_effective),
                )
        else:
            expected_frames_total, expected_frames_float = self._expected_frame_counts_for_recording(
                self.recording_start_time,
                end_for_calc,
                sensor_count_effective,
            )
            if not quiet_summary:
                if len(self.fps_timeline) > 1:
                    logging.info(
                        "Using integrated FPS timeline with %d segment(s) for expected-frame calculation.",
                        len(self.fps_timeline),
                    )
                elif self.fps_timeline:
                    logging.info(
                        "Using FPS %.6f for expected-frame calculation.",
                        self.fps_timeline[-1][1],
                    )
                else:
                    logging.info("Using configured FPS fallback for expected-frame calculation.")

        if not quiet_summary:
            logging.info(f"Calculated expected number of frames: {expected_frames_total}")
            logging.info(f"Actual number of recorded frames: {recorded_frames_total}")

        # Only credit dropped-frame holes that explain a genuine shortfall.
        # If the disk count already meets or exceeds expected, compensation
        # would push the difference further negative and trigger a false warning.
        shortfall_total = max(0, expected_frames_total - recorded_frames_total)
        dropped_frame_slots_compensated = min(dropped_frame_slots_total, shortfall_total)
        sync_recorded_frames_total = recorded_frames_total + dropped_frame_slots_compensated
        diff = expected_frames_total - sync_recorded_frames_total
        sync_warning_suppressed = self.live_sync_suppressed_current_take
        frames_in_sync = (
            abs(diff) <= self.final_sync_analysis_tolerance_frames
            or sync_warning_suppressed
        )

        # ── Option 3: split TC holes from genuinely missing files ────────────
        # tc_hole_count  = gap events during recording (frame arrived late enough
        #                  to round to ≥2 frame periods; file may still be present)
        # missing_frame_count = raw shortfall on disk vs wall-clock expectation
        #                       (max(0, expected − recorded), confirmed absent files)
        missing_frames_count = max(0, expected_frames_total - recorded_frames_total)
        # Confirmed disk-write failures reported live by cinepi-raw this take.
        # These explain a shortfall that produced no TC gap (storage too slow/
        # failing), so they are attributed in the verdict below.
        write_failures_this_take = max(
            int(self.write_failure_count_current_take),
            int(self.hw_write_failures or 0),
        )

        # ── Option 2: drop_frame_during_last_take only fires on genuine shortfall
        # A take that produced the right number of files doesn't carry a persistent
        # drop warning into the next take, even if TC holes were observed live.
        drop_during_last_take = (
            (not self.recording_was_preroll)
            and missing_frames_count > 0
        )
        self.redis_controller.set_value(
            ParameterKey.DROP_FRAME_DURING_LAST_TAKE.value,
            1 if drop_during_last_take else 0,
        )
        # drop_frame_count keeps its existing meaning (tc_hole_count) for
        # backward compatibility; tc_hole_count is the explicit named alias.
        self.redis_controller.set_value(
            ParameterKey.DROP_FRAME_COUNT.value,
            drop_frame_count_for_reporting,
        )
        self.redis_controller.set_value(
            ParameterKey.TC_HOLE_COUNT.value,
            drop_frame_count_for_reporting,
        )
        self.redis_controller.set_value(
            ParameterKey.MISSING_FRAME_COUNT.value,
            missing_frames_count,
        )
        if not quiet_summary:
            # Report TC timing and file integrity as a single precise verdict.
            #
            # Three distinct states:
            #  A) all files present + consecutive indices + TC has late-arrival
            #     events → timing irregularity only, no data loss.
            #  B) files missing (missing_frames_count > 0) or index gaps
            #     (segment_index_hole_frames_total > 0) → genuine data loss.
            #  C) no TC events, no missing files → clean take (covered by ✓).
            all_files_present = (missing_frames_count == 0)
            no_index_gaps = (segment_index_hole_frames_total == 0)

            if drop_frame_count_for_reporting > 0 and all_files_present and no_index_gaps:
                # Every frame is on disk and the DNG index is contiguous.
                # The TC values are not perfectly consecutive — some frames
                # arrived late (inter-frame gap ≥ 1.5× frame period) causing
                # the timecode counter to skip forward — but no data was lost.
                logging.info(
                    "TC timing: %d late-arrival event(s) created timecode "
                    "discontinuity/discontinuities in the DNG metadata. "
                    "All %d files present with contiguous indices — no data lost.",
                    drop_frame_count_for_reporting,
                    recorded_frames_total,
                )
            elif missing_frames_count > 0 and write_failures_this_take > 0:
                logging.warning(
                    "Missing frames: %d frame(s) not written to disk "
                    "(%d confirmed disk-write failure(s), %d TC gap event(s) during "
                    "recording). Storage could not keep up — use exFAT or ext4 for "
                    "sustained recording.",
                    missing_frames_count,
                    write_failures_this_take,
                    drop_frame_count_for_reporting,
                )
            elif missing_frames_count > 0:
                logging.warning(
                    "Missing frames: %d frame(s) not written to disk "
                    "(%d TC gap event(s) during recording).",
                    missing_frames_count,
                    drop_frame_count_for_reporting,
                )
            elif segment_index_hole_frames_total > 0:
                logging.warning(
                    "DNG index gaps: %d missing file slot(s) in sequence "
                    "(%d TC gap event(s) during recording).",
                    segment_index_hole_frames_total,
                    drop_frame_count_for_reporting,
                )

            if dropped_frame_slots_compensated:
                logging.info(
                    "Counting %d hole(s) as sync slot(s) to reconcile shortfall.",
                    dropped_frame_slots_compensated,
                )

        if sync_warning_suppressed:
            if not quiet_summary:
                logging.info(
                    "Skipping frame-sync warning because FPS or resolution changed during this take."
                )
        elif frames_in_sync:
            if not quiet_summary:
                if diff == 0:
                    logging.info("✓ All frames accounted for.")
                else:
                    logging.info(
                        "Frames within final tolerance: %+d frame difference between expected and recorded counts.",
                        diff,
                    )
        elif not quiet_summary:
            if diff < 0:
                logging.warning(
                    "Sensor ran fast: recorded %d extra frame(s) vs %d expected "
                    "(diff %+d, tolerance ±%g). Sensor correction factor may be needed.",
                    -diff,
                    expected_frames_total,
                    diff,
                    self.final_sync_analysis_tolerance_frames,
                )
            else:
                if write_failures_this_take > 0:
                    low_hint = (
                        "%d confirmed disk-write failure(s) this take — storage could "
                        "not keep up (use exFAT or ext4)." % write_failures_this_take
                    )
                else:
                    low_hint = "Check for dropped frames."
                logging.warning(
                    "Frame count low: %d fewer frame(s) than expected %d "
                    "(diff %+d, tolerance ±%g). %s",
                    diff,
                    expected_frames_total,
                    diff,
                    self.final_sync_analysis_tolerance_frames,
                    low_hint,
                )

        live_sync_warning_latched = (
            self.frames_off_sync_latched_current_take
            and not sync_warning_suppressed
        )
        if frames_in_sync and live_sync_warning_latched:
            # Final analysis is clean — clear the latch regardless of whether
            # this was a segmented or normal recording. The live check fires
            # conservatively early; the final disk count is the authoritative
            # verdict. A clean final analysis always unlatches.
            live_sync_warning_latched = False
            self.frames_off_sync_latched_current_take = False
            if not quiet_summary:
                if segmented_recording:
                    logging.info(
                        "Clearing live frame-sync warning after segmented final analysis accounted for all frames."
                    )
                else:
                    logging.info(
                        "Clearing live frame-sync warning: final analysis confirmed all frames present."
                    )
        if not frames_in_sync and not sync_warning_suppressed:
            self.frames_off_sync_latched_current_take = True

        all_frames_accounted = frames_in_sync
        self.redis_controller.set_value(
            ParameterKey.FRAMES_IN_SYNC.value,
            1 if frames_in_sync and not live_sync_warning_latched else 0,
        )

        current_correction_factor = self.fps_correction_factor_at_rec_start
        if not current_correction_factor or current_correction_factor <= 0:
            current_correction_factor = self._current_correction_factor()

        suggestion_value = current_correction_factor or 1.0

        if self.recording_was_preroll:
            pass
        elif all_frames_accounted:
            if segmented_recording:
                logging.info(
                    "No FPS correction suggestion from segmented recording; "
                    "wall-clock duration includes reconfigure gaps."
                )
            elif current_correction_factor:
                logging.info(
                    "Sensor timing OK: correction factor %.6f is active and matches the capture.",
                    current_correction_factor,
                )
            else:
                logging.info("Sensor timing OK: all frames accounted for (no correction factor active).")
        elif (
            expected_frames_float > 0
            and recorded_frames_total > 0
            and current_correction_factor
        ):
            multiplier = expected_frames_float / recorded_frames_total
            suggestion_value = current_correction_factor * multiplier
            _sensor = self.redis_controller.get_value(ParameterKey.SENSOR.value) or "unknown"
            try:
                _mode = int(self.redis_controller.get_value(ParameterKey.SENSOR_MODE.value))
            except (TypeError, ValueError):
                _mode = "?"
            _user_fps_str = f"{self.fps_at_rec_start:g}" if self.fps_at_rec_start else "?"
            _drift_pct = (1.0 - multiplier) * 100.0
            logging.info(
                "Sensor correction needed: %.6f suggested for %s mode %s at %s fps "
                "(sensor ran %.3f%% %s; update sensor_correction_factors.py).",
                suggestion_value,
                _sensor,
                _mode,
                _user_fps_str,
                abs(_drift_pct),
                "faster" if _drift_pct > 0 else "slower",
            )
        else:
            logging.info("Insufficient data to derive FPS correction factor suggestion.")

        self.redis_controller.set_value(
            ParameterKey.FPS_CORRECTION_SUGGESTION.value,
            f"{suggestion_value:.6f}",
        )

        self.fps_correction_factor_at_rec_start = None
        self.fps_at_rec_start = None
        self.fps_timeline = []


    def calculate_average_framerate_last_100_frames(self):
        if len(self.sensor_timestamps) > 1:
            timestamps_in_seconds = [ts / 1_000_000 for ts in self.sensor_timestamps]
            time_diffs = [t2 - t1 for t1, t2 in zip(timestamps_in_seconds, timestamps_in_seconds[1:])]
            
            if time_diffs:
                average_time_diff = sum(time_diffs) / len(time_diffs)
                average_fps = (1.0 / average_time_diff) * 1000 if average_time_diff != 0 else 0
                #logging.info(f"Average framerate of the last 100 frames: {average_fps:.6f} FPS : fps: {self.redis_controller.get_value('fps')}")
                
                return average_fps
            else:
                logging.warning("Time differences calculation resulted in an empty list.")
        else:
            logging.warning("Not enough sensor timestamps to calculate average framerate.")
        return None
    
    def adjust_fps(self, avg_framerate):
        if avg_framerate is None:
            return

        desired_fps = round(float(self.redis_controller.get_value('fps_user')))
        current_fps = float(self.redis_controller.get_value('fps'))
        
        fps_difference = desired_fps - avg_framerate
        
        # Calculate adaptive step size
        step_size = min(
            self.max_fps_adjustment,
            max(self.min_fps_adjustment, abs(fps_difference) / 10)
        )
        
        if abs(fps_difference) > self.min_fps_adjustment:
            if fps_difference > 0:
                new_fps = current_fps + step_size
            else:
                new_fps = current_fps - step_size
            
            # Ensure new FPS is not negative and doesn't overshoot the target
            new_fps = max(0, min(new_fps, desired_fps * 1.00001))  # Allow up to 1% overshoot
            
            # Round to 7 decimal places to avoid floating point precision issues
            new_fps = round(new_fps, 7)
            
            self.redis_controller.set_value('fps', new_fps)
            logging.info(f"Adjusted FPS from {current_fps} to {new_fps} (step size: {step_size:.5f})")
        else:
            logging.info(f"FPS is within acceptable range. Current: {current_fps}, Avg: {avg_framerate}, Desired: {desired_fps}")
