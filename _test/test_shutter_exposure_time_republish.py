"""set_shutter_a() and set_shutter_a_nom() must republish exposure_time, and
set_shutter_a() must keep self.shutter_angle_actual in sync too.

Before the first fix, exposure_time (ParameterKey.EXPOSURE_TIME) was only
ever written to Redis from the fps-change path. A shutter-only change
updated the real sensor control (shutter_a, which cinepi-raw actually
consumes) and computed a fresh self.exposure_time_seconds, but never
published it -- so the web GUI's exposure readout (template.html's 'v-exp',
bound to V.exposure_time) went stale after any shutter change that didn't
also touch fps. That read as "the shutter change didn't take effect" even
though the real capture path was fine.

Before the second fix, set_shutter_a() wrote the corrected value to the
shutter_angle_actual REDIS KEY but never updated the shutter_angle_actual
PYTHON ATTRIBUTE that set_fps()'s "keep motion-blur constant" snap (and
update_shutter_angle_for_fps()) read instead. The next fps change -- and
every mode switch triggers one -- re-derived a snapped angle from whatever
that attribute was stale at BEFORE the shutter change and overwrote the
correct Redis value with it. Confirmed live on hardware: `set shutter a 1`
correctly set shutter_a=1 and shutter_angle_actual=1, but a subsequent mode
switch (which changes fps) silently reverted shutter_angle_actual to an
earlier session's 180 while shutter_a (the key cinepi-raw actually reads)
stayed at 1 -- the sensor kept capturing at 1 degree while the display
claimed 180.
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


class ShutterActualAttributeStalenessTests(unittest.TestCase):
    def test_set_shutter_a_updates_the_actual_attribute_not_just_the_redis_key(self):
        c = make_controller(fps=25)
        c.shutter_angle_actual = 180.0  # stale, as if left over from an earlier session

        c.set_shutter_a(90.0)

        self.assertEqual(c.shutter_angle_actual, 90.0)
        self.assertEqual(
            c.redis_controller.get_value(ParameterKey.SHUTTER_A_ACTUAL.value), 90.0
        )

    def test_a_subsequent_fps_change_snaps_from_the_just_set_angle_not_a_stale_one(self):
        """Reproduces the hardware bug directly by calling the real
        set_fps(), not by re-implementing its snap inline. The previous
        version of this test never called set_fps() at all -- it recomputed
        the snap by hand against the static c.shutter_a_steps, so it passed
        regardless of whether set_fps() itself (which actually reads
        self.shutter_a_steps_dynamic, not shutter_a_steps) was correct.
        """
        c = make_controller(fps=25)
        c.settings = {
            "arrays": {
                "shutter_a": {"steps": [1, 45.0, 90.0, 180.0, 270.0, 360.0]},
                "fps": {"steps": [1, 25, 50]},
            }
        }
        c.fps_lock = False
        c.lock_override = False
        c.fps_free = False
        c.dynamic_resolution_enabled = False
        c.dynamic_resolution_active = False
        c.dynamic_resolution_desired_mode = None
        c.user_fps = 25
        c.fps_max = 50
        c.redis_controller.set_value(ParameterKey.FPS_MAX.value, "50")
        c.shutter_angle_actual = 180.0  # stale, as if left over from an earlier session

        c.set_shutter_a(90.0)
        c.set_fps(25)

        self.assertEqual(c.shutter_angle_actual, 90.0)

    def test_sync_mode_set_shutter_a_survives_a_subsequent_fps_change(self):
        """Mirror of the test above for shutter_a_sync_mode == 1. set_fps()'s
        sync branch (cinepi_controller.py ~line 1056) derives
        shutter_angle_actual from self.exposure_time_nominal, not from
        whatever set_shutter_a() just accepted -- so leaving that attribute
        stale resurrects the pre-existing nominal angle (often the 180 degree
        startup default) on the very next fps change, which every mode switch
        triggers. Confirmed on hardware: `set shutter a 1` correctly set
        shutter_a=1, but the following mode switch (which changes fps)
        silently reverted shutter_angle_actual to 180 while shutter_a (the
        key cinepi-raw actually reads) stayed at 1.
        """
        c = make_controller(fps=25)
        c.fps_lock = False
        c.lock_override = False
        c.fps_free = False
        c.dynamic_resolution_enabled = False
        c.dynamic_resolution_active = False
        c.dynamic_resolution_desired_mode = None
        c.user_fps = 25
        c.redis_controller.set_value(ParameterKey.FPS_MAX.value, "50")
        c.shutter_a_sync_mode = 1
        c.shutter_angle_nom = 180.0
        c.shutter_angle_actual = 180.0
        c.exposure_time_nominal = (180.0 / 360.0) / 25  # stale startup default

        c.set_shutter_a(1.0)
        c.set_fps(25)  # e.g. triggered by a mode switch

        self.assertEqual(c.shutter_angle_actual, 1.0)


if __name__ == "__main__":
    unittest.main()
