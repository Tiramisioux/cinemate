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
        self.assertIn("data: first message", body)
        self.assertIn("data: second message", body)


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

    def test_a_restart_does_not_wipe_the_log(self):
        # the console carries runtime history; clearing it on restart would
        # throw away the lines explaining whatever prompted the restart
        engine = self.html[self.html.index("function runBootSequence(opts){"):]
        engine = engine[:engine.index("var restartBtn")]
        self.assertNotIn("innerHTML = ''", engine)

    def test_the_restart_reports_the_camera_actually_answering(self):
        self.assertIn("/api/v1/hello", self.html)
        self.assertIn("answering again after", self.html)

    def test_the_first_poll_waits_so_it_cannot_see_the_old_server(self):
        # the server answers for a moment after the command is dispatched
        self.assertIn("opts.settleMs || 4000", self.html)

    def test_the_card_no_longer_promises_a_startup_sequence(self):
        self.assertNotIn("You'll see the real startup sequence", self.html)


if __name__ == "__main__":
    unittest.main()
