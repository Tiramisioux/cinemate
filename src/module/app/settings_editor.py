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
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Blueprint,
    after_this_request,
    current_app,
    jsonify,
    make_response,
    render_template,
    request,
    send_file,
)

from module.config_loader import (
    DEFAULT_CONFORM_FRAME_RATE,
    SettingsLoadError,
    _apply_settings_defaults,
    load_settings,
    strip_jsonc,
    DEFAULT_SETTINGS_PATH,
)
from module.app import boot_config, playback, raw_files
from module.jsonc_edit import apply_updates
from module.redis_controller import ParameterKey
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
    {"group": "Zoom / anamorphic", "value": "set_zoom", "label": "Set preview zoom", "no_arg": "cycle",
     "arg": {"type": "select", "options": [1, 2], "suffix": "×"}},
    {"group": "Zoom / anamorphic", "value": "inc_zoom", "label": "Zoom in one stop"},
    {"group": "Zoom / anamorphic", "value": "dec_zoom", "label": "Zoom out one stop"},
    {"group": "Zoom / anamorphic", "value": "set_anamorphic_factor", "label": "Set anamorphic desqueeze", "no_arg": "cycle",
     "arg": {"type": "select", "options": [1, 1.33, 2], "suffix": "×"}},
    {"group": "Resolution / preview", "value": "set_resolution", "label": "Change resolution", "no_arg": "cycle",
     "arg": {"type": "number", "placeholder": "mode #"}},
    {"group": "Resolution / preview", "value": "set_dynamic_resolution_enabled", "label": "Toggle dynamic resolution", "no_arg": "toggle", "arg": {"type": "toggle01"}},
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
    {"group": "System", "value": "restart_cinemate", "label": "Restart Cinemate"},
    {"group": "System", "value": "restart_camera", "label": "Restart camera process"},
    {"group": "System", "value": "reboot", "label": "Reboot the Pi"},
    {"group": "System", "value": "safe_shutdown", "label": "Safe shutdown"},
]


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


@settings_editor_bp.route("/")
def index():
    settings = current_app.config["SETTINGS"]
    return render_template("settings_editor.html", api_token=web_api_settings(settings).get("token") or "")


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

    try:
        settings = _apply_settings_defaults(body)
    except Exception as exc:  # pragma: no cover - defensive, mirrors load_settings' own catch-all
        logger.exception("Rejected settings save: failed to normalize payload")
        return jsonify({"ok": False, "message": f"Invalid settings payload: {exc}"}), 400

    dest = Path(SETTINGS_FILE)
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
    if cinepi_controller is not None and hasattr(cinepi_controller, "reboot"):
        rebooting = True
        # cinepi_controller.reboot() stops any active recording, then
        # `sudo reboot`s -- give this HTTP response a moment to actually
        # reach the client first.
        timer = threading.Timer(0.4, cinepi_controller.reboot)
        timer.daemon = True
        timer.start()

    return jsonify({"ok": True, "message": "Saved.", "rebooting": rebooting})


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
    """Detected modes per camera model, for the fps-ceiling override pane
    (F-298). sensor_detect.res_modes/sensor_resolutions already carry any
    settings.jsonc custom_modes override merged in (that's the *effective*
    fps_max cinepi-raw actually launches with); fps_max_detected is only
    present on a mode _finalize_modes() overrode, and is what the sensor
    itself reported before that override was applied -- see
    sensor_detect.py's _finalize_modes(). Absent means "not overridden",
    i.e. fps_max itself is the detected value.
    """
    sensor_detect = current_app.config.get("SENSOR_DETECT")
    if sensor_detect is None:
        return jsonify({"ok": True, "sensors": {}})

    sensors = {}
    for camera_name, modes in (sensor_detect.sensor_resolutions or {}).items():
        entries = []
        for mode in modes.values():
            detected_fps = mode.get("fps_max_detected", mode.get("fps_max"))
            entries.append({
                "width": mode.get("width"),
                "height": mode.get("height"),
                "bit_depth": mode.get("bit_depth"),
                "hdr": bool(mode.get("hdr", False)),
                "fps_max_detected": detected_fps,
                "fps_max_effective": mode.get("fps_max"),
            })
        entries.sort(key=lambda m: ((m["width"] or 0) * (m["height"] or 0), m["bit_depth"] or 0), reverse=True)
        sensors[camera_name] = entries

    return jsonify({"ok": True, "sensors": sensors})


@settings_editor_bp.route("/api/playback/clips", methods=["GET"])
def get_playback_clips():
    conform = DEFAULT_CONFORM_FRAME_RATE
    settings = current_app.config.get("SETTINGS") or {}
    try:
        conform = int(settings.get("settings", {}).get(
            "conform_frame_rate", DEFAULT_CONFORM_FRAME_RATE))
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


@settings_editor_bp.route("/api/raw/takes/<name>", methods=["DELETE"])
def delete_raw_take(name):
    ok, message = raw_files.delete_take(name)
    return jsonify({"ok": ok, "message": message}), (200 if ok else 404)


@settings_editor_bp.route("/api/raw/takes/<name>/download", methods=["GET"])
def download_raw_take(name):
    path = raw_files.resolve_take(name)
    if path is None:
        return jsonify({"ok": False, "message": f"Take '{name}' not found"}), 404

    zip_path = raw_files.build_take_zip(path)

    @after_this_request
    def _cleanup(response):
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove temp zip %s", zip_path)
        return response

    return send_file(zip_path, as_attachment=True, download_name=f"{name}.zip")


@settings_editor_bp.route("/api/raw/bulk", methods=["POST"])
def bulk_raw_action():
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    names = body.get("names") or []
    if action != "delete" or not isinstance(names, list):
        return jsonify({"ok": False, "message": "Expected {action: 'delete', names: [...]}"}), 400

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
