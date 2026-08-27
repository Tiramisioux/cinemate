"""A mono sensor has no CFA, so --awb/--awbgains are meaningless for it --
cinepi_multi.py used to send them anyway (`--awb auto --awbgains 3.3,1.5` on
a mono launch, per the 2026-08-27 hardware log). CinePiProcess._build_args()
now omits both, and the cg_rb value they would have carried, for a mono
CameraInfo -- and still sends them, unchanged, for a colour one.

CinePiProcess._build_args() has a lot of surface area (storage profiles,
CineMate Log resolution, dual-HDMI, ...), none of which this test seam
touches: every dependency is a minimal fake returning defaults, so a failure
here can only be the AWB guard, not one of those other reads.
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("psutil", types.SimpleNamespace())

from module.cinepi_multi import CameraInfo, CinePiProcess


class FakeRedisController:
    """get_value returns whatever default the caller asks for; nothing in
    _build_args needs a real, moving value for this test."""

    def get_value(self, key, default=None):
        return default

    def set_value(self, key, value):
        pass


class FakeSensorDetect:
    def get_resolution_info(self, model_key, sensor_mode):
        return {"width": 1920, "height": 1080, "bit_depth": 12}

    def get_packing_for_platform(self, model_key, sensor_mode, is_pi4):
        return "U"

    def resolve_log_encode_target(self, model_key, bit_depth, requested, hdr):
        return None


def build_args(is_mono: bool) -> list[str]:
    fmt = "MONO" if is_mono else "RGB"
    cam = CameraInfo(0, "imx585", fmt, "i2c@88000")
    proc = CinePiProcess(FakeRedisController(), FakeSensorDetect(), cam, primary=True, multi=False)
    return proc._build_args()


class MonoAwbArgsTests(unittest.TestCase):
    def test_a_mono_launch_carries_no_awb_arguments(self):
        args = build_args(is_mono=True)
        self.assertNotIn("--awb", args)
        self.assertNotIn("--awbgains", args)

    def test_a_colour_launch_is_unaffected(self):
        args = build_args(is_mono=False)
        self.assertIn("--awb", args)
        self.assertEqual(args[args.index("--awb") + 1], "auto")
        self.assertIn("--awbgains", args)
        # The default gain pair, since FakeRedisController.get_value always
        # returns the caller's default and cinepi_multi.py falls back to it.
        self.assertEqual(args[args.index("--awbgains") + 1], "2.5,2.2")


if __name__ == "__main__":
    unittest.main()
