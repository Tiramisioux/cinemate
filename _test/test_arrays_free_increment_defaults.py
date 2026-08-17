import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.config_loader import _apply_settings_defaults, strip_jsonc


EXPECTED_FREE_INCREMENT_DEFAULTS = {
    "iso": 100,
    "shutter_a": 1,
    "fps": 1,
    "wb": 100,
    "hdr_threshold_low": 16,
    "hdr_threshold_high": 16,
    "hdr_blend": 1,
    "hdr_gain_adder": 1,
}


class RuntimeDefaultsTests(unittest.TestCase):
    """_apply_settings_defaults runs on every launch to fill gaps in a live
    Pi settings.jsonc -- these lock in the free_increment defaults the user
    asked for, and the four new HDR array entries parameters.py now reads
    steps from instead of a hardcoded range."""

    def test_a_from_scratch_settings_file_gets_every_free_increment_default(self):
        arrays_cfg = _apply_settings_defaults({})["arrays"]
        for name, expected in EXPECTED_FREE_INCREMENT_DEFAULTS.items():
            with self.subTest(name=name):
                self.assertEqual(arrays_cfg[name]["free_increment"], expected)

    def test_hdr_array_entries_default_free_to_false(self):
        arrays_cfg = _apply_settings_defaults({})["arrays"]
        for name in ("hdr_threshold_low", "hdr_threshold_high", "hdr_blend", "hdr_gain_adder"):
            with self.subTest(name=name):
                self.assertIs(arrays_cfg[name]["free"], False)

    def test_hdr_array_entries_get_a_populated_steps_table(self):
        arrays_cfg = _apply_settings_defaults({})["arrays"]
        self.assertEqual(arrays_cfg["hdr_blend"]["steps"], [0, 1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(arrays_cfg["hdr_gain_adder"]["steps"], [0, 1, 2, 3, 4, 5])
        self.assertIn(4095, arrays_cfg["hdr_threshold_low"]["steps"])
        self.assertIn(4095, arrays_cfg["hdr_threshold_high"]["steps"])

    def test_an_existing_free_increment_choice_is_preserved_not_overwritten(self):
        settings = _apply_settings_defaults(
            {"arrays": {"iso": {"free_increment": 25}}}
        )
        self.assertEqual(settings["arrays"]["iso"]["free_increment"], 25)
        # untouched siblings still get their own defaults filled in
        self.assertEqual(settings["arrays"]["shutter_a"]["free_increment"], 1)

    def test_shutter_a_gets_its_own_sync_increment_default(self):
        arrays_cfg = _apply_settings_defaults({})["arrays"]
        self.assertEqual(arrays_cfg["shutter_a"]["sync_increment"], 0.1)

    def test_an_existing_sync_increment_choice_is_preserved_not_overwritten(self):
        settings = _apply_settings_defaults(
            {"arrays": {"shutter_a": {"sync_increment": 0.5}}}
        )
        self.assertEqual(settings["arrays"]["shutter_a"]["sync_increment"], 0.5)
        # free_increment is a separate field and still gets its own default
        self.assertEqual(settings["arrays"]["shutter_a"]["free_increment"], 1)


class StockSettingsFileTests(unittest.TestCase):
    """The shipped resources/settings/settings_default.jsonc (the
    from-scratch stock file, distinct from the runtime-fill path above)."""

    def setUp(self):
        self.arrays_cfg = json.loads(strip_jsonc(
            (ROOT / "resources/settings/settings_default.jsonc").read_text(encoding="utf-8")
        ))["arrays"]

    def test_every_array_entry_ships_a_free_increment(self):
        for name, expected in EXPECTED_FREE_INCREMENT_DEFAULTS.items():
            with self.subTest(name=name):
                self.assertEqual(self.arrays_cfg[name]["free_increment"], expected)

    def test_shutter_a_ships_its_own_sync_increment(self):
        self.assertEqual(self.arrays_cfg["shutter_a"]["sync_increment"], 0.1)


if __name__ == "__main__":
    unittest.main()
