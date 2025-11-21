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
    def __init__(self, redis_controller, ssd_monitor, framerate_callback=None, host='localhost', port=6379, db=0):
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

        self.cinepi_running = True

        self.framecount_changing = False
        self.last_framecount = 0
        self.last_framecount_check_time = datetime.datetime.now()
        self.framecount_check_interval = 1.0  # Default to 1 second, will be updated based on FPS

        self.redis_controller.set_value('rec', "0")

        self.active_sensor_labels: set[str] = set()
        self.redis_controller.set_value(ParameterKey.FRAMES_IN_SYNC.value, 1)
        self.redis_controller.set_value(ParameterKey.FPS_CORRECTION_SUGGESTION.value, 1.0)
        
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

        self.recording_was_preroll = False


        self.start_listeners()

    def start_listeners(self):
        self.pubsub_stats.subscribe(self.channel_name_stats)
        self.pubsub_controls.subscribe(self.channel_name_controls)

        self.listener_thread_stats = threading.Thread(target=self.listen_stats)
        self.listener_thread_stats.daemon = True
        self.listener_thread_stats.start()

        self.listener_thread_controls = threading.Thread(target=self.listen_controls)
        self.listener_thread_controls.daemon = True
        self.listener_thread_controls.start()

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
            if new_count is None:
                return

            # ── not recording → freeze counter ───────────────────────────────────
            if not self.is_recording:
                if new_count == 0 and self.framecount != 0:
                    self.framecount = 0
                    self.redis_controller.set_value("framecount", 0)
                return
            # ─────────────────────────────────────────────────────────────────────

            # one allowed 0 right after Record (CinePi resets its counter once)
            if new_count == 0 and self.allow_initial_zero:
                self.framecount = 0
                self.redis_controller.set_value("framecount", 0)
                self.allow_initial_zero = False
                return

            # ── 1) strictly higher → accept & publish ───────────────────────────
            if new_count > self.framecount:
                self.framecount = new_count
                self.redis_controller.set_value("framecount", new_count)
                return

            # ── 2) equal → nothing to do ────────────────────────────────────────
            if new_count == self.framecount:
                return

            # ── 3) lower but *non-zero*  → IGNORE  (mitigates flicker) ──────────
            #     Only a real zero (encoder reset) is considered significant.
            if new_count < self.framecount and new_count != 0:
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

    @staticmethod
    def _expected_frame_counts(fps_expected: float | None, duration: float, sensor_count: int) -> tuple[int, float]:
        if fps_expected is None or fps_expected <= 0 or duration <= 0:
            return 0, 0.0

        sensor_effective = max(1, sensor_count)
        expected_float = fps_expected * duration * sensor_effective
        expected_int = int(math.floor(expected_float + 1e-6))
        return expected_int, expected_float

    def _update_frames_in_sync(self, stats_data: dict[str, object] | None = None) -> None:
        if stats_data is not None:
            self._update_active_sensors(stats_data)

        if not self.recording_start_time:
            # No reference point – assume healthy until a recording starts.
            self.redis_controller.set_value(ParameterKey.FRAMES_IN_SYNC.value, 1)
            return

        fps_expected = self._determine_expected_fps()
        if fps_expected is None or fps_expected <= 0:
            return

        if self.is_recording:
            end_for_calc = datetime.datetime.now()
        elif self.recording_end_time:
            end_for_calc = self.recording_end_time
        else:
            # Recording hasn’t officially started or stopped; keep the last known value.
            return

        duration = (end_for_calc - self.recording_start_time).total_seconds()
        if duration < 0:
            duration = 0.0

        sensor_count = self._current_sensor_count()
        expected_int, _ = self._expected_frame_counts(fps_expected, duration, sensor_count)
        recorded_frames = int(self.framecount or 0)

        in_sync = abs(expected_int - recorded_frames) <= 1
        self.redis_controller.set_value(
            ParameterKey.FRAMES_IN_SYNC.value,
            1 if in_sync else 0,
        )

    def listen_stats(self):
        for message in self.pubsub_stats.listen():
            if message['type'] == 'message':
                message_data = message['data'].decode('utf-8').strip()
                if message_data.startswith("{") and message_data.endswith("}"):
                    try:
                        stats_data = json.loads(message_data)
                        buffer_size = stats_data.get('bufferSize', None)
                        self.frame_count = stats_data.get('frameCount', None)
                        color_temp = stats_data.get('colorTemp', None)
                        sensor_timestamp = stats_data.get('sensorTimestamp', None)
                        timestamp = stats_data.get('timestamp')
                        timestamp_cam0 = stats_data.get('timestamp_cam0')
                        timestamp_cam1 = stats_data.get('timestamp_cam1')
                        self.current_framerate = stats_data.get('framerate', None)

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

                        # Update Redis key for current buffer size if changed
                        if buffer_size is not None:
                            current_buffer = self.redis_controller.get_value(ParameterKey.BUFFER.value)
                            # Redis returns bytes or None → normalise to int or None
                            current_buffer = int(current_buffer) if current_buffer is not None else None

                            if current_buffer != buffer_size:
                                self.redis_controller.set_value(ParameterKey.BUFFER.value, buffer_size)
                                #logging.info(f"Buffer size changed to {buffer_size}")

                        # Update sensor timestamps
                        if sensor_timestamp is not None:
                            self.sensor_timestamps.append(int(sensor_timestamp))
                            self.calculate_average_framerate_last_100_frames()
                        
                        if len(self.sensor_timestamps) > 1:
                            self.calculate_current_framerate()

                        # Update framecount in Redis (only if it has changed, and doesnt report a lower number than before, except 0
                        self._maybe_publish_framecount(self.frame_count)
                        self._update_frames_in_sync(stats_data)

                        # Check and set buffering status if changed
                        is_buffering = buffer_size > 0 if buffer_size is not None else False
                        current_buffering_status = self.redis_controller.get_value('is_buffering')
                        new_buffering_status = 1 if is_buffering else 0
                        if current_buffering_status is None or int(current_buffering_status) != new_buffering_status:
                            logging.debug(f"Updating is_buffering to {new_buffering_status}")
                            self.redis_controller.set_value('is_buffering', new_buffering_status)

                        # Add current framerate value to the list
                        if self.current_framerate is not None:
                            self.framerate_values.append(self.current_framerate)
                            
                        # Check for framerate deviation
                        expected_fps = float(self.redis_controller.get_value('fps'))
                        if self.current_framerate is not None:
                            fps_difference = abs((self.current_framerate) - expected_fps)
                            # print(f"Expected FPS: {expected_fps}, Actual FPS: {self.current_framerate*1000}")
                            # print(f"FPS difference: {fps_difference}")
                            
                            # do NOT raise drop-frame while the user is changing fps
                            if fps_difference > 1 and not self.drop_frame and not self.user_changing_fps:

                                self.drop_frame = True
                                logging.info("Drop frame detected")
                                
                                # Set a timer to reset the drop_frame flag after 0.5 seconds
                                if self.drop_frame_timer:
                                    self.drop_frame_timer.cancel()
                                self.drop_frame_timer = threading.Timer(0.5, self.reset_drop_frame)
                                self.drop_frame_timer.start()

                            # Update framecount check interval based on current FPS
                            if self.current_framerate == 0 or None:
                                framecount_fps = 1
                            else:
                                framecount_fps = self.current_framerate
                            self.framecount_check_interval = max(0.5, 2 / framecount_fps)

                        # Check if framecount is changing
                        self.check_framecount_changing()
                        
                        # # Calculate average framerate of last 100 frames
                        # avg_framerate = self.calculate_average_framerate_last_100_frames()

                        # # Adjust FPS if necessary
                        # current_time = datetime.datetime.now()
                        # if (current_time - self.last_fps_adjustment_time).total_seconds() >= self.fps_adjustment_interval:
                        #     self.adjust_fps(avg_framerate)
                        #     self.last_fps_adjustment_time = current_time


                    except json.JSONDecodeError as e:
                        logging.error(f"Failed to parse JSON data: {e}")
                    except TypeError as e:
                        logging.error(f"Type error in stats data: {e}")
                else:
                    logging.warning(f"Received unexpected data format: {message_data}")
                    
    def reset_drop_frame(self):
        self.drop_frame = False
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

        
    def check_framecount_changing(self):
        """
        Toggle Redis key 'rec':
            • rec=1  as soon as frameCount rises
            • rec=0  only after <rec_hold_seconds> of no rise, OR when frameCount hits 0
        Any lower-but-non-zero values are ignored entirely.
        """
        now = datetime.datetime.now()
        new = self.frame_count
        old = self.last_framecount               # last *accepted* count

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

            self.last_rise_time = now             # remember when we last rose
            self.last_framecount = new
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
                    self.reset_framecount()
                    self.recording_start_time = datetime.datetime.now()
                    self.recording_end_time = None
                    logging.info(f"Recording started at: {self.recording_start_time}")

                    self.recording_was_preroll = self._storage_preroll_active()

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

                    self.framerate = float(self.redis_controller.get_value('fps_user'))  # keep if you still use it elsewhere
                    self.allow_initial_zero = True


                elif value_str == '0':
                    if self.is_recording:
                        self.is_recording = False
                        if self.recording_start_time:
                            self.recording_end_time = datetime.datetime.now()
                            logging.info(f"Recording stopped at: {self.recording_end_time}")
                            self._update_frames_in_sync()
                            try:
                                self.analyze_frames()
                            finally:
                                self.recording_was_preroll = False
                            self.framerate_values = []
                        else:
                            logging.warning("Recording stopped, but no recording start time was registered.")
                            self.recording_was_preroll = False
                    self.allow_initial_zero = True
                    
            elif changed_key == "fps":
                try:
                    self._note_fps_change(float(value_str))
                except ValueError:
                    logging.warning(f"Ignoring invalid fps value {value_str!r}")
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
    _IDX_RE = re.compile(r'C(\d{5,})', re.IGNORECASE)

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
        Single pass: count valid DNG files and find the highest C##### index.
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
        # --------------------------- 1) collect candidate dirs -----------------
        folders = self.ssd_monitor.get_latest_recording_infos()
        per_sensor = []   # (label, fs_count|None, monitor_count|None, last_idx|None, last_name|None)

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
                    c, li, ln = self._stable_dng_count(resolved)
                    fs_count, last_idx, last_name = c, li, ln
                    if fs_count is None:
                        fs_count = 0

                per_sensor.append((label, fs_count, monitor_count, last_idx, last_name))

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

            sensor_count_effective = sum(1 for _, c, _, _ in final_counts if c > 0)
            recorded_frames_total = sum(c for _, c, _, _ in final_counts)

            # Diagnostics
            for label, c, li, ln in final_counts:
                if ln:
                    logging.info(f"{label}: {c} DNGs (last={ln}, idx={li})")
                else:
                    logging.info(f"{label}: {c} DNGs")

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
        logging.info(f"Recording duration in seconds (start→end): {duration:.6f}")

        # ------------------------- expected FPS (locked) ----------------------
        if self.fps_at_rec_start is not None and self.fps_at_rec_start > 0:
            fps_expected = self.fps_at_rec_start
            logging.info(f"Using FPS locked at record start: {fps_expected:.6f}")
        else:
            # hard fallback if start FPS was missing
            try:
                fps_expected = float(self.redis_controller.get_value('fps'))
                logging.info(f"Using configured FPS (fallback): {fps_expected:.6f}")
            except (TypeError, ValueError):
                logging.error("Expected FPS missing/invalid; aborting expected-frame calc.")
                return

        # ----------------------- expected frames (per sensor) -----------------
        # Discrete sampling: frames are whole numbers; floor avoids the +1 overshoot at the stop edge.
        expected_frames_total, expected_frames_float = self._expected_frame_counts(
            fps_expected,
            duration,
            sensor_count_effective,
        )

        logging.info(f"Calculated expected number of frames: {expected_frames_total}")
        logging.info(f"Actual number of recorded frames: {recorded_frames_total}")

        diff = expected_frames_total - recorded_frames_total
        frames_in_sync = abs(diff) <= 1

        if frames_in_sync:
            if diff == 0:
                logging.info("✓ All frames accounted for.")
            else:
                logging.info(
                    "Frames within tolerance: %+d frame difference between expected and recorded counts.",
                    diff,
                )
        else:
            logging.warning(
                f"Discrepancy detected: {diff:+d} frames difference between expected and recorded counts."
            )

        all_frames_accounted = frames_in_sync
        self.redis_controller.set_value(
            ParameterKey.FRAMES_IN_SYNC.value,
            1 if frames_in_sync else 0,
        )

        current_correction_factor = self.fps_correction_factor_at_rec_start
        if not current_correction_factor or current_correction_factor <= 0:
            current_correction_factor = self._current_correction_factor()

        suggestion_value = current_correction_factor or 1.0

        if self.recording_was_preroll:
            logging.info(
                "Skipping FPS correction suggestion: storage pre-roll recording (keeping %.6f).",
                suggestion_value,
            )
        elif all_frames_accounted:
            if current_correction_factor:
                logging.info(
                    "No FPS correction adjustment needed; existing factor %.6f matches the capture.",
                    current_correction_factor,
                )
            else:
                logging.info("No FPS correction suggestion needed: all frames accounted for.")
        elif (
            expected_frames_float > 0
            and recorded_frames_total > 0
            and current_correction_factor
        ):
            multiplier = expected_frames_float / recorded_frames_total
            suggestion_value = current_correction_factor * multiplier
            logging.info(
                "Suggested FPS correction factor based on recording: %.6f (multiplier %.6f × current %.6f)",
                suggestion_value,
                multiplier,
                current_correction_factor,
            )
        else:
            logging.info("Insufficient data to derive FPS correction factor suggestion.")

        self.redis_controller.set_value(
            ParameterKey.FPS_CORRECTION_SUGGESTION.value,
            f"{suggestion_value:.6f}",
        )

        self.fps_correction_factor_at_rec_start = None


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