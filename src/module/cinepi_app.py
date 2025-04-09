import subprocess
import logging
from queue import Queue
from threading import Thread
import re
import time

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
            self.default_args = self.get_default_args()
            self.process = None
            
            # Get sensor resolution
            self.width = int(self.redis_controller.get_value("width"))
            logging.info(f'redis width: {self.width}')
            self.height = int(self.redis_controller.get_value("height"))
            logging.info(f'redis height: {self.height}')
            
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
                'vu': re.compile(r'\[VU\] \d+'),
                # Add more patterns as needed
            }
            # self.active_filters = set(['frame', 'agc', 'ccm'])  # Default active filters
            self.active_filters = set(['frame', 'agc', 'ccm', 'vu'])  # Block frame count messages from cinepi-raw
            
            # self.start_cinepi_process()
            self.initialized = True
            logging.info('CinePi instantiated')

    def get_default_args(self):
        sensor_mode = self.redis_controller.get_value('sensor_mode')
        if sensor_mode is None:
            sensor_mode = '0'
        else:
            sensor_mode = int(sensor_mode)

        self.sensor_detect.detect_camera_model()
        sensor_model = self.sensor_detect.camera_model
        pi_model = self.redis_controller.get_value("pi_model")

        # If we're on Pi 4 and using imx477, override packing
        packing_override = None
        if pi_model == "pi4" and sensor_model == "imx477":
            packing_override = 'P'

        tuning_file_path = f'/home/pi/libcamera/src/ipa/rpi/pisp/data/{sensor_model}.json'

        cg_rb = self.redis_controller.get_value('cg_rb')
        if cg_rb is None:
            cg_rb = '2.5,2.2'  # Default for IMX477 at 3200K

        self.width = int(self.redis_controller.get_value("width"))
        self.height = int(self.redis_controller.get_value("height"))

        self.aspect_ratio = self.width / self.height

        self.anamorphic_factor = self.redis_controller.get_value('anamorphic_factor')
        if self.anamorphic_factor is None:
            self.anamorphic_factor = 1.0
        else:
            self.anamorphic_factor = float(self.anamorphic_factor)

        frame_width = 1920
        frame_height = 1080
        padding_x = 94
        padding_y = 50

        available_width = frame_width - (2 * padding_x)
        available_height = frame_height - (2 * padding_y)

        lores_height = min(720, available_height)
        lores_width = int((lores_height * self.aspect_ratio) * self.anamorphic_factor)

        if lores_width > available_width:
            lores_width = available_width
            lores_height = int(round((lores_width / (self.aspect_ratio * self.anamorphic_factor))))

        self.redis_controller.set_value('lores_width', lores_width)
        self.redis_controller.set_value('lores_height', lores_height)

        preview_x, preview_y, preview_w, preview_h = self.calculate_preview_window(
            lores_width, lores_height, padding_x, padding_y, frame_width, frame_height
        )

        # Get bit depth and packing (possibly overridden)
        bit_depth = self.sensor_detect.get_bit_depth(sensor_model, sensor_mode)
        packing = self.sensor_detect.get_packing(sensor_model, sensor_mode)

        if packing_override is not None:
            logging.info(f"Overriding packing for {sensor_model} on {pi_model} to {packing_override}")
            packing = packing_override

        args = [
            '--mode', f"{self.width}:{self.height}:{bit_depth}:{packing}",
            '--width', f"{self.width}",
            '--height', f"{self.height}",
            '--lores-width', f"{lores_width}",
            '--lores-height', f"{lores_height}",
            '-p', f'{preview_x},{preview_y},{preview_w},{preview_h}',
            '--post-process-file', '/home/pi/post-processing.json',
            '--shutter', '20000',
            '--awbgains', cg_rb,
            '--awb', 'auto',
        ]

        return args

    def calculate_preview_window(self, width, height, padding_x, padding_y, output_width, output_height):
        """
        Calculate the preview window while maintaining the correct aspect ratio.

        - The preview will be centered within the output frame.
        - The aspect ratio will be preserved.
        - It ensures the preview is as large as possible within the available area.
        """
        # Calculate available space after padding
        max_width = output_width - (2 * padding_x)
        max_height = output_height - (2 * padding_y)

        # Calculate aspect ratio
        aspect_ratio = width / height

        # Scale based on available space while preserving aspect ratio
        if (max_width / max_height) > aspect_ratio:
            # Height is the limiting factor
            preview_h = max_height
            preview_w = int(preview_h * aspect_ratio)
        else:
            # Width is the limiting factor
            preview_w = max_width
            preview_h = int(preview_w / aspect_ratio)

        # Ensure preview is centered
        preview_x = (output_width - preview_w) // 2
        preview_y = (output_height - preview_h) // 2

        logging.info(f"Corrected Preview Window -> x={preview_x}, y={preview_y}, width={preview_w}, height={preview_h}, aspect_ratio={preview_w / preview_h:.2f}")

        return preview_x, preview_y, preview_w, preview_h

    def start_cinepi_process(self, cinepi_args=None):
        if cinepi_args is None:
            cinepi_args = self.get_default_args()
        else:
            cinepi_args = list(cinepi_args) + self.default_args

        command = ['cinepi-raw'] + cinepi_args
        logging.info(f'Issuing {command}')
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
        self.redis_controller.set_value('sensor', self.sensor_detect.camera_model)
        
        # while self.redis_controller.get_value('cinepi_running') == 'False':
        #     time.sleep(2)
        #     self.shutdown()
        #     # Restart the process with default arguments
        #     self.start_cinepi_process()
        #     logging.info('CinePi instance restarted.')