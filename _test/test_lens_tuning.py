"""The autofocus tuning layer: lens calibration in, a derived tuning file out.

module/lens_tuning.py turns one lens database entry's `focus` section into an
`rpi.af` block, splices it into whichever base tuning is active, and writes the
result under a name that carries a hash of both inputs (PLAN.md D9). Its
module docstring explains why it must degrade rather than raise: a tuning file
libcamera cannot load blacks the camera instead of merely losing autofocus.
These tests pin that contract off hardware:

  * the block holds only keys libcamera's af.cpp reads, with PDAF zeroed;
  * a map libcamera would silently replace with its generic one is refused up
    front, because for a Canon lens that generic map points at wrong positions;
  * placement matches where Pinefeat and libcamera's own imx708 tuning keep it;
  * the file name is a function of the base bytes and the block, so changing
    the base tuning yields a new instance by itself, and an unchanged pair is
    reused rather than rewritten;
  * every failure is (None, reason) and nothing is half-written.

The launch wiring (gate, Redis, --autofocus-mode manual) has its own file,
test_lens_tuning_launch.py.
"""

import copy
import json
import math
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module import lens_tuning  # noqa: E402
from module.lens_tuning import (  # noqa: E402
    LensTuningError,
    af_section,
    autofocus_gate,
    build_lens_tuning,
    load_lens_entry,
)
from module.tuning_files import tuning_json_problem  # noqa: E402

# Every key af.cpp's CfgParams::read / RangeDependentParams::read /
# SpeedDependentParams::read consults (libcamera/src/ipa/rpi/controller/rpi/
# af.cpp lines 80-82, 87-95, 100-142). A key outside these is one libcamera
# would silently ignore, which the module promises not to emit.
AF_CPP_TOP_KEYS = {"ranges", "speeds", "conf_epsilon", "conf_thresh", "conf_clip", "skip_frames", "map"}
AF_CPP_RANGE_KEYS = {"min", "max", "default"}
AF_CPP_SPEED_KEYS = {
    "step_coarse", "step_fine", "contrast_ratio", "pdaf_gain", "pdaf_squelch",
    "max_slew", "pdaf_frames", "dropout_frames", "step_frames",
}

# PLAN.md section 3's example entry, focus section.
FOCUS = {
    "calibrated_at": "2026-10-04T12:00:00Z",
    "position_min": 0,
    "position_max": 1069,
    "mfd_m": 0.28,
    "distance_encoder": False,
    "map": [0.0, 1037, 3.57, 0],
    "dioptre_min": 0.0,
    "dioptre_max": 3.57,
    "step_frames": 4,
}
ENTRY = {"name": "Sigma 18-35 f/1.8", "lens_id": 235, "focus": FOCUS}


def focus(**changes):
    out = copy.deepcopy(FOCUS)
    out.update(changes)
    return out


def entry(**focus_changes):
    return {"name": "x", "lens_id": 1, "focus": focus(**focus_changes)}


def tuning(algorithms, target="pisp", **extra):
    data = {"version": 2.0, "target": target, "algorithms": algorithms}
    data.update(extra)
    return json.dumps(data, indent=4)


def names(path):
    return [next(iter(a)) for a in json.loads(Path(path).read_text())["algorithms"]]


class TmpCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.cache = self.tmp / "cache"

    def base(self, text=None, name="imx477.json"):
        path = self.tmp / name
        path.write_text(text if text is not None else tuning([
            {"rpi.ccm": {}}, {"rpi.sharpen": {}}, {"rpi.hdr": {}}, {"rpi.sync": {}},
        ]))
        return path

    def build(self, base, ent=ENTRY, **kw):
        return build_lens_tuning(base, ent, self.cache, **kw)

    def derived_files(self, stem="imx477"):
        return sorted(p.name for p in self.cache.glob(f"{stem}.*.json")) if self.cache.exists() else []


class AfSectionTests(unittest.TestCase):
    def test_block_for_the_example_entry(self):
        section = af_section(FOCUS)
        self.assertEqual(section["ranges"], {"normal": {"min": 0.0, "max": 3.57, "default": 3.57}})
        self.assertEqual(section["map"], [0.0, 1037, 3.57, 0])
        speed = section["speeds"]["normal"]
        self.assertEqual(speed["step_frames"], 4)
        self.assertEqual(speed["step_coarse"], 0.2)
        self.assertEqual(speed["step_fine"], 0.05)
        self.assertEqual(speed["contrast_ratio"], 0.75)
        self.assertEqual(speed["max_slew"], 2.0)

    def test_only_keys_afcpp_reads_and_only_the_normal_range_and_speed(self):
        section = af_section(FOCUS)
        self.assertEqual(set(section), AF_CPP_TOP_KEYS)
        self.assertEqual(set(section["ranges"]), {"normal"})
        self.assertEqual(set(section["ranges"]["normal"]), AF_CPP_RANGE_KEYS)
        self.assertEqual(set(section["speeds"]), {"normal"})
        self.assertEqual(set(section["speeds"]["normal"]), AF_CPP_SPEED_KEYS)

    def test_pdaf_is_zeroed(self):
        section = af_section(FOCUS)
        speed = section["speeds"]["normal"]
        for key in ("pdaf_gain", "pdaf_squelch", "pdaf_frames", "dropout_frames"):
            self.assertEqual(speed[key], 0, key)
        for key in ("conf_epsilon", "conf_thresh", "conf_clip"):
            self.assertEqual(section[key], 0, key)

    def test_step_frames_comes_from_the_entry(self):
        self.assertEqual(af_section(focus(step_frames=9))["speeds"]["normal"]["step_frames"], 9)

    def test_step_frames_defaults_to_pinefeats_value_when_absent(self):
        f = focus()
        del f["step_frames"]
        self.assertEqual(af_section(f)["speeds"]["normal"]["step_frames"], 4)

    def test_integral_float_step_frames_is_accepted(self):
        self.assertEqual(af_section(focus(step_frames=6.0))["speeds"]["normal"]["step_frames"], 6)

    def test_range_defaults_to_the_map_span_when_the_entry_has_none(self):
        f = focus(map=[0.00153, 1069, 0.5, 996, 4.35, 0])
        del f["dioptre_min"], f["dioptre_max"]
        rng = af_section(f)["ranges"]["normal"]
        self.assertEqual(rng, {"min": 0.00153, "max": 4.35, "default": 4.35})

    def test_a_multi_point_map_passes_through_untouched(self):
        pairs = [0.00153, 1069, 0.154, 1042, 0.446, 996, 4.35, 0]
        section = af_section(focus(map=pairs, dioptre_min=0.00153, dioptre_max=4.35))
        self.assertEqual(section["map"], pairs)

    def test_section_is_json_serialisable(self):
        json.dumps(af_section(FOCUS), allow_nan=False)

    def test_does_not_modify_its_input(self):
        original = copy.deepcopy(FOCUS)
        af_section(FOCUS)
        self.assertEqual(FOCUS, original)

    def test_no_focus_section(self):
        for bad in (None, "x", [], 3):
            with self.assertRaises(LensTuningError, msg=repr(bad)):
                af_section(bad)

    def test_invalid_maps_are_refused_for_the_right_reason(self):
        # The reason is asserted, not just the refusal: an entry whose range
        # also disagrees with a broken map would be refused either way.
        two = "at least two"
        asc = "strictly ascending"
        finite = "not a finite number"
        cases = {
            "missing": (None, two),
            "not a list": ("0,1,2,3", two),
            "empty": ([], two),
            "one point": ([0.0, 1037], two),
            "odd length": ([0.0, 1037, 3.57], two),
            "equal dioptres": ([1.0, 100, 1.0, 50], asc),
            "descending dioptres": ([3.57, 0, 0.0, 1037], asc),
            "closer than libcamera's epsilon": ([1.0, 100, 1.0000005, 50], asc),
            "nan": ([0.0, 1037, float("nan"), 0], finite),
            "infinity": ([0.0, 1037, math.inf, 0], finite),
            "string value": ([0.0, "1037", 3.57, 0], finite),
            "boolean value": ([0.0, True, 3.57, 0], finite),
            "negative dioptre": ([-0.5, 1037, 3.57, 0], "negative dioptre"),
            "negative position": ([0.0, -1, 3.57, 0], "negative lens position"),
        }
        for label, (bad, fragment) in cases.items():
            f = focus(map=bad)
            if bad is None:
                del f["map"]
            with self.subTest(label), self.assertRaisesRegex(LensTuningError, fragment):
                af_section(f)

    def test_invalid_dioptre_ranges_are_refused_for_the_right_reason(self):
        empty = "empty or negative"
        outside = "outside the focus map"
        cases = {
            "min equals max": ({"dioptre_min": 1.0, "dioptre_max": 1.0}, empty),
            "min above max": ({"dioptre_min": 3.0, "dioptre_max": 1.0}, empty),
            "negative min": ({"dioptre_min": -1.0}, empty),
            "max beyond the map": ({"dioptre_max": 5.0}, outside),
            "min before the map": ({"dioptre_min": 0.0, "map": [0.5, 1037, 3.57, 0]}, outside),
            "not a number": ({"dioptre_max": "3.57"}, "finite numbers"),
            "nan": ({"dioptre_max": float("nan")}, "finite numbers"),
            "null": ({"dioptre_max": None}, "finite numbers"),
        }
        for label, (change, fragment) in cases.items():
            with self.subTest(label), self.assertRaisesRegex(LensTuningError, fragment):
                af_section(focus(**change))

    def test_rounding_slack_in_the_range_is_tolerated(self):
        # The calibrator rounds the range and the map separately.
        af_section(focus(dioptre_max=3.575, map=[0.0, 1037, 3.5701, 0]))

    def test_invalid_step_frames_are_refused(self):
        for bad in (0, -1, "4", True, 2.5, None):
            with self.subTest(repr(bad)), self.assertRaises(LensTuningError):
                af_section(focus(step_frames=bad))


class PlacementTests(TmpCase):
    def test_goes_before_rpi_hdr(self):
        path, reason = self.build(self.base())
        self.assertEqual(reason, "ok")
        self.assertEqual(names(path), ["rpi.ccm", "rpi.sharpen", "rpi.af", "rpi.hdr", "rpi.sync"])

    def test_hdr_wins_even_when_it_comes_before_sharpen(self):
        base = self.base(tuning([{"rpi.hdr": {}}, {"rpi.sharpen": {}}]))
        path, _ = self.build(base)
        self.assertEqual(names(path), ["rpi.af", "rpi.hdr", "rpi.sharpen"])

    def test_goes_after_rpi_sharpen_when_there_is_no_hdr(self):
        base = self.base(tuning([{"rpi.ccm": {}}, {"rpi.sharpen": {}}, {"rpi.sync": {}}]))
        path, _ = self.build(base)
        self.assertEqual(names(path), ["rpi.ccm", "rpi.sharpen", "rpi.af", "rpi.sync"])

    def test_is_appended_when_there_is_neither(self):
        base = self.base(tuning([{"rpi.black_level": {}}, {"rpi.contrast": {}}]))
        path, _ = self.build(base)
        self.assertEqual(names(path), ["rpi.black_level", "rpi.contrast", "rpi.af"])

    def test_an_existing_af_block_is_replaced_not_duplicated(self):
        # A stock imx708-style file, PDAF settings and all.
        stock_af = {"rpi.af": {"ranges": {"normal": {"min": 0.0, "max": 12.0, "default": 1.0}},
                               "speeds": {"normal": {"pdaf_gain": -0.02, "pdaf_frames": 20}},
                               "map": [0.0, 445, 15.0, 925]}}
        base = self.base(tuning([{"rpi.ccm": {}}, {"rpi.sharpen": {}}, stock_af, {"rpi.hdr": {}}]))
        path, _ = self.build(base)
        self.assertEqual(names(path), ["rpi.ccm", "rpi.sharpen", "rpi.af", "rpi.hdr"])
        af = [a for a in json.loads(path.read_text())["algorithms"] if "rpi.af" in a][0]["rpi.af"]
        self.assertEqual(af["map"], [0.0, 1037, 3.57, 0])
        self.assertEqual(af["speeds"]["normal"]["pdaf_gain"], 0.0)

    def test_the_rest_of_the_file_is_untouched(self):
        algorithms = [{"rpi.black_level": {"black_level": 3200}},
                      {"rpi.ccm": {"ccms": [{"ct": 2000, "ccm": [1.5, -0.2, 0.1]}]}},
                      {"rpi.sharpen": {"threshold": 0.25}},
                      {"rpi.hdr": {"Off": {"cadence": [0]}}}]
        base = self.base(tuning(algorithms, comment_free_extra=1))
        path, _ = self.build(base)
        derived = json.loads(path.read_text())
        original = json.loads(base.read_text())
        self.assertEqual(derived["version"], original["version"])
        self.assertEqual(derived["target"], original["target"])
        self.assertEqual(derived["comment_free_extra"], 1)
        self.assertEqual(
            [a for a in derived["algorithms"] if "rpi.af" not in a], original["algorithms"],
        )

    def test_the_derived_file_passes_the_launch_guard(self):
        path, _ = self.build(self.base())
        self.assertIsNone(tuning_json_problem(json.loads(path.read_text())))

    def test_the_base_file_is_never_modified(self):
        base = self.base()
        before = base.read_bytes()
        self.build(base)
        self.assertEqual(base.read_bytes(), before)

    def test_the_af_block_is_exactly_af_section(self):
        path, _ = self.build(self.base())
        af = [a for a in json.loads(path.read_text())["algorithms"] if "rpi.af" in a][0]
        self.assertEqual(af, {"rpi.af": af_section(FOCUS)})

    def test_vc4_base_is_accepted_for_bcm2835(self):
        base = self.base(tuning([{"rpi.sharpen": {}}, {"rpi.hdr": {}}], target="bcm2835"))
        path, reason = self.build(base, expected_target="bcm2835")
        self.assertEqual(reason, "ok")
        self.assertEqual(json.loads(path.read_text())["target"], "bcm2835")


class NamingAndReuseTests(TmpCase):
    def test_name_is_base_stem_dot_hash12(self):
        path, _ = self.build(self.base())
        self.assertEqual(path.parent, self.cache)
        self.assertRegex(path.name, r"^imx477\.[0-9a-f]{12}\.json$")

    def test_same_inputs_give_the_same_file_and_it_is_not_rewritten(self):
        base = self.base()
        first, _ = self.build(base)
        with mock.patch.object(lens_tuning, "_write_atomic") as write:
            second, _ = self.build(base)
        self.assertEqual(first, second)
        write.assert_not_called()
        self.assertEqual(len(self.derived_files()), 1)

    def test_changing_the_base_yields_a_new_instance(self):
        # The operator's requirement: switch the base tuning and a new derived
        # file appears by itself. Even a whitespace-only edit counts, because
        # the hash covers the base's bytes, not its parsed value.
        base = self.base()
        first, _ = self.build(base)
        base.write_text(base.read_text() + "\n")
        second, _ = self.build(base)
        self.assertNotEqual(first, second)
        self.assertEqual(self.derived_files(), sorted([first.name, second.name]))

    def test_a_different_base_with_the_same_stem_name_gets_its_own_file(self):
        other = self.tmp / "other"
        other.mkdir()
        one, _ = self.build(self.base())
        (other / "imx477.json").write_text(tuning([{"rpi.sharpen": {"x": 1}}]))
        two, _ = self.build(other / "imx477.json")
        self.assertNotEqual(one.name, two.name)

    def test_changing_the_lens_calibration_yields_a_new_instance(self):
        base = self.base()
        one, _ = self.build(base, entry(step_frames=4))
        two, _ = self.build(base, entry(step_frames=8))
        three, _ = self.build(base, entry(map=[0.0, 1000, 3.0, 0], dioptre_max=3.0))
        self.assertEqual(len({one, two, three}), 3)

    def test_fields_outside_the_af_block_do_not_change_the_name(self):
        # last_iris, last_used, the lens name... are operational, not tuning.
        base = self.base()
        one, _ = self.build(base, ENTRY)
        noisy = copy.deepcopy(ENTRY)
        noisy.update({"name": "Renamed", "last_used": "2027-01-01T00:00:00Z", "last_iris": 5.6})
        noisy["focus"]["calibrated_at"] = "2027-01-01T00:00:00Z"
        two, _ = self.build(base, noisy)
        self.assertEqual(one, two)

    def test_a_hand_edited_derived_file_is_restored(self):
        base = self.base()
        path, _ = self.build(base)
        good = path.read_bytes()
        path.write_text("{}")
        again, reason = self.build(base)
        self.assertEqual((again, reason), (path, "ok"))
        self.assertEqual(path.read_bytes(), good)

    def test_no_temp_files_are_left_behind(self):
        self.build(self.base())
        self.assertEqual([p.name for p in self.cache.iterdir() if p.name.endswith(".tmp")], [])

    def test_cache_dir_is_created_when_missing(self):
        nested = self.tmp / "a" / "b" / "tuning"
        path, reason = build_lens_tuning(self.base(), ENTRY, nested)
        self.assertEqual(reason, "ok")
        self.assertEqual(path.parent, nested)

    def test_default_cache_dir_is_cinemates_own(self):
        self.assertEqual(lens_tuning.DEFAULT_CACHE_DIR, Path("/home/pi/.cache/cinemate/tuning"))
        with mock.patch.object(lens_tuning, "DEFAULT_CACHE_DIR", self.cache):
            path, _ = build_lens_tuning(self.base(), ENTRY)
        self.assertEqual(path.parent, self.cache)


class PruneTests(TmpCase):
    def _build_generations(self, count, keep, stem="imx477"):
        base = self.base(name=f"{stem}.json")
        paths = []
        for n in range(count):
            base.write_text(tuning([{"rpi.sharpen": {"generation": n}}]))
            path, reason = self.build(base, keep=keep)
            self.assertEqual(reason, "ok")
            os.utime(path, (1_000_000 + n, 1_000_000 + n))   # strictly increasing age
            paths.append(path)
        return paths

    def test_oldest_are_pruned_beyond_the_cap(self):
        paths = self._build_generations(6, keep=3)
        self.assertEqual(self.derived_files(), sorted(p.name for p in paths[-3:]))

    def test_the_file_just_written_is_never_pruned(self):
        paths = self._build_generations(4, keep=1)
        self.assertTrue(paths[-1].exists())
        self.assertEqual(self.derived_files(), [paths[-1].name])

    def test_other_stems_and_unrelated_files_are_left_alone(self):
        self.cache.mkdir(parents=True)
        other = self.cache / "imx585.0123456789ab.json"
        other.write_text("{}")
        longer = self.cache / "imx477_mono.0123456789ab.json"   # a different stem, not ours
        longer.write_text("{}")
        note = self.cache / "notes.txt"
        note.write_text("x")
        self._build_generations(5, keep=2)
        for survivor in (other, longer, note):
            self.assertTrue(survivor.exists(), survivor.name)

    def test_a_prune_failure_never_fails_the_build(self):
        with mock.patch("pathlib.Path.unlink", side_effect=PermissionError("nope")):
            paths = self._build_generations(3, keep=1)
        # The prune ran and could not delete: all three are still there.
        self.assertEqual(self.derived_files(), sorted(p.name for p in paths))


class FailureTests(TmpCase):
    """Every failure is (None, reason), never an exception, and leaves
    nothing behind that libcamera could mistake for a tuning."""

    def assertFails(self, result, fragment):
        path, reason = result
        self.assertIsNone(path)
        self.assertIn(fragment, reason)
        self.assertEqual(self.derived_files(), [])

    def test_base_missing(self):
        self.assertFails(self.build(self.tmp / "absent.json"), "base tuning not found")

    def test_base_is_none(self):
        self.assertFails(self.build(None), "no base tuning file")

    def test_base_unreadable(self):
        self.assertFails(self.build(self.tmp), "base tuning")   # a directory

    def test_base_not_json(self):
        self.assertFails(self.build(self.base("not json")), "not JSON")

    def test_base_not_utf8(self):
        path = self.tmp / "bin.json"
        path.write_bytes(b"\xff\xfe\x00")
        self.assertFails(self.build(path), "not JSON")

    def test_base_for_the_other_platform(self):
        vc4 = self.base(tuning([{"rpi.sharpen": {}}], target="bcm2835"))
        self.assertFails(self.build(vc4), 'expected "pisp"')
        pisp = self.base(tuning([{"rpi.sharpen": {}}], target="pisp"), name="p.json")
        path, reason = self.build(pisp, expected_target="bcm2835")
        self.assertIsNone(path)
        self.assertIn('expected "bcm2835"', reason)

    def test_base_without_an_algorithms_list(self):
        self.assertFails(self.build(self.base(json.dumps({"target": "pisp"}))), "algorithms")

    def test_base_that_cannot_be_reserialised(self):
        text = '{"target": "pisp", "algorithms": [{"rpi.sharpen": {"x": NaN}}]}'
        self.assertFails(self.build(self.base(text)), "cannot be re-serialised")

    def test_entry_without_a_focus_section(self):
        base = self.base()
        for bad in ({"name": "x"}, {"name": "x", "focus": None}, None, "x"):
            with self.subTest(repr(bad)):
                self.assertFails(self.build(base, bad), "focus")

    def test_invalid_map_keeps_nothing_and_names_it(self):
        self.assertFails(self.build(self.base(), entry(map=[3.0, 1, 1.0, 2])), "ascending")

    def test_unwritable_cache_dir(self):
        blocker = self.tmp / "blocker"
        blocker.write_text("a file where a directory should be")
        path, reason = build_lens_tuning(self.base(), ENTRY, blocker / "tuning")
        self.assertIsNone(path)
        self.assertIn("tuning cache unavailable", reason)

    def test_a_write_failure_is_reported(self):
        with mock.patch.object(lens_tuning, "_write_atomic", side_effect=OSError("disk full")):
            path, reason = self.build(self.base())
        self.assertIsNone(path)
        self.assertIn("disk full", reason)

    def test_an_unexpected_exception_is_contained(self):
        with mock.patch.object(lens_tuning, "_build", side_effect=RuntimeError("boom")):
            path, reason = self.build(self.base())
        self.assertIsNone(path)
        self.assertEqual(reason, "unexpected RuntimeError: boom")


class LoadLensEntryTests(TmpCase):
    def db(self, text):
        path = self.tmp / "lenses.json"
        path.write_text(text)
        return path

    def test_found(self):
        path = self.db(json.dumps({"schema": 1, "lenses": {"sigma": ENTRY, "other": {"name": "o"}}}))
        found, reason = load_lens_entry(str(path), "sigma")
        self.assertEqual((found, reason), (ENTRY, "ok"))

    def test_missing_file_is_an_empty_database(self):
        found, reason = load_lens_entry(str(self.tmp / "nope.json"), "sigma")
        self.assertIsNone(found)
        self.assertIn("no lens database", reason)

    def test_missing_key(self):
        path = self.db(json.dumps({"schema": 1, "lenses": {}}))
        found, reason = load_lens_entry(str(path), "sigma")
        self.assertIsNone(found)
        self.assertIn('no lens "sigma"', reason)

    def test_not_json(self):
        found, reason = load_lens_entry(str(self.db("{ nope")), "sigma")
        self.assertIsNone(found)
        self.assertIn("not JSON", reason)

    def test_no_lenses_object(self):
        for text in ("[]", json.dumps({"schema": 1}), json.dumps({"lenses": []})):
            with self.subTest(text):
                found, reason = load_lens_entry(str(self.db(text)), "sigma")
                self.assertIsNone(found)
                self.assertIn('"lenses"', reason)

    def test_entry_that_is_not_an_object(self):
        found, _ = load_lens_entry(str(self.db(json.dumps({"lenses": {"sigma": 3}}))), "sigma")
        self.assertIsNone(found)

    def test_unknown_fields_are_returned_untouched(self):
        rich = dict(ENTRY, future_field={"a": 1})
        path = self.db(json.dumps({"schema": 1, "extra": 2, "lenses": {"sigma": rich}}))
        self.assertEqual(load_lens_entry(str(path), "sigma")[0], rich)

    def test_no_value_means_the_default_repo_relative_file(self):
        for value in (None, ""):
            found, reason = load_lens_entry(value, "sigma")
            self.assertIsNone(found)
            self.assertIn(str(ROOT / "resources" / "lenses.json"), reason)

    def test_a_relative_value_resolves_against_the_repo_root(self):
        found, reason = load_lens_entry("resources/does-not-exist-lenses.json", "sigma")
        self.assertIsNone(found)
        self.assertIn(str(ROOT / "resources" / "does-not-exist-lenses.json"), reason)


class AutofocusGateTests(unittest.TestCase):
    OK = dict(
        autofocus=True, lens_control="1", lens_detected="1", provenance="v4l2-subdev",
        lens_port="cam0", lens_key="sigma", camera_port="cam0",
    )

    def gate(self, **changes):
        return autofocus_gate(**{**self.OK, **changes})

    def test_all_conditions_met(self):
        self.assertEqual(self.gate(), ("sigma", "ok"))

    def test_each_condition_is_required(self):
        cases = {
            "autofocus off": ({"autofocus": False}, "autofocus is off"),
            "lens control off": ({"lens_control": "0"}, "lens control is off"),
            "lens control unset": ({"lens_control": None}, "lens control is off"),
            "no adapter": ({"lens_detected": "0"}, "no adapter"),
            "raw backend": ({"provenance": "i2c-raw"}, "i2c-raw"),
            "no provenance": ({"provenance": ""}, "nothing"),
            "other camera": ({"lens_port": "cam1"}, "cam1"),
            "no port": ({"lens_port": ""}, "no port"),
            "no lens selected": ({"lens_key": ""}, "no lens is selected"),
            "lens key unset": ({"lens_key": None}, "no lens is selected"),
        }
        for label, (change, fragment) in cases.items():
            with self.subTest(label):
                key, reason = self.gate(**change)
                self.assertIsNone(key)
                self.assertIn(fragment, reason)

    def test_the_first_unmet_condition_is_the_one_named(self):
        _, reason = self.gate(autofocus=False, lens_detected="0")
        self.assertIn("autofocus is off", reason)

    def test_redis_values_may_be_bytes_or_padded(self):
        self.assertEqual(
            self.gate(lens_control=b"1", lens_detected=" 1 ", provenance=b"v4l2-subdev",
                      lens_port=b"cam0", lens_key=b"sigma"),
            ("sigma", "ok"),
        )

    def test_single_camera_waives_the_port_comparison_only(self):
        self.assertEqual(self.gate(lens_port="cam1", single_camera=True), ("sigma", "ok"))
        self.assertEqual(self.gate(lens_port="", single_camera=True), ("sigma", "ok"))
        key, _ = self.gate(lens_detected="0", single_camera=True)
        self.assertIsNone(key)


class ModuleHygieneTests(unittest.TestCase):
    def test_standard_library_only(self):
        # The module is imported with no camera and no Redis; its only
        # in-repo imports are the two stdlib-only siblings.
        source = (ROOT / "src/module/lens_tuning.py").read_text()
        imported = set(re.findall(r"^(?:from|import) ([\w.]+)", source, re.M))
        project = {name for name in imported if name.startswith("module")}
        self.assertEqual(project, {"module.sensor_database", "module.tuning_files"})
        for name in ("redis", "psutil", "smbus", "smbus2", "module.redis_controller"):
            self.assertNotIn(name, imported)


if __name__ == "__main__":
    unittest.main()
