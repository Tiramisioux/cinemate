import threading
import time
from module.grove_base_hat_adc import ADC
import smbus2
from collections import deque
import logging

class AnalogControls(threading.Thread):
    def __init__(self, cinepi_controller, iso_pot=0, shutter_a_pot=2, fps_pot=4):
        threading.Thread.__init__(self)

        self.cinepi_controller = cinepi_controller
        self.adc = ADC()
        
        self.iso_pot = iso_pot
        self.shutter_a_pot = shutter_a_pot
        self.fps_pot = fps_pot

        self.iso_steps = self.cinepi_controller.iso_steps
        self.shutter_a_steps = self.cinepi_controller.shutter_a_steps
        self.fps_steps = self.cinepi_controller.fps_steps
        
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
            #logging.info(f"Grove Base HAT found!")
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
            self.last_iso = self.calculate_iso(self.adc.read(self.iso_pot))
            self.last_shutter_a = self.calculate_shutter_a(self.adc.read(self.shutter_a_pot))
            self.last_fps = self.calculate_fps(self.adc.read(self.fps_pot))
            self.last_fps_set = self.calculate_fps(self.adc.read(self.fps_pot))
            logging.info(f"A0 {self.adc.read(0)}")
            logging.info(f"A1 {self.adc.read(1)}")
            logging.info(f"A2 {self.adc.read(2)}")
            logging.info(f"A3 {self.adc.read(3)}")
        
        self.start()
    
    def calculate_iso_index(self, iso_value):
        iso_steps = self.iso_steps
        return iso_steps.index(iso_value)
                    
    def calculate_iso(self, value):
        # Add the new reading to the deque
        self.iso_readings.append(value)
        # Calculate the average of the readings in the deque
        average_value = sum(self.iso_readings) / len(self.iso_readings)
        index = round((len(self.iso_steps) - 1) * average_value / 1000)
        try:
            return self.iso_steps[index]
        except IndexError:
            print("Error occurred while accessing ISO list elements.")
            print("List length: ", len(self.iso_steps))
            print("Index value: ", index)
    
    def calculate_shutter_a(self, value):
        # Add the new reading to the deque
        self.shutter_a_readings.append(value)
        # Calculate the average of the readings in the deque
        average_value = sum(self.shutter_a_readings) / len(self.shutter_a_readings)
        index = round((len(self.shutter_a_steps) - 1) * average_value / 1000)
        try:
            return self.shutter_a_steps[index]
        except IndexError:
            print("Error occurred while accessing shutter angle list elements.")
            print("List length: ", len(self.shutter_a_steps))
            print("Index value: ", index)

    def calculate_fps(self, value):
        # Add the new reading to the deque
        self.fps_readings.append(value)
        # Calculate the average of the readings in the deque
        average_value = sum(self.fps_readings) / len(self.fps_readings)
        index = round((len(self.fps_steps) - 1) * average_value / 1000)
        try:
            return self.fps_steps[index]
        except IndexError:
            print("Error occurred while accessing fps list elements.")
            print("List length: ", len(self.fps_steps))
            print("Index value: ", index)             

    def update_parameters(self):
        iso_read = self.adc.read(self.iso_pot)
        shutter_a_read = self.adc.read(self.shutter_a_pot)
        fps_read = self.adc.read(self.fps_pot)

        iso_new = self.calculate_iso(iso_read)
        shutter_a_new = self.calculate_shutter_a(shutter_a_read)
        fps_new = self.calculate_fps(fps_read)
        
        if iso_new != self.last_iso:
            self.cinepi_controller.set_iso(iso_new)
            self.last_iso = iso_new
            logging.info(f"A{self.iso_pot} ADC read {iso_read}")

        if not self.cinepi_controller.parameters_lock and shutter_a_new != self.last_shutter_a:
            self.cinepi_controller.set_shutter_a(shutter_a_new)
            self.last_shutter_a = shutter_a_new
            logging.info(f"A{self.shutter_a_pot} ADC read {shutter_a_read}")
        
        if not self.cinepi_controller.parameters_lock and fps_new != self.last_fps:
            self.cinepi_controller.set_fps(int(fps_new))
            self.last_fps = fps_new
            logging.info(f"A{self.fps_pot} ADC read {fps_read}")

    def run(self):
        try:
            while True:
                if self.grove_base_hat_connected:
                    self.update_parameters()
                time.sleep(0.02)
        except Exception as e:
            print(f"Error occurred in ManualControls run loop: {e}")