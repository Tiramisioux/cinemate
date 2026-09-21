import json
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
    def __init__(self, res_modes, camera_model="imx585"):
        self.res_modes = res_modes
        self.camera_model = camera_model


class StartupSensorModeTests(unittest.TestCase):
    """Covers the crash from settings.jsonc narrowing `resolutions.k_steps`
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

    def controller_with_memory(self, sensor_model, res_modes, memory, sensor_mode=None):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = FakeRedis(sensor_mode)
        controller.redis_controller.values[ParameterKey.SENSOR_MODE_MEMORY.value] = json.dumps(memory)
        controller.sensor_detect = FakeSensorDetect(res_modes, sensor_model)
        controller.current_sensor = sensor_model
        return controller


    def test_mode_is_restored_from_the_current_sensor_slot(self):
        memory = {
            "imx585": {
                "mode": 1,
                "signature": {
                    "width": 3840, "height": 2160, "bit_depth": 12,
                    "hdr": False,
                },
            },
            "imx477": {
                "mode": 0,
                "signature": {
                    "width": 4056, "height": 3040, "bit_depth": 12,
                    "hdr": False,
                },
            },
        }

        c585 = self.controller_with_memory(
            "imx585",
            {
                0: {"width": 1920, "height": 1080, "bit_depth": 12, "hdr": False},
                1: {"width": 3840, "height": 2160, "bit_depth": 12, "hdr": False},
            },
            memory,
            sensor_mode=0,  # Deliberately points at the wrong IMX585 mode.
        )
        self.assertEqual(c585._get_startup_sensor_mode(), 1)

        c477 = self.controller_with_memory(
            "imx477",
            {
                0: {"width": 4056, "height": 3040, "bit_depth": 12, "hdr": False},
                1: {"width": 2028, "height": 1520, "bit_depth": 12, "hdr": False},
            },
            memory,
            sensor_mode=1,  # Same global index, but must not win over IMX477 memory.
        )
        self.assertEqual(c477._get_startup_sensor_mode(), 0)

    def test_sensor_mode_memory_recovers_when_mode_index_changes(self):
        memory = {
            "imx585": {
                "mode": 6,
                "signature": {
                    "width": 3840, "height": 2160, "bit_depth": 12,
                    "hdr": False,
                    "crop_x": 0, "crop_y": 0,
                    "crop_width": 3840, "crop_height": 2160,
                    "binning_x": 1, "binning_y": 1,
                },
            }
        }
        controller = self.controller_with_memory(
            "imx585",
            {
                0: {"width": 1920, "height": 1080, "bit_depth": 12, "hdr": False},
                1: {
                    "width": 3840, "height": 2160, "bit_depth": 12, "hdr": False,
                    "crop_x": 0, "crop_y": 0,
                    "crop_width": 3840, "crop_height": 2160,
                    "binning_x": 1, "binning_y": 1,
                },
            },
            memory,
        )

        self.assertEqual(controller._get_startup_sensor_mode(), 1)
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.SENSOR_MODE.value),
            1,
        )

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


class StoredShapeIdentityTests(unittest.TestCase):
    """WP-CM-2 / finding M4: `_sensor_mode_from_stored_shape` used to match
    on height (+-64), bit depth and HDR only, so 1920x1080 and 1440x1080
    were the same mode to it, and 1080/1100/1120 collided. It must now
    match the stored capture's full shape (width included, height exact)
    the same way the per-sensor mode memory does, falling back to the old
    loose height match -- and saying so -- only for a record that predates
    width being stored."""

    def controller(self, sensor_mode, res_modes, width=None, height=None,
                    bit_depth=None, hdr="0"):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = FakeRedis(sensor_mode)
        controller.sensor_detect = FakeSensorDetect(res_modes)
        if height is not None:
            controller.redis_controller.values[ParameterKey.HEIGHT.value] = height
        if width is not None:
            controller.redis_controller.values[ParameterKey.WIDTH.value] = width
        if bit_depth is not None:
            controller.redis_controller.values[ParameterKey.BIT_DEPTH.value] = bit_depth
        controller.redis_controller.values[ParameterKey.HDR.value] = hdr
        return controller

    def test_same_height_different_widths_resolve_distinctly(self):
        controller = self.controller(
            sensor_mode="9",  # not in res_modes -- forces shape-based recovery
            res_modes={
                0: {"width": 1920, "height": 1080, "bit_depth": 12, "hdr": False},
                1: {"width": 1440, "height": 1080, "bit_depth": 12, "hdr": False},
            },
            width=1440, height=1080, bit_depth=12, hdr="0",
        )

        with self.assertLogs(level="INFO"):
            mode = controller._get_startup_sensor_mode()

        self.assertEqual(mode, 1)

    def test_1080_1100_1120_resolve_distinctly(self):
        controller = self.controller(
            sensor_mode="9",
            res_modes={
                0: {"width": 1920, "height": 1080, "bit_depth": 12, "hdr": False},
                1: {"width": 1920, "height": 1100, "bit_depth": 12, "hdr": False},
                2: {"width": 1920, "height": 1120, "bit_depth": 12, "hdr": False},
            },
            width=1920, height=1100, bit_depth=12, hdr="0",
        )

        with self.assertLogs(level="INFO"):
            mode = controller._get_startup_sensor_mode()

        self.assertEqual(mode, 1)

    def test_old_record_without_width_still_resolves_and_says_so(self):
        controller = self.controller(
            sensor_mode="9",
            res_modes={
                0: {"width": 1920, "height": 1080, "bit_depth": 12, "hdr": False},
            },
            height=1080, bit_depth=12, hdr="0",  # no width -- predates it
        )

        with self.assertLogs(level="WARNING") as cm:
            mode = controller._get_startup_sensor_mode()

        self.assertEqual(mode, 0)
        self.assertTrue(any("width" in message for message in cm.output))


class GetCurrentSensorModeTests(unittest.TestCase):
    """Same finding (M4) for the sibling lookup, `get_current_sensor_mode`,
    which matched height, bit depth and HDR only and so had the same
    1920x1080 vs 1440x1080 blind spot."""

    def controller(self, res_modes, width, height, bit_depth, hdr="0"):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = FakeRedis()
        controller.sensor_detect = FakeSensorDetect(res_modes)
        controller.redis_controller.values[ParameterKey.HEIGHT.value] = height
        controller.redis_controller.values[ParameterKey.WIDTH.value] = width
        controller.redis_controller.values[ParameterKey.BIT_DEPTH.value] = bit_depth
        controller.redis_controller.values[ParameterKey.HDR.value] = hdr
        return controller

    def test_same_height_different_widths_resolve_distinctly(self):
        controller = self.controller(
            res_modes={
                0: {"width": 1920, "height": 1080, "bit_depth": 12, "hdr": False},
                1: {"width": 1440, "height": 1080, "bit_depth": 12, "hdr": False},
            },
            width=1440, height=1080, bit_depth=12, hdr="0",
        )

        mode = controller.get_current_sensor_mode()

        self.assertEqual(mode, 1)

    def test_old_record_without_width_still_resolves_and_says_so(self):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = FakeRedis()
        controller.sensor_detect = FakeSensorDetect({
            0: {"width": 1920, "height": 1080, "bit_depth": 12, "hdr": False},
        })
        controller.redis_controller.values[ParameterKey.HEIGHT.value] = 1080
        controller.redis_controller.values[ParameterKey.BIT_DEPTH.value] = 12
        controller.redis_controller.values[ParameterKey.HDR.value] = "0"
        # No WIDTH key at all -- simulates a record from before CineMate
        # stored it.

        with self.assertLogs(level="WARNING") as cm:
            mode = controller.get_current_sensor_mode()

        self.assertEqual(mode, 0)
        self.assertTrue(any("width" in message for message in cm.output))


if __name__ == "__main__":
    unittest.main()
