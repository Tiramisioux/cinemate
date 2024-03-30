import threading
import time
from module.grove_base_hat_adc import ADC
import smbus2
from collections import deque
import logging

class AnalogControls(threading.Thread):
    def __init__(self, cinepi_controller, iso_pot=None, shutter_a_pot=None, fps_pot=None):
        threading.Thread.__init__(self)

        self.cinepi_controller = cinepi_controller
        self.adc = ADC()

        self.iso_pot = iso_pot
        self.shutter_a_pot = shutter_a_pot
        self.fps_pot = fps_pot
        
        self.iso_steps = self.cinepi_controller.iso_steps if iso_pot is not None else []
        self.shutter_a_steps = self.cinepi_controller.shutter_a_steps if shutter_a_pot is not None else []
        self.fps_steps = self.cinepi_controller.fps_steps if fps_pot is not None else []
        
        #Check if Grove Base HAT is connected
        
        # I2C address of Grove Base HAT
        GROVE_BASE_HAT_ADDRESS = 0x08

        # Raspberry Pi I2C bus (usually bus 1)
        I2C_BUS = 1

        try:
            # Try to read a byte from the Grove Base HAT
            bus = smbus2.SMBus(I2C_BUS)
            bus.read_byte(GROVE_BASE_HAT_ADDRESS)
            self.grove_base_hat_connected = True
            logging.info(f"Grove Base HAT found!")
                # Close the I2C bus
            bus.close()
        except OSError as e:
            # If an error occurs, the device is not connected
            self.grove_base_hat_connected = False
            logging.info(f"Grove Base HAT not found.")
        
        # Create deques for storing the last N readings
        self.iso_readings = deque(maxlen=10)
        self.shutter_a_readings = deque(maxlen=10)
        self.fps_readings = deque(maxlen=10)

        if self.grove_base_hat_connected:
            self.last_iso = 0
            self.last_shutter_a = 0
            self.last_fps = 0
            self.last_fps_set = 0
            logging.debug(f"  A0: {self.adc.read(0)}")
            logging.debug(f"  A1: {self.adc.read(1)}")
            logging.debug(f"  A2: {self.adc.read(2)}")
            logging.debug(f"  A3: {self.adc.read(3)}")
            logging.debug(f"  A4: {self.adc.read(4)}")
            logging.debug(f"  A5: {self.adc.read(5)}")
            logging.debug(f"  A6: {self.adc.read(6)}")
            logging.debug(f"  A7: {self.adc.read(7)}")
        
            self.update_parameters()
        
        self.start()
    
    def calculate_iso_index(self, iso_value):
        iso_steps = self.iso_steps
        return iso_steps.index(iso_value)
                    
    def calculate_iso(self, value):
        # Add the new reading to the deque
        self.iso_readings.append(value)
        
        if self.iso_readings:
            # Calculate the average of the readings in the deque
            average_value = sum(self.iso_readings) / len(self.iso_readings)
            index = round((len(self.iso_steps) - 1) * average_value / 1000)
            try:
                return self.iso_steps[index]
            except IndexError:
                # Handle the IndexError gracefully
                logging.error("Error occurred while accessing ISO list elements.")
                logging.error("Setting default ISO value.")
                # You can set a default ISO value here or just return None
                return None
        else:
            logging.warning("No ISO readings available.")
            return None

    def calculate_shutter_a(self, value):
        # Add the new reading to the deque
        self.shutter_a_readings.append(value)
        
        if self.shutter_a_readings:
            # Calculate the average of the readings in the deque
            average_value = sum(self.shutter_a_readings) / len(self.shutter_a_readings)
            index = round((len(self.shutter_a_steps) - 1) * average_value / 1000)
            try:
                return self.shutter_a_steps[index]
            except IndexError:
                # Handle the IndexError gracefully
                logging.error("Error occurred while accessing shutter angle list elements.")
                logging.error("Setting default shutter angle value.")
                # You can set a default shutter angle value here or just return None
                return None
        else:
            logging.warning("No shutter angle readings available.")
            return None

    def calculate_fps(self, value):
        # Add the new reading to the deque
        self.fps_readings.append(value)
        
        if self.fps_readings:
            # Calculate the average of the readings in the deque
            average_value = sum(self.fps_readings) / len(self.fps_readings)
            index = round((len(self.fps_steps) - 1) * average_value / 1000)
            try:
                return self.fps_steps[index]
            except IndexError:
                # Handle the IndexError gracefully
                logging.error("Error occurred while accessing fps list elements.")
                logging.error("Setting default fps value.")
                # You can set a default fps value here or just return None
                return None
        else:
            logging.warning("No fps readings available.")
            return None
            

    def update_parameters(self):
        # Example modification for handling a nullable fps_pot
        if self.iso_pot is not None:
            iso_read = self.adc.read(self.iso_pot)
            iso_new = self.calculate_iso(iso_read)
            
            if iso_new != self.last_iso:
                logging.info(f"  A{self.iso_pot}: {iso_read}")
                self.cinepi_controller.set_iso(iso_new)
                self.last_iso = iso_new

        if self.shutter_a_pot is not None:
            shutter_a_read = self.adc.read(self.shutter_a_pot)
            shutter_a_new = self.calculate_shutter_a(shutter_a_read)
            
            if shutter_a_new != self.last_shutter_a:
                logging.info(f"  A{self.shutter_a_pot}: {shutter_a_read}")
                self.cinepi_controller.set_shutter_a_nom(shutter_a_new)
                self.last_shutter_a = shutter_a_new

        if self.fps_pot is not None:
            fps_read = self.adc.read(self.fps_pot)
            fps_new = self.calculate_fps(fps_read)
            
            if fps_new != self.last_fps:
                logging.info(f"  A{self.fps_pot}: {fps_read}")
                self.cinepi_controller.set_fps(int(fps_new))
                self.last_fps = fps_new


    def run(self):
        try:
            while True:
                if self.grove_base_hat_connected:
                    self.update_parameters()
                time.sleep(0.02)
        except Exception as e:
            logging.error(f"Error occurred in ManualControls run loop: {e}")