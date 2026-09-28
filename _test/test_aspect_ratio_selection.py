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
    def test_only_the_ratios_actually_reached_are_offered(self):
        """"No closest" (PLAN.md, 2026-09-28), superseding this test's
        earlier "every ratio resolves to something approximate" claim: a
        camera offers exactly the ratios its own modes come home to, and
        nothing else. IMX477_MODES' two shapes (1.33, 1.88) come home to
        1.33:1 and 1.89:1 (within ASPECT_RATIO_TOLERANCE of each); a ratio
        neither is near, like 2.55:1, is simply absent -- not present with
        exact=False the way it used to be."""
        d = _detector()
        d.sensor_modes_unfiltered = {"imx477": [dict(m) for m in IMX477_MODES]}
        avail = d.available_aspect_ratios("imx477")
        self.assertEqual(set(avail), {"1.33:1", "1.89:1"})
        self.assertNotIn("2.55:1", avail)

    def test_a_ratio_the_sensor_actually_hits_is_exact(self):
        d = _detector()
        d.sensor_modes_unfiltered = {"imx477": [dict(m) for m in IMX477_MODES]}
        avail = d.available_aspect_ratios("imx477")
        self.assertTrue(avail["1.33:1"]["exact"])

    def test_enabling_133_still_offers_both_modes_when_neither_homes_there(self):
        # "No closest" (2026-09-28): neither mode below actually comes home
        # to 1.33:1 -- the first's real aspect (1.30) is outside tolerance of
        # every table ratio (home "native:1.30"), and the second (1.37) comes
        # home to the table's own "1.37:1", not "1.33:1". So enabling only
        # "1.33:1" claims neither, and both survive through _finalize_modes'
        # unrelated "never leave a camera without modes" fallback instead --
        # a different mechanism than the near-tie union this test used to
        # name, reaching the same two modes.
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

    def test_a_global_default_entry_is_ignored_and_does_not_affect_either_camera(self):
        # PLAN.md D2 (2026-09-28): "default" is unconditionally ignored now --
        # exactly the cross-sensor carrier that let an imx585 choice narrow an
        # imx477 after a swap. A present "default": ["1.78:1"] no longer
        # narrows anything; imx283 (no per-camera entry of its own) falls
        # straight to the stock rule instead, unaffected by imx585's own
        # separate, unrelated per-camera entry.
        d = _detector(aspect_ratios_cfg={"imx585": ["2.39:1"], "default": ["1.78:1"]})
        pruned = d._finalize_modes({
            "imx585": [dict(m) for m in self.IMX585_SET],
            "imx283": [dict(m) for m in self.IMX283_SET],
        })
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx585"].values()},
            {(3840, 1608)},
        )
        # imx283's stock rule: 1.33:1 and 1.78:1, both offered -- "default"
        # never gets consulted at all.
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx283"].values()},
            {(5472, 4104), (5472, 3080)},
        )

    def test_no_default_entry_at_all_falls_to_the_stock_rule_per_camera(self):
        # No "default" key present at all, and no per-camera entry either.
        # Each camera resolves through its OWN modes (_default_ratio_ids'
        # stock rule: 1.33:1/1.78:1/full, only if actually offered), not a
        # shared hardcoded ratio and not "default" (which is ignored either way).
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
        # PLAN.md D4 (2026-09-28): an explicit enabled_modes choice is no
        # longer exempt from the ratio gate -- it also needs its mode's home
        # ratio enabled, same as the stock/ratio-driven path. imx283's home
        # ratio here is 2.39:1 (aspect exactly 2.39), so it must be enabled
        # explicitly too, or the dial would show nothing for it; imx585's own
        # aspect_ratios entry stays completely unrelated to imx283's.
        d = _detector(
            aspect_ratios_cfg={"imx585": ["2.39:1"], "imx283": ["2.39:1"]},
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
        # imx283's enabled_modes entry is authoritative over WHICH mode, once
        # its ratio is enabled -- independent of imx585's own, unrelated
        # aspect_ratios entry.
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx283"].values()},
            {(5472, 2288)},
        )

    def test_an_explicit_mode_under_a_disabled_ratio_is_not_in_the_dial(self):
        """PLAN.md's own worked example for D4: an explicit enabled_modes
        choice whose mode's home ratio is not enabled must not reach the
        dial -- the fix for "hidden rows keep their checkbox and bypass the
        ratio filter" (PLAN.md D4). Two modes are explicitly enabled here --
        one under the enabled ratio, one under a disabled one -- so the
        camera is never left empty and the "never leave a camera without
        modes" fallback (a different mechanism) cannot be mistaken for this
        one."""
        d = _detector(
            aspect_ratios_cfg={"imx283": ["1.33:1"]},   # 2.39:1 left disabled
            enabled_modes={"imx283": [
                {"width": 5472, "height": 4104, "bit_depth": 12, "hdr": False},  # home 1.33:1, enabled
                {"width": 5472, "height": 2288, "bit_depth": 12, "hdr": False},  # home 2.39:1, disabled
            ]},
        )
        pruned = d._finalize_modes({"imx283": [dict(m) for m in self.IMX283_SET]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx283"].values()}
        self.assertEqual(sizes, {(5472, 4104)})
        self.assertIsNone(d.mode_selection_notice("imx283"),
                          "the camera was never actually left empty -- no fallback fired")


class ConfigLoaderDefaultRegressionTests(unittest.TestCase):
    """Per-sensor-settings-backend, 2026-09-28: the aspect_ratios_cfg/
    min_mode_width a real config_loader.py hands a real settings.jsonc that
    predates image_capture.aspect_ratios entirely (every settings.jsonc from
    before WP-CM-6) now resolves through the SAME stock rule as any other
    camera nobody has chosen ratios for -- there is no more "key truly
    absent -> skip the ratio matcher altogether" escape hatch (WP-CM-6's own
    "a settings file with no aspect_ratios must behave exactly as it does
    today" compatibility clause). PLAN.md's whole premise is that the stock
    rule applies unconditionally, with no opt-in required, so this class now
    asserts THAT instead of asserting "no opinion" is inert.

    Real numbers from resources/sensors.json's imx477 entry: a 16:9-ish
    ratio (1.87, home 1.85:1 -- a table tie broken by table order, see
    ASPECT_RATIO_TOLERANCE's own comment), the sensor's full-FOV 4:3 readout
    (1.33) and its high-fps crop (1.34, also home 1.33:1). 1.78:1 itself is
    not offered, so the stock rule is 1.33:1 alone.
    """

    IMX477_STOCK_MODES = [
        {"width": 2028, "height": 1080, "bit_depth": 12, "hdr": False,
         "fps_max": 50, "aspect": 1.87},
        {"width": 2028, "height": 1520, "bit_depth": 12, "hdr": False,
         "fps_max": 40, "aspect": 1.33},
        {"width": 1332, "height": 990, "bit_depth": 10, "hdr": False,
         "fps_max": 120, "aspect": 1.34},
    ]

    def test_a_legacy_settings_jsonc_gets_the_stock_rule_not_every_mode(self):
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
        self.assertEqual(sizes, {(2028, 1520), (1332, 990)})
        self.assertEqual(d._enabled_ratio_ids("imx477"), ["1.33:1"])


class ShippedDefaultFreshInstallRegressionTests(unittest.TestCase):
    """A present-but-empty image_capture.aspect_ratios ({}, what every fresh
    install ships -- WP-CM-6 item 1) resolves through the stock rule, not
    through some earlier hardcoded ratio: this class runs the REAL shipped
    settings against the REAL resources/sensors.json imx477 entry (via
    config_loader.load_settings()/sensor_database.load_sensor_database(),
    never a hand-picked fixture) through the real _finalize_modes(), exactly
    as SensorDetect would on a fresh install.

    Per-sensor-settings-backend, 2026-09-28: the stock rule (PLAN.md,
    superseding 2026-09-26's "1.78:1 or closest" -- see aspect_ratios.
    PREFERRED_DELIVERY_RATIO_ID's comment) is now literal, three-step
    membership testing, not a search for the nearest available shape. imx477
    has no true 16:9 mode (its widest, 2028x1080/4056x2160, is 1.87, home
    ratio 1.89:1 -- a DIFFERENT id, not "1.78:1"), so 1.78:1 is simply not
    offered and the stock rule is 1.33:1 alone: the sensor's full-FOV 4:3
    readout (4056x3040), its 2028x1520 half-res readout and its 120fps
    1332x990 crop. The two 1.89-ish modes start hidden -- reachable, but one
    toggle away -- which is the literal, no-inference behaviour PLAN.md's D2
    finding asked for after the previous "or closest" stand-in mechanism
    (1.89:1 filling the 16:9 slot) was traced to a saved ratio choice
    surviving a sensor swap onto a camera that never had that shape.
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

    # Of those five, the ones the stock rule selects: 1.33:1 is offered (the
    # two 4:3 readouts and the 1332x990 crop, aspect 1.35, home 1.33:1); 1.78:1
    # is not (nothing on this sensor is within tolerance of it); the full
    # frame is not knowable (this database fixture carries no crop
    # annotation). So the stock rule is 1.33:1 alone, and the two 1.89:1-homed
    # modes (2028x1080/4056x2160, both aspect 1.87) start hidden.
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
            f"{source_label}: the fresh-install stock rule on this sensor is "
            f"1.33:1 alone -- it has no true 16:9 mode, and 'or closest' no "
            f"longer stands 1.89:1 in for it",
        )
        self.assertEqual(
            {(m["width"], m["height"]) for m in d.sensor_modes_unfiltered["imx477"]},
            self.ALL_STOCK_IMX477_SIZES,
            f"{source_label}: every stock mode stays reachable in the "
            f"unfiltered table the settings page offers",
        )
        self.assertEqual(
            set(d._enabled_ratio_ids("imx477")), {"1.33:1"},
            f"{source_label}: 1.78:1 itself must never be selected on a sensor "
            f"with no mode that comes home to it, and 'no closest' means "
            f"nothing stands in for it any more either -- the stock rule is "
            f"1.33:1 alone",
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
    unfiltered table. See StockRatioRuleTests below for the general case and
    the "neither ratio offered" fallback.

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
        # stock rule. That entry's modes are ~1.5 or ~1.78 and it has nothing
        # at 4:3.
        #
        # Per-sensor-settings-backend, 2026-09-28: this fixture carries no
        # crop geometry, so full_frame_ratio() cannot say what the whole
        # frame is, and "no closest" means the 1.5-aspect modes are simply
        # outside ASPECT_RATIO_TOLERANCE of every table ratio (home
        # "native:1.50", not "1.37:1" or any stand-in) -- neither preferred
        # id is offered for them, so they stay hidden by default (one toggle
        # away), unlike 2026-09-22/26's "native readout always on" rule this
        # class used to assert. 1.78:1 IS offered and is the whole stock
        # rule; the 5568x3094 10-bit mode also homes to 1.78:1 but k_steps
        # (k=5.5, absent from the shipped [1.5, 2, 3, 4]) excludes it anyway
        # -- unrelated to the ratio axis.
        expected = {(2784, 1542, 12), (3936, 2176, 10)}
        for settings_path, label in (
            (ROOT / "settings.jsonc", "settings.jsonc"),
            (ROOT / "resources" / "settings" / "settings_default.jsonc", "settings_default.jsonc"),
        ):
            settings = load_settings(settings_path)
            image_capture_cfg = settings["image_capture"]
            # WP-CM-11: ships as {}, an empty dict -- not the old hardcoded
            # {"default": ["1.78:1"]}. A present, empty key means "no per-
            # camera opinion", which resolves through the stock rule either
            # way now (present vs absent no longer distinguishes anything for
            # the ratio axis -- see SensorDetect.__init__'s own comment).
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
    """The imx477 case above is a sensor whose closest mode is 1.87, close
    enough to 1.89:1 to be exact. This is the harder shape: a sensor whose
    ENTIRE family sits at a materially different native aspect. Every imx283
    mode is about 1.5 or about 1.78, and the 1.5-aspect modes are a quarter
    away from every table ratio -- further than any imx477 mode ever is.

    Per-sensor-settings-backend, 2026-09-28: "no closest" means the 1.5
    family homes to "native:1.50", never a table id. 1.78:1 IS offered
    (imx283's own ~1.78 modes are exact), so the stock rule is 1.78:1 alone
    -- the 1.5 family stays hidden, one toggle away. _default_ratio_ids'
    fallback (never empty for a camera that offers ANY ratio) is what the
    all-1.5 fixture below exercises: neither preferred id is offered at all,
    so the stock rule falls back to every ratio the camera DOES offer --
    here, the single native id, keeping the whole table.
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
            f"{label}: the stock rule selected something other than this "
            f"sensor's ~1.78 family. It has no 4:3 mode, so 1.33:1 must not "
            f"be selected, and the selection must not be empty either.",
        )
        # "No closest": the 1.5 family is outside tolerance of every table
        # ratio and homes to "native:1.50", never "1.37:1" -- neither
        # preferred id names it, so only the offered 1.78:1 is stock.
        self.assertEqual(
            set(d._enabled_ratio_ids("imx283")), {"1.78:1"},
        )

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
        offered and narrowing to them would leave nothing selected. Falling
        back to every ratio the camera DOES offer -- here, its one native id
        -- is the only honest answer."""
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx283": [dict(m) for m in self.ALL_1_5_MODES]})
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx283"].values()},
            {(m["width"], m["height"]) for m in self.ALL_1_5_MODES},
        )
        self.assertEqual(d._enabled_ratio_ids("imx283"), ["native:1.50"])


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


class StockRatioRuleTests(unittest.TestCase):
    """Per-sensor-settings-backend, 2026-09-28: a camera with no explicit
    selection resolves through _default_ratio_ids' stock rule -- "1.33:1" if
    OFFERED, "1.78:1" if offered, then the full frame if known/offered/not
    already in, else every ratio the camera offers. Not the old hardcoded
    single ratio ("1.78:1"), not 2026-09-26's "or closest" stand-in
    mechanism (_derived_default_ratio_ids/_stand_in_ratio_id, removed this
    batch), and never "default" (PLAN.md D2) at any precedence level.

    This class replaces DerivedDefaultRatioSetTests, which asserted the
    removed stand-in mechanism directly; its imx477/imx296/imx585/imx283
    fixtures are kept, with the numbers recomputed for the literal rule.
    """

    def test_imx477_stock_is_133_alone(self):
        # imx477 has no 16:9 mode at all -- its widest is 2028x1080 = 1.878,
        # home ratio 1.89:1, a DIFFERENT id from 1.78:1 -- so 1.78:1 is simply
        # not offered, and "no closest" means nothing stands in for it. Full
        # frame is unknown (no crop annotation in this fixture). Stock is
        # 1.33:1 alone; the two 1.89-homed modes start hidden.
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx477": [dict(m) for m in IMX477_FIVE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertEqual(sizes, {(4056, 3040), (2028, 1520), (1332, 990)})
        self.assertEqual(
            set(d._enabled_ratio_ids("imx477")), {"1.33:1"},
        )

    def test_imx477_offers_133_and_189(self):
        # What the pane's toggles show, independent of which is enabled by
        # default: both ratios this camera's modes actually come home to.
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"imx477": [dict(m) for m in IMX477_FIVE_MODES]}
        self.assertEqual(
            set(d.available_aspect_ratios("imx477")), {"1.33:1", "1.89:1"},
        )

    def test_imx296_single_mode_survives_with_no_config(self):
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx296": [dict(m) for m in IMX296_ONE_MODE]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx296"].values()}
        self.assertEqual(sizes, {(1456, 1088)})

    def test_imx296_stock_is_133_only(self):
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"imx296": [dict(m) for m in IMX296_ONE_MODE]}
        self.assertEqual(set(d._enabled_ratio_ids("imx296")), {"1.33:1"})

    def test_imx585_aspect_family_default_selects_4x3_and_16x9(self):
        # Both preferred ratios OFFERED (the aspect-family driver produces
        # all fourteen shapes exactly): the stock rule picks exactly the 4:3
        # and 16:9 ones, and the other twelve families start hidden.
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx585": [dict(m) for m in IMX585_ASPECT_FAMILY]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx585"].values()}
        self.assertEqual(sizes, {(2880, 2160), (3840, 2160)})

    def test_imx585_offers_all_fourteen_ratios(self):
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"imx585": [dict(m) for m in IMX585_ASPECT_FAMILY]}
        self.assertEqual(
            set(d.available_aspect_ratios("imx585")), ALL_FOURTEEN_RATIO_IDS,
        )
        self.assertEqual(
            d._enabled_ratio_ids("imx585"), ["1.33:1", "1.78:1"],
            "the preferred pair, in stock-rule order",
        )

    def test_imx283_stock_is_178_alone(self):
        # This metadata table has ~1.78 modes but no 4:3 one, and no crop
        # annotation to know the full frame -- so the SHAPE and full-frame
        # slots find nothing, and the stock rule is 1.78:1 alone. The three
        # 1.5-aspect modes (home "native:1.50", not "1.37:1" -- see
        # ShippedDefaultAcrossANativelyDifferentSensorTests) start hidden,
        # including the sensor's own 2784x1828 binned full frame.
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx283": [dict(m) for m in IMX283_SIX_MODES]})
        sizes = {
            (m["width"], m["height"], m["bit_depth"]) for m in pruned["imx283"].values()
        }
        self.assertEqual(
            sizes,
            {(2784, 1542, 12), (5568, 3094, 10), (3936, 2176, 10)},
        )

    def test_explicit_per_camera_selection_still_narrows(self):
        d = _detector(aspect_ratios_cfg={"imx477": ["1.89:1"]})
        pruned = d._finalize_modes({"imx477": [dict(m) for m in IMX477_FIVE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertEqual(sizes, {(4056, 2160), (2028, 1080)})

    def test_a_default_only_entry_is_ignored_and_falls_to_stock(self):
        # PLAN.md D2: "default" is never consulted at any precedence level --
        # not even when it is the ONLY entry present. imx477 with no
        # per-camera key of its own falls straight to the stock rule
        # (1.33:1 alone), exactly as if aspect_ratios_cfg were {}.
        d = _detector(aspect_ratios_cfg={"default": ["1.89:1"]})
        pruned = d._finalize_modes({"imx477": [dict(m) for m in IMX477_FIVE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertEqual(sizes, {(4056, 3040), (2028, 1520), (1332, 990)})
        self.assertEqual(set(d._enabled_ratio_ids("imx477")), {"1.33:1"})

    def test_a_mode_far_from_every_ratio_still_gets_its_own_reachable_toggle(self):
        # imx283's 1.5-aspect modes are outside ASPECT_RATIO_TOLERANCE of
        # every table ratio -- "no closest" means this is a native id, not an
        # "approximate" 1.37:1 match. As the camera's only shape it is still
        # reachable: _default_ratio_ids' fallback (every offered ratio, when
        # neither preference nor the full frame apply) never leaves it empty.
        far_mode = {"width": 2784, "height": 1828, "bit_depth": 12, "hdr": False,
                    "fps_max": 36, "aspect": 1.5}
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"imx283": [dict(far_mode)]}
        self.assertEqual(d._enabled_ratio_ids("imx283"), ["native:1.50"])
        pruned = d._finalize_modes({"imx283": [dict(far_mode)]})
        self.assertEqual(len(pruned["imx283"]), 1)


class LegacyDefaultIsIgnoredNotMigratedTests(unittest.TestCase):
    """Per-sensor-settings-backend, 2026-09-28: config_loader.py's old
    _migrate_legacy_shipped_aspect_ratio_default() -- which cleared an
    on-disk image_capture.aspect_ratios == {"default": ["1.78:1"]} back to
    {} before SensorDetect ever saw it -- is removed. See config_loader.py's
    own comment for why: "default" is now unconditionally ignored at every
    precedence level (PLAN.md D2), so a leftover value can no longer narrow
    anything whether or not it is ever cleared from disk. This class proves
    both halves of that: _apply_settings_defaults() leaves a legacy
    "default" value on disk untouched (nothing clears it any more -- it is
    dropped only at save time, by settings_editor.put_settings, once an
    operator saves through the new per-sensor mechanism), and SensorDetect
    still behaves exactly like a camera nobody chose ratios for regardless.
    """

    def test_apply_settings_defaults_no_longer_clears_it(self):
        from module.config_loader import _apply_settings_defaults  # noqa: PLC0415

        out = _apply_settings_defaults(
            {"image_capture": {"aspect_ratios": {"default": ["1.78:1"]}}}
        )
        self.assertEqual(out["image_capture"]["aspect_ratios"], {"default": ["1.78:1"]})

    def test_imx477_behaves_like_a_fresh_camera_regardless(self):
        d = _detector(aspect_ratios_cfg={"default": ["1.78:1"]})
        pruned = d._finalize_modes({"imx477": [dict(m) for m in IMX477_FIVE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertEqual(
            sizes,
            {(4056, 3040), (2028, 1520), (1332, 990)},
            "a stray on-disk \"default\" must not narrow imx477 -- it must "
            "behave exactly like a camera nobody chose ratios for, the stock "
            "rule's 1.33:1 alone",
        )
        self.assertEqual(set(d._enabled_ratio_ids("imx477")), {"1.33:1"})

    def test_a_genuine_per_camera_choice_of_178_is_unaffected(self):
        # An operator who deliberately picks 1.78:1 for a specific camera (a
        # per-camera key, never "default") is untouched either way.
        from module.config_loader import _apply_settings_defaults  # noqa: PLC0415

        out = _apply_settings_defaults(
            {"image_capture": {"aspect_ratios": {"imx477": ["1.78:1"]}}}
        )
        self.assertEqual(out["image_capture"]["aspect_ratios"], {"imx477": ["1.78:1"]})


# ── WP-CM-11 rework, non-blocking review finding: the "covers every mode by
# construction" guarantee (available_aspect_ratios) is proven above only
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


class Imx519Imx708StockRatioRuleTests(unittest.TestCase):
    """WP-CM-11 rework, non-blocking review finding: StockRatioRuleTests
    above only fixtures imx477/imx296/imx283/imx585. This class covers the
    other two sensors WORK-PACKAGES.md's WP-CM-11 explicitly names in the
    same "unmodified driver" bucket, with real mode tables read from the
    mainline drivers (see the module-level comment above IMX519_FIVE_MODES).
    Both fixtures' shapes are exact table matches, so the stock rule's
    outcome here is unaffected by "no closest" -- unlike imx477/imx283 above.
    """

    def test_imx519_five_modes_all_survive_with_no_config(self):
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx519": [dict(m) for m in IMX519_FIVE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx519"].values()}
        self.assertEqual(sizes, {(m["width"], m["height"]) for m in IMX519_FIVE_MODES})

    def test_imx519_stock_is_133_and_178(self):
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"imx519": [dict(m) for m in IMX519_FIVE_MODES]}
        self.assertEqual(set(d._enabled_ratio_ids("imx519")), {"1.33:1", "1.78:1"})

    def test_imx708_three_modes_all_survive_with_no_config(self):
        d = _detector(aspect_ratios_cfg={})
        pruned = d._finalize_modes({"imx708": [dict(m) for m in IMX708_THREE_MODES]})
        sizes = {(m["width"], m["height"]) for m in pruned["imx708"].values()}
        self.assertEqual(sizes, {(m["width"], m["height"]) for m in IMX708_THREE_MODES})

    def test_imx708_stock_is_178_only(self):
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"imx708": [dict(m) for m in IMX708_THREE_MODES]}
        self.assertEqual(set(d._enabled_ratio_ids("imx708")), {"1.78:1"})


# HomeRatioAlwaysClaimsItsModesTests retired, per-sensor-settings-backend,
# 2026-09-28: it pinned a WP-CM-11 reviewer finding that a mode further than
# ASPECT_RATIO_TOLERANCE from its nearest ratio, but sharing that "home" with
# an in-tolerance sibling, must not be dropped by the tolerance-first search
# _modes_within_ratio_tolerance used to do. "No closest" removes the
# mechanism the finding was about: home_ratio_id() no longer performs a
# tolerance-gated search that a sibling mode's closer distance could starve
# -- it is a pure per-mode function, and a mode outside tolerance of every
# table ratio gets its own native id rather than inheriting an in-tolerance
# sibling's. The two modes this class's MODES fixture used (aspect 1.333 and
# 1.290) now home to "1.33:1" and "native:1.29" respectively -- two DIFFERENT
# ids -- so the scenario "two modes share a home, only one within tolerance"
# cannot arise any more, and there is nothing left for this class to guard.


class PreferredDefaultRatioPairTests(unittest.TestCase):
    """The stock rule in one place (PLAN.md, per-sensor-settings-backend,
    2026-09-28): _default_ratio_ids tries PREFERRED_SHAPE_RATIO_ID ("1.33:1"),
    then PREFERRED_DELIVERY_RATIO_ID ("1.78:1"), then the camera's own full
    frame -- each ONLY if actually offered (available_aspect_ratios
    membership) -- and falls back to every offered ratio if none of the three
    apply.

    Supersedes 2026-09-26's "or closest": there is no more stand-in search
    (_stand_in_ratio_id, removed) for the nearest shape to a preference when
    the preference itself is not offered. A camera with no 16:9 mode simply
    does not get 1.78:1 in its stock set, full stop -- see
    aspect_ratios.PREFERRED_DELIVERY_RATIO_ID's own comment for why this
    replaced the stand-in mechanism (PLAN.md D2: a stand-in choice surviving
    a sensor swap is exactly the bug this batch fixes).

    The ids come from aspect_ratios' own constants, read here rather than typed
    again, so these tests cannot pass while the constants say something else.
    """

    @staticmethod
    def _mode(aspect):
        return {"width": 1920, "height": int(round(1920 / aspect)),
                "bit_depth": 12, "hdr": False, "fps_max": 30, "aspect": aspect}

    def _detector_with(self, aspects):
        d = _detector(aspect_ratios_cfg={})
        d.sensor_modes_unfiltered = {"cam": [self._mode(a) for a in aspects]}
        return d

    def test_the_constants_are_4x3_and_16x9_and_are_in_the_table(self):
        from module.aspect_ratios import (  # noqa: PLC0415
            PREFERRED_DELIVERY_RATIO_ID, PREFERRED_SHAPE_RATIO_ID,
            load_aspect_ratio_table,
        )

        self.assertEqual(PREFERRED_SHAPE_RATIO_ID, "1.33:1")
        self.assertEqual(PREFERRED_DELIVERY_RATIO_ID, "1.78:1")
        table_ids = [e["id"] for e in load_aspect_ratio_table()]
        for rid in (PREFERRED_SHAPE_RATIO_ID, PREFERRED_DELIVERY_RATIO_ID):
            self.assertIn(
                rid, table_ids,
                "a preference that is not in the canonical table has no value "
                "to measure 'or closest' against, so it could never be filled",
            )

    def test_both_present(self):
        d = self._detector_with([1.33, 1.78, 2.39])
        self.assertEqual(d._default_ratio_ids("cam"), ["1.33:1", "1.78:1"])
        self.assertEqual(d._enabled_ratio_ids("cam"), ["1.33:1", "1.78:1"])

    def test_no_16x9_mode_means_1_78_is_simply_not_offered(self):
        # THE imx477 CASE, in miniature. This camera's widest shape is
        # exactly 1.89 (an EXACT table match, "1.89:1"), 0.11 from 16:9 --
        # far outside tolerance. "No closest" means nothing stands in for
        # 1.78:1 any more: it is not offered, so it is not in the stock set,
        # full stop. Under 2026-09-26's superseded rule 1.89:1 used to fill
        # the delivery slot as a stand-in.
        d = self._detector_with([1.33, 1.89])
        self.assertEqual(d._default_ratio_ids("cam"), ["1.33:1"])

    def test_no_4x3_mode_leaves_the_shape_slot_empty(self):
        # 1.78:1 is offered exactly, so the stock rule may narrow to it;
        # 2.39:1 is not 1.33:1 and is not offered under that id, so the shape
        # slot simply contributes nothing.
        d = self._detector_with([1.78, 2.39])
        self.assertEqual(d._default_ratio_ids("cam"), ["1.78:1"])

    def test_neither_preference_offered_keeps_the_whole_table(self):
        # Neither preference is offered and there is no crop geometry to give
        # a full frame, so this camera is not one the preferences describe at
        # all -- the fallback (every ratio the camera DOES offer) is the only
        # honest answer, keeping both of its shapes rather than picking one.
        d = self._detector_with([2.39, 2.00])
        self.assertEqual(
            set(d._default_ratio_ids("cam")),
            set(d.available_aspect_ratios("cam")),
        )
        self.assertEqual(set(d._default_ratio_ids("cam")), {"2.39:1", "2.00:1"})

    def test_a_camera_with_no_modes_at_all_selects_nothing(self):
        # Not a regression: with no modes there is nothing to select for, and
        # _finalize_modes' own "never leave a camera without modes" fallback is
        # what covers a camera whose table is empty for other reasons.
        d = self._detector_with([])
        self.assertEqual(d._default_ratio_ids("cam"), [])

    def test_an_explicit_choice_still_wins_over_the_stock_rule(self):
        d = self._detector_with([1.33, 1.78, 2.39])
        d.aspect_ratios_cfg = {"cam": ["2.39:1"]}
        self.assertEqual(d._enabled_ratio_ids("cam"), ["2.39:1"])
        self.assertFalse(d._ratio_selection_is_derived("cam"))

        # PLAN.md D2: "default" is NEVER consulted, even when it is the only
        # entry present -- this now falls straight to the stock rule, unlike
        # the superseded behaviour where "default" was itself a real choice.
        d.aspect_ratios_cfg = {"default": ["2.39:1"]}
        self.assertEqual(d._enabled_ratio_ids("cam"), ["1.33:1", "1.78:1"])
        self.assertTrue(d._ratio_selection_is_derived("cam"))

        # And with neither entry, the same stock pair -- which
        # _ratio_selection_is_derived has to agree is the derived case, or
        # the two have drifted.
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
        # No "(full)" suffix -- the operator dropped it on 2026-09-22. It
        # reads as a plain ratio because that is what it is: this sensor's
        # native shape. `is_full` is what the tooltip and the default use.
        self.assertEqual(entry["label"], "1.50:1")
        self.assertEqual(entry["value"], 1.5)

    def test_the_full_toggle_is_off_table_and_carries_its_own_value(self):
        """It is not a table id, and it must carry a numeric value.

        Originally the pane appended it last. The operator revised that on
        2026-09-22 -- "that is the native aspect ratio, put it into its place
        in the list, not last" -- so the pane now places it by VALUE among the
        table's ratios (1.50 lands between 1.37:1 and 1.78:1). That sort lives
        in renderAspectRatioToggles(); what this side owes it is an entry that
        is genuinely off-table and has a value to be placed by, since an entry
        without one falls back to being appended last.
        """
        sd = self._detector(self._three_two_sensor())
        table_ids = {e["id"] for e in sd._aspect_ratio_table()}
        self.assertNotIn(FULL_FRAME_RATIO_ID, table_ids)
        entry = sd.available_aspect_ratios("cam")[FULL_FRAME_RATIO_ID]
        self.assertIsInstance(entry["value"], float)
        neighbours = sorted(e["value"] for e in sd._aspect_ratio_table())
        self.assertTrue(min(neighbours) < entry["value"] < max(neighbours),
                        "1.50 falls inside the table's range, so it has a place in it")

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

    def test_the_native_ratio_is_always_on_for_a_new_camera(self):
        """"make sure this native aspect ratio is always active for newly
        connected cameras" -- operator, 2026-09-22. A camera nobody has
        configured yet resolves through _default_ratio_ids, and the native
        shape has to be in it however odd that shape is."""
        sd = self._detector(self._three_two_sensor())
        full_id, _ = sd.full_frame_ratio("cam")
        self.assertIn(full_id, sd._enabled_ratio_ids("cam"))
        self.assertTrue(sd._ratio_selection_is_derived("cam"),
                        "nobody chose these, so this is the new-camera path")

    def test_the_stock_rule_includes_every_slot_this_sensor_actually_offers(self):
        """Per-sensor-settings-backend, 2026-09-28: the stock rule is three
        independent membership tests (1.33:1, then 1.78:1, then the full
        frame), not two mutually-exclusive "shape"/"delivery" slots. This 3:2
        sensor happens to offer all three -- its own 1.33 crop, its own 1.78
        crop, AND an off-table full frame (1.50) -- so all three end up in
        the stock set, in that fixed check order. Superseded 2026-09-26's
        "full frame occupies the shape slot, so 1.33:1 is not selected by
        default": that was a property of the old two-slot mechanism, which
        this rule does not have any more."""
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
        self.assertEqual(available["1.78:1"]["label"], "1.78:1",
                         "an on-table full frame is not renamed")

    def test_an_on_table_full_frame_collapses_to_one_toggle(self):
        # This sensor's full frame IS 1.78:1 and it has no OTHER shape at all
        # -- so the "1.78:1 offered" check and the "full frame offered, not
        # already in" check both name the same id, and the stock rule is ONE
        # toggle, not two. (Compare test_the_stock_rule_includes_every_slot_
        # this_sensor_actually_offers, whose fixture also has an independent
        # 1.33 crop and therefore does end up with more than one.)
        modes = [self._mode(3840, 2160, sw=3856, sh=2180)]
        sd = self._detector(modes)
        self.assertEqual(sd.full_frame_ratio("cam")[0], "1.78:1")
        self.assertEqual(sd._default_ratio_ids("cam"), ["1.78:1"])

    # ---- no geometry: no full frame is knowable, so no toggle

    def test_a_sensor_with_no_crop_geometry_gets_no_full_toggle(self):
        modes = [self._mode(4056, 3040, geometry=False),
                 self._mode(2028, 1080, geometry=False)]
        sd = self._detector(modes)
        self.assertEqual(sd.full_frame_ratio("cam"), (None, None))
        self.assertNotIn(FULL_FRAME_RATIO_ID, sd.available_aspect_ratios("cam"))
        # No knowable full frame, and 1.78:1 is not offered either (this
        # camera's other shape is 1.88, home ratio 1.89:1 -- a DIFFERENT id,
        # "no closest" means nothing stands in for 1.78:1 any more). The
        # stock rule is 1.33:1 alone -- imx477's own real shape.
        self.assertEqual(sd._default_ratio_ids("cam"), ["1.33:1"])

    # ---- the invariant the whole design rests on

    def test_selecting_every_offered_ratio_still_loses_no_mode(self):
        # available_aspect_ratios() covers every mode by construction: each
        # mode contributes its own home id, so enabling all of them can never
        # drop a mode. This replaces _derived_default_ratio_ids (removed) --
        # available_aspect_ratios() is the one place that guarantee is stated
        # and tested now.
        for modes in (self._three_two_sensor(),
                      [self._mode(3840, 2160, sw=3856, sh=2180),
                       self._mode(2880, 2160, cx=480, sw=3856, sh=2180)],
                      [self._mode(4056, 3040, geometry=False)]):
            with self.subTest(modes=len(modes)):
                probe = self._detector(modes)
                offered = list(probe.available_aspect_ratios("cam"))
                sd = self._detector(modes, {"cam": offered})
                matches = sd._ratio_matches_for_camera("cam", modes)
                self.assertEqual(
                    [m for m in modes if id(m) not in matches], [],
                    "every offered ratio together must cover every mode, full frame included")
