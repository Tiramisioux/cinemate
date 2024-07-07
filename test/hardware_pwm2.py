from rpi_hardware_pwm import HardwarePWM
import time

pwm = HardwarePWM(pwm_channel=3, hz=60, chip=2)
pwm.start(100) # full duty cycle

pwm.change_duty_cycle(50)
pwm.change_frequency(10.5203)

time.sleep(10)
pwm.stop()