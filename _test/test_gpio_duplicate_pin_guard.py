"""Two settings.jsonc entries claiming one GPIO used to abort startup.

The shipped settings.jsonc puts a button on GPIO10 (press -> rec) and also
names GPIO10 as the rotary encoder's button_pin. That collision is latent
only because the encoder ships `enabled: false`; the settings editor makes
flipping that a one-click operation. Observed on a real camera (2026-08-28):
enabling the encoder took cinemate down every boot with

  GPIOPinInUse: pin GPIO10 is already in use by
    <gpiozero.Button object on pin GPIO10, pull_up=True, is_active=False>

which names the pin but neither of the two entries that collided, so the
message gives no route back to the setting that caused it.

ComponentInitializer already refused pins reserved for GPIO *output*; it
just never tracked what its own inputs had claimed, so the second claim
reached gpiozero and raised. It now refuses a duplicate the same way it
refuses a reserved output pin -- name both claimants, skip the later one --
because a config typo should not brick the camera.

Multi-pin components (three-way switches, encoder CLK/DT) claim
all-or-nothing: a switch holding only some of its pins would read garbage
states, so the whole component is refused and the pins are left with their
existing owner.
"""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class _FakePin:
    """Mimics gpiozero's one-owner-per-pin rule."""

    claimed: dict = {}

    def __init__(self, pin, **kwargs):
        pin = int(pin)
        if pin in _FakePin.claimed:
            raise RuntimeError(f"pin GPIO{pin} is already in use")
        _FakePin.claimed[pin] = self
        self.pin = pin

    def __getattr__(self, name):
        # when_pressed/when_held/... assignment and reads are all no-ops
        return lambda *a, **kw: None


class _FakeButton(_FakePin):
    def __init__(self, pin, **kwargs):
        super().__init__(pin, **kwargs)
        self.is_pressed = False


class _FakeRotaryEncoder:
    def __init__(self, a, b, **kwargs):
        # gpiozero's RotaryEncoder holds both of its pins
        self._a = _FakePin(a)
        self._b = _FakePin(b)

    def __getattr__(self, name):
        return lambda *a, **kw: None


sys.modules["gpiozero"] = types.SimpleNamespace(
    Button=_FakeButton,
    RotaryEncoder=_FakeRotaryEncoder,
    CPUTemperature=object,
)

from module.gpio_input import ComponentInitializer  # noqa: E402


class _NullController:
    """Every action name resolves to a no-op."""

    def __getattr__(self, name):
        return lambda *a, **kw: None


def _build(settings):
    _FakePin.claimed = {}
    return ComponentInitializer(_NullController(), settings)


class DuplicateInputPinTests(unittest.TestCase):

    def test_encoder_button_colliding_with_a_button_does_not_abort_startup(self):
        """The exact shipped shape: button on 10, encoder button_pin 10."""
        settings = {
            "hardware_controls": {
                "buttons": [
                    {"pin": 10, "pull_up": True, "debounce_time": 0.1,
                     "press_action": {"method": "rec"}},
                ],
                "rotary_encoders": [
                    {"enabled": True, "clk_pin": 9, "dt_pin": 11,
                     "button_pin": 10,
                     "encoder_actions": {
                         "rotate_clockwise": {"method": "inc_iso"},
                         "rotate_counterclockwise": {"method": "dec_iso"}}},
                ],
            }
        }
        component = _build(settings)  # must not raise

        # The button keeps the pin; the encoder's rotation still binds.
        self.assertEqual(component.claimed_input_pins[10], "button on pin 10")
        self.assertIn(9, component.claimed_input_pins)
        self.assertIn(11, component.claimed_input_pins)
        # Only one device ended up on GPIO10.
        self.assertEqual(len([p for p in _FakePin.claimed if p == 10]), 1)

    def test_first_claimant_wins_and_later_duplicate_is_skipped(self):
        settings = {
            "hardware_controls": {
                "buttons": [
                    {"pin": 7, "pull_up": True, "debounce_time": 0.1,
                     "press_action": {"method": "rec"}},
                    {"pin": 7, "pull_up": True, "debounce_time": 0.1,
                     "press_action": {"method": "reboot"}},
                ],
            }
        }
        component = _build(settings)
        self.assertEqual(component.claimed_input_pins[7], "button on pin 7")
        self.assertEqual(len(component.smart_buttons_list), 1)

    def test_two_way_switch_cannot_steal_a_button_pin(self):
        settings = {
            "hardware_controls": {
                "buttons": [
                    {"pin": 24, "pull_up": True, "debounce_time": 0.1,
                     "press_action": {"method": "rec"}},
                ],
                "two_way_switches": [
                    {"pin": 24, "state_on_action": {"method": "set_zoom"},
                     "state_off_action": {"method": "set_zoom"}},
                ],
            }
        }
        component = _build(settings)
        self.assertEqual(component.claimed_input_pins[24], "button on pin 24")

    def test_three_way_switch_is_all_or_nothing(self):
        """A partially-bound switch would read garbage, so refuse it whole."""
        settings = {
            "hardware_controls": {
                "buttons": [
                    {"pin": 5, "pull_up": True, "debounce_time": 0.1,
                     "press_action": {"method": "rec"}},
                ],
                "three_way_switches": [
                    {"pins": [4, 5], "state_0_action": {"method": "rec"}},
                ],
            }
        }
        component = _build(settings)
        # 5 stays with the button, and 4 is NOT half-claimed by the switch.
        self.assertEqual(component.claimed_input_pins[5], "button on pin 5")
        self.assertNotIn(4, component.claimed_input_pins)
        self.assertNotIn(4, _FakePin.claimed)

    def test_encoder_rotation_pin_collision_skips_the_whole_encoder(self):
        settings = {
            "hardware_controls": {
                "buttons": [
                    {"pin": 9, "pull_up": True, "debounce_time": 0.1,
                     "press_action": {"method": "rec"}},
                ],
                "rotary_encoders": [
                    {"enabled": True, "clk_pin": 9, "dt_pin": 11,
                     "button_pin": 10,
                     "encoder_actions": {
                         "rotate_clockwise": {"method": "inc_iso"},
                         "rotate_counterclockwise": {"method": "dec_iso"}}},
                ],
            }
        }
        component = _build(settings)
        self.assertEqual(component.claimed_input_pins[9], "button on pin 9")
        # DT and the encoder's button must not be claimed by a dead encoder.
        self.assertNotIn(11, component.claimed_input_pins)
        self.assertNotIn(10, component.claimed_input_pins)

    def test_distinct_pins_all_bind_normally(self):
        """The guard must not refuse a well-formed config."""
        settings = {
            "hardware_controls": {
                "buttons": [
                    {"pin": 7, "pull_up": True, "debounce_time": 0.1,
                     "press_action": {"method": "rec"}},
                ],
                "two_way_switches": [
                    {"pin": 24, "state_on_action": {"method": "set_zoom"},
                     "state_off_action": {"method": "set_zoom"}},
                ],
                "rotary_encoders": [
                    {"enabled": True, "clk_pin": 9, "dt_pin": 11,
                     "button_pin": 8,
                     "encoder_actions": {
                         "rotate_clockwise": {"method": "inc_iso"},
                         "rotate_counterclockwise": {"method": "dec_iso"}}},
                ],
            }
        }
        component = _build(settings)
        for pin in (7, 8, 9, 11, 24):
            with self.subTest(pin=pin):
                self.assertIn(pin, component.claimed_input_pins)

    def test_disabled_encoder_claims_nothing(self):
        """`enabled: false` must not reserve pins for a device never built."""
        settings = {
            "hardware_controls": {
                "rotary_encoders": [
                    {"enabled": False, "clk_pin": 9, "dt_pin": 11,
                     "button_pin": 10,
                     "encoder_actions": {
                         "rotate_clockwise": {"method": "inc_iso"},
                         "rotate_counterclockwise": {"method": "dec_iso"}}},
                ],
            }
        }
        component = _build(settings)
        self.assertEqual(component.claimed_input_pins, {})


if __name__ == "__main__":
    unittest.main()
