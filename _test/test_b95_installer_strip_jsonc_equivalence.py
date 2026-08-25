"""F-191: cinemate-install.sh's settings-patcher heredoc reimplements
module.config_loader.strip_jsonc() by hand, with a comment explaining why:
the heredoc runs under the system python3 during install, outside the
cinemate package/venv, so it cannot import module.config_loader. That is a
legitimate reason -- unlike the codebase's other hand-sync comments, this
one names it -- but the finding is right that it still had no check.

The two implementations are NOT byte-identical by design: config_loader's
version blanks comments/trailing-commas to spaces to stay length- and
line-preserving (for accurate error reporting), while the installer's
heredoc simply deletes them (it only needs to produce parseable JSON once,
during an install step, not point at a source line in a later error). The
actual contract that matters is: given the same well-formed settings.jsonc
text, both must parse to the *same dict*. That's what this test checks --
by extracting the live function straight out of cinemate-install.sh, never
a copy of it, so this test can't silently stop testing the real thing.
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

from module.config_loader import strip_jsonc  # noqa: E402


def _extract_heredoc_strip_jsonc():
    text = (ROOT / "cinemate-install.sh").read_text(encoding="utf-8")
    m = re.search(
        r"^def _strip_jsonc\(text\):.*?\n    return \"\"\.join\(out\)\n",
        text,
        re.S | re.M,
    )
    assert m, "_strip_jsonc() not found in cinemate-install.sh -- did it move or get renamed?"
    namespace = {}
    exec(m.group(0), namespace)  # noqa: S102 -- test-only, extracting known-local source
    return namespace["_strip_jsonc"]


SAMPLES = [
    '{"a": 1, "b": 2}',
    '{\n  // a leading comment\n  "a": 1,\n}',
    '{\n  "a": 1, /* trailing block comment */\n  "b": [1, 2, 3,],\n}',
    '{"note": "a string with // not a comment and a , trailing comma-look-alike"}',
    '{"note": "an escaped \\" quote then // still not a comment"}',
    '{\n  /* multi\n     line\n     block */\n  "shutter_a": {"steps": [1, 45, 346.6,],},\n}',
    '{"nested": {"deep": {"steps": [1, 2, 3,],},}, "trailing": true,}',
]


class InstallerStripJsoncEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.heredoc_strip_jsonc = _extract_heredoc_strip_jsonc()

    def test_both_implementations_parse_representative_input_identically(self):
        for sample in SAMPLES:
            with self.subTest(sample=sample):
                canonical = json.loads(strip_jsonc(sample))
                heredoc = json.loads(self.heredoc_strip_jsonc(sample))
                self.assertEqual(
                    canonical, heredoc,
                    "config_loader.strip_jsonc() and the installer's hand-synced "
                    "copy parsed this input to different results",
                )

    def test_both_implementations_agree_on_the_real_settings_default_jsonc(self):
        real_text = (ROOT / "resources/settings/settings_default.jsonc").read_text(
            encoding="utf-8"
        )
        canonical = json.loads(strip_jsonc(real_text))
        heredoc = json.loads(self.heredoc_strip_jsonc(real_text))
        self.assertEqual(canonical, heredoc)


if __name__ == "__main__":
    unittest.main()
