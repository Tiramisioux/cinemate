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

    def test_pisp_comp1_takes_its_depth_from_the_listing_header(self):
        """COMP1's name has no digits, so the depth comes from the header.

        cinepi-raw prints the sensor's own maximum depth in the camera header,
        taken over the named Bayer formats, and that is the only evidence in the
        listing for what a compressed container carries. Asserting the
        container's own 16 bits would mislabel a 10- or 12-bit COMP1 mode -- and
        the "16-bit in the SDR state is dropped" guard would then discard it --
        while inheriting the previous format block's depth would label this mode
        with a different mode's number.
        """
        output = """\
0 : imx519 [4656x3496 10-bit RGGB]
    Modes: 'SRGGB10_CSI2P' : 1920x1080 [60.00 fps - (0, 0)/4656x3496 crop]
           'BGGR_PISP_COMP1' : 2328x1748 [30.00 fps - (0, 0)/4656x3496 crop]
"""
        modes = self._detector()._parse_cinepi_output(output)["imx519"]
        by_size = {(m["width"], m["height"]): m for m in modes}
        self.assertEqual(by_size[(1920, 1080)]["bit_depth"], 10)
        self.assertIn((2328, 1748), by_size)
        self.assertEqual(by_size[(2328, 1748)]["bit_depth"], 10)

    def test_pisp_comp1_is_skipped_when_the_header_states_no_depth(self):
        """With no header depth and no ClearHDR state, skip rather than guess.

        A skipped line loses a mode; a guessed depth loses the operator's trust
        in every number beside it, and silently changes which modes the
        bit-depth filter keeps.
        """
        output = """\
0 : imx519 [4656x3496]
    Modes: 'SRGGB10_CSI2P' : 1920x1080 [60.00 fps - (0, 0)/4656x3496 crop]
           'BGGR_PISP_COMP1' : 2328x1748 [30.00 fps - (0, 0)/4656x3496 crop]
"""
        modes = self._detector()._parse_cinepi_output(output)["imx519"]
        by_size = {(m["width"], m["height"]): m for m in modes}
        self.assertEqual(by_size[(1920, 1080)]["bit_depth"], 10)
        self.assertNotIn((2328, 1748), by_size)

    def test_pisp_comp1_in_the_clearhdr_state_is_sixteen_bit(self):
        """The imx585 RAW16 case, in the two-state shape the probe really emits.

        Uses the SDR-then-ClearHDR listing rather than an HDR-only one because
        this test is about the COMP1 branch, not about the parser's state
        handling (which test_clearhdr_probe_state.py and
        test_clearhdr_16bit_modes_survive_the_probe.py cover).
        """
        output = """\
0 : imx585 [3856x2180 12-bit RGGB]
    Modes: 'SRGGB12_CSI2P' : 3840x2160 [44.00 fps - (0, 0)/3856x2180 crop]
CLEAR HDR / SENSOR HDR
0 : imx585 [3856x2180 16-bit RGGB]
    Modes: 'BGGR_PISP_COMP1' : 3840x2200 [22.00 fps - (0, 0)/3856x2180 crop]
"""
        modes = self._detector()._parse_cinepi_output(output, hdr=True)["imx585"]
        by_size = {(m["width"], m["height"]): m for m in modes}
        self.assertEqual(by_size[(3840, 2160)]["bit_depth"], 12)
        self.assertEqual(by_size[(3840, 2200)]["bit_depth"], 16)
        self.assertTrue(by_size[(3840, 2200)]["hdr"])


if __name__ == "__main__":
    unittest.main()
