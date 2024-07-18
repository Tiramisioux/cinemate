import logging
import time
import subprocess
from rpi_hardware_pwm import HardwarePWM, HardwarePWMException

class HardwarePWMController:
    PIN_CHANNEL_MAP = {12: 0, 13: 1, 18: 2, 19: 3}
    DEFAULT_CHIP = 2  # Set default chip value here

    def __init__(self, Pin, frequency=60, chip=DEFAULT_CHIP):
        if Pin not in self.PIN_CHANNEL_MAP:
            raise ValueError(f"Invalid PWM Pin {Pin}. Must be one of [12, 13, 18, 19].")
        
        self.pin = Pin
        self.channel = self.PIN_CHANNEL_MAP[self.pin]
        self.frequency = frequency
        self.duty_cycle = 100  # Start with full duty cycle

        try:
            logging.info(f"Attempting to initialize PWM on pin {self.pin} (channel {self.channel}) with frequency {self.frequency}Hz and chip {chip}")
            self.pwm = HardwarePWM(pwm_channel=self.channel, hz=self.frequency, chip=chip)
            self.pwm.start(100)  # Initialize with 100% duty cycle
            logging.info(f"PWM successfully initialized on pin {self.pin} (channel {self.channel}) with frequency {self.frequency}Hz and chip {chip}")
        except (HardwarePWMException, OSError) as e:
            logging.error(f"Failed to initialize PWM on pin {self.pin}: {e}")
            self.pwm = None
    
    def enable(self, flag):
        if self.pwm is not None:
            if flag:
                self.pwm.change_duty_cycle(self.duty_cycle)
            else:
                self.pwm.stop()
            logging.info(f"PWM {'enabled' if flag else 'disabled'} on pin {self.pin}")
    
    def set_frequency(self, frequency):
        if self.pwm is not None:
            self.frequency = frequency
            self.pwm.change_frequency(self.frequency)
            #logging.info(f"PWM frequency set to {self.frequency}Hz on pin {self.pin}")
    
    def set(self, duty_cycle):
        if self.pwm is not None:
            self.duty_cycle = duty_cycle / 65535 * 100  # Convert to percentage
            self.pwm.change_duty_cycle(self.duty_cycle)
            logging.info(f"PWM duty cycle set to {self.duty_cycle}% on pin {self.pin}")
    
    def stop(self):
        if hasattr(self, 'pwm') and self.pwm is not None:
            self.pwm.stop()
            logging.info(f"PWM stopped on pin {self.pin}")
    
    def __del__(self):
        self.stop()

class PWMController:
    def __init__(self, sensor_detect, PWM_pin=None, PWM_inv_pin=None, start_freq=24, shutter_angle=180, trigger_mode=0):
        self.sensor_detect = sensor_detect
        
        self.PWM_pin = PWM_pin
        self.PWM_inv_pin = PWM_inv_pin
        
        if PWM_pin not in [None, 12, 13, 18, 19]:
            logging.info("Invalid PWM_pin value. Should be None, 12, 13, 18, or 19.")
            return
        
        self.fps = start_freq
        self.shutter_angle = shutter_angle

        self.freq = start_freq
        self.period = 1.0 / self.freq
        self.duty_cycle = 32767  # 50% duty cycle
        self.exposure_time = 50000 - (self.duty_cycle * self.period)
        
        if PWM_pin in [12, 13, 18, 19]:
            self.pwm = HardwarePWMController(PWM_pin, start_freq, chip=2)  # Use chip=2
            self.pwm_inv = None
            if PWM_inv_pin in [12, 13, 18, 19]:
                self.pwm_inv = HardwarePWMController(PWM_inv_pin, start_freq, chip=2)  # Use chip=2
            logging.info(f"PWM controller instantiated on PWM_pin {PWM_pin}")
        
        self.update_pwm()  # Start the PWM
    
    def start_pwm(self, freq, shutter_angle, trigger_mode):
        logging.info(f"Starting PWM with freq={freq}, shutter_angle={shutter_angle}, trigger_mode={trigger_mode}")  
        self.set_freq(50)
        self.set_duty_cycle(shutter_angle)
        #self.set_trigger_mode(trigger_mode)
        self.update_pwm()
        logging.info("PWM started")
    
    def stop_pwm(self):
        self.set_trigger_mode(0)
        if self.pwm is not None:
            self.pwm.stop()  # Stop the PWM
        if self.pwm_inv is not None:
            self.pwm_inv.stop()  # Stop the inverted PWM
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
        #logging.info(f"Setting PWM with fps={fps}, shutter_angle={shutter_angle}")
        if fps is not None:
            self.fps = 50
            self.set_freq(fps)
        if shutter_angle is not None:
            self.shutter_angle = shutter_angle
            self.set_duty_cycle(shutter_angle)
        self.update_pwm()
    
    def set_duty_cycle(self, shutter_angle):
        try:
            shutter_angle = float(shutter_angle)
            self.shutter_angle = max(min(shutter_angle, 360.0), 1.0)
            frame_interval = 1.0 / self.fps
            shutter_time = (self.shutter_angle / 360.0) * frame_interval
            shutter_time_microseconds = shutter_time * 1_000_000
            frame_length_microseconds = frame_interval * 1_000_000
            duty_cycle = int((shutter_time_microseconds / frame_length_microseconds) * 65535)
            duty_cycle = max(min(duty_cycle, 65535), 0)
            self.duty_cycle = duty_cycle
            self.exposure_time = shutter_time_microseconds
        except ValueError:
            logging.error("Invalid value for shutter_angle. It must be a float.")
    
    def set_freq(self, new_freq):
        #logging.info(f"Setting frequency to {new_freq}")
        safe_value = max(min(new_freq, 50), 1)
        if self.freq == safe_value:
            return
        self.freq = safe_value
        self.period = 1.0 / self.freq
        if self.pwm is not None:
            self.pwm.set_frequency(self.freq)

    def get_frequency(self):
        return self.freq
    
    def update_pwm(self, cycles=1):
        logging.info(f"Updating PWM with cycles={cycles}")
        frame_interval = 1.0 / self.fps
        remaining_time = cycles * frame_interval - (time.time() % frame_interval)
        if remaining_time > 0:
            time.sleep(remaining_time)
        if self.pwm is not None:
            self.pwm.set(self.duty_cycle)
        if self.pwm_inv is not None:
            self.pwm_inv.set(65535 - self.duty_cycle)
        
        frame_length_microseconds = 1_000_000 / self.freq
        shutter_time_microseconds = (self.duty_cycle / 65535) * frame_length_microseconds
        shutter_angle = (shutter_time_microseconds / frame_length_microseconds) * 360
        duty_cycle_percentage = (self.duty_cycle / 65535) * 100
        exposure_time = (self.duty_cycle / 65535) * (1 / self.freq)
        #logging.info(f"Updated PWM with frequency {self.freq}, duty cycle {duty_cycle_percentage:.2f}%, shutter angle {shutter_angle:.1f}, exposure time {exposure_time:.6f}")
    
    def ramp_mode(self, ramp_mode):
        logging.info(f"Setting ramp mode to {ramp_mode}")
        if ramp_mode not in [0, 2, 3]:
            raise ValueError("Invalid argument: must be 0, 2 or 3")
        if ramp_mode in [2, 3]:
            self.start_pwm(self.freq, self.shutter_angle, 2)
        else:
            self.set_trigger_mode(0)
            self.stop_pwm()
    
    def stop(self):
        logging.info("Stopping PWM")
        self.set_trigger_mode(0)
        if self.pwm is not None:
            self.pwm.stop()
        if self.pwm_inv is not None:
            self.pwm_inv.stop()
        logging.info("PWM stopped")