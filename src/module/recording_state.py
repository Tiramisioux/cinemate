import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class RecordingStateSnapshot:
    frame_count: int | None = None
    framerate: float | None = None
    sensor_timestamp_ns: int | None = None
    timestamp_ns: int | None = None
    timestamp_cam0_ns: int | None = None
    timestamp_cam1_ns: int | None = None
    buffer_size: int | None = None
    encode_queue_size: int | None = None
    disk_queue_size: int | None = None
    ram_buffers: int | None = None
    encode_latency_ms: float | None = None
    disk_latency_ms: float | None = None
    stats_seq: int | None = None
    gap_count: int = 0


class RecordingStateAggregator:
    """Authoritative cp_stats -> canonical runtime recording state."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = RecordingStateSnapshot()
        self._last_stats_seq: int | None = None

    @staticmethod
    def _to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def ingest_cp_stats(self, stats_data: dict) -> RecordingStateSnapshot:
        with self._lock:
            current = self._state
            stats_seq = self._to_int(stats_data.get("stats_seq"))
            gap_count = current.gap_count
            if stats_seq is not None and self._last_stats_seq is not None and stats_seq > self._last_stats_seq + 1:
                gap_count += 1
            if stats_seq is not None:
                self._last_stats_seq = stats_seq

            sensor_timestamp = self._to_int(stats_data.get("sensorTimestamp"))
            timestamp = self._to_int(stats_data.get("timestamp"))
            timestamp_cam0 = self._to_int(stats_data.get("timestamp_cam0"))
            timestamp_cam1 = self._to_int(stats_data.get("timestamp_cam1"))

            self._state = RecordingStateSnapshot(
                frame_count=self._to_int(stats_data.get("frameCount")),
                framerate=self._to_float(stats_data.get("framerate")),
                sensor_timestamp_ns=sensor_timestamp,
                timestamp_ns=timestamp,
                timestamp_cam0_ns=timestamp_cam0,
                timestamp_cam1_ns=timestamp_cam1,
                buffer_size=self._to_int(stats_data.get("bufferSize")),
                encode_queue_size=self._to_int(stats_data.get("encode_queue_size")),
                disk_queue_size=self._to_int(stats_data.get("disk_queue_size")),
                ram_buffers=self._to_int(stats_data.get("ram_buffers")),
                encode_latency_ms=self._to_float(stats_data.get("encode_latency_ms")),
                disk_latency_ms=self._to_float(stats_data.get("disk_latency_ms")),
                stats_seq=stats_seq,
                gap_count=gap_count,
            )
            return self._state

    def snapshot(self) -> RecordingStateSnapshot:
        with self._lock:
            return self._state
