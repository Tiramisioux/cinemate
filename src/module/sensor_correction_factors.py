"""Static FPS correction-factor tables per sensor/mode/FPS.

Each sensor exposes one table per sensor mode.  FPS entries can be added
incrementally as calibration data becomes available.  If a specific FPS is not
present for a given mode the lookup falls back to the optional per-mode default
(`"_default"`) and finally to ``DEFAULT_CORRECTION_FACTOR``.
"""
from __future__ import annotations

from typing import Dict

DEFAULT_CORRECTION_FACTOR: float = 1.0

# Mapping: sensor -> sensor_mode -> {fps -> correction factor}
# Modes start with indices 0 and 1 for each sensor so that additional FPS
# entries can be appended as measurements become available.
SENSOR_CORRECTION_FACTORS: Dict[str, Dict[int | str, Dict[int, float] | float]] = {
    "imx296": {
        "_default": DEFAULT_CORRECTION_FACTOR,
        0: {},
        1: {},
    },
    "imx286": {
        "_default": DEFAULT_CORRECTION_FACTOR,
        0: {},
        1: {},
    },
    "imx283": {
        "_default": DEFAULT_CORRECTION_FACTOR,
        0: {},
        1: {},
    },
    "imx477": {
        "_default": DEFAULT_CORRECTION_FACTOR,
        0: {},
        1: {},
    },
    "imx519": {
        "_default": DEFAULT_CORRECTION_FACTOR,
        0: {},
        1: {},
    },
    "imx585": {
        "_default": DEFAULT_CORRECTION_FACTOR,
        0: {},
        1: {},
    },
    "imx585_mono": {
        "_default": DEFAULT_CORRECTION_FACTOR,
        0: {
            24: 0.9994, #verified 10000 frames 4K
            25: 0.9993,    
        },
        1: {
            24: 0.9980, #verified 10000 frames
            25: 0.9979, #verified 10000 frames
        },
    },
}

__all__ = ["DEFAULT_CORRECTION_FACTOR", "SENSOR_CORRECTION_FACTORS"]