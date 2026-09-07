import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.dynamic_resolution import (
    DYNAMIC_RESOLUTION_PRIORITIES,
    PRIORITY_MODE,
    PRIORITY_NONE,
    PRIORITY_RESOLUTION,
    choose_resolution,
    dynamic_resolution_indicator_active,
    dynamic_resolution_is_lower_substitute,
    max_fps_for_context,
    normalize_priority,
)


IMX585_MODES = {
    0: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 87},
    1: {"width": 3840, "height": 2160, "bit_depth": 12, "fps_max": 40},
}

IMX585_DETECTED_ORDER_MODES = {
    0: {"width": 3856, "height": 2180, "bit_depth": 12, "fps_max": 43},
    1: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 50},
}

# Three classes on an imx585 running the 7-mode driver: SDR, 12-bit ClearHDR,
# 16-bit ClearHDR -- the same three blocks sensor_detect lays the mode table
# out in, and the shape every ladder test below is written against.
IMX585_THREE_CLASS_MODES = {
    0: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 87},
    1: {"width": 3856, "height": 2180, "bit_depth": 12, "fps_max": 43},
    2: {"width": 1928, "height": 1090, "bit_depth": 12, "hdr": True, "fps_max": 60},
    3: {"width": 3856, "height": 2180, "bit_depth": 12, "hdr": True, "fps_max": 30},
    4: {"width": 1928, "height": 1090, "bit_depth": 16, "hdr": True, "fps_max": 40},
    5: {"width": 3856, "height": 2180, "bit_depth": 16, "hdr": True, "fps_max": 21},
}

# The same camera with 12-bit ClearHDR switched off in settings.jsonc, which
# is the configuration the ladder was asked for: two classes, two sizes each.
IMX585_TWO_CLASS_MODES = {
    0: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 87},
    1: {"width": 3856, "height": 2180, "bit_depth": 12, "fps_max": 40},
    2: {"width": 1928, "height": 1090, "bit_depth": 16, "hdr": True, "fps_max": 40},
    3: {"width": 3856, "height": 2180, "bit_depth": 16, "hdr": True, "fps_max": 21},
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

    def test_a_downshift_drops_resolution_and_never_bit_depth(self):
        # Mode 9's own ceiling is 11.72fps, so 13fps cannot be served at that
        # resolution. Mode 4 -- the same frame size at 10-bit -- would sustain
        # it, and used to be chosen. It is not chosen now: a substitution the
        # operator did not ask for may cost frame size, which they can see in
        # the readout, but not bit depth, which they cannot. The answer is the
        # largest 12-bit mode that clears the bar.
        choice = choose_resolution(
            sensor_modes=IMX477_MODES,
            desired_mode=9,
            requested_fps=13,
        )

        self.assertIsNotNone(choice)
        self.assertEqual(choice.mode, 8)
        self.assertEqual(IMX477_MODES[choice.mode]["bit_depth"], 12)
        self.assertTrue(choice.dynamic_active)

    def test_a_family_is_hdr_and_bit_depth_together(self):
        # A 16-bit HDR request that cannot be sustained walks down its own
        # class before it looks at any other one -- so the first substitute
        # is 16-bit HD, not the 12-bit HDR mode that would also serve the fps.
        modes = IMX585_THREE_CLASS_MODES

        choice = choose_resolution(sensor_modes=modes, desired_mode=5, requested_fps=30)
        self.assertEqual(choice.mode, 4)
        self.assertEqual(modes[choice.mode]["bit_depth"], 16)
        self.assertTrue(modes[choice.mode]["hdr"])
        self.assertFalse(choice.mode_class_changed)

        # Nothing in the 16-bit class reaches 45fps. Under "none" that is the
        # end of it -- the class is never left, so there is no answer.
        self.assertIsNone(
            choose_resolution(
                sensor_modes=modes,
                desired_mode=5,
                requested_fps=45,
                priority=PRIORITY_NONE,
            )
        )

        # Under the ladder there is one: the next class down, at the largest
        # size in it that clears the bar. 12-bit ClearHDR HD, not SDR --
        # a class is given up one step at a time, not all at once.
        crossed = choose_resolution(
            sensor_modes=modes, desired_mode=5, requested_fps=45
        )
        self.assertEqual(crossed.mode, 2)
        self.assertTrue(crossed.mode_class_changed)
        self.assertTrue(crossed.dynamic_active)

        # And no policy reaches *up* a class: an SDR selection stays SDR
        # however well an HDR mode would serve the frame rate.
        for priority in DYNAMIC_RESOLUTION_PRIORITIES:
            with self.subTest(priority=priority):
                self.assertEqual(
                    choose_resolution(
                        sensor_modes=modes,
                        desired_mode=1,
                        requested_fps=60,
                        priority=priority,
                    ).mode,
                    0,
                )

    def test_mode_priority_walks_the_ladder_the_operator_described(self):
        # 12-bit ClearHDR off, 16-bit 4K selected. Holding the mode class:
        # 16-bit 4K -> 16-bit HD -> (4K SDR) -> HD SDR. 4K SDR is on the
        # ladder below 16-bit HD but never wins, because they tie at 40fps
        # and the class-holding policy takes the richer one.
        modes = IMX585_TWO_CLASS_MODES
        landed = [
            choose_resolution(
                sensor_modes=modes,
                desired_mode=3,
                requested_fps=fps,
                priority=PRIORITY_MODE,
            )
            for fps in (21, 40, 87)
        ]
        self.assertEqual([c.mode for c in landed], [3, 2, 0])
        self.assertEqual([c.mode_class_changed for c in landed], [False, False, True])

    def test_resolution_priority_walks_the_ladder_the_operator_described(self):
        # Same camera, same selection, holding the frame size instead:
        # 16-bit 4K -> 4K SDR -> HD SDR. 16-bit HD is on this ladder too,
        # below 4K SDR -- and never wins, because 4K SDR already covers
        # every frame rate it could serve.
        modes = IMX585_TWO_CLASS_MODES
        landed = [
            choose_resolution(
                sensor_modes=modes,
                desired_mode=3,
                requested_fps=fps,
                priority=PRIORITY_RESOLUTION,
            )
            for fps in (21, 40, 87)
        ]
        self.assertEqual([c.mode for c in landed], [3, 1, 0])
        self.assertEqual([c.mode_class_changed for c in landed], [False, True, True])

    def test_mode_priority_answers_exactly_as_none_does_until_it_runs_out(self):
        # This is why "mode" is the default rather than "none": it exhausts
        # the desired mode's own class before it crosses anything, so every
        # request "none" can serve, it serves identically. It differs only
        # where "none" has no answer at all.
        #
        # "resolution" is deliberately not in this claim -- giving up the
        # class before the frame size is the whole point of it, so it crosses
        # at 25fps here, while the 16-bit class still has 40fps of HD left.
        modes = IMX585_THREE_CLASS_MODES
        for fps in (10, 21, 25, 30, 40, 45, 60, 87, 120):
            with self.subTest(fps=fps):
                locked = choose_resolution(
                    sensor_modes=modes,
                    desired_mode=5,
                    requested_fps=fps,
                    priority=PRIORITY_NONE,
                )
                if locked is None:
                    continue
                self.assertEqual(
                    choose_resolution(
                        sensor_modes=modes,
                        desired_mode=5,
                        requested_fps=fps,
                        priority=PRIORITY_MODE,
                    ).mode,
                    locked.mode,
                )

        # 25fps is where "resolution" parts company: it holds 4K and takes
        # the 12-bit ClearHDR mode, where the other two hold the 16-bit class
        # and take HD.
        self.assertEqual(
            choose_resolution(
                sensor_modes=modes,
                desired_mode=5,
                requested_fps=25,
                priority=PRIORITY_RESOLUTION,
            ).mode,
            3,
        )

    def test_a_pinned_class_is_never_left(self):
        # What a running take gets: the ladder is pinned to the mode actually
        # on the sensor, because crossing a class needs cinepi-raw relaunched
        # and a relaunch ends the take.
        modes = IMX585_TWO_CLASS_MODES
        self.assertIsNone(
            choose_resolution(
                sensor_modes=modes,
                desired_mode=3,
                requested_fps=87,
                restrict_to_family_of=3,
            )
        )
        # Pinned to a class the ladder has already dropped into, the answer
        # is the best mode in *that* class -- not a climb back up into the
        # desired one, which is just as much of a relaunch.
        pinned = choose_resolution(
            sensor_modes=modes,
            desired_mode=3,
            requested_fps=24,
            restrict_to_family_of=0,
        )
        self.assertEqual(pinned.mode, 1)
        self.assertTrue(pinned.mode_class_changed)

    def test_a_callers_pin_outranks_the_policy_under_every_policy(self):
        # This asserted the opposite until a review caught it, and the
        # inversion mattered: "none" used to DISCARD the caller's pin and fall
        # back to the desired mode's class. Mid-take that returned a 16-bit
        # ClearHDR mode while the sensor was running 12-bit SDR, and
        # _resolution_change_needs_restart() returns False while recording --
        # so it was applied with no relaunch and cinepi-raw kept writing the
        # old format under new metadata. A pin is a statement about what the
        # hardware can do right now; no policy may overrule it.
        for priority in DYNAMIC_RESOLUTION_PRIORITIES:
            with self.subTest(priority=priority):
                choice = choose_resolution(
                    sensor_modes=IMX585_TWO_CLASS_MODES,
                    desired_mode=3,
                    requested_fps=40,
                    priority=priority,
                    restrict_to_family_of=0,
                )
                self.assertEqual(choice.mode, 1)
                self.assertFalse(IMX585_TWO_CLASS_MODES[choice.mode].get("hdr", False))

        # With no pin, "none" still refuses to leave the selected class.
        self.assertEqual(
            choose_resolution(
                sensor_modes=IMX585_TWO_CLASS_MODES,
                desired_mode=3,
                requested_fps=40,
                priority=PRIORITY_NONE,
            ).mode,
            2,
        )

    def test_priority_is_decoded_from_whatever_the_operator_typed(self):
        for value in ("mode", "MODE", " Follow Mode ", "follow_mode", "1"):
            with self.subTest(value=value):
                self.assertEqual(normalize_priority(value), PRIORITY_MODE)
        for value in ("resolution", "res", "follow-resolution", "2"):
            with self.subTest(value=value):
                self.assertEqual(normalize_priority(value), PRIORITY_RESOLUTION)
        for value in ("none", "off", "family", "0"):
            with self.subTest(value=value):
                self.assertEqual(normalize_priority(value), PRIORITY_NONE)
        # Unset and unrecognised both fall back rather than raising: this is
        # read on the fps path and on the GUI redraw path.
        for value in (None, "", "sideways", object()):
            with self.subTest(value=value):
                self.assertEqual(normalize_priority(value), PRIORITY_MODE)
        self.assertIsNone(normalize_priority("sideways", default=None))

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

    def test_the_ceiling_is_read_from_the_same_ladder_the_choice_is(self):
        # The fps step table is built from this number, so it has to agree
        # with what choose_resolution() will actually do -- otherwise the dial
        # offers frame rates nothing can serve, or hides ones the ladder
        # would have reached. 16-bit 4K selected on the two-class imx585:
        # its own class tops out at 40, the whole ladder at 87.
        modes = IMX585_TWO_CLASS_MODES
        self.assertEqual(
            max_fps_for_context(
                sensor_modes=modes, desired_mode=3, priority=PRIORITY_NONE
            ),
            40,
        )
        for priority in (PRIORITY_MODE, PRIORITY_RESOLUTION):
            with self.subTest(priority=priority):
                self.assertEqual(
                    max_fps_for_context(
                        sensor_modes=modes, desired_mode=3, priority=priority
                    ),
                    87,
                )

    def test_a_pinned_class_lowers_the_ceiling_with_it(self):
        # The take-length ceiling: pinned to the 16-bit class, 40 is all that
        # is reachable without the relaunch that would end the take. Pinned
        # to the SDR class the ladder already dropped into, the full 87 is
        # back -- the pin is not a penalty, it is just where we are.
        modes = IMX585_TWO_CLASS_MODES
        self.assertEqual(
            max_fps_for_context(
                sensor_modes=modes, desired_mode=3, restrict_to_family_of=3
            ),
            40,
        )
        self.assertEqual(
            max_fps_for_context(
                sensor_modes=modes, desired_mode=3, restrict_to_family_of=0
            ),
            87,
        )

    def test_dynamic_max_fps_none_when_desired_mode_unknown(self):
        fps_max = max_fps_for_context(
            sensor_modes=IMX585_MODES,
            desired_mode=99,
        )

        self.assertIsNone(fps_max)


if __name__ == "__main__":
    unittest.main()
