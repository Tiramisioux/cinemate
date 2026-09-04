"""The editor must not re-create the degenerate 0/0 ClearHDR threshold pair.

bfea0be8 removed the seeded 0/0 data-selection pair from settings.jsonc. The
settings editor could put it straight back.

applyControlValue() returns early on `undefined`, so when
image_capture.hdr.threshold_low/high are ABSENT the input's static markup value
survives hydration. Both inputs shipped `value="0"`. Both shipped .jsonc files
now carry the pair explicitly as null, which hydrates blank exactly as absent
did, but a hand-written or older settings file can still omit them, and
resources/settings/settings_default.jsonc is served both when
/home/pi/cinemate/settings.jsonc is missing and for "Revert to defaults".
buildState() then read parseFloat("0") for both and Save wrote 0/0.

That pair is not rejected downstream -- cinepi_controller.cpp only refuses
high < low, not high == low -- so it reaches EXP_TH_H == EXP_TH_L, the
weighted-blend fallback the imx585 driver documents as leaving the combiner
clamped near black level.

The driver's own pair is low 0 / high 4095 (hdr_thresh_def[2] = {0x0FFF,
0x0000}, with th[0] -> EXP_TH_H and th[1] -> EXP_TH_L), and null on both sides
means "leave it alone", which is what blank must round-trip to.

Verified in a browser with the keys absent: both fields blank, placeholder
"driver", and a save would carry null/null rather than 0/0.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


class ClearHdrThresholdMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def _input(self, field_id):
        m = re.search(rf'<input[^>]*id="{field_id}"[^>]*>', self.html)
        self.assertIsNotNone(m, f"{field_id} not found")
        return m.group(0)

    def test_thresholds_do_not_ship_a_literal_zero(self):
        for fid in ("f-hdr-thlow", "f-hdr-thhigh"):
            tag = self._input(fid)
            self.assertIn('value=""', tag, f"{fid} must hydrate blank, not 0")
            self.assertNotIn('value="0"', tag)

    def test_thresholds_are_not_dirty_against_a_zero_original(self):
        for fid in ("f-hdr-thlow", "f-hdr-thhigh"):
            self.assertIn('data-original=""', self._input(fid))

    def test_blank_is_explained_to_the_operator(self):
        # A blank box that silently means "keep the driver's pair" is not
        # self-describing; the card has to say so.
        self.assertIn("Leave a threshold blank", self.html)
        self.assertIn("low 0, high 4095", self.html)

    def test_both_thresholds_still_bound_to_their_settings_keys(self):
        self.assertIn('data-path="image_capture.hdr.threshold_low"', self.html)
        self.assertIn('data-path="image_capture.hdr.threshold_high"', self.html)


if __name__ == "__main__":
    unittest.main()
