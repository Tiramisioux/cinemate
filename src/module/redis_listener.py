import redis
import logging
import threading
import statistics
import datetime
import json
from collections import deque

class RedisListener:
    def __init__(self, redis_controller, framerate_callback=None, host='localhost', port=6379, db=0):
        self.redis_client = redis.StrictRedis(host=host, port=port, db=db)
        
        self.pubsub_stats = self.redis_client.pubsub()
        self.pubsub_controls = self.redis_client.pubsub()
        self.channel_name_stats = "cp_stats"
        self.channel_name_controls = "cp_controls"

        self.stdev_threshold = 2.0
        self.lock = threading.Lock()
        self.is_recording = False
        self.framerate_values = []  # Initialize the framerate_values attribute
        self.sensor_timestamps = deque(maxlen=100)  # Store the last 100 sensor timestamps
        
        self.recording_start_time = None
        self.recording_end_time = None
        
        self.redis_controller = redis_controller
        self.framerate_callback = framerate_callback  # Callback function for framerate changes
        
        self.framerate = float(self.redis_controller.get_value('fps_actual'))
        
        self.bufferSize = 0
        self.colorTemp = 0
        self.focus = 0
        self.frameCount = 0
        
        self.cinepi_running = True
        
        self.start_listeners()

    def start_listeners(self):
        # Subscribe to the channels
        self.pubsub_stats.subscribe(self.channel_name_stats)
        self.pubsub_controls.subscribe(self.channel_name_controls)

        # Start the listener threads
        self.listener_thread_stats = threading.Thread(target=self.listen_stats)
        self.listener_thread_stats.daemon = True
        self.listener_thread_stats.start()

        self.listener_thread_controls = threading.Thread(target=self.listen_controls)
        self.listener_thread_controls.daemon = True
        self.listener_thread_controls.start()

    def listen_stats(self):
        for message in self.pubsub_stats.listen():
            if message['type'] == 'message':
                message_data = message['data'].decode('utf-8').strip()
                if message_data.startswith("{") and message_data.endswith("}"):
                    try:
                        stats_data = json.loads(message_data)
                        self.bufferSize = stats_data.get('bufferSize', None)
                        self.colorTemp = stats_data.get('colorTemp', None)
                        self.focus = stats_data.get('focus', None)        
                        self.frameCount = stats_data.get('frameCount', None)
                        self.sensorTimestamp = stats_data.get('sensorTimestamp', None)
                        
                        # Update sensor timestamps
                        if self.sensorTimestamp is not None:
                            self.sensor_timestamps.append(int(self.sensorTimestamp))
                            self.calculate_average_framerate_last_100_frames()
                            
                        if len(self.sensor_timestamps) > 1:    
                            self.calculate_current_framerate()                         
                        
                        # If framerate changes, call the callback function
                        if self.framerate is not None and self.framerate_callback:
                            self.framerate_callback(self.framerate)

                        if self.sensorTimestamp:
                            self.redis_controller.get_value('cinepi_running') == "True"

                        else:
                            self.redis_controller.get_value('cinepi_running') == "False"
                        
                        # Update frame count and framerate
                        new_frame_count = stats_data.get('frameCount', None)
                        if new_frame_count is not None:
                            if self.frameCount == 0:
                                self.frameCount = new_frame_count
                            elif new_frame_count > self.frameCount:
                                self.frameCount = new_frame_count
                                # If frame count increases, assume recording has started
                                if not self.is_recording:
                                    self.is_recording = True
                                    self.recording_start_time = datetime.datetime.now()
                                    logging.info(f"Recording started at: {self.recording_start_time}")
                                    self.framerate = stats_data.get('framerate', None)
                    
                        # Add current framerate value to the list
                        current_framerate = stats_data.get('framerate', None)
                        if current_framerate is not None:
                            self.framerate_values.append(current_framerate)

                    except json.JSONDecodeError as e:
                        logging.error(f"Failed to parse JSON data: {e}")
                else:
                    logging.warning(f"Received unexpected data format: {message_data}")

    def listen_controls(self):
        for message in self.pubsub_controls.listen():
            if message["type"] == "message":
                changed_key = message["data"].decode('utf-8')
                with self.lock:
                    value = self.redis_client.get(changed_key)
                    value_str = value.decode('utf-8')

                    if changed_key == 'is_recording':
                        if value_str == '1':
                            self.is_recording = True
                            self.recording_start_time = datetime.datetime.now()
                            logging.info(f"Recording started at: {self.recording_start_time}")
                            self.framerate = float(self.redis_controller.get_value('fps'))
                        elif value_str == '0':
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
            # Convert timestamps from microseconds to seconds
            timestamps_in_seconds = [ts / 1_000_000 for ts in self.sensor_timestamps]
            # Calculate time differences between consecutive sensor timestamps
            time_diffs = [t2 - t1 for t1, t2 in zip(timestamps_in_seconds, timestamps_in_seconds[1:])]
            
            if time_diffs:
                # Calculate the average time difference in seconds
                average_time_diff = sum(time_diffs) / len(time_diffs)
                logging.debug(f"Time differences between consecutive frames: {time_diffs}")
                logging.debug(f"Average time difference: {average_time_diff}")
                
                # Calculate the current framerate in FPS with higher precision
                self.current_framerate = 1.0 / average_time_diff if average_time_diff != 0 else 0
                logging.debug(f"Calculated current framerate: {self.current_framerate:.6f} FPS")
            else:
                logging.warning("Time differences calculation resulted in an empty list.")
                self.current_framerate = None
        else:
            self.current_framerate = None
            #logging.warning("Not enough sensor timestamps to calculate framerate.")
        self.redis_controller.set_value('fps_actual', (self.current_framerate*1000))

    def analyze_frames(self):
        if self.recording_start_time and self.recording_end_time:
            time_diff_seconds = (self.recording_end_time - self.recording_start_time).total_seconds()
            fps_value = self.redis_controller.get_value('fps')
            try:
                fps_float = float(fps_value)  # Convert the retrieved value to a float
                expected_frames = int(fps_float * time_diff_seconds)
                recorded_frames = self.frameCount  # The number of frames recorded
                
                logging.info(f"Total number of recorded frames: {recorded_frames}")
                logging.info(f"Total number of expected frames: {expected_frames}")
            except (TypeError, ValueError) as e:
                logging.error(f"Error converting fps value to float: {e}")
        else:
            logging.warning("Cannot calculate expected frames: Recording start or end time not registered.")



    def calculate_average_framerate_last_100_frames(self):
        if len(self.sensor_timestamps) > 1:
            # Convert timestamps from microseconds to seconds
            timestamps_in_seconds = [ts / 1_000_000 for ts in self.sensor_timestamps]
            # Calculate time differences between consecutive sensor timestamps
            time_diffs = [t2 - t1 for t1, t2 in zip(timestamps_in_seconds, timestamps_in_seconds[1:])]
            
            if time_diffs:
                # Calculate the average time difference in seconds
                average_time_diff = sum(time_diffs) / len(time_diffs)
                average_fps = (1.0 / average_time_diff)*1000 if average_time_diff != 0 else 0
                #logging.info(f"Average framerate of the last 100 frames: {average_fps:.6f} FPS")
            else:
                logging.warning("Time differences calculation resulted in an empty list.")
        else:
            logging.warning("Not enough sensor timestamps to calculate average framerate.")
