import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.config_loader import _apply_settings_defaults, strip_jsonc
from module.sensor_detect import SensorDetect


class ResolutionDefaultsTests(unittest.TestCase):
    def test_runtime_defaults_include_4k_step(self):
        settings = _apply_settings_defaults({})

        self.assertIn(4.0, settings["image_capture"]["k_steps"])

    def test_stock_settings_include_4k_step(self):
        settings = json.loads(strip_jsonc(
            (ROOT / "resources/settings/settings_default.jsonc").read_text(encoding="utf-8")
        ))

        self.assertIn(4, settings["image_capture"]["k_steps"])

    def test_clearhdr_16bit_driver_binning_is_preserved(self):
        detector = SensorDetect.__new__(SensorDetect)
        detector.settings = {}
        detector.k_steps = []
        detector.bit_depths = []
        detector.custom_modes = {}
        detector.hdr_modes = [False, True]
        detector.clear_hdr_depths = {16}
        detector.sensor_database_file = "resources/sensors.json"
        detector.sensor_database = detector._load_sensor_database()
        detector.packing_info = detector._packing_info_from_database()

        output = """
0 : imx585 [3840x2160 16-bit RGGB] (/base/i2c/imx585@1a)
    Modes: 'SRGGB16' : 1440x1100 [30.00 fps - (240, 0)/1440x1080 crop; binning 2x2; mode-crop (480,0)/2880x2160]
                               1920x1100 [30.00 fps - (0, 0)/1920x1080 crop; binning 2x2; mode-crop (0,0)/3840x2160]
                               1920x1120 [57.69 fps - (960, 540)/1920x1080 crop; binning 1x1; mode-crop (960,540)/1920x1080]
                               2880x2200 [29.58 fps - (480, 0)/2880x2160 crop; binning 1x1; mode-crop (480,0)/2880x2160]
                               3840x2200 [21.99 fps - (0, 0)/3840x2160 crop; binning 1x1; mode-crop (0,0)/3840x2160]
"""
        parsed = detector._parse_cinepi_output(output, hdr=True)["imx585"]

        by_size = {(m["width"], m["height"]): m for m in parsed}
        self.assertEqual((2, 2), (by_size[(1440, 1100)]["binning_x"],
                                  by_size[(1440, 1100)]["binning_y"]))
        self.assertEqual((2, 2), (by_size[(1920, 1100)]["binning_x"],
                                  by_size[(1920, 1100)]["binning_y"]))
        self.assertEqual((1, 1), (by_size[(1920, 1120)]["binning_x"],
                                  by_size[(1920, 1120)]["binning_y"]))
        self.assertEqual((1, 1), (by_size[(3840, 2200)]["binning_x"],
                                  by_size[(3840, 2200)]["binning_y"]))

    def test_stock_filter_keeps_imx585_4k_mode(self):
        settings = json.loads(strip_jsonc(
            (ROOT / "resources/settings/settings_default.jsonc").read_text(encoding="utf-8")
        ))
        rc = settings["image_capture"]
        detector = SensorDetect.__new__(SensorDetect)
        detector.settings = settings
        detector.k_steps = rc["k_steps"]
        detector.bit_depths = rc["bit_depths"]
        detector.custom_modes = rc["custom_modes"]
        detector.hdr_modes = SensorDetect._hdr_whitelist(rc.get("hdr", {}))
        detector.sensor_database_file = "resources/sensors.json"
        detector.sensor_database = detector._load_sensor_database()
        detector.packing_info = detector._packing_info_from_database()

        base = detector._parse_cinepi_output(
            """
0 : imx585 [3856x2180] (/base/soc/i2c0mux/i2c@1/imx585@1a)
    Modes: 'SRGGB12_CSI2P' : 1928x1090 [50.00 fps - (0, 0)/3856x2180 crop]
                              3856x2180 [40.00 fps - (0, 0)/3856x2180 crop]
"""
        )
        parsed = detector._finalize_modes(detector._merge_mode_lists(base, {}))
        resolutions = {
            (mode["width"], mode["height"])
            for mode in parsed["imx585"].values()
        }

        self.assertIn((3856, 2180), resolutions)


if __name__ == "__main__":
    unittest.main()
