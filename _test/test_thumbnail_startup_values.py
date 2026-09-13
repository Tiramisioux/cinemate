"""thumbnail_startup_value() and thumbnail_size_startup_value()
(config_loader.py) are the validated startup values main.py seeds
ParameterKey.THUMBNAIL / THUMBNAIL_SIZE with at every boot, and the
fallback _recompute_file_size() (cinepi_controller.py) uses when the live
Redis keys are absent. No prior test exercised either function directly --
this is that coverage, mirroring test_config_loader_as_bool.py's
decision-table style.

Both degrade the same way: int() the configured raw value, clamp it, and
fall back to the shipped default on TypeError/ValueError (a bool, None, a
list/dict, or a non-numeric string) rather than raising or reaching Redis
unvalidated -- see each function's own docstring for why (B-1 / C9).
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.config_loader import thumbnail_startup_value, thumbnail_size_startup_value


_ABSENT = object()   # sentinel: no image_capture.thumbnail[_size] key at all


def _settings(key, raw):
    if raw is _ABSENT:
        return {"image_capture": {}}
    return {"image_capture": {key: raw}}


class ThumbnailStartupValueTests(unittest.TestCase):
    # (raw settings.jsonc value, expected validated value)
    CASES = [
        (_ABSENT, 1),          # no key at all -> shipped default (mono, 2026-09-13)
        (0, 0),
        (1, 1),
        (2, 2),
        (-5, 0),               # clamped to the floor
        (99, 2),               # clamped to the ceiling
        (True, 1),             # int(True) == 1, a valid mode -- does not crash
        (False, 0),            # int(False) == 0
        ("2", 2),              # numeric string
        ("0", 0),
        ("banana", 1),         # ValueError -> default
        (None, 1),             # TypeError -> default
        ([], 1),               # TypeError -> default
        ({}, 1),               # TypeError -> default
    ]

    def test_decision_table(self):
        for raw, expected in self.CASES:
            with self.subTest(raw=raw):
                self.assertEqual(
                    thumbnail_startup_value(_settings("thumbnail", raw)), expected
                )

    def test_empty_settings_dict_is_the_default(self):
        self.assertEqual(thumbnail_startup_value({}), 1)

    def test_missing_image_capture_section_is_the_default(self):
        self.assertEqual(thumbnail_startup_value({"some_other_key": {}}), 1)


class ThumbnailSizeStartupValueTests(unittest.TestCase):
    # (raw settings.jsonc value, expected validated value)
    CASES = [
        (_ABSENT, 1),          # no key at all -> shipped default (shift 1, 640x360)
        (0, 0),
        (1, 1),
        (4, 4),
        (-1, 0),               # clamped to the floor
        (12, 4),               # cinepi-raw would accept 12; this setting stops at 4
        (5, 4),                # one past the ceiling
        (True, 1),             # int(True) == 1, a valid shift -- does not crash
        ("2", 2),              # numeric string
        ("nonsense", 1),       # ValueError -> default
        (None, 1),             # TypeError -> default
        ([], 1),               # TypeError -> default
    ]

    def test_decision_table(self):
        for raw, expected in self.CASES:
            with self.subTest(raw=raw):
                self.assertEqual(
                    thumbnail_size_startup_value(_settings("thumbnail_size", raw)), expected
                )

    def test_empty_settings_dict_is_the_default(self):
        self.assertEqual(thumbnail_size_startup_value({}), 1)

    def test_missing_image_capture_section_is_the_default(self):
        self.assertEqual(thumbnail_size_startup_value({"some_other_key": {}}), 1)


if __name__ == "__main__":
    unittest.main()
