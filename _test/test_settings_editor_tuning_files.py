"""The settings editor must stop lying about tuning-file uploads, and the
picker must stop being two hardcoded option lists.

FINDINGS.md S1: the "Upload .json" control's `change` handler never uploaded
anything -- it fabricated an `<option>` client-side and toasted "Uploaded
<name> to resources/tuning_files/" regardless. FINDINGS.md S3.3: the picker
itself is a literal HTML option list at two template call sites, so a file
copied into resources/tuning_files/ over SSH (the documented procedure)
never appears until the operator re-adds it by name through that same
control.

PLAN.md S1.2/S1.3 is the fix: GET/POST /settings-editor/api/tuning-files,
backed by a real directory listing (_list_tuning_files()) and a real,
validated write, with index() rendering both cam0/cam1 pickers from that
same listing instead of a hardcoded list. The upload route shares its JSON
validation (target == "pisp", an "algorithms" list) with the launch guard in
module.tuning_files, so the editor and the launch-time fallback can never
disagree about what counts as a usable tuning file.

Harness copied from test_settings_editor_sensor_db.py: a bare Flask app
registering the real blueprint, with module.app stubbed to an empty package
(so importing the blueprint does not need flask_socketio) and TUNING_FILES_DIR
patched to a scratch directory seeded with two files, so nothing here reads
or writes the repo's real resources/tuning_files/.
"""

import json
import re
import sys
import tempfile
import types
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

_APP_PKG = types.ModuleType("module.app")
_APP_PKG.__path__ = [str(ROOT / "src" / "module" / "app")]
sys.modules.setdefault("module.app", _APP_PKG)

from flask import Flask  # noqa: E402

from module.app import settings_editor  # noqa: E402
from module.app.settings_editor import settings_editor_bp  # noqa: E402

# Not imported from module.app.settings_editor at module scope: that name
# does not exist on dev, and an ImportError here would fail collection of
# this whole file instead of letting each route test fail on its own
# assertion (404, today) the way PLAN.md S4.2 expects. PLAN.md S1.2 fixes
# this value at 4 MiB -- the largest shipped tuning file is 90 KB -- so it is
# safe to assume here rather than reach into the module for it.
TUNING_FILE_MAX_BYTES = 4 * 1024 * 1024

TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"

VALID_PISP_JSON = json.dumps({"version": 2.0, "target": "pisp", "algorithms": []}).encode("utf-8")
BCM2835_JSON = json.dumps({"version": 2.0, "target": "bcm2835", "algorithms": []}).encode("utf-8")


def _client(settings=None):
    app = Flask(__name__)
    app.config["SETTINGS"] = settings or {"sensors": {}}
    app.register_blueprint(settings_editor_bp)
    return app.test_client()


class _SeededTuningDirCase(unittest.TestCase):
    """Seeds a scratch resources/tuning_files/ with two valid pisp files and
    points the blueprint at it for the duration of the test."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tuning_dir = Path(tmp.name)
        (self.tuning_dir / "custom_a.json").write_bytes(VALID_PISP_JSON)
        (self.tuning_dir / "custom_b.json").write_bytes(VALID_PISP_JSON)
        # create=True: TUNING_FILES_DIR does not exist as a module attribute
        # on dev yet. Without it, patch.object raises AttributeError out of
        # setUp() on dev, turning every route test into a setup error instead
        # of the 404 PLAN.md S4.2 expects from the missing route itself.
        patcher = mock.patch.object(settings_editor, "TUNING_FILES_DIR", self.tuning_dir, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)


class TuningFileRouteTests(_SeededTuningDirCase):
    def test_get_lists_the_seeded_folder(self):
        resp = _client().get("/settings-editor/api/tuning-files")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["dir"], "resources/tuning_files")
        names = [f["name"] for f in body["files"]]
        self.assertEqual(names, ["custom_a.json", "custom_b.json"])
        for f in body["files"]:
            self.assertEqual(f["path"], f"resources/tuning_files/{f['name']}")

    def test_page_is_rendered_from_the_folder(self):
        html = _client().get("/settings-editor/").get_data(as_text=True)
        self.assertEqual(
            html.count('<option value="resources/tuning_files/custom_a.json">'), 2,
            "expected one option per camera (cam0, cam1)",
        )
        self.assertNotIn("resources/tuning_files/imx219.json", html)

    def test_post_accepts_a_pisp_file(self):
        resp = _client().post(
            "/settings-editor/api/tuning-files",
            data={"file": (BytesIO(VALID_PISP_JSON), "custom_c.json")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["path"], "resources/tuning_files/custom_c.json")
        written = self.tuning_dir / "custom_c.json"
        self.assertTrue(written.is_file())
        self.assertEqual(written.read_bytes(), VALID_PISP_JSON)

    def test_post_refuses_a_bcm2835_target(self):
        resp = _client().post(
            "/settings-editor/api/tuning-files",
            data={"file": (BytesIO(BCM2835_JSON), "vc4.json")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)
        message = resp.get_json()["message"]
        self.assertIn("bcm2835", message)
        self.assertIn("pisp", message)
        self.assertFalse((self.tuning_dir / "vc4.json").exists())

    def test_post_refuses_non_json_body(self):
        resp = _client().post(
            "/settings-editor/api/tuning-files",
            data={"file": (BytesIO(b"not json"), "bad.json")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse((self.tuning_dir / "bad.json").exists())

    def test_post_refuses_a_non_json_name(self):
        resp = _client().post(
            "/settings-editor/api/tuning-files",
            data={"file": (BytesIO(VALID_PISP_JSON), "custom.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse((self.tuning_dir / "custom.txt").exists())

    def test_post_refuses_an_oversize_body(self):
        oversized = b"{" + b" " * (TUNING_FILE_MAX_BYTES + 1) + b"}"
        resp = _client().post(
            "/settings-editor/api/tuning-files",
            data={"file": (BytesIO(oversized), "big.json")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse((self.tuning_dir / "big.json").exists())

    def test_post_refuses_an_existing_name(self):
        resp = _client().post(
            "/settings-editor/api/tuning-files",
            data={"file": (BytesIO(VALID_PISP_JSON), "custom_a.json")},
            content_type="multipart/form-data",
        )
        self.assertEqual(resp.status_code, 409)
        # Untouched -- still the seed content, not (coincidentally identical
        # here, but the point is the write must never have been attempted).
        self.assertEqual((self.tuning_dir / "custom_a.json").read_bytes(), VALID_PISP_JSON)


class TuningFilePlatformTests(_SeededTuningDirCase):
    """PLAN D19: the picker shows each file's target, marks the ones this Pi
    cannot load, and the upload route validates against the running platform."""

    def setUp(self):
        super().setUp()
        (self.tuning_dir / "vc4_a.json").write_bytes(BCM2835_JSON)
        (self.tuning_dir / "broken.json").write_bytes(b"not json")

    def _as(self, pi4):
        patcher = mock.patch.object(settings_editor, "is_pi4_family", return_value=pi4)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _files(self):
        body = _client().get("/settings-editor/api/tuning-files").get_json()
        return body, {f["name"]: f for f in body["files"]}

    def test_a_pi5_marks_the_vc4_file_and_the_unreadable_one(self):
        self._as(False)
        body, files = self._files()
        self.assertEqual(body["platform_target"], "pisp")
        self.assertEqual(files["custom_a.json"]["target"], "pisp")
        self.assertTrue(files["custom_a.json"]["matches_platform"])
        self.assertEqual(files["custom_a.json"]["label"], "custom_a.json (pisp)")
        self.assertFalse(files["vc4_a.json"]["matches_platform"])
        self.assertIn("bcm2835", files["vc4_a.json"]["label"])
        self.assertIn("not for this Pi 5", files["vc4_a.json"]["label"])
        self.assertIsNone(files["broken.json"]["target"])
        self.assertFalse(files["broken.json"]["matches_platform"])

    def test_a_pi4_flips_which_files_match(self):
        self._as(True)
        body, files = self._files()
        self.assertEqual(body["platform_target"], "bcm2835")
        self.assertTrue(files["vc4_a.json"]["matches_platform"])
        self.assertFalse(files["custom_a.json"]["matches_platform"])
        self.assertIn("not for this Pi 4", files["custom_a.json"]["label"])

    def test_the_page_marks_a_mismatched_option(self):
        self._as(True)
        html = _client().get("/settings-editor/").get_data(as_text=True)
        self.assertIn('<option value="resources/tuning_files/custom_a.json" class="tune-mismatch">', html)
        self.assertIn('<option value="resources/tuning_files/vc4_a.json">', html)

    def test_a_pi4_accepts_a_vc4_upload_and_refuses_a_pisp_one(self):
        self._as(True)
        ok = _client().post("/settings-editor/api/tuning-files",
                            data={"file": (BytesIO(BCM2835_JSON), "vc4_new.json")},
                            content_type="multipart/form-data")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.get_json()["target"], "bcm2835")
        self.assertIn("bcm2835", ok.get_json()["label"])
        bad = _client().post("/settings-editor/api/tuning-files",
                             data={"file": (BytesIO(VALID_PISP_JSON), "pisp_new.json")},
                             content_type="multipart/form-data")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("pisp", bad.get_json()["message"])
        self.assertFalse((self.tuning_dir / "pisp_new.json").exists())

    def test_a_pi5_still_refuses_a_vc4_upload(self):
        self._as(False)
        bad = _client().post("/settings-editor/api/tuning-files",
                             data={"file": (BytesIO(BCM2835_JSON), "vc4_new.json")},
                             content_type="multipart/form-data")
        self.assertEqual(bad.status_code, 400)


class TuningFileTemplateStructureTests(unittest.TestCase):
    """Structural guards in the style of test_settings_editor_page_restore.py
    -- pin that the code is present; the unlisted-value behaviour itself
    needs a browser and is hardware-gate item 4 in PLAN.md S5."""

    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_both_tuning_selects_accept_an_unlisted_value(self):
        for cam in ("c0", "c1"):
            m = re.search(
                rf'id="f-{cam}-tunefile"[^>]*>', self.html
            )
            self.assertIsNotNone(m, f"f-{cam}-tunefile select not found")
            self.assertIn('data-accept-unlisted="1"', m.group(0))

    def test_upload_handler_posts_to_the_real_route(self):
        self.assertIn("fetch('/settings-editor/api/tuning-files'", self.html)

    def test_uploaded_option_uses_the_servers_label(self):
        self.assertIn("opt.textContent = data.label || data.name;", self.html)

    def test_client_side_fabrication_is_gone(self):
        self.assertNotIn("opt.value = 'resources/tuning_files/' + file.name;", self.html)

    def test_apply_control_value_handles_unlisted_selects(self):
        m = re.search(r"function applyControlValue\(el, value\)\{.*?\n  \}\n", self.html, re.S)
        self.assertIsNotNone(m, "applyControlValue function not found")
        self.assertIn("data-accept-unlisted", m.group(0))


if __name__ == "__main__":
    unittest.main()
