import json
import logging
from pathlib import Path

from module.dynamic_resolution import default_dynamic_resolution_config

ANSI_RESET = "\033[0m"
ANSI_RED = "\033[1;31m"
ANSI_YELLOW = "\033[1;33m"
ANSI_CYAN = "\033[1;36m"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


class SettingsLoadError(RuntimeError):
    def __init__(
        self,
        path: Path,
        summary: str,
        detail: str,
        recommendation: str,
        *,
        line: int | None = None,
        column: int | None = None,
        context: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.path = path
        self.summary = summary
        self.detail = detail
        self.recommendation = recommendation
        self.line = line
        self.column = column
        self.context = context

    @classmethod
    def from_json_decode_error(cls, path: Path, exc: json.JSONDecodeError) -> "SettingsLoadError":
        detail = f"{exc.msg} at line {exc.lineno}, column {exc.colno}"
        return cls(
            path=path,
            summary="settings.json is not valid JSON",
            detail=detail,
            recommendation=_recommend_json_fix(exc.msg),
            line=exc.lineno,
            column=exc.colno,
            context=_format_error_context(path, exc.lineno, exc.colno),
        )

    def format_for_cli(self, use_color: bool = True) -> str:
        def colorize(text: str, color: str) -> str:
            if not use_color:
                return text
            return f"{color}{text}{ANSI_RESET}"

        lines = [
            f"{colorize('File:', ANSI_CYAN)} {self.path}",
            f"{colorize('Problem:', ANSI_RED)} {self.detail}",
        ]
        if self.context:
            lines.extend(
                [
                    "",
                    colorize("Context:", ANSI_YELLOW),
                    self.context,
                ]
            )
        lines.extend(
            [
                "",
                f"{colorize('Recommended fix:', ANSI_YELLOW)} {self.recommendation}",
                "Fix the highlighted line(s) in settings.json and start Cinemate again.",
            ]
        )
        return "\n".join(lines)


def _recommend_json_fix(message: str) -> str:
    normalized = message.lower()
    if "trailing comma" in normalized:
        return "Remove the trailing comma just before this point. JSON does not allow commas before } or ]."
    if "property name enclosed in double quotes" in normalized:
        return "Check for a trailing comma before this point, or wrap the key name in double quotes."
    if "expecting value" in normalized:
        return "Check for a missing value, a trailing comma, or a comment. JSON does not allow comments."
    if "expecting ',' delimiter" in normalized:
        return "Check for a missing comma between entries, or a mismatched quote/bracket just before this point."
    if "unterminated string" in normalized:
        return "Close the quoted string before the end of the line."
    if "invalid control character" in normalized:
        return "Escape special characters inside strings, for example as \\n, instead of writing them raw."
    if "extra data" in normalized:
        return "Remove the extra text that appears after the final closing } or ]."
    return "Fix the JSON syntax near the highlighted line. Common causes are trailing commas, missing commas, comments, or missing double quotes."


def _format_error_context(path: Path, line: int, column: int, radius: int = 1) -> str | None:
    try:
        source_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    if not source_lines:
        return None

    start_line = max(1, line - radius)
    end_line = min(len(source_lines), line + radius)
    line_width = len(str(end_line))
    snippet: list[str] = []

    for current_line in range(start_line, end_line + 1):
        text = source_lines[current_line - 1]
        marker = ">" if current_line == line else " "
        snippet.append(f"{marker} {current_line:>{line_width}} | {text}")
        if current_line == line:
            caret_column = max(1, min(column, len(text) + 1))
            snippet.append(f"  {' ' * line_width} | {' ' * (caret_column - 1)}^")

    return "\n".join(snippet)


def _coerce_bool_setting(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
    return default


def auto_storage_preroll_enabled(settings: dict) -> bool:
    """Return whether automatic storage pre-roll should run."""

    settings_cfg = settings.get("settings", {})
    if isinstance(settings_cfg, dict):
        if "auto_storage_preroll" in settings_cfg:
            return _coerce_bool_setting(settings_cfg.get("auto_storage_preroll"), True)
        if "storage_preroll" in settings_cfg:
            return _coerce_bool_setting(settings_cfg.get("storage_preroll"), True)
    return _coerce_bool_setting(settings.get("storage_preroll"), True)


def storage_preroll_enabled(settings: dict) -> bool:
    """Backward-compatible alias for automatic storage pre-roll."""

    return auto_storage_preroll_enabled(settings)


def _apply_settings_defaults(settings: dict) -> dict:
    # Top-level placeholders.
    gpio_defaults = {
        "pwm_pin": 19,
        "rec_out_pin": [6, 21],
        "rec_tone_pin": [],
        "rec_tone_frequency_hz": 1000,
        "rec_tone_duty_cycle": 50,
        "rec_tone_relay_drop_frames": False,
    }
    gpio_cfg = settings.setdefault("gpio_output", {})
    for k, v in gpio_defaults.items():
        gpio_cfg.setdefault(k, v)
    settings["gpio_output"] = gpio_cfg
    settings.setdefault("arrays", {})
    settings_cfg = settings.setdefault("settings", {})
    auto_storage_preroll = auto_storage_preroll_enabled(settings)
    settings_cfg.pop("storage_preroll", None)
    settings_defaults = {
        "auto_storage_preroll": auto_storage_preroll,
        "light_hz": [50, 60],
        "conform_frame_rate": 24,
        "live_sync_warning_tolerance_frames": 5,
        "live_sync_startup_guard_frames": 10,
        "final_sync_analysis_tolerance_frames": 1,
        "tc_drop_jitter_tolerance_frames": 1,
    }
    for k, v in settings_defaults.items():
        settings_cfg.setdefault(k, v)
    settings_cfg["auto_storage_preroll"] = _coerce_bool_setting(
        settings_cfg.get("auto_storage_preroll"), True
    )
    settings["settings"] = settings_cfg
    settings.pop("storage_preroll", None)
    system_cfg = settings.setdefault("system", {})
    wifi_defaults = {
        "name": "CinePi",
        "password": "11111111",
        "enabled": True,
    }
    wifi_cfg = system_cfg.setdefault("wifi_hotspot", {})
    for k, v in wifi_defaults.items():
        wifi_cfg.setdefault(k, v)
    system_cfg["wifi_hotspot"] = wifi_cfg
    settings["system"] = system_cfg
    settings.setdefault("analog_controls", {})
    settings.setdefault(
        "free_mode",
        {
            "iso_free": False,
            "shutter_a_free": False,
            "fps_free": False,
            "wb_free": False,
        },
    )
    settings.setdefault("buttons", [])
    settings.setdefault("two_way_switches", [])
    settings.setdefault("rotary_encoders", [])
    settings.setdefault(
        "quad_rotary_controller",
        {"enabled": False, "encoders": {}},
    )
    settings.setdefault("welcome_message", "THIS IS A COOL MACHINE")
    if "show_welcome_message" not in settings:
        settings["show_welcome_message"] = settings.get("show_startup_message", True)
    settings.setdefault("welcome_image", None)

    # Preview / zoom defaults.
    preview_defaults = {
        "default_zoom": 1.0,
        "zoom_steps": [1.0, 1.5, 2.0],
    }
    preview_cfg = settings.setdefault("preview", {})
    for k, v in preview_defaults.items():
        preview_cfg.setdefault(k, v)

    preview_cfg["zoom_steps"] = sorted(set(preview_cfg["zoom_steps"]))
    if preview_cfg["default_zoom"] not in preview_cfg["zoom_steps"]:
        preview_cfg["default_zoom"] = preview_cfg["zoom_steps"][0]
    settings["preview"] = preview_cfg

    # Audio capture defaults.
    audio_defaults = {
        "capture_gain_db": 0.0,
        "plain_arecord_timecode_offset_frames": 2,
    }
    audio_cfg = settings.setdefault("audio", {})
    for k, v in audio_defaults.items():
        audio_cfg.setdefault(k, v)
    settings["audio"] = audio_cfg

    # Anamorphic preview defaults (used by CinePiController).
    ana_defaults = {
        "anamorphic_steps": [1.00, 1.33, 2.00],
        "default_anamorphic_factor": 1.00,
    }
    ana_cfg = settings.setdefault("anamorphic_preview", {})
    for k, v in ana_defaults.items():
        ana_cfg.setdefault(k, v)
    settings["anamorphic_preview"] = ana_cfg

    # Array step tables (iso / shutter-angle / fps / white-balance).
    array_defaults = {
        "iso_steps": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
        "shutter_a_steps": [1, 45, 90, 135, 172.8, 180, 225, 270, 315, 360],
        "fps_steps": [1, 2, 4, 8, 12, 16, 18, 24, 25, 30],
        "wb_steps": [3200, 4400, 5600],
    }
    arrays_cfg = settings["arrays"]
    for k, v in array_defaults.items():
        arrays_cfg.setdefault(k, v)
    settings["arrays"] = arrays_cfg

    # Resolution filter defaults.
    resolution_defaults = {
        "k_steps": [1.5, 2.0, 4.0],
        "bit_depths": [10, 12],
        "custom_modes": {},
    }
    res_cfg = settings.setdefault("resolutions", {})
    for k, v in resolution_defaults.items():
        res_cfg.setdefault(k, v)
    settings["resolutions"] = res_cfg

    sensor_defaults = {
        "database_file": "resources/sensors.json",
    }
    sensor_cfg = settings.setdefault("sensors", {})
    for k, v in sensor_defaults.items():
        sensor_cfg.setdefault(k, v)
    settings["sensors"] = sensor_cfg

    dynamic_resolution_cfg = settings.setdefault(
        "dynamic_resolution",
        default_dynamic_resolution_config(),
    )
    dynamic_resolution_defaults = default_dynamic_resolution_config()
    for k, v in dynamic_resolution_defaults.items():
        dynamic_resolution_cfg.setdefault(k, v)
    settings["dynamic_resolution"] = dynamic_resolution_cfg

    return settings


def load_settings(filename: str | Path) -> dict:
    """
    Load CineMate’s JSON configuration *and* guarantee that every section the
    code relies on is present with safe defaults.

    Return an always-valid settings dict for valid JSON input.
    Raise SettingsLoadError when the file exists but cannot be parsed safely.
    """
    filename = Path(filename)
    try:
        with filename.open("r", encoding="utf-8") as fp:
            settings = json.load(fp)
    except FileNotFoundError:
        logging.warning("Settings file %s not found – using built-in defaults", filename)
        settings = {}
    except json.JSONDecodeError as exc:
        raise SettingsLoadError.from_json_decode_error(filename, exc) from exc
    except UnicodeDecodeError as exc:
        raise SettingsLoadError(
            filename,
            "settings.json is not valid UTF-8 text",
            str(exc),
            "Save settings.json as UTF-8 text and remove any invalid binary characters.",
        ) from exc
    except OSError as exc:
        raise SettingsLoadError(
            filename,
            "settings.json could not be read",
            str(exc),
            "Check that the file exists, is readable, and is not being edited by another process.",
        ) from exc

    if not isinstance(settings, dict):
        raise SettingsLoadError(
            filename,
            "settings.json must contain a top-level object",
            f"Expected the root of the file to be a JSON object, but found {type(settings).__name__}.",
            "Wrap the settings in { ... } and keep the top level as key/value pairs.",
        )

    return _apply_settings_defaults(settings)
