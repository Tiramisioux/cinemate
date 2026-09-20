"""WP-CM-10: the crop annotation the driver reports is in native sensor
coordinates (WP-585-1), not in the mode's binned output domain. The
settings-editor mode catalogue (GET /settings-editor/api/sensor-modes) has
two readers that used to assume the opposite and double-counted binning:

- the diagram's coordinate extent, which must be the full sensor-domain
  crop as reported (3840x2160 on IMX585), not that multiplied by binning
  again (which would double it to 7680x4320);
- ``active_width``/``active_height``, which must present the recorded
  picture (``width``/``height``), not the sensor-domain crop divided by
  nothing.

A sensor that reports no crop at all (every stock sensor) must be
unaffected.
"""

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

import flask

from module.app.settings_editor import settings_editor_bp


class FakeSensorDetect:
    """Exposes exactly the attributes get_sensor_modes() reads from a real
    SensorDetect: ``sensor_modes_unfiltered`` (the full driver catalogue)
    and, optionally, ``enabled_modes``."""

    def __init__(self, sensor_modes_unfiltered, enabled_modes=None):
        self.sensor_modes_unfiltered = sensor_modes_unfiltered
        self.enabled_modes = enabled_modes or {}


def _make_app(sensor_detect):
    app = flask.Flask(__name__)
    app.register_blueprint(settings_editor_bp)
    app.config["SENSOR_DETECT"] = sensor_detect
    app.config["SETTINGS"] = {}
    return app


def _get_modes(sensor_detect, camera="imx585"):
    app = _make_app(sensor_detect)
    res = app.test_client().get("/settings-editor/api/sensor-modes")
    body = res.get_json()
    assert body["ok"], body
    by_size = {(m["width"], m["height"]): m for m in body["sensors"][camera]}
    return by_size


class CropDomainSettingsEditorTests(unittest.TestCase):
    def test_full_2x2_mode_presents_its_recorded_picture_as_active(self):
        by_size = _get_modes(FakeSensorDetect({
            "imx585": [{
                "width": 1920, "height": 1080, "bit_depth": 12, "fps_max": 50,
                "hdr": False,
                "crop_x": 0, "crop_y": 0,
                "crop_width": 3840, "crop_height": 2160,
                "sensor_width": 3856, "sensor_height": 2180,
                "binning_x": 2, "binning_y": 2,
            }],
        }))
        mode = by_size[(1920, 1080)]
        self.assertTrue(mode["full"])
        self.assertEqual(mode["active_width"], 1920)
        self.assertEqual(mode["active_height"], 1080)

    def test_2x2_window_presents_its_recorded_picture_as_active(self):
        by_size = _get_modes(FakeSensorDetect({
            "imx585": [{
                "width": 1440, "height": 1080, "bit_depth": 12, "fps_max": 50,
                "hdr": False,
                "crop_x": 240, "crop_y": 0,
                "crop_width": 2880, "crop_height": 2160,
                "sensor_width": 3856, "sensor_height": 2180,
                "binning_x": 2, "binning_y": 2,
            }],
        }))
        mode = by_size[(1440, 1080)]
        self.assertFalse(mode["full"])
        self.assertEqual(mode["active_width"], 1440)
        self.assertEqual(mode["active_height"], 1080)

    def test_diagram_extent_is_the_sensor_domain_crop_not_double_that(self):
        by_size = _get_modes(FakeSensorDetect({
            "imx585": [{
                "width": 1920, "height": 1080, "bit_depth": 12, "fps_max": 50,
                "hdr": False,
                "crop_x": 0, "crop_y": 0,
                "crop_width": 3840, "crop_height": 2160,
                "sensor_width": 3856, "sensor_height": 2180,
                "binning_x": 2, "binning_y": 2,
            }],
        }))
        mode = by_size[(1920, 1080)]
        self.assertEqual(mode["diagram_sensor_width"], 3840)
        self.assertEqual(mode["diagram_sensor_height"], 2160)

    def test_stock_sensor_with_no_crop_metadata_is_unaffected(self):
        by_size = _get_modes(FakeSensorDetect({
            "imx477": [{
                "width": 4056, "height": 3040, "bit_depth": 12, "fps_max": 20,
                "hdr": False,
                "crop_x": None, "crop_y": None,
                "crop_width": None, "crop_height": None,
                "sensor_width": None, "sensor_height": None,
                "binning_x": None, "binning_y": None,
            }],
        }), camera="imx477")
        mode = by_size[(4056, 3040)]
        self.assertFalse(mode["full"])
        self.assertFalse(mode["crop_known"])
        self.assertEqual(mode["active_width"], 4056)
        self.assertEqual(mode["active_height"], 3040)
        self.assertIsNone(mode["diagram_sensor_width"])
        self.assertIsNone(mode["diagram_sensor_height"])


if __name__ == "__main__":
    unittest.main()
