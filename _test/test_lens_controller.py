"""module/lens/controller.py: detection, selection, commands, calibration, autofocus.

Everything runs against fakes (a scripted adapter, a Redis that dedups like the
real one, a clock that only moves when told to) and drives the controller with
``poll_once()``, so no thread and no hardware is involved. One test starts the
real thread.
"""
import json
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lens_fakes  # noqa: E402
from lens_fakes import (  # noqa: E402
    FakeBackend,
    FakeClock,
    FakeRedis,
    encoder_sweep,
    frame,
    no_encoder_sweep,
    sigma_no_feedback_sweep,
)

from module.lens import controller as controller_module  # noqa: E402
from module.lens.controller import LensController  # noqa: E402
from module.lens.database import LensDatabase  # noqa: E402

TWO_POINT_FOCUS = {
    "calibrated_at": "2026-10-04T12:00:00Z", "position_min": 0, "position_max": 1069,
    "mfd_m": 0.28, "distance_encoder": False, "map": [0.0, 1037, 3.57, 0],
    "dioptre_min": 0.0, "dioptre_max": 3.57, "step_frames": 4,
}


def saved_entry(name="Sigma 18-35 f/1.8", lens_id=235, **extra):
    base = {"name": name, "lens_id": lens_id, "aperture": {"min": 1.8, "max": 16.0,
                                                           "source": "manual"},
            "last_iris": None, "focus": None}
    base.update(extra)
    return base


class ControllerCase(unittest.TestCase):
    """A controller wired to fakes. ``self.poll(n)`` advances the clock a poll
    interval at a time and polls."""

    DETECT_ON_START = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = LensDatabase(Path(self._tmp.name) / "lenses.json",
                               now=lambda: datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc))
        self.clock = FakeClock()
        self.redis = FakeRedis({"lens_control": "1"})
        self.backend = FakeBackend(frame(lens_id=235))
        self.factory_result = (self.backend, "") if self.DETECT_ON_START else (None, "no adapter")
        self.factory_calls = []
        self.restarts = []
        self.ctrl = self.make()

    def make(self, **kwargs):
        kwargs.setdefault("request_camera_restart", self.restarts.append)
        return LensController(self.redis, database=self.db, backend_factory=self._factory,
                              clock=self.clock, sleep=self.clock.sleep, **kwargs)

    def _factory(self, port, cameras):
        self.factory_calls.append((port, cameras))
        return self.factory_result

    # -- helpers --------------------------------------------------------------

    def poll(self, count=1, step=0.25):
        for _ in range(count):
            self.ctrl.poll_once()
            self.clock.advance(step)

    def value(self, key):
        return self.redis.cache.get(key)

    def state(self):
        return self.value("lens_state")

    def message(self):
        return self.value("lens_message")

    def toggle(self, on):
        self.redis.set_value("lens_control", "1" if on else "0")

    def set_rec(self, on):
        self.redis.set_value("rec", "1" if on else "0")


# ── detection ───────────────────────────────────────────────────────────────

class DetectionTests(ControllerCase):
    DETECT_ON_START = False

    def test_an_absent_adapter_is_reported_with_its_reason(self):
        self.poll()
        self.assertEqual(self.value("lens_detected"), "0")
        self.assertEqual(self.state(), "absent")
        self.assertIn("no adapter", self.message())
        self.assertEqual(self.value("lens_provenance"), "")
        self.assertEqual(self.value("lens_port"), "")
        self.assertEqual(self.value("lens_id"), "")
        self.assertFalse(self.ctrl.effective())

    def test_the_toggle_cannot_be_switched_on_without_the_adapter(self):
        self.redis.cache.pop("lens_control")
        self.poll()
        ok, message = self.ctrl.set_enabled(True)
        self.assertFalse(ok)
        self.assertIn("no adapter", message)
        self.assertNotIn("lens_control", self.redis.cache)       # D1: nothing written
        self.assertFalse(self.ctrl.enabled())

    def test_switching_off_always_works(self):
        ok, _ = self.ctrl.set_enabled(False)
        self.assertTrue(ok)
        self.assertEqual(self.value("lens_control"), "0")

    def test_a_persisted_toggle_survives_a_missing_adapter_but_is_not_effective(self):
        self.poll()
        self.assertEqual(self.value("lens_control"), "1")        # the operator's choice stays
        self.assertTrue(self.ctrl.enabled())
        self.assertFalse(self.ctrl.effective())                  # ... but nothing is driven

    def test_nothing_is_written_to_the_lens_while_absent(self):
        self.poll()
        for ok, _ in (self.ctrl.set_iris(2.8), self.ctrl.set_focus(100),
                      self.ctrl.request_calibration()):
            self.assertFalse(ok)
        self.assertEqual(self.backend.iris_calls + self.backend.focus_calls, [])

    def test_it_probes_again_only_after_the_detect_interval(self):
        self.poll()
        self.assertEqual(len(self.factory_calls), 1)
        self.poll(step=1.0)
        self.assertEqual(len(self.factory_calls), 1)
        self.clock.advance(5.0)
        self.poll()
        self.assertEqual(len(self.factory_calls), 2)

    def test_the_adapter_appearing_later_is_picked_up(self):
        self.poll()
        self.factory_result = (self.backend, "")
        self.clock.advance(6.0)
        self.poll()
        self.assertEqual(self.value("lens_detected"), "1")
        self.assertTrue(self.ctrl.effective())

    def test_the_factory_is_given_the_port_and_the_parsed_camera_list(self):
        self.redis.set_value("cameras", json.dumps([{"model": "imx477", "port": "cam0"}]))
        self.ctrl = self.make(port="cam0")
        self.poll()
        self.assertEqual(self.factory_calls[0], ("cam0", [{"model": "imx477", "port": "cam0"}]))

    def test_a_garbled_camera_list_is_an_empty_one(self):
        self.redis.set_value("cameras", "{not json")
        self.poll()
        self.assertEqual(self.factory_calls[0][1], [])

    def test_a_factory_that_raises_is_an_absent_adapter_not_a_crash(self):
        def boom(port, cameras):
            raise RuntimeError("driver exploded")
        self.ctrl._factory = boom
        with self.assertLogs(level="ERROR"):
            self.poll()
        self.assertEqual(self.state(), "absent")
        self.assertIn("driver exploded", self.message())

    def test_an_unfitted_adapter_is_logged_once_not_every_probe(self):
        with self.assertLogs("module.lens.controller", level="INFO") as logs:
            for _ in range(4):
                self.poll(step=6.0)
        self.assertEqual(len([r for r in logs.records if "not found" in r.getMessage()]), 1)


class FoundTests(ControllerCase):
    def test_found_reports_provenance_port_and_how_the_bus_was_derived(self):
        self.poll()
        self.assertEqual(self.value("lens_detected"), "1")
        self.assertEqual(self.value("lens_provenance"), "v4l2-subdev")
        self.assertEqual(self.value("lens_port"), "cam0")
        self.assertIn("i2c-0", self.message())
        self.assertIn("cef168 subdev", self.message())

    def test_status_carries_the_bus_and_its_derivation(self):
        self.poll()
        status = self.ctrl.status()
        self.assertEqual((status["bus"], status["bus_source"], status["port"]),
                         (0, "cef168-subdev", "cam0"))
        self.assertIn("i2c-0", status["bus_description"])

    def test_the_raw_backend_s_derivation_is_reported_too(self):
        self.backend.provenance, self.backend.bus_source = "i2c-raw", "sensor-subdev"
        self.poll()
        self.assertEqual(self.ctrl.status()["bus_source"], "sensor-subdev")
        self.assertIn("sensor subdev", self.message())

    def test_no_lens_mounted(self):
        self.backend.data = frame(lens_id=0)
        self.poll()
        self.assertEqual(self.state(), "no_lens")
        self.assertEqual(self.value("lens_id"), "")
        self.assertIn("no lens", self.message().lower())
        ok, message = self.ctrl.set_iris(2.8)
        self.assertFalse(ok)
        self.assertIn("No lens", message)

    def test_an_unknown_lens(self):
        self.poll()
        self.assertEqual(self.state(), "unknown_lens")
        self.assertEqual(self.value("lens_id"), "235")
        self.assertEqual(self.value("lens_key"), "")
        self.assertEqual(self.value("lens_name"), "")
        working = self.ctrl.working_entry()
        self.assertEqual((working["lens_id"], working["name"], working["dirty"], working["key"]),
                         (235, "", False, None))

    def test_the_state_follows_the_toggle_without_losing_the_lens(self):
        self.toggle(False)
        self.poll()
        self.assertEqual(self.value("lens_detected"), "1")
        self.assertFalse(self.ctrl.effective())
        self.toggle(True)
        self.poll()
        self.assertTrue(self.ctrl.effective())

    def test_every_documented_key_is_published(self):
        self.poll()
        for key in ("lens_detected", "lens_provenance", "lens_port", "lens_id", "lens_key",
                    "lens_name", "lens_state", "lens_message", "lens_aperture_range",
                    "focus_position"):
            self.assertIn(key, self.redis.cache, key)


class AdapterLossTests(ControllerCase):
    def test_a_few_failed_reads_are_shrugged_off(self):
        self.poll()
        self.backend.read_errors = 2
        self.poll(2)
        self.poll()
        self.assertEqual(self.state(), "unknown_lens")

    def test_three_failed_reads_in_a_row_are_an_error_with_a_message(self):
        self.poll()
        self.backend.read_errors = 3
        self.poll(3)
        self.assertEqual(self.state(), "error")
        self.assertIn("not answering", self.message())
        self.poll()                                   # the board is back
        self.assertEqual(self.state(), "unknown_lens")

    def test_a_board_that_stays_silent_is_declared_gone_and_closed(self):
        self.poll()
        self.backend.read_fails_forever = True
        self.poll(controller_module.LOST_AFTER_FAILURES)
        self.assertEqual(self.state(), "absent")
        self.assertEqual(self.value("lens_detected"), "0")
        self.assertTrue(self.backend.closed)
        self.assertIn("stopped answering", self.message())

    def test_it_comes_back_with_the_same_lens_and_restores_the_iris(self):
        self.db.add(saved_entry(last_iris=5.6))
        self.poll()
        self.assertEqual(self.backend.iris_calls, [5.6])
        self.backend.read_fails_forever = True
        self.poll(controller_module.LOST_AFTER_FAILURES)
        replacement = FakeBackend(frame(lens_id=235))
        self.factory_result = (replacement, "")
        self.clock.advance(6.0)
        self.poll()
        self.assertEqual(self.state(), "uncalibrated")
        self.assertEqual(self.value("lens_key"), "sigma-18-35-f1-8")
        self.assertEqual(replacement.iris_calls, [5.6])

    def test_unsaved_work_survives_a_dropped_cable(self):
        self.poll()
        self.ctrl.set_aperture_range(2.8, 16.0)
        self.backend.read_fails_forever = True
        self.poll(controller_module.LOST_AFTER_FAILURES)
        self.factory_result = (FakeBackend(frame(lens_id=235)), "")
        self.clock.advance(6.0)
        self.poll()
        working = self.ctrl.working_entry()
        self.assertTrue(working["dirty"])
        self.assertEqual(working["aperture"]["min"], 2.8)

    def test_taking_the_lens_off_clears_the_selection(self):
        self.db.add(saved_entry())
        self.poll()
        self.assertEqual(self.value("lens_key"), "sigma-18-35-f1-8")
        self.backend.data = frame(lens_id=0)
        self.poll()
        self.assertEqual(self.state(), "no_lens")
        self.assertEqual(self.value("lens_key"), "")
        self.assertEqual(self.value("lens_id"), "")

    def test_a_write_failure_shows_as_an_error_until_the_next_good_read(self):
        self.poll()
        self.backend.iris_error = "EIO"
        ok, message = self.ctrl.set_iris(4.0)
        self.assertFalse(ok)
        self.assertIn("EIO", message)
        self.poll()                         # publishes
        self.assertEqual(self.state(), "unknown_lens")   # the read after it was fine

    def test_a_write_failure_is_visible_in_state_and_message_straight_away(self):
        self.poll()
        self.backend.iris_error = "EIO"
        self.ctrl.set_iris(4.0)
        self.ctrl._publish_all()
        self.assertEqual(self.state(), "error")
        self.assertIn("EIO", self.message())


# ── selection (D6b) and saving (D6c) ───────────────────────────────────────

class SelectionTests(ControllerCase):
    def test_one_matching_entry_is_selected_and_stamped(self):
        key = self.db.add(saved_entry())
        self.poll()
        self.assertEqual(self.value("lens_key"), key)
        self.assertEqual(self.value("lens_name"), "Sigma 18-35 f/1.8")
        self.assertEqual(self.value("lens_aperture_range"), "1.8-16")
        self.assertEqual(self.db.get(key)["last_used"], "2026-10-04T12:00:00Z")
        self.assertEqual(self.state(), "uncalibrated")

    def test_a_calibrated_entry_is_ready(self):
        self.db.add(saved_entry(focus=TWO_POINT_FOCUS))
        self.poll()
        self.assertEqual(self.state(), "ready")

    def test_several_matches_pick_the_most_recently_used(self):
        old = self.db.add(saved_entry(name="Old"))
        new = self.db.add(saved_entry(name="New"))
        self.db.touch(old, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.db.touch(new, datetime(2026, 6, 1, tzinfo=timezone.utc))
        self.poll()
        self.assertEqual(self.value("lens_key"), new)

    def test_entries_for_other_lenses_are_not_candidates(self):
        self.db.add(saved_entry(name="Other", lens_id=7))
        self.poll()
        self.assertEqual(self.state(), "unknown_lens")

    def test_swapping_the_lens_changes_the_entry(self):
        a = self.db.add(saved_entry(name="A", lens_id=235))
        b = self.db.add(saved_entry(name="B", lens_id=112))
        self.poll()
        self.assertEqual(self.value("lens_key"), a)
        self.backend.data = frame(lens_id=112)
        self.poll()
        self.assertEqual(self.value("lens_key"), b)

    def test_select_lens_by_key(self):
        a = self.db.add(saved_entry(name="A"))
        b = self.db.add(saved_entry(name="B"))
        self.poll()
        other = a if self.value("lens_key") == b else b
        ok, message = self.ctrl.select_lens(other)
        self.assertTrue(ok, message)
        self.assertEqual(self.value("lens_key"), other)
        self.assertEqual(self.db.get(other)["last_used"], "2026-10-04T12:00:00Z")

    def test_select_lens_without_a_key_cycles_through_the_mounted_id(self):
        keys = [self.db.add(saved_entry(name=f"L{i}")) for i in range(3)]
        self.db.add(saved_entry(name="Other", lens_id=9))
        self.poll()
        seen = [self.value("lens_key")]
        for _ in range(3):
            self.assertTrue(self.ctrl.select_lens()[0])
            seen.append(self.value("lens_key"))
        self.assertEqual(sorted(set(seen)), sorted(keys))
        self.assertEqual(seen[0], seen[3])             # wrapped round

    def test_cycling_with_no_candidates_says_so(self):
        self.poll()
        ok, message = self.ctrl.select_lens()
        self.assertFalse(ok)
        self.assertIn("235", message)

    def test_selecting_an_entry_for_another_lens_is_allowed_but_warned(self):
        other = self.db.add(saved_entry(name="Other", lens_id=7))
        self.poll()
        ok, message = self.ctrl.select_lens(other)
        self.assertTrue(ok)
        self.assertIn("warning", message)
        self.assertIn("7", message)

    def test_selecting_a_missing_key_is_refused(self):
        self.poll()
        ok, message = self.ctrl.select_lens("nope")
        self.assertFalse(ok)
        self.assertIn("nope", message)

    def test_selecting_discards_unsaved_changes_and_says_so(self):
        a = self.db.add(saved_entry(name="A"))
        b = self.db.add(saved_entry(name="B"))
        self.poll()
        self.ctrl.set_aperture_range(2.8, 11.0)
        target = a if self.value("lens_key") == b else b
        ok, message = self.ctrl.select_lens(target)
        self.assertIn("unsaved changes were discarded", message)
        self.assertFalse(self.ctrl.working_entry()["dirty"])
        self.assertEqual(self.ctrl.working_entry()["aperture"]["min"], 1.8)

    def test_an_entry_deleted_behind_our_back_is_kept_as_unsaved(self):
        key = self.db.add(saved_entry(focus=TWO_POINT_FOCUS))
        self.poll()
        self.db.delete(key)
        with self.assertLogs("module.lens.controller", level="WARNING"):
            self.poll()
        self.assertEqual(self.value("lens_key"), "")
        self.assertEqual(self.state(), "unknown_lens")
        working = self.ctrl.working_entry()
        self.assertTrue(working["dirty"])
        self.assertEqual(working["focus"]["position_max"], 1069)


class SavingTests(ControllerCase):
    def test_nothing_reaches_the_file_until_the_operator_saves(self):
        key = self.db.add(saved_entry())
        self.poll()
        self.ctrl.set_aperture_range(2.8, 11.0)
        self.assertTrue(self.ctrl.working_entry()["dirty"])
        self.assertEqual(self.db.get(key)["aperture"]["min"], 1.8)

    def test_save_as_new_adds_an_entry_and_selects_it(self):
        self.poll()
        self.ctrl.set_aperture_range(1.8, 16.0)
        ok, message = self.ctrl.save_lens("My Sigma")
        self.assertTrue(ok, message)
        self.assertEqual(self.value("lens_key"), "my-sigma")
        self.assertEqual(self.value("lens_name"), "My Sigma")
        saved = self.db.get("my-sigma")
        self.assertEqual((saved["lens_id"], saved["aperture"]["max"]), (235, 16.0))
        self.assertFalse(self.ctrl.working_entry()["dirty"])
        self.assertEqual(self.state(), "uncalibrated")

    def test_save_as_new_from_a_selected_entry_leaves_the_original_alone(self):
        original = self.db.add(saved_entry())
        self.poll()
        self.ctrl.set_aperture_range(2.8, 11.0)
        ok, _ = self.ctrl.save_lens("Variant")
        self.assertTrue(ok)
        self.assertEqual(self.db.get(original)["aperture"]["min"], 1.8)
        self.assertEqual(self.db.get("variant")["aperture"]["min"], 2.8)

    def test_save_over_keeps_the_key_and_may_rename(self):
        key = self.db.add(saved_entry())
        self.poll()
        self.ctrl.set_aperture_range(2.8, 11.0)
        ok, message = self.ctrl.save_lens("Renamed", key)
        self.assertTrue(ok, message)
        self.assertEqual(list(self.db.entries()), [key])
        self.assertEqual(self.db.get(key)["name"], "Renamed")
        self.assertEqual(self.db.get(key)["aperture"]["min"], 2.8)
        self.assertEqual(self.value("lens_key"), key)
        self.assertEqual(self.value("lens_name"), "Renamed")

    def test_save_over_preserves_fields_the_controller_does_not_know(self):
        key = self.db.add(saved_entry(notes="from the rental house"))
        self.poll()
        self.ctrl.save_lens("Same", key)
        self.assertEqual(self.db.get(key)["notes"], "from the rental house")

    def test_save_over_a_missing_entry_is_refused(self):
        self.poll()
        ok, message = self.ctrl.save_lens("X", "nope")
        self.assertFalse(ok)
        self.assertIn("nope", message)

    def test_a_name_is_required(self):
        self.poll()
        for name in ("", "   ", None):
            ok, message = self.ctrl.save_lens(name)
            self.assertFalse(ok)
            self.assertIn("name", message)

    def test_saving_with_no_lens_mounted_is_refused(self):
        self.backend.data = frame(lens_id=0)
        self.poll()
        ok, message = self.ctrl.save_lens("X")
        self.assertFalse(ok)
        self.assertIn("No lens", message)

    def test_a_database_that_cannot_be_written_is_a_message_not_an_exception(self):
        self.poll()
        import os
        real = os.replace
        os.replace = lambda *a: (_ for _ in ()).throw(OSError(13, "read-only"))
        try:
            ok, message = self.ctrl.save_lens("X")
        finally:
            os.replace = real
        self.assertFalse(ok)
        self.assertIn("Could not save", message)
        self.assertEqual(self.db.entries(), {})


class ApertureRangeTests(ControllerCase):
    def test_entering_a_range_marks_the_working_entry_dirty_and_publishes_it(self):
        self.poll()
        ok, message = self.ctrl.set_aperture_range(1.8, 22)
        self.assertTrue(ok, message)
        self.assertEqual(self.value("lens_aperture_range"), "1.8-22")
        working = self.ctrl.working_entry()
        self.assertTrue(working["dirty"])
        self.assertEqual(working["aperture"], {"min": 1.8, "max": 22.0, "source": "manual"})

    def test_clearing_it(self):
        self.db.add(saved_entry())
        self.poll()
        self.assertTrue(self.ctrl.set_aperture_range(None, None)[0])
        self.assertEqual(self.value("lens_aperture_range"), "")

    def test_nonsense_is_refused(self):
        self.poll()
        for lo, hi in ((16, 2.8), (0, 5), (1.8, 500), ("x", 5), (None, 5), (1.8, None)):
            self.assertFalse(self.ctrl.set_aperture_range(lo, hi)[0], (lo, hi))
        self.assertFalse(self.ctrl.working_entry()["dirty"])

    def test_it_needs_a_mounted_lens(self):
        self.backend.data = frame(lens_id=0)
        self.poll()
        self.assertFalse(self.ctrl.set_aperture_range(1.8, 16)[0])

    def test_a_missing_range_is_noted_in_the_ready_message(self):
        self.db.add(saved_entry(aperture=None, focus=TWO_POINT_FOCUS))
        self.poll()
        self.assertIn("aperture range not set", self.message())


# ── iris ───────────────────────────────────────────────────────────────────

class IrisTests(ControllerCase):
    def test_the_stored_iris_is_restored_on_detect_clamped_to_the_range(self):
        self.db.add(saved_entry(last_iris=22.0))             # entry range tops out at 16
        self.poll()
        self.assertEqual(self.backend.iris_calls, [16.0])
        self.assertEqual(self.value("iris"), "16.0")

    def test_it_is_an_absolute_write_and_only_one(self):
        self.db.add(saved_entry(last_iris=5.6))
        self.poll(3)
        self.assertEqual(self.backend.iris_calls, [5.6])

    def test_without_a_stored_iris_the_redis_value_is_used(self):
        self.redis.set_value("iris", "4.0")
        self.db.add(saved_entry())
        self.poll()
        self.assertEqual(self.backend.iris_calls, [4.0])

    def test_with_nothing_to_restore_nothing_is_written(self):
        self.db.add(saved_entry())
        self.poll()
        self.assertEqual(self.backend.iris_calls, [])

    def test_nothing_is_restored_while_the_toggle_is_off_and_it_is_when_switched_on(self):
        self.toggle(False)
        self.db.add(saved_entry(last_iris=5.6))
        self.poll(2)
        self.assertEqual(self.backend.iris_calls, [])
        self.assertTrue(self.ctrl.set_enabled(True)[0])
        self.poll()
        self.assertEqual(self.backend.iris_calls, [5.6])

    def test_a_different_lens_gets_its_own_stored_iris(self):
        self.db.add(saved_entry(name="A", lens_id=235, last_iris=4.0))
        self.db.add(saved_entry(name="B", lens_id=112, last_iris=2.8))
        self.poll()
        self.backend.data = frame(lens_id=112)
        self.poll()
        self.assertEqual(self.backend.iris_calls, [4.0, 2.8])

    def test_set_iris_writes_the_lens_redis_and_the_entry(self):
        key = self.db.add(saved_entry())
        self.poll()
        ok, message = self.ctrl.set_iris(2.8)
        self.assertTrue(ok, message)
        self.assertEqual(self.backend.iris_calls, [2.8])
        self.assertEqual(self.value("iris"), "2.8")
        self.assertEqual(self.db.get(key)["last_iris"], 2.8)

    def test_last_iris_is_written_silently_it_does_not_dirty_the_entry(self):
        self.db.add(saved_entry())
        self.poll()
        self.ctrl.set_iris(2.8)
        working = self.ctrl.working_entry()
        self.assertFalse(working["dirty"])
        self.assertEqual(working["last_iris"], 2.8)

    def test_set_iris_clamps_to_the_range_and_says_so(self):
        self.db.add(saved_entry())
        self.poll()
        ok, message = self.ctrl.set_iris(22)
        self.assertTrue(ok)
        self.assertEqual(self.backend.iris_calls, [16.0])
        self.assertIn("clamped", message)
        self.ctrl.set_iris(1.2)
        self.assertEqual(self.backend.iris_calls[-1], 1.8)

    def test_an_unknown_lens_has_no_entry_to_write_last_iris_to(self):
        self.poll()
        ok, _ = self.ctrl.set_iris(4.0)
        self.assertTrue(ok)
        self.assertEqual(self.db.entries(), {})
        self.assertEqual(self.value("iris"), "4.0")

    def test_not_a_number(self):
        self.poll()
        ok, message = self.ctrl.set_iris("wide open")
        self.assertFalse(ok)
        self.assertIn("f-number", message)

    def test_a_backend_dropped_between_the_check_and_the_write_is_a_refusal_not_a_crash(self):
        self.poll()
        self.ctrl._backend = None          # the poll thread dropped it a moment ago
        for call in (lambda: self.ctrl.set_iris(4.0), lambda: self.ctrl.set_focus(100)):
            ok, message = call()
            self.assertFalse(ok)
            self.assertIn("not found", message)

    def test_a_failing_autofocus_setting_does_not_take_the_loop_down(self):
        def broken():
            raise RuntimeError("settings reload in progress")
        self.ctrl = self.make(autofocus_enabled=broken)
        self.poll(2)
        self.assertEqual(self.state(), "unknown_lens")
        self.assertFalse(self.ctrl.status()["af"]["enabled"])

    def test_refused_when_the_toggle_is_off(self):
        self.poll()
        self.toggle(False)
        self.poll()
        ok, message = self.ctrl.set_iris(4.0)
        self.assertFalse(ok)
        self.assertIn("off", message)
        self.assertEqual(self.backend.iris_calls, [])

    def test_step_iris_walks_third_stops_from_the_last_value(self):
        self.db.add(saved_entry())
        self.poll()
        self.ctrl.set_iris(2.8)
        self.assertTrue(self.ctrl.step_iris(1)[0])
        self.assertTrue(self.ctrl.step_iris(1)[0])
        self.assertTrue(self.ctrl.step_iris(-1)[0])
        self.assertEqual(self.backend.iris_calls, [2.8, 3.2, 3.5, 3.2])

    def test_step_iris_stops_at_the_ends_of_the_range(self):
        self.db.add(saved_entry())
        self.poll()
        self.ctrl.set_iris(16)
        self.ctrl.step_iris(1)
        self.assertEqual(self.backend.iris_calls[-1], 16.0)
        self.ctrl.set_iris(1.8)
        self.ctrl.step_iris(-1)
        self.assertEqual(self.backend.iris_calls[-1], 1.8)

    def test_step_iris_starts_from_the_redis_value_after_a_restart(self):
        self.redis.set_value("iris", "5.6")
        self.poll()
        self.backend.iris_calls.clear()
        self.assertTrue(self.ctrl.step_iris(1)[0])
        self.assertEqual(self.backend.iris_calls[-1], 6.3)

    def test_iris_never_uses_a_relative_write(self):
        # D5: relative iris is only valid after an absolute write since the last
        # zoom change, and a lens we cannot read back makes that unknowable.
        # The backend interface has no relative call, and the controller never
        # names the relative commands or controls.
        source = Path(controller_module.__file__).read_text()
        for forbidden in ("IRIS_RELATIVE", "INP_SET_APERTURE_P", "INP_SET_APERTURE_N"):
            self.assertNotIn(forbidden, source)
        self.assertFalse(hasattr(lens_fakes.Cef168Backend, "set_iris_relative"))


# ── focus ──────────────────────────────────────────────────────────────────

class FocusTests(ControllerCase):
    def test_focus_goes_straight_to_the_board_clamped_to_its_range(self):
        self.poll()
        self.assertTrue(self.ctrl.set_focus(600)[0])
        self.ctrl.set_focus(5000)
        self.ctrl.set_focus(-30)
        self.assertEqual(self.backend.focus_calls, [600, 1069, 0])

    def test_step_focus_is_one_percent_of_the_range_towards_infinity(self):
        self.backend.data = frame(focus_position_cur=500)
        self.poll()
        self.assertTrue(self.ctrl.step_focus(1)[0])
        self.assertEqual(self.backend.focus_calls, [511])        # 1 % of 1069 = 10.69 -> 11
        self.ctrl.step_focus(-3)
        self.assertEqual(self.backend.focus_calls[-1], 500 - 33)

    def test_focus_is_refused_with_no_lens_or_toggle(self):
        self.backend.data = frame(lens_id=0)
        self.poll()
        self.assertFalse(self.ctrl.set_focus(100)[0])
        self.assertFalse(self.ctrl.step_focus(1)[0])
        self.assertEqual(self.backend.focus_calls, [])

    def test_focus_position_is_published_from_the_readback(self):
        self.backend.data = frame(focus_position_cur=777)
        self.poll()
        self.assertEqual(self.value("focus_position"), "777")


# ── calibration ────────────────────────────────────────────────────────────

class CalibrationTests(ControllerCase):
    def setUp(self):
        super().setUp()
        self.backend.sweep = encoder_sweep()

    def calibrate(self):
        self.poll()
        ok, message = self.ctrl.request_calibration()
        self.assertTrue(ok, message)
        self.poll()
        return self.ctrl.status()["calibration"]["last"]

    def test_refused_while_recording(self):
        self.poll()
        self.set_rec(True)
        ok, message = self.ctrl.request_calibration()
        self.assertFalse(ok)
        self.assertIn("recording", message)
        self.assertEqual(self.backend.calibrate_calls, 0)

    def test_refused_while_the_other_recording_flag_is_up_too(self):
        self.poll()
        self.redis.set_value("is_recording", "1")
        self.assertFalse(self.ctrl.request_calibration()[0])

    def test_refused_when_not_effective(self):
        self.poll()
        self.toggle(False)
        self.poll()
        ok, message = self.ctrl.request_calibration()
        self.assertFalse(ok)
        self.assertIn("off", message)

    def test_refused_with_no_lens(self):
        self.backend.data = frame(lens_id=0)
        self.poll()
        self.assertFalse(self.ctrl.request_calibration()[0])

    def test_refused_when_the_adapter_is_absent(self):
        self.factory_result = (None, "gone")
        self.ctrl = self.make()
        self.poll()
        ok, message = self.ctrl.request_calibration()
        self.assertFalse(ok)
        self.assertIn("not found", message)

    def test_the_request_shows_as_calibrating_immediately(self):
        self.poll()
        self.ctrl.request_calibration()
        self.assertEqual(self.state(), "calibrating")
        self.assertEqual(self.backend.calibrate_calls, 0)        # the thread does the sweep

    def test_a_second_request_while_one_is_queued_does_not_double_up(self):
        self.poll()
        self.ctrl.request_calibration()
        self.ctrl.request_calibration()
        self.poll()
        self.assertEqual(self.backend.calibrate_calls, 1)

    def test_the_result_lands_in_the_working_entry_not_the_file(self):
        key = self.db.add(saved_entry())
        last = self.calibrate()
        self.assertTrue(last["ok"], last["reason"])
        working = self.ctrl.working_entry()
        self.assertTrue(working["dirty"])
        self.assertEqual(working["focus"]["position_max"], 1069)
        self.assertEqual(working["capabilities"]["focus"], True)
        self.assertIsNone(self.db.get(key)["focus"])             # D6c: not saved
        self.assertEqual(self.state(), "ready")
        self.assertIn("Not saved yet", self.message())

    def test_saving_then_writes_it_out(self):
        key = self.db.add(saved_entry())
        self.calibrate()
        self.assertTrue(self.ctrl.save_lens("Sigma", key)[0])
        stored = self.db.get(key)
        self.assertEqual(stored["focus"]["position_max"], 1069)
        self.assertEqual(stored["capabilities"]["focus"], True)

    def test_the_sweep_runs_to_completion_before_anything_else_is_polled(self):
        self.calibrate()
        self.assertEqual(self.backend.calibrate_calls, 1)
        self.assertFalse(self.ctrl.status()["calibration"]["running"])
        self.assertNotEqual(self.state(), "calibrating")

    def test_commands_are_refused_while_the_sweep_runs_and_progress_is_visible(self):
        self.poll()
        self.ctrl.request_calibration()
        seen = {}
        real_sleep = self.ctrl._sleep

        def spy(seconds):
            if "iris" not in seen:
                seen["iris"] = self.ctrl.set_iris(2.8)
                seen["focus"] = self.ctrl.set_focus(100)
                seen["status"] = self.ctrl.status()
            real_sleep(seconds)

        self.ctrl._sleep = spy
        self.poll()
        self.assertFalse(seen["iris"][0])
        self.assertIn("calibrating", seen["iris"][1])
        self.assertFalse(seen["focus"][0])
        self.assertEqual(seen["status"]["state"], "calibrating")
        self.assertTrue(seen["status"]["calibration"]["running"])
        self.assertEqual(self.backend.iris_calls, [])

    def test_progress_is_published_while_sweeping(self):
        self.poll()
        self.ctrl.request_calibration()
        self.poll()
        positions = [int(v) for v in self.redis.published("focus_position")]
        self.assertGreater(len(positions), 3)
        self.assertEqual(max(positions), 1069)
        self.assertTrue(any("Calibrating" in m for m in self.redis.published("lens_message")))

    def test_the_lens_message_names_the_kind_of_map(self):
        self.calibrate()
        self.assertIn("distance-encoder map", self.message())

    def test_a_lens_without_an_encoder_gets_the_two_point_map(self):
        self.backend.sweep = no_encoder_sweep()
        last = self.calibrate()
        self.assertEqual(last["focus"]["map"], [0.0, 1037, 3.57, 0])
        self.assertIn("2-point", self.message())

    def test_an_operator_supplied_mfd_reaches_the_calibration(self):
        self.backend.sweep = no_encoder_sweep(mfd_cm=0)
        self.poll()
        self.ctrl.request_calibration(mfd_m=0.45)
        self.poll()
        self.assertEqual(self.ctrl.working_entry()["focus"]["map"], [0.0, 1037, 2.22, 0])

    def test_the_mfd_from_an_earlier_calibration_is_reused(self):
        self.db.add(saved_entry(focus={**TWO_POINT_FOCUS, "mfd_m": 0.5}))
        self.backend.sweep = no_encoder_sweep(mfd_cm=0)
        self.poll()
        self.ctrl.request_calibration()
        self.poll()
        self.assertEqual(self.ctrl.working_entry()["focus"]["map"][2], 2.0)

    def test_a_fresh_reading_from_the_board_beats_the_mfd_remembered_from_before(self):
        self.db.add(saved_entry(focus={**TWO_POINT_FOCUS, "mfd_m": 0.28}))
        self.backend.sweep = no_encoder_sweep(mfd_cm=50)         # the lens now says 0.5 m
        self.poll()
        self.ctrl.request_calibration()
        self.poll()
        self.assertEqual(self.ctrl.working_entry()["focus"]["map"][2], 2.0)

    def test_a_failed_calibration_says_why_and_changes_nothing(self):
        self.backend.sweep = [frame(focus_position_cur=300)] * 4        # never starts
        self.db.add(saved_entry(focus=TWO_POINT_FOCUS))
        self.poll()
        self.ctrl.request_calibration()
        with self.assertLogs("module.lens.controller", level="WARNING"):
            self.poll()
        self.assertIn("never started", self.message())
        working = self.ctrl.working_entry()
        self.assertFalse(working["dirty"])
        self.assertEqual(working["focus"]["position_max"], 1069)
        self.assertIsNone(working["capabilities"]["focus"])      # "never started" is not a verdict


class NoFocusFeedbackLensTests(ControllerCase):
    """D20 / G0.2: the Sigma 18-35 f/1.8 Art (lens id 112) never reports a focus
    position. Calibration says so, the entry records it, the controls gate on it."""

    def setUp(self):
        super().setUp()
        self.backend.data = frame(lens_id=112, focus_position_max=0, focus_position_cur=0,
                                  focus_distance_min=28, focus_distance_max=28)
        self.backend.sweep = sigma_no_feedback_sweep()

    def fail_calibration(self):
        self.poll()
        self.assertTrue(self.ctrl.request_calibration()[0])
        with self.assertLogs("module.lens.controller", level="WARNING"):
            self.poll()

    def test_the_working_entry_records_that_focus_and_autofocus_are_unavailable(self):
        self.fail_calibration()
        working = self.ctrl.working_entry()
        self.assertEqual(working["capabilities"],
                         {"iris": None, "focus": False, "autofocus": False})
        self.assertTrue(working["dirty"])                         # the operator saves it
        self.assertIsNone(working["focus"])

    def test_the_lens_message_explains_it(self):
        self.fail_calibration()
        self.assertIn("never reported a focus position", self.message())
        self.assertIn("Save the lens", self.message())

    def test_status_exposes_the_capabilities(self):
        self.fail_calibration()
        status = self.ctrl.status()
        self.assertEqual(status["capabilities"]["focus"], False)
        self.assertEqual(status["capabilities"]["autofocus"], False)
        self.assertFalse(status["calibration"]["last"]["ok"])

    def test_saving_keeps_the_verdict_with_the_lens(self):
        self.fail_calibration()
        self.assertTrue(self.ctrl.save_lens("Sigma 18-35 f/1.8 Art")[0])
        stored = self.db.get("sigma-18-35-f1-8-art")
        self.assertEqual(stored["capabilities"], {"iris": None, "focus": False, "autofocus": False})
        self.assertEqual(stored["lens_id"], 112)

    def test_a_lens_marked_this_way_is_ready_for_iris_use_not_nagged_to_calibrate(self):
        self.fail_calibration()
        self.ctrl.save_lens("Sigma")
        self.assertEqual(self.state(), "ready")
        self.clock.advance(300.0)           # let the "Saved as ..." notice expire
        self.poll()
        self.assertIn("iris only", self.message())

    def test_focus_requests_are_refused_with_the_reason_and_never_reach_the_lens(self):
        self.fail_calibration()
        for call in (lambda: self.ctrl.set_focus(100), lambda: self.ctrl.step_focus(1)):
            ok, message = call()
            self.assertFalse(ok)
            self.assertIn("never reported a focus position", message)
        self.assertEqual(self.backend.focus_calls, [])

    def test_autofocus_requests_are_refused_too(self):
        self.fail_calibration()
        for call in (self.ctrl.af_once, self.ctrl.af_cancel,
                     lambda: self.ctrl.set_af_mode("continuous")):
            ok, message = call()
            self.assertFalse(ok)
            self.assertIn("focus position", message)

    def test_iris_is_unaffected(self):
        self.fail_calibration()
        ok, message = self.ctrl.set_iris(4.0)
        self.assertTrue(ok, message)
        self.assertEqual(self.backend.iris_calls, [4.0])
        self.assertTrue(self.ctrl.step_iris(1)[0])

    def test_the_self_test_gesture_does_not_sweep_such_a_lens_again(self):
        self.fail_calibration()
        self.ctrl.save_lens("Sigma")
        self.backend.calibrate_calls = 0
        # The detector reports a finished self-test; the controller declines to calibrate.
        self.ctrl._on_selftest_event("selftest_finished")
        self.poll()
        self.assertEqual(self.backend.calibrate_calls, 0)
        self.assertIn("marked unavailable", self.message())

    def test_an_explicit_request_still_works(self):
        self.fail_calibration()
        self.ctrl.save_lens("Sigma")
        self.assertTrue(self.ctrl.request_calibration()[0])

    def test_a_later_successful_calibration_clears_the_verdict(self):
        self.fail_calibration()
        self.backend.data = frame(lens_id=112)
        self.backend.sweep = [f if f.lens_id == 112 else f for f in
                              [frame(**{**vars(g), "lens_id": 112}) for g in encoder_sweep()]]
        self.assertTrue(self.ctrl.request_calibration()[0])
        self.poll()
        working = self.ctrl.working_entry()
        self.assertEqual(working["capabilities"]["focus"], True)
        self.assertIsNone(working["capabilities"]["autofocus"])
        self.assertIsNotNone(working["focus"])

    def test_no_restart_is_requested_for_such_a_lens(self):
        self.ctrl = self.make(autofocus_enabled=True)
        self.db.add(saved_entry(lens_id=112, focus=TWO_POINT_FOCUS,
                                capabilities={"iris": None, "focus": False, "autofocus": False}))
        self.poll(2)
        self.assertEqual(self.restarts, [])


# ── the self-test gesture end to end ───────────────────────────────────────

class SelfTestTests(ControllerCase):
    """Frames come from the backend one per poll (4 Hz), as in life."""

    def uncalibrated_bursts(self, count):
        frames = []
        for _ in range(count):
            frames.append(frame(moving=True, focus_position_min=0, focus_position_max=0,
                                focus_position_cur=0))
            frames.append(frame(moving=False, focus_position_min=0, focus_position_max=0,
                                focus_position_cur=0))
        return frames

    def quiet(self, n):
        return [frame(moving=False, focus_position_min=0, focus_position_max=0,
                      focus_position_cur=0)] * n

    def run_frames(self, frames):
        states = []
        for data in frames:
            self.backend.queue.append(data)
            self.poll()
            states.append(self.state())
        return states

    def test_the_gesture_starts_a_calibration_whose_result_lands_in_the_working_entry(self):
        self.backend.sweep = encoder_sweep()
        self.poll()
        states = self.run_frames(self.uncalibrated_bursts(4) + self.quiet(10))
        self.assertIn("selftest", states)
        self.assertEqual(self.backend.calibrate_calls, 1)
        working = self.ctrl.working_entry()
        self.assertTrue(working["dirty"])
        self.assertEqual(working["focus"]["position_max"], 1069)

    def test_it_waits_for_the_self_test_to_finish_before_sweeping(self):
        self.backend.sweep = encoder_sweep()
        self.poll()
        self.run_frames(self.uncalibrated_bursts(4))
        self.assertEqual(self.state(), "selftest")
        self.assertEqual(self.backend.calibrate_calls, 0)

    def test_a_calibrated_lens_is_recognised_by_its_min_max_min_excursion(self):
        self.backend.sweep = encoder_sweep()
        self.poll()
        positions = [300, 100, 400, 700, 950, 700, 400, 100]
        frames = [frame(moving=True, focus_position_cur=p, focus_position_min=0,
                        focus_position_max=1000) for p in positions]
        frames += [frame(moving=False, focus_position_cur=0, focus_position_min=0,
                         focus_position_max=1000)] * 10
        self.run_frames(frames)
        self.assertEqual(self.backend.calibrate_calls, 1)

    def test_a_manual_focus_pull_never_starts_a_sweep(self):
        self.poll()
        positions = [0, 200, 500, 800, 1000, 800, 500, 200, 0]
        frames = [frame(moving=False, focus_position_cur=p, focus_position_min=0,
                        focus_position_max=1000) for p in positions]
        frames += [frame(moving=False, focus_position_cur=0, focus_position_min=0,
                         focus_position_max=1000)] * 12
        self.run_frames(frames)
        self.assertEqual(self.backend.calibrate_calls, 0)

    def test_not_while_recording(self):
        self.backend.sweep = encoder_sweep()
        self.poll()
        self.set_rec(True)
        self.run_frames(self.uncalibrated_bursts(4) + self.quiet(10))
        self.assertEqual(self.backend.calibrate_calls, 0)
        self.assertIn("recording", self.message())

    def test_not_while_the_toggle_is_off(self):
        self.backend.sweep = encoder_sweep()
        self.poll()
        self.toggle(False)
        self.run_frames(self.uncalibrated_bursts(4) + self.quiet(10))
        self.assertEqual(self.backend.calibrate_calls, 0)

    def test_the_commands_cinemate_sends_are_not_mistaken_for_it(self):
        self.poll()
        # CineMate's own iris write opens a grace window around the motion that
        # follows: these four bursts would be the gesture if the board had not
        # just been told to move (they fit inside the 2 s window).
        self.ctrl.set_iris(4.0)
        states = self.run_frames(self.uncalibrated_bursts(4))
        self.assertNotIn("selftest", states)
        self.run_frames(self.quiet(10))
        self.assertEqual(self.backend.calibrate_calls, 0)

    def test_the_sweep_s_own_motion_does_not_retrigger_it(self):
        self.backend.sweep = encoder_sweep()
        self.poll()
        self.run_frames(self.uncalibrated_bursts(4) + self.quiet(40))
        self.assertEqual(self.backend.calibrate_calls, 1)

    def test_polling_speeds_up_once_part_of_the_gesture_has_been_seen(self):
        self.poll()
        slow = self.ctrl._interval()
        self.run_frames(self.uncalibrated_bursts(1))
        self.assertLess(self.ctrl._interval(), slow)
        self.assertAlmostEqual(self.ctrl._interval(), 1 / controller_module.FAST_POLL_HZ)


# ── autofocus (D15-D17) ────────────────────────────────────────────────────

class AutofocusTests(ControllerCase):
    KEY = "sigma-18-35-f1-8"

    def setUp(self):
        super().setUp()
        self.ctrl = self.make(autofocus_enabled=True)
        self.db.add(saved_entry(focus=TWO_POINT_FOCUS))
        self.redis.set_value("af_available", self.KEY)
        self.poll()

    def test_with_the_autofocus_setting_off_none_of_it_does_anything(self):
        # Autofocus is paused: off is the default, and off means inert even if
        # something wrote af_available.
        ctrl = self.make()                       # autofocus_enabled defaults to False
        self.assertFalse(ctrl.af_active())
        self.redis.writes.clear()
        ctrl.poll_once()
        ok, _ = ctrl.set_focus(300)
        self.assertTrue(ok)
        self.assertEqual(self.backend.focus_calls, [300])          # straight to the board
        for call in (ctrl.af_once, ctrl.af_cancel, lambda: ctrl.set_af_mode("continuous")):
            self.assertFalse(call()[0])
        written = {key for key, _, _ in self.redis.writes}
        self.assertFalse(written & {"af_mode", "af_trigger", "lens_position"})
        self.assertEqual(self.restarts, [])
        self.assertFalse(ctrl.status()["af"]["active"])

    def test_af_is_active_when_the_camera_was_launched_with_a_tuning_for_this_entry(self):
        self.assertTrue(self.ctrl.af_active())
        self.assertTrue(self.ctrl.status()["af"]["active"])

    def test_it_is_not_active_for_another_entry_or_none(self):
        self.redis.set_value("af_available", "some-other-lens")
        self.assertFalse(self.ctrl.af_active())
        self.redis.set_value("af_available", "")
        self.assertFalse(self.ctrl.af_active())

    def test_it_is_not_active_when_lens_control_is_off(self):
        self.toggle(False)
        self.poll()
        self.assertFalse(self.ctrl.af_active())

    def test_focus_is_converted_to_dioptres_and_given_to_libcamera(self):
        ok, message = self.ctrl.set_focus(518.5)
        self.assertTrue(ok, message)
        self.assertEqual(self.redis.published("lens_position"), ["1.7850"])
        self.assertEqual(self.backend.focus_calls, [])            # never written directly

    def test_the_conversion_uses_the_saved_map_not_an_unsaved_recalibration(self):
        # libcamera's tuning was built from the saved entry; positions must
        # convert through the same map, whatever the working entry now holds.
        self.backend.sweep = no_encoder_sweep(mfd_cm=0)
        self.ctrl.request_calibration(mfd_m=0.5)                 # a 2.0 dioptre max
        self.poll()
        self.assertEqual(self.ctrl.working_entry()["focus"]["dioptre_max"], 2.0)
        self.ctrl.set_focus(0)
        self.assertEqual(self.redis.published("lens_position")[-1], "3.5700")   # saved map's 3.57

    def test_manual_focus_takes_the_lens_back_from_autofocus(self):
        self.redis.set_value("af_mode", "continuous")
        self.ctrl.set_focus(300)
        self.assertEqual(self.value("af_mode"), "manual")

    def test_focus_positions_beyond_the_map_clamp_to_its_ends(self):
        self.ctrl.set_focus(5000)
        self.ctrl.set_focus(-5)
        self.assertEqual(self.redis.published("lens_position"), ["0.0000", "3.5700"])

    def test_step_focus_starts_from_where_libcamera_says_the_lens_is(self):
        self.redis.set_value("lens_position_actual", "1.785")        # = position 518.5
        ok, _ = self.ctrl.step_focus(1)
        self.assertTrue(ok)
        # one step is 1 % of the range (11 positions) towards infinity: fewer dioptres
        self.assertLess(float(self.value("lens_position")), 1.785)
        self.assertAlmostEqual(float(self.value("lens_position")), 1.785 - 11 * 3.57 / 1037, places=3)
        self.assertEqual(self.backend.focus_calls, [])

    def test_without_autofocus_focus_goes_to_the_board_again(self):
        self.redis.set_value("af_available", "")
        self.ctrl.set_focus(300)
        self.assertEqual(self.backend.focus_calls, [300])
        self.assertEqual(self.redis.published("lens_position"), [])

    def test_iris_is_never_libcamera_s(self):
        self.assertTrue(self.ctrl.set_iris(4.0)[0])
        self.assertEqual(self.backend.iris_calls, [4.0])

    def test_one_shot_af_sets_auto_and_triggers_a_start(self):
        ok, message = self.ctrl.af_once()
        self.assertTrue(ok, message)
        self.assertEqual(self.value("af_mode"), "auto")
        self.assertEqual(self.value("af_trigger"), "start")

    def test_the_trigger_is_published_every_time_it_is_edge_triggered(self):
        self.ctrl.af_once()
        self.ctrl.af_once()
        self.assertEqual(self.redis.published("af_trigger"), ["start", "start"])
        forced = [force for key, _, force in self.redis.writes if key == "af_trigger"]
        self.assertEqual(forced, [True, True])

    def test_continuous_af_is_the_operator_s_choice(self):
        self.assertTrue(self.ctrl.set_af_mode("continuous")[0])
        self.assertEqual(self.value("af_mode"), "continuous")
        self.assertTrue(self.ctrl.set_af_mode(" AUTO ")[0])
        self.assertEqual(self.value("af_mode"), "auto")

    def test_an_unknown_mode_is_refused(self):
        ok, message = self.ctrl.set_af_mode("turbo")
        self.assertFalse(ok)
        self.assertIn("turbo", message)

    def test_manual_mode_holds_the_lens_where_libcamera_reports_it(self):
        self.redis.set_value("lens_position_actual", "2.1")
        self.ctrl.set_af_mode("continuous")
        self.assertTrue(self.ctrl.set_af_mode("manual")[0])
        self.assertEqual(self.value("af_mode"), "manual")
        self.assertEqual(self.value("lens_position"), "2.1000")

    def test_cancel_stops_the_scan_and_holds(self):
        self.redis.set_value("lens_position_actual", "0.9")
        self.ctrl.af_once()
        ok, _ = self.ctrl.af_cancel()
        self.assertTrue(ok)
        self.assertEqual(self.value("af_trigger"), "cancel")
        self.assertEqual(self.value("af_mode"), "manual")
        self.assertEqual(self.value("lens_position"), "0.9000")

    def test_af_requests_say_why_when_it_is_not_active(self):
        self.redis.set_value("af_available", "")
        self.ctrl = self.make(autofocus_enabled=False)
        self.poll()
        for call in (self.ctrl.af_once, self.ctrl.af_cancel,
                     lambda: self.ctrl.set_af_mode("continuous")):
            ok, message = call()
            self.assertFalse(ok)
            self.assertIn("not available", message)
            self.assertIn("switched off in the settings", message)
        self.assertEqual(self.redis.published("af_trigger"), [])

    def test_the_reason_walks_through_what_is_missing(self):
        self.redis.set_value("af_available", "")
        self.ctrl = self.make(autofocus_enabled=True)
        self.poll()
        self.assertIn("restarted", self.ctrl.af_once()[1])
        self.backend.provenance = "i2c-raw"
        self.assertIn("kernel driver", self.ctrl.af_once()[1])

    def test_the_self_test_detector_is_suspended_while_af_is_active(self):
        self.backend.sweep = encoder_sweep()
        for _ in range(4):
            for moving in (True, False):
                self.backend.queue.append(frame(
                    moving=moving, focus_position_min=0, focus_position_max=0,
                    focus_position_cur=0))
                self.poll()
        for _ in range(10):
            self.backend.queue.append(frame(moving=False, focus_position_min=0,
                                            focus_position_max=0))
            self.poll()
        self.assertEqual(self.backend.calibrate_calls, 0)
        self.assertTrue(self.ctrl.status()["selftest"]["armed"] is False)

    def test_an_explicit_calibration_takes_autofocus_off_the_lens_first(self):
        self.backend.sweep = encoder_sweep()
        self.redis.set_value("af_mode", "continuous")
        self.ctrl.request_calibration()
        self.poll()
        self.assertEqual(self.value("af_mode"), "manual")


# ── asking for a camera restart (D17) ──────────────────────────────────────

class RestartTests(ControllerCase):
    KEY = "sigma-18-35-f1-8"

    def setUp(self):
        super().setUp()
        self.ctrl = self.make(autofocus_enabled=True)
        self.db.add(saved_entry(focus=TWO_POINT_FOCUS))

    def test_a_calibrated_saved_entry_with_no_matching_tuning_asks_for_a_restart(self):
        self.poll()
        self.assertEqual(len(self.restarts), 1)
        self.assertIn(self.KEY, self.restarts[0])
        self.assertEqual(self.ctrl.status()["af"]["restart_pending"], self.restarts[0])

    def test_it_asks_once_not_on_every_poll(self):
        self.poll(5)
        self.assertEqual(len(self.restarts), 1)

    def test_it_asks_again_if_the_restart_did_not_take(self):
        self.poll()
        self.clock.advance(controller_module.RESTART_RETRY_S + 1)
        self.poll()
        self.assertEqual(len(self.restarts), 2)

    def test_it_is_satisfied_once_the_camera_is_launched_with_the_tuning(self):
        self.poll()
        self.redis.set_value("af_available", self.KEY)
        self.poll()
        self.assertIsNone(self.ctrl.status()["af"]["restart_pending"])
        self.clock.advance(1000)
        self.poll()
        self.assertEqual(len(self.restarts), 1)

    def test_it_is_deferred_while_recording_and_sent_when_the_take_ends(self):
        self.set_rec(True)
        self.poll(3)
        self.assertEqual(self.restarts, [])
        self.assertIsNotNone(self.ctrl.status()["af"]["restart_pending"])
        self.set_rec(False)
        self.poll()
        self.assertEqual(len(self.restarts), 1)

    def test_a_lens_swap_makes_the_running_tuning_stale(self):
        other = self.db.add(saved_entry(name="Other", lens_id=7, focus=TWO_POINT_FOCUS))
        self.redis.set_value("af_available", self.KEY)
        self.poll()
        self.assertEqual(self.restarts, [])
        self.backend.data = frame(lens_id=7)
        self.poll()
        self.assertEqual(len(self.restarts), 1)
        self.assertIn(other, self.restarts[0])

    def test_changing_the_saved_calibration_makes_it_stale(self):
        self.redis.set_value("af_available", self.KEY)
        self.poll()
        self.assertEqual(self.restarts, [])
        self.db.update(self.KEY, focus={**TWO_POINT_FOCUS, "map": [0.0, 1000, 3.0, 0]})
        self.poll()
        self.assertEqual(len(self.restarts), 1)
        self.assertIn("changed", self.restarts[0])

    def test_not_asked_when_autofocus_is_off(self):
        self.ctrl = self.make(autofocus_enabled=False)
        self.poll(2)
        self.assertEqual(self.restarts, [])

    def test_the_setting_can_change_live(self):
        self.ctrl = self.make(autofocus_enabled=False)
        self.poll()
        self.ctrl.set_autofocus_enabled(True)
        self.poll()
        self.assertEqual(len(self.restarts), 1)

    def test_not_asked_without_the_kernel_driver(self):
        self.backend.provenance = "i2c-raw"
        self.poll(2)
        self.assertEqual(self.restarts, [])

    def test_not_asked_for_an_uncalibrated_entry(self):
        self.db.update(self.KEY, focus=None)
        self.poll(2)
        self.assertEqual(self.restarts, [])

    def test_not_asked_for_an_unsaved_working_entry(self):
        self.db.delete(self.KEY)
        self.poll()
        self.ctrl.set_aperture_range(1.8, 16)
        self.backend.sweep = encoder_sweep()
        self.ctrl.request_calibration()
        self.poll(2)
        self.assertEqual(self.restarts, [])           # a tuning is built from the saved file

    def test_not_asked_while_lens_control_is_off(self):
        self.toggle(False)
        self.poll(2)
        self.assertEqual(self.restarts, [])

    def test_without_a_callback_nothing_happens(self):
        self.ctrl = LensController(self.redis, database=self.db, backend_factory=self._factory,
                                   clock=self.clock, sleep=self.clock.sleep,
                                   autofocus_enabled=True)
        self.poll(2)
        self.assertIsNone(self.ctrl.status()["af"]["restart_pending"])

    def test_a_callback_that_raises_does_not_stop_the_controller(self):
        def boom(reason):
            raise RuntimeError("restart machinery down")
        self.ctrl = self.make(autofocus_enabled=True, request_camera_restart=boom)
        with self.assertLogs("module.lens.controller", level="ERROR"):
            self.poll()
        self.poll()
        self.assertEqual(self.state(), "ready")


# ── the thread ─────────────────────────────────────────────────────────────

class RunLoopTests(ControllerCase):
    def test_run_polls_until_stopped_and_never_raises(self):
        ticks = []

        def sleep(seconds):
            ticks.append(seconds)
            self.clock.advance(seconds)
            if len(ticks) >= 6:
                self.ctrl.stop()

        self.ctrl._sleep_override = sleep
        self.ctrl.run()
        self.assertEqual(len(ticks), 6)
        self.assertEqual(self.value("lens_state"), "absent")      # published on the way out

    def test_the_idle_rate_applies_when_the_toggle_is_off_and_the_set_rate_when_on(self):
        self.ctrl = self.make(poll_hz=4.0, idle_poll_hz=1.0)
        self.poll()
        self.assertAlmostEqual(self.ctrl._interval(), 0.25)
        self.toggle(False)
        self.poll()
        self.assertAlmostEqual(self.ctrl._interval(), 1.0)

    def test_the_poll_rate_is_configurable(self):
        self.ctrl = self.make(poll_hz=10.0)
        self.poll()
        self.assertAlmostEqual(self.ctrl._interval(), 0.1)

    def test_an_unexpected_exception_is_contained_shown_and_retried(self):
        calls = {"n": 0}
        real_read = self.backend.read_data

        def explode_once():
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("a bug, not an I/O error")
            return real_read()

        self.backend.read_data = explode_once
        ticks = []

        def sleep(seconds):
            ticks.append(seconds)
            self.clock.advance(seconds)
            if len(ticks) == 2:
                self.assertEqual(self.value("lens_state"), "error")
                self.assertIn("a bug", self.value("lens_message"))
            if len(ticks) >= 40:
                self.ctrl.stop()

        self.ctrl._sleep_override = sleep
        with self.assertLogs("module.lens.controller", level="ERROR"):
            self.ctrl.run()
        # ... and after the retry delay it found the adapter again.
        self.assertEqual(self.value("lens_detected"), "0")      # stopped, so published absent
        self.assertGreaterEqual(len(self.factory_calls), 2)
        self.assertTrue(self.backend.closed)

    def test_a_failing_redis_never_takes_the_controller_down(self):
        def broken(*args, **kwargs):
            raise ConnectionError("redis is down")
        self.redis.set_value = broken
        self.poll(3)
        self.assertTrue(self.ctrl.effective())       # still running, still driving the lens
        self.assertTrue(self.ctrl.set_iris(4.0)[0])

    def test_stop_and_join_with_the_real_thread_and_clock(self):
        ctrl = LensController(self.redis, database=self.db, backend_factory=self._factory,
                              poll_hz=200.0, idle_poll_hz=200.0, detect_interval_s=0.01)
        ctrl.start()
        deadline = time.monotonic() + 3.0
        while self.value("lens_state") != "unknown_lens" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.value("lens_state"), "unknown_lens")
        ctrl.stop()
        ctrl.join(timeout=3.0)
        self.assertFalse(ctrl.is_alive())
        self.assertEqual(self.value("lens_detected"), "0")
        self.assertTrue(self.backend.closed)

    def test_the_thread_is_a_daemon_named_for_what_it_is(self):
        self.assertTrue(self.ctrl.daemon)
        self.assertEqual(self.ctrl.name, "LensController")


class ToggleSyncTests(ControllerCase):
    def test_the_controller_follows_the_redis_toggle(self):
        self.poll()
        self.assertTrue(self.ctrl.enabled())
        self.toggle(False)
        self.poll()
        self.assertFalse(self.ctrl.enabled())

    def test_set_enabled_on_writes_redis_when_found(self):
        self.toggle(False)
        self.poll()
        ok, message = self.ctrl.set_enabled(True)
        self.assertTrue(ok, message)
        self.assertEqual(self.value("lens_control"), "1")
        self.assertTrue(self.ctrl.effective())


class StatusTests(ControllerCase):
    def test_status_is_json_serialisable_and_complete(self):
        self.db.add(saved_entry(focus=TWO_POINT_FOCUS))
        self.poll()
        status = self.ctrl.status()
        json.dumps(status)
        for key in ("enabled", "found", "effective", "state", "message", "provenance", "port",
                    "bus", "bus_source", "lens_id", "lens_key", "lens_name", "working", "dirty",
                    "aperture_range", "capabilities", "iris", "iris_steps", "focus_position",
                    "focus_range", "board", "calibration", "selftest", "af"):
            self.assertIn(key, status)
        self.assertEqual(status["state"], "ready")
        self.assertEqual(status["focus_range"], [0, 1069])
        self.assertEqual(status["iris_steps"][0], 1.8)

    def test_status_before_anything_is_found(self):
        self.factory_result = (None, "nothing here")
        self.ctrl = self.make()
        status = self.ctrl.status()
        self.assertEqual((status["found"], status["state"]), (False, "absent"))
        self.assertIsNone(status["lens_id"])
        json.dumps(status)

    def test_effective_is_toggle_and_found(self):
        self.assertFalse(self.ctrl.effective())       # not polled yet: not found
        self.poll()
        self.assertTrue(self.ctrl.effective())


if __name__ == "__main__":
    unittest.main()
