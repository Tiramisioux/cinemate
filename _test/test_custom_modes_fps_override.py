"""custom_modes must be able to correct a detected fps_max, not just add to
it (F-298). Before this fix, an entry whose dimensions matched an already-
detected mode was appended as a second, duplicate mode instead of
overriding the first -- so a sensor's advertised ceiling (an electrical
property, not a measure of what this storage/CPU can sustain) could never
actually be corrected downward from settings.jsonc.
"""

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.config_loader import strip_jsonc
from module.dynamic_resolution import choose_resolution
from module.sensor_detect import SensorDetect


IMX585_LIST_CAMERAS_OUTPUT = """
0 : imx585 [3856x2180] (/base/soc/i2c0mux/i2c@1/imx585@1a)
    Modes: 'SRGGB12_CSI2P' : 1928x1090 [87.00 fps - (0, 0)/3856x2180 crop]
                              3856x2180 [40.00 fps - (0, 0)/3856x2180 crop]
"""


def _build_detector(custom_modes):
    settings = json.loads(strip_jsonc(
        (ROOT / "resources/settings/settings_default.jsonc").read_text(encoding="utf-8")
    ))
    rc = settings["image_capture"]
    detector = SensorDetect.__new__(SensorDetect)
    detector.settings = settings
    detector.k_steps = rc["k_steps"]
    detector.bit_depths = rc["bit_depths"]
    detector.custom_modes = custom_modes
    detector.hdr_modes = SensorDetect._hdr_whitelist(rc.get("hdr", {}))
    detector.sensor_database_file = "resources/sensors.json"
    detector.sensor_database = detector._load_sensor_database()
    detector.packing_info = detector._packing_info_from_database()
    return detector


def _modes_by_resolution(detector):
    base = detector._parse_cinepi_output(IMX585_LIST_CAMERAS_OUTPUT)
    finalized = detector._finalize_modes(detector._merge_mode_lists(base, {}))
    return {
        (mode["width"], mode["height"]): mode
        for mode in finalized["imx585"].values()
    }, finalized["imx585"]


class CustomModesFpsOverrideTests(unittest.TestCase):
    def test_no_override_keeps_the_detected_ceiling(self):
        by_res, _ = _modes_by_resolution(_build_detector({}))
        self.assertEqual(by_res[(1928, 1090)]["fps_max"], 87.0)

    def test_matching_custom_mode_overrides_fps_max_in_place(self):
        detector = _build_detector({
            "imx585": [{"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 60}],
        })
        by_res, indexed = _modes_by_resolution(detector)

        self.assertEqual(by_res[(1928, 1090)]["fps_max"], 60)
        # Overriding must not produce a duplicate -- one entry per resolution.
        matching = [m for m in indexed.values() if (m["width"], m["height"]) == (1928, 1090)]
        self.assertEqual(len(matching), 1)

    def test_non_matching_custom_mode_still_appends(self):
        detector = _build_detector({
            "imx585": [{"width": 2028, "height": 1520, "bit_depth": 12, "fps_max": 30}],
        })
        by_res, _ = _modes_by_resolution(detector)

        self.assertIn((2028, 1520), by_res)
        self.assertEqual(by_res[(2028, 1520)]["fps_max"], 30)
        # The detected modes are both still there, untouched.
        self.assertEqual(by_res[(1928, 1090)]["fps_max"], 87.0)
        self.assertEqual(by_res[(3856, 2180)]["fps_max"], 40)

    def test_overriding_a_mode_lower_changes_which_mode_choose_resolution_picks(self):
        """The actual point of F-298: the operator found by trial that this
        storage can't sustain the sensor's advertised fps_max at its
        largest mode, so they cap it lower in settings.jsonc.
        choose_resolution() needs no change -- it still just looks at
        fps_max, which the sensor_detect.py fix above now lets settings.jsonc
        actually correct -- but the *selection* must consequently fall back
        to a smaller mode it would previously have skipped, once the big
        mode's capped fps_max can no longer sustain the request.

        This exercises choose_resolution() directly with hand-built mode
        dicts (same style as test_dynamic_resolution.py) rather than
        routing through _finalize_modes()'s k_steps/bit_depths filtering,
        which is orthogonal to this fix and would just be noise here.
        """
        # choose_resolution() never substitutes to a mode larger than
        # desired_mode, so desired_mode must be the largest here for the
        # two smaller modes to be valid fallback candidates at all.
        modes_before_override = {
            0: {"width": 3856, "height": 2180, "bit_depth": 12, "fps_max": 40},  # desired
            1: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 87},  # gets capped
            2: {"width": 964, "height": 545, "bit_depth": 12, "fps_max": 65},    # skipped before
        }
        before_choice = choose_resolution(
            sensor_modes=modes_before_override, desired_mode=0, requested_fps=60,
        )
        self.assertIsNotNone(before_choice)
        self.assertEqual(before_choice.mode, 1)  # 1928x1090 -- biggest eligible mode

        # settings.jsonc now caps mode 1's real-world fps_max at 55 (< the
        # sensor's advertised 87) -- exactly what the sensor_detect.py fix
        # above lets a matching custom_modes entry do in place.
        modes_after_override = dict(modes_before_override)
        modes_after_override[1] = dict(modes_before_override[1], fps_max=55)

        after_choice = choose_resolution(
            sensor_modes=modes_after_override, desired_mode=0, requested_fps=60,
        )
        self.assertIsNotNone(after_choice)
        self.assertEqual(after_choice.mode, 2)  # falls back to 964x545, skipped before


if __name__ == "__main__":
    unittest.main()
