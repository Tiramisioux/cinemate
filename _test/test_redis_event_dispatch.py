"""One bad subscriber must not take the live-state bus down with it.

Event.emit runs every subscriber synchronously on RedisController's single
_listen thread. An unguarded raise there killed the thread, and because
get_value() answers from the cache rather than from redis, nothing failed
loudly: every surface carried on rendering the values it last saw. A frozen
GUI that still looks correct mid-take is the worst failure this system has.
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.redis_controller import Event


class EventDispatchTests(unittest.TestCase):
    def test_a_raising_subscriber_does_not_stop_the_others(self):
        seen = []

        event = Event()
        event.subscribe(lambda data: seen.append(("first", data)))
        event.subscribe(lambda data: (_ for _ in ()).throw(RuntimeError("boom")))
        event.subscribe(lambda data: seen.append(("third", data)))

        with self.assertLogs(level="ERROR"):
            event.emit({"key": "iso", "value": "800"})

        # The subscriber after the failure still ran -- that is the whole point.
        self.assertEqual(
            seen,
            [("first", {"key": "iso", "value": "800"}),
             ("third", {"key": "iso", "value": "800"})],
        )

    def test_the_failure_is_logged_not_swallowed(self):
        event = Event()
        event.subscribe(lambda data: (_ for _ in ()).throw(ValueError("nope")))

        with self.assertLogs(level="ERROR") as captured:
            event.emit(None)

        # "fail visible, never silent" (storage_profiles.py:41-49): the traceback
        # has to reach the log, or this guard just moves the silence.
        joined = "\n".join(captured.output)
        self.assertIn("ValueError", joined)
        self.assertIn("nope", joined)

    def test_a_raising_subscriber_does_not_unsubscribe_itself(self):
        calls = []

        def flaky(data):
            calls.append(data)
            raise RuntimeError("every time")

        event = Event()
        event.subscribe(flaky)

        for _ in range(3):
            with self.assertLogs(level="ERROR"):
                event.emit("tick")

        # Still subscribed after failing. Dropping it would be a quiet behaviour
        # change: the operator would see the key stop updating with no error.
        self.assertEqual(calls, ["tick", "tick", "tick"])


if __name__ == "__main__":
    unittest.main()
