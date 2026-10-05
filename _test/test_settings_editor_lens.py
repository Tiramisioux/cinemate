"""The settings editor's Lens / Pinefeat pane: routes and markup.

Routes run against a real LensController wired to fakes (a scripted adapter, a
Redis that dedups like the real one) and a real LensDatabase in a temp dir. The
editor's own rule is tested too: with no camera running (LENS_CONTROLLER None)
and no Redis, the pane still reads the saved lenses straight from the file and
every command answers "camera not running" instead of failing.
"""
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

import flask  # noqa: E402

from lens_fakes import FakeBackend, FakeClock, FakeRedis, frame, no_encoder_sweep  # noqa: E402
from module.app.settings_editor import settings_editor_bp  # noqa: E402
from module.lens.controller import LensController  # noqa: E402
from module.lens.database import LensDatabase  # noqa: E402

TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"
CALLS = "/settings-editor/api/lens"

SIGMA = {"name": "Sigma 18-35 f/1.8", "lens_id": 235,
         "aperture": {"min": 1.8, "max": 16.0, "source": "manual"},
         "focus": {"calibrated_at": "2026-10-04T12:00:00Z", "position_min": 0, "position_max": 1069,
                   "mfd_m": 0.28, "distance_encoder": False, "map": [0.0, 1037, 3.57, 0],
                   "dioptre_min": 0.0, "dioptre_max": 3.57, "step_frames": 4}}


class PaneCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = LensDatabase(Path(tmp.name) / "lenses.json")
        self.clock = FakeClock()
        self.redis = FakeRedis({"lens_control": "1"})
        self.backend = FakeBackend(frame(lens_id=235))
        self.backend.sweep = no_encoder_sweep(step=100)
        self.ctrl = LensController(self.redis, database=self.db,
                                   backend_factory=lambda port, cams: (self.backend, ""),
                                   clock=self.clock, sleep=self.clock.sleep)

    def app(self, controller=True, database=True, settings=None):
        app = flask.Flask(__name__)
        app.register_blueprint(settings_editor_bp)
        app.config["SETTINGS"] = settings if settings is not None else {}
        if controller:
            app.config["LENS_CONTROLLER"] = self.ctrl
        if database:
            app.config["LENS_DATABASE"] = self.db
        return app

    def client(self, **kw):
        return self.app(**kw).test_client()

    def poll(self, n=1):
        for _ in range(n):
            self.ctrl.poll_once()
            self.clock.advance(0.25)

    def post(self, path, body=None, **kw):
        return self.client(**kw).post(f"{CALLS}{path}", json=body if body is not None else {})


class ReadTests(PaneCase):
    def test_status_and_entries_in_one_read(self):
        self.db.add(dict(SIGMA))
        self.poll()
        body = self.client().get(CALLS).get_json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["controller"])
        self.assertEqual(body["message"], "")
        st = body["status"]
        self.assertTrue(st["found"])
        self.assertEqual(st["provenance"], "v4l2-subdev")
        self.assertEqual(st["bus_description"], "i2c-0, from the cef168 subdev name")
        self.assertEqual(st["lens_id"], 235)
        entry = body["entries"][0]
        self.assertEqual(entry["name"], SIGMA["name"])
        self.assertEqual(entry["aperture"], "1.8-16")
        self.assertTrue(entry["calibrated"])
        self.assertEqual(entry["focus"]["points"], 2)
        self.assertEqual(entry["focus"]["mfd_m"], 0.28)
        self.assertEqual(body["database"]["path"], str(self.db.path))

    def test_it_does_no_bus_traffic(self):
        self.poll()
        reads = self.backend.reads
        for _ in range(5):
            self.client().get(CALLS)
        self.assertEqual(self.backend.reads, reads, "polling the pane must not read the adapter")

    def test_entries_are_sorted_by_name_for_the_dropdown(self):
        self.db.add({"name": "zeiss", "lens_id": 1})
        self.db.add({"name": "Angenieux", "lens_id": 2})
        names = [e["name"] for e in self.client().get(CALLS).get_json()["entries"]]
        self.assertEqual(names, ["Angenieux", "zeiss"])

    def test_calibration_progress_and_last_result_are_exposed(self):
        self.db.add(dict(SIGMA))
        self.poll()
        self.assertTrue(self.post("/calibrate").get_json()["ok"])
        self.poll(40)
        cal = self.client().get(CALLS).get_json()["status"]["calibration"]
        self.assertFalse(cal["running"])
        self.assertTrue(cal["last"]["ok"])
        self.assertIn("map", cal["last"]["focus"])
        self.assertFalse(cal["last"]["no_position_feedback"])


class NoCameraTests(PaneCase):
    """The editor's rule: it works with no camera and no Redis."""

    def test_saved_lenses_are_read_from_the_file_with_no_controller(self):
        self.db.add(dict(SIGMA))
        body = self.client(controller=False).get(CALLS).get_json()
        self.assertTrue(body["ok"])
        self.assertFalse(body["controller"])
        self.assertIsNone(body["status"])
        self.assertIn("camera is not running", body["message"])
        self.assertEqual([e["name"] for e in body["entries"]], [SIGMA["name"]])

    def test_the_database_comes_from_settings_when_none_was_handed_over(self):
        self.db.add(dict(SIGMA))
        settings = {"lens_control": {"database_file": str(self.db.path)}}
        body = self.client(controller=False, database=False, settings=settings).get(CALLS).get_json()
        self.assertEqual([e["name"] for e in body["entries"]], [SIGMA["name"]])

    def test_an_empty_database_is_an_empty_list_not_an_error(self):
        body = self.client(controller=False).get(CALLS).get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["entries"], [])

    def test_every_command_says_the_camera_is_not_running(self):
        for path, payload in (("/control", {"enabled": True}), ("/select", {"key": "x"}),
                              ("/save", {"name": "n"}), ("/aperture", {"min": 2, "max": 8}),
                              ("/calibrate", {})):
            res = self.post(path, payload, controller=False)
            self.assertEqual(res.status_code, 503, path)
            self.assertFalse(res.get_json()["ok"])
            self.assertIn("not running", res.get_json()["message"])

    def test_delete_works_with_no_camera(self):
        key = self.db.add(dict(SIGMA))
        res = self.client(controller=False).delete(f"{CALLS}/entries/{key}")
        self.assertTrue(res.get_json()["ok"])
        self.assertIsNone(self.db.get(key))

    def test_the_pane_template_renders_with_no_camera(self):
        res = self.client(controller=False).get("/settings-editor/")
        self.assertEqual(res.status_code, 200)
        self.assertIn('id="lens"', res.get_data(as_text=True))


class CommandTests(PaneCase):
    def test_the_toggle_works_when_found_and_is_refused_when_not(self):
        self.poll()
        self.assertTrue(self.post("/control", {"enabled": False}).get_json()["ok"])
        self.assertFalse(self.ctrl.enabled())
        self.assertTrue(self.post("/control", {"enabled": True}).get_json()["ok"])
        self.assertTrue(self.ctrl.enabled())

    def test_switching_on_without_the_adapter_is_refused_with_the_reason(self):
        self.redis.cache["lens_control"] = "0"
        self.ctrl = LensController(self.redis, database=self.db,
                                   backend_factory=lambda p, c: (None, "nothing at 0x0d"),
                                   clock=self.clock, sleep=self.clock.sleep)
        self.poll()
        res = self.post("/control", {"enabled": True})
        body = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertFalse(body["ok"])
        self.assertIn("nothing at 0x0d", body["message"])
        self.assertFalse(self.ctrl.enabled())

    def test_control_needs_a_real_boolean(self):
        self.assertEqual(self.post("/control", {"enabled": "yes"}).status_code, 400)
        self.assertEqual(self.post("/control", {}).status_code, 400)

    def test_select_and_unknown_key(self):
        key = self.db.add(dict(SIGMA))
        self.poll()
        self.assertEqual(self.ctrl.status()["lens_key"], key)       # auto-selected by id
        other = self.db.add({"name": "Canon", "lens_id": 77})
        ok = self.post("/select", {"key": other}).get_json()
        self.assertTrue(ok["ok"])
        self.assertIn("warning", ok["message"])                      # id differs from the mounted lens
        self.assertFalse(self.post("/select", {"key": "nope"}).get_json()["ok"])
        self.assertEqual(self.post("/select", {}).status_code, 400)

    def test_save_as_new_and_save_over(self):
        self.poll()
        self.assertEqual(self.ctrl.status()["state"], "unknown_lens")
        self.assertEqual(self.post("/save", {"name": "  "}).status_code, 400)
        res = self.post("/save", {"name": "Sigma 18-35 f/1.8"}).get_json()
        self.assertTrue(res["ok"], res)
        key = self.ctrl.status()["lens_key"]
        self.assertEqual(self.db.get(key)["name"], "Sigma 18-35 f/1.8")
        self.post("/aperture", {"min": 1.8, "max": 22})
        self.assertTrue(self.ctrl.status()["dirty"])
        self.assertTrue(self.post("/save", {"name": "Sigma renamed", "key": key}).get_json()["ok"])
        self.assertEqual(self.db.get(key)["name"], "Sigma renamed")
        self.assertEqual(self.db.get(key)["aperture"]["max"], 22.0)
        self.assertFalse(self.ctrl.status()["dirty"])
        self.assertEqual(len(self.db.entries()), 1, "save over must not add an entry")
        self.assertFalse(self.post("/save", {"name": "x", "key": "gone"}).get_json()["ok"])

    def test_aperture_set_validate_and_clear(self):
        self.poll()
        ok = self.post("/aperture", {"min": 2.0, "max": 11}).get_json()
        self.assertTrue(ok["ok"])
        self.assertEqual(self.ctrl.status()["aperture_range"], "2-11")
        bad = self.post("/aperture", {"min": 11, "max": 2}).get_json()
        self.assertFalse(bad["ok"])
        self.assertTrue(self.post("/aperture", {"min": None, "max": None}).get_json()["ok"])
        self.assertEqual(self.ctrl.status()["aperture_range"], "")
        self.assertFalse(self.post("/aperture", {"min": 2}).get_json()["ok"])

    def test_calibrate_is_refused_with_the_controllers_reason(self):
        self.poll()
        self.redis.cache["lens_control"] = "0"
        self.ctrl.set_enabled(False)
        off = self.post("/calibrate").get_json()
        self.assertFalse(off["ok"])
        self.assertIn("off", off["message"].lower())
        self.ctrl.set_enabled(True)
        self.redis.cache["rec"] = "1"
        rec = self.post("/calibrate").get_json()
        self.assertFalse(rec["ok"])
        self.assertIn("recording", rec["message"])
        self.redis.cache["rec"] = "0"
        self.assertTrue(self.post("/calibrate").get_json()["ok"])

    def test_calibrate_validates_the_minimum_focus_distance(self):
        self.poll()
        self.assertEqual(self.post("/calibrate", {"mfd_m": "abc"}).status_code, 400)
        self.assertEqual(self.post("/calibrate", {"mfd_m": 1000}).status_code, 400)
        self.assertTrue(self.post("/calibrate", {"mfd_m": 0.45}).get_json()["ok"])

    def test_the_no_focus_position_case_is_flagged_for_the_pane(self):
        from lens_fakes import sigma_no_feedback_sweep
        self.backend = FakeBackend(frame(lens_id=112))
        self.backend.sweep = sigma_no_feedback_sweep()
        self.ctrl = LensController(self.redis, database=self.db,
                                   backend_factory=lambda p, c: (self.backend, ""),
                                   clock=self.clock, sleep=self.clock.sleep)
        self.poll()
        self.assertTrue(self.post("/calibrate").get_json()["ok"])
        self.poll(30)
        st = self.client().get(CALLS).get_json()["status"]
        self.assertTrue(st["calibration"]["last"]["no_position_feedback"])
        self.assertFalse(st["calibration"]["last"]["ok"])
        self.assertIs(st["capabilities"]["focus"], False)

    def test_delete_removes_the_entry_and_unknown_is_404(self):
        key = self.db.add(dict(SIGMA))
        self.assertTrue(self.client().delete(f"{CALLS}/entries/{key}").get_json()["ok"])
        self.assertEqual(self.client().delete(f"{CALLS}/entries/{key}").status_code, 404)

    def test_deleting_the_selected_entry_keeps_the_working_lens_as_unsaved(self):
        key = self.db.add(dict(SIGMA))
        self.poll()
        self.client().delete(f"{CALLS}/entries/{key}")
        self.poll()
        st = self.client().get(CALLS).get_json()["status"]
        self.assertEqual(st["lens_key"], "")
        self.assertTrue(st["dirty"], "a calibration must not vanish with the entry")

    def test_a_controller_that_raises_is_a_500_not_a_crash(self):
        class Boom:
            def set_enabled(self, _):
                raise RuntimeError("x")
        app = self.app()
        app.config["LENS_CONTROLLER"] = Boom()
        res = app.test_client().post(f"{CALLS}/control", json={"enabled": True})
        self.assertEqual(res.status_code, 500)
        self.assertFalse(res.get_json()["ok"])


class PaneMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_the_page_has_a_lens_tab_and_landing_section(self):
        self.assertIn('data-page-tab="lens"', self.html)
        self.assertRegex(self.html, r'<section class="group" id="lens" data-page="lens">')
        self.assertIn("lens: 'lens'", self.html)

    def test_it_is_a_no_file_page_like_the_i2c_pane(self):
        self.assertIn("activePage === 'lens'", self.html.split("function syncTopbarForPage")[1][:900])

    def test_the_toggle_starts_disabled_and_is_disabled_unless_found(self):
        self.assertRegex(self.html, r'id="lensControlToggle"[^>]*disabled')
        self.assertIn("tog.disabled = !found;", self.html)

    def test_save_over_confirms_and_delete_confirms(self):
        over = re.search(r"lensEl\('lensSaveOver'\)\.addEventListener\('click'.*?\n  \}\);", self.html, re.S).group(0)
        self.assertIn("showConfirm(", over)
        self.assertIn("okLabel: 'Save over'", over)
        self.assertIn("showConfirm('Delete the saved lens", self.html)

    def test_the_dirty_marker_follows_working_dirty(self):
        self.assertIn("lensEl('lensDirtyChip').hidden = !(running && working.dirty);", self.html)

    def test_polling_stops_off_the_pane_and_never_overlaps(self):
        refresh = re.search(r"function lensRefresh\(\)\{(.*?)\n  \}\n", self.html, re.S).group(1)
        self.assertIn("activePage === 'lens' && !document.hidden", refresh)
        self.assertIn("if (lensLoading) return;", refresh)
        self.assertIn("else if (lensTimer){ clearTimeout(lensTimer); lensTimer = null; }", self.html)

    def test_a_poll_does_not_overwrite_what_the_operator_is_typing(self):
        render = re.search(r"function lensRender\(\)\{(.*?)\n  \}\n", self.html, re.S).group(1)
        self.assertIn("!lensTouched.name && document.activeElement !== nameEl", render)
        self.assertIn("!lensTouched.aperture", render)
        self.assertIn("document.activeElement !== sel", render)

    def test_calibration_refusals_stay_on_the_card(self):
        self.assertIn("'Not started: ' + res.message", self.html)

    def test_iris_only_note_and_failure_reason_are_shown(self):
        self.assertIn("Iris only: this lens never reported a focus position", self.html)
        self.assertIn("last.no_position_feedback", self.html)

    def test_the_pane_calls_its_own_routes_not_the_cmd_api(self):
        pane = self.html.split("/* ---------- Lens / Pinefeat pane ---------- */")[1].split("Which page a reload lands on")[0]
        self.assertNotIn("apiCmd(", pane)
        for route in ("/api/lens/control", "/api/lens/select", "/api/lens/save", "/api/lens/aperture",
                      "/api/lens/calibrate", "/api/lens/entries/"):
            self.assertIn(route, pane)

    def test_no_autofocus_ui_beyond_the_reserved_chip(self):
        pane = self.html.split("/* ---------- Lens / Pinefeat pane ---------- */")[1].split("Which page a reload lands on")[0]
        self.assertNotIn("af_once", pane)
        self.assertNotIn("autofocus_mode", pane)


if __name__ == "__main__":
    unittest.main()
