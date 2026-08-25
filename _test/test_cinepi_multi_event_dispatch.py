"""cinepi_multi.Event fans out cinepi-raw's subprocess output on the reader
thread (CinePiManager.message, see cinepi_multi.py:281/:299, subscribed by
Mediator.handle_cinepi_message via main.py's CinePi alias). This was F-204
verbatim -- the same defect B3.1 fixed in redis_controller.Event -- until a
raising listener could kill that thread and silently stop the log relay
(fixed in place by B9.6a). B9.6b then collapsed the four independent Event
classes (F-127) into one: cinepi_multi.Event is now a re-exported alias of
redis_controller.Event, not a copy. The identity check below is what proves
that; the behavioural tests keep exercising the actual imported name so a
future re-introduction of a local copy fails here, not just in principle.
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.cinepi_multi import Event
from module.redis_controller import Event as RedisControllerEvent


class CinepiMultiEventDispatchTests(unittest.TestCase):
    def test_is_the_shared_redis_controller_event_not_a_copy(self):
        self.assertIs(Event, RedisControllerEvent)

    def test_a_raising_listener_does_not_stop_the_others(self):
        seen = []

        event = Event()
        event.subscribe(lambda data: seen.append(("first", data)))
        event.subscribe(lambda data: (_ for _ in ()).throw(RuntimeError("boom")))
        event.subscribe(lambda data: seen.append(("third", data)))

        with self.assertLogs(level="ERROR"):
            event.emit("cinepi-raw stdout line")

        self.assertEqual(
            seen,
            [("first", "cinepi-raw stdout line"), ("third", "cinepi-raw stdout line")],
        )

    def test_the_failure_is_logged_not_swallowed(self):
        event = Event()
        event.subscribe(lambda data: (_ for _ in ()).throw(ValueError("nope")))

        with self.assertLogs(level="ERROR") as captured:
            event.emit(None)

        joined = "\n".join(captured.output)
        self.assertIn("ValueError", joined)
        self.assertIn("nope", joined)


if __name__ == "__main__":
    unittest.main()
