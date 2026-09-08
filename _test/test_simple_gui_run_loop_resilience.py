"""D2: one bad frame must not end the HDMI GUI thread.

`SimpleGUI.run()` was a single `try: ... finally:` around the whole `while`
loop with no `except`. Any exception on any frame ran `_teardown_display()`
and left the thread dead for the rest of the session -- nothing restarts it,
nothing tells the operator, and the framebuffer keeps whatever was last drawn.
The web GUI has no state of its own (it consumes this thread's
`populate_values()` dict over Socket.IO), so it freezes with it.

D1 was one instance of that. These tests cover the missing handler itself.
"""

import logging
import sys
import time
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("flask_socketio", types.SimpleNamespace(SocketIO=object))
sys.modules.setdefault("gpiozero", types.SimpleNamespace(CPUTemperature=object))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))
sys.modules.setdefault("sugarpie", types.SimpleNamespace(pisugar=types.SimpleNamespace()))

import threading

from module.simple_gui import SimpleGUI, FRAME_ERROR_LOG_INTERVAL_S


def make_loop_gui(populate_values, max_frames=3):
    """A SimpleGUI carrying only what run()'s loop body touches."""
    gui = SimpleGUI.__new__(SimpleGUI)
    gui._running = True
    gui._fast_dirty = True
    gui._slow_dirty = False
    gui._slow_values = {"x": 1}
    gui._last_slow_refresh_ts = time.monotonic()
    gui.slow_refresh_interval = 1000.0
    gui._redraw_event = threading.Event()
    gui.min_frame_interval = 0.0
    gui._last_draw_ts = 0.0
    gui._frame_error_state = {}
    gui._clear_framebuffer_on_exit = False
    gui._release_console_on_exit = False

    gui.calls = []
    gui.teardowns = []

    def _populate():
        gui.calls.append(time.monotonic())
        if len(gui.calls) >= max_frames:
            gui._running = False
        return populate_values()

    gui.check_display = lambda *a, **k: False
    gui._maybe_restart_camera_for_display_attach = lambda: None
    gui._vu_active = lambda: True
    gui._refresh_slow_values = lambda: None
    gui.update_smoothed_vu_levels = lambda: None
    gui.populate_values = _populate
    gui.draw_gui = lambda values: None
    gui._teardown_display = lambda **kwargs: gui.teardowns.append(kwargs)
    return gui


class RunLoopSurvivesFrameErrorsTests(unittest.TestCase):

    def test_a_throwing_populate_values_does_not_kill_the_thread(self):
        def _boom():
            raise AttributeError(
                "'CinePiController' object has no attribute 'file_size'"
            )

        gui = make_loop_gui(_boom, max_frames=3)

        with self.assertLogs(level=logging.ERROR):
            gui.run()

        # Three frames attempted, not one -- before the fix the first throw
        # was also the last frame of the session.
        self.assertEqual(len(gui.calls), 3)

    def test_teardown_still_runs_once_on_genuine_shutdown(self):
        gui = make_loop_gui(lambda: {}, max_frames=2)

        gui.run()

        self.assertEqual(len(gui.teardowns), 1)
        self.assertEqual(
            gui.teardowns[0],
            {"clear_framebuffer": False, "release_console": False},
        )

    def test_a_throwing_frame_still_tears_down_exactly_once_at_the_end(self):
        gui = make_loop_gui(lambda: (_ for _ in ()).throw(ValueError("nope")),
                            max_frames=4)

        with self.assertLogs(level=logging.ERROR):
            gui.run()

        self.assertEqual(len(gui.teardowns), 1)

    def test_keyboard_interrupt_is_not_swallowed(self):
        # `except Exception` deliberately excludes BaseException, so a real
        # shutdown still unwinds through the finally: instead of being
        # retried at frame rate forever.
        def _interrupt():
            raise KeyboardInterrupt

        gui = make_loop_gui(_interrupt, max_frames=99)

        with self.assertRaises(KeyboardInterrupt):
            gui.run()
        self.assertEqual(len(gui.teardowns), 1)

    def test_a_failing_frame_does_not_busy_spin(self):
        # The except branch has to leave the loop in the same shape a
        # completed frame does, or `due_in` stays 0 and the thread retries
        # the same broken frame as fast as the CPU allows.
        gui = make_loop_gui(lambda: (_ for _ in ()).throw(RuntimeError("x")),
                            max_frames=2)
        gui.min_frame_interval = 1 / 12

        with self.assertLogs(level=logging.ERROR):
            gui.run()

        self.assertGreater(gui._last_draw_ts, 0.0)
        self.assertFalse(gui._fast_dirty)
        self.assertFalse(gui._slow_dirty)


class FrameErrorLogRateLimitTests(unittest.TestCase):
    """A fault that reproduces every frame must not fill the journal at the
    refresh rate -- but the first occurrence must be loud and complete."""

    def _gui(self):
        gui = SimpleGUI.__new__(SimpleGUI)
        gui._frame_error_state = {}
        return gui

    def _raise(self, exc):
        try:
            raise exc
        except type(exc) as caught:
            return caught

    def test_first_occurrence_logs_the_traceback(self):
        gui = self._gui()
        exc = self._raise(AttributeError("no file_size"))

        with self.assertLogs(level=logging.ERROR) as captured:
            gui._handle_frame_error(exc)

        self.assertIn("Traceback", captured.output[0])

    def test_repeats_of_the_same_fault_are_suppressed(self):
        gui = self._gui()

        with self.assertLogs(level=logging.ERROR) as captured:
            for _ in range(50):
                gui._handle_frame_error(self._raise(AttributeError("no file_size")))

        self.assertEqual(len(captured.output), 1)

    def test_a_different_fault_is_logged_on_its_own(self):
        gui = self._gui()

        with self.assertLogs(level=logging.ERROR) as captured:
            gui._handle_frame_error(self._raise(AttributeError("a")))
            gui._handle_frame_error(self._raise(ValueError("b")))

        self.assertEqual(len(captured.output), 2)

    def test_a_persistent_fault_is_re_logged_after_the_interval(self):
        gui = self._gui()

        with self.assertLogs(level=logging.ERROR) as captured:
            gui._handle_frame_error(self._raise(AttributeError("a")))
            for key, (seen, _ts) in list(gui._frame_error_state.items()):
                gui._frame_error_state[key] = (
                    seen, time.monotonic() - FRAME_ERROR_LOG_INTERVAL_S - 1
                )
            gui._handle_frame_error(self._raise(AttributeError("a")))

        self.assertEqual(len(captured.output), 2)
        self.assertIn("still failing", captured.output[1])


if __name__ == "__main__":
    unittest.main()
