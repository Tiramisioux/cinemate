import threading
import time
import RPi.GPIO as GPIO
from module.adc import ADC
from queue import Queue, Empty

class ManualControls(threading.Thread):
    def __init__(self, cinepi_controller, monitor, iso_steps=None, shutter_angle_steps=None, fps_steps=None, iso_pot=0, shutter_angle_pot=2, fps_pot=4,
                 iso_inc_pin=None, iso_dec_pin=None, pot_lock_pin=None, res_button_pin=None,
                 rec_pin=None, rec_out_pin=None, fps_mult_pin1=None, fps_mult_pin2=None):
        threading.Thread.__init__(self)

        self.cinepi_controller = cinepi_controller
        self.adc = ADC() 
        self.monitor = monitor

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        pin_configurations = [
            (iso_inc_pin, GPIO.BOTH, self.iso_inc_callback),
            (iso_dec_pin, GPIO.RISING, self.iso_dec_callback),
            (pot_lock_pin, GPIO.BOTH, self.pot_lock_callback),
            (res_button_pin, GPIO.RISING, self.res_button_callback),
            (fps_mult_pin1, GPIO.BOTH, self.fps_mult_callback), 
            (fps_mult_pin2, GPIO.BOTH, self.fps_mult_callback),
        ]

        if rec_pin is not None:
            if isinstance(rec_pin, list):
                for pin in rec_pin:
                    pin_configurations.append((pin, GPIO.RISING, self.gpio_callback))
            else:
                pin_configurations.append((rec_pin, GPIO.RISING, self.gpio_callback))

        if rec_out_pin is not None:
            if isinstance(rec_out_pin, list):
                for pin in rec_out_pin:
                    GPIO.setup(pin, GPIO.OUT)
                    GPIO.output(pin, GPIO.LOW)
            else:
                GPIO.setup(rec_out_pin, GPIO.OUT)
                GPIO.output(rec_out_pin, GPIO.LOW)

        for pin, edge, callback in pin_configurations:
            if pin is not None:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                GPIO.add_event_detect(pin, edge, callback=callback, bouncetime=400)

        self.rec_pin = rec_pin
        self.rec_out_pin = rec_out_pin
        self.iso_inc_pin = iso_inc_pin
        self.iso_dec_pin = iso_dec_pin
        self.pot_lock_pin = pot_lock_pin
        self.res_button_pin = res_button_pin
        self.fps_mult_pin1 = fps_mult_pin1
        self.fps_mult_pin2 = fps_mult_pin2
        self.iso_pot = iso_pot
        self.shutter_angle_pot = shutter_angle_pot
        self.fps_pot = fps_pot

        self.iso_steps = iso_steps or [100, 200, 400, 800, 1600, 3200]
        self.shutter_angle_steps = shutter_angle_steps or list(range(1, 361))
        self.fps_steps = fps_steps or list(range(1, 50))

        self.last_iso = self.calculate_iso(self.adc.read(self.iso_pot))
        self.last_shutter_angle = self.calculate_shutter_angle(self.adc.read(self.shutter_angle_pot))
        self.last_fps = self.calculate_fps(self.adc.read(self.fps_pot))
        self.last_fps_set = self.calculate_fps(self.adc.read(self.fps_pot))
        
        # Check if shu_lock_pin and fps_lock_pin are defined
        if pot_lock_pin is not None:
            self.pot_locked = GPIO.input(pot_lock_pin) == GPIO.HIGH
            
        self.flip_switched = 0
        
        self.start()

    def gpio_callback(self, channel):
        if channel in self.rec_pin and GPIO.input(channel) == GPIO.HIGH:
            drive_mounted = self.monitor.is_drive_connected()
            if drive_mounted:
                if not self.cinepi_controller.get_recording_status():
                    self.cinepi_controller.start_recording()
                    if self.rec_out_pin is not None:
                        for pin in self.rec_out_pin:
                            GPIO.output(pin, GPIO.HIGH)  # set rec_out_pin to high when recording
                else:
                    self.cinepi_controller.stop_recording()
                    if self.rec_out_pin is not None:
                        for pin in self.rec_out_pin:
                            GPIO.output(pin, GPIO.LOW)  # set rec_out_pin to low when not recording

    def pot_lock_callback(self, channel):
        if GPIO.input(self.pot_lock_pin) == GPIO.LOW:  # GPIO pin 18 is high
            self.pot_locked = False
        if GPIO.input(self.pot_lock_pin) == GPIO.HIGH:  # GPIO pin 19 is high
            self.pot_locked = True
            
        print("pot lock: ", self.pot_locked)
        
    def res_button_callback(self, channel):
            if channel == self.res_button_pin:
                if self.cinepi_controller.get_control_value('height') == '1080':
                    self.cinepi_controller.set_control_value('height', 1520)
                elif self.cinepi_controller.get_control_value('height') == '1520':
                    self.cinepi_controller.set_control_value('height', 1080)
                    
    def fps_mult(self):
        if GPIO.input(self.fps_mult_pin1) == GPIO.LOW:  # GPIO pin 18 is high
            fps_multiplier = 0.5
        elif GPIO.input(self.fps_mult_pin2) == GPIO.LOW:  # GPIO pin 19 is high
            fps_multiplier = 2
        else:  # Both GPIO pins are low
            fps_multiplier = 1
            
        return fps_multiplier
    
    def fps_mult_callback(self, channel):
        self.flip_switched = 1
    
    def calculate_iso_index(self, iso_value):
        iso_steps = ManualControls.iso_steps
        return iso_steps.index(iso_value)
            
    def iso_inc_callback(self, channel):
        if GPIO.input(self.iso_inc_pin) == GPIO.HIGH:
            iso_current = self.cinepi_controller.get_control_value('iso')
            if iso_current is not None:
                iso_current = int(iso_current)
                iso_index = self.calculate_iso_index(iso_current)
                if iso_index < len(ManualControls.iso_steps) - 1:
                    iso_new = ManualControls.iso_steps[iso_index + 1]
                    self.cinepi_controller.set_control_value('iso', iso_new)
                    self.last_iso = iso_new

    def iso_dec_callback(self, channel):
        if GPIO.input(self.iso_dec_pin) == GPIO.HIGH:
            iso_current = self.cinepi_controller.get_control_value('iso')
            if iso_current is not None:
                iso_current = int(iso_current)
                iso_index = self.calculate_iso_index(iso_current)
                if iso_index > 0:
                    iso_new = ManualControls.iso_steps[iso_index - 1]
                    self.cinepi_controller.set_control_value('iso', iso_new)
                    self.last_iso = iso_new
                 
    def calculate_iso(self, value):
        index = round((len(self.iso_steps) - 1) * value / 1000)
        try:
            return self.iso_steps[index]
        except IndexError:
            print("Error occurred while accessing ISO list elements.")
            print("List length: ", len(self.iso_steps))
            print("Index value: ", index)

    def calculate_shutter_angle(self, value):
        index = round((len(self.shutter_angle_steps) - 1) * value / 1000)
        try:
            return self.shutter_angle_steps[index]
        except IndexError:
            print("Error occurred while accessing shutter angle list elements.")
            print("List length: ", len(self.shutter_angle_steps))
            print("Index value: ", index)

    def calculate_fps(self, value):
        index = round((len(self.fps_steps) - 1) * value / 1000)
        try:
            return self.fps_steps[index]
        except IndexError:
            print("Error occurred while accessing fps list elements.")
            print("List length: ", len(self.fps_steps))
            print("Index value: ", index)

    def update_parameters(self):
        iso_read = self.adc.read(self.iso_pot)
        shutter_angle_read = self.adc.read(self.shutter_angle_pot)
        fps_read = self.adc.read(self.fps_pot)

        iso_new = self.calculate_iso(iso_read)
        shutter_angle_new = self.calculate_shutter_angle(shutter_angle_read)
        fps_new = self.calculate_fps(fps_read)
        
        fps_multiplier = self.fps_mult()
        fps_new = round(fps_new*fps_multiplier)
        
        if iso_new != self.last_iso:
            self.cinepi_controller.set_control_value('iso', iso_new)
            self.last_iso = iso_new

        if not self.pot_locked and shutter_angle_new != self.last_shutter_angle:
            self.cinepi_controller.set_control_value('shutter_a', shutter_angle_new)
            self.last_shutter_angle = shutter_angle_new
        
        if not self.pot_locked and fps_new != self.last_fps:
            self.cinepi_controller.set_control_value('fps', int(fps_new))
            self.last_fps = fps_new
            
            
        if self.pot_locked and fps_new != self.last_fps and self.flip_switched == 1:
            self.cinepi_controller.set_control_value('fps', int(fps_new))
            self.last_fps = fps_new
            self.flip_switched = 0


    def run(self):
        try:
            while True:
                self.update_parameters()
                time.sleep(0.02)
        except Exception as e:
            print(f"Error occurred in ManualControls run loop: {e}")