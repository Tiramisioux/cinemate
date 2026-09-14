"""ClearHDR's usable ISO range.

The imx585's HG/LG merge stops reaching the top of the container above roughly
analogue gain code 60, and nothing in the picture says so -- the mode quietly
stops being an HDR mode. Measured on the rig 2026-09-14 in 12-bit HD, reading
cinepi-raw's own ccmpPreview log line:

    ISO        800  | 1600  2500  3200
    gain code   60  |   80    80    80

The driver caps analogue gain in ClearHDR at code 80, which the ISO steps reach
at about ISO 1585, so 1600/2500/3200 all record the SAME exposure -- above the
cap only the preview brightens, via ISP digital gain. The 1600 step is kept and
lands on 1585, shown green; 2500 and 3200 are dropped.

So the cap withholds the steps above it rather than warning about them. These
tests pin the three things that can go wrong: capping when it should not (an
SDR mode, or an operator who lifted it), failing to cap when it should, and
capping so hard that no ISO is selectable at all.
"""

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
    def __init__(self, hdr):
        self.values = {ParameterKey.HDR.value: hdr}
        self.sets = []

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = value
        self.sets.append((key, value))


class _Lock:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


SHIPPED_STEPS = [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200]


def controller(hdr="1", iso_max=1585, steps=None, omit_key=False):
    c = CinePiController.__new__(CinePiController)
    c.redis_controller = FakeRedis(hdr)
    c.iso_steps = list(SHIPPED_STEPS if steps is None else steps)
    c.iso_lock = False
    c.parameters_lock_obj = _Lock()
    hdr_cfg = {"blend": 5, "gain_adder": 1}
    if not omit_key:
        hdr_cfg["iso_max"] = iso_max
    c.settings = {"image_capture": {"hdr": hdr_cfg}}
    return c


class ClearHdrIsoCeilingTests(unittest.TestCase):
    def test_the_first_step_above_the_cap_is_kept(self):
        """1600 stays selectable and lands on 1585; 2500 and up are dropped,
        being identical recordings with a brighter preview."""
        c = controller()
        self.assertEqual(c.effective_iso_steps(), [100, 200, 400, 640, 800, 1200, 1600])

    def test_sdr_mode_is_not_capped(self):
        """The merge is not engaged, so none of this applies."""
        c = controller(hdr="0")
        self.assertEqual(c.effective_iso_steps(), SHIPPED_STEPS)
        c.set_iso(3200)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 3200)

    def test_set_iso_above_the_cap_holds_at_the_cap(self):
        c = controller()
        c.set_iso(3200)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 1585)

    def test_selecting_the_1600_step_lands_on_1585(self):
        c = controller()
        c.set_iso(1600)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 1585)

    def test_iso_is_capped_drives_the_green_tint(self):
        c = controller()
        c.set_iso(1600)
        self.assertTrue(c.iso_is_capped())
        c.set_iso(400)
        self.assertFalse(c.iso_is_capped())

    def test_iso_is_capped_is_false_in_sdr(self):
        c = controller(hdr="0")
        c.set_iso(3200)
        self.assertFalse(c.iso_is_capped())

    def test_set_iso_inside_the_range_is_untouched(self):
        c = controller()
        c.set_iso(640)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 640)

    def test_null_iso_max_lifts_the_cap(self):
        """An operator who would rather have the sensitivity than the
        highlights can say so, and is then not second-guessed."""
        c = controller(iso_max=None)
        self.assertEqual(c.effective_iso_steps(), SHIPPED_STEPS)
        c.set_iso(3200)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 3200)

    def test_missing_key_still_caps(self):
        """A settings.jsonc written before this key existed is the common
        case on a camera in the field, and it must still be protected."""
        c = controller(omit_key=True)
        self.assertEqual(max(c.effective_iso_steps()), 1600)

    def test_a_cap_below_every_step_leaves_one(self):
        """A camera with no selectable ISO is worse than a badly set cap."""
        c = controller(iso_max=50)
        self.assertEqual(c.effective_iso_steps(), [100])
        c.set_iso(3200)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 50)

    def test_a_non_numeric_cap_falls_back_to_the_default(self):
        c = controller(iso_max="nonsense")
        self.assertEqual(max(c.effective_iso_steps()), 1600)

    def test_iso_lock_still_wins(self):
        """The cap must not become a way round the lock."""
        c = controller()
        c.iso_lock = True
        c.set_iso(400)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), None)


if __name__ == "__main__":
    unittest.main()
