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


if __name__ == "__main__":
    unittest.main()
