"""D6a: warn when the installed system files are older than the checkout.

C3.4's whole mechanism is one character -- the leading `-` on
`ExecStartPre=-/usr/local/bin/camera-ready.sh`. But the unit is copied into
`/etc/systemd/system/` by `sudo make install`, not symlinked, so a `git pull`
on the Pi does not deliver it. An operator who updates by pulling keeps the
strict gate: no camera -> the gate exits 1 -> systemd fails the unit BEFORE
main.py runs -> bare terminal on tty1, with no CineMate error to explain it.
"""

import logging
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.installed_files import (
    INSTALLED_FILES,
    find_installed_file_drift,
    log_installed_file_drift,
)


class InstalledFileListMatchesTheMakefileTests(unittest.TestCase):
    """The list is a hand-maintained mirror of the Makefile's install
    target. Duplicated truth stops agreeing, so check it here."""

    def _makefile_install_pairs(self):
        makefile = (ROOT / "Makefile").read_text()
        variables = dict(
            re.findall(r"^([A-Z_]+)\s*:?=\s*(\S+)\s*$", makefile, re.MULTILINE)
        )

        def expand(text):
            for _ in range(5):
                replaced = re.sub(
                    r"\$\(([A-Z_]+)\)", lambda m: variables.get(m.group(1), m.group(0)), text
                )
                if replaced == text:
                    break
                text = replaced
            return text

        install_body = makefile.split("\ninstall:", 1)[1].split("\n\n", 1)[0]
        pairs = set()
        for source, destination in re.findall(
            r"install -m \d+ (\S+) (\S+)", install_body
        ):
            pairs.add((expand(source), expand(destination)))
        return pairs

    def test_every_makefile_install_is_covered(self):
        self.assertEqual(self._makefile_install_pairs(), set(INSTALLED_FILES))

    def test_every_repo_path_in_the_list_exists(self):
        for relative_path, _installed in INSTALLED_FILES:
            with self.subTest(path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())


class NotInstalledAtAllTests(unittest.TestCase):
    """A Pi running CineMate manually, or installed with autostart disabled,
    has none of these files. That is not drift, and warning about all five
    on every boot would be a standing false alarm the operator learns to
    ignore -- which is exactly how the real warning would get missed."""

    def test_the_default_check_is_silent_when_the_unit_is_not_installed(self):
        from module import installed_files

        original = installed_files.INSTALL_SENTINEL
        installed_files.INSTALL_SENTINEL = "/nonexistent/cinemate-autostart.service"
        self.addCleanup(setattr, installed_files, "INSTALL_SENTINEL", original)

        with self.assertNoLogs(level=logging.WARNING):
            result = installed_files.log_installed_file_drift(ROOT)

        self.assertEqual(result, [])


class FindInstalledFileDriftTests(unittest.TestCase):

    def _pair(self, tmp, repo_text, installed_text):
        repo_file = tmp / "repo" / "unit.service"
        repo_file.parent.mkdir(parents=True, exist_ok=True)
        repo_file.write_text(repo_text)
        installed = tmp / "installed" / "unit.service"
        installed.parent.mkdir(parents=True, exist_ok=True)
        if installed_text is not None:
            installed.write_text(installed_text)
        return [("repo/unit.service", str(installed))]

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self.addCleanup(self._tmpdir.cleanup)

    def test_identical_copies_are_not_drift(self):
        pairs = self._pair(self.tmp, "ExecStartPre=-/x.sh\n", "ExecStartPre=-/x.sh\n")

        self.assertEqual(find_installed_file_drift(self.tmp / "repo" / "..", pairs), [])

    def test_a_stale_installed_copy_is_reported(self):
        # The exact C3.4 case: the repo has the advisory `-`, the installed
        # copy still has the strict gate.
        pairs = self._pair(self.tmp, "ExecStartPre=-/x.sh\n", "ExecStartPre=/x.sh\n")

        drifted = find_installed_file_drift(self.tmp / "repo" / "..", pairs)

        self.assertEqual(len(drifted), 1)
        self.assertIn("differs", drifted[0].reason)

    def test_a_missing_installed_copy_is_reported(self):
        pairs = self._pair(self.tmp, "anything\n", None)

        drifted = find_installed_file_drift(self.tmp / "repo" / "..", pairs)

        self.assertEqual(len(drifted), 1)
        self.assertEqual(drifted[0].reason, "not installed")

    def test_a_missing_repo_file_is_not_reported(self):
        # Nothing to compare against -- silence beats a false alarm.
        pairs = [("no/such/file", str(self.tmp / "also-absent"))]

        self.assertEqual(find_installed_file_drift(self.tmp, pairs), [])


class LogInstalledFileDriftTests(unittest.TestCase):

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self.addCleanup(self._tmpdir.cleanup)
        (self.tmp / "repo").mkdir()
        (self.tmp / "repo" / "unit.service").write_text("new\n")
        (self.tmp / "unit.service").write_text("old\n")
        self.pairs = [("repo/unit.service", str(self.tmp / "unit.service"))]

    def test_the_warning_names_the_remedy(self):
        with self.assertLogs(level=logging.WARNING) as captured:
            log_installed_file_drift(self.tmp, pairs=self.pairs)

        joined = "\n".join(captured.output)
        self.assertIn("sudo make install", joined)
        self.assertIn("daemon-reload", joined)
        self.assertIn(str(self.tmp), joined)

    def test_nothing_is_logged_when_everything_matches(self):
        (self.tmp / "unit.service").write_text("new\n")

        with self.assertNoLogs(level=logging.WARNING):
            log_installed_file_drift(self.tmp, pairs=self.pairs)

    def test_it_never_shells_out(self):
        # "Warn, don't act" -- CineMate must never sudo on the operator's
        # behalf, so the remedy is a string it prints, never a command it
        # runs. Assert that structurally: the module imports nothing that
        # can spawn a process or write a file.
        import ast

        source = (ROOT / "src" / "module" / "installed_files.py").read_text()
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])

        for forbidden in ("subprocess", "shutil", "pty", "multiprocessing"):
            with self.subTest(module=forbidden):
                self.assertNotIn(forbidden, imported)

        for forbidden_call in ("os.system", "os.popen", "os.execv", "open("):
            with self.subTest(call=forbidden_call):
                self.assertNotIn(forbidden_call, source)


if __name__ == "__main__":
    unittest.main()
