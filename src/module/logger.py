import logging
from termcolor import colored
import queue
import os

class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
        
    def emit(self, record):
        log_entry = self.format(record)
        self.log_queue.put(log_entry)
      
class ColoredFormatter(logging.Formatter):
    """
    Formatter that colors and bolds the entire log record (level, module, message),
    while leaving the timestamp in default color.
    """
    MODULE_COLORS = {
        'main': {'color': 'light_grey', 'attrs': ['bold']},
        'cinepi_multi': {'color': 'blue', 'attrs': ['bold']},
        'redis_controller': {'color': 'green', 'attrs': ['bold']},
        'usb_monitor': {'color': 'light_grey', 'attrs': ['bold']},
        'audio_recorder': {'color': 'cyan', 'attrs': ['bold']},
        'gpio_input': {'color': 'light_yellow', 'attrs': ['bold']},
        'cinepi_controller': {'color': 'light_green', 'attrs': ['bold']},
        'analog_controls': {'color': 'yellow', 'attrs': ['bold']},
        'ssd_monitor': {'color': 'cyan', 'attrs': ['bold']},
        'gpio_output': {'color': 'light_red', 'attrs': ['bold']},
        'system_button': {'color': 'white', 'attrs': ['bold']},
        'rotary_encoder': {'color': 'yellow', 'attrs': ['bold']},
        'oled': {'color': 'light_blue', 'attrs': ['bold']},
        'simple_gui': {'color': 'light_blue', 'attrs': ['bold']},
        'sensor_detect': {'color': 'light_blue', 'attrs': ['bold']},
        'dmesg_monitor': {'color': 'yellow', 'attrs': ['bold']},
    }

    LEVEL_COLORS = {
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red',
    }
    MAX_MODULE_LENGTH = 18  # Adjust to align columns

    def format(self, record):
        # Build timestamp with milliseconds
        asctime = self.formatTime(record, self.datefmt)
        timestamp = f"{asctime}.{int(record.msecs):03d}"

        # Determine level and module
        level = record.levelname
        module_name = record.module.strip()
        padded_module = module_name.ljust(self.MAX_MODULE_LENGTH)

        # Full message
        message = record.getMessage()

        # Choose base color from module, fallback to level color
        module_info = self.MODULE_COLORS.get(module_name)
        if module_info:
            color = module_info['color']
            attrs = module_info['attrs']
        else:
            color = self.LEVEL_COLORS.get(level, 'dark_grey')
            attrs = ['bold']

        # Format and color the part after the timestamp
        record_text = f"{level}: {padded_module} {message}"
        colored_record = colored(record_text, color, attrs=attrs)

        return f"{timestamp}: {colored_record}"

# Configure the logging

def configure_logging(MODULES_OUTPUT_TO_SERIAL, level=logging.INFO):
    # Base format (timestamp handled by formatter)
    log_format = '%(asctime)s.%(msecs)03d: %(levelname)s: %(module)s %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    formatter = ColoredFormatter(log_format, datefmt=date_format)

    logger = logging.getLogger()
    logger.setLevel(level)

    # Clean existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler with colored output for level/module/message
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (plain text)
    log_dir = '/home/pi/cinemate/src/logs'
    os.makedirs(log_dir, exist_ok=True)
    file_path = os.path.join(log_dir, 'system.log')
    file_handler = logging.FileHandler(file_path)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    logger.addHandler(file_handler)

    # Queue handler for in-app UI or processing
    log_queue = queue.Queue()
    queue_handler = QueueHandler(log_queue)
    queue_handler.setFormatter(formatter)
    logger.addHandler(queue_handler)

    return logger, log_queue
