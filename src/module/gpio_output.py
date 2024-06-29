import RPi
import logging

class GPIOOutput:
    def __init__(self, rec_out_pins=None):
        self.rec_out_pins = rec_out_pins if rec_out_pins is not None else []  # This is the list of pins for recording

        # Set up each pin in rec_out_pins as an output if the list is provided
        for pin in self.rec_out_pins:
            RPi.GPIO.setup(pin, RPi.GPIO.OUT)
            logging.info(f"REC light instantiated on pin {pin}")

    def set_recording(self, status):
        """Set the status of the recording pins based on the given status."""
        for pin in self.rec_out_pins:
            RPi.GPIO.output(pin, RPi.GPIO.HIGH if status else RPi.GPIO.LOW)
            logging.info(f"GPIO {pin} set to {'HIGH' if status else 'LOW'}")