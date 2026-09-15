"""A save must not delete the settings keys the page has no control for.

The editor's buildState() walks document.querySelectorAll('[data-path]') and
builds the object it posts from exactly those elements, so every
settings.jsonc key without a rendered control was absent from the payload and
_apply_settings_defaults() decided it instead. Observed live on a camera on
2026-09-15: settings.jsonc had lost both image_capture.hdr.
imx585_clear_hdr_12bit and the legacy imx585_clear_hdr, and because
SensorDetect._clear_hdr_depths() reads a missing _12bit key as "fall back to
imx585_clear_hdr, default True", 12-bit ClearHDR came back on -- the opposite
of the shipped default. That one key now has a toggle (3114014f); the walk
still drops every other unrendered key, which is what this covers.

The fix is that a page is a view of the file, not the file:
_merge_saved_settings() overlays the payload on what is already on disk, so a
key the payload never mentions survives. The subtrees the page genuinely owns
-- image_capture.custom_modes, the quad rotary's encoders -- are still taken
as sent, or removing the last override for a camera could never stick.
"""

import json
import re
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
from module.app.settings_editor import (  # noqa: E402
    _merge_saved_settings,
    settings_editor_bp,
)
from module.config_loader import strip_jsonc  # noqa: E402

TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"
STOCK = ROOT / "resources" / "settings" / "settings_default.jsonc"


def _client():
    app = Flask(__name__)
    app.config["SETTINGS"] = {"sensors": {}}
    app.register_blueprint(settings_editor_bp)
    return app.test_client()


def _leaves(node, path=()):
    """Every scalar/list leaf as {dotted path: value}."""
    if isinstance(node, dict) and node:
        out = {}
        for key, sub in node.items():
            out.update(_leaves(sub, path + (str(key),)))
        return out
    return {".".join(path): node}


def _dig(node, parts):
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None, False
        node = node[part]
    return node, True


def _set(node, parts, value):
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _rendered_paths():
    """The settings paths the page actually has a control for.

    Same three attributes buildState() reads: a single field (data-path), a
    checkbox set (data-set-path) and a chip list (data-chip-path). The two
    templated occurrences ("' + path + '", written by the JS that builds a
    free-stepping card) are not literal paths and are skipped.
    """
    html = TEMPLATE.read_text(encoding="utf-8")
    found = set(re.findall(r'data-(?:path|set-path|chip-path)="([^"]+)"', html))
    return {p for p in found if "+" not in p}


class MergeSavedSettingsTests(unittest.TestCase):
    def test_a_key_the_payload_never_mentions_survives(self):
        existing = {"image_capture": {"hdr": {
            "sdr": True, "imx585_clear_hdr": False, "imx585_clear_hdr_12bit": False,
        }}}
        payload = {"image_capture": {"hdr": {"sdr": True}}}

        merged = _merge_saved_settings(existing, payload)

        self.assertEqual(merged["image_capture"]["hdr"]["imx585_clear_hdr_12bit"], False)
        self.assertEqual(merged["image_capture"]["hdr"]["imx585_clear_hdr"], False)

    def test_the_payload_wins_wherever_it_speaks(self):
        merged = _merge_saved_settings({"a": {"x": 1, "y": 2}}, {"a": {"x": 9}})

        self.assertEqual(merged["a"], {"x": 9, "y": 2})

    def test_a_null_the_operator_cleared_is_a_value_not_an_omission(self):
        # An empty number field posts null (parseFloat('') is NaN, which
        # JSON.stringify writes as null). Clearing a threshold must clear it.
        merged = _merge_saved_settings(
            {"image_capture": {"hdr": {"threshold_low": 1200}}},
            {"image_capture": {"hdr": {"threshold_low": None}}},
        )

        self.assertIsNone(merged["image_capture"]["hdr"]["threshold_low"])

    def test_a_list_is_replaced_whole_so_a_removed_chip_stays_removed(self):
        merged = _merge_saved_settings(
            {"arrays": {"iso": {"steps": [100, 200, 400]}}},
            {"arrays": {"iso": {"steps": [100, 400]}}},
        )

        self.assertEqual(merged["arrays"]["iso"]["steps"], [100, 400])

    def test_custom_modes_is_the_pages_own_so_a_deleted_override_stays_deleted(self):
        merged = _merge_saved_settings(
            {"image_capture": {"custom_modes": {"imx585": [{"width": 1920}]}}},
            {"image_capture": {"custom_modes": {}}},
        )

        self.assertEqual(merged["image_capture"]["custom_modes"], {})

    def test_a_deleted_quad_encoder_stays_deleted(self):
        merged = _merge_saved_settings(
            {"input_peripherals": {"quad_rotary_controller": {
                "enabled": True, "encoders": {"0": {"setting_name": "iso"}},
            }}},
            {"input_peripherals": {"quad_rotary_controller": {
                "enabled": True, "encoders": {},
            }}},
        )

        self.assertEqual(
            merged["input_peripherals"]["quad_rotary_controller"]["encoders"], {})

    def test_a_scalar_where_the_file_had_an_object_does_not_merge(self):
        self.assertEqual(_merge_saved_settings({"a": {"x": 1}}, {"a": 3}), {"a": 3})

    def test_nothing_on_disk_leaves_the_payload_alone(self):
        payload = {"system": {"welcome": {"show": False}}}
        self.assertEqual(_merge_saved_settings({}, payload), payload)


class SaveRoundTripTests(unittest.TestCase):
    """The real route, against a real file, posting what the page would post."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.dest = self.dir / "settings.jsonc"
        self.original = STOCK.read_text(encoding="utf-8")
        self.dest.write_text(self.original, encoding="utf-8")
        self.stock = json.loads(strip_jsonc(self.original))

    def _put(self, payload):
        with mock.patch.object(settings_editor, "SETTINGS_FILE", str(self.dest)):
            res = _client().put("/settings-editor/api/settings", json=payload)
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertTrue(res.get_json()["ok"], res.get_json())
        return json.loads(strip_jsonc(self.dest.read_text(encoding="utf-8")))

    def _page_payload(self, **overrides):
        """What buildState()'s [data-path] walk produces from the stock file:
        the rendered paths and nothing else."""
        payload = {}
        for dotted in sorted(_rendered_paths()):
            parts = dotted.split(".")
            value, found = _dig(self.stock, parts)
            if found:
                _set(payload, parts, value)
        for dotted, value in overrides.items():
            _set(payload, dotted.split("."), value)
        return payload

    def test_every_key_in_the_file_survives_a_save_of_the_rendered_ones(self):
        saved = self._put(self._page_payload())

        missing = {
            path: value for path, value in _leaves(self.stock).items()
            if _leaves(saved).get(path, "\0") != value
        }
        self.assertEqual(missing, {}, "keys lost or changed by an unrelated save")

    def test_the_clearhdr_keys_that_were_lost_on_the_camera_come_back_out(self):
        # The 2026-09-15 case: neither key had a control, both vanished, and a
        # missing _12bit reads as "fall back to imx585_clear_hdr, default
        # True" -- so the deletion alone switched 12-bit ClearHDR on.
        self.dest.write_text(json.dumps({
            "image_capture": {"hdr": {
                "sdr": True,
                "imx585_clear_hdr": False,
                "imx585_clear_hdr_12bit": False,
                "imx585_clear_hdr_16bit": True,
            }},
        }, indent=2), encoding="utf-8")

        saved = self._put({"image_capture": {"hdr": {"sdr": True}}})

        self.assertIs(saved["image_capture"]["hdr"]["imx585_clear_hdr_12bit"], False)
        self.assertIs(saved["image_capture"]["hdr"]["imx585_clear_hdr"], False)

    def test_an_edited_value_still_lands(self):
        saved = self._put(self._page_payload(**{"system.welcome.message": "HELLO"}))

        self.assertEqual(saved["system"]["welcome"]["message"], "HELLO")

    def test_an_unreadable_file_does_not_block_the_save(self):
        self.dest.write_text("{ this is not json", encoding="utf-8")

        saved = self._put({"system": {"welcome": {"show": False}}})

        self.assertIs(saved["system"]["welcome"]["show"], False)

    def test_an_absent_file_is_written_from_the_payload_alone(self):
        self.dest.unlink()

        saved = self._put({"system": {"welcome": {"show": False}}})

        self.assertIs(saved["system"]["welcome"]["show"], False)


class TemplateGuardTests(unittest.TestCase):
    """The client carries the same rule, so Upload and "revert to defaults"
    mean the whole file rather than the live camera's unrendered keys."""

    def setUp(self):
        self.html = TEMPLATE.read_text(encoding="utf-8")

    def test_build_state_starts_from_the_settings_the_page_loaded(self):
        body = self.html.split("function buildState(){", 1)[1].split("\n  }", 1)[0]
        self.assertIn("lastLoadedSettings", body)
        self.assertNotIn("var state = {};", body)

    def test_the_quad_rotary_enabled_flag_is_carried_not_invented(self):
        body = self.html.split("function buildQuadRotaryState(){", 1)[1].split("\n  }", 1)[0]
        self.assertNotIn("enabled: true", body)
        self.assertIn("lastLoadedSettings", body)


if __name__ == "__main__":
    unittest.main()
