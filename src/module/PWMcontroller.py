import logging
import time
import subprocess
from rpi_hardware_pwm import HardwarePWM, HardwarePWMException

class PWMController:
    PIN_CHANNEL_MAP = {12: 0, 13: 1, 18: 2, 19: 3}
    DEFAULT_CHIP = 2  # Set default chip value here

    def __init__(self, sensor_detect, PWM_pin=None, PWM_inv_pin=None, start_freq=24, shutter_angle=180, trigger_mode=0):
        self.sensor_detect = sensor_detect
        self.PWM_pin = PWM_pin
        self.PWM_inv_pin = PWM_inv_pin

        if PWM_pin not in [None, 12, 13, 18, 19]:
            logging.error("Invalid PWM_pin value. Should be None, 12, 13, 18, or 19.")
            return

        self.fps = start_freq
        self.shutter_angle = shutter_angle
        self.freq = float(start_freq)
        self.period = 1.0 / self.freq
        self.duty_cycle = 32767  # 50% duty cycle
        self.exposure_time = 50000 - (self.duty_cycle * self.period)

        self.pwm = None
        self.pwm_inv = None
        if PWM_pin in self.PIN_CHANNEL_MAP:
            self.pwm = self.initialize_pwm(PWM_pin, start_freq)
        if PWM_inv_pin in self.PIN_CHANNEL_MAP:
            self.pwm_inv = self.initialize_pwm(PWM_inv_pin, start_freq)

        self.update_pwm()  # Start the PWM

    def initialize_pwm(self, Pin, frequency):
        channel = self.PIN_CHANNEL_MAP[Pin]
        try:
            logging.info(f"Initializing PWM on pin {Pin} (channel {channel}) with frequency {frequency}Hz and chip {self.DEFAULT_CHIP}")
            pwm = HardwarePWM(pwm_channel=channel, hz=frequency, chip=self.DEFAULT_CHIP)
            pwm.start(100)  # Initialize with 100% duty cycle
            logging.info(f"PWM successfully initialized on pin {Pin} (channel {channel}) with frequency {frequency}Hz")
            return pwm
        except (HardwarePWMException, OSError) as e:
            logging.error(f"Failed to initialize PWM on pin {Pin}: {e}")
            return None

    def enable(self, flag):
        if self.pwm is not None:
            if flag:
                self.pwm.change_duty_cycle(self.duty_cycle / 65535 * 100)
            else:
                self.pwm.stop()
            logging.info(f"PWM {'enabled' if flag else 'disabled'} on pin {self.PWM_pin}")

        if self.pwm_inv is not None:
            if flag:
                self.pwm_inv.change_duty_cycle((65535 - self.duty_cycle) / 65535 * 100)
            else:
                self.pwm_inv.stop()
            logging.info(f"Inverted PWM {'enabled' if flag else 'disabled'} on pin {self.PWM_inv_pin}")

    def set_frequency(self, frequency):
        try:
            self.freq = float(frequency)
            self.period = 1.0 / self.freq
            if self.pwm is not None:
                self.pwm.change_frequency(self.freq)
            if self.pwm_inv is not None:
                self.pwm_inv.change_frequency(self.freq)
            logging.info(f"PWM frequency set to {self.freq}Hz on pins {self.PWM_pin}, {self.PWM_inv_pin}")
        except ValueError:
            logging.error(f"Invalid frequency value: {frequency}")

    def set(self, duty_cycle):
        if duty_cycle is not None:
            self.duty_cycle = int(duty_cycle)
            logging.info(f"PWM duty cycle set to {self.duty_cycle / 65535 * 100}% on pins {self.PWM_pin}, {self.PWM_inv_pin}")
        else:
            logging.info(f"PWM duty cycle unchanged: {self.duty_cycle / 65535 * 100}% on pins {self.PWM_pin}, {self.PWM_inv_pin}")

        if self.pwm is not None:
            self.pwm.change_duty_cycle(self.duty_cycle / 65535 * 100)
        if self.pwm_inv is not None:
            self.pwm_inv.change_duty_cycle((65535 - self.duty_cycle) / 65535 * 100)

    def stop(self):
        if self.pwm is not None:
            self.pwm.stop()
        if self.pwm_inv is not None:
            self.pwm_inv.stop()
        logging.info("PWM stopped")

    def start_pwm(self, freq, shutter_angle, trigger_mode):
        logging.info(f"Starting PWM with freq={freq}, shutter_angle={shutter_angle}, trigger_mode={trigger_mode}")  
        self.set_frequency(freq)
        if shutter_angle is not None:
            self.set_duty_cycle(shutter_angle)
        self.set_trigger_mode(trigger_mode)
        self.update_pwm()
        logging.info("PWM started")

    def stop_pwm(self):
        self.set_trigger_mode(0)
        self.stop()
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

    def set_duty_cycle(self, shutter_angle):
        try:
            if shutter_angle is not None:
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
                logging.info(f"PWM duty cycle calculated and set to {self.duty_cycle}")
            else:
                logging.info("Shutter angle is None, keeping existing duty cycle.")
        except ValueError:
            logging.error("Invalid value for shutter_angle. It must be a float.")

    def set_pwm(self, fps=None, shutter_angle=None):
        logging.info(f"Setting PWM with fps={fps}, shutter_angle={shutter_angle}")
        if fps is not None:
            self.set_frequency(fps)
        self.set_duty_cycle(shutter_angle)
        self.update_pwm()

    def get_frequency(self):
        return self.freq

    def update_pwm(self, cycles=1):
        logging.info(f"Updating PWM with cycles={cycles}")
        frame_interval = 1.0 / self.fps
        remaining_time = cycles * frame_interval - (time.time() % frame_interval)
        if remaining_time > 0:
            time.sleep(remaining_time)
        self.set(self.duty_cycle)

    def ramp_mode(self, ramp_mode):
        logging.info(f"Setting ramp mode to {ramp_mode}")
        if ramp_mode not in [0, 2, 3]:
            raise ValueError("Invalid argument: must be 0, 2 or 3")
        if ramp_mode in [2, 3]:
            self.start_pwm(self.freq, self.shutter_angle, 2)
        else:
            self.set_trigger_mode(0)
            self.stop_pwm()
    
    def __del__(self):
        self.stop()