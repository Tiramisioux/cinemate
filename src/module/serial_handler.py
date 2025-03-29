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

        self.serial_connected = False  # Flag to indicate USB serial device connection

        self.running = True
        self.last_received_time = {}  # Track last received time for each port

        # Initial scan for available ports
        self.update_available_ports()

        if len(self.serials) == 0:
            logging.info("No USB serial devices")

    def write_to_ports(self, message):
        for ser in self.serials:
            try:
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

        for ser in self.serials[:]:
            try:
                while ser.in_waiting:
                    line = ser.readline()
                    string_line = line.decode('utf-8')

                    if r"b'\x00'" in string_line:
                        logging.info(f"Received NULL from {ser.port}. Ignoring.")
                        continue

                    current_time = time.time()
                    last_time = self.last_received_time.get(ser.port, 0)
                    if current_time - last_time < threshold_time:
                        logging.info(f"Ignoring message received within {threshold_time * 1000} ms on {ser.port}")
                        continue

                    self.last_received_time[ser.port] = current_time
                    responses.append((ser.port, string_line.strip()))

            except (OSError, serial.SerialException) as e:
                logging.error(f"Failed to read from {ser.port}: {e}")
                logging.info(f"Failed to read from {ser.port}: {e}")
                if ser.port == '/dev/ttyACM0':
                    self.serial_connected = False
                self.serials.remove(ser)
                ser.close()

        if responses:
            for port, response in responses:
                logging.info(f'Received from {port}: {response}')
                if not "b'\x00'" in response:
                    self.callback(response)

        return responses

    def update_available_ports(self):
        for ser in self.serials[:]:
            if ser.port not in self.portlist:
                ser.close()
                self.serials.remove(ser)

        self.current_ports = [ser.port for ser in self.serials]

        for port in self.portlist:
            if port not in self.current_ports:
                try:
                    ser = serial.Serial(port, self.baudrate, timeout=self.timeout)
                    self.serials.append(ser)
                    logging.info(f"Successfully opened port {port}")
                    self.current_ports = [s.port for s in self.serials]

                    if port == '/dev/ttyACM0':
                        self.serial_connected = True

                except serial.SerialException:
                    continue

        # Reconfirm state in case ACM0 was removed in previous step
        if '/dev/ttyACM0' not in self.current_ports:
            self.serial_connected = False

    def run(self):
        while self.running:
            self.update_available_ports()
            responses = self.read_from_ports()
            if responses:
                for port, response in responses:
                    logging.info(f'Received from {port}: {response.strip()}')
            time.sleep(0.01)
