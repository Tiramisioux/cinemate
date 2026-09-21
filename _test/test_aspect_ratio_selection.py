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

from module.aspect_ratios import FULL_FRAME_RATIO_ID
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
    # CM-2: the 4:3 mode is here so the two tests below still differ from each
    # other. The shipped default is 1.33:1 and 1.78:1 where the camera has
    # them, so without it this camera would resolve to 1.78:1 either way and
    # "derived" would be indistinguishable from an explicit "default":
    # ["1.78:1"] -- which is the very thing this class exists to tell apart.
    IMX283_SET = [
        {"width": 5472, "height": 4104, "bit_depth": 12, "hdr": False,
         "fps_max": 20, "aspect": 1.33},
        {"width": 5472, "height": 3080, "bit_depth": 12, "hdr": False,
         "fps_max": 24, "aspect": 1.78},
        {"width": 5472, "height": 2288, "bit_depth": 12, "hdr": False,
         "fps_max": 30, "aspect": 2.39},
    ]

    def test_a_per_camera_entry_does_not_affect_the_other_camera(self):
        # WP-CM-11: an explicit "default" entry is a deliberate global choice
        # regardless of which ids it names -- there is no more "is this
        # value the shipped one" special case (the shipped value is now {},
        # not ["1.78:1"]; see _enabled_ratio_ids's precedence). So a present
        # "default": ["1.78:1"] genuinely narrows every camera with no
        # per-camera entry of its own, same as any other explicit choice.
        d = _detector(aspect_ratios_cfg={"imx585": ["2.39:1"], "default": ["1.78:1"]})
        pruned = d._finalize_modes({
            "imx585": [dict(m) for m in self.IMX585_SET],
            "imx283": [dict(m) for m in self.IMX283_SET],
        })
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx585"].values()},
            {(3840, 1608)},
        )
        # imx283 has no entry of its own, so it falls to the explicit
        # "default" -- 1.78:1 only -- and narrows to its one exactly-1.78
        # mode, unaffected by imx585's own separate, unrelated entry.
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx283"].values()},
            {(5472, 3080)},
        )

    def test_no_default_entry_at_all_falls_to_the_derived_set_per_camera(self):
        # The case the old exemption used to cover by comparing the
        # resolved list to a hardcoded default: no "default" key present at
        # all, and no per-camera entry either. Each camera resolves through
        # its OWN modes (_default_ratio_ids over _derived_default_ratio_ids),
        # not a shared hardcoded ratio.
        #
        # CM-2: that step is the shipped 1.33:1/1.78:1 pair now, so imx283
        # keeps both of the shapes it has for them -- including the 4:3 mode an
        # explicit "default": ["1.78:1"] takes away (the test above) -- and its
        # 2.39 mode starts hidden, one toggle away in the settings page. What
        # this test guards is unchanged: imx585's per-camera entry does not
        # reach imx283, and imx283's answer comes from imx283's modes.
        d = _detector(aspect_ratios_cfg={"imx585": ["2.39:1"]})
        pruned = d._finalize_modes({
            "imx585": [dict(m) for m in self.IMX585_SET],
            "imx283": [dict(m) for m in self.IMX283_SET],
        })
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx585"].values()},
            {(3840, 1608)},
        )
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx283"].values()},
            {(5472, 4104), (5472, 3080)},
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


class ConfigLoaderDefaultRegressionTests(unittest.TestCase):
    """WP-CM-6 rework: the aspect_ratios_cfg/min_mode_width a real
    config_loader.py hands a real settings.jsonc that predates this
    package -- not a hand-picked None/{} in a test fixture -- must not
    narrow a stock, mixed-aspect sensor's mode table.

    Tier5B_Imx477Tests above proves the matcher behaves sanely once it is
    *asked* to run: available_aspect_ratios() (informational), or an
    explicit non-default selection like {"imx477": ["1.33:1"]}. Neither of
    those proves the matcher stays off for the case WORK-PACKAGES.md's
    WP-CM-6 promises unchanged behaviour for -- "a settings file with no
    aspect_ratios must behave exactly as it does today" -- because a
    hand-set aspect_ratios_cfg={} already IS an operator opinion (an
    explicit, if empty, key) that this test file's other classes correctly
    resolve to the "default" ratio and never exercise the truly-absent-key
    path through the real defaulting code.

    Real numbers from resources/sensors.json's imx477 entry: a 16:9-ish
    ratio (1.87), the sensor's full-FOV 4:3 readout (1.33), and its high-fps
    crop (1.34) -- none of which are both within ASPECT_RATIO_TOLERANCE of
    1.78, so a wrongly-engaged matcher collapses all three down to the one
    closest to 1.78 instead of leaving today's bit_depths/k_steps-only
    result alone.
    """

    IMX477_STOCK_MODES = [
        {"width": 2028, "height": 1080, "bit_depth": 12, "hdr": False,
         "fps_max": 50, "aspect": 1.87},
        {"width": 2028, "height": 1520, "bit_depth": 12, "hdr": False,
         "fps_max": 40, "aspect": 1.33},
        {"width": 1332, "height": 990, "bit_depth": 10, "hdr": False,
         "fps_max": 120, "aspect": 1.34},
    ]

    def test_default_cfg_from_config_loader_keeps_every_stock_imx477_mode(self):
        from module.config_loader import _apply_settings_defaults  # noqa: PLC0415

        # A settings.jsonc written before WP-CM-6 landed -- no image_capture
        # section at all, let alone aspect_ratios/min_mode_width. This is
        # every settings.jsonc deployed before this package, since both
        # keys are brand new.
        legacy_settings = _apply_settings_defaults({})
        image_capture_cfg = legacy_settings["image_capture"]
        self.assertNotIn("aspect_ratios", image_capture_cfg)
        self.assertNotIn("min_mode_width", image_capture_cfg)

        d = _detector(
            aspect_ratios_cfg=image_capture_cfg.get("aspect_ratios"),
            min_mode_width=image_capture_cfg.get("min_mode_width"),
            bit_depths=image_capture_cfg.get("bit_depths"),
            k_steps=image_capture_cfg.get("k_steps"),
        )
        pruned = d._finalize_modes(
            {"imx477": [dict(m) for m in self.IMX477_STOCK_MODES]}
        )
        sizes = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertEqual(
            sizes,
            {(m["width"], m["height"]) for m in self.IMX477_STOCK_MODES},
        )


class ShippedDefaultFreshInstallRegressionTests(unittest.TestCase):
    """WP-CM-6 rework, second blocking finding: ConfigLoaderDefaultRegressionTests
    above only proves the *legacy* path (a settings.jsonc written before
    WP-CM-6, where the key is truly absent and aspect_ratios_cfg ends up
    None). It never runs the *literal shipped default* through the matcher
    -- and a present key (WP-CM-11: ships as {}, an empty dict, so each
    camera derives its own default from its own modes -- see
    DerivedDefaultRatioSetTests above) is present on every fresh install,
    because resources/settings/settings_default.jsonc and settings.jsonc
    both ship it (WP-CM-6 item 1). A present key means aspect_ratios_cfg is
    not None, so the ratio matcher in _finalize_modes actively runs on a
    fresh install too.

    For imx477 (tier B), none of its five stock modes is within
    ASPECT_RATIO_TOLERANCE of 1.78 (closest is the 2028x1080 mode at 1.87).
    Before WP-CM-6's original fix this silently dropped the 4:3 2028x1520
    mode and the sensor's fastest mode, 1332x990@120fps; before WP-CM-11
    replaced the hardcoded "1.78:1"-plus-exemption mechanism that fix used,
    those modes were only kept by an exemption that had to
    recognise "nobody chose anything" as a special case. WP-CM-11 made
    this structural instead: the default is built from the camera's own modes.

    CM-2 (operator instruction, 2026-09-21: default to 1.33:1 and 1.78:1 "if
    present") narrows that step, so what this class guards is no longer "every
    stock mode survives". imx477 has no 16:9 mode at all, so the pair it can
    offer is 1.33:1 alone -- the sensor's full-FOV 4:3 readout, its 2028x1520
    half-res readout and its 120fps 1332x990 crop, the three modes the original
    finding was about -- and its two 1.89-ish modes start hidden. The property
    that has to hold is the one the exemption used to provide: a fresh install
    never lands on a ratio this sensor does not have, and never on an empty
    table. _default_ratio_ids checks the pair against the camera's own modes
    before selecting it; see its docstring and WORK-PACKAGES.md's WP-CM-11.

    This test loads the real image_capture.aspect_ratios default the
    repo actually ships in BOTH settings.jsonc and
    resources/settings/settings_default.jsonc (via the real
    config_loader.load_settings(), not a hand-picked fixture) and the real
    imx477 entry from resources/sensors.json (via the real
    sensor_database.load_sensor_database()), and runs both through
    _finalize_modes() exactly as SensorDetect would on a fresh install.
    """

    @staticmethod
    def _imx477_modes_from_database():
        from module.sensor_database import load_sensor_database  # noqa: PLC0415

        db = load_sensor_database(str(ROOT / "resources" / "sensors.json"))
        raw_modes = db["sensors"]["imx477"]["modes"]
        # Shape matches what SensorDetect's own probe/parsing attaches to a
        # runtime mode dict (width/height/bit_depth/aspect/fps_max/hdr) --
        # see _mode_from_metadata_or_detected. hdr is always False here:
        # imx477 has no ClearHDR modes in the database.
        return [
            {
                "width": m["width"],
                "height": m["height"],
                "bit_depth": m["bit_depth"],
                "aspect": m["aspect"],
                "fps_max": m["max_fps"],
                "hdr": False,
            }
            for m in raw_modes
        ]

    # WP-CM-12: resources/sensors.json's imx477 entry grew two modes (the
    # driver's 4056x3040 full readout and its 4056x2160 16:9 crop, both
    # missing before), so the fresh-install survivor set is five sizes now,
    # not three.
    ALL_STOCK_IMX477_SIZES = {
        (2028, 1080), (2028, 1520), (1332, 990), (4056, 3040), (4056, 2160),
    }

    # CM-2: of those five, the ones the shipped 1.33:1/1.78:1 default selects.
    # imx477 has nothing at 1.78, so this is its 1.33 family: the two 4:3
    # readouts and the 1332x990 crop (aspect 1.35, home ratio 1.33:1).
    DEFAULT_SELECTED_IMX477_SIZES = {(2028, 1520), (1332, 990), (4056, 3040)}

    def _assert_the_default_selects_the_133_family(self, image_capture_cfg, source_label):
        modes = self._imx477_modes_from_database()
        self.assertEqual(
            {(m["width"], m["height"]) for m in modes},
            self.ALL_STOCK_IMX477_SIZES,
            f"resources/sensors.json's imx477 entry changed shape -- update "
            f"this test's expectations ({source_label})",
        )
        d = _detector(
            aspect_ratios_cfg=image_capture_cfg.get("aspect_ratios"),
            min_mode_width=image_capture_cfg.get("min_mode_width"),
            bit_depths=image_capture_cfg.get("bit_depths"),
            k_steps=image_capture_cfg.get("k_steps"),
        )
        pruned = d._finalize_modes({"imx477": [dict(m) for m in modes]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertEqual(
            sizes,
            self.DEFAULT_SELECTED_IMX477_SIZES,
            f"{source_label}: the fresh-install default is 1.33:1 on this "
            f"sensor (no 16:9 mode exists), so its 4:3 readouts and the "
            f"1332x990@120fps crop must all be selected",
        )
        self.assertEqual(
            {(m["width"], m["height"]) for m in d.sensor_modes_unfiltered["imx477"]},
            self.ALL_STOCK_IMX477_SIZES,
            f"{source_label}: the 1.89 modes are unselected, not lost -- the "
            f"settings page offers them from the unfiltered table",
        )
        self.assertEqual(
            set(d._enabled_ratio_ids("imx477")), {"1.33:1"},
            f"{source_label}: 1.78:1 must not be selected on a sensor with no "
            f"mode that comes home to it",
        )

    def test_shipped_settings_jsonc_default_selects_the_imx477_133_family(self):
        from module.config_loader import load_settings  # noqa: PLC0415

        settings = load_settings(ROOT / "settings.jsonc")
        image_capture_cfg = settings["image_capture"]
        # The literal shipped default this finding is about -- a *present*
        # key (WP-CM-11: an empty dict, not the old hardcoded "1.78:1"), not
        # the legacy absent-key case.
        self.assertEqual(image_capture_cfg.get("aspect_ratios"), {})
        self._assert_the_default_selects_the_133_family(
            image_capture_cfg, "settings.jsonc",
        )

    def test_shipped_settings_default_jsonc_selects_the_imx477_133_family(self):
        from module.config_loader import load_settings  # noqa: PLC0415

        # The fresh-install template: a brand-new settings.jsonc is this
        # file's content verbatim (WP-CM-6 item 1's own justification for
        # not setdefault'ing the keys in _apply_settings_defaults).
        settings = load_settings(ROOT / "resources" / "settings" / "settings_default.jsonc")
        image_capture_cfg = settings["image_capture"]
        self.assertEqual(image_capture_cfg.get("aspect_ratios"), {})
        self._assert_the_default_selects_the_133_family(
            image_capture_cfg, "settings_default.jsonc",
        )


class ShippedDefaultPartialMatchRegressionTests(unittest.TestCase):
    """WP-CM-7 rework, blocking review finding: ShippedDefaultFreshInstallRegressionTests
    above only proves the all-or-nothing case (imx477: *no* mode is within
    ASPECT_RATIO_TOLERANCE of 1.78:1). It never exercises the more common
    partial-match case, where *some* of a camera's stock modes are within
    tolerance of a given ratio and others are not.

    imx283 (tier B/C) is exactly this case with real numbers from
    resources/sensors.json: three modes are ~1.78 and two are 1.5. Before
    the WP-CM-7 fix, the 1.5-aspect 2784x1828 12-bit mode vanished from the
    default-selected table on a fresh install even though it passes every
    pre-existing bit_depths/k_steps filter -- contradicting
    ASPECT-RATIOS.md's "1.78:1 when nothing has been chosen, so a fresh
    camera behaves as it does today" (the shipped default at the time).

    WP-CM-11 replaced that single hardcoded default with one derived per
    camera from its own modes -- ships as {}, not {"default": ["1.78:1"]}.

    CM-2 (operator instruction, 2026-09-21) narrows that step to 1.33:1 and
    1.78:1 where the camera has them, so the 1.5-aspect 2784x1828 mode is
    hidden by default again -- deliberately this time, and by a rule that is
    the same on every sensor, rather than by a hardcoded ratio that happened
    to miss this sensor's whole family. What this class still guards is the
    partial-match shape itself: with only *some* of a camera's modes near an
    enabled ratio, the selection must be exactly the modes that ratio claims
    (here imx283's ~1.8 family, since the metadata table has no 4:3 mode) and
    the rest must remain offered by the settings page, not dropped from the
    unfiltered table. See DerivedDefaultRatioSetTests below for the general
    case and the "neither ratio present" fallback.

    This mirrors ShippedDefaultFreshInstallRegressionTests's own method:
    the real shipped image_capture.aspect_ratios default (via config_loader
    .load_settings()) and the real per-camera mode table (via
    sensor_database.load_sensor_database()), run through the real
    _finalize_modes() exactly as SensorDetect would on a fresh install.
    """

    @staticmethod
    def _modes_from_database(camera_name):
        from module.sensor_database import load_sensor_database  # noqa: PLC0415

        db = load_sensor_database(str(ROOT / "resources" / "sensors.json"))
        raw_modes = db["sensors"][camera_name]["modes"]
        return [
            {
                "width": m["width"],
                "height": m["height"],
                "bit_depth": m["bit_depth"],
                "aspect": m["aspect"],
                "fps_max": m["max_fps"],
                "hdr": False,
            }
            for m in raw_modes
        ]

    def _assert_the_default_selects(self, camera_name, expected_sizes,
                                    image_capture_cfg, source_label):
        modes = self._modes_from_database(camera_name)
        d = _detector(
            aspect_ratios_cfg=image_capture_cfg.get("aspect_ratios"),
            min_mode_width=image_capture_cfg.get("min_mode_width"),
            bit_depths=image_capture_cfg.get("bit_depths"),
            k_steps=image_capture_cfg.get("k_steps"),
        )
        pruned = d._finalize_modes({camera_name: [dict(m) for m in modes]})
        sizes = {
            (m["width"], m["height"], m["bit_depth"])
            for m in pruned[camera_name].values()
        }
        self.assertEqual(
            sizes, expected_sizes,
            f"{source_label}/{camera_name}: the fresh-install ratio selection "
            f"is not the set of modes the shipped default's ratios claim",
        )
        self.assertTrue(
            sizes.issubset({
                (m["width"], m["height"], m["bit_depth"])
                for m in d.sensor_modes_unfiltered[camera_name]
            }),
            f"{source_label}/{camera_name}: every selected mode has to come "
            f"from the unfiltered table",
        )
        self.assertTrue(
            sizes, f"{source_label}/{camera_name}: the default left the camera empty",
        )

    def test_shipped_default_selects_the_imx283_16x9_family(self):
        from module.config_loader import load_settings  # noqa: PLC0415

        # Real numbers from resources/sensors.json's imx283 entry, narrowed
        # by today's bit_depths=[10,12,16]/k_steps=[1.5,2,3,4] and then by the
        # shipped default. That entry's modes are ~1.5 (home ratio 1.37:1) or
        # ~1.8 (home ratio 1.78:1) and it has nothing at 4:3, so the default
        # resolves to 1.78:1 alone and the 1.5-aspect 2784x1828 12-bit mode is
        # hidden until the operator ticks 1.37:1 in the settings page. The
        # driver actually shipped for this sensor reports a full 14-ratio crop
        # family, where the same rule selects 1.33:1 and 1.78:1 -- this fixture
        # is the metadata table, which is deliberately a different, smaller
        # shape (see DerivedDefaultRatioSetTests' own note).
        expected = {(2784, 1542, 12), (3936, 2176, 10)}
        for settings_path, label in (
            (ROOT / "settings.jsonc", "settings.jsonc"),
            (ROOT / "resources" / "settings" / "settings_default.jsonc", "settings_default.jsonc"),
        ):
            settings = load_settings(settings_path)
            image_capture_cfg = settings["image_capture"]
            # WP-CM-11: ships as {}, an empty dict -- not the old hardcoded
            # {"default": ["1.78:1"]}. A present, empty key still runs the
            # ratio matcher (aspect_ratios_cfg is not None), but with no
            # per-camera or "default" entry it falls to imx283's own modes
            # (_default_ratio_ids), never a single global ratio.
            self.assertEqual(image_capture_cfg.get("aspect_ratios"), {})
            self._assert_the_default_selects(
                "imx283", expected, image_capture_cfg, label,
            )

    def test_shipped_default_keeps_the_stock_imx296_mode(self):
        from module.config_loader import load_settings  # noqa: PLC0415

        # imx296's only stock mode (1456x1088, aspect 1.33) -- the
        # all-or-nothing case, kept here as a stock-sensor sanity check
        # alongside imx283's partial-match case.
        expected = {(1456, 1088, 10)}
        settings = load_settings(ROOT / "settings.jsonc")
        image_capture_cfg = settings["image_capture"]
        self.assertEqual(image_capture_cfg.get("aspect_ratios"), {})
        self._assert_the_default_selects(
            "imx296", expected, image_capture_cfg, "settings.jsonc",
        )


class ShippedDefaultAcrossANativelyDifferentSensorTests(unittest.TestCase):
    """The imx477 case above is a sensor whose closest mode is 1.87, a tenth away
    from 16:9. This is the harder shape the reviewer asked for: a sensor whose
    ENTIRE family sits at a materially different native aspect.

    Every imx283 mode is about 1.5 or about 1.8, and the 5568x3664 and 2784x1828
    modes are 1.52 -- a quarter away from 1.78, and further from it than any
    imx477 mode. WP-CM-11 removed the hardcoded single-ratio shipped default
    this class's name refers to, precisely because a *hardcoded* default
    narrowing to "the closest mode to one fixed ratio" would make a
    OneInchEye owner lose most of the sensor's table on a fresh install,
    having chosen nothing.

    CM-2 gives the default two preferred ratios again, but checked against the
    camera before they are applied, so what this class asserts is the surviving
    half of that property: whatever the preferred pair is, a sensor is never
    left selecting a ratio it does not have, and a sensor that has *neither*
    preferred ratio keeps its whole table (_default_ratio_ids' fallback --
    which is this class's original guarantee, now scoped to the case where it
    is the only safe answer). imx283's metadata table does have ~1.8 modes, so
    it resolves to 1.78:1 and its 1.5 family starts hidden; the all-1.5 fixture
    below is the sensor shape that has nothing either preferred ratio can
    claim, and it keeps everything.
    """

    @staticmethod
    def _imx283_modes_from_database():
        from module.sensor_database import load_sensor_database  # noqa: PLC0415

        db = load_sensor_database(str(ROOT / "resources" / "sensors.json"))
        return [
            {
                "width": m["width"],
                "height": m["height"],
                "bit_depth": m["bit_depth"],
                "aspect": m["aspect"],
                "fps_max": m.get("max_fps"),
                "hdr": False,
            }
            for m in db["sensors"]["imx283"]["modes"]
        ]

    # A sensor with nothing at 4:3 and nothing at 16:9: aspect 1.5 throughout,
    # which is what the imx283's own native readout actually is (5472x3648 =
    # 1.50, and 1.50 is not one of the fourteen canonical ratios). Both
    # preferred ratios are absent, so the default has to fall back.
    ALL_1_5_MODES = [
        {"width": 5472, "height": 3648, "bit_depth": 12, "hdr": False,
         "fps_max": 21, "aspect": 1.5},
        {"width": 2736, "height": 1824, "bit_depth": 12, "hdr": False,
         "fps_max": 51, "aspect": 1.5},
    ]

    def _assert_the_default_selects(self, settings_path, label, expected):
        from module.config_loader import load_settings  # noqa: PLC0415

        image_capture_cfg = load_settings(settings_path)["image_capture"]
        # WP-CM-11: ships as {}, not the old hardcoded {"default": ["1.78:1"]}.
        self.assertEqual(image_capture_cfg.get("aspect_ratios"), {})

        modes = self._imx283_modes_from_database()
        self.assertGreaterEqual(
            len(modes), 6,
            "resources/sensors.json's imx283 entry changed shape -- update this test",
        )

        d = _detector(
            aspect_ratios_cfg=image_capture_cfg.get("aspect_ratios"),
            min_mode_width=image_capture_cfg.get("min_mode_width"),
            # Deliberately NOT passing bit_depths/k_steps: this test is about the
            # ratio matcher alone. Those two filters are the operator's own and
            # are tested elsewhere; mixing them in here would hide which filter
            # dropped a mode.
        )
        pruned = d._finalize_modes({"imx283": [dict(m) for m in modes]})
        after = {(m["width"], m["height"], m["bit_depth"]) for m in pruned["imx283"].values()}
        self.assertEqual(
            after, expected,
            f"{label}: the shipped default selected something other than this "
            f"sensor's 16:9 family. It has no 4:3 mode, so 1.33:1 must not be "
            f"selected, and the selection must not be empty either.",
        )
        self.assertEqual(set(d._enabled_ratio_ids("imx283")), {"1.78:1"})

    def test_shipped_settings_jsonc_selects_the_imx283_16x9_family(self):
        self._assert_the_default_selects(
            ROOT / "settings.jsonc", "settings.jsonc",
            {(2784, 1542, 12), (5568, 3094, 10), (3936, 2176, 10)},
        )

    def test_shipped_settings_default_jsonc_selects_the_imx283_16x9_family(self):
        self._assert_the_default_selects(
            ROOT / "resources" / "settings" / "settings_default.jsonc",
            "settings_default.jsonc",
            {(2784, 1542, 12), (5568, 3094, 10), (3936, 2176, 10)},
        )

    def test_a_sensor_with_neither_preferred_ratio_keeps_its_whole_table(self):
        """The fallback, and the reason it exists: a 3:2 sensor's own native
        shape is not a canonical ratio at all, so neither 1.33:1 nor 1.78:1 is
        present and narrowing to them would leave nothing selected. The whole
        derived set is then the only honest answer."""
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx283": [dict(m) for m in self.ALL_1_5_MODES]})
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx283"].values()},
            {(m["width"], m["height"]) for m in self.ALL_1_5_MODES},
        )
        self.assertEqual(d._enabled_ratio_ids("imx283"), ["1.37:1"])


# ── WP-CM-11: the default ratio set is the one the sensor actually has ────
# Real numbers, not resources/sensors.json -- WP-CM-12 records that file as
# missing two of the imx477's five real modes, and the runtime table this
# package's rule has to hold for comes from the probe, not the metadata
# file. Numbers are WORK-PACKAGES.md's own WP-CM-11 table, read from the
# mainline imx477/imx296 drivers.
IMX477_FIVE_MODES = [
    {"width": 4056, "height": 3040, "bit_depth": 12, "hdr": False, "fps_max": 10},
    {"width": 4056, "height": 2160, "bit_depth": 12, "hdr": False, "fps_max": 20},
    {"width": 2028, "height": 1520, "bit_depth": 12, "hdr": False, "fps_max": 40},
    {"width": 2028, "height": 1080, "bit_depth": 12, "hdr": False, "fps_max": 50},
    {"width": 1332, "height": 990, "bit_depth": 10, "hdr": False, "fps_max": 120},
]

IMX296_ONE_MODE = [
    {"width": 1456, "height": 1088, "bit_depth": 10, "hdr": False, "fps_max": 60},
]

# imx283's real 6 modes (resources/sensors.json): three at aspect 1.78,
# three at 1.5 -- already used above by the ShippedDefault* regression
# classes.
IMX283_SIX_MODES = [
    {"width": 5568, "height": 3664, "bit_depth": 12, "hdr": False, "fps_max": 18, "aspect": 1.5},
    {"width": 2784, "height": 1828, "bit_depth": 12, "hdr": False, "fps_max": 36, "aspect": 1.5},
    {"width": 2784, "height": 1542, "bit_depth": 12, "hdr": False, "fps_max": 41, "aspect": 1.78},
    {"width": 5568, "height": 3664, "bit_depth": 10, "hdr": False, "fps_max": 18, "aspect": 1.5},
    {"width": 5568, "height": 3094, "bit_depth": 10, "hdr": False, "fps_max": 21, "aspect": 1.78},
    {"width": 3936, "height": 2176, "bit_depth": 10, "hdr": False, "fps_max": 44, "aspect": 1.78},
]

# imx585, all-pixel (1x1) aspect family: active WxH and "achieved" aspect
# for all fourteen ratios, from ASPECT-RATIOS.md's "imx585, all-pixel (1x1),
# active 3840x2160" table -- read verbatim, not recomputed.
IMX585_ASPECT_FAMILY = [
    {"width": 2160, "height": 2160, "bit_depth": 12, "hdr": False, "fps_max": 50, "aspect": 1.000},
    {"width": 2880, "height": 2160, "bit_depth": 12, "hdr": False, "fps_max": 50, "aspect": 1.333},
    {"width": 2976, "height": 2160, "bit_depth": 12, "hdr": False, "fps_max": 50, "aspect": 1.378},
    {"width": 3840, "height": 2160, "bit_depth": 12, "hdr": False, "fps_max": 50, "aspect": 1.778},
    {"width": 3840, "height": 2072, "bit_depth": 12, "hdr": False, "fps_max": 52, "aspect": 1.853},
    {"width": 3840, "height": 2032, "bit_depth": 12, "hdr": False, "fps_max": 53, "aspect": 1.890},
    {"width": 3840, "height": 2024, "bit_depth": 12, "hdr": False, "fps_max": 53, "aspect": 1.897},
    {"width": 3840, "height": 1920, "bit_depth": 12, "hdr": False, "fps_max": 56, "aspect": 2.000},
    {"width": 3840, "height": 1744, "bit_depth": 12, "hdr": False, "fps_max": 62, "aspect": 2.202},
    {"width": 3840, "height": 1728, "bit_depth": 12, "hdr": False, "fps_max": 62, "aspect": 2.222},
    {"width": 3840, "height": 1632, "bit_depth": 12, "hdr": False, "fps_max": 66, "aspect": 2.353},
    {"width": 3840, "height": 1608, "bit_depth": 12, "hdr": False, "fps_max": 67, "aspect": 2.388},
    {"width": 3840, "height": 1536, "bit_depth": 12, "hdr": False, "fps_max": 70, "aspect": 2.500},
    {"width": 3840, "height": 1504, "bit_depth": 12, "hdr": False, "fps_max": 71, "aspect": 2.553},
]

ALL_FOURTEEN_RATIO_IDS = {
    "1:1", "1.33:1", "1.37:1", "1.78:1", "1.85:1", "1.89:1", "1.90:1",
    "2.00:1", "2.20:1", "2.22:1", "2.35:1", "2.39:1", "2.50:1", "2.55:1",
}


class DerivedDefaultRatioSetTests(unittest.TestCase):
    """WP-CM-11: a camera with no explicit selection resolves through the
    ratios its own modes map to, derived at startup, never stored -- not the
    old hardcoded single ratio ("1.78:1") and not the "a default nobody chose
    is not a filter" exemption that used to widen it (WORK-PACKAGES.md's own
    table).

    CM-2 (operator instruction, 2026-09-21: "make default selected aspect
    ratios for a new sensor the standard 1.33:1, 1.78:1 (if present)") adds the
    step this class now covers in all three of its shapes: both preferred
    ratios present, one present, neither present. The derived set is still what
    "present" is measured against, and still the fallback when neither is --
    see _default_ratio_ids.

    _derived_default_ratio_ids itself is unchanged and still covers every mode
    by construction; the tests below that name it assert that directly, so its
    guarantee stays under test independently of what the default does with it.
    """

    def test_imx477_default_selects_its_133_family_only(self):
        # One preferred ratio present. imx477 has no 16:9 mode (its widest is
        # 1.88, home ratio 1.89:1), so 1.33:1 is selected alone and the two
        # 1.88 modes start hidden.
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx477": [dict(m) for m in IMX477_FIVE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertEqual(sizes, {(4056, 3040), (2028, 1520), (1332, 990)})

    def test_imx477_derived_set_is_still_133_and_189(self):
        # The derived set -- what "if present" is checked against, and the
        # fallback -- is every ratio the camera's modes come home to.
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"imx477": [dict(m) for m in IMX477_FIVE_MODES]}
        self.assertEqual(
            set(d._derived_default_ratio_ids("imx477")), {"1.33:1", "1.89:1"},
        )
        self.assertEqual(set(d._enabled_ratio_ids("imx477")), {"1.33:1"})

    def test_imx296_single_mode_survives_with_no_config(self):
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx296": [dict(m) for m in IMX296_ONE_MODE]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx296"].values()}
        self.assertEqual(sizes, {(1456, 1088)})

    def test_imx296_derived_default_is_133_only(self):
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"imx296": [dict(m) for m in IMX296_ONE_MODE]}
        self.assertEqual(set(d._enabled_ratio_ids("imx296")), {"1.33:1"})

    def test_imx585_aspect_family_default_selects_4x3_and_16x9(self):
        # Both preferred ratios present: the aspect-family driver offers all
        # fourteen shapes, so the default picks exactly the 4:3 and 16:9 ones
        # and the other twelve families start hidden. This is the biggest
        # difference CM-2 makes to what an operator sees on the dial.
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx585": [dict(m) for m in IMX585_ASPECT_FAMILY]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx585"].values()}
        self.assertEqual(sizes, {(2880, 2160), (3840, 2160)})

    def test_imx585_derived_set_is_still_all_fourteen_ratios(self):
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"imx585": [dict(m) for m in IMX585_ASPECT_FAMILY]}
        self.assertEqual(
            set(d._derived_default_ratio_ids("imx585")), ALL_FOURTEEN_RATIO_IDS,
        )
        self.assertEqual(
            d._enabled_ratio_ids("imx585"), ["1.33:1", "1.78:1"],
            "the preferred pair, in ratio-table order",
        )

    def test_imx283_default_selects_its_16x9_family(self):
        # Neither-nor is covered by
        # ShippedDefaultAcrossANativelyDifferentSensorTests' all-1.5 fixture;
        # this metadata table has ~1.8 modes but no 4:3 one, so 1.78:1 alone is
        # selected and the three 1.5-aspect modes (home ratio 1.37:1) are
        # hidden -- including both full-resolution 5568x3664 readouts.
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx283": [dict(m) for m in IMX283_SIX_MODES]})
        sizes = {
            (m["width"], m["height"], m["bit_depth"]) for m in pruned["imx283"].values()
        }
        self.assertEqual(
            sizes, {(2784, 1542, 12), (5568, 3094, 10), (3936, 2176, 10)},
        )

    def test_explicit_per_camera_selection_still_narrows(self):
        d = _detector(aspect_ratios_cfg={"imx477": ["1.89:1"]})
        pruned = d._finalize_modes({"imx477": [dict(m) for m in IMX477_FIVE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertEqual(sizes, {(4056, 2160), (2028, 1080)})

    def test_explicit_global_default_still_narrows(self):
        d = _detector(aspect_ratios_cfg={"default": ["1.89:1"]})
        pruned = d._finalize_modes({"imx477": [dict(m) for m in IMX477_FIVE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertEqual(sizes, {(4056, 2160), (2028, 1080)})

    def test_a_mode_whose_nearest_ratio_is_approximate_is_still_covered(self):
        # imx283's 1.5-aspect modes: nearest canonical is 1.37:1 (err 0.13),
        # squarely outside ASPECT_RATIO_TOLERANCE (0.02) -- an approximate
        # match, not a near-exact one like imx477's 1.878 ~= 1.89.
        far_mode = {"width": 2784, "height": 1828, "bit_depth": 12, "hdr": False,
                    "fps_max": 36, "aspect": 1.5}
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"imx283": [dict(far_mode)]}
        self.assertEqual(d._enabled_ratio_ids("imx283"), ["1.37:1"])
        pruned = d._finalize_modes({"imx283": [dict(far_mode)]})
        self.assertEqual(len(pruned["imx283"]), 1)


class LegacyShippedDefaultMigrationTests(unittest.TestCase):
    """WP-CM-11 rework, blocking review finding: every settings.jsonc a
    WP-CM-6/7 install actually wrote to disk carries
    image_capture.aspect_ratios == {"default": ["1.78:1"]} -- the literal
    pre-WP-CM-11 shipped value (`git show <this package's parent
    commit>:settings.jsonc`), not the {} this package ships from here on.
    ShippedDefaultFreshInstallRegressionTests/ShippedDefaultPartialMatchRegressionTests
    above only ever load the NEW shipped {} via config_loader.load_settings()
    on the checked-in settings.jsonc; neither exercises this pre-existing
    on-disk shape, which is what every worktree or Pi test rig that has not
    been reformatted since WP-CM-6/7 actually has.

    WP-CM-11 deletes the exemption (_ratio_selection_is_a_choice) that used
    to recognise this exact value as "nobody chose this" and skip the
    matcher for it -- an explicit "default" entry is now unconditionally a
    choice, on the premise that there is no longer a single shipped value to
    compare against. There still is one, on disk, until config_loader.py
    migrates it: this class constructs exactly that pre-existing shape (not
    the new {} shipped value) and proves _apply_settings_defaults() clears
    it back to "no opinion" before SensorDetect ever sees it, so imx477 and
    imx283 keep every stock mode through _finalize_modes() exactly as a
    fresh WP-CM-11 install does.
    """

    @staticmethod
    def _legacy_on_disk_settings():
        # A fresh dict per call -- _apply_settings_defaults may mutate its
        # image_capture sub-dict in place, and this exact value must not
        # leak mutated state between tests.
        return {"image_capture": {"aspect_ratios": {"default": ["1.78:1"]}}}

    def test_apply_settings_defaults_clears_the_legacy_shipped_value(self):
        from module.config_loader import _apply_settings_defaults  # noqa: PLC0415

        out = _apply_settings_defaults(self._legacy_on_disk_settings())
        self.assertEqual(out["image_capture"]["aspect_ratios"], {})

    # CM-2: the migration's effect is no longer "every mode survives" -- the
    # shipped default narrows to 1.33:1/1.78:1 where the camera has them -- so
    # what these two assert is that a migrated file behaves exactly like a
    # camera nobody has chosen ratios for, and specifically NOT like the stale
    # 1.78:1-only value. On imx477 the two answers are disjoint, which is what
    # makes the assertion load-bearing: the stale value keeps only the 1.88
    # modes, the migrated one only the 1.33 family.
    def test_imx477_after_the_legacy_shipped_value_matches_a_fresh_camera(self):
        from module.config_loader import _apply_settings_defaults  # noqa: PLC0415

        image_capture_cfg = _apply_settings_defaults(
            self._legacy_on_disk_settings()
        )["image_capture"]
        d = _detector(aspect_ratios_cfg=image_capture_cfg.get("aspect_ratios"))
        pruned = d._finalize_modes({"imx477": [dict(m) for m in IMX477_FIVE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertEqual(
            sizes,
            {(4056, 3040), (2028, 1520), (1332, 990)},
            "a settings.jsonc left over from before WP-CM-11, carrying the "
            "old shipped {\"default\": [\"1.78:1\"]}, still narrows imx477 to "
            "the modes nearest 1.78 on reload -- it must instead behave like a "
            "camera nobody chose ratios for, which on this sensor is 1.33:1",
        )
        self.assertEqual(set(d._enabled_ratio_ids("imx477")), {"1.33:1"})

    def test_imx283_after_the_legacy_shipped_value_matches_a_fresh_camera(self):
        from module.config_loader import _apply_settings_defaults  # noqa: PLC0415

        image_capture_cfg = _apply_settings_defaults(
            self._legacy_on_disk_settings()
        )["image_capture"]
        d = _detector(aspect_ratios_cfg=image_capture_cfg.get("aspect_ratios"))
        pruned = d._finalize_modes({"imx283": [dict(m) for m in IMX283_SIX_MODES]})
        sizes = {
            (m["width"], m["height"], m["bit_depth"])
            for m in pruned["imx283"].values()
        }
        # This sensor's metadata table has no 4:3 mode, so the migrated file and
        # the stale value happen to select the same three ~1.8 modes. The
        # distinguishing evidence here is therefore the resolved ratio set
        # itself: derived from imx283's own modes, not carried over from a
        # global entry that no longer exists.
        self.assertEqual(
            sizes, {(2784, 1542, 12), (5568, 3094, 10), (3936, 2176, 10)},
        )
        self.assertEqual(image_capture_cfg.get("aspect_ratios"), {})
        self.assertTrue(d._ratio_selection_is_derived("imx283"))

    def test_a_genuine_per_camera_choice_of_178_still_narrows(self):
        # The migration must only recognise the exact, global, pre-existing
        # shape -- it must not defeat an operator who deliberately picks
        # 1.78:1 for a specific camera (a per-camera key, never "default";
        # see WORK-PACKAGES.md WP-CM-11 item 4) after this lands.
        from module.config_loader import _apply_settings_defaults  # noqa: PLC0415

        out = _apply_settings_defaults(
            {"image_capture": {"aspect_ratios": {"imx477": ["1.78:1"]}}}
        )
        self.assertEqual(out["image_capture"]["aspect_ratios"], {"imx477": ["1.78:1"]})

    def test_a_default_with_extra_keys_is_not_treated_as_leftover(self):
        # Only the exact single-key {"default": ["1.78:1"]} shape is
        # leftover from before WP-CM-11. Anything wider -- e.g. a per-camera
        # entry alongside "default" -- is real operator config and must
        # survive the migration untouched.
        from module.config_loader import _apply_settings_defaults  # noqa: PLC0415

        cfg = {"default": ["1.78:1"], "imx585": ["2.39:1"]}
        out = _apply_settings_defaults({"image_capture": {"aspect_ratios": dict(cfg)}})
        self.assertEqual(out["image_capture"]["aspect_ratios"], cfg)


# ── WP-CM-11 rework, non-blocking review finding: the "covers every mode by
# construction" guarantee (_derived_default_ratio_ids) is proven above only
# for imx477/imx296/imx283/imx585. ASPECT-RATIOS.md names imx519 and imx708
# in the same "unmodified driver" category as imx477/imx296, but
# resources/sensors.json has no mode data for either (imx519: [], imx708:
# None), so no fixture anywhere in this repo exercised them. Numbers below
# are read from the real mainline Raspberry Pi kernel drivers (not guessed,
# not from resources/sensors.json), same convention as IMX477_FIVE_MODES
# above:
#   https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.12.y/drivers/media/i2c/imx519.c
#   https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.12.y/drivers/media/i2c/imx708.c
# imx519's supported_modes_10bit[]: width/height verbatim; fps_max from each
# mode's own timeperframe_default fraction (denominator/numerator). imx519
# is the more interesting fixture of the two -- like imx477, its modes span
# two distinct native aspects (its full 4656x3496/2328x1748 readouts are
# ~4:3, its 3840x2160/1920x1080/1280x720 crops are 16:9), so this actually
# exercises "a mode's own nearest ratio is in the set" for two ratios, not
# one.
IMX519_FIVE_MODES = [
    {"width": 4656, "height": 3496, "bit_depth": 10, "hdr": False, "fps_max": 9},
    {"width": 3840, "height": 2160, "bit_depth": 10, "hdr": False, "fps_max": 18},
    {"width": 2328, "height": 1748, "bit_depth": 10, "hdr": False, "fps_max": 30},
    {"width": 1920, "height": 1080, "bit_depth": 10, "hdr": False, "fps_max": 60},
    {"width": 1280, "height": 720, "bit_depth": 10, "hdr": False, "fps_max": 80},
]

# imx708's supported_modes_10bit_no_hdr[]: width/height verbatim; fps_max
# computed from each mode's own pixel_rate / line_length_pix / vblank_min
# (the driver has no direct frame-rate field), which reproduces Raspberry
# Pi's published Camera Module 3 spec (14 / 56 / 120 fps) exactly. Every
# non-HDR mode is exactly 16:9 -- unlike imx519, this is the trivial
# all-one-ratio case (same shape as imx296's single mode), kept here because
# WORK-PACKAGES.md names imx708 explicitly and a fixture proves it rather
# than assumes it.
IMX708_THREE_MODES = [
    {"width": 4608, "height": 2592, "bit_depth": 10, "hdr": False, "fps_max": 14},
    {"width": 2304, "height": 1296, "bit_depth": 10, "hdr": False, "fps_max": 56},
    {"width": 1536, "height": 864, "bit_depth": 10, "hdr": False, "fps_max": 120},
]


class Imx519Imx708DerivedDefaultRatioSetTests(unittest.TestCase):
    """WP-CM-11 rework, non-blocking review finding: DerivedDefaultRatioSetTests
    above only fixtures imx477/imx296/imx283/imx585. This class covers the
    other two sensors WORK-PACKAGES.md's WP-CM-11 explicitly names in the
    same "unmodified driver" bucket, with real mode tables read from the
    mainline drivers (see the module-level comment above IMX519_FIVE_MODES).
    """

    def test_imx519_five_modes_all_survive_with_no_config(self):
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx519": [dict(m) for m in IMX519_FIVE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx519"].values()}
        self.assertEqual(sizes, {(m["width"], m["height"]) for m in IMX519_FIVE_MODES})

    def test_imx519_derived_default_is_133_and_178(self):
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"imx519": [dict(m) for m in IMX519_FIVE_MODES]}
        self.assertEqual(set(d._enabled_ratio_ids("imx519")), {"1.33:1", "1.78:1"})

    def test_imx708_three_modes_all_survive_with_no_config(self):
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx708": [dict(m) for m in IMX708_THREE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx708"].values()}
        self.assertEqual(sizes, {(m["width"], m["height"]) for m in IMX708_THREE_MODES})

    def test_imx708_derived_default_is_178_only(self):
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"imx708": [dict(m) for m in IMX708_THREE_MODES]}
        self.assertEqual(set(d._enabled_ratio_ids("imx708")), {"1.78:1"})


class HomeRatioAlwaysClaimsItsModesTests(unittest.TestCase):
    """The derived default is built from each mode's home ratio, so a ratio has to
    claim the modes that come home to it -- not only the ones sitting within
    tolerance of it.

    Found by a reviewer on WP-CM-11. _modes_within_ratio_tolerance returns just
    the within-tolerance group as soon as that group is non-empty, so a mode whose
    nearest ratio is R, but which is further than the tolerance from R, is dropped
    the moment a sibling mode sits closer to R. Both modes below come home to
    1.33:1, which is therefore the whole derived default, and the further one used
    to vanish -- breaking the very property the derived default exists to provide.
    """

    MODES = [
        {"width": 1600, "height": 1200, "bit_depth": 12, "hdr": False,
         "fps_max": 30, "aspect": 1.333},   # within tolerance of 1.33:1
        {"width": 1620, "height": 1256, "bit_depth": 12, "hdr": False,
         "fps_max": 30, "aspect": 1.290},   # same home ratio, outside tolerance
    ]

    def test_both_modes_survive_the_derived_default(self):
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"testsensor": [dict(m) for m in self.MODES]}
        self.assertEqual(d._enabled_ratio_ids("testsensor"), ["1.33:1"],
                         "both modes come home to 1.33:1, so that is the whole "
                         "derived default")
        pruned = d._finalize_modes({"testsensor": [dict(m) for m in self.MODES]})
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["testsensor"].values()},
            {(1600, 1200), (1620, 1256)},
            "the mode outside tolerance was dropped even though the default "
            "enabled its own home ratio to keep it",
        )

    def test_an_explicit_choice_of_that_ratio_keeps_both_too(self):
        # Same claim, chosen rather than derived. Picking 1.33:1 means picking the
        # modes that belong to it, including the one further from it: the pane
        # labels that row 1.33:1, so hiding it while 1.33:1 is on would contradict
        # what the operator sees.
        d = _detector(aspect_ratios_cfg={"testsensor": ["1.33:1"]})
        d.sensor_modes_unfiltered = {"testsensor": [dict(m) for m in self.MODES]}
        pruned = d._finalize_modes({"testsensor": [dict(m) for m in self.MODES]})
        self.assertEqual(len(pruned["testsensor"]), 2)


class PreferredDefaultRatioPairTests(unittest.TestCase):
    """CM-2, the rule in one place: _default_ratio_ids returns the preferred
    pair restricted to what the camera has, and the whole derived set when it
    has neither. The three shapes are asserted here on minimal fixtures so the
    rule is readable without a sensor's full mode table; the per-sensor classes
    above are what prove it on the real ones.

    The ids come from aspect_ratios.PREFERRED_DEFAULT_RATIO_IDS, read here
    rather than typed again, so this test cannot pass while the constant says
    something else.
    """

    @staticmethod
    def _mode(aspect):
        return {"width": 1920, "height": int(round(1920 / aspect)),
                "bit_depth": 12, "hdr": False, "fps_max": 30, "aspect": aspect}

    def _detector_with(self, aspects):
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"cam": [self._mode(a) for a in aspects]}
        return d

    def test_the_constant_is_4x3_and_16x9_in_table_order(self):
        from module.aspect_ratios import (  # noqa: PLC0415
            PREFERRED_DEFAULT_RATIO_IDS, load_aspect_ratio_table,
        )

        self.assertEqual(PREFERRED_DEFAULT_RATIO_IDS, ("1.33:1", "1.78:1"))
        table_ids = [e["id"] for e in load_aspect_ratio_table()]
        self.assertEqual(
            [rid for rid in table_ids if rid in PREFERRED_DEFAULT_RATIO_IDS],
            list(PREFERRED_DEFAULT_RATIO_IDS),
            "a preferred id that is not in the canonical table could never be "
            "selected, and the order here is the order the pane shows",
        )

    def test_both_present(self):
        d = self._detector_with([1.33, 1.78, 2.39])
        self.assertEqual(d._default_ratio_ids("cam"), ["1.33:1", "1.78:1"])
        self.assertEqual(d._enabled_ratio_ids("cam"), ["1.33:1", "1.78:1"])

    def test_only_4x3_present(self):
        d = self._detector_with([1.33, 1.89])
        self.assertEqual(d._default_ratio_ids("cam"), ["1.33:1"])

    def test_only_16x9_present(self):
        d = self._detector_with([1.78, 2.39])
        self.assertEqual(d._default_ratio_ids("cam"), ["1.78:1"])

    def test_neither_present_falls_back_to_every_derived_ratio(self):
        d = self._detector_with([2.39, 2.00])
        self.assertEqual(
            d._default_ratio_ids("cam"), d._derived_default_ratio_ids("cam"),
        )
        self.assertEqual(set(d._default_ratio_ids("cam")), {"2.39:1", "2.00:1"})

    def test_a_camera_with_no_modes_at_all_selects_nothing(self):
        # Not a regression: with no modes there is nothing to select for, and
        # _finalize_modes' own "never leave a camera without modes" fallback is
        # what covers a camera whose table is empty for other reasons.
        d = self._detector_with([])
        self.assertEqual(d._default_ratio_ids("cam"), [])

    def test_an_explicit_choice_still_wins_over_the_pair(self):
        d = self._detector_with([1.33, 1.78, 2.39])
        d.aspect_ratios_cfg = {"cam": ["2.39:1"]}
        self.assertEqual(d._enabled_ratio_ids("cam"), ["2.39:1"])
        self.assertFalse(d._ratio_selection_is_derived("cam"))

        d.aspect_ratios_cfg = {"default": ["2.39:1"]}
        self.assertEqual(d._enabled_ratio_ids("cam"), ["2.39:1"])
        self.assertFalse(d._ratio_selection_is_derived("cam"))

        # And with neither entry, the shipped pair -- which _ratio_selection_
        # is_derived has to agree is the derived case, or the two have drifted.
        d.aspect_ratios_cfg = {}
        self.assertEqual(d._enabled_ratio_ids("cam"), ["1.33:1", "1.78:1"])
        self.assertTrue(d._ratio_selection_is_derived("cam"))


if __name__ == "__main__":
    unittest.main()


class FullFrameToggleTests(unittest.TestCase):
    """The whole-sensor toggle (operator, 2026-09-22).

    "among the aspect ratios, also add the full option (last). then i get the
    full frame options for the sensor regardless of aspect ratio. unless the
    full frame actually _is_ one of the aspect ratios. then this option should
    read: 1.33:1 (full) ... if the full frame is not any of the standard
    aspect ratios it should be on the lower right (last among the options) and
    read the aspect ratio and the (full)".

    Three sensor shapes exercise all of it: a 3:2 sensor whose full frame is
    off-table (imx283, 1.50), one whose full frame is a table ratio (imx585 at
    1.78), and a stock sensor that reports no crop geometry at all and so has
    no knowable full frame (imx477).
    """

    SW, SH = 5472, 3648

    def _mode(self, cw, ch, cx=0, cy=0, geometry=True, bx=1, by=1, sw=None, sh=None):
        m = {"width": cw + 96, "height": ch + 16, "bit_depth": 12,
             "aspect": round(cw / ch, 2)}
        if geometry:
            m.update({"crop_x": cx, "crop_y": cy, "crop_width": cw, "crop_height": ch,
                      "sensor_width": sw or self.SW, "sensor_height": sh or self.SH,
                      "binning_x": bx, "binning_y": by})
        return m

    def _detector(self, modes, cfg=None):
        sd = SensorDetect.__new__(SensorDetect)
        sd.sensor_modes_unfiltered = {"cam": modes}
        sd.aspect_ratios_cfg = cfg or {}
        sd.aspect_ratio_table = None
        return sd

    def _three_two_sensor(self):
        return [
            self._mode(5472, 3648),                       # full frame, 1.50
            self._mode(5472, 3648, bx=2, by=2),           # full frame, binned
            self._mode(4864, 3648, cx=304),               # 1.33 crop
            self._mode(5016, 3648, cx=228),               # 1.37 crop
            self._mode(5472, 3080, cy=284),               # 1.78 crop
        ]

    # ---- off-table full frame: its own toggle, last, labelled with the ratio

    def test_off_table_full_frame_gets_its_own_toggle(self):
        sd = self._detector(self._three_two_sensor())
        self.assertEqual(sd.full_frame_ratio("cam"), (FULL_FRAME_RATIO_ID, 1.5))
        entry = sd.available_aspect_ratios("cam")[FULL_FRAME_RATIO_ID]
        self.assertTrue(entry["is_full"])
        self.assertEqual(entry["label"], "1.50:1 (full)")
        self.assertEqual(entry["value"], 1.5)

    def test_the_full_toggle_sorts_after_every_table_ratio(self):
        # The pane ranks an id the canonical table does not carry at 999, so
        # "last" is a property of the id being off-table. Pin that it IS
        # off-table, which is what puts it lower-right.
        sd = self._detector(self._three_two_sensor())
        table_ids = {e["id"] for e in sd._aspect_ratio_table()}
        self.assertNotIn(FULL_FRAME_RATIO_ID, table_ids)

    def test_the_full_toggle_claims_whole_sensor_modes_and_only_those(self):
        modes = self._three_two_sensor()
        sd = self._detector(modes, {"cam": [FULL_FRAME_RATIO_ID]})
        matches = sd._ratio_matches_for_camera("cam", modes)
        claimed = [m for m in modes if id(m) in matches]
        self.assertEqual(len(claimed), 2, "both full-frame modes, whatever their binning")
        for m in claimed:
            self.assertTrue(SensorDetect._mode_is_full(m))
            self.assertEqual(matches[id(m)][0], FULL_FRAME_RATIO_ID)

    def test_a_whole_sensor_mode_does_not_also_appear_under_a_table_ratio(self):
        # 1.50 is nearest to 1.37 of the fourteen, and _modes_within_ratio_
        # tolerance's near-tie fallback would otherwise hand the native
        # readouts back to 1.37:1 -- so they would reappear with "full" off.
        modes = self._three_two_sensor()
        sd = self._detector(modes, {"cam": ["1.37:1"]})
        matches = sd._ratio_matches_for_camera("cam", modes)
        for m in modes:
            if SensorDetect._mode_is_full(m):
                self.assertNotIn(id(m), matches,
                                 "a full-frame mode must hide behind the full toggle alone")
        # ...and 1.37:1 still yields its own crop, so it is not left empty.
        self.assertTrue(any(id(m) in matches for m in modes
                            if not SensorDetect._mode_is_full(m)))

    def test_rows_are_labelled_with_the_toggle_that_shows_them(self):
        # home_ratio_id is what settings_editor.nearest_ratio labels rows
        # with; if it disagreed with the matcher a row would vanish while its
        # own toggle was on.
        modes = self._three_two_sensor()
        sd = self._detector(modes)
        for m in modes:
            rid = sd.home_ratio_id("cam", m)
            if SensorDetect._mode_is_full(m):
                self.assertEqual(rid, FULL_FRAME_RATIO_ID)
            else:
                self.assertNotEqual(rid, FULL_FRAME_RATIO_ID)

    def test_the_shipped_default_keeps_the_whole_sensor_reachable(self):
        sd = self._detector(self._three_two_sensor())
        self.assertEqual(sd._default_ratio_ids("cam"),
                         ["1.33:1", "1.78:1", FULL_FRAME_RATIO_ID])

    # ---- on-table full frame: no extra toggle, the existing one says (full)

    def test_on_table_full_frame_relabels_instead_of_adding_a_toggle(self):
        modes = [
            self._mode(3840, 2160, sw=3856, sh=2180),              # full, 1.78
            self._mode(2880, 2160, cx=480, sw=3856, sh=2180),      # 1.33 crop
        ]
        sd = self._detector(modes)
        self.assertEqual(sd.full_frame_ratio("cam"), ("1.78:1", 1.78))
        available = sd.available_aspect_ratios("cam")
        self.assertNotIn(FULL_FRAME_RATIO_ID, available,
                         "no fifteenth toggle when the full frame is one of the fourteen")
        self.assertTrue(available["1.78:1"]["is_full"])
        self.assertEqual(available["1.78:1"]["label"], "1.78:1 (full)")

    def test_an_on_table_full_frame_adds_nothing_to_the_default(self):
        modes = [
            self._mode(3840, 2160, sw=3856, sh=2180),
            self._mode(2880, 2160, cx=480, sw=3856, sh=2180),
        ]
        sd = self._detector(modes)
        self.assertEqual(sd._default_ratio_ids("cam"), ["1.33:1", "1.78:1"])

    # ---- no geometry: no full frame is knowable, so no toggle

    def test_a_sensor_with_no_crop_geometry_gets_no_full_toggle(self):
        modes = [self._mode(4056, 3040, geometry=False),
                 self._mode(2028, 1080, geometry=False)]
        sd = self._detector(modes)
        self.assertEqual(sd.full_frame_ratio("cam"), (None, None))
        self.assertNotIn(FULL_FRAME_RATIO_ID, sd.available_aspect_ratios("cam"))
        self.assertEqual(sd._default_ratio_ids("cam"), ["1.33:1"])

    # ---- the invariant the whole design rests on

    def test_selecting_the_whole_derived_set_still_loses_no_mode(self):
        for modes in (self._three_two_sensor(),
                      [self._mode(3840, 2160, sw=3856, sh=2180),
                       self._mode(2880, 2160, cx=480, sw=3856, sh=2180)],
                      [self._mode(4056, 3040, geometry=False)]):
            with self.subTest(modes=len(modes)):
                probe = self._detector(modes)
                derived = probe._derived_default_ratio_ids("cam")
                sd = self._detector(modes, {"cam": derived})
                matches = sd._ratio_matches_for_camera("cam", modes)
                self.assertEqual(
                    [m for m in modes if id(m) not in matches], [],
                    "the derived set must cover every mode, full frame included")
