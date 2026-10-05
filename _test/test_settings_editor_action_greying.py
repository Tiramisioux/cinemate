"""D11: the Lens (Pinefeat) actions stay visible and assignable in the editor's
action picker, greyed with the reason while lens control is not effective.

/api/actions carries `greyed` + `grey_reason` (settings_editor.get_actions);
the page consumes them in applyActionGrey(). The server half is tested through
a real Flask client, the page half structurally -- what the browser does with
an <option> needs a browser, and was checked in one (see the WP4 report).
"""
import re
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

import flask  # noqa: E402

from module.app.settings_editor import LENS_ACTION_GROUP, settings_editor_bp  # noqa: E402

TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


class FakeLens:
    def __init__(self, found=True, enabled=True, message="Sigma ready"):
        self._s = {"found": found, "enabled": enabled, "effective": found and enabled,
                   "message": message}

    def status(self):
        return dict(self._s)


def actions(lens=None, with_lens=True):
    app = flask.Flask(__name__)
    app.register_blueprint(settings_editor_bp)
    app.config["SETTINGS"] = {}
    if with_lens:
        app.config["LENS_CONTROLLER"] = lens
    body = app.test_client().get("/settings-editor/api/actions").get_json()
    return body["actions"]


def lens_actions(acts):
    return [a for a in acts if a["group"] == LENS_ACTION_GROUP]


class ActionGreyingRouteTests(unittest.TestCase):
    def test_effective_lens_control_greys_nothing(self):
        for a in lens_actions(actions(FakeLens())):
            self.assertNotIn("greyed", a)

    def test_switched_off_greys_the_lens_group_with_the_reason(self):
        acts = actions(FakeLens(enabled=False))
        self.assertTrue(lens_actions(acts))
        for a in lens_actions(acts):
            self.assertTrue(a["greyed"])
            # not the lens message ("Sigma ready"), which says nothing of why
            self.assertEqual(a["grey_reason"], "Lens control is off")

    def test_an_absent_adapter_greys_them_with_its_own_message(self):
        acts = actions(FakeLens(found=False, enabled=False, message="Lens adapter not found: nothing on i2c-6"))
        for a in lens_actions(acts):
            self.assertIn("not found", a["grey_reason"])

    def test_no_controller_greys_them_too(self):
        for a in lens_actions(actions(None)):
            self.assertTrue(a["greyed"])

    def test_other_groups_are_never_greyed(self):
        for a in actions(FakeLens(enabled=False)):
            if a["group"] != LENS_ACTION_GROUP:
                self.assertNotIn("greyed", a)

    def test_greyed_actions_are_still_listed(self):
        # a saved button layout must keep pointing at something
        names = {a["value"] for a in lens_actions(actions(FakeLens(enabled=False)))}
        self.assertTrue({"set_iris", "inc_iris", "calibrate_lens", "set_lens"} <= names)


class ActionGreyingPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_the_page_fetches_the_greying(self):
        self.assertIn("fetch('/settings-editor/api/actions'", self.html)
        self.assertIn("a.greyed", self.html)
        self.assertIn("a.grey_reason", self.html)

    def test_greyed_options_are_dimmed_never_disabled(self):
        fn = re.search(r"function applyActionGrey\(sel\)\{(.*?)\n  \}\n", self.html, re.S).group(1)
        self.assertIn("action-greyed", fn)
        self.assertIn("opt.title = reason", fn)
        self.assertNotIn("disabled", fn)

    def test_the_reason_reaches_the_group_heading_for_touch_screens(self):
        fn = re.search(r"function applyActionGrey\(sel\)\{(.*?)\n  \}\n", self.html, re.S).group(1)
        self.assertIn("og.label", fn)

    def test_every_picker_is_greyed_when_built_and_when_the_answer_arrives(self):
        build = re.search(r"function buildActionMethodSelect\(.*?\n  \}\n", self.html, re.S).group(0)
        self.assertIn("applyActionGrey(sel)", build)
        refresh = re.search(r"function refreshActionGrey\(\)\{(.*?)\n  \}\n", self.html, re.S).group(1)
        self.assertIn("select.action-method", refresh)

    def test_the_js_catalogue_still_carries_the_lens_group_name_the_server_uses(self):
        self.assertIn("group: '" + LENS_ACTION_GROUP + "'", self.html)


if __name__ == "__main__":
    unittest.main()
