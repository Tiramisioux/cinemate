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
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


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
    # Borrows shutter_a's step table AND its free/sync policy verbatim
    # (set_shutter_a_nom gates on shutter_a_sync_mode/shutter_a_free, not a
    # shutter_a_nom-specific flag) - only the lock is its own.
    steps=_SHUTTER_A.steps,
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
    steps=lambda c: c.settings.get("preview", {}).get(
        "zoom_steps", [0.5, 1.0, 1.5, 2.0]),
)

_HDR_BLEND = _param(
    "hdr_blend", "ClearHDR Blend Mode", "",
    steps=lambda c: list(range(0, 9)),
)

_HDR_GAIN_ADDER = _param(
    "hdr_gain_adder", "ClearHDR Gain Adder", "",
    steps=lambda c: list(range(0, 6)),
)

_HDR_THRESHOLD_LOW = _param(
    "hdr_threshold_low", "ClearHDR Threshold Low", "",
    steps=lambda c: list(range(0, 4096, 16)),
)

_HDR_THRESHOLD_HIGH = _param(
    "hdr_threshold_high", "ClearHDR Threshold High", "",
    steps=lambda c: list(range(0, 4096, 16)),
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
