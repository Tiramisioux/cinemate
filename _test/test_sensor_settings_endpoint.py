"""PUT /settings-editor/api/settings' `sensor_settings` key and
DELETE /settings-editor/api/sensor-settings/<camera> -- the settings-editor
wiring for per-sensor settings files (PLAN.md, per-sensor-settings-backend,
2026-09-28).

Exercises the real Flask blueprint against a real temp settings.jsonc, the
same way test_aspect_ratio_legacy_migration_save_path.py (retired by this
package -- its own save-path mechanism, image_capture.aspect_ratios merged
straight from the PUT body, no longer exists) used to.
"""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

_APP_PKG = types.ModuleType("module.app")
_APP_PKG.__path__ = [str(ROOT / "src" / "module" / "app")]
sys.modules.setdefault("module.app", _APP_PKG)

from flask import Flask  # noqa: E402

from module.app import settings_editor  # noqa: E402
from module.app.settings_editor import settings_editor_bp  # noqa: E402
from module import sensor_settings  # noqa: E402
from module.config_loader import strip_jsonc  # noqa: E402


def _client():
    app = Flask(__name__)
    app.config["SETTINGS"] = {"sensors": {}}
    app.register_blueprint(settings_editor_bp)
    return app.test_client()


class PutSensorSettingsTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.dest = self.dir / "settings.jsonc"
        self.dest.write_text(json.dumps({
            "image_capture": {
                "aspect_ratios": {"default": ["1.78:1"], "imx585": ["1.78:1"]},
                "enabled_modes": {"imx585": [{"width": 1920, "height": 1080, "bit_depth": 12, "hdr": False}]},
                "custom_modes": {"imx585": [{"width": 1920, "height": 1080, "bit_depth": 12, "hdr": False, "fps_max": 40}]},
            },
        }, indent=2), encoding="utf-8")

    def _put(self, payload):
        with mock.patch.object(settings_editor, "SETTINGS_FILE", str(self.dest)):
            res = _client().put("/settings-editor/api/settings", json=payload)
        return res

    def _on_disk(self):
        return json.loads(strip_jsonc(self.dest.read_text(encoding="utf-8")))

    def test_a_save_writes_the_per_sensor_file(self):
        res = self._put({"sensor_settings": {"imx477": {"aspect_ratios": ["1.33:1"]}}})
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        body = res.get_json()
        self.assertTrue(body["ok"], body)
        self.assertEqual(body["sensor_files"], ["settings_imx477.jsonc"])
        loaded = sensor_settings.load_sensor_settings("imx477", self.dir)
        self.assertEqual(loaded, {"aspect_ratios": ["1.33:1"]})

    def test_saving_one_camera_removes_its_own_legacy_entries(self):
        self._put({"sensor_settings": {"imx585": {"aspect_ratios": ["2.39:1"]}}})
        saved = self._on_disk()
        ic = saved["image_capture"]
        self.assertNotIn("imx585", ic.get("aspect_ratios", {}))
        self.assertNotIn("imx585", ic.get("enabled_modes", {}))
        self.assertNotIn("imx585", ic.get("custom_modes", {}))

    def test_saving_any_camera_drops_the_global_default(self):
        self._put({"sensor_settings": {"imx477": {"aspect_ratios": ["1.33:1"]}}})
        saved = self._on_disk()
        self.assertNotIn("default", saved["image_capture"].get("aspect_ratios", {}))

    def test_a_save_with_no_sensor_settings_key_leaves_per_sensor_files_alone(self):
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.33:1"]}, self.dir)
        self._put({})
        self.assertEqual(
            sensor_settings.load_sensor_settings("imx477", self.dir),
            {"aspect_ratios": ["1.33:1"]},
        )

    def test_a_save_with_no_sensor_settings_key_leaves_default_alone(self):
        self._put({})
        saved = self._on_disk()
        self.assertEqual(saved["image_capture"]["aspect_ratios"].get("default"), ["1.78:1"])

    def test_legacy_image_capture_keys_in_the_body_are_stripped_not_merged(self):
        # A stale client sending the OLD shape must not be able to narrow a
        # camera through that channel any more -- put_settings() strips it.
        res = self._put({"image_capture": {"aspect_ratios": {"imx585": ["2.39:1"]}}})
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        saved = self._on_disk()
        # The pre-existing legacy value for imx585 (1.78:1) survives
        # untouched -- the stripped payload never reached the merge.
        self.assertEqual(saved["image_capture"]["aspect_ratios"]["imx585"], ["1.78:1"])

    def test_invalid_camera_name_is_rejected(self):
        res = self._put({"sensor_settings": {"IM/X 477": {"aspect_ratios": ["1.33:1"]}}})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["ok"])

    def test_non_dict_camera_data_is_rejected(self):
        res = self._put({"sensor_settings": {"imx477": ["1.33:1"]}})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["ok"])

    def test_two_cameras_saved_in_one_request_each_get_their_own_file(self):
        res = self._put({"sensor_settings": {
            "imx477": {"aspect_ratios": ["1.33:1"]},
            "imx585": {"aspect_ratios": ["2.39:1"]},
        }})
        self.assertTrue(res.get_json()["ok"])
        self.assertEqual(
            sorted(res.get_json()["sensor_files"]),
            ["settings_imx477.jsonc", "settings_imx585.jsonc"],
        )
        self.assertEqual(sensor_settings.load_sensor_settings("imx477", self.dir), {"aspect_ratios": ["1.33:1"]})
        self.assertEqual(sensor_settings.load_sensor_settings("imx585", self.dir), {"aspect_ratios": ["2.39:1"]})


class DeleteSensorSettingsEndpointTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.dest = self.dir / "settings.jsonc"
        self.dest.write_text(json.dumps({
            "image_capture": {"aspect_ratios": {"imx477": ["1.33:1"]}},
        }, indent=2), encoding="utf-8")
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.89:1"]}, self.dir)

    def _delete(self, camera_name):
        with mock.patch.object(settings_editor, "SETTINGS_FILE", str(self.dest)):
            return _client().delete(f"/settings-editor/api/sensor-settings/{camera_name}")

    def test_delete_removes_the_file(self):
        res = self._delete("imx477")
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertTrue(res.get_json()["ok"])
        self.assertIsNone(sensor_settings.load_sensor_settings("imx477", self.dir))

    def test_delete_removes_the_legacy_entry_too(self):
        self._delete("imx477")
        saved = json.loads(strip_jsonc(self.dest.read_text(encoding="utf-8")))
        self.assertNotIn("imx477", saved["image_capture"].get("aspect_ratios", {}))

    def test_delete_is_idempotent(self):
        self._delete("imx477")
        res = self._delete("imx477")
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertTrue(res.get_json()["ok"])

    def test_delete_rejects_an_invalid_camera_name_shape(self):
        res = self._delete("not-a-real-camera!")
        self.assertEqual(res.status_code, 404)
        self.assertFalse(res.get_json()["ok"])

    def test_delete_rejects_a_path_traversal_shaped_name(self):
        # A literal "/" in the URL is Flask's own routing concern (the
        # <camera_name> converter does not match it) -- either way this must
        # 404, whether from this view or from Flask itself.
        res = self._delete("..%2F..%2Fetc")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
