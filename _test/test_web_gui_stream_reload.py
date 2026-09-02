"""The preview reload must not put a query string on the MJPEG URL.

cinepi-raw's preview is served by nadjieb cpp-mjpeg-streamer, which publishes
exactly one topic -- `streamer_->publish("/stream", ...)` in
mjpegPreviewStage.cpp -- and routes by the RAW request-target:

    mjpeg_streamer.hpp:68   std::getline(iss, target_, ' ');   // query included
    mjpeg_streamer.hpp:724  bool pathExists(p) { return topics_.find(p) != end; }
    mjpeg_streamer.hpp:890  if (!publisher_.pathExists(req.getTarget())) -> 404

So `GET /stream?reload=1756800000000` misses the map and the server answers 404
and closes the connection. template.html appended exactly that cache-buster,
and every recovery path funnels through the one function that did it:
`reload_stream` from the socket, the socket-reconnect path, the end of a
resolution switch, and the naturalWidth watchdog. None could succeed, and the
`error` handler re-armed the same broken request once a second forever.

It was worse than inert. cinepi-raw deliberately keeps the MJPEG listener and
its clients alive across a camera reconfigure (mjpegPreviewStage.cpp Teardown/
Configure), so the operator's existing connection would have survived a
resolution change on its own -- the reload code aborted a working stream and
replaced it with a permanent 404. Recovery only came from a full page reload,
which requests the clean server-rendered URL, and which is suppressed while
recording. Hence "flaky" rather than "always broken".

Verified against a harness made faithful to that routing (the stock desk
harness did `self.path.split("?")[0]`, which is why this never reproduced):
`/stream?reload=...` -> 404, `/stream` -> 200, and a stream drop/restore cycle
now produces two clean `/stream` requests and no 404s.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "template.html"


class StreamReloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")
        m = re.search(r"function scheduleStreamReload\(.*?\n    \}", cls.html, re.S)
        assert m, "scheduleStreamReload not found"
        cls.fn = m.group(0)
        # Assert on code, not on comments -- the comment quotes the broken URL
        # on purpose, as the explanation for why it must not be built.
        cls.code = re.sub(r"//[^\n]*", "", cls.fn)
        cls.html_code = re.sub(r"//[^\n]*", "", cls.html)

    def test_no_cache_buster_is_appended_to_the_stream_url(self):
        self.assertNotIn("?reload=", self.code)
        self.assertNotIn("?reload=", self.html_code)

    def test_the_reload_requests_the_bare_stream_base(self):
        self.assertIn("img.src = img.dataset.streamBase;", self.code)

    def test_it_still_forces_a_refetch_of_an_identical_url(self):
        # Reassigning the same src is a no-op; dropping it first is what makes
        # the browser reconnect, and is why the cache-buster existed at all.
        self.assertIn("img.removeAttribute('src')", self.code)
        self.assertLess(
            self.code.index("img.removeAttribute('src')"),
            self.code.index("img.src = img.dataset.streamBase;"),
        )

    def test_no_query_string_is_built_onto_any_stream_url(self):
        for m in re.finditer(r"dataset\.streamBase\s*\+", self.html_code):
            self.fail(f"stream URL is being concatenated at offset {m.start()}")


if __name__ == "__main__":
    unittest.main()
