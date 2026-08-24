"""A redis subscriber must never sleep on the listener thread.

register_events' redis_change_handler runs on RedisController's single _listen
thread, synchronously, ahead of eight other subscribers. It used to
time.sleep(2) before emitting 'reload_browser' on every white-balance change,
which stalled the whole live-state bus -- and stopped the pub/sub loop
consuming the next message -- for those two seconds.
"""

import sys
import threading
import time
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

# Other tests in this suite stub flask_socketio as SimpleNamespace(SocketIO=object),
# and sys.modules is process-wide, so whichever test imports first decides what
# `flask_socketio` means for the rest of the run. events.py needs `emit` from it.
# Top it up rather than replacing it -- clobbering the stub would break them back.
_flask_socketio = sys.modules.get("flask_socketio")
if _flask_socketio is not None and not hasattr(_flask_socketio, "emit"):
    _flask_socketio.emit = lambda *args, **kwargs: None

from module.redis_controller import Event, ParameterKey
from module.app.main.events import register_events


class FakeSocketIO:
    def __init__(self):
        self.emitted = []
        self._lock = threading.Lock()

    def on(self, _name):
        return lambda fn: fn

    def emit(self, name, payload=None):
        with self._lock:
            self.emitted.append(name)

    def names(self):
        with self._lock:
            return list(self.emitted)


class FakeRedisController:
    def __init__(self):
        self.redis_parameter_changed = Event()

    def get_value(self, key, default=None):
        return {ParameterKey.FPS_ACTUAL.value: "24"}.get(key, default)


class FakeController:
    iso_steps = shutter_a_steps_dynamic = fps_steps_dynamic = wb_steps = []

    def calculate_dynamic_shutter_angles(self, _fps):
        return []


class WbReloadTests(unittest.TestCase):
    def setUp(self):
        self.socketio = FakeSocketIO()
        self.redis = FakeRedisController()
        register_events(
            self.socketio,
            self.redis,
            FakeController(),
            types.SimpleNamespace(get_background_color=lambda: "black",
                                  populate_values=dict),
            types.SimpleNamespace(get_available_resolutions=list, camera_model=None),
        )

    def test_a_wb_change_returns_immediately(self):
        started = time.monotonic()
        self.redis.redis_parameter_changed.emit(
            {"key": ParameterKey.WB.value, "value": "5600"}
        )
        elapsed = time.monotonic() - started

        # The old code took 2 s here, with every other subscriber waiting behind it.
        self.assertLess(elapsed, 0.5, "the handler blocked the listener thread")

    def test_the_reload_still_happens_afterwards(self):
        self.redis.redis_parameter_changed.emit(
            {"key": ParameterKey.WB.value, "value": "5600"}
        )
        self.assertNotIn("reload_browser", self.socketio.names())

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if "reload_browser" in self.socketio.names():
                break
            time.sleep(0.05)

        # Deferred, not dropped -- the browser reload is still the behaviour.
        self.assertIn("reload_browser", self.socketio.names())


if __name__ == "__main__":
    unittest.main()
