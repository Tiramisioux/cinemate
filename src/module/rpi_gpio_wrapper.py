import lgpio

class GPIO:
    OUT = 'out'
    IN = 'in'
    LOW = 0
    HIGH = 1
    BCM = 'bcm'
    BOARD = 'board'
    
    _chip_handle = None
    _warned = False

    @staticmethod
    def setmode(mode):
        # lgpio doesn't need this, but we keep it for compatibility
        pass

    @staticmethod
    def setwarnings(flag):
        GPIO._warned = not flag

    @staticmethod
    def _get_handle():
        if GPIO._chip_handle is None:
            GPIO._chip_handle = lgpio.gpiochip_open(0)
        return GPIO._chip_handle

    @staticmethod
    def setup(channel, direction, initial=None, pull_up_down=None):
        h = GPIO._get_handle()
        if direction == GPIO.OUT:
            lgpio.gpio_claim_output(h, channel)
            if initial is not None:
                lgpio.gpio_write(h, channel, initial)
        elif direction == GPIO.IN:
            flags = 0
            if pull_up_down == GPIO.PUD_UP:
                flags = lgpio.SET_PULL_UP
            elif pull_up_down == GPIO.PUD_DOWN:
                flags = lgpio.SET_PULL_DOWN
            lgpio.gpio_claim_input(h, channel, flags)

    @staticmethod
    def output(channel, state):
        h = GPIO._get_handle()
        lgpio.gpio_write(h, channel, state)

    @staticmethod
    def input(channel):
        h = GPIO._get_handle()
        return lgpio.gpio_read(h, channel)

    @staticmethod
    def cleanup(channel=None):
        if GPIO._chip_handle is not None:
            if channel is None:
                lgpio.gpiochip_close(GPIO._chip_handle)
                GPIO._chip_handle = None
            else:
                lgpio.gpio_free(GPIO._chip_handle, channel)

    # Add other methods as needed...

# Create a module-like object
class RPi:
    GPIO = GPIO

# Assign the RPi object to a variable named RPi
RPi = RPi()