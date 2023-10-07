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
        'main2': 'light_grey',
        'cinepi_app': 'light_blue',
        'redis_controller': 'green',
        'usb_monitor': 'light_grey',
        'audio_recorder': 'cyan',
        'gpio_controls': 'light_cyan',
        'cinepi_controller': 'light_green',
        'analog_controls': 'red',
        'ssd_monitor': 'dark_grey',
        'gpio_output': 'magenta'
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
        colored_message = colored(log_message, self.MODULE_COLORS.get(record.module.strip(), 'white'))

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
