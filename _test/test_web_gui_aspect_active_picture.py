"""The main web GUI's grey aspect box read "1.81" for a mode the settings
pane correctly called 1.78:1 -- the imx283 10-bit UHD base mode
(IMX283_MODE_1C), whose delivered active picture (3840x2160 -> 1.78) is
smaller than the transport frame cinepi-raw allocates for it (3936x2176 ->
1.81: 96 leading optical-black columns, 16 trailing OB rows), confirmed
against a real DNG (DefaultCropSize 3840x2160, frame 3936x2176).

module.sensor_detect.active_picture_size() is the one shared helper for
"what is the delivered active picture" (Round 2, Defect D/B2; routed through
by commit 75a3ab4b for _mode_from_metadata_or_detected,
compute_preview_geometry and settings_editor._active_dimension). CAM0's
"aspect" and CAM1's "aspect_cam1" in SimpleGUI.populate_values() were two
more copies still deriving straight from WIDTH/HEIGHT -- the transport frame
-- and were the grey box's actual code path. This test locks both to the
active picture whenever a mode's active/crop geometry differs from its
transport size, and confirms the transport-only fallback still applies when
a mode reports no such geometry at all (a stock sensor with no crop
annotation).
"""

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("flask_socketio", types.SimpleNamespace(SocketIO=object))
sys.modules.setdefault("gpiozero", types.SimpleNamespace(CPUTemperature=object))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))
sys.modules.setdefault("sugarpie", types.SimpleNamespace(pisugar=types.SimpleNamespace()))

from module.redis_controller import ParameterKey  # noqa: E402

from test_simple_gui_no_camera import make_gui  # noqa: E402


class FakeSensorDetectWithModes:
    """get_resolution_info() returns whatever mode dict the test wants for
    a given (camera_name, sensor_mode) pair -- the same shape
    SensorDetect.get_resolution_info() returns for real (a full mode dict,
    including any active_width/active_height/crop_width/crop_height/
    binning_x/binning_y keys the driver reported)."""

    def __init__(self, modes_by_key, res_modes=None, camera_model=None):
        self._modes_by_key = modes_by_key
        self.res_modes = res_modes if res_modes is not None else {}
        self.camera_model = camera_model

    def get_resolution_info(self, camera_name, sensor_mode):
        return self._modes_by_key[(camera_name, int(sensor_mode))]


IMX283_MODE_1C_TRANSPORT_WIDTH = 3936
IMX283_MODE_1C_TRANSPORT_HEIGHT = 2176
IMX283_MODE_1C_ACTIVE_WIDTH = 3840
IMX283_MODE_1C_ACTIVE_HEIGHT = 2160


class WebGuiAspectActivePictureTests(unittest.TestCase):
    def test_cam0_aspect_uses_the_active_picture_not_the_transport_frame(self):
        gui = make_gui(
            cameras_json='[{"port": "cam0", "model": "imx283", "mono": false}]'
        )
        gui.redis_controller.values.update({
            ParameterKey.WIDTH.value: IMX283_MODE_1C_TRANSPORT_WIDTH,
            ParameterKey.HEIGHT.value: IMX283_MODE_1C_TRANSPORT_HEIGHT,
            ParameterKey.SENSOR_MODE.value: 0,
        })
        gui.sensor_detect = FakeSensorDetectWithModes({
            ("imx283", 0): {
                "width": IMX283_MODE_1C_TRANSPORT_WIDTH,
                "height": IMX283_MODE_1C_TRANSPORT_HEIGHT,
                "active_width": IMX283_MODE_1C_ACTIVE_WIDTH,
                "active_height": IMX283_MODE_1C_ACTIVE_HEIGHT,
            },
        })

        values = gui.populate_values()

        # 3840/2160 = 1.7778 -> "1.78", matching the settings pane -- not
        # 3936/2176 = 1.8088 -> "1.81", the transport frame's own ratio.
        self.assertEqual(values["aspect"], "1.78")

    def test_cam1_aspect_uses_the_active_picture_not_the_transport_frame(self):
        gui = make_gui(
            cameras_json=(
                '[{"port": "cam0", "model": "imx283", "mono": false},'
                ' {"port": "cam1", "model": "imx283", "mono": false}]'
            )
        )
        gui.draw_right_col = True
        gui.redis_controller.values.update({
            ParameterKey.WIDTH.value: IMX283_MODE_1C_TRANSPORT_WIDTH,
            ParameterKey.HEIGHT.value: IMX283_MODE_1C_TRANSPORT_HEIGHT,
            ParameterKey.SENSOR_MODE.value: 0,
        })
        mode = {
            "width": IMX283_MODE_1C_TRANSPORT_WIDTH,
            "height": IMX283_MODE_1C_TRANSPORT_HEIGHT,
            "active_width": IMX283_MODE_1C_ACTIVE_WIDTH,
            "active_height": IMX283_MODE_1C_ACTIVE_HEIGHT,
            "bit_depth": 10,
        }
        gui.sensor_detect = FakeSensorDetectWithModes({
            ("imx283", 0): mode,
        })

        values = gui.populate_values()

        self.assertEqual(values["aspect_cam1"], 1.78)

    def test_transport_only_fallback_still_applies_with_no_crop_geometry(self):
        # A stock sensor whose driver reports no crop/active annotation at
        # all (e.g. imx477): active_picture_size()'s tier 4. Must not
        # regress to "N/A" or throw just because the mode dict is bare.
        gui = make_gui(
            cameras_json='[{"port": "cam0", "model": "imx477", "mono": false}]'
        )
        gui.redis_controller.values.update({
            ParameterKey.WIDTH.value: 4056,
            ParameterKey.HEIGHT.value: 3040,
            ParameterKey.SENSOR_MODE.value: 0,
        })
        gui.sensor_detect = FakeSensorDetectWithModes({
            ("imx477", 0): {"width": 4056, "height": 3040},
        })

        values = gui.populate_values()

        self.assertEqual(values["aspect"], "1.33")


if __name__ == "__main__":
    unittest.main()
