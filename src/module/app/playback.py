"""Clip indexing and frame serving for the settings editor's Playback pane.

Sits between `raw_files` (which finds takes and gates every path that touches
the card) and `dng_preview` (which turns one CinemaDNG into a JPEG). This module
owns the part neither of them does: what a *clip* is, as opposed to a directory
of frames.

Deliberately does not depend on the live SSDMonitor or on Redis -- same reasoning
as `raw_files`: a take on the card is a fact on disk, and reading it should not
require the capture pipeline to be healthy. The one live fact playback does need
(whether a recording is running) is passed in by the caller rather than looked up
here, so this module stays testable off-hardware.

Two costs are worth knowing about before changing anything here:

- Building the index reads each take's *first frame only*, and only its tag
  block -- about 2 kB per take, because cinepi-raw writes the IFD at the tail
  with its offset in the header. Listing a full card is therefore cheap. Reading
  whole frames to build an index would not be.
- Listing a take's frames is a directory scan, which is not cheap for a long
  take (a ten-minute 25 fps take is 15000 entries). Scans are cached against the
  directory mtime, so scrubbing does not re-scan per frame.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from module.app import dng_preview, raw_files

logger = logging.getLogger(__name__)


def _render_token() -> str:
    """A short token that changes whenever the decoder does.

    Decoded frames are served with a long `immutable` cache lifetime, because a
    frame is a pure function of (take, index, scale, mono) and takes never
    change once written. But it is *not* a pure function of the decoder -- so
    after a cinemate update the browser would happily serve frames rendered by
    the old code for the rest of the cache lifetime. Mixing this token into the
    URL makes an updated decoder produce new URLs, which is what keeps that from
    happening without giving up the caching.
    """
    try:
        stat = Path(dng_preview.__file__).stat()
        return f"{int(stat.st_mtime):x}{stat.st_size:x}"
    except OSError:
        return "0"


RENDER_TOKEN = _render_token()

# Bound on concurrent decodes. Decoding is CPU-bound and the Pi has four cores
# that cinemate also needs; past this, requests are refused rather than queued,
# so a client that cannot keep up backs off instead of building a backlog the
# operator would experience as latency.
MAX_CONCURRENT_DECODES = 2
_decode_slots = threading.BoundedSemaphore(MAX_CONCURRENT_DECODES)

# take name -> (dir mtime, [frame filenames sorted])
_frame_cache: dict[str, tuple[float, list[str]]] = {}
_frame_cache_lock = threading.Lock()


class PlaybackError(Exception):
    """Raised when a clip or frame cannot be served."""


class Busy(PlaybackError):
    """All decode slots are in use."""


def _frame_names(take_dir: Path) -> list[str]:
    """Sorted DNG filenames in ``take_dir``, cached against the directory mtime.

    cinepi-raw numbers frames with a zero-padded 9-digit index, so a plain
    lexical sort is the capture order. Indices are *not* guaranteed contiguous:
    a dropped frame leaves a gap, which is why playback works on positions in
    this list rather than on the numbers in the filenames.
    """
    key = str(take_dir)
    try:
        mtime = take_dir.stat().st_mtime
    except OSError as exc:
        raise PlaybackError(f"take directory unreadable: {exc}") from exc

    with _frame_cache_lock:
        cached = _frame_cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]

    names = sorted(p.name for p in take_dir.glob("*.dng"))

    with _frame_cache_lock:
        _frame_cache[key] = (mtime, names)
    return names


def clip_info(name: str) -> dict:
    """Index one take: frame count plus what its first frame's tags report.

    Everything image-related comes from the DNG rather than from settings,
    because a take on the card may predate whatever the camera is configured for
    now. Returns ``{}`` if the take cannot be resolved.
    """
    take_dir = raw_files.resolve_take(name)
    if take_dir is None:
        return {}

    names = _frame_names(take_dir)
    info = {
        "name": name,
        "frame_count": len(names),
        "has_wav": any(take_dir.glob("*.wav")),
    }
    if not names:
        return info

    try:
        meta = dng_preview.read_metadata(take_dir / names[0])
    except (dng_preview.DngError, OSError) as exc:
        # A take whose first frame will not parse is still listable; it just
        # cannot be described. Say so rather than dropping it from the index.
        logger.debug("playback: cannot read tags for %s: %s", name, exc)
        info["unreadable"] = True
        return info

    hdr, encoding, label = dng_preview.describe_mode(meta)
    info.update({
        "width": int(meta.get("width", 0)),
        "height": int(meta.get("height", 0)),
        "bits": int(meta.get("bits", 0)),
        "fps": dng_preview.frame_rate(meta),
        "hdr": hdr,
        "encoding": encoding,
        "mode_label": label,
        "sensor": meta.get("model", ""),
        # Whether a take carries thumbnails is a property of the take, not of
        # a frame -- cinepi-raw's toggle cannot change mid-take -- so the HUD
        # reads it from here. The per-frame X-Frame-Source header carries the
        # same answer for anything looking at one response on its own.
        "source": frame_source(meta),
    })
    return info


def list_clips() -> list[dict]:
    """Every take on mounted storage, newest first, with its playback metadata."""
    clips = []
    for take in raw_files.list_takes():
        info = clip_info(take["name"])
        if not info:
            continue
        info.update({
            "storage": take.get("storage"),
            "size_bytes": take.get("size_bytes"),
            "mtime": take.get("mtime"),
        })
        clips.append(info)
    return clips


# How a frame reached the browser. Two paths, and an operator must never have
# to guess which one they are looking at: a 720p mono proxy and a demosaiced
# quarter-res frame are different pictures of the same take, and only one of
# them is worth judging focus on. Reported per frame, all the way to the HUD.
SOURCE_THUMBNAIL = "thumbnail"   # the embedded lores plane cinepi-raw writes
SOURCE_DECODE = "decode"         # demosaiced from the raw image


def frame_source(meta: dict) -> str:
    """Which path will serve this frame -- the one seam the decision lives in.

    Everything else in the pane is indifferent to where the pixels came from,
    so this is deliberately the only place that decides, rather than a test
    repeated down the route.

    The thumbnail side is not implemented yet: it needs cinepi-raw's Phase 0
    change (a thumbnail chained as IFD1) both landed and actually present in
    the take, and a take shot before that will never have one. Until the
    reader lands this always answers SOURCE_DECODE, which is the correct
    answer for every frame currently on any card.
    """
    if meta.get("thumbnail"):
        return SOURCE_THUMBNAIL
    return SOURCE_DECODE


def frame_jpeg(name: str, index: int, scale: int = 4, mono: bool = False,
               quality: int = 80) -> tuple[bytes, int, int, str]:
    """Serve frame ``index`` (a position, not a filename number) of a take.

    Returns ``(jpeg, width, height, source)`` where ``source`` is one of the
    ``SOURCE_*`` constants -- see ``frame_source``.

    Raises ``Busy`` when every decode slot is taken -- the caller should turn
    that into a 503 so the client drops the frame and asks for the next one,
    which is what keeps playback on the clock instead of accumulating lag.
    """
    take_dir = raw_files.resolve_take(name)
    if take_dir is None:
        raise PlaybackError("take not found")

    names = _frame_names(take_dir)
    if not names:
        raise PlaybackError("take has no frames")
    if not 0 <= index < len(names):
        raise PlaybackError(f"frame {index} outside 0..{len(names) - 1}")

    path = take_dir / names[index]
    if not _decode_slots.acquire(blocking=False):
        raise Busy("all decode slots in use")
    try:
        meta = dng_preview.read_metadata(path)
        source = frame_source(meta)
        if source == SOURCE_THUMBNAIL:      # not reachable until the reader lands
            raise PlaybackError("embedded thumbnail path is not implemented")
        data, (width, height) = dng_preview.decode_frame(
            path, meta, scale=scale, mono=mono, quality=quality)
        return data, width, height, source
    except dng_preview.DngError as exc:
        raise PlaybackError(str(exc)) from exc
    finally:
        _decode_slots.release()


def wav_path(name: str) -> Path | None:
    """The take's WAV sidecar, or None. Audio is optional on every take."""
    take_dir = raw_files.resolve_take(name)
    if take_dir is None:
        return None
    return next(iter(sorted(take_dir.glob("*.wav"))), None)
