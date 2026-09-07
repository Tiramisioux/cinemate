import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.cinepi_controller import CinePiController
from module.redis_controller import ParameterKey


class FakeRedis:
    def __init__(self, **values):
        self.values = {}
        for key, value in values.items():
            self.values[ParameterKey[key.upper()].value] = value

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value


# The imx585 configuration the ladder was asked for: 12-bit ClearHDR hidden,
# so two classes -- SDR and 16-bit ClearHDR -- at two sizes each.
MODES = {
    0: {"width": 1928, "height": 1090, "bit_depth": 12, "fps_max": 87},
    1: {"width": 3856, "height": 2180, "bit_depth": 12, "fps_max": 40},
    2: {"width": 1928, "height": 1090, "bit_depth": 16, "hdr": True, "fps_max": 40},
    3: {"width": 3856, "height": 2180, "bit_depth": 16, "hdr": True, "fps_max": 21},
}


class FakeSensorDetect:
    res_modes = MODES

    def get_fps_max(self, _sensor, mode):
        return MODES[int(mode)]["fps_max"]


class DynamicResolutionPriorityTests(unittest.TestCase):
    """The setting that decides which half of the picture dynamic resolution
    gives up first, and the one place it is not allowed to decide: mid-take,
    where crossing a mode class would mean relaunching cinepi-raw."""

    def controller(self, redis=None, *, sensor_mode=3, desired_mode=3,
                   priority="mode"):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = redis if redis is not None else FakeRedis()
        controller.dynamic_resolution_enabled = True
        controller.dynamic_resolution_active = False
        controller.dynamic_resolution_desired_mode = desired_mode
        controller.dynamic_resolution_priority = priority
        controller.dynamic_resolution_suspended = False
        controller.dynamic_resolution_deferred = False
        controller.sensor_mode = sensor_mode
        controller.current_sensor = "imx585"
        controller.sensor_detect = FakeSensorDetect()
        controller.fps_free = False
        controller.fps_free_increment = 1
        controller.fps_steps = [24, 25, 30, 50, 60, 87]
        controller.fps_steps_dynamic = []
        controller.settings = {
            "arrays": {"fps": {"steps": [24, 25, 30, 50, 60, 87]}},
            "image_capture": {"dynamic_resolution": True},
        }
        return controller

    # ── startup read-back ────────────────────────────────────────────────
    def test_startup_prefers_redis_then_settings_then_the_default(self):
        controller = self.controller()
        self.assertEqual(
            controller._get_startup_dynamic_resolution_priority(), "mode")

        controller.settings["image_capture"]["dynamic_resolution_priority"] = "resolution"
        self.assertEqual(
            controller._get_startup_dynamic_resolution_priority(), "resolution")

        # Redis is the operator's most recent explicit answer, so it wins over
        # settings.jsonc exactly as the enabled flag does.
        controller.redis_controller.set_value(
            ParameterKey.DYNAMIC_RESOLUTION_PRIORITY.value, "none")
        self.assertEqual(
            controller._get_startup_dynamic_resolution_priority(), "none")

    def test_a_typo_in_settings_falls_back_rather_than_failing_the_boot(self):
        controller = self.controller()
        controller.settings["image_capture"]["dynamic_resolution_priority"] = "sideways"
        self.assertEqual(
            controller._get_startup_dynamic_resolution_priority(), "mode")

    # ── the setter ───────────────────────────────────────────────────────
    def test_setting_a_priority_publishes_it_and_moves_the_ceiling_with_it(self):
        # Mode 3 (16-bit 4K) tops out at 21 on its own and 40 within its
        # class; 87 is only reachable by giving the class up. The step table
        # is built from this number, so it has to follow the policy.
        controller = self.controller(priority="none")

        controller.set_dynamic_resolution_priority("none")
        self.assertEqual(controller.fps_max, 40)

        controller.set_dynamic_resolution_priority("resolution")

        self.assertEqual(controller.dynamic_resolution_priority, "resolution")
        self.assertEqual(controller.fps_max, 87)
        self.assertEqual(
            controller.redis_controller.get_value(
                ParameterKey.DYNAMIC_RESOLUTION_PRIORITY.value),
            "resolution",
        )
        self.assertLessEqual(max(controller.fps_steps_dynamic), 87)

    def test_a_bare_call_cycles_so_it_can_be_bound_to_a_button(self):
        controller = self.controller(priority="mode")

        seen = []
        for _ in range(4):
            controller.set_dynamic_resolution_priority()
            seen.append(controller.dynamic_resolution_priority)

        self.assertEqual(seen, ["resolution", "none", "mode", "resolution"])

    def test_an_unrecognised_priority_is_rejected_not_silently_defaulted(self):
        # And rejected without raising: this is reachable from the CLI with
        # an arbitrary string, and an exception there takes the dispatch
        # thread down with it.
        controller = self.controller(priority="resolution")

        with self.assertLogs(level="ERROR"):
            controller.set_dynamic_resolution_priority("sideways")

        self.assertEqual(controller.dynamic_resolution_priority, "resolution")

    def test_setting_a_priority_re_settles_the_live_mode(self):
        # Without this the camera keeps whatever the old policy last chose
        # until the operator happens to touch fps again.
        controller = self.controller(priority="none")
        controller.redis_controller.set_value(ParameterKey.FPS_USER.value, 50)
        applied = []
        controller._maybe_apply_dynamic_resolution_for_fps = applied.append

        controller.set_dynamic_resolution_priority("mode")

        self.assertEqual(applied, [50.0])

    # ── the one place the policy does not get to decide ──────────────────
    def test_off_take_the_ladder_crosses_the_class(self):
        controller = self.controller()

        choice = controller._dynamic_resolution_choice_for_fps(60)

        self.assertEqual(choice.mode, 0)
        self.assertTrue(choice.mode_class_changed)
        self.assertFalse(controller.dynamic_resolution_deferred)

    def test_mid_take_a_class_change_is_held_back_not_applied(self):
        # Bit depth is part of --mode and ClearHDR is the --hdr sensor launch
        # flag, so crossing a class means relaunching cinepi-raw -- which
        # would end the take under the operator.
        controller = self.controller(redis=FakeRedis(is_recording=1))

        choice = controller._dynamic_resolution_choice_for_fps(60)

        self.assertIsNone(choice)
        self.assertTrue(controller.dynamic_resolution_deferred)

    def test_mid_take_a_same_class_substitution_still_happens(self):
        controller = self.controller(redis=FakeRedis(is_recording=1))

        choice = controller._dynamic_resolution_choice_for_fps(40)

        self.assertEqual(choice.mode, 2)
        self.assertFalse(choice.mode_class_changed)
        self.assertFalse(controller.dynamic_resolution_deferred)

    def test_the_ceiling_shrinks_to_the_running_class_for_the_take(self):
        idle = self.controller()
        self.assertIsNone(idle._in_take_fps_ceiling())

        recording = self.controller(redis=FakeRedis(is_recording=1))
        self.assertEqual(recording._in_take_fps_ceiling(), 40)

        # Already dropped into SDR before the take started: the pin is where
        # we are, not a penalty, so the full ladder ceiling is back.
        dropped = self.controller(redis=FakeRedis(is_recording=1), sensor_mode=0)
        self.assertEqual(dropped._in_take_fps_ceiling(), 87)

        # "none" never crosses a class in the first place, so a take imposes
        # no extra limit on it.
        locked = self.controller(redis=FakeRedis(is_recording=1), priority="none")
        self.assertIsNone(locked._in_take_fps_ceiling())

    def test_a_held_back_class_change_settles_when_the_take_ends(self):
        controller = self.controller(redis=FakeRedis(is_recording=1))
        controller.redis_controller.set_value(ParameterKey.FPS_USER.value, 60)
        controller._cancel_timed_recording_stop = lambda: None
        controller.stop_recording_worker = lambda: None
        applied = []
        controller._maybe_apply_dynamic_resolution_for_fps = applied.append

        controller._dynamic_resolution_choice_for_fps(60)
        self.assertTrue(controller.dynamic_resolution_deferred)

        controller.stop_recording()

        self.assertEqual(applied, [60.0])
        self.assertFalse(controller.dynamic_resolution_deferred)

    def test_nothing_is_re_settled_when_nothing_was_held_back(self):
        controller = self.controller(redis=FakeRedis(is_recording=1))
        controller.redis_controller.set_value(ParameterKey.FPS_USER.value, 24)
        controller._cancel_timed_recording_stop = lambda: None
        controller.stop_recording_worker = lambda: None
        applied = []
        controller._maybe_apply_dynamic_resolution_for_fps = applied.append

        controller.stop_recording()

        self.assertEqual(applied, [])


if __name__ == "__main__":
    unittest.main()
