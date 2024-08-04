import threading
import time
from module.grove_base_hat_adc import ADC
import smbus2
import logging
import traceback  # For detailed exception traceback

class AnalogControls(threading.Thread):
    def __init__(self, cinepi_controller, redis_controller, iso_pot=None, shutter_a_pot=None, fps_pot=None, wb_pot=None, iso_steps=None, shutter_a_steps=None, fps_steps=None, wb_steps=None):
        threading.Thread.__init__(self)

        self.cinepi_controller = cinepi_controller
        self.redis_controller = redis_controller

        self.adc = ADC()

        self.iso_pot = self.convert_to_int_or_none(iso_pot)
        self.shutter_a_pot = self.convert_to_int_or_none(shutter_a_pot)
        self.fps_pot = self.convert_to_int_or_none(fps_pot)
        self.wb_pot = self.convert_to_int_or_none(wb_pot)
        
        self.iso_steps = iso_steps or []
        self.shutter_a_steps = shutter_a_steps or []
        self.fps_steps = fps_steps or []
        self.wb_steps = wb_steps or []

        # Last set values for debouncing
        self.last_iso = None
        self.last_shutter_a = None
        self.last_fps = None
        self.last_wb = None
        
        GROVE_BASE_HAT_ADDRESS = 0x08
        I2C_BUS = 1

        try:
            bus = smbus2.SMBus(I2C_BUS)
            bus.read_byte(GROVE_BASE_HAT_ADDRESS)
            self.grove_base_hat_connected = True
            logging.info("Grove Base HAT found!")
            bus.close()
        except OSError:
            self.grove_base_hat_connected = False
            logging.info("Grove Base HAT not found.")
        
        if self.grove_base_hat_connected:
            self.start()

    def convert_to_int_or_none(self, value):
        if value is None or value == 'None':
            return None
        try:
            return int(value)
        except ValueError:
            logging.error(f"Invalid potentiometer value: {value}")
            return None

    def map_adc_to_wb(self, adc_value, min_adc=0, max_adc=1023, min_wb=3200, max_wb=5600):
        """Map ADC value to WB temperature range."""
        return ((adc_value - min_adc) / (max_adc - min_adc)) * (max_wb - min_wb) + min_wb

    def find_nearest_step(self, value, steps):
        """Find the nearest step to the given value."""
        if not steps:
            logging.warning("No steps defined for the parameter.")
            return None  # Or a sensible default
        logging.debug(f"Finding nearest step for value {value} in steps: {steps}")
        nearest = min(steps, key=lambda x: abs(x - value))
        #logging.info(f"Nearest WB step for value {value} is {nearest}")
        return nearest

    def update_parameters(self):
        try:
            if self.iso_pot is not None:
                iso_read = self.adc.read(self.iso_pot)
                if self.iso_steps:
                    new_iso = self.find_nearest_step(iso_read, self.iso_steps)
                    if new_iso != self.last_iso:
                        logging.info(f"Setting ISO to {new_iso}")
                        self.cinepi_controller.set_iso(new_iso)
                        self.last_iso = new_iso
                else:
                    logging.warning("ISO steps are not defined or empty.")

            if self.shutter_a_pot is not None:
                shutter_a_read = self.adc.read(self.shutter_a_pot)
                if self.shutter_a_steps:
                    new_shutter_a = self.find_nearest_step(shutter_a_read, self.shutter_a_steps)
                    if new_shutter_a != self.last_shutter_a:
                        logging.info(f"Setting Shutter Angle to {new_shutter_a}")
                        self.cinepi_controller.set_shutter_a_nom(new_shutter_a)
                        self.last_shutter_a = new_shutter_a
                else:
                    logging.warning("Shutter angle steps are not defined or empty.")

            if self.fps_pot is not None:
                fps_read = self.adc.read(self.fps_pot)
                if self.fps_steps:
                    new_fps = self.find_nearest_step(fps_read, self.fps_steps)
                    if new_fps != self.last_fps:
                        logging.info(f"Setting FPS to {new_fps}")
                        self.redis_controller.set_value('fps', new_fps)
                        self.last_fps = new_fps
                else:
                    logging.warning("FPS steps are not defined or empty.")

            if self.wb_pot is not None:
                wb_read = self.adc.read(self.wb_pot)
                logging.debug(f"ADC value for wb_pot: {wb_read}")
                if self.wb_steps:
                    #logging.info(f"Available WB steps: {self.wb_steps}, searching for nearest to: {wb_read}")
                    wb_mapped = self.map_adc_to_wb(wb_read)
                    #logging.info(f"Mapped WB value: {wb_mapped}")
                    new_wb = self.find_nearest_step(wb_mapped, self.wb_steps)
                    if new_wb is not None and new_wb != self.last_wb:
                        logging.info(f"Setting White Balance to {new_wb}K")
                        self.redis_controller.set_value('wb_user', new_wb)
                        self.cinepi_controller.set_wb(new_wb)
                        self.last_wb = new_wb
                    else:
                        #logging.warning(f"No valid WB step found for {wb_mapped}")
                        pass
                else:
                    #logging.warning("WB steps are not defined or empty.")
                    pass
        except Exception as e:
            logging.error(f"Error occurred while updating parameters: {e}\n{traceback.format_exc()}")

    def run(self):
        try:
            while True:
                if self.grove_base_hat_connected:
                    self.update_parameters()
                time.sleep(0.1)  # Adjust delay as needed
        except Exception as e:
            logging.error(f"Error occurred in AnalogControls run loop: {e}\n{traceback.format_exc()}")
