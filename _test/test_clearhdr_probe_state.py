"""Regression tests for SDR/ClearHDR probe state.

The two cinepi-raw probes have a strict contract:
- plain --list-cameras => SDR modes
- --hdr sensor => ClearHDR modes

The latter may be printed either as an HDR-only listing or as an
SDR-then-ClearHDR listing. FPS is deliberately not part of mode identity.
"""

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.sensor_detect import SensorDetect


class ClearHdrProbeStateTests(unittest.TestCase):
    def _detector(self):
        d = SensorDetect.__new__(SensorDetect)
        d.sensor_database = {"sensors": {}}
        d.packing_info = {}
        return d

    def test_hdr_only_probe_marks_every_mode_hdr(self):
        output = """\
0 : imx585 [3856x2180]
    Modes: 'SRGGB12_CSI2P' : 3840x2160 [22.00 fps - (0, 0)/3856x2180 crop]
    Modes: 'R16' : 3840x2200 [22.00 fps - (0, 0)/3856x2180 crop]
"""
        modes = self._detector()._parse_cinepi_output(output, hdr=True)["imx585"]
        self.assertTrue(all(m["hdr"] for m in modes))

    def test_two_state_probe_keeps_sdr_and_marks_only_second_state_hdr(self):
        output = """\
0 : imx585 [3856x2180]
    Modes: 'SRGGB12_CSI2P' : 3840x2160 [44.00 fps - (0, 0)/3856x2180 crop]
CLEAR HDR / SENSOR HDR
0 : imx585 [3856x2180]
    Modes: 'SRGGB12_CSI2P' : 3840x2160 [22.00 fps - (0, 0)/3856x2180 crop]
"""
        modes = self._detector()._parse_cinepi_output(output, hdr=True)["imx585"]
        self.assertEqual([m["hdr"] for m in modes], [False, True])

    def test_sdr_and_hdr_same_readout_are_distinct_even_when_fps_differs(self):
        d = self._detector()
        base = {"imx585": [{
            "width": 3840, "height": 2160, "bit_depth": 12,
            "fps_max": 44, "hdr": False,
            "crop_x": 0, "crop_y": 0, "crop_width": 3856, "crop_height": 2180,
            "binning_x": 1, "binning_y": 1,
        }]}
        hdr = {"imx585": [{
            "width": 3840, "height": 2160, "bit_depth": 12,
            "fps_max": 22, "hdr": True,
            "crop_x": 0, "crop_y": 0, "crop_width": 3856, "crop_height": 2180,
            "binning_x": 1, "binning_y": 1,
        }]}
        merged = d._merge_mode_lists(base, hdr)
        self.assertEqual(len(merged["imx585"]), 2)
        self.assertEqual({bool(m["hdr"]) for m in merged["imx585"]}, {False, True})

    def test_same_state_duplicate_with_different_fps_is_not_a_second_mode(self):
        d = self._detector()
        base = {"imx585": [{
            "width": 3840, "height": 2160, "bit_depth": 12,
            "fps_max": 44, "hdr": True,
            "crop_x": 0, "crop_y": 0, "crop_width": 3856, "crop_height": 2180,
            "binning_x": 1, "binning_y": 1,
        }]}
        hdr = {"imx585": [{
            "width": 3840, "height": 2160, "bit_depth": 12,
            "fps_max": 22, "hdr": True,
            "crop_x": 0, "crop_y": 0, "crop_width": 3856, "crop_height": 2180,
            "binning_x": 1, "binning_y": 1,
        }]}
        merged = d._merge_mode_lists(base, hdr)
        self.assertEqual(len(merged["imx585"]), 1)
        self.assertEqual(merged["imx585"][0]["fps_max"], 44)


if __name__ == "__main__":
    unittest.main()
