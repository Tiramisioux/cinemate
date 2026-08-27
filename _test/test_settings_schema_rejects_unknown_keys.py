"""The schema has to be able to say no.

settings.schema.json carried "additionalProperties": true at 25 sites and
false at none, including at the document root, so a misspelled key validated
clean and was then silently ignored at read time. Nothing in the running
system validates against this schema -- it is editor tooling -- which is
exactly why it has to be strict: the editor is the only place a typo can be
caught before it costs someone a shoot.

Tightening it also required completing it: cam_config described three
properties where the shipped settings use seven.
"""

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.config_loader import strip_jsonc

try:
    import jsonschema
except ImportError:  # pragma: no cover - jsonschema is a dev convenience, not a runtime dep
    jsonschema = None


def load(path):
    return json.loads(strip_jsonc(Path(path).read_text(encoding="utf-8")))


@unittest.skipIf(jsonschema is None, "jsonschema not installed")
class SchemaStrictnessTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads((ROOT / "settings.schema.json").read_text(encoding="utf-8"))
        self.validator = jsonschema.Draft7Validator(self.schema)

    def test_every_shipped_settings_file_validates(self):
        for name in ("settings.jsonc",
                     "resources/settings/settings_default.jsonc",
                     "resources/settings/settings_komodo.jsonc"):
            with self.subTest(name):
                errors = list(self.validator.iter_errors(load(ROOT / name)))
                self.assertEqual(
                    errors, [],
                    "\n".join(f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
                              for e in errors))

    def test_a_misspelled_top_level_section_is_rejected(self):
        doc = load(ROOT / "settings.jsonc")
        doc["systemm"] = doc.pop("system")
        self.assertTrue(list(self.validator.iter_errors(doc)))

    def test_a_misspelled_nested_key_is_rejected(self):
        doc = load(ROOT / "settings.jsonc")
        doc["system"]["wifi_hotspott"] = {"name": "oops"}
        self.assertTrue(list(self.validator.iter_errors(doc)))

    def test_a_misspelled_per_sensor_key_is_rejected(self):
        doc = load(ROOT / "settings.jsonc")
        doc["sensors"]["cam0"]["camera_nmae"] = "typo"
        self.assertTrue(list(self.validator.iter_errors(doc)))

    def test_no_object_is_left_open(self):
        # A single additionalProperties:true anywhere reopens the hole for
        # everything under it.
        raw = (ROOT / "settings.schema.json").read_text(encoding="utf-8")
        self.assertNotIn('"additionalProperties": true', raw)


if __name__ == "__main__":
    unittest.main()
