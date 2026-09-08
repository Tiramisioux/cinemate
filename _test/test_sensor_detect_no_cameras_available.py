"""Review item 6: a zero-camera boot must not become a fake-camera boot.

Every degraded-boot guard on this branch keys on `if not
sensor_detect.res_modes`. That predicate is only equivalent to "no camera"
if the probe actually leaves res_modes empty -- and with a `custom_modes`
entry configured it didn't.

cinepi-raw prints "No cameras available!" to stdout, so
detect_camera_model()'s `if not out.strip()` guard never fires: the output
is non-empty, it just doesn't describe a camera. Detection proceeded to
_finalize_modes({}), whose custom-modes loop did `sensors.setdefault(cam, [])`
and appended unconditionally -- manufacturing a camera out of a settings key.
res_modes came back non-empty, camera_model was set to the custom_modes key,
and every "no camera" guard this branch added was bypassed. The state
corruption c3.13 exists to prevent could still happen, gated on an unrelated
settings feature rather than on camera presence.
"""

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.config_loader import strip_jsonc
from module.sensor_detect import SensorDetect


# What cinepi-raw actually prints with no sensor attached
# (cinepi-raw/core/options.cpp). Note it goes to stdout and is NOT empty --
# that is the whole problem.
NO_CAMERAS_OUTPUT = "No cameras available!\n"

CUSTOM_MODES = {
    "imx585": [
        {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 50},
    ],
}


def _build_detector(custom_modes, list_cameras_output):
    settings = json.loads(strip_jsonc(
        (ROOT / "resources/settings/settings_default.jsonc").read_text(encoding="utf-8")
    ))
    rc = settings["image_capture"]
    detector = SensorDetect.__new__(SensorDetect)
    detector.settings = settings
    detector.k_steps = rc["k_steps"]
    detector.bit_depths = rc["bit_depths"]
    detector.custom_modes = custom_modes
    detector.hdr_modes = SensorDetect._hdr_whitelist(rc.get("hdr", {}))
    detector.sensor_database_file = "resources/sensors.json"
    detector.sensor_database = detector._load_sensor_database()
    detector.packing_info = detector._packing_info_from_database()
    detector.sensor_resolutions = {}
    detector.camera_model = None
    detector.res_modes = {}
    detector._kill_stale_cinepi_raw = lambda: None
    detector._list_cameras = lambda hdr=False: list_cameras_output
    return detector


class NoCamerasAvailableTests(unittest.TestCase):

    def test_no_custom_modes_gives_a_clean_no_camera_result(self):
        detector = _build_detector({}, NO_CAMERAS_OUTPUT)

        detector.detect_camera_model()

        self.assertIsNone(detector.camera_model)
        self.assertEqual(detector.res_modes, {})

    def test_custom_modes_do_not_manufacture_a_camera(self):
        detector = _build_detector(CUSTOM_MODES, NO_CAMERAS_OUTPUT)

        detector.detect_camera_model()

        self.assertIsNone(detector.camera_model)
        self.assertEqual(detector.res_modes, {})

    def test_the_degraded_boot_predicate_actually_holds(self):
        # This is the assertion the rest of the branch depends on: every
        # guard added by C3 tests `not res_modes`, so if that is False here
        # the whole state-preservation mechanism silently does not engage.
        detector = _build_detector(CUSTOM_MODES, NO_CAMERAS_OUTPUT)

        detector.detect_camera_model()

        self.assertFalse(detector.res_modes)


class CustomModesStillApplyToADetectedCameraTests(unittest.TestCase):
    """The fix must not stop custom_modes doing its actual job."""

    IMX585_OUTPUT = """
0 : imx585 [3856x2180] (/base/soc/i2c0mux/i2c@1/imx585@1a)
    Modes: 'SRGGB12_CSI2P' : 1928x1090 [87.00 fps - (0, 0)/3856x2180 crop]
                              3856x2180 [40.00 fps - (0, 0)/3856x2180 crop]
"""

    def test_an_entry_for_a_detected_camera_is_still_applied(self):
        detector = _build_detector(CUSTOM_MODES, self.IMX585_OUTPUT)

        detector.detect_camera_model()

        self.assertEqual(detector.camera_model, "imx585")
        fps_maxes = {
            (m["width"], m["height"]): m.get("fps_max")
            for m in detector.res_modes.values()
        }
        self.assertEqual(fps_maxes[(1928, 1090)], 50)

    def test_an_entry_for_an_absent_camera_does_not_invent_it(self):
        detector = _build_detector(
            {"imx477": [{"width": 2028, "height": 1080, "bit_depth": 12, "fps_max": 50}]},
            self.IMX585_OUTPUT,
        )

        detector.detect_camera_model()

        self.assertEqual(detector.camera_model, "imx585")
        self.assertNotIn("imx477", detector.sensor_resolutions)


if __name__ == "__main__":
    unittest.main()
