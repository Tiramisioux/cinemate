"""One loader for resources/sensors.json.

SensorDetect used to own the only reader. boot_config needs the same file now
that the link-frequency menu comes from the database rather than a table
hardcoded in Python, and a second loader would be a second set of fallback
rules to keep in step -- exactly the drift this database exists to prevent.

Stdlib only, and no import of anything under module/ that pulls in redis:
boot_config is imported by the settings editor blueprint, which has to work
with no camera attached and no Redis running.

A missing capability block means "this sensor does not support it", the same
convention log_encode uses. A *malformed* one is different: it means someone
edited the database and got it wrong, so it warns rather than passing
silently as an absence.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

DEFAULT_SENSOR_DATABASE_FILE = "resources/sensors.json"

logger = logging.getLogger(__name__)

_EMPTY: dict[str, Any] = {"schema_version": 1, "sensors": {}}


def repo_root() -> Path:
    # src/module/sensor_database.py -> repo root
    return Path(__file__).resolve().parents[2]


def resolve_database_path(path_value: str | None = None) -> Path:
    path = Path(path_value or DEFAULT_SENSOR_DATABASE_FILE)
    return path if path.is_absolute() else repo_root() / path


def load_sensor_database(path_value: str | None = None) -> dict[str, Any]:
    """Parse the database, or return an empty one after warning.

    sensors.json is strict JSON -- a single `//` comment takes the whole file
    down. Returning empty rather than raising keeps a broken database from
    stopping Cinemate from booting, but it must be loud: silently running with
    no sensor metadata looks like "this sensor has no capabilities".
    """
    path = resolve_database_path(path_value)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.warning("Sensor database unavailable (%s): %s", path, exc)
        return dict(_EMPTY)
    except json.JSONDecodeError as exc:
        logger.warning("Sensor database is invalid JSON (%s): %s", path, exc)
        return dict(_EMPTY)

    if not isinstance(data.get("sensors"), dict):
        logger.warning("Sensor database %s has no sensors object", path)
        return dict(_EMPTY)
    return data


def base_model(model: str) -> str:
    """'imx585_mono' -> 'imx585'. The database keys on the silicon, and the
    mono variant is the same die with a different CFA."""
    return model[:-len("_mono")] if model.endswith("_mono") else model


def sensor_entry(database: dict[str, Any], model: str) -> dict[str, Any]:
    sensors = database.get("sensors", {})
    entry = sensors.get(base_model(model))
    return entry if isinstance(entry, dict) else {}


def link_frequency_block(database: dict[str, Any], model: str) -> dict[str, Any]:
    """The sensor's link_frequency capability block, or {} if it has none.

    Warns on a block that is present but the wrong shape -- that is a database
    edit that went wrong, and treating it as "unsupported" would hide it.
    """
    entry = sensor_entry(database, model)
    if "link_frequency" not in entry:
        return {}

    block = entry["link_frequency"]
    if not isinstance(block, dict):
        logger.warning("link_frequency for %s is %s, expected an object", model, type(block).__name__)
        return {}

    options = block.get("options")
    if not isinstance(options, list) or not options:
        logger.warning("link_frequency for %s has no options list", model)
        return {}
    if any(not isinstance(o, dict) or not isinstance(o.get("hz"), int) for o in options):
        logger.warning("link_frequency for %s has an option with no integer hz", model)
        return {}

    default_hz = block.get("default_hz")
    if not isinstance(default_hz, int):
        logger.warning("link_frequency for %s has no integer default_hz", model)
        return {}
    if default_hz not in [o["hz"] for o in options]:
        logger.warning("link_frequency default_hz %s for %s is not among its options", default_hz, model)
        return {}

    return block


def link_frequency_values(database: dict[str, Any], model: str) -> list[int]:
    return [o["hz"] for o in link_frequency_block(database, model).get("options", [])]


def link_frequency_default(database: dict[str, Any], model: str) -> int | None:
    return link_frequency_block(database, model).get("default_hz")


def link_frequency_is_selectable(database: dict[str, Any], model: str) -> bool:
    """True when the overlay actually exposes a link-frequency parameter AND
    the menu is enabled.

    Two separate reasons a sensor with known values still offers no menu:
    the overlay has no parameter to set (imx296, imx519), or the values are
    recorded but the menu is deliberately held back pending hardware
    verification (`"menu_enabled": false` -- imx477 until Gate 2).
    """
    block = link_frequency_block(database, model)
    if not block:
        return False
    if not block.get("selectable", False):
        return False
    return block.get("menu_enabled", True) is not False


def link_frequency_max_for_platform(
    database: dict[str, Any], model: str, is_pi4: bool = False,
) -> int | None:
    """Receiver-side ceiling for this platform, or None if unrecorded.

    Mirrors get_packing_for_platform: the per-platform block narrows what the
    generic entry allows, it never widens it.
    """
    block = link_frequency_block(database, model)
    if not block:
        return None
    by_platform = block.get("by_platform")
    if not isinstance(by_platform, dict):
        return None
    entry = by_platform.get("pi4" if is_pi4 else "pi5")
    if not isinstance(entry, dict):
        return None
    max_hz = entry.get("max_hz")
    return max_hz if isinstance(max_hz, int) else None
