import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.sensor_detect import SensorDetect


class SensorDatabaseTests(unittest.TestCase):
    def _detector_without_probe(self):
        detector = SensorDetect.__new__(SensorDetect)
        detector.sensor_database_file = "resources/sensors.json"
        detector.sensor_database = detector._load_sensor_database()
        detector.packing_info = detector._packing_info_from_database()
        return detector

    def test_loads_sensor_database_and_alias_packing(self):
        detector = self._detector_without_probe()

        self.assertIn("imx585", detector.sensor_database["sensors"])
        self.assertEqual(detector.packing_info["imx585_mono"], "U")

    def test_enriches_detected_mode_with_sustainable_fps(self):
        detector = self._detector_without_probe()
        mode = detector._mode_from_metadata_or_detected(
            camera_name="imx585_mono",
            width=1928,
            height=1090,
            bit_depth=12,
            fps_max=87,
        )

        sustainable_rows = mode["sustainable_fps"]
        self.assertTrue(
            any(
                row["filesystem"] == "ext4" and row["fps"] == 50
                for row in sustainable_rows
            )
        )


if __name__ == "__main__":
    unittest.main()
