import sys
import io
from queue import Queue
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

fake = types.ModuleType("module.redis_controller")
class _Key:
    def __init__(self, value):
        self.value = value
class ParameterKey:
    ZOOM = _Key("zoom")
    IS_RECORDING = _Key("is_recording")
    FPS = _Key("fps")
    FPS_ACTUAL = _Key("fps_actual")
    BUFFER = _Key("buffer")
    BUFFER_SIZE = _Key("buffer_size")
    IS_BUFFERING = _Key("is_buffering")
    IS_WRITING_BUF = _Key("is_writing_buf")
    WRITE_SPEED_TO_DRIVE = _Key("write_speed_to_drive")
    STORAGE_TYPE = _Key("storage_type")
fake.ParameterKey = ParameterKey
sys.modules.setdefault("module.redis_controller", fake)

from module.cinepi_multi import _resolve_launch_policy, _resolve_recording_profile, _resolve_stdout_relay, CinePiProcess
fake.ParameterKey = ParameterKey
sys.modules.setdefault("module.redis_controller", fake)

from module.cinepi_multi import _resolve_launch_policy, _resolve_recording_profile


class TestCinePiLaunchAndProfile(unittest.TestCase):
    def test_profile_b_default(self):
        name, profile = _resolve_recording_profile({
            "recording_profiles": {
                "active": "B",
                "profiles": {"B": {"encode_workers": 2, "disk_workers": 1}},
            }
        })
        self.assertEqual(name, "B")
        self.assertEqual(profile["encode_workers"], 2)

    def test_launch_policy_defaults(self):
        policy = _resolve_launch_policy({})
        self.assertEqual(policy["rt_mode"], "off")
        self.assertEqual(policy["rt_priority"], 20)
        self.assertEqual(policy["cpu_affinity"], "1-3")

    def test_stdout_relay_defaults(self):
        relay = _resolve_stdout_relay({})
        self.assertFalse(relay["enabled"])
        self.assertEqual(relay["level"], "debug")
        self.assertEqual(relay["filters"], [])

    def test_stdout_relay_level_validation(self):
        relay = _resolve_stdout_relay({"stdout_relay": {"enabled": True, "level": "warn", "filters": ["DNG", "VU"]}})
        self.assertTrue(relay["enabled"])
        self.assertEqual(relay["level"], "debug")
        self.assertEqual(relay["filters"], ["DNG", "VU"])

    def _make_test_proc(self, relay_enabled=False, metadata_enabled=False):
        proc = CinePiProcess.__new__(CinePiProcess)
        proc.stdout_relay = {"enabled": relay_enabled, "level": "debug", "filters": []}
        proc.stdout_metadata_enabled = metadata_enabled
        proc.cam = type("Cam", (), {"port": "cam0", "index": 0})()
        redis_calls = []

        class _RC:
            @staticmethod
            def set_value(*args, **kwargs):
                redis_calls.append((args, kwargs))

        msg_events = []
        proc.redis_controller = _RC()
        proc.message = type("Evt", (), {"emit": lambda _self, payload=None: msg_events.append(payload)})()
        return proc, redis_calls, msg_events

    def test_pump_no_relay_when_disabled(self):
        proc, redis_calls, msg_events = self._make_test_proc(relay_enabled=False, metadata_enabled=False)
        log_calls = []
        proc._log = lambda _line: log_calls.append(_line)

        q = Queue()
        pipe = io.BytesIO(b"line1\nline2\n")
        proc._pump(pipe, q)

        self.assertEqual(log_calls, [])
        self.assertEqual(msg_events, [])
        self.assertEqual(redis_calls, [])
        self.assertEqual(q.get_nowait(), "line1")
        self.assertEqual(q.get_nowait(), "line2")

    def test_pump_relay_enabled_forwards_lines(self):
        proc, redis_calls, msg_events = self._make_test_proc(relay_enabled=True, metadata_enabled=False)
        log_calls = []
        proc._log = lambda line: log_calls.append(line)

        q = Queue()
        pipe = io.BytesIO(b"line1\nline2\n")
        proc._pump(pipe, q)

        self.assertEqual(log_calls, ["line1", "line2"])
        self.assertEqual(msg_events, ["line1", "line2"])
        self.assertEqual(redis_calls, [])

    def test_no_dng_redis_update_when_stdout_metadata_disabled(self):
        proc, redis_calls, _msg_events = self._make_test_proc(relay_enabled=False, metadata_enabled=False)
        q = Queue()
        pipe = io.BytesIO(b"DNG written: /tmp/clip_0001.dng\n")
        proc._pump(pipe, q)

        self.assertEqual(redis_calls, [])


if __name__ == "__main__":
    unittest.main()
