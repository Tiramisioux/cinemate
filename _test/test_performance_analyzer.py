import csv
import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from module.performance_analyzer import PerformanceAnalyzer


class DummyPubSub:
    def __init__(self, messages):
        self._messages = messages

    def subscribe(self, _channel):
        return None

    def listen(self):
        for msg in self._messages:
            yield msg

    def close(self):
        return None


class DummyRedisClient:
    def __init__(self, messages):
        self._messages = messages

    def pubsub(self):
        return DummyPubSub(self._messages)


class TestPerformanceAnalyzer(unittest.TestCase):
    def build_analyzer(self, tempdir, messages):
        redis_controller = MagicMock()
        redis_controller.get_value.side_effect = lambda key, default=None: {
            "is_recording": "0",
            "fps": "24",
            "fps_actual": "24",
            "buffer_size": "128",
            "is_buffering": "0",
            "is_writing_buf": "0",
            "write_speed_to_drive": "100 MB/s",
            "storage_type": "ssd",
        }.get(key, default)

        cinepi_controller = MagicMock()
        ssd_monitor = MagicMock()
        ssd_monitor.is_mounted = True

        analyzer = PerformanceAnalyzer(
            redis_controller=redis_controller,
            cinepi_controller=cinepi_controller,
            ssd_monitor=ssd_monitor,
            dmesg_monitor=MagicMock(undervoltage_flag=False),
            usb_monitor=MagicMock(usb_mic=None, audio_monitor=MagicMock(sample_rate=None, channels=None)),
            analysis_root=tempdir,
            redis_client=DummyRedisClient(messages),
        )
        return analyzer, redis_controller, cinepi_controller, ssd_monitor

    def test_timestamp_fallback_and_key(self):
        analyzer, *_ = self.build_analyzer(Path(tempfile.mkdtemp()), [])

        ts, key = analyzer._extract_sensor_timestamp({"sensorTimestamp": 1234})
        self.assertEqual(ts, 1234)
        self.assertEqual(key, "sensorTimestamp")

        ts, key = analyzer._extract_sensor_timestamp({"timestamp": 5678})
        self.assertEqual(ts, 5678)
        self.assertEqual(key, "timestamp")

    @patch("module.performance_analyzer.os.path.ismount", return_value=True)
    def test_csv_creation_with_headers(self, _ismount):
        tempdir = Path(tempfile.mkdtemp())
        messages = [
            {"type": "message", "data": b'{"timestamp": 1000, "frameCount": 1, "framerate": 24, "bufferSize": 0}'},
            {"type": "message", "data": b'{"timestamp": 2000, "frameCount": 2, "framerate": 24, "bufferSize": 0}'},
        ]
        analyzer, _redis, controller, _ssd = self.build_analyzer(tempdir, messages)

        started = analyzer.start("f", 2)
        self.assertTrue(started)
        analyzer._thread.join(timeout=2)

        csv_files = list(tempdir.glob("*_analyze.csv"))
        self.assertEqual(len(csv_files), 1)

        with csv_files[0].open() as f:
            reader = csv.reader(f)
            header = next(reader)
        self.assertEqual(header, PerformanceAnalyzer.CSV_FIELDS)

        summary_files = list(tempdir.glob("*_summary.json"))
        self.assertEqual(len(summary_files), 1)
        summary = json.loads(summary_files[0].read_text())
        self.assertEqual(summary["rows_written"], 2)
        controller.rec.assert_called_once()

    def test_timestamp_gap_drop_detection(self):
        analyzer, *_ = self.build_analyzer(Path(tempfile.mkdtemp()), [])
        dropped, reason = analyzer._detect_drop(1_000_000_000, 1, fps_expected=24, fps_actual=24)
        self.assertFalse(dropped)
        self.assertEqual(reason, "")

        dropped, reason = analyzer._detect_drop(1_100_000_000, 2, fps_expected=24, fps_actual=24)
        self.assertTrue(dropped)
        self.assertEqual(reason, "timestamp_gap")

    def test_stats_seq_gap_detection(self):
        analyzer, *_ = self.build_analyzer(Path(tempfile.mkdtemp()), [])
        seq, gap = analyzer._extract_seq_gap({"stats_seq": 1})
        self.assertEqual(seq, 1)
        self.assertEqual(gap, 0)

        seq, gap = analyzer._extract_seq_gap({"stats_seq": 4})
        self.assertEqual(seq, 4)
        self.assertEqual(gap, 1)

    @patch("module.performance_analyzer.os.path.ismount", return_value=False)
    def test_storage_unavailable_fails_cleanly(self, _ismount):
        tempdir = Path(tempfile.mkdtemp())
        analyzer, *_ = self.build_analyzer(tempdir, [])
        analyzer.ssd_monitor.is_mounted = False
        started = analyzer.start("s", 1)
        self.assertFalse(started)


if __name__ == "__main__":
    unittest.main()
