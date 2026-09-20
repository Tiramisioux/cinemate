"""The preview reload must not put a query string on the MJPEG URL, and it
must actually issue one.

cinepi-raw's preview is served by nadjieb cpp-mjpeg-streamer, which publishes
exactly one topic -- `streamer_->publish("/stream", ...)` in
mjpegPreviewStage.cpp -- and routes by the RAW request-target:

    mjpeg_streamer.hpp:68   std::getline(iss, target_, ' ');   // query included
    mjpeg_streamer.hpp:724  bool pathExists(p) { return topics_.find(p) != end; }
    mjpeg_streamer.hpp:890  if (!publisher_.pathExists(req.getTarget())) -> 404

So `GET /stream?reload=1756800000000` misses the map and the server answers 404
and closes the connection. An earlier version of `template.html` appended
exactly that cache-buster; this file still pins that it must never come back.

The second, larger thing this file pins is a different bug in the same
recovery path, found later. Measured in Chromium against a deliberately
silent MJPEG server (cinemate-handbook/working/browser-side-traps.md, "An
identical-URL src reset issues no request"): setting `img.src` back to the
SAME URL, in the SAME task, as `img.removeAttribute('src')` issues **no
network request at all** -- the browser joins the still-pending request
instead of opening a new one. That is precisely the "accepted-and-silent"
case every recovery signal in this file exists to catch (cinepi-raw
registers `/stream` before the first frame exists, so the connection is
accepted and then produces neither `error` nor `load`), so a single-callback
reload -- tear the src down and set it back in one synchronous function body
-- reconnects nothing: every four seconds the watchdog fired and re-armed a
request that was never sent.

The handbook (`working/browser-side-traps.md`, commit 1b947e8, 2026-09-07)
already described the fix this file now pins -- two timers (tear down,
settle 250ms, re-request) and a `streamReloadPending` flag that any other
"is a reload already under way?" check must consult, or it fires a second
teardown into the settle gap and cancels the re-request it was waiting for.
But `git log --all -S streamReloadPending` across this repository was empty
before this change landed: the measurement had happened in a browser and the
code never did. This test suite is what makes that no longer true, and pins
it so nobody goes looking for a commit that was never made.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "template.html"
SETTINGS_EDITOR = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


def _function_body(html, name):
    """Scrape a top-level function's source text by its closing brace.

    Every function this file inspects is defined at 4-space indentation
    (one level inside the page's IIFE) with no other 4-space-indented
    closing brace inside it -- nested callbacks all sit deeper -- so the
    first "\\n    }" after the signature is the function's own close.
    """
    start = html.index(f"function {name}(")
    rest = html[start:]
    end = rest.index("\n    }")
    return rest[: end + len("\n    }")]


class StreamReloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")
        cls.fn = _function_body(cls.html, "scheduleStreamReload")
        # Assert on code, not on comments -- a comment quotes the broken URL
        # on purpose, as the explanation for why it must not be built.
        cls.code = re.sub(r"//[^\n]*", "", cls.fn)
        cls.html_code = re.sub(r"//[^\n]*", "", cls.html)

    def test_no_cache_buster_is_appended_to_the_stream_url(self):
        self.assertNotIn("?reload=", self.code)
        self.assertNotIn("?reload=", self.html_code)

    def test_the_reload_requests_the_bare_stream_base(self):
        self.assertIn("img.src = img.dataset.streamBase;", self.code)

    def test_no_query_string_is_built_onto_any_stream_url(self):
        for m in re.finditer(r"dataset\.streamBase\s*\+", self.html_code):
            self.fail(f"stream URL is being concatenated at offset {m.start()}")

    def test_teardown_and_request_sit_in_different_setTimeout_callbacks(self):
        # Not "removeAttribute happens before img.src is reassigned" -- that
        # was already true in the single-callback version this replaces, and
        # was exactly the shape that issued no request. The requirement is
        # that a fresh setTimeout call separates the two: the re-request
        # cannot run in the same task as the teardown it follows.
        removed_at = self.code.index("img.removeAttribute('src')")
        requested_at = self.code.index("img.src = img.dataset.streamBase;")
        self.assertLess(removed_at, requested_at)
        between = self.code[removed_at:requested_at]
        self.assertIn(
            "setTimeout(",
            between,
            "img.src is reassigned in the same callback as removeAttribute() -- "
            "measured in Chromium to issue no network request at all for an "
            "identical URL (browser-side-traps.md)",
        )

    def test_a_settle_constant_is_named_and_used(self):
        self.assertIn("STREAM_RELOAD_SETTLE_MS = 250", self.html_code)
        self.assertIn("STREAM_RELOAD_SETTLE_MS", self.fn)


class StreamReloadPendingTests(unittest.TestCase):
    """`streamReloadPending` must be true for the whole tear-down-to-request
    span, and every other reconnect-detector must consult it before firing
    its own teardown -- otherwise a signal arriving during the 250ms settle
    gap cancels the re-request it was waiting for (browser-side-traps.md)."""

    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_streamReloadPending_exists_and_checks_both_timers(self):
        self.assertIn("function streamReloadPending(img)", self.html)
        fn = _function_body(self.html, "streamReloadPending")
        self.assertIn("_reloadTimerA", fn)
        self.assertIn("_reloadTimerB", fn)

    def test_scheduleStreamReload_tracks_two_distinct_timer_handles(self):
        fn = _function_body(self.html, "scheduleStreamReload")
        self.assertIn("_reloadTimerA", fn)
        self.assertIn("_reloadTimerB", fn)

    def test_the_dead_stream_sweep_consults_streamReloadPending(self):
        self.assertIn("naturalWidth === 0", self.html)
        sweep = self.html[self.html.index("naturalWidth === 0") - 400:]
        sweep = sweep[: sweep.index("\n    }") + len("\n    }")]
        self.assertIn("streamReloadPending", sweep)

    def test_no_stale_single_timer_field_remains(self):
        # The old shape tracked one timer handle (`_reloadTimer`); every
        # caller must have moved to the A/B pair above, or a leftover
        # reference would silently read `undefined` forever.
        self.assertNotRegex(self.html, r"_reloadTimer\b(?!A|B)")


class BfcacheAndVisibilityTests(unittest.TestCase):
    """A page pulled from bfcache resumes with a dead MJPEG connection and no
    event on the <img> ever fires for it; a backgrounded tab can miss
    reload_stream and have its own timers throttled past the 4s sweep."""

    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_pageshow_reloads_streams_when_restored_from_bfcache(self):
        self.assertIn("addEventListener('pageshow'", self.html)
        pageshow = self.html[self.html.index("addEventListener('pageshow'"):]
        pageshow = pageshow[: pageshow.index(");") + 2]
        self.assertIn("event.persisted", pageshow)
        self.assertIn("reloadStreams()", pageshow)

    def test_visibilitychange_runs_the_sweep_once_immediately(self):
        self.assertIn("addEventListener('visibilitychange'", self.html)
        handler = self.html[self.html.index("addEventListener('visibilitychange'"):]
        handler = handler[: handler.index(");") + 2]
        self.assertIn("visibilityState", handler)
        # Reuses the sweep's own dead-stream check rather than duplicating
        # it -- a comment asserting the two agree would be exactly the kind
        # of unchecked claim conventions/style.md warns against.
        self.assertIn("sweepDeadStreams", handler)


class FirstFrameWatchdogTests(unittest.TestCase):
    """A connection that is accepted and then silent must still recover.

    cinepi-raw registers /stream before the first frame exists, on purpose, so
    that a browser navigating to the clean preview during boot does not land on
    a 404. That is right for a person typing the address and a trap for the
    GUI's <img>: it used to get the 404, fire error, and recover through the
    retry below. Accepted-and-silent fires no error at all, so nothing retried
    and the preview stayed black until something else called reloadStreams() --
    which a resolution change does, and which is exactly how it was reported.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_a_watchdog_is_armed_when_a_src_is_set(self):
        self.assertIn("function armStreamWatchdog(img)", self.html)
        # both the markup's own src and every reconnect
        self.assertIn("armStreamWatchdog($('stream'));", self.html)
        reload_fn = _function_body(self.html, "scheduleStreamReload")
        self.assertIn("armStreamWatchdog(img)", reload_fn)

    def test_a_reconnect_is_watched_even_after_a_working_stream(self):
        # load fires once per connection, not per frame (measured on the
        # camera: zero load events in ten seconds of a running stream), so
        # _gotFrame describes the connection that set it and nothing else.
        # Carrying it across a reconnect left every recovery unwatched --
        # including the one reloadStreams() fires when the camera restarts,
        # which is precisely when the new connection is likely to be silent.
        reload_fn = _function_body(self.html, "scheduleStreamReload")
        self.assertIn("img._gotFrame = false;", reload_fn)
        self.assertLess(reload_fn.index("img._gotFrame = false;"),
                        reload_fn.index("img.src = img.dataset.streamBase;"))

    def test_the_first_frame_disarms_it_for_good(self):
        # not re-armed per load: whether a browser fires load per part of a
        # multipart/x-mixed-replace response is not worth betting a reconnect
        # loop on
        self.assertIn("img._gotFrame = true;", self.html)
        watchdog = _function_body(self.html, "armStreamWatchdog")
        self.assertIn("if (img._gotFrame) { return; }", watchdog)

    def test_the_watchdog_reconnects_rather_than_giving_up(self):
        watchdog = _function_body(self.html, "armStreamWatchdog")
        self.assertIn("scheduleStreamReload(img, 0)", watchdog)


class LiveViewLauncherHrefTests(unittest.TestCase):
    """The floating launcher in the settings editor used to hardcode
    `http://cinepi.local:5000`. On the hotspot the camera answers as
    10.42.0.1 and mDNS is not guaranteed (routes.py's `_stream_host()`
    exists for exactly this reason on the stream URL itself), so a
    hardcoded host sends the operator to an address that may not resolve
    from wherever the settings editor was actually reached. The web GUI is
    mounted at the app root (module/app/__init__.py registers main_routes
    with no url_prefix, settings_editor_bp at /settings-editor), so an
    origin-relative href reaches it from any host/port the page was loaded
    on -- no JS is involved, so this is a static markup check."""

    @classmethod
    def setUpClass(cls):
        cls.html = SETTINGS_EDITOR.read_text(encoding="utf-8")
        start = cls.html.index('id="cinepiLiveLauncher"')
        end = cls.html.index("</div>", start)
        cls.launcher = cls.html[start:end]

    def test_four_hrefs_present(self):
        hrefs = re.findall(r'href="([^"]*)"', self.launcher)
        self.assertEqual(len(hrefs), 4, hrefs)

    def test_no_href_carries_a_scheme_or_host(self):
        hrefs = re.findall(r'href="([^"]*)"', self.launcher)
        for href in hrefs:
            self.assertTrue(href.startswith("/"), href)
            self.assertNotIn("cinepi.local", href)
            self.assertNotIn("://", href)

    def test_the_preview_query_targets_are_unchanged(self):
        hrefs = re.findall(r'href="([^"]*)"', self.launcher)
        self.assertIn("/", hrefs)
        self.assertIn("/?preview=cam0", hrefs)
        self.assertIn("/?preview=cam1", hrefs)
        self.assertIn("/?preview=combined", hrefs)


if __name__ == "__main__":
    unittest.main()
