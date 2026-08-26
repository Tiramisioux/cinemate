"""The web GUI didn't refresh automatically on a resolution change, and the
switch-complete path could double-fire. Three defects, one fix:

D1 (client) -- a frozen MJPEG <img> after a cinepi-raw restart fires neither
`error` nor a naturalWidth drop, so the single `reload_stream` emit was the
only recovery path; miss it (backgrounded tab, socket hiccup during the
restart) and the preview stays frozen until a manual refresh.

D2 (server) -- `restart()` runs synchronously inside `_apply_resolution_mode`,
so cinepi-raw's "Raw stream: WxH" evidence usually clears RESOLUTION_SWITCHING
and fires switch-complete *before* `_schedule_resolution_switch_complete` is
even called. The fallback timer got scheduled anyway and fired a second,
redundant switch-complete `GUI_RESOLUTION_SWITCHING_HOLD_SECONDS` later.

D3 (requirement) -- resolution changes only reloaded the stream `<img>`; the
operator wants the white-balance behaviour, a full automatic browser refresh
once the switch completes.

Fix: (A) module/app/__init__.py's switch-complete callback now also schedules
a deferred `reload_browser` emit -- same threading.Timer shape as the WB path
in main/events.py -- gated off while recording and debounced to one pending
timer per switch. (B) cinepi_controller.py's _schedule_resolution_switch_complete
returns before scheduling if RESOLUTION_SWITCHING is already 0 -- the evidence
path already completed this switch during the synchronous restart. (C)
template.html gives stream recovery a second, independent path: it tracks the
resolution_switching truthy->falsy edge (fed by the Redis fan-out, not by the
reload_stream emit) and calls reloadStreams() on that edge.

This checks the wiring end to end against the real sources -- no Flask app is
constructed and no browser runs.
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_INIT = ROOT / "src/module/app/__init__.py"
CINEPI_CONTROLLER = ROOT / "src/module/cinepi_controller.py"
TEMPLATE = ROOT / "src/module/app/templates/template.html"


class WebGuiResolutionAutoRefreshTests(unittest.TestCase):
    def setUp(self):
        self.app_init_src = APP_INIT.read_text(encoding="utf-8")
        self.cinepi_controller_src = CINEPI_CONTROLLER.read_text(encoding="utf-8")
        self.template_src = TEMPLATE.read_text(encoding="utf-8")

    # -- A: server schedules a deferred, gated reload_browser -------------

    def test_switch_complete_callback_schedules_reload_browser_via_timer(self):
        m = re.search(
            r"def emit_reload_stream\(\):(.*?)\n        cinepi_controller\."
            r"add_resolution_switch_complete_callback",
            self.app_init_src,
            re.S,
        )
        self.assertIsNotNone(m, "emit_reload_stream callback not found")
        body = m.group(1)
        self.assertIn(
            "socketio.emit('reload_stream')",
            body,
            "switch-complete callback no longer emits reload_stream",
        )
        self.assertIn(
            "threading.Timer(2.0,",
            body,
            "reload_browser is no longer scheduled on a deferred 2.0s threading.Timer",
        )
        self.assertIn(
            "socketio.emit('reload_browser')",
            body,
            "the deferred timer no longer emits reload_browser",
        )

    def test_reload_browser_is_gated_on_is_recording(self):
        self.assertRegex(
            self.app_init_src,
            r"ParameterKey\.IS_RECORDING\.value\)\s*==\s*\"1\"",
            "reload_browser scheduling lost its IS_RECORDING gate",
        )

    def test_reload_browser_is_debounced_to_one_pending_timer(self):
        # A closure variable must hold the live Timer and be checked before
        # scheduling another one -- otherwise every switch-complete during a
        # single switch would queue its own page reload.
        self.assertIn("reload_browser_timer", self.app_init_src)
        self.assertRegex(
            self.app_init_src,
            r"if reload_browser_timer is not None:\s*\n(?:\s*#.*\n)*\s*return",
            "no debounce guard against a second pending reload_browser timer",
        )

    # -- B: single-fire switch-complete -----------------------------------

    def test_schedule_resolution_switch_complete_has_already_complete_guard(self):
        m = re.search(
            r"def _schedule_resolution_switch_complete\(self, value, resolution_info\):"
            r"(.*?)\n    def ",
            self.cinepi_controller_src,
            re.S,
        )
        self.assertIsNotNone(m, "_schedule_resolution_switch_complete not found")
        body = m.group(1)
        cancel_idx = body.find("self._cancel_resolution_switching_timer()")
        guard_idx = body.find(
            "as_bool(self.redis_controller.get_value(ParameterKey.RESOLUTION_SWITCHING.value))"
        )
        self.assertNotEqual(cancel_idx, -1, "timer cancel call missing")
        self.assertNotEqual(guard_idx, -1, "already-complete guard missing")
        self.assertLess(
            cancel_idx,
            guard_idx,
            "already-complete guard must run after cancelling the fallback timer",
        )
        guard_to_timer = body[guard_idx:body.find("threading.Timer", guard_idx)]
        self.assertIn(
            "return",
            guard_to_timer,
            "an already-0 RESOLUTION_SWITCHING must return without scheduling",
        )

    # -- C: client-side falling-edge redundancy ----------------------------

    def test_template_handles_reload_browser(self):
        self.assertIn(
            "socket.on('reload_browser'",
            self.template_src,
            "template.html no longer handles reload_browser",
        )

    def test_template_seeds_the_edge_tracker_from_initial_values(self):
        m = re.search(
            r"socket\.on\('initial_values', \(data\) => \{(.*?)\n    \}\);",
            self.template_src,
            re.S,
        )
        self.assertIsNotNone(m, "initial_values handler not found")
        self.assertIn(
            "resolution_switching",
            m.group(1),
            "initial_values handler no longer seeds the resolution_switching tracker "
            "-- page load would be misread as a falling edge",
        )

    def test_resolution_switching_assignment_reacts_to_the_edge(self):
        for event in ("parameter_change", "resolution_change"):
            with self.subTest(event=event):
                m = re.search(
                    rf"socket\.on\('{event}', \(data\) => \{{(.*?)\n    \}}\);",
                    self.template_src,
                    re.S,
                )
                self.assertIsNotNone(m, f"{event} handler not found")
                body = m.group(1)
                switching_idx = body.find(
                    "V.resolution_switching = data.resolution_switching;"
                )
                self.assertNotEqual(
                    switching_idx, -1, f"{event} no longer assigns V.resolution_switching"
                )
                after = body[switching_idx:]
                self.assertRegex(
                    after,
                    r"reloadStreams\(\)|noteResolutionSwitching\(\)",
                    f"{event} no longer reacts to the resolution_switching edge",
                )

    def test_falling_edge_helper_uses_truthy_and_reloads_streams(self):
        m = re.search(
            r"function noteResolutionSwitching\(\) \{(.*?)\n    \}",
            self.template_src,
            re.S,
        )
        self.assertIsNotNone(m, "noteResolutionSwitching() not found")
        body = m.group(1)
        self.assertIn("truthy(", body, "falling-edge check no longer uses truthy()")
        self.assertIn(
            "reloadStreams()", body, "falling edge no longer calls reloadStreams()"
        )


if __name__ == "__main__":
    unittest.main()
