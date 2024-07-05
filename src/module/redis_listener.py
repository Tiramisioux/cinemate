# redis_listener.py

import redis
import logging
import threading
import time
import statistics
import datetime
import json

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
        
        self.recording_start_time = None
        self.recording_end_time = None
        
        self.redis_controller = redis_controller
        self.framerate_callback = framerate_callback  # Callback function for framerate changes
        
        self.framerate = float(self.redis_controller.get_value('fps_actual'))
        
        self.bufferSize = 0
        self.colorTemp = 0
        self.focus = 0
        self.frameCount = 0
        
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
                        self.framerate = stats_data.get('framerate', None) 
                        
                        # If framerate changes, call the callback function
                        if self.framerate is not None and self.framerate_callback:
                            self.framerate_callback(self.framerate)
                        
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

    def analyze_frames(self):
        if self.recording_start_time and self.recording_end_time:
            time_diff_seconds = (self.recording_end_time - self.recording_start_time).total_seconds()
            expected_frames = int(self.framerate * time_diff_seconds)
        else:
            logging.warning("Cannot calculate expected frames: Recording start or end time not registered.")
        
        num_frames = self.frameCount  # Use the frame count received from listen_stats
        
        if num_frames > 0:
            average_framerate = num_frames / time_diff_seconds
            self.framerate_values.append(average_framerate)
            min_framerate = min(self.framerate_values)
            max_framerate = max(self.framerate_values)
            median_framerate = statistics.median(self.framerate_values)
            stdev_framerate = statistics.stdev(self.framerate_values) if len(self.framerate_values) > 1 else 0
            variance_framerate = statistics.variance(self.framerate_values) if len(self.framerate_values) > 1 else 0
            cv_framerate = stdev_framerate / average_framerate if average_framerate != 0 else 0
            
            logging.info(f"Total number of frames registered: {num_frames}")
            logging.info(f"Total number of frames expected: {expected_frames}")
            
            logging.info(f"Average framerate value: {average_framerate}")
            logging.info(f"Minimum framerate value: {min_framerate}")
            logging.info(f"Maximum framerate value: {max_framerate}")
            logging.info(f"Median framerate value: {median_framerate}")
            logging.info(f"Standard deviation of framerate values: {stdev_framerate}")
            logging.info(f"Variance of framerate values: {variance_framerate}")
            logging.info(f"Coefficient of variation of framerate values: {cv_framerate}")
        else:
            logging.warning("No framerate values recorded.")
