"""WP-CM-7: the aspect pane's data source, GET /settings-editor/api/sensor-modes.

ASPECT-RATIOS.md steps 3 and 4: per camera, the ratio selection is the first
section and the mode table sits under it, filtered to the ratios selected for
that camera. "Rendering is not testable here; the endpoint is" (WP-CM-7's own
Tests note), so this covers exactly the five things that note lists:

1. the page is served the ratio table from the single canonical source
   (module.aspect_ratios / SensorDetect.aspect_ratio_table, not a second copy
   the endpoint invents);
2. the offered set excludes a ratio with no mode behind it;
3. a mode outside ASPECT_RATIO_TOLERANCE of every table ratio gets its own
   reachable "native:<aspect>" toggle, never an "approximate" match against
   a ratio it merely resembles ("no closest", PLAN.md, 2026-09-28 --
   superseding this file's earlier "approximate ratio" claim);
4. each row's `aspect_ratio_id`/the per-camera `enabled` list change as the
   operator's saved ratio choice (image_capture.aspect_ratios) changes --
   `selected` itself is deliberately ratio-agnostic now (see
   LegacyFiltersStillApplyToMoreThanTheStockRuleTests' own docstring), so
   what toggling narrows is which ids are in `enabled`, not `selected`;
5. saving round-trips settings.jsonc without losing neighbouring keys -- the
   settings-editor save that silently deleted whole blocks from a camera's
   settings before (test_settings_editor_preserves_unrendered_keys.py), now
   for the aspect_ratios/min_mode_width keys WP-CM-6 added.

Built the same way test_aspect_ratio_selection.py builds its SensorDetect
fixtures: SensorDetect.__new__(SensorDetect) with only the filter attributes
under test set, so the endpoint runs the real
home_ratio_id()/available_aspect_ratios()/_aspect_ratio_table(), not a
hand-rolled stand-in that could drift from them.
"""

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

import flask  # noqa: E402

from module.app.settings_editor import (  # noqa: E402
    _merge_saved_settings,
    settings_editor_bp,
)
from module.sensor_detect import SensorDetect  # noqa: E402


def _detector(aspect_ratio_table, aspect_ratios_cfg, sensor_modes_unfiltered,
              min_mode_width=None, enabled_modes=None):
    d = SensorDetect.__new__(SensorDetect)
    d.aspect_ratio_table = aspect_ratio_table
    d.aspect_ratios_cfg = aspect_ratios_cfg
    d.min_mode_width = min_mode_width
    d.enabled_modes = enabled_modes or {}
    d.sensor_modes_unfiltered = sensor_modes_unfiltered
    return d


def _make_app(sensor_detect):
    app = flask.Flask(__name__)
    app.register_blueprint(settings_editor_bp)
    app.config["SENSOR_DETECT"] = sensor_detect
    app.config["SETTINGS"] = {}
    return app


def _get(sensor_detect):
    app = _make_app(sensor_detect)
    res = app.test_client().get("/settings-editor/api/sensor-modes")
    body = res.get_json()
    assert body["ok"], body
    return body


# A small three-ratio table, deliberately not the real fourteen-entry one --
# proves the endpoint reads whatever table the sensor detect instance was
# given rather than a copy it keeps of its own.
TABLE = [
    {"id": "1.78:1", "value": 1.78, "name": "16:9"},
    {"id": "2.39:1", "value": 2.39, "name": "Scope"},
    {"id": "1:1", "value": 1.0, "name": "Square"},
]


class AspectRatioTableSourceTests(unittest.TestCase):
    def test_table_served_is_the_sensor_detect_instance_own_table(self):
        d = _detector(TABLE, {"default": ["1.78:1"]}, {
            "imx585": [{"width": 1920, "height": 1080, "bit_depth": 12,
                        "fps_max": 50, "hdr": False, "aspect": 1.78}],
        })
        body = _get(d)
        self.assertEqual(body["aspect_ratio_table"], TABLE)


class OfferedRatiosExcludeUnmatchedTests(unittest.TestCase):
    def test_a_ratio_with_no_mode_behind_it_is_not_offered(self):
        # SensorDetect.available_aspect_ratios() resolves every ratio in the
        # table to *some* mode's closest match -- "no mode behind it" is
        # only possible when the camera has no mode with a known aspect at
        # all (test_aspect_ratio_selection.py's own
        # test_every_ratio_resolves_to_a_closest_mode_marked_approximate
        # confirms all fourteen otherwise resolve, even a distant one, as
        # approximate). A mode missing both width and height is exactly
        # that case: SensorDetect._mode_aspect() returns None for it.
        d = _detector(TABLE, {"default": ["1.78:1"]}, {
            "imx585": [{"bit_depth": 12, "fps_max": 50, "hdr": False}],
        })
        body = _get(d)
        available = body["aspect_ratios"]["imx585"]["available"]
        self.assertEqual(available, {})
        for ratio_id in ("1.78:1", "2.39:1", "1:1"):
            self.assertNotIn(ratio_id, available)

    def test_a_ratio_this_cameras_modes_do_reach_is_offered(self):
        d = _detector(TABLE, {"default": ["1.78:1"]}, {
            "imx585": [
                {"width": 1920, "height": 1080, "bit_depth": 12, "fps_max": 50,
                 "hdr": False, "aspect": 1.78},
            ],
        })
        available = _get(d)["aspect_ratios"]["imx585"]["available"]
        self.assertIn("1.78:1", available)
        self.assertTrue(available["1.78:1"]["exact"])


class NativeRatioIsReachableTests(unittest.TestCase):
    """"No closest" (PLAN.md, 2026-09-28), superseding this class's own
    earlier "approximate ratio" claim: a mode outside ASPECT_RATIO_TOLERANCE
    of every table ratio is never filed under the nearest one as an
    "approximate" match. It gets its own native id instead, and that id is
    what the row and the per-camera `available` set both carry -- there is
    no more delta/exactness spectrum, only "reachable under this id" or
    "not offered at all"."""

    def test_a_mode_far_from_every_table_ratio_gets_a_native_id(self):
        # imx477-style tier B camera: one mode at 1.33, nowhere near this
        # fixture's sparse table (1.78/2.39/1:1).
        d = _detector(TABLE, {}, {
            "imx477": [
                {"width": 2028, "height": 1520, "bit_depth": 12, "fps_max": 40,
                 "hdr": False, "aspect": 1.33},
            ],
        })
        body = _get(d)
        available = body["aspect_ratios"]["imx477"]["available"]
        self.assertNotIn("2.39:1", available, "1.33 is not APPROXIMATELY 2.39 -- it is not offered at all")
        self.assertNotIn("1.78:1", available)
        native = available["native:1.33"]
        self.assertTrue(native["exact"])
        self.assertEqual(native["real_aspect"], 1.33)
        self.assertEqual(native["delta"], 0.0)
        self.assertEqual(native["name"], "Native")

        row = body["sensors"]["imx477"][0]
        self.assertEqual(row["aspect_ratio_id"], "native:1.33")
        self.assertTrue(row["aspect_ratio_exact"])


class TogglingRatioChangesEnabledIdsTests(unittest.TestCase):
    """Per-sensor-settings-backend, 2026-09-28: the endpoint's "selected" is
    deliberately ratio-agnostic now (PLAN.md's contract), so what an operator
    toggling a ratio actually changes is the per-camera `enabled` set and
    each row's `aspect_ratio_id` labelling -- the pane combines the two
    (`selected AND aspect_ratio_id in enabled`) to decide a row's checkbox
    state, which is exactly what SensorDetect._finalize_modes' own dial does
    (see test_aspect_ratio_selection.py). This class asserts that
    combination directly, computed the same way the pane would.
    """

    MODES = {
        "imx585": [
            {"width": 1920, "height": 1080, "bit_depth": 12, "fps_max": 50,
             "hdr": False, "aspect": 1.78},
            {"width": 1920, "height": 804, "bit_depth": 12, "fps_max": 50,
             "hdr": False, "aspect": 2.39},
        ],
    }

    def _dial(self, cfg):
        d = _detector(TABLE, cfg, self.MODES)
        body = _get(d)
        enabled = set(body["aspect_ratios"]["imx585"]["enabled"])
        by_size = {(m["width"], m["height"]): m for m in body["sensors"]["imx585"]}
        return {
            size: row["selected"] and row["aspect_ratio_id"] in enabled
            for size, row in by_size.items()
        }

    def test_toggling_the_enabled_ratio_changes_the_dial(self):
        # Narrowing to a single ratio via an EXPLICIT PER-CAMERA key --
        # {"imx585": [...]}, the shape buildAspectRatiosState() actually
        # writes for a camera the operator has interacted with (templates/
        # settings_editor.html:4021-4028), never the global "default" key,
        # which is unconditionally ignored now (PLAN.md D2).
        only_scope = self._dial({"imx585": ["2.39:1"]})
        self.assertFalse(only_scope[(1920, 1080)])
        self.assertTrue(only_scope[(1920, 804)])

        both = self._dial({"imx585": ["1.78:1", "2.39:1"]})
        self.assertTrue(both[(1920, 1080)])
        self.assertTrue(both[(1920, 804)])

    def test_narrowing_to_178_excludes_the_native_shaped_mode(self):
        """Regression test for the WP-CM-7 rework's original blocking review
        finding, restated for "no closest": an operator who deliberately
        narrows a camera to exactly 16:9 must see that choice actually
        narrow the dial -- including a mode whose real aspect used to be
        filed under 1.78:1 as an "approximate" match against a sparse table.
        Under "no closest" that mode instead gets its own native id and is
        excluded from a 1.78:1-only dial outright, which is the more literal
        version of the same guarantee: an explicit choice must narrow."""
        modes = {
            "imx283": [
                {"width": 5760, "height": 2160, "bit_depth": 12, "fps_max": 24,
                 "hdr": False, "aspect": 2.67},
                {"width": 5472, "height": 3648, "bit_depth": 12, "fps_max": 18,
                 "hdr": False, "aspect": 1.5},
                {"width": 3840, "height": 2160, "bit_depth": 12, "fps_max": 30,
                 "hdr": False, "aspect": 1.78},
            ],
        }
        cfg = {"imx283": ["1.78:1"]}

        d = _detector(TABLE, cfg, modes)
        body = _get(d)
        enabled = set(body["aspect_ratios"]["imx283"]["enabled"])
        self.assertEqual(enabled, {"1.78:1"})
        by_size = {(m["width"], m["height"]): m for m in body["sensors"]["imx283"]}
        self.assertEqual(by_size[(3840, 2160)]["aspect_ratio_id"], "1.78:1")
        self.assertEqual(by_size[(5760, 2160)]["aspect_ratio_id"], "native:2.67")
        self.assertEqual(by_size[(5472, 3648)]["aspect_ratio_id"], "native:1.50")

        sd = SensorDetect.__new__(SensorDetect)
        sd.aspect_ratio_table = TABLE
        sd.aspect_ratios_cfg = cfg
        sd.sensor_modes_unfiltered = modes
        matches = sd._ratio_matches_for_camera("imx283", modes["imx283"])
        matched_sizes = {
            (m["width"], m["height"])
            for m in modes["imx283"] if id(m) in matches
        }
        self.assertEqual(matched_sizes, {(3840, 2160)})


class SettingsRoundTripTests(unittest.TestCase):
    """_merge_saved_settings is what put_settings() runs the payload through
    (see test_settings_editor_preserves_unrendered_keys.py for the same
    pattern against the bug this guards)."""

    def test_toggling_one_cameras_ratios_leaves_the_others_and_the_floor_alone(self):
        existing = {
            "image_capture": {
                "aspect_ratios": {
                    "default": ["1.78:1"],
                    "imx585": ["1.78:1"],
                    "imx283": ["1.78:1", "1.33:1"],
                },
                "min_mode_width": 1280,
                "k_steps": [1.5, 2, 3, 4],
                "enabled_modes": {},
            },
        }
        # A save that only touches imx585's selection -- the shape
        # buildAspectRatiosState() sends for the camera(s) actually rendered
        # on the page.
        payload = {
            "image_capture": {
                "aspect_ratios": {
                    "default": ["1.78:1"],
                    "imx585": ["1.78:1", "2.39:1"],
                },
            },
        }
        merged = _merge_saved_settings(existing, payload)
        ic = merged["image_capture"]
        self.assertEqual(ic["aspect_ratios"]["imx585"], ["1.78:1", "2.39:1"])
        self.assertEqual(ic["aspect_ratios"]["imx283"], ["1.78:1", "1.33:1"])
        self.assertEqual(ic["min_mode_width"], 1280)
        self.assertEqual(ic["k_steps"], [1.5, 2, 3, 4])


class LegacyFiltersStillApplyToMoreThanTheStockRuleTests(unittest.TestCase):
    """A row the page shows as selected reflects mode_selected() alone
    (per-sensor-settings-backend, 2026-09-28): the endpoint's "selected" is
    now deliberately RATIO-AGNOSTIC (PLAN.md's contract -- "the mode's own
    selection, IGNORING the ratio gate"), so the pane can remember a mode's
    own checkbox state while its ratio group is toggled off, and AND it with
    `aspect_ratio_id in enabled` client-side rather than losing that state on
    a round trip. What used to be tested here -- a ratio match combined with
    the legacy k_steps/bit_depths filters -- is now exactly
    SensorDetect._stock_mode_selected(), reading k_steps off the detector
    itself rather than a second copy the endpoint used to keep from
    current_app.config["SETTINGS"]. See test_aspect_ratio_selection.py's own
    mode_selected coverage for the k_steps/bit_depths/HDR filter mechanics in
    isolation; this class keeps the imx519 fixture and the settings-editor
    round trip.

    imx519's native 4656x3496 is the worked example: k_val 4.5, which the
    shipped k_steps does not list.
    """

    MODES = {
        "imx519": [
            {"width": 4656, "height": 3496, "bit_depth": 10, "fps_max": 9,
             "hdr": False, "aspect": 1.33},
            {"width": 2328, "height": 1748, "bit_depth": 10, "fps_max": 30,
             "hdr": False, "aspect": 1.33},
        ],
    }

    def _selected(self, k_steps):
        d = _detector(TABLE, {}, self.MODES)
        d.k_steps = k_steps
        body = _get(d)
        return {(m["width"], m["height"]): m["selected"] for m in body["sensors"]["imx519"]}

    def test_a_mode_excluded_by_k_steps_is_not_shown_selected(self):
        # 4.5 absent, 2.5 present: the big mode must not be offered, the small one may.
        selected = self._selected([1.5, 2, 2.5, 3, 4])
        self.assertFalse(selected[(4656, 3496)],
                         "a mode k_steps excludes was shown as selected, so a save "
                         "would promote it into enabled_modes permanently")
        self.assertTrue(selected[(2328, 1748)])

    def test_with_the_mode_inside_k_steps_it_is_shown_selected(self):
        # Same fixture, only k_steps changed, so this proves the exclusion
        # above came from k_steps and not from anything else mode_selected checks.
        selected = self._selected([2.5, 4.5])
        self.assertTrue(selected[(4656, 3496)])


if __name__ == "__main__":
    unittest.main()
