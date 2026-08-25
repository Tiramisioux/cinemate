import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.dynamic_resolution import (
    choose_resolution,
    dynamic_resolution_indicator_active,
    dynamic_resolution_is_lower_substitute,
    max_fps_for_context,
)


IMX585_MODES = {
    0: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 87},
    1: {"width": 3840, "height": 2160, "bit_depth": 12, "fps_max": 40},
}

IMX585_DETECTED_ORDER_MODES = {
    0: {"width": 3856, "height": 2180, "bit_depth": 12, "fps_max": 43},
    1: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 50},
}

# Real imx477 mode table, `cinepi-raw --list-cameras` on hardware (dev 2026-08-24).
# The 10-bit and 12-bit modes at each resolution always tie on area; only the
# max-resolution pair matters for F-286, but the whole table is included so
# the fixture is a faithful stand-in for the live sensor, not a minimal repro.
IMX477_MODES = {
    0: {"width": 1332, "height": 990, "bit_depth": 10, "fps_max": 120.50},
    1: {"width": 2028, "height": 1080, "bit_depth": 10, "fps_max": 74.74},
    2: {"width": 2028, "height": 1520, "bit_depth": 10, "fps_max": 53.77},
    3: {"width": 4056, "height": 2160, "bit_depth": 10, "fps_max": 19.58},
    4: {"width": 4056, "height": 3040, "bit_depth": 10, "fps_max": 14.00},
    5: {"width": 1332, "height": 990, "bit_depth": 12, "fps_max": 101.68},
    6: {"width": 2028, "height": 1080, "bit_depth": 12, "fps_max": 62.81},
    7: {"width": 2028, "height": 1520, "bit_depth": 12, "fps_max": 45.19},
    8: {"width": 4056, "height": 2160, "bit_depth": 12, "fps_max": 16.39},
    9: {"width": 4056, "height": 3040, "bit_depth": 12, "fps_max": 11.72},
}


class DynamicResolutionTests(unittest.TestCase):
    def test_resolution_indicator_only_when_dynamic_substitute_is_active(self):
        self.assertFalse(
            dynamic_resolution_indicator_active(
                enabled=True,
                active=True,
                current_mode=0,
                desired_mode=0,
            )
        )
        self.assertTrue(
            dynamic_resolution_indicator_active(
                enabled=True,
                active=True,
                current_mode=1,
                desired_mode=0,
            )
        )
        self.assertFalse(
            dynamic_resolution_indicator_active(
                enabled=True,
                active=False,
                current_mode=1,
                desired_mode=0,
            )
        )
        self.assertFalse(
            dynamic_resolution_indicator_active(
                enabled=False,
                active=True,
                current_mode=1,
                desired_mode=0,
            )
        )

    def test_resolution_indicator_only_when_current_mode_is_lower_than_desired(self):
        self.assertTrue(
            dynamic_resolution_indicator_active(
                enabled=True,
                active=True,
                current_mode=0,
                desired_mode=1,
                sensor_modes=IMX585_MODES,
            )
        )
        self.assertFalse(
            dynamic_resolution_indicator_active(
                enabled=True,
                active=True,
                current_mode=1,
                desired_mode=0,
                sensor_modes=IMX585_MODES,
            )
        )
        self.assertFalse(
            dynamic_resolution_is_lower_substitute(
                sensor_modes=IMX585_MODES,
                current_mode=1,
                desired_mode=0,
            )
        )

    def test_switches_down_when_requested_fps_exceeds_desired_mode_max(self):
        choice = choose_resolution(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
            requested_fps=41,
        )

        self.assertIsNotNone(choice)
        self.assertEqual(choice.mode, 0)
        self.assertTrue(choice.dynamic_active)
        self.assertEqual(choice.fps_max, 87)
        self.assertEqual(choice.desired_fps_max, 40)

    def test_keeps_desired_mode_when_it_can_sustain_requested_fps(self):
        choice = choose_resolution(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
            requested_fps=40,
        )

        self.assertIsNotNone(choice)
        self.assertEqual(choice.mode, 1)
        self.assertFalse(choice.dynamic_active)

    def test_explicit_max_resolution_request_honors_bit_depth(self):
        # F-286. imx477 at 4056x3040: 10-bit (mode 4, fps_max 14.00) and
        # 12-bit (mode 9, fps_max 11.72) tie on area -- the sensor's max
        # resolution, so there is no larger mode either could be beaten by.
        # An explicit request for the 12-bit mode at a sustainable fps must
        # return the 12-bit mode, not silently substitute the faster 10-bit
        # one nothing asked for.
        choice = choose_resolution(
            sensor_modes=IMX477_MODES,
            desired_mode=9,
            requested_fps=10,
        )

        self.assertIsNotNone(choice)
        self.assertEqual(choice.mode, 9)
        self.assertEqual(IMX477_MODES[choice.mode]["bit_depth"], 12)
        self.assertFalse(choice.dynamic_active)

    def test_genuine_downgrade_prefers_bit_depth_over_unused_fps_headroom(self):
        # F-286 tie-break correction. requested_fps=20 excludes both
        # 4056x3040 and 4056x2160 variants (all four fps_max < 20), forcing
        # a real downgrade. The next-largest area, 2028x1520, has both
        # 10-bit (mode 2, fps_max 53.77) and 12-bit (mode 7, fps_max 45.19)
        # eligible and tied on area. Both already clear requested_fps=20,
        # so the extra headroom the 10-bit mode has over the 12-bit one is
        # unused -- bit depth should win the tie, not fps_max.
        choice = choose_resolution(
            sensor_modes=IMX477_MODES,
            desired_mode=9,
            requested_fps=20,
        )

        self.assertIsNotNone(choice)
        self.assertEqual(choice.mode, 7)
        self.assertEqual(IMX477_MODES[choice.mode]["bit_depth"], 12)
        self.assertTrue(choice.dynamic_active)

    def test_max_resolution_downshift_still_reaches_10bit_when_12bit_cannot_sustain_fps(self):
        # The 12-bit mode's own ceiling is 11.72fps; requesting faster than
        # that at the same desired mode must still fall through to the
        # tie-break (10-bit, faster) rather than return nothing.
        choice = choose_resolution(
            sensor_modes=IMX477_MODES,
            desired_mode=9,
            requested_fps=13,
        )

        self.assertIsNotNone(choice)
        self.assertEqual(choice.mode, 4)
        self.assertEqual(IMX477_MODES[choice.mode]["bit_depth"], 10)

    def test_keeps_manual_desired_mode_when_it_is_already_the_low_one(self):
        choice = choose_resolution(
            sensor_modes=IMX585_MODES,
            desired_mode=0,
            requested_fps=24,
        )

        self.assertIsNotNone(choice)
        self.assertEqual(choice.mode, 0)
        self.assertFalse(choice.dynamic_active)

    def test_returns_none_when_no_mode_can_sustain_requested_fps(self):
        choice = choose_resolution(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
            requested_fps=200,
        )

        self.assertIsNone(choice)

    HDR_MODES = {
        0: {"width": 1928, "height": 1090, "bit_depth": 12, "hdr": False, "fps_max": 87},
        1: {"width": 3856, "height": 2180, "bit_depth": 12, "hdr": False, "fps_max": 40},
        2: {"width": 1928, "height": 1090, "bit_depth": 12, "hdr": True, "fps_max": 50},
        3: {"width": 3856, "height": 2180, "bit_depth": 12, "hdr": True, "fps_max": 25},
    }

    def test_hdr_class_downshift_stays_within_hdr(self):
        # imx585 ClearHDR: the 12-bit HDR modes share width/height/bit_depth
        # with the plain 12-bit ones. A genuine HDR downshift must land on a
        # lower-resolution HDR mode, never cross over into the SDR class
        # (that would silently drop --hdr sensor).
        choice = choose_resolution(
            sensor_modes=self.HDR_MODES,
            desired_mode=3,
            requested_fps=41,
        )

        self.assertIsNotNone(choice)
        self.assertEqual(choice.mode, 2)
        self.assertTrue(self.HDR_MODES[choice.mode]["hdr"])

    def test_dynamic_max_fps_uses_lower_modes_own_ceiling(self):
        fps_max = max_fps_for_context(
            sensor_modes=IMX585_MODES,
            desired_mode=1,
        )

        self.assertEqual(fps_max, 87)

    def test_dynamic_max_fps_handles_live_imx585_detected_mode_order(self):
        fps_max = max_fps_for_context(
            sensor_modes=IMX585_DETECTED_ORDER_MODES,
            desired_mode=0,
        )
        high_fps_choice = choose_resolution(
            sensor_modes=IMX585_DETECTED_ORDER_MODES,
            desired_mode=0,
            requested_fps=45,
        )
        restored_choice = choose_resolution(
            sensor_modes=IMX585_DETECTED_ORDER_MODES,
            desired_mode=0,
            requested_fps=25,
        )

        self.assertEqual(fps_max, 50)
        self.assertIsNotNone(high_fps_choice)
        self.assertEqual(high_fps_choice.mode, 1)
        self.assertTrue(high_fps_choice.dynamic_active)
        self.assertIsNotNone(restored_choice)
        self.assertEqual(restored_choice.mode, 0)
        self.assertFalse(restored_choice.dynamic_active)

    def test_dynamic_max_fps_none_when_desired_mode_unknown(self):
        fps_max = max_fps_for_context(
            sensor_modes=IMX585_MODES,
            desired_mode=99,
        )

        self.assertIsNone(fps_max)


if __name__ == "__main__":
    unittest.main()
