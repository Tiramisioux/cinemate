"""Reverse and Wrap for the quad I2C rotary board (QuadRotaryController).

update() computes change = pos - self.last_positions[idx] per encoder;
reverse negates that before _update_setting dispatches it to inc_<setting>/
dec_<setting>. wrap is forwarded to whichever of those two the change picks,
but -- same reasoning as the GPIO dispatcher in gpio_input.py -- only to a
method that actually declares a wrap parameter, found by inspecting its
signature rather than assuming or catching TypeError.

Uses the same hardware-module stub shape as
test_quad_rotary_controller_setting_names.py. QuadRotaryController skips
_initialize_device() entirely when enabled is False, so these tests build
the controller that way and then set the update()-loop state (encoders,
last_positions, switches, ...) by hand, as if one detent had already been
read off the board -- this is the standard way this module is driven
without real seesaw hardware.
"""

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for name in (
    "board", "busio", "digitalio",
    "adafruit_seesaw", "adafruit_seesaw.seesaw", "adafruit_seesaw.rotaryio",
    "adafruit_seesaw.digitalio", "adafruit_seesaw.neopixel",
):
    sys.modules.setdefault(name, types.ModuleType(name))

sys.modules["adafruit_seesaw.seesaw"].Seesaw = object
sys.modules["adafruit_seesaw.rotaryio"].IncrementalEncoder = object
sys.modules["adafruit_seesaw.digitalio"].DigitalIO = object
sys.modules["adafruit_seesaw.neopixel"].NeoPixel = object
sys.modules["digitalio"].Pull = types.SimpleNamespace(UP=1)

from module.i2c.quad_rotary_controller import QuadRotaryController  # noqa: E402


def settings_with(encoders):
    return {"input_peripherals": {"quad_rotary_controller": {"enabled": False, "encoders": encoders}}}


class _FakeController:
    """Real bound methods, not Mock: inspect.signature() needs an actual
    parameter named 'wrap' to find."""

    def __init__(self):
        self.calls = []

    def inc_iso(self, wrap=False):
        self.calls.append(("inc_iso", wrap))

    def dec_iso(self, wrap=False):
        self.calls.append(("dec_iso", wrap))

    def inc_no_wrap(self):
        self.calls.append(("inc_no_wrap",))


def _one_detent_turn(qrc, cfg):
    """Wires the state update() reads as if encoder 0 had just turned one
    detent positive (position 0 -> 1), with no button involvement."""
    qrc.enabled = True
    qrc.connected = True
    qrc.encoder_cfg = {"0": cfg}
    qrc.encoders = [SimpleNamespace(position=1)]
    qrc.last_positions = [0]
    qrc.switches = [SimpleNamespace(value=True)]  # not pressed
    qrc.button_states = [False]
    qrc.buttons = {}
    qrc.pixels = None


class ReverseTests(unittest.TestCase):
    def test_unreversed_encoder_turning_positive_calls_inc(self):
        controller = _FakeController()
        qrc = QuadRotaryController(controller, settings_with({}))
        _one_detent_turn(qrc, {"setting_name": "iso"})
        qrc.update()
        self.assertEqual(controller.calls, [("inc_iso", False)])

    def test_reversed_encoder_turning_positive_calls_dec(self):
        controller = _FakeController()
        qrc = QuadRotaryController(controller, settings_with({}))
        _one_detent_turn(qrc, {"setting_name": "iso", "reverse": True})
        qrc.update()
        self.assertEqual(controller.calls, [("dec_iso", False)])


class WrapTests(unittest.TestCase):
    def test_wrap_on_is_forwarded_to_a_method_that_accepts_it(self):
        controller = _FakeController()
        qrc = QuadRotaryController(controller, settings_with({}))
        _one_detent_turn(qrc, {"setting_name": "iso", "wrap": True})
        qrc.update()
        self.assertEqual(controller.calls, [("inc_iso", True)])

    def test_wrap_off_is_still_forwarded_explicitly(self):
        controller = _FakeController()
        qrc = QuadRotaryController(controller, settings_with({}))
        _one_detent_turn(qrc, {"setting_name": "iso", "wrap": False})
        qrc.update()
        self.assertEqual(controller.calls, [("inc_iso", False)])

    def test_wrap_on_a_method_with_no_wrap_parameter_does_not_raise(self):
        controller = _FakeController()
        qrc = QuadRotaryController(controller, settings_with({}))
        _one_detent_turn(qrc, {"setting_name": "no_wrap", "wrap": True})
        qrc.update()  # must not raise
        self.assertEqual(controller.calls, [("inc_no_wrap",)])

    def test_wrap_on_a_method_with_no_wrap_parameter_logs_it(self):
        controller = _FakeController()
        qrc = QuadRotaryController(controller, settings_with({}))
        _one_detent_turn(qrc, {"setting_name": "no_wrap", "wrap": True})
        with self.assertLogs(level="INFO") as cm:
            qrc.update()
        self.assertTrue(any("wrap" in line.lower() for line in cm.output))


if __name__ == "__main__":
    unittest.main()
