import os
import signal
import subprocess
import re
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

from module import rp1_regime
from module.sensor_database import load_sensor_database
from module.aspect_ratios import (
    FULL_FRAME_RATIO_ID,
    NATIVE_RATIO_PREFIX,
    PREFERRED_DELIVERY_RATIO_ID,
    PREFERRED_SHAPE_RATIO_ID,
    load_aspect_ratio_table,
)
from module import sensor_settings

# The state boundary cinepi-raw prints between the SDR listing and the
# ClearHDR listing of the same cameras. It appears on EVERY
# --list-cameras run of a build that knows the sensor has ClearHDR, with
# or without --hdr sensor (cinepi-raw core/options.cpp, print_modes):
# the plain probe therefore contains the ClearHDR state too, and reads
# only what comes before this line.
CLEAR_HDR_MARKER_RE = re.compile(
    r"CLEAR\s+HDR\s*/\s*SENSOR\s+HDR", re.IGNORECASE,
)

DEFAULT_SENSOR_DATABASE_FILE = "resources/sensors.json"
# image_capture.min_mode_width's own default: modes narrower than this are
# hidden (not removed) from the dial/GUIs unless an enabled_modes entry names
# them.
DEFAULT_MIN_MODE_WIDTH = 1280
# How close a mode's real aspect has to be to a ratio's value to count as
# that ratio "exact" rather than merely the closest available shape.
ASPECT_RATIO_TOLERANCE = 0.02
# WP-CM-11: a floating-point noise guard on every `err <= ASPECT_RATIO_TOLERANCE`
# comparison below. _mode_aspect() and _nearest_ratio_id() round to 2 decimal
# places, so a mode can land a real, exact 0.02 away from a ratio's value --
# imx477's shipped 2028x1080 (aspect 1.87) is 0.019999999999999796 from
# "1.89:1" in resources/sensors.json today, and this package's own synthetic
# 1332x990 fixture (aspect 1.35, nearest "1.33:1") lands on the other side,
# 0.020000000000000018. Which side of exactly 0.02 a given pair of floats
# lands on is not something either the derived default's "covers every mode
# by construction" guarantee (_derived_default_ratio_ids) or an operator's
# own explicit choice can depend on.
_ASPECT_TOLERANCE_EPS = 1e-9
FALLBACK_PACKING_INFO = {
    "imx296": "U",
    "imx283": "U",
    "imx477": "U",
    "imx519": "P",
    "imx585": "U",
    "imx585_mono": "U",
}

# Raspberry Pi models that run the VC4/Unicam camera receiver. On these the
# packed CSI2 modes are preferred (lower DMA/CMA than unpacked). This is the
# single canonical platform check; cinepi_multi and cinepi_controller both reach
# it through SensorDetect so the launch command and the GUI/telemetry agree.
PI4_MODEL_MARKERS = (
    "Raspberry Pi 4",
    "Raspberry Pi 400",
    "Compute Module 4",
)

# Raspberry Pi models that run the RP1 camera receiver. "Compute Module 5" is
# the marker that matters in practice -- CineMate's own dev unit is a CM5, and
# /proc/device-tree/model reports it as "Raspberry Pi Compute Module 5", which
# does not contain the string "Raspberry Pi 5".
PI5_MODEL_MARKERS = (
    "Raspberry Pi 5",
    "Raspberry Pi 500",
    "Compute Module 5",
)

# DNG frame-size model, calibrated against real captures (imx585 3856x2180
# linear/log at 10/12/16-bit -- see innomaker585/pi-2026-08-05-goodkernel/).
# cinepi-raw packs pixel data tightly at N bits/row ((width*bits+7)//8 bytes),
# so pixel_bytes scales exactly with the *effective* bit depth (the live
# --log-encode target when active, else the sensor mode's native depth).
# The remaining per-frame overhead (DNG header/tags, plus a LinearizationTable
# on log-encoded frames) is <0.07% of frame size across every measured case,
# so one flat constant is used rather than modelling it exactly -- true only
# once the embedded thumbnail's own bytes are included via thumbnail_bytes
# below. Without that term this model silently under-counts: by +1.4% to
# +5.6% at the shipped colour/shift-2 default, and by +22% to +89% at the
# full-lores colour size CineMate 3.4 actually shipped with before this fix
# -- which is exactly what made file_size and the GUI's minutes-remaining
# wrong (FINDINGS.md and the 2026-09-13 hardware-log entry,
# development/dng-thumbnail-cost/).
DNG_HEADER_OVERHEAD_BYTES = 1024
# cinepi-raw writes DNGs uncompressed (COMPRESSION_NONE is hardcoded in
# dng_encoder.cpp; the vendored lj92 lossless codec is dead code) -- this is
# the seam to update once that changes, so the minutes-left math doesn't need
# a redesign when it does.
DNG_COMPRESSION_RATIO = 1.0


# Colour-JPEG (mode 3) per-frame ESTIMATE, not the exact formula the other
# three modes have: a JPEG's actual size depends on scene content, and is
# unknowable here the same way it is unknowable to cinepi-raw's own
# dng_thumbnail.hpp before libjpeg has actually encoded a given frame (see
# that header's ThumbGeometry::compressed comment -- its own JPEG number is
# a RESERVATION, the uncompressed worst case, deliberately different from
# this estimate). Measured 0.04-0.08 B/px at quality 85 across three
# ordinary takes (FINDINGS.md §2b, development/dng-thumbnail-cost/);
# detailed or noisy scenes compressed two to three times worse there. 0.15
# is deliberately ABOVE that measured range: this feeds compute_frame_size_mb()
# and, through it, the GUI's minutes-remaining figure, and an under-estimate
# here would tell an operator they have more card space left than they
# really do -- the one direction that figure must never be wrong in. Named
# once so every reader of file_size math sees the same number and the same
# reasoning; see thumbnail_choice_labels() below for the DIFFERENT (and
# lower, since it is describing typical size rather than budgeting worst
# case) range shown to an operator choosing a mode in the settings editor.
THUMBNAIL_JPEG_BUDGET_BYTES_PER_PIXEL = 0.15


def thumbnail_plane_bytes(lores_w: int, lores_h: int, mode: int, shift: int) -> int:
    """Bytes the embedded DNG thumbnail (IFD1) adds to one frame.

    Mirrors cinepi/dng_thumbnail.hpp's thumbnail_geometry(): same formula,
    kept here only because cinemate's file_size / minutes-remaining
    estimate has no C++ to call into. That header is the authority for
    this number; this is the mirror. tests/dng_thumbnail_test.cpp and
    _test/test_frame_size_model.py pin the same cases on both sides, so a
    change to one formula that is not made to the other shows up as the
    two test files disagreeing, not as a silent drift in file_size.

    NOTE the argument order: (lores_w, lores_h, mode, shift) here, versus
    thumbnail_geometry()'s (lores_w, lores_h, shift, mode) on the C++ side
    -- mode and shift are swapped. Read the parameter names, not the
    position, when calling either one.

    mode: 0 off, 1 mono (1 byte/pixel), 2 colour (3 bytes/pixel), 3 colour
    JPEG -- THUMBNAIL_JPEG_BUDGET_BYTES_PER_PIXEL per pixel, a conservative
    ESTIMATE (see that constant's own comment), not the uncompressed spp
    formula the other three modes use and not the same number as
    cinepi-raw's own JPEG reservation in dng_thumbnail.hpp.
    shift: right-shift applied to each lores dimension, 0..12 (cinepi-raw's
    own clamp; see thumbnail_size_startup_value() in config_loader.py for
    cinemate's own, tighter 0..4). Returns 0 when mode is 0; width/height
    are not returned here -- nothing on this side needs them the way
    cinepi-raw's dng_thumbnail.hpp does for its own log line.
    """
    width = max(1, lores_w >> shift)
    height = max(1, lores_h >> shift)
    if mode == 0:
        return 0
    if mode == 3:
        return int(width * height * THUMBNAIL_JPEG_BUDGET_BYTES_PER_PIXEL)
    spp = 3 if mode == 2 else 1
    return width * height * spp


def _format_thumbnail_kb(n_bytes: int) -> str:
    """n_bytes as whole decimal KB for a settings-editor label, e.g. the
    mono default at 640x360 (230,400 B) -> "230 KB"."""
    return f"{round(n_bytes / 1000):,} KB"


# Colour-JPEG label range, keyed by thumbnail_size (shift) -- the settings
# editor's size dropdown only ever offers 0/1/2 (Full lores / Half / Quarter,
# item 6), so these are the three sizes an operator can actually choose,
# and each is a MEASURED range (FINDINGS.md §2b's own re-encodes; shift 0's
# is FINDINGS.md §1's full-lores figure), cited here rather than re-derived
# from a formula -- the ground rule for how measured numbers travel into
# docs/labels. Wider than FINDINGS.md's narrowest per-take figures on
# purpose, matching that section's own "detailed or noisy scenes compress
# two to three times worse" caveat: a label should not undersell how big a
# demanding scene's thumbnail can get.
_THUMBNAIL_JPEG_LABEL_RANGE_KB = {
    0: (64, 76),    # full lores (~1280x720), FINDINGS.md §1 / §2b
    1: (10, 25),    # half (~640x360)
    2: (3, 8),      # quarter (~320x180)
}


# Measured per-frame encode cost of each thumbnail mode, as (ms, percent over
# a take with no thumbnail at all), keyed by mode and then by shift. From the
# 2026-09-13 hardware benchmark (the entry in cinemate-handbook's hardware log):
# imx585 4K 16-bit ClearHDR with CineMate Log 12 at 25 fps, 250+ frames per
# cell, against a 22.2 ms no-thumbnail baseline. The noise floor that session
# measured -- two identical "off" takes three minutes apart -- was 0.09 ms, so
# every figure here is real rather than scatter.
#
# One configuration, and the labels say so: on a log-encoded frame the LUT pass
# dominates dng_save(), so the thumbnail's share is smaller than it would be on
# a plain linear take, and smaller again than at HD where the raw frame is far
# cheaper to encode. Treat these as "what it cost on the mode this camera
# actually shoots", not as a universal constant -- which is exactly why the
# figure is written down once, here, instead of being restated in the settings
# page, the docs and the schema.
#
# Shift 0 is absent on purpose: it was not measured. Its labels fall back to
# the nearest measured shift rather than extrapolating a number nobody has seen.
_THUMBNAIL_CPU_MS = {
    1: {1: (1.25, 5.6), 2: (0.66, 3.0)},    # mono
    2: {1: (3.22, 14.5), 2: (1.10, 5.0)},   # colour
    3: {1: (4.02, 18.1), 2: (1.26, 5.7)},   # jpeg
}


def _thumbnail_cpu_phrase(mode: int, shift: int) -> str:
    """The measured encode-time cost of *mode* at *shift*, as label prose.

    Falls back to the nearest measured shift when the exact one has no
    measurement (shift 0, and anything past 2), and says "about" in that case
    rather than quoting a number as if it had been observed at that size.
    """
    by_shift = _THUMBNAIL_CPU_MS.get(mode)
    if not by_shift:
        return "no CPU"
    exact = by_shift.get(shift)
    if exact is not None:
        ms, pct = exact
        return f"+{ms:.1f} ms per frame (+{pct:.0f}%)"
    nearest = min(by_shift, key=lambda k: abs(k - shift))
    ms, pct = by_shift[nearest]
    return f"about +{ms:.1f} ms per frame (+{pct:.0f}%) at the nearest measured size"


def _thumbnail_jpeg_label_range_kb(width: int, height: int, shift: int) -> tuple[int, int]:
    """(low, high) whole-KB range for the JPEG choice's label at this size.

    Uses the measured table above for the three shifts the settings editor
    actually offers; falls back to scaling FINDINGS.md §2b's own stated
    0.04-0.08 B/px range by actual pixel count for any other shift, so this
    stays a total function over the same domain thumbnail_plane_bytes()
    accepts even though nothing in this codebase currently asks for a
    shift outside 0-2 here.
    """
    if shift in _THUMBNAIL_JPEG_LABEL_RANGE_KB:
        return _THUMBNAIL_JPEG_LABEL_RANGE_KB[shift]
    pixels = width * height
    low_rate, high_rate = 0.04, 0.08
    return (
        max(1, round(pixels * low_rate / 1000)),
        max(1, round(pixels * high_rate / 1000)),
    )


def thumbnail_choice_labels(lores_w: int, lores_h: int, shift: int) -> list[tuple[str, str]]:
    """(value, label) for the four `image_capture.thumbnail` choices, sized
    and costed for the CURRENT camera's lores plane and the CURRENT
    thumbnail_size -- what the settings editor's mode dropdown renders, so
    an operator picks with the bytes-per-frame and CPU cost in front of
    them instead of a bare word. Order matches THUMBNAIL_MODE_NAMES
    (config_loader.py): off, mono, colour, jpeg.

    Bytes for mono/colour come from thumbnail_plane_bytes() -- the same
    formula file_size uses, so the label can never disagree with what a
    take actually costs. JPEG's is a measured RANGE
    (_thumbnail_jpeg_label_range_kb()), not thumbnail_plane_bytes()'s own
    conservative budget estimate for mode 3 -- that budget is deliberately
    pessimistic for minutes-remaining math, which is not what an operator
    asking "how big will this actually be" should be shown.
    """
    width = max(1, lores_w >> shift)
    height = max(1, lores_h >> shift)
    dims = f"{width}×{height}"

    mono_bytes = thumbnail_plane_bytes(lores_w, lores_h, 1, shift)
    colour_bytes = thumbnail_plane_bytes(lores_w, lores_h, 2, shift)
    jpeg_low_kb, jpeg_high_kb = _thumbnail_jpeg_label_range_kb(width, height, shift)

    return [
        ("off", "Off — 0 B per frame, no extra encode time; takes are not playable "
                "in the Playback pane"),
        ("mono", f"Greyscale {dims} — {_format_thumbnail_kb(mono_bytes)} per frame, "
                 f"{_thumbnail_cpu_phrase(1, shift)}"),
        ("colour", f"Colour {dims} — {_format_thumbnail_kb(colour_bytes)} per frame, "
                   f"{_thumbnail_cpu_phrase(2, shift)}"),
        ("jpeg", f"Colour JPEG {dims} — about {jpeg_low_kb}–{jpeg_high_kb} KB per frame "
                 f"(varies by scene), {_thumbnail_cpu_phrase(3, shift)}"),
    ]


def compute_frame_size_mb(width: int, height: int, bit_depth: int,
                           compression_ratio: float = DNG_COMPRESSION_RATIO,
                           thumbnail_bytes: int = 0) -> float:
    """DNG frame size in decimal MB for a *bit_depth*-packed frame of *width*
    x *height*, plus the embedded thumbnail's own bytes, if any.

    thumbnail_bytes defaults to 0 for callers with no live thumbnail state
    to hand it (SensorDetect's own per-mode metadata below, built before
    any take exists and therefore before a mode/shift is known) -- see
    thumbnail_plane_bytes() for how a caller that DOES know the live
    thumbnail/thumbnail_size keys computes this term.
    See DNG_HEADER_OVERHEAD_BYTES/DNG_COMPRESSION_RATIO above."""
    row_bytes = (int(width) * int(bit_depth) + 7) // 8
    pixel_bytes = row_bytes * int(height) + int(thumbnail_bytes)
    return round((pixel_bytes + DNG_HEADER_OVERHEAD_BYTES) / compression_ratio / 1_000_000, 2)


def active_picture_size(mode: dict, fallback_width, fallback_height) -> tuple[float, float]:
    """The best-known size of *mode*'s delivered active picture -- the
    optical-black-excluded image a DNG or a preview frame actually shows,
    as opposed to the padded transport frame cinepi-raw allocates for it.

    Round 2, Defect D/B2. This is the ONE place that arithmetic lives; every
    caller that used to compute its own aspect or active size from crop/
    binning (sensor_detect._mode_from_metadata_or_detected,
    compute_preview_geometry, settings_editor._active_dimension) now calls
    this instead, so a future evidence source (tier 1 below) only has to be
    taught once.

    Three tiers, best evidence first, never interpolated or invented:

    1. ``active_width``/``active_height`` -- an explicit annotation of the
       delivered active picture, when cinepi-raw's ``--list-cameras`` reports
       one (see _parse_cinepi_output's "active" annotation parsing). This is
       the only tier that is exactly right at any binning, because it
       already IS the delivered picture -- no arithmetic needed.
    2. ``crop_width``/``crop_height`` divided by ``binning_x``/``binning_y``
       -- an approximation. WP-CM-10's domain contract: crop_* is the
       sensor-side readout window, in NATIVE sensor coordinates, at any
       binning. Dividing by the binning factor reaches the recorded picture
       size, but can still differ from the true active picture by a few
       pixels when the transport buffer is itself padded beyond it (a RAW16
       ClearHDR mode) -- exactly why tier 1 exists.
    3. ``crop_width``/``crop_height`` divided by an INFERRED binning factor,
       when binning is not reported but crop/fallback lands within 0.01 of
       the same integer n >= 1 in both dimensions (PLAN.md D1, 2026-09-28) --
       else ``crop_width``/``crop_height`` alone. The plain-crop fallback is
       only ratio-correct when binning_x == binning_y (this was Defect B2 --
       the sensor-WINDOW aspect standing in for the picture aspect) and, for
       a binned mode reported with no binning annotation at all, is
       positively misleading: it relabels the mode with its sensor-domain
       window size, identical to whatever OTHER mode reads that same window
       unbinned. That is exactly the operator report this package fixes --
       imx477's binned 2028x1080 mode, reported with crop 4056x2160 and no
       binning, showed in the settings pane as "4056x2160", indistinguishable
       from the real 4056x2160 mode. The inferred factor is never written
       back into binning_x/binning_y: it is evidence good enough for THIS
       calculation, not a fact this module is in a position to assert about
       the driver.
    4. *fallback_width*/*fallback_height* -- the transport frame. Provably
       wrong whenever the transport carries optical-black padding rows or
       columns (Defect D's 1.02:1 for a 1:1 mode is exactly this), but the
       only thing left when the driver reports no geometry at all -- a stock
       sensor (imx477, imx296), or a cinepi-raw build that predates the crop
       annotation.

    Returns floats; a caller wanting whole pixels rounds itself. Never
    averages tiers or fills a partial one -- an incomplete tier is skipped
    outright, exactly like every other geometry field in this module.
    """
    aw, ah = mode.get("active_width"), mode.get("active_height")
    if aw and ah:
        return float(aw), float(ah)

    cw, ch = mode.get("crop_width"), mode.get("crop_height")
    if cw and ch:
        bx, by = mode.get("binning_x"), mode.get("binning_y")
        if (
            isinstance(bx, (int, float)) and bx > 0
            and isinstance(by, (int, float)) and by > 0
        ):
            return float(cw) / bx, float(ch) / by

        fw, fh = float(fallback_width), float(fallback_height)
        if fw > 0 and fh > 0:
            nx, ny = float(cw) / fw, float(ch) / fh
            n = round(nx)
            if n >= 1 and abs(nx - n) <= 0.01 and abs(ny - n) <= 0.01:
                return float(cw) / n, float(ch) / n
        return float(cw), float(ch)

    return float(fallback_width), float(fallback_height)


# Preview canvas defaults, shared with simple_gui.py's own
# PREVIEW_PADDING_X/Y (94/50) and cinepi_multi.py's inline px, py = 94, 50.
PREVIEW_TARGET_LINES = 720
PREVIEW_PADDING_X = 94
PREVIEW_PADDING_Y = 50


def compute_preview_geometry(
    mode: dict,
    canvas_width: int,
    canvas_height: int,
    anamorphic_factor: float = 1.0,
    *,
    target_lines: int = PREVIEW_TARGET_LINES,
    padding_x: int = PREVIEW_PADDING_X,
    padding_y: int = PREVIEW_PADDING_Y,
) -> dict:
    """Shared geometry for the live preview: the lores stream size cinepi-raw
    is launched with (--lores-width/--lores-height) and the `-p` window that
    places the preview on the canvas.

    WP-CM-1 (findings C3, M2). *mode* is a resolution-info dict shaped like
    get_resolution_info()'s return value -- 'width'/'height' are the
    transport frame (a RAW16 mode's optical-black padding included) and
    'crop_width'/'crop_height' (and, when the driver reports it, the exact
    'active_width'/'active_height') describe the driver-reported active
    image. This one helper replaces three previously separate, drifting
    copies of the same arithmetic: SensorDetect's own lores getters,
    CinePiProcess._build_args() and simple_gui._calculate_preview_guide_rect().

    Aspect comes from active_picture_size() -- the delivered active picture,
    never the padded transport size, which used to stretch a ClearHDR
    preview and include the optical-black rows (M2). Round 2 (Defect B2)
    tightened this further: the sensor-WINDOW aspect (raw crop_width/
    crop_height) is only accidentally equal to the delivered picture's own
    aspect, and silently drifts from it whenever binning_x != binning_y --
    that drift, not a pillarbox from a real aspect mismatch, is what put a
    1-2px sliver on both preview edges. active_picture_size() divides by
    binning before taking the ratio, so the -p window, the lores request and
    the buffer this function sizes all agree with the same delivered shape.
    Absent any crop annotation (a stock sensor -- see the campaign's DEC-4:
    no annotation means *unknown*, never *full frame*) this still falls back
    to the mode's own width/height, exactly as every caller already did.

    ASSUMPTION (Defect B2, stated explicitly per the brief): this function
    only fixes the REQUESTED aspect -- the -p window and the lores size
    cinepi-raw is launched with. It assumes the ISP's ScalerCrop is, or will
    be, set to the active rectangle by cinepi-raw itself (a parallel worker's
    job, ROUND2.md "The fix, and why ScalerCrop rather than the DRM source
    rect"); this function does not touch ScalerCrop and never will. If that
    ISP crop is NOT yet in place, the lores buffer's actual content still
    carries the optical-black band this function cannot see or remove --
    only its outer aspect. Once the ISP crop lands, the buffer's real content
    matches the aspect requested here exactly, with no double-correction: no
    factor here is scaled by whether the ISP crop is active, so there is
    nothing to double up.

    Both outputs are clamped to *mode*'s own width/height, not just to the
    padded canvas: a mode shorter than 720 rows (e.g. a small imx585 crop
    window) used to get a taller/wider lores request than the mode itself
    delivers, and cinepi-raw's ConfigureVideo throws
    "Low res image larger than raw image" (C3).

    Returns unrounded values (no even-alignment) -- that stays each caller's
    own choice, because simple_gui._calculate_preview_guide_rect() must
    match DrmPreview::Show()'s own unrounded fit exactly.

    Round 3 (operator issue 4, "anamorphic fills the web UI but not HDMI"):
    the `-p` window used to be sized from the un-desqueezed *aspect* while
    the lores buffer it frames was already desqueezed
    (lores_w = lores_h * aspect * anamorphic_factor). DrmPreview::Show()
    fits that buffer into the window by preserving the BUFFER's aspect, so
    a too-narrow-for-its-height window doesn't crop or stretch anything --
    it just leaves the window under-filled on whichever axis the buffer
    turned out wider than the window's own shape assumed, which reads as a
    letterboxed picture that never reaches the edges of the padded canvas.
    Sizing the window from the same desqueezed aspect the buffer already
    carries removes that daylight: the window's own shape now matches the
    buffer's, so Show()'s fit has (at most, from int rounding) a pixel or
    two of slack rather than a deliberate margin. Both blocks below now
    share one `desqueezed_aspect` instead of one using `aspect` and the
    other `aspect * anamorphic_factor` for what is meant to be the same
    quantity -- the C3 clamp branch was the easiest place for those two to
    silently drift apart again, since it recomputes lores_h from whichever
    divisor it's handed.
    """
    width = mode.get('width') or canvas_width
    height = mode.get('height') or canvas_height
    active_width, active_height = active_picture_size(mode, width, height)
    aspect = (active_width / active_height) if active_height else 1.0
    desqueezed_aspect = aspect * anamorphic_factor

    aw = canvas_width - 2 * padding_x
    ah = canvas_height - 2 * padding_y

    # -p preview window: desqueezed aspect -- the same shape the lores
    # buffer below is actually requested at -- centred in the padded canvas
    # area. Using the un-desqueezed `aspect` here (pre-Round-3) left the
    # window narrower or shorter than the buffer DrmPreview::Show() fits
    # into it, so the picture never reached the padded canvas's own edges.
    if ah and (aw / ah) > desqueezed_aspect:
        preview_h = ah
        preview_w = int(preview_h * desqueezed_aspect)
    else:
        preview_w = aw
        preview_h = int(preview_w / desqueezed_aspect) if desqueezed_aspect else ah
    preview_x = (canvas_width - preview_w) // 2
    preview_y = (canvas_height - preview_h) // 2

    # Lores stream: target `target_lines`, clamped to the padded canvas AND
    # to the mode's own delivered size -- the fix for C3.
    lores_h = min(target_lines, ah, height)
    lores_w = int(lores_h * desqueezed_aspect)
    max_lores_w = min(aw, width)
    if lores_w > max_lores_w:
        lores_w = max_lores_w
        lores_h = int(round(lores_w / desqueezed_aspect)) if desqueezed_aspect else lores_h

    return {
        "lores_width": lores_w,
        "lores_height": lores_h,
        "preview_x": preview_x,
        "preview_y": preview_y,
        "preview_width": preview_w,
        "preview_height": preview_h,
    }


def read_pi_model() -> str:
    try:
        with open("/proc/device-tree/model", "r") as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return ""


def is_pi4_family() -> bool:
    """True on any Raspberry Pi 4 / 400 / CM4 (VC4/Unicam) platform."""
    model = read_pi_model()
    return any(marker in model for marker in PI4_MODEL_MARKERS)


def is_pi5_family() -> bool:
    """True on any Raspberry Pi 5 / 500 / CM5 (RP1) platform."""
    model = read_pi_model()
    return any(marker in model for marker in PI5_MODEL_MARKERS)


def pi_family() -> str:
    """Coarse platform family: 'pi5', 'pi4', 'other', or 'unknown'.

    Matching is by family marker, not by the exact board name, because the
    boards CineMate actually ships on are Compute Modules: a CM5 reports
    "Raspberry Pi Compute Module 5 Rev 1.0", which contains neither
    "Raspberry Pi 5" nor "Raspberry Pi 4". Substring checks against the
    consumer board names alone therefore classify every CM as 'other' and send
    Pi-5-only code down the legacy path.
    """
    model = read_pi_model()
    if not model:
        return "unknown"
    if any(marker in model for marker in PI5_MODEL_MARKERS):
        return "pi5"
    if any(marker in model for marker in PI4_MODEL_MARKERS):
        return "pi4"
    return "other"


class SensorDetect:
    def __init__(self, settings=None, settings_dir=None):
        self.camera_model = None
        self.res_modes = {}
        self.settings = settings or {}
        # Per-sensor settings.py file layer (settings_<camera>.jsonc):
        # None disables it entirely, leaving legacy/stock resolution only --
        # this keeps every existing unit test hermetic, since a test built
        # with SensorDetect(settings) and no settings_dir must never read a
        # real /home/pi/cinemate/settings_*.jsonc just because one happens to
        # exist on the machine running the suite. main.py passes
        # Path(SETTINGS_FILE).parent -- the same directory settings.jsonc
        # itself lives in and the settings editor already writes into.
        self.settings_dir = settings_dir
        # cam -> "file" | "legacy" | "stock", set once per camera inside
        # _finalize_modes by resolve_sensor_settings(). Read by the
        # settings-editor endpoint's per-camera `source` field.
        self.sensor_settings_source: Dict[str, str] = {}
        # cam -> [ratio ids], the saved-but-not-offered ids _finalize_modes
        # dropped for that camera. Read by the settings-editor endpoint's
        # per-camera `dropped` field. See dropped_ratio_ids().
        self.sensor_settings_dropped: Dict[str, List[str]] = {}
        res_cfg = self.settings.get("image_capture", {})
        self.k_steps = res_cfg.get("k_steps", [])
        self.bit_depths = res_cfg.get("bit_depths", [])
        self.custom_modes = res_cfg.get("custom_modes", {})
        # Per-mode operator selection. An absent camera entry preserves the
        # legacy k_steps/bit_depths filters for backward compatibility.
        self.enabled_modes = res_cfg.get("enabled_modes", {})
        # WP-CM-6: per-camera aspect-ratio selection, keyed exactly as
        # enabled_modes is keyed above. Availability -- which ratios a camera
        # can actually produce -- is derived at startup from the mode table
        # (see available_aspect_ratios()), never stored here: it depends on
        # the driver installed right now, and a cached answer would outlive
        # it. An enabled_modes entry for the camera is still authoritative
        # and skips this filter outright, same as it already skips
        # k_steps/bit_depths above.
        #
        # A camera with no entry of its own falls to the STOCK rule
        # (_default_ratio_ids), computed fresh from this camera's own modes
        # -- never to a "default" entry (PLAN.md D2, 2026-09-28): a settings.
        # jsonc left with a stray global "default" key from before per-sensor
        # settings files existed is exactly the cross-sensor carrier that let
        # an imx585 ratio choice silently narrow an imx477 after a swap. See
        # _enabled_ratio_ids()/legacy_sensor_settings() -- a bare "default"
        # entry is surfaced as a one-time warning notice in _finalize_modes,
        # never read as a value, at any precedence level.
        #
        # _finalize_modes() overwrites this dict's per-camera entries in
        # place with whatever sensor_settings.resolve_sensor_settings() finds
        # for that camera (a per-sensor file beats this legacy value, which
        # is otherwise used as-is) -- see its own "resolve per-sensor
        # settings" section.
        self.aspect_ratios_cfg = res_cfg.get("aspect_ratios") or {}
        # Modes narrower than this are hidden (not removed -- they stay in
        # sensor_modes_unfiltered) from the dial/GUIs by default. An
        # enabled_modes entry bypasses this floor too: an explicit choice
        # beats a default. Same "no default here" reasoning as
        # aspect_ratios_cfg above -- an absent key must not turn the floor
        # on for a settings.jsonc that predates it; a falsy floor is a
        # no-op in _finalize_modes()'s `if floor:` check either way.
        self.min_mode_width = res_cfg.get("min_mode_width")
        # The canonical ratio table (id, exact value, common name) -- one
        # file, read here and, from WP-CM-7, by the settings page. See
        # module.aspect_ratios.
        self.aspect_ratio_table = load_aspect_ratio_table()
        # Optional ClearHDR (imx585) whitelist. settings.jsonc → resolutions.hdr
        # is {"sdr": bool, "imx585_clear_hdr": bool}; both true (default)
        # exposes plain and ClearHDR modes, turn a flag off to hide that class
        # of modes. Mirrors the bit_depths / k_steps whitelists above.
        self.hdr_modes = self._hdr_whitelist(res_cfg.get("hdr", {}))
        # Which ClearHDR bit depths are offered, decided separately from the
        # SDR/ClearHDR class above. image_capture.bit_depths cannot express
        # this: it is global, so switching 12 off there to drop 12-bit
        # ClearHDR would take the 12-bit SDR modes with it.
        #
        # These two switches are the whole ClearHDR answer: they say which
        # ClearHDR *captures* exist, and image_capture.k_steps then says which
        # frame sizes of them are offered, exactly as it does for SDR. There
        # used to be a third switch, imx585_clear_hdr_16bit_hd, adding the
        # binned 16-bit mode on its own -- it gated every binned ClearHDR mode
        # regardless of depth, so turning it on for 16-bit HD also handed back
        # 12-bit HD. Dropped 2026-09-15; drop 2K from k_steps to lose the
        # binned modes instead.
        self.clear_hdr_depths = self._clear_hdr_depths(res_cfg.get("hdr", {}))
        sensor_cfg = self.settings.get("sensors", {})
        self.sensor_database_file = sensor_cfg.get(
            "database_file",
            DEFAULT_SENSOR_DATABASE_FILE,
        )
        self.sensor_database = self._load_sensor_database()
        # Detected resolutions per camera will be stored here
        self.sensor_resolutions = {}
        # cam -> {"kind": str, "text": str} whenever _finalize_modes had to
        # offer something other than what the operator's own settings asked
        # for. Empty when every camera's selection resolved cleanly.
        self.mode_selection_notices: Dict[str, Dict[str, str]] = {}
        # Pre-filter counterpart of the above; see _finalize_modes().
        self.sensor_modes_unfiltered: Dict[str, List[Dict]] = {}

        # Packing information per sensor (U = unpacked, P = packed).
        self.packing_info = self._packing_info_from_database()

        # Populate camera model and modes on startup
        self.detect_camera_model()

    def _resolve_repo_path(self, path_value: str) -> Path:
        path = Path(path_value or DEFAULT_SENSOR_DATABASE_FILE)
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parents[2] / path

    def _load_sensor_database(self) -> dict[str, Any]:
        # Delegates to module.sensor_database, which boot_config also uses --
        # two loaders would mean two sets of fallback rules to keep in step,
        # which is the drift this database exists to prevent.
        return load_sensor_database(str(self._resolve_repo_path(self.sensor_database_file)))

    def _packing_info_from_database(self) -> dict[str, str]:
        packing = dict(FALLBACK_PACKING_INFO)
        for sensor_id, sensor_info in self.sensor_database.get("sensors", {}).items():
            if not isinstance(sensor_info, dict):
                continue
            sensor_packing = sensor_info.get("packing")
            if not sensor_packing:
                continue
            sensor_key = str(sensor_id).strip().lower()
            packing[sensor_key] = str(sensor_packing)
            for alias in sensor_info.get("aliases", []) or []:
                packing[str(alias).strip().lower()] = str(sensor_packing)
        return packing

    def _sensor_database_entry(self, camera_name: str | None) -> dict[str, Any] | None:
        camera_key = str(camera_name or "").strip().lower()
        if not camera_key:
            return None

        sensors = self.sensor_database.get("sensors", {})
        direct = sensors.get(camera_key)
        if isinstance(direct, dict):
            return direct

        base_key = camera_key[:-5] if camera_key.endswith("_mono") else camera_key
        direct = sensors.get(base_key)
        if isinstance(direct, dict):
            return direct

        for sensor_info in sensors.values():
            if not isinstance(sensor_info, dict):
                continue
            aliases = {
                str(alias).strip().lower()
                for alias in sensor_info.get("aliases", []) or []
            }
            if camera_key in aliases:
                return sensor_info
        return None

    def _sensor_mode_metadata(
        self,
        camera_name: str | None,
        width: int,
        height: int,
        bit_depth: int | None,
    ) -> dict[str, Any]:
        sensor_info = self._sensor_database_entry(camera_name)
        if not sensor_info:
            return {}

        for mode_info in sensor_info.get("modes", []) or []:
            if not isinstance(mode_info, dict):
                continue
            if int(mode_info.get("width", 0) or 0) != int(width):
                continue
            if int(mode_info.get("height", 0) or 0) != int(height):
                continue
            mode_bit_depth = mode_info.get("bit_depth")
            if (
                bit_depth is not None
                and mode_bit_depth is not None
                and int(mode_bit_depth) != int(bit_depth)
            ):
                continue
            return mode_info
        return {}

    def _mode_from_metadata_or_detected(
        self,
        *,
        camera_name: str,
        width: int,
        height: int,
        bit_depth: int | None,
        fps_max: int | None,
        hdr: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = self._sensor_mode_metadata(camera_name, width, height, bit_depth)
        sensor_info = self._sensor_database_entry(camera_name) or {}
        extra = extra or {}
        packing = (
            extra.get("packing")
            or metadata.get("packing")
            or sensor_info.get("packing")
            or self.packing_info.get(camera_name, "U")
        )
        # Always computed from the packed-bytes model (compute_frame_size_mb).
        # sensors.json no longer carries a static file_size_mb -- it doesn't
        # know about --log-encode, which is a runtime toggle applied
        # dynamically in cinepi_controller instead.
        file_size = compute_frame_size_mb(width, height, bit_depth) if bit_depth else None
        fps_max_value = fps_max if fps_max is not None else extra.get("fps_max", metadata.get("max_fps"))
        binning_x = extra.get("binning_x", metadata.get("binning_x"))
        binning_y = extra.get("binning_y", metadata.get("binning_y"))
        # Aspect ratio is an image property, not a transport-frame property.
        # In particular, IMX585 ClearHDR RAW16 modes include optical-black
        # rows (e.g. 3840x2200 carrying a 3840x2160 active image), and some
        # modes have binned/cropped transport geometry. The settings table
        # must therefore use the reported active picture whenever geometry
        # is known, and never the raw sensor-side crop on its own: that
        # ratio only coincides with the active picture's own aspect when
        # binning_x == binning_y, and silently drifts from it otherwise
        # (Round 2, Defect B2/D) -- active_picture_size() divides by binning
        # (or uses an explicit active-size annotation, when the driver
        # reports one) before ever taking the ratio. Falling back to
        # width/height keeps this correct for drivers that report no crop
        # metadata at all.
        aspect_width, aspect_height = active_picture_size(
            {
                "active_width": extra.get("active_width"),
                "active_height": extra.get("active_height"),
                "crop_width": extra.get("crop_width"),
                "crop_height": extra.get("crop_height"),
                "binning_x": binning_x,
                "binning_y": binning_y,
            },
            width, height,
        )
        detected_aspect = (
            round(aspect_width / aspect_height, 2)
            if aspect_height else None
        )

        mode = {
            "aspect": detected_aspect if detected_aspect is not None else (
                extra.get("aspect", metadata.get("aspect", round(width / height, 2)))
            ),
            "width": width,
            "height": height,
            "bit_depth": bit_depth,
            "packing": packing,
            "fps_max": fps_max_value,
            "gui_layout": extra.get("gui_layout", metadata.get("gui_layout", 0)),
            "file_size": file_size,
            # Keep crop and binning as driver-discovered mode metadata.  Crop
            # geometry comes directly from cinepi-raw --list-cameras; binning
            # is parsed from the driver's mode description and is never
            # reconstructed from output dimensions.
            #
            # Domain contract (WP-CM-10): crop_x/crop_y/crop_width/crop_height
            # is the sensor-side readout window, in native sensor coordinates
            # -- this is what V4L2_SEL_TGT_CROP reports and what libcamera
            # requires (WP-585-1). The recorded picture is width/height;
            # binning is the ratio between the two (crop / binning ==
            # width/height for a binned mode). Never multiply crop_* by
            # binning to "reach" the sensor domain -- it is already there.
            # A sensor that reports no crop at all (every stock sensor today)
            # leaves these None, which every reader must keep treating as
            # unknown geometry, not as a zero-size or full-frame crop.
            "crop_x": extra.get("crop_x"),
            "crop_y": extra.get("crop_y"),
            "crop_width": extra.get("crop_width"),
            "crop_height": extra.get("crop_height"),
            "sensor_width": extra.get("sensor_width"),
            "sensor_height": extra.get("sensor_height"),
            "binning_x": binning_x,
            "binning_y": binning_y,
            # The delivered active picture, in OUTPUT (post-binning,
            # optical-black-excluded) coordinates -- unlike crop_x/crop_y/
            # crop_width/crop_height above, which stay in native sensor
            # coordinates. Round 2, Defect D item 3: cinepi-raw does not
            # print this yet on any build this package has seen; a parallel
            # worker is adding it to --list-cameras. Parsed defensively (see
            # _parse_cinepi_output's "active" regex) and left None, never
            # guessed, when the running cinepi-raw predates it -- every
            # reader goes through active_picture_size(), which already knows
            # how to fall back.
            "active_left": extra.get("active_left"),
            "active_top": extra.get("active_top"),
            "active_width": extra.get("active_width"),
            "active_height": extra.get("active_height"),
            # ClearHDR flag (imx585). A mode is HDR when it is reported only
            # by `cinepi-raw --list-cameras --hdr sensor`; selecting it makes
            # cinepi-raw launch with --hdr sensor. See detect_camera_model().
            "hdr": bool(extra.get("hdr", hdr)),
        }
        return mode

    # Round 2, Defect D item 3. The label a parallel cinepi-raw worker's new
    # active-rectangle annotation is assumed to use, mirroring the existing
    # "mode-crop"/"crop" label this parser already accepts (see
    # _search_labeled_rect): "active", "mode-active", "active-size" or
    # "active-window" -- deliberately NOT "active-crop", which would also
    # satisfy the "crop" label above and be misread as a crop annotation on
    # the same line. Assumed full shape, same as mode-crop's:
    #   "active (48, 0)/2736x1824"   or   "mode-active (48,0)/2736x1824"
    #   "(48, 0)/2736x1824 active"   (trailing-label form, like plain "crop")
    # This is a documented ASSUMPTION, not read from the other worker's
    # code (unavailable to this session) -- report it back so the two
    # halves can be reconciled once both land. If cinepi-raw instead prints
    # a bare size with no origin ("active 2736x1824"), _ACTIVE_SIMPLE_RE
    # below is tried as a fallback whenever the rect form does not match.
    _ACTIVE_LABEL = r"active(?:[-_](?:size|window))?"
    _ACTIVE_SIMPLE_RE = r"\bactive(?:[-_](?:size|window))?\s*[:=]?\s*(\d+)\s*x\s*(\d+)\b"

    @staticmethod
    def _search_labeled_rect(line: str, label: str):
        """Find a `(left,top)/WxH` rectangle on *line* that is unambiguously
        labeled -- either a `mode-<label>`/`<label>` prefix (e.g.
        "mode-crop (108,40)/5472x3648") or a trailing `<label>` suffix (e.g.
        "(0, 0)/3840x2160 crop") -- and never a bare, unlabeled
        `(left,top)/WxH`.

        Round 2, Defect D item 3. More than one annotation can share this
        exact shape on the same probe line once a parallel cinepi-raw change
        adds an "active" rectangle alongside the existing "mode-crop" one
        (ROUND2.md: "the two halves can be reconciled" once this parses).
        Requiring the label is what keeps the two from being read as each
        other -- the previous crop regex made both the prefix and the
        suffix optional, so a bare `(x,y)/WxH` belonging to any OTHER
        labeled rectangle on the same line would have been misread as a
        crop. Every crop annotation this parser has ever seen (driver
        output and every test fixture) carries the literal word "crop" as
        one or the other, so this is not a behaviour change for crop itself.

        *label* is a regex fragment (already alternation-safe, no capturing
        groups) such as ``"crop"`` or ``"active(?:[-_](?:size|window))?"``.
        Returns (left, top, width, height) as ints, or None.
        """
        m = re.search(
            rf"(?:mode-)?{label}\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*/\s*(\d+)x(\d+)"
            rf"|\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*/\s*(\d+)x(\d+)\s*(?:mode-)?{label}\b",
            line, re.IGNORECASE,
        )
        if not m:
            return None
        g = m.groups()
        chosen = g[0:4] if g[0] is not None else g[4:8]
        return tuple(int(v) for v in chosen)

    # ────────────────────────────────────────────────────────────────
    #  1.  Parse *all* cameras and all modes that cinepi-raw reports
    # ────────────────────────────────────────────────────────────────
    # A mode line's OUTPUT size is the first "WxH" on it that is neither the
    # "/WxH" of a crop annotation nor the "NxN" of a binning token. Both
    # used to satisfy the plain (\d+)x(\d+) search, so a continuation line
    # carrying only geometry read as a brand-new WxH mode and the "attach
    # to the previous mode" branch was never reached (WP-CM-10's own note).
    _BINNING_TOKEN_RE = re.compile(
        r"\bbinning(?:\s+(?:factor|mode))?\s*[:=]?\s*\d+\s*[x×]\s*\d+\b",
        re.IGNORECASE,
    )
    _OUTPUT_SIZE_RE = re.compile(r"(?<![/\d])(\d+)x(\d+)")

    @classmethod
    def _output_size_on_line(cls, line: str):
        """The first WxH on *line* that is an output size, as a match with
        groups (width, height), or None when the line carries no output
        size -- only a crop and/or binning annotation, or nothing."""
        return cls._OUTPUT_SIZE_RE.search(cls._BINNING_TOKEN_RE.sub(" ", line))

    def _parse_cinepi_output(
        self,
        output: str,
        hdr: bool = False,
        *,
        clear_hdr_section: bool = False,
    ) -> Dict[str, List[Dict]]:
        """
        Return a mapping   {camera_model → [mode_dict, …]}   covering every
        camera found in a single *cinepi-raw --list-cameras* run. A mono sensor
        is reported as “<model>_mono”.

        ``hdr`` says the text came from a ``--hdr sensor`` run: the parser
        then watches for the ``CLEAR HDR / SENSOR HDR`` marker and for a
        repeated camera header, and tags what follows either as ClearHDR.
        The caller merges the plain and HDR runs.

        ``clear_hdr_section`` says the text IS the ClearHDR section -- the
        caller already cut the marker off -- so every camera in it starts
        in the ClearHDR state and a new camera header does not reset it.

        Without ``hdr`` the text is the plain probe, and the plain probe is
        the SDR state only: cinepi-raw prints the ClearHDR section on every
        --list-cameras run, so parsing stops at the marker rather than
        reading the ClearHDR state's timings back as SDR duplicates.

        A 16-bit line is ClearHDR whatever state the parser is in: the
        imx585 driver enumerates RAW16 only with wide_dynamic_range on, so
        the line is itself evidence of the ClearHDR state. Such lines used
        to be dropped when the parser believed it was still in the SDR
        state -- which it was for the whole of a pre-cut ClearHDR section
        and for any single-section listing -- and that is how every 16-bit
        ClearHDR mode vanished from the mode table while the 12-bit ones
        survived.
        """

        sensors: Dict[str, List[Dict]] = {}
        current_cam = None
        current_bit_depth = None
        header_bits = None
        comp1_sdr_warned = False
        sensor_width = None
        sensor_height = None
        parsing_modes = False                     # inside a “Modes:” block?
        # --hdr sensor may print SDR then HDR, or HDR only; a pre-cut
        # ClearHDR section starts, and stays, in the ClearHDR state.
        current_hdr = bool(clear_hdr_section)
        last_mode = None

        for raw in output.splitlines():
            line = raw.rstrip("\n")

            # ── camera header  e.g.  “0 : imx283 [5472x3648 …] (…)”
            m = re.match(r"^\s*\d+\s*:\s*([^\s]+)(?:\s*\[.*?(MONO)?\])?", line)
            if m:
                # --hdr sensor normally prints an explicit CLEAR HDR marker,
                # but some cinepi-raw/libcamera formatter combinations repeat
                # the camera header when switching sensor state without
                # printing that marker. If the same camera header appears
                # again during the --hdr probe, that second section is the
                # ClearHDR state. This is deliberately scoped to the HDR
                # probe; a normal --list-cameras run never promotes a repeated
                # header to HDR.
                next_cam = m.group(1)
                if m.group(2) == "MONO":
                    next_cam += "_mono"

                # Reset the ClearHDR flag by default whenever this header
                # belongs to a genuinely different camera than the one we
                # were just parsing. Without this, current_hdr set True by
                # one camera's own ClearHDR section (repeat header or the
                # literal marker below) would otherwise leak into a second,
                # different camera's mode block within the same combined
                # multi-camera --hdr sensor probe. The repeat/marker logic
                # right below re-sets it True again for that camera's own
                # ClearHDR section only.
                if next_cam != current_cam:
                    current_hdr = bool(clear_hdr_section)

                if hdr and next_cam in sensors and sensors.get(next_cam):
                    current_hdr = True

                # flush state & start a new camera section. Keep current_hdr
                # across the repeated header so the modes following it remain
                # tagged as ClearHDR.
                current_cam = next_cam
                sensors.setdefault(current_cam, [])
                current_bit_depth = None
                sensor_width = None
                sensor_height = None
                last_mode = None
                header_size = re.search(r"\[\s*(\d+)x(\d+)", line)
                if header_size:
                    sensor_width, sensor_height = map(int, header_size.groups())
                # cinepi-raw's header carries the sensor's own maximum depth
                # ("[3856x2180 12-bit RGGB]"), taken over the named Bayer
                # formats. That is the evidence for a compressed format whose
                # name has no digits to read -- see the PISP_COMP1 branch.
                header_bits_match = re.search(r"\[\s*\d+x\d+\s+(\d+)-bit", line)
                header_bits = int(header_bits_match.group(1)) if header_bits_match else None
                parsing_modes = False
                continue

            # we can’t do anything without a current camera
            if current_cam is None:
                continue

            # A plain probe is the SDR state and nothing else. cinepi-raw
            # prints the ClearHDR section on every --list-cameras run, so
            # stop at its marker: what follows is the other sensor state,
            # which the --hdr sensor probe reads on its own terms. Reading
            # on would file every ClearHDR-state 12-bit timing as an SDR
            # duplicate at half the ceiling.
            if not hdr and CLEAR_HDR_MARKER_RE.search(line):
                break

            # --hdr sensor is a two-state listing: cinepi-raw first
            # prints the ordinary SDR sensor state, then toggles the sensor
            # and prints the ClearHDR state after this separator. The old
            # parser tagged the entire --hdr invocation as HDR, which caused
            # ordinary modes from the first half to be duplicated/misclassified.
            if hdr and (
                re.search(r"CLEAR\s+HDR\s*/\s*SENSOR\s+HDR", line, re.IGNORECASE)
                or re.search(r"\bCLEAR\s+HDR\b", line, re.IGNORECASE)
            ):
                # The IMX585 probe switches from its normal SDR state to the
                # ClearHDR sensor state. Keep this state even when the driver
                # repeats the camera header afterwards.
                current_hdr = True
                parsing_modes = False
                current_bit_depth = None
                last_mode = None
                continue

            # ── “Modes:” line starts (or continues) a mode list
            if "Modes:" in line:
                parsing_modes = True  # don’t *continue* – this line may
                # already contain format + resolution

            if not parsing_modes:
                continue

            # ── format / bit-depth (may share the line with a resolution)
            # Accept any four-letter Bayer order (SRGGB, SBGGR, SGRBG,
            # SGBRG, ...): libcamera's format name follows the Bayer order
            # after any sensor flip, so depending on one fixed order is a
            # latent trap. Keep the mono and packed spellings (R.../Y...).
            fmt = re.search(r"'(?:S[RGB]{4}|R|GREY|Y)(\d+)", line)
            if fmt:
                current_bit_depth = int(fmt.group(1))
            elif "PISP_COMP1" in line:
                # PiSP COMP1 is a 16-bit *container* and its name has no digits,
                # so the line itself cannot say what depth it carries.
                # cinepi-raw's resolve_dng_output_depth() narrows a COMP1 stream
                # to 12- or 10-bit precisely because the container does carry
                # sub-16-bit sensor modes, so asserting 16 would mislabel those
                # and then the 16-bit-in-SDR guard below would silently drop
                # them; inheriting the previous format block's depth would label
                # this mode with another mode's number.
                #
                # The evidence is in the camera header, which cinepi-raw prints
                # as "[WxH N-bit ORDER]" from the sensor's own named formats. Use
                # it, fall back to the container's 16 bits in the ClearHDR state
                # where a 16-bit readout is what the sensor reports, and skip the
                # line when neither is available rather than inventing a number.
                if header_bits is not None:
                    current_bit_depth = header_bits
                elif current_hdr:
                    current_bit_depth = 16
                else:
                    if not comp1_sdr_warned:
                        logging.warning(
                            "%s reports a PiSP COMP1 format and no bit depth in "
                            "its header, so those lines are skipped: the listing "
                            "cannot say what depth the container carries.",
                            current_cam,
                        )
                        comp1_sdr_warned = True
                    continue

            # ── first OUTPUT resolution on the line (if any): never the crop
            # annotation's own /WxH, never a binning token's NxN.
            res = self._output_size_on_line(line)
            if not res:
                # Some drivers print mode geometry on a continuation line.
                # Attach explicitly reported crop/binning metadata to the
                # most recently parsed mode; never infer either from output
                # dimensions. rpicam's normal --list-cameras formatter keeps
                # the crop on the same line, but cinepi-raw variants that
                # probe a mode can emit it separately.
                crop_only = self._search_labeled_rect(line, "crop")
                if crop_only and last_mode is not None:
                    cx, cy, cw, ch = crop_only
                    last_mode["crop_x"] = cx
                    last_mode["crop_y"] = cy
                    last_mode["crop_width"] = cw
                    last_mode["crop_height"] = ch
                    last_mode["sensor_width"] = sensor_width
                    last_mode["sensor_height"] = sensor_height

                binning_only = re.search(
                    r"\bbinning(?:\s+(?:factor|mode))?\s*[:=]?\s*"
                    r"(\d+)\s*[x×]\s*(\d+)\b",
                    line, re.IGNORECASE,
                )
                if binning_only and last_mode is not None:
                    last_mode["binning_x"] = int(binning_only.group(1))
                    last_mode["binning_y"] = int(binning_only.group(2))

                # Round 2, Defect D item 3: the active-picture annotation a
                # parallel cinepi-raw worker is adding to --list-cameras.
                # Its exact format is not visible from this session, so this
                # is parsed defensively -- see _ACTIVE_LABEL's own comment
                # (just above _search_labeled_rect) for the shape assumed
                # and the fallback order (active annotation, then crop/
                # binning, then transport) that active_picture_size()
                # applies when this finds nothing.
                active_only = self._search_labeled_rect(line, self._ACTIVE_LABEL)
                if active_only and last_mode is not None:
                    al, at, aw, ah = active_only
                    last_mode["active_left"] = al
                    last_mode["active_top"] = at
                    last_mode["active_width"] = aw
                    last_mode["active_height"] = ah
                elif last_mode is not None:
                    active_simple = re.search(self._ACTIVE_SIMPLE_RE, line, re.IGNORECASE)
                    if active_simple:
                        last_mode["active_width"] = int(active_simple.group(1))
                        last_mode["active_height"] = int(active_simple.group(2))
                continue

            width, height = map(int, res.groups())
            fps = re.search(r"\[(\d+(?:\.\d+)?)\s*fps", line)
            fps_max = int(float(fps.group(1))) if fps else None
            mode_extra = {}
            crop = self._search_labeled_rect(line, "crop")
            if crop:
                cx, cy, cw, ch = crop
                mode_extra.update({
                    "crop_x": cx, "crop_y": cy,
                    "crop_width": cw, "crop_height": ch,
                    "sensor_width": sensor_width,
                    "sensor_height": sensor_height,
                })

            # Round 2, Defect D item 3: parse the active-picture annotation
            # defensively -- see _ACTIVE_LABEL's own comment (just above
            # _search_labeled_rect) for the exact shape assumed. Absent this
            # annotation (every cinepi-raw build this package has actually
            # seen), active_width/active_height simply stay unset and
            # active_picture_size() falls back to crop/binning, then to the
            # transport frame, exactly as before this fix.
            active = self._search_labeled_rect(line, self._ACTIVE_LABEL)
            if active:
                al, at, aw, ah = active
                mode_extra.update({
                    "active_left": al, "active_top": at,
                    "active_width": aw, "active_height": ah,
                })
            else:
                active_simple = re.search(self._ACTIVE_SIMPLE_RE, line, re.IGNORECASE)
                if active_simple:
                    mode_extra["active_width"] = int(active_simple.group(1))
                    mode_extra["active_height"] = int(active_simple.group(2))

            # The driver annotation is authoritative. Keep this parser deliberately
            # permissive because the human-readable libcamera/rpicam formatter has
            # appeared in several equivalent forms:
            #   "binning 2x2", "binning: 2x2", "binning factor 2x2",
            #   "binning mode 2×2".
            # Never derive binning from the output resolution: 1920x1080 can
            # legitimately be either 1x1 or 2x2 on IMX585.
            binning = re.search(
                r"\bbinning(?:\s+(?:factor|mode))?\s*[:=]?\s*"
                r"(\d+)\s*[x×]\s*(\d+)\b",
                line, re.IGNORECASE,
            )
            if binning:
                bx, by = map(int, binning.groups())
                mode_extra["binning_x"] = bx
                mode_extra["binning_y"] = by
            # RAW16 is a ClearHDR-only imx585 format: the driver enumerates
            # it only with wide_dynamic_range on, so a 16-bit line is evidence
            # of the ClearHDR state on its own, whatever state the parser is
            # in. Tag it, never drop it. This used to `continue` whenever the
            # parser believed it was still in the SDR state -- which it was
            # for the whole of a pre-cut ClearHDR section, and for any
            # single-section listing -- and that is how every 16-bit ClearHDR
            # mode vanished from the mode table while the 12-bit ones survived.
            line_hdr = current_hdr or current_bit_depth == 16

            last_mode = self._mode_from_metadata_or_detected(
                camera_name=current_cam, width=width, height=height,
                bit_depth=current_bit_depth, fps_max=fps_max, hdr=line_hdr,
                extra=mode_extra,
            )
            sensors[current_cam].append(last_mode)

        # Do not promote the whole --hdr invocation here when no state
        # marker was seen. Some formatter variants print both SDR and HDR
        # timings without a separator, and doing that here would incorrectly
        # mark the repeated SDR timings as ClearHDR. detect_camera_model()
        # compares the HDR probe against the plain probe before merge and
        # promotes only timings that are genuinely new to the HDR state.
        return sensors

    @staticmethod
    def _hdr_whitelist(hdr_cfg: Any) -> List[bool]:
        """Normalize settings.jsonc resolutions.hdr into the internal
        [bool, ...] whitelist consumed by _finalize_modes.

        Accepts the named form {"sdr": bool, "imx585_clear_hdr": bool} (both
        default true) or the legacy [false, true] list form for old Pi
        settings.jsonc files.
        """
        if isinstance(hdr_cfg, dict):
            return [
                val for val, key in ((False, "sdr"), (True, "imx585_clear_hdr"))
                if hdr_cfg.get(key, True)
            ]
        return list(hdr_cfg or [])

    @staticmethod
    def _clear_hdr_depths(hdr_cfg: Any):
        """Which ClearHDR bit depths settings.jsonc offers, or None for all.

        The imx585 reports ClearHDR at 12-bit and 16-bit, and an operator
        wants to choose between them: they are different captures, not two
        spellings of one. image_capture.bit_depths is the wrong lever for it
        -- it applies to every mode, so dropping 12 there would take the
        12-bit SDR modes as well.

        imx585_clear_hdr, the older single switch, is honoured as the default
        for both: a settings.jsonc that turned ClearHDR off wholesale keeps
        both depths off, and one that never mentioned any of these keeps both
        on. None means "no opinion", which is also what a non-dict config
        (the legacy list form) yields -- there is nothing per-depth to read
        out of it.
        """
        if not isinstance(hdr_cfg, dict):
            return None
        legacy = bool(hdr_cfg.get("imx585_clear_hdr", True))
        depths = set()
        if bool(hdr_cfg.get("imx585_clear_hdr_12bit", legacy)):
            depths.add(12)
        if bool(hdr_cfg.get("imx585_clear_hdr_16bit", legacy)):
            depths.add(16)
        return depths

    @classmethod
    def _normalize_hdr_probe_modes(
        cls,
        base_modes: Dict[str, List[Dict]],
        hdr_modes: Dict[str, List[Dict]],
    ) -> None:
        """Decide which modes of an unmarked ``--hdr sensor`` probe are HDR.

        The plain probe is SDR. The --hdr sensor probe is ClearHDR. This is
        the semantic contract between cinepi-raw and CineMate, so FPS is never
        used to decide HDR state.

        If the formatter explicitly prints an SDR section before switching to
        ClearHDR, _parse_cinepi_output() has already marked that first section
        as hdr=False and the second section as hdr=True, and this method leaves
        both alone: an explicit parser state always wins.

        What is left is the formatter that prints no state boundary at all, and
        there the probe itself is not evidence of anything: a sensor with no
        ClearHDR ignores --hdr sensor and prints its plain listing back,
        character for character (observed on imx283, and true of every stock
        sensor whose driver has no HDR mode -- imx477, imx296). Promoting that
        wholesale is what produced 42 rows for the imx283's 21 modes, half of
        them phantom "CLEAR HDR" duplicates in the GUI.

        So an unmarked mode is promoted only on evidence that the sensor
        actually changed state, and there are exactly two kinds:

        * The probe lists a timing the plain probe never reported
          (_mode_timing_key, geometry plus the fps ceiling). ClearHDR halves
          the readout rate, so a real ClearHDR mode arrives either as a
          geometry the plain probe does not have at all (the 16-bit modes) or
          as a known geometry at a new, lower ceiling.
        * The probe lists the same readout twice at two different ceilings.
          That is the SDR-then-ClearHDR listing without its separator, so the
          repeat is the second state even when the plain probe happens to list
          that lower ceiling too.

        A mode that is neither -- same readout, same ceiling, already in the
        plain listing -- stays hdr=False and _merge_mode_lists then drops it as
        the duplicate it is. A sensor that echoes its plain listing therefore
        contributes zero hdr=True modes, while imx585 keeps gaining them.

        The residual risk is a genuine ClearHDR mode reported at exactly the
        SDR geometry *and* the SDR ceiling, which would be read as an echo.
        Nothing in the listing could distinguish the two, and on the hardware
        that has ClearHDR the probe prints the CLEAR HDR marker anyway, so the
        marked path above is what imx585 actually takes.
        """
        for cam, modes in hdr_modes.items():
            plain = base_modes.get(cam) or []
            # WHOLE-LISTING ECHO TEST, before any per-mode reasoning.
            #
            # A sensor with no ClearHDR ignores --hdr sensor and prints its
            # plain listing back. The per-mode rules below then have to infer
            # that from each row in isolation, and they infer it from the fps
            # ceiling and the crop fields -- both of which can differ between
            # two probes for reasons that have nothing to do with HDR (the
            # ceiling is re-read per configure, and the crop fields come from
            # driver controls sampled during enumeration). Any such jitter makes
            # every row look like "a timing the plain probe never reported", and
            # the whole listing is promoted: 2026-09-27, the imx283 showed every
            # one of its modes twice, once as STANDARD and once as CLEAR HDR.
            #
            # The listing as a whole cannot jitter that way. ClearHDR is a
            # different sensor STATE, so a sensor that has one always offers at
            # least one readout the plain probe does not -- imx585's 16-bit
            # geometries. Comparing readout sets (geometry, depth, crop,
            # binning; fps deliberately excluded) answers "did this probe change
            # anything at all" without depending on the values that jitter.
            #
            # No new readout means the probe is an echo and nothing in it is
            # ClearHDR. Explicitly marked rows are still honoured -- the parser
            # saw a CLEAR HDR section, which is evidence this test cannot
            # override -- so imx585's marked path is untouched.
            # The key is deliberately COARSE -- width, height, depth, fps --
            # because the two probes do not always agree on the rest. crop_* and
            # binning_* come from driver controls sampled during enumeration,
            # and a probe that fails to read them reports None for every mode,
            # which makes every fine-grained key differ and every row look new.
            # That, not fps, is what promoted the imx283's whole table: the
            # operator's listing showed each mode twice at the SAME ceiling
            # (32 fps and 32 fps), so the ceilings matched and only the crop
            # fields did not.
            def robust(m):
                return (int(m.get("width") or 0), int(m.get("height") or 0),
                        int(m.get("bit_depth") or 0), m.get("fps_max"))

            # Two keys, and the difference matters. The SUBSET test uses the
            # timing key (fps included): a genuine ClearHDR listing offers a
            # ceiling the plain probe does not, so it is not a subset. The
            # REPEAT test uses the readout key (fps excluded): one readout
            # listed at two ceilings inside a single probe is the
            # SDR-then-ClearHDR listing with its separator missing, and that
            # stays the per-mode rules' job however the subset test comes out.
            def readout_only(m):
                return (int(m.get("width") or 0), int(m.get("height") or 0),
                        int(m.get("bit_depth") or 0))

            plain_timings_coarse = {robust(m) for m in plain}
            probe_timings_coarse = [robust(m) for m in modes]
            probe_readouts_only = [readout_only(m) for m in modes]
            repeated = len(probe_readouts_only) != len(set(probe_readouts_only))
            if (probe_timings_coarse and not repeated
                    and set(probe_timings_coarse) <= plain_timings_coarse):
                if not any(m.get("hdr") is True for m in modes):
                    logging.info(
                        "%s: --hdr sensor echoed the plain listing (%d modes, "
                        "no new readout) -- no ClearHDR on this sensor",
                        cam, len(modes),
                    )
                    continue

            plain_timings = {
                cls._mode_timing_key(m) for m in plain
            }
            # Readout (_mode_key: geometry and depth, no fps) -> the ceilings
            # this probe has already listed for it. Built as we go, so "seen
            # earlier in this probe" means exactly that.
            timings_seen: Dict[tuple, set] = {}
            for mode in modes:
                # Read the readout key before any promotion below: _mode_key
                # carries the HDR flag, so promoting first would file the mode
                # under a different readout than its unmarked siblings.
                readout = cls._mode_key(mode)
                timing = cls._mode_timing_key(mode)
                seen = timings_seen.setdefault(readout, set())
                # An explicit parser state always wins.
                if mode.get("hdr") is True:
                    seen.add(timing)
                    continue
                second_state = bool(seen) and timing not in seen
                if second_state or timing not in plain_timings:
                    mode["hdr"] = True
                seen.add(timing)


    @staticmethod
    def _mode_timing_key(mode: Dict) -> tuple:
        """Identity of a mode including its reported timing ceiling.

        Unlike _mode_key(), this deliberately excludes the SDR/ClearHDR state.
        It is used only to compare the HDR probe with the plain probe when the
        human-readable formatter does not expose a reliable state separator
        (_normalize_hdr_probe_modes) -- a comparison that has to see both
        probes' timings and must not depend on the state it is deciding.
        """
        return (
            int(mode.get("width") or 0),
            int(mode.get("height") or 0),
            int(mode.get("bit_depth") or 0),
            mode.get("fps_max"),
            mode.get("crop_x"), mode.get("crop_y"),
            mode.get("crop_width"), mode.get("crop_height"),
            mode.get("binning_x"), mode.get("binning_y"),
        )

    @staticmethod
    def _mode_key(mode: Dict) -> tuple:
        """Identity of a sensor readout state.

        FPS is a timing ceiling, not part of the mode identity. The same
        physical readout can be reported at different ceilings by the plain
        and HDR probes. HDR itself is part of the identity because SDR and
        ClearHDR are different sensor states.
        """
        return (
            int(mode.get("width") or 0),
            int(mode.get("height") or 0),
            int(mode.get("bit_depth") or 0),
            bool(mode.get("hdr")),
            mode.get("crop_x"), mode.get("crop_y"),
            mode.get("crop_width"), mode.get("crop_height"),
            mode.get("binning_x"), mode.get("binning_y"),
        )

    def _merge_mode_lists(
        self,
        base: Dict[str, List[Dict]],
        hdr: Dict[str, List[Dict]],
    ) -> Dict[str, List[Dict]]:
        """Combine the plain (non-HDR) and ``--hdr sensor`` mode lists.

        A mode from the HDR run is appended only when the plain run reported no
        mode with the same _mode_key -- the readout state, which includes the
        SDR/ClearHDR flag and excludes fps -- so one readout reported at two
        ceilings does not become two modes.

        The collapse for a sensor that ignores ``--hdr sensor`` is decided
        before this, in _normalize_hdr_probe_modes: such a probe's modes are
        never promoted, so they arrive here with a key the plain list already
        holds and are dropped, and only real ClearHDR sensors (imx585) gain HDR
        modes. This method cannot do that job itself -- by the time it runs, a
        promoted mode's key carries hdr=True and can never equal a plain
        hdr=False key, which is why the collapse it used to promise here never
        happened.
        """
        merged: Dict[str, List[Dict]] = {cam: list(modes) for cam, modes in base.items()}
        for cam, hdr_modes in hdr.items():
            base_keys = {self._mode_key(m) for m in merged.get(cam, [])}
            for mode in hdr_modes:
                key = self._mode_key(mode)
                if key in base_keys:
                    continue
                merged.setdefault(cam, []).append(mode)
                base_keys.add(key)
        return merged

    @staticmethod
    def _mode_identity(mode: Dict) -> tuple:
        return (
            int(mode.get("width") or 0), int(mode.get("height") or 0),
            int(mode.get("bit_depth") or 0), bool(mode.get("hdr")),
            mode.get("crop_x"), mode.get("crop_y"),
            mode.get("crop_width"), mode.get("crop_height"),
        )

    @staticmethod
    def _mode_identity_coarse(mode: Dict) -> tuple:
        """The part of a mode's identity that survives a driver geometry change.

        _mode_identity below is the full key and includes crop_x/crop_y/
        crop_width/crop_height, deliberately: two modes can deliver the same
        width x height at different crops, and only the crop tells them apart.
        But that makes a saved enabled_modes entry unmatchable the moment a
        driver moves its windows -- and the imx283 campaign moved EVERY one of
        them (the corrected active area shifted crop_x from 40 to 108 across the
        table, and MODE_1C's family from 236 to 924). The operator's single
        chosen mode then matched nothing and _finalize_modes fell back to
        showing all 73, which reads as "my setting was ignored".
        """
        return (
            int(mode.get("width") or 0), int(mode.get("height") or 0),
            int(mode.get("bit_depth") or 0), bool(mode.get("hdr")),
        )

    @classmethod
    def _mode_matches_enabled(cls, mode: Dict, entries: List[Dict]) -> bool:
        ident = cls._mode_identity(mode)
        return any(isinstance(e, dict) and cls._mode_identity(e) == ident for e in (entries or []))

    @classmethod
    def _match_enabled_modes(cls, modes: List[Dict], entries: List[Dict]):
        """(modes to keep, tier) for an explicit enabled_modes selection.

        Tier "exact"  - full identity, crop geometry included. Unchanged
                        behaviour, and the only tier that can run when the
                        driver still reports the geometry the choice was saved
                        against.
        Tier "coarse" - tried ONLY when "exact" matched nothing at all, i.e.
                        the saved choice has been invalidated wholesale rather
                        than the operator having deselected everything. Falls
                        back to width/height/depth/hdr, which is what survives a
                        geometry change.
        Tier "none"   - neither matched. The caller decides what to do; it must
                        not silently widen to the whole table.

        The coarse tier can keep MORE modes than were chosen, when two modes
        share a size at different crops. That is honest -- the saved entry no
        longer carries anything that could tell them apart -- and it is a far
        smaller surprise than the whole table. The tier is returned rather than
        swallowed so the caller can say which one it used.
        """
        exact_keys = {cls._mode_identity(e) for e in (entries or []) if isinstance(e, dict)}
        keep = [m for m in modes if cls._mode_identity(m) in exact_keys]
        if keep:
            return keep, "exact"

        coarse_keys = {cls._mode_identity_coarse(e) for e in (entries or []) if isinstance(e, dict)}
        keep = [m for m in modes if cls._mode_identity_coarse(m) in coarse_keys]
        if keep:
            return keep, "coarse"

        return [], "none"

    def mode_selected(self, camera_name: str, mode: Dict) -> bool:
        """This mode's own selection, IGNORING the ratio gate entirely
        (PLAN.md's W1<->W2 contract: "the mode's own selection, IGNORING the
        ratio gate (explicit enabled_modes match, else the stock mode
        rule)").

        The one public predicate both _finalize_modes' dial and the
        settings-editor endpoint's "selected" column now call, replacing two
        separate reimplementations of the same question (settings_editor.
        selected_for(), _finalize_modes' own inline use_individual_selection
        branch) that had already drifted from each other on the ratio-gate
        bypass PLAN.md's D4 finding describes: enabled_modes used to skip the
        ratio matcher entirely, so a mode explicitly enabled under a ratio
        the operator later hid stayed selected and reachable in the dial. The
        actual ratio gate is applied by the CALLER, uniformly for both the
        explicit and stock paths -- see _finalize_modes' "filter & index"
        section -- so this function answers only "does the operator want
        this mode at all", never "and is its toggle currently on".

        An explicit enabled_modes entry for this camera is authoritative
        (the exact -> coarse tiers _match_enabled_modes already implements,
        including the notices _finalize_modes raises when neither tier
        matches). With no such entry, falls to the stock mode rule: 1x1
        binning, or binning not reported at all (PLAN.md's "1x1 modes on,
        every mode when the driver does not report binning" -- explicitly
        NOT the D1 tier-3 INFERRED binning active_picture_size() computes for
        display purposes only), passed through the same global filters
        (bit_depths, k_steps, the HDR switches) the non-explicit path in
        _finalize_modes has always applied. min_mode_width is deliberately
        not checked here -- see _stock_mode_selected()'s own docstring.

        Matches *mode* against the saved entries BY VALUE (_mode_identity/
        _mode_identity_coarse), never by Python object identity: this is
        called both from _finalize_modes, whose *mode* is one of the
        camera's live mode dicts, and from the settings-editor endpoint,
        whose *mode* comes from a DIFFERENT list (sensor_modes_unfiltered's
        own dict-copies) -- two objects with identical fields but different
        id()s. The pool used to decide the tier (exact vs coarse vs none) is
        always sensor_modes_unfiltered, since that decision is a property of
        the WHOLE saved selection against the CURRENT driver table, not of
        this one mode; when it is missing (mode_selected called before
        _finalize_modes has populated it) *mode* stands in as a one-element
        pool so a direct, standalone call still resolves sensibly.
        """
        entries = (getattr(self, "enabled_modes", None) or {}).get(camera_name)
        if isinstance(entries, list) and entries:
            pool = (getattr(self, "sensor_modes_unfiltered", None) or {}).get(camera_name) or [mode]
            _keep, tier = self._match_enabled_modes(pool, entries)
            if tier == "exact":
                return self._mode_matches_enabled(mode, entries)
            if tier == "coarse":
                coarse_keys = {
                    self._mode_identity_coarse(e) for e in entries if isinstance(e, dict)
                }
                return self._mode_identity_coarse(mode) in coarse_keys
            return False
        return self._stock_mode_selected(mode)

    def _stock_mode_selected(self, mode: Dict) -> bool:
        """The stock rule for a camera with no explicit enabled_modes entry:
        1x1 binning, or binning simply not reported (never an INFERRED one --
        see active_picture_size()'s tier 3 and PLAN.md D1; a mode's binning
        being unknown must not be conflated with a display-only guess about
        it), plus the same bit_depths/k_steps/HDR filters the non-explicit
        path in _finalize_modes already applies today.

        min_mode_width is NOT checked here on purpose: the width floor has
        always hidden a narrow mode from the dial/GUIs without touching
        whether it counts as "selected" (settings_editor's own
        below_width_floor field marks it instead), and mode_selected() exists
        to answer exactly the same question selected_for() used to, not to
        widen it.

        Every filter attribute is read through getattr with a "no opinion"
        default: mode_selected() is called both from _finalize_modes (where a
        real SensorDetect and this file's own test doubles always set them)
        and from the settings-editor endpoint, whose own, more minimal test
        doubles may not -- same convention _finalize_modes itself already
        uses for clear_hdr_depths/aspect_ratios_cfg.
        """
        bx, by = self._mode_binning(mode)
        if bx is not None and by is not None and (bx, by) != (1, 1):
            return False
        bit_depths = getattr(self, "bit_depths", None)
        if bit_depths and mode.get("bit_depth") not in bit_depths:
            return False
        clear_hdr_depths = getattr(self, "clear_hdr_depths", None)
        if bool(mode.get("hdr")) and clear_hdr_depths is not None:
            if int(mode.get("bit_depth") or 0) not in clear_hdr_depths:
                return False
        hdr_modes = getattr(self, "hdr_modes", None)
        if hdr_modes and bool(mode.get("hdr")) not in hdr_modes:
            return False
        k_steps = getattr(self, "k_steps", None)
        if k_steps:
            k_val = round((mode.get("width") or 0) / 1000 * 2) / 2
            if k_val not in k_steps:
                return False
        return True

    @staticmethod
    def _mode_binning(mode: Dict) -> tuple:
        bx, by = mode.get("binning_x"), mode.get("binning_y")
        if all(isinstance(v, (int, float)) and v > 0 for v in (bx, by)):
            return (int(bx), int(by))
        return (None, None)

    @classmethod
    def _mode_is_full(cls, mode: Dict) -> bool:
        """
        True only when the driver supplied crop geometry that identifies the
        mode as the full active sensor window.

        A missing crop annotation is deliberately *unknown*, not full frame.
        This matters for stock drivers such as IMX477 which do not expose the
        optional geometry metadata.

        WP-CM-10: crop_x/crop_y/crop_width/crop_height is always the sensor-
        side readout window in native sensor coordinates (see the contract
        comment in _mode_from_metadata_or_detected), at any binning. A
        zero-origin crop is compared to the native array directly -- it is
        never multiplied by binning to "reach" the sensor domain, because it
        is already expressed there.
        """
        cw, ch = mode.get("crop_width"), mode.get("crop_height")
        if cw is None or ch is None:
            return False

        cx = int(mode.get("crop_x") or 0)
        cy = int(mode.get("crop_y") or 0)
        if cx != 0 or cy != 0:
            return False

        bx, by = cls._mode_binning(mode)
        sw, sh = mode.get("sensor_width"), mode.get("sensor_height")
        if bx is not None and by is not None:
            if sw and sh:
                # Permit the small optical-black/native-array margins present
                # on sensors such as IMX585 (3856x2180 native, 3840x2160
                # active). The crop is already in sensor coordinates, so
                # this compares it to the native array directly -- no
                # binning multiplication.
                active_w, active_h = int(cw), int(ch)
                native_w, native_h = int(sw), int(sh)
                return (
                    active_w <= native_w and active_h <= native_h and
                    native_w - active_w <= max(32, bx * 16) and
                    native_h - active_h <= max(32, by * 16)
                )
            # No native dimensions, but the driver explicitly says
            # zero-origin and gives binning: treat it as a full sensor
            # window.
            return True

        if sw and sh:
            return int(cw) == int(sw) and int(ch) == int(sh)

        return False

    @classmethod
    def _mode_sort_key(cls, mode: Dict) -> tuple:
        """Stable operator-facing mode order.

        Capture classes are grouped exactly as the settings pane presents them:
        16-bit ClearHDR 1x1 -> 16-bit ClearHDR 2x2 ->
        12-bit ClearHDR 1x1 -> 12-bit ClearHDR 2x2 ->
        16-bit SDR 1x1 -> 16-bit SDR 2x2 ->
        12-bit SDR 1x1 -> 12-bit SDR 2x2 ->
        10-bit SDR 1x1 -> 10-bit SDR 2x2.

        Within each class the full active frame comes first, followed by
        sensor-windowed derivatives, largest crop first.
        """
        bx, by = cls._mode_binning(mode)
        bin_factor = (bx or 1) * (by or 1)
        full = cls._mode_is_full(mode)
        known_crop = mode.get("crop_width") is not None

        hdr = bool(mode.get("hdr"))
        depth = int(mode.get("bit_depth") or 0)
        if hdr and depth == 16:
            class_rank = 0
        elif hdr and depth == 12:
            class_rank = 2
        elif not hdr and depth == 16:
            # Standard 16-bit modes belong above standard 12-bit modes.
            class_rank = 4
        elif not hdr and depth == 12:
            class_rank = 6
        elif not hdr and depth == 10:
            class_rank = 8
        else:
            class_rank = 10

        return (
            class_rank,
            bin_factor,
            0 if full else (1 if known_crop else 2),
            -(int(mode.get("crop_width") or mode.get("width") or 0)
              * int(mode.get("crop_height") or mode.get("height") or 0)),
            int(mode.get("crop_x") or 0),
            int(mode.get("crop_y") or 0),
        )

    # ────────────────────────────────────────────────────────────────
    #  WP-CM-6: aspect ratio as a selection axis
    # ────────────────────────────────────────────────────────────────
    @staticmethod
    def _mode_aspect(mode: Dict) -> float | None:
        """The real aspect of a mode: its own "aspect" field when one has
        already been computed (tier A/B: from the driver's crop; tier C:
        from width/height -- see _mode_from_metadata_or_detected), else a
        width/height fallback for a mode dict that predates that field.
        Never derived from binning -- this is purely the picture shape."""
        a = mode.get("aspect")
        if a is not None:
            try:
                return float(a)
            except (TypeError, ValueError):
                pass
        w, h = mode.get("width"), mode.get("height")
        if w and h:
            try:
                return round(float(w) / float(h), 2)
            except (TypeError, ValueError, ZeroDivisionError):
                return None
        return None

    def _aspect_ratio_table(self) -> List[Dict[str, Any]]:
        table = getattr(self, "aspect_ratio_table", None)
        return table if table is not None else load_aspect_ratio_table()

    def _nearest_ratio_id(self, aspect: float) -> str | None:
        """The canonical ratio id closest to `aspect`, whatever the
        distance -- unlike _modes_within_ratio_tolerance there is no
        tolerance gate here, because this is used to find a mode's "home"
        ratio for the derived default (_derived_default_ratio_ids), not to
        decide whether a match counts as exact. None only when the ratio
        table itself is empty (see load_aspect_ratio_table's own
        "never stop CineMate booting" fallback)."""
        table = self._aspect_ratio_table()
        if not table:
            return None
        return min(table, key=lambda e: abs(e["value"] - aspect))["id"]

    def _full_frame_modes(self, camera_name: str) -> List[Dict]:
        """This camera's whole-sensor modes, from its raw pre-filter table.

        _mode_is_full() is deliberately false when the driver reports no crop
        geometry at all, so a stock sensor that never answers the five
        geometry controls (imx477, imx296) has no full-frame modes as far as
        this is concerned, and therefore gets no "full" toggle. That is the
        honest answer rather than a guess: without geometry nothing here knows
        which of its modes reads the whole array, and picking the largest
        would be inventing the fact. Those sensors are not left worse off --
        their biggest mode is 4:3, which the shipped default already selects.
        """
        modes = (getattr(self, "sensor_modes_unfiltered", None) or {}).get(camera_name) or []
        return [m for m in modes if self._mode_is_full(m)]

    def full_frame_ratio(self, camera_name: str):
        """(ratio_id, aspect) for this camera's whole-sensor shape, or
        (None, None) when it has no mode known to be full frame.

        The id is a TABLE id when the full frame really is one of the
        canonical ratios -- within ASPECT_RATIO_TOLERANCE, the same test
        "exact" uses everywhere else -- and FULL_FRAME_RATIO_ID otherwise.
        That single decision is what drives all three behaviours the operator
        asked for: whether a fifteenth toggle appears, what it is called, and
        which toggle a full-frame row hides behind.

        Tolerance, not the home ratio, is what "actually is one of the aspect
        ratios" has to mean here. The imx283's 1.50 comes *home* to 1.37:1
        because 1.37 is the nearest of the fourteen, but 1.50 plainly is not
        1.37 -- it is 0.13 away, six times tolerance -- and calling that
        toggle "1.37:1 (full)" would be a lie an operator could measure.
        """
        modes = self._full_frame_modes(camera_name)
        aspect = None
        for m in modes:
            aspect = self._mode_aspect(m)
            if aspect is not None:
                break
        if aspect is None:
            return None, None
        table = self._aspect_ratio_table()
        if table:
            best = min(table, key=lambda e: abs(e["value"] - aspect))
            if abs(best["value"] - aspect) <= ASPECT_RATIO_TOLERANCE + _ASPECT_TOLERANCE_EPS:
                return best["id"], aspect
        return FULL_FRAME_RATIO_ID, aspect

    def home_ratio_id(self, camera_name: str, mode: Dict) -> str | None:
        """The ONE toggle a mode belongs to (PLAN.md, 2026-09-28, "no
        closest"):

        1. a whole-sensor mode on a camera whose full frame is off-table
           belongs to FULL_FRAME_RATIO_ID;
        2. else its nearest canonical ratio, but ONLY when that is within
           ASPECT_RATIO_TOLERANCE -- ties broken by table order, same as
           _nearest_ratio_id/full_frame_ratio;
        3. else a NATIVE_RATIO_PREFIX id carrying the mode's own real aspect
           (aspect_ratios.NATIVE_RATIO_PREFIX's own comment), UNLESS that
           rounded aspect equals the off-table full frame's own rounded
           aspect, in which case it is folded into FULL_FRAME_RATIO_ID
           instead -- so a windowed crop that happens to share the sensor's
           native shape does not mint a second toggle with the same label
           the full-frame toggle already carries.

        Superseded WP-CM-11's version, which returned the nearest canonical
        ratio unconditionally (no tolerance gate) -- exactly the "closest"
        behaviour PLAN.md's D2 finding traced to a saved ratio choice
        surviving a sensor swap onto a camera that never had that shape.

        One function because three places have to agree or the pane lies:
        the stock default (which ratios a fresh camera selects, via
        available_aspect_ratios), the matcher (which modes an enabled ratio
        yields) and the settings page's row labels (which toggle a row hides
        behind) all call this, never their own copy of the rule.
        """
        aspect = self._mode_aspect(mode)
        if aspect is None:
            return None

        full_id, full_aspect = self.full_frame_ratio(camera_name)
        full_off_table = full_id == FULL_FRAME_RATIO_ID

        if full_off_table and self._mode_is_full(mode):
            return FULL_FRAME_RATIO_ID

        nearest_id = self._nearest_ratio_id(aspect)
        if nearest_id is not None:
            table = self._aspect_ratio_table()
            nearest_value = next((e["value"] for e in table if e["id"] == nearest_id), None)
            if (
                nearest_value is not None
                and abs(nearest_value - aspect) <= ASPECT_RATIO_TOLERANCE + _ASPECT_TOLERANCE_EPS
            ):
                return nearest_id

        if full_off_table and full_aspect is not None and round(aspect, 2) == round(full_aspect, 2):
            return FULL_FRAME_RATIO_ID

        return f"{NATIVE_RATIO_PREFIX}{aspect:.2f}"

    def _default_ratio_ids(self, camera_name: str) -> List[str]:
        """The stock rule for a camera nobody has chosen ratios for (operator,
        2026-09-28, PLAN.md -- superseding 2026-09-26's "1.78:1 or closest";
        see aspect_ratios.PREFERRED_DELIVERY_RATIO_ID's comment for the full
        rationale and worked examples): PREFERRED_SHAPE_RATIO_ID ("1.33:1")
        if this camera OFFERS it, PREFERRED_DELIVERY_RATIO_ID ("1.78:1") if
        it offers that, then this camera's own full frame if it is known,
        offered, and not already selected.

        "Offers" means literal membership in available_aspect_ratios(camera)
        -- a mode whose own home_ratio_id() is that id -- never a stand-in
        found by searching for the nearest shape to a preference. That
        stand-in/mutual-nearest mechanism (_derived_default_ratio_ids,
        _stand_in_ratio_id) is gone: this is three plain membership checks in
        a fixed order.

        Never empty for a camera that offers any ratio at all: falls back to
        every ratio it offers when none of the three checks add anything (a
        camera with neither preferred ratio and no knowable full frame, e.g.
        an all-anamorphic sensor at 2.39:1/2.00:1 alone).
        """
        offered = self.available_aspect_ratios(camera_name)
        if not offered:
            return []

        selected: List[str] = []
        if PREFERRED_SHAPE_RATIO_ID in offered:
            selected.append(PREFERRED_SHAPE_RATIO_ID)
        if PREFERRED_DELIVERY_RATIO_ID in offered and PREFERRED_DELIVERY_RATIO_ID not in selected:
            selected.append(PREFERRED_DELIVERY_RATIO_ID)
        full_id, _ = self.full_frame_ratio(camera_name)
        if full_id and full_id in offered and full_id not in selected:
            selected.append(full_id)

        return selected or list(offered.keys())

    def _enabled_ratio_ids(self, camera_name: str) -> List[str]:
        """Precedence: an explicit per-camera entry in aspect_ratios_cfg
        wins; else the stock rule (_default_ratio_ids). NEVER a "default"
        entry (PLAN.md D2, 2026-09-28): a stray global choice left over from
        before per-sensor settings files existed is exactly the cross-sensor
        carrier that let an imx585 selection narrow an imx477 after a swap.
        See dropped_ratio_ids() for the saved ids this drops and why, and
        SensorDetect._finalize_modes for where a "default" entry's mere
        presence is surfaced as a one-time warning notice instead.

        A saved id this camera does not currently offer is dropped rather
        than applied (a driver swap, or a ratio pruned from the table); if
        EVERY saved id was dropped this falls back to the stock rule so the
        camera is never left with zero enabled toggles.
        """
        cfg = getattr(self, "aspect_ratios_cfg", None) or {}
        saved = cfg.get(camera_name)
        if not saved:
            return self._default_ratio_ids(camera_name)
        offered = self.available_aspect_ratios(camera_name)
        valid = [rid for rid in saved if rid in offered]
        return valid if valid else self._default_ratio_ids(camera_name)

    def dropped_ratio_ids(self, camera_name: str) -> List[str]:
        """Saved ratio ids this camera's saved selection names but does not
        currently offer -- PLAN.md's settings-editor contract field
        `dropped`. Ignored by _enabled_ratio_ids, reported here so the
        operator/GUI can say so instead of silently doing something other
        than what was saved."""
        cfg = getattr(self, "aspect_ratios_cfg", None) or {}
        saved = cfg.get(camera_name)
        if not saved:
            return []
        offered = self.available_aspect_ratios(camera_name)
        return [rid for rid in saved if rid not in offered]

    def _ratio_selection_is_derived(self, camera_name: str) -> bool:
        """True when nobody chose this camera's ratios and the set came from
        _default_ratio_ids. Mirrors _enabled_ratio_ids' precedence (never
        "default"), so the two cannot drift apart."""
        cfg = getattr(self, "aspect_ratios_cfg", None) or {}
        return not cfg.get(camera_name)

    def _ratio_matches_for_camera(self, camera_name: str, modes: List[Dict]) -> Dict[int, tuple]:
        """id(mode) -> (ratio_id, exact, real_aspect) for every mode whose
        own home_ratio_id() is one of the camera's enabled ratios.

        "No closest" (PLAN.md, 2026-09-28): a ratio yields EXACTLY the modes
        whose home is that ratio -- no tolerance union, no near-tie fallback,
        no separate "whole sensor" carve-out here, because home_ratio_id()
        already encodes all of that (the full-frame exception, the tolerance
        gate, the native-id fallback). exact is unconditionally True:
        home_ratio_id() never returns an id a mode does not actually belong
        to. Superseded WP-CM-11's version, which unioned two groups per ratio
        (a tolerance match, plus every mode whose home was that ratio however
        far away) specifically to work around the old rule's "nearest
        canonical ratio, whatever the distance" semantics -- home_ratio_id()
        no longer has that problem, since it never returns a ratio a mode
        merely resembles.
        """
        enabled = set(self._enabled_ratio_ids(camera_name))
        out: Dict[int, tuple] = {}
        for m in modes:
            rid = self.home_ratio_id(camera_name, m)
            if rid is not None and rid in enabled:
                out[id(m)] = (rid, True, self._mode_aspect(m))
        return out

    def available_aspect_ratios(self, camera_name: str) -> Dict[str, Dict[str, Any]]:
        """Which ratios this camera can actually produce: exactly the set of
        home_ratio_id() results across its raw, pre-filter mode table --
        never stored, because it depends on the driver installed right now
        and a cached answer would outlive it.

        "No closest" (PLAN.md, 2026-09-28): every entry is `exact: True` and
        `delta: 0.0`, because home_ratio_id() only ever returns an id a mode
        actually belongs to -- a table ratio it is within
        ASPECT_RATIO_TOLERANCE of, its own native shape (a
        NATIVE_RATIO_PREFIX id, `name: "Native"`, labelled "%.2f:1" % its
        aspect), or FULL_FRAME_RATIO_ID for a whole-sensor mode whose full
        frame is off-table. Superseded WP-CM-7's version, which resolved
        EVERY one of the table's fourteen ratios to this camera's closest
        mode regardless of distance (an "approximate" match, carrying a
        nonzero delta) -- a camera now offers only the ratios some mode of
        its own is actually home to, and a camera with no aspect-bearing
        modes at all returns {}.
        """
        modes = (getattr(self, "sensor_modes_unfiltered", None) or {}).get(camera_name) or []
        table_by_id = {e["id"]: e for e in self._aspect_ratio_table()}
        full_id, full_aspect = self.full_frame_ratio(camera_name)
        result: Dict[str, Dict[str, Any]] = {}
        for m in modes:
            rid = self.home_ratio_id(camera_name, m)
            if rid is None or rid in result:
                continue

            if rid == FULL_FRAME_RATIO_ID:
                # full_aspect is this camera's own whole-frame aspect --
                # always available here since home_ratio_id() only returns
                # FULL_FRAME_RATIO_ID when full_frame_ratio() already found
                # one. `is_full` and no "(full)" suffix: operator, 2026-09-22,
                # revising their own earlier request for the suffix -- it
                # reads as a plain ratio, because that is what it is.
                result[rid] = {
                    "id": rid, "value": full_aspect, "name": "Full frame",
                    "exact": True, "real_aspect": full_aspect, "delta": 0.0,
                    "is_full": True, "label": "%.2f:1" % full_aspect,
                }
                continue

            if rid.startswith(NATIVE_RATIO_PREFIX):
                aspect = self._mode_aspect(m)
                result[rid] = {
                    "id": rid, "value": aspect, "name": "Native",
                    "exact": True, "real_aspect": aspect, "delta": 0.0,
                    "is_full": False, "label": "%.2f:1" % aspect,
                }
                continue

            entry = table_by_id.get(rid, {})
            value = entry.get("value", self._mode_aspect(m))
            result[rid] = {
                "id": rid, "value": value, "name": entry.get("name", rid),
                "exact": True, "real_aspect": value, "delta": 0.0,
                # The full frame IS one of the table's fourteen on some
                # cameras (imx585 at 1.78) -- that toggle both offers this
                # shape AND covers the whole sensor, so is_full travels here
                # too rather than only on the off-table branch above.
                "is_full": full_id == rid,
                "label": rid,
            }
        return result

    def _order_modes(self, selected: List[Dict]) -> List[Dict]:
        """Order recording modes in the same class/geometry order used by the UI."""
        return sorted(selected, key=self._mode_sort_key)

    def _finalize_modes(
        self,
        sensors: Dict[str, List[Dict]],
    ) -> Dict[str, Dict[int, Dict]]:
        """Resolve per-sensor settings, add custom modes, apply the settings
        filters, order and index.

        F-298: a custom_modes entry whose (width, height, bit_depth, hdr)
        matches an already-detected mode overrides that mode's fps_max in
        place -- the sensor's advertised ceiling is an electrical property
        and says nothing about what this storage/CPU actually sustain, so
        it needs to be correctable, not just addable-to. Only fps_max is
        overridable this way; the rest of the detected mode (packing,
        gui_layout, aspect) is left alone. A non-matching entry still
        appends a brand-new mode exactly as before -- this only changes
        what happens when the dimensions already exist.
        """
        # ── resolve per-sensor settings (file > legacy > stock) ───────
        # Camera names are only known now, after the probe -- this is the
        # first point in the boot sequence _finalize_modes' caller can name
        # them. Runs before custom_modes are applied below, because a
        # per-sensor file's own custom_modes has to reach that loop the same
        # way a legacy settings.jsonc entry always has.
        #
        # Gated on hasattr(self, "settings_dir"): only a real SensorDetect,
        # built through __init__, ever sets that attribute (settings_dir=None
        # included -- it is always assigned, never left unset). A test double
        # built with SensorDetect.__new__ and its own hand-picked
        # aspect_ratios_cfg/enabled_modes/custom_modes never has it, so this
        # step is skipped for those and their direct attribute values are
        # used exactly as set -- this is what keeps this method's many
        # filter-only unit tests unaffected by the per-sensor-file layer.
        #
        # Two physical sensors of the same model (a dual-imx585 rig) share
        # one file here: both keys in *sensors* resolve through the identical
        # model name cinepi-raw reports, sensor_settings.sensor_settings_path
        # has no per-port concept, and that is intended -- the operator's
        # saved choice is a property of "the imx585 I own", not of which
        # physical port it is plugged into.
        if hasattr(self, "settings_dir"):
            image_capture_cfg = self.settings.get("image_capture") if isinstance(self.settings, dict) else None
            image_capture_cfg = image_capture_cfg if isinstance(image_capture_cfg, dict) else {}
            legacy_aspect_ratios_cfg = image_capture_cfg.get("aspect_ratios")
            # PLAN.md D2/2f: a stray global "default" survives on disk until
            # the operator saves through the new per-sensor mechanism (which
            # drops it -- settings_editor.put_settings). It is never read as
            # a value at any precedence level (legacy_sensor_settings/
            # _enabled_ratio_ids both key on the camera name only) -- this
            # only decides whether to warn that it is being ignored.
            self._default_ratio_ignored = bool(
                isinstance(legacy_aspect_ratios_cfg, dict)
                and legacy_aspect_ratios_cfg.get("default")
            )
            if self._default_ratio_ignored and not getattr(self, "_default_ratio_warned", False):
                logging.warning(
                    "image_capture.aspect_ratios has a \"default\" entry, "
                    "which is ignored: ratio selection is per camera now "
                    "(a per-camera key, or a per-sensor settings_<camera>"
                    ".jsonc file). Re-save each camera's ratios from the "
                    "settings page to drop it.",
                )
                self._default_ratio_warned = True

            for cam in sensors:
                resolved, source = sensor_settings.resolve_sensor_settings(
                    self.settings, cam, self.settings_dir,
                )
                self.sensor_settings_source[cam] = source
                if "aspect_ratios" in resolved:
                    self.aspect_ratios_cfg[cam] = resolved["aspect_ratios"]
                else:
                    self.aspect_ratios_cfg.pop(cam, None)
                if "enabled_modes" in resolved:
                    self.enabled_modes[cam] = resolved["enabled_modes"]
                else:
                    self.enabled_modes.pop(cam, None)
                # custom_modes has no "fall through to legacy" concept beyond
                # what resolve_sensor_settings already applied -- a missing
                # key here just means no custom modes for this camera.
                self.custom_modes[cam] = resolved.get("custom_modes") or []
        else:
            self._default_ratio_ignored = False

        # ── add or correct user-defined custom modes ─────────────────
        for cam, extras in self.custom_modes.items():
            # Only ever extend or correct a camera the probe actually found.
            # This used to be sensors.setdefault(cam, []), which invented the
            # camera when it wasn't detected -- so a settings.jsonc entry for
            # a sensor that isn't plugged in produced a fabricated mode table
            # for it. custom_modes exists to add modes to a real sensor and to
            # correct a detected fps_max (F-298), never to declare a camera.
            if cam not in sensors:
                logging.warning(
                    "custom_modes has an entry for %s, which was not detected "
                    "-- ignoring it. custom_modes extends a camera that is "
                    "present; it cannot declare one that isn't.", cam,
                )
                continue
            for extra in extras:
                w, h = int(extra["width"]), int(extra["height"])
                bd   = int(extra["bit_depth"])
                fps  = extra.get("fps_max")
                # A 16-bit entry that says nothing about ClearHDR is a
                # ClearHDR entry: RAW16 exists on the imx585 only with
                # wide_dynamic_range on, the same rule the parser applies to
                # a 16-bit line. Without it a hand-written 16-bit fps ceiling
                # could never match the detected 16-bit mode and would be
                # added as a second, SDR-tagged copy of it instead.
                hdr_flag = bool(extra.get("hdr", bd == 16))
                def custom_match(m):
                    if (
                        int(m.get("width") or 0) != w or
                        int(m.get("height") or 0) != h or
                        int(m.get("bit_depth") or 0) != bd or
                        bool(m.get("hdr")) != hdr_flag
                    ):
                        return False

                    # A custom entry that does not specify geometry is an FPS
                    # override for the detected mode. If geometry is supplied,
                    # require it to match so a genuinely distinct windowed
                    # mode can still be added intentionally.
                    geometry_fields = ("crop_x", "crop_y", "crop_width", "crop_height")
                    if any(extra.get(k) is not None for k in geometry_fields):
                        for k in geometry_fields:
                            if extra.get(k) is not None and m.get(k) != extra.get(k):
                                return False

                    if extra.get("binning_x") is not None and m.get("binning_x") != extra.get("binning_x"):
                        return False
                    if extra.get("binning_y") is not None and m.get("binning_y") != extra.get("binning_y"):
                        return False
                    return True

                candidates = [m for m in sensors[cam] if custom_match(m)]
                if candidates:
                    # Prefer a fully described full-frame mode for a geometry-
                    # unspecified FPS override; this keeps legacy custom_modes
                    # deterministic when a driver exposes both a native mode
                    # and a windowed mode at the same output size.
                    existing = sorted(
                        candidates,
                        key=lambda m: (
                            0 if self._mode_is_full(m) else 1,
                            0 if self._mode_binning(m)[0] is not None else 1,
                        ),
                    )[0]
                else:
                    existing = None
                if existing is not None:
                    if fps is not None:
                        detected_fps = existing.get("fps_max")
                        if detected_fps is not None and fps > detected_fps:
                            logging.warning(
                                "custom_modes override for %s %dx%d (%d-bit%s) raises "
                                "fps_max from the detected %s to %s -- the sensor did "
                                "not report this; if storage/CPU can't actually sustain "
                                "it, lower the value instead of raising it.",
                                cam, w, h, bd, " HDR" if hdr_flag else "",
                                detected_fps, fps,
                            )
                        # Stash the sensor's own value before overwriting it --
                        # the settings editor shows this as the "detected"
                        # placeholder next to the editable effective value.
                        existing.setdefault("fps_max_detected", detected_fps)
                        existing["fps_max"] = fps
                    continue
                sensors[cam].append(
                    self._mode_from_metadata_or_detected(
                        camera_name=cam,
                        width=w,
                        height=h,
                        bit_depth=bd,
                        fps_max=fps,
                        hdr=hdr_flag,
                        extra=extra,
                    )
                )

        # Deduplicate modes after the plain/HDR probes and custom-mode
        # expansion. Some libcamera/cinepi-raw combinations report the same
        # mode more than once (often with the same geometry but a slightly
        # different advertised FPS). FPS is not part of mode identity: a
        # single sensor mode must not become two operator choices just because
        # the probe returned two timing ceilings.
        for cam, modes in list(sensors.items()):
            unique = {}
            for m in modes:
                key = self._mode_identity(m) + (
                    self._mode_binning(m),
                )
                existing = unique.get(key)
                if existing is None:
                    unique[key] = m
                    continue
                # Preserve the higher detected ceiling, but also merge
                # driver metadata from a duplicate occurrence. A mode can be
                # encountered once through a plain probe/custom expansion and
                # once through a probe that carries the driver's crop annotation.
                # The mode identity deliberately includes geometry, but legacy
                # entries without geometry can still collide with a richer
                # occurrence. Never let the poorer occurrence erase geometry.
                for field in (
                    "crop_x", "crop_y", "crop_width", "crop_height",
                    "sensor_width", "sensor_height", "binning_x", "binning_y",
                ):
                    if existing.get(field) is None and m.get(field) is not None:
                        existing[field] = m[field]

                a = existing.get("fps_max")
                b = m.get("fps_max")
                if a is None and b is not None:
                    existing["fps_max"] = b
                elif a is not None and b is not None:
                    try:
                        existing["fps_max"] = max(float(a), float(b))
                    except (TypeError, ValueError):
                        pass
            sensors[cam] = list(unique.values())

        # Keep the raw sensor mode inventory before settings filters, but
        # after structural deduplication. The settings editor/API uses this
        # inventory to show every detected mode. Publishing it before dedup
        # made repeated probe timings (for example 67 fps + 30 fps for the
        # same 3840x2160 SDR readout) appear as duplicate rows.
        self.sensor_modes_unfiltered = dict(
            getattr(self, "sensor_modes_unfiltered", {}),
            **{cam: [dict(m) for m in modes] for cam, modes in sensors.items()},
        )

        # ── filter & index (aspect ratios / k-steps / bit depths / hdr) ──
        pruned: Dict[str, Dict[int, Dict]] = {}
        for cam, modes in sensors.items():
            mode_entries = (getattr(self, "enabled_modes", {}) or {}).get(cam)
            use_individual_selection = isinstance(mode_entries, list) and len(mode_entries) > 0

            # An explicit enabled_modes choice is resolved once, for the whole
            # camera, because the exact-then-coarse fallback is a property of
            # the SELECTION and not of any single mode: "did anything match at
            # all" cannot be answered inside a per-mode test.
            enabled_tier = "exact"
            if use_individual_selection:
                _keep, enabled_tier = self._match_enabled_modes(modes, mode_entries)

            # PLAN.md's dial rule (2026-09-28, fixing D4): selected AND its
            # ratio toggle enabled, for an explicit enabled_modes choice
            # exactly as much as for the stock/ratio-driven path. Before this,
            # enabled_modes bypassed the ratio filter entirely, so a mode
            # explicitly enabled under a ratio the operator later hid stayed
            # selected and reachable -- the pane could show a toggle off while
            # the dial still held modes behind it.
            enabled_ratio_ids = set(self._enabled_ratio_ids(cam))
            dropped_ids = self.dropped_ratio_ids(cam)
            # getattr: same "no opinion on an instance built with __new__"
            # convention as mode_selection_notices below -- only a real
            # SensorDetect's __init__ pre-creates this dict.
            dropped_by_camera = getattr(self, "sensor_settings_dropped", None)
            if dropped_by_camera is None:
                dropped_by_camera = {}
                self.sensor_settings_dropped = dropped_by_camera
            dropped_by_camera[cam] = dropped_ids

            selected = []
            for m in modes:
                # Every mode gets its home ratio, unconditionally -- unlike
                # the old ratio-matcher branch, which only annotated a mode it
                # was actively filtering. Consumers of `pruned` (the dial) can
                # now see which toggle EVERY row belongs to, selected or not.
                rid = self.home_ratio_id(cam, m)
                m["aspect_ratio_id"] = rid
                # "No closest" (PLAN.md 2026-09-28): a mode with a known
                # aspect always has an exact home -- see home_ratio_id()'s own
                # docstring for the tolerance-gated/native/full-frame cases it
                # covers. None only when the mode has no known aspect at all.
                m["aspect_ratio_exact"] = True if rid is not None else None
                m["aspect_ratio_real"] = self._mode_aspect(m)

                if not self.mode_selected(cam, m):
                    continue
                if rid not in enabled_ratio_ids:
                    continue
                selected.append(m)

            # WP-CM-6 item 5: the width floor. Hidden, not removed -- the
            # narrow mode stays reachable in sensor_modes_unfiltered for the
            # settings editor to offer by hand. An explicit per-mode choice is
            # never subject to it -- small sensor modes are valid modes and
            # must reach the resolution picker when the operator enables them.
            # getattr: same "no opinion on an instance that never set this"
            # convention as aspect_ratios_cfg/clear_hdr_depths elsewhere here.
            if not use_individual_selection:
                floor = getattr(self, "min_mode_width", None)
                if floor:
                    selected = [m for m in selected if int(m.get("width") or 0) >= floor]

            # Never leave a camera without modes -- but never do it silently
            # either. Swapping the operator's chosen selection for the ENTIRE
            # table reads as "my setting was ignored", which is exactly how this
            # surfaced: one mode selected in the settings page, seventy-three in
            # the dial. The notice below is what the GUI shows so the widening
            # is visible instead of mysterious. Priority, highest first: an
            # invalidated explicit choice, then a saved ratio this camera no
            # longer offers, then the global "default" leftover, then (if
            # `selected` is STILL empty after all of the above) the generic
            # "filters excluded everything" fallback -- which fires
            # regardless of whether a higher-priority notice already did,
            # because the empty-selection widening always needs to be visible.
            notice = None
            if use_individual_selection and enabled_tier == "coarse":
                notice = {
                    "kind": "geometry_changed",
                    "text": (
                        "Your saved mode selection was matched by size only: "
                        "the driver now reports different crop geometry than "
                        "when it was saved. Re-pick your modes to store the "
                        "current geometry."
                    ),
                }
                logging.warning(
                    "%s: enabled_modes matched by size only (crop geometry "
                    "changed since it was saved) -- %d mode(s) kept",
                    cam, len(selected),
                )
            elif use_individual_selection and enabled_tier == "none":
                notice = {
                    "kind": "selection_unmatched",
                    "text": (
                        "None of your saved modes exist in this driver's mode "
                        "table, so every mode is being offered. Re-pick your "
                        "modes in the settings page."
                    ),
                }
                logging.warning(
                    "%s: enabled_modes matched NOTHING (not even by size) -- "
                    "falling back to the full table of %d modes",
                    cam, len(modes),
                )
            elif dropped_ids:
                notice = {
                    "kind": "ratios_not_offered",
                    "text": (
                        "Some of this camera's saved aspect ratios (%s) are "
                        "not offered by the current driver and are being "
                        "ignored." % ", ".join(dropped_ids)
                    ),
                }
                logging.warning(
                    "%s: saved aspect ratios %s are not offered -- ignoring them",
                    cam, dropped_ids,
                )
            elif getattr(self, "_default_ratio_ignored", False):
                notice = {
                    "kind": "default_ratio_ignored",
                    "text": (
                        "settings.jsonc has a global \"default\" aspect-ratio "
                        "entry, which is now ignored -- ratio selection is per "
                        "camera. Re-save this camera's ratios from the "
                        "settings page to remove it."
                    ),
                }

            if not selected:
                if notice is None:
                    notice = {
                        "kind": "filters_excluded_everything",
                        "text": (
                            "No mode passed the current filters, so every mode "
                            "is being offered. Check the aspect-ratio, bit-depth "
                            "and resolution filters in the settings page."
                        ),
                    }
                    logging.warning("No modes passed the filters for %s – "
                                    "keeping full list instead", cam)
                selected = modes

            # getattr: _finalize_modes is reachable on an instance built with
            # __new__ (many tests do exactly that, setting only the filter
            # attributes they care about), and the same "no opinion" convention
            # the other optional attributes use applies here.
            notices = getattr(self, "mode_selection_notices", None)
            if notices is None:
                notices = {}
                self.mode_selection_notices = notices
            if notice is not None:
                notices[cam] = notice
            else:
                notices.pop(cam, None)

            pruned[cam] = {i: m for i, m in enumerate(self._order_modes(selected))}
        return pruned

    @staticmethod
    def _running_cinepi_raw_pids() -> List[str]:
        try:
            result = subprocess.run(
                ["pgrep", "-x", "cinepi-raw"], capture_output=True, text=True,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logging.debug("Could not check for a running cinepi-raw process: %s", exc)
            return []
        return [pid for pid in result.stdout.split() if pid.strip()]

    def _kill_stale_cinepi_raw(self, timeout: float = 3.0) -> None:
        """Kill any cinepi-raw process already running before probing sensor
        modes.

        detect_camera_model() runs once, at Cinemate startup -- before
        Cinemate has launched its own cinepi-raw child, so any cinepi-raw
        found here is orphaned (e.g. a botched previous restart, or a manual
        test session left running). If it isn't killed first, the
        ``--hdr sensor`` probe can't actually toggle wide_dynamic_range on a
        sensor subdev the orphan already holds (V4L2 reports the control as
        "grabbed"), so ClearHDR/16-bit modes silently vanish from this
        session's mode table instead of the probe failing loudly.
        """
        pids = self._running_cinepi_raw_pids()
        if not pids:
            return
        logging.warning(
            "Found stale cinepi-raw process(es) %s at startup -- killing before "
            "probing sensor modes so ClearHDR/16-bit detection isn't silently "
            "degraded by an already-held sensor subdev.", pids,
        )
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGKILL)
            except (ValueError, ProcessLookupError, PermissionError) as exc:
                logging.warning("Failed to kill stale cinepi-raw pid %s: %s", pid, exc)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._running_cinepi_raw_pids():
                return
            time.sleep(0.1)
        logging.warning(
            "Stale cinepi-raw process(es) %s did not exit within %.1fs -- "
            "ClearHDR/16-bit mode detection may still be degraded this session.",
            pids, timeout,
        )

    def _list_cameras(self, hdr: bool = False) -> str:
        """Run ``cinepi-raw --list-cameras`` (optionally with ``--hdr sensor``).

        Returns stdout, or "" when the run fails. The HDR run is best-effort:
        a cinepi-raw build without ClearHDR support just yields no extra modes.
        """
        # Probe under the same pixel-rate ceiling the real launch will use, so
        # the mode table cannot advertise a frame rate the configured RP1
        # regime could never sustain. Harmless if libcamera turns out to apply
        # the bound only at configure time rather than during enumeration --
        # that is what hardware gate G2 settles.
        max_pixel_rate = rp1_regime.pixel_rate()
        rate_arg = f" --max-pixel-rate {max_pixel_rate}" if max_pixel_rate is not None else ""
        cmd = "cinepi-raw --list-cameras" + rate_arg + (" --hdr sensor" if hdr else "")
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        except Exception as exc:  # pragma: no cover - defensive
            logging.warning("'%s' failed: %s", cmd, exc)
            return ""
        return proc.stdout or ""


    # ────────────────────────────────────────────────────────────────
    #  2.  Discover sensors once, cache every model’s modes
    # ────────────────────────────────────────────────────────────────
    def detect_camera_model(self):
        """
        Runs *cinepi-raw --list-cameras* twice — once plain and once with
        ``--hdr sensor`` — fills ``self.sensor_resolutions`` with **all**
        detected cameras (plain + ClearHDR modes), and chooses the first one as
        ``self.camera_model`` (the caller may later override this).
        """
        try:
            self._kill_stale_cinepi_raw()

            out = self._list_cameras(hdr=False)
            logging.info("cinepi-raw output:\n%s", out)

            if not out.strip():
                logging.warning("No output from cinepi-raw")
                self.camera_model = None
                self.res_modes = {}
                return

            # Second pass exposes the imx585 ClearHDR (16-bit + 12-bit HDR)
            # modes; a sensor that ignores --hdr sensor prints its plain
            # listing again, which _normalize_hdr_probe_modes refuses to
            # promote and _merge_mode_lists then collapses.
            hdr_out = self._list_cameras(hdr=True)
            if hdr_out.strip():
                logging.info("cinepi-raw --hdr sensor output:\n%s", hdr_out)

            # The plain probe is the SDR state: the parser stops at the
            # ClearHDR marker cinepi-raw prints on every --list-cameras run,
            # so the ClearHDR section is read only below, as ClearHDR.
            base_modes = self._parse_cinepi_output(out, hdr=False)

            # Parse the HDR probe by its explicit state boundary. The
            # output is a two-state listing on IMX585: SDR first, then the
            # literal "CLEAR HDR / SENSOR HDR" marker, then the ClearHDR
            # camera header and modes. Splitting here makes the provenance
            # unambiguous and avoids depending on camera-header repetition.
            hdr_modes = {}
            if hdr_out.strip():
                marker = CLEAR_HDR_MARKER_RE.search(hdr_out)
                if marker:
                    # Everything after the marker is the ClearHDR state, and
                    # the parser is told so up front (clear_hdr_section)
                    # instead of being run in the SDR state and re-tagged
                    # afterwards: run that way it dropped every 16-bit line
                    # before the re-tag could reach it.
                    hdr_modes = self._parse_cinepi_output(
                        hdr_out[marker.end():], hdr=True, clear_hdr_section=True,
                    )
                    logging.info(
                        "ClearHDR marker found: parsed %d modes across %d cameras",
                        sum(len(m) for m in hdr_modes.values()),
                        len(hdr_modes),
                    )
                else:
                    # Some sensors/builds expose only an HDR listing. In that
                    # case the dedicated invocation itself is the provenance;
                    # never infer HDR from FPS.
                    hdr_modes = self._parse_cinepi_output(hdr_out, hdr=True)
                    self._normalize_hdr_probe_modes(base_modes, hdr_modes)

            merged = self._merge_mode_lists(base_modes, hdr_modes)

            # The two states of the IMX585 probe should carry identical driver
            # geometry for an identical transport mode. If a libcamera/rpicam
            # build omits the optional geometry annotation on one state, copy
            # it from the matching state rather than presenting a known crop as
            # "Geometry not reported". Never infer geometry from the output
            # dimensions: the source must be another explicitly annotated mode.
            for cam, modes in merged.items():
                for mode in modes:
                    if mode.get("crop_width") is not None:
                        continue
                    matches = [
                        other for other in modes
                        if other is not mode
                        # SDR and ClearHDR are two sensor states of the
                        # same physical readout. Geometry is transport/readout
                        # metadata, not an HDR property, so an annotation from
                        # the plain probe is also authoritative for the matching
                        # ClearHDR mode (and vice versa).
                        and int(other.get("width") or 0) == int(mode.get("width") or 0)
                        and int(other.get("height") or 0) == int(mode.get("height") or 0)
                        and int(other.get("bit_depth") or 0) == int(mode.get("bit_depth") or 0)
                        and other.get("crop_width") is not None
                    ]
                    if len(matches) == 1:
                        source_mode = matches[0]
                        for key in (
                            "crop_x", "crop_y", "crop_width", "crop_height",
                            "sensor_width", "sensor_height",
                            "binning_x", "binning_y",
                        ):
                            if source_mode.get(key) is not None:
                                mode[key] = source_mode[key]

            # The HDR probe "succeeding" (non-empty output) but adding zero new
            # modes means --hdr sensor couldn't actually change what the sensor
            # reports. On a sensor with no ClearHDR at all (imx283, imx477,
            # imx296) that is the expected outcome and the whole point of the
            # collapse above. On one that does have it, the usual cause is
            # another process (see _kill_stale_cinepi_raw above) still holding
            # the subdev, and shipping a mode table silently missing ClearHDR is
            # the failure this warning exists to make visible -- so it stays
            # loud, and says both things rather than asserting the second.
            if hdr_out.strip():
                added = sum(
                    len(merged.get(cam, [])) - len(base_modes.get(cam, []))
                    for cam in merged
                )
                if added == 0:
                    logging.warning(
                        "ClearHDR probe (--hdr sensor) returned no modes beyond "
                        "the plain probe. Expected on a sensor without ClearHDR. "
                        "If this sensor supports ClearHDR (e.g. imx585), 16-bit "
                        "modes are unavailable this session -- likely because "
                        "something already held the sensor subdev when Cinemate "
                        "started."
                    )

            # No camera header line parsed. This is NOT the same test as the
            # `not out.strip()` one above: cinepi-raw prints "No cameras
            # available!" to stdout, so the output is non-empty and that
            # guard never fires. Stop here rather than in _finalize_modes(),
            # because the custom_modes loop there would otherwise manufacture
            # a camera out of a settings key -- leaving res_modes non-empty
            # and camera_model set on a boot with no sensor attached, which
            # bypasses every `if not res_modes` degraded-boot guard in
            # cinepi_controller.py and storage_preroll.py.
            if not merged:
                logging.warning(
                    "No camera parsed from the cinepi-raw listing -- treating "
                    "this as no camera attached."
                )
                self.camera_model = None
                self.res_modes = {}
                return

            # full assembly → {model → {mode_idx → mode_dict}}
            sensors = self._finalize_modes(merged)

            if not sensors:
                logging.warning("No cameras parsed")
                self.camera_model = None
                self.res_modes = {}
                return

            # merge (allows hot-plug re-detect)
            self.sensor_resolutions.update(sensors)

            # choose a default model if the current one isn’t valid
            if self.camera_model not in sensors:
                self.camera_model = next(iter(sensors))

            logging.info("Detected camera models: %s (default: %s)",
                         list(sensors.keys()), self.camera_model)

            self.load_sensor_resolutions()      # sets self.res_modes

        except Exception as e:
            logging.error("detect_camera_model() failed: %s", e)
            self.camera_model = None
            self.res_modes = {}

    def check_camera(self):
        self.detect_camera_model()
        return self.camera_model

    def mode_selection_notice(self, camera_name: str):
        """The notice for *camera_name*, or None when its selection resolved
        cleanly. See _finalize_modes: a notice means the operator is being shown
        something other than what their own settings asked for."""
        return (getattr(self, "mode_selection_notices", None) or {}).get(camera_name)

    def load_sensor_resolutions(self):
        if self.camera_model in self.sensor_resolutions:
            self.res_modes = self.sensor_resolutions[self.camera_model]
        else:
            logging.error(f"Unknown camera model: {self.camera_model}")
            self.res_modes = {}

    def get_sensor_resolution(self, mode):
        return self.res_modes.get(mode, {})
    
    def get_resolution_info(self, camera_name: str, sensor_mode: int) -> Dict:
        """
        Return mode dict for *camera_name* and *sensor_mode*.
        If the requested mode is missing, fall back to the first available
        mode so callers always get valid width/height/fps values.
        """
        if camera_name not in self.sensor_resolutions:
            logging.error("Unknown camera model: %s", camera_name)
            return {'width': None, 'height': None, 'fps_max': None,
                    'gui_layout': None}

        modes = self.sensor_resolutions[camera_name]
        sensor_mode = int(sensor_mode)

        if sensor_mode not in modes:
            logging.warning("Sensor mode %d not found for %s – "
                            "using mode 0 instead", sensor_mode, camera_name)
            return next(iter(modes.values()))  # first (usually 0)

        return modes[sensor_mode]


    def get_fps_max(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('fps_max', None)
    
    def get_gui_layout(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('gui_layout', None)
    
    def get_width(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('width', None)
    
    def get_height(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('height', None)
    
    def get_bit_depth(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('bit_depth', None)
    
    def get_packing(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('packing', None)

    def get_packing_for_platform(self, camera_name, sensor_mode, is_pi4=None):
        """Return the packing token ('P'/'U') for *camera_name*/*sensor_mode* on
        the current platform.

        Resolution order (most specific wins):
          1. the matching mode's ``packing_by_platform[platform]`` in sensors.json
          2. the sensor's ``packing_by_platform[platform]`` in sensors.json
          3. the sensor's default packing (mode/sensor ``packing`` or fallback)

        ``is_pi4`` selects the platform key ('pi4' vs 'pi5'); when left as None it
        is auto-detected with :func:`is_pi4_family`, so callers that do not track
        the Pi model still get the right answer. Data-driving this from
        sensors.json replaces the old hardcoded per-sensor Pi-4 override.
        """
        res = self.get_resolution_info(camera_name, sensor_mode)
        base = str(res.get('packing') or 'U').upper()

        if is_pi4 is None:
            is_pi4 = is_pi4_family()
        platform = 'pi4' if is_pi4 else 'pi5'

        sensor_info = self._sensor_database_entry(camera_name) or {}
        mode_meta = self._sensor_mode_metadata(
            camera_name,
            res.get('width') or 0,
            res.get('height') or 0,
            res.get('bit_depth'),
        )
        for source in (mode_meta, sensor_info):
            overrides = source.get('packing_by_platform') if isinstance(source, dict) else None
            if isinstance(overrides, dict):
                value = overrides.get(platform)
                if value:
                    return str(value).strip().upper()
        return base

    def _log_encode_info(self, camera_name: str | None) -> dict[str, Any] | None:
        """Return sensors.json's ``log_encode`` block for *camera_name*, or
        None when absent. Absence means the sensor is unsupported — there is
        no special-casing here, mirroring how ``packing_by_platform`` absence
        just falls through to the default packing above.
        """
        sensor_info = self._sensor_database_entry(camera_name)
        if not sensor_info:
            return None
        log_encode = sensor_info.get('log_encode')
        return log_encode if isinstance(log_encode, dict) else None

    def supports_log_encode(self, camera_name: str | None) -> bool:
        """True when *camera_name* has a ``log_encode`` block in sensors.json."""
        return self._log_encode_info(camera_name) is not None

    def get_log_encode_targets(self, camera_name: str | None) -> dict[int, dict[str, Any]]:
        """Return ``{source_bit_depth: {'valid': [target, ...], 'default': target}}``
        for *camera_name*, or ``{}`` when the sensor has no ``log_encode`` block.

        This is capability data only. ``valid`` is every target whose spec
        matches this sensor's black level for that source depth (imx585
        16-bit has both a 16to10 and a 16to12 spec); ``default`` is the one
        a bare toggle picks. Resolving a live target from the camera's
        current mode is :meth:`resolve_log_encode_target`.
        """
        info = self._log_encode_info(camera_name)
        if not info:
            return {}
        targets = info.get('targets')
        if not isinstance(targets, dict):
            return {}
        result: dict[int, dict[str, Any]] = {}
        for source_bits, spec in targets.items():
            try:
                source_key = int(source_bits)
            except (TypeError, ValueError):
                continue
            if not isinstance(spec, dict):
                continue
            valid = [int(t) for t in (spec.get('valid') or [])]
            default = spec.get('default')
            result[source_key] = {
                'valid': valid,
                'default': int(default) if default is not None else None,
            }
        return result

    def get_log_encode_valid_targets(self, camera_name: str | None, source_bit_depth: int | None) -> list[int]:
        """Return the target depths *camera_name* supports from
        *source_bit_depth*, or ``[]`` when there is no matching spec (the
        sensor is unsupported, or this source depth has none)."""
        if source_bit_depth is None:
            return []
        entry = self.get_log_encode_targets(camera_name).get(int(source_bit_depth))
        return list(entry['valid']) if entry else []

    def get_log_encode_default_target(self, camera_name: str | None, source_bit_depth: int | None) -> int | None:
        """Return the default (bare-toggle) target for *camera_name* at
        *source_bit_depth*, or None when this source depth has no spec."""
        if source_bit_depth is None:
            return None
        entry = self.get_log_encode_targets(camera_name).get(int(source_bit_depth))
        return entry['default'] if entry else None

    def resolve_log_encode_target(
        self,
        camera_name: str | None,
        source_bit_depth: int | None,
        requested: int | None = None,
        hdr: bool = False,
    ) -> int | None:
        """Resolve the ``--log-encode`` target for *camera_name* currently
        running at *source_bit_depth*.

        ``requested=None`` (a bare ``set log`` toggle) resolves to this
        source depth's default (16-bit -> 12, 12-bit -> 10). An explicit
        ``requested`` (e.g. ``set log 10`` to force 16-bit down to 16to10
        instead of the 16to12 default) is returned only when it is one of
        this sensor/source-depth's valid targets; otherwise None — this
        never silently substitutes a different target than what was asked
        for or implied.

        *hdr* is whether the launch will carry ``--hdr sensor``. It is not
        used to refuse anything here (see below) — it is accepted so the
        call site never has to special-case ClearHDR itself.
        """
        # ── 12-bit ClearHDR (CCMP) is not a special case here ────────────
        #
        # 12-bit ClearHDR companies on-sensor (CCMP), so it is not a LINEAR
        # log source. That used to make this function refuse it outright
        # (return None whenever hdr and source_bit_depth == 12), because
        # cinepi-raw could only log-encode a linear 12-bit source and would
        # otherwise compand the already-companded data a second time.
        #
        # cinepi-raw now composes instead: decompand to 16-bit linear first
        # (the CCMP curve, itself gated), then apply the 16-to-target log
        # curve — see get_ccmp_composed_log_lut() / log_source_is_companded()
        # in cinepi-raw's cinepi/log_lut.hpp. From cinemate's side that is
        # invisible: it is still "12-bit source -> target 10", exactly what
        # sensors.json's imx585 "12": {"valid":[10],"default":10} already
        # says, hdr or not. So *hdr* no longer changes this function's
        # answer — it is kept as a parameter only so callers that pass it
        # (there is exactly one valid target either way) do not need editing.
        valid = self.get_log_encode_valid_targets(camera_name, source_bit_depth)
        if not valid:
            return None
        if requested is None:
            return self.get_log_encode_default_target(camera_name, source_bit_depth)
        try:
            requested_target = int(requested)
        except (TypeError, ValueError):
            return None
        return requested_target if requested_target in valid else None

    def resolve_effective_bit_depth(
        self,
        camera_name: str | None,
        native_bit_depth: int | None,
        *,
        log_requested: bool | int = False,
        hdr: bool = False,
    ) -> int | None:
        """Return the bit depth DNG frames are actually written at: the
        resolved --log-encode target when CineMate Log applies for this
        sensor/mode/request, else *native_bit_depth* unchanged.

        *log_requested* is the live `set log` request -- False/True/10/12,
        e.g. from redis_controller.decode_log_encode_request(). Mirrors the
        --log-encode resolution CinePiProcess._build_args() applies at
        launch (cinepi_multi.py) so file-size estimates always match what
        cinepi-raw will actually write.
        """
        if native_bit_depth is None:
            return None
        if not log_requested:
            return native_bit_depth
        target = self.resolve_log_encode_target(
            camera_name, native_bit_depth,
            requested=None if log_requested is True else log_requested,
            hdr=hdr,
        )
        return target if target is not None else native_bit_depth

    def get_log_encode_black_level_16bit(self, camera_name: str | None) -> int | None:
        """Return sensors.json's ``log_encode.black_level_16bit`` for
        *camera_name*, or None when the sensor has no ``log_encode`` block."""
        info = self._log_encode_info(camera_name)
        if not info:
            return None
        black_level = info.get('black_level_16bit')
        return int(black_level) if black_level is not None else None

    def get_file_size(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('file_size', None)


    def _calc_lores(self, sensor_w: int, sensor_h: int) -> tuple[int, int]:
        """Return the PiSP lores preview size for a sensor aspect ratio.

        Keep the lores stream at the established preview geometry rather than
        shrinking it to tiny sensor readouts.  The small IMX585 modes are
        valid capture modes, but using their native dimensions as the lores
        stream regressed the live preview to black.  cinepi-raw/PiSP can scale
        the small sensor image into this preview stream; this is also the
        geometry used by the preview path before the small-mode picker was
        exposed.

        Thin, crop-blind wrapper (no `self` access -- called unbound as
        `SensorDetect._calc_lores(None, w, h)` from several tests) over the
        shared compute_preview_geometry(); see get_lores_width()/
        get_lores_height() for the crop-aware entry points WP-CM-1 added.
        """
        geometry = compute_preview_geometry(
            {"width": sensor_w, "height": sensor_h}, 1920, 1080,
        )
        lw = geometry["lores_width"] & ~1
        lh = geometry["lores_height"] & ~1
        return lw, lh

    def get_lores_width(self, camera_name, sensor_mode):
        res = self.get_resolution_info(camera_name, sensor_mode)
        geometry = compute_preview_geometry(res, 1920, 1080)
        return geometry["lores_width"] & ~1

    def get_lores_height(self, camera_name, sensor_mode):
        res = self.get_resolution_info(camera_name, sensor_mode)
        geometry = compute_preview_geometry(res, 1920, 1080)
        return geometry["lores_height"] & ~1
    
    def get_hdr(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return bool(resolution_info.get('hdr', False))

    def get_available_resolutions(self):
        """Return resolutions ordered by the four operator-facing groups.

        The dropdown renderer inserts one separator when the group changes.
        Therefore the backend must make each group contiguous; iterating
        res_modes in discovery/index order can otherwise interleave HDR/SDR or
        bit-depth groups and produce repeated dashed lines.
        """
        group_rank = {
            (True, 16): 0,
            (True, 12): 1,
            (False, 12): 2,
            (False, 10): 3,
        }
        items = []
        for mode, info in self.res_modes.items():
            group = (
                bool(info.get('hdr')),
                int(info.get('bit_depth') or 0),
            )
            items.append((group_rank.get(group, 99), mode, info))

        def sort_key(item):
            rank, mode, info = item
            bx = int(info.get('binning_x') or 1)
            by = int(info.get('binning_y') or 1)
            area = int(info.get('width') or 0) * int(info.get('height') or 0)
            crop_x = int(info.get('crop_x') or 0)
            crop_y = int(info.get('crop_y') or 0)
            return (rank, bx * by, -area, crop_x, crop_y, int(mode))

        items.sort(key=sort_key)

        resolutions = []
        for rank, mode, info in items:
            group = (
                bool(info.get('hdr')),
                int(info.get('bit_depth') or 0),
            )
            resolution = f"{info['width']} : {info['height']} : {info['bit_depth']}b"
            if info.get('hdr'):
                resolution += " :HDR"
            resolutions.append({
                'mode': mode,
                'resolution': resolution,
                'group': group,
                'group_label': (
                    ("Clear HDR" if info.get('hdr') else "Standard")
                    + f" · {info['bit_depth']}-bit"
                ),
            })
        return resolutions
