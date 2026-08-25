"""Restarting Cinemate must not kill its own web server (F-291).

os.execl() re-execs the process in place, but the Flask/SocketIO listening
socket survives exec() (it isn't marked close-on-exec) -- confirmed by a
standalone repro against real hardware (system-review/FINDINGS.md), the
re-exec'd process failed to rebind its port and the web GUI stayed dead.

restart_cinemate() now asks systemd to do a real restart instead, which
tears the whole process down first -- routed through `systemd-run` rather
than a direct `systemctl restart` because the direct form is a child of
this process, so it lives in cinemate-autostart.service's own cgroup and
gets killed by the unit's own stop signal (KillMode=control-group) before
the restart job is even queued -- also confirmed on real hardware, exiting
with returncode -2.
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


class RestartCinemateTests(unittest.TestCase):
    def controller(self):
        return CinePiController.__new__(CinePiController)

    def test_restarts_via_systemd_run_not_execl(self):
        controller = self.controller()
        with mock.patch("subprocess.run") as run, mock.patch("os.execl") as execl:
            run.return_value = types.SimpleNamespace(returncode=0, stdout="", stderr="")
            controller.restart_cinemate()

        execl.assert_not_called()
        run.assert_called_once()
        cmd = run.call_args.args[0]
        self.assertEqual(
            cmd,
            [
                "sudo", "-n", "systemd-run", "--no-block", "--collect",
                "--unit=cinemate-restart-trigger",
                "--", "systemctl", "restart", "cinemate-autostart",
            ],
        )

    def test_a_failed_restart_is_logged_not_raised(self):
        controller = self.controller()
        with mock.patch(
            "subprocess.run",
            return_value=types.SimpleNamespace(returncode=1, stdout="", stderr="sudo: a password is required"),
        ):
            controller.restart_cinemate()  # must not raise

    def test_an_unavailable_sudo_binary_is_logged_not_raised(self):
        controller = self.controller()
        with mock.patch("subprocess.run", side_effect=OSError("sudo not found")):
            controller.restart_cinemate()  # must not raise


if __name__ == "__main__":
    unittest.main()
