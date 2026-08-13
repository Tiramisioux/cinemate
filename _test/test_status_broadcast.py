import sys
import time
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.redis_controller import Event
from module.status_broadcast import MAX_PAYLOAD_BYTES, StatusBroadcaster, build_payload


class FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.redis_parameter_changed = Event()

    def get_value(self, key, default=None):
        return self.values.get(key, default)

    def set_value(self, key, value):
        self.values[key] = str(value)
        self.redis_parameter_changed.emit({"key": key, "value": str(value)})


class BuildPayloadTests(unittest.TestCase):
    """Plan section 9: UDP payload assembly is unit-testable without hardware."""

    def test_formats_space_separated_key_value_pairs(self):
        redis = FakeRedis({"is_recording": "1", "iso": "800"})
        payload = build_payload(redis.get_value, ["is_recording", "iso"])
        self.assertEqual(payload, b"is_recording=1 iso=800")

    def test_missing_key_renders_as_empty_value(self):
        redis = FakeRedis({})
        payload = build_payload(redis.get_value, ["iso"])
        self.assertEqual(payload, b"iso=")

    def test_matches_documented_example_shape(self):
        values = {
            "is_recording": "1", "iso": "800", "fps": "24.0", "shutter_a_actual": "180.0",
            "recording_time_tod": "01:02:03:04", "space_left": "412",
            "drop_frame_count": "0", "is_mounted": "1",
        }
        redis = FakeRedis(values)
        keys = ["is_recording", "iso", "fps", "shutter_a_actual", "recording_time_tod",
                "space_left", "drop_frame_count", "is_mounted"]
        payload = build_payload(redis.get_value, keys).decode()
        self.assertEqual(
            payload,
            "is_recording=1 iso=800 fps=24.0 shutter_a_actual=180.0 "
            "recording_time_tod=01:02:03:04 space_left=412 drop_frame_count=0 is_mounted=1",
        )

    def test_truncates_oversized_payload_under_500_bytes(self):
        redis = FakeRedis({"blob": "x" * 1000})
        payload = build_payload(redis.get_value, ["blob"])
        self.assertLessEqual(len(payload), MAX_PAYLOAD_BYTES)


class StatusBroadcasterCoalesceTests(unittest.TestCase):
    """Coalescing/cadence logic, driven with a real (but short) clock —
    no network required since destinations are mocked out."""

    def _make_broadcaster(self, keys=("iso",), hz=5):
        redis = FakeRedis({"iso": "800"})
        b = StatusBroadcaster(redis, list(keys), port=18888, hz=hz)
        sent = []
        b._send = lambda: sent.append(time.monotonic())
        return b, redis, sent

    def test_sends_once_immediately_on_start(self):
        b, _redis, sent = self._make_broadcaster()
        b.start()
        time.sleep(0.05)
        b.stop()
        b.join(timeout=1)
        self.assertGreaterEqual(len(sent), 1)

    def test_ignores_changes_to_keys_not_in_the_broadcast_list(self):
        b, redis, sent = self._make_broadcaster(keys=("iso",))
        b.start()
        time.sleep(0.02)
        sent.clear()
        redis.set_value("fps", "24.0")  # not in the broadcast key list
        self.assertFalse(b._dirty.is_set())
        b.stop()
        b.join(timeout=1)

    def test_change_to_tracked_key_marks_dirty(self):
        b, redis, sent = self._make_broadcaster(keys=("iso",))
        b._dirty.clear()
        redis.set_value("iso", "400")
        self.assertTrue(b._dirty.is_set())
        b.stop()

    def test_stop_unsubscribes_from_redis_events(self):
        b, redis, sent = self._make_broadcaster()
        self.assertEqual(len(redis.redis_parameter_changed._handlers), 1)
        b.stop()
        self.assertEqual(len(redis.redis_parameter_changed._handlers), 0)

    def test_non_positive_hz_falls_back_to_default(self):
        redis = FakeRedis({})
        b = StatusBroadcaster(redis, ["iso"], hz=0)
        self.assertEqual(b.hz, 5)
        b.stop()


class SubnetBroadcastAddressTests(unittest.TestCase):
    def test_returns_none_for_a_nonexistent_interface(self):
        from module.status_broadcast import subnet_broadcast_address
        self.assertIsNone(subnet_broadcast_address("not-a-real-iface0"))


if __name__ == "__main__":
    unittest.main()
