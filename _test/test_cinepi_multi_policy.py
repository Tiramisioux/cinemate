import io
import sys
import types
import unittest
from queue import Queue
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

from module.cinepi_multi import _resolve_launch_policy, _resolve_recording_profile, _resolve_cli_relay, CinePiProcess


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

    def test_cli_relay_defaults(self):
        relay = _resolve_cli_relay({})
        self.assertEqual(relay["mode"], "event")
        self.assertEqual(relay["level"], "info")
        self.assertEqual(relay["filters"], [])
        self.assertEqual(relay["frame_sample_n"], 1)

    def test_cli_relay_validation(self):
        relay = _resolve_cli_relay({"cli_relay": {"mode": "bad", "level": "warn", "frame_sample_n": 0, "filters": ["DNG", ""]}})
        self.assertEqual(relay["mode"], "event")
        self.assertEqual(relay["level"], "info")
        self.assertEqual(relay["frame_sample_n"], 1)
        self.assertEqual(relay["filters"], ["DNG"])

    def _make_test_proc(self, cli_relay=None, metadata_enabled=False):
        proc = CinePiProcess.__new__(CinePiProcess)
        proc.cli_relay = cli_relay or {"mode": "off", "level": "info", "filters": [], "frame_sample_n": 1}
        from module.cinepi_multi import _CliRelayPolicy

        proc.cli_relay_policy = _CliRelayPolicy(proc.cli_relay)
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

    def test_mode_off_drops_all(self):
        proc, redis_calls, msg_events = self._make_test_proc(cli_relay={"mode": "off", "level": "debug", "filters": [], "frame_sample_n": 1})
        log_calls = []
        proc._log = lambda _line: log_calls.append(_line)

        q = Queue()
        pipe = io.BytesIO(b"Encoder configured\nFrame Number: 1\n")
        proc._pump(pipe, q)

        self.assertEqual(log_calls, [])
        self.assertEqual(msg_events, [])
        self.assertEqual(redis_calls, [])

    def test_mode_event_relays_only_events(self):
        proc, _redis_calls, msg_events = self._make_test_proc(cli_relay={"mode": "event", "level": "debug", "filters": [], "frame_sample_n": 1})
        log_calls = []
        proc._log = lambda line: log_calls.append(line)

        q = Queue()
        pipe = io.BytesIO(b"Encoder configured\nFrame Number: 1\nCamera detected\n")
        proc._pump(pipe, q)

        self.assertEqual(log_calls, ["Encoder configured", "Camera detected"])
        self.assertEqual(msg_events, ["Encoder configured", "Camera detected"])

    def test_mode_frame_sampling(self):
        proc, _redis_calls, msg_events = self._make_test_proc(cli_relay={"mode": "frame", "level": "debug", "filters": [], "frame_sample_n": 2})
        log_calls = []
        proc._log = lambda line: log_calls.append(line)

        q = Queue()
        pipe = io.BytesIO(
            b"Frame Number: 1\nFrame Number: 2\nEncoder configured\nFrame Number: 3\nFrame Number: 4\n"
        )
        proc._pump(pipe, q)

        self.assertEqual(log_calls, ["Frame Number: 2", "Frame Number: 4"])
        self.assertEqual(msg_events, ["Frame Number: 2", "Frame Number: 4"])

    def test_filters_apply_after_mode(self):
        proc, _redis_calls, msg_events = self._make_test_proc(cli_relay={"mode": "event", "level": "debug", "filters": ["storage"], "frame_sample_n": 1})
        log_calls = []
        proc._log = lambda line: log_calls.append(line)

        q = Queue()
        pipe = io.BytesIO(b"Encoder configured\nStorage mounted\n")
        proc._pump(pipe, q)

        self.assertEqual(log_calls, ["Storage mounted"])
        self.assertEqual(msg_events, ["Storage mounted"])

    def test_no_dng_redis_update_when_stdout_metadata_disabled(self):
        proc, redis_calls, _msg_events = self._make_test_proc(cli_relay={"mode": "off", "level": "debug", "filters": [], "frame_sample_n": 1}, metadata_enabled=False)
        q = Queue()
        pipe = io.BytesIO(b"DNG written: /tmp/clip_0001.dng\n")
        proc._pump(pipe, q)

        self.assertEqual(redis_calls, [])


if __name__ == "__main__":
    unittest.main()
