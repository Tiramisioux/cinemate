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

DEFAULT_SENSOR_DATABASE_FILE = "resources/sensors.json"
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
    def __init__(self, settings=None):
        self.camera_model = None
        self.res_modes = {}
        self.settings = settings or {}
        res_cfg = self.settings.get("image_capture", {})
        self.k_steps = res_cfg.get("k_steps", [])
        self.bit_depths = res_cfg.get("bit_depths", [])
        self.custom_modes = res_cfg.get("custom_modes", {})
        # Per-mode operator selection. An absent camera entry preserves the
        # legacy k_steps/bit_depths filters for backward compatibility.
        self.enabled_modes = res_cfg.get("enabled_modes", {})
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
        mode = {
            "aspect": extra.get("aspect", metadata.get("aspect", round(width / height, 2))),
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
            "crop_x": extra.get("crop_x"),
            "crop_y": extra.get("crop_y"),
            "crop_width": extra.get("crop_width"),
            "crop_height": extra.get("crop_height"),
            "binning_x": extra.get("binning_x", metadata.get("binning_x")),
            "binning_y": extra.get("binning_y", metadata.get("binning_y")),
            # ClearHDR flag (imx585). A mode is HDR when it is reported only
            # by `cinepi-raw --list-cameras --hdr sensor`; selecting it makes
            # cinepi-raw launch with --hdr sensor. See detect_camera_model().
            "hdr": bool(extra.get("hdr", hdr)),
        }
        return mode

    # ────────────────────────────────────────────────────────────────
    #  1.  Parse *all* cameras and all modes that cinepi-raw reports    
    # ────────────────────────────────────────────────────────────────
    def _parse_cinepi_output(self, output: str, hdr: bool = False) -> Dict[str, List[Dict]]:
        """
        Return a mapping   {camera_model → [mode_dict, …]}   covering every
        camera found in a single *cinepi-raw --list-cameras* run. A mono sensor
        is reported as “<model>_mono”. ``hdr`` tags every mode parsed from a
        ``--hdr sensor`` run; the caller merges the plain and HDR runs.
        """

        sensors: Dict[str, List[Dict]] = {}
        current_cam = None
        current_bit_depth = None
        parsing_modes = False                     # inside a “Modes:” block?

        for raw in output.splitlines():
            line = raw.rstrip("\n")

            # ── camera header  e.g.  “0 : imx283 [5472x3648 …] (…)”
            m = re.match(r"^\s*\d+\s*:\s*([^\s]+)(?:\s*\[.*?(MONO)?\])?", line)
            if m:
                # flush state & start a new camera section
                current_cam = m.group(1)
                if m.group(2) == "MONO":
                    current_cam += "_mono"
                sensors.setdefault(current_cam, [])
                current_bit_depth = None
                parsing_modes = False
                continue

            # we can’t do anything without a current camera
            if current_cam is None:
                continue

            # ── “Modes:” line starts (or continues) a mode list
            if "Modes:" in line:
                parsing_modes = True  # don’t *continue* – this line may
                # already contain format + resolution

            if not parsing_modes:
                continue

            # ── format / bit-depth (may share the line with a resolution)
            fmt = re.search(r"'(?:SRGGB|R|GREY|Y)(\d+)", line)
            if fmt:
                current_bit_depth = int(fmt.group(1))

            # ── first resolution on the line (if any)
            res = re.search(r"(\d+)x(\d+)", line)
            if not res:
                continue

            width, height = map(int, res.groups())
            fps = re.search(r"\[(\d+(?:\.\d+)?)\s*fps", line)
            fps_max = int(float(fps.group(1))) if fps else None
            mode_extra = {}
            crop = re.search(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*/\s*(\d+)x(\d+)\s+crop", line, re.IGNORECASE)
            if crop:
                cx, cy, cw, ch = map(int, crop.groups())
                mode_extra.update({"crop_x": cx, "crop_y": cy, "crop_width": cw, "crop_height": ch})

            # The driver describes binned modes explicitly.  Prefer that
            # declaration over inferring binning from crop/output geometry:
            # a crop is not a binning operation, and the two must remain
            # independent in the mode database.
            binning = re.search(
                r"\b(\d+)\s*[x×]\s*(\d+)\s*(?:binning|binned)\b",
                line, re.IGNORECASE,
            )
            if binning:
                bx, by = map(int, binning.groups())
                mode_extra.update({"binning_x": bx, "binning_y": by})
            sensors[current_cam].append(
                self._mode_from_metadata_or_detected(
                    camera_name=current_cam, width=width, height=height,
                    bit_depth=current_bit_depth, fps_max=fps_max, hdr=hdr,
                    extra=mode_extra,
                )
            )

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

    @staticmethod
    def _mode_key(mode: Dict) -> tuple:
        """Identity used to dedupe a mode across the plain and HDR runs."""
        return (
            int(mode.get("width") or 0),
            int(mode.get("height") or 0),
            int(mode.get("bit_depth") or 0),
            mode.get("fps_max"),
        )

    def _merge_mode_lists(
        self,
        base: Dict[str, List[Dict]],
        hdr: Dict[str, List[Dict]],
    ) -> Dict[str, List[Dict]]:
        """Combine the plain (non-HDR) and ``--hdr sensor`` mode lists.

        A mode reported by the HDR run is kept as HDR only when the plain run
        did not already report an identical (width, height, bit_depth, fps)
        mode. Sensors that ignore ``--hdr sensor`` therefore return the same
        modes twice and collapse back to a single non-HDR list, so only real
        ClearHDR sensors (imx585) gain HDR modes.
        """
        merged: Dict[str, List[Dict]] = {cam: list(modes) for cam, modes in base.items()}
        for cam, hdr_modes in hdr.items():
            base_keys = {self._mode_key(m) for m in merged.get(cam, [])}
            for mode in hdr_modes:
                if self._mode_key(mode) in base_keys:
                    continue
                merged.setdefault(cam, []).append(mode)
        return merged

    @staticmethod
    def _mode_identity(mode: Dict) -> tuple:
        return (
            int(mode.get("width") or 0), int(mode.get("height") or 0),
            int(mode.get("bit_depth") or 0), bool(mode.get("hdr")),
            mode.get("crop_x"), mode.get("crop_y"),
            mode.get("crop_width"), mode.get("crop_height"),
        )

    @classmethod
    def _mode_matches_enabled(cls, mode: Dict, entries: List[Dict]) -> bool:
        ident = cls._mode_identity(mode)
        return any(isinstance(e, dict) and cls._mode_identity(e) == ident for e in (entries or []))

    @staticmethod
    def _mode_binning(mode: Dict) -> tuple:
        # Binning is a sensor/driver property, not something that should be
        # inferred from the crop rectangle. cinepi-raw --list-cameras is the
        # authoritative source for the runtime mode catalogue.
        bx, by = mode.get("binning_x"), mode.get("binning_y")
        if all(isinstance(v, (int, float)) and v > 0 for v in (bx, by)):
            return (int(bx), int(by))
        # Legacy database entries may not have explicit binning yet. Keep the
        # old geometric fallback only for those entries so existing sensors do
        # not disappear; newly discovered driver modes always carry explicit
        # binning when the driver reports it.
        cw, ch = mode.get("crop_width"), mode.get("crop_height")
        w, h = mode.get("width"), mode.get("height")
        if not all(isinstance(v, (int, float)) and v > 0 for v in (cw, ch, w, h)):
            return (None, None)
        bx, by = cw / w, ch / h
        if abs(bx - round(bx)) > 1e-6 or abs(by - round(by)) > 1e-6:
            return (None, None)
        return (int(round(bx)), int(round(by)))

    @classmethod
    def _mode_is_full(cls, mode: Dict) -> bool:
        # Full/native is orthogonal to binning. A 2x1 or 2x2 binned mode can
        # still cover the complete sensor. The driver/list-cameras crop tuple
        # is therefore the only thing used to decide whether a mode is cropped.
        return mode.get("crop_width") is None or mode.get("crop_height") is None

    @classmethod
    def _mode_sort_key(cls, mode: Dict) -> tuple:
        bx, by = cls._mode_binning(mode)
        bin_factor = (bx or 1) * (by or 1)
        known_crop = mode.get("crop_width") is not None
        full = cls._mode_is_full(mode)
        return (
            -(int(mode.get("width") or 0) * int(mode.get("height") or 0)),
            -(int(mode.get("bit_depth") or 0)),
            -bin_factor,
            0 if full else (1 if known_crop else 2),
            int(mode.get("crop_x") or 0), int(mode.get("crop_y") or 0),
        )

    def _order_modes(self, selected: List[Dict]) -> List[Dict]:
        """Order dynamic recording modes: resolution/depth, then binning,
        with crop variants following the corresponding binning group."""
        return sorted(selected, key=self._mode_sort_key)

    def _finalize_modes(
        self,
        sensors: Dict[str, List[Dict]],
    ) -> Dict[str, Dict[int, Dict]]:
        """Add custom modes, apply the settings.jsonc filters, order and index.

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
                hdr_flag = bool(extra.get("hdr", False))
                identity = {
                    "width": w, "height": h, "bit_depth": bd, "hdr": hdr_flag,
                    "crop_x": extra.get("crop_x"), "crop_y": extra.get("crop_y"),
                    "crop_width": extra.get("crop_width"), "crop_height": extra.get("crop_height"),
                }
                existing = next((m for m in sensors[cam] if self._mode_identity(m) == self._mode_identity(identity)), None)
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

        # Every mode this camera reported, before the settings.jsonc filters
        # take anything away. sensor_resolutions is the filtered table, so it
        # cannot answer "does this sensor have any 3K mode?" -- switching 3K
        # off would make the answer no, and the settings page would grey out
        # the very switch that did it. Kept per camera, merged rather than
        # replaced, for the same hot-plug reason sensor_resolutions is.
        # getattr, and reassigned rather than mutated: _finalize_modes is
        # reachable on an instance built with __new__ (several tests do
        # exactly that, setting only the filter attributes it reads), and a
        # class-level default dict would be shared across instances.
        self.sensor_modes_unfiltered = dict(
            getattr(self, "sensor_modes_unfiltered", {}),
            **{cam: [dict(m) for m in modes] for cam, modes in sensors.items()},
        )

        # ── filter & index (k-steps / bit depths / hdr) ─────────────
        pruned: Dict[str, Dict[int, Dict]] = {}
        for cam, modes in sensors.items():
            selected = []
            mode_entries = (getattr(self, "enabled_modes", {}) or {}).get(cam)
            use_individual_selection = isinstance(mode_entries, list) and len(mode_entries) > 0
            for m in modes:
                if use_individual_selection:
                    if not self._mode_matches_enabled(m, mode_entries):
                        continue
                elif self.bit_depths and m["bit_depth"] not in self.bit_depths:
                    continue
                # A ClearHDR mode also has to pass its own depth switch. The
                # two are separate questions -- "expose ClearHDR at all" and
                # "which of its depths" -- and only the second one can tell
                # 12-bit ClearHDR from 12-bit SDR.
                # getattr: _finalize_modes is reachable on an instance built
                # with __new__ (several tests do exactly that, setting only
                # the filter attributes they care about), and a missing switch
                # must mean "no opinion", not an exception.
                clear_hdr_depths = getattr(self, "clear_hdr_depths", None)
                if not use_individual_selection and bool(m.get("hdr")) and clear_hdr_depths is not None:
                    if int(m.get("bit_depth") or 0) not in clear_hdr_depths:
                        continue
                # settings.jsonc → image_capture.hdr: {sdr, imx585_clear_hdr}
                # whitelist of the ClearHDR flag, normalized by _hdr_whitelist.
                if not use_individual_selection and self.hdr_modes and bool(m.get("hdr")) not in self.hdr_modes:
                    continue
                k_val = round(m["width"] / 1000 * 2) / 2
                if not use_individual_selection and self.k_steps and k_val not in self.k_steps:
                    continue
                selected.append(m)

            # ⚑ NEW: never leave a camera without modes
            if not selected:
                logging.warning("No modes passed the filters for %s – "
                                "keeping full list instead", cam)
                selected = modes

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
            # modes; sensors that ignore --hdr sensor collapse back to the
            # plain list in _merge_mode_lists().
            hdr_out = self._list_cameras(hdr=True)
            if hdr_out.strip():
                logging.info("cinepi-raw --hdr sensor output:\n%s", hdr_out)

            base_modes = self._parse_cinepi_output(out, hdr=False)
            hdr_modes = self._parse_cinepi_output(hdr_out, hdr=True) if hdr_out.strip() else {}
            merged = self._merge_mode_lists(base_modes, hdr_modes)

            # The HDR probe "succeeding" (non-empty output) but adding zero new
            # modes means --hdr sensor couldn't actually change what the sensor
            # reports -- most commonly because another process (see
            # _kill_stale_cinepi_raw above) still held the subdev. Surface this
            # loudly instead of silently shipping a mode table missing ClearHDR.
            if hdr_out.strip():
                added = sum(
                    len(merged.get(cam, [])) - len(base_modes.get(cam, []))
                    for cam in merged
                )
                if added == 0:
                    logging.warning(
                        "ClearHDR probe (--hdr sensor) returned no modes beyond "
                        "the plain probe. If this sensor supports ClearHDR (e.g. "
                        "imx585), 16-bit modes are unavailable this session -- "
                        "likely because something already held the sensor "
                        "subdev when Cinemate started."
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
        """Return (lores_width, lores_height) preserving sensor aspect ratio within the preview area."""
        fw, fh = 1920, 1080
        px, py = 94, 50
        aw, ah = fw - 2 * px, fh - 2 * py
        aspect = sensor_w / sensor_h
        lh = min(720, ah)
        lw = int(lh * aspect)
        if lw > aw:
            lw, lh = aw, int(round(aw / aspect))
        lw &= ~1
        lh &= ~1
        return lw, lh

    def get_lores_width(self, camera_name, sensor_mode):
        res = self.get_resolution_info(camera_name, sensor_mode)
        w = res.get('width') or 1920
        h = res.get('height') or 1080
        return self._calc_lores(w, h)[0]

    def get_lores_height(self, camera_name, sensor_mode):
        res = self.get_resolution_info(camera_name, sensor_mode)
        w = res.get('width') or 1920
        h = res.get('height') or 1080
        return self._calc_lores(w, h)[1]
    
    def get_hdr(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return bool(resolution_info.get('hdr', False))

    def get_available_resolutions(self):
        resolutions = []
        for mode, info in self.res_modes.items():
            resolution = f"{info['width']} : {info['height']} : {info['bit_depth']}b"
            # imx585 ClearHDR modes are tagged in the web GUI dropdown so the
            # 12-bit HDR modes are distinguishable from the plain 12-bit ones.
            if info.get('hdr'):
                resolution += " :HDR"
            resolutions.append({'mode': mode, 'resolution': resolution})
        return resolutions
