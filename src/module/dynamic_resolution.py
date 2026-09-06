"""Dynamic resolution selection.

Given a desired sensor mode and a requested fps, picks the highest-resolution
mode (at or below the desired mode's own resolution, within its own family)
whose sensor-declared ``fps_max`` (the value reported by
``cinepi-raw --list-cameras``, see sensor_detect.py) can sustain that fps.

A *family* is (hdr, bit_depth) -- the same grouping sensor_detect._order_modes
uses to lay the mode table out, so on an imx585 the three families are exactly
the three blocks the operator sees: SDR, 12-bit ClearHDR, 16-bit ClearHDR. The
bit depth is part of the key rather than a tie-break, so this only ever changes
*resolution*. Trading 12-bit for 10-bit at the same frame size would buy fps by
throwing away image data the operator explicitly asked for, and a substitution
the operator did not ask for is not the place to make that trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from module.config_loader import as_bool


@dataclass(frozen=True)
class DynamicResolutionChoice:
    mode: int
    fps_max: float
    desired_mode: int
    desired_fps_max: float
    dynamic_active: bool


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result <= 0:
        return None
    return result


def _normalize_modes(sensor_modes: dict[int, dict[str, Any]] | None) -> dict[int, dict[str, Any]]:
    normalized: dict[int, dict[str, Any]] = {}
    for mode, info in (sensor_modes or {}).items():
        mode_int = _as_int(mode)
        if mode_int is None or not isinstance(info, dict):
            continue
        normalized[mode_int] = info
    return normalized


def _mode_area(mode_info: dict[str, Any]) -> int | None:
    width = _as_int(mode_info.get("width"))
    height = _as_int(mode_info.get("height"))
    if width is None or height is None:
        return None
    return width * height


def dynamic_resolution_is_lower_substitute(
    *,
    sensor_modes: dict[int, dict[str, Any]] | None,
    current_mode: Any,
    desired_mode: Any,
) -> bool:
    current = _as_int(current_mode)
    desired = _as_int(desired_mode)
    if current is None or desired is None or current == desired:
        return False

    normalized_modes = _normalize_modes(sensor_modes)
    current_info = normalized_modes.get(current)
    desired_info = normalized_modes.get(desired)
    current_area = _mode_area(current_info) if current_info else None
    desired_area = _mode_area(desired_info) if desired_info else None
    if current_area is None or desired_area is None:
        return current != desired
    # Not-larger rather than strictly-smaller. Two modes in one family can tie
    # on area, and a substitution between them is still the system choosing
    # the mode -- which is the whole thing the indicator reports. Only a
    # current mode *above* the desired one is something dynamic resolution
    # cannot have caused, so only that is excluded.
    return current_area <= desired_area


def dynamic_resolution_indicator_active(
    *,
    enabled: Any,
    active: Any,
    current_mode: Any,
    desired_mode: Any,
    sensor_modes: dict[int, dict[str, Any]] | None = None,
) -> bool:
    """Return True while dynamic resolution is actively showing a substitute mode."""
    if not as_bool(enabled) or not as_bool(active):
        return False
    return dynamic_resolution_is_lower_substitute(
        sensor_modes=sensor_modes,
        current_mode=current_mode,
        desired_mode=desired_mode,
    )


def mode_family(mode_info: dict[str, Any]) -> tuple[bool, int]:
    """The (hdr, bit_depth) block a mode belongs to.

    Matches sensor_detect._order_modes' sort key, so a family here is one
    contiguous block of the operator's mode table rather than a set that
    straddles it.
    """
    return (
        bool(mode_info.get("hdr", False)),
        _as_int(mode_info.get("bit_depth")) or 0,
    )


def _candidate_modes(
    normalized_modes: dict[int, dict[str, Any]],
    desired_mode: int,
) -> tuple[dict[str, Any], list[tuple[int, dict[str, Any], int]]] | None:
    """Return (desired_info, [(mode, info, area), ...]) for modes at or below
    the desired mode's resolution within its own family, or None if the
    desired mode itself is unknown."""
    desired_info = normalized_modes.get(desired_mode)
    if desired_info is None:
        return None
    desired_area = _mode_area(desired_info)
    if desired_area is None:
        return None
    desired_family = mode_family(desired_info)

    candidates = []
    for mode, info in normalized_modes.items():
        if mode_family(info) != desired_family:
            continue
        area = _mode_area(info)
        if area is None or area > desired_area:
            continue
        candidates.append((mode, info, area))
    return desired_info, candidates


def choose_resolution(
    *,
    sensor_modes: dict[int, dict[str, Any]],
    desired_mode: int,
    requested_fps: float,
) -> DynamicResolutionChoice | None:
    """Choose the highest-resolution mode that can sustain requested_fps.

    Only ever substitutes within the desired mode's own HDR class and never
    to a larger resolution than desired_mode.
    """
    desired_mode_int = _as_int(desired_mode)
    fps = _as_float(requested_fps)
    if desired_mode_int is None or fps is None:
        return None

    normalized_modes = _normalize_modes(sensor_modes)
    resolved = _candidate_modes(normalized_modes, desired_mode_int)
    if resolved is None:
        return None
    desired_info, candidates = resolved

    desired_fps_max = _as_float(desired_info.get("fps_max"))
    if desired_fps_max is None:
        return None

    eligible = [
        (mode, area, mode_fps_max, mode_bit_depth)
        for mode, info, area in candidates
        for mode_fps_max in [_as_float(info.get("fps_max"))]
        for mode_bit_depth in [_as_int(info.get("bit_depth")) or 0]
        if mode_fps_max is not None and mode_fps_max >= fps
    ]
    if not eligible:
        return None

    # An explicit, sustainable request for the desired mode is honored
    # directly: no substitution is needed, so none is made.
    desired_eligible = next(
        (item for item in eligible if item[0] == desired_mode_int),
        None,
    )
    if desired_eligible is not None:
        selected_mode, _selected_area, selected_fps_max, _bit_depth = desired_eligible
    else:
        # Genuine downgrade: the desired mode itself cannot sustain
        # requested_fps, so a substitute must be chosen among candidates that
        # all already clear the fps bar. Every candidate shares the desired
        # mode's family, so they all share its bit depth -- the only axis left
        # is resolution, and the largest that clears the bar wins. fps_max
        # breaks a remaining area tie; beyond requested_fps it is unused
        # headroom, not something the request needs.
        selected_mode, _selected_area, selected_fps_max, _bit_depth = max(
            eligible, key=lambda item: (item[1], item[2])
        )
    return DynamicResolutionChoice(
        mode=selected_mode,
        fps_max=selected_fps_max,
        desired_mode=desired_mode_int,
        desired_fps_max=desired_fps_max,
        # Any substitution at all is the system governing the resolution --
        # that is what the readout reports, so it does not additionally
        # require the substitute to be strictly smaller.
        dynamic_active=selected_mode != desired_mode_int,
    )


def max_fps_for_context(
    *,
    sensor_modes: dict[int, dict[str, Any]],
    desired_mode: int | None = None,
) -> float | None:
    """Return the highest fps achievable across candidate modes for
    desired_mode (or across all modes, if desired_mode is None)."""
    normalized_modes = _normalize_modes(sensor_modes)
    if not normalized_modes:
        return None

    if desired_mode is not None:
        desired_mode_int = _as_int(desired_mode)
        if desired_mode_int is None:
            return None
        resolved = _candidate_modes(normalized_modes, desired_mode_int)
        if resolved is None:
            return None
        _, candidates = resolved
        infos = [info for _, info, _ in candidates]
    else:
        infos = list(normalized_modes.values())

    maxes = [
        fps_max
        for info in infos
        for fps_max in [_as_float(info.get("fps_max"))]
        if fps_max is not None
    ]
    if not maxes:
        return None
    return max(maxes)
