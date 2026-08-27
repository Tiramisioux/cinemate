"""Coverage for parameters.free_stepping_steps() and the CinePiController
_rebuild_*_steps methods that use it to expand a parameter's step table to
a configurable-granularity continuous range once its free stepping is on.
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))
for name in ("smbus2", "grove", "grove.i2c"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["grove.i2c"].Bus = object
sys.modules["smbus2"].SMBus = object

from module import parameters
from module.cinepi_controller import CinePiController
from module.analog_controls import AnalogControls


class FreeModeStepsTests(unittest.TestCase):
    def test_evenly_divisible_range(self):
        self.assertEqual(
            parameters.free_stepping_steps(100, 3200, 100),
            list(range(100, 3201, 100)),
        )

    def test_always_includes_the_exact_max_even_when_increment_does_not_divide_evenly(self):
        self.assertEqual(parameters.free_stepping_steps(0, 10, 3), [0, 3, 6, 9, 10])

    def test_fractional_increment(self):
        self.assertEqual(parameters.free_stepping_steps(1, 2, 0.5), [1, 1.5, 2])

    def test_whole_number_results_are_returned_as_int_not_float(self):
        steps = parameters.free_stepping_steps(0, 5, 1)
        self.assertTrue(all(isinstance(v, int) for v in steps))

    def test_zero_or_negative_increment_falls_back_to_one(self):
        self.assertEqual(parameters.free_stepping_steps(0, 3, 0), [0, 1, 2, 3])
        self.assertEqual(parameters.free_stepping_steps(0, 3, -5), [0, 1, 2, 3])

    def test_non_numeric_increment_falls_back_to_one(self):
        self.assertEqual(parameters.free_stepping_steps(0, 3, "not a number"), [0, 1, 2, 3])


def make_stub():
    """A bare object carrying only what the _rebuild_*_steps methods read,
    exercised via the unbound CinePiController methods - avoids constructing
    a real controller (redis, GPIO, sensor detection, ...) just to test step
    table math."""
    stub = types.SimpleNamespace()
    stub.settings = {
        "arrays": {
            "iso": {"steps": [100, 200, 400]},
            "shutter_a": {"steps": [45.0, 90.0, 180.0]},
            "fps": {"steps": [1, 12, 24]},
            "wb": {"steps": [3200, 4400, 5600]},
            "hdr_threshold_low": {"steps": [0, 2048, 4095]},
            "hdr_threshold_high": {"steps": [0, 2048, 4095]},
            "hdr_blend": {"steps": [0, 4, 8]},
            "hdr_gain_adder": {"steps": [0, 2, 5]},
        }
    }
    stub.light_hz = []
    stub.current_fps = 25
    stub.fps_max = 50
    stub.calculate_dynamic_shutter_angles = lambda fps: list(stub.shutter_a_steps)
    stub._fps_steps_capped_at_max = CinePiController._fps_steps_capped_at_max.__get__(stub)
    stub.initialize_shutter_angle_steps = CinePiController.initialize_shutter_angle_steps.__get__(stub)
    stub.calculate_flicker_free_steps = CinePiController.calculate_flicker_free_steps.__get__(stub)
    stub.redis_controller = types.SimpleNamespace(set_value=lambda key, value: None)
    stub.shutter_angle_nom = 180.0
    stub.shutter_a_sync_mode = 0
    stub.shutter_a_sync_increment = 0.1
    for name, default_increment in (
        ("iso", 100), ("shutter_a", 1), ("fps", 1), ("wb", 100),
        ("hdr_threshold_low", 16), ("hdr_threshold_high", 16),
        ("hdr_blend", 1), ("hdr_gain_adder", 1),
    ):
        setattr(stub, f"{name}_free", False)
        setattr(stub, f"{name}_free_increment", default_increment)
    return stub


class RebuildStepsHonourFreeIncrementTests(unittest.TestCase):
    def test_steps_mode_uses_the_configured_table_verbatim(self):
        stub = make_stub()
        CinePiController._rebuild_iso_steps(stub)
        self.assertEqual(stub.iso_steps, [100, 200, 400])

    def test_free_stepping_uses_the_configured_increment(self):
        stub = make_stub()
        stub.iso_free = True
        stub.iso_free_increment = 50
        CinePiController._rebuild_iso_steps(stub)
        self.assertEqual(stub.iso_steps, list(range(100, 3201, 50)))

    def test_shutter_a_free_stepping_uses_the_configured_increment(self):
        stub = make_stub()
        stub.shutter_a_free = True
        CinePiController._rebuild_shutter_steps(stub)
        self.assertEqual(stub.shutter_a_steps, list(range(1, 361)))

    def test_fps_free_stepping_is_bounded_by_fps_max(self):
        stub = make_stub()
        stub.fps_free = True
        CinePiController._rebuild_fps_steps(stub)
        self.assertEqual(stub.fps_steps[-1], stub.fps_max)
        self.assertEqual(stub.fps_steps, list(range(1, stub.fps_max + 1)))

    def test_wb_free_stepping_uses_the_configured_increment(self):
        stub = make_stub()
        stub.wb_free = True
        CinePiController._rebuild_wb_steps(stub)
        self.assertEqual(stub.wb_steps, list(range(2800, 6501, 100)))

    def test_hdr_knobs_default_to_their_configured_steps_table(self):
        stub = make_stub()
        CinePiController._rebuild_hdr_threshold_low_steps(stub)
        CinePiController._rebuild_hdr_threshold_high_steps(stub)
        CinePiController._rebuild_hdr_blend_steps(stub)
        CinePiController._rebuild_hdr_gain_adder_steps(stub)
        self.assertEqual(stub.hdr_threshold_low_steps, [0, 2048, 4095])
        self.assertEqual(stub.hdr_threshold_high_steps, [0, 2048, 4095])
        self.assertEqual(stub.hdr_blend_steps, [0, 4, 8])
        self.assertEqual(stub.hdr_gain_adder_steps, [0, 2, 5])

    def test_hdr_knobs_free_stepping_expand_to_the_full_hardware_range(self):
        # free_stepping_steps always includes the exact max, so this reaches the
        # true hardware ceiling (4095) rather than stopping at 4080 the way
        # a plain range(0, 4096, 16) would.
        stub = make_stub()
        stub.hdr_threshold_low_free = True
        stub.hdr_blend_free = True
        stub.hdr_gain_adder_free = True
        CinePiController._rebuild_hdr_threshold_low_steps(stub)
        CinePiController._rebuild_hdr_blend_steps(stub)
        CinePiController._rebuild_hdr_gain_adder_steps(stub)
        self.assertEqual(stub.hdr_threshold_low_steps, list(range(0, 4081, 16)) + [4095])
        self.assertEqual(stub.hdr_blend_steps, list(range(0, 9)))
        self.assertEqual(stub.hdr_gain_adder_steps, list(range(0, 6)))


class ShutterASyncGranularityTests(unittest.TestCase):
    """sync mode (`set shutter a sync`) and free stepping used to share one
    hardcoded 0.1 degree literal, so toggling either looked identical. They
    now read separate settings -- these lock in that sync mode keeps its own
    granularity regardless of what free_increment is set to."""

    def test_sync_mode_on_uses_sync_increment_not_free_increment(self):
        stub = make_stub()
        stub.shutter_a_free_increment = 1     # deliberately different...
        stub.shutter_a_sync_increment = 0.1   # ...from this, to tell them apart
        CinePiController.set_shutter_a_sync_mode(stub, 1)
        self.assertEqual(stub.shutter_angle_steps, parameters.free_stepping_steps(1, 360, 0.1))
        self.assertNotEqual(stub.shutter_angle_steps, parameters.free_stepping_steps(1, 360, 1))

    def test_sync_mode_off_falls_back_to_the_static_table(self):
        stub = make_stub()
        stub.shutter_a_sync_mode = 1
        CinePiController.set_shutter_a_sync_mode(stub, 0)
        self.assertEqual(stub.shutter_a_sync_mode, 0)
        self.assertEqual(stub.shutter_angle_steps, [45.0, 90.0, 180.0])  # stub's configured steps


def make_analog_controls_for_shutter_a(**controller_overrides):
    defaults = dict(
        shutter_a_free=False,
        shutter_a_sync_mode=0,
        shutter_a_free_increment=1,
        shutter_a_sync_increment=0.1,
        shutter_a_steps_dynamic=["static-table-sentinel"],
    )
    defaults.update(controller_overrides)
    ac = AnalogControls.__new__(AnalogControls)
    ac.cinepi_controller = types.SimpleNamespace(**defaults)
    return ac


class AnalogControlsShutterAPrecedenceTests(unittest.TestCase):
    def test_sync_mode_wins_over_free_stepping_when_both_are_on(self):
        ac = make_analog_controls_for_shutter_a(
            shutter_a_free=True, shutter_a_sync_mode=1,
            shutter_a_free_increment=1, shutter_a_sync_increment=0.1,
        )
        self.assertEqual(ac._get_steps('shutter_a'), parameters.free_stepping_steps(1, 360, 0.1))

    def test_free_stepping_alone_uses_free_increment(self):
        ac = make_analog_controls_for_shutter_a(shutter_a_free=True, shutter_a_free_increment=1)
        self.assertEqual(ac._get_steps('shutter_a'), parameters.free_stepping_steps(1, 360, 1))

    def test_neither_free_nor_sync_returns_the_static_table(self):
        ac = make_analog_controls_for_shutter_a()
        self.assertEqual(ac._get_steps('shutter_a'), ["static-table-sentinel"])


if __name__ == "__main__":
    unittest.main()
