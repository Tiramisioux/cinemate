"""The action catalogue exists three times. They have to agree.

settings_editor.py's ACTION_METHODS, a hand-maintained copy of the same list
in the settings editor's JavaScript, and CinePiController's actual methods.
The two hand-maintained copies agreed perfectly for a long time -- including
agreeing on `set_log`, which does not exist, so that button silently did
nothing when pressed. Two copies in exact agreement is not evidence they are
right; it is evidence they were copied.

GET /api/actions already computes exactly this check and ships an `available`
flag per action. The template never fetches it. Until it does, this test is
the thing standing between a rename and another silent button.
"""

import ast
import re
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

CONTROLLER = ROOT / "src/module/cinepi_controller.py"
EDITOR_PY = ROOT / "src/module/app/settings_editor.py"
EDITOR_HTML = ROOT / "src/module/app/templates/settings_editor.html"


def controller_methods() -> set[str]:
    tree = ast.parse(CONTROLLER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CinePiController":
            return {n.name for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    raise AssertionError("CinePiController not found")


def python_catalogue() -> set[str]:
    return set(re.findall(r'"value":\s*"([a-z0-9_]+)"',
                          EDITOR_PY.read_text(encoding="utf-8")))


def js_catalogue() -> set[str]:
    html = EDITOR_HTML.read_text(encoding="utf-8")
    block = re.search(r"var ACTION_METHODS = \[(.*?)\n  \];", html, re.S)
    assert block, "ACTION_METHODS array not found in the template"
    return set(re.findall(r"value:\s*'([a-z0-9_]+)'", block.group(1)))


class ActionCatalogueTests(unittest.TestCase):
    def test_every_offered_action_exists_on_the_controller(self):
        missing = sorted(python_catalogue() - controller_methods())
        self.assertEqual(missing, [],
                         f"offered by the settings editor but absent: {missing}")

    def test_every_javascript_action_exists_on_the_controller(self):
        missing = sorted(js_catalogue() - controller_methods())
        self.assertEqual(missing, [],
                         f"offered by the browser but absent: {missing}")

    def test_the_two_hand_maintained_copies_have_not_drifted(self):
        py, js = python_catalogue(), js_catalogue()
        self.assertEqual(sorted(py - js), [], "in the Python catalogue, missing from the JS")
        self.assertEqual(sorted(js - py), [], "in the JS catalogue, missing from the Python")


if __name__ == "__main__":
    unittest.main()
