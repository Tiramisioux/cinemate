import time
import RPi.GPIO as GPIO
from adc import ADC

GPIO.setwarnings(False) # Ignore warning for now
GPIO.setmode(GPIO.BCM) # Use GPIO pin numbering

# Set GPIO functions
pin = 11          

GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

while True:
    print(GPIO.input(pin)) 