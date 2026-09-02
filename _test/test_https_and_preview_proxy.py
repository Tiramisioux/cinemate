"""HTTPS for the web UI, and the preview proxy that keeps it usable.

Serving the UI over TLS is not a free upgrade, and these tests pin the two
things that make it survivable:

1. cinepi-raw's MJPEG preview is plain HTTP on 8000/8001 and cannot speak TLS.
   A secure page may not load an insecure subresource, so a naive switch to
   HTTPS blacks out the live preview. main.routes serves the stream through a
   same-origin proxy when, and ONLY when, the page was served over TLS -- a
   plain-HTTP rig keeps talking straight to cinepi-raw and pays nothing.

2. cinepi.local and the hotspot's 10.42.0.1 can never hold a publicly-trusted
   certificate, so this is always self-signed and always shows an interstitial.
   It is therefore opt-in, and a camera that cannot mint a certificate falls
   back to plain HTTP rather than failing to serve at all.

Verified live, beyond these unit checks: Flask serving with the minted cert
over TLS returns the proxy path in the page; the proxy relays a real multipart
MJPEG stream (200, boundary preserved, JPEG SOI present); with no upstream it
returns 503 so the page's <img> error handler retries; and plain HTTP still
emits the direct http://<host>:8000/stream URL.
"""

import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))
_APP_PKG = types.ModuleType("module.app")
_APP_PKG.__path__ = [str(ROOT / "src" / "module" / "app")]
sys.modules.setdefault("module.app", _APP_PKG)

from flask import Flask

from module.app.main.routes import main_routes
from module.https_settings import (
    DEFAULT_HTTPS_SETTINGS,
    ensure_certificate,
    https_settings,
    ssl_context_for,
)

TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


def _app():
    app = Flask(
        __name__, template_folder=str(ROOT / "src" / "module" / "app" / "templates")
    )
    app.config["SIMPLE_GUI"] = types.SimpleNamespace(get_background_color=lambda: "black")
    app.config["SETTINGS"] = {}
    app.register_blueprint(main_routes)
    return app


class HttpsSettingsTests(unittest.TestCase):
    def test_off_by_default(self):
        self.assertFalse(DEFAULT_HTTPS_SETTINGS["enabled"])
        self.assertFalse(https_settings({})["enabled"])
        self.assertIsNone(ssl_context_for({}))

    def test_partial_block_keeps_the_other_defaults(self):
        cfg = https_settings({"system": {"https": {"enabled": True}}})
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["cert_file"], DEFAULT_HTTPS_SETTINGS["cert_file"])

    def test_unknown_keys_are_ignored(self):
        cfg = https_settings({"system": {"https": {"nonsense": 1}}})
        self.assertNotIn("nonsense", cfg)


@unittest.skipUnless(__import__("shutil").which("openssl"), "openssl not installed")
class CertificateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = {
            "enabled": True,
            "cert_file": str(self.tmp / "c.crt"),
            "key_file": str(self.tmp / "c.key"),
            "valid_days": 30,
        }

    def test_a_certificate_is_minted_with_the_names_a_camera_is_reached_by(self):
        cert, key = ensure_certificate(self.cfg)
        self.assertTrue(cert.is_file() and key.is_file())
        text = subprocess.run(
            ["openssl", "x509", "-in", str(cert), "-noout", "-text"],
            capture_output=True, text=True,
        ).stdout
        for name in ("cinepi.local", "127.0.0.1", "10.42.0.1"):
            self.assertIn(name, text)

    def test_the_private_key_is_not_world_readable(self):
        _, key = ensure_certificate(self.cfg)
        self.assertEqual(key.stat().st_mode & 0o077, 0)

    def test_an_existing_certificate_is_reused(self):
        cert, _ = ensure_certificate(self.cfg)
        stamp = cert.stat().st_mtime_ns
        ensure_certificate(self.cfg)
        self.assertEqual(cert.stat().st_mtime_ns, stamp)

    def test_a_camera_that_cannot_mint_one_still_serves(self):
        # Falling back to plain HTTP beats not answering on :5000 at all.
        with mock.patch("module.https_settings.shutil.which", return_value=None):
            self.assertIsNone(ensure_certificate(self.cfg))


class PreviewProxyTests(unittest.TestCase):
    def test_plain_http_talks_straight_to_cinepi_raw(self):
        html = _app().test_client().get("/").get_data(as_text=True)
        self.assertIn(":8000/stream", html)
        self.assertNotIn('src="/preview/', html)

    def test_https_uses_the_same_origin_proxy(self):
        # An absolute http:// stream URL on a secure page is blocked as mixed
        # content, and the preview goes black.
        html = _app().test_client().get(
            "/", base_url="https://cinepi.local:5000"
        ).get_data(as_text=True)
        self.assertIn('src="/preview/0/stream"', html)
        self.assertNotIn("http://cinepi.local:8000/stream", html)

    def test_the_proxy_reports_unavailable_rather_than_hanging(self):
        # Nothing is listening on 8000 in the test environment.
        resp = _app().test_client().get("/preview/0/stream")
        self.assertEqual(resp.status_code, 503)

    def test_only_the_two_real_cameras_are_proxied(self):
        self.assertEqual(_app().test_client().get("/preview/7/stream").status_code, 404)


class FolderDownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_the_button_is_hidden_until_the_api_is_known_to_exist(self):
        # showDirectoryPicker is undefined on a plain-HTTP origin and in
        # Safari/Firefox entirely, so the button must not be offered blindly.
        self.assertIn('id="bulkDownloadFolder" hidden', self.html)
        self.assertIn("typeof window.showDirectoryPicker === 'function'", self.html)

    def test_takes_are_written_one_at_a_time(self):
        # The old bulk path fired n top-level navigations 800ms apart, which
        # cancel each other; this chains them instead.
        self.assertIn("names.reduce(function(chain, name, i)", self.html)
        self.assertIn("res.body.pipeTo(w)", self.html)

    def test_dismissing_the_picker_is_not_reported_as_a_failure(self):
        self.assertIn("err.name === 'AbortError'", self.html)


if __name__ == "__main__":
    unittest.main()
