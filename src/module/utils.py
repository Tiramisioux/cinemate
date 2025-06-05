import psutil
from gpiozero import CPUTemperature

class Utils:
    @staticmethod
    def cpu_load() -> str:
        return str(int(psutil.cpu_percent())) + '%'

    @staticmethod
    def cpu_temp() -> str:
        return ('{}\u00B0C'.format(int(CPUTemperature().temperature)))
    
    @staticmethod
    def memory_usage() -> str:
        return str(int(psutil.virtual_memory().percent)) + '%'
