"""Every "method" string in a shipped settings file must exist on the controller.

Button, encoder and combined actions are dispatched reflectively --
`getattr(controller, name)` -- so a name that no longer resolves produces no
error, no log line, nothing: just a control that silently does nothing when
pressed. That has shipped at least once (`set_log`).

`tools/gui_field_extract.py` gates the settings editor's action catalogue, and
`tools/docs_drift_check.py` gates docs/. Neither reads settings.jsonc's method
strings -- the handbook's orientation/entry-points.md names this row
"**nothing**". This is that check.

Static, via ast: importing CinePiController drags in redis, smbus and the rest
of the hardware stack, and the question here is only "is this name defined on
the class".
"""

import ast
import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CONTROLLER = ROOT / "src/module/cinepi_controller.py"

SHIPPED_SETTINGS = (
    "settings.jsonc",
    "resources/settings/settings_default.jsonc",
    "resources/settings/settings_komodo.jsonc",
)


def strip_jsonc(text: str) -> str:
    """Drop // comments outside strings. Same shape as the loader's own."""
    out, in_str, esc = [], False, False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    # trailing commas are not valid JSON
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def controller_method_names() -> set[str]:
    tree = ast.parse(CONTROLLER.read_text(encoding="utf-8"))
    cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "CinePiController"
    )
    return {
        n.name for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def method_strings(node, path="$"):
    """Every ("method" value, where it lives) pair, at any depth."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "method" and isinstance(value, str):
                yield value, path
            else:
                yield from method_strings(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from method_strings(value, f"{path}[{index}]")


class SettingsMethodNamesResolveTests(unittest.TestCase):
    def setUp(self):
        self.methods = controller_method_names()
        # A guard on the guard: if the ast walk ever stops finding the class,
        # every name would "fail" for the wrong reason -- or, with the
        # assertion inverted by a later edit, none would.
        self.assertIn("rec", self.methods)

    def test_every_shipped_settings_file_dispatches_to_a_real_method(self):
        checked = 0
        for name in SHIPPED_SETTINGS:
            path = ROOT / name
            self.assertTrue(path.exists(), f"{name} is missing")
            doc = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
            for method, where in method_strings(doc):
                checked += 1
                with self.subTest(file=name, method=method, at=where):
                    self.assertIn(
                        method, self.methods,
                        f"{name}: {where} dispatches to CinePiController."
                        f"{method}, which does not exist -- that control does "
                        f"nothing at all, silently.",
                    )
        # Nothing to check would pass vacuously, and this file's whole job is
        # to notice when a name goes missing.
        self.assertGreater(checked, 0, "no method strings found to check")

    def test_pot_settings_name_a_real_control(self):
        for name in SHIPPED_SETTINGS:
            doc = json.loads(strip_jsonc((ROOT / name).read_text(encoding="utf-8")))
            pots = (doc.get("input_peripherals") or {}).get("pots") or []
            for pot in pots:
                setting = pot.get("setting")
                if not setting:
                    continue
                with self.subTest(file=name, setting=setting):
                    self.assertTrue(
                        any(f"set_{setting}{suffix}" in self.methods
                            for suffix in ("", "_nom")),
                        f"{name}: pot setting {setting!r} has no set_{setting}"
                        f"() on CinePiController.",
                    )


if __name__ == "__main__":
    unittest.main()
