import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.sensor_correction_factors import SENSOR_CORRECTION_FACTORS
from module.sensor_detect import SensorDetect


class SensorCorrectionFactorTests(unittest.TestCase):
    def test_stock_imx585_4k_25fps_uses_exfat_ssd_calibration(self):
        detector = SensorDetect.__new__(SensorDetect)
        detector.fps_correction_factor = SENSOR_CORRECTION_FACTORS

        self.assertEqual(
            detector.get_fps_correction_factor("imx585", 0, 25),
            0.998721,
        )
        self.assertEqual(
            detector.get_fps_correction_factor("imx585_mono", 0, 25),
            0.998721,
        )


if __name__ == "__main__":
    unittest.main()
