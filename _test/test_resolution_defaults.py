import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.config_loader import _apply_settings_defaults
from module.sensor_detect import SensorDetect


class ResolutionDefaultsTests(unittest.TestCase):
    def test_runtime_defaults_include_4k_step(self):
        settings = _apply_settings_defaults({})

        self.assertIn(4.0, settings["resolutions"]["k_steps"])

    def test_stock_settings_include_4k_step(self):
        settings = json.loads(
            (ROOT / "resources/settings/settings_default.json").read_text(encoding="utf-8")
        )

        self.assertIn(4, settings["resolutions"]["k_steps"])

    def test_stock_filter_keeps_imx585_4k_mode(self):
        settings = json.loads(
            (ROOT / "resources/settings/settings_default.json").read_text(encoding="utf-8")
        )
        rc = settings["resolutions"]
        detector = SensorDetect.__new__(SensorDetect)
        detector.settings = settings
        detector.k_steps = rc["k_steps"]
        detector.bit_depths = rc["bit_depths"]
        detector.custom_modes = rc["custom_modes"]
        detector.min_frame_rate = rc.get("min_frame_rate", 20)
        detector.hdr_modes = rc.get("hdr", [])
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
