"""_set_wide_dynamic_range() must retry before giving up.

It races the outgoing cinepi-raw process's teardown -- confirmed on hardware
(round 6): the identical `v4l2-ctl --set-ctrl wide_dynamic_range=1` succeeds
standalone with no process contention, yet logged "no subdev accepted" on
effectively every resolution change all session, because it never retried a
transient failure.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.cinepi_controller import CinePiController


def make_controller():
    return CinePiController.__new__(CinePiController)


class WideDynamicRangeRetryTests(unittest.TestCase):
    def test_retries_and_succeeds_after_a_transient_failure(self):
        c = make_controller()
        attempts = {"n": 0}

        # Exactly one subdev exists, so each OUTER retry attempt makes exactly
        # one subprocess.run call. Before the fix, attempts["n"] could also be
        # driven past 3 by the inner 16-subdev loop alone (with every subdev
        # reporting "exists"), letting this test pass without the outer retry
        # loop ever running more than once.
        with mock.patch(
            "module.cinepi_controller.os.path.exists",
            side_effect=lambda p: p == "/dev/v4l-subdev0",
        ):

            def fake_run(cmd, capture_output, text):
                attempts["n"] += 1
                ok = attempts["n"] >= 3  # fails twice, then succeeds
                return types.SimpleNamespace(
                    returncode=0 if ok else 1,
                    stderr="" if ok else "Device or resource busy",
                )

            with mock.patch("module.cinepi_controller.subprocess.run", side_effect=fake_run), \
                 mock.patch("module.cinepi_controller.time.sleep"):
                result = c._set_wide_dynamic_range(True)

        self.assertTrue(result)
        self.assertEqual(attempts["n"], 3)

    def test_gives_up_after_exhausting_retries(self):
        c = make_controller()

        def fake_run(cmd, capture_output, text):
            return types.SimpleNamespace(returncode=1, stderr="Device or resource busy")

        with mock.patch("module.cinepi_controller.os.path.exists", return_value=True), \
             mock.patch("module.cinepi_controller.subprocess.run", side_effect=fake_run), \
             mock.patch("module.cinepi_controller.time.sleep") as mock_sleep, \
             mock.patch("module.cinepi_controller.logging.warning") as mock_warn:
            result = c._set_wide_dynamic_range(True)

        self.assertFalse(result)
        self.assertTrue(mock_sleep.called)
        mock_warn.assert_called_once()

    def test_all_subdevs_reporting_unknown_control_is_reported_not_silent(self):
        """No imx585 driver bound at all -- every subdev says "unknown
        control" -- is the one unambiguously genuine failure. last_errors is
        reset at the top of every attempt and only ever collects non-"unknown
        control" errors, so this case must not fall through silently: the
        pre-retry code logged it, and this must too.
        """
        c = make_controller()

        def fake_run(cmd, capture_output, text):
            return types.SimpleNamespace(returncode=1, stderr="unknown control 'wide_dynamic_range'")

        with mock.patch("module.cinepi_controller.os.path.exists", return_value=True), \
             mock.patch("module.cinepi_controller.subprocess.run", side_effect=fake_run), \
             mock.patch("module.cinepi_controller.time.sleep"), \
             mock.patch("module.cinepi_controller.logging.warning") as mock_warn:
            result = c._set_wide_dynamic_range(True)

        self.assertFalse(result)
        mock_warn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
