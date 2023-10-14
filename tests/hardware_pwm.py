from rpi_hardware_pwm import HardwarePWM
import time

def set_duty_cycle(exposure_time_us, pwm_freq):
    total_period_us = 1e6 / pwm_freq  # Convert frequency to period in microseconds
    duty_cycle = int(((total_period_us - exposure_time_us) / total_period_us) * 100)  # Duty cycle percentage
    return duty_cycle

# Set your desired exposure time in microseconds and frequency in Hz
exposure_time_us = 20833
pwm_freq = 24  # 30 Hz for 30 frames per second

duty_cycle = set_duty_cycle(exposure_time_us, pwm_freq)

# Use channel 0, which corresponds to GPIO 18
pwm_channel = 0
pwm = HardwarePWM(pwm_channel, pwm_freq)
pwm.start(duty_cycle)

try:
    while True:
        # The PWM signal will continue until you stop the script
        time.sleep(1)
except KeyboardInterrupt:
    pass

# Stop the PWM output and cleanup
pwm.stop()
