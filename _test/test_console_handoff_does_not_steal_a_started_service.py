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


class OnlyOneGettyStarterUnderSystemdTests(unittest.TestCase):
    """Two things started a getty on tty1 during a stop; only one can judge it.

    main.py's restore_local_console_prompt() runs while the unit is still
    "deactivating", so it cannot tell a plain stop from a restart -- and it
    then sleeps 2.5 s inside a 5 s TimeoutStopSec holding that decision open,
    which is ample for the next instance to come up behind it and be stopped
    by the conflict. It also has no sudoers grant, so under systemd its
    privileged form fails and only the unprivileged fallback ever did
    anything.

    The ExecStopPost script can judge it: it runs as root, after this process
    is gone, and checks whether CineMate is back before taking the console.
    So under systemd it is the only one that runs. Outside systemd -- the
    `cinemate` shell command this function was written for -- there is no
    ExecStopPost and no conflicting unit, and it stays.
    """

    def test_cleanup_skips_the_console_restore_under_systemd(self):
        src = (ROOT / "src/main.py").read_text(encoding="utf-8")
        guard = ("if not shutdown_in_progress and not "
                 "running_under_systemd_service():")
        self.assertIn(guard, src)
        after = src[src.index(guard) + len(guard):src.index(guard) + len(guard) + 120]
        self.assertIn("restore_local_console_prompt()", after)

    def test_it_still_runs_outside_systemd(self):
        # The guard must be the systemd predicate, not a blanket removal:
        # `cinemate` from an SSH session still has to hand the console back.
        src = (ROOT / "src/main.py").read_text(encoding="utf-8")
        self.assertIn("def restore_local_console_prompt()", src)
        self.assertIn("running_under_systemd_service()", src)


if __name__ == "__main__":
    unittest.main()
