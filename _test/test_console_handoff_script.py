"""cinemate-console-handoff.sh: unprivileged systemctl unit-start calls must
run under `sudo -n`.

F-283: reproduced on hardware with `timeout 10 bash -x` on the installed
script -- as user `pi`, `systemctl start <unit>` triggers a PolicyKit
"AUTHENTICATING FOR org.freedesktop.systemd1.manage-units" prompt with no
tty to answer it. It blocks until systemd kills this ExecStopPost step at
TimeoutStopSec and the unit lands failed instead of restarting. `pi` has
passwordless sudo, so running as root skips the prompt entirely; `-n`
guarantees a fast failure instead of a hang if that sudoers rule is ever
tightened. This closes the hang/failed symptom, verified on hardware across
many restarts.

A separate, narrower race is still open (not covered by this test):
Conflicts=getty@tty1.service on the unit can occasionally collide with the
start half of an in-flight `systemctl restart`, leaving the unit inactive
instead of active (not failed/hung). See the longer comment in the script
itself for the four mitigations tried and rejected.
"""

import re
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "services"
    / "cinemate-autostart"
    / "cinemate-console-handoff.sh"
)


class ConsoleHandoffScriptTest(unittest.TestCase):
    def setUp(self):
        self.text = SCRIPT.read_text()

    def test_every_systemctl_start_runs_under_sudo_n(self):
        for line in self.text.splitlines():
            if line.lstrip().startswith("#"):
                continue
            if re.search(r"\bsystemctl\b.*\bstart\b", line):
                self.assertIn(
                    "sudo -n",
                    line,
                    f"unprivileged 'systemctl start' hangs on a PolicyKit "
                    f"prompt in ExecStopPost (F-283): {line!r}",
                )

    def test_no_bare_sudo_without_noninteractive_flag(self):
        for line in self.text.splitlines():
            if "sudo " in line and "sudo -n" not in line:
                self.fail(f"sudo without -n can block on a password prompt: {line!r}")


if __name__ == "__main__":
    unittest.main()
