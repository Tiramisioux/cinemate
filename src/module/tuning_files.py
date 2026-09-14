"""Shared rule for what counts as a usable libcamera tuning file.

Standard library only, the way sensor_database.py's repo_root()/
resolve_database_path() are: this module is imported both by cinepi_multi.py
(the launch guard, before cinepi-raw ever starts) and by the settings-editor
Flask blueprint (the upload route, before a file is written), and the
settings editor "has to work with no camera attached and no Redis running"
(sensor_database.py's own docstring). Importing cinepi_multi.py itself from
the blueprint to reuse this logic would work today -- a bare `python3 -c`
import with the same sys.modules stubs the launch test uses succeeds -- but
it would newly pull module.framebuffer and module.storage_profiles into the
editor's process for two small pure functions, coupling a settings-page
upload route to the camera-launch module's entire import graph for no
reason. Keeping the rule here instead means the launch guard and the editor
both depend downward on one small, dependency-free module, never on each
other (PLAN.md S1.2).

FINDINGS.md S1 is why this has to run before --tuning-file is ever built:
libcamera's ipa_proxy.cpp treats the LIBCAMERA_RPI_TUNING_FILE env override
as authoritative and never stat()s it, so a path that cannot be opened fails
camera *registration* outright further down the stack, while cinepi_multi.py's
own camera *discovery* already succeeded without the flag -- so the launch is
attempted, times out, and CineMate comes up with the GUI alive and HDMI
black. The only place a bad override can be turned into a degraded picture
instead of a black one is here, before the launch. FINDINGS.md S2 is the
second way to the same ending: a "target": "bcm2835" file (a Pi 4 / vc4
tuning) opens fine but fails libcamera's platform check the same way.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


def tuning_json_problem(data: Any) -> Optional[str]:
    """The JSON-shape rules a tuning file must satisfy, shared by the launch
    guard and the settings-editor upload route so the two can never disagree
    (PLAN.md S1.2). Takes already-parsed JSON -- the caller owns reading and
    parsing, since the two callers get their bytes from different places (a
    file on disk vs. an in-memory upload body).

    Returns None when *data* is fine, otherwise the reason a human or a log
    line should see.
    """
    target = data.get("target") if isinstance(data, dict) else None
    if target != "pisp":
        # Covers "not a dict" too (target is then None): a Pi 4 / vc4 tuning
        # (FINDINGS.md S2) is the only real-world way this fires, since every
        # file resources/tuning_files/ ships is already "pisp".
        return f'target is "{target}", expected "pisp" (a Pi 4 / vc4 tuning cannot load on a Pi 5)'
    if not isinstance(data.get("algorithms"), list):
        return 'no "algorithms" list (not a version 2 tuning file)'
    return None


def resolve_tuning_override(override: dict, repo_root: Path) -> tuple[Optional[Path], str]:
    """Decide whether *override* names a tuning file cinepi-raw can actually
    load. Pure: no logging, no Redis, no globals -- so both the launch guard
    and its own unit tests can call it directly.

    Returns (path, "ok") when usable; otherwise (None, reason), where reason
    is a short phrase safe to put straight into a log line or a 400 body.
    Relative paths resolve against *repo_root* -- not the process's current
    working directory, which is what made this fragile before (FINDINGS.md
    S3.1: a relative override only worked because cinemate-autostart.service
    happened to pin WorkingDirectory=/home/pi/cinemate; see
    cinemate-handbook/working/changing-the-installer.md, "Prefer absolute
    paths"). sensors.database_file in this same settings block already
    resolves this way via sensor_database.repo_root() -- this reuses that
    convention rather than requiring "always absolute".
    """
    if not override.get("enabled"):
        return None, "disabled"

    raw_path = override.get("path")
    if not raw_path:
        return None, "enabled but no path set"

    candidate = Path(raw_path)
    resolved = candidate if candidate.is_absolute() else repo_root / candidate

    if not resolved.is_file():
        return None, f"file not found: {resolved}"

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"unreadable or not JSON: {exc}"

    problem = tuning_json_problem(data)
    if problem:
        return None, problem

    return resolved, "ok"
