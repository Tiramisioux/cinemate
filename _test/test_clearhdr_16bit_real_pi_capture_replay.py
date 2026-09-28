"""Gate 3 of the clearhdr16-visibility-closeout: replay the operator's own
2026-09-20 Pi capture through current `dev`, with the shipped settings.jsonc,
and confirm the 16-bit Clear HDR modes survive.

This is not a synthetic fixture like test_clearhdr_16bit_modes_survive_the_probe.py
(that one pins the parser's state-machine contract with trimmed listings).
This one is the actual offline reproduction the closeout brief called for: the
real `cinepi-raw --list-cameras` / `--list-cameras --hdr sensor` stdout the
operator captured from their own Pi on 2026-09-20 --
development/todo-2026-09-20/captures/{plain,hdr}-probe-extracted.txt, one
directory above this repo -- fed through SensorDetect.detect_camera_model()
exactly as a real boot would, with the real, shipped settings.jsonc (not a
hand-built settings dict), stubbing out only the two things that touch the
OS: killing a stale cinepi-raw process and running the two probes themselves.

At the time of that capture the live API returned `available.bit_depths:
[10, 12]` and not one 16-bit row in 31 -- consistent with a parse-time drop
of every 16-bit line. The numbers pinned below (PARSED counts by
(bit_depth, hdr), and the four 16-bit rows that survive _finalize_modes) are
exactly what was recorded in RESULTS.md after fix 0e6899e7 landed. If this
test ever goes red, the fix has regressed for the exact capture that first
exposed the bug.
"""

import sys
import types
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.config_loader import load_settings
from module.sensor_detect import SensorDetect

CAPTURES = ROOT.parent / "development" / "todo-2026-09-20" / "captures"
PLAIN_CAPTURE = CAPTURES / "plain-probe-extracted.txt"
HDR_CAPTURE = CAPTURES / "hdr-probe-extracted.txt"

SIXTEEN_BIT_ROWS = {
    # (width, height): (binning_x, fps_max)
    #
    # The stock rule of 2026-09-28 (1.33:1 and 1.78:1 where offered plus the
    # full frame, 1x1 modes only) decides which of the four enumerated 16-bit
    # sizes open selected. The binned 1920x1100 (2x2) is no longer stock --
    # it is still parsed (see the PARSED counts above) and one tick away in
    # the settings page -- and the 1x1 2880x2200 crop, a 1.33:1 shape, now is.
    (3840, 2200): (1, 21),
    (2880, 2200): (1, 29),
    (1920, 1120): (1, 57),
    (1280, 760): (1, 83),
}


@unittest.skipUnless(
    PLAIN_CAPTURE.is_file() and HDR_CAPTURE.is_file(),
    "development/todo-2026-09-20/captures/ not present next to this checkout",
)
class ClearHdr16BitRealPiCaptureReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plain_text = PLAIN_CAPTURE.read_text(encoding="utf-8")
        cls.hdr_text = HDR_CAPTURE.read_text(encoding="utf-8")
        cls.settings = load_settings(str(ROOT / "settings.jsonc"))

    def _detect(self):
        plain_text, hdr_text = self.plain_text, self.hdr_text

        class ReplayedSensorDetect(SensorDetect):
            def _kill_stale_cinepi_raw(self, timeout: float = 3.0) -> None:
                pass

            def _list_cameras(self, hdr: bool = False) -> str:
                return hdr_text if hdr else plain_text

        return ReplayedSensorDetect(settings=self.settings)

    def test_parsed_counts_match_the_recorded_replay(self):
        """PARSED: {(10,False):10, (12,False):10, (12,True):10, (16,True):10}
        -- the pre-filter table, before k_steps/bit_depths/hdr whitelists
        narrow it. All four 16-bit ClearHDR sizes the driver enumerated must
        come through; none dropped at parse."""
        d = self._detect()
        unfiltered = d.sensor_modes_unfiltered["imx585"]
        counts = Counter((m["bit_depth"], bool(m["hdr"])) for m in unfiltered)
        self.assertEqual(
            counts,
            Counter({(10, False): 10, (12, False): 10, (12, True): 10, (16, True): 10}),
        )

    def test_finalized_table_offers_four_16bit_clearhdr_modes(self):
        """AFTER _finalize_modes, with the shipped settings.jsonc
        (imx585_clear_hdr_16bit: true, imx585_clear_hdr_12bit: false,
        k_steps [1.5, 2, 3, 4], bit_depths [10, 12, 16]) and the per-sensor
        stock rule (1.33:1 + 1.78:1 + full frame, 1x1 only): 10 modes total,
        four of them 16-bit Clear HDR, at the sizes/fps the operator's Pi
        actually reported."""
        d = self._detect()
        self.assertEqual(d.camera_model, "imx585")
        final = d.sensor_resolutions["imx585"]
        self.assertEqual(len(final), 10)

        sixteen = {
            (m["width"], m["height"]): (m.get("binning_x"), m.get("fps_max"))
            for m in final.values()
            if m["bit_depth"] == 16
        }
        self.assertEqual(sixteen, SIXTEEN_BIT_ROWS)
        self.assertTrue(all(
            m["hdr"] for m in final.values() if m["bit_depth"] == 16
        ))

    def test_no_12bit_clearhdr_leaks_through_with_the_shipped_default(self):
        """image_capture.hdr.imx585_clear_hdr_12bit ships false -- the
        12-bit ClearHDR rows the parser correctly kept must still be
        filtered out of the finalized table, same as before this fix."""
        d = self._detect()
        final = d.sensor_resolutions["imx585"]
        twelve_bit_hdr = [m for m in final.values() if m["bit_depth"] == 12 and m["hdr"]]
        self.assertEqual(twelve_bit_hdr, [])


if __name__ == "__main__":
    unittest.main()
