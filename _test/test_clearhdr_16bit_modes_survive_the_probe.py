"""The 16-bit ClearHDR modes must survive the two cinepi-raw probes.

Observed on the dev Pi, 2026-09-25, on CineMate `dev` with the cinemate-modes
imx585 driver: every 12-bit ClearHDR row was in the settings pane and every
16-bit ClearHDR row was missing. The driver enumerated all fifteen RAW16
sizes; the parser threw them away.

How: cinepi-raw (core/options.cpp, print_modes) prints a two-state listing on
every --list-cameras run -- the SDR modes, then the literal
``CLEAR HDR / SENSOR HDR`` marker, then the same cameras again in the ClearHDR
state, 16-bit block first. detect_camera_model() found the marker and parsed
the section after it with the parser in the SDR state, re-tagging the
survivors as HDR afterwards. The parser dropped every 16-bit line it met in
the SDR state ("RAW16 is ClearHDR-only, do not expose it as SDR"), so nothing
16-bit ever reached the re-tag, while the 12-bit lines were never dropped and
came out as the 12-bit ClearHDR rows the pane did show. The unmarked path had
the same hole: the 16-bit block prints before any repeated header could flip
the state.

The contract these tests pin:

* a 16-bit line is ClearHDR wherever the parser meets it -- the imx585 driver
  enumerates RAW16 only with wide_dynamic_range on, so the line is evidence of
  the state by itself -- and is never dropped;
* the section after the marker is parsed IN the ClearHDR state
  (``clear_hdr_section=True``), not re-tagged after the fact;
* the plain probe is the SDR state only: it stops at the marker instead of
  filing the ClearHDR state's 12-bit timings as SDR duplicates.
"""

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.sensor_detect import CLEAR_HDR_MARKER_RE, SensorDetect

# What cinepi-raw `dev` prints, trimmed to four sizes per format. The same
# text comes back from the plain run and from the --hdr sensor run: in list
# mode the flag is ignored and both states are always printed. The
# `; binning NxN; mode-crop (l,t)/WxH` tail is the driver's own geometry
# (core/driver_mode_metadata.hpp), the `(x, y)/WxH crop` before it is
# libcamera's ScalerCropMaximum; on the cinemate-modes driver they agree.
SDR_SECTION = """\
Available cameras
-----------------
0 : imx585 [3856x2180 12-bit RGGB] (/base/axi/pcie@1000120000/rp1/i2c@88000/imx585@1a)
    Modes: 'SRGGB10_CSI2P' : 1920x1080 [90.00 fps - (0, 0)/3840x2160 crop; binning 2x2; mode-crop (0,0)/3840x2160]
                             3840x2160 [90.00 fps - (0, 0)/3840x2160 crop; binning 1x1; mode-crop (0,0)/3840x2160]
           'SRGGB12_CSI2P' : 1920x1080 [69.00 fps - (0, 0)/3840x2160 crop; binning 2x2; mode-crop (0,0)/3840x2160]
                             2880x2160 [43.80 fps - (480, 0)/2880x2160 crop; binning 1x1; mode-crop (480,0)/2880x2160]
                             3840x1608 [58.00 fps - (0, 276)/3840x1608 crop; binning 1x1; mode-crop (0,276)/3840x1608]
                             3840x2160 [43.80 fps - (0, 0)/3840x2160 crop; binning 1x1; mode-crop (0,0)/3840x2160]

"""

CLEARHDR_SECTION = """\
    CLEAR HDR / SENSOR HDR
0 : imx585 [3856x2180 16-bit RGGB] (/base/axi/pcie@1000120000/rp1/i2c@88000/imx585@1a)
    Modes: 'SRGGB16' : 1920x1100 [30.00 fps - (0, 0)/3840x2160 crop; binning 2x2; mode-crop (0,0)/3840x2160]
                       2880x2200 [21.90 fps - (480, 0)/2880x2160 crop; binning 1x1; mode-crop (480,0)/2880x2160]
                       3840x1648 [29.00 fps - (0, 276)/3840x1608 crop; binning 1x1; mode-crop (0,276)/3840x1608]
                       3840x2200 [21.90 fps - (0, 0)/3840x2160 crop; binning 1x1; mode-crop (0,0)/3840x2160]
           'SRGGB12_CSI2P' : 1920x1080 [34.00 fps - (0, 0)/3840x2160 crop; binning 2x2; mode-crop (0,0)/3840x2160]
                             2880x2160 [21.90 fps - (480, 0)/2880x2160 crop; binning 1x1; mode-crop (480,0)/2880x2160]
                             3840x1608 [29.00 fps - (0, 276)/3840x1608 crop; binning 1x1; mode-crop (0,276)/3840x1608]
                             3840x2160 [21.90 fps - (0, 0)/3840x2160 crop; binning 1x1; mode-crop (0,0)/3840x2160]

"""

TWO_STATE_LISTING = SDR_SECTION + CLEARHDR_SECTION

# An older cinepi-raw (its `main`): --hdr sensor switches the sensor before
# the one and only listing, so the probe is a single section with no marker,
# 16-bit block first, and the plain probe is a different listing.
SINGLE_SECTION_HDR_LISTING = CLEARHDR_SECTION.replace("    CLEAR HDR / SENSOR HDR\n", "")

SIXTEEN_BIT_SIZES = {(1920, 1100), (2880, 2200), (3840, 1648), (3840, 2200)}
TWELVE_BIT_SIZES = {(1920, 1080), (2880, 2160), (3840, 1608), (3840, 2160)}


def _detector():
    """A SensorDetect with every settings.jsonc filter set to 'no opinion',
    so what comes out of detect_camera_model() is what the parser kept."""
    d = SensorDetect.__new__(SensorDetect)
    d.settings = {}
    d.custom_modes = {}
    d.bit_depths = []
    d.k_steps = []
    d.hdr_modes = []
    d.clear_hdr_depths = None
    d.aspect_ratios_cfg = None
    d.min_mode_width = None
    d.enabled_modes = {}
    d.sensor_database = {"sensors": {}}
    d.packing_info = {}
    d.sensor_modes_unfiltered = {}
    d.sensor_resolutions = {}
    d.camera_model = None
    d.res_modes = {}
    d._kill_stale_cinepi_raw = lambda *a, **k: None
    return d


def _detect(plain: str, hdr_text: str):
    d = _detector()
    d._list_cameras = lambda hdr=False: hdr_text if hdr else plain
    d.detect_camera_model()
    return d


def _shape(modes):
    return sorted(
        (m["width"], m["height"], m["bit_depth"], bool(m.get("hdr")), m.get("fps_max"))
        for m in modes
    )


class ParserStateTests(unittest.TestCase):
    def test_a_16bit_line_is_clearhdr_wherever_the_parser_meets_it(self):
        """No marker, no repeated header, hdr=True: the parser has no state
        evidence for the 12-bit line (that is _normalize_hdr_probe_modes'
        decision, from timings), but the 16-bit lines are evidence on their
        own. They used to be dropped here."""
        modes = _detector()._parse_cinepi_output(SINGLE_SECTION_HDR_LISTING, hdr=True)["imx585"]
        sixteen = {(m["width"], m["height"]) for m in modes if m["bit_depth"] == 16}
        self.assertEqual(sixteen, SIXTEEN_BIT_SIZES)
        self.assertTrue(all(m["hdr"] for m in modes if m["bit_depth"] == 16))
        # The 12-bit lines are still parsed, and still left to the timing
        # comparison: the parser does not guess their state.
        self.assertEqual({(m["width"], m["height"]) for m in modes if m["bit_depth"] == 12},
                         TWELVE_BIT_SIZES)

    def test_a_16bit_line_in_a_plain_parse_is_kept_and_tagged(self):
        """Even with hdr=False -- RAW16 cannot be SDR on this sensor, so a
        line that says RAW16 is not "a false STANDARD 16-BIT mode", it is a
        ClearHDR mode the formatter printed without a marker."""
        modes = _detector()._parse_cinepi_output(SINGLE_SECTION_HDR_LISTING, hdr=False)["imx585"]
        sixteen = [m for m in modes if m["bit_depth"] == 16]
        self.assertEqual(len(sixteen), 4)
        self.assertTrue(all(m["hdr"] for m in sixteen))

    def test_a_pre_cut_clearhdr_section_is_parsed_in_the_clearhdr_state(self):
        """What detect_camera_model() hands the parser after the marker: the
        whole section is ClearHDR, 16-bit and 12-bit alike, with no re-tag
        afterwards."""
        section = TWO_STATE_LISTING[CLEAR_HDR_MARKER_RE.search(TWO_STATE_LISTING).end():]
        modes = _detector()._parse_cinepi_output(section, hdr=True, clear_hdr_section=True)["imx585"]
        self.assertEqual(len(modes), 8)
        self.assertTrue(all(m["hdr"] for m in modes))
        self.assertEqual({(m["width"], m["height"]) for m in modes if m["bit_depth"] == 16},
                         SIXTEEN_BIT_SIZES)

    def test_the_plain_probe_stops_at_the_marker(self):
        """cinepi-raw prints the ClearHDR section on every run. A plain
        parse must not read the ClearHDR state's 12-bit timings back as SDR
        modes at half the ceiling."""
        modes = _detector()._parse_cinepi_output(TWO_STATE_LISTING, hdr=False)["imx585"]
        self.assertEqual(len(modes), 6)
        self.assertTrue(all(not m["hdr"] for m in modes))
        self.assertEqual({m["fps_max"] for m in modes if (m["width"], m["height"]) == (3840, 2160)},
                         {90, 43})

    def test_the_marker_regex_is_the_one_cinepi_raw_prints(self):
        self.assertIsNotNone(CLEAR_HDR_MARKER_RE.search("    CLEAR HDR / SENSOR HDR"))
        self.assertIsNone(CLEAR_HDR_MARKER_RE.search("0 : imx585 [3856x2180 16-bit RGGB]"))


class EndToEndTests(unittest.TestCase):
    """detect_camera_model() with both probes stubbed to what the Pi prints."""

    def test_two_state_listing_keeps_every_16bit_clearhdr_mode(self):
        """The case on the rig: both probes return the two-state listing."""
        d = _detect(TWO_STATE_LISTING, TWO_STATE_LISTING)
        table = d.sensor_modes_unfiltered["imx585"]
        sixteen = {(m["width"], m["height"]) for m in table if m["bit_depth"] == 16}
        self.assertEqual(sixteen, SIXTEEN_BIT_SIZES)
        self.assertTrue(all(m["hdr"] for m in table if m["bit_depth"] == 16))

    def test_two_state_listing_keeps_the_12bit_clearhdr_modes_too(self):
        d = _detect(TWO_STATE_LISTING, TWO_STATE_LISTING)
        table = d.sensor_modes_unfiltered["imx585"]
        twelve_hdr = {(m["width"], m["height"]): m["fps_max"]
                      for m in table if m["bit_depth"] == 12 and m["hdr"]}
        self.assertEqual(set(twelve_hdr), TWELVE_BIT_SIZES)
        self.assertEqual(twelve_hdr[(3840, 2160)], 21)

    def test_two_state_listing_files_no_sdr_duplicates_at_clearhdr_ceilings(self):
        """Before the plain probe stopped at the marker, the 12-bit ClearHDR
        timings were also read as SDR, and dedup then had to paper over the
        pair. Now the SDR side is exactly the SDR section."""
        d = _detect(TWO_STATE_LISTING, TWO_STATE_LISTING)
        table = d.sensor_modes_unfiltered["imx585"]
        sdr = _shape(m for m in table if not m["hdr"])
        self.assertEqual(sdr, [
            (1920, 1080, 10, False, 90),
            (1920, 1080, 12, False, 69),
            (2880, 2160, 12, False, 43),
            (3840, 1608, 12, False, 58),
            (3840, 2160, 10, False, 90),
            (3840, 2160, 12, False, 43),
        ])
        self.assertEqual(len(table), 14)
        self.assertEqual(len(d.res_modes), 14)

    def test_single_section_hdr_probe_keeps_every_16bit_clearhdr_mode(self):
        """The older cinepi-raw shape: plain probe is SDR only, --hdr sensor
        probe is one unmarked ClearHDR listing."""
        d = _detect(SDR_SECTION, SINGLE_SECTION_HDR_LISTING)
        table = d.sensor_modes_unfiltered["imx585"]
        sixteen = {(m["width"], m["height"]) for m in table if m["bit_depth"] == 16}
        self.assertEqual(sixteen, SIXTEEN_BIT_SIZES)
        self.assertTrue(all(m["hdr"] for m in table if m["bit_depth"] == 16))
        # ...and the 12-bit ClearHDR modes are still promoted by their new,
        # lower ceilings, as before.
        twelve_hdr = {(m["width"], m["height"]) for m in table if m["bit_depth"] == 12 and m["hdr"]}
        self.assertEqual(twelve_hdr, TWELVE_BIT_SIZES)
        self.assertEqual(len(table), 14)


if __name__ == "__main__":
    unittest.main()
