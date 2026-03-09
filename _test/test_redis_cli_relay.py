import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

sys.modules.setdefault("redis", types.ModuleType("redis"))
sys.modules.setdefault("psutil", types.ModuleType("psutil"))

from module.redis_controller import _CliRelayPolicy, _resolve_cli_relay


class TestRedisCliRelayPolicy(unittest.TestCase):
    def test_defaults(self):
        relay = _resolve_cli_relay({})
        self.assertEqual(relay, {
            "mode": "event",
            "level": "info",
            "filters": [],
            "frame_sample_n": 1,
        })

    def test_validation(self):
        relay = _resolve_cli_relay({
            "cli_relay": {
                "mode": "bad",
                "level": "warn",
                "filters": ["Frame", ""],
                "frame_sample_n": 0,
            }
        })
        self.assertEqual(relay["mode"], "event")
        self.assertEqual(relay["level"], "info")
        self.assertEqual(relay["filters"], ["frame"])
        self.assertEqual(relay["frame_sample_n"], 1)

    def test_mode_off_drops_all(self):
        policy = _CliRelayPolicy({"mode": "off", "filters": [], "frame_sample_n": 1})
        self.assertFalse(policy.should_relay("event", "Changed value: rec = 1"))
        self.assertFalse(policy.should_relay("frame", "Frame 1"))

    def test_event_mode_drops_frame(self):
        policy = _CliRelayPolicy({"mode": "event", "filters": [], "frame_sample_n": 1})
        self.assertTrue(policy.should_relay("event", "Changed value: rec = 1"))
        self.assertFalse(policy.should_relay("frame", "Frame 1"))

    def test_frame_mode_sampling(self):
        policy = _CliRelayPolicy({"mode": "frame", "filters": [], "frame_sample_n": 2})
        self.assertTrue(policy.should_relay("frame", "Frame 1"))
        self.assertFalse(policy.should_relay("frame", "Frame 2"))
        self.assertTrue(policy.should_relay("frame", "Frame 3"))

    def test_frame_mode_keeps_event_lines(self):
        policy = _CliRelayPolicy({"mode": "frame", "filters": [], "frame_sample_n": 2})
        self.assertTrue(policy.should_relay("event", "Changed value: rec = 1"))

    def test_filters_applied_after_mode(self):
        policy = _CliRelayPolicy({"mode": "event", "filters": ["rec"], "frame_sample_n": 1})
        self.assertTrue(policy.should_relay("event", "Changed value: rec = 1"))
        self.assertFalse(policy.should_relay("event", "Changed value: iso = 200"))

    def test_filters_apply_to_frame_mode_events_and_frames(self):
        policy = _CliRelayPolicy({"mode": "frame", "filters": ["rec"], "frame_sample_n": 1})
        self.assertTrue(policy.should_relay("event", "Changed value: rec = 1"))
        self.assertFalse(policy.should_relay("event", "Changed value: iso = 100"))
        self.assertFalse(policy.should_relay("frame", "Frame 1"))


if __name__ == "__main__":
    unittest.main()
