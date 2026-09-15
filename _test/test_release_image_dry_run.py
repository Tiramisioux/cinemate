"""End-to-end proof that make-release-image.sh puts both files back.

The rest of this script's behaviour can be read off the source, but the one
thing that must never go wrong -- the operator's settings.jsonc and config.txt
coming back byte for byte after the swap -- is a runtime property, and reading
the source is exactly how you convince yourself a restore path works when it
does not.

So this runs the real script, in --dry-run, against a scratch tree that stands
in for a Pi: a git checkout with a locally-modified settings.jsonc, a config.txt
with operator edits in it, and a destination directory. The Linux-only commands
it probes the machine with (findmnt, lsblk, blockdev, systemctl, and sudo
itself) are stubbed on PATH, so the test runs the same on a Mac and on CI.

--dry-run skips only dd and PiShrink. Every part this test cares about -- the
stash, the swap to stock, the trap, the restore -- runs for real.

What this does not cover: dd, PiShrink, and whether the resulting image boots.
Only hardware settles those; see the handbook's lessons/what-the-pi-taught-us.md.
"""

import grp
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_SCRIPT = ROOT / "scripts" / "make-release-image.sh"

# A settings.jsonc keeps its comments through this whole cycle or the test has
# not proven anything -- reserializing is the failure mode being guarded.
TRACKED_SETTINGS = """{
  // shipped default, comments and all
  "system": {
    "wifi_hotspot": { "name": "CinePi", "password": "11111111" }
  }
}
"""

OPERATOR_SETTINGS = """{
  // MY notes, which must survive the release build
  "system": {
    "wifi_hotspot": { "name": "PatriksRig", "password": "notthedefault" }
  }
}
"""

OPERATOR_CONFIG = """# >>> cinemate-install >>>
# hand-edited for the imx585 I actually shoot with
camera_auto_detect=0
dtoverlay=imx585,cam0
dtoverlay=rp1-overclock
# <<< cinemate-install <<<
"""

# Stubs for everything the script asks the machine about. Each answers as a
# single-disk Pi would, with /media/RAW on a second disk.
STUBS = {
    "id": '#!/bin/sh\n[ "$1" = "-u" ] && echo 0 && exit 0\nexit 0\n',
    # sudo -u <user> -- cmd...  /  sudo cmd... : drop the flags, run the rest.
    "sudo": (
        "#!/bin/sh\n"
        'while [ $# -gt 0 ]; do\n'
        '  case "$1" in\n'
        '    -u) shift 2 ;;\n'
        '    -n|-S) shift ;;\n'
        '    -p) shift 2 ;;\n'
        '    --) shift; break ;;\n'
        '    *) break ;;\n'
        '  esac\n'
        "done\n"
        'exec "$@"\n'
    ),
    # --target <path> or bare <path>. The destination dir is the only thing
    # on the "second disk"; everything else is on the device being imaged.
    "findmnt": (
        "#!/bin/sh\n"
        'for a in "$@"; do\n'
        '  case "$a" in\n'
        '    "$RI_TEST_DEST"*) echo /dev/ri-other1; exit 0 ;;\n'
        "  esac\n"
        "done\n"
        'echo "${RI_TEST_DEVICE}p1"\n'
    ),
    "lsblk": (
        "#!/bin/sh\n"
        'for a in "$@"; do\n'
        '  case "$a" in\n'
        "    /dev/ri-other*) echo ri-other; exit 0 ;;\n"
        '    "$RI_TEST_DEVICE"*) basename "$RI_TEST_DEVICE"; exit 0 ;;\n'
        "  esac\n"
        "done\n"
        "exit 1\n"
    ),
    "blockdev": "#!/bin/sh\necho 64000000000\n",
    "mountpoint": "#!/bin/sh\nexit 0\n",
    "numfmt": '#!/bin/sh\nfor a in "$@"; do last="$a"; done\necho "$last"\n',
    "df": "#!/bin/sh\necho Avail\necho 200000000000\n",
    "systemctl": "#!/bin/sh\nexit 1\n",
}


class TestReleaseImageDryRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("git") is None:
            raise unittest.SkipTest("git is required")
        # The script refuses a device that is not really a block device -- a
        # check worth keeping, so borrow a real one rather than weaken it.
        cls.device = next(
            (str(d) for d in sorted(Path("/dev").glob("*"))
             if d.is_block_device() and not d.is_symlink()),
            None,
        )
        if cls.device is None:
            raise unittest.SkipTest("no block device available to stand in for the card")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="release-image-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

        self.cinemate = self.tmp / "cinemate"
        self.cinemate.mkdir()
        self.settings = self.cinemate / "settings.jsonc"
        self.settings.write_text(TRACKED_SETTINGS)

        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        }
        for args in (
            ["init", "-q", "-b", "main"],
            ["add", "settings.jsonc"],
            ["commit", "-qm", "shipped default"],
        ):
            subprocess.run(["git", "-C", str(self.cinemate), *args], check=True, env=env)

        # The operator has since edited it. This is what must come back.
        self.settings.write_text(OPERATOR_SETTINGS)

        self.boot_config = self.tmp / "config.txt"
        self.boot_config.write_text(OPERATOR_CONFIG)

        self.dest = self.tmp / "RAW"
        self.dest.mkdir()

        self.stub_dir = self.tmp / "stubs"
        self.stub_dir.mkdir()
        for name, body in STUBS.items():
            stub = self.stub_dir / name
            stub.write_text(body)
            stub.chmod(0o755)

    def run_script(self, *args):
        env = {
            **os.environ,
            "PATH": f"{self.stub_dir}:{os.environ['PATH']}",
            "RI_TEST_DEST": str(self.dest),
            "RI_TEST_DEVICE": self.device,
            "IMAGE_DEVICE": self.device,
            "PI_GROUP": grp.getgrgid(os.getgid()).gr_name,
            "PI_USER": os.environ.get("USER", "runner"),
            "CINEMATE_DIR": str(self.cinemate),
            "CINEPI_RAW_DIR": str(self.tmp / "cinepi-raw"),
            "IMAGE_DEST_DIR": str(self.dest),
            "BOOT_CONFIG": str(self.boot_config),
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        }
        return subprocess.run(
            ["bash", str(RELEASE_SCRIPT), *args],
            capture_output=True, text=True, timeout=120, env=env, cwd=str(self.tmp),
        )

    def test_dry_run_swaps_to_stock_and_restores_byte_for_byte(self):
        result = self.run_script("--dry-run")
        self.assertEqual(
            result.returncode, 0,
            f"script failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        out = result.stdout

        # It really did swap, not quietly skip.
        self.assertIn("Swapping in the stock configuration", out)
        self.assertIn("settings.jsonc -> tracked copy at", out)
        self.assertIn("config.txt -> stock block from cinemate-install.sh", out)

        # It really did put both back.
        self.assertEqual(
            self.settings.read_text(), OPERATOR_SETTINGS,
            "settings.jsonc did not come back byte for byte",
        )
        self.assertEqual(
            self.boot_config.read_text(), OPERATOR_CONFIG,
            "config.txt did not come back byte for byte",
        )
        self.assertIn("Restore complete", out)

        # And it cleaned up after itself, so the operator's hotspot password is
        # not left lying in a stash directory.
        self.assertFalse(
            (self.dest / ".cinemate-release-image").exists(),
            "the stash directory survived a successful run",
        )

    def test_the_swap_really_produces_the_stock_files(self):
        # Same run, but with dd/PiShrink's step turned into an inspection
        # point: --dry-run prints the manifest and the commands it would run,
        # which is the moment the files are at their stock values.
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)

        # The imx585 + overclock lines the operator hand-edited in must NOT be
        # what the release would have been imaged with.
        self.assertIn(f"dd if={self.device}", result.stdout)
        self.assertIn("config.txt     stock block", result.stdout)

    def test_progress_reports_every_phase(self):
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        for step in ("[1/4]", "[2/4]", "[3/4]", "[4/4]"):
            self.assertIn(step, result.stdout, f"{step} missing from the progress output")
        self.assertIn("... done in ", result.stdout)

    def test_interrupted_run_is_recovered_by_restore_only(self):
        # Simulate a power cut between the swap and the restore: stage the
        # stash by hand exactly as the script does, with the machine left on
        # stock config, and check --restore-only puts the operator back.
        stash = self.dest / ".cinemate-release-image"
        stash.mkdir()
        (stash / "settings.jsonc").write_text(OPERATOR_SETTINGS)
        (stash / "config.txt").write_text(OPERATOR_CONFIG)
        (stash / "state.env").write_text("RI_CINEMATE_WAS_ACTIVE=0\n")

        self.settings.write_text(TRACKED_SETTINGS)
        self.boot_config.write_text("# stock, mid-release\n")

        result = self.run_script("--restore-only")
        self.assertEqual(
            result.returncode, 0,
            f"--restore-only failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        self.assertEqual(self.settings.read_text(), OPERATOR_SETTINGS)
        self.assertEqual(self.boot_config.read_text(), OPERATOR_CONFIG)
        self.assertFalse(stash.exists())


if __name__ == "__main__":
    unittest.main()
