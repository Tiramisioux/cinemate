"""thumbnail_startup_value() and thumbnail_size_startup_value()
(config_loader.py) are the validated startup values main.py seeds
ParameterKey.THUMBNAIL / THUMBNAIL_SIZE with at every boot, and the
fallback _recompute_file_size() (cinepi_controller.py) uses when the live
Redis keys are absent. No prior test exercised either function directly --
this is that coverage, mirroring test_config_loader_as_bool.py's
decision-table style.

thumbnail_size_startup_value() still degrades the Phase 1 way: int() the
configured raw value, clamp it, and fall back to the shipped default on
TypeError/ValueError (None, a list/dict, or a non-numeric string) --
bool included, since int(True)/int(False) are valid shifts (1/0) and
never reach cinepi-raw as anything else. thumbnail_startup_value() now
goes through parse_thumbnail_mode() (Phase 2): it additionally accepts the
four words ("off"/"mono"/"colour"/"color"/"jpeg", case-insensitive,
stripped) and a fourth numeric value (3, JPEG), and -- the one place the
two functions now differ -- rejects a bool outright instead of coercing
it, since int(True) == 1 being "a valid mode" was itself part of how B-1
went unnoticed. See each function's own docstring for the full reasoning.
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.config_loader import (
    parse_thumbnail_mode,
    thumbnail_startup_value,
    thumbnail_size_startup_value,
    THUMBNAIL_MODE_NAMES,
)


_ABSENT = object()   # sentinel: no image_capture.thumbnail[_size] key at all


def _settings(key, raw):
    if raw is _ABSENT:
        return {"image_capture": {}}
    return {"image_capture": {key: raw}}


class ParseThumbnailModeTests(unittest.TestCase):
    # (raw value, expected parse_thumbnail_mode() result)
    CASES = [
        ("off", 0), ("mono", 1), ("colour", 2), ("color", 2), ("jpeg", 3),
        ("OFF", 0), (" Colour ", 2), ("JPEG", 3),   # case-insensitive, stripped
        (0, 0), (1, 1), (2, 2), (3, 3),
        ("0", 0), ("3", 3),                          # numeric strings
        (-1, None),             # out of range, not clamped -- a strict enum, unlike thumbnail_size
        (4, None),
        (99, None),
        ("banana", None),       # unrecognised word and not numeric
        (True, None),           # B-1: a bool must not silently become int(True) == 1
        (False, None),
        (None, None),
        ([], None),
        ({}, None),
    ]

    def test_decision_table(self):
        for raw, expected in self.CASES:
            with self.subTest(raw=raw):
                self.assertEqual(parse_thumbnail_mode(raw), expected)

    def test_thumbnail_mode_names_is_the_reverse_of_the_accepted_words(self):
        # Every value parse_thumbnail_mode() can return has a name, and
        # that name parses back to the same value -- the two directions
        # (settings.jsonc word -> int, int -> label/log text) agree.
        for value, name in THUMBNAIL_MODE_NAMES.items():
            self.assertEqual(parse_thumbnail_mode(name), value)


class ThumbnailStartupValueTests(unittest.TestCase):
    # (raw settings.jsonc value, expected validated value)
    CASES = [
        (_ABSENT, 2),          # no key at all -> shipped default (colour, 2026-09-13 final)
        (0, 0),
        (1, 1),
        (2, 2),
        (3, 3),                # jpeg
        ("off", 0),
        ("mono", 1),
        ("colour", 2),
        ("color", 2),
        ("jpeg", 3),
        (" JPEG ", 3),         # case-insensitive, stripped
        (-5, 2),               # out of range -> default (not clamped: see parse_thumbnail_mode)
        (99, 2),               # out of range -> default
        (True, 2),             # Phase 2: a bool is now rejected, not coerced -- was (True, 1)
        (False, 2),            # Phase 2: ditto -- was (False, 0)
        ("2", 2),              # numeric string
        ("0", 0),
        ("banana", 2),         # unrecognised -> default
        (None, 2),             # TypeError path -> default
        ([], 2),               # TypeError path -> default
        ({}, 2),               # TypeError path -> default
    ]

    def test_decision_table(self):
        for raw, expected in self.CASES:
            with self.subTest(raw=raw):
                self.assertEqual(
                    thumbnail_startup_value(_settings("thumbnail", raw)), expected
                )

    def test_empty_settings_dict_is_the_default(self):
        self.assertEqual(thumbnail_startup_value({}), 2)

    def test_missing_image_capture_section_is_the_default(self):
        self.assertEqual(thumbnail_startup_value({"some_other_key": {}}), 2)


class ThumbnailSizeStartupValueTests(unittest.TestCase):
    # (raw settings.jsonc value, expected validated value)
    CASES = [
        (_ABSENT, 2),          # no key at all -> shipped default (shift 2, 320x180)
        (0, 0),
        (1, 1),
        (4, 4),
        (-1, 0),               # clamped to the floor
        (12, 4),               # cinepi-raw would accept 12; this setting stops at 4
        (5, 4),                # one past the ceiling
        (True, 1),             # int(True) == 1, a valid shift -- does not crash
        ("2", 2),              # numeric string
        ("nonsense", 2),       # ValueError -> default
        (None, 2),             # TypeError -> default
        ([], 2),               # TypeError -> default
    ]

    def test_decision_table(self):
        for raw, expected in self.CASES:
            with self.subTest(raw=raw):
                self.assertEqual(
                    thumbnail_size_startup_value(_settings("thumbnail_size", raw)), expected
                )

    def test_empty_settings_dict_is_the_default(self):
        self.assertEqual(thumbnail_size_startup_value({}), 2)

    def test_missing_image_capture_section_is_the_default(self):
        self.assertEqual(thumbnail_size_startup_value({"some_other_key": {}}), 2)


if __name__ == "__main__":
    unittest.main()
