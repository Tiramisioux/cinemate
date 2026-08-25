"""usb_monitor.Event.emit takes *args (mic hotswap payloads carry action,
device, model, serial). Before this fix it iterated the live listener list
with no copy, so a listener that subscribes/unsubscribes in response to its
own event -- the mic hotswap handlers do -- could raise RuntimeError and take
the whole emit down with it. It also logged failures with traceback.print_exc()
to stdout instead of the log file, so a raising listener was invisible outside
a live terminal (fixed in place by B9.6a). B9.6b then collapsed the four
independent Event classes (F-127) into one: usb_monitor.Event is now a
re-exported alias of redis_controller.Event, not a copy -- see the identity
check below.
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault(
    "pyudev",
    types.SimpleNamespace(Context=object, Monitor=object, MonitorObserver=object),
)
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.usb_monitor import Event
from module.redis_controller import Event as RedisControllerEvent


class UsbMonitorEventDispatchTests(unittest.TestCase):
    def test_is_the_shared_redis_controller_event_not_a_copy(self):
        self.assertIs(Event, RedisControllerEvent)

    def test_a_raising_listener_does_not_stop_the_others(self):
        seen = []

        event = Event()
        event.subscribe(lambda *args: seen.append(("first", args)))
        event.subscribe(lambda *args: (_ for _ in ()).throw(RuntimeError("boom")))
        event.subscribe(lambda *args: seen.append(("third", args)))

        with self.assertLogs(level="ERROR"):
            event.emit("mic_changed", "/dev/snd/card1", "USB Mic", "12345")

        self.assertEqual(
            seen,
            [
                ("first", ("mic_changed", "/dev/snd/card1", "USB Mic", "12345")),
                ("third", ("mic_changed", "/dev/snd/card1", "USB Mic", "12345")),
            ],
        )

    def test_the_failure_is_logged_not_swallowed(self):
        event = Event()
        event.subscribe(lambda *args: (_ for _ in ()).throw(ValueError("nope")))

        with self.assertLogs(level="ERROR") as captured:
            event.emit("add", "/dev/snd/card0")

        joined = "\n".join(captured.output)
        self.assertIn("ValueError", joined)
        self.assertIn("nope", joined)

    def test_a_listener_that_unsubscribes_itself_mid_emit_does_not_crash(self):
        # Mutating the listener list while emit() is iterating it used to
        # raise RuntimeError: list changed size during iteration.
        calls = []
        event = Event()

        def self_removing(*args):
            calls.append(args)
            event._handlers.remove(self_removing)

        event.subscribe(self_removing)
        event.subscribe(lambda *args: calls.append(("second", args)))

        event.emit("add", "/dev/snd/card2")

        self.assertEqual(len(calls), 2)
        self.assertNotIn(self_removing, event._handlers)


if __name__ == "__main__":
    unittest.main()
