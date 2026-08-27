"""Saving settings must never be the only copy of what it overwrote.

put_settings() rewrites settings.jsonc from a parsed JSON object, which drops
every comment in the file -- 74 of its 386 lines, including the section banners
and the per-key explanations. Preserving them is a separate change; making the
overwrite recoverable is this one, and it is the part that must not wait.

The recovery console has done this correctly all along: "Back up, then
atomically replace. The order is not negotiable."
"""

import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.app.settings_editor import SETTINGS_BACKUP_KEEP, _backup_settings


SAMPLE = '{\n  // a comment worth keeping\n  "system": {"welcome": {"show": true}}\n}\n'


class SettingsBackupTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.settings = self.dir / "settings.jsonc"
        self.settings.write_text(SAMPLE, encoding="utf-8")

    def test_backup_is_byte_identical_including_comments(self):
        backup = _backup_settings(self.settings)

        self.assertIsNotNone(backup)
        self.assertEqual(backup.read_bytes(), SAMPLE.encode("utf-8"))
        # The comment is the whole reason the backup exists.
        self.assertIn("// a comment worth keeping", backup.read_text(encoding="utf-8"))

    def test_backups_rotate_rather_than_growing_without_bound(self):
        for _ in range(SETTINGS_BACKUP_KEEP + 5):
            _backup_settings(self.settings)

        kept = list((self.dir / ".settings-backups").glob("settings.jsonc.*.bak"))
        self.assertLessEqual(len(kept), SETTINGS_BACKUP_KEEP)

    def test_saves_inside_one_second_do_not_collide(self):
        first = _backup_settings(self.settings)
        second = _backup_settings(self.settings)

        self.assertNotEqual(first, second)
        self.assertTrue(first.exists() and second.exists())

    def test_a_missing_source_is_not_an_error(self):
        # Writing a settings file that was never there is legitimate and must
        # not be blocked by a failed backup.
        self.assertIsNone(_backup_settings(self.dir / "absent.jsonc"))


if __name__ == "__main__":
    unittest.main()
