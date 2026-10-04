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

The platform decision lives here too (PLAN.md D19). The source-built libcamera
tree keeps one tuning directory per ISP -- pisp/data for the Pi 5 family,
vc4/data for the Pi 4 family (Pi 4, 400, CM4) -- and each file carries the
"target" that libcamera checks against the running pipeline. That pair used
to be written twice, hardcoded to pisp, in cinepi_multi.py (--tuning-file) and
cinepi_controller.py (the white-balance ct_curve loader), which left a
generation-4 board launching without a tuning file at all and reading the
*Pi 5* curve for its white balance. Every function that depends on the
platform takes `is_pi4` as a parameter instead of reading the board itself, so
the callers pass sensor_detect.is_pi4_family() and the tests need no hardware.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


# What a wrong-platform file is, in the words an operator needs when the
# reason lands in a log line or a 400 body.
_TARGET_HINTS = {
    "pisp": "a Pi 4 / vc4 tuning cannot load on a Pi 5",
    "bcm2835": "a Pi 5 / PiSP tuning cannot load on a Pi 4",
}


def tuning_json_problem(data: Any, expected_target: str = "pisp") -> Optional[str]:
    """The JSON-shape rules a tuning file must satisfy, shared by the launch
    guard and the settings-editor upload route so the two can never disagree
    (PLAN.md S1.2). Takes already-parsed JSON -- the caller owns reading and
    parsing, since the two callers get their bytes from different places (a
    file on disk vs. an in-memory upload body).

    *expected_target* defaults to "pisp" so every existing caller -- the
    settings-editor upload route and the Pi 5 override guard -- keeps
    rejecting a vc4 file exactly as before. Only the autofocus layer
    (module/lens_tuning.py) passes "bcm2835": on a Pi 4 / CM4 it derives its
    tuning from the vc4 stock file, and that file is the one a "pisp" check
    would wrongly refuse.

    Returns None when *data* is fine, otherwise the reason a human or a log
    line should see.
    """
    target = data.get("target") if isinstance(data, dict) else None
    if target != expected_target:
        # Covers "not a dict" too (target is then None): a Pi 4 / vc4 tuning
        # (FINDINGS.md S2) is the only real-world way this fires with the
        # default, since every file resources/tuning_files/ ships is already
        # "pisp".
        hint = _TARGET_HINTS.get(expected_target)
        suffix = f" ({hint})" if hint else ""
        return f'target is "{target}", expected "{expected_target}"{suffix}'
    if not isinstance(data.get("algorithms"), list):
        return 'no "algorithms" list (not a version 2 tuning file)'
    return None


# libcamera's own tuning directories in the source-built tree
# (cinemate-install.sh build_libcamera builds both pipelines from
# $LIBCAMERA_DIR, default /home/pi/libcamera, and installs them under
# /usr/local/share/libcamera/ipa/rpi/). Keyed by the "target" a file in the
# directory must carry. Read at call time, so tests can point it at a tmp tree.
LIBCAMERA_DATA_DIRS = {
    "pisp": "/home/pi/libcamera/src/ipa/rpi/pisp/data",
    "bcm2835": "/home/pi/libcamera/src/ipa/rpi/vc4/data",
}


def tuning_target(is_pi4: bool) -> str:
    """The "target" a tuning file must carry on this platform: libcamera
    matches it against the running pipeline handler, PiSP on the Pi 5 family
    and VC4 ("bcm2835") on the Pi 4 family."""
    return "bcm2835" if is_pi4 else "pisp"


def libcamera_data_dir(is_pi4: bool) -> Path:
    """The stock tuning directory for this platform."""
    return Path(LIBCAMERA_DATA_DIRS[tuning_target(is_pi4)])


def stock_tuning_path(model_key: str, is_pi4: bool) -> Path:
    """Where libcamera's own tuning for *model_key* (e.g. "imx585_mono")
    lives on this platform. Pure: it does not check the file exists."""
    return libcamera_data_dir(is_pi4) / f"{model_key}.json"


def _load_checked(path: Path, expected_target: str) -> tuple[Optional[Path], str]:
    """(path, "ok") when *path* is a readable tuning file for
    *expected_target*, else (None, reason). The one place the three failure
    reasons are worded, so an override, a stock file and a derived base all
    read the same in a log line."""
    if not path.is_file():
        return None, f"file not found: {path}"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"unreadable or not JSON: {exc}"

    problem = tuning_json_problem(data, expected_target)
    if problem:
        return None, problem

    return path, "ok"


def resolve_stock_tuning(model_key: str, is_pi4: bool) -> tuple[Optional[Path], str]:
    """The stock tuning file for *model_key* on this platform, checked.

    (path, "ok") when it exists and carries the platform's target; otherwise
    (None, reason). Pure: no logging, no Redis. The Pi 4 launch path uses it
    to decide whether a --tuning-file can be passed at all -- on that family
    libcamera used to be left to find its own tuning, and still is whenever
    this says no.
    """
    return _load_checked(stock_tuning_path(model_key, is_pi4), tuning_target(is_pi4))


def resolve_tuning_override(
    override: dict, repo_root: Path, expected_target: str = "pisp",
) -> tuple[Optional[Path], str]:
    """Decide whether *override* names a tuning file cinepi-raw can actually
    load. Pure: no logging, no Redis, no globals -- so both the launch guard
    and its own unit tests can call it directly.

    *expected_target* is the running platform's tuning_target(); it defaults
    to "pisp" so a caller that does not pass it keeps the Pi 5 rule. A file
    for the other ISP is refused with the usual reason, in both directions.

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

    return _load_checked(resolved, expected_target)
