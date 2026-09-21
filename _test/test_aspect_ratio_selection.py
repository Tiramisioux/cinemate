"""WP-CM-6: aspect ratio as the selection axis, with a width floor.

Mirrors test_clear_hdr_depth_switches.py's house pattern: a SensorDetect
built with __new__, only the filter attributes under test set on it, run
through the real _finalize_modes()/available_aspect_ratios().

Never infer binning from a size ratio (ASPECT-RATIOS.md): an unknown is
honest, a guess produces a binning of 6 for a 1440x1080 window and breaks the
ClearHDR companding downstream. None of these tests set binning_x/binning_y
on a mode, and none of the assertions below should ever require one.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.sensor_detect import SensorDetect


def _detector(aspect_ratios_cfg=None, min_mode_width=None, enabled_modes=None,
              bit_depths=None, k_steps=None, hdr_cfg=None):
    d = SensorDetect.__new__(SensorDetect)
    d.bit_depths = bit_depths if bit_depths is not None else []
    d.k_steps = k_steps if k_steps is not None else []
    d.custom_modes = {}
    d.hdr_modes = SensorDetect._hdr_whitelist(hdr_cfg or {})
    d.clear_hdr_depths = None
    d.enabled_modes = enabled_modes or {}
    if aspect_ratios_cfg is not None:
        d.aspect_ratios_cfg = aspect_ratios_cfg
    if min_mode_width is not None:
        d.min_mode_width = min_mode_width
    d.sensor_modes_unfiltered = {}
    return d


# ── imx585, aspect family: two well-separated shapes, real numbers from
# ASPECT-RATIOS.md's "imx585, all-pixel (1x1), active 3840x2160" table ──────
IMX585_16X9 = {"width": 3840, "height": 2160, "bit_depth": 12, "hdr": False,
               "fps_max": 50, "aspect": 1.78}
IMX585_239 = {"width": 3840, "height": 1608, "bit_depth": 12, "hdr": False,
              "fps_max": 67, "aspect": 2.39}


class UnionAcrossRatiosTests(unittest.TestCase):
    def test_enabling_only_239_offers_239_and_not_16x9(self):
        d = _detector(aspect_ratios_cfg={"imx585": ["2.39:1"]})
        pruned = d._finalize_modes({"imx585": [dict(IMX585_16X9), dict(IMX585_239)]})
        widths_heights = {(m["width"], m["height"]) for m in pruned["imx585"].values()}
        self.assertEqual(widths_heights, {(3840, 1608)})

    def test_the_default_offers_todays_modes_and_nothing_more(self):
        # "Today's modes" for imx585 (pre-aspect-family): both stock 16:9
        # detections, same numbers as test_clear_hdr_depth_switches.py's
        # fixture.
        today = [
            {"width": 1928, "height": 1090, "bit_depth": 12, "hdr": False, "fps_max": 87},
            {"width": 3856, "height": 2180, "bit_depth": 12, "hdr": False, "fps_max": 40},
        ]
        d = _detector(aspect_ratios_cfg={})  # no camera entry -> "default"
        pruned = d._finalize_modes({"imx585": [dict(m) for m in today]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx585"].values()}
        self.assertEqual(sizes, {(1928, 1090), (3856, 2180)})

    def test_matched_modes_carry_the_ratio_real_aspect_and_exactness(self):
        d = _detector(aspect_ratios_cfg={"imx585": ["2.39:1"]})
        pruned = d._finalize_modes({"imx585": [dict(IMX585_16X9), dict(IMX585_239)]})
        mode = next(iter(pruned["imx585"].values()))
        self.assertEqual(mode["aspect_ratio_id"], "2.39:1")
        self.assertTrue(mode["aspect_ratio_exact"])
        self.assertAlmostEqual(mode["aspect_ratio_real"], 2.39)


class WidthFloorTests(unittest.TestCase):
    NARROW = {"width": 640, "height": 360, "bit_depth": 12, "hdr": False,
              "fps_max": 100, "aspect": 1.78}
    WIDE = {"width": 3840, "height": 2160, "bit_depth": 12, "hdr": False,
            "fps_max": 50, "aspect": 1.78}

    def test_a_narrow_mode_is_hidden_by_the_default_floor(self):
        d = _detector(aspect_ratios_cfg={}, min_mode_width=1280)
        pruned = d._finalize_modes({"imx585": [dict(self.NARROW), dict(self.WIDE)]})
        widths = {m["width"] for m in pruned["imx585"].values()}
        self.assertNotIn(640, widths)
        self.assertIn(3840, widths)

    def test_the_narrow_mode_still_reaches_sensor_modes_unfiltered(self):
        d = _detector(aspect_ratios_cfg={}, min_mode_width=1280)
        d._finalize_modes({"imx585": [dict(self.NARROW), dict(self.WIDE)]})
        widths = {m["width"] for m in d.sensor_modes_unfiltered["imx585"]}
        self.assertIn(640, widths)

    def test_lowering_min_mode_width_reveals_it(self):
        d = _detector(aspect_ratios_cfg={}, min_mode_width=320)
        pruned = d._finalize_modes({"imx585": [dict(self.NARROW), dict(self.WIDE)]})
        widths = {m["width"] for m in pruned["imx585"].values()}
        self.assertIn(640, widths)

    def test_an_enabled_modes_entry_bypasses_the_floor_regardless(self):
        d = _detector(
            aspect_ratios_cfg={}, min_mode_width=1280,
            enabled_modes={"imx585": [
                {"width": 640, "height": 360, "bit_depth": 12, "hdr": False},
            ]},
        )
        pruned = d._finalize_modes({"imx585": [dict(self.NARROW), dict(self.WIDE)]})
        widths = {m["width"] for m in pruned["imx585"].values()}
        self.assertEqual(widths, {640})


# ── imx477, tier B: a stock driver, only two shapes it can ever produce ────
IMX477_MODES = [
    {"width": 2028, "height": 1524, "bit_depth": 12, "hdr": False, "fps_max": 40},  # aspect 1.33
    {"width": 2028, "height": 1080, "bit_depth": 12, "hdr": False, "fps_max": 50},  # aspect 1.878
]


class Tier5B_Imx477Tests(unittest.TestCase):
    def test_every_ratio_resolves_to_a_closest_mode_marked_approximate(self):
        d = _detector()
        d.sensor_modes_unfiltered = {"imx477": [dict(m) for m in IMX477_MODES]}
        avail = d.available_aspect_ratios("imx477")
        # Camera never left empty: all fourteen ratios resolve to something.
        self.assertEqual(len(avail), 14)
        # A ratio far from both shapes is approximate, and carries the real
        # aspect of whichever mode is closest.
        far = avail["2.55:1"]
        self.assertFalse(far["exact"])
        self.assertAlmostEqual(far["real_aspect"], 1.88, places=2)

    def test_a_ratio_the_sensor_actually_hits_is_exact(self):
        d = _detector()
        d.sensor_modes_unfiltered = {"imx477": [dict(m) for m in IMX477_MODES]}
        avail = d.available_aspect_ratios("imx477")
        self.assertTrue(avail["1.33:1"]["exact"])

    def test_enabling_133_offers_a_near_tie_when_nothing_is_exact(self):
        # Neither mode below is within tolerance of 1.33 (errors 0.03 and
        # 0.04), but they are within 0.02 of *each other's* error -- a
        # near-tie, and the matcher must offer both rather than pick one.
        near_tie = [
            {"width": 2000, "height": 1538, "bit_depth": 12, "hdr": False,
             "fps_max": 30},  # aspect 1.30, error 0.03
            {"width": 2000, "height": 1460, "bit_depth": 12, "hdr": False,
             "fps_max": 30},  # aspect 1.37, error 0.04
        ]
        d = _detector(aspect_ratios_cfg={"imx477": ["1.33:1"]})
        pruned = d._finalize_modes({"imx477": [dict(m) for m in near_tie]})
        heights = {m["height"] for m in pruned["imx477"].values()}
        self.assertEqual(heights, {1538, 1460})

    def test_the_camera_is_never_left_empty(self):
        d = _detector(aspect_ratios_cfg={"imx477": ["2.55:1"]})
        pruned = d._finalize_modes({"imx477": [dict(m) for m in IMX477_MODES]})
        self.assertTrue(len(pruned["imx477"]) >= 1)


class TierCTests(unittest.TestCase):
    def test_a_sizes_only_listing_still_produces_ratios(self):
        # No crop, no aspect field at all -- the width/height fallback in
        # _mode_aspect() must still let availability derive something.
        sizes_only = [
            {"width": 1920, "height": 1080, "bit_depth": 10, "hdr": False, "fps_max": 30},
        ]
        d = _detector()
        d.sensor_modes_unfiltered = {"imx519": [dict(m) for m in sizes_only]}
        avail = d.available_aspect_ratios("imx519")
        self.assertIn("1.78:1", avail)
        self.assertTrue(avail["1.78:1"]["exact"])


class BinningNeverInferredTests(unittest.TestCase):
    def test_a_windowed_mode_with_no_binning_annotation_stays_unknown(self):
        windowed = {
            "width": 1440, "height": 1080, "bit_depth": 12, "hdr": False,
            "fps_max": 60, "aspect": 1.33,
            # No binning_x/binning_y at all -- exactly the tier B case
            # ASPECT-RATIOS.md warns about (1440x1080 must not become a
            # binning of 6).
        }
        d = _detector(aspect_ratios_cfg={"imx585": ["1.33:1"]})
        pruned = d._finalize_modes({"imx585": [dict(windowed)]})
        mode = next(iter(pruned["imx585"].values()))
        self.assertIsNone(mode.get("binning_x"))
        self.assertIsNone(mode.get("binning_y"))


class SensorSwapScopingTests(unittest.TestCase):
    IMX585_SET = [dict(IMX585_16X9), dict(IMX585_239)]
    IMX283_SET = [
        {"width": 5472, "height": 3080, "bit_depth": 12, "hdr": False,
         "fps_max": 24, "aspect": 1.78},
        {"width": 5472, "height": 2288, "bit_depth": 12, "hdr": False,
         "fps_max": 30, "aspect": 2.39},
    ]

    def test_a_per_camera_entry_does_not_affect_the_other_camera(self):
        d = _detector(aspect_ratios_cfg={"imx585": ["2.39:1"], "default": ["1.78:1"]})
        pruned = d._finalize_modes({
            "imx585": [dict(m) for m in self.IMX585_SET],
            "imx283": [dict(m) for m in self.IMX283_SET],
        })
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx585"].values()},
            {(3840, 1608)},
        )
        # imx283 has no entry of its own -> falls back to "default" (1.78:1).
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx283"].values()},
            {(5472, 3080)},
        )

    def test_enabled_modes_scoping_is_independent_of_aspect_ratios_scoping(self):
        d = _detector(
            aspect_ratios_cfg={"imx585": ["2.39:1"]},
            enabled_modes={"imx283": [
                {"width": 5472, "height": 2288, "bit_depth": 12, "hdr": False},
            ]},
        )
        pruned = d._finalize_modes({
            "imx585": [dict(m) for m in self.IMX585_SET],
            "imx283": [dict(m) for m in self.IMX283_SET],
        })
        # imx585 goes through the aspect matcher (no enabled_modes entry).
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx585"].values()},
            {(3840, 1608)},
        )
        # imx283's enabled_modes entry is authoritative, independent of the
        # imx585-only aspect_ratios entry above.
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx283"].values()},
            {(5472, 2288)},
        )


if __name__ == "__main__":
    unittest.main()
