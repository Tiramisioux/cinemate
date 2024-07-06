import os
import time
from signal import pause
import subprocess
import logging

class pi5RC:

    def __init__(self, Pin, frequency=50):
        pins = [12, 13, 14, 15, 18, 19]
        afunc = ['a0', 'a0', 'a0', 'a0', 'a3', 'a3']
        self.pwmx = [0, 1, 2, 3, 2, 3]
        self.enableFlag = False
        self.onTime_us = 0
        self.frequency = frequency
        if Pin in pins:
            self.pin = Pin
            self.pinIdx = pins.index(Pin)
            # let's set pin ctrl
            os.system("/usr/bin/pinctrl set {} {}".format(self.pin, afunc[self.pinIdx]))
            # let export pin
            if not os.path.exists("/sys/class/pwm/pwmchip2/pwm{}".format(self.pwmx[self.pinIdx])):
                os.system("echo {} > /sys/class/pwm/pwmchip2/export".format(self.pwmx[self.pinIdx]))
            # Set period based on the frequency
            time.sleep(0.2)
            self.set_frequency(self.frequency)
            self.enable(False)
            self.file_duty = open("/sys/class/pwm/pwmchip2/pwm{}/duty_cycle".format(self.pwmx[self.pinIdx]), "w")
            if self.file_duty.closed:
                raise IOError("Unable to create pwm{} file".format(self.pwmx[self.pinIdx]))
        else:
            self.pin = None
            raise IOError("Error Invalid PWM Pin {}".format(Pin))

    def enable(self, flag):
        self.enableFlag = flag
        os.system("echo {} > /sys/class/pwm/pwmchip2/pwm{}/enable".format(int(self.enableFlag), self.pwmx[self.pinIdx]))

    def set_frequency(self, frequency):
        self.frequency = frequency
        period = int(1e9 / self.frequency)  # Period in nanoseconds
        os.system("echo {} > /sys/class/pwm/pwmchip2/pwm{}/period".format(period, self.pwmx[self.pinIdx]))

    def __del__(self):
        if self.pin is not None:
            # ok take PWM out
            os.system("echo {} > /sys/class/pwm/pwmchip2/unexport".format(self.pwmx[self.pinIdx]))
            # disable PWM Pin
            os.system("/usr/bin/pinctrl set {} no".format(self.pin))
            if not self.file_duty.closed:
                self.file_duty.close()

    def set(self, onTime_us):
        if self.pin is not None:
            if not self.enableFlag:
                self.enable(True)
            self.onTime_us = onTime_us
            self.file_duty.write("{}".format(onTime_us))
            self.file_duty.flush()

# # Example usage:
# pwm = pi5RC(19)
# pwm.set_frequency(24)  # Set frequency to 24 Hz
# pwm.set(500000)        # Set duty cycle to 50%
# pwm.enable(True)       # Enable PWM

# pause()

class PWMController:
    def __init__(self, sensor_detect, PWM_pin=None, PWM_inv_pin=None, start_freq=24, shutter_angle=180, trigger_mode=0):
        self.sensor_detect = sensor_detect
        
        self.PWM_pin = PWM_pin
        self.PWM_inv_pin = PWM_inv_pin
        
        if PWM_pin not in [None, 18, 19]:
            logging.info("Invalid PWM_pin value. Should be None, 18, or 19.")
            return  # Exit the __init__ method if PWM_pin is invalid
        
        self.fps = start_freq
        self.shutter_angle = shutter_angle

        self.freq = start_freq
        self.period = 1.0 / self.freq
        self.duty_cycle = 500_000  # 50% duty cycle
        self.exposure_time = 50000 - (self.duty_cycle * self.period)
        
        if PWM_pin in [18, 19]:
            self.pwm = pi5RC(PWM_pin, start_freq)
            self.pwm_inv = None
            if PWM_inv_pin in [18, 19]:
                self.pwm_inv = pi5RC(PWM_inv_pin, start_freq)
            logging.info(f"PWM controller instantiated on PWM_pin {PWM_pin}")
        
        self.update_pwm()  # Start the PWM
    
    def start_pwm(self, freq, shutter_angle, trigger_mode):
        self.set_freq(freq)
        self.set_duty_cycle(shutter_angle)
        self.set_trigger_mode(trigger_mode)
        self.update_pwm()
        logging.info("PWM started")
        
    def stop_pwm(self):
        self.set_trigger_mode(0)
        self.pwm.enable(False)  # Stop the PWM
        if self.pwm_inv is not None:
            self.pwm_inv.enable(False)  # Stop the inverted PWM
        logging.info("PWM stopped")
        
    def set_trigger_mode(self, value):
        if value not in [0, 2]:
            raise ValueError("Invalid argument: must be 0 or 2")
        
        if self.sensor_detect.camera_model == 'imx477':
            command = f'echo {value} > /sys/module/imx477/parameters/trigger_mode'

        elif self.sensor_detect.camera_model == 'imx296':
            if value == 2: value = 1
            command = f'echo {value} > /sys/module/imx296/parameters/trigger_mode'
            
        full_command = ['sudo', 'su', '-c', command]
        subprocess.run(full_command, check=True)
        logging.info(f"Trigger mode set to {value}")

    def set_pwm(self, fps=None, shutter_angle=None):
        if fps is not None:
            self.fps = fps
            self.set_freq(fps)
        if shutter_angle is not None:
            self.shutter_angle = shutter_angle
            self.set_duty_cycle(shutter_angle)
        self.update_pwm()

    def set_duty_cycle(self, shutter_angle):
        self.shutter_angle = max(min(shutter_angle, 360), 1)  # Ensure shutter angle is within 1-360
        frame_interval = 1.0 / self.fps  # Frame interval in seconds
        shutter_time = (float(self.shutter_angle) / 360.0) * frame_interval  # Shutter open time in seconds
        shutter_time_microseconds = shutter_time * 1_000_000  # Convert shutter time to microseconds
        frame_length_microseconds = frame_interval * 1_000_000  # Convert frame interval to microseconds
        duty_cycle = int((1 - ((shutter_time_microseconds - 14) / frame_length_microseconds)) * 65535)
        duty_cycle = max(min(duty_cycle, 65535), 0)  # Ensure duty cycle is within 0-65535
        self.duty_cycle = duty_cycle
        self.exposure_time = shutter_time_microseconds  # Update the exposure time

    def set_freq(self, new_freq):
        safe_value = max(min(new_freq, 50), 1)
        if self.freq == safe_value:  # If the frequency is already set to the new value
            return  # Exit the method without updating the frequency
        self.freq = safe_value
        self.period = 1.0 / self.freq  # Update the period
        self.pwm.set_frequency(self.freq)  # Update the frequency on the PWM controller
        
    def update_pwm(self, cycles=1):
        frame_interval = 1.0 / self.fps
        remaining_time = cycles * frame_interval - (time.time() % frame_interval)
        if remaining_time > 0:  # Only sleep if remaining_time is positive
            time.sleep(remaining_time)  # Wait for the current cycle to complete
        self.pwm.set(self.duty_cycle)
        if self.pwm_inv is not None:
            self.pwm_inv.set(65535 - self.duty_cycle)
        
        frame_length_microseconds = 1_000_000 / self.freq
        shutter_time_microseconds = (self.duty_cycle / 65535) * frame_length_microseconds
        shutter_angle = (shutter_time_microseconds / frame_length_microseconds) * 360

        duty_cycle_percentage = (self.duty_cycle / 65535) * 100
        exposure_time = (self.duty_cycle / 65535) * (1 / self.freq)
        logging.info(f"Updated PWM with frequency {self.freq}, duty cycle {duty_cycle_percentage:.2f}%, shutter angle {shutter_angle:.1f}, exposure time {exposure_time:.6f}")

    
    def ramp_mode(self, ramp_mode):
        if ramp_mode not in [0, 2, 3]:
            raise ValueError("Invalid argument: must be 0, 2 or 3")
        if ramp_mode == 2 or ramp_mode == 3:
            self.start_pwm(self.freq, self.shutter_angle, 2)
        else:
            self.set_trigger_mode(0)
            self.stop_pwm()
            
    def stop(self):
        self.set_trigger_mode(0)
        self.pwm.enable(False)  # Stop the PWM
        if self.pwm_inv is not None:
            self.pwm_inv.enable(False)  # Stop the inverted PWM
        logging.info("PWM stopped")
