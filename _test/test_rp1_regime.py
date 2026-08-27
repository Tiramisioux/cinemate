"""The pixel-rate ceiling must never be over-stated.

Under-stating it makes the IPA pad the line length further: slower, nothing
else. Over-stating it overruns the CSI2-to-ISP-FE FIFO mid-line and corrupts
every mode wide enough for the bound to be what limits the line time -- with
nothing logged anywhere, because the one warning on that path fires when the
*sensor* cannot supply enough blanking, which a too-high rate makes less likely
to trigger, not more.

So every ambiguous case here has to resolve downward. The case that matters
most is a config.txt with the overlay enabled on a board that has not rebooted
yet: stated intent says 580, the hardware is still running stock, and believing
the file would corrupt wide modes silently.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("psutil", types.SimpleNamespace())

from module import rp1_regime


ENABLED = "dtparam=audio=on\ndtoverlay=rp1-overclock\n"
COMMENTED = "dtparam=audio=on\n#dtoverlay=rp1-overclock\n"
ABSENT = "dtparam=audio=on\n"

STOCK_HZ = 200_000_000
OVERCLOCKED_HZ = 333_333_333          # what the 300MHz overlay actually yields


class OverlayDetectionTests(unittest.TestCase):
    def test_an_uncommented_line_is_enabled(self):
        self.assertTrue(rp1_regime.overlay_enabled(ENABLED))

    def test_a_commented_line_is_not(self):
        self.assertFalse(rp1_regime.overlay_enabled(COMMENTED))

    def test_an_absent_line_is_not(self):
        self.assertFalse(rp1_regime.overlay_enabled(ABSENT))


class PixelRateTests(unittest.TestCase):
    def _rate(self, config_txt, measured, rp1=True):
        with mock.patch.object(rp1_regime, "is_rp1_platform", return_value=rp1), \
             mock.patch.object(rp1_regime, "overlay_enabled",
                               return_value=rp1_regime.overlay_enabled(config_txt)), \
             mock.patch.object(rp1_regime, "measured_clk_sys_hz", return_value=measured):
            return rp1_regime.pixel_rate()

    def test_boards_without_an_rp1_get_no_ceiling_at_all(self):
        # vc4 carries an unconstrained bound in libcamera; passing a number
        # would invent a limit that does not exist.
        self.assertIsNone(self._rate(ENABLED, OVERCLOCKED_HZ, rp1=False))

    def test_overlay_on_and_clock_raised_gives_the_overclocked_rate(self):
        self.assertEqual(self._rate(ENABLED, OVERCLOCKED_HZ), rp1_regime.PIXEL_RATE_OVERCLOCKED)

    def test_overlay_off_gives_the_stock_rate(self):
        self.assertEqual(self._rate(COMMENTED, STOCK_HZ), rp1_regime.PIXEL_RATE_STOCK)

    def test_overlay_on_but_not_rebooted_yet_is_vetoed_down_to_stock(self):
        # The dangerous case, and the whole reason the live clock is consulted.
        self.assertEqual(self._rate(ENABLED, STOCK_HZ), rp1_regime.PIXEL_RATE_STOCK)

    def test_an_unreadable_clock_still_honours_the_switch(self):
        # debugfs needs root and sudo may be unavailable; the operator's stated
        # intent stands rather than the feature silently doing nothing.
        self.assertEqual(self._rate(ENABLED, None), rp1_regime.PIXEL_RATE_OVERCLOCKED)

    def test_the_threshold_accepts_the_rate_the_overlay_actually_produces(self):
        # The overlay asks for 300MHz; the hardware lands on 333.33MHz. An
        # equality test against 300000000 would veto every real overclock.
        self.assertGreater(OVERCLOCKED_HZ, rp1_regime.OVERCLOCK_CLK_THRESHOLD_HZ)
        self.assertLess(STOCK_HZ, rp1_regime.OVERCLOCK_CLK_THRESHOLD_HZ)
        self.assertEqual(self._rate(ENABLED, 300_000_000), rp1_regime.PIXEL_RATE_OVERCLOCKED)

    def test_the_overclocked_rate_is_the_higher_one(self):
        self.assertGreater(rp1_regime.PIXEL_RATE_OVERCLOCKED, rp1_regime.PIXEL_RATE_STOCK)


class ClockParsingTests(unittest.TestCase):
    SUMMARY = (
        "    pll_sys        2  2  0  333333333  0  0  50000  Y  deviceless\n"
        "       clk_sys     5  5  0  333333333  0  0  50000  Y  1f00088000.i2c\n"
    )

    def test_the_rate_column_is_read_not_the_use_counts(self):
        with mock.patch.object(rp1_regime.subprocess, "run") as run:
            run.return_value = types.SimpleNamespace(returncode=0, stdout=self.SUMMARY)
            self.assertEqual(rp1_regime.measured_clk_sys_hz(), 333333333)

    def test_a_failed_read_is_not_an_error(self):
        with mock.patch.object(rp1_regime.subprocess, "run") as run:
            run.return_value = types.SimpleNamespace(returncode=1, stdout="")
            self.assertIsNone(rp1_regime.measured_clk_sys_hz())

    def test_a_missing_sudo_is_not_an_error(self):
        with mock.patch.object(rp1_regime.subprocess, "run", side_effect=OSError):
            self.assertIsNone(rp1_regime.measured_clk_sys_hz())


if __name__ == "__main__":
    unittest.main()
