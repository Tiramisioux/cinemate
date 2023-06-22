import curses
import RPi.GPIO as GPIO
import time

# Initialize GPIO mode
GPIO.setmode(GPIO.BCM)

# Set all pins as input
pins = list(range(2, 28)) + [0, 1, 5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]
for pin in pins:
    GPIO.setup(pin, GPIO.IN)

# Initialize curses
stdscr = curses.initscr()
curses.noecho()
curses.cbreak()
stdscr.keypad(True)

try:
    while True:
        # Clear the screen
        stdscr.clear()

        # Get screen size
        max_y, max_x = stdscr.getmaxyx()

        # Only display as many pins as can fit on the screen
        pins_to_display = min(len(pins), max_y)

        for i in range(pins_to_display):
            pin = pins[i]
            stdscr.addstr(i, 0, f"Pin {pin}: {'HIGH' if GPIO.input(pin) else 'LOW'}")

        # Refresh the screen
        stdscr.refresh()

        # Sleep for a bit to avoid excessive CPU usage
        time.sleep(0.1)
except KeyboardInterrupt:
    # Clean up on Ctrl-C
    GPIO.cleanup()
finally:
    # Clean up the screen
    curses.echo()
    curses.nocbreak()
    stdscr.keypad(False)
    curses.endwin()
