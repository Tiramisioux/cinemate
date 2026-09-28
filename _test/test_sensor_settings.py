"""module.sensor_settings: settings_<camera>.jsonc load/save/delete and the
file > legacy > stock precedence (PLAN.md, per-sensor-settings-backend,
2026-09-28).

The whole point of this module: an aspect-ratio/mode choice saved for one
sensor must never survive onto a DIFFERENT sensor after a swap. Before this
package, that choice lived in settings.jsonc's image_capture section, keyed
by camera name -- so it could not literally leak across models, but a stray
global "default" entry (WP-CM-6/7 vintage) could, and a fresh install's
per-camera default (_default_ratio_ids) had no notion of "per sensor, on
disk" at all. This file tests the new per-sensor file itself in isolation;
_test/test_aspect_ratio_selection.py and test_aspect_ratio_pane_endpoint.py
cover how SensorDetect/the settings editor wire it in.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module import sensor_settings  # noqa: E402


class NormalizedCameraNameTests(unittest.TestCase):
    def test_lowercases_and_keeps_underscores(self):
        self.assertEqual(sensor_settings.sensor_settings_filename("imx585_mono"), "settings_imx585_mono.jsonc")

    def test_uppercase_is_lowered(self):
        self.assertEqual(sensor_settings.sensor_settings_filename("IMX477"), "settings_imx477.jsonc")

    def test_non_alnum_characters_become_underscores(self):
        self.assertEqual(sensor_settings.sensor_settings_filename("imx 477!"), "settings_imx_477_.jsonc")

    def test_empty_name_is_rejected(self):
        with self.assertRaises(ValueError):
            sensor_settings.sensor_settings_filename("")

    def test_punctuation_only_name_becomes_underscores_not_empty(self):
        # [^a-z0-9_] -> "_" is a 1:1 substitution, never a deletion, so only
        # a truly EMPTY input (test_empty_name_is_rejected) can ever produce
        # an empty result -- "!!!" is a valid, if silly, filename.
        self.assertEqual(sensor_settings.sensor_settings_filename("!!!"), "settings____.jsonc")


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_save_then_load_round_trips_scoped_keys(self):
        data = {
            "aspect_ratios": ["1.33:1", "1.89:1"],
            "enabled_modes": [{"width": 2028, "height": 1520, "bit_depth": 12, "hdr": False}],
            "custom_modes": [{"width": 2028, "height": 1080, "bit_depth": 12, "hdr": False, "fps_max": 40}],
        }
        path = sensor_settings.save_sensor_settings("imx477", data, self.dir)
        self.assertEqual(path, self.dir / "settings_imx477.jsonc")
        loaded = sensor_settings.load_sensor_settings("imx477", self.dir)
        self.assertEqual(loaded, data)

    def test_header_comment_is_present(self):
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.33:1"]}, self.dir)
        text = (self.dir / "settings_imx477.jsonc").read_text(encoding="utf-8")
        self.assertIn("// CineMate settings for the imx477 sensor", text)
        self.assertIn("Reset to stock", text)

    def test_version_and_sensor_are_written(self):
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.33:1"]}, self.dir)
        text = (self.dir / "settings_imx477.jsonc").read_text(encoding="utf-8")
        raw = json.loads(sensor_settings.strip_jsonc(text))
        self.assertEqual(raw["version"], sensor_settings.SENSOR_SETTINGS_VERSION)
        self.assertEqual(raw["sensor"], "imx477")

    def test_unknown_top_level_keys_are_dropped_on_save(self):
        sensor_settings.save_sensor_settings(
            "imx477",
            {"aspect_ratios": ["1.33:1"], "bogus": "nope", "custom_modes": None},
            self.dir,
        )
        loaded = sensor_settings.load_sensor_settings("imx477", self.dir)
        self.assertEqual(loaded, {"aspect_ratios": ["1.33:1"]})

    def test_missing_key_means_stock_for_that_key(self):
        sensor_settings.save_sensor_settings("imx477", {"enabled_modes": [{"width": 1, "height": 1, "bit_depth": 8, "hdr": False}]}, self.dir)
        loaded = sensor_settings.load_sensor_settings("imx477", self.dir)
        self.assertNotIn("aspect_ratios", loaded)
        self.assertNotIn("custom_modes", loaded)

    def test_absent_file_loads_as_none(self):
        self.assertIsNone(sensor_settings.load_sensor_settings("imx585", self.dir))

    def test_broken_json_loads_as_none_without_raising(self):
        (self.dir / "settings_imx585.jsonc").write_text("{not json", encoding="utf-8")
        self.assertIsNone(sensor_settings.load_sensor_settings("imx585", self.dir))

    def test_non_object_json_loads_as_none(self):
        (self.dir / "settings_imx585.jsonc").write_text("[1, 2, 3]", encoding="utf-8")
        self.assertIsNone(sensor_settings.load_sensor_settings("imx585", self.dir))

    def test_wrong_shaped_scoped_key_is_dropped_not_fatal(self):
        # aspect_ratios must be a list of str -- a list of dicts (an
        # enabled_modes-shaped value in the wrong slot) is invalid and must
        # not take the whole file down with it.
        (self.dir / "settings_imx585.jsonc").write_text(
            json.dumps({
                "version": 1, "sensor": "imx585",
                "aspect_ratios": [{"not": "a string"}],
                "enabled_modes": [{"width": 1920, "height": 1080, "bit_depth": 12, "hdr": False}],
            }),
            encoding="utf-8",
        )
        loaded = sensor_settings.load_sensor_settings("imx585", self.dir)
        self.assertIsNotNone(loaded)
        self.assertNotIn("aspect_ratios", loaded)
        self.assertIn("enabled_modes", loaded)

    def test_atomic_write_leaves_no_tmp_file(self):
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.33:1"]}, self.dir)
        leftovers = [p for p in self.dir.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_backup_created_on_overwrite(self):
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.33:1"]}, self.dir)
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.78:1"]}, self.dir)
        backups = list((self.dir / sensor_settings.BACKUP_DIR_NAME).glob("settings_imx477.jsonc.*.bak"))
        self.assertEqual(len(backups), 1)
        # The backup holds the FIRST save's content, not the second's.
        self.assertIn("1.33:1", backups[0].read_text(encoding="utf-8"))

    def test_first_save_takes_no_backup(self):
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.33:1"]}, self.dir)
        backup_dir = self.dir / sensor_settings.BACKUP_DIR_NAME
        self.assertFalse(backup_dir.exists() and any(backup_dir.iterdir()))


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_delete_removes_the_file(self):
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.33:1"]}, self.dir)
        self.assertTrue(sensor_settings.delete_sensor_settings("imx477", self.dir))
        self.assertFalse((self.dir / "settings_imx477.jsonc").exists())

    def test_delete_backs_up_first(self):
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.33:1"]}, self.dir)
        sensor_settings.delete_sensor_settings("imx477", self.dir)
        backups = list((self.dir / sensor_settings.BACKUP_DIR_NAME).glob("settings_imx477.jsonc.*.bak"))
        self.assertEqual(len(backups), 1)

    def test_delete_is_idempotent(self):
        self.assertTrue(sensor_settings.delete_sensor_settings("imx477", self.dir))
        self.assertTrue(sensor_settings.delete_sensor_settings("imx477", self.dir))


class LegacySensorSettingsTests(unittest.TestCase):
    def test_reads_only_this_cameras_own_entries(self):
        settings = {
            "image_capture": {
                "aspect_ratios": {"imx585": ["1.78:1"], "imx477": ["1.33:1"]},
                "enabled_modes": {"imx585": [{"width": 1, "height": 1, "bit_depth": 8, "hdr": False}]},
            },
        }
        self.assertEqual(
            sensor_settings.legacy_sensor_settings(settings, "imx477"),
            {"aspect_ratios": ["1.33:1"]},
        )

    def test_never_reads_default(self):
        settings = {
            "image_capture": {
                "aspect_ratios": {"default": ["1.78:1"]},
            },
        }
        self.assertEqual(sensor_settings.legacy_sensor_settings(settings, "imx477"), {})

    def test_no_image_capture_section_is_empty(self):
        self.assertEqual(sensor_settings.legacy_sensor_settings({}, "imx477"), {})

    def test_empty_list_value_is_not_carried(self):
        settings = {"image_capture": {"aspect_ratios": {"imx477": []}}}
        self.assertEqual(sensor_settings.legacy_sensor_settings(settings, "imx477"), {})


class ResolveSensorSettingsPrecedenceTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_file_beats_legacy(self):
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.89:1"]}, self.dir)
        settings = {"image_capture": {"aspect_ratios": {"imx477": ["1.33:1"]}}}
        data, source = sensor_settings.resolve_sensor_settings(settings, "imx477", self.dir)
        self.assertEqual(source, "file")
        self.assertEqual(data, {"aspect_ratios": ["1.89:1"]})

    def test_legacy_used_when_no_file(self):
        settings = {"image_capture": {"aspect_ratios": {"imx477": ["1.33:1"]}}}
        data, source = sensor_settings.resolve_sensor_settings(settings, "imx477", self.dir)
        self.assertEqual(source, "legacy")
        self.assertEqual(data, {"aspect_ratios": ["1.33:1"]})

    def test_stock_when_neither(self):
        data, source = sensor_settings.resolve_sensor_settings({}, "imx477", self.dir)
        self.assertEqual(source, "stock")
        self.assertEqual(data, {})

    def test_default_only_legacy_resolves_to_stock_not_default(self):
        # PLAN.md D2: a stray global "default" is not a legacy source for
        # ANY camera -- it must resolve exactly as if nothing were saved.
        settings = {"image_capture": {"aspect_ratios": {"default": ["1.78:1"]}}}
        data, source = sensor_settings.resolve_sensor_settings(settings, "imx477", self.dir)
        self.assertEqual(source, "stock")
        self.assertEqual(data, {})

    def test_settings_dir_none_disables_the_file_layer(self):
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.89:1"]}, self.dir)
        settings = {"image_capture": {"aspect_ratios": {"imx477": ["1.33:1"]}}}
        data, source = sensor_settings.resolve_sensor_settings(settings, "imx477", None)
        self.assertEqual(source, "legacy")
        self.assertEqual(data, {"aspect_ratios": ["1.33:1"]})

    def test_a_present_but_empty_file_is_still_source_file(self):
        sensor_settings.save_sensor_settings("imx477", {}, self.dir)
        settings = {"image_capture": {"aspect_ratios": {"imx477": ["1.33:1"]}}}
        data, source = sensor_settings.resolve_sensor_settings(settings, "imx477", self.dir)
        self.assertEqual(source, "file")
        self.assertEqual(data, {})

    def test_swap_safety_each_camera_resolves_its_own_file(self):
        sensor_settings.save_sensor_settings("imx477", {"aspect_ratios": ["1.33:1"]}, self.dir)
        sensor_settings.save_sensor_settings("imx585", {"aspect_ratios": ["1.78:1"]}, self.dir)

        data_477, source_477 = sensor_settings.resolve_sensor_settings({}, "imx477", self.dir)
        data_585, source_585 = sensor_settings.resolve_sensor_settings({}, "imx585", self.dir)

        self.assertEqual((data_477, source_477), ({"aspect_ratios": ["1.33:1"]}, "file"))
        self.assertEqual((data_585, source_585), ({"aspect_ratios": ["1.78:1"]}, "file"))
        # Deleting one camera's file must never touch the other's.
        sensor_settings.delete_sensor_settings("imx477", self.dir)
        data_585_after, source_585_after = sensor_settings.resolve_sensor_settings({}, "imx585", self.dir)
        self.assertEqual((data_585_after, source_585_after), ({"aspect_ratios": ["1.78:1"]}, "file"))


if __name__ == "__main__":
    unittest.main()
