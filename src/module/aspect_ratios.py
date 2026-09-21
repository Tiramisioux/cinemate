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
