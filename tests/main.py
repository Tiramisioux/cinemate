from drive_monitor import DriveMonitor
from signal import pause
import threading
import RPi.GPIO as GPIO  # Add this line

if __name__ == "__main__":
    try:
        monitor = DriveMonitor('/media/RAW/', gpio_pin=5)
        threading.Thread(target=monitor.start_space_monitoring, args=(0.1,)).start()
        pause()
    finally:
        GPIO.cleanup()