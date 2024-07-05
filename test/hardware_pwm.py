import os
import time
from signal import pause

class pi5RC:

    def __init__(self, Pin, frequency=50):
        pins = [12, 13, 14, 15, 18, 19]
        afunc = ['a0', 'a0', 'a0', 'a0', 'a3', 'a3']
        self.pwmx = [0, 1, 2, 3, 2, 3]
        self.enableFlag = False
        self.onTime_us = 0
        self.frequency = frequency
        if Pin in pins:
            self.pin = Pin
            self.pinIdx = pins.index(Pin)
            # let's set pin ctrl
            os.system("/usr/bin/pinctrl set {} {}".format(self.pin, afunc[self.pinIdx]))
            # let export pin
            if not os.path.exists("/sys/class/pwm/pwmchip2/pwm{}".format(self.pwmx[self.pinIdx])):
                os.system("echo {} > /sys/class/pwm/pwmchip2/export".format(self.pwmx[self.pinIdx]))
            # Set period based on the frequency
            time.sleep(0.2)
            self.set_frequency(self.frequency)
            self.enable(False)
            self.file_duty = open("/sys/class/pwm/pwmchip2/pwm{}/duty_cycle".format(self.pwmx[self.pinIdx]), "w")
            if self.file_duty.closed:
                raise IOError("Unable to create pwm{} file".format(self.pwmx[self.pinIdx]))
        else:
            self.pin = None
            raise IOError("Error Invalid PWM Pin {}".format(Pin))

    def enable(self, flag):
        self.enableFlag = flag
        os.system("echo {} > /sys/class/pwm/pwmchip2/pwm{}/enable".format(int(self.enableFlag), self.pwmx[self.pinIdx]))

    def set_frequency(self, frequency):
        self.frequency = frequency
        period = int(1e9 / self.frequency)  # Period in nanoseconds
        os.system("echo {} > /sys/class/pwm/pwmchip2/pwm{}/period".format(period, self.pwmx[self.pinIdx]))

    def __del__(self):
        if self.pin is not None:
            # ok take PWM out
            os.system("echo {} > /sys/class/pwm/pwmchip2/unexport".format(self.pwmx[self.pinIdx]))
            # disable PWM Pin
            os.system("/usr/bin/pinctrl set {} no".format(self.pin))
            if not self.file_duty.closed:
                self.file_duty.close()

    def set(self, onTime_us):
        if self.pin is not None:
            if not self.enableFlag:
                self.enable(True)
            self.onTime_us = onTime_us
            self.file_duty.write("{}".format(onTime_us))
            self.file_duty.flush()

# Example usage:
pwm = pi5RC(19)
pwm.set_frequency(24)  # Set frequency to 24 Hz
pwm.set(500000)        # Set duty cycle to 50%
pwm.enable(True)       # Enable PWM

pause()

