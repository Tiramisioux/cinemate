import time
from time import sleep
import RPi.GPIO as GPIO
from signal import pause
import Adafruit_ADS1x15 
import os
from redis_proxy import CameraParameters

adc0 = Adafruit_ADS1x15.ADS1115(address=0x48, busnum=6)

GAIN = 1
pot_max = 26480
threshold = round(pot_max*0.001)

GPIO.setwarnings(False) # Ignore warning for now
GPIO.setmode(GPIO.BCM) # Use GPIO pin numbering

alert_pin0 = 27

pin4 = 4        #rec pin
pin21 = 21      #rec out pin

pin16 = 16      #resolution switch
pin12 = 12      #speed ramping button
pin13 = 13      #3 way switch position -1 - half speed 
pin6 = 6        #3 way switch position +1 - double speed

pwmPin = 41

GPIO.setup(alert_pin0, GPIO.IN, pull_up_down = GPIO.PUD_DOWN) # Set GPIO 21 as input for alert

GPIO.setup(pin4, GPIO.IN, pull_up_down=GPIO.PUD_UP)     # Rec button
GPIO.setup(pin12, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(pin16, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(pin13, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(pin6, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(pwmPin, GPIO.OUT)

p = GPIO.PWM(pwmPin, 50)

iso_steps = [100,200,400,500,640,800,1000,1200,2000,2500,3200]
shutter_angle_steps = [*range(0, 361, 1)]
shutter_angle_steps[0] = 1

fps_steps = [*range(0, 51, 1)]
fps_steps[0] = 1

switched = 0

fps_multiplier = 1

iso_setting = CameraParameters("ISO")
shutter_angle_setting = CameraParameters("SHUTTER")
shutter_angle_fps_synced_setting = CameraParameters("SHUTTER_FPS_SYNCED")
fps_setting = CameraParameters("FPS")
is_recording_setting = CameraParameters("IS_RECORDING")
resolution_setting = CameraParameters("RESOLUTION")

iso = 100
shutter_angle = 180
fps = 24

fps_nom = fps
is_recording = "0"
    
def start_adc():
    value0 = adc0.read_adc_difference(0, gain=1, data_rate=None)
    value0_new = adc0.start_adc_difference_comparator(0, (value0 + threshold), (value0 - threshold), gain=1, data_rate=128, active_low=True, traditional=False, latching=False, num_readings=4)

def stop_adc():
    adc0.stop_adc()

def check_pots():
    pot0 = adc0.read_adc(1, gain = 1, data_rate = None)
    pot1 = adc0.read_adc(2, gain = 1, data_rate = None)
    pot2 = adc0.read_adc(3, gain = 1, data_rate = None)
    return pot0, pot1, pot2

def check_switch0():
    if GPIO.input(pin6) == 0: switch0 = 2
    if GPIO.input(pin13) == 0: switch0 = 0.5
    if GPIO.input(pin6) == 1 and GPIO.input(pin13) == 1: switch0 = 1
    return switch0

def set_camera_parameters(channel):
    global iso, shutter_angle, fps
    
    stop_adc()
    iso_pot, shutter_angle_pot, fps_pot = check_pots()
    fps_multiplier = check_switch0()

    iso_set = iso_steps[round((len(iso_steps)-1)*iso_pot/pot_max)]
    shutter_angle_set = shutter_angle_steps[round((len(shutter_angle_steps)-1)*shutter_angle_pot/pot_max)]
    fps_set = fps_multiplier * fps_steps[round((len(fps_steps)-1)*fps_pot/pot_max)]
    fps_set = min(fps_steps, key=lambda x:abs(x-fps_set))
    
    print(iso_set, shutter_angle_set, fps_set)
    
    if iso_set != iso:
        iso_setting.set(iso_set)
        iso = int(iso_setting.get())
        
    if shutter_angle_set != shutter_angle:
        shutter_angle_setting.set(shutter_angle_set)
        shutter_angle = shutter_angle_set
        
    if fps_set != int(fps):
        fps_setting.set(fps_set)
        fps = fps_setting.get()
        
    shutter_angle_fps_synced_setting.set(shutter_angle_set) # this adjust the shutter angle along with frame rate for constant exposure
                                                            # comment out for normal camera behaviour
    
    start_adc()
    
    print()
    print("iso: " + str(iso_setting.get()))
    print("angle: " + str(shutter_angle_setting.get()))
    print("fps: " + str(fps_setting.get()))
    print("resolution: " + str(resolution_setting.get()))
    print()
    
def change_res_button(channel):
    if resolution_setting.get() == "1080": resolution_setting.set("1520")     # full frame
    elif resolution_setting.get() == "1520" or resolution_setting.get() == "3040": resolution_setting.set("1080")     # cropped frame
    
    print()
    print("iso: " + str(iso_setting.get()))
    print("angle: " + str(shutter_angle_setting.get()))
    print("fps: " + str(fps_setting.get()))
    print("resolution: " + str(resolution_setting.get()))
    print()
    
def start_stop_record(channel):
    if is_recording_setting.get() == "0":
        is_recording_setting.set("1") 
        p.start(20)   
        
    elif is_recording_setting.get() == "1":
        is_recording_setting.set("0")
        p.stop()
    
GPIO.add_event_detect(pin4, GPIO.FALLING, callback=start_stop_record, bouncetime=600)
GPIO.add_event_detect(alert_pin0, GPIO.FALLING, callback=set_camera_parameters)
GPIO.add_event_detect(pin16, GPIO.RISING, callback=change_res_button, bouncetime=400)
# GPIO.add_event_detect(pin12, GPIO.BOTH, callback=resolution)
GPIO.add_event_detect(pin13, GPIO.BOTH, callback=set_camera_parameters)
GPIO.add_event_detect(pin6, GPIO.BOTH, callback=set_camera_parameters)

set_camera_parameters(1)

pause()