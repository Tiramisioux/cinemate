"""config.txt saves must not silently fail as User=pi (F-288).

/boot/firmware is root-owned; the settings editor runs unprivileged, so a
direct write there raises PermissionError before a byte is written. That
case must fall back to staging the text somewhere pi-writable and handing
it to the privileged helper cinemate-install.sh's configure_sudoers()
grants -- and a failure in that fallback must not leave a staged file
behind.
"""

import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.app import boot_config


class WriteConfigTxtDirectTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.dest = self.dir / "config.txt"
        self.dest.write_text("original\n", encoding="utf-8")
        self.patched = mock.patch.object(boot_config, "CONFIG_TXT_PATH", str(self.dest))
        self.patched.start()
        self.addCleanup(self.patched.stop)

    def test_writes_directly_when_the_destination_is_writable(self):
        boot_config.write_config_txt("new content\n")
        self.assertEqual(self.dest.read_text(encoding="utf-8"), "new content\n")

    def test_direct_write_leaves_no_temp_file_behind(self):
        boot_config.write_config_txt("new content\n")
        leftovers = list(self.dir.glob(".settings-editor-*"))
        self.assertEqual(leftovers, [])


class WriteConfigTxtFallbackTests(unittest.TestCase):
    """Simulates the real /boot/firmware permission wall with a read-only
    directory, so the fallback path exercises a genuine PermissionError
    rather than a mocked one."""

    def setUp(self):
        self.root_dir = Path(tempfile.mkdtemp())
        self.readonly_dir = self.root_dir / "firmware"
        self.readonly_dir.mkdir()
        self.dest = self.readonly_dir / "config.txt"
        self.dest.write_text("original\n", encoding="utf-8")
        self.readonly_dir.chmod(0o555)
        self.addCleanup(self.readonly_dir.chmod, 0o755)

        self.staging_dir = Path(tempfile.mkdtemp())
        self.staged = self.staging_dir / "config.txt.staged"

        self.patches = [
            mock.patch.object(boot_config, "CONFIG_TXT_PATH", str(self.dest)),
            mock.patch.object(boot_config, "STAGED_CONFIG_TXT_PATH", str(self.staged)),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

        if os.geteuid() == 0:
            self.skipTest("root bypasses the read-only directory this test relies on")

    def test_falls_back_to_the_helper_on_permission_denied(self):
        def fake_helper(cmd, **kwargs):
            # Stands in for cinemate-apply-config-txt: read the staged file,
            # write it to dest (which the real helper can because it runs
            # as root; here we bypass the chmod ourselves for the same
            # effect).
            self.readonly_dir.chmod(0o755)
            self.dest.write_text(self.staged.read_text(encoding="utf-8"), encoding="utf-8")
            self.readonly_dir.chmod(0o555)
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch("subprocess.run", side_effect=fake_helper) as run:
            boot_config.write_config_txt("staged via helper\n")

        run.assert_called_once()
        called_cmd = run.call_args.args[0]
        self.assertEqual(called_cmd, ["sudo", "-n", boot_config.APPLY_CONFIG_TXT_HELPER])
        self.readonly_dir.chmod(0o755)
        self.assertEqual(self.dest.read_text(encoding="utf-8"), "staged via helper\n")

    def test_a_failed_helper_raises_and_cleans_up_the_staged_file(self):
        with mock.patch(
            "subprocess.run",
            return_value=types.SimpleNamespace(returncode=1, stdout="", stderr="sudo: a password is required"),
        ):
            with self.assertRaises(PermissionError):
                boot_config.write_config_txt("should not land\n")

        self.assertFalse(self.staged.exists())
        self.readonly_dir.chmod(0o755)
        self.assertEqual(self.dest.read_text(encoding="utf-8"), "original\n")


if __name__ == "__main__":
    unittest.main()
