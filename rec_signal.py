import time
import RPi.GPIO as GPIO
from signal import pause
from pysinewave import SineWave
from time import sleep

ledPin = 20
pwmPin = 23

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(ledPin, GPIO.IN)
GPIO.setup(pwmPin, GPIO.OUT)

p = GPIO.PWM(pwmPin, 82.41) 

recording = 0

def rec_detect(channel):
    if GPIO.input(ledPin):
        print("recording")
        p.start(50)

    if not GPIO.input(ledPin):
        print("stopped recording")
        p.stop()

print("start")

GPIO.add_event_detect(ledPin, GPIO.BOTH, callback=rec_detect)


pause()
    


