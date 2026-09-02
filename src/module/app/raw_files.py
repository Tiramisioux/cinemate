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

import logging
import errno
import shutil
import tempfile
import zipfile
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)

MEDIA_ROOT = Path("/media")
ACTIVE_LABEL = "RAW"


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


def _candidate_paths(name: str):
    """Every path *name* could denote under a mounted media root, whether or
    not it currently looks like a take. Refuses anything that would escape
    that root (path traversal)."""
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return
    for root in _media_roots():
        candidate = root / name
        try:
            if candidate.resolve().parent != root.resolve():
                continue
        except OSError:
            continue
        yield candidate


def resolve_take(name: str) -> Path | None:
    """Resolve *name* (a bare take dir name, no path separators) to its
    real path under one of the known media roots. Refuses anything that
    would escape that root (path traversal) or isn't actually a take dir."""
    for candidate in _candidate_paths(name):
        if _is_take_dir(candidate):
            return candidate
    return None


def delete_take(name: str) -> tuple[bool, str]:
    """Delete a take. Idempotent: a take that is already gone is a success.

    Deleting is slow (thousands of unlinks) and the pane refresh behind it is
    slower still, so the row stays on screen well after the take is gone and a
    second tap is easy. Reporting "not found" there told the operator a delete
    had failed when it had in fact succeeded -- and turned one already-gone
    name in a bulk selection into "Some deletes failed".

    _candidate_paths rather than resolve_take, because a take whose *.dng
    files were already removed by a partial delete is not an _is_take_dir any
    more: it would neither list nor delete, and sat on the card forever.
    """
    path = next(iter(_candidate_paths(name)), None)
    if path is None:
        # Not a legal take name at all (traversal, separators) -- a real
        # client error, unlike a name that is simply gone.
        return False, f"Take '{name}' not found"

    for candidate in _candidate_paths(name):
        if not candidate.exists():
            continue
        try:
            shutil.rmtree(candidate)
        except OSError as exc:
            logger.exception("Failed to delete take %s", candidate)
            return False, _friendly_delete_error(exc, candidate)
        logger.info("Deleted take %s", candidate)
        return True, "Deleted"

    logger.info("Take %s was already gone", name)
    return True, "Already deleted"


def _friendly_delete_error(exc: OSError, path: Path) -> str:
    """A raw errno string is not something to put in front of an operator."""
    if exc.errno == errno.EROFS:
        return ("The card is mounted read-only, so nothing can be deleted "
                "from it. Unmount and check the filesystem, then remount.")
    if exc.errno in (errno.EACCES, errno.EPERM):
        return "No permission to delete that take from the card."
    if exc.errno == errno.EBUSY:
        return "That take is in use right now. Stop recording and try again."
    return f"Could not delete that take: {exc.strerror or exc}"


def build_take_zip(path: Path) -> Path:
    """Build a temporary zip of *path* and return its location. DNGs are
    already stored uncompressed (dng_encoder.cpp hardcodes
    COMPRESSION_NONE), so this uses ZIP_STORED rather than spending CPU on
    compression that won't shrink anything. The caller is responsible for
    deleting the returned temp file once it's been sent -- this
    necessarily doubles disk usage for the duration of one take's zip
    (build a real, well-tested archive with Python's zipfile rather than a
    hand-rolled streaming encoder, which risks silently corrupt downloads
    on a format this unforgiving)."""
    fd, tmp_path = tempfile.mkstemp(prefix="settings-editor-", suffix=".zip")
    import os
    os.close(fd)
    tmp = Path(tmp_path)
    with zipfile.ZipFile(tmp, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for f in sorted(path.rglob("*")):
            if f.is_file():
                zf.write(f, arcname=f"{path.name}/{f.relative_to(path)}")
    return tmp
