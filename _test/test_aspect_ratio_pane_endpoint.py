"""WP-CM-7: the aspect pane's data source, GET /settings-editor/api/sensor-modes.

ASPECT-RATIOS.md steps 3 and 4: per camera, the ratio selection is the first
section and the mode table sits under it, filtered to the ratios selected for
that camera. "Rendering is not testable here; the endpoint is" (WP-CM-7's own
Tests note), so this covers exactly the five things that note lists:

1. the page is served the ratio table from the single canonical source
   (module.aspect_ratios / SensorDetect.aspect_ratio_table, not a second copy
   the endpoint invents);
2. the offered set excludes a ratio with no mode behind it;
3. an approximate ratio carries the nearest mode's real aspect;
4. toggling a ratio (image_capture.aspect_ratios) changes which modes the
   endpoint marks selected;
5. saving round-trips settings.jsonc without losing neighbouring keys -- the
   settings-editor save that silently deleted whole blocks from a camera's
   settings before (test_settings_editor_preserves_unrendered_keys.py), now
   for the aspect_ratios/min_mode_width keys WP-CM-6 added.

Built the same way test_aspect_ratio_selection.py builds its SensorDetect
fixtures: SensorDetect.__new__(SensorDetect) with only the filter attributes
under test set, so the endpoint runs the real
_ratio_matches_for_camera()/available_aspect_ratios()/_aspect_ratio_table(),
not a hand-rolled stand-in that could drift from them.
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


class ApproximateRatioRealAspectTests(unittest.TestCase):
    def test_approximate_ratio_carries_the_nearest_modes_real_aspect(self):
        # imx477-style tier B camera: one mode at 1.33, nowhere near 2.39.
        d = _detector(TABLE, {"default": ["1.78:1"]}, {
            "imx477": [
                {"width": 2028, "height": 1520, "bit_depth": 12, "fps_max": 40,
                 "hdr": False, "aspect": 1.33},
            ],
        })
        body = _get(d)
        available = body["aspect_ratios"]["imx477"]["available"]
        scope = available["2.39:1"]
        self.assertFalse(scope["exact"])
        self.assertEqual(scope["real_aspect"], 1.33)
        self.assertGreater(scope["delta"], 0)


class TogglingRatioChangesSelectedTests(unittest.TestCase):
    def test_toggling_the_enabled_ratio_changes_which_modes_are_selected(self):
        modes = {
            "imx585": [
                {"width": 1920, "height": 1080, "bit_depth": 12, "fps_max": 50,
                 "hdr": False, "aspect": 1.78},
                {"width": 1920, "height": 804, "bit_depth": 12, "fps_max": 50,
                 "hdr": False, "aspect": 2.39},
            ],
        }
        # Narrowing to a single ratio via an EXPLICIT PER-CAMERA key --
        # {"imx585": [...]}, the shape buildAspectRatiosState() actually
        # writes for a camera the operator has interacted with (templates/
        # settings_editor.html:4021-4028), not the global "default" key.
        # additive_fallback is keyed off presence of this per-camera entry
        # (_camera_has_explicit_ratio_selection), so this is what narrowing
        # looks like for a real operator toggle regardless of which ratio
        # they narrowed to -- including 2.39 here, and separately below the
        # single most likely real selection, narrowing to plain 1.78:1
        # (test_narrowing_a_camera_to_only_the_default_ratio_still_narrows).
        only_scope = _detector(TABLE, {"default": ["1.78:1"], "imx585": ["2.39:1"]}, modes)
        by_size_scope = {(m["width"], m["height"]): m for m in _get(only_scope)["sensors"]["imx585"]}
        self.assertFalse(by_size_scope[(1920, 1080)]["selected"])
        self.assertTrue(by_size_scope[(1920, 804)]["selected"])

        both = _detector(TABLE, {"default": ["1.78:1"], "imx585": ["1.78:1", "2.39:1"]}, modes)
        by_size_both = {(m["width"], m["height"]): m for m in _get(both)["sensors"]["imx585"]}
        self.assertTrue(by_size_both[(1920, 1080)]["selected"])
        self.assertTrue(by_size_both[(1920, 804)]["selected"])

    def test_narrowing_a_camera_to_only_the_default_ratio_still_narrows(self):
        """Regression test for the WP-CM-7 rework's blocking review finding:
        an operator who deliberately toggles a multi-ratio camera down to
        exactly 16:9 saves {"<camera>": ["1.78:1"]} -- bit-for-bit the same
        list the old hardcoded shipped default ("1.78:1") resolved to for an
        untouched camera, so a value-equality check could never tell the two
        apart and this selection silently stopped narrowing anything (every
        mode with a known aspect survived, mislabeled as 1.78:1). WP-CM-11
        replaced that hardcoded default with one derived per camera from its
        own modes, but the same trap applies to it: an explicit per-camera
        key must still narrow even when its value happens to equal what the
        derived default would have produced on its own. This saves the
        explicit per-camera key -- never the global "default" key -- and
        asserts the non-1.78 mode is excluded, from both the endpoint
        (settings_editor.selected_for(), via _ratio_matches_for_camera) and
        _ratio_matches_for_camera() directly."""
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
        by_size = {(m["width"], m["height"]): m for m in _get(d)["sensors"]["imx283"]}
        self.assertTrue(by_size[(3840, 2160)]["selected"])
        # 5760x2160 is 2.67, whose home in this fixture's table is 2.39:1, so a
        # 1.78:1-only selection excludes it.
        self.assertFalse(by_size[(5760, 2160)]["selected"])
        # 5472x3648 is 1.50. Against the REAL fourteen-ratio table its home would
        # be 1.37:1 and it would be excluded here too -- but this fixture uses a
        # deliberately sparse three-ratio table, where 1.78:1 is the nearest entry
        # to 1.50 and so the label this row carries. Selection filters on that
        # label, because it is what the operator sees on the row, so a row labelled
        # 1.78:1 must not vanish while 1.78:1 is on.
        self.assertTrue(by_size[(5472, 3648)]["selected"])

        sd = SensorDetect.__new__(SensorDetect)
        sd.aspect_ratio_table = TABLE
        sd.aspect_ratios_cfg = cfg
        matches = sd._ratio_matches_for_camera("imx283", modes["imx283"])
        matched_sizes = {
            (m["width"], m["height"])
            for m in modes["imx283"] if id(m) in matches
        }
        # Same reasoning as the row assertions above: against this fixture's sparse
        # table 1.50 comes home to 1.78:1, so the matcher claims it. 2.67 comes home
        # to 2.39:1 and stays out.
        self.assertEqual(matched_sizes, {(3840, 2160), (5472, 3648)})


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


class LegacyFiltersStillApplyToARatioMatchTests(unittest.TestCase):
    """A row the page shows as selected must be a row the camera would offer.

    The ratio matcher is not the last word: bit_depths and k_steps run after it
    in _finalize_modes. If the endpoint reported a ratio-matched mode as selected
    without applying them, the page would disagree with the camera -- and worse,
    a plain save writes the displayed selection into enabled_modes, which IS
    authoritative, so the mode would be promoted past those filters for good.

    imx519's native 4656x3496 is the worked example: k_val 4.5, which the shipped
    k_steps does not list.
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
        d = _detector(TABLE, {"imx519": ["1:1"]}, self.MODES)
        app = _make_app(d)
        app.config["SETTINGS"] = {"image_capture": {"k_steps": k_steps}}
        body = app.test_client().get("/settings-editor/api/sensor-modes").get_json()
        assert body["ok"], body
        return {(m["width"], m["height"]): m["selected"] for m in body["sensors"]["imx519"]}

    def test_a_ratio_match_excluded_by_k_steps_is_not_shown_selected(self):
        # 4.5 absent, 2.5 present: the big mode must not be offered, the small one may.
        selected = self._selected([1.5, 2, 2.5, 3, 4])
        self.assertFalse(selected[(4656, 3496)],
                         "a mode k_steps excludes was shown as selected, so a save "
                         "would promote it into enabled_modes permanently")
        self.assertTrue(selected[(2328, 1748)])

    def test_with_the_mode_inside_k_steps_it_is_shown_selected(self):
        # Same ratio match, same code path: only k_steps changed, so this proves
        # the exclusion above came from k_steps and not from the ratio matcher.
        selected = self._selected([2.5, 4.5])
        self.assertTrue(selected[(4656, 3496)])


if __name__ == "__main__":
    unittest.main()
