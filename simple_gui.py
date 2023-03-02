from PIL import Image, ImageDraw, ImageFont
from framebuffer import Framebuffer  # pytorinox
import os
from os import path
from shutil import disk_usage
from gpiozero import CPUTemperature
import psutil
import redis
from redis_proxy import CameraParameters
import multiprocessing
import time
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

rec_out_pin = 19
GPIO.setup(rec_out_pin,GPIO.OUT)

# Frame buffer coordinates
fb = Framebuffer(0)
print(fb)
cx = fb.size[0] // 2
cy = fb.size[1] // 2

fill_color = "black"

r = redis.Redis(host='localhost', port=6379, db=0)
    
# Remove cursor from shell
os.system('sudo sh -c "TERM=linux setterm -foreground black -clear all >/dev/tty0"')

# Connect to Redis
r = redis.Redis(host='localhost', port=6379, db=0)

# Make control objects
iso_setting = CameraParameters("ISO")
shutter_a_setting = CameraParameters("SHUTTER")
fps_setting = CameraParameters("FPS")
resolution_setting = CameraParameters("RESOLUTION")
is_recording_setting = CameraParameters("IS_RECORDING")


def check_drive_mounted():

    mount_point = "/media/RAW"
    if os.path.ismount(mount_point):
        # Get disk usage
        total_bytes, used_bytes, free_bytes = disk_usage(path.realpath('/media/RAW'))
        drive_mounted = 1
        if resolution_setting.get() == "1080": file_size = 3.2
        if resolution_setting.get() == "1520": file_size = 4.8
        min_left = int((free_bytes / 1000000) / (file_size * int(fps) * 60))
        
    else:
        drive_mounted = 0
        min_left = None
    
    return drive_mounted, min_left

def check_last_clip_folder_name():
    
    # get a list of all directories in the folder_path
    dirs = os.listdir('/media/RAW')

    # sort the directories by their creation time (mtime)
    dirs = sorted(dirs, key=lambda d: os.path.getmtime(os.path.join('/media/RAW', d)))

    # get the last (most recently created) directory
    if dirs: 
        last_dir = dirs[-1]
    else:
        last_dir = ""
    
    return last_dir


def get_values():
    global iso, shutter_a, fps, resolution, is_recording
    
    iso = iso_setting.get()
    shutter_a = shutter_a_setting.get()
    fps = fps_setting.get()
    resolution = resolution_setting.get()
    is_recording = is_recording_setting.get()
    
    return iso, shutter_a, fps, resolution, is_recording

def get_system_stats():
    # Get cpu statistics
    cpu_load = str(psutil.cpu_percent()) + '%'
    cpu_temp = ('{}\u00B0'.format(int(CPUTemperature().temperature)))

    return cpu_load, cpu_temp

def draw_display():

    fill_color = "black"
    
    if is_recording == "1" and drive_mounted == 1:
        fill_color = "red"
        GPIO.output(rec_out_pin,GPIO.HIGH)
    if is_recording == "0":
        GPIO.output(rec_out_pin,GPIO.LOW)
        fill_color = "black"
        
    image = Image.new("RGBA", fb.size)
    draw = ImageDraw.Draw(image)
    draw.rectangle(((0, 0), fb.size), fill=fill_color)

    font = ImageFont.truetype('/home/pi/cinemate2/fonts/smallest_pixel-7.ttf', 33)
    font2 = ImageFont.truetype('/home/pi/cinemate2/fonts/smallest_pixel-7.ttf', 233)  

    # GUI Upper line
    draw.text((10, -0), str(iso), font = font, align ="left", fill="white")
    draw.text((110, 0), str(shutter_a), font = font, align ="left", fill="white")
    draw.text((190, 0), str(fps), font = font, align ="left", fill="white")
    draw.text((310, 0), str(cpu_load), font = font, align ="left", fill="white")
    draw.text((445, 0), str(cpu_temp), font = font, align ="left", fill="white")
    
    # GUI Middle logo
    draw.text((400, 400), "cinepi-raw", font = font2, align ="left", fill="white")
    
    # GUI Lower line
    if drive_mounted:
        draw.text((10, 1051), str((str(min_left)) + " min"), font = font, align ="left", fill="white")
    else:
        draw.text((10, 1051), "no disk", font = font, align ="left", fill="white")
    
    #draw.text((160, 1051), str(resolution), font = font, align ="left", fill="white")
    draw.text((722, 1051), str(last_clip), font = font, align ="left", fill="white")
            
    fb.show(image)
    
# Program

GPIO.output(rec_out_pin,GPIO.LOW)

# Subscribe to a pattern
pubsub = r.pubsub()
pubsub.psubscribe("cp_controls")

# Get initial values
iso, shutter_a, fps, resolution, is_recording = (get_values())
resolution = int(resolution)

file_size = 3.3
if resolution == 1080: 
    file_size = 3.3
if resolution == 1520: 
    file_size = 4.8
drive_mounted, min_left = check_drive_mounted()
if drive_mounted: 
    last_clip = check_last_clip_folder_name()
else:
    last_clip = ""


# Get cpu statistics
cpu_load = str(psutil.cpu_percent()) + '%'
cpu_temp = ('{}\u00B0'.format(int(CPUTemperature().temperature)))
    
# Draw display
draw_display()

while True:
    iso, shutter_a, fps, resolution, is_recording = get_values()
    cpu_load, cpu_temp = get_system_stats()
    drive_mounted, min_left = check_drive_mounted()
    if drive_mounted: 
        last_clip = check_last_clip_folder_name()
    else:
        last_clip = ""

    draw_display()
    time.sleep(0.5)

# # Start listening for messages
# for message in pubsub.listen():
#     if message['type'] == 'pmessage':
#         handle_message(message)
    
#         # Get camera parameters    
#         awb, shu_a, iso, shutter_a, is_recording, shuter_a, shu_s, shutter_s, cam_init, compress, height, width, fps, io = (get_values())
        
#         # Draw display
#         draw_display(int(is_recording))
        
#     elif message['type'] == 'punsubscribe':
#         pubsub.close()
#         break
    
    



    
