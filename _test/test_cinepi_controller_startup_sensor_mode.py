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
    def __init__(self, sensor_mode=None):
        self.values = {}
        if sensor_mode is not None:
            self.values[ParameterKey.SENSOR_MODE.value] = sensor_mode
        self.sets = []

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value
        self.sets.append((key, value))


class FakeSensorDetect:
    def __init__(self, res_modes):
        self.res_modes = res_modes


class StartupSensorModeTests(unittest.TestCase):
    """Covers the crash from settings.json narrowing `resolutions.k_steps`
    (e.g. to 4K only): SensorDetect re-indexes res_modes from 0, so a
    sensor_mode saved in redis from a wider mode table (e.g. 3) is no
    longer a valid key. _get_startup_sensor_mode() must not hand that
    stale index to callers like _recompute_file_size(), which does a
    plain res_modes[...] lookup."""

    def controller(self, sensor_mode, res_modes):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = FakeRedis(sensor_mode)
        controller.sensor_detect = FakeSensorDetect(res_modes)
        return controller

    def test_stale_mode_survives_resolution_narrowing(self):
        controller = self.controller(
            sensor_mode="3",
            res_modes={0: {"width": 3856, "height": 2180, "bit_depth": 12}},
        )

        with self.assertLogs(level="INFO"):
            mode = controller._get_startup_sensor_mode()

        self.assertEqual(mode, 0)
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.SENSOR_MODE.value),
            0,
        )

    def test_valid_mode_is_kept_unchanged(self):
        controller = self.controller(
            sensor_mode="1",
            res_modes={
                0: {"width": 1928, "height": 1090, "bit_depth": 12},
                1: {"width": 3856, "height": 2180, "bit_depth": 12},
            },
        )

        mode = controller._get_startup_sensor_mode()

        self.assertEqual(mode, 1)
        self.assertEqual(controller.redis_controller.sets, [])

    def test_missing_mode_falls_back_to_zero(self):
        controller = self.controller(
            sensor_mode=None,
            res_modes={0: {"width": 1928, "height": 1090, "bit_depth": 12}},
        )

        mode = controller._get_startup_sensor_mode()

        self.assertEqual(mode, 0)
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.SENSOR_MODE.value),
            0,
        )

    def test_stale_mode_falls_back_to_lowest_available_key_when_zero_missing(self):
        # Defensive case: res_modes without a 0 key (shouldn't happen given
        # SensorDetect always enumerates from 0, but _get_startup_sensor_mode
        # must not raise even if it did).
        controller = self.controller(
            sensor_mode="9",
            res_modes={2: {"width": 3856, "height": 2180, "bit_depth": 12}},
        )

        with self.assertLogs(level="INFO"):
            mode = controller._get_startup_sensor_mode()

        self.assertEqual(mode, 2)


if __name__ == "__main__":
    unittest.main()
