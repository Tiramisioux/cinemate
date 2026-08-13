import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.config_loader import (
    SettingsLoadError,
    _strip_jsonc_comments,
    _strip_trailing_commas,
    load_settings,
    strip_jsonc,
)


class StripCommentsTests(unittest.TestCase):
    def test_line_comment_is_blanked(self):
        text = '{"a": 1, // trailing\n"b": 2}'
        stripped = _strip_jsonc_comments(text)
        self.assertEqual(len(stripped), len(text))  # positions stay aligned
        self.assertNotIn("//", stripped)
        self.assertTrue(stripped.startswith('{"a": 1,'))
        self.assertTrue(stripped.endswith('\n"b": 2}'))

    def test_block_comment_is_blanked(self):
        text = '{"a": /* inline */ 1}'
        stripped = _strip_jsonc_comments(text)
        self.assertEqual(len(stripped), len(text))
        self.assertNotIn("/*", stripped)
        self.assertNotIn("*/", stripped)
        self.assertTrue(stripped.startswith('{"a":'))
        self.assertTrue(stripped.endswith("1}"))

    def test_multiline_block_comment_preserves_newlines(self):
        text = '{"a": 1, /* line one\nline two */ "b": 2}'
        stripped = _strip_jsonc_comments(text)
        # Same number of lines as the original -- downstream line numbers
        # for anything after the comment must not shift.
        self.assertEqual(stripped.count("\n"), text.count("\n"))

    def test_comment_markers_inside_strings_are_left_alone(self):
        for text in (
            '{"url": "http://example.com"}',
            '{"note": "/* not a comment */"}',
            '{"note": "still // not a comment"}',
        ):
            self.assertEqual(_strip_jsonc_comments(text), text)

    def test_escaped_quote_does_not_end_the_string_early(self):
        text = '{"a": "he said \\"hi // not a comment\\""}'
        self.assertEqual(_strip_jsonc_comments(text), text)

    def test_unterminated_block_comment_reports_its_start_position(self):
        text = '{"a": 1,\n  /* never closed'
        with self.assertRaises(Exception) as ctx:
            _strip_jsonc_comments(text)
        exc = ctx.exception
        self.assertEqual(exc.line, 2)
        self.assertEqual(exc.column, 3)


class StripTrailingCommasTests(unittest.TestCase):
    def test_trailing_comma_before_closing_brace_is_blanked(self):
        self.assertEqual(
            _strip_trailing_commas('{"a": 1,}'),
            '{"a": 1 }',
        )

    def test_trailing_comma_before_closing_bracket_is_blanked(self):
        self.assertEqual(
            _strip_trailing_commas("[1, 2,]"),
            "[1, 2 ]",
        )

    def test_trailing_comma_after_whitespace_and_newlines_is_blanked(self):
        text = '{\n  "a": 1,\n}'
        stripped = _strip_trailing_commas(text)
        self.assertNotIn(",", stripped)

    def test_comma_immediately_after_a_closing_quote_is_still_caught(self):
        # The common real-world shape: "key": "value",\n} -- the character
        # right before the comma is the string's closing quote.
        self.assertEqual(
            _strip_trailing_commas('{"a": "x",}'),
            '{"a": "x" }',
        )

    def test_non_trailing_comma_is_untouched(self):
        self.assertEqual(_strip_trailing_commas('{"a": 1, "b": 2}'), '{"a": 1, "b": 2}')

    def test_comma_inside_a_string_followed_by_brace_like_text_is_untouched(self):
        text = '{"note": "looks like this, }", "b": 2}'
        self.assertEqual(_strip_trailing_commas(text), text)


class StripJsoncEndToEndTests(unittest.TestCase):
    def test_comments_and_trailing_commas_together_still_parse(self):
        import json

        text = (
            "{\n"
            '  // top-level comment\n'
            '  "a": 1, /* inline */\n'
            '  "b": [1, 2, 3,],\n'
            '  "c": {"nested": true,},\n'
            "}\n"
        )
        self.assertEqual(
            json.loads(strip_jsonc(text)),
            {"a": 1, "b": [1, 2, 3], "c": {"nested": True}},
        )

    def test_length_is_preserved_so_json_error_positions_still_line_up(self):
        # A real syntax error AFTER a comment must still be reported at its
        # true position in the original file, not shifted by the strip.
        text = '{\n  // a comment\n  "a": 1 "b": 2\n}'
        import json

        with self.assertRaises(json.JSONDecodeError) as ctx:
            json.loads(strip_jsonc(text))
        # "a": 1 "b" -- json should complain right at the second key,
        # i.e. line 3, not somewhere inside/after the stripped comment.
        self.assertEqual(ctx.exception.lineno, 3)


class LoadSettingsJsoncTests(unittest.TestCase):
    def _load(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(text, encoding="utf-8")
            return load_settings(path)

    def test_a_hand_commented_file_loads_like_its_comment_free_equivalent(self):
        commented = (
            "{\n"
            '  // hotspot config\n'
            '  "system": {\n'
            '    "wifi_hotspot": {"name": "MyRig", "password": "changeme1", "enabled": true},\n'
            "  },\n"
            "}\n"
        )
        plain = '{"system": {"wifi_hotspot": {"name": "MyRig", "password": "changeme1", "enabled": true}}}'

        self.assertEqual(self._load(commented), self._load(plain))

    def test_unterminated_block_comment_raises_settings_load_error(self):
        text = '{\n  "a": 1,\n  /* never closed\n  "b": 2\n}'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(SettingsLoadError) as ctx:
                load_settings(path)
        self.assertIn("unterminated", ctx.exception.summary.lower())
        self.assertEqual(ctx.exception.line, 3)

    def test_a_genuine_syntax_error_past_a_comment_still_reports_correctly(self):
        text = '{\n  // fine\n  "a": 1 "b": 2\n}'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(SettingsLoadError) as ctx:
                load_settings(path)
        self.assertEqual(ctx.exception.line, 3)

    def test_real_shipped_settings_json_still_loads(self):
        # Regression guard: today's settings.json has no comments at all,
        # so strip_jsonc must be a no-op on it end to end.
        settings = load_settings(ROOT / "settings.json")
        self.assertIn("camera", settings)
        self.assertIn("system", settings)


if __name__ == "__main__":
    unittest.main()
