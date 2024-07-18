import subprocess
import logging
from queue import Queue
from threading import Thread
import re

class Event:
    def __init__(self):
        self._listeners = []

    def subscribe(self, listener):
        self._listeners.append(listener)

    def emit(self, data=None):
        for listener in self._listeners:
            listener(data)

def enqueue_output(out, queue, event):
    for line in iter(out.readline, b''):
        queue.put(line)
        event.emit(line.decode('utf-8'))
    out.close()

class CinePi:
    _instance = None  # Singleton instance

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, redis_controller, sensor_detect):
        if not hasattr(self, 'initialized'):  # only initialize once
            self.message = Event()
            self.redis_controller = redis_controller
            self.sensor_detect = sensor_detect
            self.default_args = self.get_default_args(sensor_detect)
            self.process = None
            
            # Logging control
            self.log_levels = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR,
                'CRITICAL': logging.CRITICAL
            }
            self.log_filters = {
                'frame': re.compile(r'\[event_loop\] \[info\] Frame Number: \d+'),
                'agc': re.compile(r'WARN RPiAgc'),
                'ccm': re.compile(r'WARN RPiCcm'),
                # Add more patterns as needed
            }
            self.active_filters = set(['frame', 'agc', 'ccm'])  # Default active filters
            
            # self.start_cinepi_process()
            self.initialized = True
            logging.info('CinePi instantiated')

    def get_default_args(self, sensor_detect):
        sensor_mode = int(self.redis_controller.get_value('sensor_mode'))
        sensor_model = sensor_detect.camera_model
        tuning_file_path = f'/home/pi/libcamera/src/ipa/rpi/pisp/data/{sensor_model}.json'
        
        return [
            '--mode', f"{sensor_detect.get_width(sensor_model, sensor_mode)}:{sensor_detect.get_height(sensor_model, sensor_mode)}:{sensor_mode}:U",
            '--width', str(sensor_detect.get_width(sensor_model, sensor_mode)),
            '--height', str(sensor_detect.get_height(sensor_model, sensor_mode)),
            '--lores-width', str(sensor_detect.get_lores_width(sensor_model, sensor_mode)),
            '--lores-height', str(sensor_detect.get_lores_height(sensor_model, sensor_mode)),
            '-p', '0,30,1920,1020',
            '--post-process-file', '/home/pi/post-processing.json',
            '--tuning-file', tuning_file_path,
            '--shutter', '20000',
            '--awbgains', '1,1',
        ]

    def start_cinepi_process(self, cinepi_args=None):
        if cinepi_args is None:
            cinepi_args = self.default_args
        else:
            cinepi_args = list(cinepi_args) + self.default_args

        command = ['cinepi-raw'] + cinepi_args
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        self.out_queue = Queue()
        self.err_queue = Queue()

        self.out_thread = Thread(target=self.process_output, args=(self.process.stdout, self.out_queue))
        self.err_thread = Thread(target=self.process_output, args=(self.process.stderr, self.err_queue))

        self.out_thread.daemon = True
        self.err_thread.daemon = True
        self.out_thread.start()
        self.err_thread.start()

    def process_output(self, out, queue):
        for line in iter(out.readline, b''):
            decoded_line = line.decode('utf-8').strip()
            queue.put(decoded_line)
            self.message.emit(decoded_line)
            self.log_message(decoded_line)
        out.close()

    def log_message(self, message):
        for filter_name, pattern in self.log_filters.items():
            if filter_name in self.active_filters and pattern.search(message):
                if 'WARN' in message:
                    logging.warning(f"[cinepi-raw] {message}")
                else:
                    logging.info(f"[cinepi-raw] {message}")
                break

    def set_log_level(self, level):
        if level in self.log_levels:
            logging.getLogger().setLevel(self.log_levels[level])
            logging.info(f"Log level set to {level}")
        else:
            logging.error(f"Invalid log level: {level}")

    def set_active_filters(self, filters):
        self.active_filters = set(filters)
        logging.info(f"Active filters set to: {', '.join(self.active_filters)}")

    def shutdown(self):
        """Shut down the CinePi instance."""
        if self.process is not None:
            fps_last = self.redis_controller.get_value('fps')
            self.redis_controller.set_value('fps_last', fps_last)
            logging.info('Shutting down CinePi instance.')
            self.process.terminate()
            self.process.wait()
            logging.info('CinePi instance shut down.')

    def restart(self):
        """Restart the CinePi instance."""
        logging.info('Restarting CinePi instance.')
        fps_last = self.redis_controller.get_value('fps')
        self.redis_controller.set_value('fps_last', fps_last)
        self.shutdown()
        # Restart the process with default arguments
        self.start_cinepi_process()
        logging.info('CinePi instance restarted.')
