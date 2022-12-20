
import time
from time import sleep
import RPi.GPIO as GPIO
from signal import pause
import Adafruit_ADS1x15
from controls import CameraParameters
import os

adc0 = Adafruit_ADS1x15.ADS1115(address=0x48, busnum=6)

GAIN = 1
pot_max = 26480
threshold = round(pot_max*0.001)

GPIO.setwarnings(False) # Ignore warning for now
GPIO.setmode(GPIO.BCM) # Use GPIO pin numbering

alert_pin0 = 27

pin16 = 16      #resolution switch
pin12 = 12      #speed ramping button
pin13 = 13      #3 way switch position -1 - half speed 
pin6 = 6        #3 way switch position +1 - double speed

GPIO.setup(alert_pin0, GPIO.IN, pull_up_down = GPIO.PUD_DOWN) # Set GPIO 21 as input for alert

GPIO.setup(pin12, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(pin16, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(pin13, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(pin6, GPIO.IN, pull_up_down=GPIO.PUD_UP)

iso_steps = [100,200,400,500,640,800,1000,1200,2000,2200]
shutter_angle_steps = [*range(0, 361, 1)]
shutter_angle_steps[0] = 1

fps_min = 12
fps_max = 50

fps_steps = [*range(fps_min, fps_max + 1, 1)]

iso_set = CameraParameters("ISO")
shutter_angle_set = CameraParameters("SHUTTER")
fps_set = CameraParameters("FPS")
resolution_set = CameraParameters("RESOLUTION")

ramping = 0
switched = 0

iso_old = 100
shutter_angle_old = 180
fps_old = 24

fps_multiplier = 1

def first_run(channel):
    sleep(3)
    
    pot0 = adc0.read_adc(1, gain = 1, data_rate = None)
    pot1 = adc0.read_adc(2, gain = 1, data_rate = None)
    pot2 = adc0.read_adc(3, gain = 1, data_rate = None)
    
    iso = iso_steps[round((len(iso_steps)-1)*pot0/pot_max)]
    shutter_angle = shutter_angle_steps[round((len(shutter_angle_steps)-1)*pot1/pot_max)]
    fps = fps_steps[round((len(fps_steps)-1)*pot2/pot_max)]
    
    iso_set.set(iso)
     
    fps_multiplier = 1
    
    if GPIO.input(pin6) == 0:
        fps_multiplier = 2
        
    if GPIO.input(pin13) == 0:
        fps_multiplier = 0.5
        
    fps = fps*fps_multiplier
    fps_set.set(fps)
    
    shutter_angle_set.set(shutter_angle)

    start_adc()
    
def stop_adc():
    adc0.stop_adc()

def start_adc():
    value0 = adc0.read_adc_difference(0, gain=1, data_rate=None)

    value0_new = adc0.start_adc_difference_comparator(0, (value0 + threshold), (value0 - threshold), gain=1, data_rate=128, active_low=True, traditional=False, latching=False, num_readings=4)
    
def check_values(channel):
    global iso, iso_old, shutter_angle, shutter_angle_old, fps, fps_old, fps_multiplier
    
    stop_adc()
    
    pot0 = adc0.read_adc(1, gain = 1, data_rate = None)
    pot1 = adc0.read_adc(2, gain = 1, data_rate = None)
    pot2 = adc0.read_adc(3, gain = 1, data_rate = None)
    
    iso = iso_steps[round((len(iso_steps)-1)*pot0/pot_max)]
    shutter_angle = shutter_angle_steps[round((len(shutter_angle_steps)-1)*pot1/pot_max)]
    fps = fps_steps[round((len(fps_steps)-1)*pot2/pot_max)]
    
    if iso != iso_old:
        iso_set.set(iso)
        print("iso: " + str(iso))
    
    if shutter_angle != shutter_angle_old:
        shutter_angle_set.set(shutter_angle)
        print("angle: " + str(shutter_angle))
        
    fps_multiplier = 1
    
    if GPIO.input(pin6) == 0:
        fps_multiplier = 2
        
    if GPIO.input(pin13) == 0:
        fps_multiplier = 0.5
        
    fps = fps*fps_multiplier
    if fps < 12:
        fps = 12  
    
    if fps != fps_old:
        fps_set.set(fps)
        print("fps: " + str(fps))

    iso_old = iso
    shutter_angle_old = shutter_angle
    fps_old = fps
    
    start_adc()
    
def fps_switch(channel):
    global iso, iso_old, shutter_angle, shutter_angle_old, fps, fps_old, fps_multiplier
    
    stop_adc()

    pot2 = adc0.read_adc(3, gain = 1, data_rate = None)

    fps = fps_steps[round((len(fps_steps)-1)*pot2/pot_max)]
    
    if GPIO.input(pin6) == 0:
        fps_multiplier = 2
        
    if GPIO.input(pin13) == 0:
        fps_multiplier = 0.5
        
    if GPIO.input(pin6) == 1 and GPIO.input(pin13) == 1:
        fps_multiplier = 1
    
    fps = fps*fps_multiplier
    if fps < 12:
        fps = 12  
    
    fps_set.set(fps)
    print("fps: " + str(fps))
    
    start_adc()
    
def speed_ramp(channel):
    stop_adc()
    
    pot2 = adc0.read_adc(3, gain = 1, data_rate = None)
    
    if GPIO.input(pin16) == 0:
        ramping = 1
        start_frame_rate = fps_steps[round((len(fps_steps)-1)*pot2/pot_max)]
        end_frame_rate = start_frame_rate*2
        current_fps = fps_set.get()
        if end_frame_rate > 48:
            end_frame_rate = 48
        else:
            pass
        while current_fps < end_frame_rate and GPIO.input(pin16) == 0:
            fps_set.set(current_fps + 1)
            sleep(5/(current_fps + 1))
            current_fps = current_fps + 1
            print("FPS: ", current_fps)
        start_adc()


    if GPIO.input(pin16) == 1: 
        ramping = 1
        start_frame_rate = fps_set.get()
        end_frame_rate = fps_steps[round((len(fps_steps)-1)*pot2/pot_max)]
        current_fps = fps_set.get()

        while current_fps > end_frame_rate and GPIO.input(pin16) == 1:
            fps_set.set(current_fps -1)
            sleep(5/(current_fps - 1))
            current_fps = current_fps - 1
            print("FPS: ", current_fps)
        start_adc()
    ramping = 0

def resolution(channel):
    if GPIO.input(12) == 1:     #cropped frame
        print(resolution_set.set(1))
    if GPIO.input(12) == 0:     #full frame
        print(resolution_set.set(2))
    

GPIO.add_event_detect(alert_pin0, GPIO.FALLING, callback=check_values)
GPIO.add_event_detect(pin16, GPIO.BOTH, callback=speed_ramp)
GPIO.add_event_detect(pin12, GPIO.BOTH, callback=resolution)
GPIO.add_event_detect(pin13, GPIO.BOTH, callback=fps_switch)
GPIO.add_event_detect(pin6, GPIO.BOTH, callback=fps_switch)

first_run(1)
#check_values(1)

pause()