from rpi_hardware_pwm import HardwarePWM
import logging
import time

logging.basicConfig(level=logging.DEBUG)

try:
    # Initialize with known good parameters
    pwm = HardwarePWM(pwm_channel=3, hz=24, chip=2)  # Adjust chip value as necessary
    pwm.start(50)  # Start with 50% duty cycle
    logging.info("PWM successfully initialized")
    time.sleep(10)
    pwm.stop()
except Exception as e:
    logging.error(f"Failed to initialize PWM: {e}")