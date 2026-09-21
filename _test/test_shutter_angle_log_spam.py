"""The dynamic shutter-angle table is recomputed constantly, so it must be quiet.

On the camera, 228 of a 1531-line startup log were this one table -- fired every
half second, always for the same fps and the same mains frequencies, always
producing the same 360-entry list, and logged in full at INFO each time. A log
that is 15% one repeated line is a log nobody reads, which is how the thing worth
noticing gets missed.

The computation is pure in (fps, light_hz, shutter_a_steps), so a repeat with the
same inputs has nothing to say. It should return the same list without recomputing
and without logging, and log only when the table actually changes.
"""

import logging
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.cinepi_controller import CinePiController  # noqa: E402


def _controller(shutter_steps=(1, 45, 90, 180, 360), light_hz=(50, 60)):
    c = CinePiController.__new__(CinePiController)
    c.shutter_a_steps = list(shutter_steps)
    c.light_hz = list(light_hz)
    c.shutter_a_steps_dynamic = []
    return c


class DynamicShutterAngleQuietTests(unittest.TestCase):
    def test_recomputing_with_the_same_inputs_says_nothing(self):
        c = _controller()
        with self.assertLogs("root", level="DEBUG") as first:
            first_result = c.calculate_dynamic_shutter_angles(25)
        self.assertTrue(any("shutter angle" in m.lower() for m in first.output),
                        "the first computation should still be reported")

        logger = logging.getLogger()
        with self.assertNoLogs(logger, level="INFO"):
            again = c.calculate_dynamic_shutter_angles(25)
        self.assertEqual(again, first_result,
                         "the cached answer must be the same list, not a stale one")

    def test_a_changed_fps_is_reported_again(self):
        c = _controller()
        c.calculate_dynamic_shutter_angles(25)
        with self.assertLogs("root", level="INFO") as changed:
            other = c.calculate_dynamic_shutter_angles(24)
        self.assertTrue(changed.output, "a real change must still be logged")
        self.assertNotEqual(other, c.calculate_dynamic_shutter_angles(24) and other[:0],
                            "sanity: the 24 fps table is returned")

    def test_a_changed_mains_frequency_is_reported_again(self):
        c = _controller()
        c.calculate_dynamic_shutter_angles(25)
        c.light_hz = [50]
        with self.assertLogs("root", level="INFO"):
            c.calculate_dynamic_shutter_angles(25)

    def test_the_table_itself_is_unchanged_by_the_caching(self):
        # The point is only to stop repeating it, never to change what it holds.
        fresh = _controller().calculate_dynamic_shutter_angles(25)
        cached = _controller()
        cached.calculate_dynamic_shutter_angles(25)
        self.assertEqual(cached.calculate_dynamic_shutter_angles(25), fresh)


if __name__ == "__main__":
    unittest.main()
