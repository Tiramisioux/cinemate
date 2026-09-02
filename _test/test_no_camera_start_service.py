import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CameraReadyGateNonFatalTests(unittest.TestCase):
    """C3.4: a failed camera-ready.sh gate must not fail the unit -- the `-`
    prefix on ExecStartPre makes the gate advisory (still waits/logs, no
    longer vetoes startup) so main.py is reached with no camera."""

    def test_exec_start_pre_camera_ready_is_non_fatal(self):
        unit = (
            ROOT / "services" / "cinemate-autostart" / "cinemate-autostart.service"
        ).read_text()
        lines = [
            ln.strip()
            for ln in unit.splitlines()
            if "camera-ready.sh" in ln and not ln.lstrip().startswith("#")
        ]
        self.assertTrue(lines, "expected an ExecStartPre line running camera-ready.sh")
        for line in lines:
            with self.subTest(line=line):
                self.assertTrue(
                    line.startswith("ExecStartPre=-"),
                    f"expected the '-' non-fatal prefix, got: {line!r}",
                )

    def test_makefile_install_target_copies_this_service_file(self):
        # The root Makefile is what cinemate-install.sh invokes
        # (`sudo make -C "$CINEMATE_SOURCE_DIR" install`), so this is the
        # path existing Pis need to re-run to pick up the ExecStartPre
        # change: `sudo make install` + `sudo systemctl daemon-reload`.
        makefile = (ROOT / "Makefile").read_text()
        install_target = makefile.split("install:", 1)[1].split("\n\n", 1)[0]
        self.assertIn(
            "sudo install -m 644 $(LOCAL_SERVICE_FILE) $(SERVICE_FILE_PATH)",
            install_target,
        )
        self.assertIn("sudo systemctl daemon-reload", install_target)


class CameraReadyGateTimeoutTests(unittest.TestCase):
    """D7: with the gate advisory, a missing camera is a supported state, so
    the wait is a boot-time cost with no payoff once a slow sensor has had
    long enough. Kept, but shortened from 30 s (system-review F-236)."""

    SCRIPT = ROOT / "services" / "cinemate-autostart" / "camera-ready.sh"

    def _setting(self, name):
        match = re.search(
            rf"^readonly {name}=(\d+)", self.SCRIPT.read_text(), re.MULTILINE
        )
        self.assertIsNotNone(match, f"{name} not found in camera-ready.sh")
        return int(match.group(1))

    def test_the_gate_still_exists(self):
        # It fixed a real black-screen-on-boot race with slow sensors.
        # Shortening it is not the same as dropping it.
        self.assertGreater(self._setting("MAX_ATTEMPTS"), 0)

    def test_the_no_camera_boot_penalty_is_at_most_ten_seconds(self):
        penalty = self._setting("MAX_ATTEMPTS") * self._setting("RETRY_INTERVAL")
        self.assertLessEqual(penalty, 10)

    def test_the_timeout_message_says_cinemate_starts_anyway(self):
        # The old message said "Cinemate may start with black screen", which
        # predates C3.4 and now contradicts the actual behaviour.
        text = self.SCRIPT.read_text()
        self.assertIn("Cinemate will start anyway", text)
        self.assertNotIn("Cinemate may start with black screen", text)


if __name__ == "__main__":
    unittest.main()
