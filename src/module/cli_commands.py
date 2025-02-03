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
            'set wb': (cinepi_controller.set_wb, [int, None]),
            'inc wb': (cinepi_controller.inc_wb, None),
            'dec wb': (cinepi_controller.dec_wb, None),
            'set resolution': (cinepi_controller.set_resolution, [int, None]),
            'unmount': (cinepi_controller.unmount, None),
            'time': (self.display_time, None),  # Fixed placement issue
            'set rtc time': (self.set_rtc_time, None),  # Fixed placement issue
            'space': (cinepi_controller.ssd_monitor.space_left, None),
            'get': (cinepi_controller.print_settings, None),
            'set pwm mode': (cinepi_controller.set_pwm_mode, [int, None]),
            'set trigger mode': (cinepi_controller.set_trigger_mode, [int, None]),  # Flexible arguments
            'set iso lock': (cinepi_controller.set_iso_lock, [int, None]),
            'set shutter a nom lock': (cinepi_controller.set_shutter_a_nom_lock, [int, None]),
            'set shutter a nom fps lock': (cinepi_controller.set_shu_fps_lock, [int, None]),
            'set fps lock': (cinepi_controller.set_fps_lock, [int, None]),
            'set all lock': (cinepi_controller.set_all_lock, [int, None]),
            'set fps double': (cinepi_controller.set_fps_double, [int, None]),
            'reboot': (cinepi_controller.reboot, None),
            'shutdown': (cinepi_controller.safe_shutdown, None),
            'restart': (cinepi_app.restart, None),
            'set iso free': (cinepi_controller.set_iso_free, [int, str]),
            'set shutter a free': (cinepi_controller.set_shutter_a_free, [int, str]),
            'set fps free': (cinepi_controller.set_fps_free, [int, str]),
            'set wb free': (cinepi_controller.set_wb_free, [int, str]),
            'set shutter a sync': (cinepi_controller.set_shutter_a_sync_mode, int),
            'set filter': (cinepi_controller.set_filter, [int]),
        }

    def display_time(self):
        """Displays the current system and RTC time."""
        logging.info(f"System Time: {datetime.datetime.now()}")  # Display current system time
        try:
            rtc_time = os.popen('hwclock -r').read().strip()  # Try to read RTC time
            logging.info(f"RTC Time:    {rtc_time}")  # Display the RTC time
        except:
            logging.info("Unable to read RTC time.")  # If unable to read RTC time, log error

    def set_rtc_time(self):
        """Sets the RTC time using the system time."""
        try:
            os.system('sudo hwclock --systohc')  # Try to sync RTC time with system time
            logging.info("RTC Time has been set to System Time")  # Log success
        except:
            logging.info("Unable to set the RTC time.")  # If unable to set RTC time, log error

    def is_valid_arg(self, arg, expected_type):
        """Validate arguments against expected types."""
        try:
            if expected_type == int:
                int(arg)
                return True
            elif expected_type == float:
                float(arg)
                return True
            elif expected_type == str:
                return True  # Strings are always valid
            else:
                return expected_type is None  # None means no argument is expected
        except ValueError:
            return False

    def handle_received_data(self, data):
        """Handles received input data and executes corresponding commands."""
        logging.info(f"Received: {data.strip()}")  # Log the received data
        input_command = data.strip().split()  # Split the input into parts

        if not input_command:
            return  # If there's no input, just return

        # Reconstruct the full command name by trying all possible matches
        command_name = None
        command_args = []

        # Start with the longest possible command name and reduce until match is found
        for i in range(len(input_command), 0, -1):
            potential_command = ' '.join(input_command[:i])
            if potential_command in self.commands:
                command_name = potential_command
                command_args = input_command[i:]
                break

        if not command_name:
            logging.info(f"Command '{data.strip()}' not found")
            return

        func, expected_types = self.commands[command_name]

        # Handle commands with arguments or those that can be called without arguments
        if isinstance(expected_types, list):  # If the command can take multiple types
            if command_args:  # Arguments provided
                arg = command_args[0]
                for expected_type in filter(None, expected_types):
                    if self.is_valid_arg(arg, expected_type):
                        func(expected_type(arg))  # Call function with converted argument
                        return
                logging.info(f"Invalid argument type for command '{command_name}'")
            else:
                func()  # Call the function without arguments
        else:  # Single expected type or no argument
            if command_args:  # Arguments provided
                arg = command_args[0]
                if self.is_valid_arg(arg, expected_types):
                    func(expected_types(arg))  # Call function with converted argument
                    return
                logging.info(f"Invalid argument type for command '{command_name}'")
            else:
                if expected_types is None:  # No arguments expected
                    func()  # Call the function without arguments
                else:
                    logging.info(f"Command '{command_name}' requires an argument")

    def run(self):
            """Thread run function to continuously process input commands."""
            while True:
                time.sleep(0.1)  # Pause for 100 ms
                data = input("\n> ")  # Read the input as a single string
                if data.strip():  # Proceed only if there is some non-whitespace input
                    self.handle_received_data(data)  # Directly handle the received data

