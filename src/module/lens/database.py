"""The lens database: one JSON file of named lens profiles, plus the maths on them.

``resources/lenses.json`` is to lenses what ``resources/sensors.json`` is to
sensors -- one file, resolved repo-relative the same way -- with one difference
that decides everything below: this file is *written by the camera*. It is
therefore gitignored (a tracked file the camera edits would block
``cinemate-update.sh``'s ``git pull --ff-only``, the same reason the per-sensor
``/settings_*.jsonc`` files are ignored), and a missing file is simply an empty
database. There is no second "defaults" file.

Standard library only, plus ``sensor_database.repo_root`` (itself stdlib only):
the settings editor imports this with no camera attached and no Redis running.

What the file protects against, because it is operator data:

* Writes are atomic (temp file in the same directory, fsync, ``os.replace``) and
  serialised by a lock, so a power cut mid-save leaves the old file, not half a
  new one.
* Unknown fields -- at the top level and inside every entry -- survive a
  rewrite. An operator who adds a ``"notes"`` field by hand does not lose it the
  next time a calibration is saved.
* A file that exists but will not parse is *not* treated as empty and silently
  overwritten: the first write after a failed load moves it aside to
  ``lenses.json.corrupt-<timestamp>`` and says so.
* Every read checks the file's mtime/size and reloads if it changed, so the
  settings editor (or a hand edit) and the camera's controller see one another.

The module also holds the iris step table and the piecewise-linear focus-map
maths, because both are properties of an *entry* and both are needed by code
(the settings editor, the web GUI) that has no controller to ask.
"""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import re
import tempfile
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence, Union

from module.sensor_database import resolve_database_path as _resolve_repo_relative

logger = logging.getLogger(__name__)

DEFAULT_LENS_DATABASE_FILE = "resources/lenses.json"
SCHEMA = 1

# Entry fields this code knows. Anything else in an entry is preserved untouched.
KNOWN_ENTRY_FIELDS = ("name", "lens_id", "last_used", "aperture", "last_iris",
                      "capabilities", "focus")

# PLAN D20: what the lens has been shown to do. None = untested. A calibration
# that finds no focus position sets "focus" (and with it "autofocus") to False;
# the controller, the GUIs and the AF tuning layer gate on these.
CAPABILITY_NAMES = ("iris", "focus", "autofocus")

# Third stops, PLAN section 3. The lens takes f x 100, so these are the values
# CineMate offers, not the lens's own (unreadable, F7) stop positions.
IRIS_STEPS: tuple[float, ...] = (
    1.0, 1.1, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.5, 2.8, 3.2, 3.5, 4.0, 4.5, 5.0,
    5.6, 6.3, 7.1, 8.0, 9.0, 10.0, 11.0, 13.0, 14.0, 16.0, 18.0, 20.0, 22.0,
    25.0, 29.0, 32.0,
)


class LensDatabaseError(OSError):
    """The database could not be written (permissions, full disk, ...)."""


def resolve_database_path(path_value: Union[str, os.PathLike, None] = None) -> Path:
    """Repo-relative like ``sensor_database.resolve_database_path``; the only
    difference is the default file name."""
    return _resolve_repo_relative(str(path_value) if path_value else DEFAULT_LENS_DATABASE_FILE)


def slug(name: str) -> str:
    """A database key from a lens name: lowercase ASCII, runs of anything else
    become one ``-``.

    ``"Sigma 18-35 f/1.8"`` -> ``"sigma-18-35-f1-8"``. The ``/`` of an f-number
    is dropped rather than made a separator (so ``f/1.8`` reads ``f1-8``, the
    way the lens is written everywhere else); any other ``/`` is a separator
    (``24/105`` -> ``24-105``). An empty result becomes ``"lens"``.
    """
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"\bf/(?=\d)", "f", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "lens"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_capabilities() -> dict:
    """Nothing tested yet."""
    return {name: None for name in CAPABILITY_NAMES}


def capabilities_of(entry: Optional[dict]) -> dict:
    """An entry's capabilities with all three keys present (None = untested);
    a missing or malformed block reads as untested. Extra keys are kept."""
    stored = (entry or {}).get("capabilities")
    out = default_capabilities()
    if isinstance(stored, dict):
        out.update({k: v for k, v in stored.items()
                    if k not in CAPABILITY_NAMES or isinstance(v, bool) or v is None})
    return out


def capability(entry: Optional[dict], name: str) -> Optional[bool]:
    """True / False / None (untested) for one capability of an entry."""
    return capabilities_of(entry).get(name)


def _normalise_entry(entry: dict) -> dict:
    """A deep copy with every known field present (None when unset)."""
    out = copy.deepcopy(entry)
    out["name"] = str(out.get("name") or "").strip()
    out.setdefault("lens_id", None)
    out.setdefault("last_used", None)
    out.setdefault("aperture", None)
    out.setdefault("last_iris", None)
    out.setdefault("focus", None)
    out["capabilities"] = capabilities_of(out)
    return out


class LensDatabase:
    """``resources/lenses.json`` as a keyed collection of lens entries.

    Entries returned are copies; mutating one changes nothing until it is passed
    back through ``add`` / ``replace`` / ``update``. Everything is guarded by
    one re-entrant lock.
    """

    def __init__(self, path: Union[str, os.PathLike, None] = None, *,
                 now: Callable[[], datetime] = _utc_now):
        self.path = resolve_database_path(path)
        self._now = now
        self._lock = threading.RLock()
        self._doc: dict[str, Any] = {"schema": SCHEMA, "lenses": {}}
        self._stamp: Optional[tuple[int, int]] = None   # (mtime_ns, size) last loaded
        self._loaded = False
        self.load_error: Optional[str] = None
        self._corrupt_original = False

    # ── reading ────────────────────────────────────────────────────────────

    def load(self) -> dict[str, dict]:
        """(Re)read the file now. Missing file -> empty database; unreadable or
        unparsable file -> empty database, ``load_error`` set, original kept
        until the first write moves it aside. Returns ``entries()``."""
        with self._lock:
            self._read_file()
            return self.entries()

    def _stat_stamp(self) -> Optional[tuple[int, int]]:
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def _refresh(self) -> None:
        """Reload if the file changed since we last read or wrote it."""
        with self._lock:
            if not self._loaded or self._stat_stamp() != self._stamp:
                self._read_file()

    def _read_file(self) -> None:
        self._loaded = True
        self.load_error = None
        self._corrupt_original = False
        stamp = self._stat_stamp()
        self._stamp = stamp
        if stamp is None:
            self._doc = {"schema": SCHEMA, "lenses": {}}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("lenses", {}), dict):
                raise ValueError("expected an object with a 'lenses' object")
        except (OSError, ValueError) as exc:
            self.load_error = f"{self.path} is unreadable ({exc})"
            self._corrupt_original = True
            logger.warning("Lens database %s", self.load_error)
            self._doc = {"schema": SCHEMA, "lenses": {}}
            return
        data.setdefault("schema", SCHEMA)
        data["lenses"] = {
            str(k): v for k, v in data.get("lenses", {}).items() if isinstance(v, dict)
        }
        self._doc = data

    def entries(self) -> dict[str, dict]:
        """All entries, key -> entry, in file order (copies)."""
        with self._lock:
            self._refresh()
            return copy.deepcopy(self._doc["lenses"])

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            self._refresh()
            entry = self._doc["lenses"].get(key)
            return copy.deepcopy(entry) if entry is not None else None

    def matching(self, lens_id: Optional[int]) -> list[tuple[str, dict]]:
        """Entries recorded for this lens id, as ``(key, entry)`` in file order.

        The id is one byte, so collisions happen; the caller picks (D6b:
        ``most_recent`` for auto-selection, file order for cycling).
        """
        with self._lock:
            self._refresh()
            if lens_id is None:
                return []
            return [(k, copy.deepcopy(e)) for k, e in self._doc["lenses"].items()
                    if e.get("lens_id") == lens_id]

    def most_recent(self, lens_id: Optional[int]) -> Optional[str]:
        """Key of the entry for this id with the newest ``last_used`` (ISO
        timestamps sort as strings); the later entry wins a tie, and an entry
        never used loses to any that was."""
        best: Optional[tuple[str, int, str]] = None
        for index, (key, entry) in enumerate(self.matching(lens_id)):
            candidate = (str(entry.get("last_used") or ""), index, key)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
        return best[2] if best else None

    # ── writing ────────────────────────────────────────────────────────────

    @staticmethod
    def _unique_key(name: str, taken: dict) -> str:
        base = slug(name)
        if base not in taken:
            return base
        n = 2
        while f"{base}-{n}" in taken:
            n += 1
        return f"{base}-{n}"

    def _mutate(self, change: Callable[[dict], Any]) -> Any:
        """Apply ``change`` to a copy of the entries, write the file, and only
        then adopt the copy -- a failed write leaves memory and disk agreeing."""
        with self._lock:
            self._refresh()
            lenses = copy.deepcopy(self._doc["lenses"])
            result = change(lenses)
            self._write({**self._doc, "lenses": lenses})
            return result

    def add(self, entry: dict) -> str:
        """Store a new entry under ``slug(name)`` (``-2``, ``-3`` on a clash)
        and return the key. The name is required: it is the dropdown label."""
        if not str(entry.get("name") or "").strip():
            raise ValueError("a lens entry needs a name")

        def change(lenses: dict) -> str:
            key = self._unique_key(entry["name"], lenses)
            lenses[key] = _normalise_entry(entry)
            return key

        return self._mutate(change)

    def replace(self, key: str, entry: dict) -> str:
        """Save over an existing entry: the key stays, the name may change.

        Fields the incoming entry does not mention but the stored one carries
        (a hand-added ``"notes"``) are kept -- "preserves unknown fields" holds
        for a replace too. Raises ``KeyError`` if the key does not exist.
        """
        if not str(entry.get("name") or "").strip():
            raise ValueError("a lens entry needs a name")

        def change(lenses: dict) -> str:
            old = lenses.get(key)
            if old is None:
                raise KeyError(key)
            kept = {k: v for k, v in old.items() if k not in KNOWN_ENTRY_FIELDS}
            lenses[key] = _normalise_entry({**kept, **entry})
            return key

        return self._mutate(change)

    def update(self, key: str, **fields: Any) -> dict:
        """Merge fields into an entry (shallow) and return the result. Raises
        ``KeyError`` if the key does not exist."""
        def change(lenses: dict) -> dict:
            old = lenses.get(key)
            if old is None:
                raise KeyError(key)
            lenses[key] = _normalise_entry({**old, **fields})
            return copy.deepcopy(lenses[key])

        return self._mutate(change)

    def delete(self, key: str) -> bool:
        """Remove an entry; False if there was no such key."""
        def change(lenses: dict) -> bool:
            return lenses.pop(key, None) is not None

        with self._lock:
            self._refresh()
            if key not in self._doc["lenses"]:
                return False
            return self._mutate(change)

    def touch(self, key: str, when: Optional[datetime] = None) -> None:
        """Stamp ``last_used`` (UTC, second resolution). Raises ``KeyError``."""
        self.update(key, last_used=_iso(when or self._now()))

    def _write(self, doc: dict) -> None:
        """Atomic rewrite of the whole file, then adopt ``doc``. Caller holds
        the lock."""
        doc = {**doc, "schema": doc.get("schema", SCHEMA)}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            aside = None
            if self._corrupt_original and self.path.exists():
                aside = self.path.with_name(
                    f"{self.path.name}.corrupt-{self._now().strftime('%Y%m%dT%H%M%S')}"
                )
            fd, tmp_name = tempfile.mkstemp(
                prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(doc, handle, indent=2, ensure_ascii=False)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                if aside is not None:
                    os.replace(self.path, aside)
                    logger.warning("Lens database %s was unreadable; moved it to %s",
                                   self.path, aside)
                os.replace(tmp_name, self.path)
            except BaseException:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        except OSError as exc:
            raise LensDatabaseError(f"cannot write {self.path}: {exc}") from exc
        self._corrupt_original = False
        self.load_error = None
        self._stamp = self._stat_stamp()
        self._doc = doc


# ── Iris ────────────────────────────────────────────────────────────────────

def _aperture_range(entry: Optional[dict]) -> Optional[tuple[float, float]]:
    """(widest, narrowest) f-number from an entry's ``aperture``, or None when
    the entry has none (or it is malformed -- treated as 'not entered')."""
    aperture = (entry or {}).get("aperture")
    if not isinstance(aperture, dict):
        return None
    try:
        lo, hi = float(aperture["min"]), float(aperture["max"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(lo) and math.isfinite(hi)) or lo <= 0 or hi <= 0:
        return None
    return (lo, hi) if lo <= hi else (hi, lo)


def iris_steps_for(entry: Optional[dict]) -> list[float]:
    """The f-numbers CineMate offers for this lens, ascending.

    No aperture range entered -> the full third-stop table. Otherwise the table
    clamped to the range, with the range's own endpoints always included (a lens
    that stops down to f/22.6 offers 22.6, not just 22).
    """
    bounds = _aperture_range(entry)
    if bounds is None:
        return list(IRIS_STEPS)
    lo, hi = bounds
    eps = 1e-6
    steps = {round(s, 2) for s in IRIS_STEPS if lo - eps <= s <= hi + eps}
    steps.add(round(lo, 2))
    steps.add(round(hi, 2))
    return sorted(steps)


def clamp_iris(fnumber: float, entry: Optional[dict] = None) -> float:
    """Clamp an f-number to the entry's aperture range -- or, with none entered,
    to the full table's ends (1.0..32). Rounded to two decimals."""
    bounds = _aperture_range(entry) or (IRIS_STEPS[0], IRIS_STEPS[-1])
    return round(min(max(float(fnumber), bounds[0]), bounds[1]), 2)


def step_iris_value(current: Optional[float], count: int, entry: Optional[dict] = None) -> float:
    """``count`` third-stops from ``current`` along ``iris_steps_for(entry)``.

    Positive = a higher f-number (stopping down); the result is always on the
    table and inside the range. ``current`` need not be on the table: it is
    first snapped to the nearest step *in the direction of travel*, so one step
    up from f/2.9 is 3.2 and one step down is 2.8. ``None`` (nothing commanded
    yet) answers the widest step.
    """
    steps = iris_steps_for(entry)
    if current is None:
        return steps[0]
    current = float(current)
    eps = 1e-6
    if count > 0:
        later = [i for i, s in enumerate(steps) if s > current + eps]
        index = (later[0] + count - 1) if later else len(steps) - 1
    elif count < 0:
        earlier = [i for i, s in enumerate(steps) if s < current - eps]
        index = (earlier[-1] + count + 1) if earlier else 0
    else:
        return clamp_iris(current, entry)
    return steps[min(max(index, 0), len(steps) - 1)]


# ── Focus map (piecewise linear, libcamera's rpi.af "map") ─────────────────

def focus_map(entry_or_map: Any) -> Optional[list[tuple[float, float]]]:
    """An entry's focus ``map`` as ``[(dioptre, position), ...]`` (the flat
    ``[d0, p0, d1, p1, ...]`` of the file), or None if there is no usable one:
    fewer than two points, odd length, non-numbers, dioptres not strictly
    ascending, or positions not strictly descending."""
    if isinstance(entry_or_map, dict):
        focus = entry_or_map.get("focus")
        flat = focus.get("map") if isinstance(focus, dict) else None
    else:
        flat = entry_or_map
    if not isinstance(flat, (list, tuple)) or len(flat) < 4 or len(flat) % 2:
        return None
    try:
        pairs = [(float(flat[i]), float(flat[i + 1])) for i in range(0, len(flat), 2)]
    except (TypeError, ValueError):
        return None
    for (d0, p0), (d1, p1) in zip(pairs, pairs[1:]):
        if not (d1 > d0 and p1 < p0):
            return None
    if not all(math.isfinite(v) for pair in pairs for v in pair):
        return None
    return pairs


def is_calibrated(entry: Optional[dict]) -> bool:
    """True when the entry carries a usable focus map."""
    return focus_map(entry) is not None


def dioptre_to_position(entry_or_map: Any, dioptre: float) -> Optional[float]:
    """Motor position for a focus distance (in dioptres), by linear
    interpolation along the map. Clamped to the map's domain -- a dioptre
    beyond the near end reads as the nearest mapped position -- because the
    caller is a focus knob, not an extrapolation. None when there is no map."""
    pairs = focus_map(entry_or_map)
    if pairs is None:
        return None
    dioptre = min(max(float(dioptre), pairs[0][0]), pairs[-1][0])
    for (d0, p0), (d1, p1) in zip(pairs, pairs[1:]):
        if dioptre <= d1:
            return p0 + (dioptre - d0) * (p1 - p0) / (d1 - d0)
    return pairs[-1][1]


def position_to_dioptre(entry_or_map: Any, position: float) -> Optional[float]:
    """Focus distance (dioptres) for a motor position -- the inverse of
    ``dioptre_to_position``. Clamped to the mapped position range."""
    pairs = focus_map(entry_or_map)
    if pairs is None:
        return None
    # Positions descend as dioptres ascend.
    position = min(max(float(position), pairs[-1][1]), pairs[0][1])
    for (d0, p0), (d1, p1) in zip(pairs, pairs[1:]):
        if position >= p1:
            return d0 + (position - p0) * (d1 - d0) / (p1 - p0)
    return pairs[-1][0]


def format_aperture_range(entry: Optional[dict]) -> str:
    """``"1.8-22"`` for the LENS_APERTURE_RANGE key, or ``""`` when not entered."""
    bounds = _aperture_range(entry)
    if bounds is None:
        return ""
    return f"{bounds[0]:g}-{bounds[1]:g}"


def blank_entry(lens_id: Optional[int] = None, name: str = "") -> dict:
    """The working entry for a lens nobody has described yet."""
    return _normalise_entry({"name": name, "lens_id": lens_id})


def iter_names(entries: dict[str, dict]) -> Iterable[tuple[str, str]]:
    """(key, name) pairs for a dropdown, sorted by name."""
    return sorted(((k, str(e.get("name") or k)) for k, e in entries.items()),
                  key=lambda kv: kv[1].lower())


__all__: Sequence[str] = (
    "CAPABILITY_NAMES", "DEFAULT_LENS_DATABASE_FILE", "IRIS_STEPS", "LensDatabase",
    "LensDatabaseError", "blank_entry", "capabilities_of", "capability", "clamp_iris",
    "default_capabilities", "dioptre_to_position", "focus_map",
    "format_aperture_range", "iris_steps_for", "is_calibrated", "iter_names",
    "position_to_dioptre", "resolve_database_path", "slug", "step_iris_value",
)
