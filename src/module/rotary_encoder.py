from gpiozero import RotaryEncoder
import logging

class SimpleRotaryEncoder:
    def __init__(self, cinepi_controller, setting=None, clk=None, dt=None):
        self.encoder = RotaryEncoder(clk, dt)
        
        self.cinepi_controller = cinepi_controller
        self.setting = setting

        # Attach event handlers
        self.encoder.when_rotated_clockwise = self.clockwise_turn
        self.encoder.when_rotated_counter_clockwise = self.counter_clockwise_turn
        
        if clk and dt:
            logging.info(f"{self.setting} rotary encoder instantiated on clk {clk}, dt {dt}")

    def clockwise_turn(self):
        getattr(self.cinepi_controller, f"inc_{self.setting}")()
        logging.info(f"{self.setting} rotary encoder UP")

    def counter_clockwise_turn(self):
        getattr(self.cinepi_controller, f"dec_{self.setting}")()
        logging.info(f"{self.setting} rotary encoder DOWN")