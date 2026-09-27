"""Issue 6 (W4, todo batch 2026-09-27): "Make it possible to enable/disable
sync warnings (toggle switch)".

Decision recorded in the findings file and the commit body: this is a
DISPLAY-only toggle (option (a) in the prompt). redis_listener.py's
judgement -- frames_in_sync, its logging, the live latch, and the
end-of-take analysis -- runs completely unconditionally. The toggle only
gates whether SimpleGUI.populate_values() lets that judgement reach the
SYNC box/flash on either GUI. DROP is a separate box driven by separate
Redis keys (drop_frame / drop_frame_during_last_take) and is deliberately
out of scope -- see the findings file.

Four groups, each covering one link of the chain:

1. The settings default (config_loader.py's single source of truth).
2. The controller setter -- the CLI/serial/API-reachable half
   (mirrors test_dynamic_resolution_enabled_toggle.py's controller()
   pattern: CinePiController.__new__ + hand-set attributes).
3. CLI dispatch, including that it does not collide with the
   unrelated `set shutter a sync` (exposure-sync mode -- a different
   "sync" one line above it in the command table).
4. The GUI gate itself: turning the toggle off must not change
   values["frames_in_sync"] (the raw judgement), only the derived
   values["frames_off_sync"] the boxes/flash are gated on.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("flask_socketio", types.SimpleNamespace(SocketIO=object))
sys.modules.setdefault("gpiozero", types.SimpleNamespace(CPUTemperature=object))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))
sys.modules.setdefault("sugarpie", types.SimpleNamespace(pisugar=types.SimpleNamespace()))

from module.cinepi_controller import CinePiController
from module.cli_commands import CommandExecutor
from module.config_loader import _apply_settings_defaults
from module.redis_controller import ParameterKey
from module.simple_gui import SimpleGUI


# ─────────────────────────── settings default ──────────────────────────

class SettingsDefaultTests(unittest.TestCase):
    def test_sync_warnings_enabled_defaults_true(self):
        # _apply_settings_defaults is the one place this default is stated
        # (config_loader.py); read it back rather than restating "True" a
        # second time in this test.
        settings = _apply_settings_defaults({})
        self.assertIs(settings["settings"]["sync_warnings_enabled"], True)

    def test_an_explicit_false_in_settings_jsonc_is_kept(self):
        # setdefault must not clobber an operator's own choice.
        settings = _apply_settings_defaults({"settings": {"sync_warnings_enabled": False}})
        self.assertIs(settings["settings"]["sync_warnings_enabled"], False)

    def test_does_not_live_inside_sync_tolerances(self):
        # It is a display switch, not a frame-count tolerance -- see the
        # commit body / findings file for why it is a sibling key.
        settings = _apply_settings_defaults({})
        self.assertNotIn("sync_warnings_enabled", settings["settings"]["sync_tolerances"])


# ─────────────────────────── controller setter ──────────────────────────

class FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value, *, force=False):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value


class ControllerSetterTests(unittest.TestCase):
    def controller(self, redis, enabled=True):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = redis
        controller.sync_warnings_enabled = enabled
        return controller

    def test_set_explicit_off_and_publishes(self):
        controller = self.controller(FakeRedis(), enabled=True)
        controller.set_sync_warnings_enabled(0)
        self.assertFalse(controller.sync_warnings_enabled)
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.SYNC_WARNINGS_ENABLED.value), 0
        )

    def test_set_explicit_on_and_publishes(self):
        controller = self.controller(FakeRedis(), enabled=False)
        controller.set_sync_warnings_enabled(1)
        self.assertTrue(controller.sync_warnings_enabled)
        self.assertEqual(
            controller.redis_controller.get_value(ParameterKey.SYNC_WARNINGS_ENABLED.value), 1
        )

    def test_toggle_with_no_value_flips_current_state(self):
        controller = self.controller(FakeRedis(), enabled=True)
        controller.set_sync_warnings_enabled()
        self.assertFalse(controller.sync_warnings_enabled)
        controller.set_sync_warnings_enabled()
        self.assertTrue(controller.sync_warnings_enabled)

    def test_invalid_value_raises(self):
        controller = self.controller(FakeRedis())
        with self.assertRaises(ValueError):
            controller.set_sync_warnings_enabled("nonsense")

    def test_accepts_bool_true_false_too(self):
        controller = self.controller(FakeRedis(), enabled=True)
        controller.set_sync_warnings_enabled(False)
        self.assertFalse(controller.sync_warnings_enabled)
        controller.set_sync_warnings_enabled(True)
        self.assertTrue(controller.sync_warnings_enabled)


# ─────────────────────────────── CLI dispatch ───────────────────────────

class CliDispatchTests(unittest.TestCase):
    def make_executor(self):
        controller = mock.MagicMock()
        app = mock.MagicMock()
        return CommandExecutor(controller, app), controller

    def test_bare_command_toggles(self):
        executor, controller = self.make_executor()
        self.assertEqual(executor.handle_received_data("set sync warnings"), (True, ""))
        controller.set_sync_warnings_enabled.assert_called_once_with()

    def test_command_with_int_argument_dispatches_and_coerces_type(self):
        executor, controller = self.make_executor()
        self.assertEqual(executor.handle_received_data("set sync warnings 0"), (True, ""))
        controller.set_sync_warnings_enabled.assert_called_once_with(0)
        self.assertIsInstance(controller.set_sync_warnings_enabled.call_args[0][0], int)

    def test_bad_argument_is_rejected(self):
        executor, controller = self.make_executor()
        self.assertEqual(
            executor.handle_received_data("set sync warnings notanumber"), (False, "bad argument")
        )
        controller.set_sync_warnings_enabled.assert_not_called()

    def test_does_not_collide_with_shutter_angle_sync_mode(self):
        # 'set shutter a sync' (exposure-sync mode) sits one line above 'set
        # sync warnings' in the command table -- two unrelated concepts that
        # both use the word "sync". Confirm dispatch keeps them apart.
        executor, controller = self.make_executor()

        self.assertEqual(executor.handle_received_data("set shutter a sync 1"), (True, ""))
        controller.set_shutter_a_sync_mode.assert_called_once_with(1)
        controller.set_sync_warnings_enabled.assert_not_called()

        self.assertEqual(executor.handle_received_data("set sync warnings 1"), (True, ""))
        controller.set_sync_warnings_enabled.assert_called_once_with(1)


# ───────────────────────── GUI display gate ─────────────────────────────

class FakeGuiRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)


class FakeGuiController:
    """Same shape as test_simple_gui_no_camera.py's FakeController, plus the
    new sync_warnings_enabled attribute this test exercises."""

    def __init__(self, sync_warnings_enabled=True):
        self.exposure_time_fractions = "1/48"
        self.iso_lock = False
        self.shutter_a_nom_lock = False
        self.fps_lock = False
        self.shutter_a_sync_mode = 0
        self.parameters_lock = False
        self.file_size = 100
        self.fps = 24
        self.iso_steps = [100, 200]
        self.shutter_a_steps_dynamic = [180]
        self.shutter_a_steps = [180]
        self.fps_steps_dynamic = [24]
        self.fps_steps = [24]
        self.wb_steps = [5600]
        self.all_lock = False
        self.fps_double = False
        self.dynamic_resolution_enabled = True
        self.dynamic_resolution_active = False
        self.dynamic_resolution_desired_mode = 0
        self.dynamic_resolution_priority = "mode"
        self.sensor_mode = 0
        self.iso_free = False
        self.shutter_a_free = False
        self.fps_free = False
        self.wb_free = False
        self.hdr_threshold_low_free = False
        self.hdr_threshold_high_free = False
        self.hdr_blend_free = False
        self.hdr_gain_adder_free = False
        self.sync_warnings_enabled = sync_warnings_enabled


class FakeSensorDetect:
    def __init__(self, res_modes=None, camera_model=None):
        self.res_modes = res_modes if res_modes is not None else {}
        self.camera_model = camera_model


class FakeSSDMonitor:
    def __init__(self):
        self.device_name = ""
        self.space_left = 0
        self.is_mounted = False
        self.write_speed_mb_s = 0

    def get_latest_recording_info(self):
        return (None, 0, 0, -1)


def make_gui(sync_warnings_enabled=True, frames_in_sync=1):
    values = {ParameterKey.CAMERAS.value: "[]"}
    if frames_in_sync is not None:
        # Real redis-py returns strings, not ints -- populate_values() reads
        # this key as `int(get_value(...) or 1)`, and a bare int 0 is falsy
        # in Python, so a fake that stored 0 would silently collapse to the
        # "missing key" default (1) instead of exercising the off-sync path.
        # "0"/"1" match what the real client hands back.
        values[ParameterKey.FRAMES_IN_SYNC.value] = str(int(frames_in_sync))
    gui = SimpleGUI.__new__(SimpleGUI)
    gui.redis_controller = FakeGuiRedis(values)
    gui.cinepi_controller = FakeGuiController(sync_warnings_enabled=sync_warnings_enabled)
    gui.ssd_monitor = FakeSSDMonitor()
    gui.dmesg_monitor = types.SimpleNamespace(undervoltage_flag=False)
    gui.battery_monitor = types.SimpleNamespace(battery_level=None, charging=False)
    gui.sensor_detect = FakeSensorDetect(res_modes={}, camera_model=None)
    gui.redis_listener = types.SimpleNamespace(colorTemp=5600)
    gui.usb_monitor = types.SimpleNamespace(
        usb_mic=None, usb_keyboard=None, audio_monitor=None
    )
    gui.serial_handler = types.SimpleNamespace(serial_connected=False)
    gui.settings = {}
    gui._cached_cams_json = None
    gui._cached_cams = []
    gui._slow_values = {}
    gui._last_slow_refresh_ts = 0.0
    gui.slow_refresh_interval = 1.0
    gui.vu_smoothed = []
    gui.vu_peaks = []
    gui.draw_right_col = False
    gui.color_mode = "normal"
    gui.current_background_color = "black"
    gui.show_buffer_vu = True
    gui.vu_meter_hatch_lines = True
    gui._frames_off_sync_prev = False
    gui._sync_flash_until = 0.0
    gui.background_color_changed = False
    gui.disp_width = 0
    gui.disp_height = 0
    gui.fb = None
    gui._font_cache = {}
    gui.setup_resources()
    return gui


class SyncWarningDisplayGateTests(unittest.TestCase):
    def test_out_of_sync_with_warnings_enabled_shows_the_box(self):
        gui = make_gui(sync_warnings_enabled=True, frames_in_sync=0)
        values = gui.populate_values()
        self.assertFalse(values["frames_in_sync"])
        self.assertTrue(values["frames_off_sync"])

    def test_out_of_sync_with_warnings_disabled_hides_the_box(self):
        gui = make_gui(sync_warnings_enabled=False, frames_in_sync=0)
        values = gui.populate_values()
        # The raw judgement is untouched -- this is the whole point of
        # choosing option (a): the toggle must not make the recorded
        # evidence disappear, only the on-screen box.
        self.assertFalse(values["frames_in_sync"])
        self.assertFalse(values["frames_off_sync"])

    def test_in_sync_is_unaffected_by_the_toggle_either_way(self):
        for enabled in (True, False):
            with self.subTest(sync_warnings_enabled=enabled):
                gui = make_gui(sync_warnings_enabled=enabled, frames_in_sync=1)
                values = gui.populate_values()
                self.assertTrue(values["frames_in_sync"])
                self.assertFalse(values["frames_off_sync"])

    def test_default_true_when_the_controller_predates_the_attribute(self):
        # getattr(..., True) in populate_values() guards a controller built
        # without running __init__ (as several older fixtures in this test
        # suite do) -- confirm the fallback keeps today's always-on behaviour
        # rather than silently going quiet.
        gui = make_gui(sync_warnings_enabled=True, frames_in_sync=0)
        del gui.cinepi_controller.sync_warnings_enabled
        values = gui.populate_values()
        self.assertTrue(values["frames_off_sync"])

    def test_drop_box_is_not_gated_by_the_sync_toggle(self):
        # Scope check: DROP is a separate box on separate Redis keys
        # (drop_frame / drop_frame_during_last_take) -- this toggle must not
        # touch it either way.
        gui = make_gui(sync_warnings_enabled=False, frames_in_sync=0)
        gui.redis_controller.values[ParameterKey.DROP_FRAME_DURING_LAST_TAKE.value] = 1
        values = gui.populate_values()
        self.assertFalse(values["frames_off_sync"])
        self.assertTrue(values["drop_frame_latched"])


class SettingsEditorMarkupTests(unittest.TestCase):
    """The settings editor's own switch idiom (aria-checked, generic
    data-path/data-type="bool" handling) -- confirms the operator ask
    ("toggle switch") is met without inventing a new control shape."""

    @classmethod
    def setUpClass(cls):
        cls.html = (
            ROOT / "src/module/app/templates/settings_editor.html"
        ).read_text(encoding="utf-8")

    def test_the_settings_page_offers_a_toggle_switch(self):
        self.assertIn('data-path="settings.sync_warnings_enabled"', self.html)
        self.assertIn('data-type="bool"', self.html)
        self.assertIn('role="switch"', self.html)

    def test_it_defaults_on_to_match_settings_jsonc(self):
        import re

        m = re.search(
            r'data-path="settings\.sync_warnings_enabled"[^>]*',
            self.html,
        )
        self.assertIsNotNone(m)
        self.assertIn('data-original="true"', m.group(0))
        self.assertIn('aria-checked="true"', m.group(0))

    def test_gui_text_keys_exist_for_the_card(self):
        # tools/gui_text_check.py gates a template key with no markdown
        # definition (renders "[missing text: key]") -- exercise the same
        # loader here rather than trusting the markdown by inspection.
        from module.app.gui_text import load_gui_text

        text = load_gui_text(ROOT / "resources/gui-text")
        self.assertIn("card.settings.sync_warnings_enabled.label", text)
        self.assertIn("card.settings.sync_warnings_enabled.help", text)


class SchemaTests(unittest.TestCase):
    def test_the_schema_knows_the_key(self):
        import json

        schema = json.loads((ROOT / "settings.schema.json").read_text(encoding="utf-8"))
        prop = schema["properties"]["settings"]["properties"]["sync_warnings_enabled"]
        self.assertEqual(prop["type"], "boolean")
        self.assertIs(prop["default"], True)

    def test_the_schema_still_refuses_unknown_settings_keys(self):
        import json

        schema = json.loads((ROOT / "settings.schema.json").read_text(encoding="utf-8"))
        self.assertIs(schema["properties"]["settings"]["additionalProperties"], False)


if __name__ == "__main__":
    unittest.main()
