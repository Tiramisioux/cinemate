import time
import RPi.GPIO as GPIO
from signal import pause
from time import sleep

ledPin = 20
pwmPin = 41

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(True)
GPIO.setup(ledPin, GPIO.IN)
GPIO.setup(pwmPin, GPIO.OUT)

p = GPIO.PWM(pwmPin, 50)

def rec_detect(channel):
    if GPIO.input(ledPin):
        print("recording")
        p.start(20)

    if not GPIO.input(ledPin):
        print("stopped recording")
        p.stop()

GPIO.add_event_detect(ledPin, GPIO.BOTH, callback=rec_detect)

pause()