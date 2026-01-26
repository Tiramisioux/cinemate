import logging
import threading
import time
from typing import Dict, Any, TypedDict

import board
import busio
import digitalio
import adafruit_seesaw.seesaw
import adafruit_seesaw.rotaryio
import adafruit_seesaw.digitalio
import adafruit_seesaw.neopixel


class QuadRotarySettings(TypedDict, total=False):
    enabled: bool
    encoders: Dict[str, Dict[str, Any]]


class I2CButton:
    """Simple button handler for the rotary encoder push buttons."""

    def __init__(self, cinepi_controller, actions: Dict[str, Any], identifier: str):
        self.cinepi_controller = cinepi_controller
        self.actions = actions or {}
        self.identifier = identifier
        self.logger = logging.getLogger(f"I2CButton[{identifier}]")
        self.lock = threading.Lock()
        self.click_count = 0
        self.is_long_press = False
        self.hold_timer = None
        self.click_timer = None

    # public API ------------------------------------------------------------
    def on_press(self):
        self.logger.debug("pressed")
        with self.lock:
            self._cancel_timers()
            self._trigger_action(self.actions.get("press_action"))
            self.hold_timer = threading.Timer(3, self._trigger_hold_action)
            self.hold_timer.start()

    def on_release(self):
        self.logger.debug("released")
        with self.lock:
            if self.hold_timer:
                self.hold_timer.cancel()
                self.hold_timer = None
            if not self.is_long_press:
                self.click_count += 1
            self.is_long_press = False
            if self.click_timer:
                self.click_timer.cancel()
            self.click_timer = threading.Timer(0.5, self._evaluate_clicks)
            self.click_timer.start()

    # internal helpers -----------------------------------------------------
    def _cancel_timers(self):
        if self.hold_timer:
            self.hold_timer.cancel()
            self.hold_timer = None
        if self.click_timer:
            self.click_timer.cancel()
            self.click_timer = None

    def _trigger_hold_action(self):
        with self.lock:
            self.is_long_press = True
            self.click_count = 0
            self._trigger_action(self.actions.get("hold_action"))

    def _evaluate_clicks(self):
        with self.lock:
            action = None
            if self.click_count == 1:
                action = self.actions.get("single_click_action")
            elif self.click_count == 2:
                action = self.actions.get("double_click_action")
            elif self.click_count >= 3:
                action = self.actions.get("triple_click_action")
            if action:
                self._trigger_action(action)
            self.click_count = 0

    def _trigger_action(self, action):
        if not action or action == "none":
            return
        if isinstance(action, str):
            action = {"method": action, "args": []}
        method = getattr(self.cinepi_controller, action.get("method"), None)
        if method:
            try:
                method(*action.get("args", []))
                self.logger.debug("executed %s", action.get("method"))
            except Exception as exc:
                self.logger.error("error executing %s: %s", action.get("method"), exc)
        else:
            self.logger.error("method %s not found", action.get("method"))


class QuadRotaryController(threading.Thread):
    RECONNECT_INTERVAL = 5  # seconds

    def __init__(self, cinepi_controller, settings: Dict[str, Any]):
        super().__init__(daemon=True)
        self.cinepi_controller = cinepi_controller
        cfg: QuadRotarySettings = settings.get("quad_rotary_controller", {})
        self.enabled = cfg.get("enabled", False)
        self.encoder_cfg = cfg.get("encoders", {})
        self.buttons = {}
        for idx, enc in self.encoder_cfg.items():
            self.buttons[int(idx)] = I2CButton(
                cinepi_controller,
                enc.get("button", {}),
                identifier=f"qr{idx}"
            )

        self.i2c = None
        self.seesaw = None
        self.encoders = []
        self.switches = []
        self.pixels = None
        self.last_positions = [0, 0, 0, 0]
        self.button_states = [False, False, False, False]
        self.connected = False
        self._last_reconnect = 0

        if self.enabled:
            self._initialize_device()

    # ------------------------------------------------------------------
    def _initialize_device(self):
        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            time.sleep(0.1)
            self.seesaw = adafruit_seesaw.seesaw.Seesaw(self.i2c, 0x49)
            self.encoders = [adafruit_seesaw.rotaryio.IncrementalEncoder(self.seesaw, n) for n in range(4)]
            self.switches = [adafruit_seesaw.digitalio.DigitalIO(self.seesaw, pin) for pin in (12, 14, 17, 9)]
            for sw in self.switches:
                sw.switch_to_input(digitalio.Pull.UP)
            self.pixels = adafruit_seesaw.neopixel.NeoPixel(self.seesaw, 18, 4)
            self.pixels.brightness = 0.5
            self.connected = True
            logging.info("Quad rotary controller initialized")
        except Exception as exc:
            self.connected = False
            logging.warning("Failed to initialize quad rotary controller: %s", exc)
            self._last_reconnect = time.time()

    # ------------------------------------------------------------------
    def update(self):
        if not self.enabled:
            return

        if not self.connected:
            now = time.time()
            if now - self._last_reconnect >= self.RECONNECT_INTERVAL:
                self._initialize_device()
            return

        try:
            positions = [enc.position for enc in self.encoders]
            for idx, pos in enumerate(positions):
                cfg = self.encoder_cfg.get(str(idx))
                if cfg is None:
                    continue
                if pos != self.last_positions[idx]:
                    change = pos - self.last_positions[idx]
                    self.last_positions[idx] = pos
                    setting = cfg.get("setting_name")
                    detents_per_pulse = max(1, int(cfg.get("detents_per_pulse", 1)))
                    if setting:
                        self._update_setting(setting, change, detents_per_pulse)
                if not self.switches[idx].value:
                    if not self.button_states[idx]:
                        self.button_states[idx] = True
                        if idx in self.buttons:
                            self.buttons[idx].on_press()
                else:
                    if self.button_states[idx]:
                        self.button_states[idx] = False
                        if idx in self.buttons:
                            self.buttons[idx].on_release()
                if self.pixels:
                    self.pixels[idx] = 0xFFFFFF if not self.switches[idx].value else self.colorwheel(idx * 8)
        except OSError as exc:
            self.connected = False
            self._last_reconnect = time.time()
            logging.error("Quad rotary controller I/O error: %s", exc)

    def _update_setting(self, name: str, change: int, detents_per_pulse: int):
        inc = getattr(self.cinepi_controller, f"inc_{name}", None)
        dec = getattr(self.cinepi_controller, f"dec_{name}", None)
        try:
            steps = abs(change) * detents_per_pulse
            if change > 0 and inc:
                for _ in range(steps):
                    inc()
            elif change < 0 and dec:
                for _ in range(steps):
                    dec()
        except Exception as exc:
            logging.error("Failed to update %s: %s", name, exc)

    # ------------------------------------------------------------------
    def run(self):
        while True:
            self.update()
            time.sleep(0.1)

    @staticmethod
    def colorwheel(pos):
        if pos < 85:
            return (255 - pos * 3, pos * 3, 0)
        if pos < 170:
            pos -= 85
            return (0, 255 - pos * 3, pos * 3)
        pos -= 170
        return (pos * 3, 0, 255 - pos * 3)
