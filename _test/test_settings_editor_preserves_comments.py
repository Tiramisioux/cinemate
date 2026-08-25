"""Saving settings must not delete the operator's comments.

settings.jsonc is 74 comment lines out of 386 -- section banners and per-key
explanations. put_settings() rewrote the file from json.dumps(parsed), which
cannot carry comments because the parsed tree does not contain them, so every
save deleted all of them silently.

The surgical path rewrites only the spans whose values changed. Where it cannot
-- a key added, an array resized -- the caller falls back to a full rewrite and
has to SAY SO, which is what the last test here checks.
"""

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.config_loader import strip_jsonc
from module.jsonc_edit import apply_updates, mask_comments

SAMPLE = """{
  // ── system ────────────────────────────────────────────
  "system": {
    "welcome": {
      "show": true,
      "message": "THIS IS A COOL MACHINE",
      "image": null // path to a bitmap logo; overrides "message" when set
    }
  },
  /* block comment, kept verbatim */
  "arrays": {
    "iso": { "steps": [100, 200, 400], "free": false }
  }
}
"""


def parse(text):
    return json.loads(strip_jsonc(text))


class PreserveCommentsTests(unittest.TestCase):
    def test_a_scalar_change_keeps_every_comment(self):
        current = parse(SAMPLE)
        desired = parse(SAMPLE)
        desired["system"]["welcome"]["show"] = False

        out = apply_updates(SAMPLE, current, desired)

        self.assertIsNotNone(out)
        self.assertEqual(parse(out)["system"]["welcome"]["show"], False)
        for fragment in ("// ── system", "// path to a bitmap logo",
                         "/* block comment, kept verbatim */"):
            self.assertIn(fragment, out)

    def test_only_the_changed_value_is_touched(self):
        current = parse(SAMPLE)
        desired = parse(SAMPLE)
        desired["arrays"]["iso"]["steps"][1] = 250

        out = apply_updates(SAMPLE, current, desired)

        changed = [
            (a, b) for a, b in zip(SAMPLE.split("\n"), out.split("\n")) if a != b
        ]
        self.assertEqual(len(changed), 1, f"expected one changed line, got {changed}")
        self.assertIn("250", changed[0][1])

    def test_an_unchanged_save_is_byte_identical(self):
        current = parse(SAMPLE)
        self.assertEqual(apply_updates(SAMPLE, current, current), SAMPLE)

    def test_a_string_with_a_slash_is_not_mistaken_for_a_comment(self):
        text = '{\n  "path": "http://cinepi.local:5000/", // trailing\n  "n": 1\n}\n'
        masked = mask_comments(text)

        # The URL survives; only the real comment is blanked.
        self.assertIn('"http://cinepi.local:5000/"', masked)
        self.assertNotIn("trailing", masked)
        self.assertEqual(len(masked), len(text), "offsets must be preserved")

    def test_structural_changes_return_none_rather_than_guessing(self):
        current = parse(SAMPLE)

        added = parse(SAMPLE)
        added["brand_new"] = 1
        self.assertIsNone(apply_updates(SAMPLE, current, added))

        removed = parse(SAMPLE)
        del removed["arrays"]
        self.assertIsNone(apply_updates(SAMPLE, current, removed))

        resized = parse(SAMPLE)
        resized["arrays"]["iso"]["steps"].append(800)
        self.assertIsNone(apply_updates(SAMPLE, current, resized))

    def test_it_works_on_the_real_settings_file(self):
        text = (ROOT / "settings.jsonc").read_text(encoding="utf-8")
        current = parse(text)
        desired = parse(text)
        desired["system"]["welcome"]["show"] = not current["system"]["welcome"]["show"]

        out = apply_updates(text, current, desired)

        self.assertIsNotNone(out)
        self.assertEqual(text.count("//"), out.count("//"))
        self.assertEqual(parse(out)["system"]["welcome"]["show"],
                         desired["system"]["welcome"]["show"])


if __name__ == "__main__":
    unittest.main()
