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

    def get_packing_for_platform(self, _sensor, mode, is_pi4=None):
        return self.res_modes[int(mode)].get("packing", "U")

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
        controller._resolution_switching_timer = None

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
                    "target_mode": controller.redis_controller.get_value(ParameterKey.RESOLUTION_TARGET_MODE.value),
                    "width": controller.redis_controller.get_value(ParameterKey.WIDTH.value),
                    "target_width": controller.redis_controller.get_value(ParameterKey.RESOLUTION_TARGET_WIDTH.value),
                    "gui_layout": controller.redis_controller.get_value(ParameterKey.GUI_LAYOUT.value),
                    "controller_mode": controller.sensor_mode,
                    "switching": controller.redis_controller.get_value(ParameterKey.RESOLUTION_SWITCHING.value),
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
                    "target_mode": "1",
                    "width": "3856",
                    "target_width": "3856",
                    "gui_layout": "1",
                    "controller_mode": 1,
                    "switching": 1,
                }
            ],
        )
        self.assertEqual(controller.notifications, [1])
        controller._cancel_resolution_switching_timer()

    def test_resolution_change_needs_restart_on_aspect_bitdepth_or_hdr(self):
        controller = self.controller()
        # Currently running 1928x1090 (~1.769) 12-bit non-HDR — seed redis.
        controller.redis_controller.set_value(ParameterKey.WIDTH.value, 1928)
        controller.redis_controller.set_value(ParameterKey.HEIGHT.value, 1090)
        controller.redis_controller.set_value(ParameterKey.BIT_DEPTH.value, 12)
        controller.redis_controller.set_value(ParameterKey.HDR.value, 0)
        controller._is_recording = lambda: False

        # Same aspect, same bit depth, same HDR (mode 1 = 3856x2180 12-bit) → no restart.
        self.assertFalse(controller._resolution_change_needs_restart(1))

        # Different-aspect target (1.33) → restart so the preview is rebuilt.
        controller.sensor_detect.res_modes[2] = {
            "width": 2028, "height": 1520, "bit_depth": 12,
            "gui_layout": 0, "file_size": 5, "fps_max": 45,
        }
        self.assertTrue(controller._resolution_change_needs_restart(2))

        # Same aspect but 16-bit ClearHDR (mode 3 = 3856x2180 16-bit HDR) →
        # restart: bit depth and --hdr sensor are launch args, so a live
        # reconfigure would keep writing 12-bit DNGs.
        controller.sensor_detect.res_modes[3] = {
            "width": 3856, "height": 2180, "bit_depth": 16, "hdr": True,
            "gui_layout": 1, "file_size": 16, "fps_max": 22,
        }
        self.assertTrue(controller._resolution_change_needs_restart(3))

        # Same aspect, same bit depth, but ClearHDR toggled on (12-bit HDR) →
        # restart so cinepi-raw relaunches with --hdr sensor.
        controller.sensor_detect.res_modes[4] = {
            "width": 3856, "height": 2180, "bit_depth": 12, "hdr": True,
            "gui_layout": 1, "file_size": 12, "fps_max": 33,
        }
        self.assertTrue(controller._resolution_change_needs_restart(4))

        # While recording, never restart — record-through is preserved.
        controller._is_recording = lambda: True
        self.assertFalse(controller._resolution_change_needs_restart(3))

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

    def test_raw_stream_ready_log_clears_resolution_switching(self):
        controller = self.controller()
        resolution_info = controller.sensor_detect.res_modes[1]
        controller._publish_resolution_target_state(1, resolution_info, switching=True)
        timer = mock.Mock()
        controller._resolution_switching_timer = timer

        controller.handle_cinepi_raw_message(
            "[2026-05-31 18:00:31.405] [event_loop] [info] Raw stream: 3856x2180 : 7712 : SRGGB16"
        )

        timer.cancel.assert_called_once()
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.RESOLUTION_SWITCHING.value),
            0,
        )

    def test_nonmatching_raw_stream_log_does_not_clear_resolution_switching(self):
        controller = self.controller()
        resolution_info = controller.sensor_detect.res_modes[1]
        controller._publish_resolution_target_state(1, resolution_info, switching=True)
        timer = mock.Mock()
        controller._resolution_switching_timer = timer

        controller.handle_cinepi_raw_message(
            "[2026-05-31 18:00:31.405] [event_loop] [info] Raw stream: 1928x1090 : 3904 : SRGGB16"
        )

        timer.cancel.assert_not_called()
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.RESOLUTION_SWITCHING.value),
            1,
        )


if __name__ == "__main__":
    unittest.main()
