import threading
import time
from module.grove_base_hat_adc import ADC
import smbus2
from collections import deque
import logging

class AnalogControls(threading.Thread):
    def __init__(self, cinepi_controller, redis_controller, iso_pot=None, shutter_a_pot=None, fps_pot=None):
        threading.Thread.__init__(self)


        self.cinepi_controller = cinepi_controller
        self.redis_controller = redis_controller

        self.adc = ADC()

        self.iso_pot = iso_pot
        self.shutter_a_pot = shutter_a_pot
        self.fps_pot = fps_pot
        
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
            # logging.debug(f"  A0: {self.adc.read(0)}")
            # logging.debug(f"  A1: {self.adc.read(1)}")
            # logging.debug(f"  A2: {self.adc.read(2)}")
            # logging.debug(f"  A3: {self.adc.read(3)}")
            # logging.debug(f"  A4: {self.adc.read(4)}")
            # logging.debug(f"  A5: {self.adc.read(5)}")
            # logging.debug(f"  A6: {self.adc.read(6)}")
            # logging.debug(f"  A7: {self.adc.read(7)}")
        
            self.update_parameters()
        
        self.start()
    
    def calculate_fine_tune_value(self, readings, value, adjustment_range):
        readings.append(value)
        
        if readings:
            average_value = sum(readings) / len(readings)
            # Normalize the value to a range of -0.5 to 0.5 and then scale to adjustment range
            fine_tuned_value = ((average_value / 1000) - 0.5) * 2 * adjustment_range
            return fine_tuned_value
        else:
            logging.warning("No readings available.")
            return None

    def update_parameters(self):
        if self.iso_pot is not None:
            iso_read = self.adc.read(self.iso_pot)
            iso_new = self.calculate_fine_tune_value(self.iso_readings, iso_read, 0.001)
            
            if iso_new is not None:
                logging.info(f"  A{self.iso_pot}: {iso_read}")
                new_iso = (float(((self.redis_controller.get_value('iso')))) + iso_new)
                self.cinepi_controller.set_iso(new_iso)
                self.last_iso = new_iso

        if self.shutter_a_pot is not None:
            shutter_a_read = self.adc.read(self.shutter_a_pot)
            shutter_a_new = self.calculate_fine_tune_value(self.shutter_a_readings, shutter_a_read, 0.001)
            
            if shutter_a_new is not None:
                logging.info(f"  A{self.shutter_a_pot}: {shutter_a_read}")
                new_shutter_a = ((float(self.redis_controller.get_value('shutter_a')) + shutter_a_new))
                self.cinepi_controller.set_shutter_a_nom(new_shutter_a)
                self.last_shutter_a = new_shutter_a

        if self.fps_pot is not None:
            fps_read = self.adc.read(self.fps_pot)
            fps_new = self.calculate_fine_tune_value(self.fps_readings, fps_read, 1.000)
            
            if fps_new is not None:
                #logging.info(f"  A{self.fps_pot}: {fps_read}")
                base_fps = 25  # Example base FPS value
                new_fps = base_fps + fps_new
                new_fps = max(24.000, min(new_fps, 25.999))
                self.redis_controller.set_value('fps', round(new_fps, 3))
                self.last_fps = new_fps
                
    def run(self):
        try:
            while True:
                if self.grove_base_hat_connected:
                    self.update_parameters()
                time.sleep(0.02)
        except Exception as e:
            logging.error(f"Error occurred in AnalogControls run loop: {e}")
