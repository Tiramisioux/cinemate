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


def resolve_take(name: str) -> Path | None:
    """Resolve *name* (a bare take dir name, no path separators) to its
    real path under one of the known media roots. Refuses anything that
    would escape that root (path traversal) or isn't actually a take dir."""
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return None
    for root in _media_roots():
        candidate = root / name
        try:
            if candidate.resolve().parent != root.resolve():
                continue
        except OSError:
            continue
        if _is_take_dir(candidate):
            return candidate
    return None


def safe_take_children(take_dir: Path, pattern: str) -> list[Path]:
    """``take_dir.glob(pattern)``, with any entry that resolves outside
    ``take_dir`` dropped.

    resolve_take() hardens the take DIRECTORY against traversal (a
    symlinked directory name can't escape the media root), but says
    nothing about what's inside it once resolved. A symlink placed inside
    an otherwise-legitimate take directory -- *.dng or *.wav pointing at,
    say, /etc/passwd or a credentials file -- would glob and later open
    exactly like a real frame, because open() follows symlinks by
    default. Every caller that lists a take's own files for later
    reading (playback's frame/WAV serving) should go through this rather
    than take_dir.glob() directly.
    """
    try:
        real_dir = take_dir.resolve()
    except OSError:
        return []
    safe = []
    for p in take_dir.glob(pattern):
        try:
            if p.resolve().parent == real_dir:
                safe.append(p)
        except OSError:
            continue
    return safe


def delete_take(name: str) -> tuple[bool, str]:
    path = resolve_take(name)
    if path is None:
        return False, f"Take '{name}' not found"
    try:
        shutil.rmtree(path)
    except OSError as exc:
        logger.exception("Failed to delete take %s", path)
        return False, str(exc)
    logger.info("Deleted take %s", path)
    return True, "Deleted"


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
