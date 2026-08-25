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

    def test_modes_are_sorted_largest_first(self):
        app = _make_app(FakeSensorDetect({
            "imx585": {
                0: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 87, "hdr": False},
                1: {"width": 3856, "height": 2180, "bit_depth": 12, "fps_max": 40, "hdr": False},
            },
        }))
        res = app.test_client().get("/settings-editor/api/sensor-modes")
        body = res.get_json()

        widths = [m["width"] for m in body["sensors"]["imx585"]]
        self.assertEqual(widths, [3856, 1928])


if __name__ == "__main__":
    unittest.main()
