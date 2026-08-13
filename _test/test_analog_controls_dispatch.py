"""AnalogControls._dispatch resolves its target setter through the
parameter registry instead of a hardcoded literal call per pot.

The shutter_a pot is the interesting case: it reads steps via
_get_steps('shutter_a') but has always written through set_shutter_a_nom,
not set_shutter_a - _dispatch must be told the registry name
'shutter_a_nom', not 'shutter_a', to keep calling the same setter.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for name in ("smbus2", "grove", "grove.i2c"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["grove.i2c"].Bus = object
sys.modules["smbus2"].SMBus = object
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.analog_controls import AnalogControls


def make_analog_controls():
    ac = AnalogControls.__new__(AnalogControls)
    ac.cinepi_controller = mock.Mock()
    return ac


class DispatchTests(unittest.TestCase):
    def test_iso_dispatches_to_set_iso(self):
        ac = make_analog_controls()
        ac._dispatch("iso", 800)
        ac.cinepi_controller.set_iso.assert_called_once_with(800)

    def test_shutter_a_nom_dispatches_to_set_shutter_a_nom(self):
        # The pot's own local name for this is 'shutter_a' (see
        # _get_steps/self.shutter_a_pot), but the registry name for the
        # setter it has always called is 'shutter_a_nom'.
        ac = make_analog_controls()
        ac._dispatch("shutter_a_nom", 172.8)
        ac.cinepi_controller.set_shutter_a_nom.assert_called_once_with(172.8)
        ac.cinepi_controller.set_shutter_a.assert_not_called()

    def test_fps_dispatches_to_set_fps(self):
        ac = make_analog_controls()
        ac._dispatch("fps", 25)
        ac.cinepi_controller.set_fps.assert_called_once_with(25)

    def test_wb_dispatches_to_set_wb(self):
        ac = make_analog_controls()
        ac._dispatch("wb", 5600)
        ac.cinepi_controller.set_wb.assert_called_once_with(5600)

    def test_hdr_knobs_dispatch_to_their_own_setters(self):
        ac = make_analog_controls()
        for name, value in (
            ("hdr_threshold_low", 128),
            ("hdr_threshold_high", 3968),
            ("hdr_blend", 4),
            ("hdr_gain_adder", 2),
        ):
            with self.subTest(name=name):
                ac._dispatch(name, value)
                getattr(ac.cinepi_controller, f"set_{name}").assert_called_once_with(value)

    def test_unknown_name_warns_and_falls_back_to_the_set_prefix(self):
        ac = make_analog_controls()
        with self.assertLogs("module.parameters", level="WARNING") as cm:
            ac._dispatch("made_up_pot", 1)
        self.assertTrue(
            any("made_up_pot" in line and "analog_controls" in line for line in cm.output)
        )
        ac.cinepi_controller.set_made_up_pot.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
