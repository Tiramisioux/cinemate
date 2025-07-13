import redis
import logging
import threading
import datetime
import json
from collections import deque
from module.redis_controller import ParameterKey

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
        
        self.recording_time_elapsed = "00:00"

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
        
        # initialise Redis key for GUI display
        self.redis_controller.set_value(ParameterKey.RECORDING_TIME_ELAPSED.value, self.recording_time_elapsed)
        
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
        
        self.redis_controller.set_value('drop_frame_detected', 0)
        
        self.cinepi_running = True
        
        self.framecount_changing = False
        self.last_framecount = 0
        self.last_framecount_check_time = datetime.datetime.now()
        self.framecount_check_interval = 1.0  # Default to 1 second, will be updated based on FPS
        
        self.redis_controller.set_value('rec', "0")
        
        self.max_fps_adjustment = 0.1  # Maximum adjustment per iteration
        self.min_fps_adjustment = 0.0001  # Minimum adjustment increment
        self.fps_adjustment_interval = 1.0  # Adjust every 1 second
        self.last_fps_adjustment_time = datetime.datetime.now()
        
        # ──  USER FPS TWEAK  ────────────────────────────────────────────────
        self.user_changing_fps = False          # True while the UI slider is moving
        self.last_fps_value     = float(self.redis_controller.get_value("fps") or 0)
        self.fps_change_timer   = None          # debounce timer


        self.current_framerate = None
        
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
                        self.current_framerate = stats_data.get('framerate', None)
                        
                        if color_temp:
                            self.colorTemp = color_temp

                        # Update Redis key for current buffer size if changed
                        if buffer_size is not None:
                            current_buffer = self.redis_controller.get_value('BUFFER')
                            # Redis returns bytes or None → normalise to int or None
                            current_buffer = int(current_buffer) if current_buffer is not None else None

                            if current_buffer != buffer_size:
                                self.redis_controller.set_value('BUFFER', buffer_size)
                                #logging.info(f"Buffer size changed to {buffer_size}")

                        # Update sensor timestamps
                        if sensor_timestamp is not None:
                            self.sensor_timestamps.append(int(sensor_timestamp))
                            self.calculate_average_framerate_last_100_frames()
                        
                        if len(self.sensor_timestamps) > 1:
                            self.calculate_current_framerate()

                        # Update framecount in Redis (only if it has changed, and doesnt report a lower number than before, except 0
                        self._maybe_publish_framecount(self.frame_count)

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
                                self.redis_controller.set_value('drop_frame_detected', 1)
                                
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
                        self.update_recording_time_elapsed()

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
        self.redis_controller.set_value('drop_frame_detected', 0)
        
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
        self.redis_controller.set_value('recording_time_elapsed', "00:00:00:00")
        logging.info("Framecount reset to 0.")
    
    def update_recording_time_elapsed(self):
        """Update Redis key with running recording time based on framecount."""
        try:
            rec = int(self.redis_controller.get_value(ParameterKey.REC.value) or 0)
            if not rec:
                # reset when framecount returns to 0
                if int(self.redis_controller.get_value(ParameterKey.FRAMECOUNT.value) or 0) == 0:
                    self.recording_time_elapsed = "00:00:00:00"
                    self.redis_controller.set_value(ParameterKey.RECORDING_TIME_ELAPSED.value, self.recording_time_elapsed)
                return

            framecount = int(self.redis_controller.get_value(ParameterKey.FRAMECOUNT.value) or 0)
            fps_user = float(self.redis_controller.get_value(ParameterKey.FPS_USER.value) or 0)
            if fps_user <= 0:
                fps_user = 1
            total_seconds = int(framecount // fps_user)
            frames = int(framecount % fps_user)

            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            seconds = int(total_seconds % 60)

            tc = f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"

            if tc != self.recording_time_elapsed:
                self.recording_time_elapsed = tc
                self.redis_controller.set_value(ParameterKey.RECORDING_TIME_ELAPSED.value, tc)
        except Exception as e:
            logging.error(f"Failed to update recording time: {e}")

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
                    self.recording_time_elapsed = "00:00:00:00"
                    self.redis_controller.set_value(ParameterKey.RECORDING_TIME_ELAPSED.value, self.recording_time_elapsed)
                    self.recording_start_time = datetime.datetime.now()
                    logging.info(f"Recording started at: {self.recording_start_time}")
                    
                    self.framerate = float(self.redis_controller.get_value('fps'))
                    self.allow_initial_zero = True

                elif value_str == '0':
                    if self.is_recording:
                        self.is_recording = False
                        if self.recording_start_time:
                            self.recording_end_time = datetime.datetime.now()
                            logging.info(f"Recording stopped at: {self.recording_end_time}")
                            self.analyze_frames()
                            self.framerate_values = []
                        else:
                            logging.warning("Recording stopped, but no recording start time was registered.")
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

    def analyze_frames(self):
        """
        Check that the number of DNGs written to disk matches the
        theoretical frame count for the recording.
        """
        # ------------------------------------------------------------------
        # 1) How many frames actually hit the SSD?
        # ------------------------------------------------------------------
        folders = self.ssd_monitor.get_latest_recording_infos()
        if not folders:
            logging.warning("No recent recording folders found — falling back to RAM counter.")
            recorded_frames_total = self.framecount
            sensor_count = 1
        else:
            recorded_frames_total = sum(n_dng for _, n_dng, _ in folders)
            sensor_count = len(folders)

            # One compact line instead of “N sensor(s) detected — …”
            logging.info(f"Total frames on disk: {recorded_frames_total}")

        # ------------------------------------------------------------------
        # 2) How long was the take?
        # ------------------------------------------------------------------
        if not (self.recording_start_time and self.recording_end_time):
            logging.warning("No start/end timestamps; cannot compute frame diff.")
            return
        duration = (self.recording_end_time - self.recording_start_time).total_seconds()
        logging.info(f"Recording duration in seconds: {duration:.3f}")

        # ------------------------------------------------------------------
        # 3) Expected frame count (fps × duration × sensor_count)
        # ------------------------------------------------------------------
        try:
            fps_expected = float(self.redis_controller.get_value("fps"))
            logging.info(f"Expected framerate retrieved from Redis: {fps_expected} FPS")
        except (TypeError, ValueError):
            logging.error("Expected FPS missing or invalid in Redis.")
            return

        expected_frames_total = int(round(fps_expected * duration * sensor_count))
        logging.info(f"Calculated expected number of frames: {expected_frames_total}")
        logging.info(f"Actual number of recorded frames: {recorded_frames_total}")

        # ------------------------------------------------------------------
        # 4) Compare and report
        # ------------------------------------------------------------------
        diff = expected_frames_total - recorded_frames_total
        if diff == 0:
            logging.info("✓ All frames accounted for.")
        else:
            logging.warning(f"Discrepancy detected: {diff:+d} frames difference "
                            f"between expected and recorded counts.")




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