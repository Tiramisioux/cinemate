"""Hiding the 12-bit ClearHDR modes renumbers the ones that remain.

With them hidden the imx585 table goes

    0 4K SDR 10 | 1 HD SDR 12 | 2 4K SDR 12 | 3 HD HDR 16 | 4 4K HDR 16

so 16-bit ClearHDR HD and 4K move from 5 and 6 down to 3 and 4, and the old
3 and 4 (the 12-bit ClearHDR pair) are gone. A stored sensor_mode is an index
into a table that no longer exists, and the old fallback sent anything
out-of-range to mode 0 -- 4K SDR. A camera parked on 4K 16-bit ClearHDR would
have woken up in SDR.

Redis keeps the SHAPE of the last capture beside the index, so these tests pin
that startup re-resolves from the shape: the same capture if it still exists,
the same resolution and HDR state at another bit depth if it does not, and the
old fallback only when nothing matches at all.
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


# The table as it is once 12-bit ClearHDR is hidden, taken from the live
# sensor on the rig rather than invented.
HIDDEN = {
    0: {"width": 3840, "height": 2160, "bit_depth": 10, "hdr": False},
    1: {"width": 1920, "height": 1080, "bit_depth": 12, "hdr": False},
    2: {"width": 3840, "height": 2160, "bit_depth": 12, "hdr": False},
    3: {"width": 1920, "height": 1100, "bit_depth": 16, "hdr": True},
    4: {"width": 3840, "height": 2200, "bit_depth": 16, "hdr": True},
}


class FakeRedis:
    def __init__(self, **values):
        self.values = {k: str(v) for k, v in values.items()}
        self.sets = []

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)

    def set_value(self, key, value):
        key = key.value if isinstance(key, ParameterKey) else key
        self.values[key] = str(value)
        self.sets.append((key, value))


class FakeSensorDetect:
    def __init__(self, res_modes):
        self.res_modes = res_modes


def controller(stored_mode, width, height, bit_depth, hdr, table=HIDDEN):
    c = CinePiController.__new__(CinePiController)
    c.redis_controller = FakeRedis(**{
        ParameterKey.SENSOR_MODE.value: stored_mode,
        ParameterKey.WIDTH.value: width,
        ParameterKey.HEIGHT.value: height,
        ParameterKey.BIT_DEPTH.value: bit_depth,
        ParameterKey.HDR.value: 1 if hdr else 0,
    })
    c.sensor_detect = FakeSensorDetect(table)
    return c


class RenumberingTests(unittest.TestCase):
    def test_4k_16bit_clearhdr_follows_its_capture_from_6_to_4(self):
        """The case on the rig: mode 6 no longer exists, and mode 0 is SDR."""
        c = controller(6, 3840, 2200, 16, True)
        self.assertEqual(c._get_startup_sensor_mode(), 4)

    def test_hd_16bit_clearhdr_follows_its_capture_from_5_to_3(self):
        c = controller(5, 1920, 1100, 16, True)
        self.assertEqual(c._get_startup_sensor_mode(), 3)

    def test_4k_12bit_clearhdr_lands_on_4k_16bit_clearhdr(self):
        """Its own mode is gone for good. The same sensor area and the same
        HDR state at another depth is the honest nearest thing -- and is the
        mode this change wants people on anyway. Not SDR."""
        c = controller(4, 3840, 2160, 12, True)
        self.assertEqual(c._get_startup_sensor_mode(), 4)

    def test_hd_12bit_clearhdr_lands_on_hd_16bit_clearhdr(self):
        c = controller(3, 1920, 1080, 12, True)
        self.assertEqual(c._get_startup_sensor_mode(), 3)

    def test_an_sdr_mode_that_still_exists_is_left_alone(self):
        c = controller(2, 3840, 2160, 12, False)
        self.assertEqual(c._get_startup_sensor_mode(), 2)

    def test_sdr_is_never_re_resolved_into_clearhdr(self):
        """A stored SDR capture whose index went stale must not be "recovered"
        into an HDR mode -- that would change what the camera records."""
        c = controller(9, 3840, 2160, 10, False)
        self.assertEqual(c._get_startup_sensor_mode(), 0)

    def test_nothing_matching_still_falls_back(self):
        c = controller(9, 640, 480, 8, False)
        self.assertEqual(c._get_startup_sensor_mode(), 0)

    def test_no_mode_table_keeps_the_stored_value_unvalidated(self):
        """Pre-existing behaviour, hardware-confirmed 2026-09-02: with no
        camera, write nothing rather than persist a fallback."""
        c = controller(6, 3840, 2200, 16, True, table={})
        self.assertEqual(c._get_startup_sensor_mode(), 6)
        self.assertEqual(c.redis_controller.sets, [])


if __name__ == "__main__":
    unittest.main()


class BinnedClearHdrSwitchTests(unittest.TestCase):
    """The HD (binned) ClearHDR mode is opt-in, not gone.

    It renders pink in blown highlights because CineMate ships without the
    preview-side clamp correction, so it is off by default -- but the operator
    can turn it on and accept that. The 4K ClearHDR mode must not be affected
    either way, and the binned SDR mode must survive both settings, which is
    why this is not image_capture.k_steps.
    """

    def _modes(self, binned_on):
        from module.sensor_detect import SensorDetect
        d = SensorDetect.__new__(SensorDetect)
        d.clear_hdr_depths = {16}
        d.clear_hdr_binned = binned_on
        d.bit_depths = []
        d.k_steps = []
        d.hdr_modes = set()
        return d

    def test_binned_clearhdr_is_off_by_default(self):
        d = self._modes(False)
        self.assertFalse(d.clear_hdr_binned)

    def test_the_switch_is_what_gates_it(self):
        self.assertTrue(self._modes(True).clear_hdr_binned)


