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


    IMX477_LISTCAMERAS = """0 : imx477 [4056x3040 12-bit RGGB] (/base/soc/i2c0mux/i2c@1/imx477@1a)
    Modes: 'SRGGB10_CSI2P' : 1332x990 [120.50 fps - (696, 528)/2664x1980 crop]
                             2028x1080 [74.74 fps - (0, 440)/4056x2160 crop]
                             2028x1520 [53.77 fps - (0, 0)/4056x3040 crop]
                             4056x2160 [19.58 fps - (0, 440)/4056x2160 crop]
                             4056x3040 [14.00 fps - (0, 0)/4056x3040 crop]
           'SRGGB12_CSI2P' : 1332x990 [101.68 fps - (696, 528)/2664x1980 crop]
                             2028x1080 [62.81 fps - (0, 440)/4056x2160 crop]
                             2028x1520 [45.19 fps - (0, 0)/4056x3040 crop]
                             4056x2160 [16.39 fps - (0, 440)/4056x2160 crop]
                             4056x3040 [11.72 fps - (0, 0)/4056x3040 crop]
           'SRGGB8' : 1332x990 [147.91 fps - (696, 528)/2664x1980 crop]
                      2028x1080 [92.27 fps - (0, 440)/4056x2160 crop]
                      2028x1520 [66.38 fps - (0, 0)/4056x3040 crop]
                      4056x2160 [24.32 fps - (0, 440)/4056x2160 crop]
                      4056x3040 [17.39 fps - (0, 0)/4056x3040 crop]
"""

    IMX585_LISTCAMERAS = """0 : imx585 [3840x2160 12-bit RGGB] (/base/axi/pcie@1000120000/rp1/i2c@70000/imx585@1a)
    Modes: 'SRGGB12_CSI2P' : 1928x1090 [50.00 fps - (0, 0)/3840x2160 crop]
                             3856x2180 [43.80 fps - (0, 0)/3840x2160 crop]
"""

    def _detector_for_parse(self):
        import json
        detector = self._detector_without_probe()
        settings = json.loads((ROOT / "src" / "settings.json").read_text())
        rc = settings.get("resolutions", {})
        detector.settings = settings
        detector.k_steps = rc.get("k_steps", [])
        detector.bit_depths = rc.get("bit_depths", [])
        detector.custom_modes = rc.get("custom_modes", {})
        detector.sensor_resolutions = {}
        return detector

    def test_imx585_mode_table_is_stable(self):
        """Regression guard: imx585's driver reports a single bit depth, so its
        parsed table must stay at exactly two 12-bit modes — unaffected by any
        handling added for multi-bit-depth sensors like imx477."""
        d = self._detector_for_parse()
        parsed = d._parse_cinepi_output(self.IMX585_LISTCAMERAS)["imx585"]
        table = {(m["width"], m["height"], m["bit_depth"]) for m in parsed.values()}
        self.assertEqual(len(parsed), 2)
        self.assertEqual(table, {(3856, 2180, 12), (1928, 1090, 12)})

    def test_imx477_multi_bitdepth_modes_are_parsed(self):
        """imx477 reports SRGGB8/10/12; the bit_depths=[10,12] filter keeps both
        the 10- and 12-bit copies of all five resolutions (8-bit dropped), so a
        resolution exists at two bit depths and the operator can reach either."""
        d = self._detector_for_parse()
        parsed = d._parse_cinepi_output(self.IMX477_LISTCAMERAS)["imx477"]
        depths = sorted({m["bit_depth"] for m in parsed.values()})
        self.assertEqual(depths, [10, 12])            # 8-bit filtered out
        self.assertEqual(len(parsed), 10)             # 5 resolutions x 2 depths
        twins = {m["bit_depth"] for m in parsed.values()
                 if (m["width"], m["height"]) == (2028, 1080)}
        self.assertEqual(twins, {10, 12})


if __name__ == "__main__":
    unittest.main()
