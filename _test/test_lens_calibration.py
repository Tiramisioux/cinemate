"""module/lens/calibration.py: validating a sweep and building the focus section.

``build_focus_section`` is pure, so the shapes of real runs are tested as plain
sample sequences. The headline case is the real run from hardware gate G0.2
(PLAN 2026-10-04, Sigma 18-35 f/1.8 Art, board lens id 112): the board sweeps for
~100 ms with the motor flag set, but position and range stay at 0 and the
distance stays at 0.28 m. That must be a clear failure, not a bogus map.
"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lens_fakes import (  # noqa: E402
    FakeBackend,
    FakeClock,
    encoder_sweep,
    frame,
    no_encoder_sweep,
    sigma_no_feedback_sweep,
)

from module.lens import calibration  # noqa: E402
from module.lens.calibration import (  # noqa: E402
    AF_ADVICE,
    CalibrationResult,
    Sample,
    build_focus_section,
    distance_cm_to_dioptre,
    lens_reports_no_position,
    run_calibration,
)
from module.lens.cef168 import Cef168Error  # noqa: E402
from module.lens.database import focus_map  # noqa: E402


def timed(frames, interval=0.02, start=0.02):
    return [Sample(round(start + i * interval, 4), f) for i, f in enumerate(frames)]


STAMP = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)


class DistanceTests(unittest.TestCase):
    def test_centimetres_to_dioptres(self):
        self.assertAlmostEqual(distance_cm_to_dioptre(28), 3.5714, places=3)
        self.assertAlmostEqual(distance_cm_to_dioptre(100), 1.0)

    def test_65535_is_infinity_and_zero_is_no_reading(self):
        self.assertEqual(distance_cm_to_dioptre(65535), 0.0)
        self.assertIsNone(distance_cm_to_dioptre(0))


class MultiPointTests(unittest.TestCase):
    """A lens with a distance encoder: the distance varies with the position."""

    def setUp(self):
        self.samples = timed(encoder_sweep())
        self.focus, self.reason = build_focus_section(
            self.samples, self.samples[-1].data, calibrated_at="2026-10-04T12:00:00Z")

    def test_it_builds_a_multi_point_map(self):
        self.assertEqual(self.reason, "")
        self.assertTrue(self.focus["distance_encoder"])
        self.assertGreaterEqual(len(self.focus["map"]) // 2, 3)

    def test_the_map_is_a_valid_libcamera_pwl(self):
        # dioptres strictly ascending, positions strictly descending
        pairs = focus_map(self.focus["map"])
        self.assertIsNotNone(pairs)

    def test_infinity_is_dioptre_zero_at_the_far_end_of_the_motor_range(self):
        self.assertEqual(self.focus["map"][0], 0.0)
        self.assertEqual(self.focus["dioptre_min"], 0.0)

    def test_the_nearest_point_sits_at_the_lowest_position(self):
        self.assertEqual(self.focus["map"][-1], 0)
        self.assertEqual(self.focus["dioptre_max"], self.focus["map"][-2])
        self.assertGreater(self.focus["dioptre_max"], 3.0)

    def test_the_stored_range_and_mfd_come_from_the_board(self):
        self.assertEqual((self.focus["position_min"], self.focus["position_max"]), (0, 1069))
        self.assertAlmostEqual(self.focus["mfd_m"], 1 / self.focus["dioptre_max"], places=2)
        self.assertEqual(self.focus["calibrated_at"], "2026-10-04T12:00:00Z")

    def test_the_lowest_position_wins_a_repeated_distance(self):
        # calibrate.cpp update(): the far-end plateau (65535 cm for many
        # positions) keeps its first, lowest position.
        samples = timed([
            frame(moving=True, calibrating=2, focus_position_cur=p, focus_distance_min=cm)
            for p, cm in [(0, 25), (400, 100), (800, 65535), (900, 65535), (1069, 65535)]
        ] + [frame(focus_position_cur=1069)] * 2, interval=0.1)
        focus, _ = build_focus_section(samples, samples[-1].data)
        self.assertEqual(focus["map"], [0.0, 800, 1.0, 400, 4.0, 0])

    def test_a_noisy_reading_does_not_drop_the_good_points_after_it(self):
        # One reading says position 5 at 1 dioptre: a greedy filter would then
        # throw away every later point. The longest consistent set is kept.
        readings = [(0, 25), (200, 50), (5, 100), (400, 200), (600, 500), (800, 65535)]
        samples = timed([
            frame(moving=True, calibrating=2, focus_position_cur=p, focus_distance_min=cm)
            for p, cm in readings
        ] + [frame(focus_position_cur=1069)] * 2, interval=0.1)
        focus, _ = build_focus_section(samples, samples[-1].data)
        positions = focus["map"][1::2]
        self.assertEqual(positions, sorted(positions, reverse=True))
        self.assertNotIn(5, positions)
        self.assertIn(400, positions)

    def test_step_frames_follow_the_slowest_move(self):
        for moving_time, expected in [(0, 4), (299, 4), (300, 5), (349, 5), (350, 6), (900, 6)]:
            frames = [f if f.calibrating == 0 else frame(
                moving=True, calibrating=2, moving_time=moving_time,
                focus_position_cur=f.focus_position_cur, focus_distance_min=f.focus_distance_min)
                for f in encoder_sweep()]
            samples = timed(frames)
            focus, _ = build_focus_section(samples, frame(moving_time=0))
            self.assertEqual(focus["step_frames"], expected, moving_time)


class TwoPointFallbackTests(unittest.TestCase):
    """No distance encoder: a constant distance, so the manual 2-point map."""

    def test_it_matches_the_contract_example_exactly(self):
        samples = timed(no_encoder_sweep(mfd_cm=28))
        focus, reason = build_focus_section(samples, samples[-1].data)
        self.assertEqual(reason, "")
        self.assertEqual(focus["map"], [0.0, 1037, 3.57, 0])     # PLAN section 3
        self.assertEqual((focus["dioptre_min"], focus["dioptre_max"]), (0.0, 3.57))
        self.assertFalse(focus["distance_encoder"])
        self.assertEqual(focus["mfd_m"], 0.28)
        self.assertEqual((focus["position_min"], focus["position_max"]), (0, 1069))

    def test_two_distinct_distances_are_still_not_enough_for_a_multi_point_map(self):
        samples = timed([frame(moving=True, calibrating=2, focus_position_cur=p,
                               focus_distance_min=cm)
                         for p, cm in [(0, 28), (300, 28), (600, 65535), (900, 65535)]]
                        + [frame(focus_position_cur=1069)] * 2, interval=0.1)
        focus, _ = build_focus_section(samples, samples[-1].data)
        self.assertFalse(focus["distance_encoder"])
        self.assertEqual(len(focus["map"]), 4)

    def test_zero_distance_means_no_mfd_unless_the_operator_supplies_one(self):
        samples = timed(no_encoder_sweep(mfd_cm=0))
        focus, reason = build_focus_section(samples, samples[-1].data)
        self.assertIsNone(focus)
        self.assertIn("minimum focus distance", reason)
        focus, reason = build_focus_section(samples, samples[-1].data, mfd_m=0.45)
        self.assertEqual(reason, "")
        self.assertEqual(focus["map"], [0.0, 1037, 2.22, 0])
        self.assertEqual(focus["mfd_m"], 0.45)

    def test_a_remembered_mfd_is_only_a_fallback(self):
        silent = timed(no_encoder_sweep(mfd_cm=0))
        focus, _ = build_focus_section(silent, silent[-1].data, fallback_mfd_m=0.5)
        self.assertEqual(focus["map"][2], 2.0)
        reporting = timed(no_encoder_sweep(mfd_cm=28))
        focus, _ = build_focus_section(reporting, reporting[-1].data, fallback_mfd_m=0.5)
        self.assertEqual(focus["map"][2], 3.57)

    def test_an_operator_supplied_mfd_beats_the_boards(self):
        samples = timed(no_encoder_sweep(mfd_cm=28))
        focus, _ = build_focus_section(samples, samples[-1].data, mfd_m=0.5)
        self.assertEqual(focus["map"][2], 2.0)


class RealSigmaRunTests(unittest.TestCase):
    """PLAN G0.2, 2026-10-04: the lens (id 112) never reports a focus position."""

    def setUp(self):
        self.samples = timed(sigma_no_feedback_sweep())
        self.final = self.samples[-1].data

    def test_the_real_frames_are_what_the_report_describes(self):
        busy = self.samples[0].data
        self.assertEqual((busy.lens_id, busy.moving, busy.calibrating, busy.moving_time), (112, True, 2, 98))
        self.assertEqual((busy.focus_position_min, busy.focus_position_max, busy.focus_position_cur),
                         (0, 0, 0))
        self.assertEqual((busy.focus_distance_min, busy.focus_distance_max), (28, 28))
        self.assertEqual((self.final.calibrating, self.final.focus_position_max), (0, 0))

    def test_no_focus_section_is_built_for_it(self):
        focus, reason = build_focus_section(self.samples, self.final)
        self.assertIsNone(focus)
        self.assertEqual(reason, calibration.NO_POSITION_REASON)

    def test_it_is_recognised_as_a_lens_with_no_position_feedback(self):
        self.assertTrue(lens_reports_no_position(self.samples, self.final))

    def test_the_reason_says_what_happened_and_what_to_try(self):
        _, reason = build_focus_section(self.samples, self.final)
        self.assertIn("never reported a focus position", reason)
        self.assertIn("AF/MF switch", reason)
        self.assertIn("iris is unaffected", reason)

    def test_running_it_end_to_end_produces_the_same_verdict(self):
        backend = FakeBackend(frame(lens_id=112, focus_position_max=0, focus_position_cur=0))
        backend.sweep = sigma_no_feedback_sweep()
        clock = FakeClock()
        result = run_calibration(backend, clock=clock, sleep=clock.sleep, now=lambda: STAMP)
        self.assertFalse(result.ok)
        self.assertTrue(result.no_position_feedback)
        self.assertIsNone(result.focus)
        self.assertEqual(result.reason, calibration.NO_POSITION_REASON)
        self.assertEqual(backend.calibrate_calls, 1)
        # ~100 ms of sweep, as measured
        self.assertAlmostEqual(result.stats["sweep_s"], 0.08, delta=0.03)
        self.assertEqual(result.stats["observed_position_max"], 0)


class OtherFailureTests(unittest.TestCase):
    def test_a_lens_that_stays_put_but_has_a_stored_range_is_told_to_flip_the_switch(self):
        # Same ~100 ms, position stuck -- but the board still holds a range from
        # an earlier calibration: not a lens without feedback, a lens that did not move.
        frames = [frame(moving=True, calibrating=2, focus_position_cur=300,
                        focus_distance_min=28) for _ in range(5)]
        frames += [frame(focus_position_cur=300, focus_distance_min=28)] * 2
        samples = timed(frames)
        focus, reason = build_focus_section(samples, samples[-1].data)
        self.assertIsNone(focus)
        self.assertIn("did not move", reason)
        self.assertIn(AF_ADVICE, reason)
        self.assertFalse(lens_reports_no_position(samples, samples[-1].data))

    def test_a_board_that_never_enters_the_calibrating_state(self):
        samples = timed([frame(focus_position_cur=0, focus_position_max=0) for _ in range(6)])
        focus, reason = build_focus_section(samples, samples[-1].data)
        self.assertIsNone(focus)
        self.assertIn("never started", reason)
        self.assertIn(AF_ADVICE, reason)
        self.assertFalse(lens_reports_no_position(samples, samples[-1].data))

    def test_a_sweep_too_short_to_be_real(self):
        # Position jumps a lot, but in 40 ms: not a sweep.
        samples = timed([
            frame(moving=True, calibrating=2, focus_position_cur=0),
            frame(moving=True, calibrating=2, focus_position_cur=1000),
            frame(focus_position_cur=1000),
        ])
        focus, reason = build_focus_section(samples, samples[-1].data)
        self.assertIsNone(focus)
        self.assertIn("did not move", reason)

    def test_a_lens_that_covers_only_part_of_its_range(self):
        frames = [frame(moving=True, calibrating=2, focus_position_cur=p, focus_distance_min=28)
                  for p in range(0, 300, 10)]
        frames += [frame(focus_position_cur=300, focus_position_max=1069)] * 2
        samples = timed(frames)
        focus, reason = build_focus_section(samples, samples[-1].data)
        self.assertIsNone(focus)
        self.assertIn("only part of its range", reason)

    def test_no_samples(self):
        focus, reason = build_focus_section([], frame())
        self.assertIsNone(focus)
        self.assertIn("No frames", reason)

    def test_a_board_that_reports_no_range_after_a_real_sweep(self):
        frames = [frame(moving=True, calibrating=2, focus_position_cur=p, focus_distance_min=28,
                        focus_position_max=0) for p in range(0, 400, 10)]
        frames += [frame(focus_position_cur=390, focus_position_max=0)] * 2
        samples = timed(frames)
        focus, reason = build_focus_section(samples, samples[-1].data)
        self.assertIsNone(focus)
        self.assertIn("no usable focus range", reason)


class RunCalibrationTests(unittest.TestCase):
    def _run(self, backend, **kwargs):
        clock = FakeClock()
        kwargs.setdefault("now", lambda: STAMP)
        return run_calibration(backend, clock=clock, sleep=clock.sleep, **kwargs), clock

    def test_a_good_sweep_with_an_encoder(self):
        backend = FakeBackend()
        backend.sweep = encoder_sweep()
        result, _ = self._run(backend)
        self.assertTrue(result.ok, result.reason)
        self.assertEqual(result.reason, "")
        self.assertTrue(result.focus["distance_encoder"])
        self.assertEqual(result.focus["calibrated_at"], "2026-10-04T12:00:00Z")
        self.assertGreater(len(result.samples), 40)
        self.assertEqual(backend.calibrate_calls, 1)

    def test_a_good_sweep_without_an_encoder_uses_the_fallback(self):
        backend = FakeBackend()
        backend.sweep = no_encoder_sweep()
        result, _ = self._run(backend)
        self.assertTrue(result.ok, result.reason)
        self.assertEqual(result.focus["map"], [0.0, 1037, 3.57, 0])

    def test_it_polls_every_twenty_milliseconds(self):
        backend = FakeBackend()
        backend.sweep = no_encoder_sweep()
        result, _ = self._run(backend)
        gaps = {round(b.t - a.t, 3) for a, b in zip(result.samples, result.samples[1:])}
        self.assertEqual(gaps, {0.02})

    def test_it_keeps_polling_through_the_initial_idle_frames(self):
        # calibrate.cpp's 100 ms grace: the board can read calibrating==0 for a
        # moment after the command. The sweep that follows must still be caught.
        backend = FakeBackend()
        backend.sweep = [frame(focus_position_cur=0)] * 3 + no_encoder_sweep()
        result, _ = self._run(backend)
        self.assertTrue(result.ok, result.reason)

    def test_it_stops_at_the_grace_when_nothing_ever_starts(self):
        backend = FakeBackend(frame(focus_position_max=0))
        result, clock = self._run(backend)
        self.assertFalse(result.ok)
        self.assertIn("never started", result.reason)
        self.assertFalse(result.no_position_feedback)
        self.assertAlmostEqual(result.duration_s, 0.1, delta=0.03)

    def test_the_progress_callback_sees_every_frame(self):
        backend = FakeBackend()
        backend.sweep = no_encoder_sweep()
        seen = []
        result, _ = self._run(backend, on_sample=seen.append)
        self.assertEqual(len(seen), len(result.samples))

    def test_a_failing_progress_callback_does_not_stop_the_sweep(self):
        backend = FakeBackend()
        backend.sweep = no_encoder_sweep()

        def broken(sample):
            raise RuntimeError("gui blew up")

        result, _ = self._run(backend, on_sample=broken)
        self.assertTrue(result.ok)

    def test_a_calibrate_command_that_fails_is_a_reason_not_an_exception(self):
        backend = FakeBackend()

        def refuse():
            raise Cef168Error("EIO on write")

        backend.calibrate = refuse
        result, _ = self._run(backend)
        self.assertFalse(result.ok)
        self.assertIn("Could not start calibration", result.reason)
        self.assertIn("EIO", result.reason)

    def test_a_brief_read_glitch_mid_sweep_is_tolerated(self):
        backend = FakeBackend()
        backend.sweep = no_encoder_sweep()
        real_read = backend.read_data
        calls = {"n": 0}

        def glitchy():
            calls["n"] += 1
            if calls["n"] in (5, 6):
                raise Cef168Error("EIO")
            return real_read()

        backend.read_data = glitchy
        result, _ = self._run(backend)
        self.assertTrue(result.ok, result.reason)

    def test_losing_the_board_mid_sweep_is_reported(self):
        backend = FakeBackend()
        backend.sweep = no_encoder_sweep()
        real_read = backend.read_data
        calls = {"n": 0}

        def dies():
            calls["n"] += 1
            if calls["n"] > 4:
                raise Cef168Error("EIO")
            return real_read()

        backend.read_data = dies
        result, _ = self._run(backend)
        self.assertFalse(result.ok)
        self.assertIn("Lost contact", result.reason)

    def test_a_sweep_that_never_ends_times_out(self):
        backend = FakeBackend(frame(moving=True, calibrating=2, focus_position_cur=0))
        result, _ = self._run(backend, timeout_s=1.0)
        self.assertFalse(result.ok)
        self.assertIn("did not finish", result.reason)

    def test_it_can_be_stopped(self):
        backend = FakeBackend(frame(moving=True, calibrating=2))
        result, _ = self._run(backend, should_stop=lambda: True)
        self.assertFalse(result.ok)
        self.assertIn("stopped", result.reason)

    def test_the_result_class_defaults(self):
        result = CalibrationResult(True)
        self.assertEqual((result.reason, result.focus, result.samples, result.stats), ("", None, [], {}))
        self.assertFalse(result.no_position_feedback)


if __name__ == "__main__":
    unittest.main()
