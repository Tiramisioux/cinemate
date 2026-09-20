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

    def test_hdr_state_does_not_leak_into_a_second_cameras_header(self):
        """A combined multi-camera ``--hdr sensor`` probe covers every
        attached camera in one transcript. If the imx585 section sets
        current_hdr True at its ClearHDR marker and that flag is never
        reset when parsing moves on to a second, different camera's own
        header, a later PISP_COMP1 line in that second camera's block
        would be force-set to 16-bit (see the PISP_COMP1 gate above) and
        would also dodge the SDR/16-bit-drop guard -- corrupting a real,
        non-ClearHDR stock sensor's mode on any dual-sensor rig that pairs
        it with an imx585."""
        output = """\
0 : imx585 [3856x2180]
    Modes: 'SRGGB12_CSI2P' : 3840x2160 [44.00 fps - (0, 0)/3856x2180 crop]
CLEAR HDR / SENSOR HDR
0 : imx585 [3856x2180]
    Modes: 'SGRBG12_CSI2P' : 3840x2160 [22.00 fps - (0, 0)/3856x2180 crop]
1 : imx519 [4656x3496 10-bit RGGB]
    Modes: 'SRGGB10_CSI2P' : 1920x1080 [60.00 fps - (0, 0)/4656x3496 crop]
           'BGGR_PISP_COMP1' : 2328x1748 [30.00 fps - (0, 0)/4656x3496 crop]
"""
        sensors = self._detector()._parse_cinepi_output(output, hdr=True)
        imx519_modes = sensors["imx519"]
        by_size = {(m["width"], m["height"]): m for m in imx519_modes}
        # The second camera's own modes must never be tagged HDR (it has no
        # ClearHDR section of its own in this transcript) and its COMP1
        # mode must keep its real, non-16 bit depth instead of being
        # force-set to 16 by the leaked imx585 current_hdr flag.
        self.assertTrue(all(not m["hdr"] for m in imx519_modes))
        self.assertEqual(by_size[(1920, 1080)]["bit_depth"], 10)
        self.assertIn((2328, 1748), by_size)
        self.assertEqual(by_size[(2328, 1748)]["bit_depth"], 10)

    def test_unmarked_probe_classifies_new_lower_fps_timings_as_hdr(self):
        d = self._detector()
        base = {"imx585": [{
            "width": 3840, "height": 2160, "bit_depth": 12,
            "fps_max": 67, "hdr": False,
            "crop_x": 0, "crop_y": 0, "crop_width": 3856, "crop_height": 2180,
            "binning_x": 1, "binning_y": 1,
        }]}
        # This is the problematic formatter shape: the HDR probe contains
        # the normal timing and the lower ClearHDR timing, but no state marker.
        hdr = {"imx585": [
            {**base["imx585"][0]},
            {**base["imx585"][0], "fps_max": 30},
        ]}
        d._normalize_hdr_probe_modes(base, hdr)
        self.assertEqual([bool(m["hdr"]) for m in hdr["imx585"]], [False, True])


    def test_unmarked_probe_still_marks_lower_fps_when_plain_probe_also_lists_it(self):
        d = self._detector()
        common = {
            "width": 3840, "height": 2160, "bit_depth": 12,
            "hdr": False,
            "crop_x": 0, "crop_y": 0, "crop_width": 3856, "crop_height": 2180,
            "binning_x": 1, "binning_y": 1,
        }
        base = {"imx585": [
            {**common, "fps_max": 67},
            {**common, "fps_max": 30},
        ]}
        hdr = {"imx585": [
            {**common, "fps_max": 67},
            {**common, "fps_max": 30},
        ]}
        d._normalize_hdr_probe_modes(base, hdr)
        self.assertEqual(
            [bool(m["hdr"]) for m in hdr["imx585"]],
            [False, True],
        )


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
