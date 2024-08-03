# Import required modules
import threading  
import time  
import datetime 
import os  
import logging  

class CommandExecutor(threading.Thread):
    def __init__(self, cinepi_controller, cinepi_app):
        threading.Thread.__init__(self)  # Initialize thread
        self.cinepi_controller = cinepi_controller  # Set controller object reference
        self.cinepi_app = cinepi_app
        
        # Define dictionary of available commands and their associated functions along with expected argument type.
        # This allows for dynamic command calling
        self.commands = {
            'rec': (cinepi_controller.rec, None),            
            'stop': (cinepi_controller.rec, None), 
                     
            'set iso': (cinepi_controller.set_iso, int),     
            'inc iso': (cinepi_controller.inc_iso, None),  
            'dec iso': (cinepi_controller.dec_iso, None),     
              
            'set shutter a': (cinepi_controller.set_shutter_a, float), 
            'inc shutter a': (cinepi_controller.inc_shutter_a, None),  
            'dec shutter a': (cinepi_controller.dec_shutter_a, None), 
             
            'set shutter a nom': (cinepi_controller.set_shutter_a_nom, float),   
            'inc shutter a nom': (cinepi_controller.inc_shutter_a_nom, None),  
            'dec shutter a nom': (cinepi_controller.dec_shutter_a_nom, None), 
                                   
            'set fps': (cinepi_controller.set_fps, float),  
            'inc fps': (cinepi_controller.inc_fps, None),  
            'dec fps': (cinepi_controller.dec_fps, None), 
            
            'set awb': (cinepi_controller.set_awb, int),
            'inc awb': (cinepi_controller.inc_awb, None),
            'dec awb': (cinepi_controller.dec_awb, None),
            
            'set resolution': (cinepi_controller.set_resolution, [int, None]),
             
            'unmount': (cinepi_controller.unmount, None),  
            'time': (self.display_time, None),  
            'set rtc time': (self.set_rtc_time, None),  
            'space': (cinepi_controller.ssd_monitor.space_left, None),  
            'get': (cinepi_controller.print_settings, None),
            
            'set pwm mode': (cinepi_controller.set_pwm_mode, [int, None]),
            'set trigger mode': (cinepi_controller.set_trigger_mode, [int, None]), 
            'set shutter a sync': (cinepi_controller.set_shutter_a_sync, [int, None]),  
            
            'set iso lock': (cinepi_controller.set_iso_lock, [int, None]),
            'set shutter a nom lock': (cinepi_controller.set_shutter_a_nom_lock, [int, None]),
            'set shutter a nom fps lock': (cinepi_controller.set_shu_fps_lock, [int, None]),
            'set fps lock': (cinepi_controller.set_fps_lock, [int, None]),
            'set all lock': (cinepi_controller.set_all_lock, [int, None]),
            
            'set wb': (cinepi_controller.set_wb, [int, None]),
            'inc wb': (cinepi_controller.inc_wb, [None]),
            'dec wb': (cinepi_controller.dec_wb, [None]),
            
            'set fps double': (cinepi_controller.set_fps_double, [int, None]),
            
            'reboot': (cinepi_controller.reboot, None),
            'shutdown': (cinepi_controller.safe_shutdown, None),
            
            'restart': (cinepi_app.restart, None)
        }

    def is_valid_arg(self, arg, expected_type):
        if expected_type == int:
            return arg.isdigit()
        elif expected_type == float:
            try:
                float(arg)
                parts = arg.split(".")
                # Check if it has only one decimal point or none and at most one digit after the decimal point
                return len(parts) <= 2 and (len(parts) == 1 or len(parts[1]) <= 1)
            except ValueError:
                return False
        elif expected_type == str:
            return True
        else:
            return expected_type is None

    
    # Function to get expected data type for a given command
    def get_expected_type_for_command(self, command_name):
        if command_name in self.commands:  
            return self.commands[command_name][1]  # Return the second element (expected type) of the tuple
        else:
            return None
    
    def handle_received_data(self, data):
        logging.info(f"Received: {data}")  # Log the received data
        input_command = data.strip().split()  # Split the input into command and possible arguments

        if not input_command:
            return  # If there's no command provided, just return

        # If there are multiple parts, determine if the last part is an argument
        if len(input_command) > 1:
            # Check if the last part is a valid argument or a part of the command
            if input_command[-1].isdigit() or self.is_valid_arg(input_command[-1], float):
                command_name = ' '.join(input_command[:-1])
                command_args = input_command[-1:]
            else:
                command_name = ' '.join(input_command)
                command_args = []
        else:
            # Only one part, it's the command name
            command_name = input_command[0]
            command_args = []

        if command_name in self.commands:
            func, expected_types = self.commands[command_name]  # Extract function and expected type(s)
            
            if isinstance(expected_types, list):
                if command_args:
                    arg = command_args[0]
                    for expected_type in filter(None, expected_types):
                        if self.is_valid_arg(arg, expected_type):
                            func(expected_type(arg))  # Call function with converted argument
                            return
                    logging.info(f"Invalid argument type for command '{command_name}'")
                else:
                    func()  # Call the function without arguments (toggle behavior)
            else:
                if command_args:  # If there are arguments provided
                    arg = command_args[0]
                    if self.is_valid_arg(arg, expected_types):
                        func(expected_types(arg))  # Call function with converted argument
                        return
                    else:
                        logging.info(f"Invalid argument type for command '{command_name}'")
                        return
                else:
                    if expected_types is not None:  # If the command expects an argument
                        logging.info(f"Command '{command_name}' missing required parameter")
                        return
                    else:  # If the command does not expect any arguments
                        func()  # Call the function without arguments
        else:
            logging.info(f"Command '{command_name}' not found")
    
    # Function to display system time and RTC time
    def display_time(self):
        logging.info(f"System Time: {datetime.datetime.now()}")  # Display current system time
        try:
            rtc_time = os.popen('hwclock -r').read().strip()  # Try to read RTC time
            logging.info(f"RTC Time:    {rtc_time}")  # Display the RTC time
        except:
            logging.info("Unable to read RTC time.")  # If unable to read RTC time, log error 
            
    # Function to set the RTC time using the system time
    def set_rtc_time(self):
        try:
            os.system('sudo hwclock --systohc')  # Try to sync RTC time with system time
            logging.info("RTC Time has been set to System Time")  # Log success
        except:
            logging.info("Unable to set the RTC time.")  # If unable to set RTC time, log error
        
    # Thread run function where data is continuously received and processed
    def run(self):
        while True:  # Infinite loop
            time.sleep(0.1)  # Pause for 100 ms
            data = input("\n> ")  # Read the input as a single string
            if data.strip():  # Proceed only if there is some non-whitespace input
                self.handle_received_data(data)  # Directly handle the received data
