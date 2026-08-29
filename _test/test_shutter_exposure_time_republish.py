"""set_shutter_a() and set_shutter_a_nom() must republish exposure_time.

Before this fix, exposure_time (ParameterKey.EXPOSURE_TIME) was only ever
written to Redis from the fps-change path. A shutter-only change updated the
real sensor control (shutter_a, which cinepi-raw actually consumes) and
computed a fresh self.exposure_time_seconds, but never published it -- so the
web GUI's exposure readout (template.html's 'v-exp', bound to V.exposure_time)
went stale after any shutter change that didn't also touch fps. That read as
"the shutter change didn't take effect" even though the real capture path was
fine.
"""

import sys
import threading
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
    def __init__(self, initial=None):
        self.values = dict(initial or {})

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value


def make_controller(fps=25):
    c = CinePiController.__new__(CinePiController)
    c.redis_controller = FakeRedis()
    c.parameters_lock_obj = threading.Lock()

    c.shutter_a_free = False
    c.shutter_a_nom_lock = False
    c.shutter_a_sync_mode = 0
    c.shutter_a_steps = [45.0, 90.0, 180.0, 270.0, 360.0]
    c.shutter_a_steps_dynamic = []
    c.light_hz = [50.0, 60.0]
    c.current_fps = fps
    c.shutter_angle_nom = None
    c.shutter_angle_actual = None
    c.exposure_time_nominal = None

    return c


class ShutterExposureTimeRepublishTests(unittest.TestCase):
    def test_set_shutter_a_republishes_exposure_time(self):
        c = make_controller(fps=25)

        c.set_shutter_a(180.0)

        expected = (180.0 / 360.0) / 25
        self.assertEqual(
            c.redis_controller.get_value(ParameterKey.EXPOSURE_TIME.value), expected
        )

    def test_set_shutter_a_updates_exposure_time_on_every_call_not_just_the_first(self):
        c = make_controller(fps=25)

        c.set_shutter_a(180.0)
        c.set_shutter_a(90.0)

        expected = (90.0 / 360.0) / 25
        self.assertEqual(
            c.redis_controller.get_value(ParameterKey.EXPOSURE_TIME.value), expected
        )

    def test_set_shutter_a_nom_republishes_exposure_time(self):
        c = make_controller(fps=25)

        c.set_shutter_a_nom(90.0)

        expected = (90.0 / 360.0) / 25
        self.assertEqual(
            c.redis_controller.get_value(ParameterKey.EXPOSURE_TIME.value), expected
        )


if __name__ == "__main__":
    unittest.main()
