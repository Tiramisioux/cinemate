import logging
import threading
import time
import json
import sys
import redis
from collections import deque
sys.path.append('/home/pi/grove.py/grove')  # Add the path to your custom Grove module
from adc import ADC  # Import the Grove library for analog controls

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
    def __init__(self, redis_controller, check_interval=0.01, error_threshold=0.1, offset=0.05):
        self.redis_controller = redis_controller
        self.lock = threading.Lock()
        self.is_running = True
        self.check_interval = check_interval
        self.error_threshold = error_threshold
        self.offset = offset  # Offset to fine-tune the frame rate

        self.target_framerate = 25.0000
        self.current_framerate = self.initialize_fps()
        self.frame_durations = deque(maxlen=50)  # Use the last 50 frames for average calculation
        self.long_term_frame_durations = deque(maxlen=100)  # Use the last 100 frames for long-term average calculation

        self.base_frame_duration_values = [40000, 40010]
        self.frame_duration_values = list(self.base_frame_duration_values)
        self.frame_duration_index = 0
        self.frame_duration = self.frame_duration_values[self.frame_duration_index]
        self.accumulated_error = 0

        self.redis_controller.set_value('frame_duration', self.frame_duration)
        
        self.listener_thread = threading.Thread(target=self.listen)
        self.listener_thread.daemon = True
        self.listener_thread.start()
        
        self.adjust_thread = threading.Thread(target=self.adjust_frame_duration)
        self.adjust_thread.daemon = True
        self.adjust_thread.start()

        self.adc = ADC()  # Initialize ADC for Grove Base Hat

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
                                self.long_term_frame_durations.append(self.current_framerate)
                                
                                if len(self.frame_durations) == 50:
                                    avg_framerate = sum(self.frame_durations) / len(self.frame_durations)
                                    sys.stdout.write(f"\rCurrent frame rate: {self.current_framerate:.10f} fps | Average frame rate (last 50 frames): {avg_framerate:.10f} fps")
                                    sys.stdout.flush()
                                    
                                    with open('/home/pi/timekeeper/logs/timekeeper.log', 'a') as log_file:
                                        log_file.write(f"Current frame rate: {self.current_framerate:.10f} fps | Average frame rate (last 50 frames): {avg_framerate:.10f} fps\n")
                                
                                if len(self.long_term_frame_durations) == 100:
                                    long_term_avg_framerate = sum(self.long_term_frame_durations) / len(self.long_term_frame_durations)
                                    sys.stdout.write(f"\rLong-term average frame rate (last 100 frames): {long_term_avg_framerate:.10f} fps")
                                    sys.stdout.flush()
                                    
                                    with open('/home/pi/timekeeper/logs/timekeeper.log', 'a') as log_file:
                                        log_file.write(f"Long-term average frame rate (last 100 frames): {long_term_avg_framerate:.10f} fps\n")

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON data: {e}")

    def adjust_frame_duration(self):
        while self.is_running:
            try:
                with self.lock:
                    if len(self.frame_durations) == 25:
                        avg_framerate = sum(self.frame_durations) / len(self.frame_durations)
                    else:
                        avg_framerate = self.current_framerate

                    # Calculate error including the offset
                    error = self.target_framerate - avg_framerate + self.offset
                    self.accumulated_error += error

                    # Read analog values from Grove Base Hat for fine-tuning
                    coarse_adjustment = self.adc.read(0)  # Read from A0 for coarse adjustment
                    fine_adjustment = self.adc.read(2)  # Read from A2 for fine adjustment

                    # Map the analog values to appropriate adjustment ranges
                    coarse_adjustment = (coarse_adjustment / 1023.0) * 0.1 - 0.5  # Map to +/- 50
                    fine_adjustment = (fine_adjustment / 1023.0) * 0.01 - 0.05  # Map to +/- 5

                    # Adjust the offset based on analog inputs
                    self.offset = coarse_adjustment + fine_adjustment

                    # Flip the frame duration based on the error
                    if abs(error) < self.error_threshold:
                        self.frame_duration_index = 1 if self.frame_duration_index == 0 else 0
                    elif error > 0:
                        self.frame_duration_index = 1  # Switch to higher frame duration
                    else:
                        self.frame_duration_index = 0  # Switch to lower frame duration

                    self.frame_duration = self.frame_duration_values[self.frame_duration_index]
                    self.redis_controller.set_value('frame_duration', self.frame_duration)

                    # Print the current and average frame rate to the CLI
                    sys.stdout.write(f"\rCurrent frame rate: {self.current_framerate:.10f} fps | Average frame rate (last 50 frames): {avg_framerate:.10f} fps")
                    sys.stdout.write(f"\rLower frame duration: {self.frame_duration_values[0]:.3f} | Higher frame duration: {self.frame_duration_values[1]:.3f} | Offset: {self.offset:.5f}")
                    sys.stdout.flush()

                    logger.info(f"Switched frame duration to {self.frame_duration} based on error {error:.10f} with offset {self.offset:.5f}")

                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Exception in adjust_frame_duration: {e}")

    def stop(self):
        self.is_running = False
        self.listener_thread.join()
        self.adjust_thread.join()
        logger.info("TimeKeeper stopped.")

def main():
    redis_controller = RedisController()
    timekeeper = TimeKeeper(redis_controller, offset=-0.53)  # Adjust the offset value as needed

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        timekeeper.stop()
        print("\nRecording stopped.")
        logger.info("Recording stopped by user.")

if __name__ == "__main__":
    main()
