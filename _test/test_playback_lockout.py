"""The recording lockout has to cover every route that reads off the card
mid-take, not just the one that was built first.

get_playback_frame() checks _playback_blocked(); get_playback_audio() did
not, so a hotspot client could stream a take's WAV off the card during a
take -- exactly the storage contention the frame lockout exists to
prevent, and the WAV is unfinalised mid-take by construction on top of
that. This pins both routes answering the same way, using the same
fake-module.app-package trick test_web_api_blueprint.py uses so importing
settings_editor doesn't require flask_socketio or a real Redis.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from flask import Flask  # noqa: E402

_APP_PKG = types.ModuleType("module.app")
_APP_PKG.__path__ = [str(ROOT / "src" / "module" / "app")]
sys.modules.setdefault("module.app", _APP_PKG)

from module.app import settings_editor as se_module  # noqa: E402
from module.redis_controller import ParameterKey  # noqa: E402


class FakeRedis:
    """Same shape as test_web_api_blueprint.py's, plus listener_alive() --
    _playback_blocked() checks it first, and the real RedisController's
    version can go False if the background listener thread has died
    (the handbook's trap 1 / F-204), which must fail playback CLOSED."""

    def __init__(self, values=None, alive=True):
        self.values = dict(values or {})
        self._alive = alive

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def listener_alive(self):
        return self._alive


def make_app(redis_values=None, alive=True):
    app = Flask(__name__)
    app.testing = True
    app.config["SETTINGS"] = {}
    app.config["REDIS_CONTROLLER"] = FakeRedis(redis_values, alive=alive)
    app.register_blueprint(se_module.settings_editor_bp)
    return app


class PlaybackLockoutTests(unittest.TestCase):
    def test_frame_route_refuses_while_recording(self):
        app = make_app({ParameterKey.IS_RECORDING.value: "1"})
        resp = app.test_client().get("/settings-editor/api/playback/clips/foo/frame/0")
        self.assertEqual(resp.status_code, 409)
        self.assertIn("Busy", resp.get_json()["message"])

    def test_audio_route_refuses_while_recording(self):
        """The fix: this route had no lockout check at all before."""
        app = make_app({ParameterKey.IS_RECORDING.value: "1"})
        resp = app.test_client().get("/settings-editor/api/playback/clips/foo/audio")
        self.assertEqual(resp.status_code, 409)
        self.assertIn("Busy", resp.get_json()["message"])

    def test_audio_route_refuses_during_post_take_flush(self):
        """Not just is_recording -- the same full blocking-key set the
        frame route already covers (storage pre-roll, buffer flush)."""
        app = make_app({ParameterKey.IS_WRITING_BUF.value: "1"})
        resp = app.test_client().get("/settings-editor/api/playback/clips/foo/audio")
        self.assertEqual(resp.status_code, 409)

    def test_audio_route_refuses_when_the_listener_is_dead(self):
        """Fails closed: a frozen redis cache must not read as 'not
        recording' (F-204)."""
        app = make_app(alive=False)
        resp = app.test_client().get("/settings-editor/api/playback/clips/foo/audio")
        self.assertEqual(resp.status_code, 409)

    def test_audio_route_not_blocked_reaches_wav_path(self):
        """Confirms the guard is additive, not a blanket refusal -- once
        clear, the route proceeds to actually look for the take (and 404s
        here only because no real take exists, not because of the lock)."""
        app = make_app()
        with mock.patch("module.app.playback.wav_path", return_value=None) as m:
            resp = app.test_client().get("/settings-editor/api/playback/clips/foo/audio")
        m.assert_called_once_with("foo")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
