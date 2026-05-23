"""Lookup-table based dynamic resolution selection."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_MATCH_TOLERANCE_PX = 32
DEFAULT_PROFILES_FILE = "resources/dynamic_resolution_profiles.json"
DEFAULT_OBSERVED_PROFILES_FILE = "src/dynamic_resolution_observed_profiles.json"
DEFAULT_PROFILE_NAME = "default"
DEFAULT_OBSERVED_PROFILE_NAME = "observed"
DEFAULT_POLICY = "highest_sustainable_resolution"
STORAGE_TYPE_ALIASES = {
    "cf express": "cfe",
    "cfexpress": "cfe",
    "cfe hat": "cfe",
    "cfehat": "cfe",
    "usb": "ssd",
    "usb ssd": "ssd",
    "usb disk": "ssd",
    "usb storage": "ssd",
}


@dataclass(frozen=True)
class ResolutionPerformance:
    sensor: str
    sensor_aliases: frozenset[str]
    storage_type: str
    filesystem: str
    width: int
    height: int
    bit_depth: int | None
    max_fps: float
    notes: str = ""

    @property
    def area(self) -> int:
        return self.width * self.height

    def effective_max_fps(self, safety_margin_fps: float = 0) -> float:
        return max(0.0, self.max_fps - max(0.0, float(safety_margin_fps or 0)))


@dataclass(frozen=True)
class DynamicResolutionChoice:
    mode: int
    row: ResolutionPerformance
    desired_mode: int
    desired_row: ResolutionPerformance
    dynamic_active: bool


def default_dynamic_resolution_config() -> dict[str, Any]:
    """Return a fresh default config for settings.json."""
    return {
        "enabled": False,
        "profile": DEFAULT_PROFILE_NAME,
        "profiles_file": DEFAULT_PROFILES_FILE,
        "use_observed_profile": False,
        "observed_profile": DEFAULT_OBSERVED_PROFILE_NAME,
        "observed_profiles_file": DEFAULT_OBSERVED_PROFILES_FILE,
        "policy": DEFAULT_POLICY,
        "safety_margin_fps": 0,
        "match_tolerance_px": DEFAULT_MATCH_TOLERANCE_PX,
        "learning": {
            "enabled": False,
            "minimum_duration_seconds": 10,
            "buffer_tolerance_frames": 0,
            "failure_backoff_fps": 1,
        },
    }


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_storage_type(value: Any) -> str:
    text = _normalize_text(value).replace("_", " ").replace("-", " ")
    text = " ".join(text.split())
    compact = text.replace(" ", "")
    if text in STORAGE_TYPE_ALIASES:
        return STORAGE_TYPE_ALIASES[text]
    if compact in STORAGE_TYPE_ALIASES:
        return STORAGE_TYPE_ALIASES[compact]
    if "cfe" in compact or "cfexpress" in compact:
        return "cfe"
    if "nvme" in compact:
        return "nvme"
    if "ssd" in compact:
        return "ssd"
    return compact or text


def _sensor_candidates(sensor: Any) -> set[str]:
    text = _normalize_text(sensor)
    candidates = {text}
    if text.endswith("_mono"):
        candidates.add(text[:-5])
    return candidates


def _row_sensor_values(row: dict[str, Any]) -> frozenset[str]:
    values = _sensor_candidates(row.get("sensor"))
    aliases = row.get("sensor_aliases", [])
    if isinstance(aliases, str):
        aliases = [aliases]
    for alias in aliases or []:
        values.update(_sensor_candidates(alias))
    return frozenset(item for item in values if item)


def _as_storage_values(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {_normalize_storage_type(item) for item in value}
    return {_normalize_storage_type(value)}


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result <= 0:
        return None
    return result


def resolve_profiles_path(profiles_file: str, settings_file: str | Path | None = None) -> Path:
    path = Path(profiles_file or DEFAULT_PROFILES_FILE)
    if path.is_absolute():
        return path

    candidates: list[Path] = []
    if settings_file:
        settings_dir = Path(settings_file).expanduser().resolve().parent
        candidates.extend([
            settings_dir / path,
            settings_dir.parent / path,
        ])
    candidates.append(Path.cwd() / path)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def load_profile_rows(config: dict[str, Any], *, settings_file: str | Path | None = None) -> list[dict[str, Any]]:
    """Load measurement rows for the selected profile.

    Inline ``performance_table`` is kept as a backward-compatible augmentation.
    Matching inline rows override profile-file rows, but they no longer replace
    the whole stock database because that can hide newer storage/filesystem rows
    from older settings files.
    """
    profile = str(config.get("profile") or DEFAULT_PROFILE_NAME)
    rows = _load_rows_from_profile_file(
        config.get("profiles_file") or DEFAULT_PROFILES_FILE,
        profile,
        settings_file=settings_file,
    )
    inline_rows = [
        dict(row)
        for row in (config.get("performance_table") or [])
        if isinstance(row, dict)
    ]
    if inline_rows:
        rows = merge_observed_rows(rows, inline_rows) if rows else inline_rows

    if config.get("use_observed_profile", False):
        observed_rows = _load_rows_from_profile_file(
            config.get("observed_profiles_file") or DEFAULT_OBSERVED_PROFILES_FILE,
            str(config.get("observed_profile") or DEFAULT_OBSERVED_PROFILE_NAME),
            settings_file=settings_file,
            warn_missing=False,
        )
        rows = merge_observed_rows(rows, observed_rows)

    return rows


def _load_rows_from_profile_file(
    profiles_file: str,
    profile: str,
    *,
    settings_file: str | Path | None = None,
    warn_missing: bool = True,
) -> list[dict[str, Any]]:
    path = resolve_profiles_path(profiles_file, settings_file=settings_file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        if warn_missing:
            logging.warning("Dynamic resolution profile file unavailable (%s): %s", path, exc)
        return []
    except json.JSONDecodeError as exc:
        logging.warning("Dynamic resolution profile file is invalid JSON (%s): %s", path, exc)
        return []

    profiles = data.get("profiles", {})
    rows = profiles.get(profile, [])
    if not isinstance(rows, list):
        logging.warning("Dynamic resolution profile %s in %s is not a list", profile, path)
        return []
    return rows


def _row_identity(row: dict[str, Any]) -> tuple:
    return (
        _normalize_text(row.get("sensor")),
        tuple(sorted(_as_storage_values(row.get("storage_type", "any")))),
        _normalize_text(row.get("filesystem")),
        _as_int(row.get("width")),
        _as_int(row.get("height")),
        _as_int(row.get("bit_depth")),
    )


def _rows_match_measurement_scope(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_identity = _row_identity(left)
    right_identity = _row_identity(right)
    if left_identity[2:] != right_identity[2:]:
        return False
    left_storage = _as_storage_values(left.get("storage_type", "any"))
    right_storage = _as_storage_values(right.get("storage_type", "any"))
    if "any" not in left_storage and "any" not in right_storage:
        if left_storage.isdisjoint(right_storage):
            return False
    return not _row_sensor_values(left).isdisjoint(_row_sensor_values(right))


def _with_storage_values(row: dict[str, Any], storage_values: set[str]) -> dict[str, Any]:
    updated = dict(row)
    values = sorted(value for value in storage_values if value)
    if len(values) == 1:
        updated["storage_type"] = values[0]
    else:
        updated["storage_type"] = values
    return updated


def merge_observed_rows(
    standard_rows: Iterable[dict[str, Any]],
    observed_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple, dict[str, Any]] = {}
    for row in standard_rows or []:
        if isinstance(row, dict):
            merged[_row_identity(row)] = dict(row)
    for row in observed_rows or []:
        if isinstance(row, dict):
            next_merged: dict[tuple, dict[str, Any]] = {}
            observed_storage = _as_storage_values(row.get("storage_type", "any"))
            for key, standard_row in merged.items():
                if not _rows_match_measurement_scope(standard_row, row):
                    next_merged[key] = standard_row
                    continue

                standard_storage = _as_storage_values(standard_row.get("storage_type", "any"))
                if "any" in standard_storage or "any" in observed_storage:
                    continue

                remaining_storage = standard_storage - observed_storage
                if remaining_storage:
                    remaining_row = _with_storage_values(standard_row, remaining_storage)
                    next_merged[_row_identity(remaining_row)] = remaining_row
            merged = next_merged
            merged[_row_identity(row)] = dict(row)
    return list(merged.values())


def update_observed_profile(
    config: dict[str, Any],
    observation: dict[str, Any],
    *,
    settings_file: str | Path | None = None,
) -> bool:
    path = resolve_profiles_path(
        config.get("observed_profiles_file") or DEFAULT_OBSERVED_PROFILES_FILE,
        settings_file=settings_file,
    )
    profile = str(config.get("observed_profile") or DEFAULT_OBSERVED_PROFILE_NAME)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {"schema_version": 1, "profiles": {}}
    except OSError as exc:
        logging.warning("Unable to read dynamic resolution observed profile %s: %s", path, exc)
        return False
    except json.JSONDecodeError as exc:
        logging.warning("Dynamic resolution observed profile is invalid JSON (%s): %s", path, exc)
        return False

    profiles = data.setdefault("profiles", {})
    rows = profiles.setdefault(profile, [])
    if not isinstance(rows, list):
        rows = []
        profiles[profile] = rows

    key = _row_identity(observation)
    existing = None
    for row in rows:
        if isinstance(row, dict) and _row_identity(row) == key:
            existing = row
            break

    observed_fps = float(observation["observed_fps"])
    candidate_max = float(observation["max_fps_no_buffer"])

    if existing is not None:
        existing_max = _as_float(existing.get("max_fps_no_buffer"))
        stable_max = _as_float(existing.get("stable_max_fps"))
        if observation.get("result") == "stable":
            if existing_max is not None:
                candidate_max = max(existing_max, candidate_max)
        elif stable_max is not None and stable_max >= observed_fps:
            candidate_max = existing_max if existing_max is not None else stable_max
        elif existing_max is not None:
            candidate_max = min(existing_max, candidate_max)

    if existing is None:
        existing = {
            "sensor": observation["sensor"],
            "sensor_aliases": observation.get("sensor_aliases", []),
            "storage_type": observation["storage_type"],
            "filesystem": observation["filesystem"],
            "media_model": observation.get("media_model", ""),
            "width": observation["width"],
            "height": observation["height"],
            "bit_depth": observation.get("bit_depth"),
            "sustainable_fps": candidate_max,
            "max_fps_no_buffer": candidate_max,
            "test_duration_seconds": observation.get("duration_seconds"),
            "buffer_peak_frames": observation.get("buffer_peak_frames", 0),
            "drop_frames": observation.get("drop_frames", 0),
            "confidence": "observed",
            "notes": "Local self-corrected observation.",
        }
        rows.append(existing)

    existing.update({
        "media_model": observation.get("media_model", existing.get("media_model", "")),
        "sustainable_fps": candidate_max,
        "max_fps_no_buffer": candidate_max,
        "test_duration_seconds": observation.get("duration_seconds"),
        "buffer_peak_frames": observation.get("buffer_peak_frames", 0),
        "drop_frames": observation.get("drop_frames", 0),
        "last_observed_at": observation.get("observed_at"),
        "last_result": observation.get("result"),
        "confidence": "observed",
    })
    existing["observation_count"] = int(existing.get("observation_count", 0) or 0) + 1
    if observation.get("result") == "stable":
        existing["stable_count"] = int(existing.get("stable_count", 0) or 0) + 1
        existing["stable_max_fps"] = max(
            float(existing.get("stable_max_fps", 0) or 0),
            observed_fps,
        )
    else:
        existing["failure_count"] = int(existing.get("failure_count", 0) or 0) + 1
        existing["max_failed_fps"] = max(
            float(existing.get("max_failed_fps", 0) or 0),
            observed_fps,
        )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        logging.warning("Unable to write dynamic resolution observed profile %s: %s", path, exc)
        return False

    return True


def parse_performance_table(rows: Iterable[dict[str, Any]]) -> list[ResolutionPerformance]:
    parsed: list[ResolutionPerformance] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        width = _as_int(row.get("width"))
        height = _as_int(row.get("height"))
        max_fps = _as_float(
            row.get(
                "sustainable_fps",
                row.get("max_fps_no_drop", row.get("max_fps_no_buffer", row.get("max_fps"))),
            )
        )
        if width is None or height is None or max_fps is None:
            continue
        storage_values = _as_storage_values(row.get("storage_type", "any"))
        sensor_values = _row_sensor_values(row)
        for storage_type in storage_values:
            parsed.append(
                ResolutionPerformance(
                    sensor=_normalize_text(row.get("sensor")),
                    sensor_aliases=sensor_values,
                    storage_type=storage_type or "any",
                    filesystem=_normalize_text(row.get("filesystem")),
                    width=width,
                    height=height,
                    bit_depth=_as_int(row.get("bit_depth")),
                    max_fps=max_fps,
                    notes=str(row.get("notes") or ""),
                )
            )
    return parsed


def _row_matches_context(
    row: ResolutionPerformance,
    *,
    sensor: str,
    storage_type: str,
    filesystem: str,
) -> bool:
    sensors = _sensor_candidates(sensor)
    if row.sensor_aliases and row.sensor_aliases.isdisjoint(sensors):
        return False
    if row.storage_type not in ("", "any", storage_type):
        return False
    if row.filesystem and row.filesystem != filesystem:
        return False
    return True


def _mode_matches_row(
    mode_info: dict[str, Any],
    row: ResolutionPerformance,
    *,
    tolerance_px: int,
) -> bool:
    width = _as_int(mode_info.get("width"))
    height = _as_int(mode_info.get("height"))
    if width is None or height is None:
        return False
    if abs(width - row.width) > tolerance_px:
        return False
    if abs(height - row.height) > tolerance_px:
        return False
    bit_depth = _as_int(mode_info.get("bit_depth"))
    if row.bit_depth is not None and bit_depth is not None and bit_depth != row.bit_depth:
        return False
    return True


def row_for_mode(
    rows: Iterable[ResolutionPerformance],
    sensor_modes: dict[int, dict[str, Any]],
    mode: int,
    *,
    tolerance_px: int,
) -> ResolutionPerformance | None:
    mode_info = sensor_modes.get(mode)
    if not mode_info:
        return None
    matches = [
        row
        for row in rows
        if _mode_matches_row(mode_info, row, tolerance_px=tolerance_px)
    ]
    if not matches:
        return None
    return max(matches, key=lambda row: (row.area, row.max_fps))


def choose_resolution(
    *,
    sensor_modes: dict[int, dict[str, Any]],
    desired_mode: int,
    requested_fps: float,
    sensor: str,
    storage_type: str,
    filesystem: str,
    performance_table: Iterable[dict[str, Any]],
    tolerance_px: int = DEFAULT_MATCH_TOLERANCE_PX,
    safety_margin_fps: float = 0,
    policy: str = DEFAULT_POLICY,
) -> DynamicResolutionChoice | None:
    """Choose the highest-resolution measured mode that can sustain requested_fps.

    Returning None means the table does not contain enough matching data to make
    a safe automatic change.
    """
    try:
        desired_mode = int(desired_mode)
        fps = float(requested_fps)
    except (TypeError, ValueError):
        return None

    normalized_modes: dict[int, dict[str, Any]] = {}
    for mode, mode_info in (sensor_modes or {}).items():
        try:
            normalized_modes[int(mode)] = mode_info
        except (TypeError, ValueError):
            continue

    if policy != DEFAULT_POLICY:
        return None

    if fps <= 0 or desired_mode not in normalized_modes:
        return None

    context_rows = [
        row
        for row in parse_performance_table(performance_table)
        if _row_matches_context(
            row,
            sensor=sensor,
            storage_type=_normalize_storage_type(storage_type),
            filesystem=_normalize_text(filesystem),
        )
    ]
    if not context_rows:
        return None

    desired_row = row_for_mode(
        context_rows,
        normalized_modes,
        desired_mode,
        tolerance_px=tolerance_px,
    )
    if desired_row is None:
        return None

    eligible: list[tuple[int, ResolutionPerformance]] = []
    for mode, mode_info in normalized_modes.items():
        mode_rows = [
            row
            for row in context_rows
            if row.effective_max_fps(safety_margin_fps) >= fps
            and _mode_matches_row(mode_info, row, tolerance_px=tolerance_px)
        ]
        if mode_rows:
            eligible.append((int(mode), max(mode_rows, key=lambda row: (row.area, row.max_fps))))

    if not eligible:
        return None

    selected_mode, selected_row = max(
        eligible,
        key=lambda item: (item[1].area, item[1].max_fps),
    )
    return DynamicResolutionChoice(
        mode=selected_mode,
        row=selected_row,
        desired_mode=desired_mode,
        desired_row=desired_row,
        dynamic_active=selected_mode != desired_mode,
    )


def max_fps_for_context(
    *,
    sensor_modes: dict[int, dict[str, Any]],
    sensor: str,
    storage_type: str,
    filesystem: str,
    performance_table: Iterable[dict[str, Any]],
    desired_mode: int | None = None,
    tolerance_px: int = DEFAULT_MATCH_TOLERANCE_PX,
    safety_margin_fps: float = 0,
    policy: str = DEFAULT_POLICY,
) -> float | None:
    if policy != DEFAULT_POLICY:
        return None

    normalized_modes: dict[int, dict[str, Any]] = {}
    for mode, mode_info in (sensor_modes or {}).items():
        try:
            normalized_modes[int(mode)] = mode_info
        except (TypeError, ValueError):
            continue

    context_rows = [
        row
        for row in parse_performance_table(performance_table)
        if _row_matches_context(
            row,
            sensor=sensor,
            storage_type=_normalize_storage_type(storage_type),
            filesystem=_normalize_text(filesystem),
        )
    ]
    if not context_rows:
        return None

    if desired_mode is not None:
        try:
            desired_mode_int = int(desired_mode)
        except (TypeError, ValueError):
            return None
        if row_for_mode(
            context_rows,
            normalized_modes,
            desired_mode_int,
            tolerance_px=tolerance_px,
        ) is None:
            return None

    measured_maxes = []
    for mode_info in normalized_modes.values():
        measured_maxes.extend(
            row.effective_max_fps(safety_margin_fps)
            for row in context_rows
            if _mode_matches_row(mode_info, row, tolerance_px=tolerance_px)
        )

    if not measured_maxes:
        return None
    return max(measured_maxes)
