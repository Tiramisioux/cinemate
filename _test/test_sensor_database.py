import json
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

    def test_log_encode_reader_returns_capability_data(self):
        """sensor_detect exposes sensors.json's log_encode block read-only --
        cinepi_multi/CLI wiring is Pass C2/C4. imx585 16-bit defaults to
        target 12 but can be forced to 10 (`set log 10`); every source depth
        this sensor supports maps to exactly one default, never a silent
        substitution when nothing matches.
        """
        detector = self._detector_without_probe()

        self.assertTrue(detector.supports_log_encode("imx585"))
        self.assertEqual(
            detector.get_log_encode_targets("imx585"),
            {
                16: {"valid": [10, 12], "default": 12},
                12: {"valid": [10], "default": 10},
            },
        )
        self.assertEqual(detector.get_log_encode_valid_targets("imx585", 16), [10, 12])
        self.assertEqual(detector.get_log_encode_default_target("imx585", 16), 12)
        self.assertEqual(detector.get_log_encode_default_target("imx585", 12), 10)
        self.assertEqual(detector.get_log_encode_black_level_16bit("imx585"), 3200)

        # Bare toggle (requested=None) resolves to the mode's default.
        self.assertEqual(detector.resolve_log_encode_target("imx585", 16), 12)
        self.assertEqual(detector.resolve_log_encode_target("imx585", 12), 10)
        # `set log 10` while in 16-bit ClearHDR overrides the 12 default.
        self.assertEqual(detector.resolve_log_encode_target("imx585", 16, requested=10), 10)
        # `set log 12` while in 12-bit mode has no matching spec (no 12to12)
        # -- resolves to None, never silently substituted to 10.
        self.assertIsNone(detector.resolve_log_encode_target("imx585", 12, requested=12))
        # A source depth this sensor never operates at (e.g. 8-bit) is
        # simply unsupported.
        self.assertIsNone(detector.resolve_log_encode_target("imx585", 8))

        # hdr=True (12-bit ClearHDR, CCMP-companded on-sensor) resolves the
        # same as plain 12-bit SDR -- P3 in cinepi-raw composes the CCMP
        # decompand with the log curve rather than refusing the source, so
        # this function no longer special-cases hdr at all. The default and
        # an explicit 10 both still work; 12 still has no composed spec.
        self.assertEqual(detector.resolve_log_encode_target("imx585", 12, hdr=True), 10)
        self.assertEqual(
            detector.resolve_log_encode_target("imx585", 12, requested=10, hdr=True), 10
        )
        self.assertIsNone(
            detector.resolve_log_encode_target("imx585", 12, requested=12, hdr=True)
        )
        # 16-bit ClearHDR was never companded (SRGGB16, no compander in the
        # path) -- hdr=True must not perturb it either.
        self.assertEqual(detector.resolve_log_encode_target("imx585", 16, hdr=True), 12)

        # Alias resolution matches the get_packing_for_platform precedent.
        self.assertTrue(detector.supports_log_encode("imx585_mono"))
        self.assertEqual(detector.get_log_encode_black_level_16bit("imx585_mono"), 3200)

        self.assertTrue(detector.supports_log_encode("imx283"))
        self.assertEqual(
            detector.get_log_encode_targets("imx283"),
            {12: {"valid": [10], "default": 10}},
        )
        self.assertEqual(detector.resolve_log_encode_target("imx283", 12), 10)
        # imx283 has 10-bit sensor modes but no 10-bit source spec.
        self.assertIsNone(detector.resolve_log_encode_target("imx283", 10))

        # Absence is the answer -- no special-casing for unsupported sensors.
        for unsupported in ("imx296", "imx296_mono", "imx477", "imx519", "does-not-exist"):
            self.assertFalse(detector.supports_log_encode(unsupported))
            self.assertEqual(detector.get_log_encode_targets(unsupported), {})
            self.assertEqual(detector.get_log_encode_valid_targets(unsupported, 12), [])
            self.assertIsNone(detector.get_log_encode_default_target(unsupported, 12))
            self.assertIsNone(detector.get_log_encode_black_level_16bit(unsupported))
            self.assertIsNone(detector.resolve_log_encode_target(unsupported, 12))

    # Sensor -> tuning-file stem covering every camera model sensors.json
    # tracks. imx519 has no shipped tuning file, so it can never clear the
    # black-level check below -- that absence is itself part of the data.
    TUNING_FILE_STEM_BY_SENSOR = {
        "imx477": "imx477",
        "imx296": "imx296",
        "imx585": "imx585",
        "imx283": "imx283",
    }

    @staticmethod
    def _tuning_black_level(stem: str) -> int:
        path = ROOT / "resources" / "tuning_files" / f"{stem}.json"
        data = json.loads(path.read_text())
        for algo in data.get("algorithms", []):
            if "rpi.black_level" in algo:
                return int(algo["rpi.black_level"]["black_level"])
        raise AssertionError(f"no rpi.black_level algorithm in {path}")

    def test_log_encode_support_matrix_is_derived_from_tuning_black_levels(self):
        """Reproduce CINEMATE-LOG-CINEMATE-PLAN.md §2 from data, not by typing
        in a sensor name list: a sensor is log-encode-supported iff its
        tuning-file black level (the 16-bit domain SensorBlackLevels reports)
        exactly matches another tracked sensor's -- the real-world fact that
        lets imx585 and imx283 share the same log spec files.
        """
        detector = self._detector_without_probe()
        sensors = detector.sensor_database["sensors"]

        tuning_black_level = {
            name: self._tuning_black_level(stem)
            for name, stem in self.TUNING_FILE_STEM_BY_SENSOR.items()
        }

        by_black_level: dict[int, list[str]] = {}
        for name, level in tuning_black_level.items():
            by_black_level.setdefault(level, []).append(name)

        # The supported cluster is whichever black level two or more tracked
        # sensors share. If a fork adds a fifth sensor at 3200 or changes
        # which two collide, this still derives the right set without
        # editing the test.
        clusters = [names for names in by_black_level.values() if len(names) > 1]
        self.assertEqual(len(clusters), 1, by_black_level)
        supported_names = set(clusters[0])
        self.assertEqual(supported_names, {"imx585", "imx283"})

        for name, sensor_info in sensors.items():
            has_block = isinstance(sensor_info.get("log_encode"), dict)
            if name in supported_names:
                self.assertTrue(has_block, f"{name} should declare log_encode")
                self.assertEqual(
                    sensor_info["log_encode"]["black_level_16bit"],
                    tuning_black_level[name],
                    f"{name} black_level_16bit must match its tuning file",
                )
            else:
                self.assertFalse(has_block, f"{name} should not declare log_encode")

        # Every non-clustered sensor sits far outside any plausible
        # quantisation tolerance (single-digit LSBs) from the supported
        # cluster's black level -- these are genuinely different sensors,
        # not a near-miss a guard should actually let through.
        cluster_level = tuning_black_level[next(iter(supported_names))]
        for name, level in tuning_black_level.items():
            if name in supported_names:
                continue
            self.assertGreater(
                abs(level - cluster_level), 32,
                f"{name} unexpectedly close to the supported black level",
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

    IMX585_HDR_LISTCAMERAS = """0 : imx585 [3840x2160 16-bit RGGB] (/base/axi/pcie@1000120000/rp1/i2c@70000/imx585@1a)
    Modes: 'SRGGB12_CSI2P' : 1928x1090 [25.00 fps - (0, 0)/3840x2160 crop]
                             3856x2180 [21.90 fps - (0, 0)/3840x2160 crop]
           'SRGGB16' : 1928x1090 [25.00 fps - (0, 0)/3840x2160 crop]
                       3856x2180 [21.90 fps - (0, 0)/3840x2160 crop]
"""

    def _detector_for_parse(self):
        import json
        from module.config_loader import strip_jsonc
        detector = self._detector_without_probe()
        settings = json.loads(strip_jsonc((ROOT / "settings.jsonc").read_text()))
        rc = settings.get("image_capture", {})
        detector.settings = settings
        detector.k_steps = rc.get("k_steps", [])
        detector.bit_depths = rc.get("bit_depths", [])
        detector.custom_modes = rc.get("custom_modes", {})
        detector.hdr_modes = SensorDetect._hdr_whitelist(rc.get("hdr", {}))
        detector.sensor_resolutions = {}
        return detector

    def _parse(self, detector, output, hdr_output=None):
        """Run a detector's parse → merge → finalize pipeline for one (or two)
        --list-cameras runs, mirroring detect_camera_model()."""
        base = detector._parse_cinepi_output(output, hdr=False)
        hdr = detector._parse_cinepi_output(hdr_output, hdr=True) if hdr_output else {}
        return detector._finalize_modes(detector._merge_mode_lists(base, hdr))

    def test_imx585_mode_table_is_stable(self):
        """Regression guard: with only the plain run, imx585 stays at exactly
        two 12-bit non-HDR modes — unaffected by any handling added for
        multi-bit-depth sensors like imx477."""
        d = self._detector_for_parse()
        parsed = self._parse(d, self.IMX585_LISTCAMERAS)["imx585"]
        table = {(m["width"], m["height"], m["bit_depth"], m["hdr"]) for m in parsed.values()}
        self.assertEqual(len(parsed), 2)
        self.assertEqual(table, {(3856, 2180, 12, False), (1928, 1090, 12, False)})

    def test_imx585_clearhdr_modes_merged_and_ordered(self):
        """The plain and --hdr sensor runs merge into one table ordered plain →
        12-bit HDR → 16-bit HDR, and the HDR modes carry hdr=True."""
        d = self._detector_for_parse()
        parsed = self._parse(d, self.IMX585_LISTCAMERAS, self.IMX585_HDR_LISTCAMERAS)["imx585"]
        ordered = [
            (m["width"], m["bit_depth"], m["hdr"]) for _, m in sorted(parsed.items())
        ]
        self.assertEqual(
            ordered,
            [
                (1928, 12, False),
                (3856, 12, False),
                (1928, 12, True),
                (3856, 12, True),
                (1928, 16, True),
                (3856, 16, True),
            ],
        )

    def test_non_hdr_sensor_not_doubled_by_hdr_probe(self):
        """A sensor that ignores --hdr sensor returns identical modes twice; the
        merge must collapse them back to a single non-HDR list."""
        d = self._detector_for_parse()
        # Same output for both runs (flag ignored by a non-HDR sensor).
        parsed = self._parse(d, self.IMX477_LISTCAMERAS, self.IMX477_LISTCAMERAS)["imx477"]
        self.assertTrue(all(m["hdr"] is False for m in parsed.values()))
        self.assertEqual(len(parsed), 10)             # not 20

    def test_imx477_multi_bitdepth_modes_are_parsed(self):
        """imx477 reports SRGGB8/10/12; the bit_depths=[10,12] filter keeps both
        the 10- and 12-bit copies of all five resolutions (8-bit dropped), so a
        resolution exists at two bit depths and the operator can reach either."""
        d = self._detector_for_parse()
        parsed = self._parse(d, self.IMX477_LISTCAMERAS)["imx477"]
        depths = sorted({m["bit_depth"] for m in parsed.values()})
        self.assertEqual(depths, [10, 12])            # 8-bit filtered out
        self.assertEqual(len(parsed), 10)             # 5 resolutions x 2 depths
        twins = {m["bit_depth"] for m in parsed.values()
                 if (m["width"], m["height"]) == (2028, 1080)}
        self.assertEqual(twins, {10, 12})


if __name__ == "__main__":
    unittest.main()
