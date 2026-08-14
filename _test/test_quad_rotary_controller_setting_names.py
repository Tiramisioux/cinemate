"""Startup validation of quad_rotary_controller's setting_name config.

Before this refactor, an encoder configured with a typo'd setting_name
(e.g. "iso_" instead of "iso") failed completely silently: _update_setting
did getattr(controller, f"inc_{name}", None) and just no-op'd if the
wrapper didn't exist. Construction now looks every configured setting_name
up in the parameter registry, so a typo is visible as a WARNING at
startup instead.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock


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

from module.i2c.quad_rotary_controller import QuadRotaryController


def settings_with(encoders):
    return {"controls": {"quad_rotary_controller": {"enabled": False, "encoders": encoders}}}


class QuadRotarySettingNameValidationTests(unittest.TestCase):
    def test_known_setting_names_do_not_warn(self):
        settings = settings_with({
            "3": {"setting_name": "iso"},
            "2": {"setting_name": "shutter_a"},
            "1": {"setting_name": "fps"},
            "0": {"setting_name": "wb"},
        })
        with self.assertNoLogs("module.parameters", level="WARNING"):
            QuadRotaryController(mock.Mock(), settings)

    def test_typo_d_setting_name_warns_at_construction(self):
        settings = settings_with({"3": {"setting_name": "isoo"}})
        with self.assertLogs("module.parameters", level="WARNING") as cm:
            QuadRotaryController(mock.Mock(), settings)
        self.assertTrue(
            any("isoo" in line and "quad_rotary_controller" in line for line in cm.output)
        )

    def test_encoder_without_a_setting_name_does_not_warn(self):
        # The wb encoder's button-only config in the stock settings.jsonc has
        # no setting_name at all (its button drives set_resolution etc, not
        # a cycle-able parameter) - that's a valid shape, not a typo.
        settings = settings_with({"0": {"button": {"press_action": {"method": "set_resolution"}}}})
        with self.assertNoLogs("module.parameters", level="WARNING"):
            QuadRotaryController(mock.Mock(), settings)


if __name__ == "__main__":
    unittest.main()
