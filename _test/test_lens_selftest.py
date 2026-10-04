"""module/lens/selftest.py: spotting the board's self-test, and refusing the rest.

The reaction to a detection is a calibration sweep through the lens's whole focus
range, so the tests that matter most are the ones that must stay silent: a hand
on the focus ring, CineMate's own moves, libcamera's autofocus scans. The
thresholds are named constants awaiting hardware gate G0.3; these tests use the
defaults and name what they rely on.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lens_fakes import frame  # noqa: E402

from module.lens import selftest  # noqa: E402
from module.lens.selftest import EVENT_FINISHED, EVENT_STARTED, SelfTestDetector  # noqa: E402

# A lens with a believable range of 0..1000: "near" is within 150 of an end.
RANGE = dict(focus_position_min=0, focus_position_max=1000)


def f(position, moving=True, **extra):
    return frame(focus_position_cur=position, moving=moving, **RANGE, **extra)


def run(detector, positions, *, t0=100.0, dt=0.25, moving=True, **extra):
    """Feed a position sequence at 4 Hz; return ([(t, event), ...], next t)."""
    events = []
    t = t0
    for position in positions:
        for event in detector.feed(t, f(position, moving=moving, **extra)):
            events.append((t, event))
        t += dt
    return events, t


def idle(detector, t, seconds, *, position=0, dt=0.25):
    """Feed quiet frames; return ([(t, event), ...], next t)."""
    events = []
    end = t + seconds
    while t < end:
        for event in detector.feed(t, f(position, moving=False)):
            events.append((t, event))
        t += dt
    return events, t


# min -> max -> min in coarse steps, the way the readme describes the test.
SELF_TEST = [300, 100, 400, 700, 950, 700, 400, 100]
NAMES = lambda events: [name for _, name in events]  # noqa: E731


class CalibratedLensSignatureTests(unittest.TestCase):
    def setUp(self):
        self.det = SelfTestDetector()

    def test_min_max_min_is_recognised(self):
        events, t = run(self.det, SELF_TEST)
        self.assertEqual(NAMES(events), [EVENT_STARTED])
        self.assertTrue(self.det.running)
        # It fires on the return to min, not before.
        self.assertEqual(events[0][0], 100.0 + 0.25 * (len(SELF_TEST) - 1))

    def test_it_finishes_once_the_lens_has_been_quiet(self):
        _, t = run(self.det, SELF_TEST)
        events, _ = idle(self.det, t, 3.0)
        self.assertEqual(NAMES(events), [EVENT_FINISHED])
        self.assertFalse(self.det.running)
        self.assertGreaterEqual(events[0][0] - (t - 0.25), selftest.SETTLE_S)

    def test_continued_activity_postpones_the_finish(self):
        # The aperture half of the test keeps the motor flag up for a few seconds.
        _, t = run(self.det, SELF_TEST)
        more, t = run(self.det, [0] * 8, t0=t)            # 2 s more of motor activity
        self.assertEqual(more, [])
        events, _ = idle(self.det, t, 3.0)
        self.assertEqual(NAMES(events), [EVENT_FINISHED])

    def test_a_test_that_never_goes_quiet_finishes_anyway(self):
        _, t = run(self.det, SELF_TEST)
        events, _ = run(self.det, [0] * 100, t0=t)        # 25 s of continuous motion
        self.assertEqual(NAMES(events), [EVENT_FINISHED])

    def test_started_and_finished_are_always_paired(self):
        events, t = run(self.det, SELF_TEST)
        more, _ = idle(self.det, t, 3.0)
        self.assertEqual(NAMES(events + more), [EVENT_STARTED, EVENT_FINISHED])

    def test_a_lens_resting_at_min_before_the_test_still_counts(self):
        # The board's first move is out from min; the touch of min is the idle
        # frame before it.
        self.det.feed(99.0, f(0, moving=False))
        events, _ = run(self.det, [300, 700, 950, 600, 200, 40])
        self.assertEqual(NAMES(events), [EVENT_STARTED])

    def test_it_can_run_twice(self):
        _, t = run(self.det, SELF_TEST)
        _, t = idle(self.det, t, 3.0)
        again, _ = run(self.det, SELF_TEST, t0=t + 1)
        self.assertEqual(NAMES(again), [EVENT_STARTED])

    def test_the_near_zones_are_a_fraction_of_the_range(self):
        # 150 is the edge of "near min" for a 0..1000 range.
        events, _ = run(self.det, [150, 600, 850, 600, 150])
        self.assertEqual(NAMES(events), [EVENT_STARTED])
        det = SelfTestDetector()
        events, _ = run(det, [151, 600, 849, 600, 151])
        self.assertEqual(events, [])


class CalibratedLensFalsePositiveTests(unittest.TestCase):
    def setUp(self):
        self.det = SelfTestDetector()

    def _silent(self, events, t, extra_idle=3.0):
        more, _ = idle(self.det, t, extra_idle)
        self.assertEqual(events + more, [])
        self.assertFalse(self.det.running)

    def test_one_manual_focus_pull_is_ignored(self):
        # A hand on the ring: the position sweeps min -> max, the motor flag stays down.
        events, t = run(self.det, [0, 100, 300, 500, 700, 900, 1000], moving=False)
        self._silent(events, t)

    def test_a_manual_rack_there_and_back_is_ignored_too(self):
        # Even the full min -> max -> min with a hand: no board motor activity.
        events, t = run(self.det, SELF_TEST, moving=False)
        self._silent(events, t)

    def test_a_one_way_motor_excursion_is_not_the_gesture(self):
        events, t = run(self.det, [100, 300, 500, 700, 950])
        self._silent(events, t)

    def test_max_then_min_then_max_is_the_wrong_shape(self):
        events, t = run(self.det, [950, 700, 100, 500, 950])
        self._silent(events, t)

    def test_host_commanded_moves_are_ignored(self):
        # CineMate pulls focus min -> max -> min itself, one command per leg,
        # each leg's motion inside the grace window of its command.
        events = []
        t = 100.0
        for target_leg in ([300, 100, 100, 100], [400, 800, 950, 950], [600, 200, 50, 50]):
            self.det.note_host_command(t)
            more, t = run(self.det, target_leg, t0=t)
            events += more
            more, t = idle(self.det, t, 1.0, position=target_leg[-1])
            events += more
        self._silent(events, t)

    def test_a_host_command_voids_a_half_seen_gesture(self):
        events, t = run(self.det, [300, 100, 500, 950])       # min -> max seen
        self.det.note_host_command(t)
        more, t = run(self.det, [600, 100], t0=t + 2.5)       # then a return to min, after grace
        self._silent(events + more, t)

    def test_a_slow_pattern_outside_the_window_is_ignored(self):
        # Same shape, but one step every 4 s: min -> max -> min takes > 15 s.
        events, t = run(self.det, [100, 950, 100], dt=8.0)
        self._silent(events, t)

    def test_activity_while_a_calibration_is_running_is_ignored(self):
        events, t = run(self.det, SELF_TEST, calibrating=2)
        self._silent(events, t)

    def test_autofocus_scans_are_ignored_while_the_detector_is_suspended(self):
        self.det.set_suspended(True, 100.0)
        events, t = run(self.det, SELF_TEST, t0=100.0)
        self.assertEqual(events, [])
        self.assertFalse(self.det.running)

    def test_resuming_after_autofocus_gives_the_motor_time_to_settle(self):
        self.det.set_suspended(True, 100.0)
        run(self.det, SELF_TEST, t0=100.0)
        self.det.set_suspended(False, 110.0)
        events, t = run(self.det, SELF_TEST, t0=110.5)         # inside the 2 s grace
        self.assertEqual(events, [])

    def test_suspension_drops_a_gesture_in_progress(self):
        run(self.det, [300, 100, 500, 950])
        self.det.set_suspended(True, 101.0)
        self.det.set_suspended(False, 101.1)
        events, _ = run(self.det, [100], t0=110.0)
        self.assertEqual(events, [])

    def test_a_flat_idle_lens_never_fires(self):
        events, _ = idle(self.det, 0.0, 120.0, position=500)
        self.assertEqual(events, [])


class UncalibratedLensSignatureTests(unittest.TestCase):
    """The board's range is 0..0: positions mean nothing, so count bursts."""

    def setUp(self):
        self.det = SelfTestDetector()

    def burst_frames(self, count):
        t = 100.0
        events = []
        for _ in range(count):
            for moving in (True, False):
                data = frame(moving=moving, focus_position_min=0, focus_position_max=0,
                             focus_position_cur=0)
                for event in self.det.feed(t, data):
                    events.append((t, event))
                t += 0.25
        return events, t

    def test_several_separate_bursts_are_recognised(self):
        events, _ = self.burst_frames(selftest.UNCALIBRATED_MIN_BURSTS)
        self.assertEqual(NAMES(events), [EVENT_STARTED])

    def test_one_fewer_is_not_enough(self):
        events, _ = self.burst_frames(selftest.UNCALIBRATED_MIN_BURSTS - 1)
        self.assertEqual(events, [])
        self.assertTrue(self.det.armed)

    def test_one_long_burst_is_one_burst(self):
        events = []
        for i in range(40):
            events += self.det.feed(100 + i * 0.25, frame(
                moving=True, focus_position_min=0, focus_position_max=0))
        self.assertEqual(events, [])

    def test_bursts_spread_over_more_than_the_window_do_not_add_up(self):
        t = 100.0
        events = []
        for _ in range(selftest.UNCALIBRATED_MIN_BURSTS + 2):
            for moving in (True, False):
                events += self.det.feed(t, frame(moving=moving, focus_position_min=0,
                                                 focus_position_max=0))
                t += 6.0
        self.assertEqual(events, [])

    def test_motion_the_host_asked_for_does_not_count(self):
        t = 100.0
        for _ in range(selftest.UNCALIBRATED_MIN_BURSTS + 2):
            self.det.note_host_command(t)
            for moving in (True, False):
                self.assertEqual(self.det.feed(t, frame(
                    moving=moving, focus_position_min=0, focus_position_max=0)), [])
                t += 0.25
            t += 2.5      # past the grace, so the next burst is not excused by it
        self.assertFalse(self.det.running)

    def test_it_is_suspended_with_autofocus_too(self):
        self.det.set_suspended(True, 100.0)
        events, _ = self.burst_frames(selftest.UNCALIBRATED_MIN_BURSTS + 3)
        self.assertEqual(events, [])

    def test_it_finishes_after_the_bursts_stop(self):
        events, t = self.burst_frames(selftest.UNCALIBRATED_MIN_BURSTS)
        more = []
        end = t + 3
        while t < end:
            more += [e for e in self.det.feed(t, frame(
                moving=False, focus_position_min=0, focus_position_max=0))]
            t += 0.25
        self.assertEqual(more, [EVENT_FINISHED])


class ArmedAndResetTests(unittest.TestCase):
    def test_armed_once_part_of_the_signature_has_been_seen(self):
        det = SelfTestDetector()
        self.assertFalse(det.armed)
        run(det, [300, 100])
        self.assertTrue(det.armed)

    def test_armed_state_expires_with_the_window(self):
        det = SelfTestDetector()
        run(det, [300, 100])
        # Quiet for longer than the window: the next frame notices it is stale.
        idle(det, 105.0, 20.0)
        self.assertFalse(det.armed)

    def test_reset_forgets_everything_including_a_running_test(self):
        det = SelfTestDetector()
        run(det, SELF_TEST)
        self.assertTrue(det.running)
        det.reset()
        self.assertFalse(det.running)
        self.assertFalse(det.armed)

    def test_thresholds_can_be_overridden_per_instance(self):
        det = SelfTestDetector(near_fraction=0.3)
        events, _ = run(det, [250, 600, 750, 600, 250])
        self.assertEqual(NAMES(events), [EVENT_STARTED])

    def test_a_motor_flag_is_required_by_default(self):
        self.assertTrue(selftest.REQUIRE_MOTOR_FLAG)

    def test_without_the_motor_flag_requirement_position_changes_count(self):
        # G0.3 may show the flag is not set during the self-test; the constant
        # then flips, and position motion alone must be enough.
        det = SelfTestDetector(require_motor_flag=False)
        events, _ = run(det, SELF_TEST, moving=False)
        self.assertEqual(NAMES(events), [EVENT_STARTED])


if __name__ == "__main__":
    unittest.main()
