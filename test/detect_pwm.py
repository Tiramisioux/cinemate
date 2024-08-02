import RPi.GPIO as GPIO
import time

# Pin Definitions
PWM_PIN = 18  # Broadcom pin 18 (P1 pin 12)

# Set up RPi.GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(PWM_PIN, GPIO.IN)

# Variables to store times
last_rising_edge = 0
high_duration = 0
period = 0

def pwm_callback(channel):
    global last_rising_edge, high_duration, period
    current_time = time.time()
    if GPIO.input(PWM_PIN):  # Rising edge
        if last_rising_edge != 0:
            period = current_time - last_rising_edge
        last_rising_edge = current_time
    else:  # Falling edge
        high_duration = current_time - last_rising_edge

def calculate_pwm():
    global period, high_duration
    if period > 0:
        frequency = 1.0 / period
        duty_cycle = (high_duration / period) * 100
        print(f"Frequency: {frequency:.2f} Hz, Duty Cycle: {duty_cycle:.2f}%")
    else:
        print("No valid PWM signal detected.")

# Set up event detection
GPIO.add_event_detect(PWM_PIN, GPIO.BOTH, callback=pwm_callback)

try:
    print("Starting PWM detection on GPIO pin 18")
    while True:
        calculate_pwm()
        time.sleep(0.5)  # Adjust as needed

except KeyboardInterrupt:
    print("Exiting PWM detection.")

finally:
    GPIO.cleanup()  # Clean up GPIO settings
