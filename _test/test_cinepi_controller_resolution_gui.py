import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

import module.cinepi_controller as cinepi_controller_module
from module.cinepi_controller import CinePiController
from module.redis_controller import ParameterKey


class FakeRedis:
    def __init__(self):
        self.values = {
            ParameterKey.FPS.value: "24",
            ParameterKey.FPS_USER.value: "24",
            ParameterKey.FPS_MAX.value: "50",
            ParameterKey.SHUTTER_A.value: "180",
            ParameterKey.IS_RECORDING.value: "0",
        }
        self.sets = []

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value
        self.sets.append((key, value))


class FakeSensorDetect:
    camera_model = "imx585"

    def __init__(self):
        self.res_modes = {
            0: {
                "width": 1928,
                "height": 1090,
                "bit_depth": 12,
                "packing": "U",
                "gui_layout": 0,
                "file_size": 25,
                "fps_max": 50,
            },
            1: {
                "width": 3856,
                "height": 2180,
                "bit_depth": 12,
                "packing": "U",
                "gui_layout": 1,
                "file_size": 90,
                "fps_max": 25,
            },
        }

    def get_lores_width(self, _sensor, mode):
        return 960 if int(mode) == 1 else 640

    def get_lores_height(self, _sensor, mode):
        return 540 if int(mode) == 1 else 360

    def get_fps_correction_factor(self, _sensor, _mode, _fps=None):
        return 1.0


class ResolutionGuiStateTests(unittest.TestCase):
    def controller(self):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = FakeRedis()
        controller.sensor_detect = FakeSensorDetect()
        controller.current_sensor = "imx585"
        controller.sensor_mode = 0
        controller.dynamic_resolution_enabled = True
        controller.dynamic_resolution_desired_mode = 0
        controller.dynamic_resolution_active = False
        controller.fps_steps = [24, 25, 40, 50]
        controller.fps_steps_dynamic = list(controller.fps_steps)
        controller.fps_free = False
        controller.current_fps = 24
        controller.fps = 24
        controller.shutter_a_sync_mode = 0
        controller.notifications = []
        controller.cinepi = mock.Mock()
        controller._is_recording = lambda: False
        controller.calculate_dynamic_shutter_angles = lambda _fps: [180]
        controller.initialize_fps_steps = lambda _steps: None
        controller.update_steps = lambda: None
        controller._notify_resolution_change = controller.notifications.append

        def refresh_fps_max():
            controller.fps_max = 50
            controller.redis_controller.set_value(ParameterKey.FPS_MAX.value, 50)
            return 50

        controller._refresh_fps_max = refresh_fps_max
        return controller

    def test_resolution_metadata_is_published_before_reconfigure_pacing(self):
        controller = self.controller()
        observed_during_pace = []

        def pace(_recording):
            observed_during_pace.append(
                {
                    "sensor_mode": controller.redis_controller.get_value(ParameterKey.SENSOR_MODE.value),
                    "width": controller.redis_controller.get_value(ParameterKey.WIDTH.value),
                    "gui_layout": controller.redis_controller.get_value(ParameterKey.GUI_LAYOUT.value),
                    "controller_mode": controller.sensor_mode,
                }
            )

        controller._pace_resolution_change = pace

        with mock.patch.object(
            cinepi_controller_module,
            "GUI_RESOLUTION_PREVIEW_DELAY_SECONDS",
            0,
        ):
            self.assertTrue(controller._apply_resolution_mode(1))

        self.assertEqual(
            observed_during_pace,
            [
                {
                    "sensor_mode": "1",
                    "width": "3856",
                    "gui_layout": "1",
                    "controller_mode": 1,
                }
            ],
        )
        self.assertEqual(controller.notifications, [1])

    def test_switch_resolution_logs_and_toggles_from_desired_mode_when_dynamic_active(self):
        controller = self.controller()
        controller.dynamic_resolution_desired_mode = 1
        controller.redis_controller.set_value(ParameterKey.SENSOR_MODE.value, "0")
        selected_modes = []
        controller.set_resolution = lambda mode: selected_modes.append(mode) or True

        with self.assertLogs(level="INFO") as logs:
            self.assertTrue(controller.switch_resolution())

        self.assertEqual(selected_modes, [0])
        self.assertIn(
            "Switching resolution from mode 1 to mode 0",
            "\n".join(logs.output),
        )


if __name__ == "__main__":
    unittest.main()
