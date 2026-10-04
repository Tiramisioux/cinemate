"""module/lens/database.py: the lens file, the iris table, the focus map.

The database is operator data written by the camera, so most of these tests are
about not losing it: atomic writes, unknown fields, a corrupt file, two readers.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.lens import database  # noqa: E402
from module.lens.database import (  # noqa: E402
    IRIS_STEPS,
    LensDatabase,
    LensDatabaseError,
    capabilities_of,
    clamp_iris,
    dioptre_to_position,
    focus_map,
    format_aperture_range,
    iris_steps_for,
    is_calibrated,
    position_to_dioptre,
    slug,
    step_iris_value,
)

FIXED = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)


def entry(name="Sigma 18-35 f/1.8", lens_id=235, **extra):
    return {"name": name, "lens_id": lens_id, **extra}


class TempDbCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "lenses.json"
        self.db = LensDatabase(self.path, now=lambda: FIXED)

    def on_disk(self):
        return json.loads(self.path.read_text())


class SlugTests(unittest.TestCase):
    def test_the_contract_example(self):
        self.assertEqual(slug("Sigma 18-35 f/1.8"), "sigma-18-35-f1-8")

    def test_other_slashes_are_separators(self):
        self.assertEqual(slug("Canon EF 24/105mm f/4L IS"), "canon-ef-24-105mm-f4l-is")

    def test_accents_fold_to_ascii(self):
        self.assertEqual(slug("Ångström 50"), "angstrom-50")

    def test_nothing_usable_becomes_lens(self):
        self.assertEqual(slug("  "), "lens")
        self.assertEqual(slug("///"), "lens")


class PathTests(unittest.TestCase):
    def test_default_is_repo_relative(self):
        self.assertEqual(database.resolve_database_path(None),
                         ROOT / "resources" / "lenses.json")

    def test_absolute_paths_are_kept(self):
        self.assertEqual(database.resolve_database_path("/tmp/x.json"), Path("/tmp/x.json"))

    def test_relative_paths_resolve_like_the_sensor_database(self):
        from module.sensor_database import resolve_database_path as sensors
        self.assertEqual(database.resolve_database_path("resources/other.json"),
                         sensors("resources/other.json"))


class ReadTests(TempDbCase):
    def test_a_missing_file_is_an_empty_database_and_is_not_created_by_reading(self):
        self.assertEqual(self.db.entries(), {})
        self.assertEqual(self.db.load(), {})
        self.assertIsNone(self.db.get("anything"))
        self.assertFalse(self.path.exists())

    def test_the_first_write_creates_the_file(self):
        self.db.add(entry())
        self.assertTrue(self.path.exists())
        self.assertEqual(self.on_disk()["schema"], 1)

    def test_entries_are_copies(self):
        key = self.db.add(entry(aperture={"min": 1.8, "max": 16.0}))
        self.db.get(key)["aperture"]["min"] = 99
        self.db.entries()[key]["name"] = "changed"
        self.assertEqual(self.db.get(key)["aperture"]["min"], 1.8)
        self.assertEqual(self.db.get(key)["name"], "Sigma 18-35 f/1.8")

    def test_an_edit_made_elsewhere_is_seen_without_asking(self):
        key = self.db.add(entry())
        other = LensDatabase(self.path)
        other.update(key, last_iris=5.6)
        self.assertEqual(self.db.get(key)["last_iris"], 5.6)

    def test_a_hand_deleted_file_reads_empty_again(self):
        self.db.add(entry())
        self.path.unlink()
        self.assertEqual(self.db.entries(), {})


class WriteTests(TempDbCase):
    def test_add_returns_the_slug_and_stores_every_known_field(self):
        key = self.db.add(entry())
        self.assertEqual(key, "sigma-18-35-f1-8")
        stored = self.on_disk()["lenses"][key]
        self.assertEqual(stored["lens_id"], 235)
        for field in ("last_used", "aperture", "last_iris", "focus"):
            self.assertIn(field, stored)
            self.assertIsNone(stored[field])

    def test_a_clash_appends_a_numeric_suffix(self):
        keys = [self.db.add(entry()) for _ in range(3)]
        self.assertEqual(keys, ["sigma-18-35-f1-8", "sigma-18-35-f1-8-2", "sigma-18-35-f1-8-3"])

    def test_a_name_is_required(self):
        with self.assertRaises(ValueError):
            self.db.add(entry(name="  "))
        with self.assertRaises(ValueError):
            self.db.replace(self.db.add(entry()), entry(name=""))

    def test_replace_keeps_the_key_even_when_the_name_changes(self):
        key = self.db.add(entry())
        self.assertEqual(self.db.replace(key, entry(name="Renamed lens")), key)
        self.assertEqual(self.db.get(key)["name"], "Renamed lens")
        self.assertEqual(list(self.db.entries()), [key])

    def test_replace_of_a_missing_key_raises(self):
        with self.assertRaises(KeyError):
            self.db.replace("nope", entry())

    def test_update_merges_fields_and_returns_the_entry(self):
        key = self.db.add(entry())
        result = self.db.update(key, last_iris=2.8, aperture={"min": 1.8, "max": 16.0})
        self.assertEqual(result["last_iris"], 2.8)
        self.assertEqual(self.db.get(key)["name"], "Sigma 18-35 f/1.8")
        with self.assertRaises(KeyError):
            self.db.update("nope", last_iris=1)

    def test_delete(self):
        key = self.db.add(entry())
        self.assertTrue(self.db.delete(key))
        self.assertFalse(self.db.delete(key))
        self.assertEqual(self.on_disk()["lenses"], {})

    def test_touch_stamps_last_used_in_utc(self):
        key = self.db.add(entry())
        self.db.touch(key)
        self.assertEqual(self.db.get(key)["last_used"], "2026-10-04T12:00:00Z")
        with self.assertRaises(KeyError):
            self.db.touch("nope")

    def test_unknown_fields_survive_every_kind_of_rewrite(self):
        self.path.write_text(json.dumps({
            "schema": 1, "future_top_level": {"keep": True},
            "lenses": {"a": {"name": "A", "lens_id": 1, "notes": "hand written",
                             "aperture": None, "focus": None, "last_iris": None,
                             "last_used": None}},
        }))
        self.db.update("a", last_iris=4.0)
        self.db.add(entry(name="B"))
        self.db.touch("a")
        self.db.replace("a", {"name": "A2", "lens_id": 1})
        doc = self.on_disk()
        self.assertEqual(doc["future_top_level"], {"keep": True})
        self.assertEqual(doc["lenses"]["a"]["notes"], "hand written")
        self.assertEqual(doc["lenses"]["a"]["name"], "A2")

    def test_the_file_is_pretty_json_that_ends_with_a_newline(self):
        self.db.add(entry())
        text = self.path.read_text()
        self.assertTrue(text.endswith("}\n"))
        self.assertIn("\n  ", text)

    def test_non_ascii_names_are_written_as_is(self):
        self.db.add(entry(name="Zeiss Planar T* 50mm å"))
        self.assertIn("å", self.path.read_text(encoding="utf-8"))

    def test_no_temp_files_are_left_behind(self):
        for index in range(3):
            self.db.add(entry(name=f"Lens {index}"))
        self.assertEqual(sorted(os.listdir(self.path.parent)), ["lenses.json"])

    def test_a_failed_write_changes_neither_disk_nor_memory(self):
        key = self.db.add(entry())
        before = self.db.entries()
        real_replace = os.replace

        def refuse(src, dst):
            raise OSError(28, "No space left on device")

        os.replace = refuse
        try:
            with self.assertRaises(LensDatabaseError):
                self.db.update(key, last_iris=11.0)
        finally:
            os.replace = real_replace
        self.assertEqual(self.db.entries(), before)
        self.assertEqual(self.on_disk()["lenses"][key]["last_iris"], None)
        self.assertEqual(sorted(os.listdir(self.path.parent)), ["lenses.json"])

    def test_the_old_file_survives_a_crash_mid_write(self):
        # json.dump into the temp file fails half way: the real file is untouched.
        key = self.db.add(entry())
        original = self.path.read_text()
        real_dump = json.dump

        def explode(*args, **kwargs):
            raise RuntimeError("power cut")

        json.dump = explode
        try:
            with self.assertRaises(RuntimeError):
                self.db.update(key, last_iris=3.5)
        finally:
            json.dump = real_dump
        self.assertEqual(self.path.read_text(), original)
        self.assertEqual(sorted(os.listdir(self.path.parent)), ["lenses.json"])

    def test_concurrent_writers_do_not_lose_entries(self):
        errors = []

        def worker(n):
            try:
                for i in range(5):
                    self.db.add(entry(name=f"Lens {n}-{i}"))
            except Exception as exc:    # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(self.on_disk()["lenses"]), 20)


class CorruptFileTests(TempDbCase):
    def test_a_corrupt_file_reads_empty_and_says_so(self):
        self.path.write_text("{ not json")
        with self.assertLogs("module.lens.database", level="WARNING"):
            self.assertEqual(self.db.entries(), {})
        self.assertIn("unreadable", self.db.load_error)

    def test_the_first_write_moves_the_corrupt_file_aside_instead_of_destroying_it(self):
        self.path.write_text("{ not json")
        with self.assertLogs("module.lens.database", level="WARNING"):
            self.db.add(entry())
        names = sorted(os.listdir(self.path.parent))
        self.assertEqual(names, ["lenses.json", "lenses.json.corrupt-20261004T120000"])
        aside = self.path.parent / names[1]
        self.assertEqual(aside.read_text(), "{ not json")
        self.assertEqual(len(self.on_disk()["lenses"]), 1)
        self.assertIsNone(self.db.load_error)

    def test_a_file_of_the_wrong_shape_counts_as_corrupt(self):
        self.path.write_text("[1, 2, 3]")
        with self.assertLogs("module.lens.database", level="WARNING"):
            self.assertEqual(self.db.entries(), {})

    def test_entries_that_are_not_objects_are_dropped_on_read(self):
        self.path.write_text(json.dumps({"lenses": {"good": {"name": "G"}, "bad": 7}}))
        self.assertEqual(list(self.db.entries()), ["good"])


class MatchingTests(TempDbCase):
    def test_matching_returns_entries_with_that_id_in_file_order(self):
        a = self.db.add(entry(name="A", lens_id=10))
        self.db.add(entry(name="B", lens_id=11))
        c = self.db.add(entry(name="C", lens_id=10))
        self.assertEqual([k for k, _ in self.db.matching(10)], [a, c])
        self.assertEqual(self.db.matching(99), [])
        self.assertEqual(self.db.matching(None), [])

    def test_most_recent_picks_the_newest_last_used(self):
        a = self.db.add(entry(name="A", lens_id=10))
        b = self.db.add(entry(name="B", lens_id=10))
        self.db.touch(a, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.db.touch(b, datetime(2026, 6, 1, tzinfo=timezone.utc))
        self.assertEqual(self.db.most_recent(10), b)
        self.db.touch(a, datetime(2026, 9, 1, tzinfo=timezone.utc))
        self.assertEqual(self.db.most_recent(10), a)

    def test_an_entry_never_used_loses_to_one_that_was(self):
        a = self.db.add(entry(name="A", lens_id=10))
        self.db.add(entry(name="B", lens_id=10))
        self.db.touch(a)
        self.assertEqual(self.db.most_recent(10), a)

    def test_most_recent_of_nothing_is_none(self):
        self.assertIsNone(self.db.most_recent(10))


class CapabilityTests(TempDbCase):
    def test_a_new_entry_has_nothing_tested(self):
        key = self.db.add(entry())
        self.assertEqual(self.db.get(key)["capabilities"],
                         {"iris": None, "focus": None, "autofocus": None})

    def test_capabilities_survive_a_rewrite(self):
        key = self.db.add(entry(capabilities={"iris": True, "focus": False, "autofocus": False}))
        self.db.update(key, last_iris=2.8)
        self.db.touch(key)
        self.assertEqual(self.db.get(key)["capabilities"],
                         {"iris": True, "focus": False, "autofocus": False})

    def test_a_partial_block_is_filled_with_untested(self):
        self.assertEqual(capabilities_of({"capabilities": {"focus": True}}),
                         {"iris": None, "focus": True, "autofocus": None})

    def test_garbage_reads_as_untested(self):
        for bad in (None, "yes", 3, [], {"focus": "maybe"}):
            self.assertEqual(capabilities_of({"capabilities": bad}),
                             {"iris": None, "focus": None, "autofocus": None}, bad)

    def test_an_unknown_capability_key_is_kept(self):
        self.assertEqual(capabilities_of({"capabilities": {"zoom": True}})["zoom"], True)

    def test_an_old_file_without_the_block_reads_untested(self):
        self.path.write_text(json.dumps({"lenses": {"a": {"name": "A", "lens_id": 1}}}))
        self.assertEqual(capabilities_of(self.db.get("a"))["focus"], None)


class IrisTests(unittest.TestCase):
    def test_the_table_is_the_contract_s_thirty_one_third_stops(self):
        self.assertEqual(len(IRIS_STEPS), 31)
        self.assertEqual(IRIS_STEPS[0], 1.0)
        self.assertEqual(IRIS_STEPS[-1], 32.0)
        self.assertEqual(list(IRIS_STEPS), sorted(IRIS_STEPS))

    def test_no_range_means_the_full_table(self):
        self.assertEqual(iris_steps_for(None), list(IRIS_STEPS))
        self.assertEqual(iris_steps_for({"aperture": None}), list(IRIS_STEPS))
        self.assertEqual(iris_steps_for({"aperture": {"min": "x"}}), list(IRIS_STEPS))

    def test_a_range_clamps_the_table_and_keeps_its_own_endpoints(self):
        steps = iris_steps_for({"aperture": {"min": 1.8, "max": 22.6}})
        self.assertEqual(steps[0], 1.8)
        self.assertEqual(steps[-2:], [22.0, 22.6])
        self.assertNotIn(1.6, steps)
        self.assertNotIn(25.0, steps)
        self.assertEqual(len(steps), len(set(steps)))

    def test_an_endpoint_that_is_already_a_step_is_not_doubled(self):
        steps = iris_steps_for({"aperture": {"min": 2.8, "max": 16.0}})
        self.assertEqual((steps[0], steps[-1], steps.count(2.8), steps.count(16.0)),
                         (2.8, 16.0, 1, 1))

    def test_a_range_between_two_steps_still_offers_its_endpoints(self):
        self.assertEqual(iris_steps_for({"aperture": {"min": 2.9, "max": 3.0}}), [2.9, 3.0])

    def test_an_inverted_range_is_read_the_right_way_round(self):
        self.assertEqual(iris_steps_for({"aperture": {"min": 16.0, "max": 2.8}})[0], 2.8)

    def test_clamp_uses_the_range_or_the_table_ends(self):
        entry_ = {"aperture": {"min": 1.8, "max": 16.0}}
        self.assertEqual(clamp_iris(1.2, entry_), 1.8)
        self.assertEqual(clamp_iris(22, entry_), 16.0)
        self.assertEqual(clamp_iris(5.6, entry_), 5.6)
        self.assertEqual(clamp_iris(0.5), 1.0)
        self.assertEqual(clamp_iris(64), 32.0)

    def test_stepping_walks_third_stops_and_stops_at_the_ends(self):
        entry_ = {"aperture": {"min": 1.8, "max": 22.6}}
        self.assertEqual(step_iris_value(2.8, 1, entry_), 3.2)
        self.assertEqual(step_iris_value(2.8, -1, entry_), 2.5)
        self.assertEqual(step_iris_value(2.8, 3, entry_), 4.0)
        self.assertEqual(step_iris_value(1.8, -1, entry_), 1.8)
        self.assertEqual(step_iris_value(22.6, 1, entry_), 22.6)
        self.assertEqual(step_iris_value(22.0, 1, entry_), 22.6)

    def test_stepping_from_a_value_between_steps_snaps_in_the_direction_of_travel(self):
        self.assertEqual(step_iris_value(2.9, 1), 3.2)
        self.assertEqual(step_iris_value(2.9, -1), 2.8)

    def test_stepping_with_nothing_commanded_yet_starts_wide(self):
        self.assertEqual(step_iris_value(None, 1, {"aperture": {"min": 2.8, "max": 16.0}}), 2.8)

    def test_format_aperture_range(self):
        self.assertEqual(format_aperture_range({"aperture": {"min": 1.8, "max": 22.0}}), "1.8-22")
        self.assertEqual(format_aperture_range({"aperture": {"min": 5.6, "max": 22.6}}), "5.6-22.6")
        self.assertEqual(format_aperture_range({"aperture": None}), "")
        self.assertEqual(format_aperture_range(None), "")


README_MAP = [0.00153, 1069, 0.154, 1042, 0.446, 996, 0.719, 969, 0.971, 941, 1.2, 901,
              1.45, 860, 1.72, 805, 2.04, 764, 2.44, 682, 2.86, 559, 3.45, 388, 3.85, 252,
              4.35, 0]
TWO_POINT = [0.0, 1037, 3.57, 0]


def with_map(flat):
    return {"focus": {"map": flat}}


class FocusMapTests(unittest.TestCase):
    def test_a_two_point_map_is_usable(self):
        self.assertEqual(focus_map(with_map(TWO_POINT)), [(0.0, 1037.0), (3.57, 0.0)])
        self.assertTrue(is_calibrated(with_map(TWO_POINT)))

    def test_unusable_maps(self):
        for bad in (None, [], [0.0, 1037], [0.0, 1037, 3.57], "x",
                    [0.0, 1037, 0.0, 0],              # dioptres not ascending
                    [0.0, 500, 3.57, 600],            # positions ascending
                    [0.0, 500, 1.0, 500, 2.0, 0],     # a plateau
                    [0.0, "a", 1.0, 2]):
            self.assertIsNone(focus_map(with_map(bad)), bad)
            self.assertFalse(is_calibrated(with_map(bad)), bad)
        self.assertFalse(is_calibrated(None))
        self.assertFalse(is_calibrated({"focus": None}))

    def test_the_two_helpers_agree_on_the_ends_and_the_middle(self):
        entry_ = with_map(TWO_POINT)
        self.assertEqual(position_to_dioptre(entry_, 1037), 0.0)
        self.assertEqual(position_to_dioptre(entry_, 0), 3.57)
        self.assertAlmostEqual(position_to_dioptre(entry_, 518.5), 1.785)
        self.assertEqual(dioptre_to_position(entry_, 0.0), 1037)
        self.assertEqual(dioptre_to_position(entry_, 3.57), 0)
        self.assertAlmostEqual(dioptre_to_position(entry_, 1.785), 518.5)

    def test_they_are_inverses_across_a_multi_point_map(self):
        entry_ = with_map(README_MAP)
        for position in (0, 100, 252, 400, 559, 700, 941, 1000, 1069):
            dioptre = position_to_dioptre(entry_, position)
            self.assertAlmostEqual(dioptre_to_position(entry_, dioptre), position, places=6)

    def test_positions_and_dioptres_outside_the_map_clamp_to_its_ends(self):
        entry_ = with_map(TWO_POINT)
        self.assertEqual(position_to_dioptre(entry_, 5000), 0.0)
        self.assertEqual(position_to_dioptre(entry_, -50), 3.57)
        self.assertEqual(dioptre_to_position(entry_, 99), 0)
        self.assertEqual(dioptre_to_position(entry_, -1), 1037)

    def test_more_dioptres_is_nearer_which_is_a_lower_position(self):
        entry_ = with_map(README_MAP)
        self.assertGreater(dioptre_to_position(entry_, 0.5), dioptre_to_position(entry_, 2.0))

    def test_no_map_answers_none(self):
        self.assertIsNone(position_to_dioptre({"focus": None}, 100))
        self.assertIsNone(dioptre_to_position(None, 1.0))

    def test_a_bare_map_list_is_accepted_too(self):
        self.assertEqual(dioptre_to_position(TWO_POINT, 0.0), 1037)


class ImportWeightTests(unittest.TestCase):
    def test_the_database_imports_with_no_camera_and_no_redis(self):
        # The settings editor imports it as-is. A fresh interpreter, nothing stubbed.
        code = (
            "import sys; sys.path.insert(0, 'src');"
            "import module.lens.database;"
            "heavy = [m for m in ('redis', 'smbus2', 'smbus', 'flask', 'psutil', 'module.redis_controller') "
            "if m in sys.modules];"
            "assert not heavy, heavy"
        )
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
