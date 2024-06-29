import os
import pygame
import sys

# Unset XDG_RUNTIME_DIR for root user
if os.geteuid() == 0:
    os.unsetenv('XDG_RUNTIME_DIR')

# Define a function to initialize the display
def init_display():
    drivers = ['kmsdrm', 'fbcon', 'directfb']
    for driver in drivers:
        try:
            os.environ["SDL_VIDEODRIVER"] = driver
            pygame.display.init()
            return True
        except pygame.error:
            print(f"Driver: {driver} failed.")
    return False

# Initialize Pygame without audio
os.environ['SDL_AUDIODRIVER'] = 'dummy'
pygame.mixer.quit()

if not init_display():
    print("Failed to initialize any video driver.")
    sys.exit(1)

try:
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
except pygame.error as e:
    print("Failed to initialize the display:", e)
    sys.exit(1)

# Main loop
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

pygame.quit()
