"""WP-CM-11 rework, blocking review finding: the real settings-editor save
path, not just _apply_settings_defaults() in isolation.

test_aspect_ratio_selection.py's LegacyShippedDefaultMigrationTests proves
_apply_settings_defaults() clears a legacy on-disk
image_capture.aspect_ratios == {"default": ["1.78:1"]} when that is the
*whole* value. It never exercises put_settings()'s own chain, where a
pre-existing on-disk file is first merged with the operator's save payload
and only then handed to _apply_settings_defaults().

That chain has a real, reproduced failure mode: buildAspectRatiosState() in
settings_editor.html seeds its payload from the already-migrated GET
response, so a normal single-camera save never mentions "default" itself,
and _merge_saved_settings() keeps whatever the payload does not mention. So
merging the operator's payload onto the raw on-disk file *before* migrating
it turned a genuine WP-CM-6/7 leftover, {"default": ["1.78:1"]}, into a
*two*-key {"default": [...], "<camera>": [...]} the whole-dict-equality
check no longer matched -- and that poisoned two-key dict got written back
to disk permanently, on the very first save any pre-existing install ever
made through the pane, silently narrowing every OTHER camera relying on the
derived default from then on.

The fix (config_loader._migrate_legacy_shipped_aspect_ratio_default(),
called on the on-disk snapshot in settings_editor.put_settings() *before*
_merge_saved_settings()) is exercised here end to end, through the real
Flask route and a real temp settings.jsonc, exactly as the pane would drive
it: a legacy on-disk leftover plus one camera's normal save must come out
with the stale "default" gone and the saved camera's own choice intact, and
imx477/imx283 -- neither of them the camera being saved -- must keep every
stock mode afterward. A genuine pre-existing two-key config (a deliberate
"default" alongside a per-camera entry -- WP-CM-11's own "a default list
stays supported as a deliberate global choice") must survive an unrelated
save untouched, proving the fix does not trade this bug for the other one
the first review round flagged (whole-dict equality, not a key-level
"default" strip, is what keeps that case safe).
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
from module.config_loader import strip_jsonc  # noqa: E402
from module.sensor_detect import SensorDetect  # noqa: E402


def _client():
    app = Flask(__name__)
    app.config["SETTINGS"] = {"sensors": {}}
    app.register_blueprint(settings_editor_bp)
    return app.test_client()


def _detector(aspect_ratios_cfg):
    d = SensorDetect.__new__(SensorDetect)
    d.bit_depths = []
    d.k_steps = []
    d.custom_modes = {}
    d.hdr_modes = SensorDetect._hdr_whitelist({})
    d.clear_hdr_depths = None
    d.enabled_modes = {}
    d.aspect_ratios_cfg = aspect_ratios_cfg
    d.sensor_modes_unfiltered = {}
    return d


# Same fixtures as test_aspect_ratio_selection.py's IMX477_FIVE_MODES /
# IMX283_SIX_MODES (WORK-PACKAGES.md's WP-CM-11 table, read from the
# mainline drivers / resources/sensors.json) -- kept local rather than
# imported so this file's own test discovery does not depend on that
# module's import side effects.
IMX477_FIVE_MODES = [
    {"width": 4056, "height": 3040, "bit_depth": 12, "hdr": False, "fps_max": 10},
    {"width": 4056, "height": 2160, "bit_depth": 12, "hdr": False, "fps_max": 20},
    {"width": 2028, "height": 1520, "bit_depth": 12, "hdr": False, "fps_max": 40},
    {"width": 2028, "height": 1080, "bit_depth": 12, "hdr": False, "fps_max": 50},
    {"width": 1332, "height": 990, "bit_depth": 10, "hdr": False, "fps_max": 120},
]

IMX283_SIX_MODES = [
    {"width": 5568, "height": 3664, "bit_depth": 12, "hdr": False, "fps_max": 18, "aspect": 1.5},
    {"width": 2784, "height": 1828, "bit_depth": 12, "hdr": False, "fps_max": 36, "aspect": 1.5},
    {"width": 2784, "height": 1542, "bit_depth": 12, "hdr": False, "fps_max": 41, "aspect": 1.78},
    {"width": 5568, "height": 3664, "bit_depth": 10, "hdr": False, "fps_max": 18, "aspect": 1.5},
    {"width": 5568, "height": 3094, "bit_depth": 10, "hdr": False, "fps_max": 21, "aspect": 1.78},
    {"width": 3936, "height": 2176, "bit_depth": 10, "hdr": False, "fps_max": 44, "aspect": 1.78},
]


class LegacyDefaultSurvivesASingleCameraSaveTests(unittest.TestCase):
    """The exact scenario the second review round reproduced by running the
    real code: a WP-CM-6/7 leftover on disk, then one ordinary save."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.dest = self.dir / "settings.jsonc"
        self.dest.write_text(json.dumps({
            "image_capture": {"aspect_ratios": {"default": ["1.78:1"]}},
        }, indent=2), encoding="utf-8")

    def _put(self, payload):
        with mock.patch.object(settings_editor, "SETTINGS_FILE", str(self.dest)):
            res = _client().put("/settings-editor/api/settings", json=payload)
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertTrue(res.get_json()["ok"], res.get_json())
        return json.loads(strip_jsonc(self.dest.read_text(encoding="utf-8")))

    def test_the_stale_default_is_gone_and_the_saved_cameras_choice_survives(self):
        saved = self._put({
            "image_capture": {"aspect_ratios": {"imx585": ["1.78:1", "1.90:1"]}},
        })

        self.assertEqual(
            saved["image_capture"]["aspect_ratios"],
            {"imx585": ["1.78:1", "1.90:1"]},
            "a legacy on-disk {\"default\": [\"1.78:1\"]} must not survive as a "
            "sibling of the camera key a normal save just wrote",
        )

    def test_imx477_keeps_all_five_modes_after_that_save(self):
        saved = self._put({
            "image_capture": {"aspect_ratios": {"imx585": ["1.78:1", "1.90:1"]}},
        })

        d = _detector(saved["image_capture"]["aspect_ratios"])
        pruned = d._finalize_modes({"imx477": [dict(m) for m in IMX477_FIVE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertEqual(
            sizes,
            {(m["width"], m["height"]) for m in IMX477_FIVE_MODES},
            "imx477 was never the camera being saved -- a surviving stale "
            "\"default\" would silently narrow it to 1.78:1 only",
        )

    def test_imx283_keeps_all_six_modes_after_that_save(self):
        saved = self._put({
            "image_capture": {"aspect_ratios": {"imx585": ["1.78:1", "1.90:1"]}},
        })

        d = _detector(saved["image_capture"]["aspect_ratios"])
        pruned = d._finalize_modes({"imx283": [dict(m) for m in IMX283_SIX_MODES]})
        sizes = {
            (m["width"], m["height"], m["bit_depth"])
            for m in pruned["imx283"].values()
        }
        self.assertEqual(
            sizes,
            {(m["width"], m["height"], m["bit_depth"]) for m in IMX283_SIX_MODES},
            "imx283 was never the camera being saved -- a surviving stale "
            "\"default\" would silently narrow it to 1.78:1 only",
        )


class GenuineTwoKeyDefaultSurvivesAnUnrelatedSaveTests(unittest.TestCase):
    """WP-CM-11 rework, first review round: a "default" alongside a
    per-camera key is real operator config (a deliberate global choice plus
    one camera's own override -- WORK-PACKAGES.md's WP-CM-11 "a default list
    stays supported as a deliberate global choice"), not leftover, and must
    not be stripped just because *some* two-key shape is also what the
    merge-order bug used to produce. Whole-dict equality on the on-disk
    snapshot (not a key-level "default" strip) is what keeps this safe even
    after the fix above."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.dest = self.dir / "settings.jsonc"
        self.dest.write_text(json.dumps({
            "image_capture": {
                "aspect_ratios": {"default": ["1.78:1"], "imx585": ["2.39:1"]},
            },
        }, indent=2), encoding="utf-8")

    def test_an_unrelated_save_does_not_touch_it(self):
        with mock.patch.object(settings_editor, "SETTINGS_FILE", str(self.dest)):
            res = _client().put("/settings-editor/api/settings", json={})
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertTrue(res.get_json()["ok"], res.get_json())

        saved = json.loads(strip_jsonc(self.dest.read_text(encoding="utf-8")))
        self.assertEqual(
            saved["image_capture"]["aspect_ratios"],
            {"default": ["1.78:1"], "imx585": ["2.39:1"]},
        )


if __name__ == "__main__":
    unittest.main()
