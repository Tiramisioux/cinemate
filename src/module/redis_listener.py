import redis
import logging
import threading
import datetime
import json
from collections import deque
from collections import defaultdict

from module.redis_controller import ParameterKey


class RedisListener:
    """
    Drop-in replacement that makes FRAMECOUNT monotonic ─ eliminates the
    259 ↔ 260 ping-pong you see when two sensors post different counts.
    """

    # ───────────────────────── INITIALISATION ──────────────────────────
    def __init__(
        self,
        redis_controller,
        framerate_callback=None,
        host="localhost",
        port=6379,
        db=0,
    ):
        # Redis connections ------------------------------------------------
        self.redis_client = redis.StrictRedis(host=host, port=port, db=db)
        self.pubsub_stats = self.redis_client.pubsub()
        self.pubsub_controls = self.redis_client.pubsub()
        self.channel_name_stats = "cp_stats"
        self.channel_name_controls = "cp_controls"

        # External handles -------------------------------------------------
        self.redis_controller = redis_controller
        self.framerate_callback = framerate_callback
        
        self._callbacks = defaultdict(list)

        # Runtime state ----------------------------------------------------
        self.lock = threading.Lock()
        self.bufferSize = 0
        self.colorTemp = 0
        self.focus = 0

        #   Frame-related
        self.frame_count = 0          # last raw value received
        self.framecount = 0           # value actually written to Redis
        self.redis_controller.set_value(ParameterKey.FRAMECOUNT.value, 0)

        #   Monotonic guard  (★ new ★)
        self.latest_framecount = 0    # highest value seen in this take
        self.decrease_slack = 2       # tolerate  ≤2 frame back-steps

        #   Recording bookkeeping
        self.is_recording = False
        self.last_is_recording_value = self.redis_controller.get_value(
            ParameterKey.IS_RECORDING.value
        )
        self.recording_start_time = None
        self.recording_end_time = None

        #   FPS / timing
        self.framerate = float(
            self.redis_controller.get_value(ParameterKey.FPS_ACTUAL.value, 0)
        )
        self.current_framerate = None
        self.sensor_timestamps = deque(maxlen=100)
        self.set_frame_count_increase_tolerance()
        self.framecount_changing = False
        self.last_framecount = 0
        self.last_framecount_check_time = datetime.datetime.now()
        self.framecount_check_interval = 1.0

        #   Misc flags
        self.drop_frame = False
        self.drop_frame_timer = None

        # Start threads ----------------------------------------------------
        self.start_listeners()

    # ─────────────────────── HELPERS & SETUP ────────────────────────────
    def start_listeners(self):
        self.pubsub_stats.subscribe(self.channel_name_stats)
        self.pubsub_controls.subscribe(self.channel_name_controls)

        self.listener_thread_stats = threading.Thread(
            target=self.listen_stats, daemon=True
        )
        self.listener_thread_stats.start()

        self.listener_thread_controls = threading.Thread(
            target=self.listen_controls, daemon=True
        )
        self.listener_thread_controls.start()

    def set_frame_count_increase_tolerance(self):
        if self.framerate > 0:
            frame_interval = 1 / self.framerate
            self.frame_count_increase_tolerance = 3 * frame_interval
        else:
            self.frame_count_increase_tolerance = 0.5
            
    def on(self, event_name: str, fn):
        print('on')
        """Register a callback that will be invoked as  on(event_name)."""
        self._callbacks[event_name].append(fn)

    def _fire(self, event_name: str, *args, **kw):
        print('fire')
        for fn in self._callbacks[event_name]:
            try:
                fn(*args, **kw)
            except Exception:                # never let a bad handler kill the loop
                logging.exception("RedisListener callback failed")

    # ──────────────────────── MONOTONIC FILTER ──────────────────────────
    def _update_global_framecount(self, new_value: int) -> None:
        """
        Accepts only forward progress in frame numbers.
        Tiny decreases due to the second sensor are ignored.
        """
        # Ignore a value that is well behind what we already published
        if new_value + self.decrease_slack < self.latest_framecount:
            return

        # Publish genuine forward progress
        if new_value > self.latest_framecount:
            self.latest_framecount = new_value
            self.redis_controller.set_value(
                ParameterKey.FRAMECOUNT.value, new_value
            )

    # ─────────────────────────── STAT LISTENER ──────────────────────────
    def listen_stats(self):
        for message in self.pubsub_stats.listen():
            if message["type"] != "message":
                continue

            data = message["data"].decode("utf-8").strip()
            if not (data.startswith("{") and data.endswith("}")):
                logging.warning(f"Unexpected stats payload: {data}")
                continue

            try:
                stats = json.loads(data)
            except json.JSONDecodeError as e:
                logging.error(f"Stats JSON error: {e}")
                continue

            # ---------- Extract values ----------
            buffer_size = stats.get("bufferSize")
            self.frame_count = stats.get("frameCount")
            color_temp = stats.get("colorTemp")
            sensor_ts = stats.get("sensorTimestamp")
            self.current_framerate = stats.get("framerate")

            if color_temp is not None:
                self.colorTemp = color_temp

            # ---------- Buffer size ----------
            current_buffer = self.redis_controller.get_value(
                ParameterKey.BUFFER.value
            )
            if (
                buffer_size is not None
                and (current_buffer is None or int(current_buffer) != buffer_size)
            ):
                self.redis_controller.set_value(
                    ParameterKey.BUFFER.value, buffer_size
                )

            # ---------- Sensor timestamps / instant FPS ----------
            if sensor_ts is not None:
                self.sensor_timestamps.append(int(sensor_ts))
                self.calculate_current_framerate()

            # ---------- Frame-count (★ monotonic logic ★) ----------
            if self.frame_count is not None:
                self._update_global_framecount(int(self.frame_count))

            # ---------- Buffering flag ----------
            is_buffering = bool(buffer_size) if buffer_size is not None else False
            new_flag = 1 if is_buffering else 0
            old_flag = self.redis_controller.get_value(
                ParameterKey.IS_BUFFERING.value
            )
            if old_flag is None or int(old_flag) != new_flag:
                self.redis_controller.set_value(
                    ParameterKey.IS_BUFFERING.value, new_flag
                )

            # ---------- More housekeeping ----------
            if self.current_framerate:
                self.framecount_check_interval = max(
                    0.5, 2 / self.current_framerate
                )
            self.check_framecount_changing()

    # ───────────────────────── CONTROL LISTENER ─────────────────────────
    def listen_controls(self):
        for message in self.pubsub_controls.listen():
            if message["type"] != "message":
                continue

            key = message["data"].decode("utf-8")
            value_bytes = self.redis_client.get(key)
            if value_bytes is None:
                continue
            value_str = value_bytes.decode("utf-8")

            # Only act on a real change
            if key == ParameterKey.IS_RECORDING.value:
                if value_str == self.last_is_recording_value:
                    continue
                self.last_is_recording_value = value_str

                if value_str == "1":          # ── Recording started
                    self.is_recording = True
                    self._fire("recording_started")
                    self.reset_framecount()
                    self.recording_start_time = datetime.datetime.now()
                    logging.info(
                        f"Recording started: {self.recording_start_time}"
                    )

                elif value_str == "0":        # ── Recording stopped
                    self._fire("recording_stopped")
                    if self.is_recording:
                        self.is_recording = False
                        self.recording_end_time = datetime.datetime.now()
                        logging.info(
                            f"Recording stopped: {self.recording_end_time}"
                        )
                        self.analyze_frames()

    # ────────────────────────── SMALL UTILITIES ────────────────────────
    def calculate_current_framerate(self):
        if len(self.sensor_timestamps) < 2:
            return

        secs = [ts / 1_000_000 for ts in self.sensor_timestamps]
        diffs = [b - a for a, b in zip(secs, secs[1:])]
        if not diffs:
            return

        avg_dt = sum(diffs) / len(diffs)
        fps = 1.0 / avg_dt if avg_dt else 0
        self.current_framerate = fps
        self.redis_controller.set_value(ParameterKey.FPS_ACTUAL.value, fps)

    def check_framecount_changing(self):
        now = datetime.datetime.now()
        if (now - self.last_framecount_check_time).total_seconds() < self.framecount_check_interval:
            return

        changing = self.frame_count != self.last_framecount
        flag = "1" if changing else "0"
        self.redis_controller.set_value(ParameterKey.REC.value, flag)

        self.framecount_changing = changing
        self.last_framecount = self.frame_count
        self.last_framecount_check_time = now

    def reset_framecount(self):
        self.framecount = 0
        self.frame_count = 0
        self.latest_framecount = 0          # ← clear monotonic guard
        self.redis_controller.set_value(ParameterKey.FRAMECOUNT.value, 0)
        logging.info("Framecount reset to 0.")

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
        self.redis_controller.set_value(ParameterKey.FPS_ACTUAL.value, self.current_framerate)

    def analyze_frames(self):
        if self.recording_start_time and self.recording_end_time:
            time_diff_seconds = (self.recording_end_time - self.recording_start_time).total_seconds()
            logging.info(f"Recording duration in seconds: {time_diff_seconds}")

            fps_value = self.redis_controller.get_value(ParameterKey.FPS.value)
            try:
                fps_float = float(fps_value)
                logging.info(f"Expected framerate retrieved from Redis: {fps_float} FPS")

                expected_frames = int(fps_float * time_diff_seconds)
                logging.info(f"Calculated expected number of frames: {expected_frames}")

                recorded_frames = self.framecount
                logging.info(f"Actual number of recorded frames: {recorded_frames}")

                frame_difference = expected_frames - recorded_frames
                if frame_difference != 0:
                    logging.warning(f"Discrepancy detected: {frame_difference} frames difference between expected and recorded counts.")

            except (TypeError, ValueError) as e:
                logging.error(f"Error converting fps value to float: {e}")
        else:
            logging.warning("Cannot calculate expected frames: Recording start or end time not registered.")

    def calculate_average_framerate_last_100_frames(self):
        if len(self.sensor_timestamps) > 1:
            timestamps_in_seconds = [ts / 1_000_000 for ts in self.sensor_timestamps]
            time_diffs = [t2 - t1 for t1, t2 in zip(timestamps_in_seconds, timestamps_in_seconds[1:])]
            
            if time_diffs:
                average_time_diff = sum(time_diffs) / len(time_diffs)
                average_fps = (1.0 / average_time_diff) * 1000 if average_time_diff != 0 else 0
                #logging.info(f"Average framerate of the last 100 frames: {average_fps:.6f} FPS : fps: {self.redis_controller.get_value(ParameterKey.FPS.value)}")
                
                return average_fps
            else:
                logging.warning("Time differences calculation resulted in an empty list.")
        else:
            logging.warning("Not enough sensor timestamps to calculate average framerate.")
        return None
    
    def adjust_fps(self, avg_framerate):
        if avg_framerate is None:
            return

        desired_fps = round(float(self.redis_controller.get_value(ParameterKey.FPS_USER.value)))
        current_fps = float(self.redis_controller.get_value(ParameterKey.FPS.value))
        
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

            self.redis_controller.set_value(ParameterKey.FPS.value, new_fps)
            logging.info(f"Adjusted FPS from {current_fps} to {new_fps} (step size: {step_size:.5f})")
        else:
            logging.info(f"FPS is within acceptable range. Current: {current_fps}, Avg: {avg_framerate}, Desired: {desired_fps}")