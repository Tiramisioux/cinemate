"""The preview falls back to the same-origin relay when the direct URL is refused.

Measured on the camera 2026-09-20: the same `<img>`, in the same page, at the
same moment, reported `naturalWidth` 0 for `http://<host>:8000/stream` and
1280x720 for `/preview/0/stream`. Some browsers will not load a subresource
from a different port than the page, and an `<img>` refused that way fires no
event at all -- so every existing recovery path retried a request the browser
was never going to make, which is why the preview stayed black on a fresh load
until a resolution change reloaded the whole document.

`main/routes.py` already relays the stream from this origin. It was reserved
for HTTPS pages, where the obstacle is mixed content rather than the port.
These tests pin that the fallback exists, that it is a fallback rather than the
default (a browser that is happy cross-port must keep paying nothing), and that
both of the paths which notice a picture-less `<img>` take it.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/module/app/templates/template.html"
ROUTES = ROOT / "src/module/app/main/routes.py"


class SameOriginFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")
        cls.routes = ROUTES.read_text(encoding="utf-8")

    def test_the_relay_route_both_cameras_need_still_exists(self):
        # The fallback is only worth anything because this route is already
        # there; if it is ever removed, this test should be what notices.
        self.assertIn("/preview/<int:cam>/stream", self.routes)
        self.assertIn("def preview_stream(cam)", self.routes)

    def test_each_camera_maps_to_its_own_relay_path(self):
        block = self.html[self.html.index("function proxyBaseFor"):]
        block = block[:block.index("\n    }")]
        self.assertIn("/preview/0/stream", block)
        self.assertIn("/preview/1/stream", block)

    def test_the_fallback_is_one_way_and_happens_once(self):
        block = self.html[self.html.index("function fallBackToSameOrigin"):]
        block = block[:block.index("\n    }")]
        # Latched: a browser that has been refused once must not be sent back
        # to the direct URL by the next retry, or it flaps for the session.
        self.assertIn("img._usingProxy", block)
        self.assertIn("img.dataset.streamBase = proxyBaseFor(img)", block)

    def test_it_is_a_fallback_not_the_default(self):
        # The markup's own src must still be the direct URL, so a browser that
        # is happy cross-port never routes frames through Flask.
        self.assertIn("stream_url", self.html)
        first_paint = self.html[:self.html.index("function proxyBaseFor")]
        self.assertNotIn("/preview/0/stream", first_paint)

    def test_both_paths_that_notice_a_dead_img_take_the_fallback(self):
        watchdog = self.html[self.html.index("function armStreamWatchdog"):]
        watchdog = watchdog[:watchdog.index("STREAM_FIRST_FRAME_MS);")]
        self.assertIn("fallBackToSameOrigin(img)", watchdog)

        sweep = self.html[self.html.index("function sweepDeadStreams"):]
        sweep = sweep[:sweep.index("\n    }")]
        self.assertIn("fallBackToSameOrigin(img)", sweep)

    def test_the_fallback_runs_before_the_reconnect_it_depends_on(self):
        # Switching the base after scheduling the reload would reconnect to the
        # URL that just failed, and only fix itself a cycle later.
        for fn in ("function armStreamWatchdog", "function sweepDeadStreams"):
            block = self.html[self.html.index(fn):]
            block = block[:block.index("\n    }\n")]
            self.assertLess(
                block.index("fallBackToSameOrigin(img)"),
                block.index("scheduleStreamReload(img, 0)"),
                f"{fn} must switch the base before reconnecting",
            )

    def test_no_query_string_is_added_to_the_relay_path(self):
        # Same rule as the direct URL: cinepi-raw matches the raw request
        # target, and the relay forwards to it.
        self.assertNotIn("/preview/0/stream?", self.html)


if __name__ == "__main__":
    unittest.main()
