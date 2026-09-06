"""The two reboot buttons do something, rather than animating.

Same defect F-291 fixed on Restart Cinemate, left in the two places where an
operator has the most reason to believe a reboot happened:

* **Save & reboot Pi** called runBootSequence() and nothing else. config.txt
  was never written, nothing rebooted, and the card still finished on "Pi is
  back up". Its own help text promises it "writes these choices into the
  managed block of config.txt and reboots".
* **Reboot Pi** scrolled to that card and clicked it -- so it did neither, and
  would additionally have carried whatever unsaved config.txt edits the other
  page was holding.

Both real paths already existed. put_config_txt() writes the file and
schedules cinepi_controller.reboot() 0.4 s after it answers, reporting that as
`rebooting`; the CLI's own `reboot` verb is dispatchable over /api/v1/cmd, the
same route Restart Cinemate uses. Verified in a browser against the real
template: Save & reboot issues PUT /settings-editor/api/config-txt, and Reboot
Pi issues POST /api/v1/cmd with the body `reboot`.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TEMPLATE = ROOT / "src/module/app/templates/settings_editor.html"
EDITOR_PY = ROOT / "src/module/app/settings_editor.py"
CLI = ROOT / "src/module/cli_commands.py"


def handler(html, button_id):
    """The body of the click listener registered for *button_id*."""
    start = html.index("document.getElementById('%s').addEventListener('click'" % button_id) \
        if "document.getElementById('%s').addEventListener" % button_id in html \
        else html.index("%s.addEventListener('click'" % button_id)
    depth, i, seen = 0, start, False
    while True:
        if html[i] == "{":
            depth += 1
            seen = True
        elif html[i] == "}":
            depth -= 1
            if seen and depth == 0:
                return html[start:i + 1]
        i += 1


class SaveAndRebootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_it_writes_config_txt_before_animating(self):
        body = handler(self.html, "cfgRebootBtn")
        self.assertIn("saveConfigTxt()", body)
        self.assertLess(body.index("saveConfigTxt()"), body.index("runBootSequence"),
                        "the animation must follow the write, not replace it")

    def test_a_failed_write_does_not_animate(self):
        body = handler(self.html, "cfgRebootBtn")
        self.assertIn("if (!res.ok)", body)
        self.assertIn("Save failed", body)

    def test_a_write_with_no_reboot_behind_it_says_so(self):
        # put_config_txt() only reboots when a controller is attached. Claiming
        # "Rebooting" without one is the same lie in a smaller font.
        body = handler(self.html, "cfgRebootBtn")
        self.assertIn("if (!res.rebooting)", body)
        self.assertIn("reboot the Pi yourself", body)

    def test_the_save_helper_posts_the_real_config_state(self):
        helper = handler(self.html, "saveBtn")
        self.assertIn("saveConfigTxt()", helper)
        block = self.html[self.html.index("function saveConfigTxt(){"):]
        block = block[:block.index("\n  }")]
        self.assertIn("'/settings-editor/api/config-txt'", block)
        self.assertIn("method: 'PUT'", block)
        self.assertIn("currentConfigState()", block)


class RebootPiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_it_dispatches_a_real_reboot(self):
        body = handler(self.html, "genericRebootBtn")
        self.assertIn("apiCmd('reboot')", body)

    def test_it_does_not_write_config_txt(self):
        # "A full reboot for any other reason" -- it must not carry the boot
        # config page's unsaved edits with it, which clicking that card did.
        body = handler(self.html, "genericRebootBtn")
        self.assertNotIn("saveConfigTxt", body)
        self.assertNotIn("cfgRebootBtn.click()", body)

    def test_a_refused_command_does_not_animate(self):
        body = handler(self.html, "genericRebootBtn")
        self.assertIn("if (!result.ok)", body)
        self.assertIn("Reboot failed", body)


class RebootIsActuallyPermittedTests(unittest.TestCase):
    """Wiring the buttons up was not enough: nothing granted the reboot.

    cinemate-autostart.service runs as `pi` (User=pi), and CineMate's sudoers
    drop-in listed mount, ntfs-3g, the restart trigger and the config.txt
    helper -- never reboot or poweroff. Whether `sudo reboot` worked at all
    came down to the distro's own 010_<user>-nopasswd rule still being in
    place, and where it had been removed EVERY reboot path failed: the CLI
    verb, the GPIO triple-click, the web API, and both settings-editor
    buttons. Silently, because reboot() ran the command through os.system(),
    which returns the shell's status and discarded it.
    """

    @classmethod
    def setUpClass(cls):
        cls.installer = (ROOT / "cinemate-install.sh").read_text(encoding="utf-8")
        cls.controller = (ROOT / "src/module/cinepi_controller.py").read_text(encoding="utf-8")

    def test_sudoers_grants_reboot_and_poweroff(self):
        self.assertIn(
            "NOPASSWD: /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff",
            self.installer)

    def test_the_grant_matches_the_command_actually_run(self):
        # A grant for a path the code never invokes protects nothing. Both
        # sides say /usr/bin/systemctl with the bare verb.
        self.assertIn('["sudo", "-n", "systemctl", verb]', self.controller)

    def test_reboot_no_longer_goes_through_os_system(self):
        block = self.controller[self.controller.index("def _power_command"):]
        block = block[:block.index("def mount(")]
        # Strip the docstrings: they explain the old os.system() defect, and
        # the point is that no code still does it.
        code = re.sub(r'"""(?:.|\n)*?"""', "", block)
        self.assertNotIn("os.system", code)
        self.assertIn("subprocess.run", block)
        self.assertIn("check=False", block)
        self.assertIn("result.returncode != 0", block)

    def test_it_fails_fast_rather_than_waiting_on_a_password_prompt(self):
        block = self.controller[self.controller.index("def _power_command"):]
        block = block[:block.index("def mount(")]
        self.assertIn('"-n"', block)

    def test_a_refusal_is_logged_with_the_remedy(self):
        block = self.controller[self.controller.index("def _power_command"):]
        block = block[:block.index("def mount(")]
        self.assertIn("logging.error", block)
        self.assertIn("sudoers", block)

    def test_both_verbs_return_whether_they_were_accepted(self):
        self.assertIn("def reboot(self) -> bool:", self.controller)
        self.assertIn("def safe_shutdown(self) -> bool:", self.controller)


class TheRealPathsExistTests(unittest.TestCase):
    """The buttons are only honest if what they call actually reboots."""

    def test_put_config_txt_schedules_a_reboot_and_reports_it(self):
        src = EDITOR_PY.read_text(encoding="utf-8")
        block = src[src.index('@settings_editor_bp.route("/api/config-txt", methods=["PUT"])'):]
        block = block[:block.index("@settings_editor_bp.route", 10)]
        self.assertIn("cinepi_controller.reboot", block)
        self.assertIn('"rebooting": rebooting', block)

    def test_rebooting_is_asked_of_sudoers_not_assumed_from_the_method(self):
        # It used to be True whenever the controller merely HAD a reboot
        # method, so the page animated a reboot sudo was about to refuse.
        src = EDITOR_PY.read_text(encoding="utf-8")
        block = src[src.index('@settings_editor_bp.route("/api/config-txt", methods=["PUT"])'):]
        block = block[:block.index("@settings_editor_bp.route", 10)]
        self.assertIn("cinepi_controller.can_reboot()", block)
        self.assertIn("not in its sudoers rule", block)

    def test_can_reboot_asks_without_rebooting(self):
        controller = (ROOT / "src/module/cinepi_controller.py").read_text(encoding="utf-8")
        block = controller[controller.index("def can_reboot"):]
        block = block[:block.index("def reboot(")]
        # `sudo -l <command>` answers the policy question without running it.
        self.assertIn('"-l"', block)
        self.assertIn('"-n"', block)

    def test_reboot_is_a_dispatchable_cli_verb(self):
        # apiCmd('reboot') goes through the same dispatcher as the CLI.
        self.assertRegex(CLI.read_text(encoding="utf-8"),
                         r"'reboot'\s*:\s*\(cinepi_controller\.reboot")


if __name__ == "__main__":
    unittest.main()
