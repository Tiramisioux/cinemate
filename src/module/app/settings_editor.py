"""Settings editor blueprint.

Real read/write UI for settings.jsonc, backed by the same
`cinepi_controller` the GPIO/quad-rotary dispatch and the CLI/web-API command
table already use. See templates/settings_editor.html, which this blueprint
serves -- ported panel by panel from the original settings-editor-ui mockup.
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import re
import tempfile
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    make_response,
    render_template,
    request,
    send_file,
    send_from_directory,
    stream_with_context,
)

from markupsafe import Markup

from module.app import hardware_probe
from module.app.gui_text import load_gui_text, lookup
from module.sensor_database import resolve_database_path
from module.config_loader import (
    DEFAULT_CONFORM_FRAME_RATE,
    SettingsLoadError,
    _apply_settings_defaults,
    load_settings,
    strip_jsonc,
    DEFAULT_SETTINGS_PATH,
    thumbnail_size_startup_value,
)
from module.app import boot_config, playback, raw_files
from module.jsonc_edit import apply_updates
from module.redis_controller import ParameterKey, smpte_frame_base
from module.sensor_detect import (
    thumbnail_choice_labels,
    SensorDetect,
)
from module.tuning_files import tuning_json_problem
from module.web_api_settings import web_api_settings

logger = logging.getLogger(__name__)

settings_editor_bp = Blueprint(
    "settings_editor",
    __name__,
    url_prefix="/settings-editor",
    template_folder="templates",
)

SETTINGS_FILE = DEFAULT_SETTINGS_PATH

# Shipped template (resources/settings/settings_default.jsonc) -- used as
# (a) the GET /api/settings fallback when the live file is missing, and
# (b) the source for the "revert to defaults" action. Resolved relative to
# the repo root, same pattern as sensor_detect.py's _resolve_repo_path.
STOCK_SETTINGS_FILE = Path(__file__).resolve().parents[3] / "resources/settings/settings_default.jsonc"

# Backs both tuning-file pickers and the upload route (FINDINGS.md S3.3, S1;
# PLAN.md S1.2). Same parents[3]-to-repo-root pattern as STOCK_SETTINGS_FILE.
TUNING_FILES_DIR = Path(__file__).resolve().parents[3] / "resources/tuning_files"
TUNING_FILES_REL = "resources/tuning_files"
# The largest shipped file is ~90 KB; a full pisp tuning with LSC tables
# stays well under this.
TUNING_FILE_MAX_BYTES = 4 * 1024 * 1024
TUNING_FILE_NAME_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.json$")

# Corrected copy of the mockup's original ACTION_METHODS catalog. Fixes the
# 3 entries that don't resolve via getattr() on cinepi_controller -- the
# same lookup gpio_input.py / i2c/quad_rotary_controller.py use at dispatch
# time: 'erase' -> 'erase_drive', 'format' -> 'format_drive',
# 'storage_preroll' dropped (it's CLI/serial/web-API-only, bound to a
# separate storage_preroll object, not a cinepi_controller method -- see
# cli_commands.py's 'storage preroll' entry).
# Every dispatcher (gpio_input.py, i2c/quad_rotary_controller.py,
# cli_commands.py) resolves the method by getattr and calls
# `method(*action.get("args", []))`. No argument is ever injected and arity is
# never checked, so an action saved WITHOUT args calls the method with zero
# arguments -- and the method's own signature is the only thing deciding what
# happens. "no_arg" records that, per method, so the editor can say which it
# is instead of labelling every blank the same way:
#
#   "cycle"    -- value=None and the body steps to the next entry in the list
#   "toggle"   -- value=None and the body inverts the current flag
#   "required" -- a bare positional (TypeError), or an optional parameter with
#                 no None branch, so leaving it blank is never what you want
#
# The distinction is not cosmetic. Before it existed the arg control offered
# one blank option reading "(none - toggle)" for all of them, which was untrue
# for eleven methods -- including format_drive, where `filesystem or "exfat"`
# means a blank argument silently formats the card.
ACTION_METHODS = [
    {"group": "Record", "value": "rec", "label": "Start / stop recording"},
    {"group": "ISO", "value": "set_iso", "label": "Set ISO", "no_arg": "required",
     "arg": {"type": "select", "options": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200]}},
    {"group": "ISO", "value": "inc_iso", "label": "ISO up one stop"},
    {"group": "ISO", "value": "dec_iso", "label": "ISO down one stop"},
    {"group": "ISO", "value": "set_iso_lock", "label": "Toggle ISO lock", "no_arg": "toggle", "arg": {"type": "toggle01"}},
    {"group": "ISO", "value": "set_iso_free", "label": "Toggle ISO free stepping", "no_arg": "toggle", "arg": {"type": "toggle01"}},
    {"group": "Shutter", "value": "set_shutter_a", "label": "Set shutter angle", "no_arg": "required",
     "arg": {"type": "select", "options": [1, 45, 90, 135, 172.8, 180, 225, 270, 315, 346.6, 360], "suffix": "°"}},
    {"group": "Shutter", "value": "inc_shutter_a", "label": "Shutter angle up one stop"},
    {"group": "Shutter", "value": "dec_shutter_a", "label": "Shutter angle down one stop"},
    {"group": "Shutter", "value": "set_shutter_a_nom", "label": "Set nominal shutter angle", "no_arg": "required",
     "arg": {"type": "number", "step": 0.1, "placeholder": "angle"}},
    {"group": "Shutter", "value": "set_shutter_a_sync_mode", "label": "Set shutter-sync mode", "no_arg": "toggle", "arg": {"type": "toggle01"}},
    {"group": "Shutter", "value": "set_shutter_a_nom_lock", "label": "Toggle nominal-shutter lock", "no_arg": "toggle", "arg": {"type": "toggle01"}},
    {"group": "Shutter", "value": "set_shutter_a_free", "label": "Toggle shutter free stepping", "no_arg": "toggle", "arg": {"type": "toggle01"}},
    {"group": "Frame rate", "value": "set_fps", "label": "Set frame rate", "no_arg": "required",
     "arg": {"type": "select", "options": [25, 33, 50]}},
    {"group": "Frame rate", "value": "inc_fps", "label": "Frame rate up one stop"},
    {"group": "Frame rate", "value": "dec_fps", "label": "Frame rate down one stop"},
    {"group": "Frame rate", "value": "set_fps_lock", "label": "Toggle FPS lock", "no_arg": "toggle", "arg": {"type": "toggle01"}},
    {"group": "Frame rate", "value": "set_fps_free", "label": "Toggle FPS free stepping", "no_arg": "toggle", "arg": {"type": "toggle01"}},
    {"group": "Frame rate", "value": "set_fps_double", "label": "Toggle double-fps mode", "no_arg": "toggle", "arg": {"type": "toggle01"}},
    {"group": "Frame rate", "value": "set_shu_fps_lock", "label": "Toggle nominal shutter+fps lock", "no_arg": "toggle", "arg": {"type": "toggle01"}},
    {"group": "White balance", "value": "set_wb", "label": "Set white balance", "no_arg": "cycle",
     "arg": {"type": "select", "options": [3200, 4400, 5600], "suffix": "K"}},
    {"group": "White balance", "value": "inc_wb", "label": "White balance up one stop"},
    {"group": "White balance", "value": "dec_wb", "label": "White balance down one stop"},
    {"group": "White balance", "value": "set_wb_free", "label": "Toggle WB free stepping", "no_arg": "toggle", "arg": {"type": "toggle01"}},
    {"group": "ClearHDR", "value": "set_hdr_threshold_low", "label": "Set HDR threshold low", "no_arg": "required",
     "arg": {"type": "number", "min": 0, "max": 4095, "placeholder": "0-4095"}},
    {"group": "ClearHDR", "value": "set_hdr_threshold_high", "label": "Set HDR threshold high", "no_arg": "required",
     "arg": {"type": "number", "min": 0, "max": 4095, "placeholder": "0-4095"}},
    {"group": "ClearHDR", "value": "set_hdr_blend", "label": "Set HDR blend", "no_arg": "required",
     "arg": {"type": "number", "min": 0, "max": 8, "placeholder": "0-8"}},
    {"group": "ClearHDR", "value": "set_hdr_gain_adder", "label": "Set HDR gain adder", "no_arg": "required",
     "arg": {"type": "number", "min": 0, "max": 5, "placeholder": "0-5"}},
    {"group": "CineMate Log", "value": "set_log_encode", "label": "Set CineMate Log target", "no_arg": "toggle",
     "arg": {"type": "select", "options": ["off", "10", "12"]}},
    {"group": "Thumbnail", "value": "set_thumbnail", "label": "Set DNG thumbnail mode", "no_arg": "required",
     "arg": {"type": "select", "options": ["off", "mono", "colour", "jpeg"]}},
    {"group": "Zoom / anamorphic", "value": "set_zoom", "label": "Set preview zoom", "no_arg": "cycle",
     "arg": {"type": "select", "options": [1, 2], "suffix": "×"}},
    {"group": "Zoom / anamorphic", "value": "inc_zoom", "label": "Zoom in one stop"},
    {"group": "Zoom / anamorphic", "value": "dec_zoom", "label": "Zoom out one stop"},
    {"group": "Zoom / anamorphic", "value": "set_anamorphic_factor", "label": "Set anamorphic desqueeze", "no_arg": "cycle",
     "arg": {"type": "select", "options": [1, 1.33, 2], "suffix": "×"}},
    {"group": "Resolution / preview", "value": "set_resolution", "label": "Change resolution", "no_arg": "cycle",
     "arg": {"type": "number", "placeholder": "mode #"}},
    {"group": "Resolution / preview", "value": "set_dynamic_resolution_enabled", "label": "Toggle dynamic resolution", "no_arg": "toggle", "arg": {"type": "toggle01"}},
    {"group": "Resolution / preview", "value": "set_dynamic_resolution_priority", "label": "Dynamic resolution priority", "no_arg": "cycle", "arg": {"type": "select", "options": ["mode", "resolution", "none"]}},
    {"group": "Resolution / preview", "value": "set_preview_source", "label": "Set HDMI preview source", "no_arg": "cycle",
     "arg": {"type": "select", "options": ["cam0", "cam1", "cam0+cam1", "pip_cam0", "pip_cam1"]}},
    {"group": "Storage", "value": "mount", "label": "Mount storage"},
    {"group": "Storage", "value": "unmount", "label": "Unmount storage"},
    {"group": "Storage", "value": "toggle_mount", "label": "Toggle mount / unmount"},
    {"group": "Storage", "value": "erase_drive", "label": "Erase drive"},
    # required, not "defaults to exfat": format_drive() falls back to exfat on
    # a blank argument, so an unset filesystem here would format the card.
    {"group": "Storage", "value": "format_drive", "label": "Format drive", "no_arg": "required",
     "arg": {"type": "select", "options": ["exfat", "ext4", "ntfs"]}},
    # set_filter's else-branch returns "Invalid value provided." -- it acts on
    # 0 or 1 only and has no toggle branch, whatever its old label implied.
    {"group": "Sensor", "value": "set_filter", "label": "Set IR-cut filter", "no_arg": "required", "arg": {"type": "toggle01"}},
    {"group": "Locks", "value": "set_all_lock", "label": "Toggle all-parameter lock", "no_arg": "toggle", "arg": {"type": "toggle01"}},
    {"group": "System", "value": "restart_cinemate", "label": "Restart CineMate"},
    {"group": "System", "value": "restart_camera", "label": "Restart camera process"},
    {"group": "System", "value": "reboot", "label": "Reboot the Pi"},
    {"group": "System", "value": "safe_shutdown", "label": "Safe shutdown"},
]


@settings_editor_bp.record_once
def _install_gui_text(state) -> None:
    """Give the app serving this blueprint its `t()` template global.

    The editor's copy lives in resources/gui-text/*.md, not in the template.
    It is read once, when the blueprint is registered -- i.e. at CineMate
    start -- so a page load costs nothing and every request sees the same
    text. Editing a string means restarting CineMate, the same as editing
    anything else under src/.

    Registered here rather than in create_app() because the template belongs
    to this blueprint: anything that serves the settings editor gets the text
    with it, including a test harness that builds a bare Flask app around
    just this blueprint.
    """
    gui_text = load_gui_text()
    state.app.config["GUI_TEXT"] = gui_text
    # Markup, not str: these strings carry their own <span class="mono"> and
    # <strong>, and render_inline has already escaped what came from markdown.
    state.app.jinja_env.globals["t"] = lambda key: Markup(lookup(gui_text, key))


def _public_method_names(obj) -> set[str]:
    return {
        name for name, member in inspect.getmembers(obj)
        if not name.startswith("_") and callable(member)
    }


# Every state in which the card is being written at rate. is_recording alone
# is not that set: the post-take buffer flush (is_writing_buf / is_buffering)
# and storage pre-roll all move frames to disk, and pre-roll in particular
# writes at full rate with is_recording still 0. These are exactly the
# storage-contention windows the playback lockout exists for.
_PLAYBACK_BLOCKING_KEYS = (
    ParameterKey.IS_RECORDING,
    ParameterKey.IS_WRITING_BUF,
    ParameterKey.IS_BUFFERING,
    ParameterKey.STORAGE_PREROLL_ACTIVE,
)


def _playback_blocked() -> tuple[bool, str]:
    """Whether the card is too busy to serve playback, and why.

    Fails CLOSED, unlike the read it replaced. RedisController.get_value()
    returns a local cache kept fresh by one background listener thread; if
    that thread has died every read keeps succeeding and every value is
    frozen (the handbook's trap 1, hardware-confirmed as F-204). A frozen
    "0" would let the pane start decoding in the middle of a take, which is
    the one thing this gate exists to prevent -- so a dead listener, or an
    unreadable bus, refuses rather than allows.
    """
    redis_controller = current_app.config.get("REDIS_CONTROLLER")
    if redis_controller is None:
        return False, ""          # no bus wired at all: desk/test use
    try:
        if not redis_controller.listener_alive():
            return True, "Camera status is stale — playback held"
        for key in _PLAYBACK_BLOCKING_KEYS:
            if str(redis_controller.get_value(key.value)).strip() == "1":
                return True, f"Busy ({key.value}) — playback held"
    except Exception:
        logger.debug("playback: could not read the recording state", exc_info=True)
        return True, "Camera status unavailable — playback held"
    return False, ""


def _is_recording() -> bool:
    """Whether playback is currently refused. Reported in the clip index so the
    pane can grey the stage out before it asks for a frame."""
    return _playback_blocked()[0]


# 16:9 lores plane, the same fallback thumbnail_choice_labels()'s own
# reservation/estimate formulas are written against -- used only when no
# camera is attached (SENSOR_DETECT unset, or CINEPI_CONTROLLER has not
# resolved a mode yet), so the DNG-thumbnails card still renders sane
# labels rather than guessing at 0x0 or raising.
_FALLBACK_LORES_SIZE = (1280, 720)


def _current_thumbnail_editor_context(settings: dict) -> dict:
    """Template context for the settings editor's "DNG thumbnails" card:
    the four mode choices' labels (thumbnail_choice_labels(), sized for the
    CURRENT camera's lores plane and thumbnail_size) and the three
    dimension strings the size <select>'s own options show.

    Lores plane: from the live sensor mode via CINEPI_CONTROLLER's
    SensorDetect (the same res_modes/sensor_mode/_calc_lores() lookup
    _recompute_file_size() uses in cinepi_controller.py), falling back to
    _FALLBACK_LORES_SIZE when no camera has resolved a mode.

    thumbnail_size: the live Redis value if one is set, else the validated
    settings.jsonc startup value -- "Redis first, settings.jsonc second",
    the same precedence _recompute_file_size() uses, because an operator's
    live `set thumbnail_size` (it restarts the camera immediately) is a
    truer answer for "what size is this camera keeping" than the file.
    """
    controller = current_app.config.get("CINEPI_CONTROLLER")
    redis_controller = current_app.config.get("REDIS_CONTROLLER")

    lores_w, lores_h = _FALLBACK_LORES_SIZE
    sensor_detect = getattr(controller, "sensor_detect", None) if controller else None
    if sensor_detect is not None:
        resolution_info = (getattr(sensor_detect, "res_modes", None) or {}).get(
            getattr(controller, "sensor_mode", None)
        )
        width = (resolution_info or {}).get("width")
        height = (resolution_info or {}).get("height")
        if width and height:
            lores_w, lores_h = sensor_detect._calc_lores(width, height)

    thumb_size_shift = None
    if redis_controller is not None:
        try:
            thumb_size_shift = max(
                0, min(4, int(redis_controller.get_value(ParameterKey.THUMBNAIL_SIZE.value)))
            )
        except (TypeError, ValueError):
            thumb_size_shift = None
    if thumb_size_shift is None:
        thumb_size_shift = thumbnail_size_startup_value(settings)

    # The editor shows ONE on/off toggle over image_capture.thumbnail, not a
    # mode picker and a size picker (operator decision 2026-09-13). All four
    # modes and every size still work and are still reachable -- by hand in
    # settings.jsonc, or live with `set thumbnail` -- but the page offers the
    # one choice that is actually a choice for most operators: a colour
    # preview in the Playback pane, or nothing.
    #
    # What the toggle needs from here is the COST of the on position, in this
    # camera's own numbers, so the card can state it instead of leaving an
    # operator to guess what "on" costs per frame. That string comes from
    # thumbnail_choice_labels() -- the same function, and therefore the same
    # byte formula, that file_size and cinepi/dng_thumbnail.hpp use -- so the
    # figure on the page can never drift from what a take actually costs.
    choices = dict(thumbnail_choice_labels(lores_w, lores_h, thumb_size_shift))
    return {
        "thumbnail_on_label": choices.get("jpeg", ""),
        "thumbnail_off_label": choices.get("off", ""),
    }


def _list_tuning_files() -> list[dict]:
    """Directory listing behind both tuning-file pickers and
    GET /api/tuning-files (FINDINGS.md S3.3: the picker used to be two
    hardcoded <option> lists, so a file copied into resources/tuning_files/
    over SSH -- the documented procedure -- never appeared in it).

    A missing directory means a broken checkout, not "no files" -- warn
    rather than let an empty picker pass as normal.
    """
    try:
        names = sorted(p.name for p in TUNING_FILES_DIR.glob("*.json") if p.is_file())
    except OSError as exc:
        logger.warning("Tuning files directory unavailable (%s): %s", TUNING_FILES_DIR, exc)
        return []
    return [{"name": name, "path": f"{TUNING_FILES_REL}/{name}"} for name in names]


def _validate_tuning_json(raw: bytes) -> str | None:
    """An uploaded tuning file must satisfy the same JSON-shape rule the
    launch guard enforces (module.tuning_files.tuning_json_problem), so the
    editor and the launch-time fallback can never disagree about what counts
    as usable (PLAN.md S1.2). Returns an error message, or None if *raw* is
    fine.
    """
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return f"Not valid JSON: {exc}"
    return tuning_json_problem(data)


@settings_editor_bp.route("/")
def index():
    settings = current_app.config["SETTINGS"]
    # The resolved path, not the relative form settings.jsonc carries.
    # sensors.database_file is operator-settable, and /home/pi/cinemate is a
    # symlink on a source install (cinemate-install.sh), which Path.resolve()
    # follows -- so the only truthful answer comes from the same helper the
    # loader itself uses.
    return render_template(
        "settings_editor.html",
        api_token=web_api_settings(settings).get("token") or "",
        sensor_db_path=str(
            resolve_database_path((settings.get("sensors") or {}).get("database_file"))
        ),
        tuning_files=_list_tuning_files(),
        **_current_thumbnail_editor_context(settings),
    )


@settings_editor_bp.route("/api/tuning-files", methods=["GET"])
def list_tuning_files():
    return jsonify({"ok": True, "dir": TUNING_FILES_REL, "files": _list_tuning_files()})


@settings_editor_bp.route("/api/tuning-files", methods=["POST"])
def upload_tuning_file():
    """Write an uploaded tuning file into resources/tuning_files/ for real --
    the control this replaces only fabricated an <option> and a toast
    claiming the same thing (FINDINGS.md S1, S3.5). Validated the same way
    the launch guard validates a configured path, so nothing accepted here
    can later black the camera at launch.
    """
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"ok": False, "message": "No file uploaded"}), 400

    name = Path(upload.filename).name
    if not TUNING_FILE_NAME_RX.match(name):
        return jsonify({"ok": False, "message": f'"{name}" is not a valid .json filename'}), 400

    raw = upload.read()
    if len(raw) > TUNING_FILE_MAX_BYTES:
        return jsonify({
            "ok": False,
            "message": f"{name} is larger than {TUNING_FILE_MAX_BYTES} bytes",
        }), 400

    problem = _validate_tuning_json(raw)
    if problem:
        return jsonify({"ok": False, "message": problem}), 400

    dest = TUNING_FILES_DIR / name
    if dest.exists():
        return jsonify({
            "ok": False,
            "message": f"{name} already exists in {TUNING_FILES_REL}/; choose another name or remove it over SSH",
        }), 409

    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(TUNING_FILES_DIR), prefix=".tuning-upload-", suffix=".json.tmp")
        try:
            with os.fdopen(fd, "wb") as fp:
                fp.write(raw)
            os.chmod(tmp_path, 0o644)
            os.replace(tmp_path, dest)
        except Exception:
            os.unlink(tmp_path)
            raise
    except OSError as exc:
        logger.exception("Failed to write %s", dest)
        return jsonify({"ok": False, "message": f"Could not write {dest}: {exc}"}), 500

    path = f"{TUNING_FILES_REL}/{name}"
    message = f"Uploaded {name} to {TUNING_FILES_REL}/"
    logger.info("tuning file uploaded via settings editor: %s (%d bytes)", path, len(raw))
    return jsonify({"ok": True, "name": name, "path": path, "message": message})


@settings_editor_bp.route("/api/settings", methods=["GET"])
def get_settings():
    live_exists = Path(SETTINGS_FILE).exists()
    source_path = SETTINGS_FILE if live_exists else STOCK_SETTINGS_FILE
    try:
        settings = load_settings(source_path)
    except SettingsLoadError as exc:
        logger.error("Failed to load %s: %s", source_path, exc)
        return jsonify({"ok": False, "message": str(exc)}), 500
    return jsonify({
        "ok": True,
        "settings": settings,
        "source": "live" if live_exists else "stock",
    })


@settings_editor_bp.route("/api/settings/default", methods=["GET"])
def get_settings_default():
    try:
        settings = load_settings(STOCK_SETTINGS_FILE)
    except SettingsLoadError as exc:
        logger.error("Failed to load stock settings %s: %s", STOCK_SETTINGS_FILE, exc)
        return jsonify({"ok": False, "message": str(exc)}), 500
    return jsonify({"ok": True, "settings": settings})


@settings_editor_bp.route("/api/settings/parse", methods=["POST"])
def parse_settings():
    """Parse arbitrary uploaded settings.jsonc text without writing it
    anywhere -- lets the client populate the editor from an uploaded file,
    still gated behind the normal Save button before anything touches
    SETTINGS_FILE."""
    raw = request.get_data(as_text=True) or ""
    try:
        parsed = json.loads(strip_jsonc(raw))
    except json.JSONDecodeError as exc:
        return jsonify({"ok": False, "message": f"Could not parse uploaded file: {exc}"}), 400
    if not isinstance(parsed, dict):
        return jsonify({"ok": False, "message": "Uploaded file must contain a JSON object"}), 400
    try:
        settings = _apply_settings_defaults(parsed)
    except Exception as exc:  # pragma: no cover - defensive
        return jsonify({"ok": False, "message": f"Invalid settings shape: {exc}"}), 400
    return jsonify({"ok": True, "settings": settings})


SETTINGS_BACKUP_KEEP = 10


def _backup_settings(dest: Path) -> Path | None:
    """Copy *dest* aside before it is overwritten. Returns the backup path.

    This deliberately reimplements what cinemate-recovery.py's backup_file()
    does rather than importing it: that console is standard-library-only by
    rule, must not be coupled to src/module, and is deployed to
    /usr/local/bin -- see its module docstring. The two therefore keep
    separate histories, and this one lives beside the settings file because
    that directory is already known-writable by this process (put_settings
    mkstemps into it), whereas the console's /var/lib/cinemate is root-owned.

    Returns None when there is nothing to back up. A missing source is not a
    reason to refuse the write.
    """
    try:
        data = dest.read_bytes()
    except OSError as exc:
        logger.info("No backup taken for %s: %s", dest, exc)
        return None

    backup_dir = dest.parent / ".settings-backups"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = backup_dir / f"{dest.name}.{stamp}.bak"
        counter = 1
        while target.exists():  # two saves inside one second
            target = backup_dir / f"{dest.name}.{stamp}-{counter}.bak"
            counter += 1
        target.write_bytes(data)

        keep = sorted(backup_dir.glob(f"{dest.name}.*.bak"))[:-SETTINGS_BACKUP_KEEP]
        for stale in keep:
            stale.unlink(missing_ok=True)
    except OSError as exc:
        # Losing the backup must not lose the save -- but say so, loudly.
        logger.error("Could not back up %s before saving: %s", dest, exc)
        return None

    return target


# Subtrees the page builds in full, where a member the payload does not
# mention has been deleted rather than left out: image_capture.custom_modes is
# keyed by camera and drops a camera whose overrides are all gone, and the quad
# rotary's encoders object drops an encoder set back to "none". Merging those
# would resurrect what the operator just removed, so they are taken as sent.
EDITOR_OWNED_SUBTREES = frozenset({
    ("image_capture", "custom_modes"),
    ("input_peripherals", "quad_rotary_controller", "encoders"),
})


def _settings_on_disk(dest: Path) -> dict:
    """The live settings.jsonc as written, with no defaults applied.

    Returns {} when there is nothing to merge over -- a first write, or a file
    the operator has already broken. Either way the payload stands alone, and
    _backup_settings() has kept whatever text was there.
    """
    try:
        parsed = json.loads(strip_jsonc(dest.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        logger.info("Saving %s without merging over the old file (%s)", dest, exc)
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _merge_saved_settings(existing: dict, payload: dict, path: tuple = ()) -> dict:
    """Overlay *payload* on *existing*, keeping keys the payload never mentions.

    The editor's buildState() walks document.querySelectorAll('[data-path]')
    and builds the object it saves from exactly those elements, so a
    settings.jsonc key with no control on the page was simply absent from the
    save and _apply_settings_defaults() decided it instead -- the operator's
    value replaced by the stock one, or by whatever a missing key means. That
    is how a camera lost image_capture.hdr.imx585_clear_hdr_12bit on
    2026-09-15 and had 12-bit ClearHDR switched back on underneath it.

    A page is a view of the file, not the file. So the payload defines the
    values it carries and the rest of the file stays as it was. Dicts merge
    recursively; lists and scalars are replaced whole, because a chip removed
    from a steps list or a pin removed from rec_out_pin has to disappear. The
    page still owns EDITOR_OWNED_SUBTREES outright.
    """
    if path in EDITOR_OWNED_SUBTREES:
        return payload
    if not isinstance(existing, dict) or not isinstance(payload, dict):
        return payload
    merged = dict(existing)
    for key, value in payload.items():
        merged[key] = (
            _merge_saved_settings(merged[key], value, path + (key,))
            if key in merged else value
        )
    return merged


def _render_settings(dest: Path, settings: dict) -> tuple[str, bool]:
    """Produce the text to write, keeping the file's comments where possible.

    Returns (text, comments_preserved). The surgical path rewrites only the
    spans whose values changed, so comments, key order and formatting survive
    untouched. It cannot express a structural change -- a key added or removed,
    an array resized -- and falls back to a full json.dumps() rewrite, which is
    correct but loses every comment. The caller must report that, not hide it.
    """
    full = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"

    try:
        original = dest.read_text(encoding="utf-8")
        current = json.loads(strip_jsonc(original))
    except (OSError, ValueError) as exc:
        # No readable file to preserve anything from -- a first write, or one
        # the user has already broken. Either way the full rewrite is right.
        logger.info("Rewriting %s in full (%s)", dest, exc)
        return full, False

    try:
        edited = apply_updates(original, current, settings)
    except Exception:  # pragma: no cover - the editor must never block a save
        logger.exception("Surgical settings edit failed; falling back to a full rewrite")
        return full, False

    if edited is None:
        return full, False
    return edited, True


@settings_editor_bp.route("/api/settings", methods=["PUT"])
def put_settings():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "message": "Request body must be a JSON object"}), 400

    dest = Path(SETTINGS_FILE)
    try:
        settings = _apply_settings_defaults(
            _merge_saved_settings(_settings_on_disk(dest), body)
        )
    except Exception as exc:  # pragma: no cover - defensive, mirrors load_settings' own catch-all
        logger.exception("Rejected settings save: failed to normalize payload")
        return jsonify({"ok": False, "message": f"Invalid settings payload: {exc}"}), 400

    backup = _backup_settings(dest)
    text, comments_kept = _render_settings(dest, settings)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(dest.parent), prefix=".settings-editor-", suffix=".jsonc.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                fp.write(text)
            os.replace(tmp_path, dest)
        except Exception:
            os.unlink(tmp_path)
            raise
    except OSError as exc:
        logger.exception("Failed to write %s", dest)
        return jsonify({"ok": False, "message": f"Could not write {dest}: {exc}"}), 500

    logger.info(
        "settings.jsonc saved via settings editor (%d bytes); comments %s; backup: %s",
        len(text),
        "preserved" if comments_kept else "LOST (structural change)",
        backup or "none",
    )

    cinepi_controller = current_app.config.get("CINEPI_CONTROLLER")
    restarting = False
    if cinepi_controller is not None and hasattr(cinepi_controller, "restart_cinemate"):
        restarting = True
        # restart_cinemate() os.execl()s the current process in place -- it
        # never returns. Give this HTTP response a moment to actually reach
        # the client before the process image is replaced out from under it.
        timer = threading.Timer(0.4, cinepi_controller.restart_cinemate)
        timer.daemon = True
        timer.start()

    message = "Saved."
    if not comments_kept:
        # Say it out loud. Silently dropping the operator's annotations is how
        # this went unnoticed in the first place.
        message = (
            "Saved, but the comments in settings.jsonc could not be kept: this change "
            "altered the file's structure, so it was rewritten from scratch."
            + (f" The previous version is at {backup}." if backup else "")
        )

    return jsonify({
        "ok": True,
        "message": message,
        "restarting": restarting,
        "comments_preserved": comments_kept,
        "backup": str(backup) if backup else None,
    })


@settings_editor_bp.route("/api/config-txt", methods=["GET"])
def get_config_txt():
    dest = Path(boot_config.CONFIG_TXT_PATH)
    try:
        text = dest.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read %s (%s) -- returning defaults", dest, exc)
        state = boot_config.default_config_state()
        state["found"] = False
        return jsonify({"ok": True, "config": state, "source": "stock"})
    return jsonify({"ok": True, "config": boot_config.parse_config_txt(text), "source": "live"})


@settings_editor_bp.route("/api/config-txt/default", methods=["GET"])
def get_config_txt_default():
    return jsonify({"ok": True, "config": boot_config.default_config_state()})


@settings_editor_bp.route("/api/config-txt/parse", methods=["POST"])
def parse_config_txt_upload():
    """Parse an uploaded config.txt without writing it anywhere -- mirrors
    /api/settings/parse's upload-without-saving pattern."""
    raw = request.get_data(as_text=True) or ""
    state = boot_config.parse_config_txt(raw)
    if not state.get("found"):
        return jsonify({"ok": False, "message": "Uploaded file has no cinemate-install managed block"}), 400
    return jsonify({"ok": True, "config": state})


@settings_editor_bp.route("/api/config-txt", methods=["PUT"])
def put_config_txt():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "message": "Request body must be a JSON object"}), 400

    dest = Path(boot_config.CONFIG_TXT_PATH)
    try:
        current_text = dest.read_text(encoding="utf-8")
    except OSError as exc:
        logger.exception("Could not read %s", dest)
        return jsonify({"ok": False, "message": f"Could not read {dest}: {exc}"}), 500

    try:
        new_text = boot_config.apply_config_txt_state(current_text, body)
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400

    try:
        boot_config.write_config_txt(new_text)
    except OSError as exc:
        logger.exception("Failed to write %s", dest)
        return jsonify({"ok": False, "message": f"Could not write {dest}: {exc}"}), 500

    logger.info("config.txt saved via settings editor")

    cinepi_controller = current_app.config.get("CINEPI_CONTROLLER")
    rebooting = False
    message = "Saved."
    if cinepi_controller is not None and hasattr(cinepi_controller, "reboot"):
        # Ask the sudoers policy first. `rebooting` used to be True whenever
        # the controller merely HAD a reboot method, so the page animated a
        # reboot whether or not one was permitted -- and until this release
        # CineMate's own sudoers drop-in never granted it, so on a Pi whose
        # distro NOPASSWD rule had been removed the answer was always no.
        rebooting = (not hasattr(cinepi_controller, "can_reboot")
                     or cinepi_controller.can_reboot())
        if rebooting:
            # cinepi_controller.reboot() stops any active recording, then
            # reboots -- give this HTTP response a moment to actually reach
            # the client first.
            timer = threading.Timer(0.4, cinepi_controller.reboot)
            timer.daemon = True
            timer.start()
        else:
            message = ("Saved, but this Pi will not let CineMate reboot itself: "
                       "`systemctl reboot` is not in its sudoers rule. Re-run "
                       "cinemate-install.sh, or reboot it yourself to apply the change.")
            logger.warning("config.txt saved but reboot is not permitted by sudoers")

    return jsonify({"ok": True, "message": message, "rebooting": rebooting})


@settings_editor_bp.route("/api/power", methods=["POST"])
def power_action():
    """Restart CineMate, reboot, or shut down the Pi -- from the settings
    editor's own blueprint, separate from POST /api/v1/cmd.

    /api/v1/cmd answers `reboot`/`shutdown` only when
    `system.web_api.allow_destructive` is true in settings.jsonc, which
    ships false by default (see docs/web-api.md for why that switch
    exists). The settings editor is a different surface -- it already
    formats drives and deletes takes through this same blueprint, and
    put_config_txt() above already reboots directly from here -- so this
    route answers the same way those do, independent of that switch.
    """
    body = request.get_json(silent=True)
    action = body.get("action") if isinstance(body, dict) else None
    if action not in ("restart_cinemate", "reboot", "shutdown"):
        return jsonify({
            "ok": False,
            "message": "action must be one of: restart_cinemate, reboot, shutdown",
        }), 400

    cinepi_controller = current_app.config.get("CINEPI_CONTROLLER")
    if cinepi_controller is None:
        return jsonify({
            "ok": False,
            "message": "No camera controller attached -- this needs to run on the Pi.",
        }), 503

    if action == "restart_cinemate":
        # 0.4 s so this response lands before the restart tears the process
        # down -- same shape as put_config_txt()'s reboot timer below.
        timer = threading.Timer(0.4, cinepi_controller.restart_cinemate)
        timer.daemon = True
        timer.start()
        return jsonify({"ok": True, "action": action, "scheduled": True})

    if action == "reboot":
        verb, method, gerund, phrase = "reboot", cinepi_controller.reboot, "reboot", "reboot it yourself"
    else:
        verb, method, gerund, phrase = "poweroff", cinepi_controller.safe_shutdown, "shut down", "shut it down yourself"

    # Ask the sudoers policy first rather than assuming the grant -- the same
    # reasoning put_config_txt() documents for `rebooting` above.
    if not cinepi_controller.can_power(verb):
        message = ("This Pi will not let CineMate %s itself: `systemctl %s` is "
                   "not in its sudoers rule. Re-run cinemate-install.sh, or "
                   "%s." % (gerund, verb, phrase))
        logger.warning("%s refused: not permitted by sudoers", action)
        return jsonify({"ok": False, "message": message}), 403

    # _power_command() (cinepi_controller.py) stops an in-progress recording
    # itself before running the verb -- documented behaviour (docs/web-api.md,
    # "Recording stops if one is in progress"), so this route does not also
    # refuse with 409 the way /api/raw/format does.
    timer = threading.Timer(0.4, method)
    timer.daemon = True
    timer.start()
    return jsonify({"ok": True, "action": action, "scheduled": True})


@settings_editor_bp.route("/api/actions", methods=["GET"])
def get_actions():
    cinepi_controller = current_app.config.get("CINEPI_CONTROLLER")
    available = _public_method_names(cinepi_controller) if cinepi_controller is not None else None

    actions = []
    for entry in ACTION_METHODS:
        item = dict(entry)
        if available is not None:
            item["available"] = entry["value"] in available
        actions.append(item)

    return jsonify({"ok": True, "actions": actions})


@settings_editor_bp.route("/api/sensor-modes", methods=["GET"])
def get_sensor_modes():
    """Return every currently detected driver mode for the dynamic mode table.

    This endpoint deliberately reads sensor_modes_unfiltered. The old
    k_steps/bit_depths settings are now only a backwards-compatible fallback;
    the new editor needs to see the complete driver catalogue so an operator
    can select individual modes.
    """
    sensor_detect = current_app.config.get("SENSOR_DETECT")
    if sensor_detect is None:
        return jsonify({"ok": True, "sensors": {}, "storage": {}})

    settings = current_app.config.get("SETTINGS") or {}
    image = settings.get("image_capture") or {}
    redis = current_app.config.get("REDIS_CONTROLLER")

    def redis_value(key, default=None):
        if redis is None:
            return default
        try:
            value = redis.get_value(key, default)
            return default if value is None else value
        except Exception:
            return default

    try:
        conform = smpte_frame_base(float(image.get("conform_frame_rate", DEFAULT_CONFORM_FRAME_RATE)))
    except (TypeError, ValueError):
        conform = DEFAULT_CONFORM_FRAME_RATE


    enabled_modes = getattr(sensor_detect, "enabled_modes", {}) or {}
    legacy_k = image.get("k_steps", []) or []
    legacy_depths = image.get("bit_depths", []) or []

    def selected_for(camera, mode):
        entries = enabled_modes.get(camera) if isinstance(enabled_modes, dict) else None
        if isinstance(entries, list) and entries:
            return SensorDetect._mode_matches_enabled(mode, entries)
        # First visit of an old settings file: preserve its existing filters,
        # but otherwise default-select every mode unless the driver's own
        # annotation marks it as a windowed (non-full) crop -- i.e. binning
        # metadata is present and the mode is not the full active window.
        # A mode with no crop/binning annotation at all, which is every stock
        # sensor and today's imx283 native readouts, stays selected exactly
        # as it is offered today, even when its crop origin is non-zero.
        if legacy_k and round((mode.get("width", 0) / 1000) * 2) / 2 not in legacy_k:
            return False
        if legacy_depths and mode.get("bit_depth") not in legacy_depths:
            return False
        bx, by = SensorDetect._mode_binning(mode)
        if bx is not None and by is not None and not SensorDetect._mode_is_full(mode):
            return False
        return True

    sensors = {}
    source = getattr(sensor_detect, "sensor_modes_unfiltered", {}) or {}
    for camera_name, modes in source.items():
        # Prefer the largest known full active window as the diagram's
        # coordinate space. For IMX585 this becomes 3840x2160 rather than the
        # native 3856x2180 array, so a 480-pixel left/right crop is actually
        # rendered centred. If geometry is unavailable (e.g. stock IMX477),
        # the diagram simply remains "geometry not reported".
        diagram_w = diagram_h = None
        for candidate in modes:
            if not SensorDetect._mode_is_full(candidate):
                continue
            cw, ch = candidate.get("crop_width"), candidate.get("crop_height")
            bx, by = SensorDetect._mode_binning(candidate)
            if cw and ch and bx and by:
                rw, rh = int(cw) * bx, int(ch) * by
            elif cw and ch:
                rw, rh = int(cw), int(ch)
            else:
                continue
            if diagram_w is None or rw * rh > diagram_w * diagram_h:
                diagram_w, diagram_h = rw, rh

        entries = []
        for mode in sorted(modes, key=SensorDetect._mode_sort_key):
            width, height = mode.get("width"), mode.get("height")
            depth = mode.get("bit_depth")
            if not width or not height or not depth:
                continue
            entries.append({
                "width": width,
                "height": height,
                # RAW16 ClearHDR modes may advertise a padded CSI buffer
                # height. The editor presents the active recording crop.
                "active_width": int(mode.get("crop_width") or width),
                "active_height": int(mode.get("crop_height") or height),
                "bit_depth": depth,
                "aspect": round(float(mode.get("aspect") or (width / height)), 3),
                "hdr": bool(mode.get("hdr", False)),
                "label": "Clear HDR" if mode.get("hdr", False) else "Standard",
                "fps_max_detected": mode.get("fps_max_detected", mode.get("fps_max")),
                "fps_max_effective": mode.get("fps_max"),
                "packing": mode.get("packing"),
                "binning_x": mode.get("binning_x"),
                "binning_y": mode.get("binning_y"),
                "crop_x": mode.get("crop_x"),
                "crop_y": mode.get("crop_y"),
                "crop_width": mode.get("crop_width"),
                "crop_height": mode.get("crop_height"),
                "sensor_width": mode.get("sensor_width"),
                "sensor_height": mode.get("sensor_height"),
                "diagram_sensor_width": diagram_w,
                "diagram_sensor_height": diagram_h,
                # crop_known is true only when the driver supplied the
                # complete crop tuple.  Do not use sensor database metadata as a
                # substitute: the mode table is specifically a readout of the
                # current cinepi-raw probe.
                "crop_known": all(mode.get(k) is not None for k in (
                    "crop_x", "crop_y", "crop_width", "crop_height",
                )),
                "full": SensorDetect._mode_is_full(mode),
                "selected": selected_for(camera_name, mode),
            })
        sensors[camera_name] = entries

    preview_source = str(redis_value(ParameterKey.HDMI_PREVIEW_SOURCE.value, "both") or "both")

    return jsonify({
        "ok": True,
        "sensors": sensors,
        "preview_source": preview_source,
        "conform_frame_rate": conform,
        "available": _available_mode_categories(sensor_detect),
    })


def _available_mode_categories(sensor_detect) -> dict:
    """Legacy availability metadata retained for older editor code."""
    k_values, bit_depths = set(), set()
    for modes in (getattr(sensor_detect, "sensor_modes_unfiltered", None) or {}).values():
        for mode in modes:
            width = mode.get("width")
            if width:
                k_values.add(round(width / 1000 * 2) / 2)
            depth = mode.get("bit_depth")
            if depth:
                bit_depths.add(int(depth))
    return {"k_steps": sorted(k_values), "bit_depths": sorted(bit_depths), "known": bool(k_values or bit_depths)}

@settings_editor_bp.route("/api/playback/clips", methods=["GET"])
def get_playback_clips():
    conform = DEFAULT_CONFORM_FRAME_RATE
    settings = current_app.config.get("SETTINGS") or {}
    raw_conform = settings.get("settings", {}).get(
        "conform_frame_rate", DEFAULT_CONFORM_FRAME_RATE)
    try:
        # smpte_frame_base(), not int(): the same "round to a whole frame
        # base" rule redis_controller._format_timecode() applies to this
        # exact setting (F-253 already records four sites with three
        # different rounding rules -- a plain int() truncation here would
        # have been a fifth, and 23.976 -> 23 both paced playback ~4% slow
        # and disagreed with the redis/DNG frame base of 24). float() first
        # so a genuinely unreadable value falls back to
        # DEFAULT_CONFORM_FRAME_RATE below rather than smpte_frame_base()'s
        # own internal fallback of 1 -- a 1 fps pane on a typo is a worse
        # failure mode than the shipped default.
        conform = smpte_frame_base(float(raw_conform))
    except (TypeError, ValueError):
        logger.debug("playback: unreadable conform_frame_rate, using %s", conform)
    return jsonify({"ok": True, "clips": playback.list_clips(),
                    "conform_frame_rate": conform,
                    "render_token": playback.RENDER_TOKEN,
                    "recording": _is_recording()})


@settings_editor_bp.route("/api/playback/clips/<name>/frame/<int:index>", methods=["GET"])
def get_playback_frame(name, index):
    # Playback loses to recording, always. Reading a take off the card while
    # another is being written to it is the shape of the storage contention that
    # has cost audio sync before, so the pane is refused rather than throttled.
    blocked, reason = _playback_blocked()
    if blocked:
        return jsonify({"ok": False, "message": reason}), 409

    try:
        scale = int(request.args.get("scale", 4))
        quality = max(40, min(95, int(request.args.get("q", 80))))
    except ValueError:
        return jsonify({"ok": False, "message": "scale and q must be integers"}), 400
    if scale not in (2, 4, 8, 16):
        return jsonify({"ok": False, "message": "scale must be 2, 4, 8 or 16"}), 400
    mono = request.args.get("mono") in ("1", "true", "yes")

    try:
        data, width, height, source = playback.frame_jpeg(
            name, index, scale=scale, mono=mono, quality=quality)
    except playback.Busy:
        # Tell the client to drop this frame rather than wait for it; holding the
        # clock is what keeps playback honest about its rate.
        return jsonify({"ok": False, "message": "busy"}), 503
    except playback.PlaybackError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 404

    response = make_response(data)
    response.headers["Content-Type"] = "image/jpeg"
    response.headers["X-Frame-Size"] = f"{width}x{height}"
    # Which path produced this frame (open decision 8). The HUD shows it, so a
    # 720p proxy is never mistaken for a demosaiced frame or the other way.
    response.headers["X-Frame-Source"] = source
    # A decoded frame is a pure function of (take, index, scale, mono, q) and
    # takes are immutable once written, so this is safe to cache hard.
    response.headers["Cache-Control"] = "private, max-age=3600, immutable"
    return response


@settings_editor_bp.route("/api/playback/clips/<name>/audio", methods=["GET"])
def get_playback_audio(name):
    # Same lockout as get_playback_frame() -- this route had none, so a
    # hotspot client could stream a take's WAV off the card mid-recording,
    # exactly the storage contention the frame lockout exists to prevent.
    # A WAV is also unfinalised mid-take by construction (its data-chunk
    # size is only written on a clean stop), so serving it during a take
    # was never just a performance question.
    blocked, reason = _playback_blocked()
    if blocked:
        return jsonify({"ok": False, "message": reason}), 409

    path = playback.wav_path(name)
    if path is None:
        return jsonify({"ok": False, "message": "no audio for this take"}), 404
    return send_file(path, mimetype="audio/wav", conditional=True)


@settings_editor_bp.route("/api/raw/storage", methods=["GET"])
def get_raw_storage():
    return jsonify({"ok": True, "storage": raw_files.storage_summary()})


@settings_editor_bp.route("/api/raw/takes", methods=["GET"])
def get_raw_takes():
    return jsonify({"ok": True, "takes": raw_files.list_takes()})


def _recording_take_names() -> set[str]:
    """Names currently being written to -- empty unless a recording is
    actually in progress, since last_dng_cam0/cam1 are only reset to "None"
    on start_all/stop_all, not on record stop."""
    redis_controller = current_app.config.get("REDIS_CONTROLLER")
    if redis_controller is None:
        return set()
    rec = str(redis_controller.get_value(ParameterKey.IS_RECORDING.value, "0") or "0").strip()
    if rec != "1":
        return set()
    return raw_files.active_take_names(redis_controller)


@settings_editor_bp.route("/api/raw/takes/<name>", methods=["DELETE"])
def delete_raw_take(name):
    storage = request.args.get("storage") or None
    if name in _recording_take_names():
        return jsonify({"ok": False, "message": "Refusing to delete while recording"}), 409
    ok, message = raw_files.delete_take(name, storage=storage)
    return jsonify({"ok": ok, "message": message}), (200 if ok else 404)


@settings_editor_bp.route("/api/raw/takes/<name>/download", methods=["GET"])
def download_raw_take(name):
    storage = request.args.get("storage") or None
    path = raw_files.resolve_take(name, storage=storage)
    if path is None:
        return jsonify({"ok": False, "message": f"Take '{name}' not found"}), 404

    if not raw_files.DOWNLOAD_SEMAPHORE.acquire(blocking=False):
        return jsonify({"ok": False, "message": "A download is already in progress"}), 429, {"Retry-After": "5"}

    # Two release paths for one acquire: guarded_stream()'s generator-finally
    # covers a GET whose body is iterated (to completion, or aborted mid-
    # stream); call_on_close covers a HEAD, whose body Werkzeug never
    # iterates -- the generator's own code, including that finally, never
    # runs, so the acquire above would otherwise leak on every HEAD. _Permit
    # makes it safe for whichever of the two actually fires to be the one
    # that releases.
    permit = raw_files._Permit(raw_files.DOWNLOAD_SEMAPHORE)
    response = Response(
        stream_with_context(raw_files.guarded_stream(raw_files.stream_take_zip(path), sem=permit)),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )
    response.call_on_close(permit.release)
    return response


@settings_editor_bp.route("/api/raw/takes/<name>/files", methods=["GET"])
def raw_take_manifest(name):
    """Feeds the folder-picker client path (W10): the file list and sizes
    it needs before it can start writing into a chosen directory."""
    storage = request.args.get("storage") or None
    path = raw_files.resolve_take(name, storage=storage)
    if path is None:
        return jsonify({"ok": False, "message": f"Take '{name}' not found"}), 404

    files = []
    total_bytes = 0
    for f in sorted(path.rglob("*")):
        if not f.is_file():
            continue
        try:
            stat = f.stat()
        except OSError:
            continue
        files.append({"name": str(f.relative_to(path)), "size_bytes": stat.st_size, "mtime": stat.st_mtime})
        total_bytes += stat.st_size

    return jsonify({
        "ok": True,
        "take": name,
        "storage": path.parent.name,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "recording": name in _recording_take_names(),
        "files": files,
    })


@settings_editor_bp.route("/api/raw/takes/<name>/files/<path:filename>", methods=["GET"])
def raw_take_file(name, filename):
    """Per-file fetch for the folder-picker path. werkzeug's safe_join
    (inside send_from_directory) is the traversal guard here, not
    raw_files.resolve_take -- but resolve_take still confines *name* to a
    real take dir before *path* is ever handed to it."""
    storage = request.args.get("storage") or None
    path = raw_files.resolve_take(name, storage=storage)
    if path is None:
        return jsonify({"ok": False, "message": f"Take '{name}' not found"}), 404
    return send_from_directory(path, filename, conditional=True, max_age=0)


@settings_editor_bp.route("/api/raw/bulk", methods=["POST"])
def bulk_raw_action():
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    names = body.get("names") or []
    if action != "delete" or not isinstance(names, list):
        return jsonify({"ok": False, "message": "Expected {action: 'delete', names: [...]}"}), 400

    # Whole-request refusal, not a per-name skip: a partial delete that
    # silently dropped the recording take would be worse than a refusal the
    # operator can see. Duplicate-name ambiguity across /media/RAW and
    # /media/RAW1 is a separate, still-open issue -- bulk stays name-only.
    blocked = _recording_take_names() & set(names)
    if blocked:
        return jsonify({
            "ok": False,
            "message": "Refusing to delete while recording",
            "recording": sorted(blocked),
        }), 409

    results = {}
    for name in names:
        ok, message = raw_files.delete_take(name)
        results[name] = {"ok": ok, "message": message}
    all_ok = all(r["ok"] for r in results.values())
    return jsonify({"ok": all_ok, "results": results})


# psutil reports the NTFS mount as ntfs, ntfs3 or fuseblk depending on which
# driver took the volume; all three mean the mkfs.ntfs succeeded. ext4 and
# exfat report literally.
_FSTYPE_ALIASES = {
    "ext4": ("ext4",),
    "exfat": ("exfat",),
    "ntfs": ("ntfs", "ntfs3", "fuseblk"),
}


@settings_editor_bp.route("/api/raw/format", methods=["POST"])
def format_raw_drive():
    body = request.get_json(silent=True) or {}
    fs = str(body.get("filesystem") or "").strip().lower()
    if fs not in _FSTYPE_ALIASES:
        return jsonify({"ok": False, "message": "filesystem must be ext4, exfat or ntfs"}), 400

    command_executor = current_app.config.get("COMMAND_EXECUTOR")
    if command_executor is None:
        return jsonify({"ok": False, "message": "Command dispatcher not available"}), 503

    # Sequencing interlock, not a permissions gate: ssd_monitor's own guard
    # only covers the buffer flush, and its unmount escalation runs
    # `fuser -km` on the mount, which would kill a running writer mid-take.
    redis_controller = current_app.config.get("REDIS_CONTROLLER")
    if redis_controller is not None:
        rec = str(redis_controller.get_value(ParameterKey.IS_RECORDING.value, "0") or "0").strip()
        if rec == "1":
            return jsonify({"ok": False, "message": "Refusing to format while recording"}), 409

    logger.info("Dispatching 'format %s' from the settings editor", fs)
    ok, message = command_executor.handle_received_data(f"format {fs}")
    if not ok:
        return jsonify({"ok": False, "message": message or "dispatch failed"}), (
            503 if message == "busy" else 500
        )

    # The dispatcher discards handler return values, so a (True, "") here says
    # only that `format` was dispatched -- never that mkfs worked. Verify
    # against reality instead: format_drive() remounts before it returns, so
    # the active mount's filesystem is the authoritative answer.
    active = next((s for s in raw_files.storage_summary() if s.get("active")), None)
    fstype = ((active or {}).get("filesystem") or "").lower()
    if active and fstype in _FSTYPE_ALIASES[fs]:
        return jsonify({"ok": True, "message": f"Formatted as {fs} and remounted."})
    if active:
        return jsonify({
            "ok": False,
            "message": f"Format may have failed — drive is mounted as {fstype or 'unknown'}. "
                       "Check the cinemate log.",
        }), 500
    return jsonify({
        "ok": False,
        "message": "Format failed — drive did not remount. Check the cinemate log.",
    }), 500


@settings_editor_bp.route("/api/raw/download", methods=["GET"])
def download_raw_takes():
    """Bulk sibling of download_raw_take(): one zip holding several takes,
    each under its own top-level folder (raw_files.stream_takes_zip()). GET,
    not POST -- the client reaches this the same way as the single-take
    download, an `<a download>` click, which cannot carry a request body.

    `names` is a comma-separated list of encodeURIComponent'd take names;
    take names are the CINEPI_... folder names storage-automount.py mints
    and can never contain a comma (asserted in
    _test/test_raw_files_download.py), so a plain split is safe.

    A selection spanning two mounted drives (/media/RAW and /media/RAW1)
    sends one request per storage from the client rather than mixing
    storages in one query -- see the bulk-download handler in
    settings_editor.html -- so, like the single-take route, `storage` here
    applies to every name in this request rather than being per-name."""
    raw_names = request.args.get("names") or ""
    names = [n for n in raw_names.split(",") if n]
    if not names:
        return jsonify({"ok": False, "message": "No take names given"}), 400

    storage = request.args.get("storage") or None
    paths = []
    missing = []
    for name in names:
        path = raw_files.resolve_take(name, storage=storage)
        if path is None:
            missing.append(name)
        else:
            paths.append(path)
    if missing:
        return jsonify({
            "ok": False,
            "message": f"Take(s) not found: {', '.join(missing)}",
        }), 404

    # Whole-request refusal, same as bulk delete: a zip silently missing the
    # recording take's newest frames would be worse than refusing the whole
    # download outright.
    blocked = _recording_take_names() & set(names)
    if blocked:
        return jsonify({
            "ok": False,
            "message": "Refusing to download while recording",
            "recording": sorted(blocked),
        }), 409

    if not raw_files.DOWNLOAD_SEMAPHORE.acquire(blocking=False):
        return jsonify({"ok": False, "message": "A download is already in progress"}), 429, {"Retry-After": "5"}

    # Same two-release-path shape as download_raw_take() -- see the comment
    # there about a HEAD request never running guarded_stream()'s generator,
    # and so never reaching its `finally`.
    permit = raw_files._Permit(raw_files.DOWNLOAD_SEMAPHORE)
    filename = "cinemate-takes-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".zip"
    response = Response(
        stream_with_context(raw_files.guarded_stream(raw_files.stream_takes_zip(paths), sem=permit)),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
    response.call_on_close(permit.release)
    return response


# ── i2c pane ─────────────────────────────────────────────────────────────
@settings_editor_bp.route("/api/hardware", methods=["GET"])
def get_hardware():
    """What is on the bus right now, plus both clocks.

    Probed per request rather than read from the drivers' cached flags:
    AnalogControls and SsdMonitor decide once at startup and never look again,
    and none of those objects is reachable from a request anyway -- they are
    locals in main(). See hardware_probe for why the drivers themselves are
    not used to answer this.
    """
    settings = current_app.config.get("SETTINGS") or {}
    oled_settings = (settings.get("output_peripherals") or {}).get("oled") or {}
    peripherals = current_app.config.get("PERIPHERALS") or {}
    quad_rotary = peripherals.get("quad_rotary")
    quad_rotary_state = quad_rotary.state() if quad_rotary is not None else None
    return jsonify({
        "ok": True,
        "bus": f"i2c-{hardware_probe.I2C_BUS}",
        "devices": hardware_probe.detect_devices(oled_settings, quad_rotary_state),
        "clocks": {
            "system": hardware_probe.system_time(),
            "rtc": hardware_probe.read_rtc_time(),
        },
    })


@settings_editor_bp.route("/api/hardware/rtc/sync", methods=["POST"])
def sync_rtc():
    """Copy the system clock onto the RTC.

    Deliberately not routed through the `set rtc time` CLI command. That runs
    `sudo hwclock --systohc` under os.system inside the dispatcher's lock, with
    no -n, no timeout and no exit-status check, so on a machine whose sudoers
    lacks a NOPASSWD rule it blocks on a console password prompt and starves
    every other CLI, serial and HTTP command -- and it reports success either
    way. This runs it with -n, checks the status, and reads the clock back.
    """
    result = hardware_probe.sync_rtc_to_system()
    status = 200 if result["ok"] else 500
    return jsonify(result), status


# ── live log ─────────────────────────────────────────────────────────────
# Enough history to still hold a camera start after a busy stretch: the
# encoder prints its configuration once, and that line is the one worth
# reaching for when a take comes out wrong.
LOG_TAIL_LINES = 800
LOG_MAX_LINE = 2000


# The console mirrors the CLI's colours. The tables are imported rather than
# restated here: they are the CLI's, and a second copy would drift the moment
# a module is added to one and not the other.
_LOG_LINE = re.compile(r"^[\d\-]+ [\d:.]+: ([A-Z]+): (\S+)")


def _line_colour(line: str) -> str:
    """The colour ColoredFormatter would have given this line.

    system.log is written by the plain file handler, so it carries no escape
    codes to reuse -- the level and module are re-read from the text and put
    back through the same lookup the console formatter uses: module first,
    level as the fallback, dark_grey when neither is known.
    """
    from module.logger import ColoredFormatter

    match = _LOG_LINE.match(line)
    if not match:
        return "dark_grey"
    level, module = match.group(1), match.group(2)
    entry = ColoredFormatter.MODULE_COLORS.get(module)
    if entry:
        return entry["color"]
    return ColoredFormatter.LEVEL_COLORS.get(level, "dark_grey")


# libcamera writes its own ANSI colour codes to stdout, cinepi-raw passes them
# through, and cinemate logs the line verbatim -- so system.log carries escape
# sequences that a browser renders as literal "[1;32m" rubbish mid-message.
# The console colours a line by its module, so the embedded codes are noise
# either way.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _log_event(line: str) -> str:
    clean = _ANSI.sub("", line)
    payload = json.dumps({"t": clean[:LOG_MAX_LINE], "c": _line_colour(clean)})
    return f"data: {payload}\n\n"


def _log_path() -> Path:
    from module.logger import log_directory
    return Path(log_directory()) / "system.log"


def _tail_lines(path: Path, count: int) -> list[str]:
    """The last *count* lines, read backwards so a large log stays cheap."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            block, data, newlines = 8192, b"", 0
            while end > 0 and newlines <= count:
                step = min(block, end)
                end -= step
                handle.seek(end)
                chunk = handle.read(step)
                data = chunk + data
                newlines += chunk.count(b"\n")
        text = data.decode("utf-8", errors="replace")
        return text.splitlines()[-count:]
    except OSError:
        return []


@settings_editor_bp.route("/api/logs", methods=["GET"])
def stream_logs():
    """The real system.log, tailed.

    The restart console used to replay a hardcoded script. This is the actual
    file the logger writes, so it carries runtime messages too, not just what
    happens around a restart.

    The file is tailed rather than the logger's queue being shared out: that
    queue has a single consumer, so a second reader would steal records from
    whoever else is draining it, and every extra browser tab would compete for
    the same lines. A file has as many readers as it likes.
    """
    path = _log_path()

    def gen():
        for line in _tail_lines(path, LOG_TAIL_LINES):
            yield _log_event(line)
        yield ": backlog-end\n\n"

        handle = None
        inode = None
        last_beat = time.monotonic()
        try:
            while True:
                try:
                    if handle is None:
                        handle = path.open("r", errors="replace")
                        handle.seek(0, os.SEEK_END)
                        inode = os.fstat(handle.fileno()).st_ino
                    line = handle.readline()
                    if line:
                        yield _log_event(line.rstrip())
                        continue
                    # Nothing new. Has the file been rotated out from under us?
                    try:
                        if os.stat(path).st_ino != inode:
                            handle.close()
                            handle = None
                            continue
                    except OSError:
                        pass
                except OSError:
                    if handle is not None:
                        handle.close()
                    handle = None

                now = time.monotonic()
                if now - last_beat >= 15.0:
                    yield ": ping\n\n"
                    last_beat = now
                time.sleep(0.4)
        finally:
            if handle is not None:
                handle.close()

    return Response(stream_with_context(gen()), mimetype="text/event-stream")
