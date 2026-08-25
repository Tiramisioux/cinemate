"""F-015: set_value() used to accept any string key silently -- the
ParameterKey enum was a convention, never enforced. This locks in the
visible-but-non-blocking fix: an un-enumerated key still gets written (a
hard reject with no Pi available to verify every call site was judged too
risky -- see the commit message), but it now logs a warning, once per key,
so the drift is observable instead of silent.
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class _FakePubSub:
    def subscribe(self, channel):
        pass

    def listen(self):
        return iter([])  # background thread exits immediately


class _FakeStrictRedis:
    def __init__(self, *args, **kwargs):
        self._store = {}

    def keys(self, pattern="*"):
        return []

    def get(self, key):
        return self._store.get(key, b"")

    def set(self, key, value):
        self._store[key] = str(value).encode()

    def publish(self, channel, message):
        pass

    def pubsub(self):
        return _FakePubSub()


sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

import module.redis_controller as _redis_controller_module  # noqa: E402

# Other test modules import module.redis_controller before this one runs and
# share the same process-wide `redis` stub (sys.modules is not reset between
# test files), so redis_controller.py's own `redis` name may already be bound
# to a stub whose StrictRedis is just `object`. Patch the attribute on the
# module it actually holds, rather than trying to win a sys.modules race.
_redis_controller_module.redis.StrictRedis = _FakeStrictRedis

RedisController = _redis_controller_module.RedisController
ParameterKey = _redis_controller_module.ParameterKey


class SetValueParameterKeyEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.controller = RedisController()

    def test_a_known_parameter_key_does_not_warn(self):
        with self.assertRaises(AssertionError):
            with self.assertLogs(level="WARNING"):
                self.controller.set_value(ParameterKey.FPS.value, "25")

    def test_a_known_parameter_key_enum_member_does_not_warn(self):
        with self.assertRaises(AssertionError):
            with self.assertLogs(level="WARNING"):
                self.controller.set_value(ParameterKey.IS_RECORDING, "1")

    def test_an_unenumerated_key_warns(self):
        with self.assertLogs(level="WARNING") as captured:
            self.controller.set_value("totally_made_up_key", "1")
        joined = "\n".join(captured.output)
        self.assertIn("totally_made_up_key", joined)

    def test_an_unenumerated_key_only_warns_once(self):
        with self.assertLogs(level="WARNING"):
            self.controller.set_value("repeated_unknown_key", "1")
        # Second write changes the value again so it isn't short-circuited
        # by the "unchanged -- nothing to do" cache check; the warning must
        # still not repeat, or a value written every frame would flood the
        # log exactly like the case this fix exists to prevent.
        with self.assertRaises(AssertionError):
            with self.assertLogs(level="WARNING"):
                self.controller.set_value("repeated_unknown_key", "2")

    def test_the_write_still_happens_for_an_unenumerated_key(self):
        # Visible, not blocking: rejecting outright risked breaking a real
        # call site with no Pi available to verify every one of them.
        self.controller.set_value("totally_made_up_key", "42")
        self.assertEqual(self.controller.get_value("totally_made_up_key"), "42")


if __name__ == "__main__":
    unittest.main()
