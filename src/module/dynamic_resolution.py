"""Dynamic resolution selection.

Given a desired sensor mode and a requested fps, picks the highest-resolution
mode (at or below the desired mode's own resolution, within its HDR class)
whose sensor-declared ``fps_max`` (the value reported by
``cinepi-raw --list-cameras``, see sensor_detect.py) can sustain that fps.
Always active -- there is no curated per-storage performance table or policy
to configure; the ceiling is whatever the sensor itself reports for each mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


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
    return current_area < desired_area


def dynamic_resolution_indicator_active(
    *,
    enabled: Any,
    active: Any,
    current_mode: Any,
    desired_mode: Any,
    sensor_modes: dict[int, dict[str, Any]] | None = None,
) -> bool:
    """Return True while dynamic resolution is actively showing a substitute mode."""
    if not _as_bool(enabled) or not _as_bool(active):
        return False
    return dynamic_resolution_is_lower_substitute(
        sensor_modes=sensor_modes,
        current_mode=current_mode,
        desired_mode=desired_mode,
    )


def _candidate_modes(
    normalized_modes: dict[int, dict[str, Any]],
    desired_mode: int,
) -> tuple[dict[str, Any], list[tuple[int, dict[str, Any], int]]] | None:
    """Return (desired_info, [(mode, info, area), ...]) for modes at or below
    the desired mode's resolution within its HDR class, or None if the
    desired mode itself is unknown."""
    desired_info = normalized_modes.get(desired_mode)
    if desired_info is None:
        return None
    desired_area = _mode_area(desired_info)
    if desired_area is None:
        return None
    desired_hdr = bool(desired_info.get("hdr", False))

    candidates = []
    for mode, info in normalized_modes.items():
        if bool(info.get("hdr", False)) != desired_hdr:
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
        (mode, area, mode_fps_max)
        for mode, info, area in candidates
        for mode_fps_max in [_as_float(info.get("fps_max"))]
        if mode_fps_max is not None and mode_fps_max >= fps
    ]
    if not eligible:
        return None

    # F-286: two modes can share an area and differ only in bit depth (a
    # sensor's max-resolution 10-bit and 12-bit modes always tie on area,
    # since both sit at the sensor's ceiling). The (area, fps_max)
    # tie-break below then prefers whichever is faster -- typically the
    # lower bit depth -- even when the desired mode itself already
    # sustains requested_fps and substitution has nothing to do. An
    # explicit, sustainable request for the desired mode is honored
    # directly, ahead of the tie-break.
    desired_eligible = next(
        (item for item in eligible if item[0] == desired_mode_int),
        None,
    )
    if desired_eligible is not None:
        selected_mode, selected_area, selected_fps_max = desired_eligible
    else:
        selected_mode, selected_area, selected_fps_max = max(
            eligible, key=lambda item: (item[1], item[2])
        )
    desired_area = _mode_area(desired_info)
    return DynamicResolutionChoice(
        mode=selected_mode,
        fps_max=selected_fps_max,
        desired_mode=desired_mode_int,
        desired_fps_max=desired_fps_max,
        dynamic_active=selected_mode != desired_mode_int and selected_area < desired_area,
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
