# Import required modules
import threading  
import time  
import datetime 
import os  
import inspect 
import logging  

class CommandExecutor(threading.Thread):
    def __init__(self, cinepi_controller, system_button):
        threading.Thread.__init__(self)  # Initialize thread
        self.cinepi_controller = cinepi_controller  # Set controller object reference
        self.system_button = system_button  # Set button object reference
        
        # Define dictionary of available commands and their associated functions along with expected argument type.
        # This allows for dynamic command calling
        self.commands = {
            'rec': (cinepi_controller.rec_button_pushed, None),  # Record command  
            'stop': (cinepi_controller.rec_button_pushed, None),  # Stop command 
            'iso': (cinepi_controller.set_iso, int),  # ISO setting command 
            'shutter_a': (cinepi_controller.set_shutter_a, float),  # Shutter_a setting command
            'shutter_a_nom': (cinepi_controller.set_shutter_a_nom, float),  # Shutter_a_nom setting command  
            'fps': (cinepi_controller.set_fps, int),  # FPS setting command 
            'res': (cinepi_controller.set_resolution, int),  # Resolution setting command 
            'unmount': (system_button.unmount_drive, None),  # Unmount command
            'time': (self.display_time, None),  # Time display command
            'set_rtc_time': (self.set_rtc_time, None),  # RTC time setting command
            'space': (cinepi_controller.ssd_monitor.output_ssd_space_left, None),  # SSD space left command
            'get': (cinepi_controller.print_settings, None),
            'pwm': (cinepi_controller.set_pwm_mode, int),  # Ramp mode command
            'shutter_sync': (cinepi_controller.set_shutter_a_sync, int)  # Sync shutter to fps
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
    
    # Function to handle received data
    def handle_received_data(self, data):
        logging.info(f"Received: {data}")  # Log the received data
        input_command = data.split()  # Split the input into command and arguments

        if len(input_command) == 0 or not input_command[0]:
            return  # If there's no command provided
        
        command_name = input_command[0]  # Extract the command name from the input
        
        if command_name in self.commands:
            func, expected_type = self.commands[command_name]  # Extract function and expected type from commands dictionary
            arg_spec = inspect.getfullargspec(func)  # Get list of arguments that func takes 
            is_bound_method = inspect.ismethod(func)  # Check if func is bound method
            num_args = len(arg_spec.args) - 1 if is_bound_method else len(arg_spec.args)  # Get number of required arguments for the function
            
            if len(input_command) > 1:  # If command has arguments
                command_args = input_command[1]  # Extract command arguments from the input

                # Check if the argument is "inc" or "dec" (increase, decrease), 
                # and corresponding method is available in cinepi_controller.
                # If available, execute the function. If not, continue to other checks.
                if command_args.lower() == "inc" and hasattr(self.cinepi_controller, f"inc_{command_name}"):
                    getattr(self.cinepi_controller, f"inc_{command_name}")()
                    return
                elif command_args.lower() == "dec" and hasattr(self.cinepi_controller, f"dec_{command_name}"):
                    getattr(self.cinepi_controller, f"dec_{command_name}")()
                    return
                # If the input command needs extra argument and the type of the argument is correct, call the command with the argument.
                elif num_args > 0 and expected_type and self.is_valid_arg(command_args, expected_type):
                    func(expected_type(command_args))
                    return
                else:
                    # If command does not take parameters or if an improper parameter type is specify a message will be logged and the function will return.
                    logging.info(f"Command '{command_name}' does not take parameters or invalid parameter type")
                    return
            else:
                # If no argument is provided and the command requires at least one argument
                if num_args > 0:
                    logging.info(f"Command '{command_name}' missing required parameter")
                else:
                    # if operration does not require parameters, then call the operation directly
                    func()
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
