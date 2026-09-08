"""The restart console is a live tail of system.log, not a scripted animation.

It used to replay a hardcoded array of log lines on a setTimeout with random
jitter, which read as streaming output and was not. The invented lines also
contradicted the machine they appeared on: two cameras on a one-camera rig,
"phase_lock engaged" when phase lock ships off, Flask on :80 when it serves
:5000, and a fixed "iso 800 / 172.8 / 25 fps" whatever the camera was doing.
The card above it promised "the real startup sequence".

The file is tailed rather than the logger's queue being shared out. That queue
has a single consumer, so a second reader would steal records from whoever is
draining it, and every extra browser tab would compete for the same lines.
"""

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

import flask

from module.app import settings_editor as se

TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


class TailTests(unittest.TestCase):
    def _write(self, text):
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        self.addCleanup(os.unlink, path)
        return Path(path)

    def test_returns_the_last_n_lines(self):
        path = self._write("".join(f"line {i}\n" for i in range(500)))
        self.assertEqual(se._tail_lines(path, 3), ["line 497", "line 498", "line 499"])

    def test_a_short_file_returns_everything_it_has(self):
        path = self._write("only one\n")
        self.assertEqual(se._tail_lines(path, 200), ["only one"])

    def test_a_file_larger_than_the_read_block_still_tails_correctly(self):
        # read backwards in 8 KiB blocks; a log well past one block is the
        # normal case on a camera that has been up a while
        path = self._write("".join(f"{i:07d} padding to make the line long enough\n"
                                   for i in range(4000)))
        self.assertEqual(se._tail_lines(path, 2)[-1], "0003999 padding to make the line long enough")

    def test_a_missing_file_is_empty_not_an_exception(self):
        self.assertEqual(se._tail_lines(Path("/nonexistent/system.log"), 10), [])


class LogRouteTests(unittest.TestCase):
    def _app(self):
        app = flask.Flask(__name__)
        app.register_blueprint(se.settings_editor_bp)
        app.config["SETTINGS"] = {}
        return app

    def test_the_backlog_is_the_real_file(self):
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, "w") as handle:
            handle.write("first message\nsecond message\n")
        self.addCleanup(os.unlink, path)

        original = se._log_path
        se._log_path = lambda: Path(path)
        try:
            res = self._app().test_client().get("/settings-editor/api/logs")
            self.assertEqual(res.mimetype, "text/event-stream")
            seen = []
            for chunk in res.response:
                text = chunk.decode()
                seen.append(text)
                if "backlog-end" in text:
                    break
            res.close()
        finally:
            se._log_path = original

        body = "".join(seen)
        self.assertIn("first message", body)
        self.assertIn("second message", body)


class ConsoleMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_no_invented_log_lines_survive(self):
        for invented in (
            "[cinepi-raw] cam0 phase_lock engaged",
            "[web] Flask + Socket.IO listening on :80",
            "[cinemate] ready — iso 800",
            "[boot] config.txt reloaded from /boot/firmware",
        ):
            with self.subTest(line=invented):
                self.assertNotIn(invented, self.html)
        self.assertNotIn("var bootLines = [", self.html)
        self.assertNotIn("function buildRebootLines", self.html)

    def test_the_console_streams_the_real_log(self):
        self.assertIn("new EventSource('/settings-editor/api/logs')", self.html)
        self.assertIn("startLogStream(document.getElementById('console'))", self.html)

    def test_the_boot_config_console_streams_it_too(self):
        # It had no stream at all: a reboot there showed an invented
        # "$ sudo reboot" and a wait message, and the real startup sequence
        # went only to the settings page's console.
        self.assertIn("startLogStream(document.getElementById('cfgConsole'))", self.html)

    def test_one_connection_feeds_every_console(self):
        # The server caps SSE clients (system.web_api.max_sse_clients), so two
        # EventSources per tab would spend that budget on the same bytes twice.
        self.assertIn("var logSinks = []", self.html)
        self.assertIn("if (logStream) return;", self.html)

    def test_no_invented_shell_prompt(self):
        # runBootSequence used to print a "$ sudo ..." line that never matched
        # what actually ran -- a restart goes through systemd-run, not a bare
        # systemctl -- while the real sequence was already arriving in the
        # console underneath it.
        self.assertNotIn("command: '$ sudo", self.html)
        self.assertNotIn("say(opts.command", self.html)

    def test_a_restart_does_not_wipe_the_log(self):
        # the console carries runtime history; clearing it on restart would
        # throw away the lines explaining whatever prompted the restart
        engine = self.html[self.html.index("function runBootSequence(opts){"):]
        engine = engine[:engine.index("var restartBtn")]
        self.assertNotIn("innerHTML = ''", engine)

    def test_the_restart_reports_the_camera_actually_answering(self):
        self.assertIn("/api/v1/hello", self.html)
        self.assertIn("answering again after", self.html)

    def test_a_timeout_does_not_settle_on_READY(self):
        # Timing out means the camera never answered. finish(opts.readyText)
        # put "READY" on the status line anyway -- the one place the page had
        # to be straight about what had just happened.
        block = self.html[self.html.index("if (Date.now() > deadline){"):]
        block = block[:block.index("setTimeout(poll, 1500);")]
        self.assertIn("opts.timeoutText", block)
        self.assertNotIn("finish(opts.readyText", block)

    def test_the_wait_is_visibly_alive(self):
        # A silent spinner for up to three minutes is indistinguishable from a
        # page that has given up -- which is what a stuck "Rebooting the Pi —
        # please wait" looked like on the rig.
        self.assertIn("still waiting — ' + waited + ' s'", self.html)
        self.assertIn("function stopTicker()", self.html)
        # and it must not keep ticking after either exit
        engine = self.html[self.html.index("function runBootSequence(opts){"):]
        engine = engine[:engine.index("\n  }")]
        self.assertEqual(engine.count("stopTicker();"), 2)

    def test_the_first_poll_waits_so_it_cannot_see_the_old_server(self):
        # the server answers for a moment after the command is dispatched
        self.assertIn("opts.settleMs || 4000", self.html)

    def test_the_card_no_longer_promises_a_startup_sequence(self):
        self.assertNotIn("You'll see the real startup sequence", self.html)


class LogColourTests(unittest.TestCase):
    """The console mirrors the CLI's colours, from the CLI's own tables.

    The module-to-colour mapping is stated once, in logger.ColoredFormatter,
    and the route reads it -- so the template never has to know which module
    is which colour. What the template does own is the palette, one CSS rule
    per termcolor name, and that is what these guard.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def _colours(self):
        from module.logger import ColoredFormatter
        names = {e["color"] for e in ColoredFormatter.MODULE_COLORS.values()}
        names |= set(ColoredFormatter.LEVEL_COLORS.values())
        names.add("dark_grey")          # the fallback
        return names

    def test_every_colour_the_formatter_can_produce_has_a_rule(self):
        for name in sorted(self._colours()):
            with self.subTest(colour=name):
                self.assertRegex(self.html, rf"\.console \.lg-{name}\s*{{")

    def test_a_module_takes_its_own_colour_over_the_level(self):
        # redis_controller is green in MODULE_COLORS; the line is INFO, which
        # is also green -- so use one where they differ.
        self.assertEqual(se._line_colour(
            "2026-09-05 23:04:19.030: INFO: cinepi_multi something"), "blue")

    def test_an_unknown_module_falls_back_to_the_level(self):
        self.assertEqual(se._line_colour(
            "2026-09-05 23:04:19.030: WARNING: quad_rotary_controller x"), "yellow")
        self.assertEqual(se._line_colour(
            "2026-09-05 23:04:19.030: ERROR: _internal x"), "red")

    def test_an_unparseable_line_is_not_an_exception(self):
        self.assertEqual(se._line_colour("not a log line"), "dark_grey")

    def test_libcameras_own_escape_codes_are_stripped(self):
        # libcamera colours its stdout, cinepi-raw passes it through and
        # cinemate logs it verbatim, so the file carries real escapes that a
        # browser would show as literal "[1;32m" mid-message.
        raw = ("2026-09-05 23:22:21.126: INFO: cinepi_multi [cam0] "
               "\x1b[1;32m INFO \x1b[1;37mCamera \x1b[0mlibcamera v0.0.0")
        event = se._log_event(raw)
        self.assertNotIn("[1;32m", event)
        self.assertIn("libcamera v0.0.0", event)
        self.assertIn("INFO Camera", event)

    def test_the_client_takes_the_colour_from_the_server(self):
        self.assertIn("'lg-' + (colour || 'dark_grey')", self.html)


if __name__ == "__main__":
    unittest.main()
