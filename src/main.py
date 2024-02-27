import logging
import sys
import traceback
import threading
import RPi.GPIO as GPIO
from signal import pause
import json

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

from module.redis_controller import RedisController
from module.cinepi_app import CinePi
from module.usb_monitor import USBMonitor
from module.ssd_monitor import SSDMonitor
from module.gpio_output import GPIOOutput
from module.cinepi_controller import CinePiController
from module.simple_gui import SimpleGUI
from module.gpio_input import GPIOInput
from module.analog_controls import AnalogControls
from module.grove_base_hat_adc import ADC
from module.keyboard import Keyboard
from module.system_button import SystemButton
from module.cli_commands import CommandExecutor
from module.serial_handler import SerialHandler
from module.logger import configure_logging
from module.rotary_encoder import SimpleRotaryEncoder
from module.PWMcontroller import PWMController
from module.sensor_detect import SensorDetect
from module.mediator import Mediator
from module.dmesg_monitor import DmesgMonitor
from module.redis_listener import RedisListener

MODULES_OUTPUT_TO_SERIAL = ['cinepi_controller']

def load_settings(filename):
    with open(filename, 'r') as file:
        settings = json.load(file)
        additional_shutter_a_steps = settings.get('additional_shutter_a_steps', [])
        shutter_a_steps = sorted(set(range(1, 361)).union(additional_shutter_a_steps))
        settings['shutter_a_steps'] = shutter_a_steps
        return settings

if __name__ == "__main__":

    logger, log_queue = configure_logging(MODULES_OUTPUT_TO_SERIAL)
    
    settings = load_settings('/home/pi/cinemate/src/settings.json')

    # Detect sensor
    sensor_detect = SensorDetect()
    
    # Instantiate the PWMController
    pwm_controller = PWMController(sensor_detect, PWM_pin=settings['pwm_pin'])

    # Instantiate the CinePi instance
    cinepi_app = CinePi()

    # Instantiate other necessary components
    redis_controller = RedisController()
    ssd_monitor = SSDMonitor()
    usb_monitor = USBMonitor(ssd_monitor)
    gpio_output = GPIOOutput(rec_out_pin=settings['rec_out_pin'])
    
    dmesg_monitor = DmesgMonitor("/var/log/kern.log")
    dmesg_monitor.start() 

    # Instantiate the CinePiController with all necessary components and settings
    cinepi_controller = CinePiController(pwm_controller,
                                        redis_controller,
                                        usb_monitor, 
                                        ssd_monitor,
                                        sensor_detect,
                                        iso_steps=settings['iso_steps'],
                                        shutter_a_steps=settings['shutter_a_steps'],
                                        fps_steps=settings['fps_steps']
                                        )

    # Instantiate the AnalogControls component
    analog_controls = AnalogControls(cinepi_controller, iso_pot=settings['analog_controls']['iso_pot'], shutter_a_pot=settings['analog_controls']['shutter_a_pot'], fps_pot=settings['analog_controls']['fps_pot'])

    # Instantiate the GPIOControls component
    gpio_input = GPIOInput(cinepi_controller, redis_controller, **settings['gpio_input'])

    # Instantiate SystemButton
    system_button = SystemButton(cinepi_controller, redis_controller, ssd_monitor, **settings['system_button'])
                                
    # Instantiate a rotary encoder for ISO control
    iso_encoder = SimpleRotaryEncoder(cinepi_controller, setting="iso", clk=settings['iso_encoder']['clk'], dt=settings['iso_encoder']['dt'])

    # Instantiate a rotary encoder for shutter angle control
    shu_encoder = SimpleRotaryEncoder(cinepi_controller, setting="shutter_a_nom", clk=settings['shu_encoder']['clk'], dt=settings['shu_encoder']['dt'])

    # Instantiate a rotary encoder for fps control
    fps_encoder = SimpleRotaryEncoder(cinepi_controller, setting="fps", clk=settings['fps_encoder']['clk'], dt=settings['fps_encoder']['dt'])

    # Instantiate the Mediator and pass the components to it
    mediator = Mediator(cinepi_app, redis_controller, usb_monitor, ssd_monitor, gpio_output)

    # Only after the mediator has been set up and subscribed to the events,
    # we can trigger methods that may cause the events to fire.
    usb_monitor.check_initial_devices()
    
    keyboard = Keyboard(cinepi_controller, usb_monitor)
    
    # Instantiate the CommandExecutor with all necessary components and settings
    command_executor = CommandExecutor(cinepi_controller, system_button)

    # Start the CommandExecutor thread
    command_executor.start()
    
    serial_handler = SerialHandler(command_executor.handle_received_data, 9600, log_queue=log_queue)
    serial_handler.start()
    

    
    redis_listener = RedisListener(redis_controller)
    
    simple_gui = SimpleGUI(pwm_controller, 
                           redis_controller, 
                           cinepi_controller, 
                           usb_monitor, 
                           ssd_monitor, 
                           serial_handler,
                           dmesg_monitor
                           )

    # Log initialization complete message
    logging.info(f"--- initialization complete")

    try:
        redis_controller.set_value('is_recording', 0)
        redis_controller.set_value('is_writing', 0)
        # Pause program execution, keeping it running until interrupted
        pause()
    except Exception:
        logging.error("An unexpected error occurred:\n" + traceback.format_exc())
        sys.exit(1)
    finally:
        # Reset trigger mode to deafult 0
        pwm_controller.stop_pwm()
        pwm_controller.set_trigger_mode(0)
        # Reset redis values to default
        redis_controller.set_value('fps', 24)
        redis_controller.set_value('is_recording', 0)
        redis_controller.set_value('is_writing', 0)
        
        # Set recording status to 0  
        gpio_output.set_recording(0)
        
        dmesg_monitor.join()
        serial_handler.join()
        command_executor.join()
        
        # Cleanup GPIO pins
        GPIO.cleanup()


# import logging
# import sys
# import traceback
# import threading
# import RPi.GPIO as GPIO 

# GPIO.setwarnings(False)
# GPIO.setmode(GPIO.BCM)  # Set pin numbering mode first

# from signal import pause

# from module.redis_controller import RedisController
# from module.cinepi_app import CinePi
# from module.usb_monitor import USBMonitor
# from module.ssd_monitor import SSDMonitor
# from module.gpio_output import GPIOOutput
# from module.cinepi_controller import CinePiController
# from module.simple_gui import SimpleGUI
# from module.gpio_input import GPIOInput
# from module.analog_controls import AnalogControls
# from module.grove_base_hat_adc import ADC
# from module.keyboard import Keyboard
# from module.system_button import SystemButton
# from module.cli_commands import CommandExecutor
# from module.serial_handler import SerialHandler
# from module.logger import configure_logging
# from module.rotary_encoder import SimpleRotaryEncoder
# from module.PWMcontroller import PWMController
# from module.sensor_detect import SensorDetect
# from module.mediator import Mediator
# from module.dmesg_monitor import DmesgMonitor
# from module.redis_listener import RedisListener

# MODULES_OUTPUT_TO_SERIAL = ['cinepi_controller'] 

# if __name__ == "__main__":

#     logger, log_queue = configure_logging(MODULES_OUTPUT_TO_SERIAL)
    
#     # Detect sensor
#     sensor_detect = SensorDetect()
    
#     # Instantiate the PWMController
#     pwm_controller = PWMController(sensor_detect, PWM_pin=19)

#     # Instantiate the CinePi instance
#     cinepi_app = CinePi()

#     # Instantiate other necessary components
#     redis_controller = RedisController()
#     ssd_monitor = SSDMonitor()
#     usb_monitor = USBMonitor()
#     gpio_output = GPIOOutput(rec_out_pin=[6, 21])

#     # Instantiate the CinePiController with all necessary components and settings
#     cinepi_controller = CinePiController(pwm_controller,
#                                         redis_controller,
#                                         usb_monitor, 
#                                         ssd_monitor,
#                                         sensor_detect,
#                                         iso_steps=[100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],                # Array for selectable ISO values
#                                         shutter_a_steps=sorted([num for num in range(1, 361)] + [172.8, 346.6]),
#                                         fps_steps=None
#                                         )

#     # Instantiate the AnalogControls component
#     analog_controls = AnalogControls(cinepi_controller, iso_pot=0, shutter_a_pot=2, fps_pot=4)

#     # Instantiate the GPIOControls component
#     gpio_input = GPIOInput(cinepi_controller, redis_controller,
#                             rec_button=[4,5],
#                             iso_inc_button=27,    
#                             iso_dec_button=10,
#                             res_switch=None,
#                             pwm_switch=22, 
#                             shutter_a_sync_switch=16, 
#                             fps_button=12,
#                             fps_switch=None,
#                             pot_lock_switch=24,
#                             )     
#     # Instantiate SystemButton
#     system_button = SystemButton(cinepi_controller, redis_controller, ssd_monitor, system_button_pin=26)

                                
#     #Instantiate a rotary encoder for ISO control
#     iso_encoder = SimpleRotaryEncoder(
#                             cinepi_controller,
#                             setting="iso",
#                             pin_a=9,    #9
#                             pin_b=11)   #11
    
#     #Instantiate a rotary encoder for shutter angle control
#     shu_encoder = SimpleRotaryEncoder(
#                             cinepi_controller,
#                             setting="shutter_a_nom",
#                             pin_a=23,   #23
#                             pin_b=25)   #25
    
#     #Instantiate a rotary encoder for fps control
#     fps_encoder = SimpleRotaryEncoder(
#                             cinepi_controller,
#                             setting="fps",
#                             pin_a=8,    #8
#                             pin_b=7)    #7

#     # Instantiate the Mediator and pass the components to it
#     mediator = Mediator(cinepi_app, redis_controller, usb_monitor, ssd_monitor, gpio_output)

#     # Only after the mediator has been set up and subscribed to the events,
#     # we can trigger methods that may cause the events to fire.
#     usb_monitor.check_initial_devices()
    
#     keyboard = Keyboard(cinepi_controller, usb_monitor)
    
#     # Instantiate the CommandExecutor with all necessary components and settings
#     command_executor = CommandExecutor(cinepi_controller, system_button)

#     # Start the CommandExecutor thread
#     command_executor.start()
    
#     serial_handler = SerialHandler(command_executor.handle_received_data, 9600, log_queue=log_queue)
#     serial_handler.start()
    
#     dmesg_monitor = DmesgMonitor("/var/log/kern.log")
#     dmesg_monitor.start() 
    
#     redis_listener = RedisListener(redis_controller)
    
#     simple_gui = SimpleGUI(pwm_controller, 
#                            redis_controller, 
#                            cinepi_controller, 
#                            usb_monitor, 
#                            ssd_monitor, 
#                            serial_handler,
#                            dmesg_monitor
#                            )

#     # Log initialization complete message
#     logging.info(f"--- initialization complete")

#     try:
#         redis_controller.set_value('is_recording', 0)
#         redis_controller.set_value('is_writing', 0)
#         # Pause program execution, keeping it running until interrupted
#         pause()
#     except Exception:
#         logging.error("An unexpected error occurred:\n" + traceback.format_exc())
#         sys.exit(1)
#     finally:
#         # Reset trigger mode to deafult 0
#         pwm_controller.stop_pwm()
#         pwm_controller.set_trigger_mode(0)
#         # Reset redis values to default                              )
#         redis_controller.set_value('fps', 24)
#         redis_controller.set_value('is_recording', 0)
#         redis_controller.set_value('is_writing', 0)
        
#         # Set recording status to 0  
#         gpio_output.set_recording(0)
        
#         dmesg_monitor.join()
#         serial_handler.join()
#         command_executor.join()
        
#         # Cleanup GPIO pins
#         GPIO.cleanup()
