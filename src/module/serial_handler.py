import serial.tools.list_ports
import time
import threading
import logging
import queue
import serial

class SerialHandler(threading.Thread):
    def __init__(self, callback, baudrate=9600, timeout=1, log_queue=None):
        threading.Thread.__init__(self)
        self.serials = []
        self.baudrate = baudrate
        self.timeout = timeout
        self.callback = callback
        
        self.log_queue = log_queue
        
        self.portlist = ['/dev/ttyACM0', '/dev/serial0', '/dev/ttyS0']
         
        self.current_ports = []

        # Start with checking available poarts during the creation of the object 
        self.update_available_ports()

        if len(self.serials) == 0:
            logging.info("No USB serial devices")

        self.running = True
        
        self.last_received_time = {}  # Initialize a dictionary to store timestamps for each port

    def write_to_ports(self, message):
        for ser in self.serials:
            try:
                # Ensure the message ends with a newline character
                if not message.endswith('\n'):
                    message += '\n'
                    
                if 'Sending' not in message:
                    ser.write(message.encode('utf-8'))
                    logging.info(f"Sending on {ser.port} {message}")
            except UnicodeEncodeError as uee:
                logging.error(f"Encoding error for message {message}: {str(uee)}")
            except (OSError, serial.SerialException) as e:
                logging.error(f"Could not write to port {ser.port}: {str(e)}")
                self.serials.remove(ser)
                ser.close()

    def read_from_ports(self):

        responses = []
        threshold_time = 0  # 100 ms threshold

        for ser in self.serials:
            try:
                while ser.in_waiting:
                    line = ser.readline()

                    # Decoding binary line to UTF-8 string, ignoring non-printable characters
                    string_line = line.decode('utf-8')
                    
                    null_string = r"b'\x00'"
                    
                    # Check if the line is a NULL character
                    if null_string in string_line:
                        logging.info(f"Received NULL from {ser.port}. Ignoring.")
                        continue
                    
                    # Check if message on the same port is received within the threshold time
                    current_time = time.time()
                    last_time = self.last_received_time.get(ser.port, 0)
                    if current_time - last_time < threshold_time:
                        logging.info(f"Ignoring message received within {threshold_time * 1000} ms on {ser.port}")
                        continue
                    
                    # Update the last received time for the port
                    self.last_received_time[ser.port] = current_time
                    
                    responses.append((ser.port, string_line.strip()))

            except (OSError, serial.SerialException) as e:
                logging.error(f"Failed to read from {ser.port}: {e}")
                logging.info(f"Failed to read from {ser.port}: {e}")
                self.serials.remove(ser)
                ser.close()

        if responses:
            for port, response in responses:   
                logging.info(f'Received from {port}: {response}')
                # Check if the response is not a NULL character before calling the callback
                if not "b'\x00'" in response:
                    self.callback(response)

        return responses

    def update_available_ports(self):
        # Close ports that are no longer available
        for ser in self.serials:
            if ser.port not in self.portlist:
                ser.close()
                self.serials.remove(ser)

        # Open new available ports
        for port in self.portlist:

            # Update current_ports at each iteration to reflect serials list state.
            self.current_ports = [ser.port for ser in self.serials]

            if port not in self.current_ports:
                try:
                    self.serials.append(serial.Serial(port, self.baudrate, timeout=self.timeout))
                    logging.info(f"Successfully opened port {port}")

                    # After opening a new port, update current_ports again
                    self.current_ports = [ser.port for ser in self.serials]
                    logging.info(f"current ports {self.current_ports}")
                except serial.SerialException as e:
                    continue
 
    def run(self):
        while self.running:
            # Update available ports at each iteration
            self.update_available_ports()

            responses = self.read_from_ports()
            if responses:
                for port, response in responses:   
                    logging.info(f'Received from {port}: {response.strip()}') 
                
            # # Check the log queue and send log messages over the serial port
            # try:
            #     # if '/dev/serial0' in self.current_ports:
            #     while not self.log_queue.empty():  # Process all log messages in the queue
            #         log_message = self.log_queue.get_nowait()  # Non-blocking get
            #         try:
            #             self.write_to_ports(log_message)  # Write each log message to the ports
            #         except Exception as e:  # Handle exceptions that occur while writing to the ports
            #             logging.error(f"Failed to write log message to ports: {str(e)}")
            # except queue.Empty:
            #     print("Queue is Empty!")  # Debugging print

            time.sleep(0.01)