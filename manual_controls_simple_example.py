import time
import RPi.GPIO as GPIO
from redis_proxy import CameraParameters, RedisMonitor
import math

# Initialize Redis monitor
monitor = RedisMonitor('cp_stats')

# Ignore GPIO warnings and set GPIO mode
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# Define GPIO pins
rec_pin = 4
rec_out_pin = 21
res_pin = 13
iso_increase_pin = 23
iso_decrease_pin = 25

# Set GPIO pin functions
GPIO.setup(rec_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(rec_out_pin, GPIO.OUT)
GPIO.setup(iso_increase_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(iso_decrease_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(res_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Load objects for reading and writing camera parameters
iso_setting = CameraParameters("ISO")
shutter_angle_setting = CameraParameters("SHUTTER")
shutter_angle_fps_synced_setting = CameraParameters("SHUTTER_FPS_SYNCED")
fps_setting = CameraParameters("FPS")
is_recording_setting = CameraParameters("IS_RECORDING")
resolution_setting = CameraParameters("RESOLUTION")


# Define interrupt callbacks
def start_stop_record(channel):
    # Check if number is increasing or decreasing
    if is_increasing == False:
        is_recording_setting.set("1") # Start recording
    elif is_increasing == True:
        is_recording_setting.set("0") # Stop recording
        
def increase_iso(channel):
    # Get current ISO value
    current_iso = int(iso_setting.get())
    # Double ISO value and keep it between 100 and 3200
    new_iso = int(max(min(current_iso * 2, 3200), 100))
    # Update ISO setting
    iso_setting.set(new_iso)
    
def decrease_iso(channel):
    # Get current ISO value
    current_iso = int(iso_setting.get())
    # Halve ISO value and keep it between 100 and 3200
    new_iso = int(max(min(current_iso / 2, 3200), 100))
    # Update ISO setting
    iso_setting.set(new_iso)
    
## Here you can add methods for changing shutter angle and frame rate
        
def change_res(channel):
    # Toggle between full-frame and cropped-frame resolutions
    if resolution_setting.get() == "1080":
        resolution_setting.set("1520") # Full frame
    elif resolution_setting.get() == "1520" or resolution_setting.get() == "3040":
        resolution_setting.set("1080") # Cropped frame

# Set interrupt callbacks
GPIO.add_event_detect(rec_pin, GPIO.FALLING, callback=start_stop_record, bouncetime=200)
GPIO.add_event_detect(iso_increase_pin, GPIO.FALLING, callback=increase_iso, bouncetime=200)
GPIO.add_event_detect(iso_decrease_pin, GPIO.FALLING, callback=decrease_iso, bouncetime=200)
GPIO.add_event_detect(res_pin, GPIO.FALLING, callback=change_res)

# Main loop
while True:
    # Listen for changes to camera parameters
    monitor.listen()
    # Check if number is increasing or decreasing
    is_increasing = monitor.is_number_increasing()
    # Set recording LED status based on number trend
    if is_increasing == True:
        GPIO.output(rec_out_pin,GPIO.HIGH)
    else:
        GPIO.output(rec_out_pin,GPIO.LOW)
    # Print current camera settings
    print("iso: ", iso_setting.get())
    print("resolution:", resolution_setting.get())
    print("is recording:", is_increasing)
    # Wait for 0.1 seconds before repeating loop
    time.sleep(0.1)
