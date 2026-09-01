import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.cinepi_controller import (
    CinePiController,
    STARTUP_FPS_DEFAULT,
    STARTUP_SHUTTER_A_DEFAULT,
)
from module.redis_controller import ParameterKey


class FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.sets = []

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value, *, force=False):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value
        self.sets.append((key, value))


class FakeSensorDetect:
    def __init__(self, res_modes=None, camera_model=None):
        self.res_modes = res_modes if res_modes is not None else {}
        self.camera_model = camera_model


def make_controller(redis_controller, sensor_detect):
    controller = CinePiController.__new__(CinePiController)
    controller.redis_controller = redis_controller
    controller.sensor_detect = sensor_detect
    return controller


class RecomputeFileSizeNoCameraTests(unittest.TestCase):
    """C3.1: _recompute_file_size() must not KeyError on an empty res_modes
    dict (every no-camera boot hands it res_modes == {})."""

    def test_empty_res_modes_returns_without_touching_redis(self):
        redis_controller = FakeRedis()
        controller = make_controller(redis_controller, FakeSensorDetect(res_modes={}))
        controller.sensor_mode = 0

        controller._recompute_file_size()

        self.assertEqual(redis_controller.sets, [])

    def test_populated_res_modes_still_computes(self):
        redis_controller = FakeRedis()
        controller = make_controller(
            redis_controller,
            FakeSensorDetect(res_modes={
                0: {"width": 1928, "height": 1090, "bit_depth": 12, "hdr": False},
            }),
        )
        controller.sensor_mode = 0
        controller.current_sensor = "imx585"
        controller._log_requested_state = lambda: False
        controller.sensor_detect.resolve_effective_bit_depth = (
            lambda camera, native_bit_depth, log_requested, hdr: native_bit_depth
        )

        controller._recompute_file_size()

        self.assertTrue(
            any(key == ParameterKey.FILE_SIZE.value for key, _ in redis_controller.sets)
        )


class ReadOrSeedTests(unittest.TestCase):
    """C3.1: seed-if-absent, never overwrite -- the anti-corruption property
    for the four guarded startup reads (fps_last, fps_user, fps, shutter_a)."""

    def test_missing_key_seeds_default_and_writes_it_back(self):
        redis_controller = FakeRedis()
        controller = make_controller(redis_controller, FakeSensorDetect())

        result = controller._read_or_seed(ParameterKey.FPS_LAST, STARTUP_FPS_DEFAULT)

        self.assertEqual(result, STARTUP_FPS_DEFAULT)
        self.assertEqual(
            redis_controller.get_value(ParameterKey.FPS_LAST.value),
            STARTUP_FPS_DEFAULT,
        )
        self.assertEqual(
            redis_controller.sets, [(ParameterKey.FPS_LAST.value, STARTUP_FPS_DEFAULT)]
        )

    def test_present_key_is_returned_untouched_no_write(self):
        redis_controller = FakeRedis({ParameterKey.FPS_LAST.value: "18"})
        controller = make_controller(redis_controller, FakeSensorDetect())

        result = controller._read_or_seed(ParameterKey.FPS_LAST, STARTUP_FPS_DEFAULT)

        self.assertEqual(result, "18")
        self.assertEqual(redis_controller.sets, [])

    def test_shutter_a_default_is_180(self):
        redis_controller = FakeRedis()
        controller = make_controller(redis_controller, FakeSensorDetect())

        result = controller._read_or_seed(
            ParameterKey.SHUTTER_A, STARTUP_SHUTTER_A_DEFAULT
        )

        self.assertEqual(result, 180)


class ApplyStartupFpsNoCameraTests(unittest.TestCase):
    """C3.1: the fps-clamp corruption chain. With no camera, set_fps() must
    never run -- it would clamp fps/fps_user to fps_max=1 (via
    _sensor_readout_fps_max()'s int(None) catch) and cleanup() would later
    persist that 1 as fps_last. Assert directly against a *primed* Redis
    that no write happens."""

    def test_no_camera_skips_set_fps_and_writes_nothing(self):
        redis_controller = FakeRedis({
            ParameterKey.FPS_LAST.value: "18",
            ParameterKey.FPS_USER.value: "18",
            ParameterKey.FPS.value: "18",
        })
        controller = make_controller(
            redis_controller, FakeSensorDetect(camera_model=None)
        )
        controller.fps = 18
        controller.dynamic_resolution_suspended = False

        def _fail_set_fps(*args, **kwargs):
            self.fail("set_fps() must not be called when no camera is detected")

        controller.set_fps = _fail_set_fps

        with self.assertLogs(level="INFO"):
            controller._apply_startup_fps()

        self.assertEqual(redis_controller.sets, [])
        self.assertEqual(redis_controller.get_value(ParameterKey.FPS_LAST.value), "18")
        self.assertEqual(redis_controller.get_value(ParameterKey.FPS_USER.value), "18")
        self.assertEqual(redis_controller.get_value(ParameterKey.FPS.value), "18")

    def test_camera_present_still_calls_set_fps(self):
        redis_controller = FakeRedis()
        controller = make_controller(
            redis_controller, FakeSensorDetect(camera_model="imx585")
        )
        controller.fps = 24
        controller.dynamic_resolution_suspended = False

        calls = []
        controller.set_fps = lambda value: calls.append(value)

        controller._apply_startup_fps()

        self.assertEqual(calls, [24])
        self.assertFalse(controller.dynamic_resolution_suspended)


if __name__ == "__main__":
    unittest.main()
