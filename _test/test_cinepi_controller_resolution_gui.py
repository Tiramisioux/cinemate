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
        self.forced_sets = []

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value, *, force=False):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value
        self.sets.append((key, value))
        if force:
            self.forced_sets.append((key, value))


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

    def resolve_effective_bit_depth(self, _camera_name, native_bit_depth, *, log_requested=False, hdr=False):
        """These tests are about resolution-switch GUI/pacing behavior, not
        CineMate Log's bit-depth math -- a trivial pass-through is enough to
        let _recompute_file_size() (wired into every resolution switch since
        671f327f) run without crashing."""
        return native_bit_depth


class ResolutionGuiStateTests(unittest.TestCase):
    def controller(self):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = FakeRedis()
        controller.sensor_detect = FakeSensorDetect()
        controller.current_sensor = "imx585"
        controller.sensor_mode = 0
        # _recompute_file_size() (671f327f) reads settings.camera.cam0.log_encode
        # as the pre-first-toggle seed -- off, like these tests' unrelated focus.
        controller.settings = {"camera": {"cam0": {"log_encode": False}, "cam1": {}}}
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
        controller._resolution_switch_complete_callbacks = []

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

    def test_raw_stream_ready_log_fires_switch_complete_not_switch_started(self):
        # F-290: reload_stream must ride the completion signal, not the one
        # that fires when the switch starts (the browser would reconnect to
        # a stream cinepi-raw hasn't finished restarting yet).
        controller = self.controller()
        resolution_info = controller.sensor_detect.res_modes[1]
        controller._publish_resolution_target_state(1, resolution_info, switching=True)
        controller._resolution_switching_timer = mock.Mock()
        complete_calls = []
        controller.add_resolution_switch_complete_callback(lambda: complete_calls.append(1))

        controller.handle_cinepi_raw_message(
            "[2026-05-31 18:00:31.405] [event_loop] [info] Raw stream: 3856x2180 : 7712 : SRGGB16"
        )

        self.assertEqual(complete_calls, [1])

    def test_nonmatching_raw_stream_log_does_not_fire_switch_complete(self):
        controller = self.controller()
        resolution_info = controller.sensor_detect.res_modes[1]
        controller._publish_resolution_target_state(1, resolution_info, switching=True)
        controller._resolution_switching_timer = mock.Mock()
        complete_calls = []
        controller.add_resolution_switch_complete_callback(lambda: complete_calls.append(1))

        controller.handle_cinepi_raw_message(
            "[2026-05-31 18:00:31.405] [event_loop] [info] Raw stream: 1928x1090 : 3904 : SRGGB16"
        )

        self.assertEqual(complete_calls, [])

    def test_switch_complete_timer_fallback_fires_the_callback(self):
        # The evidence path (handle_cinepi_raw_message) is the fast path;
        # this is the fallback if that log line is never seen. RESOLUTION_SWITCHING
        # has to be published True first -- as _apply_resolution_mode always does
        # before calling this -- or the already-complete guard treats the switch
        # as finished and returns without scheduling.
        controller = self.controller()
        resolution_info = controller.sensor_detect.res_modes[1]
        controller._publish_resolution_target_state(1, resolution_info, switching=True)
        complete_calls = []
        controller.add_resolution_switch_complete_callback(lambda: complete_calls.append(1))

        with mock.patch.object(cinepi_controller_module.threading, "Timer") as fake_timer_cls:
            fake_timer = mock.Mock()
            fake_timer_cls.return_value = fake_timer
            controller._schedule_resolution_switch_complete(1, resolution_info)
            complete_fn = fake_timer_cls.call_args.args[1]

        self.assertEqual(complete_calls, [])  # not fired until the timer actually runs
        complete_fn()
        self.assertEqual(complete_calls, [1])

    def test_switch_complete_force_republishes_camera_facing_keys(self):
        # LIVE-RESULTS-2026-08-27 §6: a mode switch resets the sensor's
        # exposure to VMAX while Redis keeps the old shutter_a, and the
        # operator's re-issued identical value is swallowed by set_value's
        # same-value dedup. Once the new stream is up, the camera-facing
        # keys must be force-republished so cinepi-raw reprograms the sensor.
        controller = self.controller()
        controller.redis_controller.values[ParameterKey.ISO.value] = "800"
        controller.redis_controller.values[ParameterKey.CG_RB.value] = "2.5,1.8"
        resolution_info = controller.sensor_detect.res_modes[1]
        controller._publish_resolution_target_state(1, resolution_info, switching=True)
        controller._resolution_switching_timer = mock.Mock()

        controller.handle_cinepi_raw_message(
            "[2026-05-31 18:00:31.405] [event_loop] [info] Raw stream: 3856x2180 : 7712 : SRGGB16"
        )

        self.assertEqual(
            controller.redis_controller.forced_sets,
            [
                (ParameterKey.SHUTTER_A.value, "180"),
                (ParameterKey.ISO.value, "800"),
                (ParameterKey.CG_RB.value, "2.5,1.8"),
            ],
        )

    def test_timer_fallback_also_force_republishes_camera_facing_keys(self):
        # The fallback path must re-apply too: if the raw-stream log line is
        # never seen, the sensor was still reconfigured and still reset.
        controller = self.controller()
        controller.redis_controller.values[ParameterKey.ISO.value] = "800"
        resolution_info = controller.sensor_detect.res_modes[1]
        controller._publish_resolution_target_state(1, resolution_info, switching=True)

        with mock.patch.object(cinepi_controller_module.threading, "Timer") as fake_timer_cls:
            fake_timer_cls.return_value = mock.Mock()
            controller._schedule_resolution_switch_complete(1, resolution_info)
            complete_fn = fake_timer_cls.call_args.args[1]

        self.assertEqual(controller.redis_controller.forced_sets, [])
        complete_fn()
        self.assertEqual(
            controller.redis_controller.forced_sets,
            [
                (ParameterKey.SHUTTER_A.value, "180"),
                (ParameterKey.ISO.value, "800"),
            ],
        )

    def test_reapply_republishes_zoom_when_present(self):
        # zoom joins the re-apply set now that cinepi-raw clears its
        # last-applied-zoom dedup baseline on every camera restart: the
        # restart resets the ISP's ScalerCrop to full frame, so the
        # operator's zoom must be force-republished to reprogram the crop.
        controller = self.controller()
        controller.redis_controller.values[ParameterKey.ZOOM.value] = "2.0"

        controller._reapply_camera_controls()

        self.assertEqual(
            controller.redis_controller.forced_sets,
            [
                (ParameterKey.SHUTTER_A.value, "180"),
                (ParameterKey.ZOOM.value, "2.0"),
            ],
        )

    def test_reapply_skips_cg_rb_for_a_mono_sensor(self):
        # cg_rb is a colour red/blue gain pair -- meaningless for a mono
        # sensor, which has no CFA to white-balance. cinepi_multi.py already
        # omits --awbgains from a mono launch line for the same reason; the
        # mode-switch republish should skip it too, for symmetry.
        controller = self.controller()
        controller.current_sensor = "imx585_mono"
        controller.redis_controller.values[ParameterKey.ISO.value] = "800"
        controller.redis_controller.values[ParameterKey.CG_RB.value] = "2.5,1.8"

        controller._reapply_camera_controls()

        self.assertEqual(
            controller.redis_controller.forced_sets,
            [
                (ParameterKey.SHUTTER_A.value, "180"),
                (ParameterKey.ISO.value, "800"),
            ],
        )

    def test_reapply_skips_keys_redis_does_not_hold(self):
        # A key never seeded (fresh boot, sensor without colour gains yet)
        # must be skipped, not published as None/empty.
        controller = self.controller()
        del controller.redis_controller.values[ParameterKey.SHUTTER_A.value]

        controller._reapply_camera_controls()

        self.assertEqual(controller.redis_controller.forced_sets, [])

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
