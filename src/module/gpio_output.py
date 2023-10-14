import RPi.GPIO as GPIO
import logging

GPIO.setwarnings(False)

class GPIOOutput:
    def __init__(self, rec_out_pins=None):
        # Using BCM mode
        GPIO.setmode(GPIO.BCM)

        self.rec_out_pins = rec_out_pins  # This is the array of pins for recording

        # Set up the rec_pins as outputs if they're provided
        if self.rec_out_pins is not None:
            for pin in self.rec_out_pins:
                GPIO.setup(pin, GPIO.OUT)
                logging.info(f"rec_out pin instantiated on pin {pin}")

    def set_recording(self, status):
        """Set the status of the recording pins based on the given status."""
        if self.rec_out_pins:
            for pin in self.rec_out_pins:
                GPIO.output(pin, GPIO.HIGH if status else GPIO.LOW)
                logging.info(f"GPIO {pin} set to {'HIGH' if status else 'LOW'}")