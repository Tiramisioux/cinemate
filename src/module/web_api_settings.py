"""Shared settings["system"]["web_api"] defaults and merge helper.

Split out of module.app.api so module.status_broadcast (and main.py) don't
need to import flask/flask_socketio just to read this one settings block.
See docs/web-api.md ("Settings") for the documented contract.
"""
from __future__ import annotations

import copy

DEFAULT_WEB_API_SETTINGS = {
    "enabled": True,
    "token": "",
    "allow_destructive": False,
    "max_commands_per_sec": 20,
    "max_sse_clients": 4,
    "broadcast": {
        "enabled": True,
        "port": 8888,
        "hz": 5,
        "keys": [
            "is_recording", "iso", "fps", "shutter_a_actual",
            "recording_tc_tod", "space_left", "drop_frame_count", "is_mounted",
        ],
    },
}


def web_api_settings(settings):
    """Merge settings["system"]["web_api"] over the documented defaults.

    A missing or partial block behaves exactly like the full defaults —
    users must not have to edit settings.jsonc to get a working API.
    """
    cfg = ((settings or {}).get("system", {}) or {}).get("web_api", {}) or {}
    merged = dict(DEFAULT_WEB_API_SETTINGS)
    merged.update({k: v for k, v in cfg.items() if k != "broadcast"})
    merged["broadcast"] = copy.deepcopy(DEFAULT_WEB_API_SETTINGS["broadcast"])
    merged["broadcast"].update(cfg.get("broadcast", {}) or {})
    return merged
