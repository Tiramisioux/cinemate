"""RAW take browsing/download/delete for the settings editor's RAW files pane.

No list-all/delete/download endpoint exists anywhere in this codebase --
only SSDMonitor.get_latest_recording_infos() (src/module/ssd_monitor.py),
which returns just the most-recent take(s) for GUI status display. This
module is new, from-scratch plumbing built on the on-disk convention
storage-automount.py owns: recordings land as subdirectories directly under
/media/RAW (active) and /media/RAW1, /media/RAW2, ... (standby, promoted on
active-drive removal).

Deliberately does not depend on the live SSDMonitor instance (create_app()
doesn't currently pass one to the Flask app, and threading a new dependency
through main.py/create_app() is out of scope for this pane) -- storage_summary()
reads free/total space and filesystem type directly via shutil/psutil instead.
"""
from __future__ import annotations

import io
import logging
import shutil
import threading
import zipfile
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)

MEDIA_ROOT = Path("/media")
ACTIVE_LABEL = "RAW"

# W9: caps full-bandwidth reads off the media volume during a download. The
# server is threaded werkzeug with no ceiling of its own -- storage
# contention here is the same contention already known to cause frame drops
# and ALSA xruns during a take. Acquired non-blocking in the route; released
# inside the streaming generator's `finally`, not `@after_this_request` --
# that hook runs at finalize_request, before the WSGI server ever consumes
# the response iterable, so it would be a no-op for the case this exists to
# protect. Matching client concurrency cap: settings_editor.html's
# DOWNLOAD_CONCURRENCY.
DOWNLOAD_SEMAPHORE = threading.BoundedSemaphore(2)


def _media_roots() -> list[Path]:
    """/media/RAW (active) first, then /media/RAW1, /media/RAW2, ...
    (standby) -- whatever's actually mounted right now."""
    if not MEDIA_ROOT.is_dir():
        return []
    roots = []
    active = MEDIA_ROOT / ACTIVE_LABEL
    if active.is_dir():
        roots.append(active)
    try:
        siblings = sorted(MEDIA_ROOT.iterdir())
    except OSError:
        siblings = []
    for entry in siblings:
        if entry.is_dir() and entry.name != ACTIVE_LABEL and entry.name.startswith(ACTIVE_LABEL):
            roots.append(entry)
    return roots


def _is_take_dir(path: Path) -> bool:
    try:
        return path.is_dir() and next(path.glob("*.dng"), None) is not None
    except OSError:
        return False


def _take_info(path: Path, root: Path) -> dict:
    dng_count = 0
    has_wav = False
    size_bytes = 0
    try:
        for f in path.iterdir():
            try:
                size_bytes += f.stat().st_size
            except OSError:
                continue
            if f.suffix.lower() == ".dng":
                dng_count += 1
            elif f.suffix.lower() == ".wav":
                has_wav = True
    except OSError:
        pass
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    return {
        "name": path.name,
        "storage": root.name,
        "frame_count": dng_count,
        "has_wav": has_wav,
        "size_bytes": size_bytes,
        "mtime": mtime,
    }


def list_takes() -> list[dict]:
    takes = []
    for root in _media_roots():
        try:
            entries = sorted(root.iterdir())
        except OSError as exc:
            logger.warning("Could not list %s: %s", root, exc)
            continue
        for entry in entries:
            if _is_take_dir(entry):
                takes.append(_take_info(entry, root))
    takes.sort(key=lambda t: t["mtime"] or 0, reverse=True)
    return takes


def storage_summary() -> list[dict]:
    partitions = {p.mountpoint: p for p in psutil.disk_partitions(all=True)}
    summaries = []
    for root in _media_roots():
        entry = {
            "label": root.name,
            "active": root.name == ACTIVE_LABEL,
            "total_bytes": None,
            "free_bytes": None,
            "filesystem": None,
            "device": None,
            "take_count": 0,
        }
        try:
            usage = shutil.disk_usage(root)
            entry["total_bytes"] = usage.total
            entry["free_bytes"] = usage.free
        except OSError:
            pass
        part = partitions.get(str(root))
        if part:
            entry["filesystem"] = part.fstype
            entry["device"] = part.device
        try:
            entry["take_count"] = sum(1 for e in root.iterdir() if _is_take_dir(e))
        except OSError:
            pass
        summaries.append(entry)
    return summaries


def resolve_take(name: str, *, storage: str | None = None) -> Path | None:
    """Resolve *name* (a bare take dir name, no path separators) to its
    real path under one of the known media roots. Refuses anything that
    would escape that root (path traversal) or isn't actually a take dir.
    *storage*, if given, restricts the match to that root's label (e.g.
    "RAW1") -- needed when the same take name exists on more than one
    mounted drive."""
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return None
    for root in _media_roots():
        if storage and root.name != storage:
            continue
        candidate = root / name
        try:
            if candidate.resolve().parent != root.resolve():
                continue
        except (OSError, ValueError):
            # ValueError: Path.resolve() raises "embedded null character in
            # path" on a %00-smuggled name -- previously escaped this
            # function entirely and surfaced as a 500.
            continue
        if _is_take_dir(candidate):
            return candidate
    return None


def active_take_names(redis_controller) -> set[str]:
    """Take names currently being written to, so a delete route can refuse
    them. last_dng_cam0/cam1 hold a full DNG path and are only reset to
    "None" on start_all/stop_all -- not on record stop -- so this must be
    ANDed with is_recording by the caller."""
    from module.redis_controller import ParameterKey

    names = set()
    for key in (ParameterKey.LAST_DNG_CAM0.value, ParameterKey.LAST_DNG_CAM1.value):
        value = redis_controller.get_value(key, "None")
        if not value or value == "None":
            continue
        names.add(Path(value).parent.name)
    return names


def delete_take(name: str, *, storage: str | None = None) -> tuple[bool, str]:
    path = resolve_take(name, storage=storage)
    if path is None:
        return False, f"Take '{name}' not found"
    try:
        shutil.rmtree(path)
    except OSError as exc:
        logger.exception("Failed to delete take %s", path)
        return False, str(exc)
    logger.info("Deleted take %s", path)
    return True, "Deleted"


class _StreamSink(io.RawIOBase):
    """A non-seekable in-memory sink zipfile can write into directly --
    stdlib zipfile handles a non-seekable destination itself (checked:
    ZipFile._seekable == False, testzip() clean, byte-exact output), so no
    hand-rolled zip encoder is needed to stream one."""

    def __init__(self):
        self._buf = bytearray()

    def writable(self):
        return True

    def write(self, b):
        self._buf += b
        return len(b)

    def drain(self):
        chunk = bytes(self._buf)
        self._buf.clear()
        return chunk


def stream_take_zip(path: Path):
    """Yield a zip of *path* as it is built, instead of writing a whole take
    to a temp file first (the previous build_take_zip -- a 60 s take was
    ~4 GB written to /tmp before a single byte reached the browser). DNGs are
    already stored uncompressed (dng_encoder.cpp hardcodes COMPRESSION_NONE),
    so this uses ZIP_STORED rather than spending CPU on compression that
    won't shrink anything."""
    sink = _StreamSink()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for f in sorted(path.rglob("*")):
            if not f.is_file():
                continue
            zi = zipfile.ZipInfo.from_file(f, arcname=f"{path.name}/{f.relative_to(path)}")
            zi.compress_type = zipfile.ZIP_STORED
            with zf.open(zi, "w") as dest, open(f, "rb") as src:
                while chunk := src.read(1 << 20):
                    dest.write(chunk)
                    if out := sink.drain():
                        yield out
            if out := sink.drain():
                yield out
    if out := sink.drain():
        yield out


def guarded_stream(gen, sem=DOWNLOAD_SEMAPHORE):
    """Release *sem* from inside the generator, not from a route-level
    `finally` or `@after_this_request` -- both of those run before the WSGI
    server consumes the response iterable (finalize_request precedes body
    iteration), so releasing there is a no-op for the case the semaphore
    exists to protect. Wrapping in try/finally here means a client abort
    (GeneratorExit) still frees the permit; without it, two aborts leak both
    permits and every later download 429s forever."""
    try:
        yield from gen
    finally:
        sem.release()
