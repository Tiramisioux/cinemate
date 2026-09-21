"""WP-CM-6 item 1, WP-CM-11: the three settings keys, in settings.jsonc,
resources/settings/settings_default.jsonc, settings.schema.json and
config_loader.py's defaults.

image_capture.enabled_modes already exists and is already per camera name --
this file is not about that one, only about the two new keys the aspect
family adds: aspect_ratios and min_mode_width. A settings file with no
aspect_ratios must behave exactly as it does today: for imx585, whose
detected modes are already ~16:9, the shipped {} -- WP-CM-11: each camera's
own derived default, not a single hardcoded ratio -- must offer the same
modes k_steps/bit_depths alone offered before this package.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.config_loader import load_settings, strip_jsonc


class SettingsKeysTests(unittest.TestCase):
    def test_settings_jsonc_and_default_both_carry_aspect_ratios(self):
        # WP-CM-11: ships as {}, an empty dict -- present (so the key exists
        # and behaves like a settings file that predates it never does, see
        # test_config_loader_leaves_a_settings_file_with_neither_key_absent
        # below), but with no "default" entry, so each camera falls to its
        # own derived set (SensorDetect._derived_default_ratio_ids) rather
        # than a single hardcoded ratio.
        for path in ("settings.jsonc", "resources/settings/settings_default.jsonc"):
            with self.subTest(path=path):
                ic = load_settings(str(ROOT / path))["image_capture"]
                self.assertIn("aspect_ratios", ic)
                self.assertEqual(ic["aspect_ratios"], {})

    def test_settings_jsonc_and_default_both_carry_min_mode_width(self):
        for path in ("settings.jsonc", "resources/settings/settings_default.jsonc"):
            with self.subTest(path=path):
                ic = load_settings(str(ROOT / path))["image_capture"]
                self.assertEqual(ic["min_mode_width"], 1280)

    def test_config_loader_leaves_a_settings_file_with_neither_key_absent(self):
        # A settings.jsonc written before this package landed has neither
        # key at all -- every deployed settings.jsonc, since both keys are
        # brand new. _apply_settings_defaults() must NOT inject either one:
        # doing so would make "the operator explicitly chose the shipped
        # default" indistinguishable from "config_loader defaulted a key
        # the operator never saw", and sensor_detect.SensorDetect relies on
        # that distinction (aspect_ratios_cfg/min_mode_width being None, not
        # merely falsy) to skip the ratio matcher/width floor entirely for a
        # settings file that predates WP-CM-6 -- otherwise a stock sensor's
        # non-16:9 modes (e.g. imx477's 4:3 full-sensor readout) would
        # silently vanish behind the new filter, which is exactly the
        # regression WORK-PACKAGES.md's WP-CM-6 rules out with "a settings
        # file with no aspect_ratios must behave exactly as it does today".
        # A fresh install still gets both keys, because they come from
        # resources/settings/settings_default.jsonc's own content (see the
        # two tests above), not from this defaulting pass.
        minimal = json.loads(strip_jsonc((ROOT / "settings.jsonc").read_text(encoding="utf-8")))
        del minimal["image_capture"]["aspect_ratios"]
        del minimal["image_capture"]["min_mode_width"]
        from module.config_loader import _apply_settings_defaults  # noqa: PLC0415
        out = _apply_settings_defaults(minimal)
        self.assertNotIn("aspect_ratios", out["image_capture"])
        self.assertNotIn("min_mode_width", out["image_capture"])

    def test_schema_declares_both_keys(self):
        props = json.loads((ROOT / "settings.schema.json").read_text())[
            "properties"]["image_capture"]["properties"]
        self.assertEqual(props["aspect_ratios"]["type"], "object")
        self.assertEqual(props["min_mode_width"]["type"], "integer")
        self.assertEqual(props["min_mode_width"]["default"], 1280)

    def test_schema_still_rejects_an_unknown_image_capture_key(self):
        # additionalProperties: false on image_capture -- confirms the new
        # keys were added to the schema's properties, not merely tolerated
        # by a permissive schema that would have hidden a typo either way.
        ic_schema = json.loads((ROOT / "settings.schema.json").read_text())[
            "properties"]["image_capture"]
        self.assertIs(ic_schema.get("additionalProperties"), False)

    def test_enabled_modes_scoping_is_untouched(self):
        # WP-CM-6 explicitly leaves this key's existing per-camera scoping
        # alone -- it is what makes swapping sensors restore each sensor's
        # own selection, and nothing about the aspect family should change
        # it. settings.jsonc carries no enabled_modes entry of its own
        # (unchanged, pre-existing); settings_default.jsonc's empty {} is
        # the key's documented "no selection yet" state.
        ic = load_settings(str(ROOT / "resources/settings/settings_default.jsonc"))["image_capture"]
        self.assertIn("enabled_modes", ic)
        self.assertEqual(ic["enabled_modes"], {})


if __name__ == "__main__":
    unittest.main()
