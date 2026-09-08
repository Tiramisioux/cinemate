"""A restart must not be mistaken for a stop when handing back tty1.

The failure that survived both earlier fixes. Pressing "Restart Cinemate" in
the settings editor, off the rig:

    02:53:47.995  Stopping cinemate-autostart.service...
    02:53:50.082  sudo root: systemctl --job-mode=fail start getty@tty1.service
    02:53:50.092  Starting cinemate-autostart.service...
    02:53:55.898  Started cinemate-autostart.service       <- fully up
    02:53:55.916  Started getty@tty1.service               <- +18 ms
    02:53:55.978  cinemate-autostart.service: Deactivated successfully.

The getty start is right when it is asked for and wrong when it is run.
cinemate-autostart declares Before=getty@tty1.service, so systemd parks that
job behind the unit's own start job and releases it the moment the new
instance is up -- and Conflicts=getty@tty1.service stops what it just
started. Seen four times: 18, 23, 29 and 30 ms after CineMate's "Started".
It is also why "start it again and it works": the second time no getty job
is left parked from a stop.

Neither earlier guard could reach it, because both read the present:

  * --job-mode=fail refuses only while a conflicting start job is already
    pending, and systemd does not enqueue a restart's start half until the
    stop has finished -- nothing pending, nothing refused.
  * `is-active` returns "deactivating" for a stop and a restart alike.

The job queue distinguishes them. The handoff's own probe, at that line,
during a restart:

    PROBE is-active=deactivating
    PROBE job: 7216 cinemate-autostart.service restart running
"""

import ast
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "services/cinemate-autostart/cinemate-console-handoff.sh"
UNIT = ROOT / "services/cinemate-autostart/cinemate-autostart.service"
MAIN = ROOT / "src/main.py"


def load_function(path, name, namespace):
    """Compile one top-level function out of a module, without importing it.

    src/main.py cannot be imported off-hardware -- it reaches for GPIO and
    Redis at import time -- and this guard is worth testing for real rather
    than by grep.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            module = ast.Module(body=[node], type_ignores=[])
            exec(compile(module, str(path), "exec"), namespace)
            return namespace[name]
    raise AssertionError(f"{name} not found in {path}")


class FakeCompleted:
    def __init__(self, stdout):
        self.stdout = stdout


def coming_back_with(jobs, raises=None):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if raises is not None:
            raise raises
        return FakeCompleted(jobs)

    ns = {
        "subprocess": types.SimpleNamespace(
            run=fake_run, PIPE=-1, DEVNULL=-3),
        "logging": types.SimpleNamespace(debug=lambda *a, **k: None),
    }
    fn = load_function(MAIN, "cinemate_service_is_coming_back", ns)
    return fn("/bin/systemctl"), calls


class ForegroundGuardTests(unittest.TestCase):
    """src/main.py's restore_local_console_prompt(), the non-systemd path.

    A foreground CineMate killed by the run lock's SIGTERM -- which is what
    happens when the service starts while one is running in an SSH session --
    asks for tty1 while that service is 10 s into its own start:

        02:52:29.485  Starting cinemate-autostart.service...
        02:52:30.543  sudo pi (pts/1): systemctl restart getty@tty1.service
        02:52:40.120  Started cinemate-autostart.service
        02:52:40.143  Started getty@tty1.service            <- +23 ms
        02:52:40.244  cinemate-autostart.service: Deactivated successfully.
    """

    def test_a_queued_restart_means_hands_off(self):
        coming_back, _ = coming_back_with(
            "7216 cinemate-autostart.service restart running\n")
        self.assertTrue(coming_back)

    def test_a_queued_start_counts_too(self):
        coming_back, _ = coming_back_with(
            "12 cinemate-autostart.service start waiting\n")
        self.assertTrue(coming_back)

    def test_a_plain_stop_still_hands_the_console_back(self):
        # The whole point of the function. A stop queues no start job.
        coming_back, _ = coming_back_with(
            "12 cinemate-autostart.service stop running\n")
        self.assertFalse(coming_back)

    def test_an_empty_queue_hands_the_console_back(self):
        coming_back, _ = coming_back_with("")
        self.assertFalse(coming_back)

    def test_other_units_are_not_us(self):
        coming_back, _ = coming_back_with(
            "1 getty@tty1.service start waiting\n"
            "2 plymouth-quit.service start waiting\n")
        self.assertFalse(coming_back)

    def test_it_reads_the_queue_and_nothing_else(self):
        # Must stay read-only and unprivileged: a privileged call here has no
        # tty to answer a PolicyKit prompt and would block until the stop
        # timeout kills it.
        _, calls = coming_back_with("")
        self.assertEqual(len(calls), 1)
        self.assertIn("list-jobs", calls[0])
        for forbidden in ("start", "restart", "stop", "sudo"):
            self.assertNotIn(forbidden, calls[0])

    def test_a_missing_systemctl_is_not_a_restart(self):
        # Fail open: on a machine with no systemd this function's caller is
        # the only thing that ever brings the prompt back.
        coming_back, _ = coming_back_with("", raises=OSError("no systemctl"))
        self.assertFalse(coming_back)

    def test_a_short_line_does_not_crash_it(self):
        coming_back, _ = coming_back_with("garbage\n\n")
        self.assertFalse(coming_back)


class HandoffScriptTests(unittest.TestCase):
    """The ExecStopPost half -- the site the journal caught in the act."""

    @classmethod
    def setUpClass(cls):
        cls.src = SCRIPT.read_text(encoding="utf-8")

    def _code(self):
        return "\n".join(l for l in self.src.split("\n")
                         if not l.lstrip().startswith("#"))

    def test_it_asks_the_job_queue(self):
        self.assertIn("list-jobs", self._code())

    def test_it_yields_to_a_queued_start_or_restart(self):
        code = self._code()
        self.assertRegex(code, r'"\$\{job_type:-\}" == "start"')
        self.assertRegex(code, r'"\$\{job_type:-\}" == "restart"')

    def test_a_stop_job_is_not_a_reason_to_yield(self):
        # `systemctl stop` queues a stop job; the console must still return.
        self.assertNotRegex(self._code(), r'job_type:-\}" == "stop"')

    def test_it_only_watches_its_own_unit(self):
        self.assertIn('"${unit:-}" == "cinemate-autostart.service"',
                      self._code())

    def test_the_guard_runs_before_the_getty_start(self):
        code = self._code()
        self.assertLess(code.index("cinemate_is_coming_back"),
                        code.index("start getty@tty1.service"),
                        "the guard has to run before the thing it guards")

    def test_the_earlier_guards_are_still_there(self):
        # Each covers a different moment; this one does not replace them.
        code = self._code()
        self.assertIn("is-active cinemate-autostart.service", code)
        self.assertIn("--job-mode=fail", code)

    def test_the_ordering_that_creates_the_delay_is_documented(self):
        # Before= is what parks the getty job. If it ever goes, this guard is
        # solving a problem that no longer exists -- and the next reader needs
        # to find that out from the file, not from the rig.
        self.assertIn("Before=getty@tty1.service", self.src)
        self.assertRegex(UNIT.read_text(encoding="utf-8"),
                         r"Before=.*getty@tty1\.service")


class NoExecStartPostTests(unittest.TestCase):
    """Confirmed on hardware: any ExecStartPost in this unit kills CineMate.

    StandardInput=tty-force with TTYVHangup=yes makes systemd hang up
    /dev/tty1 for every Exec command in the unit. ExecStartPre and
    ExecStopPost are safe because main.py is not running yet, or not any
    more. An ExecStartPost runs while main.py is alive and owns that tty, and
    main.py takes the SIGHUP:

        Process: ExecStartPost=/bin/true (code=exited, status=0/SUCCESS)
        Main PID: 24488 (code=killed, signal=HUP)
        Duration: 23ms

    /bin/true is enough. This is a trap for anyone who tries to fix the
    console race on the way up instead of on the way down.
    """

    def test_the_unit_has_no_exec_start_post(self):
        unit = UNIT.read_text(encoding="utf-8")
        self.assertNotIn("ExecStartPost", unit,
                         "ExecStartPost + TTYVHangup=yes SIGHUPs main.py; "
                         "guard on the stop path instead")

    def test_the_hangup_settings_that_make_it_a_trap_still_hold(self):
        unit = UNIT.read_text(encoding="utf-8")
        self.assertIn("TTYVHangup=yes", unit)
        self.assertIn("StandardInput=tty-force", unit)


if __name__ == "__main__":
    unittest.main()
