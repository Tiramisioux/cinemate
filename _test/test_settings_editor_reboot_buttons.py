"""The reboot/restart/shutdown buttons do something, rather than animating.

Same defect F-291 fixed on Restart Cinemate, left in the places where an
operator has the most reason to believe a power action happened:

* **Save & reboot Pi** called runBootSequence() and nothing else. config.txt
  was never written, nothing rebooted, and the card still finished on "Pi is
  back up". Its own help text promises it "writes these choices into the
  managed block of config.txt and reboots".
* **Reboot Pi** scrolled to that card and clicked it -- so it did neither, and
  would additionally have carried whatever unsaved config.txt edits the other
  page was holding.

put_config_txt() writes the file and schedules cinepi_controller.reboot()
0.4 s after it answers, reporting that as `rebooting` -- that part still
holds. What changed: Restart CineMate, Reboot Pi and the new Shut down Pi
buttons used to (or, for shutdown, would have had to) dispatch through
POST /api/v1/cmd, the same route the CLI and serial share. That route
refuses `reboot`/`shutdown` unless `system.web_api.allow_destructive` is
true, which a stock settings.jsonc ships false -- the switch exists to keep
those two verbs away from anyone else on the hotspot, not from this page.
So on an unmodified camera every one of these buttons used to answer 403
"err blocked" and the page toasted "Reboot failed: err blocked". They now
post to this blueprint's own POST /settings-editor/api/power instead, the
same way put_config_txt() already reboots directly and the RAW pane already
formats drives and deletes takes with no such switch in the way.
"""

import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

# Same mechanism as test_settings_editor_format.py: stub the parent package
# so the `settings_editor` submodule resolves via __path__ without executing
# module/app/__init__.py's flask_socketio import.
_APP_PKG = types.ModuleType("module.app")
_APP_PKG.__path__ = [str(ROOT / "src" / "module" / "app")]
sys.modules.setdefault("module.app", _APP_PKG)

from flask import Flask

from module.app.settings_editor import settings_editor_bp
from module.cinepi_controller import CinePiController

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
        # Used to assert apiCmd('reboot') -- POST /api/v1/cmd, which refuses
        # reboot/shutdown unless system.web_api.allow_destructive is true.
        # The shipped settings.jsonc sets that false (the switch exists to
        # protect that route from anyone else on the hotspot, not from this
        # page), so on a stock camera the button always got back 403 "err
        # blocked" and toasted "Reboot failed: err blocked". The settings
        # editor already performs other destructive actions (format, delete)
        # through its own blueprint with no such switch, and put_config_txt()
        # already reboots directly from there -- so this button now posts to
        # that blueprint's own /api/power route instead.
        body = handler(self.html, "genericRebootBtn")
        self.assertIn("powerAction('reboot')", body)
        self.assertNotIn("apiCmd(", body)

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

    def test_can_power_asks_without_running_the_command(self):
        # can_reboot() generalised to can_power(verb) so the settings
        # editor's shutdown button can ask sudoers about `poweroff` too,
        # rather than assuming its grant follows reboot's.
        controller = (ROOT / "src/module/cinepi_controller.py").read_text(encoding="utf-8")
        block = controller[controller.index("def can_power"):]
        block = block[:block.index("def can_reboot(")]
        # `sudo -l <command>` answers the policy question without running it.
        self.assertIn('"-l"', block)
        self.assertIn('"-n"', block)

    def test_can_reboot_is_a_thin_wrapper_over_can_power(self):
        # Kept under its own name: put_config_txt() and this file pin it.
        controller = (ROOT / "src/module/cinepi_controller.py").read_text(encoding="utf-8")
        block = controller[controller.index("def can_reboot"):]
        block = block[:block.index("def reboot(")]
        self.assertIn('can_power("reboot")', block)

    def test_reboot_is_a_dispatchable_cli_verb(self):
        # The CLI/serial/web-API dispatcher still maps 'reboot' -- CLI and
        # serial callers, and any /api/v1/cmd caller with allow_destructive
        # on, still go through cinepi_controller.reboot this way. The
        # settings editor no longer does (see RebootPiTests above).
        self.assertRegex(CLI.read_text(encoding="utf-8"),
                         r"'reboot'\s*:\s*\(cinepi_controller\.reboot")


class CanPowerTests(unittest.TestCase):
    """can_power(verb) -- the general form can_reboot() now wraps.

    Neither method touches `self`, so these call it unbound against a bare
    stub rather than constructing a full CinePiController (a wide
    constructor wired to Redis, the sensor detector, and every step table --
    see entry-points.md's note on this class).
    """

    def test_true_when_sudo_grants_it(self):
        with mock.patch("module.cinepi_controller.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0)
            self.assertTrue(CinePiController.can_power(None, "poweroff"))
            run.assert_called_once_with(
                ["sudo", "-n", "-l", "/usr/bin/systemctl", "poweroff"],
                capture_output=True, text=True, timeout=5, check=False)

    def test_false_when_sudo_refuses(self):
        with mock.patch("module.cinepi_controller.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=1)
            self.assertFalse(CinePiController.can_power(None, "poweroff"))

    def test_false_when_sudo_is_missing_or_times_out(self):
        import subprocess
        with mock.patch("module.cinepi_controller.subprocess.run",
                         side_effect=subprocess.TimeoutExpired("sudo", 5)):
            self.assertFalse(CinePiController.can_power(None, "reboot"))

    def test_can_reboot_asks_can_power_for_the_reboot_verb(self):
        class Stub:
            asked = None

            def can_power(self, verb):
                self.asked = verb
                return True

        stub = Stub()
        self.assertTrue(CinePiController.can_reboot(stub))
        self.assertEqual(stub.asked, "reboot")


def _make_power_app(controller=None):
    """Same minimal-app pattern as test_settings_editor_format.py."""
    app = Flask(__name__)
    app.testing = True
    if controller is not None:
        app.config["CINEPI_CONTROLLER"] = controller
    app.register_blueprint(settings_editor_bp)
    return app


def _post_power(app, action):
    return app.test_client().post("/settings-editor/api/power", json={"action": action})


class PowerRouteTests(unittest.TestCase):
    """POST /settings-editor/api/power -- restart_cinemate / reboot / shutdown."""

    def test_unknown_action_is_400_and_dispatches_nothing(self):
        controller = mock.MagicMock()
        res = _post_power(_make_power_app(controller), "erase")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["ok"])
        controller.reboot.assert_not_called()
        controller.safe_shutdown.assert_not_called()
        controller.restart_cinemate.assert_not_called()

    def test_no_controller_attached_is_503(self):
        res = _post_power(_make_power_app(controller=None), "reboot")
        self.assertEqual(res.status_code, 503)
        self.assertFalse(res.get_json()["ok"])

    def test_restart_cinemate_is_scheduled_without_asking_sudoers(self):
        controller = mock.MagicMock()
        with mock.patch("module.app.settings_editor.threading.Timer") as timer_cls:
            timer = timer_cls.return_value
            res = _post_power(_make_power_app(controller), "restart_cinemate")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["scheduled"])
        controller.can_power.assert_not_called()
        timer_cls.assert_called_once_with(0.4, controller.restart_cinemate)
        timer.start.assert_called_once()

    def test_reboot_refuses_with_403_when_sudo_refuses(self):
        controller = mock.MagicMock()
        controller.can_power.return_value = False
        with mock.patch("module.app.settings_editor.threading.Timer") as timer_cls:
            res = _post_power(_make_power_app(controller), "reboot")
        self.assertEqual(res.status_code, 403)
        body = res.get_json()
        self.assertFalse(body["ok"])
        self.assertIn("not in its sudoers rule", body["message"])
        self.assertIn("cinemate-install.sh", body["message"])
        controller.can_power.assert_called_once_with("reboot")
        timer_cls.assert_not_called()
        controller.reboot.assert_not_called()

    def test_shutdown_refuses_with_403_when_sudo_refuses(self):
        controller = mock.MagicMock()
        controller.can_power.return_value = False
        with mock.patch("module.app.settings_editor.threading.Timer") as timer_cls:
            res = _post_power(_make_power_app(controller), "shutdown")
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.get_json()["ok"])
        controller.can_power.assert_called_once_with("poweroff")
        timer_cls.assert_not_called()
        controller.safe_shutdown.assert_not_called()

    def test_reboot_is_scheduled_on_a_timer_when_permitted(self):
        controller = mock.MagicMock()
        controller.can_power.return_value = True
        with mock.patch("module.app.settings_editor.threading.Timer") as timer_cls:
            timer = timer_cls.return_value
            res = _post_power(_make_power_app(controller), "reboot")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["scheduled"])
        timer_cls.assert_called_once_with(0.4, controller.reboot)
        timer.start.assert_called_once()

    def test_shutdown_is_scheduled_on_a_timer_when_permitted(self):
        controller = mock.MagicMock()
        controller.can_power.return_value = True
        with mock.patch("module.app.settings_editor.threading.Timer") as timer_cls:
            timer = timer_cls.return_value
            res = _post_power(_make_power_app(controller), "shutdown")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["scheduled"])
        timer_cls.assert_called_once_with(0.4, controller.safe_shutdown)
        timer.start.assert_called_once()


class ConfigPaneButtonsTests(unittest.TestCase):
    """The one power button left at the bottom of the config.txt pane.

    There used to be three -- Restart CineMate, Reboot Pi, Shut down Pi.
    Restart and Reboot were removed at the operator's request (2026-09-22):
    "Save & reboot Pi" sits directly above them in the same pane, so a bare
    Reboot Pi beside it was an invitation to discard the unsaved config.txt
    edits the pane was holding, and a CineMate restart does nothing for a file
    that is only read at boot. Both actions still exist in the System pane
    (genericRebootBtn / restartBtn), which is what the other tests in this
    file cover. Shutdown stayed, because ending a session at the rig is a
    reasonable thing to do from this pane.

    The removal must take the click handlers with it: a bare
    document.getElementById(id).addEventListener(...) throws on null and
    would take every listener registered after it down with it.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_only_shutdown_remains(self):
        self.assertIn('id="cfgShutdownBtn"', self.html)
        for button_id in ("cfgRestartBtn", "cfgGenericRebootBtn"):
            self.assertNotIn('id="%s"' % button_id, self.html,
                             "%s was removed from the config.txt pane" % button_id)

    def test_the_removed_buttons_left_no_listener_behind(self):
        for button_id in ("cfgRestartBtn", "cfgGenericRebootBtn"):
            self.assertNotIn("getElementById('%s')" % button_id, self.html,
                             "%s has no element to bind; the listener would "
                             "throw and kill the handlers after it" % button_id)

    def test_shutdown_does_not_save_config_txt(self):
        body = handler(self.html, "cfgShutdownBtn")
        self.assertNotIn("saveConfigTxt", body,
                         "cfgShutdownBtn must not write config.txt")

    def test_the_help_text_no_longer_promises_three_buttons(self):
        # The copy lives in resources/gui-text/, not the template, and it
        # used to read "these three never touch config.txt".
        md = (ROOT / "resources/gui-text/01-config-boot-config.md").read_text(encoding="utf-8")
        body = md[md.index("<!-- key: help.bootconfig.1 -->"):]
        body = body[:body.index("###", 10)]
        self.assertNotIn("these three", body)
        self.assertIn("config.txt", body)


class ShutdownHandlerTests(unittest.TestCase):
    """Shutdown never animates a return that is never coming."""

    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_both_shutdown_buttons_exist(self):
        self.assertIn('id="systemShutdownBtn"', self.html)
        self.assertIn('id="cfgShutdownBtn"', self.html)

    def test_neither_shutdown_handler_calls_run_boot_sequence(self):
        for button_id in ("systemShutdownBtn", "cfgShutdownBtn"):
            body = handler(self.html, button_id)
            self.assertNotIn("runBootSequence", body,
                              "%s must not claim the Pi comes back" % button_id)
            self.assertIn("powerAction('shutdown')", body)

    def test_shutdown_asks_for_confirmation_first(self):
        for button_id in ("systemShutdownBtn", "cfgShutdownBtn"):
            body = handler(self.html, button_id)
            self.assertIn("showConfirm(", body)
            self.assertIn("danger: true", body)

    def test_run_shutdown_sequence_never_claims_ready(self):
        start = self.html.index("function runShutdownSequence(")
        end = self.html.index("\n  }", start)
        body = self.html[start:end]
        self.assertNotIn("/api/v1/hello", body)
        self.assertNotIn("READY", body)
        self.assertIn("power can be removed", body)


if __name__ == "__main__":
    unittest.main()
