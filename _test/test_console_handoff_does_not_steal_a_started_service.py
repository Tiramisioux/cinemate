"""The console handoff must not take tty1 back from a CineMate that is up.

Observed on the rig, restarting from the settings page. Whole sequence inside
one second, with the service fully started -- "Initialization Complete", Flask
serving, systemd's own "Started":

    systemd[1]: Started cinemate-autostart.service
    sudo[5736]: root : COMMAND=/bin/systemctl --job-mode=fail start getty@tty1
    systemd[1]: cinemate-autostart.service: Deactivated successfully.
    systemd[1]: Stopped cinemate-autostart.service

Deactivated *successfully*: not a crash, not the camera-ready gate, not a
SIGHUP. cinemate-autostart declares Conflicts=getty@tty1.service, so starting
a getty means stopping CineMate, and systemd did precisely that -- to the
instance it had just finished starting. The operator lands at a shell prompt
and starting again works, because the second time there is no stale
ExecStopPost still in flight.

--job-mode=fail does not cover this. It refuses while a start job for the
conflicting unit is PENDING; here the start had already completed, so there
was no job left to refuse. The state check is what closes it.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "services/cinemate-autostart/cinemate-console-handoff.sh"
UNIT = ROOT / "services/cinemate-autostart/cinemate-autostart.service"


class HandoffGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = SCRIPT.read_text(encoding="utf-8")

    def _code(self):
        """The script minus comments -- prose about the bug is not the fix."""
        return "\n".join(l for l in self.src.split("\n")
                         if not l.lstrip().startswith("#"))

    def test_it_asks_whether_cinemate_is_already_running(self):
        code = self._code()
        self.assertIn("is-active cinemate-autostart.service", code)

    def test_active_and_activating_both_stop_it(self):
        # "activating" matters as much as "active": the start half can still
        # be in progress when this runs, and taking the console then loses the
        # same race one moment earlier.
        code = self._code()
        for state in ("active", "activating"):
            with self.subTest(state=state):
                self.assertRegex(code, rf'"\$\{{state\}}" == "{state}"')

    def test_the_check_comes_before_the_getty_start(self):
        code = self._code()
        self.assertLess(code.index("is-active cinemate-autostart.service"),
                        code.index("start getty@tty1.service"),
                        "the guard has to run before the thing it guards")

    def test_job_mode_fail_is_still_there(self):
        # Belt and braces: it still covers the pending-job case, which is the
        # earlier and more common half of the same race.
        self.assertIn("--job-mode=fail", self._code())

    def test_the_conflict_this_guards_still_exists(self):
        # If Conflicts= ever goes, this guard's reason goes with it -- and the
        # script's own history says removing it breaks worse.
        self.assertIn("Conflicts=getty@tty1.service", UNIT.read_text(encoding="utf-8"))

    def test_the_shutdown_path_is_untouched(self):
        # A real shutdown must still hand off to plymouth; the new guard sits
        # after that branch, not in front of it.
        code = self._code()
        self.assertLess(code.index("plymouth-start.service"),
                        code.index("is-active cinemate-autostart.service"))


if __name__ == "__main__":
    unittest.main()
