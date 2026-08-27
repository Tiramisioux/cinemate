"""One conform frame rate, stated in places that cannot import each other.

`settings.conform_frame_rate` had drifted: the JSON schema and `config_loader`
said 24, both shipped `.jsonc` files said 25, and three more call sites restated
24 independently -- six statements of one fact, split 2-4, with nothing
comparing them (system review F-251, "no arbiter"). Nothing failed, because
nothing checked; the value simply meant something different depending on which
path you arrived by.

The Python side is now one exported constant. What this test exists for is the
part that cannot be deduplicated: `settings.schema.json` and the two shipped
`settings*.jsonc` files are data, read by tools that never import Python, so
their copies can only be *checked*, not removed.

This is the project's own rule applied to its own finding -- if two things must
agree, write a check rather than a comment.
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
    DEFAULT_CONFORM_FRAME_RATE,
    _apply_settings_defaults,
)

KEY = "conform_frame_rate"


def _jsonc_value(path):
    """Read the key out of a .jsonc without a full parse.

    Deliberately a regex and not `strip_jsonc` + `json.loads`: this test is the
    thing standing behind those files, so it should not depend on the loader it
    is checking.
    """
    text = Path(path).read_text(encoding="utf-8")
    match = re.search(rf'"{KEY}"\s*:\s*([0-9.]+)', text)
    assert match, f"{path} does not name {KEY}"
    return float(match.group(1))


class ConformFrameRateDefaultTest(unittest.TestCase):
    def test_schema_default_matches_the_python_constant(self):
        schema = json.loads((ROOT / "settings.schema.json").read_text(encoding="utf-8"))
        declared = schema["properties"]["settings"]["properties"][KEY]["default"]
        self.assertEqual(
            declared, DEFAULT_CONFORM_FRAME_RATE,
            "settings.schema.json's default disagrees with "
            "config_loader.DEFAULT_CONFORM_FRAME_RATE",
        )

    def test_shipped_configs_match_the_default(self):
        """The shipped files may legitimately differ -- but silently, they did.

        `settings_default.jsonc` is what the editor's "revert to defaults"
        button hands the operator, so if it disagrees with the code's default
        then reverting produces a config the code would never have produced.
        """
        for rel in ("settings.jsonc", "resources/settings/settings_default.jsonc"):
            with self.subTest(rel):
                self.assertEqual(
                    _jsonc_value(ROOT / rel), float(DEFAULT_CONFORM_FRAME_RATE),
                    f"{rel} disagrees with config_loader.DEFAULT_CONFORM_FRAME_RATE",
                )

    def test_loader_applies_the_constant_when_the_key_is_absent(self):
        settings = _apply_settings_defaults({})
        self.assertEqual(settings["settings"][KEY], DEFAULT_CONFORM_FRAME_RATE)

    def test_an_explicit_value_is_never_overridden_by_the_default(self):
        settings = _apply_settings_defaults({"settings": {KEY: 23.976}})
        self.assertEqual(settings["settings"][KEY], 23.976)

    def test_no_call_site_restates_the_number(self):
        """A bare fallback is how this drifted in the first place.

        Anything reading the key with its own literal fallback is a seventh
        copy waiting to disagree; they should take the constant instead.
        """
        offenders = []
        for path in (ROOT / "src").rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if KEY not in line:
                    continue
                # A literal after the key, e.g. .get("conform_frame_rate", 24)
                if re.search(rf'"{KEY}"\s*,\s*[0-9]', line) or \
                   re.search(rf'{KEY}\s*:\s*(int|float)\s*=\s*[0-9]', line):
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "these restate the default instead of importing "
            "DEFAULT_CONFORM_FRAME_RATE:\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
