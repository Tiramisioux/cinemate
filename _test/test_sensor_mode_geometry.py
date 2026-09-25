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
        """Geometry printed on its own line belongs to the mode above it.

        Red from WP-CM-10 until 2026-09-25: a crop annotation's own "/WxH" and
        a "binning NxN" token satisfied the same-line resolution search, so a
        continuation line carrying only geometry read as a brand-new mode and
        the "attach to last_mode" branch was never reached. The output size is
        now the first WxH that is neither (_output_size_on_line).
        """
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


class OutputSizeOnLineTests(unittest.TestCase):
    """_output_size_on_line: the first WxH that is an output size."""

    def test_crop_and_binning_sizes_are_not_output_sizes(self):
        for line in (
            "                              (0, 0)/3840x2160 crop binning 1x1",
            "                              mode-crop (480, 0)/2880x2160 crop",
            "                              binning: 1x1",
            "                              binning factor 2x2",
        ):
            self.assertIsNone(SensorDetect._output_size_on_line(line), line)

    def test_the_output_size_is_found_ahead_of_the_annotations(self):
        line = ("                             2784x1828 [51.80 fps - (0, 0)/5472x3648 crop;"
                " binning 2x2; mode-crop (0,0)/5472x3648]")
        m = SensorDetect._output_size_on_line(line)
        self.assertEqual(tuple(map(int, m.groups())), (2784, 1828))
        m = SensorDetect._output_size_on_line("    Modes: 'SRGGB16' : 3840x2200 [21.90 fps]")
        self.assertEqual(tuple(map(int, m.groups())), (3840, 2200))


if __name__ == "__main__":
    unittest.main()
