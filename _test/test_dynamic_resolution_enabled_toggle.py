import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.cinepi_controller import CinePiController
from module.redis_controller import ParameterKey


class FakeRedis:
    def __init__(self, dynamic_resolution_enabled=None):
        self.values = {}
        if dynamic_resolution_enabled is not None:
            self.values[ParameterKey.DYNAMIC_RESOLUTION_ENABLED.value] = dynamic_resolution_enabled
        self.sets = []

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value
        self.sets.append((key, value))


# Two modes in one family: the small one runs to 87fps, the big one to 40.
MODES = {
    0: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 87},
    1: {"width": 3856, "height": 2180, "bit_depth": 12, "fps_max": 40},
}


class FakeSensorDetect:
    res_modes = MODES

    def get_fps_max(self, _sensor, mode):
        return MODES[int(mode)]["fps_max"]


class DynamicResolutionEnabledToggleTests(unittest.TestCase):
    """F-286. dynamic_resolution_enabled was a hardcoded True with no CLI or
    redis-write toggle -- published for display only, never read back. This
    covers the startup read-back and the new setter, mirroring
    test_cinepi_controller_startup_sensor_mode.py's controller() pattern."""

    def controller(self, redis, sensor_mode=1, desired_mode=None):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = redis
        controller.dynamic_resolution_enabled = True
        controller.dynamic_resolution_active = False
        controller.dynamic_resolution_desired_mode = desired_mode
        # The toggle re-derives the fps ceiling, so the fake needs the same
        # mode table the real controller reads it from.
        controller.sensor_mode = sensor_mode
        controller.current_sensor = "imx585"
        controller.sensor_detect = FakeSensorDetect()
        controller.fps_free = False
        controller.fps_free_increment = 1
        controller.fps_steps = [24, 25, 30, 50, 60]
        controller.fps_steps_dynamic = []
        controller.settings = {
            "arrays": {"fps": {"steps": [24, 25, 30, 50, 60]}},
            "image_capture": {"dynamic_resolution": True},
        }
        return controller

    def test_startup_defaults_to_enabled_when_unset(self):
        controller = self.controller(FakeRedis())
        self.assertTrue(controller._get_startup_dynamic_resolution_enabled())

    def test_startup_reads_back_disabled_from_redis(self):
        controller = self.controller(FakeRedis(dynamic_resolution_enabled=0))
        self.assertFalse(controller._get_startup_dynamic_resolution_enabled())

    def test_startup_falls_back_to_settings_jsonc_when_redis_is_unset(self):
        # A camera that has never been told either way boots from the file.
        # This used to be a hardcoded True, so a rig configured to keep the
        # feature off had to be told so again after every reflash.
        controller = self.controller(FakeRedis())
        controller.settings["image_capture"] = {"dynamic_resolution": False}
        self.assertFalse(controller._get_startup_dynamic_resolution_enabled())

        controller.settings["image_capture"] = {"dynamic_resolution": True}
        self.assertTrue(controller._get_startup_dynamic_resolution_enabled())

    def test_redis_outranks_settings_jsonc(self):
        # `set dynamic resolution 0` is meant to survive the reboot after it.
        controller = self.controller(FakeRedis(dynamic_resolution_enabled=0))
        controller.settings["image_capture"] = {"dynamic_resolution": True}
        self.assertFalse(controller._get_startup_dynamic_resolution_enabled())

    def test_startup_reads_back_enabled_from_redis(self):
        controller = self.controller(FakeRedis(dynamic_resolution_enabled=1))
        self.assertTrue(controller._get_startup_dynamic_resolution_enabled())

    def test_set_explicit_value_and_publishes(self):
        controller = self.controller(FakeRedis(dynamic_resolution_enabled=1))

        controller.set_dynamic_resolution_enabled(0)

        self.assertFalse(controller.dynamic_resolution_enabled)
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.DYNAMIC_RESOLUTION_ENABLED.value),
            0,
        )

    def test_toggle_with_no_value_flips_current_state(self):
        controller = self.controller(FakeRedis(dynamic_resolution_enabled=1))
        controller.dynamic_resolution_enabled = True

        controller.set_dynamic_resolution_enabled()

        self.assertFalse(controller.dynamic_resolution_enabled)

    def test_turning_it_off_drops_the_ceiling_to_this_mode_s_own_cap(self):
        # Mode 1 tops out at 40fps on its own; the 87 comes from mode 0, which
        # only dynamic resolution can reach. Turning the feature off used to
        # leave 87 standing, so the dial went on offering frame rates the
        # sensor could not deliver at the resolution actually selected.
        controller = self.controller(FakeRedis(dynamic_resolution_enabled=1))
        controller.set_dynamic_resolution_enabled(1)
        self.assertEqual(controller.fps_max, 87)

        controller.set_dynamic_resolution_enabled(0)

        self.assertEqual(controller.fps_max, 40)
        self.assertEqual(
            int(controller.redis_controller.get_value(ParameterKey.FPS_MAX.value)), 40)
        self.assertLessEqual(max(controller.fps_steps_dynamic), 40)

    def test_turning_it_back_on_restores_the_family_wide_ceiling(self):
        controller = self.controller(FakeRedis(dynamic_resolution_enabled=0))
        controller.dynamic_resolution_enabled = False

        controller.set_dynamic_resolution_enabled(1)

        self.assertEqual(controller.fps_max, 87)

    def test_turning_it_off_adopts_the_mode_on_screen_as_the_desired_one(self):
        # Substituted down to mode 0 while desiring mode 1. Switching the
        # feature off makes mode 0 the operator's own choice -- so re-enabling
        # later must not jump back to mode 1 behind their back.
        controller = self.controller(FakeRedis(), sensor_mode=0, desired_mode=1)

        controller.set_dynamic_resolution_enabled(0)

        self.assertEqual(controller.dynamic_resolution_desired_mode, 0)
        self.assertFalse(controller.dynamic_resolution_active)

    def test_invalid_value_raises(self):
        controller = self.controller(FakeRedis())
        with self.assertRaises(ValueError):
            controller.set_dynamic_resolution_enabled("nonsense")


if __name__ == "__main__":
    unittest.main()
