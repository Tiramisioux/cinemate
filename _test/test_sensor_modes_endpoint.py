"""GET /settings-editor/api/sensor-modes -- the fps-ceiling override pane's
data source (F-298). Detected vs effective fps_max must both be visible so
the settings editor can show the sensor's own value as a placeholder next
to an editable, possibly-overridden effective value.
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

import flask

from module.app.settings_editor import settings_editor_bp
from module.sensor_detect import SensorDetect


class FakeSensorDetect:
    def __init__(self, sensor_resolutions):
        self.sensor_resolutions = sensor_resolutions


def _make_app(sensor_detect):
    app = flask.Flask(__name__)
    app.register_blueprint(settings_editor_bp)
    app.config["SENSOR_DETECT"] = sensor_detect
    app.config["SETTINGS"] = {}
    return app


class SensorModesEndpointTests(unittest.TestCase):
    def test_no_override_reports_the_same_value_twice(self):
        app = _make_app(FakeSensorDetect({
            "imx585": {0: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 87, "hdr": False}},
        }))
        res = app.test_client().get("/settings-editor/api/sensor-modes")
        body = res.get_json()

        self.assertTrue(body["ok"])
        mode = body["sensors"]["imx585"][0]
        self.assertEqual(mode["fps_max_detected"], 87)
        self.assertEqual(mode["fps_max_effective"], 87)

    def test_an_override_reports_both_values_distinctly(self):
        app = _make_app(FakeSensorDetect({
            "imx585": {0: {
                "width": 1928, "height": 1090, "bit_depth": 12,
                "fps_max": 60, "fps_max_detected": 87, "hdr": False,
            }},
        }))
        res = app.test_client().get("/settings-editor/api/sensor-modes")
        body = res.get_json()

        mode = body["sensors"]["imx585"][0]
        self.assertEqual(mode["fps_max_detected"], 87)
        self.assertEqual(mode["fps_max_effective"], 60)

    def test_no_sensor_detect_returns_empty_not_an_error(self):
        app = _make_app(None)
        res = app.test_client().get("/settings-editor/api/sensor-modes")
        body = res.get_json()

        self.assertTrue(body["ok"])
        self.assertEqual(body["sensors"], {})

    def test_modes_are_listed_in_cinemate_mode_order(self):
        """Same order as the mode table, the GUI mode index and
        docs/sensors.md -- SensorDetect._order_modes()'s (hdr, bit_depth,
        width, height). This pane used to sort by pixel count descending, so
        the same modes appeared here in a different order from everywhere
        else."""
        app = _make_app(FakeSensorDetect({
            "imx585": {
                0: {"width": 3840, "height": 2200, "bit_depth": 16, "fps_max": 25, "hdr": True},
                1: {"width": 3840, "height": 2160, "bit_depth": 12, "fps_max": 50, "hdr": False},
                2: {"width": 3840, "height": 2160, "bit_depth": 10, "fps_max": 60, "hdr": False},
                3: {"width": 1920, "height": 1100, "bit_depth": 16, "fps_max": 25, "hdr": True},
                4: {"width": 1920, "height": 1080, "bit_depth": 12, "fps_max": 50, "hdr": False},
            },
        }))
        res = app.test_client().get("/settings-editor/api/sensor-modes")
        body = res.get_json()

        shape = [(m["width"], m["bit_depth"], m["hdr"]) for m in body["sensors"]["imx585"]]
        self.assertEqual(shape, [
            (3840, 10, False),   # 0  4K SDR 10-bit
            (1920, 12, False),   # 1  HD SDR 12-bit
            (3840, 12, False),   # 2  4K SDR 12-bit
            (1920, 16, True),    # 3  HD ClearHDR 16-bit
            (3840, 16, True),    # 4  4K ClearHDR 16-bit
        ])


def _real_unfiltered_detector(sensor_modes_unfiltered, enabled_modes=None):
    """A real SensorDetect (per-sensor-settings-backend, 2026-09-28), not a
    hand-rolled stand-in: the endpoint's "selected" column now delegates to
    SensorDetect.mode_selected() (PLAN.md D4), which needs the real stock-
    mode-rule/enabled_modes machinery a minimal FakeSensorDetectUnfiltered
    no longer provides. Built the same way test_aspect_ratio_selection.py's
    own _detector() is: SensorDetect.__new__ with only the filter attributes
    under test set."""
    d = SensorDetect.__new__(SensorDetect)
    d.sensor_modes_unfiltered = sensor_modes_unfiltered
    d.enabled_modes = enabled_modes or {}
    d.bit_depths = []
    d.k_steps = []
    d.hdr_modes = set()
    d.clear_hdr_depths = None
    d.aspect_ratios_cfg = {}
    d.aspect_ratio_table = None
    d.min_mode_width = None
    return d


class NativeModeDefaultSelectionTests(unittest.TestCase):
    """M5: a native mode with a non-zero crop origin (imx283 1A/2A/1C) must
    default-select on a settings file with no explicit selection, exactly
    like a mode with no crop annotation at all. Only a driver-annotated
    windowed (binned, non-full) crop should arrive unselected."""

    def _selected(self, mode):
        app = flask.Flask(__name__)
        app.register_blueprint(settings_editor_bp)
        app.config["SENSOR_DETECT"] = _real_unfiltered_detector({"cam": [mode]})
        app.config["SETTINGS"] = {}
        res = app.test_client().get("/settings-editor/api/sensor-modes")
        body = res.get_json()
        return body["sensors"]["cam"][0]["selected"]

    def test_native_mode_with_nonzero_origin_and_no_binning_is_selected(self):
        # imx283-style centred native readout: crop origin is not 0,0, and
        # the driver supplies no binning annotation at all.
        mode = {
            "width": 3840, "height": 2160, "bit_depth": 12, "hdr": False,
            "fps_max": 24,
            "crop_x": 100, "crop_y": 40,
            "crop_width": 3840, "crop_height": 2160,
        }
        self.assertTrue(self._selected(mode))

    def test_annotated_windowed_crop_is_unselected(self):
        # imx585-style binned windowed crop: binning annotation is present
        # and the crop is not the full active window.
        mode = {
            "width": 1920, "height": 1080, "bit_depth": 10, "hdr": False,
            "fps_max": 50,
            "binning_x": 2, "binning_y": 2,
            "crop_x": 200, "crop_y": 200,
            "crop_width": 960, "crop_height": 540,
            "sensor_width": 3856, "sensor_height": 2180,
        }
        self.assertFalse(self._selected(mode))

    def test_full_field_annotated_mode_is_selected(self):
        mode = {
            "width": 3840, "height": 2160, "bit_depth": 12, "hdr": False,
            "fps_max": 50,
            "binning_x": 1, "binning_y": 1,
            "crop_x": 0, "crop_y": 0,
            "crop_width": 3840, "crop_height": 2160,
            "sensor_width": 3856, "sensor_height": 2180,
        }
        self.assertTrue(self._selected(mode))


class ActiveWidthHeightFieldTests(unittest.TestCase):
    """Round 2, Defect D: the pane's active_width/active_height fields go
    through the one shared helper (active_picture_size) instead of the
    settings_editor-only _active_dimension this package retired."""

    def _entry(self, mode):
        app = flask.Flask(__name__)
        app.register_blueprint(settings_editor_bp)
        app.config["SENSOR_DETECT"] = _real_unfiltered_detector({"cam": [mode]})
        app.config["SETTINGS"] = {}
        res = app.test_client().get("/settings-editor/api/sensor-modes")
        body = res.get_json()
        return body["sensors"]["cam"][0]

    def test_crop_divided_by_binning_when_no_active_annotation(self):
        mode = {
            "width": 1440, "height": 1080, "bit_depth": 12, "hdr": False,
            "fps_max": 50,
            "binning_x": 2, "binning_y": 2,
            "crop_x": 0, "crop_y": 0,
            "crop_width": 2880, "crop_height": 2160,
        }
        entry = self._entry(mode)
        self.assertEqual(entry["active_width"], 1440)
        self.assertEqual(entry["active_height"], 1080)

    def test_explicit_active_annotation_wins_over_crop_binning(self):
        # The active annotation is the delivered picture already -- it must
        # be used as-is, not further divided by binning.
        mode = {
            "width": 2784, "height": 1828, "bit_depth": 12, "hdr": False,
            "fps_max": 36,
            "binning_x": 2, "binning_y": 2,
            "crop_x": 108, "crop_y": 40,
            "crop_width": 5472, "crop_height": 3648,
            "active_width": 2736, "active_height": 1824,
        }
        entry = self._entry(mode)
        self.assertEqual(entry["active_width"], 2736)
        self.assertEqual(entry["active_height"], 1824)

    def test_transport_fallback_when_no_geometry_at_all(self):
        mode = {
            "width": 1332, "height": 990, "bit_depth": 12, "hdr": False,
            "fps_max": 120,
        }
        entry = self._entry(mode)
        self.assertEqual(entry["active_width"], 1332)
        self.assertEqual(entry["active_height"], 990)


if __name__ == "__main__":
    unittest.main()
