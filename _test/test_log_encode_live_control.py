import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.cinepi_controller import CinePiController
from module.redis_controller import (
    ParameterKey,
    decode_log_encode_request,
    encode_log_encode_request,
)


class FakeRedis:
    def __init__(self, initial=None):
        self.values = dict(initial or {})
        self.sets = []

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value
        self.sets.append((key, value))


class FakeSensorDetect:
    """Just enough of SensorDetect for set_log_encode()'s
    _recompute_file_size() call to run -- these tests are about the
    redis/restart side of set_log_encode(), not the file-size number, so
    resolve_effective_bit_depth() is a trivial pass-through rather than the
    real resolver."""

    def __init__(self):
        self.res_modes = {0: {"bit_depth": 12, "width": 1928, "height": 1090, "hdr": False}}

    def resolve_effective_bit_depth(self, camera_name, native_bit_depth, *, log_requested=False, hdr=False):
        return native_bit_depth


class LogEncodeRequestCodecTests(unittest.TestCase):
    def test_round_trips_every_valid_settings_value(self):
        for value in (False, True, 10, 12):
            self.assertEqual(decode_log_encode_request(encode_log_encode_request(value)), value)

    def test_unparsable_or_unset_decodes_to_off(self):
        self.assertIs(decode_log_encode_request(None), False)
        self.assertIs(decode_log_encode_request("not-a-number"), False)
        self.assertIs(decode_log_encode_request(-1), False)

    def test_encode_rejects_garbage_as_off(self):
        self.assertEqual(encode_log_encode_request("garbage"), 0)


class SetLogEncodeTests(unittest.TestCase):
    def controller(self, *, redis_initial=None, settings_log_encode=False, recording=False):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = FakeRedis(redis_initial)
        controller.settings = {
            "camera": {"cam0": {"log_encode": settings_log_encode}, "cam1": {}}
        }
        controller.cinepi = mock.Mock()
        controller._is_recording = lambda: recording
        controller.sensor_detect = FakeSensorDetect()
        controller.sensor_mode = 0
        controller.current_sensor = "imx585"
        return controller

    def test_bare_toggle_uses_settings_seed_when_redis_unset(self):
        """No `set log` has run yet this session (redis key absent) -- the
        bare toggle's "current" state must fall back to the settings.jsonc
        seed (cam0.log_encode), matching what _build_args() itself falls
        back to, or the first toggle would guess the wrong direction."""
        controller = self.controller(settings_log_encode=False)

        controller.set_log_encode()

        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.LOG_ENCODE_REQUEST.value),
            1,
        )
        controller.cinepi.restart.assert_called_once()

    def test_bare_toggle_flips_existing_redis_state(self):
        controller = self.controller(
            redis_initial={ParameterKey.LOG_ENCODE_REQUEST.value: 12}
        )

        controller.set_log_encode()

        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.LOG_ENCODE_REQUEST.value),
            0,
        )
        controller.cinepi.restart.assert_called_once()

    def test_explicit_target_10_and_12_are_accepted(self):
        for target in (10, 12):
            controller = self.controller()
            controller.set_log_encode(target)
            self.assertEqual(
                controller.redis_controller.get_value(ParameterKey.LOG_ENCODE_REQUEST.value),
                target,
            )
            controller.cinepi.restart.assert_called_once()

    def test_explicit_invalid_target_is_rejected_not_substituted(self):
        """set log 11 is not a real target (no 11-bit spec exists) -- it
        must be rejected outright, never silently coerced to 10 or 12."""
        controller = self.controller(
            redis_initial={ParameterKey.LOG_ENCODE_REQUEST.value: 10}
        )

        controller.set_log_encode(11)

        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.LOG_ENCODE_REQUEST.value),
            10,
        )
        controller.cinepi.restart.assert_not_called()

    def test_string_off_and_on_forms(self):
        controller = self.controller(
            redis_initial={ParameterKey.LOG_ENCODE_REQUEST.value: 12}
        )
        controller.set_log_encode("off")
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.LOG_ENCODE_REQUEST.value), 0
        )

        controller.set_log_encode("on")
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.LOG_ENCODE_REQUEST.value), 1
        )
        self.assertEqual(controller.cinepi.restart.call_count, 2)

    def test_unrecognized_string_is_rejected(self):
        controller = self.controller(
            redis_initial={ParameterKey.LOG_ENCODE_REQUEST.value: 10}
        )

        controller.set_log_encode("bogus")

        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.LOG_ENCODE_REQUEST.value), 10
        )
        controller.cinepi.restart.assert_not_called()

    def test_deferred_while_recording_never_splits_a_take(self):
        """The request still applies (visible to the next cinepi-raw launch
        via the redis key), but cinepi-raw must not be restarted mid-take."""
        controller = self.controller(recording=True)

        controller.set_log_encode(12)

        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.LOG_ENCODE_REQUEST.value),
            12,
        )
        controller.cinepi.restart.assert_not_called()


if __name__ == "__main__":
    unittest.main()
