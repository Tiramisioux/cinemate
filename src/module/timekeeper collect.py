import logging
import threading
import time
import json
import sys
import redis
import psutil
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
    def __init__(self, redis_controller, check_interval=0.01):
        self.redis_controller = redis_controller
        self.lock = threading.Lock()
        self.is_running = True
        self.check_interval = check_interval

        self.target_framerate = 25.0001
        self.current_framerate = self.initialize_fps()
        self.frame_durations = deque(maxlen=50)

        self.frame_duration_values = [39950.000, 40050.000]
        self.frame_duration = self.frame_duration_values[0]
        self.accumulated_error = 0

        self.redis_controller.set_value('frame_duration', self.frame_duration)
        
        self.listener_thread = threading.Thread(target=self.listen)
        self.listener_thread.daemon = True
        self.listener_thread.start()
        
        self.adjust_thread = threading.Thread(target=self.adjust_frame_duration)
        self.adjust_thread.daemon = True
        self.adjust_thread.start()

        # Open the log file in append mode
        self.log_file = open('/home/pi/timekeeper/logs/timekeeper_exploration.log', 'a')

        # Calculate and print the total estimated time to complete all combinations
        total_combinations = 10000
        total_time_seconds = total_combinations * 2
        total_time_hours = total_time_seconds / 3600
        print(f"Estimated time to complete all combinations: {total_time_hours:.2f} hours")

        # Initialize flip tracking variables
        self.flip_count = 0
        self.flip_direction = "initial"

    def initialize_fps(self):
        fps = self.redis_controller.get_value('fps')
        if fps is not None:
            logger.info(f"Initial FPS retrieved from Redis: {fps}")
            return float(fps)
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
                        if framerate is not None and framerate > 0:
                            with self.lock:
                                self.current_framerate = float(framerate)
                                self.frame_durations.append(self.current_framerate)
                                
                                if len(self.frame_durations) == 50:
                                    avg_framerate = sum(self.frame_durations) / len(self.frame_durations)
                                    cpu_load = psutil.cpu_percent()
                                    memory_usage = psutil.virtual_memory().percent
                                    temperature = self.get_temperature()
                                    timestamp_ns = time.time_ns()

                                    # Log the details
                                    self.log_file.write(f"{timestamp_ns} - Upper value: {self.frame_duration_values[1]}, Lower value: {self.frame_duration_values[0]}, Frame rate: {avg_framerate:.10f}, CPU load: {cpu_load}%, Memory usage: {memory_usage}%, Temperature: {temperature}°C, Flip count: {self.flip_count}, Flip direction: {self.flip_direction}\n")
                                    self.log_file.flush()

                                    sys.stdout.write(f"\r{timestamp_ns} - Upper value: {self.frame_duration_values[1]}, Lower value: {self.frame_duration_values[0]}, Frame rate: {avg_framerate:.10f}, CPU load: {cpu_load}%, Memory usage: {memory_usage}%, Temperature: {temperature}°C, Flip count: {self.flip_count}, Flip direction: {self.flip_direction}\n")
                                    sys.stdout.flush()

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON data: {e}")

    def adjust_frame_duration(self):
        lower_bound = 39950
        upper_bound = 40050

        for lower_value in range(lower_bound, upper_bound + 1):
            for upper_value in range(lower_value, upper_bound + 1):
                if not self.is_running:
                    return

                with self.lock:
                    self.frame_duration_values = [lower_value, upper_value]
                    self.redis_controller.set_value('frame_duration', self.frame_duration_values[0])
                    self.flip_count += 1
                    self.flip_direction = "lower to upper"

                time.sleep(2)  # Run each combination for 2 seconds

                with self.lock:
                    self.redis_controller.set_value('frame_duration', self.frame_duration_values[1])
                    self.flip_count += 1
                    self.flip_direction = "upper to lower"

                time.sleep(2)  # Run each combination for 2 seconds

    def get_temperature(self):
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = f.read()
                return float(temp) / 1000.0  # Convert from millidegree to degree Celsius
        except FileNotFoundError:
            return 'N/A'

    def stop(self):
        self.is_running = False
        self.listener_thread.join()
        self.adjust_thread.join()
        self.log_file.close()
        logger.info("TimeKeeper stopped.")

def main():
    redis_controller = RedisController()
    timekeeper = TimeKeeper(redis_controller)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        timekeeper.stop()
        print("\nExploration stopped.")
        logger.info("Exploration stopped by user.")

if __name__ == "__main__":
    main()
