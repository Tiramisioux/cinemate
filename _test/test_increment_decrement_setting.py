"""Wiring-parity tests for increment_setting/decrement_setting.

These exercise the real CinePiController methods (not stand-ins) to lock in
that resolving step tables through parameters.REGISTRY produces the exact
same dispatch as the old per-parameter `if setting_name == ...` branches it
replaced. set_fps and update_shutter_angle_nom are mocked out: their own
internals are unmodified by this change, so what matters here is that
increment_setting/decrement_setting still hand them the right value - not
re-proving set_fps's fps_max clamp, which is covered by the Pi hardware
before/after comparison instead.
"""

import sys
import threading
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.cinepi_controller import CinePiController
from module.redis_controller import ParameterKey


class FakeRedis:
    def __init__(self, initial=None):
        self.values = dict(initial or {})

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value


def make_controller(redis_seed=None):
    c = CinePiController.__new__(CinePiController)
    c.redis_controller = FakeRedis(redis_seed)
    c.parameters_lock_obj = threading.Lock()

    c.iso_lock = False
    c.shutter_a_nom_lock = False
    c.fps_lock = False
    c.all_lock = False

    c.iso_free = False
    c.shutter_a_free = False
    c.fps_free = False

    c.iso_steps = [100, 200, 400, 800, 1600, 3200]
    c.fps_steps = [1, 12, 24, 25, 50]
    c.shutter_a_steps = [45.0, 90.0, 180.0, 270.0, 360.0]
    c.shutter_a_steps_dynamic = []
    c.light_hz = [50.0]
    # A deliberately non-default fps: 29 isn't a round number, so any
    # flicker-free angle it produces is guaranteed not to already be sitting
    # in the static shutter_a_steps table by coincidence.
    c.current_fps = 29
    c.fps = 29
    c.shutter_a_sync_mode = 0

    c.set_fps = mock.Mock(name="set_fps")
    c.update_shutter_angle_nom = mock.Mock(name="update_shutter_angle_nom")

    return c


class IsoWiringTests(unittest.TestCase):
    def test_increment_moves_to_the_next_table_entry(self):
        c = make_controller({ParameterKey.ISO.value: "400"})
        c.increment_setting("iso", c.iso_steps)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 800)

    def test_increment_clamps_at_the_top_of_the_table(self):
        c = make_controller({ParameterKey.ISO.value: "3200"})
        c.increment_setting("iso", c.iso_steps)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 3200)

    def test_decrement_clamps_at_the_bottom_of_the_table(self):
        c = make_controller({ParameterKey.ISO.value: "100"})
        c.decrement_setting("iso", c.iso_steps)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 100)

    def test_lock_blocks_the_write(self):
        c = make_controller({ParameterKey.ISO.value: "400"})
        c.iso_lock = True
        c.increment_setting("iso", c.iso_steps)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), "400")


class ShutterAWiringTests(unittest.TestCase):
    def test_increment_honours_flicker_free_angles_at_the_current_fps(self):
        c = make_controller({ParameterKey.SHUTTER_A.value: "180.0"})
        expected_table = c.calculate_dynamic_shutter_angles(29)
        idx = expected_table.index(180.0)
        expected_next = expected_table[idx + 1]

        c.increment_setting("shutter_a", c.shutter_a_steps, fps=29)

        self.assertEqual(c.redis_controller.get_value(ParameterKey.SHUTTER_A.value), expected_next)
        # The point of this test: at fps=29/50Hz the very next legal angle
        # above 180 is a flicker-free harmonic, not the static table's 270.
        self.assertNotIn(expected_next, c.shutter_a_steps)


class ShutterANomWiringTests(unittest.TestCase):
    """shutter_a_nom is the registry's stress test: it borrows shutter_a's
    static step *table* (not shutter_a's own flicker-free-recomputing
    steps() callable) while keeping its own lock.

    NOTE: increment_setting/decrement_setting read the current value via
    get_setting(setting_name), which looks the raw string 'shutter_a_nom' up
    directly in Redis - but every writer (set_shutter_a_nom,
    update_shutter_angle_nom) persists under ParameterKey.SHUTTER_A_NOM
    ('shutter_angle_nom'), a different key. That mismatch is a pre-existing
    bug this refactor does not touch or fix; these tests seed the literal
    'shutter_a_nom' key to exercise the surrounding dispatch logic exactly
    as increment_setting reads it today.
    """

    def test_increment_only_cycles_through_the_static_table(self):
        c = make_controller({"shutter_a_nom": "180.0"})
        c.increment_setting("shutter_a_nom", c.shutter_a_steps)

        # Static table is [45, 90, 180, 270, 360]: the next entry is 270,
        # not one of the flicker-free harmonics that shutter_a itself would
        # step through at this fps.
        self.assertEqual(
            c.redis_controller.get_value(ParameterKey.SHUTTER_A_NOM.value), 270.0
        )

    def test_decrement_only_cycles_through_the_static_table(self):
        c = make_controller({"shutter_a_nom": "180.0"})
        c.decrement_setting("shutter_a_nom", c.shutter_a_steps)
        self.assertEqual(
            c.redis_controller.get_value(ParameterKey.SHUTTER_A_NOM.value), 90.0
        )

    def test_lock_blocks_the_write(self):
        c = make_controller({"shutter_a_nom": "180.0"})
        c.shutter_a_nom_lock = True
        c.increment_setting("shutter_a_nom", c.shutter_a_steps)
        self.assertIsNone(c.redis_controller.get_value(ParameterKey.SHUTTER_A_NOM.value))

    def test_sync_mode_routes_to_update_shutter_angle_nom_not_set_shutter_a_nom(self):
        c = make_controller({"shutter_a_nom": "180.0"})
        c.shutter_a_sync_mode = 1
        c.set_shutter_a_nom = mock.Mock(name="set_shutter_a_nom")

        c.increment_setting("shutter_a_nom", c.shutter_a_steps)

        c.update_shutter_angle_nom.assert_called_once_with(270.0)
        c.set_shutter_a_nom.assert_not_called()


class FpsWiringTests(unittest.TestCase):
    def test_increment_dispatches_to_set_fps_with_the_raw_uncapped_next_value(self):
        c = make_controller({ParameterKey.FPS.value: "24"})
        c.increment_setting("fps", c.fps_steps)
        # fps_max clamping happens inside set_fps itself (unmodified by this
        # refactor, and covered by the Pi hardware before/after check) -
        # increment_setting's job is only to hand it the next raw table
        # value, uncapped.
        c.set_fps.assert_called_once_with(25)

    def test_decrement_dispatches_to_set_fps_with_the_raw_uncapped_previous_value(self):
        c = make_controller({ParameterKey.FPS.value: "25"})
        c.decrement_setting("fps", c.fps_steps)
        c.set_fps.assert_called_once_with(24)

    def test_sync_mode_still_calls_set_fps(self):
        c = make_controller({ParameterKey.FPS.value: "24"})
        c.shutter_a_sync_mode = 1
        c.increment_setting("fps", c.fps_steps)
        c.set_fps.assert_called_once_with(25)


class UnknownSettingNameFallbackTests(unittest.TestCase):
    def test_unknown_name_warns_and_falls_back_to_the_passed_steps_and_set_prefix(self):
        c = make_controller({"totally_made_up": "1"})
        c.set_totally_made_up = mock.Mock(name="set_totally_made_up")

        with self.assertLogs("module.parameters", level="WARNING") as cm:
            c.increment_setting("totally_made_up", [1, 2, 3])

        self.assertTrue(
            any("totally_made_up" in line and "increment_setting" in line for line in cm.output)
        )
        c.set_totally_made_up.assert_called_once_with(2)


if __name__ == "__main__":
    unittest.main()
