import logging
import threading
import time
from collections import deque
import json
import os
import re
import math

from .analyze_logs import analyze_logs  # Use relative import

class PIDController:
    def __init__(self, kp, ki, kd, setpoint, output_limits=(None, None)):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.setpoint = setpoint
        self.output_limits = output_limits

        self._last_error = 0
        self._integral = 0
        self._last_time = time.time()

    def compute(self, input_value):
        current_time = time.time()
        delta_time = current_time - self._last_time
        if delta_time <= 0.0:
            return 0

        error = self.setpoint - input_value
        self._integral += error * delta_time
        derivative = (error - self._last_error) / delta_time

        output = (self.kp * error) + (self.ki * self._integral) + (self.kd * derivative)

        if self.output_limits[0] is not None:
            output = max(self.output_limits[0], output)
        if self.output_limits[1] is not None:
            output = min(self.output_limits[1], output)

        self._last_error = error
        self._last_time = current_time

        # Log detailed PID information
        #logging.info(f"PID Controller: error={error:.4f}, integral={self._integral:.4f}, derivative={derivative:.4f}, output={output:.4f}")

        return output

class TimeKeeper:
    def __init__(self, redis_controller, pwm_controller, kp=0.2, ki=0.04, kd=0.08, check_interval=0.5, window_size=5):
        self.redis_controller = redis_controller
        self.pwm_controller = pwm_controller
        self.lock = threading.Lock()
        self.is_running = True
        self.check_interval = check_interval

        self.target_framerate = 24.0  # Hardcoded user-selected frame rate for testing
        self.current_framerate = 0.0  # Initialize current_framerate

        # Initialize deque for moving average
        self.framerate_history = deque(maxlen=window_size)

        # Get recommended PID values from log file if available
        kp, ki, kd = self.get_recommended_pid_values('/home/pi/cinemate/src/logs/system.log', kp, ki, kd)

        # PID controller for frequency adjustment
        self.pid = PIDController(kp, ki, kd, setpoint=self.target_framerate, output_limits=(-10, 10))

        self.listener_thread = threading.Thread(target=self.listen)
        self.listener_thread.daemon = True
        self.listener_thread.start()

        self.adjustment_thread = threading.Thread(target=self.adjust_pwm_continuously)
        self.adjustment_thread.daemon = True
        self.adjustment_thread.start()

        self.recording_thread = threading.Thread(target=self.monitor_recording)
        self.recording_thread.daemon = True
        self.recording_thread.start()

    def get_recommended_pid_values(self, logfile, default_kp, default_ki, default_kd):
        if os.path.exists(logfile):
            try:
                with open(logfile, 'r') as file:
                    for line in file:
                        if "Suggested PID values:" in line:
                            kp = float(re.findall(r"kp: (\d+\.\d+)", line)[0])
                            ki = float(re.findall(r"ki: (\d+\.\d+)", line)[0])
                            kd = float(re.findall(r"kd: (\d+\.\d+)", line)[0])
                            logging.info(f"Loaded PID values from log: kp={kp}, ki={ki}, kd={kd}")
                            return kp, ki, kd
            except Exception as e:
                logging.error(f"Failed to read recommended PID values from log: {e}")

        logging.info("Using default PID values")
        return default_kp, default_ki, default_kd

    def listen(self):
        pubsub = self.redis_controller.redis_client.pubsub()
        pubsub.subscribe('cp_stats')

        for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    stats_data = json.loads(message['data'].decode('utf-8').strip())
                    framerate = stats_data.get('framerate', None)
                    framecount = stats_data.get('frameCount', None)
                    if framerate is not None and framerate > 0:
                        with self.lock:
                            self.current_framerate = float(framerate)
                            self.framerate_history.append(self.current_framerate)
                        if framecount is not None:
                            with self.lock:
                                self.frame_count = int(framecount)
                            print(f"Received framecount: {framecount}, framerate: {framerate:.5f}", end='\r')
                        else:
                            logging.info(f"Received framerate: {framerate:.5f}", end='\r')
                    else:
                        logging.warning(f"Received invalid framerate: {framerate}")

                except json.JSONDecodeError as e:
                    logging.error(f"Failed to parse JSON data: {e}")

    def get_smoothed_framerate(self):
        with self.lock:
            if len(self.framerate_history) == 0:
                return self.target_framerate  # Fallback to target framerate if no valid data
            return sum(self.framerate_history) / len(self.framerate_history)

    def get_framerate_change_rate(self):
        with self.lock:
            if len(self.framerate_history) < 2:
                return 0.0  # Not enough data to calculate change rate
            return (self.framerate_history[-1] - self.framerate_history[0]) / len(self.framerate_history)

    def adjust_pwm_continuously(self):
        while self.is_running:
            smoothed_framerate = self.get_smoothed_framerate()
            #logging.info(f"Smoothed framerate: {smoothed_framerate:.10f}")

            if smoothed_framerate > 0:
                # Compute the new frequency using the PID controller
                adjustment = self.pid.compute(smoothed_framerate)
                new_frequency = self.pwm_controller.get_frequency() + adjustment
                new_frequency = max(1, min(50, new_frequency))  # Clamp frequency within limits
                self.pwm_controller.set_freq(new_frequency)
                #logging.info(f"Adjusted PWM frequency to: {new_frequency:.5f} Hz to match target framerate: {self.target_framerate} Hz")
                #logging.info(f"PID Adjustment: {adjustment:.5f}, New Frequency: {new_frequency:.5f}")

            time.sleep(self.check_interval)

    def monitor_recording(self):
        previous_state = '0'
        while self.is_running:
            current_state = self.redis_controller.get_value('is_recording')
            if (current_state is not None and current_state == '1') and previous_state == '0':
                # Recording started
                with open('/home/pi/cinemate/src/logs/system.log', 'w') as f:
                    f.truncate()
                logging.info("Recording started, log file reset.")
                self.start_time = time.time()
                self.frame_count = 0

            elif (current_state is not None and current_state == '0') and previous_state == '1':
                # Recording stopped
                self.stop_time = time.time()
                expected_frames = (self.stop_time - self.start_time) * self.target_framerate
                logging.info(f"Recording stopped, frame count: {self.frame_count}, expected frames: {expected_frames:.5f}")
                
                # Run analysis and adjust PID values
                kp, ki, kd = analyze_logs('/home/pi/cinemate/src/logs/system.log')
                self.pid.kp = kp
                self.pid.ki = ki
                self.pid.kd = kd
                logging.info(f"Adjusted PID values to kp={kp}, ki={ki}, kd={kd}")

            previous_state = current_state
            time.sleep(0.1)

    def increment_frame_count(self):
        with self.lock:
            self.frame_count += 1

    def stop(self):
        self.is_running = False
        self.listener_thread.join()
        self.adjustment_thread.join()
        self.recording_thread.join()
        
    def get_effort_level(self):
        with self.lock:
            # Calculate the deviation from the target framerate
            deviation = abs(self.target_framerate - self.current_framerate)
            
            # Logarithmic scaling to a 0-99 range
            if deviation < 0.001:
                effort_level = 0
            else:
                # Scale the logarithm of the deviation
                effort_level = min(int(10 * math.log10(deviation * 1000)), 99)
            
            return effort_level
