import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from module.recording_state import RecordingStateAggregator


class TestRecordingStateAggregator(unittest.TestCase):
    def test_ingest_and_seq_gap(self):
        agg = RecordingStateAggregator()
        snap1 = agg.ingest_cp_stats({"frameCount": 10, "sensorTimestamp": 1000, "stats_seq": 1})
        self.assertEqual(snap1.frame_count, 10)
        self.assertEqual(snap1.sensor_timestamp_ns, 1000)
        self.assertEqual(snap1.gap_count, 0)

        snap2 = agg.ingest_cp_stats({"frameCount": 11, "sensorTimestamp": 1040, "stats_seq": 4})
        self.assertEqual(snap2.frame_count, 11)
        self.assertEqual(snap2.gap_count, 1)

    def test_missing_fields_are_safe(self):
        agg = RecordingStateAggregator()
        snap = agg.ingest_cp_stats({"frameCount": "x", "encode_latency_ms": "12.3"})
        self.assertIsNone(snap.frame_count)
        self.assertEqual(snap.encode_latency_ms, 12.3)


if __name__ == "__main__":
    unittest.main()
