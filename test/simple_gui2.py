import os
import time
from PIL import Image, ImageDraw
from framebuffer import Framebuffer  # Assuming this is a custom module
import logging

fb_path = "/dev/fb0"

if os.path.exists(fb_path):
    fb = Framebuffer(0)
    disp_width, disp_height = fb.size
    print(f"HDMI display found. {disp_width, disp_height}")
else:
    print("No HDMI display found")

fill_color = "red"
    
image = Image.new("RGBA", fb.size)
draw = ImageDraw.Draw(image)
draw.rectangle(((0, 0), fb.size), fill=fill_color)

fb.show(image)


while True:
    print()
    time.sleep(0.1)
