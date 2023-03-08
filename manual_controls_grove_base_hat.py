import time
import RPi.GPIO as GPIO
from adc import ADC
from redis_proxy import CameraParameters, RedisMonitor
from signal import pause

monitor = RedisMonitor('cp_stats')

GPIO.setwarnings(False) # Ignore warning for now
GPIO.setmode(GPIO.BCM) # Use GPIO pin numbering

# Set GPIO functions
rec_pin = 5             #rec pin
rec_out_pin = 6         #rec out pin
res_switch = 24         #resolution switch
fps_half_switch = 16    #frame rate half speed
fps_double_switch = 17  #frame rate double speed

shu_sync_mode_switch = 26     #shutter angle fps_sync mode
fps_lock_switch = 18    #frame rate lock switch 
safe_shutdown_pin = 7  #pin for safe shutdown
pwmPin = 41             #rec signal out pin (RPi headphone jack right channel)

GPIO.setup(rec_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(rec_out_pin, GPIO.OUT)
GPIO.setup(res_switch, GPIO.IN, pull_up_down=G PIO.PUD_UP)
GPIO.setup(fps_half_switch, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(fps_double_switch, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(shu_sync_mode_switch, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(fps_lock_switch, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(safe_shutdown_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(pwmPin, GPIO.OUT)

# Set PWM out
p = GPIO.PWM(pwmPin, 50)

# Load ADC
adc = ADC()

# Set channels for potentiometers
iso_pot = 0
shutter_angle_pot = 2
fps_pot = 4

# Set arrays for legal ISO, SHUTTER SPEED and FPS
iso_steps = [100,200,400,500,640,800,1000,1200,2000,2500,3200]  #ISO values (100-3200)
shutter_angle_steps = [*range(0, 361, 1)]                       #SHUTTER ANGLE values (1-360)
shutter_angle_steps[0] = 1                                      

fps_steps = [*range(0, 51, 1)]                                  #FPS values (1-50)
fps_steps[0] = 1

# Load instances for reading and writing camera parameters
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

if GPIO.input(fps_half_switch) == 0: 
    fps_multiplier = 0.5
if GPIO.input(fps_double_switch) == 0:
    fps_multiplier = 2
if GPIO.input(fps_half_switch) == 1 and GPIO.input(fps_double_switch) == 1:
    fps_multiplier = 1

shu_sync_mode = 1    
fps_lock = 0 

def start_stop_record(channel):

    if is_increasing == False:
        is_recording_setting.set("1") 
        p.start(20)   
        
    if is_increasing == True:
        is_recording_setting.set("0")
        p.stop()
        
def change_res(channel):
    if resolution_setting.get() == "1080": resolution_setting.set("1520")     # full frame
    elif resolution_setting.get() == "1520" or resolution_setting.get() == "3040": resolution_setting.set("1080")     # cropped frame
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
    fps_lock = GPIO.input(fps_lock_switch)

    
# Set callbacks for interrupts
GPIO.add_event_detect(rec_pin, GPIO.FALLING, callback=start_stop_record, bouncetime=600)
GPIO.add_event_detect(res_switch, GPIO.FALLING, callback=change_res)
GPIO.add_event_detect(fps_half_switch, GPIO.BOTH, callback=set_fps_multiplier)
GPIO.add_event_detect(fps_double_switch, GPIO.BOTH, callback=set_fps_multiplier)
GPIO.add_event_detect(shu_sync_mode_switch, GPIO.RISING, callback=set_shu_sync_mode, bouncetime=400)
GPIO.add_event_detect(fps_lock_switch, GPIO.BOTH, callback=set_fps_lock)


while True:
    
    monitor.listen()
    is_increasing = monitor.is_number_increasing()
    
    if is_increasing == True:
        GPIO.output(rec_out_pin,GPIO.HIGH)
    else:
        GPIO.output(rec_out_pin,GPIO.LOW)
    
    iso_read = adc.read(iso_pot)
    shutter_angle_read = adc.read(shutter_angle_pot)
    fps_read = adc.read(fps_pot)
    
    if abs(iso_read - iso_read_old) > 1000/len(iso_steps):
        iso_new = iso_steps[round((len(iso_steps)-1)*adc.read(iso_pot)/999)]
        iso_setting.set(iso_new)
        iso_read_old = iso_read
        
    if abs(shutter_angle_read - shutter_angle_read_old) > 1000/len(shutter_angle_steps):
        shutter_angle_new = shutter_angle_steps[round((len(shutter_angle_steps)-1)*adc.read(shutter_angle_pot)/1000)]
        shutter_angle_setting.set(shutter_angle_new)
        shutter_angle_read_old = shutter_angle_read
    shutter_angle_set = 180
        
    if abs(fps_read - fps_read_old) > 1000/len(fps_steps) and not fps_lock:
        fps_new = fps_steps[round((len(fps_steps)-1)*adc.read(fps_pot)/999)]
        print("fps: " + str(fps_new))
        fps_setting.set(fps_new)
        fps_read_old = fps_read
        if shu_sync_mode == 1:
            shutter_angle_fps_synced_setting.set(shutter_angle_set)
            
    print("iso: ", iso_setting.get())
    print("shutter_angle: ", shutter_angle_setting.get())
    print("fps: ", fps_setting.get())
    print()
    print("res", resolution_setting.get())
    print("shu_sync_mode: ", str(shu_sync_mode))
    print("fps_lock: ", str(fps_lock))
    print()
    print("is recording", is_increasing)
     
    
    time.sleep(0.1)
 
