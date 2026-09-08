"""Deleting a clip must not report failure for a delete that worked.

The operator report was "deleting a clip shows error". The delete itself is
fine -- method, URL escaping, folder-vs-file and permissions all check out.
What was wrong is that it was not idempotent:

  * nothing disabled the row while the request was in flight, and showConfirm
    closes the modal before running its callback, so the row is instantly
    clickable again;
  * rmtree is thousands of unlinks, and the refresh behind it stats every file
    on the card, so the deleted row stays on screen for a long time;
  * a second tap hit a take that was already gone and got
    "Delete failed: Take '...' not found" -- on a delete that had succeeded.

The bulk path had it worse: `all_ok = all(...)`, so one already-gone name
turned a whole batch into "Some deletes failed".

A partial rmtree was also unrecoverable: once the *.dng files were gone the
directory no longer satisfied _is_take_dir(), so it neither listed nor
deleted, and sat on the card taking space.
"""

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

_APP_PKG = types.ModuleType("module.app")
_APP_PKG.__path__ = [str(ROOT / "src" / "module" / "app")]
sys.modules.setdefault("module.app", _APP_PKG)

from module.app import raw_files


class DeleteTakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "RAW"
        (self.root).mkdir()
        self.take = self.root / "CINEPI_25-07-01_220547_F10_C00000_cam0"
        self.take.mkdir()
        (self.take / "000000.dng").write_bytes(b"x")
        (self.take / "audio.wav").write_bytes(b"y")
        self.patch = mock.patch.object(raw_files, "MEDIA_ROOT", self.tmp)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_first_delete_succeeds(self):
        ok, msg = raw_files.delete_take(self.take.name)
        self.assertTrue(ok, msg)
        self.assertFalse(self.take.exists())

    def test_second_delete_is_also_a_success(self):
        raw_files.delete_take(self.take.name)
        ok, msg = raw_files.delete_take(self.take.name)
        self.assertTrue(ok, msg)          # the actual bug
        self.assertIn("already", msg.lower())

    def test_a_partially_deleted_take_can_still_be_removed(self):
        # No *.dng left: not an _is_take_dir any more, so the old resolve
        # returned None and the orphan was undeletable.
        (self.take / "000000.dng").unlink()
        self.assertTrue(self.take.exists())
        ok, msg = raw_files.delete_take(self.take.name)
        self.assertTrue(ok, msg)
        self.assertFalse(self.take.exists())

    def test_traversal_is_still_refused(self):
        for bad in ("../escape", "a/b", "a\\b", "..", ".", ""):
            ok, _ = raw_files.delete_take(bad)
            self.assertFalse(ok, f"{bad!r} should be refused")

    def test_a_real_failure_is_still_a_failure_and_is_readable(self):
        import errno
        with mock.patch.object(
            raw_files.shutil, "rmtree",
            side_effect=OSError(errno.EROFS, "Read-only file system")
        ):
            ok, msg = raw_files.delete_take(self.take.name)
        self.assertFalse(ok)
        self.assertIn("read-only", msg.lower())
        self.assertNotIn("Errno", msg)     # not a raw errno string

    def test_resolve_take_still_only_matches_real_takes(self):
        self.assertIsNotNone(raw_files.resolve_take(self.take.name))
        (self.take / "000000.dng").unlink()
        self.assertIsNone(raw_files.resolve_take(self.take.name))


if __name__ == "__main__":
    unittest.main()
