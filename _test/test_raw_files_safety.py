"""resolve_take() hardens a take DIRECTORY against traversal; nothing
previously said anything about a symlink placed INSIDE an otherwise-
legitimate take directory. A *.dng or *.wav symlink there globbed and
later opened exactly like a real file, because open() follows symlinks by
default -- an arbitrary-file-read primitive for anything able to write one
file into a take directory the pane already trusts. safe_take_children()
is the fix; these pin that it actually excludes what it should and keeps
what it shouldn't.
"""

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.app import raw_files  # noqa: E402


class SafeTakeChildrenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.take_dir = self.root / "CINEPI_take"
        self.take_dir.mkdir()
        self.outside = self.root / "outside"
        self.outside.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_real_file_is_included(self):
        real = self.take_dir / "F00000000.dng"
        real.write_bytes(b"not a real dng, just a marker")
        found = raw_files.safe_take_children(self.take_dir, "*.dng")
        self.assertEqual([p.name for p in found], ["F00000000.dng"])

    def test_a_symlink_escaping_the_take_dir_is_excluded(self):
        secret = self.outside / "secret.txt"
        secret.write_text("not for the pane to serve")
        evil = self.take_dir / "F00000001.dng"
        os.symlink(secret, evil)

        found = raw_files.safe_take_children(self.take_dir, "*.dng")
        self.assertEqual(found, [], "a symlink resolving outside take_dir must not be returned")

    def test_a_symlink_pointing_inside_the_take_dir_is_included(self):
        """Only escaping symlinks are the problem -- one that stays inside
        the take directory it links from is no different from a hardlink
        or a copy, and refusing it would just be a wrong-in-a-new-way bug."""
        real = self.take_dir / "F00000000.dng"
        real.write_bytes(b"marker")
        alias = self.take_dir / "F00000001.dng"
        os.symlink(real, alias)

        found = {p.name for p in raw_files.safe_take_children(self.take_dir, "*.dng")}
        self.assertEqual(found, {"F00000000.dng", "F00000001.dng"})

    def test_frame_names_and_wav_path_exclude_escaping_symlinks(self):
        """The actual call sites, not just the helper in isolation."""
        from module.app import playback

        for i in range(3):
            (self.take_dir / f"F0000000{i}.dng").write_bytes(b"marker")
        secret = self.outside / "id_rsa"
        secret.write_text("private key material")
        os.symlink(secret, self.take_dir / "F00000099.dng")

        names = playback._frame_names(self.take_dir)
        self.assertEqual(len(names), 3, "the escaping symlink must not appear in the frame list")

        wav_secret = self.outside / "shadow"
        wav_secret.write_text("not audio")
        os.symlink(wav_secret, self.take_dir / "audio.wav")
        # wav_path() calls raw_files.resolve_take() first, which this test
        # cannot satisfy without a real /media mount -- exercise the same
        # glob safe_take_children() call it makes instead.
        found_wav = raw_files.safe_take_children(self.take_dir, "*.wav")
        self.assertEqual(found_wav, [], "an escaping WAV symlink must not be servable as audio")


if __name__ == "__main__":
    unittest.main()
