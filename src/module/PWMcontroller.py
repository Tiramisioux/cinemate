import RPi
import time
import subprocess
import logging  

class PWMController:
    def __init__(self, sensor_detect, PWM_pin=None, PWM_inv_pin=None, start_freq=24, shutter_angle=180, trigger_mode=0):
        # self.sensor_detect = sensor_detect
        
        # self.PWM_pin = PWM_pin
        # self.PWM_inv_pin = PWM_inv_pin
        
        # if PWM_pin not in [None, 18, 19]:
        #     logging.info("Invalid PWM_pin value. Should be None, 18, or 19.")
        #     #return  # Exit the __init__ method if PWM_pin is invalid
        
        # self.fps = start_freq
        # self.shutter_angle = shutter_angle

        # #self.ramp_mode(0)
        
        # self.freq = 24  # 24 Hz   
        # self.period = 1.0 / self.freq
        # self.duty_cycle = 500_000  # 50% duty cycle
        # self.exposure_time = 50000 - (self.duty_cycle * self.period)  # Initialize with default values
        
        # self.set_freq(start_freq)
        # self.set_duty_cycle(shutter_angle)
        
        # if PWM_pin in [18, 19]:
        #     logging.info(f"PWM controller instantiated on PWM_pin {PWM_pin}")
        
        #     #logging.info(f"PWM controller instantiated on PWM_pin {PWM_pin}, PWM_inv_pin {PWM_inv_pin}, fps {start_freq}, shutter angle {shutter_angle},  trigger mode {trigger_mode}")
        
        # #self.update_pwm()  # Start the PWM
        pass
    
    def start_pwm(self, freq, shutter_angle, trigger_mode):
        # self.set_freq(freq)
        # self.set_duty_cycle(shutter_angle)
        # self.set_trigger_mode(trigger_mode)
        # self.update_pwm()
        # logging.info("PWM started")
        pass
        
    def stop_pwm(self):
        # self.set_trigger_mode(0)
        # self.pi.hardware_PWM(self.PWM_pin, 0, 0)  # Stop the PWM
        # if self.PWM_inv_pin is not None:
        #     self.pi.hardware_PWM(self.PWM_inv_pin, 0, 0)  # Stop the inverted PWM
        # logging.info("PWM stopped")
        pass
        
    def set_trigger_mode(self, value):
        # if value not in [0, 2]:
        #     raise ValueError("Invalid argument: must be 0 or 2")
        
        # if self.sensor_detect.camera_model == 'imx477':
        #     command = f'echo {value} > /sys/module/imx477/parameters/trigger_mode'

        # elif self.sensor_detect.camera_model == 'imx296':
        #     if value == 2: value = 1
        #     command = f'echo {value} > /sys/module/imx296/parameters/trigger_mode'
            
        # full_command = ['sudo', 'su', '-c', command]
        # subprocess.run(full_command, check=True)
        # logging.info(f"Trigger mode set to {value}")
        pass

    def set_pwm(self, fps=None, shutter_angle=None):
        # if fps is not None:
        #     self.fps = fps
        #     self.freq = fps  # Update the frequency
        #     self.set_freq(fps)
        # if shutter_angle is not None:
        #     self.shutter_angle = shutter_angle
        #     self.set_duty_cycle(shutter_angle)
        # self.update_pwm()
        pass

    def set_duty_cycle(self, shutter_angle):
        # self.shutter_angle = max(min(shutter_angle, 360), 1)  # Ensure shutter angle is within 1-360
        # frame_interval = 1.0 / self.fps  # Frame interval in seconds
        # shutter_time = (float(self.shutter_angle) / 360.0) * frame_interval  # Shutter open time in seconds
        # shutter_time_microseconds = shutter_time * 1_000_000  # Convert shutter time to microseconds
        # frame_length_microseconds = frame_interval * 1_000_000  # Convert frame interval to microseconds
        # duty_cycle = int((1 - ((shutter_time_microseconds - 14) / frame_length_microseconds)) * 1_000_000)
        # duty_cycle = max(min(duty_cycle, 1_000_000), 0)  # Ensure duty cycle is within 0-1M
        # self.duty_cycle = duty_cycle
        # self.exposure_time = shutter_time_microseconds  # Update the exposure time
        pass

    def set_freq(self, new_freq):
        # safe_value = max(min(new_freq, 50), 1)
        # if self.fps == safe_value:  # If the frequency is already set to the new value
        #     return  # Exit the method without updating the frequency
        # self.fps = safe_value
        # self.freq = safe_value  # Update the frequency
        pass
        
    def update_pwm(self, cycles=1):
        # frame_interval = 1.0 / self.fps
        # remaining_time = cycles * frame_interval - (time.time() % frame_interval)
        # if remaining_time > 0:  # Only sleep if remaining_time is positive
        #     time.sleep(remaining_time)  # Wait for the current cycle to complete
        # shutter_angle = (1 - self.duty_cycle) * (1 / self.freq) * 360
        # self.pi.hardware_PWM(self.PWM_pin, self.freq, self.duty_cycle)
        # if self.PWM_inv_pin is not None:
        #     self.pi.hardware_PWM(self.PWM_inv_pin, self.freq, 1_000_000 - self.duty_cycle)
        
        # frame_length_microseconds = 1_000_000 / self.freq
        # shutter_time_microseconds = (1 - (self.duty_cycle / 1_000_000)) * frame_length_microseconds + 14
        # shutter_angle = (shutter_time_microseconds / frame_length_microseconds) * 360

        # duty_cycle_percentage = 100 - ((self.duty_cycle / 1_000_000) * 100)
        # exposure_time = (1 - (self.duty_cycle / 1_000_000)) * (1 / self.freq)
        # logging.info(f"Updated PWM with frequency {self.freq}, duty cycle {duty_cycle_percentage:.2f}%, shutter angle {shutter_angle:.1f}, exposure time {exposure_time:.6f}")       
        pass
    
    def ramp_mode(self, ramp_mode):
        # if ramp_mode not in [0, 2, 3]:
        #     raise ValueError("Invalid argument: must be 0, 2 or 3")
        # if ramp_mode == 2 or ramp_mode == 3:
        #     self.start_pwm()
        #     #self.update_pwm()
        #     self.set_trigger_mode(2)
        # else:
        #     self.set_trigger_mode(0)
        #     self.stop_pwm()
        #     #self.stop()
        pass
            
    def stop(self):
        # self.set_trigger_mode(0)
        # self.pi.hardware_PWM(self.PWM_pin, 0, 0)  # Stop the PWM
        # if self.PWM_inv_pin is not None:
        #     self.pi.hardware_PWM(self.PWM_inv_pin, 0, 0)  # Stop the inverted PWM
        # self.pi.stop()  # Disconnect from the Pi
        # logging.info("PWM stopped")     
        pass  
