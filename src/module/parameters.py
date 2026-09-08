"""Canonical registry of Cinemate's cycle-able camera parameters.

At least four call sites already address these parameters by string name:
``increment_setting``/``decrement_setting`` in ``cinepi_controller.py``, the
quad-rotary encoder config (``setting_name``), the OLED display config
(``values``), and the analog-pot config (``analog_controls``). The naming
convention was real but implicit; this module is the single place it is
declared. Existing consumers should resolve parameters through
``REGISTRY``/``get()`` rather than re-deriving the convention locally.

Step tables are NOT uniformly stored attributes on the controller (fps is
capped at ``fps_max`` elsewhere, shutter_a is recomputed for flicker-free
angles, zoom comes from ``preview.zoom_steps``), so ``Parameter.steps`` is a
callable that takes the live controller and returns the current legal step
list, not an attribute name.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def steps_bounds(steps, fallback):
    """Return ``(lowest, highest)`` of a parameter's ``steps`` table.

    Free stepping sweeps between the ends of ``arrays.<name>.steps`` rather
    than a range hardcoded at the call site, so its bounds now come from data
    the settings editor lets an operator rewrite. That list can arrive empty
    (every chip deleted), or carrying a ``null`` from a chip that failed to
    parse; ``free_stepping_steps`` guards only its *increment*, so anything
    unusable here would surface as a TypeError or ValueError deep in a rebuild.

    Non-finite and non-numeric entries are dropped, and *fallback* -- the pair
    that call site sweeps when it has nothing to go on -- is returned when
    nothing usable is left. A single usable entry is honoured as written: the
    lowest and the highest really are the same value, and the sweep collapses
    to it.
    """
    values = [v for v in (steps or [])
              if isinstance(v, (int, float))
              and not isinstance(v, bool)
              and math.isfinite(v)]
    if not values:
        return fallback
    return min(values), max(values)


def free_stepping_steps(min_value, max_value, increment):
    """Build the fine step table a parameter's free stepping expands to.

    Shared by every ``_rebuild_*_steps``/``_get_steps`` call site that
    replaces a coarse ``arrays.<name>.steps`` table with a (near-)continuous
    range once free stepping is on, so the granularity comes from one formula
    instead of a hardcoded literal re-typed at each call site. *max_value*
    is always included even when it is not an exact multiple of *increment*
    above *min_value*.
    """
    try:
        increment = float(increment)
    except (TypeError, ValueError):
        increment = 1.0
    if increment <= 0:
        increment = 1.0

    # floor, not round: rounding up here can overshoot max_value (e.g. 0-4095
    # step 16 is 255.9375 steps, which round() takes to 256 -> a spurious
    # 4096). The "append max_value if undershooting" line below is what
    # guarantees the true max is still always reachable.
    # The bounds come from an operator-editable array (see steps_bounds), so
    # they can arrive the wrong way round. Reversed used to die on values[-1]
    # below, because range(count + 1) is empty when count is negative.
    if max_value < min_value:
        min_value, max_value = max_value, min_value

    count = int((max_value - min_value) / increment)
    values = [round(min_value + i * increment, 6) for i in range(count + 1)]
    if values[-1] < max_value:
        values.append(float(max_value))

    return [int(v) if float(v).is_integer() else v for v in values]


@dataclass(frozen=True)
class Parameter:
    name: str
    label: str
    unit: str
    redis_key: str
    setter: str
    cycle: str  # "steps" (increment/decrement through a table) or
                # "direction" (set_X(direction="next"/"prev") owns its own
                # cycling logic)
    steps: Callable[[object], list]
    policy_key: str
    free_attr: Optional[str] = None
    lock_attr: Optional[str] = None
    menu: bool = True


def _param(name, label, unit, steps, *, cycle="steps", redis_key=None,
           setter=None, policy_key=None, free_attr=None, lock_attr=None,
           menu=True):
    if cycle not in ("steps", "direction"):
        raise ValueError(f"unknown cycle kind: {cycle!r}")
    return Parameter(
        name=name,
        label=label,
        unit=unit,
        redis_key=redis_key if redis_key is not None else name,
        setter=setter if setter is not None else f"set_{name}",
        cycle=cycle,
        steps=steps,
        policy_key=policy_key if policy_key is not None else name,
        free_attr=free_attr,
        lock_attr=lock_attr,
        menu=menu,
    )


_ISO = _param(
    "iso", "ISO", "",
    steps=lambda c: c.iso_steps,
    free_attr="iso_free",
    lock_attr="iso_lock",
)

_SHUTTER_A = _param(
    "shutter_a", "Shutter Angle", "°",
    # increment_setting always recomputes the flicker-free-aware table for
    # shutter_a, ignoring whatever step list its caller passed in.
    steps=lambda c: c.calculate_dynamic_shutter_angles(c.current_fps),
    free_attr="shutter_a_free",
)

_SHUTTER_A_NOM = _param(
    "shutter_a_nom", "Shutter Angle (Nominal)", "°",
    redis_key="shutter_angle_nom",
    # Borrows shutter_a's underlying step-table ATTRIBUTE (the static
    # configured list) and its free/sync policy verbatim (set_shutter_a_nom
    # gates on shutter_a_sync_mode/shutter_a_free, not a shutter_a_nom-
    # specific flag) - only the lock is its own.
    #
    # This is deliberately NOT shutter_a's own steps() callable: shutter_a's
    # callable recomputes the flicker-free-augmented table, but
    # increment_setting has only ever cycled shutter_a_nom through the
    # plain static list (inc_shutter_a_nom passes self.shutter_a_steps
    # straight through). Sharing shutter_a's callable here would widen the
    # set of angles shutter_a_nom can land on - an observable behaviour
    # change, not a refactor.
    steps=lambda c: c.shutter_a_steps,
    policy_key="shutter_a",
    free_attr=_SHUTTER_A.free_attr,
    lock_attr="shutter_a_nom_lock",
)

_FPS = _param(
    "fps", "FPS", "fps",
    steps=lambda c: c.fps_steps,
    free_attr="fps_free",
    lock_attr="fps_lock",
)

_WB = _param(
    "wb", "White Balance", "K",
    # set_wb persists the user-facing kelvin value under wb_user, not wb.
    redis_key="wb_user",
    cycle="direction",
    steps=lambda c: c.wb_steps,
    free_attr="wb_free",
)

_ZOOM = _param(
    "zoom", "Zoom", "×",
    cycle="direction",
    steps=lambda c: c.settings.get("hdmi_display", {}).get("preview", {}).get(
        "zoom_steps", [0.5, 1.0, 1.5, 2.0]),
)

_HDR_BLEND = _param(
    "hdr_blend", "ClearHDR Blend Mode", "",
    steps=lambda c: c.hdr_blend_steps,
    free_attr="hdr_blend_free",
)

_HDR_GAIN_ADDER = _param(
    "hdr_gain_adder", "ClearHDR Gain Adder", "",
    steps=lambda c: c.hdr_gain_adder_steps,
    free_attr="hdr_gain_adder_free",
)

_HDR_THRESHOLD_LOW = _param(
    "hdr_threshold_low", "ClearHDR Threshold Low", "",
    steps=lambda c: c.hdr_threshold_low_steps,
    free_attr="hdr_threshold_low_free",
)

_HDR_THRESHOLD_HIGH = _param(
    "hdr_threshold_high", "ClearHDR Threshold High", "",
    steps=lambda c: c.hdr_threshold_high_steps,
    free_attr="hdr_threshold_high_free",
)

REGISTRY: dict[str, Parameter] = {
    p.name: p
    for p in (
        _ISO, _SHUTTER_A, _SHUTTER_A_NOM, _FPS, _WB, _ZOOM,
        _HDR_BLEND, _HDR_GAIN_ADDER, _HDR_THRESHOLD_LOW, _HDR_THRESHOLD_HIGH,
    )
}


def get(name: str, *, source: str = "") -> Optional[Parameter]:
    """Look up a parameter by its canonical name.

    Logs a WARNING naming *source* when *name* is not registered, so a
    typo'd config string is visible at startup instead of silently
    no-oping the way ``getattr(obj, name, None)`` does.
    """
    param = REGISTRY.get(name)
    if param is None:
        where = f" ({source})" if source else ""
        logger.warning("Unknown parameter name %r%s", name, where)
    return param


def menu_parameters(settings) -> list:
    """Registry entries relevant to *settings*, in declaration order.

    Placeholder for a future menu system: nothing consumes this yet, and
    for now it just returns the registry's menu-eligible entries in
    declaration order regardless of *settings*.
    """
    return [p for p in REGISTRY.values() if p.menu]
