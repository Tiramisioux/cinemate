import RPi.GPIO as GPIO
import time

# Use BCM numbering
GPIO.setmode(GPIO.BCM)

# Set up GPIO 18 as an output
GPIO.setup(18, GPIO.OUT)

try:
    while True:
        GPIO.output(18, GPIO.HIGH)  # Turn on the LED
        time.sleep(0.5)             # Wait for 0.5 seconds
        GPIO.output(18, GPIO.LOW)   # Turn off the LED
        time.sleep(0.5)             # Wait for 0.5 seconds
except KeyboardInterrupt:
    GPIO.cleanup()  # Clean up GPIO on CTRL+C exit
