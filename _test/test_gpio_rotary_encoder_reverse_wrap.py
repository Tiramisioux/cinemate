"""Reverse and Wrap for the GPIO rotary encoder (RotaryEncoder in gpio_input.py).

Reverse swaps which physical rotation gpiozero's when_rotated_clockwise /
when_rotated_counter_clockwise callbacks are bound to, so on_rotated_clockwise
always still means "run whatever settings.jsonc configured for
rotate_clockwise" -- it is just wired to the opposite physical turn when
reverse is on. Wrap is forwarded to the dispatched controller method only
when that method actually declares a wrap parameter (inspected via
inspect.signature, never a blanket try/except TypeError, so a real error in
the call still surfaces) -- an operator can bind a rotary encoder to any
controller method by name, not only an inc_/dec_ pair.

Uses the same gpiozero stub shape as test_gpio_duplicate_pin_guard.py.
"""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class _FakePin:
    def __init__(self, pin, **kwargs):
        self.pin = pin

    def __getattr__(self, name):
        return lambda *a, **kw: None


class _FakeRotaryEncoder:
    def __init__(self, a, b, **kwargs):
        self._a = _FakePin(a)
        self._b = _FakePin(b)

    def __getattr__(self, name):
        return lambda *a, **kw: None


sys.modules["gpiozero"] = types.SimpleNamespace(
    Button=object,
    RotaryEncoder=_FakeRotaryEncoder,
    CPUTemperature=object,
)

from module.gpio_input import RotaryEncoder  # noqa: E402


class _FakeController:
    """Real bound methods, not Mock: inspect.signature() needs an actual
    parameter named 'wrap' to find, which a generic Mock() does not have."""

    def __init__(self):
        self.calls = []

    def inc_iso(self, wrap=False):
        self.calls.append(("inc_iso", wrap))

    def dec_iso(self, wrap=False):
        self.calls.append(("dec_iso", wrap))

    def custom_no_wrap(self):
        self.calls.append(("custom_no_wrap",))


ACTIONS = {
    "rotate_clockwise": {"method": "inc_iso"},
    "rotate_counterclockwise": {"method": "dec_iso"},
}


class ReverseBindingTests(unittest.TestCase):
    def test_unreversed_binds_each_handler_to_its_own_direction(self):
        enc = RotaryEncoder(_FakeController(), 9, 11, ACTIONS, reverse=False)
        self.assertEqual(enc.encoder.when_rotated_clockwise, enc.on_rotated_clockwise)
        self.assertEqual(enc.encoder.when_rotated_counter_clockwise, enc.on_rotated_counter_clockwise)

    def test_reverse_swaps_the_two_handler_bindings(self):
        enc = RotaryEncoder(_FakeController(), 9, 11, ACTIONS, reverse=True)
        self.assertEqual(enc.encoder.when_rotated_clockwise, enc.on_rotated_counter_clockwise)
        self.assertEqual(enc.encoder.when_rotated_counter_clockwise, enc.on_rotated_clockwise)


class WrapDispatchTests(unittest.TestCase):
    def test_wrap_on_reaches_a_method_that_accepts_it(self):
        controller = _FakeController()
        enc = RotaryEncoder(controller, 9, 11, ACTIONS, wrap=True)
        enc.on_rotated_clockwise()
        self.assertEqual(controller.calls, [("inc_iso", True)])

    def test_wrap_off_is_still_forwarded_explicitly(self):
        controller = _FakeController()
        enc = RotaryEncoder(controller, 9, 11, ACTIONS, wrap=False)
        enc.on_rotated_clockwise()
        self.assertEqual(controller.calls, [("inc_iso", False)])

    def test_wrap_on_a_method_with_no_wrap_parameter_does_not_raise(self):
        controller = _FakeController()
        actions = {
            "rotate_clockwise": {"method": "custom_no_wrap"},
            "rotate_counterclockwise": {"method": "custom_no_wrap"},
        }
        enc = RotaryEncoder(controller, 9, 11, actions, wrap=True)
        enc.on_rotated_clockwise()  # must not TypeError
        self.assertEqual(controller.calls, [("custom_no_wrap",)])

    def test_wrap_on_a_method_with_no_wrap_parameter_logs_it(self):
        controller = _FakeController()
        actions = {
            "rotate_clockwise": {"method": "custom_no_wrap"},
            "rotate_counterclockwise": {"method": "custom_no_wrap"},
        }
        enc = RotaryEncoder(controller, 9, 11, actions, wrap=True)
        with self.assertLogs(enc.logger.name, level="INFO") as cm:
            enc.on_rotated_clockwise()
        self.assertTrue(any("wrap" in line.lower() for line in cm.output))


if __name__ == "__main__":
    unittest.main()
