import os
import pygame
import sys

# Set XDG_RUNTIME_DIR
os.environ['XDG_RUNTIME_DIR'] = '/run/user/pi'  # Replace '1000' with your user ID if needed

# Initialize Pygame without audio
os.environ['SDL_AUDIODRIVER'] = 'dummy'
pygame.mixer.quit()

# Initialize Pygame
pygame.init()

# Set up the display
try:
    screen = pygame.display.set_mode((1920, 1080), pygame.NOFRAME)  # Assuming a 1080p display
except pygame.error as e:
    print("Failed to initialize the display:", e)
    sys.exit(1)

# # Initialize font
# pygame.font.init()
# font = pygame.font.Font(None, 36)  # You can adjust the font size as needed

# # Render text
# text_surface = font.render('Hello, world!', True, (255, 255, 255))  # White text

# Clear the screen to black
screen.fill((0, 0, 0))

# # Blit text onto the screen
# text_rect = text_surface.get_rect(center=screen.get_rect().center)  # Center the text
# screen.blit(text_surface, text_rect)

# Update the display
pygame.display.update()

# Main loop
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            print("Mouse button pressed")
            # Optional: Add logic here to respond to mouse button presses

pygame.quit()


