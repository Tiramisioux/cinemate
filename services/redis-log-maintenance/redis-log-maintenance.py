#!/usr/bin/env python3
"""Trim Redis logs to keep the Pi root filesystem healthy."""

from __future__ import annotations

import fcntl
import logging
import os
import sys
from pathlib import Path

LOG_LEVEL = os.getenv("REDIS_LOG_MAINTENANCE_LOG", "INFO").upper()
LOG_DIR = Path(os.getenv("REDIS_LOG_DIR", "/var/log/redis"))
ACTIVE_LOG = Path(os.getenv("REDIS_LOG_PATH", str(LOG_DIR / "redis-server.log")))
ROTATION_GLOB = os.getenv("REDIS_LOG_ROTATION_GLOB", "redis-server.log.*")
MAX_ACTIVE_BYTES = int(os.getenv("REDIS_LOG_MAX_BYTES", str(16 * 1024 * 1024)))
KEEP_ACTIVE_BYTES = int(os.getenv("REDIS_LOG_KEEP_BYTES", str(4 * 1024 * 1024)))
KEEP_ROTATIONS = int(os.getenv("REDIS_LOG_KEEP_ROTATIONS", "2"))
LOCK_PATH = Path(os.getenv("REDIS_LOG_LOCK_PATH", "/run/redis-log-maintenance.lock"))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [redis-log-maintenance] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("redis-log-maintenance")


def _human_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    amount = float(value)
    for unit in units:
        if amount < 1024.0 or unit == units[-1]:
            return f"{amount:.1f}{unit}"
        amount /= 1024.0
    return f"{value}B"


def _rotation_files() -> list[Path]:
    return sorted(
        (
            path
            for path in LOG_DIR.glob(ROTATION_GLOB)
            if path.is_file() and path != ACTIVE_LOG
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _prune_rotations() -> int:
    if KEEP_ROTATIONS < 0 or not LOG_DIR.exists():
        return 0

    reclaimed = 0
    for stale_path in _rotation_files()[KEEP_ROTATIONS:]:
        try:
            size = stale_path.stat().st_size
            stale_path.unlink()
            reclaimed += size
            log.info("Removed old Redis rotation %s (%s)", stale_path, _human_bytes(size))
        except FileNotFoundError:
            continue
        except OSError as exc:
            log.warning("Failed to remove %s: %s", stale_path, exc)
    return reclaimed


def _trim_active_log() -> int:
    if not ACTIVE_LOG.exists():
        log.info("Active Redis log %s does not exist; nothing to trim", ACTIVE_LOG)
        return 0

    max_active = max(0, MAX_ACTIVE_BYTES)
    keep_active = max(0, KEEP_ACTIVE_BYTES)

    try:
        size = ACTIVE_LOG.stat().st_size
    except OSError as exc:
        log.warning("Failed to stat %s: %s", ACTIVE_LOG, exc)
        return 0

    if max_active <= 0 or size <= max_active:
        log.info("Redis log size is %s; no trim needed", _human_bytes(size))
        return 0

    keep_active = min(size, keep_active if keep_active else min(size, max_active))

    try:
        with ACTIVE_LOG.open("rb+") as handle:
            if keep_active:
                handle.seek(size - keep_active)
                tail = handle.read(keep_active)
            else:
                tail = b""
            handle.seek(0)
            handle.write(tail)
            handle.truncate(len(tail))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        log.warning("Failed to trim %s: %s", ACTIVE_LOG, exc)
        return 0

    reclaimed = size - len(tail)
    log.info(
        "Trimmed %s from %s to %s",
        ACTIVE_LOG,
        _human_bytes(size),
        _human_bytes(len(tail)),
    )
    return reclaimed


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log.info("Another redis-log-maintenance run is already in progress")
            return 0

        reclaimed = _prune_rotations()
        reclaimed += _trim_active_log()
        log.info("Redis log maintenance finished; reclaimed %s", _human_bytes(reclaimed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
