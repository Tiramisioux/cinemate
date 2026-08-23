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
    render_template,
    request,
    send_file,
)

from module.config_loader import (
    SettingsLoadError,
    _apply_settings_defaults,
    load_settings,
    strip_jsonc,
)
from module.app import boot_config, raw_files
from module.jsonc_edit import apply_updates

logger = logging.getLogger(__name__)

settings_editor_bp = Blueprint(
    "settings_editor",
    __name__,
    url_prefix="/settings-editor",
    template_folder="templates",
)

# Every settings.jsonc caller in this codebase hardcodes this same absolute
# path (src/main.py:51, cinepi_multi.py:27, cinepi_controller.py:27,
# wifi_hotspot.py:37) -- it is a live-hardware constant, not configurable.
SETTINGS_FILE = "/home/pi/cinemate/settings.jsonc"

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
ACTION_METHODS = [
    {"group": "Record", "value": "rec", "label": "Start / stop recording"},
    {"group": "ISO", "value": "set_iso", "label": "Set ISO",
     "arg": {"type": "select", "options": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200]}},
    {"group": "ISO", "value": "inc_iso", "label": "ISO up one stop"},
    {"group": "ISO", "value": "dec_iso", "label": "ISO down one stop"},
    {"group": "ISO", "value": "set_iso_lock", "label": "Toggle ISO lock", "arg": {"type": "toggle01"}},
    {"group": "ISO", "value": "set_iso_free", "label": "Toggle ISO free mode", "arg": {"type": "toggle01"}},
    {"group": "Shutter", "value": "set_shutter_a", "label": "Set shutter angle",
     "arg": {"type": "select", "options": [1, 45, 90, 135, 172.8, 180, 225, 270, 315, 346.6, 360], "suffix": "°"}},
    {"group": "Shutter", "value": "inc_shutter_a", "label": "Shutter angle up one stop"},
    {"group": "Shutter", "value": "dec_shutter_a", "label": "Shutter angle down one stop"},
    {"group": "Shutter", "value": "set_shutter_a_nom", "label": "Set nominal shutter angle", "arg": {"type": "number", "step": 0.1}},
    {"group": "Shutter", "value": "set_shutter_a_sync_mode", "label": "Set shutter-sync mode", "arg": {"type": "toggle01"}},
    {"group": "Shutter", "value": "set_shutter_a_nom_lock", "label": "Toggle nominal-shutter lock", "arg": {"type": "toggle01"}},
    {"group": "Shutter", "value": "set_shutter_a_free", "label": "Toggle shutter free mode", "arg": {"type": "toggle01"}},
    {"group": "Frame rate", "value": "set_fps", "label": "Set frame rate", "arg": {"type": "select", "options": [25, 33, 50]}},
    {"group": "Frame rate", "value": "inc_fps", "label": "Frame rate up one stop"},
    {"group": "Frame rate", "value": "dec_fps", "label": "Frame rate down one stop"},
    {"group": "Frame rate", "value": "set_fps_lock", "label": "Toggle FPS lock", "arg": {"type": "toggle01"}},
    {"group": "Frame rate", "value": "set_fps_free", "label": "Toggle FPS free mode", "arg": {"type": "toggle01"}},
    {"group": "Frame rate", "value": "set_fps_double", "label": "Toggle double-fps mode", "arg": {"type": "toggle01"}},
    {"group": "Frame rate", "value": "set_shu_fps_lock", "label": "Toggle nominal shutter+fps lock", "arg": {"type": "toggle01"}},
    {"group": "White balance", "value": "set_wb", "label": "Set white balance", "arg": {"type": "select", "options": [3200, 4400, 5600], "suffix": "K"}},
    {"group": "White balance", "value": "inc_wb", "label": "White balance up one stop"},
    {"group": "White balance", "value": "dec_wb", "label": "White balance down one stop"},
    {"group": "White balance", "value": "set_wb_free", "label": "Toggle WB free mode", "arg": {"type": "toggle01"}},
    {"group": "ClearHDR", "value": "set_hdr_threshold_low", "label": "Set HDR threshold low", "arg": {"type": "number", "min": 0, "max": 4095}},
    {"group": "ClearHDR", "value": "set_hdr_threshold_high", "label": "Set HDR threshold high", "arg": {"type": "number", "min": 0, "max": 4095}},
    {"group": "ClearHDR", "value": "set_hdr_blend", "label": "Set HDR blend", "arg": {"type": "number", "min": 0, "max": 8}},
    {"group": "ClearHDR", "value": "set_hdr_gain_adder", "label": "Set HDR gain adder", "arg": {"type": "number", "min": 0, "max": 5}},
    {"group": "CineMate Log", "value": "set_log", "label": "Set CineMate Log target", "arg": {"type": "select", "options": ["off", "10", "12"]}},
    {"group": "Zoom / anamorphic", "value": "set_zoom", "label": "Set preview zoom", "arg": {"type": "select", "options": [1, 2], "suffix": "×"}},
    {"group": "Zoom / anamorphic", "value": "inc_zoom", "label": "Zoom in one stop"},
    {"group": "Zoom / anamorphic", "value": "dec_zoom", "label": "Zoom out one stop"},
    {"group": "Zoom / anamorphic", "value": "set_anamorphic_factor", "label": "Set anamorphic desqueeze", "arg": {"type": "select", "options": [1, 1.33, 2], "suffix": "×"}},
    {"group": "Resolution / preview", "value": "set_resolution", "label": "Change resolution", "arg": {"type": "number", "placeholder": "mode #, blank = cycle"}},
    {"group": "Resolution / preview", "value": "set_preview_source", "label": "Set HDMI preview source", "arg": {"type": "select", "options": ["cam0", "cam1", "cam0+cam1"]}},
    {"group": "Storage", "value": "mount", "label": "Mount storage"},
    {"group": "Storage", "value": "unmount", "label": "Unmount storage"},
    {"group": "Storage", "value": "toggle_mount", "label": "Toggle mount / unmount"},
    {"group": "Storage", "value": "erase_drive", "label": "Erase drive"},
    {"group": "Storage", "value": "format_drive", "label": "Format drive", "arg": {"type": "select", "options": ["exfat", "ext4", "ntfs"]}},
    {"group": "Sensor", "value": "set_filter", "label": "Toggle IR-cut filter", "arg": {"type": "toggle01"}},
    {"group": "Locks", "value": "set_all_lock", "label": "Toggle all-parameter lock", "arg": {"type": "toggle01"}},
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


@settings_editor_bp.route("/")
def index():
    return render_template("settings_editor.html")


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
        fd, tmp_path = tempfile.mkstemp(dir=str(dest.parent), prefix=".settings-editor-", suffix=".config.txt.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                fp.write(new_text)
            os.replace(tmp_path, dest)
        except Exception:
            os.unlink(tmp_path)
            raise
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
