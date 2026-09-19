"""Geometry metadata used by the settings-editor mode catalogue.

The parser must understand both cinepi-raw crop syntaxes and must not invent
binning/full-frame information when a stock sensor driver does not provide it.
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
    Modes: 'SRGGB16_CSI2P' : 3840x2200 [30.00 fps - (0, 0)/3840x2160 crop] binning 1x1
                              2880x2200 [30.00 fps - (480, 0)/2880x2160 crop] binning 1x1
                              1920x1100 [30.00 fps - (0, 0)/1920x1080 crop] binning 2x2
                              1440x1100 [30.00 fps - (240, 0)/1440x1080 crop] binning 2x2
"""
        modes = d._parse_cinepi_output(out)["imx585"]
        by_size = {(m["width"], m["height"]): m for m in modes}
        self.assertEqual(by_size[(2880, 2200)]["crop_x"], 480)
        self.assertFalse(SensorDetect._mode_is_full(by_size[(2880, 2200)]))
        self.assertEqual(by_size[(2880, 2200)]["binning_x"], 1)
        self.assertTrue(SensorDetect._mode_is_full(by_size[(1920, 1100)]))
        self.assertEqual(by_size[(1920, 1100)]["binning_x"], 2)
        self.assertFalse(SensorDetect._mode_is_full(by_size[(1440, 1100)]))


    def test_geometry_on_continuation_line_is_attached_to_previous_mode(self):
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

    def test_custom_fps_override_does_not_duplicate_a_now-described_mode(self):
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


if __name__ == "__main__":
    unittest.main()
