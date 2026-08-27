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


class DynamicResolutionEnabledToggleTests(unittest.TestCase):
    """F-286. dynamic_resolution_enabled was a hardcoded True with no CLI or
    redis-write toggle -- published for display only, never read back. This
    covers the startup read-back and the new setter, mirroring
    test_cinepi_controller_startup_sensor_mode.py's controller() pattern."""

    def controller(self, redis):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = redis
        controller.dynamic_resolution_enabled = True
        controller.dynamic_resolution_active = False
        controller.dynamic_resolution_desired_mode = None
        return controller

    def test_startup_defaults_to_enabled_when_unset(self):
        controller = self.controller(FakeRedis())
        self.assertTrue(controller._get_startup_dynamic_resolution_enabled())

    def test_startup_reads_back_disabled_from_redis(self):
        controller = self.controller(FakeRedis(dynamic_resolution_enabled=0))
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

    def test_invalid_value_raises(self):
        controller = self.controller(FakeRedis())
        with self.assertRaises(ValueError):
            controller.set_dynamic_resolution_enabled("nonsense")


if __name__ == "__main__":
    unittest.main()
