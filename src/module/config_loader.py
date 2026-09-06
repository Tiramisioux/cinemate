import json
import logging
from pathlib import Path

ANSI_RESET = "\033[0m"
ANSI_RED = "\033[1;31m"
ANSI_YELLOW = "\033[1;33m"
ANSI_CYAN = "\033[1;36m"

# F-260: this absolute path used to be hardcoded independently in six files
# (main.py, cinepi_multi.py, cinepi_controller.py, wifi_hotspot.py,
# simple_gui.py, app/settings_editor.py); one had already drifted out of
# sync with a comment that tried to enumerate the others by line number.
# services/cinemate-recovery/cinemate-recovery.py keeps its own copy
# deliberately -- that process must import nothing from module.* (F-221) so
# it can still run when the rest of the stack cannot.
DEFAULT_SETTINGS_PATH = "/home/pi/cinemate/settings.jsonc"

# The conform frame rate used when settings.jsonc does not name one. Exported
# because the same value was previously restated at four other call sites and
# had already drifted from the shipped configs (F-251: schema and this loader
# said 24, both shipped .jsonc files said 25, with no arbiter). Import it rather
# than writing the number again; settings.schema.json carries a sixth copy that
# cannot import, so _test/test_conform_frame_rate_default.py pins them together.
DEFAULT_CONFORM_FRAME_RATE = 25

# Public: a handful of call sites need the raw membership test (e.g. a CLI
# parser that must reject an unrecognised value outright rather than fall
# back to a default) instead of the as_bool() default-fallback shape below.
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


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


def normalize_log_encode(value, default: bool = False):
    """Decode a `log_encode` flag to its native type: bool, or an int target.

    `log_encode` is the one settings key whose options are not all one type --
    False | True | 10 | 12 -- so it cannot go through `as_bool`, and a plain
    string passes through the launch path silently wrong rather than loudly:
    `if log_requested:` in cinepi_multi makes the string "false" TRUTHY, so a
    corrupted "false" reads as log-on, while "true" is passed on as an explicit
    target, matches no valid bit depth, and records linear with only a warning.

    The settings editor used to write exactly those strings (its log_encode
    select was `data-type="string"`), so files already on cameras carry them.
    Normalising on load means such a file heals itself on the next start
    instead of needing a hand edit.

    - bool and int pass through unchanged (an out-of-range int is left alone;
      `SensorDetect.resolve_log_encode_target()` is what validates targets).
    - A string matching TRUE_VALUES/FALSE_VALUES decodes via `as_bool`.
    - Any other numeric string becomes that int, so "10"/"12" behave as 10/12.
    - Anything unrecognised falls back to `default`, same as an absent key.
    """
    if isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        if text.lower() in TRUE_VALUES or text.lower() in FALSE_VALUES:
            return as_bool(text, default=default)
        try:
            return int(text)
        except ValueError:
            logging.debug(
                "normalize_log_encode: unrecognised value %r, defaulting to %s",
                value, default,
            )
            return default
    return default


def as_bool(value, default: bool = False) -> bool:
    """Decode a settings.jsonc / Redis boolean the same way everywhere.

    This used to be four independent copies (cinepi_controller, gpio_input,
    dynamic_resolution, mediator) that quietly disagreed -- e.g. `_as_bool(2)`
    was `True` in gpio_input and `False` in the other three (F-126) -- plus
    the same `("1","true","yes","on")` truth-set re-typed standalone in half
    a dozen more places. This is the one decoder; everything routes here now.

    - bool passes through unchanged.
    - None means "not set" and returns `default` silently -- that is the
      normal, expected shape of an absent key.
    - int/float use Python truthiness (`bool(value)`): 2 is True, matching
      how a settings-file author reads a truthy value, and matching what
      gpio_input already did. (Nothing in settings.jsonc currently sends a
      non-0/1 number through here -- checked when this was unified -- so
      this is a decision for future values, not an observed behaviour fix.)
    - str is matched case-insensitively against `TRUE_VALUES`/`FALSE_VALUES`
      first (Redis stores every value as text, so this is the common path),
      then against a numeric fallback (`bool(int(text))`) so a stray "2"
      decodes the same way the int 2 does instead of being "unrecognised" --
      three call sites already relied on exactly this before the merge.
    - Anything else -- an unrecognised string, or a non-str/bool/int/float/
      None object -- is NOT the same as an explicit false. It falls back to
      `default`, same as an absent value, but at `debug` level (not `warning`)
      because this runs on the 12 fps GUI redraw path and a stuck bad value
      must not flood the log every frame -- see "fail visible" vs. the
      redraw-path logging rule, both in the project's own conventions.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in TRUE_VALUES:
            return True
        if normalized in FALSE_VALUES:
            return False
        try:
            return bool(int(normalized))
        except ValueError:
            pass
    logging.debug(
        "as_bool: unrecognised value %r, defaulting to %s", value, default
    )
    return default


def auto_storage_preroll_enabled(settings: dict) -> bool:
    """Return whether automatic storage pre-roll should run."""

    storage_cfg = settings.get("system", {}).get("storage", {})
    return as_bool(
        storage_cfg.get("auto_preroll") if isinstance(storage_cfg, dict) else None, True
    )


def storage_preroll_enabled(settings: dict) -> bool:
    """Backward-compatible alias for automatic storage pre-roll."""

    return auto_storage_preroll_enabled(settings)


def clearhdr_self_heal_enabled(settings: dict) -> bool:
    """Return whether the ClearHDR flat-pedestal self-heal may run.

    Defaults to False. The self-heal fires from ``CinePiManager.start_all()``,
    which every cold start and every resolution switch funnels through, and
    none of the recovery actions it can take has been shown to work on
    hardware -- the mode bounce and an earlier analogue-gain shock were both
    live-tested and failed. Its detector also has no way to distinguish the
    defect from a legitimately flat or dark scene. Off unless asked for.
    """

    hdr_cfg = settings.get("image_capture", {}).get("hdr", {})
    return as_bool(
        hdr_cfg.get("self_heal") if isinstance(hdr_cfg, dict) else None, False
    )


def clearhdr_startup_values(settings: dict) -> dict:
    """Startup values for the ClearHDR live knobs, keyed by Redis key.

    The two data-selection thresholds only come back as numbers when
    ``image_capture.hdr`` actually configures them. Left unset they come back
    as ``""``, which means "write nothing" rather than "write zero":
    cinepi-raw skips the sensor write entirely while both are empty, so the
    imx585 driver keeps the pair it boots with (EXP_TH_H 0x0FFF,
    EXP_TH_L 0x0000).

    That distinction is the point of this helper. EXP_TH_H == EXP_TH_L selects
    the AppNote's weighted-blend fallback, which leaves the ClearHDR combiner
    clamped near the black level on ordinary scenes; the driver carries a
    comment saying exactly that, and defaults to the rule-based range instead.
    Seeding 0/0 wrote that rejected configuration over the driver's own
    default on every boot.

    The empty string is written rather than skipped so a 0 persisted into
    Redis by an earlier build is cleared on upgrade instead of surviving it.

    ``blend`` is seeded at 5 (HG 1/16) rather than the driver's own 0. Seeding 0
    is what produces the flat black-level pedestal launches described in
    docs/clear-hdr.md; 5 is the value that was measured to avoid them. The
    mechanism is separate from the threshold pair above, which fails a different
    way. ``gain_adder`` keeps its previous default: 1 (+6 dB) is a deliberate
    choice over the driver's +12 dB.
    """

    hdr_cfg = settings.get("image_capture", {}).get("hdr", {})
    if not isinstance(hdr_cfg, dict):
        hdr_cfg = {}

    def threshold(name):
        value = hdr_cfg.get(name)
        return "" if value is None else value

    return {
        "hdr_threshold_low": threshold("threshold_low"),
        "hdr_threshold_high": threshold("threshold_high"),
        "hdr_blend": hdr_cfg.get("blend", 5),
        "hdr_gain_adder": hdr_cfg.get("gain_adder", 1),
    }


def thumbnail_startup_value(settings: dict) -> int:
    """Validated startup value for image_capture.thumbnail, keyed by Redis key.

    main.py used to pass settings.get("image_capture", {}).get("thumbnail", 0)
    straight to redis_controller.set_value() with no validation -- unlike
    set_thumbnail() (cinepi_controller.py), which clamps int(value) to 0..2.
    A hand-edited settings.jsonc with "thumbnail": true crashed Cinemate at
    startup (redis-py rejects a bool where set_thumbnail() would have
    coerced it), a non-numeric string reached cinepi-raw's sync() and its
    then-unguarded stoi(), and 3 passed through where the CLI path clamps
    to 2 -- so the same raw value in the file meant "off" via one path and
    "colour" via the other. This applies the exact same clamp as
    set_thumbnail() so both paths agree, and so a malformed value degrades
    to a safe default instead of reaching either process unvalidated.

    Defaults to 2 (colour), not 0: the embedded thumbnail is now the
    standard playback path, and playback.py's raw-decode fallback is
    disabled (too demanding on the Pi, operator decision after G10/G11) --
    so a take recorded with thumbnail=0, or a parse failure that used to
    fall back to 0, would otherwise be unplayable in the pane.
    """
    raw = settings.get("image_capture", {}).get("thumbnail", 2)
    try:
        return max(0, min(2, int(raw)))
    except (TypeError, ValueError):
        return 2


REC_TONE_DEFAULTS = {
    "pin": [],
    "frequency_hz": 1000,
    "duty_cycle": 50,
    "relay_drop_frames": False,
}


def rec_tone_config(gpio_cfg: dict) -> dict:
    """Read hardware_outputs.rec_tone, tolerating the pre-c171975e flat keys.

    c171975e regrouped `rec_tone_pin` / `rec_tone_frequency_hz` /
    `rec_tone_duty_cycle` / `rec_tone_relay_drop_frames` under a nested
    `rec_tone` object. main.py's section name was updated; its leaf reads were
    not, so every one of them silently fell back to a hardcoded default -- the
    configured tone pin was ignored in favour of pwm_pin, frequency and duty
    cycle could not be changed at all, and relay_drop_frames could never be
    true, which meant relay_drop_frame_on_rec_tone() returned at its guard on
    every call. settings.schema.json declares rec_tone with
    additionalProperties:false, so the flat keys cannot appear in a current
    file; the fallback is only for a hand-written one predating the rename.
    """
    nested = gpio_cfg.get("rec_tone") or {}
    return {
        key: nested[key] if key in nested else gpio_cfg.get(f"rec_tone_{key}", default)
        for key, default in REC_TONE_DEFAULTS.items()
    }


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
    storage_cfg["auto_preroll"] = as_bool(storage_cfg.get("auto_preroll"), True)
    storage_cfg.setdefault("recognized_ssds", [])
    system_cfg["storage"] = storage_cfg

    settings["system"] = system_cfg

    # ── sensors: per-sensor hardware + dual-sensor record policy ───────────
    sensors_cfg = settings.setdefault("sensors", {})
    sensors_cfg.setdefault("raw_buffer_count", 0)
    # "follow_preview": recording follows the HDMI preview (side-by-side
    # records both, a full-screen/pip-main sensor records alone). A camera
    # token on `rec` overrides either policy for one take. No effect with a
    # single sensor. "always_both" forces both sensors every take regardless
    # of preview. See docs/dual-sensors.md#recording.
    sensors_cfg.setdefault("record_policy", "follow_preview")
    # Legacy top-level "geometry"/"output" sections (written by settings.jsonc
    # files that predate the cam0/cam1 nesting) still fold in here.
    old_geo = settings.pop("geometry", None) or {}
    old_out = settings.pop("output", None) or {}
    for port, default_hdmi in (("cam0", 0), ("cam1", 1)):
        cam = sensors_cfg.setdefault(port, {})
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
        cam["log_encode"] = normalize_log_encode(cam.get("log_encode", False))
    sensors_cfg.setdefault("database_file", "resources/sensors.json")
    settings["sensors"] = sensors_cfg

    # ── settings: frame-rate conform + flicker-free input + sync tuning ────
    settings_cfg = settings.setdefault("settings", {})
    settings_cfg.setdefault("conform_frame_rate", DEFAULT_CONFORM_FRAME_RATE)
    settings_cfg.setdefault("light_hz", [50, 60])

    tol_cfg = settings_cfg.setdefault("sync_tolerances", {})
    tolerance_defaults = {
        "live_sync_warning_frames": 5,
        "live_sync_startup_guard_frames": 10,
        "final_sync_analysis_frames": 1,
        "tc_drop_jitter_frames": 1,
    }
    for k, v in tolerance_defaults.items():
        tol_cfg.setdefault(k, v)
    settings_cfg["sync_tolerances"] = tol_cfg
    settings["settings"] = settings_cfg

    # ── arrays: one block per cycle-able camera parameter ──────────────────
    # steps = the selectable table; free = continuous stepping instead of the
    # table, in units of free_increment. Each parameter block is kept in the
    # shape parameters.REGISTRY expects (name -> {steps, free, free_increment})
    # -- see module/parameters.py.
    arrays_cfg = settings.setdefault("arrays", {})
    parameter_defaults = {
        "iso": {
            "steps": [100, 200, 400, 640, 800, 1200, 1600, 2500, 3200],
            "free": False,
            "free_increment": 100,
        },
        "shutter_a": {
            "steps": [1, 45, 90, 135, 172.8, 180, 225, 270, 315, 346.6, 360],
            "free": True,
            "free_increment": 1,
            # Own granularity used only while shutter-angle sync mode is on
            # (`set shutter a sync`) -- independent of free_increment, which
            # is for manual free-roam pot/encoder control.
            "sync_increment": 0.1,
        },
        "fps": {
            "steps": [25, 33, 50],
            "free": False,
            "free_increment": 1,
        },
        "wb": {
            "steps": [3200, 4400, 5600],
            "free": True,
            "free_increment": 100,
        },
        # ClearHDR live knobs -- ranges per the imx585 driver: thresholds
        # 0-4095 each, blend mode 0-8, gain adder 0-5.
        "hdr_threshold_low": {
            "steps": [0, 512, 1024, 1536, 2048, 2560, 3072, 3584, 4095],
            "free": False,
            "free_increment": 16,
        },
        "hdr_threshold_high": {
            "steps": [0, 512, 1024, 1536, 2048, 2560, 3072, 3584, 4095],
            "free": False,
            "free_increment": 16,
        },
        "hdr_blend": {
            "steps": [0, 1, 2, 3, 4, 5, 6, 7, 8],
            "free": False,
            "free_increment": 1,
        },
        "hdr_gain_adder": {
            "steps": [0, 1, 2, 3, 4, 5],
            "free": False,
            "free_increment": 1,
        },
    }
    for name, defaults in parameter_defaults.items():
        p_cfg = arrays_cfg.setdefault(name, {})
        for k, v in defaults.items():
            p_cfg.setdefault(k, v)
        arrays_cfg[name] = p_cfg
    settings["arrays"] = arrays_cfg

    # ── image_capture: resolution / bit-depth / HDR filters ────────────────
    image_capture_cfg = settings.setdefault("image_capture", {})
    image_capture_defaults = {
        "k_steps": [1.5, 2.0, 3.0, 4.0],
        "bit_depths": [10, 12, 16],
        # ClearHDR (imx585) whitelist. Both true exposes the plain and the HDR
        # modes; set "imx585_clear_hdr" false to hide the HDR modes. See
        # SensorDetect._hdr_whitelist.
        "hdr": {"sdr": True, "imx585_clear_hdr": True},
        # 2 (colour): the embedded thumbnail is the standard playback path
        # now, not an opt-in -- see thumbnail_startup_value()'s docstring.
        "thumbnail": 2,
        # Dynamic resolution: substitute a smaller mode from the same family
        # when the requested fps outruns the selected one. Startup default
        # only -- `set dynamic resolution 0/1` overrides it for the session
        # and persists in Redis, which is what a later boot reads back.
        "dynamic_resolution": True,
        "custom_modes": {},
    }
    for k, v in image_capture_defaults.items():
        image_capture_cfg.setdefault(k, v)
    settings["image_capture"] = image_capture_cfg

    # ── audio_capture: capture gain + timecode offset per mic path ─────────
    # Migrate old flat keys to nested per-toolchain objects.
    audio_cfg = settings.setdefault("audio_capture", {})
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
    settings["audio_capture"] = audio_cfg

    # ── hdmi_display: HDMI canvas, GUI overlays, preview ────────────────────
    hdmi_display_cfg = settings.setdefault("hdmi_display", {})
    hdmi_display_cfg.setdefault("width", 1920)
    hdmi_display_cfg.setdefault("height", 1080)
    # Single-sensor only: mirrors the one sensor's preview (with GUI) onto
    # BOTH HDMI connectors via cinepi-raw's --same-hdmi. The dual-sensor
    # compositor already owns both-feed layouts, so this has no effect with
    # two sensors attached.
    hdmi_display_cfg.setdefault("mirror_to_both_ports", False)

    overlays_cfg = hdmi_display_cfg.setdefault("overlays", {})
    overlays_cfg.setdefault("buffer_vu_meter", True)
    overlays_cfg.setdefault("vu_meter_hatch_lines", True)
    hdmi_display_cfg["overlays"] = overlays_cfg

    preview_cfg = hdmi_display_cfg.setdefault("preview", {})
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
    hdmi_display_cfg["preview"] = preview_cfg

    settings["hdmi_display"] = hdmi_display_cfg

    # ── hardware_controls: direct-GPIO physical inputs, channel-first ──────
    controls_cfg = settings.setdefault("hardware_controls", {})
    controls_cfg.setdefault("buttons", [])
    controls_cfg.setdefault("two_way_switches", [])
    controls_cfg.setdefault("three_way_switches", [])
    controls_cfg.setdefault("rotary_encoders", [])
    controls_cfg.setdefault("combined_actions", [])
    settings["hardware_controls"] = controls_cfg

    # ── input_peripherals: Grove Base HAT pots + quad I2C rotary board ─────
    input_peripherals_cfg = settings.setdefault("input_peripherals", {})
    # Analog pots: [{"channel": <adc-channel>, "setting": "<settings key>"}]
    input_peripherals_cfg.setdefault("pots", [])
    quad_cfg = input_peripherals_cfg.setdefault(
        "quad_rotary_controller",
        {"enabled": False, "encoders": {}},
    )
    quad_cfg.setdefault("enabled", False)
    quad_cfg.setdefault("encoders", {})
    input_peripherals_cfg["quad_rotary_controller"] = quad_cfg
    settings["input_peripherals"] = input_peripherals_cfg

    # ── hardware_outputs: direct-GPIO outputs Cinemate drives ──────────────
    outputs_cfg = settings.setdefault("hardware_outputs", {})
    outputs_cfg.setdefault("pwm_pin", 19)
    outputs_cfg.setdefault("rec_out_pin", [6, 21])
    rec_tone_cfg = outputs_cfg.setdefault("rec_tone", {})
    for _key, _default in REC_TONE_DEFAULTS.items():
        rec_tone_cfg.setdefault(_key, _default)
    outputs_cfg["rec_tone"] = rec_tone_cfg
    settings["hardware_outputs"] = outputs_cfg

    # ── output_peripherals: the optional I2C OLED status screen ────────────
    output_peripherals_cfg = settings.setdefault("output_peripherals", {})
    oled_cfg = output_peripherals_cfg.setdefault("oled", {})
    oled_cfg.setdefault("enabled", False)
    oled_cfg.setdefault("width", 128)
    oled_cfg.setdefault("height", 64)
    oled_cfg.setdefault("font_size", 20)
    oled_cfg.setdefault("values", ["iso", "tc_cam0", "RECORDING_TC"])
    output_peripherals_cfg["oled"] = oled_cfg
    settings["output_peripherals"] = output_peripherals_cfg

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
