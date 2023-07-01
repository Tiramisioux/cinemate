from time import sleep
import threading
from signal import pause
import redis
import RPi.GPIO as GPIO
from module.cinepi import Config, CinePi, CinePiController
from module.monitor import DriveMonitor
from module.simple_gui import SimpleGUI
from module.manual_controls import ManualControls

# Create the Redis connection
r = redis.Redis(host=Config.REDIS_HOST, port=Config.REDIS_PORT, db=Config.REDIS_DB)

# Instantiate the CinePi instance
cinepi = CinePi(r)

# Instantiate the CinePi instance and CinePiController
cinepi_controller = CinePiController(cinepi, r)

# Instantiate and start the Monitor instance
monitor = DriveMonitor('/media/RAW/', gpio_pin=5)
threading.Thread(target=monitor.start_space_monitoring, args=(0.1,)).start()


# Initialize SimpleGUI with the controller and monitor instances
simple_gui = SimpleGUI(cinepi_controller, monitor)

# Display current camera settings
print()
print("Camera Settings:")
print("ISO:", cinepi_controller.get_control_value('iso'))
print("Shutter Angle:", cinepi_controller.get_control_value('shutter_a'))
print("FPS:", cinepi_controller.get_control_value('fps'))
print("Resolution:", cinepi_controller.get_control_value('height'))
print()

# Example: Set ISO value
cinepi_controller.set_control_value('iso', 200)

# Example: Start recording
cinepi_controller.start_recording()

# Record for 5 seconds)
sleep(5)

# Example: Stop recording
cinepi_controller.stop_recording()

# Example: Reporting function
def report_last_recording():
    last_subfolder = monitor.get_last_subfolder()
    last_wav_file = monitor.get_last_wav_file()
    print()
    print("Last Recorded Clip:")
    print("Subfolder:", last_subfolder)
    if last_wav_file:
        print("WAV File:", last_wav_file)
    else:
        print("No WAV File found.")
    print()

# Call the reporting function
report_last_recording()

# Cleanup GPIO
GPIO.cleanup()
