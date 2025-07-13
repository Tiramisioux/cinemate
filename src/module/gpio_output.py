import logging
import threading
import time
import math
from module.rpi_gpio_wrapper import RPi
from module.redis_controller import ParameterKey

# simple RGB colour lookup (1=on, 0=off)
COLOR_DICT = {
    "red":    (1, 0, 0),
    "green":  (0, 1, 0),
    "blue":   (0, 0, 1),
    "yellow": (1, 1, 0),
    "cyan":   (0, 1, 1),
    "magenta":(1, 0, 1),
    "white":  (1, 1, 1),
    "off":    (0, 0, 0),
}

class _LED(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.mode = "off"
        self.color = (1, 1, 1)
        self._event = threading.Event()
        self.running = True

    def set_mode(self, mode, color=None):
        self.mode = mode
        if color is not None:
            self.color = color
        self._event.set()

    def stop(self):
        self.running = False
        self._event.set()

    # subclasses must implement _write(r,g,b) with 0/1 or duty 0..100

    def run(self):
        phase = 0.0
        while self.running:
            m = self.mode
            if m == "steady":
                self._write(*self.color)
                self._event.wait(0.1)
            elif m == "blink":
                state = int((time.time()*5) % 2 < 1)
                self._write(*(c*state for c in self.color))
                self._event.wait(0.1)
            elif m == "blink_long":
                state = int((time.time()) % 1 < 0.5)
                self._write(*(c*state for c in self.color))
                self._event.wait(0.1)
            elif m == "pulse":
                phase = (phase + 0.05) % 1.0
                duty = (1-math.cos(2*math.pi*phase))/2
                self._write_pwm(duty)
                self._event.wait(0.05)
            else:
                self._write(0,0,0)
                self._event.wait(0.1)
            self._event.clear()

    # default PWM writer falls back to on/off
    def _write_pwm(self, duty):
        state = 1 if duty > 0.5 else 0
        self._write(*(c*state for c in self.color))

class SystemLED(_LED):
    def __init__(self, pin):
        super().__init__()
        self.pin = pin
        RPi.GPIO.setup(pin, RPi.GPIO.OUT)

    def _write(self, r, g, b=None):
        RPi.GPIO.output(self.pin, RPi.GPIO.HIGH if r else RPi.GPIO.LOW)

class SystemLED_RGB(_LED):
    def __init__(self, pins):
        super().__init__()
        self.pins = pins
        for p in pins:
            RPi.GPIO.setup(p, RPi.GPIO.OUT)

    def _write(self, r, g, b):
        for val, pin in zip((r,g,b), self.pins):
            RPi.GPIO.output(pin, RPi.GPIO.HIGH if val else RPi.GPIO.LOW)

class GPIOOutput:
    """Handle recording indicator GPIO pins and LED threads."""

    def __init__(self, rec_out_pins=None):
        # list of pins driving LEDs indicating recording/writing status
        self.rec_out_pins = rec_out_pins if rec_out_pins is not None else []

        # container for optional LED threads started by other modules
        self._led_threads = []
        self._stop_event = threading.Event()

        # Set up each pin in rec_out_pins as an output if the list is provided
        for pin in self.rec_out_pins:
            RPi.GPIO.setup(pin, RPi.GPIO.OUT)
            logging.info(f"REC light instantiated on pin {pin}")

    def set_recording(self, status):
        """Set the status of the recording pins."""
        for pin in self.rec_out_pins:
            RPi.GPIO.output(pin, RPi.GPIO.HIGH if status else RPi.GPIO.LOW)
            logging.info(f"GPIO {pin} set to {'HIGH' if status else 'LOW'}")

    def cleanup(self):
        """Stop LED threads and release GPIO pins."""
        self._stop_event.set()
        for thread in list(self._led_threads):
            if thread.is_alive():
                thread.join()
        self._led_threads.clear()

        try:
            RPi.GPIO.cleanup()
            logging.info("GPIO pins cleaned up")
        except Exception as exc:
            logging.warning(f"GPIO cleanup failed: {exc}")

class RedisGPIOOutput:
    def __init__(self, redis_controller, sys_led_configs=None, sys_led_rgb_configs=None):
        self.redis = redis_controller
        self.leds = []  # list of (led, rules)

        for cfg in sys_led_configs or []:
            led = SystemLED(cfg.get("pin"))
            self.leds.append((led, cfg.get("rules", [])))
            led.start()

        for cfg in sys_led_rgb_configs or []:
            led = SystemLED_RGB(cfg.get("pins", []))
            self.leds.append((led, cfg.get("rules", [])))
            led.start()

        if self.leds:
            self.redis.redis_parameter_changed.subscribe(self._redis_update)
            # initial state
            for led, rules in self.leds:
                self._update_led(led, rules)

    def _redis_update(self, data):
        key = data["key"]
        for led, rules in self.leds:
            if any(rule.get("key") == key for rule in rules):
                self._update_led(led, rules)

    def _get_value(self, key):
        return self.redis.get_value(key)

    def _match(self, val, rule_val):
        if rule_val is None:
            return str(val) not in ("0", "False", "false", "None", "")
        return str(val) == str(int(rule_val)) or str(val).lower() == str(rule_val).lower()

    def _update_led(self, led, rules):
        for rule in rules:
            val = self._get_value(rule.get("key"))
            if self._match(val, rule.get("value")):
                color = COLOR_DICT.get(rule.get("color", "white"), (1,1,1))
                led.set_mode(rule.get("mode", "off"), color)
                return
        led.set_mode("off")

    def set_recording(self, status):
        # compatibility shim – set first LED if defined
        for led, rules in self.leds:
            for r in rules:
                if r.get("key") == ParameterKey.REC.value:
                    val = 1 if status else 0
                    if self._match(val, r.get("value")):
                        color = COLOR_DICT.get(r.get("color", "white"), (1,1,1))
                        led.set_mode(r.get("mode", "off"), color)
                    else:
                        led.set_mode("off")

    def cleanup(self):
        for led, _ in self.leds:
            led.stop()