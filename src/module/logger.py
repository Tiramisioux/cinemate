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

# Blacklist of modules to filter out from logging  
      
class ColoredFormatter(logging.Formatter):
    
    MODULE_COLORS = {
        'main': {'color': 'light_grey', 'attrs': []},
        'cinepi_app': {'color': 'light_blue', 'attrs': ['bold']},
        'redis_controller': {'color': 'green', 'attrs': ['bold']},
        'usb_monitor': {'color': 'light_grey', 'attrs': []},
        'audio_recorder': {'color': 'cyan', 'attrs': []},
        'gpio_input': {'color': 'light_yellow', 'attrs': []},
        'cinepi_controller': {'color': 'light_green', 'attrs': []},
        'analog_controls': {'color': 'yellow', 'attrs': []},
        'ssd_monitor': {'color': 'cyan', 'attrs': ['bold']},
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
    
class BlacklistFilter(logging.Filter):
    def __init__(self, blocked_modules):
        super().__init__()
        self.blocked = set(blocked_modules)

    def filter(self, record):
        # return False to drop the record entirely
        return record.module.strip() not in self.blocked


# Configure the logging
def configure_logging(_blacklist, level=logging.INFO):
    
    BLACKLISTED_MODULES = [
    #'[storage-automount]'
    'ssd_monitor',
    #'dmesg_monitor',
    #'usb_monitor',
    #'audio_recorder',
    #'gpio_input',
    #'analog_controls',
    #'gpio_output',
    #'system_button',
    #'rotary_encoder',
    #'simple_gui',
    #'sensor_detect',
    #'cinepi_app',
    #'redis_controller',
    #'cinepi_controller',
    #'main',
]
    
    log_format = '%(asctime)s.%(msecs)03d: %(levelname)s: %(module)s %(message)s'
    date_format = '%S'
    formatter = ColoredFormatter(log_format, datefmt=date_format)

    logger = logging.getLogger()
    logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler('/home/pi/cinemate/src/logs/system.log')
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    logger.addHandler(file_handler)

    # Create a thread-safe queue to hold log messages
    log_queue = queue.Queue()

    # Instantiate and configure QueueHandler
    queue_handler = QueueHandler(log_queue)
    queue_handler.setFormatter(formatter)
    
    blacklist = ['ssd_monitor', 'dmesg_monitor']
    queue_handler.addFilter(BlacklistFilter(BLACKLISTED_MODULES))

    logger.addHandler(queue_handler)

    return logger, log_queue
