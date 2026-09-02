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
import re
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

    names = sorted(p.name for p in raw_files.safe_take_children(take_dir, "*.dng"))

    with _frame_cache_lock:
        _frame_cache[key] = (mtime, names)
    return names


# cinepi-raw's own zero-padded, 9-digit capture-sequence suffix -- e.g.
# "CINEPI_25-07-01_220547_F10_C00000_000000009.dng" (simple_gui.py's
# _format_last_dng() strips this same suffix, going the other direction).
_FRAME_INDEX_RE = re.compile(r"_(\d+)\.dng$", re.IGNORECASE)


def dropped_frame_count(take_dir: Path) -> int | None:
    """How many frames are missing from this take's own capture sequence.

    Read purely from gaps in the frame filenames' index suffix -- no
    redis, no recording-time telemetry -- matching this module's file-only
    design (a take on the card is a fact on disk, reading it should not
    need the capture pipeline to be healthy or even running). This is the
    same guarantee _frame_names()'s own docstring already relies on: a
    dropped frame leaves a gap in the numbering, which is exactly why
    playback indexes by list position rather than by the number in the
    filename. Returns None when it can't be determined (no frames, or a
    filename that doesn't match the expected suffix) -- distinct from 0
    (determined, and no frames were dropped).
    """
    names = _frame_names(take_dir)
    if not names:
        return None
    indices = []
    for name in names:
        m = _FRAME_INDEX_RE.search(name)
        if not m:
            return None
        indices.append(int(m.group(1)))
    indices.sort()
    span = indices[-1] - indices[0] + 1
    return max(0, span - len(indices))


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
        "has_wav": any(raw_files.safe_take_children(take_dir, "*.wav")),
        # From the RECORDING, not from playback's own render speed -- a
        # gap in cinepi-raw's own frame-index suffix, not whether this
        # decode session kept up. Independent of whether the take's tags
        # can even be read, so computed before the early-return below.
        "dropped_frames": dropped_frame_count(take_dir),
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

    hdr, encoding, label, display_bits, log10 = dng_preview.describe_mode(meta)
    info.update({
        "width": int(meta.get("width", 0)),
        "height": int(meta.get("height", 0)),
        # The take's ORIGINAL/source depth, not the 10-bit storage encoding
        # a log-to-10 take is compressed to -- describe_mode() only makes
        # that substitution when it's unambiguous (bits==10 with a table).
        "bits": display_bits,
        "log10": log10,
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
    """Every take on mounted storage, in SHOOTING order (oldest first), with
    its playback metadata.

    raw_files.list_takes() itself stays newest-first -- that ordering is
    right for the RAW files pane (most recent take at the top for quick
    access/deletion) and this function must not change it for that caller.
    Re-sorted here, scoped to the Playback pane only, so the take strip
    reads left-to-right in the order it was shot: first take upper-left,
    each later take to its right.
    """
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
    clips.sort(key=lambda c: c["mtime"] or 0)
    return clips


# How a frame reached the browser. Two paths, and an operator must never have
# to guess which one they are looking at: a 720p mono proxy and a demosaiced
# quarter-res frame are different pictures of the same take, and only one of
# them is worth judging focus on. Reported per frame, all the way to the HUD.
SOURCE_THUMBNAIL = "thumbnail"   # the embedded lores plane cinepi-raw writes
SOURCE_DECODE = "decode"         # demosaiced from the raw image

# Operator decision, after hardware verification: raw decode is far more
# demanding on the Pi than serving the embedded thumbnail (no demosaic, no
# LinearizationTable, no bit-unpacking) and is no longer the pane's
# fallback for a take with none. decode_frame()/_load_rows()/etc. in
# dng_preview.py are all still here, untouched, in case this is revisited
# -- flipping this one flag is the entire re-enable. frame_source() still
# answers SOURCE_DECODE for a thumbnail-less take (it is still a true
# statement about what WOULD serve it); this flag only gates whether
# frame_jpeg() actually acts on that answer or refuses instead.
_RAW_DECODE_FALLBACK_ENABLED = False


def frame_source(meta: dict) -> str:
    """Which path will serve this frame -- the one seam the decision lives in.

    Everything else in the pane is indifferent to where the pixels came from,
    so this is deliberately the only place that decides, rather than a test
    repeated down the route.

    Answers SOURCE_THUMBNAIL when dng_preview.read_metadata() found a second
    IFD chained after the raw image (cinepi-raw's embedded DNG thumbnail,
    C9 Phase 0) -- which requires both a rebuilt cinepi-raw and the toggle
    having been on when the take was recorded. Every take shot before that,
    or with the toggle off, has no second IFD and answers SOURCE_DECODE.
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
        if source == SOURCE_THUMBNAIL:
            data, (width, height) = dng_preview.decode_thumbnail(
                path, meta, quality=quality)
        elif _RAW_DECODE_FALLBACK_ENABLED:
            data, (width, height) = dng_preview.decode_frame(
                path, meta, scale=scale, mono=mono, quality=quality)
        else:
            raise PlaybackError(
                "this take has no embedded thumbnail (recorded before "
                "thumbnail=1/2 was set, or on cinepi-raw without Phase 0) "
                "-- raw playback is currently disabled")
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
    return next(iter(sorted(raw_files.safe_take_children(take_dir, "*.wav"))), None)
