"""The sensor-database card must tell the truth, and must not eat the key.

Two defects lived in the same read-only card:

1. It printed the literal string "resources/sensors.json" regardless of what
   `sensors.database_file` actually said, and regardless of where that
   relative path resolved to. On a source install /home/pi/cinemate is a
   symlink (cinemate-install.sh), which Path.resolve() follows, so only the
   backend can name the file Cinemate really opens.

2. Worse, and invisible: buildState() in the editor collects only [data-path]
   elements. The card had none, so a Save posted no `sensors.database_file`
   at all -- and _apply_settings_defaults() setdefaults the stock relative
   path back in, which then gets written to settings.jsonc. An operator with
   a custom database silently lost it the first time they pressed Save, and
   the card's hardcoded label became "true" again in the process.
"""

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

_APP_PKG = types.ModuleType("module.app")
_APP_PKG.__path__ = [str(ROOT / "src" / "module" / "app")]
sys.modules.setdefault("module.app", _APP_PKG)

from flask import Flask

from module.app.settings_editor import settings_editor_bp
from module.config_loader import _apply_settings_defaults
from module.sensor_database import resolve_database_path

TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


def _client(settings):
    app = Flask(__name__)
    app.config["SETTINGS"] = settings
    app.register_blueprint(settings_editor_bp)
    return app.test_client()


class SensorDatabaseCardTests(unittest.TestCase):
    def test_card_renders_the_resolved_absolute_path(self):
        html = _client({"sensors": {"database_file": "resources/sensors.json"}}).get(
            "/settings-editor/"
        ).get_data(as_text=True)

        expected = str(resolve_database_path("resources/sensors.json"))
        self.assertTrue(Path(expected).is_absolute(), expected)
        self.assertIn(expected, html)

    def test_card_follows_an_operator_override(self):
        html = _client({"sensors": {"database_file": "/mnt/ssd/my-sensors.json"}}).get(
            "/settings-editor/"
        ).get_data(as_text=True)

        self.assertIn("/mnt/ssd/my-sensors.json", html)
        # The stock path must not also appear in the card.
        self.assertNotIn(
            ">resources/sensors.json</span>", html.replace("\n", "")
        )

    def test_missing_sensors_block_does_not_500(self):
        resp = _client({}).get("/settings-editor/")
        self.assertEqual(resp.status_code, 200)


class SensorDatabaseRoundTripTests(unittest.TestCase):
    def test_template_carries_a_data_path_so_save_round_trips_the_key(self):
        # buildState() only collects [data-path]; without this the key is
        # dropped from every Save payload. This is the regression guard.
        self.assertIn(
            'data-path="sensors.database_file"',
            TEMPLATE.read_text(encoding="utf-8"),
        )

    def test_a_payload_carrying_the_key_keeps_it(self):
        out = _apply_settings_defaults({"sensors": {"database_file": "/mnt/ssd/x.json"}})
        self.assertEqual(out["sensors"]["database_file"], "/mnt/ssd/x.json")

    def test_a_payload_missing_the_key_is_what_destroyed_it(self):
        # Documents the hazard the [data-path] field exists to prevent: this
        # is exactly what the editor used to post.
        out = _apply_settings_defaults({"sensors": {}})
        self.assertEqual(out["sensors"]["database_file"], "resources/sensors.json")


if __name__ == "__main__":
    unittest.main()
