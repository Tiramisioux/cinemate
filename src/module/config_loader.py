import json
import logging
from pathlib import Path

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
            summary="settings.jsonc is not valid JSON",
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
                "Fix the highlighted line(s) in settings.jsonc and start Cinemate again.",
            ]
        )
        return "\n".join(lines)


def _recommend_json_fix(message: str) -> str:
    normalized = message.lower()
    if "property name enclosed in double quotes" in normalized:
        return "Wrap the key name in double quotes."
    if "expecting value" in normalized:
        return "Check for a missing value near this point, for example an empty array/object entry or two commas in a row."
    if "expecting ',' delimiter" in normalized:
        return "Check for a missing comma between entries, or a mismatched quote/bracket just before this point."
    if "unterminated string" in normalized:
        return "Close the quoted string before the end of the line."
    if "invalid control character" in normalized:
        return "Escape special characters inside strings, for example as \\n, instead of writing them raw."
    if "extra data" in normalized:
        return "Remove the extra text that appears after the final closing } or ]."
    return "Fix the JSON syntax near the highlighted line. // and /* */ comments and trailing commas are allowed; common remaining causes are a missing comma, an unquoted key, or a stray quote."


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

    storage_cfg = settings.get("system", {}).get("storage", {})
    return _coerce_bool_setting(
        storage_cfg.get("auto_preroll") if isinstance(storage_cfg, dict) else None, True
    )


def storage_preroll_enabled(settings: dict) -> bool:
    """Backward-compatible alias for automatic storage pre-roll."""

    return auto_storage_preroll_enabled(settings)


def _apply_settings_defaults(settings: dict) -> dict:
    # ── system: splash, network, storage behavior ──────────────────────────
    system_cfg = settings.setdefault("system", {})

    welcome_cfg = system_cfg.setdefault("welcome", {})
    welcome_cfg.setdefault("show", True)
    welcome_cfg.setdefault("message", "THIS IS A COOL MACHINE")
    welcome_cfg.setdefault("image", None)
    system_cfg["welcome"] = welcome_cfg

    wifi_defaults = {
        "name": "CinePi",
        "password": "11111111",
        "enabled": True,
    }
    wifi_cfg = system_cfg.setdefault("wifi_hotspot", {})
    for k, v in wifi_defaults.items():
        wifi_cfg.setdefault(k, v)
    system_cfg["wifi_hotspot"] = wifi_cfg

    storage_cfg = system_cfg.setdefault("storage", {})
    storage_cfg.setdefault("auto_preroll", True)
    storage_cfg["auto_preroll"] = _coerce_bool_setting(storage_cfg.get("auto_preroll"), True)
    storage_cfg.setdefault("recognized_ssds", [])
    system_cfg["storage"] = storage_cfg

    settings["system"] = system_cfg

    # ── camera: per-sensor hardware + dual-sensor record policy ────────────
    camera_cfg = settings.setdefault("camera", {})
    camera_cfg.setdefault("raw_buffer_count", 0)
    # "follow_preview": recording follows the HDMI preview (side-by-side
    # records both, a full-screen/pip-main sensor records alone). A camera
    # token on `rec` overrides either policy for one take. No effect with a
    # single sensor. "always_both" forces both sensors every take regardless
    # of preview. See docs/dual-sensors.md#recording.
    camera_cfg.setdefault("record_policy", "follow_preview")
    # Legacy top-level "geometry"/"output" sections (written by settings.jsonc
    # files that predate the camera.cam0/cam1 nesting) still fold in here.
    old_geo = settings.pop("geometry", None) or {}
    old_out = settings.pop("output", None) or {}
    for port, default_hdmi in (("cam0", 0), ("cam1", 1)):
        cam = camera_cfg.setdefault(port, {})
        if "geometry" not in cam and port in old_geo:
            cam["geometry"] = old_geo[port]
        geo = cam.setdefault("geometry", {})
        geo.setdefault("rotate_180",       False)
        geo.setdefault("horizontal_flip",  False)
        geo.setdefault("vertical_flip",    False)
        if "output" not in cam and port in old_out:
            cam["output"] = old_out[port]
        out = cam.setdefault("output", {})
        out.setdefault("hdmi_port", default_hdmi)
        cam.setdefault("override_camera_name", False)
        cam.setdefault("camera_name",          "")
        cam.setdefault("phase_lock", True)
        tf = cam.setdefault("tuning_file_override", {})
        tf.setdefault("enabled", False)
        tf.setdefault("path", "resources/tuning_files/imx477.json")
        # CineMate Log target: False (off) | True (on, mode's default target) |
        # 10 | 12 (on, forced target). Off by default -- log changes recorded
        # output. Resolved against the live sensor + bit depth at launch via
        # SensorDetect.resolve_log_encode_target(); never a raw flag value.
        cam.setdefault("log_encode", False)
    sensor_cfg = camera_cfg.setdefault("sensors", {})
    sensor_cfg.setdefault("database_file", "resources/sensors.json")
    camera_cfg["sensors"] = sensor_cfg
    settings["camera"] = camera_cfg

    # ── capture: recording-wide behavior + resolution/HDR filters ──────────
    capture_cfg = settings.setdefault("capture", {})
    capture_cfg.setdefault("conform_frame_rate", 24)
    capture_cfg.setdefault("light_hz", [50, 60])

    tol_cfg = capture_cfg.setdefault("sync_tolerances", {})
    tolerance_defaults = {
        "live_sync_warning_frames": 5,
        "live_sync_startup_guard_frames": 10,
        "final_sync_analysis_frames": 1,
        "tc_drop_jitter_frames": 1,
    }
    for k, v in tolerance_defaults.items():
        tol_cfg.setdefault(k, v)
    capture_cfg["sync_tolerances"] = tol_cfg

    res_cfg = capture_cfg.setdefault("resolutions", {})
    resolution_defaults = {
        "k_steps": [1.5, 2.0, 4.0],
        "bit_depths": [10, 12],
        # ClearHDR (imx585) whitelist. Both true exposes the plain and the HDR
        # modes; set "imx585_clear_hdr" false to hide the HDR modes. See
        # SensorDetect._hdr_whitelist.
        "hdr": {"sdr": True, "imx585_clear_hdr": True},
        "custom_modes": {},
    }
    for k, v in resolution_defaults.items():
        res_cfg.setdefault(k, v)
    capture_cfg["resolutions"] = res_cfg
    settings["capture"] = capture_cfg

    # ── parameters: one block per cycle-able camera parameter ──────────────
    # steps = the selectable table; free = continuous stepping instead of the
    # table. Kept in the shape parameters.REGISTRY expects (name -> {steps,
    # free}) -- see module/parameters.py.
    parameters_cfg = settings.setdefault("parameters", {})
    parameter_defaults = {
        "iso": {
            "steps": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
            "free": False,
        },
        "shutter_a": {
            "steps": [1, 45, 90, 135, 172.8, 180, 225, 270, 315, 360],
            "free": False,
        },
        "fps": {
            "steps": [1, 2, 4, 8, 12, 16, 18, 24, 25, 30],
            "free": False,
        },
        "wb": {
            "steps": [3200, 4400, 5600],
            "free": False,
        },
    }
    for name, defaults in parameter_defaults.items():
        p_cfg = parameters_cfg.setdefault(name, {})
        for k, v in defaults.items():
            p_cfg.setdefault(k, v)
        parameters_cfg[name] = p_cfg
    settings["parameters"] = parameters_cfg

    # ── audio: capture gain + timecode offset per mic path ──────────────────
    # Migrate old flat keys to nested per-toolchain objects.
    audio_cfg = settings.setdefault("audio", {})
    old_gain = audio_cfg.pop("capture_gain_db", 0.0)
    if "timecode_offset_frames" in audio_cfg and "24bit" not in audio_cfg:
        audio_cfg["24bit"] = {
            "capture_gain_db": old_gain,
            "timecode_offset_frames": audio_cfg.pop("timecode_offset_frames"),
        }
    if "plain_arecord_timecode_offset_frames" in audio_cfg and "16bit" not in audio_cfg:
        audio_cfg["16bit"] = {
            "capture_gain_db": old_gain,
            "timecode_offset_frames": audio_cfg.pop("plain_arecord_timecode_offset_frames"),
        }
    audio_cfg.setdefault("24bit", {})
    audio_cfg["24bit"].setdefault("capture_gain_db", 0.0)
    audio_cfg["24bit"].setdefault("timecode_offset_frames", 0)
    audio_cfg.setdefault("16bit", {})
    audio_cfg["16bit"].setdefault("capture_gain_db", 0.0)
    audio_cfg["16bit"].setdefault("timecode_offset_frames", 0)
    settings["audio"] = audio_cfg

    # ── display: everything the operator sees ───────────────────────────────
    display_cfg = settings.setdefault("display", {})

    hdmi_cfg = display_cfg.setdefault("hdmi", {})
    hdmi_cfg.setdefault("width", 1920)
    hdmi_cfg.setdefault("height", 1080)
    # Single-sensor only: mirrors the one sensor's preview (with GUI) onto
    # BOTH HDMI connectors via cinepi-raw's --same-hdmi. The dual-sensor
    # compositor already owns both-feed layouts, so this has no effect with
    # two sensors attached.
    hdmi_cfg.setdefault("mirror_to_both_ports", False)
    display_cfg["hdmi"] = hdmi_cfg

    overlays_cfg = display_cfg.setdefault("overlays", {})
    overlays_cfg.setdefault("buffer_vu_meter", True)
    overlays_cfg.setdefault("vu_meter_hatch_lines", True)
    display_cfg["overlays"] = overlays_cfg

    preview_cfg = display_cfg.setdefault("preview", {})
    preview_cfg.setdefault("default_zoom", 1.0)
    preview_cfg.setdefault("zoom_steps", [1.0, 1.5, 2.0])
    preview_cfg["zoom_steps"] = sorted(set(preview_cfg["zoom_steps"]))
    if preview_cfg["default_zoom"] not in preview_cfg["zoom_steps"]:
        preview_cfg["default_zoom"] = preview_cfg["zoom_steps"][0]
    # Dual-sensor HDMI preview source at startup: both | cam0 | cam1 |
    # pip_cam0 | pip_cam1. Switch live with `set preview`. No effect with a
    # single sensor.
    preview_cfg.setdefault("default_hdmi_source", "both")
    pip_cfg = preview_cfg.setdefault("pip", {})
    pip_cfg.setdefault("scale", 0.28)
    pip_cfg.setdefault("corner", "lower_right")
    pip_cfg.setdefault("margin", 0.03)
    preview_cfg["pip"] = pip_cfg
    anamorphic_cfg = preview_cfg.setdefault("anamorphic", {})
    anamorphic_cfg.setdefault("default_factor", 1.00)
    anamorphic_cfg.setdefault("steps", [1.00, 1.33, 2.00])
    preview_cfg["anamorphic"] = anamorphic_cfg
    display_cfg["preview"] = preview_cfg

    settings["display"] = display_cfg

    # ── controls: every physical input, channel-first ──────────────────────
    controls_cfg = settings.setdefault("controls", {})
    controls_cfg.setdefault("buttons", [])
    controls_cfg.setdefault("two_way_switches", [])
    controls_cfg.setdefault("three_way_switches", [])
    controls_cfg.setdefault("rotary_encoders", [])
    controls_cfg.setdefault("combined_actions", [])
    # Analog pots: [{"channel": <adc-channel>, "setting": "<parameters key>"}]
    controls_cfg.setdefault("pots", [])
    controls_cfg.setdefault(
        "quad_rotary_controller",
        {"enabled": False, "encoders": []},
    )
    settings["controls"] = controls_cfg

    # ── outputs: everything Cinemate drives ─────────────────────────────────
    outputs_cfg = settings.setdefault("outputs", {})
    oled_cfg = outputs_cfg.setdefault("oled", {})
    oled_cfg.setdefault("enabled", False)
    oled_cfg.setdefault("width", 128)
    oled_cfg.setdefault("height", 64)
    oled_cfg.setdefault("font_size", 20)
    oled_cfg.setdefault("values", ["iso", "tc_cam0", "RECORDING_TC"])
    outputs_cfg["oled"] = oled_cfg
    outputs_cfg.setdefault("pwm_pin", 19)
    outputs_cfg.setdefault("rec_out_pin", [6, 21])
    rec_tone_cfg = outputs_cfg.setdefault("rec_tone", {})
    rec_tone_cfg.setdefault("pin", [])
    rec_tone_cfg.setdefault("frequency_hz", 1000)
    rec_tone_cfg.setdefault("duty_cycle", 50)
    rec_tone_cfg.setdefault("relay_drop_frames", False)
    outputs_cfg["rec_tone"] = rec_tone_cfg
    settings["outputs"] = outputs_cfg

    return settings


class _UnterminatedBlockComment(Exception):
    def __init__(self, line: int, column: int) -> None:
        self.line = line
        self.column = column


def _strip_jsonc_comments(text: str) -> str:
    """Blank out // and /* */ comments, outside of string literals.

    Comment characters become spaces rather than being deleted (newlines
    inside a block comment stay newlines), so every remaining character
    keeps its original line/column position. A json.JSONDecodeError raised
    against the result still points at the right place in the *original*
    file, and _format_error_context() -- which re-reads the original file
    from disk -- shows the user their real text, comments included.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            line_start = text.rfind("\n", 0, i) + 1
            start_line = text.count("\n", 0, i) + 1
            start_col = i - line_start + 1
            out.append("  ")
            i += 2
            closed = False
            while i < n:
                if text[i] == "*" and i + 1 < n and text[i + 1] == "/":
                    out.append("  ")
                    i += 2
                    closed = True
                    break
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if not closed:
                raise _UnterminatedBlockComment(start_line, start_col)
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _strip_trailing_commas(text: str) -> str:
    """Blank out a comma followed only by whitespace before } or ], outside
    of string literals, so a trailing comma parses instead of raising
    "Expecting property name enclosed in double quotes" / "Expecting value".
    """
    out = list(text)
    in_string = False
    escape = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                out[i] = " "
        i += 1
    return "".join(out)


def strip_jsonc(text: str) -> str:
    """Make settings.jsonc tolerant of // and /* */ comments and trailing
    commas, matching how a hand-edited config file is normally expected to
    behave. Length- and line-preserving, so downstream error reporting
    (SettingsLoadError.line/column, _format_error_context) stays accurate
    against the original file.
    """
    return _strip_trailing_commas(_strip_jsonc_comments(text))


def load_settings(filename: str | Path) -> dict:
    """
    Load CineMate’s JSON configuration *and* guarantee that every section the
    code relies on is present with safe defaults.

    Tolerates // and /* */ comments and trailing commas (see strip_jsonc()).

    Return an always-valid settings dict for valid JSON input.
    Raise SettingsLoadError when the file exists but cannot be parsed safely.
    """
    filename = Path(filename)
    try:
        with filename.open("r", encoding="utf-8") as fp:
            raw_text = fp.read()
    except FileNotFoundError:
        logging.warning("Settings file %s not found – using built-in defaults", filename)
        raw_text = None
    except UnicodeDecodeError as exc:
        raise SettingsLoadError(
            filename,
            "settings.jsonc is not valid UTF-8 text",
            str(exc),
            "Save settings.jsonc as UTF-8 text and remove any invalid binary characters.",
        ) from exc
    except OSError as exc:
        raise SettingsLoadError(
            filename,
            "settings.jsonc could not be read",
            str(exc),
            "Check that the file exists, is readable, and is not being edited by another process.",
        ) from exc

    if raw_text is None:
        settings = {}
    else:
        try:
            cleaned = strip_jsonc(raw_text)
        except _UnterminatedBlockComment as exc:
            raise SettingsLoadError(
                filename,
                "settings.jsonc has an unterminated /* comment",
                f"A /* comment starting at line {exc.line}, column {exc.column} is never closed with */",
                "Add the closing */ after the comment, or remove the stray /*.",
                line=exc.line,
                column=exc.column,
                context=_format_error_context(filename, exc.line, exc.column),
            ) from exc
        try:
            settings = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise SettingsLoadError.from_json_decode_error(filename, exc) from exc

    if not isinstance(settings, dict):
        raise SettingsLoadError(
            filename,
            "settings.jsonc must contain a top-level object",
            f"Expected the root of the file to be a JSON object, but found {type(settings).__name__}.",
            "Wrap the settings in { ... } and keep the top level as key/value pairs.",
        )

    return _apply_settings_defaults(settings)
