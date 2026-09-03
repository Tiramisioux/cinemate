"""The DROP badge used to measure this playback session's own render
speed -- confounding "the camera couldn't decode fast enough right now"
with "the recording itself is missing frames," which is what an operator
actually wants to know about a take. dropped_frame_count() reads the
latter, purely from gaps in cinepi-raw's own zero-padded frame-index
suffix (e.g. "..._000000009.dng" -- simple_gui.py's _format_last_dng()
strips this same suffix going the other direction), matching this
module's file-only design: no redis, no recording-time telemetry.
"""

import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.app import playback  # noqa: E402


def make_frames(take_dir: Path, indices: list[int]) -> None:
    for i in indices:
        (take_dir / f"CINEPI_25-07-01_220547_F10_C00000_{i:09d}.dng").write_bytes(b"")


class DroppedFrameCountTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.take_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_contiguous_sequence_has_no_drops(self):
        make_frames(self.take_dir, range(10))
        self.assertEqual(playback.dropped_frame_count(self.take_dir), 0)

    def test_one_gap_is_one_drop(self):
        make_frames(self.take_dir, [0, 1, 2, 4, 5])  # 3 missing
        self.assertEqual(playback.dropped_frame_count(self.take_dir), 1)

    def test_multiple_gaps_sum(self):
        make_frames(self.take_dir, [0, 2, 3, 6, 9])  # missing 1, 4, 5, 7, 8
        self.assertEqual(playback.dropped_frame_count(self.take_dir), 5)

    def test_a_take_not_starting_at_zero_still_counts_correctly(self):
        """The span is what matters, not whether frame 0 exists -- a take
        resumed after a mid-take reconfigure could plausibly start later."""
        make_frames(self.take_dir, [100, 101, 103])  # missing 102
        self.assertEqual(playback.dropped_frame_count(self.take_dir), 1)

    def test_a_single_frame_take_has_no_drops(self):
        make_frames(self.take_dir, [0])
        self.assertEqual(playback.dropped_frame_count(self.take_dir), 0)

    def test_an_empty_take_is_undetermined_not_zero(self):
        self.assertIsNone(playback.dropped_frame_count(self.take_dir))

    def test_an_unexpected_filename_shape_is_undetermined(self):
        """Refuse to guess rather than silently mis-detect drops (or their
        absence) from a naming convention this wasn't written against."""
        (self.take_dir / "not_a_cinepi_frame.dng").write_bytes(b"")
        self.assertIsNone(playback.dropped_frame_count(self.take_dir))

    def test_wav_and_other_non_dng_files_are_ignored(self):
        make_frames(self.take_dir, range(5))
        (self.take_dir / "CINEPI_25-07-01_220547_F10_C00000.wav").write_bytes(b"")
        self.assertEqual(playback.dropped_frame_count(self.take_dir), 0)


if __name__ == "__main__":
    unittest.main()
