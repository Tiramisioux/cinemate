"""A saved enabled_modes selection outliving a driver geometry change.

Operator, 2026-09-27: "i have only one selected resolution, yet many choices in
the menu on 5000".

WHAT WENT WRONG
SensorDetect._mode_identity keys a saved mode on
(width, height, bit_depth, hdr, crop_x, crop_y, crop_width, crop_height). The
crop half is there on purpose -- two modes can deliver the same width x height
from different windows, and only the crop tells them apart. But it also means a
saved selection stops matching the instant a driver moves its windows, and the
imx283 campaign moved every one of them at once: the corrected active area
shifted crop_x from 40 to 108 across the whole table, and MODE_1C's family from
236 to 924.

With nothing matching, _finalize_modes fell through to its last-resort "never
leave a camera without modes" branch and offered the ENTIRE table. One mode
chosen in the settings page, seventy-three in the dial, and no indication that
anything had happened.

WHAT THESE ASSERT
1. The exact tier is unchanged and still wins when the driver reports the same
   geometry the choice was saved against.
2. When the exact tier matches NOTHING, a coarse tier (size/depth/hdr) recovers
   the selection, and a notice says it was matched by size only.
3. When neither tier matches, the table still widens -- a camera with no modes
   is useless -- but a notice says so.
4. A selection that resolves cleanly leaves no notice behind, including on a
   later re-run over a repaired table.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from module.sensor_detect import SensorDetect  # noqa: E402


def _mode(w, h, *, depth=12, crop_x=108, crop_y=40, cw=5472, ch=3648):
    return {
        "width": w, "height": h, "bit_depth": depth, "hdr": False,
        "aspect": round(w / h, 2), "fps_max": 30,
        "crop_x": crop_x, "crop_y": crop_y,
        "crop_width": cw, "crop_height": ch,
        "binning_x": 1, "binning_y": 1,
    }


def _detector(enabled_modes):
    d = SensorDetect.__new__(SensorDetect)
    d.custom_modes = {}
    d.k_steps = []
    d.bit_depths = []
    d.hdr_modes = {False, True}
    d.enabled_modes = enabled_modes
    d.aspect_ratios_cfg = {}
    d.aspect_ratio_table = None
    d.min_mode_width = None
    d.mode_selection_notices = {}
    d.sensor_modes_unfiltered = {}
    return d


class EnabledModesGeometryDriftTests(unittest.TestCase):

    # The operator's saved choice: one mode, stored with the geometry the
    # driver reported at the time (the OLD crop origin, 40).
    SAVED = [_mode(2784, 1828, crop_x=40, crop_y=108)]

    def test_exact_match_is_unchanged_when_geometry_still_agrees(self):
        d = _detector({"imx283": self.SAVED})
        table = [_mode(2784, 1828, crop_x=40, crop_y=108), _mode(3744, 3664, crop_x=40, crop_y=108)]
        pruned = d._finalize_modes({"imx283": [dict(m) for m in table]})
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx283"].values()},
            {(2784, 1828)},
            "the one saved mode, and only it",
        )
        self.assertIsNone(d.mode_selection_notice("imx283"),
                          "nothing unusual happened, so nothing to report")

    def test_a_moved_crop_origin_is_recovered_by_size(self):
        # Same sizes, every crop origin moved -- exactly what the corrected
        # active area did to the whole imx283 table.
        d = _detector({"imx283": self.SAVED})
        table = [_mode(2784, 1828), _mode(3744, 3664)]
        pruned = d._finalize_modes({"imx283": [dict(m) for m in table]})
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx283"].values()},
            {(2784, 1828)},
            "the selection survives the geometry change instead of collapsing "
            "into the whole table",
        )
        notice = d.mode_selection_notice("imx283")
        self.assertIsNotNone(notice)
        self.assertEqual(notice["kind"], "geometry_changed")

    def test_coarse_tier_runs_only_after_exact_finds_nothing(self):
        # A mode the operator did NOT choose, sharing nothing but the table, must
        # not be dragged in while an exact match for their real choice exists.
        d = _detector({"imx283": self.SAVED})
        table = [
            _mode(2784, 1828, crop_x=40, crop_y=108),   # exact match
            _mode(2784, 1828),                          # same size, moved crop
        ]
        pruned = d._finalize_modes({"imx283": [dict(m) for m in table]})
        kept = list(pruned["imx283"].values())
        self.assertEqual(len(kept), 1, "the exact match alone")
        self.assertEqual((kept[0]["crop_x"], kept[0]["crop_y"]), (40, 108))
        self.assertIsNone(d.mode_selection_notice("imx283"))

    def test_a_size_that_no_longer_exists_widens_but_says_so(self):
        # The 2x2 requantisation changed delivered SIZES too, so a saved mode
        # can fail both tiers. Widening is still right -- a camera with no modes
        # is useless -- but it must not be silent.
        d = _detector({"imx283": self.SAVED})
        table = [_mode(2784, 1168), _mode(3744, 3664)]
        pruned = d._finalize_modes({"imx283": [dict(m) for m in table]})
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx283"].values()},
            {(2784, 1168), (3744, 3664)},
            "the whole table, because nothing else can be offered",
        )
        notice = d.mode_selection_notice("imx283")
        self.assertIsNotNone(notice, "the whole point: this must be visible")
        self.assertEqual(notice["kind"], "selection_unmatched")

    def test_the_notice_is_cleared_once_the_selection_resolves_again(self):
        # Re-picking in the settings page stores the current geometry; the next
        # run must not keep warning about a problem that is over.
        d = _detector({"imx283": self.SAVED})
        d._finalize_modes({"imx283": [_mode(2784, 1828)]})
        self.assertIsNotNone(d.mode_selection_notice("imx283"))

        d.enabled_modes = {"imx283": [_mode(2784, 1828)]}
        d._finalize_modes({"imx283": [_mode(2784, 1828)]})
        self.assertIsNone(d.mode_selection_notice("imx283"))

    def test_an_instance_that_never_set_the_notice_store_still_works(self):
        # The file's own convention: _finalize_modes is reachable on an instance
        # built with __new__ that set only the attributes it cared about.
        d = _detector({"imx283": self.SAVED})
        del d.mode_selection_notices
        pruned = d._finalize_modes({"imx283": [_mode(2784, 1828)]})
        self.assertEqual(len(pruned["imx283"]), 1)
        self.assertEqual(d.mode_selection_notice("imx283")["kind"], "geometry_changed")


if __name__ == "__main__":
    unittest.main()
