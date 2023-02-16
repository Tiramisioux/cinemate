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
GPIO.setup(21,GPIO.OUT)

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
is_recording_setting = CameraParameters("IS_RECORDING")

# Callback function for the subscription
def handle_message(message):
    print("Received message:", message['data'].decode())
    key = message['data'].decode()
    value = r.get(key)
    return [key, value]

def get_values():
    global iso, shutter_a, fps, is_recording
    
    iso = iso_setting.get()
    shutter_a = shutter_a_setting.get()
    fps = fps_setting.get()
    is_recording = is_recording_setting.get()
    return [iso, shutter_a, fps, is_recording]

def get_system_stats():
    # Get cpu statistics
    cpu_load = str(psutil.cpu_percent()) + '%'
    cpu_temp = ('{}\u00B0'.format(int(CPUTemperature().temperature)))
    
    # Get disk usage
    total_bytes, used_bytes, free_bytes = disk_usage(path.realpath('/media/RAW'))
    min_left = int((free_bytes / 1000000) / (3.3 * int(fps) * 60))

    return [cpu_load, cpu_temp, total_bytes, min_left]

def draw_display():
    # Get disk usage
    
    fill_color = "black"
    
    if is_recording == "1":
        fill_color = "red"
        GPIO.output(21,GPIO.HIGH)
    if is_recording == "0":
        GPIO.output(21,GPIO.LOW)
        fill_color = "black"
        
    image = Image.new("RGBA", fb.size)
    draw = ImageDraw.Draw(image)
    draw.rectangle(((0, 0), fb.size), fill=fill_color)

    font = ImageFont.truetype('fonts/smallest_pixel-7.ttf', 33)
    font2 = ImageFont.truetype('fonts/smallest_pixel-7.ttf', 233)  

    # GUI Upper line
    draw.text((10, -0), str(iso_setting.get()), font = font, align ="left", fill="white")
    draw.text((110, 0), str(shutter_a), font = font, align ="left", fill="white")
    draw.text((190, 0), str(fps), font = font, align ="left", fill="white")
    draw.text((310, 0), str(cpu_load), font = font, align ="left", fill="white")
    draw.text((445, 0), str(cpu_temp), font = font, align ="left", fill="white")
    
    # GUI Middle logo
    draw.text((400, 400), "cinepi-raw", font = font2, align ="left", fill="white")
    
    # GUI Lower line
    draw.text((10, 1051), str((str(min_left)) + " min"), font = font, align ="left", fill="white")
    draw.text((190, 1051), str(is_recording), font = font, align ="left", fill="white")
            
    fb.show(image)
    
# Program

GPIO.output(21,GPIO.LOW)

# Subscribe to a pattern
pubsub = r.pubsub()
pubsub.psubscribe("cp_controls")

# Get initial values
iso, shutter_a, fps, is_recording = (get_values())

# Get cpu statistics
cpu_load = str(psutil.cpu_percent()) + '%'
cpu_temp = ('{}\u00B0'.format(int(CPUTemperature().temperature)))

# Get disk usage
total_bytes, used_bytes, free_bytes = disk_usage(path.realpath('/media/RAW'))
min_left = int((free_bytes / 1000000) / (3.3 * int(fps) * 60))
    
# Draw display
draw_display()

while True:
    iso, shutter_a, fps, is_recording = (get_values())
    cpu_load, cpu_temp, total_bytes, min_left = get_system_stats()
    draw_display()
    time.sleep(0.01)

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
    
    



    
