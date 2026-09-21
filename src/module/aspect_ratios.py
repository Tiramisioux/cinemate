"""One loader for resources/aspect_ratios.json -- the canonical ratio table.

ASPECT-RATIOS.md, "What CineMate does with this", step 2/5: id, exact value,
common name, in one file both the Python side (SensorDetect's per-sensor
availability derivation and the ratio matcher) and, from WP-CM-7, the
settings page read. A second copy in JavaScript is the mistake
resources/sensors.json's own loader (module.sensor_database) already exists
to avoid -- this module mirrors that one's shape deliberately.

Stdlib only, and no import of anything under module/ that pulls in redis:
the settings editor blueprint has to read this with no camera attached and
no Redis running, exactly like the sensor database.

resources/aspect_ratios.json is strict JSON (no comments), same convention
as resources/sensors.json -- a stray `//` would take the whole file down.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

DEFAULT_ASPECT_RATIO_TABLE_FILE = "resources/aspect_ratios.json"

# The ratios a camera nobody has chosen ratios for starts out selected on,
# in table order, and only the ones that camera has a mode for
# (SensorDetect._default_ratio_ids applies the "if present" half).
#
# Operator instruction, 2026-09-21: "make default selected aspect ratios for a
# new sensor the standard 1.33:1, 1.78:1 (if present)". These two because they
# are what footage is delivered in -- 4:3 and 16:9 -- not because of anything
# about the sensors: a fresh camera should open on the two shapes almost every
# operator wants, with the other twelve one toggle away in the settings page
# rather than filling the mode dial from the start.
#
# Ids, not values: the table is the one place a ratio's number lives (that is
# this module's whole job), so these are looked up in it and a ratio missing
# from it simply cannot be preferred.
PREFERRED_DEFAULT_RATIO_IDS = ("1.33:1", "1.78:1")

# The id of the synthetic "whole sensor" toggle, which is NOT in
# resources/aspect_ratios.json and deliberately so: it does not name a shape,
# it names "whatever this sensor reads when it reads everything". Its value,
# label and very existence are per-camera, so it cannot live in a table shared
# by every camera.
#
# Operator instruction, 2026-09-22: "among the aspect ratios, also add the full
# option (last). then i get the full frame options for the sensor regardless of
# aspect ratio. unless the full frame actually _is_ one of the aspect ratios.
# then this option should read: 1.33:1 (full)".
#
# So there are two shapes this takes, decided per camera in
# SensorDetect.full_frame_ratio():
#
#   - the sensor's full frame IS one of the table's ratios (within
#     ASPECT_RATIO_TOLERANCE) -- imx585's 3840x2160 is 1.78, imx477's 4056x3040
#     is 1.33 -- and then NO extra toggle appears. The existing one is simply
#     labelled "1.78:1 (full)", because turning it on already gives you the
#     whole sensor.
#   - the sensor's full frame is a shape the table does not carry -- the
#     imx283 is a 3:2 sensor at 1.50, and 1.50 is not one of the fourteen --
#     and then this id appears as its own toggle, sorted last (the settings
#     pane ranks unknown ids after every table id), labelled with the real
#     aspect and "(full)": "1.50:1 (full)".
#
# Why it is not simply a fifteenth row in the table: 1.50 is the imx283's
# native shape and nothing at all on an imx585, and a table entry would offer
# it on every camera. The toggle has to be derived from the sensor in front of
# you, which is the same reason available_aspect_ratios() is derived and never
# stored.
FULL_FRAME_RATIO_ID = "full"

logger = logging.getLogger(__name__)

_EMPTY: list[dict[str, Any]] = []


def repo_root() -> Path:
    # src/module/aspect_ratios.py -> repo root
    return Path(__file__).resolve().parents[2]


def resolve_aspect_ratio_table_path(path_value: str | None = None) -> Path:
    path = Path(path_value or DEFAULT_ASPECT_RATIO_TABLE_FILE)
    return path if path.is_absolute() else repo_root() / path


def load_aspect_ratio_table(path_value: str | None = None) -> list[dict[str, Any]]:
    """Parse the canonical ratio table, or return an empty one after warning.

    A missing/broken table must not stop CineMate from booting -- it falls
    back to no ratios matching, which _finalize_modes's existing "never leave
    a camera without modes" fallback already covers -- but it has to be
    loud: silently running with no ratio table looks like "no ratio is
    offered", not like a broken file.
    """
    path = resolve_aspect_ratio_table_path(path_value)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.warning("Aspect ratio table unavailable (%s): %s", path, exc)
        return list(_EMPTY)
    except json.JSONDecodeError as exc:
        logger.warning("Aspect ratio table is invalid JSON (%s): %s", path, exc)
        return list(_EMPTY)

    ratios = data.get("ratios") if isinstance(data, dict) else None
    if not isinstance(ratios, list):
        logger.warning("Aspect ratio table %s has no ratios array", path)
        return list(_EMPTY)

    out: list[dict[str, Any]] = []
    for entry in ratios:
        if not isinstance(entry, dict):
            continue
        rid = entry.get("id")
        value = entry.get("value")
        if rid is None or value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        out.append({
            "id": str(rid),
            "value": value,
            "name": entry.get("name", str(rid)),
        })
    return out
