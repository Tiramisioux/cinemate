"""WP3: the Pinefeat CEF168 lens adapter reachable from every control surface.

module/lens (WP1) is tested on its own. This file tests the wiring around it:
the CinePiController methods, the five places a method has to be listed, the
parameter registry, the Grove pot, the settings and the boot helpers. Where a
test needs the lens it uses the real LensController driven by ``poll_once()``
against the WP1 fakes, so a refusal reason in an assertion is the real one.
"""
import ast
import json
import logging
import re
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lens_fakes  # noqa: E402
from lens_fakes import FakeBackend, FakeClock, FakeRedis, frame  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))
sys.modules.setdefault("gpiozero", types.SimpleNamespace(CPUTemperature=object))
for _name in ("smbus2", "grove", "grove.i2c"):
    sys.modules.setdefault(_name, types.ModuleType(_name))
sys.modules["grove.i2c"].Bus = object
sys.modules["smbus2"].SMBus = object
# The quad rotary and OLED drivers import their CircuitPython stacks at the top.
for _name in ("board", "busio", "digitalio", "adafruit_ssd1306",
              "adafruit_seesaw", "adafruit_seesaw.seesaw", "adafruit_seesaw.rotaryio",
              "adafruit_seesaw.digitalio", "adafruit_seesaw.neopixel"):
    sys.modules.setdefault(_name, types.ModuleType(_name))
sys.modules["adafruit_seesaw.seesaw"].Seesaw = object
sys.modules["adafruit_seesaw.rotaryio"].IncrementalEncoder = object
sys.modules["adafruit_seesaw.digitalio"].DigitalIO = object
sys.modules["adafruit_seesaw.neopixel"].NeoPixel = object
sys.modules["digitalio"].Pull = types.SimpleNamespace(UP=1)

import flask  # noqa: E402

from module.analog_controls import AnalogControls  # noqa: E402
from module.app.settings_editor import ACTION_METHODS, LENS_ACTION_GROUP, settings_editor_bp  # noqa: E402
from module.cinepi_controller import CinePiController  # noqa: E402
from module.cli_commands import CommandExecutor  # noqa: E402
from module.config_loader import _apply_settings_defaults, load_settings, strip_jsonc  # noqa: E402
from module.lens import controller as lens_controller_module  # noqa: E402
from module.lens import startup  # noqa: E402
from module.lens.controller import LensController  # noqa: E402
from module.lens.database import IRIS_STEPS, LensDatabase, iris_steps_for  # noqa: E402

LENS_COMMANDS = {
    "set iris": "set_iris", "inc iris": "inc_iris", "dec iris": "dec_iris",
    "set focus": "set_focus", "inc focus": "inc_focus", "dec focus": "dec_focus",
    "set lens control": "set_lens_control", "calibrate lens": "calibrate_lens",
    "set lens": "set_lens", "save lens": "save_lens",
    "set lens aperture": "set_lens_aperture_range",
}
LENS_METHODS = tuple(LENS_COMMANDS.values())
# What a button can carry; save_lens and set_lens_aperture_range need typed text.
LENS_BUTTON_METHODS = (
    "set_iris", "inc_iris", "dec_iris", "set_focus", "inc_focus", "dec_focus",
    "set_lens_control", "calibrate_lens", "set_lens",
)

ENTRY = {
    "name": "Sigma 18-35 f/1.8", "lens_id": 235,
    "aperture": {"min": 1.8, "max": 16.0, "source": "manual"}, "last_iris": None,
    "focus": {"calibrated_at": "2026-10-04T12:00:00Z", "position_min": 0, "position_max": 1069,
              "mfd_m": 0.28, "distance_encoder": False, "map": [0.0, 1037, 3.57, 0],
              "dioptre_min": 0.0, "dioptre_max": 3.57, "step_frames": 4},
}


class Rig(unittest.TestCase):
    """A CinePiController (built with __new__: only the lens methods run) with a
    real LensController behind it, fed by a scripted adapter."""

    DETECT = True
    SAVED = True

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = LensDatabase(Path(tmp.name) / "lenses.json",
                               now=lambda: datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc))
        if self.SAVED:
            self.key = self.db.add(dict(ENTRY))
        self.clock = FakeClock()
        self.redis = FakeRedis({"lens_control": "1"})
        self.backend = FakeBackend(frame(lens_id=235))
        self.result = (self.backend, "") if self.DETECT else (None, "no adapter")
        self.lens = LensController(
            self.redis, database=self.db, backend_factory=lambda port, cameras: self.result,
            clock=self.clock, sleep=self.clock.sleep)
        self.controller = CinePiController.__new__(CinePiController)
        self.controller.attach_lens_controller(self.lens)
        self.poll(2)

    def poll(self, count=1):
        for _ in range(count):
            self.lens.poll_once()
            self.clock.advance(0.25)

    def value(self, key):
        return self.redis.cache.get(key)

    def logged(self):
        return self.assertLogs(level="INFO")


class IrisTests(Rig):
    def test_set_iris_commands_the_lens_and_publishes_the_commanded_value(self):
        self.assertTrue(self.controller.set_iris(2.8))
        self.assertEqual(self.backend.iris_calls[-1], 2.8)
        self.assertEqual(self.value("iris"), "2.8")

    def test_set_iris_is_clamped_to_the_entrys_aperture_range(self):
        self.assertTrue(self.controller.set_iris(32))
        self.assertEqual(self.backend.iris_calls[-1], 16.0)

    def test_set_iris_takes_a_string_from_a_hardware_action(self):
        self.assertTrue(self.controller.set_iris("5.6"))
        self.assertEqual(self.backend.iris_calls[-1], 5.6)

    def test_inc_and_dec_step_a_third_stop(self):
        self.controller.set_iris(2.8)
        self.assertTrue(self.controller.inc_iris())
        self.assertEqual(self.backend.iris_calls[-1], 3.2)
        self.assertTrue(self.controller.dec_iris())
        self.assertTrue(self.controller.dec_iris())
        self.assertEqual(self.backend.iris_calls[-1], 2.5)

    def test_inc_stops_at_the_narrow_end_unless_wrapping(self):
        self.controller.set_iris(16)
        self.controller.inc_iris()
        self.assertEqual(self.backend.iris_calls[-1], 16.0)
        self.controller.inc_iris(wrap=True)
        self.assertEqual(self.backend.iris_calls[-1], 1.8)

    def test_dec_wraps_from_the_wide_end_to_the_narrow_end(self):
        self.controller.set_iris(1.8)
        self.controller.dec_iris()
        self.assertEqual(self.backend.iris_calls[-1], 1.8)
        self.controller.dec_iris(wrap=True)
        self.assertEqual(self.backend.iris_calls[-1], 16.0)

    def test_wrap_with_nothing_commanded_yet_just_steps(self):
        self.assertTrue(self.controller.inc_iris(wrap=True))

    def test_iris_steps_follow_the_selected_lens_live(self):
        self.assertEqual(self.controller.iris_steps(), iris_steps_for(ENTRY))
        self.lens.set_aperture_range(2.8, 8)
        self.assertEqual(self.controller.iris_steps()[0], 2.8)
        self.assertEqual(self.controller.iris_steps()[-1], 8.0)

    def test_with_lens_control_off_nothing_is_written_and_the_reason_is_logged(self):
        self.redis.set_value("lens_control", "0")
        self.poll()
        before = len(self.backend.iris_calls)
        with self.logged() as logs:
            self.assertFalse(self.controller.set_iris(2.8))
            self.assertFalse(self.controller.inc_iris())
        self.assertEqual(len(self.backend.iris_calls), before)
        self.assertTrue(any("Lens control is off" in line for line in logs.output), logs.output)

    def test_a_lens_whose_entry_says_iris_does_nothing_is_not_commanded(self):
        self.db.update(self.key, capabilities={"iris": False, "focus": None, "autofocus": None})
        self.lens.select_lens(self.key)
        before = len(self.backend.iris_calls)
        with self.logged() as logs:
            self.assertFalse(self.controller.set_iris(2.8))
        self.assertEqual(len(self.backend.iris_calls), before)
        self.assertTrue(any("iris is not available" in line for line in logs.output))

    def test_a_lens_with_iris_untested_is_commanded(self):
        # null = untested, not "unsupported": the first command is how it gets tested.
        self.assertIsNone(self.lens.working_entry()["capabilities"]["iris"])
        self.assertTrue(self.controller.set_iris(4))

    def test_iris_works_for_a_lens_with_no_focus_feedback(self):
        self.db.update(self.key, capabilities={"iris": None, "focus": False, "autofocus": None})
        self.lens.select_lens(self.key)
        self.assertTrue(self.controller.set_iris(4))
        with self.logged():
            self.assertFalse(self.controller.inc_focus())


class NoAdapterTests(Rig):
    DETECT = False

    def test_every_lens_method_refuses_without_raising(self):
        calls = {
            "set_iris": (2.8,), "inc_iris": (), "dec_iris": (), "set_focus": (500,),
            "inc_focus": (), "dec_focus": (), "calibrate_lens": (), "set_lens": (),
            "save_lens": ("x",), "set_lens_aperture_range": (1.8, 22),
        }
        for name, args in calls.items():
            with self.subTest(method=name), self.logged():
                self.assertFalse(getattr(self.controller, name)(*args))

    def test_the_toggle_cannot_be_switched_on_and_says_why(self):
        self.redis.cache.pop("lens_control")
        with self.logged() as logs:
            self.assertFalse(self.controller.set_lens_control(1))
        self.assertTrue(any("not found" in line for line in logs.output), logs.output)
        self.assertNotIn("lens_control", self.redis.cache)

    def test_toggling_with_no_value_cannot_switch_it_on_either(self):
        self.redis.cache.pop("lens_control")
        self.poll()
        with self.logged():
            self.assertFalse(self.controller.set_lens_control())
        self.assertNotIn("lens_control", self.redis.cache)

    def test_switching_off_always_works(self):
        with self.logged():
            self.assertTrue(self.controller.set_lens_control(0))
        self.assertEqual(self.value("lens_control"), "0")

    def test_the_default_iris_table_is_the_full_one(self):
        self.assertEqual(self.controller.iris_steps(), list(IRIS_STEPS))


class FocusTests(Rig):
    def test_set_focus_moves_the_motor(self):
        self.assertTrue(self.controller.set_focus(700))
        self.assertEqual(self.backend.focus_calls[-1], 700)

    def test_inc_and_dec_move_one_percent_of_the_range(self):
        self.assertTrue(self.controller.inc_focus())
        self.assertEqual(self.backend.focus_calls[-1], 511)      # 500 + 1 % of 1069, rounded
        self.assertTrue(self.controller.dec_focus())

    def test_wrap_is_accepted_and_ignored(self):
        self.backend.data = frame(lens_id=235, focus_position_cur=1069)
        self.poll()
        self.assertTrue(self.controller.inc_focus(wrap=True))
        self.assertEqual(self.backend.focus_calls[-1], 1069)     # clamped, did not wrap to 0

    def test_focus_with_lens_control_off_is_a_logged_no_op(self):
        self.redis.set_value("lens_control", "0")
        self.poll()
        with self.logged() as logs:
            self.assertFalse(self.controller.set_focus(700))
        self.assertEqual(self.backend.focus_calls, [])
        self.assertTrue(any("Lens control is off" in line for line in logs.output))

    def test_focus_range_is_the_boards_range(self):
        self.assertEqual(self.controller.focus_range(), [0, 1069])


class ToggleTests(Rig):
    def test_no_value_toggles(self):
        self.assertTrue(self.controller.set_lens_control())
        self.assertEqual(self.value("lens_control"), "0")
        self.assertTrue(self.controller.set_lens_control())
        self.assertEqual(self.value("lens_control"), "1")

    def test_explicit_values(self):
        for value, expected in ((0, "0"), ("1", "1"), (False, "0"), ("on", "1"), ("off", "0")):
            with self.subTest(value=value):
                self.assertTrue(self.controller.set_lens_control(value))
                self.assertEqual(self.value("lens_control"), expected)

    def test_a_value_that_is_neither_is_refused(self):
        with self.logged() as logs:
            self.assertFalse(self.controller.set_lens_control("maybe"))
        self.assertTrue(any("0 or 1" in line for line in logs.output))
        self.assertEqual(self.value("lens_control"), "1")


class CalibrationAndDatabaseTests(Rig):
    def test_calibrate_starts_a_sweep(self):
        self.backend.sweep = lens_fakes.encoder_sweep()
        self.assertTrue(self.controller.calibrate_lens())
        self.assertEqual(self.value("lens_state"), "calibrating")

    def test_calibrate_is_refused_while_recording(self):
        self.redis.set_value("rec", "1")
        with self.logged() as logs:
            self.assertFalse(self.controller.calibrate_lens())
        self.assertTrue(any("recording" in line for line in logs.output))
        self.assertEqual(self.backend.calibrate_calls, 0)

    def test_set_lens_cycles_the_entries_for_the_mounted_lens(self):
        second = self.db.add({**ENTRY, "name": "Sigma twin"})
        self.poll()
        first = self.value("lens_key")
        self.assertTrue(self.controller.set_lens())
        self.assertNotEqual(self.value("lens_key"), first)
        self.assertTrue(self.controller.set_lens())
        self.assertEqual(self.value("lens_key"), first)
        self.assertTrue(self.controller.set_lens(second))
        self.assertEqual(self.value("lens_key"), second)

    def test_set_lens_with_an_unknown_key_says_so(self):
        with self.logged() as logs:
            self.assertFalse(self.controller.set_lens("nope"))
        self.assertTrue(any("No saved lens" in line for line in logs.output))

    def test_set_aperture_range_with_two_numbers(self):
        self.assertTrue(self.controller.set_lens_aperture_range(2.0, 11))
        self.assertEqual(self.value("lens_aperture_range"), "2-11")
        self.assertTrue(self.lens.working_entry()["dirty"])

    def test_set_aperture_range_from_the_clis_one_string(self):
        for text in ("1.4-16", "1.4 16", "f/1.4 f/16", "1.4,16"):
            with self.subTest(text=text):
                self.assertTrue(self.controller.set_lens_aperture_range(text))
                self.assertEqual(self.value("lens_aperture_range"), "1.4-16")

    def test_set_aperture_range_clear(self):
        for args in (("clear",), ()):
            with self.subTest(args=args):
                self.controller.set_lens_aperture_range(2, 8)
                self.assertTrue(self.controller.set_lens_aperture_range(*args))
                self.assertEqual(self.value("lens_aperture_range"), "")

    def test_set_aperture_range_rejects_what_it_cannot_read(self):
        with self.logged():
            self.assertFalse(self.controller.set_lens_aperture_range("wide open"))
            self.assertFalse(self.controller.set_lens_aperture_range("1.8"))
            self.assertFalse(self.controller.set_lens_aperture_range(22, 1.8))

    def test_save_lens_as_new_with_a_name(self):
        self.controller.set_lens_aperture_range(2, 8)
        self.assertTrue(self.controller.save_lens("Sigma, stopped down"))
        keys = [k for k, e in self.db.entries().items() if e["name"] == "Sigma, stopped down"]
        self.assertEqual(len(keys), 1)
        self.assertEqual(self.db.get(keys[0])["aperture"]["max"], 8.0)

    def test_save_lens_with_no_name_saves_over_the_selected_entry(self):
        self.controller.set_lens_aperture_range(2, 8)
        self.assertTrue(self.controller.save_lens())
        self.assertEqual(len(self.db.entries()), 1)
        self.assertEqual(self.db.get(self.key)["aperture"]["max"], 8.0)
        self.assertFalse(self.lens.working_entry()["dirty"])

    def test_save_lens_over_a_named_key(self):
        other = self.db.add({**ENTRY, "name": "Other"})
        self.assertTrue(self.controller.save_lens("Renamed", other))
        self.assertEqual(self.db.get(other)["name"], "Renamed")


class UnknownLensTests(Rig):
    SAVED = False

    def test_save_with_no_name_needs_a_name_for_a_lens_with_no_entry(self):
        with self.logged() as logs:
            self.assertFalse(self.controller.save_lens())
        self.assertTrue(any("give it a name" in line for line in logs.output))
        self.assertEqual(self.db.entries(), {})

    def test_save_as_new_adds_it(self):
        self.assertTrue(self.controller.save_lens("Brand new"))
        self.assertEqual([e["name"] for e in self.db.entries().values()], ["Brand new"])


class NoLensControllerTests(unittest.TestCase):
    """Nothing attached (a build without the lens thread, or a test rig): every
    method says so and the registry's callables still answer."""

    def setUp(self):
        self.controller = CinePiController.__new__(CinePiController)

    def test_methods_decline_and_log(self):
        needs_a_value = {"set_iris": (2.8,), "set_focus": (500,)}
        for name in LENS_METHODS:
            with self.subTest(method=name), self.assertLogs(level="INFO") as logs:
                self.assertFalse(getattr(self.controller, name)(*needs_a_value.get(name, ())))
            self.assertTrue(any("not available" in line for line in logs.output))

    def test_the_registry_callables_still_answer(self):
        self.assertEqual(self.controller.iris_steps(), list(IRIS_STEPS))
        self.assertEqual(self.controller.focus_range(), [0, 65535])

    def test_attach_makes_them_live(self):
        sentinel = mock.Mock()
        sentinel.set_iris.return_value = (True, "f/2.8")
        self.controller.attach_lens_controller(sentinel)
        self.assertTrue(self.controller.set_iris(2.8))
        sentinel.set_iris.assert_called_once_with(2.8)


class ParameterRegistryTests(Rig):
    """The quad rotary, GPIO encoders, OLED and increment_setting reach the lens
    by registry name."""

    def test_increment_setting_by_name_steps_the_lens(self):
        self.controller.set_iris(2.8)
        self.controller.increment_setting("iris", [])
        self.assertEqual(self.backend.iris_calls[-1], 3.2)
        self.controller.decrement_setting("iris", [])
        self.assertEqual(self.backend.iris_calls[-1], 2.8)

    def test_increment_with_no_iris_commanded_yet_does_not_raise(self):
        # Redis `iris` is "" here: the generic path would float("") it.
        self.assertEqual(self.value("iris"), None)
        self.controller.increment_setting("iris", [])
        self.assertEqual(len(self.backend.iris_calls), 1)

    def test_increment_setting_wrap_reaches_inc_iris(self):
        self.controller.set_iris(16)
        self.controller.increment_setting("iris", [], wrap=True)
        self.assertEqual(self.backend.iris_calls[-1], 1.8)

    def test_increment_setting_by_name_steps_focus(self):
        self.controller.increment_setting("focus", [])
        self.assertEqual(self.backend.focus_calls[-1], 511)
        self.controller.decrement_setting("focus", [])
        self.assertEqual(len(self.backend.focus_calls), 2)

    def test_get_setting_reads_the_registered_redis_keys(self):
        self.controller.redis_controller = self.redis
        self.controller.set_iris(4)
        self.assertEqual(self.controller.get_setting("iris"), "4.0")
        self.assertEqual(self.controller.get_setting("focus"), "500")

    def test_the_quad_rotary_and_gpio_dispatchers_find_inc_and_dec(self):
        for name in ("iris", "focus"):
            for prefix in ("inc_", "dec_"):
                self.assertTrue(callable(getattr(self.controller, prefix + name)))
        # Both dispatchers forward `wrap` only to a method that declares it.
        import inspect
        self.assertIn("wrap", inspect.signature(self.controller.inc_iris).parameters)

    def test_quad_rotary_resolves_the_setting_names_without_a_warning(self):
        from module.i2c.quad_rotary_controller import QuadRotaryController
        settings = {"input_peripherals": {"quad_rotary_controller": {
            "enabled": True, "encoders": {"0": {"setting_name": "iris"},
                                          "1": {"setting_name": "focus"}}}}}
        with self.assertNoLogs("module.parameters", level="WARNING"):
            QuadRotaryController(self.controller, settings)

    def test_a_quad_rotary_turn_calls_inc_iris(self):
        from module.i2c.quad_rotary_controller import QuadRotaryController
        quad = QuadRotaryController.__new__(QuadRotaryController)
        quad.cinepi_controller = self.controller
        self.controller.set_iris(2.8)
        quad._update_setting("iris", 1)
        self.assertEqual(self.backend.iris_calls[-1], 3.2)
        quad._update_setting("iris", -1)
        self.assertEqual(self.backend.iris_calls[-1], 2.8)
        quad._update_setting("focus", 1)
        self.assertEqual(self.backend.focus_calls[-1], 511)


class OledTests(unittest.TestCase):
    """OLED `values` rows are Redis key names: `iris` prints as it is, `focus`
    is read from the motor-position readback."""

    def screen_for(self, values, redis_values):
        from module.i2c.i2c_oled import I2cOled
        oled = I2cOled.__new__(I2cOled)
        oled.connected, oled.values = True, values
        oled.redis_controller = FakeRedis(redis_values)
        oled._last_reconnect = 0
        shown = []
        oled.display_text = shown.append
        oled.update()
        return shown[-1]

    def test_the_iris_row_prints_the_commanded_f_number(self):
        self.assertEqual(self.screen_for(["iris"], {"iris": "2.8"}), "IRIS: 2.8")

    def test_the_focus_row_reads_the_motor_position_readback(self):
        self.assertEqual(self.screen_for(["focus"], {"focus_position": "512"}), "FOCUS: 512")

    def test_a_row_that_is_not_aliased_still_reads_its_own_key(self):
        self.assertEqual(self.screen_for(["focus_position"], {"focus_position": "512"}),
                         "FOCUS_POSITION: 512")
        self.assertEqual(self.screen_for(["iso"], {"iso": "800"}), "ISO: 800")


class CommandLineTests(Rig):
    """The CLI table, end to end through the real CommandExecutor."""

    def setUp(self):
        super().setUp()
        self.controller.ssd_monitor = mock.MagicMock()
        self.controller.redis_controller = self.redis
        self.executor = CommandExecutor(self.controller, mock.MagicMock())

    def run_command(self, text):
        return self.executor.handle_received_data(text)

    def test_every_lens_command_is_in_the_table_and_bound_to_its_method(self):
        for command, method in LENS_COMMANDS.items():
            with self.subTest(command=command):
                self.assertIn(command, self.executor.commands)
                self.assertEqual(self.executor.commands[command][0].__name__, method)

    def test_set_iris(self):
        self.assertEqual(self.run_command("set iris 2.8"), (True, ""))
        self.assertEqual(self.backend.iris_calls[-1], 2.8)

    def test_set_iris_reports_the_clamped_value_it_actually_set(self):
        ok, message = self.run_command("set iris 32")
        self.assertTrue(ok)
        self.assertIn("live value is 16.0", message)

    def test_set_iris_with_lens_control_off_says_the_live_value_differs(self):
        self.redis.set_value("lens_control", "0")
        self.poll()
        ok, message = self.run_command("set iris 4")
        self.assertTrue(ok)
        self.assertEqual(self.backend.iris_calls, [])
        self.assertIn("requested 4.0", message)

    def test_inc_and_dec_iris(self):
        self.run_command("set iris 4")
        self.run_command("inc iris")
        self.assertEqual(self.backend.iris_calls[-1], 4.5)
        self.run_command("dec iris")
        self.assertEqual(self.backend.iris_calls[-1], 4.0)

    def test_set_iris_needs_a_number(self):
        self.assertEqual(self.run_command("set iris"), (False, "missing argument"))
        self.assertEqual(self.run_command("set iris wide"), (False, "bad argument"))

    def test_set_focus_is_not_compared_with_the_trailing_readback(self):
        with self.assertNoLogs(level="WARNING"):
            self.assertEqual(self.run_command("set focus 700"), (True, ""))
        self.assertEqual(self.backend.focus_calls[-1], 700)

    def test_inc_and_dec_focus(self):
        self.assertEqual(self.run_command("inc focus"), (True, ""))
        self.assertEqual(self.backend.focus_calls[-1], 511)
        self.run_command("dec focus")
        self.assertEqual(len(self.backend.focus_calls), 2)

    def test_set_lens_control_toggles_and_sets(self):
        self.run_command("set lens control")
        self.assertEqual(self.value("lens_control"), "0")
        self.run_command("set lens control 1")
        self.assertEqual(self.value("lens_control"), "1")
        self.run_command("set lens control 0")
        self.assertEqual(self.value("lens_control"), "0")

    def test_the_longer_lens_commands_are_not_read_as_set_lens(self):
        with mock.patch.object(self.controller, "set_lens") as set_lens:
            self.run_command("set lens control 1")
            self.run_command("set lens aperture 1.8 22")
            set_lens.assert_not_called()

    def test_set_lens_with_a_key_and_without(self):
        second = self.db.add({**ENTRY, "name": "Twin"})
        self.poll()
        self.run_command(f"set lens {second}")
        self.assertEqual(self.value("lens_key"), second)
        self.run_command("set lens")
        self.assertEqual(self.value("lens_key"), self.key)

    def test_calibrate_lens(self):
        self.backend.sweep = lens_fakes.encoder_sweep()
        self.assertEqual(self.run_command("calibrate lens"), (True, ""))
        self.assertEqual(self.value("lens_state"), "calibrating")

    def test_calibrate_lens_with_a_minimum_focus_distance(self):
        with mock.patch.object(self.controller, "calibrate_lens") as calibrate:
            self.executor.commands["calibrate lens"] = (calibrate, [float, None])
            self.run_command("calibrate lens 0.45")
            calibrate.assert_called_once_with(0.45)

    def test_save_lens_takes_the_rest_of_the_line_as_the_name(self):
        self.assertEqual(self.run_command("save lens Sigma 18-35 f/1.8 night"), (True, ""))
        self.assertIn("Sigma 18-35 f/1.8 night",
                      [e["name"] for e in self.db.entries().values()])

    def test_save_lens_with_no_name_saves_over_the_selected_one(self):
        self.run_command("set lens aperture 2 8")
        self.assertEqual(self.run_command("save lens"), (True, ""))
        self.assertEqual(self.db.get(self.key)["aperture"]["max"], 8.0)

    def test_set_lens_aperture(self):
        self.assertEqual(self.run_command("set lens aperture 1.4 16"), (True, ""))
        self.assertEqual(self.value("lens_aperture_range"), "1.4-16")
        self.run_command("set lens aperture clear")
        self.assertEqual(self.value("lens_aperture_range"), "")

    def test_other_commands_still_take_one_word(self):
        self.assertEqual(self.run_command("set iris 4 5"), (True, ""))
        self.assertEqual(self.backend.iris_calls[-1], 4.0)


class ActionCatalogueTests(unittest.TestCase):
    def test_the_lens_group_is_named_the_same_in_both_copies(self):
        html = (ROOT / "src/module/app/templates/settings_editor.html").read_text(encoding="utf-8")
        self.assertEqual(LENS_ACTION_GROUP, "Lens (Pinefeat)")
        self.assertIn("group: 'Lens (Pinefeat)'", html)

    def test_every_button_method_is_offered_in_both_copies_under_the_lens_group(self):
        python = {e["value"]: e for e in ACTION_METHODS if e["group"] == LENS_ACTION_GROUP}
        self.assertEqual(set(python), set(LENS_BUTTON_METHODS))
        html = (ROOT / "src/module/app/templates/settings_editor.html").read_text(encoding="utf-8")
        block = re.search(r"var ACTION_METHODS = \[(.*?)\n  \];", html, re.S).group(1)
        js = {value: group for group, value
              in re.findall(r"group: '([^']+)', value: '([a-z_]+)'", block)}
        for method in LENS_BUTTON_METHODS:
            self.assertEqual(js[method], LENS_ACTION_GROUP, method)

    def test_no_arg_kinds_say_what_a_blank_does(self):
        by_name = {e["value"]: e for e in ACTION_METHODS if e["group"] == LENS_ACTION_GROUP}
        self.assertEqual(by_name["set_iris"]["no_arg"], "required")
        self.assertEqual(by_name["set_focus"]["no_arg"], "required")
        self.assertEqual(by_name["set_lens_control"]["no_arg"], "toggle")
        self.assertEqual(by_name["set_lens"]["no_arg"], "cycle")
        for stepper in ("inc_iris", "dec_iris", "inc_focus", "dec_focus", "calibrate_lens"):
            self.assertNotIn("arg", by_name[stepper])

    def test_the_iris_options_are_the_database_table(self):
        options = next(e for e in ACTION_METHODS if e["value"] == "set_iris")["arg"]["options"]
        self.assertEqual([float(o) for o in options], [float(s) for s in IRIS_STEPS])
        html = (ROOT / "src/module/app/templates/settings_editor.html").read_text(encoding="utf-8")
        js = re.search(r"value: 'set_iris'.*?options: \[([^\]]*)\]", html).group(1)
        self.assertEqual([float(o) for o in js.split(",")], [float(s) for s in IRIS_STEPS])

    def test_save_lens_and_the_aperture_range_are_cli_only(self):
        offered = {e["value"] for e in ACTION_METHODS}
        self.assertNotIn("save_lens", offered)
        self.assertNotIn("set_lens_aperture_range", offered)


class ActionsEndpointTests(unittest.TestCase):
    def make_app(self, lens):
        app = flask.Flask(__name__)
        app.register_blueprint(settings_editor_bp)
        app.config["LENS_CONTROLLER"] = lens
        return app

    def actions(self, lens):
        body = self.make_app(lens).test_client().get("/settings-editor/api/actions").get_json()
        return {a["value"]: a for a in body["actions"]}

    def test_lens_actions_are_greyed_with_the_reason_while_lens_control_is_not_effective(self):
        lens = mock.Mock()
        lens.status.return_value = {"effective": False, "message": "Lens control is off"}
        actions = self.actions(lens)
        for method in LENS_BUTTON_METHODS:
            self.assertTrue(actions[method]["greyed"], method)
            self.assertEqual(actions[method]["grey_reason"], "Lens control is off")
        self.assertNotIn("greyed", actions["set_iso"])

    def test_they_stay_listed_and_are_not_greyed_when_effective(self):
        lens = mock.Mock()
        lens.status.return_value = {"effective": True, "message": "ready"}
        actions = self.actions(lens)
        for method in LENS_BUTTON_METHODS:
            self.assertIn(method, actions)
            self.assertNotIn("greyed", actions[method])

    def test_no_lens_controller_at_all_greys_them(self):
        actions = self.actions(None)
        self.assertEqual(actions["set_iris"]["grey_reason"], "Lens control is not available")

    def test_a_broken_status_greys_instead_of_failing_the_endpoint(self):
        lens = mock.Mock()
        lens.status.side_effect = RuntimeError("boom")
        self.assertTrue(self.actions(lens)["inc_focus"]["greyed"])

    def test_the_methods_exist_on_the_controller(self):
        tree = ast.parse((ROOT / "src/module/cinepi_controller.py").read_text(encoding="utf-8"))
        cls = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.ClassDef) and n.name == "CinePiController")
        defined = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
        self.assertLessEqual(set(LENS_METHODS), defined)


class AnalogPotTests(unittest.TestCase):
    """Grove ADC `iris_pot`, exactly like the other pots."""

    def make(self, readings, steps=(1.8, 2.8, 4.0, 5.6, 8.0, 11.0)):
        pot = AnalogControls.__new__(AnalogControls)
        pot.cinepi_controller = mock.Mock()
        pot.cinepi_controller.iris_steps.return_value = list(steps)
        pot.dispatch_lock = None
        pot._last_dispatch_raw = {}
        for name in ("iso", "shutter_a", "fps", "wb", "hdr_threshold_low", "hdr_threshold_high",
                     "hdr_blend", "hdr_gain_adder"):
            setattr(pot, f"{name}_pot", None)
        pot.iris_pot = 3
        from collections import deque
        pot.iris_buffer = deque(maxlen=5)
        pot.last_iris = None
        pot.adc = mock.Mock()
        pot.adc.read.side_effect = list(readings)
        return pot

    def test_the_pot_dispatches_set_iris_with_the_lens_table(self):
        pot = self.make([700] * 5)
        for _ in range(5):
            pot.update_parameters()
        pot.cinepi_controller.set_iris.assert_called_once_with(8.0)

    def test_it_follows_the_selected_lens_table_live(self):
        pot = self.make([0] * 5, steps=(2.8, 5.6))
        pot.update_parameters()
        pot.cinepi_controller.set_iris.assert_called_once_with(2.8)
        pot.cinepi_controller.iris_steps.assert_called()

    def test_a_pot_at_rest_does_not_redispatch(self):
        pot = self.make([700] * 8)
        for _ in range(8):
            pot.update_parameters()
        self.assertEqual(pot.cinepi_controller.set_iris.call_count, 1)

    def test_F285_noise_below_the_movement_threshold_does_not_clobber_a_command(self):
        pot = self.make([700, 700, 700, 701, 700, 699, 700])
        for _ in range(7):
            pot.update_parameters()
        self.assertEqual(pot.cinepi_controller.set_iris.call_count, 1)

    def test_a_real_swing_dispatches_again(self):
        pot = self.make([100] * 5 + [900] * 5)
        for _ in range(10):
            pot.update_parameters()
        values = [c.args[0] for c in pot.cinepi_controller.set_iris.call_args_list]
        self.assertEqual(values[0], 1.8)
        self.assertEqual(values[-1], 11.0)

    def test_dispatch_takes_the_command_executors_lock(self):
        pot = self.make([700])
        lock = mock.MagicMock()
        pot.dispatch_lock = lock
        pot._dispatch("iris", 4.0)
        lock.__enter__.assert_called_once()
        pot.cinepi_controller.set_iris.assert_called_once_with(4.0)

    def test_no_pot_wired_means_the_adc_is_never_read_for_iris(self):
        pot = self.make([])
        pot.iris_pot = None
        pot.update_parameters()
        pot.adc.read.assert_not_called()

    def test_the_constructor_takes_iris_pot_and_main_wires_it(self):
        import inspect
        self.assertIn("iris_pot", inspect.signature(AnalogControls.__init__).parameters)
        main_source = (ROOT / "src/main.py").read_text(encoding="utf-8")
        self.assertIn('iris_pot=pot_channel_by_setting.get("iris", "None")', main_source)


class SettingsTests(unittest.TestCase):
    def shipped(self, name):
        return json.loads(strip_jsonc((ROOT / name).read_text(encoding="utf-8")))

    def test_the_block_and_its_defaults_agree_everywhere(self):
        loader = _apply_settings_defaults({})["lens_control"]
        schema = json.loads((ROOT / "settings.schema.json").read_text(encoding="utf-8"))
        props = schema["properties"]["lens_control"]["properties"]
        for name in ("settings.jsonc", "resources/settings/settings_default.jsonc"):
            with self.subTest(name):
                self.assertEqual(self.shipped(name)["lens_control"], loader)
        self.assertEqual({k: v["default"] for k, v in props.items()}, loader)

    def test_defaults_match_the_lens_modules_own_constants(self):
        from module.lens.database import DEFAULT_LENS_DATABASE_FILE
        loader = _apply_settings_defaults({})["lens_control"]
        self.assertEqual(loader["database_file"], DEFAULT_LENS_DATABASE_FILE)
        self.assertEqual(loader["poll_hz"], lens_controller_module.DEFAULT_POLL_HZ)
        self.assertEqual(loader["poll_hz"], startup.DEFAULT_POLL_HZ)

    def test_autofocus_ships_off_and_self_test_calibration_ships_on(self):
        block = self.shipped("settings.jsonc")["lens_control"]
        self.assertIs(block["autofocus"], False)
        self.assertIs(block["calibrate_on_selftest"], True)

    def test_a_partial_block_is_filled_in(self):
        out = _apply_settings_defaults({"lens_control": {"poll_hz": 8}})["lens_control"]
        self.assertEqual(out["poll_hz"], 8)
        self.assertIs(out["calibrate_on_selftest"], True)

    def test_an_absent_block_is_not_an_error(self):
        self.assertEqual(load_settings(str(ROOT / "settings.jsonc"))["lens_control"]["poll_hz"], 4)

    def test_the_block_is_commented_in_the_house_style(self):
        text = (ROOT / "settings.jsonc").read_text(encoding="utf-8")
        block = text[text.index('"lens_control"'):text.index("// ── settings:")]
        self.assertGreaterEqual(block.count("//"), 8)
        self.assertIn("PAUSED", block)

    def test_the_iris_pot_ships_unassigned_in_the_live_settings(self):
        pots = self.shipped("settings.jsonc")["input_peripherals"]["pots"]
        self.assertIn({"channel": "None", "setting": "iris"}, pots)

    def test_the_installer_seeds_the_two_lens_keys(self):
        script = (ROOT / "cinemate-install.sh").read_text(encoding="utf-8")
        seed = script[script.index("seed_redis_defaults() {"):]
        seed = seed[:seed.index("\n}\n")]
        self.assertIn('lens_control 0 iris ""', seed)
        self.assertNotIn("af_mode", seed)       # would switch off stock Camera Module 3 AF


@unittest.skipIf(__import__("importlib").util.find_spec("jsonschema") is None,
                 "jsonschema not installed")
class SchemaTests(unittest.TestCase):
    def setUp(self):
        import jsonschema
        self.schema = json.loads((ROOT / "settings.schema.json").read_text(encoding="utf-8"))
        self.validator = jsonschema.Draft7Validator(self.schema)
        self.doc = json.loads(strip_jsonc((ROOT / "settings.jsonc").read_text(encoding="utf-8")))

    def errors(self):
        return list(self.validator.iter_errors(self.doc))

    def test_the_shipped_block_validates(self):
        self.assertEqual(self.errors(), [])

    def test_an_unknown_key_in_the_block_is_rejected(self):
        self.doc["lens_control"]["poll_hertz"] = 4
        self.assertTrue(self.errors())

    def test_poll_hz_must_be_a_sane_number(self):
        for bad in ("fast", 0, 100):
            with self.subTest(bad=bad):
                self.doc["lens_control"]["poll_hz"] = bad
                self.assertTrue(self.errors())

    def test_the_flags_must_be_booleans(self):
        self.doc["lens_control"]["calibrate_on_selftest"] = "yes"
        self.assertTrue(self.errors())


class StartupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.redis = FakeRedis()
        self.started = []
        self.addCleanup(self.stop_threads)

    def stop_threads(self):
        for controller in self.started:
            controller.stop()
            controller.join(timeout=2)

    def start(self, block=None, factory=None, **kwargs):
        settings = {"lens_control": {"database_file": str(self.tmp / "lenses.json"),
                                     **(block or {})}}
        controller, database = startup.start_lens_controller(
            settings, self.redis,
            backend_factory=factory or (lambda port, cameras: (None, "no adapter")), **kwargs)
        self.started.append(controller)
        return controller, database

    def test_seeds_only_what_is_absent(self):
        startup.seed_lens_defaults(self.redis)
        self.assertEqual(self.redis.cache, {"lens_control": "0", "iris": ""})

    def test_a_warm_redis_keeps_the_toggle_and_the_last_iris(self):
        warm = FakeRedis({"lens_control": "1", "iris": "5.6"})
        startup.seed_lens_defaults(warm)
        self.assertEqual(warm.writes, [])
        self.assertEqual(warm.cache, {"lens_control": "1", "iris": "5.6"})

    def test_af_mode_is_never_seeded(self):
        startup.seed_lens_defaults(self.redis)
        self.assertNotIn("af_mode", self.redis.cache)

    def test_the_first_probe_has_run_before_start_returns(self):
        # cinepi_multi reads lens_detected while building its launch arguments.
        calls = []
        controller, _ = self.start(factory=lambda port, cameras: calls.append(1) or (None, "none"))
        self.assertTrue(calls)
        self.assertEqual(self.redis.cache["lens_detected"], "0")
        self.assertEqual(self.redis.cache["lens_state"], "absent")
        self.assertTrue(controller.is_alive())

    def test_an_adapter_that_is_there_is_published_before_start_returns(self):
        backend = FakeBackend(frame(lens_id=235))
        self.start(factory=lambda port, cameras: (backend, ""))
        self.assertEqual(self.redis.cache["lens_detected"], "1")
        self.assertEqual(self.redis.cache["lens_id"], "235")

    def test_the_database_path_comes_from_the_setting(self):
        _, database = self.start()
        self.assertEqual(database.path, self.tmp / "lenses.json")

    def test_poll_rate_comes_from_the_setting_and_a_bad_one_falls_back(self):
        controller, _ = self.start({"poll_hz": 8})
        self.assertEqual(controller._poll_hz, 8.0)
        with self.assertLogs(level="WARNING"):
            controller, _ = self.start({"poll_hz": 0})
        self.assertEqual(controller._poll_hz, startup.DEFAULT_POLL_HZ)
        with self.assertLogs(level="WARNING"):
            controller, _ = self.start({"poll_hz": "fast"})
        self.assertEqual(controller._poll_hz, startup.DEFAULT_POLL_HZ)

    def test_settings_reach_the_controller(self):
        controller, _ = self.start({"calibrate_on_selftest": False, "autofocus": True},
                                   restart_camera=print)
        self.assertFalse(controller._calibrate_on_selftest())
        self.assertTrue(controller._autofocus_enabled())
        self.assertIs(controller._request_restart, print)

    def test_the_defaults_are_a_default_factory_that_accepts_the_controllers_call(self):
        # LensController calls factory(port, cameras) positionally; open_adapter
        # takes `cameras` keyword-only, so it cannot be passed in directly.
        import inspect
        from module.lens import cef168
        with self.assertRaises(TypeError):
            inspect.signature(cef168.open_adapter).bind(None, [])
        with mock.patch.object(cef168, "open_adapter", return_value=(None, "mocked")) as opened:
            controller = LensController(self.redis)
            self.assertEqual(controller._factory(None, [{"port": "cam0"}]), (None, "mocked"))
            opened.assert_called_once_with(None, cameras=[{"port": "cam0"}])

    def test_no_missing_lens_database_file_is_created_by_starting(self):
        self.start()
        self.assertFalse((self.tmp / "lenses.json").exists())


class SelfTestSettingTests(Rig):
    """calibrate_on_selftest, the only WP1 behaviour WP3 added a switch to."""

    def finish_selftest(self, controller):
        controller._on_selftest_event(lens_controller_module.EVENT_FINISHED)

    def test_on_by_default_the_gesture_queues_a_calibration(self):
        self.finish_selftest(self.lens)
        self.assertIsNotNone(self.lens._calibration_job)

    def test_off_it_only_says_it_saw_it(self):
        lens = LensController(
            self.redis, database=self.db, backend_factory=lambda p, c: (self.backend, ""),
            clock=self.clock, sleep=self.clock.sleep, calibrate_on_selftest=False)
        lens.poll_once()
        self.finish_selftest(lens)
        self.assertIsNone(lens._calibration_job)
        self.assertIn("calibrate_on_selftest", lens.status()["message"])

    def test_it_can_be_a_callable_asked_each_time(self):
        flag = {"on": False}
        lens = LensController(
            self.redis, database=self.db, backend_factory=lambda p, c: (self.backend, ""),
            clock=self.clock, sleep=self.clock.sleep, calibrate_on_selftest=lambda: flag["on"])
        lens.poll_once()
        self.finish_selftest(lens)
        self.assertIsNone(lens._calibration_job)
        flag["on"] = True
        self.finish_selftest(lens)
        self.assertIsNotNone(lens._calibration_job)


class MainWiringTests(unittest.TestCase):
    """main.py cannot be imported without the hardware stack, so its order of
    events is pinned by reading it."""

    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "src/main.py").read_text(encoding="utf-8")
        tree = ast.parse(cls.source)
        function = next(n for n in tree.body
                        if isinstance(n, ast.FunctionDef) and n.name == "run_application")
        cls.run_source = ast.get_source_segment(cls.source, function)

    def index(self, needle):
        found = self.run_source.find(needle)
        self.assertGreaterEqual(found, 0, f"{needle!r} not in run_application")
        return found

    def test_the_lens_thread_starts_before_cinepi_raw_is_launched(self):
        started = self.index("start_lens_controller(")
        self.assertLess(started, self.index("cinepi = CinePi("))
        self.assertLess(started, self.index("\n    cinepi.start_all()\n"))

    def test_defaults_are_seeded_before_it_starts(self):
        self.assertLess(self.index("seed_lens_defaults("), self.index("start_lens_controller("))

    def test_the_controller_is_handed_over_and_published_to_the_web_app(self):
        self.assertIn("cinepi_controller.attach_lens_controller(lens_controller)", self.run_source)
        self.assertIn("lens_controller=lens_controller", self.run_source)
        self.assertIn("lens_database=lens_database", self.run_source)

    def test_it_is_stopped_and_joined_in_cleanup_like_the_other_threads(self):
        cleanup = self.run_source[self.index("def cleanup():"):]
        self.assertIn("lens_controller.stop()", cleanup)
        self.assertIn('join_thread(lens_controller, "LensController")', cleanup)

    def test_the_lens_wiring_cannot_import_the_hardware_stack(self):
        tree = ast.parse((ROOT / "src/module/lens/startup.py").read_text(encoding="utf-8"))
        imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported, {"__future__", "module.lens.controller",
                                    "module.lens.database", "module.redis_controller"})

    def test_create_app_publishes_both_handles(self):
        init = (ROOT / "src/module/app/__init__.py").read_text(encoding="utf-8")
        self.assertIn("app.config['LENS_CONTROLLER'] = lens_controller", init)
        self.assertIn("app.config['LENS_DATABASE'] = lens_database", init)


class RestartCallbackTests(unittest.TestCase):
    def test_a_restart_asked_before_the_controller_exists_is_dropped_not_raised(self):
        # The closure in run_application reads a late-bound holder.
        main_source = (ROOT / "src/main.py").read_text(encoding="utf-8")
        self.assertIn("lens_restart_target.get(\"controller\")", main_source)
        self.assertIn('lens_restart_target["controller"] = cinepi_controller', main_source)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    unittest.main()
