"""B9.5: config defaults stated in several places, locked in with a check.

F-256 (already drifted, fixed by this batch): arrays.iso.steps /
arrays.shutter_a.steps were stated 7x across Python, JSONC and the settings
editor's HTML+JS -- and config_loader.py's Python fallback was missing
346.6 from the shutter table. Restoring the value fixes the live bug;
this test is the check that stops it drifting back, across every source
that must agree: config_loader.py's built-in defaults (the fallback used
when settings.jsonc omits the block), settings.jsonc and
settings_default.jsonc (JSONC), and the settings editor's Python
ACTION_METHODS catalogue and its HTML-template JS twin.

F-252: system.web_api.* / system.recovery.* defaults are stated 3x each
(settings.schema.json, web_api_settings.py / cinemate-recovery.py) and
currently agree -- this is the check that was missing, not a fix to a
disagreement.

F-180: pwm_pin's default of 19 is stated twice (schema, config_loader.py)
and was "caught before it drifted" -- same shape, same fix: add the check.

F-251: conform_frame_rate was stated six times and had actually drifted --
schema and config_loader said 24, both shipped JSONC files said 25, and
three call sites restated 24 independently, with nothing comparing them.
The Python side is now one exported constant; the schema and the two
shipped files are data that cannot import, so they are checked here.

F-260: the settings.jsonc absolute path used to be an independent literal
in six files; one had already drifted out of a comment that tried to
enumerate the others by line number. All six now import
config_loader.DEFAULT_SETTINGS_PATH. This test guards against a new literal
creeping back in. services/cinemate-recovery/cinemate-recovery.py keeps its
own copy deliberately (F-221 isolation) and is excluded on purpose.
"""

import json
import re
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.config_loader import (  # noqa: E402
    _apply_settings_defaults,
    strip_jsonc,
    DEFAULT_CONFORM_FRAME_RATE,
    DEFAULT_SETTINGS_PATH,
)


def _load_jsonc(path: Path) -> dict:
    return json.loads(strip_jsonc(path.read_text(encoding="utf-8")))


class ArraysStepsConsistencyTests(unittest.TestCase):
    """F-256."""

    def setUp(self):
        self.config_loader_defaults = _apply_settings_defaults({})
        self.settings_jsonc = _load_jsonc(ROOT / "settings.jsonc")
        self.settings_default_jsonc = _load_jsonc(
            ROOT / "resources/settings/settings_default.jsonc"
        )
        editor_py = (ROOT / "src/module/app/settings_editor.py").read_text(encoding="utf-8")
        editor_html = (ROOT / "src/module/app/templates/settings_editor.html").read_text(
            encoding="utf-8"
        )
        iso_m = re.search(
            r'"value":\s*"set_iso".*?"options":\s*(\[[^\]]*\])', editor_py, re.S
        )
        shutter_m = re.search(
            r'"value":\s*"set_shutter_a".*?"options":\s*(\[[^\]]*\])', editor_py, re.S
        )
        self.editor_py_iso = json.loads(iso_m.group(1))
        self.editor_py_shutter_a = json.loads(shutter_m.group(1))

        html_iso_m = re.search(
            r"data-chip-path=\"arrays\.iso\.steps\"[^>]*data-chip-original=\"(\[[^\"]*\])\"",
            editor_html,
        )
        html_shutter_m = re.search(
            r"data-chip-path=\"arrays\.shutter_a\.steps\"[^>]*data-chip-original=\"(\[[^\"]*\])\"",
            editor_html,
        )
        self.editor_html_iso = json.loads(html_iso_m.group(1))
        self.editor_html_shutter_a = json.loads(html_shutter_m.group(1))

        js_iso_m = re.search(
            r"value:\s*'set_iso'.*?options:\s*(\[[^\]]*\])", editor_html, re.S
        )
        js_shutter_m = re.search(
            r"value:\s*'set_shutter_a'.*?options:\s*(\[[^\]]*\])", editor_html, re.S
        )
        self.editor_js_iso = json.loads(js_iso_m.group(1))
        self.editor_js_shutter_a = json.loads(js_shutter_m.group(1))

    def test_iso_steps_agree_everywhere(self):
        sources = {
            "config_loader.py default": self.config_loader_defaults["arrays"]["iso"]["steps"],
            "settings.jsonc": self.settings_jsonc["arrays"]["iso"]["steps"],
            "settings_default.jsonc": self.settings_default_jsonc["arrays"]["iso"]["steps"],
            "settings_editor.py ACTION_METHODS": self.editor_py_iso,
            "settings_editor.html data-chip-original": self.editor_html_iso,
            "settings_editor.html JS ACTION_METHODS": self.editor_js_iso,
        }
        canonical = sources["settings.jsonc"]
        for name, steps in sources.items():
            self.assertEqual(steps, canonical, f"{name} disagrees with settings.jsonc")

    def test_shutter_a_steps_agree_everywhere(self):
        sources = {
            "config_loader.py default": self.config_loader_defaults["arrays"]["shutter_a"]["steps"],
            "settings.jsonc": self.settings_jsonc["arrays"]["shutter_a"]["steps"],
            "settings_default.jsonc": self.settings_default_jsonc["arrays"]["shutter_a"]["steps"],
            "settings_editor.py ACTION_METHODS": self.editor_py_shutter_a,
            "settings_editor.html data-chip-original": self.editor_html_shutter_a,
            "settings_editor.html JS ACTION_METHODS": self.editor_js_shutter_a,
        }
        canonical = sources["settings.jsonc"]
        for name, steps in sources.items():
            self.assertEqual(steps, canonical, f"{name} disagrees with settings.jsonc")
            # The bug this test exists to catch: 346.6 quietly missing from
            # exactly one copy.
            self.assertIn(346.6, steps, f"{name} is missing 346.6")


class WebApiAndRecoveryDefaultsConsistencyTests(unittest.TestCase):
    """F-252."""

    def setUp(self):
        schema = json.loads((ROOT / "settings.schema.json").read_text(encoding="utf-8"))
        self.schema_web_api = schema["properties"]["system"]["properties"]["web_api"]["properties"]
        self.schema_recovery = schema["properties"]["system"]["properties"]["recovery"]["properties"]

        from module.web_api_settings import DEFAULT_WEB_API_SETTINGS

        self.web_api_settings_py = DEFAULT_WEB_API_SETTINGS

        recovery_src = (
            ROOT / "services/cinemate-recovery/cinemate-recovery.py"
        ).read_text(encoding="utf-8")
        m = re.search(r"^DEFAULTS = \{(.*?)^\}", recovery_src, re.S | re.M)
        # Evaluate the dict literal in isolation -- no import needed, and this
        # is the actual source text, not a re-typed copy of it.
        self.recovery_defaults = eval("{" + m.group(1) + "}")  # noqa: S307

    def test_web_api_scalar_defaults_agree(self):
        for key in ("enabled", "token", "allow_destructive", "max_commands_per_sec", "max_sse_clients"):
            self.assertEqual(
                self.schema_web_api[key]["default"],
                self.web_api_settings_py[key],
                f"system.web_api.{key} disagrees between the schema and web_api_settings.py",
            )

    def test_web_api_broadcast_defaults_agree(self):
        schema_bc = self.schema_web_api["broadcast"]["properties"]
        py_bc = self.web_api_settings_py["broadcast"]
        for key in ("enabled", "port", "hz", "keys"):
            self.assertEqual(
                schema_bc[key]["default"],
                py_bc[key],
                f"system.web_api.broadcast.{key} disagrees between the schema and web_api_settings.py",
            )

    def test_recovery_defaults_agree(self):
        for key in ("enabled", "port", "token", "allow_config_txt", "config_confirm_timeout_s"):
            self.assertEqual(
                self.schema_recovery[key]["default"],
                self.recovery_defaults[key],
                f"system.recovery.{key} disagrees between the schema and cinemate-recovery.py",
            )


class PwmPinDefaultConsistencyTests(unittest.TestCase):
    """F-180."""

    def test_pwm_pin_default_agrees(self):
        schema = json.loads((ROOT / "settings.schema.json").read_text(encoding="utf-8"))
        schema_default = schema["properties"]["hardware_outputs"]["properties"]["pwm_pin"]["default"]

        result = _apply_settings_defaults({})
        loader_default = result["hardware_outputs"]["pwm_pin"]

        self.assertEqual(schema_default, loader_default)


class SettingsPathSingleSourceTests(unittest.TestCase):
    """F-260."""

    SIX_FILES = [
        "src/main.py",
        "src/module/cinepi_multi.py",
        "src/module/cinepi_controller.py",
        "src/module/wifi_hotspot.py",
        "src/module/simple_gui.py",
        "src/module/app/settings_editor.py",
    ]

    def test_default_settings_path_is_the_expected_live_path(self):
        self.assertEqual(DEFAULT_SETTINGS_PATH, "/home/pi/cinemate/settings.jsonc")

    def test_no_file_restates_the_path_as_a_new_literal(self):
        # The recovery console is excluded deliberately (F-221 isolation) --
        # everything else must go through DEFAULT_SETTINGS_PATH.
        offenders = []
        for rel in self.SIX_FILES:
            text = (ROOT / rel).read_text(encoding="utf-8")
            if '"/home/pi/cinemate/settings.jsonc"' in text:
                offenders.append(rel)
        self.assertEqual(offenders, [], f"re-typed the literal instead of importing it: {offenders}")


class ConformFrameRateDefaultTests(unittest.TestCase):
    """F-251 -- the one in this file that had already drifted, not just could."""

    KEY = "conform_frame_rate"

    def _schema_default(self):
        schema = json.loads((ROOT / "settings.schema.json").read_text(encoding="utf-8"))
        return schema["properties"]["settings"]["properties"][self.KEY]["default"]

    def test_schema_default_agrees(self):
        self.assertEqual(self._schema_default(), DEFAULT_CONFORM_FRAME_RATE)

    def test_shipped_jsonc_files_agree(self):
        # settings_default.jsonc is what the settings editor's "revert to
        # defaults" hands the operator. While it disagreed with the code, that
        # button produced a config the code would never have produced.
        for rel in ("settings.jsonc", "resources/settings/settings_default.jsonc"):
            with self.subTest(rel):
                cfg = _load_jsonc(ROOT / rel)
                self.assertEqual(cfg["settings"][self.KEY], DEFAULT_CONFORM_FRAME_RATE)

    def test_loader_applies_it_when_the_key_is_absent(self):
        settings = _apply_settings_defaults({})
        self.assertEqual(settings["settings"][self.KEY], DEFAULT_CONFORM_FRAME_RATE)

    def test_an_explicit_value_is_not_overridden(self):
        settings = _apply_settings_defaults({"settings": {self.KEY: 23.976}})
        self.assertEqual(settings["settings"][self.KEY], 23.976)

    def test_the_templates_javascript_copies_agree(self):
        """The pane's JS holds two copies of the rate and cannot import Python.

        Both are reachable. `pbConform`'s initializer stands until the clip
        index resolves and survives a failed or not-ok fetch, and `pbRate()`
        paces playback off it -- so a stale copy runs takes at the wrong speed
        while the readout names a different one. The sweep below cannot see
        either: it reads .py files, and one of these lines does not even
        contain the key.
        """
        template = (ROOT / "src/module/app/templates/settings_editor.html").read_text(
            encoding="utf-8")
        literals = re.findall(r"pbConform\s*=\s*(?:[a-zA-Z_.]+\s*\|\|\s*)?([0-9]+(?:\.[0-9]+)?)",
                              template)
        self.assertTrue(literals, "expected the playback JS to carry a conform fallback")
        for value in literals:
            self.assertEqual(
                float(value), float(DEFAULT_CONFORM_FRAME_RATE),
                "settings_editor.html restates the conform rate as "
                f"{value}, but the default is {DEFAULT_CONFORM_FRAME_RATE}",
            )

    def test_no_call_site_restates_the_number(self):
        """A bare literal fallback is how this drifted in the first place."""
        offenders = []
        for path in (ROOT / "src").rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if self.KEY not in line:
                    continue
                if re.search(rf'"{self.KEY}"\s*,\s*[0-9]', line) or \
                   re.search(rf'{self.KEY}\s*:\s*(int|float)\s*=\s*[0-9]', line):
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "restated the default instead of importing "
            "DEFAULT_CONFORM_FRAME_RATE:\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
