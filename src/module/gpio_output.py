import RPi.GPIO as GPIO
import logging

class GPIOOutput:
    def __init__(self, rec_out_pin=None):
        self.rec_out_pin = rec_out_pin  # This is the pin for recording

        # Set up the rec_pin as an output if it's provided
        if self.rec_out_pin is not None:
            GPIO.setup(self.rec_out_pin, GPIO.OUT)
            logging.info(f"REC light instantiated on pin {self.rec_out_pin}")

    def set_recording(self, status):
        """Set the status of the recording pin based on the given status."""
        if self.rec_out_pin:
            GPIO.output(self.rec_out_pin, GPIO.HIGH if status else GPIO.LOW)
            logging.info(f"GPIO {self.rec_out_pin} set to {'HIGH' if status else 'LOW'}")
