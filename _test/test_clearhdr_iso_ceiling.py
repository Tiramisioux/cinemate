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

THERE ARE TWO CEILINGS, NOT ONE. The 1585 above is the 16-bit story. The 12-bit
CCMP modes hit a different and much lower wall first -- the sensor only combines
its two reads while GAIN + EXP_GAIN stays inside 9.6-29.1 dB (imx585.c:167), and
ClearHDR's +12 dB adder puts that at gain code 57, i.e. ISO 799. Measured
2026-09-14:

    ISO        640  700  799 | 800  900  1000
    gain code   51   56   56 |  60   63    66

Past it the merge collapses and 12-bit ClearHDR returns LESS highlight range
than SDR. So the cap is per sensor bit depth, and the last block of tests below
exists because collapsing the two numbers back into one is the obvious tidy-up
and is silently destructive.
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
    def __init__(self, hdr, bit_depth=None, recording="0"):
        self.values = {ParameterKey.HDR.value: hdr,
                       ParameterKey.IS_RECORDING.value: recording}
        if bit_depth is not None:
            self.values[ParameterKey.BIT_DEPTH.value] = bit_depth
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


def controller(hdr="1", iso_max=1585, steps=None, omit_key=False, bit_depth=None,
               recording="0"):
    c = CinePiController.__new__(CinePiController)
    c.redis_controller = FakeRedis(hdr, bit_depth, recording)
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

    # ── the two families, two measured ceilings ──────────────────────────
    #
    # These all omit `iso_max` on purpose: the per-family defaults are only
    # consulted when the operator has NOT written a ceiling of their own, and
    # a test that passes one would never reach the code it means to check.

    def test_12bit_clearhdr_caps_at_799(self):
        """The CCMP modes hit the combination window (GAIN + EXP_GAIN <=
        29.1 dB) at gain code 57 long before the driver's own gain cap."""
        c = controller(omit_key=True, bit_depth="12")
        self.assertEqual(c._clearhdr_iso_ceiling(), 799)
        c.set_iso(3200)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 799)

    def test_16bit_clearhdr_caps_at_1585(self):
        """No compander, so the only limit is IMX585_ANA_GAIN_MAX_HDR."""
        c = controller(omit_key=True, bit_depth="16")
        self.assertEqual(c._clearhdr_iso_ceiling(), 1585)
        c.set_iso(3200)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 1585)

    def test_12bit_keeps_the_800_step_and_lands_it_on_799(self):
        """Same shape as 16-bit's 1600 -> 1585: the step above the cap stays
        selectable so the operator is not stranded at 640, and the GUI tints
        it green to say the camera is holding it."""
        c = controller(omit_key=True, bit_depth="12")
        self.assertEqual(c.effective_iso_steps(), [100, 200, 400, 640, 800])
        c.set_iso(800)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 799)
        self.assertTrue(c.iso_is_capped())

    def test_the_two_ceilings_are_different_numbers(self):
        """A guard, not a tautology. Collapsing these back to one constant is
        the obvious 'simplification', and it silently runs 12-bit ClearHDR a
        full stop past the point where its merge stops delivering HDR at all
        -- which looks like nothing in the picture until the highlights are
        already gone."""
        c12 = controller(omit_key=True, bit_depth="12")
        c16 = controller(omit_key=True, bit_depth="16")
        self.assertLess(c12._clearhdr_iso_ceiling(), c16._clearhdr_iso_ceiling())

    def test_an_unreadable_bit_depth_falls_back_to_the_16bit_ceiling(self):
        """HDR on with no resolution applied is not reachable through
        set_resolution(), which writes both keys. This pins the behaviour
        anyway, and pins it to what the code did before the split."""
        for bogus in (None, "", "nonsense"):
            c = controller(omit_key=True, bit_depth=bogus)
            self.assertEqual(c._clearhdr_iso_ceiling(), 1585, f"bit_depth={bogus!r}")

    def test_iso_max_stays_one_override_for_both_families(self):
        """An operator who writes a ceiling gets that ceiling, whichever mode
        is engaged. Splitting the override per depth would mean the camera
        quietly used a number they never wrote."""
        for depth in ("12", "16"):
            c = controller(iso_max=1000, bit_depth=depth)
            self.assertEqual(c._clearhdr_iso_ceiling(), 1000, f"bit_depth={depth}")
        for depth in ("12", "16"):
            c = controller(iso_max=None, bit_depth=depth)
            self.assertIsNone(c._clearhdr_iso_ceiling(), f"bit_depth={depth}")

    def test_sdr_is_uncapped_at_either_depth(self):
        """The cap is a ClearHDR combination limit; a 12-bit SDR mode is not
        subject to it just for being 12-bit."""
        for depth in ("12", "16"):
            c = controller(hdr="0", omit_key=True, bit_depth=depth)
            self.assertIsNone(c._clearhdr_iso_ceiling())
            self.assertEqual(c.effective_iso_steps(), SHIPPED_STEPS)

    # ── ISO is frozen for the length of a ClearHDR take ──────────────────
    #
    # cinepi-raw latches a measured WhiteLevel on the take's first frame, and
    # the sensor's clamp moves with analogue gain -- the wrong way round from
    # what people expect. More gain means a LOWER ceiling, so lowering ISO
    # mid-take raises the real clamp ABOVE the WhiteLevel already written and
    # every converter crushes the band between them to flat white.

    def test_iso_is_held_while_recording_in_clearhdr(self):
        c = controller(recording="1")
        c.set_iso(400)
        self.assertIsNone(c.redis_controller.get_value(ParameterKey.ISO.value))
        self.assertEqual(c.redis_controller.sets, [])

    def test_the_held_direction_is_both(self):
        """Lowering ISO is the destructive one, but the control is held both
        ways: a knob that moves up and not down would teach the opposite of
        the truth."""
        for value in (100, 3200):
            c = controller(recording="1")
            c.set_iso(value)
            self.assertIsNone(c.redis_controller.get_value(ParameterKey.ISO.value),
                              f"iso {value} should have been held")

    def test_recording_in_sdr_is_not_held(self):
        """Nothing latches a measured WhiteLevel in SDR, so there is nothing
        to protect and no reason to take the control away."""
        c = controller(hdr="0", recording="1")
        c.set_iso(3200)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 3200)

    def test_not_recording_in_clearhdr_is_not_held(self):
        c = controller(recording="0")
        c.set_iso(400)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), 400)

    def test_lifting_the_cap_does_not_lift_the_recording_hold(self):
        """`iso_max: null` is a choice about how much highlight range to
        trade for sensitivity. It is not consent to destroy the highlights of
        a take already in progress, so the two are gated separately."""
        c = controller(iso_max=None, recording="1")
        self.assertIsNone(c._clearhdr_iso_ceiling())      # cap really is lifted
        c.set_iso(3200)
        self.assertIsNone(c.redis_controller.get_value(ParameterKey.ISO.value))

    def test_iso_lock_still_wins(self):
        """The cap must not become a way round the lock."""
        c = controller()
        c.iso_lock = True
        c.set_iso(400)
        self.assertEqual(c.redis_controller.get_value(ParameterKey.ISO.value), None)


if __name__ == "__main__":
    unittest.main()
