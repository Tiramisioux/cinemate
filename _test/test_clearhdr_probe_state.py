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

    def test_hdr_only_probe_keeps_the_16bit_mode_and_tags_it_hdr(self):
        """An unmarked --hdr sensor listing: one section, no CLEAR HDR marker,
        no repeated header. The parser has no state evidence for the 12-bit
        line -- that is _normalize_hdr_probe_modes' decision, from timings,
        and this test never calls it -- but the 'R16' line is evidence on its
        own: the imx585 driver enumerates RAW16 only with wide_dynamic_range
        on. So it is tagged ClearHDR and kept.

        Until 2026-09-25 it was dropped outright here by a "16-bit in the SDR
        state" guard, because an unmarked probe left the parser in that
        state -- and so was every 16-bit line of the marked probe, whose
        post-marker section was parsed in the SDR state too. That is how the
        16-bit ClearHDR modes vanished from the mode table while the 12-bit
        ones survived (CM-1 left this red and called it a real defect; see
        test_clearhdr_16bit_modes_survive_the_probe.py for the whole chain).
        """
        output = """\
0 : imx585 [3856x2180]
    Modes: 'SRGGB12_CSI2P' : 3840x2160 [22.00 fps - (0, 0)/3856x2180 crop]
    Modes: 'R16' : 3840x2200 [22.00 fps - (0, 0)/3856x2180 crop]
"""
        modes = self._detector()._parse_cinepi_output(output, hdr=True)["imx585"]
        by_depth = {m["bit_depth"]: m for m in modes}
        self.assertIn(16, by_depth, "the RAW16 mode must survive the parse")
        self.assertTrue(by_depth[16]["hdr"])
        self.assertIn(12, by_depth)
        self.assertFalse(by_depth[12]["hdr"], "left to _normalize_hdr_probe_modes")

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

    # ── the unmarked probe, end to end (parse → normalize → merge) ──
    #
    # These two drive the same chain detect_camera_model() runs when the
    # formatter prints no CLEAR HDR marker, because the defect they cover was
    # only visible once the three steps ran together: promotion in
    # _normalize_hdr_probe_modes made every promoted mode's _mode_key unique,
    # so the collapse _merge_mode_lists was documented to perform could not
    # happen and the GUI got two rows per mode.
    def _unmarked_probe(self, plain: str, hdr_text: str):
        d = self._detector()
        base = d._parse_cinepi_output(plain, hdr=False)
        hdr = d._parse_cinepi_output(hdr_text, hdr=True)
        d._normalize_hdr_probe_modes(base, hdr)
        return base, hdr, d._merge_mode_lists(base, hdr)

    # Observed on the second dev Pi, 2026-09-21: `cinepi-raw --list-cameras`
    # and `--list-cameras --hdr sensor` are character-for-character identical
    # on the imx283, which has no ClearHDR and ignores the option. Trimmed to
    # three modes; what matters is that the two strings are the same one.
    IMX283_LISTING = """\
0 : imx283 [5568x3664 12-bit RGGB] (/base/axi/pcie@1000120000/rp1/i2c@88000/imx283@1a)
    Modes: 'SRGGB10_CSI2P' : 3936x2176 [60.16 fps - (196, 0)/3840x2160 crop; binning 1x1]
           'SRGGB12_CSI2P' : 5568x3664 [21.40 fps - (0, 0)/5472x3648 crop; binning 1x1]
                             2784x1828 [51.80 fps - (0, 0)/5472x3648 crop; binning 2x2]
"""

    def test_a_probe_identical_to_the_plain_one_contributes_no_hdr_modes(self):
        """A sensor that ignores --hdr sensor must add nothing.

        Before this, the imx283's 21 modes reached /api/sensor-modes as 42 --
        21 real plus 21 phantom rows the GUI grouped under "CLEAR HDR", on a
        sensor with no HDR at all.
        """
        base, hdr, merged = self._unmarked_probe(
            self.IMX283_LISTING, self.IMX283_LISTING,
        )
        self.assertEqual(len(base["imx283"]), 3)
        self.assertTrue(
            all(not m["hdr"] for m in hdr["imx283"]),
            "an echo of the plain listing is not evidence of a sensor state change",
        )
        self.assertEqual(len(merged["imx283"]), 3)
        self.assertTrue(all(not m["hdr"] for m in merged["imx283"]))

    def test_a_genuinely_different_hdr_listing_still_yields_hdr_modes(self):
        """The imx585 shape: ClearHDR halves the readout rate, so the same
        geometry comes back at a new ceiling, and one geometry is new outright.
        Both are evidence; the mode echoed at its SDR ceiling is not."""
        plain = """\
0 : imx585 [3856x2180 12-bit RGGB] (/base/imx585@1a)
    Modes: 'SRGGB12_CSI2P' : 1928x1090 [50.00 fps - (0, 0)/3840x2160 crop; binning 2x2]
                             3856x2180 [43.80 fps - (0, 0)/3840x2160 crop; binning 1x1]
"""
        hdr_text = """\
0 : imx585 [3856x2180 16-bit RGGB] (/base/imx585@1a)
    Modes: 'SRGGB12_CSI2P' : 1928x1090 [50.00 fps - (0, 0)/3840x2160 crop; binning 2x2]
                             3856x2180 [21.90 fps - (0, 0)/3840x2160 crop; binning 1x1]
                             2880x2160 [29.58 fps - (480, 0)/2880x2160 crop; binning 1x1]
"""
        base, hdr, merged = self._unmarked_probe(plain, hdr_text)
        by_size = {(m["width"], m["fps_max"]): m for m in hdr["imx585"]}
        self.assertFalse(by_size[(1928, 50)]["hdr"], "echoed timing is SDR")
        self.assertTrue(by_size[(3856, 21)]["hdr"], "new ceiling for a known readout")
        self.assertTrue(by_size[(2880, 29)]["hdr"], "geometry the plain probe never had")

        # Partial overlap: the echo collapses, the two real ClearHDR modes are
        # added. Killing the phantoms must not cost a real HDR mode.
        self.assertEqual(len(base["imx585"]), 2)
        self.assertEqual(len(merged["imx585"]), 4)
        self.assertEqual(
            sorted((m["width"], m["fps_max"]) for m in merged["imx585"] if m["hdr"]),
            [(2880, 29), (3856, 21)],
        )

    def test_a_repeated_readout_in_one_probe_is_the_second_state(self):
        """No marker, no repeated camera header, two ceilings for one readout:
        that is the SDR-then-ClearHDR listing with its separator missing, so
        the repeat is HDR even though the plain probe also lists that lower
        ceiling (it is the same sensor, the plain probe just enumerated both
        timings). Distinguishing this from an echo is why the comparison is
        per-mode and not "is the whole listing the same"."""
        plain = """\
0 : imx585 [3856x2180 12-bit RGGB] (/base/imx585@1a)
    Modes: 'SRGGB12_CSI2P' : 3856x2180 [43.80 fps - (0, 0)/3840x2160 crop; binning 1x1]
                             3856x2180 [21.90 fps - (0, 0)/3840x2160 crop; binning 1x1]
"""
        _, hdr, merged = self._unmarked_probe(plain, plain)
        self.assertEqual([bool(m["hdr"]) for m in hdr["imx585"]], [False, True])
        self.assertEqual(
            {(m["fps_max"], bool(m["hdr"])) for m in merged["imx585"]},
            {(43, False), (21, False), (21, True)},
        )

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
