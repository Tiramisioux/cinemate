import redis
import logging
import threading
import datetime
import json
from collections import deque

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
        
        self.last_is_recording_value = self.redis_controller.get_value('is_recording')


        
        self.drop_frame = False
        self.drop_frame_timer = None
        
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

                        # Update framecount in Redis only if it has changed
                        if self.frame_count is not None and self.frame_count != self.framecount:
                            self.framecount = self.frame_count
                            logging.debug(f"Updating framecount in Redis to {self.frame_count}")
                            self.redis_controller.set_value('framecount', self.frame_count)

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
                            if fps_difference > 1 and not self.drop_frame:
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

    def check_framecount_changing(self):
        current_time = datetime.datetime.now()
        time_elapsed = (current_time - self.last_framecount_check_time).total_seconds()

        if time_elapsed >= self.framecount_check_interval:
            if self.frame_count != self.last_framecount:
                if not self.framecount_changing:
                    self.framecount_changing = True
                    self.redis_controller.set_value('rec', "1")
                    logging.info("Framecount is changing")
            else:
                if self.framecount_changing:
                    self.framecount_changing = False
                    self.redis_controller.set_value('rec', "0")
                    logging.info("Framecount is stable")

            self.last_framecount = self.frame_count
            self.last_framecount_check_time = current_time
        
    def reset_framecount(self):
        self.framecount = 0
        self.frame_count = 0
        self.redis_controller.set_value('framecount', 0)
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
                    logging.info(f"Recording started at: {self.recording_start_time}")
                    self.framerate = float(self.redis_controller.get_value('fps'))

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