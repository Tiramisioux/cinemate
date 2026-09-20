"""Bit-depth parsing from cinepi-raw's quoted Bayer format name.

``SensorDetect._parse_cinepi_output`` reads the mode's bit depth out of the
quoted libcamera/rpicam format string, e.g. ``'SRGGB12_CSI2P'``. The parser
must not assume the Bayer order is always RGGB: libcamera's format name
follows the Bayer order after any sensor flip, so ``SBGGR10_CSI2P``,
``SGRBG12_CSI2P`` and ``SGBRG12_CSI2P`` are all legitimate and must be read
the same way. A format that carries no depth digits at all, such as the
compressed ``*_PISP_COMP1`` container, must not silently keep whatever bit
depth the previous format in the same mode block left behind.
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


class BitDepthParsingTests(unittest.TestCase):
    def _detector(self):
        d = SensorDetect.__new__(SensorDetect)
        d.sensor_database = {"sensors": {}}
        d.packing_info = {}
        return d

    def _single_mode(self, output, camera="imx585"):
        modes = self._detector()._parse_cinepi_output(output)[camera]
        self.assertEqual(len(modes), 1)
        return modes[0]

    def test_sbggr10_csi2p_reports_bit_depth_10(self):
        mode = self._single_mode("""\
0 : imx585 [3856x2180]
    Modes: 'SBGGR10_CSI2P' : 1928x1090 [50.00 fps - (0, 0)/3856x2180 crop]
""")
        self.assertEqual(mode["bit_depth"], 10)

    def test_sgrbg12_csi2p_reports_bit_depth_12(self):
        mode = self._single_mode("""\
0 : imx585 [3856x2180]
    Modes: 'SGRBG12_CSI2P' : 1928x1090 [50.00 fps - (0, 0)/3856x2180 crop]
""")
        self.assertEqual(mode["bit_depth"], 12)

    def test_sgbrg12_csi2p_reports_bit_depth_12(self):
        mode = self._single_mode("""\
0 : imx585 [3856x2180]
    Modes: 'SGBRG12_CSI2P' : 1928x1090 [50.00 fps - (0, 0)/3856x2180 crop]
""")
        self.assertEqual(mode["bit_depth"], 12)

    def test_r10_csi2p_still_reports_bit_depth_10(self):
        """Mono spelling, already matched before this change; guard against
        regressing it while widening the Bayer-order alternation."""
        mode = self._single_mode("""\
0 : imx585_mono [3856x2180]
    Modes: 'R10_CSI2P' : 1928x1090 [50.00 fps - (0, 0)/3856x2180 crop]
""", camera="imx585_mono")
        self.assertEqual(mode["bit_depth"], 10)

    def test_y12_still_reports_bit_depth_12(self):
        """Mono spelling, already matched before this change."""
        mode = self._single_mode("""\
0 : imx585_mono [3856x2180]
    Modes: 'Y12' : 1928x1090 [50.00 fps - (0, 0)/3856x2180 crop]
""", camera="imx585_mono")
        self.assertEqual(mode["bit_depth"], 12)

    def test_pisp_comp1_format_does_not_inherit_previous_bit_depth(self):
        """PISP_COMP1 is a 16-bit compressed container and carries no depth
        digits of its own. A format block that switches to it, after an
        earlier 12-bit format in the same ClearHDR state, must not leave
        current_bit_depth at 12 -- that is the exact "keeps whatever the
        previous block left" bug this package fixes."""
        output = """\
0 : imx585 [3856x2180]
    Modes: 'SRGGB12_CSI2P' : 3840x2160 [44.00 fps - (0, 0)/3856x2180 crop]
CLEAR HDR / SENSOR HDR
0 : imx585 [3856x2180]
    Modes: 'SGRBG12_CSI2P' : 3840x2160 [22.00 fps - (0, 0)/3856x2180 crop]
           'BGGR_PISP_COMP1' : 3840x2200 [22.00 fps - (0, 0)/3856x2180 crop]
"""
        modes = self._detector()._parse_cinepi_output(output, hdr=True)["imx585"]
        by_size = {(m["width"], m["height"]): m for m in modes}
        self.assertEqual(by_size[(3840, 2160)]["bit_depth"], 12)
        self.assertEqual(by_size[(3840, 2200)]["bit_depth"], 16)


if __name__ == "__main__":
    unittest.main()
