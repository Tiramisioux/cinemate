"""The libcamera autofocus tuning layer for the Pinefeat CEF168 adapter.

Standard library only, the way tuning_files.py and sensor_database.py are: it
is imported by cinepi_multi.py at launch, before cinepi-raw exists, and it
must work with no camera attached and no Redis running -- the tests (and
later the settings editor) call it on a desk. The lens database reader below
is deliberately tiny for the same reason; the full LensDatabase lives in
module/lens/ and is swapped in at integration.

Why a derived file at all (PLAN.md D9, F10, F11): aperture needs no tuning
file, but libcamera's AF does. libcamera only exposes AfMode -- and only
drives the lens -- when the active tuning carries an `rpi.af` block, and that
block holds the lens's calibration (focus range in dioptres, the dioptre ->
motor-position PWL map). The calibration belongs to the *lens*, not the
sensor, so it is not something to bake into resources/tuning_files/. Instead
the launch takes whichever base tuning is active (the stock file, or the
operator's tuning_file_override), strips any `rpi.af` it carries, inserts
ours, and writes the result to a cache directory. The file name carries a
hash of the base bytes and of our block, so:

  * switching the base tuning (a different override, an edited stock file, a
    rebuilt libcamera) yields a new file by itself -- nothing is "updated";
  * the same inputs reuse the same file, so a relaunch costs one read;
  * a stale derived file can never be picked up for a changed input.

Why it degrades instead of failing: tuning_files.py explains the chain
(FINDINGS.md S1) -- a tuning file libcamera cannot load fails camera
*registration*, not just the feature, and CineMate comes up with the GUI
alive and HDMI black. So nothing here raises into the launch. Every failure
returns (None, reason) and the caller launches with the base tuning, which is
a working camera without autofocus. The base is also re-checked with
tuning_json_problem(), for the platform's own "target" (bcm2835 on the Pi 4
family, pisp on the Pi 5 family), so a derived file can only ever be as valid
as the file it came from.

Why --autofocus-mode manual always accompanies a derived tuning (F11): with
`rpi.af` present libcamera advertises AfMode, and cinepi-raw with no
--autofocus-mode picks the *maximum* advertised mode -- continuous AF. A
cinema camera must not hunt the moment it starts. In manual mode libcamera
never moves the lens until LensPosition is set, so launching with the layer
changes nothing visible until the operator asks for AF (D15). The caller adds
the flag; this module only decides *whether* the layer applies.

Every key in the `rpi.af` block we emit is one libcamera's af.cpp reads
(Af::CfgParams::read, RangeDependentParams::read, SpeedDependentParams::read
under src/ipa/rpi/controller/rpi/). Keys the Pinefeat readme's example carries
that this libcamera does not read -- retrigger_ratio, retrigger_delay,
check_for_ir -- are left out on purpose rather than emitted and silently
ignored.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from module.sensor_database import resolve_database_path
from module.tuning_files import tuning_json_problem

DEFAULT_LENS_DATABASE_FILE = "resources/lenses.json"

# Cinemate's own cache, in the camera user's home like the rest of its
# per-user state. Overridable per call so tests never touch /home/pi.
DEFAULT_CACHE_DIR = Path("/home/pi/.cache/cinemate/tuning")

# Derived files kept per base stem. Each distinct (base, lens) pair ever
# launched leaves one; a small cap keeps the directory from growing without
# bound while still holding the lens the operator swapped away from a minute
# ago. The file just written is never pruned.
MAX_DERIVED_PER_BASE = 6

LENS_PROVENANCE_DRIVER = "v4l2-subdev"

# libcamera's Pwl::append() drops a point whose x is not more than eps beyond
# the previous one, and the PWL reader then returns nothing -- at which point
# libcamera silently substitutes a generic 0..15 dioptre map. For a Canon lens
# that is a map to the wrong positions. So the same eps is enforced here.
_PWL_EPS = 1e-6

# How far a requested dioptre range may stray outside the map's own span before
# the entry is called inconsistent. The calibrator rounds the range and the map
# separately, so an exact match is not expected; a real error is far larger.
_RANGE_SLACK = 0.01

# Pinefeat's published example speeds (cef168/readme.md, "Tuning"). PDAF is
# zeroed throughout: phase-detect pixels are tied to specific sensor-lens
# pairs and give nonsense with a Canon lens (readme, "Troubleshooting"), so
# autofocus here is contrast-detect only.
_DEFAULT_STEP_FRAMES = 4
_SPEED_NORMAL = {
    "step_coarse": 0.2,
    "step_fine": 0.05,
    "contrast_ratio": 0.75,
    "pdaf_gain": 0.0,
    "pdaf_squelch": 0.0,
    "max_slew": 2.0,
    "pdaf_frames": 0,
    "dropout_frames": 0,
}
_SKIP_FRAMES = 5


class LensTuningError(ValueError):
    """An entry or a base file cannot produce a usable tuning. str() is the
    reason, written to be read in a log line."""


def _is_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # an int too large for a float
        return False


def af_section(focus: dict) -> dict:
    """The contents of the `rpi.af` algorithm block for one lens.

    *focus* is an entry's `focus` section (PLAN.md section 3). Raises
    LensTuningError with the reason when the calibration cannot be trusted:
    libcamera would otherwise fall back to a generic map without a word.

    Emitted keys and where af.cpp reads them:
      ranges.normal.min / max / default   RangeDependentParams::read (80-82),
                                          reached from CfgParams::read (100-104)
      speeds.normal.step_coarse .. step_frames
                                          SpeedDependentParams::read (87-95),
                                          reached from CfgParams::read (122-126)
      conf_epsilon, conf_thresh, conf_clip, skip_frames
                                          CfgParams::read (136-139)
      map                                 CfgParams::read (141-142), parsed by
                                          libipa's Pwl getter (pwl.cpp 435-459)
    Only `normal` is emitted: macro, full and fast fall back to it in
    CfgParams::read (108, 112-116, 129), which is what the readme advises.
    """
    if not isinstance(focus, dict):
        raise LensTuningError("lens has no focus calibration")

    raw_map = focus.get("map")
    if not isinstance(raw_map, list) or len(raw_map) % 2 or len(raw_map) < 4:
        raise LensTuningError(
            "focus map must be a list of at least two [dioptre, position] pairs"
        )
    if not all(_is_number(v) for v in raw_map):
        raise LensTuningError("focus map holds a value that is not a finite number")

    dioptres = raw_map[0::2]
    positions = raw_map[1::2]
    if dioptres[0] < 0:
        raise LensTuningError("focus map starts at a negative dioptre")
    for earlier, later in zip(dioptres, dioptres[1:]):
        if not later > earlier + _PWL_EPS:
            raise LensTuningError("focus map dioptres are not strictly ascending")
    if any(p < 0 for p in positions):
        raise LensTuningError("focus map holds a negative lens position")

    # The entry carries its own range (the calibrator's min/max); a hand-built
    # entry may not, and the map's span is by definition the calibrated range.
    dmin = focus.get("dioptre_min", dioptres[0])
    dmax = focus.get("dioptre_max", dioptres[-1])
    if not (_is_number(dmin) and _is_number(dmax)):
        raise LensTuningError("dioptre_min / dioptre_max must be finite numbers")
    if dmin < 0 or not dmin < dmax:
        raise LensTuningError(f"dioptre range {dmin}..{dmax} is empty or negative")
    if dmin < dioptres[0] - _RANGE_SLACK or dmax > dioptres[-1] + _RANGE_SLACK:
        raise LensTuningError(
            f"dioptre range {dmin}..{dmax} lies outside the focus map "
            f"({dioptres[0]}..{dioptres[-1]})"
        )

    step_frames = focus.get("step_frames", _DEFAULT_STEP_FRAMES)
    if isinstance(step_frames, float) and step_frames.is_integer():
        step_frames = int(step_frames)
    if isinstance(step_frames, bool) or not isinstance(step_frames, int) or step_frames < 1:
        raise LensTuningError(f"step_frames {step_frames!r} must be a whole number of at least 1")

    speed = dict(_SPEED_NORMAL)
    speed["step_frames"] = step_frames
    return {
        "ranges": {"normal": {"min": dmin, "max": dmax, "default": dmax}},
        "speeds": {"normal": speed},
        "conf_epsilon": 0,
        "conf_thresh": 0,
        "conf_clip": 0,
        "skip_frames": _SKIP_FRAMES,
        "map": list(raw_map),
    }


def _insertion_index(algorithms: list) -> int:
    """Where `rpi.af` goes: before rpi.hdr when the file has one, otherwise
    after rpi.sharpen, otherwise at the end. That is where Pinefeat's readme
    places it and where libcamera's own imx708 tuning keeps it; the order is
    the order the controller runs the algorithms in."""
    names = [
        next(iter(item), None) if isinstance(item, dict) else None
        for item in algorithms
    ]
    if "rpi.hdr" in names:
        return names.index("rpi.hdr")
    if "rpi.sharpen" in names:
        return names.index("rpi.sharpen") + 1
    return len(algorithms)


def _write_atomic(path: Path, payload: bytes) -> None:
    """Temp file in the same directory, then rename: a reader (libcamera, or
    the other camera's launch) sees the old file or the whole new one, never
    half of it."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            logging.debug("could not remove temp file %s", tmp_name, exc_info=True)
        raise


def _prune(cache_dir: Path, stem: str, keep_path: Path, keep: int, base_path: Path) -> None:
    """Delete the oldest derived files for *stem* beyond *keep*. Best effort:
    a file that cannot be removed is left, and never blocks the launch."""
    pattern = re.compile(rf"^{re.escape(stem)}\.[0-9a-f]{{12}}\.json$")
    try:
        derived = [
            p for p in cache_dir.iterdir()
            if pattern.match(p.name) and p != keep_path and p != base_path
        ]
        derived.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
        for stale in derived[max(keep - 1, 0):]:
            stale.unlink()
    except OSError:
        logging.debug("pruning derived tuning files in %s failed", cache_dir, exc_info=True)


def _build(base_path, entry, cache_dir, expected_target, keep) -> Path:
    if base_path is None:
        raise LensTuningError("no base tuning file to derive from")
    base = Path(base_path)
    try:
        base_bytes = base.read_bytes()
    except FileNotFoundError:
        raise LensTuningError(f"base tuning not found: {base}") from None
    except OSError as exc:
        raise LensTuningError(f"base tuning unreadable: {exc}") from None
    try:
        data = json.loads(base_bytes.decode("utf-8"))
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError both
        raise LensTuningError(f"base tuning is not JSON: {exc}") from None
    problem = tuning_json_problem(data, expected_target)
    if problem:
        raise LensTuningError(f"base tuning rejected: {problem}")

    focus = entry.get("focus") if isinstance(entry, dict) else None
    section = af_section(focus)

    block = {"rpi.af": section}
    block_json = json.dumps(block, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(base_bytes + b"\0" + block_json.encode("utf-8")).hexdigest()[:12]

    algorithms = [
        item for item in data["algorithms"]
        if not (isinstance(item, dict) and "rpi.af" in item)
    ]
    algorithms.insert(_insertion_index(algorithms), block)
    derived = dict(data)  # shallow: keeps version/target and their order
    derived["algorithms"] = algorithms
    try:
        payload = (json.dumps(derived, indent=2, allow_nan=False) + "\n").encode("utf-8")
    except ValueError as exc:
        raise LensTuningError(f"base tuning cannot be re-serialised: {exc}") from None

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise LensTuningError(f"tuning cache unavailable ({cache_dir}): {exc}") from None
    target = cache_dir / f"{base.stem}.{digest}.json"

    try:
        reusable = target.is_file() and target.read_bytes() == payload
        if reusable:
            os.utime(target)  # recency decides what _prune keeps
        else:
            _write_atomic(target, payload)
    except OSError as exc:
        raise LensTuningError(f"cannot write {target}: {exc}") from None

    _prune(cache_dir, base.stem, target, keep, base)
    return target


def build_lens_tuning(
    base_path,
    entry: dict,
    cache_dir=None,
    *,
    expected_target: str = "pisp",
    keep: int = MAX_DERIVED_PER_BASE,
) -> tuple[Optional[Path], str]:
    """Derive the autofocus tuning for *entry* from the base tuning file.

    Returns (path, "ok") on success, otherwise (None, reason). Never raises:
    the launch must always be able to fall back to the base tuning.

    *base_path* is whichever tuning is active (None is a refusal, for a Pi 4
    with no vc4 stock file). *expected_target* is that platform's
    tuning_files.tuning_target(). The file is written to
    `<cache_dir>/<base-stem>.<hash12>.json`, the hash covering the base bytes
    and the rpi.af block; an identical file already there is reused, and older
    derived files for the same base stem beyond *keep* are removed.
    """
    try:
        path = _build(
            base_path, entry, Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR,
            expected_target, keep,
        )
    except LensTuningError as exc:
        return None, str(exc)
    except Exception as exc:
        # Nothing may propagate into the launch. The class name keeps the
        # reason diagnosable; the traceback goes to the debug log.
        logging.debug("derived tuning build failed unexpectedly", exc_info=True)
        return None, f"unexpected {type(exc).__name__}: {exc}"
    return path, "ok"


def load_lens_entry(database_value, key: str) -> tuple[Optional[dict], str]:
    """One entry of the lens database, or (None, reason).

    *database_value* is `lens_control.database_file` (None or "" means the
    default, resources/lenses.json), resolved repo-relative exactly like
    sensors.database_file. A missing file is simply an empty database -- the
    file is created on the first write -- so it is a reason, not an error.
    Strict JSON, per PLAN.md section 3; unknown fields are left alone.
    """
    path = resolve_database_path(database_value or DEFAULT_LENS_DATABASE_FILE)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, f"no lens database at {path}"
    except OSError as exc:
        return None, f"lens database unreadable ({path}): {exc}"
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return None, f"lens database is not JSON ({path}): {exc}"
    lenses = data.get("lenses") if isinstance(data, dict) else None
    if not isinstance(lenses, dict):
        return None, f'lens database {path} has no "lenses" object'
    entry = lenses.get(key)
    if not isinstance(entry, dict):
        return None, f'no lens "{key}" in {path}'
    return entry, "ok"


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    return "" if value is None else str(value).strip()


def autofocus_gate(
    *,
    autofocus: bool,
    lens_control: Any,
    lens_detected: Any,
    provenance: Any,
    lens_port: Any,
    lens_key: Any,
    camera_port: str,
    single_camera: bool = False,
) -> tuple[Optional[str], str]:
    """Whether the AF layer is wanted for the camera on *camera_port*.

    Returns (lens_key, "ok") when every condition holds, else (None, reason)
    naming the first that does not. The values are the raw ones from settings
    and Redis (strings, possibly None), so the caller does no parsing and the
    conditions are testable on their own:

      lens_control.autofocus  and  lens_control == 1  and  lens_detected == 1
      and  provenance == "v4l2-subdev"  and  lens_port == camera_port
      and  a lens_key is selected.

    Only the v4l2-subdev backend qualifies: libcamera drives the lens through
    the kernel driver's subdev, so a raw-I2C adapter has nothing for
    libcamera to move (PLAN.md D2/D3).

    *single_camera* waives the port comparison. CineMate forces every sensor
    on a Pi 4 to "cam0" (there is one CSI port in its model), so the lens
    port the backend reports cannot be compared against it; with one camera
    process the adapter is necessarily on that camera.
    """
    if not autofocus:
        return None, "lens_control.autofocus is off"
    if _text(lens_control) != "1":
        return None, "lens control is off"
    if _text(lens_detected) != "1":
        return None, "no adapter detected"
    prov = _text(provenance)
    if prov != LENS_PROVENANCE_DRIVER:
        return None, (
            f"the adapter is reached over {prov or 'nothing'}; "
            f"autofocus needs the cef168 driver ({LENS_PROVENANCE_DRIVER})"
        )
    port = _text(lens_port)
    if not single_camera and port != camera_port:
        return None, f"the adapter is on {port or 'no port'}, this camera is {camera_port}"
    key = _text(lens_key)
    if not key:
        return None, "no lens is selected"
    return key, "ok"
