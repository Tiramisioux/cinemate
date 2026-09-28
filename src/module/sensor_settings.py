"""Per-sensor settings: settings_<camera>.jsonc, one file per sensor model.

Operator report, 2026-09-28: swapping imx585 -> imx477 left the settings pane
showing only the 2K crop's rows, because the aspect-ratio SELECTION that was
right for the imx585 (a global `image_capture.aspect_ratios` key) silently
carried over and narrowed the imx477 to a ratio it barely has. PLAN.md's
fix moves the three per-camera selection keys -- aspect_ratios, enabled_modes,
custom_modes -- out of settings.jsonc and into a file scoped to the sensor
MODEL, so swapping cameras can never again apply one sensor's saved choices
to another.

Precedence per camera, resolved once at boot (resolve_sensor_settings):
`settings_<camera>.jsonc` (this module) beats a legacy per-camera entry in
settings.jsonc's image_capture section, which beats the stock rule computed
fresh from the camera's own mode table (sensor_detect.py). A missing key,
at any level, means "stock for that key" -- there is no partial fall-through
from "file" to "legacy": once a file exists for a camera, that camera's
config is the file, whatever it does or does not mention.

Stdlib only, no redis import -- the settings editor must be able to load this
with no camera attached and no Redis running, exactly like sensor_database.py
and aspect_ratios.py (see their own module docstrings). Mirrors their shape:
a loader that warns and returns None/{} on a broken file rather than raising,
because a corrupt per-sensor file must not be able to stop CineMate booting.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from module.config_loader import strip_jsonc

logger = logging.getLogger(__name__)

SENSOR_SETTINGS_VERSION = 1

# The three per-camera keys that move out of settings.jsonc's image_capture
# section and into a sensor's own file. Global filters that are not scoped to
# one camera -- bit_depths, k_steps, min_mode_width, the HDR switches -- stay
# in settings.jsonc; see PLAN.md's "Which keys move to the per-sensor file?"
# row for why the split falls exactly here.
SENSOR_SCOPED_KEYS = ("aspect_ratios", "enabled_modes", "custom_modes")

# settings_<name>.jsonc backups live beside the per-sensor files themselves,
# same directory and same retention settings_editor.py already uses for
# settings.jsonc's own backups -- see backup_file()'s docstring.
BACKUP_DIR_NAME = ".settings-backups"
BACKUP_KEEP = 10

_INVALID_NAME_CHARS_RE = re.compile(r"[^a-z0-9_]")


def _normalized_camera_name(camera_name: str) -> str:
    """camera model, lowercased, with every character outside [a-z0-9_]
    replaced by '_'. Raises ValueError when nothing survives -- there is no
    safe filename to write for an empty or punctuation-only name."""
    name = _INVALID_NAME_CHARS_RE.sub("_", (camera_name or "").lower())
    if not name:
        raise ValueError(
            f"camera name {camera_name!r} has no characters valid in a filename"
        )
    return name


def sensor_settings_filename(camera_name: str) -> str:
    """The basename alone, e.g. "settings_imx477.jsonc" -- split out from
    sensor_settings_path() so a caller that only needs the name for display
    (the settings-editor endpoint's `file` field, which PLAN.md's contract
    says is "always present", file-on-disk or not) does not need a directory
    to compute it."""
    return f"settings_{_normalized_camera_name(camera_name)}.jsonc"


def sensor_settings_path(camera_name: str, settings_dir: str | Path) -> Path:
    """settings_dir/settings_<name>.jsonc for this camera.

    Two sensors of the same model (a dual-imx585 rig) resolve to the SAME
    path here, deliberately: the file is scoped to the sensor MODEL, not to
    which physical port it is plugged into, because the operator's mode/ratio
    choices are a property of "the imx585 I own", not of cam0 vs cam1. See
    sensor_detect.SensorDetect's own comment where this is wired in.
    """
    return Path(settings_dir) / sensor_settings_filename(camera_name)


def backup_file(dest: Path) -> Path | None:
    """Copy *dest* aside before it is overwritten. Returns the backup path,
    or None when there was nothing to back up (a missing source is not a
    reason to refuse the write).

    Moved here from settings_editor.py's own _backup_settings() (per-sensor-
    settings-backend, 2026-09-28): that function's body was always stdlib-
    only -- Path, datetime, logging, no Flask -- so it could move somewhere
    both settings.jsonc's own save path and this module's save_sensor_
    settings() can call, rather than this module growing a second copy of
    the same backup/retention logic. settings_editor._backup_settings is now
    a thin alias for this function; see its own comment for why that one is
    kept (external callers/tests still import it by that name).
    """
    try:
        data = dest.read_bytes()
    except OSError as exc:
        logger.info("No backup taken for %s: %s", dest, exc)
        return None

    backup_dir = dest.parent / BACKUP_DIR_NAME
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = backup_dir / f"{dest.name}.{stamp}.bak"
        counter = 1
        while target.exists():  # two saves inside one second
            target = backup_dir / f"{dest.name}.{stamp}-{counter}.bak"
            counter += 1
        target.write_bytes(data)

        keep = sorted(backup_dir.glob(f"{dest.name}.*.bak"))[:-BACKUP_KEEP]
        for stale in keep:
            stale.unlink(missing_ok=True)
    except OSError as exc:
        # Losing the backup must not lose the save -- but say so, loudly.
        logger.error("Could not back up %s before saving: %s", dest, exc)
        return None

    return target


def _validate_scoped_value(key: str, value: Any) -> bool:
    """True when *value* is the shape SENSOR_SCOPED_KEYS[key] must be:
    aspect_ratios is a list of str; enabled_modes/custom_modes are each a
    list of dict. Anything else is a hand-edited or corrupted file -- the
    caller drops that one key rather than trusting it."""
    if not isinstance(value, list):
        return False
    if key == "aspect_ratios":
        return all(isinstance(v, str) for v in value)
    return all(isinstance(v, dict) for v in value)


def load_sensor_settings(camera_name: str, settings_dir: str | Path) -> dict | None:
    """Parse settings_<camera>.jsonc, or None when it is absent or broken.

    A missing file is the ordinary case (no per-sensor choice saved yet) and
    logs nothing. A file that exists but fails to parse, or is not a JSON
    object, is different -- someone or something wrote a broken file -- and
    that is logged at error, same as sensor_database.load_sensor_database()'s
    own "must not stop CineMate booting, but must be loud" rule. Either way
    the caller falls back to the next precedence level (see
    resolve_sensor_settings); a broken file must never crash the boot.

    Each of SENSOR_SCOPED_KEYS is validated independently and dropped on its
    own if the wrong shape, so one broken key does not throw away a sibling
    key that parsed fine. Unknown top-level keys (a stray hand edit) are
    silently ignored.
    """
    path = sensor_settings_path(camera_name, settings_dir)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.error("Could not read %s: %s", path, exc)
        return None

    try:
        data = json.loads(strip_jsonc(raw))
    except ValueError as exc:
        logger.error("%s is not valid JSON(C): %s", path, exc)
        return None

    if not isinstance(data, dict):
        logger.error(
            "%s must contain a JSON object, found %s", path, type(data).__name__,
        )
        return None

    out: dict[str, Any] = {}
    for key in SENSOR_SCOPED_KEYS:
        if key not in data:
            continue
        if _validate_scoped_value(key, data[key]):
            out[key] = data[key]
        else:
            logger.error("%s: %r is the wrong shape for %s -- ignoring it", path, data[key], key)
    return out


def save_sensor_settings(camera_name: str, data: dict, settings_dir: str | Path) -> Path:
    """Write camera_name's own settings file: header comment, then `version`,
    `sensor`, and whichever of SENSOR_SCOPED_KEYS *data* provides (a key
    *data* omits, or sets to None, is left out of the file entirely -- that
    is what "stock for that key" means on disk). Anything in *data* outside
    SENSOR_SCOPED_KEYS is dropped, same convention load_sensor_settings()
    uses for an unknown key on read.

    Atomic: a backup of any existing file first (backup_file(), same
    retention as settings.jsonc's own saves), then write to a temp file in
    the same directory, fsync, and os.replace() over the real path -- so a
    reader never observes a half-written file and a crash mid-write leaves
    the previous version intact, not a corrupt one.
    """
    path = sensor_settings_path(camera_name, settings_dir)
    payload: dict[str, Any] = {
        "version": SENSOR_SETTINGS_VERSION,
        "sensor": _normalized_camera_name(camera_name),
    }
    for key in SENSOR_SCOPED_KEYS:
        value = data.get(key)
        if value is not None:
            payload[key] = value

    header = (
        f"// CineMate settings for the {camera_name} sensor, written by the "
        f"settings editor.\n"
        f"// Delete this file (or use \"Reset to stock\") to return this "
        f"sensor to stock.\n"
    )
    text = header + json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    backup_file(path)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}-", suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(text)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise
    return path


def delete_sensor_settings(camera_name: str, settings_dir: str | Path) -> bool:
    """Back up, then delete camera_name's file. Idempotent: a camera with no
    file already reports success without taking a backup -- "this sensor now
    has no file" is already true, and there is nothing to back up."""
    path = sensor_settings_path(camera_name, settings_dir)
    if not path.exists():
        return True
    backup_file(path)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.error("Could not delete %s: %s", path, exc)
        return False
    return True


def legacy_sensor_settings(settings: dict, camera_name: str) -> dict:
    """This camera's own entries from image_capture.aspect_ratios/
    enabled_modes/custom_modes. Never "default": PLAN.md D2 -- a settings.
    jsonc left with a stray global `"default"` entry (from before per-sensor
    files existed) is exactly the cross-sensor carrier that let an imx585
    choice narrow an imx477 after a swap, and per-sensor files exist to make
    that impossible by construction. A per-camera key is the only legacy
    source this reads; "default" is surfaced separately, as a notice, by
    sensor_detect.py -- never as a value here.
    """
    image_capture = settings.get("image_capture") if isinstance(settings, dict) else None
    image_capture = image_capture if isinstance(image_capture, dict) else {}
    out: dict[str, Any] = {}
    for key in SENSOR_SCOPED_KEYS:
        section = image_capture.get(key)
        if not isinstance(section, dict):
            continue
        value = section.get(camera_name)
        if value:
            out[key] = value
    return out


def resolve_sensor_settings(
    settings: dict, camera_name: str, settings_dir: str | Path | None,
) -> tuple[dict, str]:
    """(data, source) for camera_name: settings_<camera>.jsonc beats a legacy
    per-camera entry in settings.jsonc, which beats the stock rule.

    source is "file" the moment a file exists and parses -- even one that
    defines none of SENSOR_SCOPED_KEYS -- because a file's presence, not its
    contents, is what ends legacy fall-through: PLAN.md's contract reads
    legacy settings.jsonc entries "only when no per-sensor file exists",
    not key by key. "legacy" is returned only when at least one per-camera
    entry actually exists; a settings.jsonc that never mentions this camera
    at all resolves to "stock" with an empty dict, same as a present-but-
    empty file would.

    settings_dir=None disables the file layer entirely (legacy/stock only)
    -- this is what keeps a SensorDetect built for a unit test hermetic; a
    test must never read a real /home/pi/cinemate/settings_*.jsonc just
    because it happened to run on a machine that has one. See
    SensorDetect.__init__.
    """
    if settings_dir is not None:
        from_file = load_sensor_settings(camera_name, settings_dir)
        if from_file is not None:
            return from_file, "file"
    legacy = legacy_sensor_settings(settings, camera_name)
    if legacy:
        return legacy, "legacy"
    return {}, "stock"
