import time
import RPi.GPIO as GPIO
from module.adc import ADC
# from module.cinepi import CameraParameters
from signal import pause

class GroveBaseHAT:
    def __init__(self, camera):
        # Initiate
        GPIO.setwarnings(False) # Ignore warning for now
        GPIO.setmode(GPIO.BCM) # Use GPIO pin numbering

        # Set GPIO functions
        self.rec_pin = 24             #rec pin
       
        # Initialize CameraControls
        self.camera = camera

        GPIO.setup(self.rec_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Set callbacks for interrupts
        GPIO.add_event_detect(self.rec_pin, GPIO.FALLING, callback=self.start_stop_record, bouncetime=200)

    def start_stop_record(self, channel):
        if self.camera.get_recording_status() == "0":
            self.camera.set_control_value("is_recording", "1")  
        if self.camera.get_recording_status() == "1":
            self.camera.set_control_value("is_recording", "0")
        
    def run(self):
        pause()
        # while True:
        #     time.sleep(1)
            # if self.camera.get_recording_status == "0":
            #     print("not recording")
            #     # GPIO.output(self.rec_out_pin,GPIO.HIGH)
            # else:
            #     print("recording")
            #     # GPIO.output(self.rec_out_pin,GPIO.LOW)