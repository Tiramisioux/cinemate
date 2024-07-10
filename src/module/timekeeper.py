import logging
import threading
import time
import json
import sys
import redis
import random
from collections import deque

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class RedisController:
    def __init__(self):
        self.redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)
    
    def get_value(self, key):
        value = self.redis_client.get(key)
        return float(value) if value else None
    
    def set_value(self, key, value):
        self.redis_client.set(key, value)

class TimeKeeper:
    def __init__(self, redis_controller, check_interval=0.01, window_size=500, initial_learning_period=100):
        self.redis_controller = redis_controller
        self.lock = threading.Lock()
        self.is_running = True
        self.check_interval = check_interval
        self.window_size = window_size
        self.initial_learning_period = initial_learning_period

        self.target_framerate = 25.000  # Target frame rate
        self.current_framerate = self.initialize_fps()  # Initialize current framerate from Redis
        self.frame_count = 0  # Initialize frame count
        self.recording = True  # Recording state
        self.frame_durations = deque(maxlen=self.window_size)  # Use deque for fixed window size

        self.frame_duration_values = [38000, 39000, 40000, 40002, 40003, 40004]#[40043, 40044, 40045, 40046]  # Define array of frame duration values
        self.frame_duration_index = 0  # Initial frame duration index
        self.frame_duration = self.frame_duration_values[self.frame_duration_index]  # Initial frame duration in microseconds
        self.accumulated_error = 0  # Accumulated error for control
        self.error_threshold = 0.0001  # Error threshold for switching
        self.learning_rate = 0.01  # Initial learning rate
        self.bias_correction = 0  # Bias correction term

        # Performance tracking
        self.performance = {value: deque(maxlen=50) for value in self.frame_duration_values}

        # Set initial frame duration in Redis
        self.redis_controller.set_value('frame_duration', self.frame_duration)
        
        # Clear the log file contents initially
        with open('/home/pi/cinemate/src/logs/system.log', 'w') as log_file:
            log_file.write("")

        self.listener_thread = threading.Thread(target=self.listen)
        self.listener_thread.daemon = True
        self.listener_thread.start()
        
        self.fps_thread = threading.Thread(target=self.check_fps)
        self.fps_thread.daemon = True
        self.fps_thread.start()
        
        self.adjust_thread = threading.Thread(target=self.adjust_frame_duration)
        self.adjust_thread.daemon = True
        self.adjust_thread.start()

    def initialize_fps(self):
        fps = self.redis_controller.get_value('fps')
        if fps is not None:
            logger.info(f"Initial FPS retrieved from Redis: {fps}")
            return 24.999
        logger.info("No initial FPS found in Redis, using default value.")
        return self.target_framerate

    def listen(self):
        pubsub = self.redis_controller.redis_client.pubsub()
        pubsub.subscribe('cp_stats')

        while self.is_running:
            for message in pubsub.listen():
                if not self.is_running:
                    break
                if message['type'] == 'message':
                    try:
                        stats_data = json.loads(message['data'].decode('utf-8').strip())
                        framerate = stats_data.get('framerate', None)
                        if framerate is not None and framerate > 0 and self.recording:
                            # Filter out outlier values
                            if abs(framerate - self.target_framerate) > 1.0:
                                logger.warning(f"Ignoring outlier framerate value: {framerate}")
                                continue

                            with self.lock:
                                self.current_framerate = float(framerate)
                                self.frame_count += 1  # Increment frame count
                                self.frame_durations.append(self.current_framerate)
                                
                                if len(self.frame_durations) == self.window_size:
                                    avg_framerate = sum(self.frame_durations) / len(self.frame_durations)

                                    # Output average frame rate to CLI on the same line
                                    sys.stdout.write(f"\rAverage frame rate (last {self.window_size} frames): {avg_framerate:.5f} fps")
                                    sys.stdout.flush()

                                    # Write directly to the file without logger formatting
                                    with open('/home/pi/cinemate/src/logs/system.log', 'a') as log_file:
                                        log_file.write(f"Average frame rate (last {self.window_size} frames): {avg_framerate:.5f} fps\n")
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON data: {e}")

    def check_fps(self):
        while self.is_running:
            try:
                fps = self.redis_controller.get_value('fps')
                if fps is not None:
                    with self.lock:
                        self.current_framerate = fps
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Exception in check_fps: {e}")

    def adjust_frame_duration(self):
        initial_learning = True
        learning_count = 0

        while self.is_running:
            try:
                if not self.recording:
                    time.sleep(self.check_interval)
                    continue

                with self.lock:
                    if self.frame_durations:
                        avg_framerate = sum(self.frame_durations) / len(self.frame_durations)
                    else:
                        avg_framerate = self.current_framerate
                    
                    # Calculate the error
                    error = self.target_framerate - avg_framerate
                    self.accumulated_error += error

                    # Record the performance of the current frame duration
                    self.performance[self.frame_duration].append(abs(error))

                    # Calculate dynamic learning rate based on error magnitude
                    self.learning_rate = max(0.01, min(0.1, abs(error) * 10))

                    # Calculate bias correction to handle persistent deviation
                    avg_performance = {key: (sum(values) / len(values)) if values else float('inf') for key, values in self.performance.items()}
                    self.bias_correction = avg_performance[self.frame_duration]

                    # Adjust the frame duration switching based on performance
                    if initial_learning or abs(self.accumulated_error + self.bias_correction) >= self.error_threshold:
                        # During initial learning period, cycle through all frame duration values
                        if initial_learning:
                            self.frame_duration_index = (self.frame_duration_index + 1) % len(self.frame_duration_values)
                            learning_count += 1
                            if learning_count >= len(self.frame_duration_values) * self.initial_learning_period:
                                initial_learning = False  # End initial learning period
                        else:
                            # Heuristic-based random switch if current frame duration is not performing well
                            if random.random() < 0.5:  # Random chance to switch
                                self.frame_duration_index = (self.frame_duration_index + 1) % len(self.frame_duration_values)
                            else:
                                best_performance_value = min(self.performance, key=lambda k: avg_performance[k])
                                self.frame_duration_index = self.frame_duration_values.index(best_performance_value)

                            self.accumulated_error = 0  # Reset the accumulated error

                        self.frame_duration = self.frame_duration_values[self.frame_duration_index]

                    # Set the new frame duration in Redis
                    self.redis_controller.set_value('frame_duration', self.frame_duration)

                    logger.info(f"Switched frame duration to {self.frame_duration} based on avg_framerate {avg_framerate:.5f}, error {error:.5f}")
                    
                time.sleep(self.check_interval)  # Sleep for the check interval
            except Exception as e:
                logger.error(f"Exception in adjust_frame_duration: {e}")

    def stop(self):
        self.is_running = False
        self.listener_thread.join()
        self.fps_thread.join()
        self.adjust_thread.join()
        logger.info("TimeKeeper stopped.")

def main():
    redis_controller = RedisController()  # This should be your actual redis controller instance
    timekeeper = TimeKeeper(redis_controller)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        timekeeper.stop()
        print("\nRecording stopped.")
        logger.info("Recording stopped by user.")

if __name__ == "__main__":
    main()
