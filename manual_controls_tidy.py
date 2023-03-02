import time
import RPi.GPIO as GPIO
from adc import ADC
from redis_proxy import CameraParameters, RedisMonitor
from signal import pause

# Initialize RedisMonitor instance

monitor = RedisMonitor('cp_stats')

# Suppress warning and set GPIO mode

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# Define GPIO pins

rec_pin = 18
rec_out_pin = 19
res_switch = 26
fps_half_switch = 16
fps_double_switch = 17
shu_sync_mode_switch = 5
fps_lock_switch = 22
safe_shutdown_pin = 24
pwm_pin = 41

# Set GPIO functions and states

GPIO.setup(rec_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(res_switch, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(fps_half_switch, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(fps_double_switch, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(shu_sync_mode_switch, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(fps_lock_switch, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(safe_shutdown_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(pwm_pin, GPIO.OUT)

# Set initial PWM output

pwm = GPIO.PWM(pwm_pin, 50)

# Initialize ADC instance

adc = ADC()

# Set channels for potentiometers

iso_pot = 0
shutter_angle_pot = 2
fps_pot = 4

# Set arrays for legal ISO, SHUTTER SPEED and FPS

iso_steps = [100, 200, 400, 500, 640, 800, 1000, 1200, 2000, 2500, 3200]
shutter_angle_steps = [*range(0, 361)]
shutter_angle_steps[0] = 1
fps_steps = [*range(1, 51)]

# Initialize CameraParameter instances for different settings

iso_setting = CameraParameters("ISO")
shutter_angle_setting = CameraParameters("SHUTTER")
shutter_angle_fps_synced_setting = CameraParameters("SHUTTER_FPS_SYNCED")
fps_setting = CameraParameters("FPS")
is_recording_setting = CameraParameters("IS_RECORDING")
resolution_setting = CameraParameters("RESOLUTION")

# Set initial values

iso = 100
shutter_angle = 180
fps = 24
iso_read_old = 100
shutter_angle_read_old = 180
fps_read_old = 24

# Set initial values for FPS multiplier, shutter sync mode, and FPS lock

fps_multiplier = 1
shu_sync_mode = 1
fps_lock = 0

# Define callback functions

def start_stop_record(channel):
    global pwm
    is_recording = is_recording_setting.get()
    if is_recording == "0":
        is_recording_setting.set("1")
        pwm.start(20)
    elif is_recording == "1":
        is_recording_setting.set("0")
        pwm.stop()

def change_res(channel):
    res_setting = resolution_setting.get()
    if res_setting == "1080":
     resolution_setting.set("1520")
    elif res_setting in ["1520", "3040"]:
        resolution_setting.set("1080")
    print("res: ", resolution_setting.get())

def set_fps_multiplier(channel):
    global fps_multiplier
    fps_multiplier = 1
    if GPIO.input(fps_half_switch) == 0: 
        fps_multiplier = 0.5
    if GPIO.input(fps_double_switch) == 0:
        fps_multiplier = 2
    if GPIO.input(fps_half_switch) == 1 and GPIO.input(fps_double_switch) == 1:
        fps_multiplier = 1
    
    fps_old = 24
    fps_new = int((fps_old*fps_multiplier))
    fps_new = min(max(fps_new, 1), 50)
    
    fps_setting.set(int(fps_new))
    print(fps_multiplier)

def set_shu_sync_mode(channel):
    global shu_sync_mode
    shu_sync_mode = GPIO.input(shu_sync_mode_switch)
    if shu_sync_mode == 1:
        shutter_angle_fps_synced_setting.set(shutter_angle_set)
        
def set_fps_lock(channel):
    global fps_lock
    fps_lock = GPIO.input(shu_sync_mode_switch)
    
# Set callbacks for interrupts

GPIO.add_event_detect(rec_pin, GPIO.FALLING, callback=start_stop_record, bouncetime=600)
GPIO.add_event_detect(res_switch, GPIO.FALLING, callback=change_res)
GPIO.add_event_detect(fps_half_switch, GPIO.BOTH, callback=set_fps_multiplier)
GPIO.add_event_detect(fps_double_switch, GPIO.BOTH, callback=set_fps_multiplier)
GPIO.add_event_detect(shu_sync_mode_switch, GPIO.RISING, callback=set_shu_sync_mode, bouncetime=400)
GPIO.add_event_detect(fps_lock_switch, GPIO.BOTH, callback=set_fps_lock)

# Start monitoring Redis keys

monitor.monitor('ISO')
monitor.monitor('SHUTTER')
monitor.monitor('FPS')

try:
    while True:
        # Read ISO potentiometer
        iso_pot_read = adc.read(iso_pot)
        iso_pot_read = int(round(iso_pot_read/100)*100)

        if iso_pot_read != iso:
            if iso_pot_read in iso_steps:
                iso_setting.set(iso_pot_read)
                iso = iso_pot_read

        # Read shutter angle potentiometer
        shutter_angle_pot_read = adc.read(shutter_angle_pot)
        shutter_angle_pot_read = int(round(shutter_angle_pot_read))

        if shutter_angle_pot_read != shutter_angle:
            if shutter_angle_pot_read in shutter_angle_steps:
                shutter_angle_setting.set(shutter_angle_pot_read)
                shutter_angle = shutter_angle_pot_read

                if shu_sync_mode == 1:
                    shutter_angle_fps_synced_setting.set(shutter_angle)
            
        # Read FPS potentiometer
        fps_pot_read = adc.read(fps_pot)
        fps_pot_read = int(round(fps_pot_read))

        if fps_pot_read != fps:
            if fps_pot_read in fps_steps:
                fps_new = int(fps_pot_read*fps_multiplier)
                fps_new = min(max(fps_new, 1), 50)

                if fps_new != fps:
                    fps_setting.set(fps_new)
                    fps = fps_new
            
        # Read camera parameters from Redis
        iso_read = int(iso_setting.get())
        shutter_angle_read = int(shutter_angle_setting.get())
        shutter_angle_fps_synced_read = int(shutter_angle_fps_synced_setting.get())
        fps_read = int(fps_setting.get())
        is_recording_read = int(is_recording_setting.get())
        resolution_read = int(resolution_setting.get())

        # Set PWM duty cycle for recording signal
        if is_recording_read == 1:
            p.ChangeDutyCycle(90)
        else:
            p.ChangeDutyCycle(0)

        # Print camera parameters to console
        if iso_read != iso_read_old:
            print("ISO: ", iso_read)
            iso_read_old = iso_read

        if shutter_angle_read != shutter_angle_read_old:
            print("Shutter angle: ", shutter_angle_read)
            shutter_angle_read_old = shutter_angle_read

        if fps_read != fps_read_old:
            print("FPS: ", fps_read)
            fps_read_old = fps_read

        # Sleep for 100ms
        time.sleep(0.1)

except KeyboardInterrupt:
    pass

# Clean up GPIO pins
GPIO.cleanup()