import logging
from termcolor import colored
import queue

class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
        
    def emit(self, record):
        log_entry = self.format(record)
        self.log_queue.put(log_entry)

class ColoredFormatter(logging.Formatter):
    
    MODULE_COLORS = {
        'main': {'color': 'light_grey', 'attrs': []},
        'cinepi_app': {'color': 'light_blue', 'attrs': ['bold']},
        'redis_controller': {'color': 'green', 'attrs': ['bold']},
        'usb_monitor': {'color': 'light_grey', 'attrs': []},
        'audio_recorder': {'color': 'cyan', 'attrs': []},
        'gpio_input': {'color': 'light_cyan', 'attrs': []},
        'cinepi_controller': {'color': 'light_green', 'attrs': []},
        'analog_controls': {'color': 'yellow', 'attrs': []},
        'PWMcontroller': {'color': 'light_yellow', 'attrs': []},
        'ssd_monitor': {'color': 'blue', 'attrs': ['bold']},
        'gpio_output': {'color': 'light_red', 'attrs': []},
        'system_button': {'color': 'white', 'attrs': []},
        'rotary_encoder': {'color': 'yellow', 'attrs': []},
        'oled': {'color': 'light_blue', 'attrs': []},
        'simple_gui': {'color': 'light_blue', 'attrs': ['bold']},
        'sensor_detect': {'color': 'light_blue', 'attrs': ['bold']},
        'dmesg_monitor': {'color': 'yellow', 'attrs': []},
    }

    LEVEL_COLORS = {
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red',
    }
    MAX_MODULE_LENGTH = 18  # Adjust as needed based on your longest module name

    def format(self, record):
        record.module = record.module.ljust(self.MAX_MODULE_LENGTH)
        log_message = super().format(record)
        module_info = self.MODULE_COLORS.get(record.module.strip(), {'color': 'white', 'attrs': []})
        module_color = module_info['color']
        module_attrs = module_info['attrs']
        
        colored_message = colored(log_message, module_color)
        colored_message = colored(colored_message, attrs=module_attrs)  # Apply module-specific attributes
        
        return colored_message

class ModuleFilter(logging.Filter):
    def __init__(self, allowed_modules):
        super().__init__()
        self.allowed_modules = allowed_modules

    def filter(self, record):
        module_name = record.module.strip()  # strip whitespaces
        is_allowed = module_name in self.allowed_modules
        if not is_allowed:
            pass #print(f"Filtered out '{module_name}', because it's not in {self.allowed_modules}")
        return is_allowed

# Configure the logging
def configure_logging(allowed_modules):
    log_format = '%(asctime)s.%(msecs)03d: %(levelname)s: %(module)s %(message)s'
    date_format = '%S'
    formatter = ColoredFormatter(log_format, datefmt=date_format)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Create a thread-safe queue to hold log messages
    log_queue = queue.Queue()

    # Instantiate and configure QueueHandler
    queue_handler = QueueHandler(log_queue)
    queue_handler.setFormatter(formatter)

    module_filter = ModuleFilter(allowed_modules)
    queue_handler.addFilter(module_filter)  # add filter to the handler

    logger.addHandler(queue_handler)

    return logger, log_queue
