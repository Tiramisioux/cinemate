"""stock_selection.extra_modes (PLAN.md addendum, 2026-09-28): "imx477
should also open with 2028x1080 -- not the 4K mode."

Data, not a Python special case: resources/sensors.json's per-sensor entry
can carry an optional::

    "stock_selection": {"extra_modes": [{"width": 2028, "height": 1080}]}

SensorDetect._default_ratio_ids() unions in the home ratio id of every
matched entry (existing order kept, new ids appended); SensorDetect.
_stock_mode_selected() then restricts an extras-only ratio's OTHER modes
(imx477's real 4056x2160, same home "1.89:1") to the extras themselves, so
turning the toggle on for 2028x1080 does not also silently select the 4K
mode nobody asked for. Only the stock path is affected -- an explicit
per-sensor file or legacy aspect_ratios/enabled_modes entry wins entirely,
exactly as it already did before this package.

Same house pattern as test_aspect_ratio_selection.py: a SensorDetect built
with __new__, only the attributes under test set on it, run through the
real _default_ratio_ids()/_stock_mode_selected()/_finalize_modes().
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

import flask  # noqa: E402

from module.app.settings_editor import settings_editor_bp  # noqa: E402
from module.sensor_database import load_sensor_database  # noqa: E402
from module.sensor_detect import SensorDetect  # noqa: E402


def _detector(aspect_ratios_cfg=None, enabled_modes=None, bit_depths=None,
              k_steps=None, sensor_database=None):
    d = SensorDetect.__new__(SensorDetect)
    d.bit_depths = bit_depths if bit_depths is not None else []
    d.k_steps = k_steps if k_steps is not None else []
    d.custom_modes = {}
    d.hdr_modes = SensorDetect._hdr_whitelist({})
    d.clear_hdr_depths = None
    d.enabled_modes = enabled_modes or {}
    d.aspect_ratios_cfg = aspect_ratios_cfg if aspect_ratios_cfg is not None else {}
    d.sensor_modes_unfiltered = {}
    # getattr-guarded in SensorDetect._sensor_database_entry(): a fixture
    # that never sets this (most of test_aspect_ratio_selection.py's own
    # detectors) gets "no stock_selection for anyone", which is exactly the
    # "unaffected" behaviour NoStockSelectionUnaffectedTests below pins.
    if sensor_database is not None:
        d.sensor_database = sensor_database
    return d


# The real resources/sensors.json imx477 entry, loaded once -- proves the
# feature against the actual shipped database, not a hand-typed stand-in of
# it. If this ever stops carrying a "stock_selection" block the assertions
# below that depend on it fail loudly rather than silently passing on dead
# code.
REAL_DATABASE = load_sensor_database(str(ROOT / "resources" / "sensors.json"))


# The operator's real driver report (PLAN.md): the 1.89:1-home family
# (2028x1080, mislabelled 4056x2160 by the NOW-FIXED D1 bug) at three bit
# depths each -- 62/74/92 fps for the 2K crop, 16/19/24 fps for the real 4K
# readout -- plus the three 1.33:1-home modes. Nine modes total, correctly
# labelled here since D1's mislabeling is a display-time bug orthogonal to
# this fixture (SensorDetect._finalize_modes already receives correctly
# labelled width/height by the time this package's own stock rule runs).
IMX477_NINE_MODE_LISTING = [
    {"width": 2028, "height": 1080, "bit_depth": 12, "hdr": False, "fps_max": 62},
    {"width": 2028, "height": 1080, "bit_depth": 10, "hdr": False, "fps_max": 74},
    {"width": 2028, "height": 1080, "bit_depth": 8, "hdr": False, "fps_max": 92},
    {"width": 4056, "height": 2160, "bit_depth": 12, "hdr": False, "fps_max": 16},
    {"width": 4056, "height": 2160, "bit_depth": 10, "hdr": False, "fps_max": 19},
    {"width": 4056, "height": 2160, "bit_depth": 8, "hdr": False, "fps_max": 24},
    {"width": 2028, "height": 1520, "bit_depth": 12, "hdr": False, "fps_max": 40},
    {"width": 4056, "height": 3040, "bit_depth": 12, "hdr": False, "fps_max": 10},
    {"width": 1332, "height": 990, "bit_depth": 10, "hdr": False, "fps_max": 120},
]


class Imx477StockRatiosGainTheAddedRatioTests(unittest.TestCase):
    def test_stock_ratios_are_133_and_189(self):
        d = _detector(sensor_database=REAL_DATABASE)
        d.sensor_modes_unfiltered = {"imx477": [dict(m) for m in IMX477_NINE_MODE_LISTING]}
        self.assertEqual(d._default_ratio_ids("imx477"), ["1.33:1", "1.89:1"])

    def test_189_is_added_only_because_of_extra_modes(self):
        d = _detector(sensor_database=REAL_DATABASE)
        d.sensor_modes_unfiltered = {"imx477": [dict(m) for m in IMX477_NINE_MODE_LISTING]}
        self.assertEqual(d._base_stock_ratio_ids("imx477"), ["1.33:1"])
        self.assertEqual(d._stock_added_ratio_ids("imx477"), {"1.89:1"})


class Imx477DialGains2KButNot4KTests(unittest.TestCase):
    """The global bit_depths filter (12- and 10-bit only, excluding the
    fixture's 8-bit rows) still applies on top of the extras rule -- PLAN.md:
    "2028x1080 (12- and 10-bit, as the global bit_depths filter allows)"."""

    def setUp(self):
        self.d = _detector(sensor_database=REAL_DATABASE, bit_depths=[12, 10])
        self.pruned = self.d._finalize_modes(
            {"imx477": [dict(m) for m in IMX477_NINE_MODE_LISTING]}
        )

    def _sizes_and_depths(self):
        return {(m["width"], m["height"], m["bit_depth"]) for m in self.pruned["imx477"].values()}

    def test_the_133_family_is_unaffected(self):
        sizes_depths = self._sizes_and_depths()
        self.assertIn((2028, 1520, 12), sizes_depths)
        self.assertIn((4056, 3040, 12), sizes_depths)
        self.assertIn((1332, 990, 10), sizes_depths)

    def test_2028x1080_is_selected_at_12_and_10_bit_not_8(self):
        sizes_depths = self._sizes_and_depths()
        self.assertIn((2028, 1080, 12), sizes_depths)
        self.assertIn((2028, 1080, 10), sizes_depths)
        self.assertNotIn((2028, 1080, 8), sizes_depths)

    def test_4056x2160_is_never_selected_at_any_bit_depth(self):
        widths_heights = {(m["width"], m["height"]) for m in self.pruned["imx477"].values()}
        self.assertNotIn((4056, 2160), widths_heights)

    def test_4056x2160_is_still_offered_unfiltered_just_not_ticked(self):
        # "visible but unticked" (PLAN.md): the row stays reachable in the
        # unfiltered table -- and its home ratio toggle (1.89:1) is ON -- it
        # is simply not itself stock-selected.
        unfiltered_sizes = {(m["width"], m["height"]) for m in self.d.sensor_modes_unfiltered["imx477"]}
        self.assertIn((4056, 2160), unfiltered_sizes)
        self.assertIn("1.89:1", self.d._enabled_ratio_ids("imx477"))
        four_k_mode = next(
            m for m in self.d.sensor_modes_unfiltered["imx477"]
            if (m["width"], m["height"], m["bit_depth"]) == (4056, 2160, 12)
        )
        self.assertEqual(self.d.home_ratio_id("imx477", four_k_mode), "1.89:1")
        self.assertFalse(self.d.mode_selected("imx477", four_k_mode))


class NoStockSelectionUnaffectedTests(unittest.TestCase):
    """A sensor with no stock_selection block in the database (every sensor
    but imx477 today) behaves exactly as before this package -- extras are a
    strict, data-driven addition, never a default that reaches into a sensor
    that never named one."""

    IMX585_16X9 = {"width": 3840, "height": 2160, "bit_depth": 12, "hdr": False,
                   "fps_max": 50, "aspect": 1.78}
    IMX585_239 = {"width": 3840, "height": 1608, "bit_depth": 12, "hdr": False,
                  "fps_max": 67, "aspect": 2.39}

    def test_imx585_has_no_extra_stock_mode_entries(self):
        d = _detector(sensor_database=REAL_DATABASE)
        self.assertEqual(d._extra_stock_mode_entries("imx585"), [])

    def test_imx585_stock_ratios_are_unaffected(self):
        d = _detector(sensor_database=REAL_DATABASE)
        d.sensor_modes_unfiltered = {"imx585": [dict(self.IMX585_16X9), dict(self.IMX585_239)]}
        self.assertEqual(d._default_ratio_ids("imx585"), list(d._base_stock_ratio_ids("imx585")))
        self.assertEqual(d._stock_added_ratio_ids("imx585"), set())

    def test_a_fixture_with_no_sensor_database_attribute_at_all_is_unaffected(self):
        # Most of test_aspect_ratio_selection.py's own detectors never set
        # sensor_database -- _sensor_database_entry()/_extra_stock_mode_
        # entries() must not raise AttributeError against them.
        d = _detector()
        d.sensor_modes_unfiltered = {"imx585": [dict(self.IMX585_16X9), dict(self.IMX585_239)]}
        self.assertEqual(d._extra_stock_mode_entries("imx585"), [])
        self.assertEqual(d._default_ratio_ids("imx585"), ["1.78:1"])


class MalformedOrUnmatchedExtraModesWarnOnceTests(unittest.TestCase):
    """An entry that matches no detected mode is ignored with one
    logging.warning (PLAN.md) -- never invents a mode, and never repeats the
    warning on every subsequent call in the same boot."""

    UNMATCHED_DB = {
        "schema_version": 1,
        "sensors": {
            "imx477": {
                "stock_selection": {"extra_modes": [{"width": 9999, "height": 9999}]},
            },
        },
    }

    def test_an_unmatched_entry_warns_once(self):
        d = _detector(sensor_database=self.UNMATCHED_DB)
        d.sensor_modes_unfiltered = {"imx477": [dict(m) for m in IMX477_NINE_MODE_LISTING]}
        with self.assertLogs(level="WARNING") as logs:
            first = d._extra_stock_modes("imx477")
        self.assertEqual(first, [])
        self.assertTrue(any("matches no detected mode" in m for m in logs.output))

        # Same camera, same instance, called again (exactly what happens
        # once per mode inside _finalize_modes' filter loop) -- no second
        # warning.
        with mock.patch("module.sensor_detect.logging.warning") as mock_warn:
            d._extra_stock_modes("imx477")
        mock_warn.assert_not_called()

    def test_stock_ratios_are_unaffected_by_an_entry_matching_nothing(self):
        d = _detector(sensor_database=self.UNMATCHED_DB)
        d.sensor_modes_unfiltered = {"imx477": [dict(m) for m in IMX477_NINE_MODE_LISTING]}
        self.assertEqual(d._default_ratio_ids("imx477"), d._base_stock_ratio_ids("imx477"))

    def test_a_non_dict_stock_selection_block_warns_and_is_ignored(self):
        db = {"schema_version": 1, "sensors": {"imx477": {"stock_selection": "nope"}}}
        d = _detector(sensor_database=db)
        with self.assertLogs(level="WARNING") as logs:
            entries = d._extra_stock_mode_entries("imx477")
        self.assertEqual(entries, [])
        self.assertTrue(any("stock_selection is" in m for m in logs.output))

    def test_a_non_list_extra_modes_warns_and_is_ignored(self):
        db = {"schema_version": 1, "sensors": {"imx477": {
            "stock_selection": {"extra_modes": "nope"},
        }}}
        d = _detector(sensor_database=db)
        with self.assertLogs(level="WARNING") as logs:
            entries = d._extra_stock_mode_entries("imx477")
        self.assertEqual(entries, [])
        self.assertTrue(any("extra_modes is" in m for m in logs.output))

    def test_an_entry_missing_width_or_height_warns_and_is_dropped(self):
        db = {"schema_version": 1, "sensors": {"imx477": {
            "stock_selection": {"extra_modes": [{"height": 1080}, {"width": 2028, "height": 1080}]},
        }}}
        d = _detector(sensor_database=db)
        with self.assertLogs(level="WARNING") as logs:
            entries = d._extra_stock_mode_entries("imx477")
        self.assertEqual(entries, [{"width": 2028, "height": 1080}])
        self.assertTrue(any("no width/height" in m for m in logs.output))


class PerSensorEntryOverridesExtrasEntirelyTests(unittest.TestCase):
    """"Only the stock path changes. A per-sensor file or legacy entry still
    wins entirely" (05-imx477-stock-2k.md). SensorDetect._finalize_modes()
    collapses a resolved per-sensor file to exactly the same aspect_ratios_
    cfg/enabled_modes shape a legacy settings.jsonc entry already used (see
    its own "resolve per-sensor settings" section) -- so setting them
    directly here exercises precisely what a real settings_imx477.jsonc
    produces, the same way every other precedence test in
    test_aspect_ratio_selection.py already does."""

    def test_an_explicit_ratio_only_choice_never_gains_the_extra_ratio(self):
        d = _detector(
            sensor_database=REAL_DATABASE,
            aspect_ratios_cfg={"imx477": ["1.33:1"]},
        )
        pruned = d._finalize_modes({"imx477": [dict(m) for m in IMX477_NINE_MODE_LISTING]})
        widths_heights = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertNotIn((2028, 1080), widths_heights)
        self.assertEqual(d._enabled_ratio_ids("imx477"), ["1.33:1"])

    def test_an_explicit_enabled_modes_choice_bypasses_extras_too(self):
        d = _detector(
            sensor_database=REAL_DATABASE,
            enabled_modes={"imx477": [
                {"width": 4056, "height": 3040, "bit_depth": 12, "hdr": False},
            ]},
        )
        pruned = d._finalize_modes({"imx477": [dict(m) for m in IMX477_NINE_MODE_LISTING]})
        widths_heights = {(m["width"], m["height"]) for m in pruned["imx477"].values()}
        self.assertEqual(widths_heights, {(4056, 3040)})


class SettingsEditorEndpointRowsTests(unittest.TestCase):
    """GET /settings-editor/api/sensor-modes' `selected` field is
    SensorDetect.mode_selected() itself (settings_editor.py's selected_for()
    delegates, no second copy) -- PLAN.md's addendum: "The settings-editor
    endpoint's stock list and each row's selected must follow automatically
    through the shared predicate W1 built... do not add a second copy."
    Proven end to end through the real Flask blueprint, not just the
    predicate in isolation.
    """

    def _get(self, bit_depths=None):
        d = _detector(sensor_database=REAL_DATABASE, bit_depths=bit_depths)
        d.aspect_ratio_table = None  # falls back to load_aspect_ratio_table()
        d.sensor_modes_unfiltered = {"imx477": [dict(m) for m in IMX477_NINE_MODE_LISTING]}
        app = flask.Flask(__name__)
        app.register_blueprint(settings_editor_bp)
        app.config["SENSOR_DETECT"] = d
        app.config["SETTINGS"] = {}
        res = app.test_client().get("/settings-editor/api/sensor-modes")
        body = res.get_json()
        self.assertTrue(body["ok"], body)
        return body

    def test_stock_list_includes_the_added_ratio(self):
        body = self._get(bit_depths=[12, 10])
        self.assertEqual(body["aspect_ratios"]["imx477"]["stock"], ["1.33:1", "1.89:1"])

    def test_4056x2160_row_is_unselected_2028x1080_is_selected(self):
        # Every detected row is listed here regardless of `selected` (this
        # endpoint shows the full driver catalogue, unlike the dial) -- the
        # fixture's own 8-bit 2028x1080 row is correctly NOT selected too
        # (the global bit_depths=[12, 10] filter, applied on top of the
        # extras rule exactly as PLAN.md specifies), so bit_depth is part of
        # the lookup key here, not just width/height.
        body = self._get(bit_depths=[12, 10])
        rows = body["sensors"]["imx477"]
        four_k = [r for r in rows if (r["width"], r["height"]) == (4056, 2160)]
        two_k_12_10 = [r for r in rows
                       if (r["width"], r["height"]) == (2028, 1080) and r["bit_depth"] in (12, 10)]
        two_k_8 = [r for r in rows
                   if (r["width"], r["height"]) == (2028, 1080) and r["bit_depth"] == 8]
        self.assertTrue(four_k)
        self.assertEqual(len(two_k_12_10), 2)
        self.assertTrue(two_k_8)
        self.assertTrue(all(r["selected"] is False for r in four_k))
        self.assertTrue(all(r["selected"] is True for r in two_k_12_10))
        self.assertTrue(all(r["selected"] is False for r in two_k_8))
        self.assertTrue(all(r["aspect_ratio_id"] == "1.89:1" for r in four_k + two_k_12_10 + two_k_8))


if __name__ == "__main__":
    unittest.main()
