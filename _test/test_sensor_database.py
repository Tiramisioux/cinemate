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

    def _detector_with_modes(self):
        detector = self._detector_without_probe()
        detector.settings = {}

        def mode(cam, w, h, b, fps):
            return detector._mode_from_metadata_or_detected(
                camera_name=cam, width=w, height=h, bit_depth=b, fps_max=fps
            )

        detector.sensor_resolutions = {
            "imx477": {0: mode("imx477", 2028, 1080, 12, 50), 2: mode("imx477", 1332, 990, 10, 120)},
            "imx296": {0: mode("imx296", 1456, 1088, 10, 60)},
            "imx296_mono": {0: mode("imx296_mono", 1456, 1088, 10, 60)},
            "imx283": {0: mode("imx283", 2736, 1538, 12, 40)},
            "imx519": {0: mode("imx519", 1920, 1080, 12, 30)},
        }
        return detector

    def test_packing_for_platform_is_data_driven(self):
        d = self._detector_with_modes()
        # Pi 4 (VC4/Unicam) forces packed for the HQ + GS cameras (incl. the mono
        # alias and the 10-bit mode); Pi 5 keeps the sensor default.
        self.assertEqual(d.get_packing_for_platform("imx477", 0, is_pi4=True), "P")
        self.assertEqual(d.get_packing_for_platform("imx477", 0, is_pi4=False), "U")
        self.assertEqual(d.get_packing_for_platform("imx477", 2, is_pi4=True), "P")
        self.assertEqual(d.get_packing_for_platform("imx296", 0, is_pi4=True), "P")
        self.assertEqual(d.get_packing_for_platform("imx296_mono", 0, is_pi4=True), "P")
        self.assertEqual(d.get_packing_for_platform("imx296", 0, is_pi4=False), "U")
        # Sensors without an override keep their default packing on both platforms.
        self.assertEqual(d.get_packing_for_platform("imx283", 0, is_pi4=True), "U")
        self.assertEqual(d.get_packing_for_platform("imx283", 0, is_pi4=False), "U")
        self.assertEqual(d.get_packing_for_platform("imx519", 0, is_pi4=True), "P")
        self.assertEqual(d.get_packing_for_platform("imx519", 0, is_pi4=False), "P")

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
