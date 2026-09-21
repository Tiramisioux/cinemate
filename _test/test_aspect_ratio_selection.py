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
        # imx283 has no entry of its own and the global "default" is still the
        # shipped ["1.78:1"], so nobody chose anything for this camera and the
        # matcher does not narrow at all, and both of imx283's fixture modes survive (one
        # exactly 1.78, one exactly 2.39) -- same as if no aspect-ratio
        # filter had ever run. WP-CM-7 rework, blocking finding: this used
        # to assert only the 1.78 mode, which was the narrowing bug (the
        # near-tie matcher returning early on a non-empty `within` set
        # before the additive_fallback check ever ran).
        self.assertEqual(
            {(m["width"], m["height"]) for m in pruned["imx283"].values()},
            {(5472, 3080), (5472, 2288)},
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
    None). It never runs the *literal shipped default*,
    {"default": ["1.78:1"]}, through the matcher -- and that value is a
    present key on every fresh install, because
    resources/settings/settings_default.jsonc and settings.jsonc both ship
    it (WP-CM-6 item 1, "Ships as {"default": ["1.78:1"]}"). A present key
    means aspect_ratios_cfg is not None, so the ratio matcher in
    _finalize_modes actively runs on a fresh install too.

    For imx477 (tier B), none of its three stock modes is within
    ASPECT_RATIO_TOLERANCE of 1.78 (closest is the 2028x1080 mode at 1.87),
    so the matcher's own near-tie fallback used to narrow the table down to
    that one mode, silently dropping the 4:3 2028x1520 mode and the
    sensor's fastest mode, 1332x990@120fps -- contradicting
    ASPECT-RATIOS.md's "1.78:1 when nothing has been chosen, so a fresh
    camera behaves as it does today" and WP-CM-6's own compatibility
    clause.

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

    def _assert_all_stock_modes_survive(self, image_capture_cfg, source_label):
        modes = self._imx477_modes_from_database()
        self.assertEqual(
            {(m["width"], m["height"]) for m in modes},
            {(2028, 1080), (2028, 1520), (1332, 990)},
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
            {(2028, 1080), (2028, 1520), (1332, 990)},
            f"{source_label}: fresh-install default silently dropped an "
            f"imx477 stock mode (expected all 3, including the "
            f"1332x990@120fps mode)",
        )

    def test_shipped_settings_jsonc_default_keeps_every_stock_imx477_mode(self):
        from module.config_loader import load_settings  # noqa: PLC0415

        settings = load_settings(ROOT / "settings.jsonc")
        image_capture_cfg = settings["image_capture"]
        # The literal shipped default this finding is about -- a *present*
        # key, not the legacy absent-key case.
        self.assertEqual(image_capture_cfg.get("aspect_ratios"), {"default": ["1.78:1"]})
        self._assert_all_stock_modes_survive(image_capture_cfg, "settings.jsonc")

    def test_shipped_settings_default_jsonc_keeps_every_stock_imx477_mode(self):
        from module.config_loader import load_settings  # noqa: PLC0415

        # The fresh-install template: a brand-new settings.jsonc is this
        # file's content verbatim (WP-CM-6 item 1's own justification for
        # not setdefault'ing the keys in _apply_settings_defaults).
        settings = load_settings(ROOT / "resources" / "settings" / "settings_default.jsonc")
        image_capture_cfg = settings["image_capture"]
        self.assertEqual(image_capture_cfg.get("aspect_ratios"), {"default": ["1.78:1"]})
        self._assert_all_stock_modes_survive(image_capture_cfg, "settings_default.jsonc")


class ShippedDefaultPartialMatchRegressionTests(unittest.TestCase):
    """WP-CM-7 rework, blocking review finding: ShippedDefaultFreshInstallRegressionTests
    above only proves the all-or-nothing case (imx477: *no* mode is within
    ASPECT_RATIO_TOLERANCE of 1.78:1), where the pre-fix additive_fallback
    branch already engaged because `within` was empty. It never exercises
    the more common partial-match case, where *some* of a camera's stock
    modes are within tolerance of 1.78 and others are not -- there
    `within` is non-empty, so the pre-fix code returned early with
    `within` alone and silently dropped every mode outside it, even for
    the shipped default.

    imx283 (tier B/C) is exactly this case with real numbers from
    resources/sensors.json: three modes are ~1.78 (within tolerance) and
    two are 1.5 (not). Before the fix, the 1.5-aspect 2784x1828 12-bit
    mode vanished from the default-selected table on a fresh install even
    though it passes every pre-existing bit_depths/k_steps filter --
    contradicting ASPECT-RATIOS.md's "1.78:1 when nothing has been chosen,
    so a fresh camera behaves as it does today".

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

    def _assert_all_pre_existing_modes_survive(self, camera_name, expected_sizes,
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
            f"{source_label}/{camera_name}: fresh-install default silently "
            f"dropped a stock mode that passed bit_depths/k_steps -- the "
            f"default ratio selection must be additive, never narrowing",
        )

    def test_shipped_default_keeps_every_pre_existing_imx283_mode(self):
        from module.config_loader import load_settings  # noqa: PLC0415

        # Real numbers from resources/sensors.json's imx283 entry, narrowed
        # by today's bit_depths=[10,12,16]/k_steps=[1.5,2,3,4] alone (no
        # aspect-ratio filter): three modes at aspect 1.78 (within
        # tolerance of the default) and one at aspect 1.5 (2784x1828,
        # 12-bit -- the one that used to vanish).
        expected = {(2784, 1542, 12), (2784, 1828, 12), (3936, 2176, 10)}
        for settings_path, label in (
            (ROOT / "settings.jsonc", "settings.jsonc"),
            (ROOT / "resources" / "settings" / "settings_default.jsonc", "settings_default.jsonc"),
        ):
            settings = load_settings(settings_path)
            image_capture_cfg = settings["image_capture"]
            self.assertEqual(image_capture_cfg.get("aspect_ratios"), {"default": ["1.78:1"]})
            self._assert_all_pre_existing_modes_survive(
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
        self.assertEqual(image_capture_cfg.get("aspect_ratios"), {"default": ["1.78:1"]})
        self._assert_all_pre_existing_modes_survive(
            "imx296", expected, image_capture_cfg, "settings.jsonc",
        )


class ShippedDefaultAcrossANativelyDifferentSensorTests(unittest.TestCase):
    """The imx477 case above is a sensor whose closest mode is 1.87, a tenth away
    from the default's 1.78. This is the harder shape the reviewer asked for: a
    sensor whose ENTIRE family sits at a materially different native aspect.

    Every imx283 mode is about 1.5 or about 1.8, and the 5568x3664 and 2784x1828
    modes are 1.52 -- a quarter away from 1.78, and further from it than any
    imx477 mode. If the shipped default narrows to "the closest mode", a
    OneInchEye owner loses most of the sensor's table on a fresh install, having
    chosen nothing. The default must not be able to do that on any sensor.
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

    def _assert_every_mode_survives(self, settings_path, label):
        from module.config_loader import load_settings  # noqa: PLC0415

        image_capture_cfg = load_settings(settings_path)["image_capture"]
        self.assertEqual(image_capture_cfg.get("aspect_ratios"), {"default": ["1.78:1"]})

        modes = self._imx283_modes_from_database()
        self.assertGreaterEqual(
            len(modes), 6,
            "resources/sensors.json's imx283 entry changed shape -- update this test",
        )
        before = {(m["width"], m["height"], m["bit_depth"]) for m in modes}

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
            after, before,
            f"{label}: the shipped default dropped an imx283 mode. Every mode in "
            f"this sensor's family is far from 1.78, so a narrowing default takes "
            f"most of the table away from an operator who chose nothing.",
        )

    def test_shipped_settings_jsonc_keeps_every_imx283_mode(self):
        self._assert_every_mode_survives(ROOT / "settings.jsonc", "settings.jsonc")

    def test_shipped_settings_default_jsonc_keeps_every_imx283_mode(self):
        self._assert_every_mode_survives(
            ROOT / "resources" / "settings" / "settings_default.jsonc", "settings_default.jsonc")


if __name__ == "__main__":
    unittest.main()
