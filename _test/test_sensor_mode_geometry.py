"""Geometry metadata used by the settings-editor mode catalogue.

The parser must understand both cinepi-raw crop syntaxes and must not invent
binning/full-frame information when a stock sensor driver does not provide it.

WP-CM-10: the driver reports V4L2_SEL_TGT_CROP in native sensor coordinates
(WP-585-1), never in the mode's binned output domain. `crop_x`/`crop_y`/
`crop_width`/`crop_height` are therefore always sensor-side numbers -- a 2x2
binned full-field mode annotates its crop as the full ~3840x2160 sensor
window, not as the smaller 1920x1080 the mode actually outputs. The two
crop-annotation tests below used to encode the opposite (output-domain)
assumption and asserted conclusions that were only correct by coincidence
for the 1x1 rows in their fixtures; they are rewritten here to the
sensor-domain fixtures the driver actually emits.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.sensor_detect import SensorDetect


class SensorModeGeometryTests(unittest.TestCase):
    def _detector(self):
        d = SensorDetect.__new__(SensorDetect)
        d.custom_modes = {}
        d.k_steps = []
        d.bit_depths = []
        d.hdr_modes = {False, True}
        d.sensor_database_file = "resources/sensors.json"
        d.sensor_database = d._load_sensor_database()
        d.packing_info = d._packing_info_from_database()
        return d

    def test_legacy_crop_annotation_is_parsed(self):
        d = self._detector()
        out = """
0 : imx585 [3856x2180] (/base/imx585@1a)
    Modes: 'SRGGB12_CSI2P' : 3840x2160 [30.00 fps - (0, 0)/3840x2160 crop] binning 1x1
                              2880x2160 [30.00 fps - (480, 0)/2880x2160 crop] binning 1x1
                              1920x1080 [30.00 fps - (0, 0)/3840x2160 crop] binning 2x2
                              1440x1080 [30.00 fps - (240, 0)/2880x2160 crop] binning 2x2
"""
        modes = d._parse_cinepi_output(out)["imx585"]
        by_size = {(m["width"], m["height"]): m for m in modes}
        # 1x1 window: crop and output coincide, as always at 1x1.
        self.assertEqual(by_size[(2880, 2160)]["crop_x"], 480)
        self.assertFalse(SensorDetect._mode_is_full(by_size[(2880, 2160)]))
        self.assertEqual(by_size[(2880, 2160)]["binning_x"], 1)
        # 2x2 full-field: the crop is the *sensor-domain* full window
        # (3840x2160), not the 1920x1080 the mode actually outputs.
        self.assertEqual(by_size[(1920, 1080)]["crop_width"], 3840)
        self.assertEqual(by_size[(1920, 1080)]["crop_height"], 2160)
        self.assertTrue(SensorDetect._mode_is_full(by_size[(1920, 1080)]))
        self.assertEqual(by_size[(1920, 1080)]["binning_x"], 2)
        # 2x2 window: crop is the sensor-domain 2880x2160 window, not the
        # 1440x1080 output.
        self.assertEqual(by_size[(1440, 1080)]["crop_width"], 2880)
        self.assertFalse(SensorDetect._mode_is_full(by_size[(1440, 1080)]))

    def test_geometry_on_continuation_line_is_attached_to_previous_mode(self):
        # NOTE (WP-CM-10): left byte-for-byte as found. Its failure on this
        # base branch is pre-existing and unrelated to the crop-domain
        # defect this package fixes -- see the worker report for WP-CM-10.
        # It is not touched here: rewriting its fixture to exercise the
        # domain contract runs into a separate, pre-existing continuation-
        # line parsing defect (a crop/binning annotation's own "NxM" text
        # satisfies the same-line resolution regex, so the "attach to
        # last_mode" branch is never reached), which is outside this
        # package's spec.
        d = self._detector()
        out = """
0 : imx585 [3856x2180] (/base/imx585@1a)
    Modes: 'SRGGB16_CSI2P' : 3840x2200 [30.00 fps]
                              (0, 0)/3840x2160 crop binning 1x1
                              2880x2200 [30.00 fps]
                              mode-crop (480, 0)/2880x2160 crop
                              binning: 1x1
"""
        modes = d._parse_cinepi_output(out)["imx585"]
        by_size = {(m["width"], m["height"]): m for m in modes}
        self.assertEqual(by_size[(3840, 2200)]["crop_width"], 3840)
        self.assertEqual(by_size[(3840, 2200)]["crop_height"], 2160)
        self.assertEqual(by_size[(3840, 2200)]["binning_x"], 1)
        self.assertEqual(by_size[(2880, 2200)]["crop_x"], 480)
        self.assertEqual(by_size[(2880, 2200)]["crop_width"], 2880)
        self.assertEqual(by_size[(2880, 2200)]["binning_y"], 1)
        self.assertFalse(SensorDetect._mode_is_full(by_size[(2880, 2200)]))

    def test_full_2x2_mode_uses_sensor_domain_crop_directly(self):
        """A 2x2 full-field mode annotated `binning 2x2; mode-crop
        (0,0)/3840x2160` is full -- the crop is compared to the native
        array with no binning multiplication."""
        mode = {
            "crop_x": 0, "crop_y": 0, "crop_width": 3840, "crop_height": 2160,
            "binning_x": 2, "binning_y": 2,
            "sensor_width": 3856, "sensor_height": 2180,
        }
        self.assertTrue(SensorDetect._mode_is_full(mode))

    def test_2x2_window_is_not_full(self):
        """A 2x2 window annotated `(240,0)/2880x2160` is not full."""
        mode = {
            "crop_x": 240, "crop_y": 0, "crop_width": 2880, "crop_height": 2160,
            "binning_x": 2, "binning_y": 2,
            "sensor_width": 3856, "sensor_height": 2180,
        }
        self.assertFalse(SensorDetect._mode_is_full(mode))

    def test_1x1_4k_mode_is_unchanged(self):
        """A 1x1 4K mode's full-frame classification is unaffected by the
        sensor-domain fix, since output and crop already coincide at 1x1."""
        mode = {
            "crop_x": 0, "crop_y": 0, "crop_width": 3840, "crop_height": 2160,
            "binning_x": 1, "binning_y": 1,
            "sensor_width": 3856, "sensor_height": 2180,
        }
        self.assertTrue(SensorDetect._mode_is_full(mode))

    def test_missing_geometry_metadata_is_not_called_full_or_binned(self):
        d = self._detector()
        out = """
0 : imx477 [4056x3040] (/base/imx477@1a)
    Modes: 'SRGGB12_CSI2P' : 2028x1520 [40.00 fps]
                              4056x3040 [20.00 fps]
"""
        modes = d._parse_cinepi_output(out)["imx477"]
        for mode in modes:
            self.assertIsNone(mode.get("binning_x"))
            self.assertFalse(SensorDetect._mode_is_full(mode))

    def test_1to1_mode_with_no_crop_metadata_reports_the_transport_aspect(self):
        """Round 2, Defect D: with no crop annotation at all, the aspect
        field still has to fall back to the transport frame -- there is
        nothing better to fall back to. This is not "the fix" for that
        row (nothing can fix it until cinepi-raw reports geometry); it
        documents the floor active_picture_size() falls to, and pins the
        exact 1.02 the operator saw so a future geometry-reporting build is
        the only thing that can change it."""
        d = self._detector()
        d.settings = {}
        built = d._mode_from_metadata_or_detected(
            camera_name="imx283", width=3744, height=3664, bit_depth=12, fps_max=None,
        )
        self.assertEqual(round(built["width"] / built["height"], 2), 1.02)
        self.assertEqual(built["aspect"], 1.02)

    def test_aspect_divides_crop_by_binning_not_the_raw_crop_ratio(self):
        """Round 2, Defect B2's root cause, exercised through the real
        parse->mode path: asymmetric binning (2x1) means the sensor-window
        ratio (5472/3648 = 1.5) is NOT the delivered picture's aspect
        (2736/3648 = 0.75). Before this fix the aspect field used the raw
        crop ratio directly and would have reported 1.5 here."""
        d = self._detector()
        d.settings = {}
        built = d._mode_from_metadata_or_detected(
            camera_name="imx283", width=2736, height=3648, bit_depth=12, fps_max=None,
            extra={
                "crop_x": 0, "crop_y": 0, "crop_width": 5472, "crop_height": 3648,
                "binning_x": 2, "binning_y": 1,
            },
        )
        self.assertEqual(built["aspect"], 0.75)

    def test_explicit_active_annotation_drives_the_aspect_field(self):
        d = self._detector()
        d.settings = {}
        built = d._mode_from_metadata_or_detected(
            camera_name="imx283", width=2784, height=1828, bit_depth=12, fps_max=None,
            extra={"active_width": 2736, "active_height": 1824},
        )
        self.assertEqual(built["aspect"], round(2736 / 1824, 2))
        self.assertEqual(built["active_width"], 2736)
        self.assertEqual(built["active_height"], 1824)

    def test_custom_fps_override_does_not_duplicate_a_now_described_mode(self):
        d = self._detector()
        d.custom_modes = {
            "imx585": [{
                "width": 1440, "height": 1100, "bit_depth": 16,
                "fps_max": 25,
            }]
        }
        base = d._parse_cinepi_output("""
0 : imx585 [3856x2180] (/base/imx585@1a)
    Modes: 'SRGGB16_CSI2P' : 1440x1100 [30.00 fps - (240, 0)/1440x1080 crop] binning 2x2
""")
        modes = d._finalize_modes(d._merge_mode_lists(base, {}))["imx585"]
        matching = [m for m in modes.values() if (m["width"], m["height"]) == (1440, 1100)]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["fps_max"], 25)


class ActiveAnnotationParsingTests(unittest.TestCase):
    """Round 2, Defect D item 3: defensive parsing of the active-picture
    annotation a parallel cinepi-raw worker is adding to --list-cameras.
    Its exact wire format is not visible from this session -- see
    SensorDetect._ACTIVE_LABEL's own comment for the shape assumed
    ("active (left,top)/WxH", mirroring the existing "mode-crop" shape, or
    a bare "active WxH" with no origin). These tests pin that assumption
    and, more importantly, that it cannot be mistaken for the pre-existing
    "mode-crop" annotation when both share a line."""

    def _detector(self):
        d = SensorDetect.__new__(SensorDetect)
        d.custom_modes = {}
        d.k_steps = []
        d.bit_depths = []
        d.hdr_modes = {False, True}
        d.sensor_database_file = "resources/sensors.json"
        d.sensor_database = d._load_sensor_database()
        d.packing_info = d._packing_info_from_database()
        return d

    def test_active_rect_annotation_same_line_as_crop(self):
        d = self._detector()
        out = """
0 : imx283 [5472x3648] (/base/imx283@1a)
    Modes: 'SRGGB12_CSI2P' : 2784x1828 [36.00 fps - (108, 40)/5472x3648 crop] binning 2x2; active (48,0)/2736x1824
"""
        modes = d._parse_cinepi_output(out)["imx283"]
        mode = modes[0]
        # The pre-existing crop/binning parsing must still work unchanged.
        self.assertEqual((mode["crop_x"], mode["crop_y"]), (108, 40))
        self.assertEqual((mode["crop_width"], mode["crop_height"]), (5472, 3648))
        self.assertEqual((mode["binning_x"], mode["binning_y"]), (2, 2))
        # And the new active annotation must be read too, not swallowed by
        # the crop regex or vice versa.
        self.assertEqual((mode["active_left"], mode["active_top"]), (48, 0))
        self.assertEqual((mode["active_width"], mode["active_height"]), (2736, 1824))

    # NOTE: a continuation-line variant of this test (active on its own
    # line, separate from the resolution) is not included here. It would
    # exercise the exact same pre-existing, out-of-scope defect documented
    # on test_geometry_on_continuation_line_is_attached_to_previous_mode
    # above: any crop/binning/active annotation's own "NxM" text satisfies
    # the parser's same-line resolution regex, so the "not res" continuation
    # branch this package also feeds (see _parse_cinepi_output) is never
    # reached for realistic content. The parsing code added here still
    # populates that branch for when that defect is eventually fixed, but
    # it cannot be exercised until then.

    def test_bare_active_size_with_no_origin_is_accepted(self):
        d = self._detector()
        out = """
0 : imx283 [5472x3648] (/base/imx283@1a)
    Modes: 'SRGGB12_CSI2P' : 2784x1828 [36.00 fps - (108, 40)/5472x3648 crop] binning 2x2; active 2736x1824
"""
        modes = d._parse_cinepi_output(out)["imx283"]
        mode = modes[0]
        self.assertEqual((mode["active_width"], mode["active_height"]), (2736, 1824))
        self.assertIsNone(mode.get("active_left"))

    def test_no_active_annotation_leaves_it_unset(self):
        # Every cinepi-raw build this package has actually seen -- the
        # common case, and it must not crash or invent a value.
        d = self._detector()
        out = """
0 : imx283 [5472x3648] (/base/imx283@1a)
    Modes: 'SRGGB12_CSI2P' : 2784x1828 [36.00 fps - (108, 40)/5472x3648 crop] binning 2x2
"""
        modes = d._parse_cinepi_output(out)["imx283"]
        mode = modes[0]
        self.assertIsNone(mode.get("active_width"))
        self.assertIsNone(mode.get("active_height"))
        self.assertEqual((mode["crop_width"], mode["crop_height"]), (5472, 3648))


if __name__ == "__main__":
    unittest.main()
