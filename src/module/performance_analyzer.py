import csv
import datetime
import json
import logging
import os
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover - allows running unit tests in minimal environments
    psutil = None

try:
    import redis
except ImportError:  # pragma: no cover - allows running unit tests in minimal environments
    redis = None

try:
    from module.redis_controller import ParameterKey
except Exception:  # pragma: no cover - tests can run without full runtime deps
    class _Key:
        def __init__(self, value):
            self.value = value

    class ParameterKey:
        IS_RECORDING = _Key("is_recording")
        FPS = _Key("fps")
        FPS_ACTUAL = _Key("fps_actual")
        BUFFER = _Key("buffer")
        BUFFER_SIZE = _Key("buffer_size")
        IS_BUFFERING = _Key("is_buffering")
        IS_WRITING_BUF = _Key("is_writing_buf")
        WRITE_SPEED_TO_DRIVE = _Key("write_speed_to_drive")
        STORAGE_TYPE = _Key("storage_type")


class PerformanceAnalyzer:
    CSV_FIELDS = [
        "monotonic_seq",
        "wall_time_iso",
        "sensor_timestamp_ns",
        "timestamp_key_used",
        "cp_stats_seq",
        "cp_stats_seq_gap",
        "cp_stats_timestamp_gap",
        "frame_count",
        "fps_expected",
        "fps_actual",
        "dropped_frame_flag",
        "hard_drop_flag",
        "soft_drop_flag",
        "drop_class",
        "drop_reason",
        "buffer_used",
        "buffer_size",
        "is_buffering",
        "is_writing_buf",
        "write_speed_mb_s",
        "encode_queue_size",
        "disk_queue_size",
        "ram_buffers",
        "encode_latency_ms",
        "disk_latency_ms",
        "cpu_percent_total",
        "cpu_percent_per_core",
        "ram_percent",
        "cpu_temp_c",
        "loadavg_1m",
        "disk_write_bytes_delta",
        "net_tx_bytes_delta",
        "net_rx_bytes_delta",
        "undervoltage_flag",
        "storage_type",
        "is_mounted",
        "mic_connected",
        "mic_sample_rate",
        "mic_channels",
        "proc_cpu_cinepi_raw",
        "proc_cpu_cinemate",
        "proc_cpu_redis",
        "proc_cpu_arecord",
        "throttled_flags",
    ]

    def __init__(
        self,
        redis_controller,
        cinepi_controller,
        ssd_monitor,
        dmesg_monitor=None,
        usb_monitor=None,
        analysis_root="/media/RAW/_analysis",
        redis_client=None,
        settings=None,
    ):
        self.redis_controller = redis_controller
        self.cinepi_controller = cinepi_controller
        self.ssd_monitor = ssd_monitor
        self.dmesg_monitor = dmesg_monitor
        self.usb_monitor = usb_monitor
        self.analysis_root = Path(analysis_root)
        self.settings = settings or {}
        self._timestamp_gap_factor = self._read_timestamp_gap_factor()
        if redis_client is not None:
            self.redis_client = redis_client
        elif redis is not None:
            self.redis_client = redis.StrictRedis(host="localhost", port=6379, db=0)
        else:
            raise RuntimeError("redis package is required when redis_client is not provided")

        self._thread = None
        self._stop_event = threading.Event()
        self._active = False
        self._lock = threading.Lock()

        self._seq = 0
        self._rows = 0
        self._drop_count = 0
        self._soft_drop_count = 0
        self._hard_drop_reasons = Counter()
        self._soft_drop_reasons = Counter()
        self._prev_timestamp_ns = None
        self._prev_frame_count = None
        self._prev_stats_seq = None
        self._stats_seq_gap_events = 0
        self._timestamp_gap_events = 0
        self._start_monotonic = None
        self._last_disk_write_bytes = None
        self._last_net_tx = None
        self._last_net_rx = None
        self._last_throttled_sample = 0.0
        self._last_throttled_flags = ""

        self._target_mode = None
        self._target_amount = None
        self._target_seconds = None
        self._target_frames = None
        self._start_is_recording = False

        self._csv_path = None
        self._summary_path = None

    @property
    def is_active(self):
        return self._active

    def start(self, mode, amount):
        with self._lock:
            if self._active:
                logging.info("Performance analyzer is already running.")
                return False

            normalized_mode = self._normalize_mode(mode)
            if normalized_mode is None:
                logging.info("Unknown analyze mode. Use 's' for seconds or 'f' for frames.")
                return False

            validated_amount = self._validate_amount(normalized_mode, amount)
            if validated_amount is None:
                return False

            if not self._prepare_output_paths():
                return False

            self._target_mode = normalized_mode
            self._target_amount = validated_amount
            if normalized_mode == "seconds":
                self._target_seconds = float(validated_amount)
                self._target_frames = None
            else:
                self._target_frames = int(validated_amount)
                self._target_seconds = None

            self._reset_session_state()

            self._start_is_recording = str(self.redis_controller.get_value(ParameterKey.IS_RECORDING.value, "0")) == "1"
            self.cinepi_controller.rec(mode, validated_amount)

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="PerformanceAnalyzer")
            self._active = True
            self._thread.start()
            logging.info(
                "Performance analyzer started (%s=%s). Writing to %s",
                normalized_mode,
                validated_amount,
                self._csv_path,
            )
            return True

    def stop(self):
        with self._lock:
            if not self._active:
                return
            self._stop_event.set()

    def _normalize_mode(self, mode):
        mode_key = str(mode).strip().lower()
        if mode_key in {"s", "sec", "secs", "second", "seconds"}:
            return "seconds"
        if mode_key in {"f", "frame", "frames"}:
            return "frames"
        return None

    def _validate_amount(self, mode, amount):
        try:
            value = float(amount) if mode == "seconds" else int(amount)
        except (TypeError, ValueError):
            logging.info("Analyze amount must be numeric.")
            return None

        if value <= 0:
            logging.info("Analyze amount must be greater than zero.")
            return None

        return value

    def _prepare_output_paths(self):
        if not getattr(self.ssd_monitor, "is_mounted", False):
            logging.error("Analyze failed: RAW storage is not mounted.")
            return False

        if not os.path.ismount("/media/RAW"):
            logging.error("Analyze failed: /media/RAW is unavailable.")
            return False

        try:
            self.analysis_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logging.error("Analyze failed: unable to create output folder %s (%s)", self.analysis_root, exc)
            return False

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._csv_path = self.analysis_root / f"{stamp}_analyze.csv"
        self._summary_path = self.analysis_root / f"{stamp}_summary.json"
        return True

    def _reset_session_state(self):
        self._seq = 0
        self._rows = 0
        self._drop_count = 0
        self._soft_drop_count = 0
        self._hard_drop_reasons.clear()
        self._soft_drop_reasons.clear()
        self._prev_timestamp_ns = None
        self._prev_frame_count = None
        self._prev_stats_seq = None
        self._stats_seq_gap_events = 0
        self._timestamp_gap_events = 0
        self._start_monotonic = time.monotonic()

        disk = psutil.disk_io_counters() if psutil and hasattr(psutil, "disk_io_counters") else None
        net = psutil.net_io_counters() if psutil and hasattr(psutil, "net_io_counters") else None
        self._last_disk_write_bytes = getattr(disk, "write_bytes", None)
        self._last_net_tx = getattr(net, "bytes_sent", None)
        self._last_net_rx = getattr(net, "bytes_recv", None)
        self._last_throttled_sample = 0.0
        self._last_throttled_flags = ""

        if psutil:
            psutil.cpu_percent(interval=None)
            psutil.cpu_percent(interval=None, percpu=True)
            for process in psutil.process_iter(attrs=["name"]):
                process.cpu_percent(None)

    def _run(self):
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe("cp_stats")

        try:
            with self._csv_path.open("w", newline="", buffering=1, encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=self.CSV_FIELDS)
                writer.writeheader()

                for message in pubsub.listen():
                    if self._stop_event.is_set():
                        break
                    if message.get("type") != "message":
                        continue
                    stats_data = self._decode_stats(message.get("data"))
                    if stats_data is None:
                        continue

                    row = self._build_row(stats_data)
                    writer.writerow(row)
                    self._rows += 1

                    if self._should_finish(row):
                        break
        finally:
            try:
                pubsub.close()
            except Exception:
                pass
            self._finalize()
            with self._lock:
                self._active = False

    def _decode_stats(self, payload):
        if payload is None:
            return None
        if isinstance(payload, bytes):
            text = payload.decode("utf-8", errors="ignore").strip()
        else:
            text = str(payload).strip()
        if not text.startswith("{"):
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _extract_sensor_timestamp(self, stats_data):
        sensor_ts = stats_data.get("sensorTimestamp")
        if sensor_ts is not None:
            try:
                return int(sensor_ts), "sensorTimestamp"
            except (TypeError, ValueError):
                pass

        fallback_ts = stats_data.get("timestamp")
        if fallback_ts is not None:
            try:
                return int(fallback_ts), "timestamp"
            except (TypeError, ValueError):
                pass

        return None, ""

    def _build_row(self, stats_data):
        self._seq += 1
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        sensor_timestamp_ns, timestamp_key_used = self._extract_sensor_timestamp(stats_data)
        frame_count = self._to_int(stats_data.get("frameCount"))
        cp_stats_seq, cp_stats_seq_gap = self._extract_seq_gap(stats_data)

        fps_expected = self._read_float(ParameterKey.FPS.value)
        fps_actual = self._to_float(stats_data.get("framerate"))
        if fps_actual is None:
            fps_actual = self._read_float(ParameterKey.FPS_ACTUAL.value)

        hard_drop_flag, soft_drop_flag, drop_reason = self._classify_drop(
            sensor_timestamp_ns=sensor_timestamp_ns,
            frame_count=frame_count,
            cp_stats_seq_gap=cp_stats_seq_gap,
            fps_expected=fps_expected,
            fps_actual=fps_actual,
        )
        cp_stats_timestamp_gap = 1 if drop_reason == "timestamp_gap" else 0
        if cp_stats_timestamp_gap:
            self._timestamp_gap_events += 1

        buffer_used = self._to_int(stats_data.get("bufferSize"))
        if buffer_used is None:
            buffer_used = self._read_int(ParameterKey.BUFFER.value)

        disk_delta = self._sample_disk_delta()
        net_tx_delta, net_rx_delta = self._sample_net_delta()

        row = {
            "monotonic_seq": self._seq,
            "wall_time_iso": now_iso,
            "sensor_timestamp_ns": sensor_timestamp_ns,
            "timestamp_key_used": timestamp_key_used,
            "cp_stats_seq": cp_stats_seq,
            "cp_stats_seq_gap": cp_stats_seq_gap,
            "cp_stats_timestamp_gap": cp_stats_timestamp_gap,
            "frame_count": frame_count,
            "fps_expected": fps_expected,
            "fps_actual": fps_actual,
            "dropped_frame_flag": int(hard_drop_flag),
            "hard_drop_flag": int(hard_drop_flag),
            "soft_drop_flag": int(soft_drop_flag),
            "drop_class": "hard" if hard_drop_flag else "soft" if soft_drop_flag else "",
            "drop_reason": drop_reason,
            "buffer_used": buffer_used,
            "buffer_size": self._read_int(ParameterKey.BUFFER_SIZE.value),
            "is_buffering": self._read_bool(ParameterKey.IS_BUFFERING.value),
            "is_writing_buf": self._read_bool(ParameterKey.IS_WRITING_BUF.value),
            "write_speed_mb_s": self._parse_write_speed(self.redis_controller.get_value(ParameterKey.WRITE_SPEED_TO_DRIVE.value)),
            "encode_queue_size": self._to_int(stats_data.get("encode_queue_size")),
            "disk_queue_size": self._to_int(stats_data.get("disk_queue_size")),
            "ram_buffers": self._to_int(stats_data.get("ram_buffers")),
            "encode_latency_ms": self._to_float(stats_data.get("encode_latency_ms")),
            "disk_latency_ms": self._to_float(stats_data.get("disk_latency_ms")),
            "cpu_percent_total": psutil.cpu_percent(interval=None) if psutil else None,
            "cpu_percent_per_core": json.dumps(psutil.cpu_percent(interval=None, percpu=True)) if psutil else "[]",
            "ram_percent": psutil.virtual_memory().percent if psutil else None,
            "cpu_temp_c": self._cpu_temp_c(),
            "loadavg_1m": os.getloadavg()[0] if hasattr(os, "getloadavg") else None,
            "disk_write_bytes_delta": disk_delta,
            "net_tx_bytes_delta": net_tx_delta,
            "net_rx_bytes_delta": net_rx_delta,
            "undervoltage_flag": int(bool(getattr(self.dmesg_monitor, "undervoltage_flag", False))),
            "storage_type": self.redis_controller.get_value(ParameterKey.STORAGE_TYPE.value) or "",
            "is_mounted": int(bool(getattr(self.ssd_monitor, "is_mounted", False))),
            "mic_connected": int(bool(getattr(self.usb_monitor, "usb_mic", None))),
            "mic_sample_rate": getattr(getattr(self.usb_monitor, "audio_monitor", None), "sample_rate", None),
            "mic_channels": getattr(getattr(self.usb_monitor, "audio_monitor", None), "channels", None),
            "proc_cpu_cinepi_raw": self._process_cpu("cinepi-raw"),
            "proc_cpu_cinemate": self._process_cpu("python"),
            "proc_cpu_redis": self._process_cpu("redis"),
            "proc_cpu_arecord": self._process_cpu("arecord"),
            "throttled_flags": self._sample_throttled_flags(),
        }

        return row

    def _extract_seq_gap(self, stats_data):
        seq = self._to_int(stats_data.get("stats_seq"))
        gap = 0
        if seq is not None and self._prev_stats_seq is not None and seq > self._prev_stats_seq + 1:
            gap = 1
            self._stats_seq_gap_events += 1
        if seq is not None:
            self._prev_stats_seq = seq
        return seq, gap

    def _should_finish(self, row):
        if self._target_mode == "seconds":
            elapsed = time.monotonic() - self._start_monotonic
            return elapsed >= self._target_seconds

        if self._target_mode == "frames":
            frame_count = row.get("frame_count")
            if frame_count is not None:
                return frame_count >= self._target_frames
            return self._rows >= self._target_frames

        return False

    def _classify_drop(self, sensor_timestamp_ns, frame_count, cp_stats_seq_gap, fps_expected, fps_actual):
        hard_drop = False
        soft_drop = False
        reason = ""

        expected_fps = fps_expected if fps_expected and fps_expected > 0 else fps_actual

        if sensor_timestamp_ns is not None and self._prev_timestamp_ns is not None and expected_fps and expected_fps > 0:
            expected_period_ns = int(1_000_000_000 / expected_fps)
            delta = sensor_timestamp_ns - self._prev_timestamp_ns
            if delta > int(expected_period_ns * self._timestamp_gap_factor):
                hard_drop = True
                reason = "timestamp_gap"

        if not hard_drop and cp_stats_seq_gap:
            hard_drop = True
            reason = "cp_stats_seq_gap"

        if not hard_drop and frame_count is not None and self._prev_frame_count is not None:
            if frame_count - self._prev_frame_count > 1:
                soft_drop = True
                reason = "framecount_discontinuity"

        if not hard_drop and not soft_drop and fps_expected and fps_actual is not None and abs(fps_actual - fps_expected) > 1:
            soft_drop = True
            reason = "fps_deviation_only"

        if (hard_drop or soft_drop) and not reason:
            reason = "unknown"

        if hard_drop:
            self._drop_count += 1
            self._hard_drop_reasons[reason] += 1
        elif soft_drop:
            self._soft_drop_count += 1
            self._soft_drop_reasons[reason] += 1

        if sensor_timestamp_ns is not None:
            self._prev_timestamp_ns = sensor_timestamp_ns
        if frame_count is not None:
            self._prev_frame_count = frame_count

        return hard_drop, soft_drop, reason

    def _finalize(self):
        summary = {
            "csv_path": str(self._csv_path),
            "target_mode": self._target_mode,
            "target_amount": self._target_amount,
            "rows_written": self._rows,
            "drop_candidates": self._drop_count,
            "hard_drop_count": self._drop_count,
            "soft_drop_count": self._soft_drop_count,
            "hard_drop_reasons": dict(self._hard_drop_reasons),
            "soft_drop_reasons": dict(self._soft_drop_reasons),
            "stats_seq_gap_events": self._stats_seq_gap_events,
            "timestamp_gap_events": self._timestamp_gap_events,
            "start_recording_already_active": self._start_is_recording,
            "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        try:
            with self._summary_path.open("w", encoding="utf-8") as handle:
                json.dump(summary, handle, indent=2)
            logging.info("Performance analyzer complete. Summary: %s", self._summary_path)
        except OSError as exc:
            logging.error("Failed to write analyzer summary: %s", exc)

    def _sample_disk_delta(self):
        if not psutil:
            return None
        counters = psutil.disk_io_counters()
        if counters is None:
            return None

        current = getattr(counters, "write_bytes", None)
        if current is None or self._last_disk_write_bytes is None:
            self._last_disk_write_bytes = current
            return None

        delta = max(0, current - self._last_disk_write_bytes)
        self._last_disk_write_bytes = current
        return delta

    def _sample_net_delta(self):
        if not psutil:
            return None, None
        counters = psutil.net_io_counters()
        if counters is None:
            return None, None

        tx = getattr(counters, "bytes_sent", None)
        rx = getattr(counters, "bytes_recv", None)

        tx_delta = None if tx is None or self._last_net_tx is None else max(0, tx - self._last_net_tx)
        rx_delta = None if rx is None or self._last_net_rx is None else max(0, rx - self._last_net_rx)

        self._last_net_tx = tx
        self._last_net_rx = rx

        return tx_delta, rx_delta

    def _cpu_temp_c(self):
        if not psutil:
            return None
        try:
            temps = psutil.sensors_temperatures() or {}
        except Exception:
            return None

        for readings in temps.values():
            if not readings:
                continue
            first = readings[0]
            value = getattr(first, "current", None)
            if value is not None:
                return value
        return None

    def _process_cpu(self, name_hint):
        total = 0.0
        hint = name_hint.lower()
        if not psutil:
            return 0.0
        for process in psutil.process_iter(attrs=["name"]):
            name = (process.info.get("name") or "").lower()
            if hint in name:
                try:
                    total += process.cpu_percent(None)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        return round(total, 3)

    def _read_bool(self, key):
        value = self.redis_controller.get_value(key)
        if value is None:
            return 0
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return 1
        if text in {"0", "false", "no", "off", ""}:
            return 0
        try:
            return 1 if int(text) else 0
        except (TypeError, ValueError):
            return 0

    def _read_float(self, key):
        return self._to_float(self.redis_controller.get_value(key))

    def _read_int(self, key):
        return self._to_int(self.redis_controller.get_value(key))

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

    @staticmethod
    def _parse_write_speed(value):
        if value is None:
            return None
        text = str(value)
        number = "".join(c for c in text if c.isdigit() or c in {".", "-"})
        if not number:
            return None
        try:
            return float(number)
        except ValueError:
            return None

    def _read_timestamp_gap_factor(self):
        value = (
            self.settings.get("analysis", {})
            .get("drop", {})
            .get("timestamp_gap_factor", 1.5)
        )
        factor = self._to_float(value)
        return factor if factor and factor > 0 else 1.5

    def _sample_throttled_flags(self):
        now = time.monotonic()
        if now - self._last_throttled_sample < 1.0:
            return self._last_throttled_flags

        self._last_throttled_sample = now
        try:
            result = subprocess.run(
                ["vcgencmd", "get_throttled"],
                capture_output=True,
                text=True,
                timeout=0.2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            self._last_throttled_flags = ""
            return self._last_throttled_flags

        output = (result.stdout or "").strip()
        if "=" in output:
            self._last_throttled_flags = output.split("=", 1)[1].strip()
        else:
            self._last_throttled_flags = ""
        return self._last_throttled_flags
