import logging
import threading
import time
import json
import os
from collections import deque
import psutil

# Set up a custom logger for the TimeKeeper class
timekeeper_logger = logging.getLogger('timekeeper')
timekeeper_logger.setLevel(logging.INFO)

# Create a file handler for the logger
file_handler = logging.FileHandler('/home/pi/cinemate/src/logs/system.log')
file_handler.setLevel(logging.INFO)

# Add the handler to the logger without any formatter
timekeeper_logger.addHandler(file_handler)

class TimeKeeper:
    def __init__(self, redis_controller, check_interval=0.1, target_framerate=25.0, max_deviation=0.3, outlier_threshold=2.0, outlier_reset_time=10.0):
        self.redis_controller = redis_controller
        self.lock = threading.Lock()
        self.is_running = True
        self.check_interval = check_interval

        self.target_framerate = target_framerate  # User-selected frame rate
        self.current_framerate = target_framerate  # Initialize current_framerate
        self.frame_count = 0  # Initialize frame count
        self.recording = False  # Recording state
        self.cumulative_deviation = 0  # Track the cumulative deviation
        self.outlier_threshold = outlier_threshold  # Threshold for detecting outliers
        self.outlier_flag = False  # Track if an outlier was detected recently
        self.outlier_reset_time = outlier_reset_time  # Time frame to reset outlier flag
        self.last_outlier_time = 0  # Last time an outlier was detected

        self.min_frame_duration = 1000000 / (self.target_framerate + max_deviation)
        self.max_frame_duration = 1000000 / (self.target_framerate - max_deviation)
        self.mean_frame_duration = 1000000 / self.target_framerate

        self.listener_thread = threading.Thread(target=self.listen)
        self.listener_thread.daemon = True
        self.listener_thread.start()

        self.recording_thread = threading.Thread(target=self.monitor_recording)
        self.recording_thread.daemon = True
        self.recording_thread.start()

    def detect_outlier(self, frame_duration):
        # Simple outlier detection using z-score method or a fixed threshold
        deviation = abs(frame_duration - self.mean_frame_duration)
        z_score = deviation / self.mean_frame_duration
        return z_score > self.outlier_threshold

    def listen(self):
        pubsub = self.redis_controller.redis_client.pubsub()
        pubsub.subscribe('cp_stats')

        for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    stats_data = json.loads(message['data'].decode('utf-8').strip())
                    framerate = stats_data.get('framerate', None)
                    if framerate is not None and framerate > 0 and self.recording:
                        with self.lock:
                            self.current_framerate = float(framerate)
                            self.frame_count += 1  # Increment frame count
                            frame_duration = 1000000 / self.current_framerate  # Calculate frame duration in microseconds

                            if self.detect_outlier(frame_duration):
                                self.outlier_flag = True
                                self.last_outlier_time = time.time()
                                frame_duration = self.mean_frame_duration  # Replace outlier duration with mean duration
                            else:
                                if time.time() - self.last_outlier_time > self.outlier_reset_time:
                                    self.outlier_flag = False

                            deviation = 40000 - frame_duration
                            self.cumulative_deviation += deviation

                            # Collect system stats
                            cpu_usage = psutil.cpu_percent()
                            memory_info = psutil.virtual_memory()
                            temperature = psutil.sensors_temperatures().get('cpu-thermal', [None])[0]
                            temp = temperature.current if temperature else 0
                            
                            # Calculate corrected frame duration
                            frame_duration_corrected = 40000 + self.cumulative_deviation

                            # Clamp frame duration correction to ensure framerate stays within the 0.4 frame deviation limit
                            frame_duration_corrected = max(min(frame_duration_corrected, self.max_frame_duration), self.min_frame_duration)

                            # Adjust cumulative deviation for next frame
                            self.cumulative_deviation = frame_duration_corrected - 40000

                            # Send corrected frame duration to Redis controller
                            self.redis_controller.set_value('frame_duration', frame_duration_corrected)

                            # Output correction value to CLI
                            correction_value = frame_duration_corrected - 40000
                            print(f"Frame {self.frame_count}: Correcting value: {correction_value:.2f} microseconds")

                            # Write directly to the file without logger formatting
                            with open('/home/pi/cinemate/src/logs/system.log', 'a') as log_file:
                                log_file.write(f"Framecount: {self.frame_count}, Framerate: {framerate:.5f}, Frame duration: {frame_duration:.2f} microseconds, Corrected frame duration: {frame_duration_corrected:.2f} microseconds, CPU usage: {cpu_usage}%, Memory usage: {memory_info.percent}%, Temperature: {temp}C, Outlier: {self.outlier_flag}\n")
                    else:
                        pass

                except json.JSONDecodeError as e:
                    timekeeper_logger.error(f"Failed to parse JSON data: {e}")

    def monitor_recording(self):
        previous_state = '0'
        while self.is_running:
            current_state = self.redis_controller.get_value('is_recording')
            if (current_state is not None and current_state == '1') and previous_state == '0':
                # Recording started
                with open('/home/pi/cinemate/src/logs/system.log', 'w') as f:
                    f.truncate()
                # Write directly to the file without logger formatting
                with open('/home/pi/cinemate/src/logs/system.log', 'a') as log_file:
                    log_file.write("Recording started, log file reset.\n")
                self.start_time = time.time()
                self.frame_count = 0
                self.cumulative_deviation = 0  # Reset cumulative deviation
                self.recording = True  # Set recording state to True

            elif (current_state is not None and current_state == '0') and previous_state == '1':
                # Recording stopped
                self.stop_time = time.time()
                total_time = self.stop_time - self.start_time
                expected_frames = total_time * self.target_framerate
                expected_time = expected_frames / self.target_framerate

                # Calculate projected time for audio sync
                if total_time > 0:
                    average_framerate = self.frame_count / total_time
                    drift_per_frame = abs(self.target_framerate - average_framerate)
                    frames_for_drift = 1 / drift_per_frame if drift_per_frame != 0 else float('inf')
                    drift_duration = frames_for_drift / self.target_framerate if frames_for_drift != float('inf') else float('inf')
                    projected_time = self.frame_count / self.target_framerate
                    drift = abs(total_time - projected_time)

                    # Convert total time to minutes and seconds
                    total_minutes = int(total_time // 60)
                    total_seconds = total_time % 60

                    output = (
                        f"Recording stopped, frame count: {self.frame_count}, expected frames: {expected_frames:.5f}\n"
                        f"Average frame rate for the last recording: {average_framerate:.5f} fps\n"
                        f"Time of recording (expected frames at {self.target_framerate} fps): {total_minutes} minutes and {total_seconds:.2f} seconds\n"
                        f"Projected number of frames at {self.target_framerate:.2f} fps: {expected_frames:.2f}\n"
                        f"Actual number of frames recorded: {self.frame_count}\n"
                        f"Projected time for audio sync: {projected_time:.2f} seconds\n"
                        f"Drift (acceptable drift of 1 frame): {drift:.2f} seconds\n"
                    )

                    # Output to CLI
                    print(output)

                    # Write to log file
                    with open('/home/pi/cinemate/src/logs/system.log', 'a') as log_file:
                        log_file.write(output)
                
                self.recording = False  # Set recording state to False

            previous_state = current_state
            time.sleep(self.check_interval)

    def stop(self):
        self.is_running = False
        self.listener_thread.join()
        self.recording_thread.join()

# Assuming redis_controller is defined elsewhere and passed to TimeKeeper
# Example usage:
# redis_controller = RedisController()  # This should be your actual redis controller instance
# timekeeper = TimeKeeper(redis_controller)
