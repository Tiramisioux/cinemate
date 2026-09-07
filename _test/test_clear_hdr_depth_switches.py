"""The two ClearHDR depths are offered independently.

The imx585 reports ClearHDR at 12-bit and 16-bit, and they are different
captures rather than two spellings of one: the 12-bit stream is companded and
needs cinepi-raw's CCMP decompand (and a measured table for the mode's
binning), the 16-bit stream is delivered linear. An operator choosing between
them had one switch covering both.

image_capture.bit_depths cannot express it. That filter is global, so turning
12 off there to drop 12-bit ClearHDR takes the 12-bit SDR modes with it -- on
an imx585 that is every SDR mode the sensor has.

So the class question ("expose ClearHDR at all") and the depth question
("which of its depths") are separate, and only the second can tell 12-bit
ClearHDR from 12-bit SDR.
"""

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.sensor_detect import SensorDetect

# An imx585 on the 7-mode driver: SDR at two sizes, then ClearHDR at 12- and
# 16-bit at those same two sizes.
MODES = [
    {"width": 1928, "height": 1090, "bit_depth": 12, "hdr": False, "fps_max": 87},
    {"width": 3856, "height": 2180, "bit_depth": 12, "hdr": False, "fps_max": 43},
    {"width": 1928, "height": 1090, "bit_depth": 12, "hdr": True, "fps_max": 60},
    {"width": 3856, "height": 2180, "bit_depth": 12, "hdr": True, "fps_max": 30},
    {"width": 1928, "height": 1090, "bit_depth": 16, "hdr": True, "fps_max": 40},
    {"width": 3856, "height": 2180, "bit_depth": 16, "hdr": True, "fps_max": 21},
]


def surviving(hdr_cfg):
    """(hdr, bit_depth) pairs left after the settings.jsonc filters."""
    detector = SensorDetect.__new__(SensorDetect)
    detector.bit_depths = []
    detector.k_steps = []
    detector.custom_modes = {}
    detector.hdr_modes = SensorDetect._hdr_whitelist(hdr_cfg)
    detector.clear_hdr_depths = SensorDetect._clear_hdr_depths(hdr_cfg)
    pruned = detector._finalize_modes({"imx585": [dict(m) for m in MODES]})
    return sorted((bool(m.get("hdr")), m["bit_depth"])
                  for m in pruned["imx585"].values())


class DepthSwitchTests(unittest.TestCase):
    def test_both_on_offers_both_depths(self):
        got = surviving({"sdr": True, "imx585_clear_hdr_12bit": True,
                         "imx585_clear_hdr_16bit": True})
        self.assertIn((True, 12), got)
        self.assertIn((True, 16), got)

    def test_16bit_off_leaves_12bit_clearhdr_and_every_sdr_mode(self):
        got = surviving({"sdr": True, "imx585_clear_hdr_12bit": True,
                         "imx585_clear_hdr_16bit": False})
        self.assertIn((True, 12), got)
        self.assertNotIn((True, 16), got)
        self.assertIn((False, 12), got)

    def test_12bit_off_keeps_the_12bit_SDR_modes(self):
        # The whole reason this is not image_capture.bit_depths: on an imx585
        # every SDR mode is 12-bit, so a global depth filter would empty the
        # sensor.
        got = surviving({"sdr": True, "imx585_clear_hdr_12bit": False,
                         "imx585_clear_hdr_16bit": True})
        self.assertNotIn((True, 12), got)
        self.assertIn((True, 16), got)
        self.assertIn((False, 12), got)

    def test_both_off_leaves_the_sensor_SDR_only(self):
        got = surviving({"sdr": True, "imx585_clear_hdr_12bit": False,
                         "imx585_clear_hdr_16bit": False})
        self.assertEqual(set(got), {(False, 12)})


class LegacyKeyTests(unittest.TestCase):
    def test_an_untouched_config_offers_everything(self):
        self.assertEqual(SensorDetect._clear_hdr_depths({}), {12, 16})

    def test_the_old_single_switch_still_turns_both_off(self):
        # A settings.jsonc written before the split says only this. Reading it
        # as "no opinion" would silently switch ClearHDR back on.
        self.assertEqual(SensorDetect._clear_hdr_depths({"imx585_clear_hdr": False}), set())
        got = surviving({"sdr": True, "imx585_clear_hdr": False})
        self.assertEqual(set(got), {(False, 12)})

    def test_an_explicit_depth_switch_outranks_the_old_one(self):
        self.assertEqual(
            SensorDetect._clear_hdr_depths(
                {"imx585_clear_hdr": False, "imx585_clear_hdr_16bit": True}),
            {16})

    def test_the_legacy_list_form_has_no_per_depth_opinion(self):
        # {sdr, imx585_clear_hdr} replaced a bare [false, true] list. There is
        # nothing per-depth to read out of that, and inventing one would
        # filter modes an old file never asked to lose.
        self.assertIsNone(SensorDetect._clear_hdr_depths([False, True]))


class WiringTests(unittest.TestCase):
    def test_the_page_offers_one_switch_per_depth(self):
        html = (ROOT / "src/module/app/templates/settings_editor.html").read_text(encoding="utf-8")
        self.assertIn('data-path="image_capture.hdr.imx585_clear_hdr_12bit"', html)
        self.assertIn('data-path="image_capture.hdr.imx585_clear_hdr_16bit"', html)

    def test_settings_and_schema_carry_both(self):
        import json  # noqa: PLC0415
        from module.config_loader import load_settings  # noqa: PLC0415
        hdr = load_settings(str(ROOT / "settings.jsonc"))["image_capture"]["hdr"]
        self.assertIs(hdr["imx585_clear_hdr_12bit"], True)
        self.assertIs(hdr["imx585_clear_hdr_16bit"], True)
        props = json.loads((ROOT / "settings.schema.json").read_text())[
            "properties"]["image_capture"]["properties"]["hdr"]["properties"]
        for key in ("imx585_clear_hdr_12bit", "imx585_clear_hdr_16bit"):
            with self.subTest(key=key):
                self.assertEqual(props[key]["type"], "boolean")


if __name__ == "__main__":
    unittest.main()
