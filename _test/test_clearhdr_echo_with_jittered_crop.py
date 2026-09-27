"""A sensor with no ClearHDR whose two probes disagree about crop metadata.

Operator, 2026-09-27: the imx283 mode table showed every mode twice, once under
"STANDARD" and once under "CLEAR HDR", at the SAME frame rate -- 5472x2328 at
32 fps in both sections, and so on down the list.

WHY THE PER-MODE RULES COULD NOT CATCH IT
_normalize_hdr_probe_modes promotes an unmarked mode when its timing key is one
the plain probe never reported. That key includes crop_x/crop_y/crop_width/
crop_height and binning_x/binning_y, which do not come from the listing's own
text -- they come from driver controls sampled during enumeration. A probe that
fails to read them reports None for every mode, and then EVERY key differs from
the plain probe's and the entire listing is promoted, even though the printed
geometry and the printed frame rate are identical.

The fps ceiling is the thing that jitter was expected to move, and here it did
not move at all: 32 fps against 32 fps. Only the unprinted fields differed.

THE FIX THESE COVER
A whole-listing echo test that runs first and uses only the fields both probes
always have: width, height, bit depth, frame rate. No new timing means the
probe is an echo and nothing in it is ClearHDR.

It is deliberately skipped in the two cases that are genuinely ClearHDR without
a marker, so the per-mode rules still decide those:
  * the probe offers a ceiling the plain listing does not (a subset test)
  * one readout appears twice inside the probe at two ceilings, which is the
    SDR-then-ClearHDR listing with its separator missing (a repeat test, keyed
    on the readout WITHOUT fps -- keying it on fps would make the two entries
    look distinct and defeat it)
Both of those paths have their own coverage in test_clearhdr_probe_state.py;
what is new here is the echo itself.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from module.sensor_detect import SensorDetect  # noqa: E402


def _mode(w, h, fps, *, depth=12, crop=True):
    m = {"width": w, "height": h, "bit_depth": depth, "fps_max": fps, "hdr": False}
    if crop:
        m.update({"crop_x": 108, "crop_y": 40, "crop_width": 5472,
                  "crop_height": 3648, "binning_x": 1, "binning_y": 1})
    else:
        m.update({"crop_x": None, "crop_y": None, "crop_width": None,
                  "crop_height": None, "binning_x": None, "binning_y": None})
    return m


class ClearHdrEchoWithJitteredCropTests(unittest.TestCase):

    def _run(self, plain, probe):
        base = {"imx283": plain}
        hdr = {"imx283": probe}
        SensorDetect._normalize_hdr_probe_modes(base, hdr)
        return [bool(m["hdr"]) for m in hdr["imx283"]]

    def test_an_echo_whose_crop_metadata_is_missing_promotes_nothing(self):
        # THE REPORTED CASE. Same geometry, same ceiling, crop fields absent
        # from the second probe only.
        plain = [_mode(5568, 2344, 32.0), _mode(2784, 1168, 113.0)]
        probe = [_mode(5568, 2344, 32.0, crop=False),
                 _mode(2784, 1168, 113.0, crop=False)]
        self.assertEqual(
            self._run(plain, probe), [False, False],
            "a sensor that echoes its plain listing has no ClearHDR, however "
            "much the unprinted metadata differs",
        )

    def test_an_echo_with_identical_metadata_also_promotes_nothing(self):
        plain = [_mode(5568, 2344, 32.0)]
        probe = [_mode(5568, 2344, 32.0)]
        self.assertEqual(self._run(plain, probe), [False])

    def test_a_genuinely_new_ceiling_is_still_promoted(self):
        # ClearHDR halves the readout rate, so it shows up as a ceiling the
        # plain probe does not have. The echo test must not swallow this.
        plain = [_mode(5568, 2344, 32.0)]
        probe = [_mode(5568, 2344, 16.0, crop=False)]
        self.assertEqual(
            self._run(plain, probe), [True],
            "a new ceiling is evidence of a second sensor state even when the "
            "crop metadata is missing",
        )

    def test_a_readout_repeated_inside_the_probe_is_still_promoted(self):
        # The SDR-then-ClearHDR listing with no separator. Both ceilings happen
        # to appear in the plain listing too, so the subset test alone would
        # call this an echo -- the repeat test is what keeps it.
        plain = [_mode(5568, 2344, 32.0), _mode(5568, 2344, 16.0)]
        probe = [_mode(5568, 2344, 32.0), _mode(5568, 2344, 16.0)]
        self.assertEqual(self._run(plain, probe), [False, True])

    def test_an_explicit_clear_hdr_marker_always_wins(self):
        # The parser saw a CLEAR HDR section. That is evidence the echo test is
        # not entitled to override, whatever the geometry looks like.
        plain = [_mode(5568, 2344, 32.0)]
        probe = [dict(_mode(5568, 2344, 32.0), hdr=True)]
        self.assertEqual(self._run(plain, probe), [True])


if __name__ == "__main__":
    unittest.main()
