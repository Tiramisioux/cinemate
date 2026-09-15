"""scripts/make-release-image.sh must keep borrowing the installer's stock
config.txt rather than growing its own copy of it.

The release script swaps /boot/firmware/config.txt to the stock managed block
before imaging the card. That block is defined once, in
cinemate-install.sh's configure_boot_config(), and the obvious shortcut --
pasting a known-good config.txt into the release script or into a resource
file -- is exactly the duplicated-truth shape this codebase has drifted on
repeatedly: the pasted copy silently stops matching what a clean install
writes, and the release ships a config.txt no install would ever produce.

Two things make the borrowing work, and both are easy to undo by accident:

  * cinemate-install.sh guards `main "$@"` behind a BASH_SOURCE check, so the
    file can be sourced as a library without running an install;
  * configure_boot_config() honours CONFIG_TXT_PATH instead of hardcoding
    /boot/firmware/config.txt.

This checks both, proves the installer really is sourceable by sourcing it,
and fails if the release script ever grows config.txt content of its own.

What it does not cover: whether the generated block is *correct*. That is a
clean-install question and only hardware settles it -- see the handbook's
lessons/what-the-pi-taught-us.md.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "cinemate-install.sh"
RELEASE_SCRIPT = ROOT / "scripts" / "make-release-image.sh"
MAC_DRIVER = ROOT / "scripts" / "pi_release_image_to_mac.sh"

# Lines that only ever belong in the one generator. If any of these turn up in
# the release script, someone has pasted the block instead of calling it.
CONFIG_TXT_FINGERPRINTS = (
    "# ---- Camera section ----",
    "# >>> cinemate-install >>>",
    "imx477,cam0",
    "dtoverlay=vc4-kms-v3d",
)


class TestReleaseImageScript(unittest.TestCase):
    def setUp(self):
        self.installer = INSTALLER.read_text(encoding="utf-8")
        self.release = RELEASE_SCRIPT.read_text(encoding="utf-8")
        # Prose is allowed to name the things the code must not do -- the
        # script's own header explains why it never reserializes settings.jsonc.
        self.release_code = "\n".join(
            line for line in self.release.splitlines()
            if not line.lstrip().startswith("#")
        )

    # ── Floor: the premises this whole test rests on still hold ──────────
    # A fingerprint check passes trivially once the thing it fingerprints
    # moves or is renamed, so assert the source still looks the way the rest
    # of this file assumes before concluding anything from an absence.

    def test_installer_still_defines_the_stock_config_block(self):
        self.assertIn("configure_boot_config() {", self.installer)
        for fingerprint in CONFIG_TXT_FINGERPRINTS:
            self.assertIn(
                fingerprint,
                self.installer,
                f"{fingerprint!r} is gone from cinemate-install.sh -- this test's "
                "fingerprints are stale, fix them before trusting the assertions below",
            )

    def test_release_scripts_are_executable(self):
        for path in (RELEASE_SCRIPT, MAC_DRIVER):
            self.assertTrue(path.is_file(), f"{path} is missing")
            self.assertTrue(path.stat().st_mode & 0o111, f"{path} is not executable")

    # ── The actual guards ────────────────────────────────────────────────

    def test_installer_main_is_guarded_so_sourcing_runs_no_install(self):
        self.assertIn('if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then', self.installer)
        self.assertNotRegex(
            self.installer,
            r"(?m)^main \"\$@\"\s*$",
            "an unguarded `main \"$@\"` is back at column 0: sourcing "
            "cinemate-install.sh would now run a full install",
        )

    def test_configure_boot_config_target_is_overridable(self):
        self.assertIn(
            'local config_txt="${CONFIG_TXT_PATH:-/boot/firmware/config.txt}"',
            self.installer,
            "configure_boot_config() hardcodes its target again, so nothing can "
            "render the stock block anywhere else",
        )

    def test_installer_is_sourceable_as_a_library(self):
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{INSTALLER}" && declare -F configure_boot_config >/dev/null',
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=ROOT,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"sourcing cinemate-install.sh failed:\n{result.stdout}\n{result.stderr}",
        )

    def test_release_script_calls_the_installer_instead_of_copying_it(self):
        self.assertIn('source "$RI_INSTALLER"', self.release)
        self.assertIn("configure_boot_config", self.release)
        for fingerprint in CONFIG_TXT_FINGERPRINTS:
            self.assertNotIn(
                fingerprint,
                self.release_code,
                f"{fingerprint!r} appears in make-release-image.sh -- the stock "
                "config.txt has been copied instead of generated. Call "
                "configure_boot_config() instead; there must be exactly one "
                "definition of what a clean install writes.",
            )

    def test_settings_jsonc_is_restored_byte_for_byte(self):
        # settings.jsonc's comments are part of the product, and a round-trip
        # through json.dumps() deletes all of them -- a bug this project has
        # already shipped once from the installer. The release script must only
        # ever copy the file, never parse and rewrite it.
        self.assertIn("checkout -- settings.jsonc", self.release_code)
        self.assertNotIn("json.dumps", self.release_code)
        self.assertNotIn("json.load", self.release_code)

    def test_restore_is_armed_before_anything_is_swapped(self):
        # The trap has to be in place before the first write, or an interrupt
        # in the window between them loses the operator's configuration.
        first_swap_at = self.release_code.index("checkout -- settings.jsonc")
        for trap in (
            "trap ri_restore EXIT",
            "trap 'ri_restore; exit 130' INT",
            "trap 'ri_restore; exit 143' TERM",
        ):
            self.assertIn(trap, self.release_code)
            self.assertLess(
                self.release_code.index(trap),
                first_swap_at,
                f"{trap!r} is armed after the first swap; an interrupt in "
                "between would strand the Pi on stock configuration",
            )


if __name__ == "__main__":
    unittest.main()


class TestBashrcAliasesMatchTheManualInstall(unittest.TestCase):
    """The .bashrc aliases are stated twice and nothing compared them.

    cinemate-install.sh writes a managed block of aliases into ~/.bashrc, and
    docs/installation-steps.md restates that block verbatim for people doing
    the install by hand. Two hand-maintained copies of one fact, with no check
    -- the exact shape this codebase keeps drifting on. Adding a fifth alias
    (make-release-image) is what surfaced it, so the check lands with it.

    Not a comment saying "keep these in sync": a comment cannot fail.
    """

    # The installer writes $CINEMATE_DIR / $PI_HOME; the docs page, aimed at
    # someone typing into nano, writes them out. Normalize before comparing.
    SUBSTITUTIONS = (
        ("$CINEMATE_DIR", "/home/pi/cinemate"),
        ("$PI_HOME", "/home/pi"),
    )

    @staticmethod
    def _aliases(text):
        found = {}
        for match in re.finditer(r"^alias ([\w-]+)='([^']*)'$", text, re.MULTILINE):
            name, body = match.groups()
            for token, expansion in TestBashrcAliasesMatchTheManualInstall.SUBSTITUTIONS:
                body = body.replace(token, expansion)
            found[name] = body
        return found

    def setUp(self):
        self.installer_aliases = self._aliases(INSTALLER.read_text(encoding="utf-8"))
        docs = (ROOT / "docs" / "installation-steps.md").read_text(encoding="utf-8")
        self.docs_aliases = self._aliases(docs)

    def test_the_extractor_found_something_plausible(self):
        # A set comparison passes trivially once the pattern stops matching.
        # Assert a floor first, so a change to how aliases are written fails as
        # "suspect this extractor" rather than passing on two empty sets.
        self.assertGreaterEqual(
            len(self.installer_aliases), 5,
            f"only found {sorted(self.installer_aliases)} in cinemate-install.sh -- "
            "the alias pattern has stopped matching, fix it before trusting the result",
        )
        self.assertIn("editsettings", self.installer_aliases)

    def test_every_installer_alias_is_in_the_manual_install(self):
        missing = set(self.installer_aliases) - set(self.docs_aliases)
        self.assertFalse(
            missing,
            f"cinemate-install.sh writes {sorted(missing)} but docs/installation-steps.md "
            "does not tell a manual installer to add it -- the two shells would differ",
        )

    def test_the_manual_install_invents_no_alias_of_its_own(self):
        extra = set(self.docs_aliases) - set(self.installer_aliases)
        self.assertFalse(
            extra,
            f"docs/installation-steps.md tells people to add {sorted(extra)}, which "
            "cinemate-install.sh does not write",
        )

    def test_the_two_copies_expand_to_the_same_commands(self):
        for name, body in sorted(self.installer_aliases.items()):
            self.assertEqual(
                body, self.docs_aliases.get(name),
                f"alias {name} differs between the installer and the manual install page",
            )


class TestUpdateRefreshesShellHelpers(unittest.TestCase):
    """cinemate-update.sh must rewrite the managed .bashrc block, not restate it.

    An alias added to cinemate-install.sh used to reach only a Pi that got a
    full reinstall -- which nobody does for an alias -- so `git pull` left the
    shell permanently behind the code. make-release-image was the first alias
    added after the initial install and would have been invisible everywhere.

    The fix calls the installer's own configure_bashrc() from the update path.
    Two things have to keep holding for that to be worth anything: the update
    script must not grow its own copy of the alias list, and the function has
    to really be idempotent, since it now runs on every update rather than
    once per install. The second is a runtime property, so it is exercised
    rather than read.
    """

    UPDATE = ROOT / "cinemate-update.sh"

    def setUp(self):
        self.update = self.UPDATE.read_text(encoding="utf-8")

    def test_update_calls_the_installer_instead_of_restating_aliases(self):
        self.assertIn("configure_bashrc", self.update)
        self.assertNotRegex(
            self.update,
            r"(?m)^\s*alias \w",
            "cinemate-update.sh defines an alias of its own -- that is a third "
            "copy of a list already stated in the installer and the manual "
            "install page. Call configure_bashrc() instead.",
        )

    def test_configure_bashrc_is_idempotent_and_writes_every_alias(self):
        if shutil.which("bash") is None:
            self.skipTest("bash is required")

        tmp = Path(tempfile.mkdtemp(prefix="bashrc-refresh-"))
        self.addCleanup(shutil.rmtree, tmp, True)

        home = tmp / "home"
        home.mkdir()
        # A .bashrc with an edit outside the fence: the managed block's stated
        # contract is that such a line survives, so check it does.
        (home / ".bashrc").write_text("export EDITOR=nano  # mine\n")

        stub_dir = tmp / "stubs"
        stub_dir.mkdir()
        sudo = stub_dir / "sudo"
        sudo.write_text(
            "#!/bin/sh\n"
            'while [ $# -gt 0 ]; do\n'
            '  case "$1" in -u) shift 2 ;; -n|-S) shift ;; -p) shift 2 ;; --) shift; break ;; *) break ;; esac\n'
            "done\n"
            'exec "$@"\n'
        )
        sudo.chmod(0o755)

        script = (
            f'export PI_USER="$(id -un)" PI_GROUP="$(id -gn)" PI_HOME="{home}" '
            f'CINEMATE_DIR="{tmp}/cinemate"\n'
            f'source "{INSTALLER}"\n'
            f'BACKUP_DIR="{tmp}/backups"\n'
            "mkdir -p \"$BACKUP_DIR\"\n"
            "configure_bashrc\n"
            "configure_bashrc\n"  # twice: this now runs on every update
        )
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}"},
        )
        self.assertEqual(
            result.returncode, 0,
            f"configure_bashrc failed\n{result.stdout}\n{result.stderr}",
        )

        written = (home / ".bashrc").read_text()
        self.assertIn("export EDITOR=nano  # mine", written,
                      "an edit outside the fence was destroyed")

        for name in ("cinemate", "editboot", "editcmdline", "editsettings",
                     "make-release-image"):
            self.assertEqual(
                written.count(f"alias {name}="), 1,
                f"alias {name} appears {written.count(f'alias {name}=')} times after "
                "two runs; configure_bashrc is not idempotent and every update "
                "would add another copy",
            )

        self.assertEqual(written.count("# >>> cinemate-install >>>"), 1)
        self.assertIn(
            f"alias make-release-image='sudo {tmp}/cinemate/scripts/make-release-image.sh'",
            written,
        )
