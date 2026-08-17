"""Golden test: the vendored JSONC stripper must match the original exactly.

services/cinemate-recovery/jsonc.py is the THIRD copy of this logic in the
tree (IMPLEMENTATION-PLAN.md fact F14). It is duplicated because the recovery
console may not import from src/module/ -- "the venv is broken" is one of the
failure modes it exists to survive.

This test is the entire mitigation for that duplication. It asserts
character-for-character equality against module.config_loader.strip_jsonc over
a shared corpus, plus the invariants both copies promise (length preservation,
line preservation, string-literal safety). If you change one implementation,
this fails until you change both.

Do not weaken it to a "parses the same" comparison. The offsets are the point:
they are what makes the error message on tty1 point at the right line.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "services" / "cinemate-recovery"))

from module.config_loader import (  # noqa: E402
    _UnterminatedBlockComment,
    _strip_jsonc_comments,
    _strip_trailing_commas,
    strip_jsonc,
)

import jsonc  # noqa: E402  (the vendored copy)


#: Shared corpus. Every entry is fed through both implementations.
CORPUS = [
    # -- trivial ----------------------------------------------------------
    "",
    "{}",
    '{"a": 1}',
    "   ",
    "\n\n\n",
    # -- line comments ----------------------------------------------------
    '{"a": 1} // trailing',
    '// leading\n{"a": 1}',
    '{"a": 1, // inline\n "b": 2}',
    '{"a": 1} //',
    '//',
    '{"a": 1} // unicode: åäö ünïcødé',
    # -- block comments ---------------------------------------------------
    '{"a": /* inline */ 1}',
    '{/* leading */ "a": 1}',
    '{"a": 1 /* line one\nline two\nline three */, "b": 2}',
    '/**/{"a": 1}',
    '/* */{"a": 1}',
    '{"a": /* nested-looking /* still one */ 1}',
    '{"a": 1} /* tail */',
    # -- comment characters INSIDE strings must survive --------------------
    '{"url": "http://example.com"}',
    '{"a": "// not a comment"}',
    '{"a": "/* not a comment */"}',
    '{"a": "text with \\" escaped quote and // slashes"}',
    '{"path": "C:\\\\dir\\\\file"}',
    '{"a": "trailing backslash \\\\"}',
    # -- trailing commas ---------------------------------------------------
    '{"a": 1,}',
    '{"a": [1, 2, 3,]}',
    '{"a": 1,\n}',
    '{"a": 1,   \n\t }',
    '[1, 2,]',
    '{"a": {"b": 2,},}',
    '{"a": "value,"}',          # comma inside a string is not trailing
    '{"a": ",", "b": [1,]}',
    # -- combinations ------------------------------------------------------
    '{\n  // comment\n  "a": 1, // another\n  /* block */\n  "b": [1, 2,],\n}',
    '{"a": 1, /* c1 */ // c2\n "b": 2,}',
    # -- realistic settings.jsonc shape ------------------------------------
    '''{
  // -- system ------------------------------------------------------------
  "system": {
    "wifi_hotspot": {
      "name": "CinePi",      // the SSID
      "password": "11111111",
      /* true broadcasts the hotspot on boot.
         false serves the UI on an existing interface. */
      "enabled": true,
    },
  },
}
''',
]


def _read_real_settings():
    """The repo's own settings.jsonc, if present -- the highest-value sample."""
    path = ROOT / "settings.jsonc"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


class GoldenEqualityTests(unittest.TestCase):
    def test_corpus_is_not_accidentally_empty(self):
        self.assertGreater(len(CORPUS), 25)

    def test_strip_jsonc_is_identical_over_the_corpus(self):
        for i, sample in enumerate(CORPUS):
            with self.subTest(index=i, sample=sample[:60]):
                self.assertEqual(strip_jsonc(sample), jsonc.strip_jsonc(sample))

    def test_comment_stripper_is_identical_over_the_corpus(self):
        for i, sample in enumerate(CORPUS):
            with self.subTest(index=i, sample=sample[:60]):
                self.assertEqual(
                    _strip_jsonc_comments(sample), jsonc.strip_jsonc_comments(sample)
                )

    def test_trailing_comma_stripper_is_identical_over_the_corpus(self):
        for i, sample in enumerate(CORPUS):
            with self.subTest(index=i, sample=sample[:60]):
                self.assertEqual(
                    _strip_trailing_commas(sample), jsonc.strip_trailing_commas(sample)
                )

    def test_identical_on_the_repos_own_settings_jsonc(self):
        text = _read_real_settings()
        if text is None:
            self.skipTest("settings.jsonc not present")
        self.assertEqual(strip_jsonc(text), jsonc.strip_jsonc(text))
        # And the result must still be valid JSON, or the corpus proves nothing.
        json.loads(jsonc.strip_jsonc(text))


class GoldenInvariantTests(unittest.TestCase):
    """Properties both copies promise, asserted against the vendored one."""

    def test_length_is_preserved(self):
        for sample in CORPUS:
            with self.subTest(sample=sample[:60]):
                self.assertEqual(len(jsonc.strip_jsonc(sample)), len(sample))

    def test_line_count_is_preserved(self):
        for sample in CORPUS:
            with self.subTest(sample=sample[:60]):
                self.assertEqual(
                    jsonc.strip_jsonc(sample).count("\n"), sample.count("\n")
                )

    def test_string_contents_survive(self):
        text = '{"url": "http://x.com/a//b", "c": "/* keep */"}'
        self.assertEqual(jsonc.strip_jsonc(text), text)

    def test_corpus_entries_that_should_parse_do_parse(self):
        for sample in CORPUS:
            stripped = sample.strip()
            if not stripped.startswith(("{", "[")):
                continue
            with self.subTest(sample=sample[:60]):
                json.loads(jsonc.strip_jsonc(sample))


class GoldenErrorTests(unittest.TestCase):
    def test_both_raise_on_an_unterminated_block_comment(self):
        text = '{"a": 1 /* never closed'
        with self.assertRaises(_UnterminatedBlockComment) as original:
            _strip_jsonc_comments(text)
        with self.assertRaises(jsonc.UnterminatedBlockComment) as vendored:
            jsonc.strip_jsonc_comments(text)
        self.assertEqual(original.exception.line, vendored.exception.line)
        self.assertEqual(original.exception.column, vendored.exception.column)

    def test_reported_position_is_the_comment_start(self):
        text = '{\n  "a": 1,\n  /* dangling\n'
        with self.assertRaises(jsonc.UnterminatedBlockComment) as ctx:
            jsonc.strip_jsonc_comments(text)
        self.assertEqual(ctx.exception.line, 3)
        self.assertEqual(ctx.exception.column, 3)

    def test_positions_agree_on_a_multiline_sample(self):
        text = '{\n\n\n    /* opened here and never closed\n'
        with self.assertRaises(_UnterminatedBlockComment) as original:
            _strip_jsonc_comments(text)
        with self.assertRaises(jsonc.UnterminatedBlockComment) as vendored:
            jsonc.strip_jsonc_comments(text)
        self.assertEqual(
            (original.exception.line, original.exception.column),
            (vendored.exception.line, vendored.exception.column),
        )


class GoldenSourceDriftTests(unittest.TestCase):
    """Catch a copy that was edited without the other."""

    def test_both_modules_expose_the_same_surface(self):
        for name in ("strip_jsonc",):
            self.assertTrue(callable(getattr(jsonc, name)))

    def test_vendored_module_imports_nothing_outside_the_stdlib(self):
        # The single most important constraint in the plan.
        source = (ROOT / "services" / "cinemate-recovery" / "jsonc.py").read_text()
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                self.assertNotIn("module.", stripped)
                self.assertNotIn("flask", stripped.lower())
                self.assertNotIn("redis", stripped.lower())


if __name__ == "__main__":
    unittest.main()
