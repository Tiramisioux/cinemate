"""A failed ClearHDR probe must be visible, not silently mode-less.

cinepi-raw 58cf8cc made ``Options::Parse()`` throw when the sensor does not
confirm ``wide_dynamic_range=1``. A thrown probe exits non-zero with an empty
stdout -- which _list_cameras used to treat as "this build has no ClearHDR",
so the ClearHDR modes disappeared from the mode table with nothing logged.
"""

import logging
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.sensor_detect import SensorDetect


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class ListCamerasProbeFailureTests(unittest.TestCase):
    def _detector(self):
        return SensorDetect.__new__(SensorDetect)

    def _run(self, proc, hdr):
        with mock.patch("module.sensor_detect.subprocess.run", return_value=proc), \
             mock.patch("module.sensor_detect.rp1_regime.pixel_rate", return_value=None), \
             self.assertLogs(level=logging.WARNING) as captured:
            out = self._detector()._list_cameras(hdr=hdr)
        return out, "\n".join(captured.output)

    def _run_expecting_silence(self, proc, hdr):
        logger = logging.getLogger()
        with mock.patch("module.sensor_detect.subprocess.run", return_value=proc), \
             mock.patch("module.sensor_detect.rp1_regime.pixel_rate", return_value=None), \
             mock.patch.object(logger, "handle") as handle:
            out = self._detector()._list_cameras(hdr=hdr)
        warned = [c for c in handle.call_args_list if c.args[0].levelno >= logging.WARNING]
        return out, warned

    def test_thrown_hdr_probe_is_logged_and_names_the_consequence(self):
        proc = _Proc(
            returncode=255,
            stdout="",
            stderr="imx585/imx708 ClearHDR: sensor did not accept wide_dynamic_range=1",
        )
        out, log = self._run(proc, hdr=True)

        # Behaviour is unchanged -- still best-effort, still "".
        self.assertEqual(out, "")
        # But the failure is now diagnosable.
        self.assertIn("exited 255", log)
        self.assertIn("wide_dynamic_range", log)
        self.assertIn("ClearHDR modes will be missing", log)

    def test_failure_is_reported_even_with_an_empty_stderr(self):
        out, log = self._run(_Proc(returncode=1), hdr=True)

        self.assertEqual(out, "")
        self.assertIn("no diagnostic on stderr", log)

    def test_plain_probe_failure_does_not_claim_a_clearhdr_cause(self):
        out, log = self._run(_Proc(returncode=1, stderr="boom"), hdr=False)

        self.assertEqual(out, "")
        self.assertIn("exited 1", log)
        self.assertNotIn("ClearHDR", log)

    def test_a_successful_probe_stays_silent(self):
        proc = _Proc(returncode=0, stdout="0 : imx585 [3840x2160]\n")
        out, warned = self._run_expecting_silence(proc, hdr=True)

        self.assertEqual(out, "0 : imx585 [3840x2160]\n")
        self.assertEqual(warned, [], "a healthy probe must not warn")

    def test_a_build_without_clearhdr_still_exits_zero_and_stays_silent(self):
        # The legitimate best-effort case the old comment described: the flag
        # is accepted, the run succeeds, it just reports no extra modes.
        proc = _Proc(returncode=0, stdout="0 : imx477 [4056x3040]\n")
        out, warned = self._run_expecting_silence(proc, hdr=True)

        self.assertEqual(out, "0 : imx477 [4056x3040]\n")
        self.assertEqual(warned, [])


if __name__ == "__main__":
    unittest.main()
