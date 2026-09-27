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

# The DELIVERY shape a camera nobody has chosen ratios for starts out selected
# on, alongside that camera's own full frame. SensorDetect._default_ratio_ids
# puts the pair together.
#
# Operator instruction, 2026-09-26: "change the stock settings file to expose
# the 1.33 and 1.78 (or closest) for imx477 as default. for other sensors,
# default should be full frame and 1.78."
#
# That is ONE rule, not two, and it is worth saying why -- it looks like it
# needs an imx477 special case and it does not. imx477's full frame (4056x3040,
# 1.334) IS 1.33:1, so "full frame + 1.78-or-closest" already gives imx477
# exactly the 1.33 the operator asked for. Per-sensor branching here would be a
# second place for the rule to live and to drift.
#
# The "or closest" half is the real change from the previous default. Before,
# 1.78:1 was selected only when some mode came *home* to it, so a sensor with
# no 16:9 mode at all -- imx477's widest is 2028x1080 = 1.878, which comes home
# to 1.89:1 -- matched neither preferred ratio and fell back to its entire
# table. Now the nearest shape the camera actually has stands in for 1.78, so
# imx477 opens on 1.33:1 + 1.89:1 instead of on everything.
#
# Worked through, with each camera's own modes:
#   imx477  full 1.334 -> "1.33:1"           nearest to 16/9: 1.89:1  => 1.33 + 1.89
#   imx283  full 1.50  -> FULL_FRAME_RATIO_ID  has 1.78:1            => full + 1.78
#   imx585  full 1.769 -> "1.78:1"             has 1.78:1            => 1.78 alone
#   imx296  full 1.338 -> "1.33:1"           nearest to 16/9: 1.33:1  => 1.33 alone
# The last two collapse to one toggle because the two halves name the same
# shape, which is correct: there is nothing else to offer.
#
# An id, not a value: the table is the one place a ratio's number lives (that
# is this module's whole job), so this is looked up in it, and a ratio missing
# from the table simply cannot be preferred.
PREFERRED_DELIVERY_RATIO_ID = "1.78:1"

# The fallback for the first slot, used when the driver reports no crop
# geometry and SensorDetect.full_frame_ratio() therefore cannot say what this
# camera's whole frame even is. Every stock sensor is in that position -- crop
# annotation is a CineMate-driver feature -- so without this the rule above
# would reduce to "1.78 alone" on exactly the cameras the operator named, and
# imx477 would lose 1.33 instead of gaining 1.89.
PREFERRED_SHAPE_RATIO_ID = "1.33:1"

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
