"""The settings editor wrote `log_encode` out as a string, and a string on
that key fails silently in the direction that loses footage.

`log_encode` is the one settings key whose options are not all one type --
False | True | 10 | 12 -- so its editor control is a <select>, not a toggle.
That select carried `data-type="string"`, and readControlValue() returns
el.value verbatim for anything that is not 'bool'/'number'. So picking
"On (mode default)" wrote the *string* "true" into settings.jsonc, and
picking "Off" wrote the string "false".

Both are wrong, and neither announces itself:

  - cinepi_multi gates the launch on `if log_requested:`, and a non-empty
    string is truthy -- so "false" reads as log-ON.
  - the truthy branch then passes anything that is not literally `True` as an
    explicit target (`requested=None if log_requested is True else ...`).
    "true" is a str, not True, so it is forwarded as a target, matches no
    valid bit depth, and records LINEAR with only a warning.

So "Off" meant on-but-broken and "On" meant off-with-a-warning. Observed on
a real camera: a settings-editor save left `"log_encode": "true"` in
settings.jsonc (2026-08-28).

Fix is in two halves, both checked here:

1. The select is `data-type="json"` and readControlValue() parses the option's
   JSON literal, so each option writes its native type.
2. config_loader.normalize_log_encode() coerces on load, so a file already
   carrying the corrupted string heals itself on the next start rather than
   needing a hand edit.
"""

import json
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.modules.setdefault("gpiozero", types.SimpleNamespace(CPUTemperature=object))

from module.config_loader import load_settings, normalize_log_encode  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/module/app/templates/settings_editor.html"


class NormalizeLogEncodeTests(unittest.TestCase):
    """The decode table. Native types pass through; strings are decoded."""

    def test_native_values_pass_through_unchanged(self):
        for value in (False, True, 10, 12):
            with self.subTest(value=value):
                result = normalize_log_encode(value)
                self.assertEqual(result, value)
                self.assertIs(type(result), type(value))

    def test_boolean_strings_decode_to_booleans(self):
        # The exact corruption the editor used to write.
        for text, expected in (
            ("true", True), ("false", False),
            ("True", True), ("False", False),
            ("on", True), ("off", False),
            ("1", True), ("0", False),
        ):
            with self.subTest(text=text):
                result = normalize_log_encode(text)
                self.assertIs(result, expected)

    def test_numeric_strings_decode_to_int_targets(self):
        for text, expected in (("10", 10), ("12", 12)):
            with self.subTest(text=text):
                result = normalize_log_encode(text)
                self.assertEqual(result, expected)
                self.assertIsInstance(result, int)
                self.assertNotIsInstance(result, bool)

    def test_unrecognised_falls_back_to_default_like_an_absent_key(self):
        # Same rule as as_bool: "the user wrote maybe" is not "the user
        # wrote off", so it takes `default` rather than hard-coding False.
        for value in ("garbage", "", "   ", None, 2.5):
            with self.subTest(value=value):
                self.assertIs(normalize_log_encode(value), False)
                self.assertIs(normalize_log_encode(value, default=True), True)

    def test_off_no_longer_reads_as_truthy(self):
        """The specific silent failure: bare `if log_requested:` on "false"."""
        self.assertTrue(bool("false"))                       # the old bug
        self.assertFalse(bool(normalize_log_encode("false")))  # after decode


class LoadSettingsHealsCorruptedFileTests(unittest.TestCase):
    """A settings.jsonc already carrying the string heals on load."""

    def _load_with_log_encode(self, raw_value):
        settings = {"sensors": {"cam0": {"log_encode": raw_value}}}
        with tempfile.NamedTemporaryFile(
            "w", suffix=".jsonc", delete=False, encoding="utf-8"
        ) as handle:
            json.dump(settings, handle)
            path = handle.name
        return load_settings(path)["sensors"]["cam0"]["log_encode"]

    def test_string_true_becomes_boolean_true(self):
        result = self._load_with_log_encode("true")
        self.assertIs(result, True)

    def test_string_false_becomes_boolean_false(self):
        result = self._load_with_log_encode("false")
        self.assertIs(result, False)

    def test_string_target_becomes_int(self):
        self.assertEqual(self._load_with_log_encode("12"), 12)

    def test_boolean_true_still_means_mode_default_target(self):
        """`True` must stay `True`, not become an int.

        cinepi_multi distinguishes them by identity --
        `requested=None if log_requested is True else log_requested` -- so
        True means "this mode's own default target" while an int forces one.
        Coercing True to 1 here would silently force a 1-bit target.
        """
        self.assertIs(self._load_with_log_encode(True), True)


class EditorWritesNativeTypesTests(unittest.TestCase):
    """Guard the template against regressing to data-type="string"."""

    def setUp(self):
        self.html = TEMPLATE.read_text(encoding="utf-8")

    def test_log_encode_selects_are_json_typed(self):
        selects = re.findall(
            r'<select[^>]*data-path="sensors\.cam\d\.log_encode"[^>]*>', self.html
        )
        self.assertEqual(len(selects), 2, "expected a cam0 and a cam1 log select")
        for tag in selects:
            with self.subTest(tag=tag):
                self.assertIn('data-type="json"', tag)
                self.assertNotIn('data-type="string"', tag)

    def test_every_log_encode_option_is_a_json_literal(self):
        """Each option's value must parse, or 'json' silently returns the str."""
        block = re.search(
            r'<select[^>]*data-path="sensors\.cam0\.log_encode".*?</select>',
            self.html, re.S,
        )
        self.assertIsNotNone(block, "cam0 log_encode select not found")
        values = re.findall(r'<option value="([^"]*)"', block.group(0))
        self.assertEqual(sorted(values), ["10", "12", "false", "true"])
        for value in values:
            with self.subTest(value=value):
                json.loads(value)  # raises if not a bare JSON literal

    def test_read_control_value_handles_the_json_type(self):
        self.assertIn("if (type === 'json')", self.html)
        self.assertIn("JSON.parse(el.value)", self.html)


if __name__ == "__main__":
    unittest.main()
