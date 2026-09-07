"""Dynamic resolution selection.

Given a desired sensor mode and a requested fps, picks the best mode the
sensor can actually sustain at that fps, where "best" is defined by a
**quality ladder** over the mode table and a policy that says which axis of
quality to give up first.

Every mode sits at a point on two axes:

* **mode class** -- ``(hdr, bit_depth)``, the same grouping
  ``sensor_detect._order_modes`` uses to lay the mode table out, so on an
  imx585 the three classes are exactly the three blocks the operator sees:
  SDR, 12-bit ClearHDR, 16-bit ClearHDR. Ordered as a tuple, a richer class
  compares greater.
* **resolution** -- frame area.

A substitute is only ever chosen from modes that are *no better than the
desired one on either axis*: never a larger frame, never a richer class.
Within that set, ``dynamic_resolution_priority`` decides the walk:

``"mode"``
    Hold the mode class as long as possible. On an imx585 with 12-bit
    ClearHDR disabled and 16-bit 4K selected, the ladder is
    16-bit 4K -> 16-bit HD -> 4K SDR -> HD SDR.

``"resolution"``
    Hold the frame size as long as possible. Same sensor, same selection:
    16-bit 4K -> 4K SDR -> HD SDR. (16-bit HD is on the ladder too, below
    4K SDR, but 4K SDR already covers everything it could serve.)

``"none"``
    Never leave the desired mode's own class -- the behaviour this module
    had before the ladder existed. Resolution is the only thing that ever
    changes, and a request the class cannot serve gets no answer at all.
    Trading bit depth or the HDR flag for frame rate is a real cost the
    operator did not ask for, so it stays available to switch off.

The class change is not free at the hardware level: bit depth is part of
``--mode`` and ClearHDR is the ``--hdr sensor`` launch flag, so crossing a
class boundary means relaunching cinepi-raw. That is why the caller can pin
the ladder to one class with ``restrict_to_family_of`` -- see
``CinePiController._dynamic_resolution_choice_for_fps``, which pins it to the
running mode for the length of a take rather than ending the take to change
the sensor format under it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from module.config_loader import as_bool


PRIORITY_MODE = "mode"
PRIORITY_RESOLUTION = "resolution"
PRIORITY_NONE = "none"

#: Every accepted value of ``image_capture.dynamic_resolution_priority``,
#: in the order the settings editor offers them.
DYNAMIC_RESOLUTION_PRIORITIES = (PRIORITY_MODE, PRIORITY_RESOLUTION, PRIORITY_NONE)

#: "mode" rather than "none" because it is the policy that changes least:
#: it exhausts the desired mode's own class exactly as "none" does before it
#: crosses anything, so every request "none" can serve, "mode" serves
#: identically. It only differs where "none" runs out of answers.
DEFAULT_DYNAMIC_RESOLUTION_PRIORITY = PRIORITY_MODE

# Spelling is not the operator's problem. The CLI, Redis and settings.jsonc
# all land here, and Redis stores everything as text, so the numeric forms
# are accepted too -- 0 is the most restrictive policy, 2 the least.
_PRIORITY_ALIASES = {
    "mode": PRIORITY_MODE,
    "follow_mode": PRIORITY_MODE,
    "follow mode": PRIORITY_MODE,
    "mode_first": PRIORITY_MODE,
    "1": PRIORITY_MODE,
    "resolution": PRIORITY_RESOLUTION,
    "res": PRIORITY_RESOLUTION,
    "follow_resolution": PRIORITY_RESOLUTION,
    "follow resolution": PRIORITY_RESOLUTION,
    "resolution_first": PRIORITY_RESOLUTION,
    "2": PRIORITY_RESOLUTION,
    "none": PRIORITY_NONE,
    "off": PRIORITY_NONE,
    "family": PRIORITY_NONE,
    "locked": PRIORITY_NONE,
    "mode_locked": PRIORITY_NONE,
    "0": PRIORITY_NONE,
}


@dataclass(frozen=True)
class DynamicResolutionChoice:
    mode: int
    fps_max: float
    desired_mode: int
    desired_fps_max: float
    dynamic_active: bool
    # True when the chosen mode is in a different (hdr, bit_depth) class than
    # the desired one -- i.e. this substitution costs more than frame size,
    # and applying it needs cinepi-raw relaunched.
    mode_class_changed: bool = False


def normalize_priority(
    value: Any,
    default: str = DEFAULT_DYNAMIC_RESOLUTION_PRIORITY,
) -> str:
    """Decode a priority from settings.jsonc, Redis or the CLI.

    Anything unrecognised returns *default* rather than raising: this is read
    on the fps path and on the GUI redraw path, and a typo in settings.jsonc
    should cost the operator the policy they meant, not the camera.
    """
    if isinstance(value, bool):
        return default
    if value is None:
        return default
    text = str(value).strip().lower().replace("-", "_")
    if not text:
        return default
    return _PRIORITY_ALIASES.get(text, default)


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
    # the mode -- which is the whole thing the indicator reports. It is also
    # how a class substitution reads: 4K SDR standing in for 4K 16-bit HDR is
    # the same frame size and a real downgrade. Only a current mode *above*
    # the desired one is something dynamic resolution cannot have caused, so
    # only that is excluded.
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


def _family_rank(mode_info: dict[str, Any]) -> tuple[int, int]:
    """mode_family() as something orderable: richer class compares greater.

    HDR outranks SDR, and within a class more bits outrank fewer -- the same
    order the operator's mode table is laid out in, bottom to top.
    """
    hdr, bit_depth = mode_family(mode_info)
    return (1 if hdr else 0, bit_depth)


def _ladder_key(priority: str) -> Callable[[tuple], tuple]:
    """Sort key over ``(mode, info, area, fps_max)`` -- greatest is best.

    Both policies order the same set; they differ only in which axis leads.
    ``fps_max`` is the last real tie-break and the mode index settles the
    rest, so one mode table always produces one ladder.
    """
    if priority == PRIORITY_RESOLUTION:
        def key(item):
            mode, info, area, fps_max = item
            hdr, bit_depth = _family_rank(info)
            return (area, hdr, bit_depth, fps_max, -mode)
    else:
        # PRIORITY_MODE, and PRIORITY_NONE -- where every candidate is in one
        # class, so the class terms are constant and this reduces to
        # (area, fps_max), the ordering this module has always used.
        def key(item):
            mode, info, area, fps_max = item
            hdr, bit_depth = _family_rank(info)
            return (hdr, bit_depth, area, fps_max, -mode)
    return key


def _candidate_modes(
    normalized_modes: dict[int, dict[str, Any]],
    desired_mode: int,
    *,
    priority: str = DEFAULT_DYNAMIC_RESOLUTION_PRIORITY,
    restrict_to_family: tuple[bool, int] | None = None,
) -> tuple[dict[str, Any], list[tuple[int, dict[str, Any], int]]] | None:
    """Return (desired_info, [(mode, info, area), ...]) for every mode no
    better than the desired one on either axis, or None if the desired mode
    itself is unknown.

    *restrict_to_family* pins the candidates to one (hdr, bit_depth) class.
    ``priority="none"`` pins them to the desired mode's own class; a caller
    can pin them to a different one (the class actually running, mid-take).
    """
    desired_info = normalized_modes.get(desired_mode)
    if desired_info is None:
        return None
    desired_area = _mode_area(desired_info)
    if desired_area is None:
        return None
    desired_rank = _family_rank(desired_info)

    if priority == PRIORITY_NONE and restrict_to_family is None:
        # "none" pins to the desired mode's own class -- but only when the
        # caller has not already pinned it to a different one. A caller's pin
        # is a statement about what the hardware can do right now (the class
        # actually running, mid-take), and no policy may override it: doing so
        # hands back a mode in a class cinepi-raw is not launched for.
        restrict_to_family = mode_family(desired_info)

    candidates = []
    for mode, info in normalized_modes.items():
        area = _mode_area(info)
        if area is None or area > desired_area:
            continue
        if restrict_to_family is not None:
            if mode_family(info) != restrict_to_family:
                continue
        elif _family_rank(info) > desired_rank:
            # Never substitute *up* a class. Dynamic resolution exists to
            # find something the sensor can sustain, not to hand the
            # operator a richer mode than the one they selected.
            continue
        candidates.append((mode, info, area))
    return desired_info, candidates


def _resolve_family_lock(
    normalized_modes: dict[int, dict[str, Any]],
    restrict_to_family_of: Any,
) -> tuple[bool, int] | None:
    locked = _as_int(restrict_to_family_of)
    if locked is None:
        return None
    locked_info = normalized_modes.get(locked)
    if locked_info is None:
        return None
    return mode_family(locked_info)


def choose_resolution(
    *,
    sensor_modes: dict[int, dict[str, Any]],
    desired_mode: int,
    requested_fps: float,
    priority: Any = DEFAULT_DYNAMIC_RESOLUTION_PRIORITY,
    restrict_to_family_of: Any = None,
) -> DynamicResolutionChoice | None:
    """Choose the best mode on the quality ladder that sustains requested_fps.

    Never substitutes a larger frame or a richer mode class than
    *desired_mode*. *priority* picks which axis is given up first; see the
    module docstring. *restrict_to_family_of* pins the answer to that mode's
    class, for callers that cannot afford the cinepi-raw relaunch a class
    change costs.
    """
    desired_mode_int = _as_int(desired_mode)
    fps = _as_float(requested_fps)
    if desired_mode_int is None or fps is None:
        return None

    priority = normalize_priority(priority)
    normalized_modes = _normalize_modes(sensor_modes)
    family_lock = _resolve_family_lock(normalized_modes, restrict_to_family_of)
    resolved = _candidate_modes(
        normalized_modes,
        desired_mode_int,
        priority=priority,
        restrict_to_family=family_lock,
    )
    if resolved is None:
        return None
    desired_info, candidates = resolved

    desired_fps_max = _as_float(desired_info.get("fps_max"))
    if desired_fps_max is None:
        return None
    desired_family = mode_family(desired_info)

    eligible = [
        (mode, info, area, mode_fps_max)
        for mode, info, area in candidates
        for mode_fps_max in [_as_float(info.get("fps_max"))]
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
        selected = desired_eligible
    else:
        # Genuine downgrade: the desired mode itself cannot sustain
        # requested_fps, so a substitute must be chosen among candidates that
        # all already clear the fps bar. Which of them is "best" is the whole
        # question the priority setting answers -- beyond requested_fps, a
        # mode's remaining fps headroom is unused, not something the request
        # needs, so it only breaks ties the two quality axes leave.
        selected = max(eligible, key=_ladder_key(priority))

    selected_mode, selected_info, _selected_area, selected_fps_max = selected
    return DynamicResolutionChoice(
        mode=selected_mode,
        fps_max=selected_fps_max,
        desired_mode=desired_mode_int,
        desired_fps_max=desired_fps_max,
        # Any substitution at all is the system governing the resolution --
        # that is what the readout reports, so it does not additionally
        # require the substitute to be strictly smaller.
        dynamic_active=selected_mode != desired_mode_int,
        mode_class_changed=mode_family(selected_info) != desired_family,
    )


def max_fps_for_context(
    *,
    sensor_modes: dict[int, dict[str, Any]],
    desired_mode: int | None = None,
    priority: Any = DEFAULT_DYNAMIC_RESOLUTION_PRIORITY,
    restrict_to_family_of: Any = None,
) -> float | None:
    """Return the highest fps achievable across candidate modes for
    desired_mode (or across all modes, if desired_mode is None).

    This is the fps ceiling the step table is built from, so it has to be
    read from the same candidate set ``choose_resolution`` picks out of --
    otherwise the dial offers frame rates nothing can serve, or hides ones
    the ladder would have reached.
    """
    normalized_modes = _normalize_modes(sensor_modes)
    if not normalized_modes:
        return None

    priority = normalize_priority(priority)
    if desired_mode is not None:
        desired_mode_int = _as_int(desired_mode)
        if desired_mode_int is None:
            return None
        family_lock = _resolve_family_lock(normalized_modes, restrict_to_family_of)
        resolved = _candidate_modes(
            normalized_modes,
            desired_mode_int,
            priority=priority,
            restrict_to_family=family_lock,
        )
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
