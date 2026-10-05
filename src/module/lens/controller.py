"""LensController: the one thread that owns the CEF168 adapter.

It detects the board, polls it, keeps the ``lens_*`` Redis keys current, picks
the right database entry for whatever lens is mounted, drives iris and focus on
request, runs calibrations, and -- when libcamera autofocus is in use -- routes
focus through libcamera instead of around it. Nothing here is wired into
``main.py`` or ``CinePiController``; that is the integration step (PLAN WP3).

How to read the rest of this file:

**Two locks, one order.** ``_io_lock`` serialises every call into the backend
(an I2C transaction or a V4L2 ioctl must not interleave with another);
``_lock`` guards the controller's own state. ``_lock`` may be taken while
holding ``_io_lock``, never the reverse, and Redis is only written with neither
held, so a Redis subscriber that calls back into the controller cannot deadlock
against it.

**The effective state is "toggle AND found" (D1).** The board is polled either
way (that is how the operator learns it is there, so they can switch the toggle
on), but nothing is ever *written* to the lens while the toggle is off, and the
self-test gesture is ignored.

**Iris is write-only (F3/F8).** The commanded value is the only record: it goes
to Redis ``iris`` and into the entry's ``last_iris`` (the one silent database
write, D6c), and is re-applied, clamped to the entry's range, whenever the lens
is detected again (D5). Always absolute writes, never relative ones.

**Calibration results land in the *working* entry, never straight in the file
(D6c).** The working entry is a copy of the selected database entry (blank for
a lens nobody has described). Calibrating or editing the aperture range marks it
``dirty``; ``save_lens`` is the only thing that writes it out.

**Capabilities gate the controls (D20).** An entry records what its lens has been
shown to do. A calibration that finds no focus position at all (the Sigma 18-35
f/1.8 Art never reports one) sets ``focus`` and ``autofocus`` to false in the
working entry; from then on focus and autofocus requests refuse with that reason,
the self-test gesture no longer starts calibrations for the lens (an explicit
``request_calibration`` still does), and iris is untouched. A later successful
calibration sets ``focus`` true again.

**One owner of the lens at a time (D16).** When libcamera autofocus is active
for the mounted lens (``af_available == lens_key``), focus requests are turned
from motor positions into dioptres and sent to cinepi-raw as ``lens_position`` --
never written to the board, because libcamera re-asserts its own lens setting.
Iris is never libcamera's, so it always goes direct. While AF is active the
self-test detector is suspended, since libcamera's moves are invisible to it.

Commands return ``(ok, message)``. The message is written for the operator and
is what a button or the CLI should show; failures are never exceptions. ``run()``
never raises either: an unexpected error is logged, shown as ``lens_state =
error`` and retried after dropping the backend.
"""
from __future__ import annotations

import contextlib
import copy
import json
import logging
import threading
import time
from typing import Any, Callable, Optional

from module.lens import cef168 as _cef168
from module.lens.calibration import (
    DEFAULT_TIMEOUT_S as CALIBRATION_TIMEOUT_S,
    CalibrationResult,
    Sample,
    run_calibration,
)
from module.lens.cef168 import NO_LENS_IDS, Cef168Backend, Cef168Data, Cef168Error
from module.lens.database import (
    LensDatabase,
    LensDatabaseError,
    blank_entry,
    capabilities_of,
    capability,
    clamp_iris,
    dioptre_to_position,
    format_aperture_range,
    iris_steps_for,
    is_calibrated,
    position_to_dioptre,
    step_iris_value,
)
from module.lens.selftest import EVENT_FINISHED, EVENT_STARTED, SelfTestDetector
from module.redis_controller import ParameterKey

logger = logging.getLogger(__name__)

# ── lens_state values (the contract in PLAN section 3) ─────────────────────
STATE_ABSENT = "absent"
STATE_NO_LENS = "no_lens"
STATE_UNKNOWN_LENS = "unknown_lens"
STATE_UNCALIBRATED = "uncalibrated"
STATE_READY = "ready"
STATE_SELFTEST = "selftest"
STATE_CALIBRATING = "calibrating"
STATE_ERROR = "error"

AF_MODES = ("manual", "auto", "continuous")

# ── tuning knobs ────────────────────────────────────────────────────────────
DEFAULT_POLL_HZ = 4.0        # D13: fast enough to see the self-test
DEFAULT_IDLE_POLL_HZ = 1.0   # adapter found but the toggle is off: just stay current
FAST_POLL_HZ = 20.0          # while part of the self-test signature has been seen
DETECT_INTERVAL_S = 5.0      # between probes while the adapter is absent

ERROR_AFTER_FAILURES = 3     # consecutive failed reads before lens_state = error
LOST_AFTER_FAILURES = 8      # ... before the adapter is declared gone (2 s at 4 Hz)

FOCUS_STEP_FRACTION = 0.01   # one step_focus(1) = 1 % of the motor range
RESTART_RETRY_S = 120.0      # do not ask for a camera restart more often than this
NOTICE_TTL_S = 60.0          # how long a one-off LENS_MESSAGE outranks the default
FOUND_NOTE_TTL_S = 120.0     # how long "[cam0 (i2c-0, from ...), v4l2-subdev]" trails the message
ERROR_LOG_INTERVAL_S = 30.0
PROGRESS_PUBLISH_S = 0.25

# Plausible f-number range for a hand-entered aperture range.
APERTURE_LIMITS = (0.5, 128.0)


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _fmt_iris(fnumber: float) -> str:
    return str(round(float(fnumber), 2))


def _default_factory(port: Optional[str], cameras: list[dict]):
    return _cef168.open_adapter(port, cameras=cameras)


class LensController(threading.Thread):
    """See the module docstring. Construct, ``start()``, ``stop()``, ``join(timeout)``.

    ``redis_controller`` needs ``get_value(key)`` and ``set_value(key, value, *,
    force=False)`` -- the cinemate ``RedisController``, or a fake. Everything
    else that touches the world is injectable so the tests need no hardware:
    ``backend_factory(port, cameras) -> (backend | None, reason)``, ``database``,
    ``clock`` (monotonic seconds) and ``sleep``.
    """

    def __init__(self, redis_controller, *,
                 database: Optional[LensDatabase] = None,
                 backend_factory: Optional[Callable[..., tuple]] = None,
                 cameras_provider: Optional[Callable[[], list]] = None,
                 port: Optional[str] = None,
                 poll_hz: float = DEFAULT_POLL_HZ,
                 idle_poll_hz: float = DEFAULT_IDLE_POLL_HZ,
                 fast_poll_hz: float = FAST_POLL_HZ,
                 detect_interval_s: float = DETECT_INTERVAL_S,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Optional[Callable[[float], None]] = None,
                 request_camera_restart: Optional[Callable[[str], None]] = None,
                 autofocus_enabled: Any = False,
                 calibrate_on_selftest: Any = True,
                 focus_step_fraction: float = FOCUS_STEP_FRACTION,
                 calibration_timeout_s: float = CALIBRATION_TIMEOUT_S,
                 detector: Optional[SelfTestDetector] = None):
        super().__init__(name="LensController", daemon=True)
        self._redis = redis_controller
        self._db = database if database is not None else LensDatabase()
        self._factory = backend_factory or _default_factory
        self._cameras_provider = cameras_provider or self._cameras_from_redis
        self._port = port
        self._poll_hz = poll_hz
        self._idle_poll_hz = idle_poll_hz
        self._fast_poll_hz = fast_poll_hz
        self._detect_interval_s = detect_interval_s
        self._clock = clock
        self._sleep_override = sleep
        self._sleep = sleep or time.sleep
        self._request_restart = request_camera_restart
        self._autofocus_enabled_source = (autofocus_enabled if callable(autofocus_enabled)
                                          else (lambda value=bool(autofocus_enabled): value))
        # ``lens_control.calibrate_on_selftest``: whether the AF/MF x3 gesture
        # starts a calibration when the board's self-test ends (a callable is
        # asked each time, like autofocus_enabled).
        self._calibrate_on_selftest_source = (
            calibrate_on_selftest if callable(calibrate_on_selftest)
            else (lambda value=calibrate_on_selftest: value))
        self._focus_step_fraction = focus_step_fraction
        self._calibration_timeout_s = calibration_timeout_s
        self._detector = detector or SelfTestDetector()

        self._lock = threading.RLock()       # controller state
        self._io_lock = threading.RLock()    # every call into the backend
        self._stop_event = threading.Event()
        self._wake = threading.Event()

        # adapter
        self._backend: Optional[Cef168Backend] = None
        self._found = False
        self._absent_reason = "not probed yet"
        self._last_detect_t: Optional[float] = None
        self._fail_count = 0
        self._data: Optional[Cef168Data] = None
        self._error_text: Optional[str] = None

        # lens and entry
        self._mounted_id: Optional[int] = None
        self._selected_key: Optional[str] = None
        self._working: Optional[dict] = None
        self._dirty = False
        self._need_iris_apply = False
        self._iris: Optional[float] = None

        # operator toggle
        self._enabled = _truthy(self._redis_get(ParameterKey.LENS_CONTROL))
        self._was_enabled = self._enabled

        # calibration
        self._calibration_job: Optional[dict] = None
        self._calibrating = False
        self._progress: Optional[dict] = None
        self._progress_published_t = float("-inf")
        self._last_calibration: Optional[CalibrationResult] = None

        # one-off message, and the "where was the adapter found" note that trails it
        self._notice: Optional[tuple[str, float]] = None
        self._found_note: Optional[tuple[str, float]] = None

        # autofocus / camera restart
        self._restart_pending: Optional[str] = None
        self._restart_sent: Optional[tuple[tuple, float]] = None
        self._af_seen: Optional[tuple[str, str]] = None

        self._last_error_log_t = float("-inf")

    # ── Redis helpers ──────────────────────────────────────────────────────

    def _redis_get(self, key: ParameterKey) -> Any:
        try:
            return self._redis.get_value(key.value)
        except Exception:
            logger.debug("redis get %s failed", key.value, exc_info=True)
            return None

    def _redis_set(self, key: ParameterKey, value: Any, *, force: bool = False) -> None:
        try:
            if force:
                self._redis.set_value(key.value, value, force=True)
            else:
                self._redis.set_value(key.value, value)
        except Exception:
            logger.debug("redis set %s failed", key.value, exc_info=True)

    def _cameras_from_redis(self) -> list[dict]:
        raw = self._redis_get(ParameterKey.CAMERAS)
        try:
            cams = json.loads(raw) if raw else []
        except (TypeError, ValueError):
            return []
        return [c for c in cams if isinstance(c, dict)] if isinstance(cams, list) else []

    def _recording(self) -> bool:
        return (_truthy(self._redis_get(ParameterKey.REC))
                or _truthy(self._redis_get(ParameterKey.IS_RECORDING)))

    # ── public read side ───────────────────────────────────────────────────

    def effective(self) -> bool:
        """Toggle on AND adapter found (D1)."""
        with self._lock:
            return self._found and self._enabled

    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def working_entry(self) -> dict:
        """A copy of the working entry, plus ``dirty`` and ``key``. Blank (and
        not dirty) when no lens is mounted."""
        with self._lock:
            entry = copy.deepcopy(self._working) if self._working is not None else blank_entry()
            entry["dirty"] = self._dirty
            entry["key"] = self._selected_key
            return entry

    def entries(self) -> dict[str, dict]:
        """The saved lens entries (key -> entry), for the lens dropdowns. The
        database re-reads its file only when it changed on disk, so this is
        cheap to call once a second."""
        return self._db.entries()

    def status(self) -> dict:
        """A JSON-friendly snapshot for the GUIs, the CLI and the settings editor."""
        with self._lock:
            backend = self._backend
            data = self._data
            working = copy.deepcopy(self._working) if self._working is not None else None
            last = self._last_calibration
            return {
                "enabled": self._enabled,
                "found": self._found,
                "effective": self._found and self._enabled,
                "state": self._derive_state(),
                "message": self._current_message(),
                "absent_reason": "" if self._found else self._absent_reason,
                "provenance": backend.provenance if backend else "",
                "port": backend.port if backend else "",
                "bus": backend.bus if backend else None,
                "bus_source": backend.bus_source if backend else "",
                "bus_description": (_cef168.describe_bus(backend.bus, backend.bus_source)
                                    if backend else ""),
                "lens_id": self._lens_id_published(),
                "lens_key": self._selected_key or "",
                "lens_name": (working or {}).get("name", "") if self._selected_key else "",
                "working": self.working_entry(),
                "dirty": self._dirty,
                "aperture_range": format_aperture_range(working),
                "capabilities": capabilities_of(working),
                "iris": self._iris,
                "iris_steps": iris_steps_for(working),
                "focus_position": data.focus_position_cur if data and self._lens_present() else None,
                "focus_range": ([data.focus_position_min, data.focus_position_max]
                                if data and data.range_valid else None),
                "board": ({
                    "lens_id": data.lens_id, "moving": data.moving,
                    "calibrating": data.calibrating, "moving_time": data.moving_time,
                    "focus_position_min": data.focus_position_min,
                    "focus_position_max": data.focus_position_max,
                    "focus_position_cur": data.focus_position_cur,
                    "focus_distance_min": data.focus_distance_min,
                    "focus_distance_max": data.focus_distance_max,
                } if data else None),
                "calibration": {
                    "running": self._calibrating or self._calibration_job is not None,
                    "progress": copy.deepcopy(self._progress),
                    "last": ({
                        "ok": last.ok, "reason": last.reason, "stats": dict(last.stats),
                        "duration_s": last.duration_s, "focus": copy.deepcopy(last.focus),
                    } if last else None),
                },
                "selftest": {"running": self._detector.running, "armed": self._detector.armed},
                "af": self._af_status(),
                "poll_hz": 1.0 / self._interval() if self._interval() > 0 else None,
            }

    def _af_status(self) -> dict:
        return {
            "enabled": bool(self._autofocus_enabled()),
            "active": self._af_active_unlocked(),
            "mode": str(self._redis_get(ParameterKey.AF_MODE) or "manual"),
            "state": str(self._redis_get(ParameterKey.AF_STATE) or ""),
            "available_for": str(self._redis_get(ParameterKey.AF_AVAILABLE) or ""),
            "restart_pending": self._restart_pending,
        }

    # ── state derivation ───────────────────────────────────────────────────

    def _lens_present(self) -> bool:
        return self._found and self._mounted_id is not None and self._mounted_id not in NO_LENS_IDS

    def _lens_id_published(self) -> Optional[int]:
        return self._mounted_id if self._found and self._lens_present() else None

    def _derive_state(self) -> str:
        if self._error_text:
            return STATE_ERROR
        if not self._found:
            return STATE_ABSENT
        if self._calibrating or self._calibration_job is not None:
            return STATE_CALIBRATING
        if self._detector.running:
            return STATE_SELFTEST
        if not self._lens_present():
            return STATE_NO_LENS
        if self._selected_key is None:
            return STATE_UNKNOWN_LENS
        if not is_calibrated(self._working) and capability(self._working, "focus") is not False:
            return STATE_UNCALIBRATED
        return STATE_READY

    def _default_message(self, state: str) -> str:
        name = (self._working or {}).get("name") or ""
        if state == STATE_ABSENT:
            return f"Lens adapter not found: {self._absent_reason}"
        if state == STATE_ERROR:
            return self._error_text or "Lens adapter error"
        if state == STATE_CALIBRATING:
            return "Calibrating the lens"
        if state == STATE_SELFTEST:
            return "Lens self-test detected; calibration starts when it finishes"
        if state == STATE_NO_LENS:
            return "Adapter found; no lens mounted"
        if state == STATE_UNKNOWN_LENS:
            return (f"Lens id {self._mounted_id} is not in the lens database: calibrate it "
                    "and save it under a name")
        if state == STATE_UNCALIBRATED:
            return f"{name}: not calibrated"
        # ready
        extra = "" if (self._working or {}).get("aperture") else " (aperture range not set)"
        if capability(self._working, "focus") is False:
            extra += " (iris only: this lens reports no focus position)"
        return f"{name} ready{extra}"

    def _current_message(self) -> str:
        state = self._derive_state()
        now = self._clock()
        notice = self._notice
        text = notice[0] if notice is not None and now < notice[1] else self._default_message(state)
        # Where the adapter was found and how that bus was worked out (PLAN D2:
        # the derivation travels with the answer) trails the message for a while.
        note = self._found_note
        if note is not None and now < note[1] and state not in (STATE_ABSENT, STATE_ERROR):
            text = f"{text} [{note[0]}]"
        return text

    def _say(self, text: str, ttl: float = NOTICE_TTL_S) -> None:
        with self._lock:
            self._notice = (text, self._clock() + ttl)

    # ── publishing ─────────────────────────────────────────────────────────

    def _publish_all(self) -> None:
        with self._lock:
            lens_present = self._lens_present()
            backend = self._backend if self._found else None
            data = self._data
            updates = {
                ParameterKey.LENS_DETECTED: "1" if self._found else "0",
                ParameterKey.LENS_PROVENANCE: backend.provenance if backend else "",
                ParameterKey.LENS_PORT: backend.port if backend else "",
                ParameterKey.LENS_ID: ("" if self._lens_id_published() is None
                                       else str(self._lens_id_published())),
                ParameterKey.LENS_KEY: self._selected_key or "",
                ParameterKey.LENS_NAME: ((self._working or {}).get("name", "")
                                         if self._selected_key else ""),
                ParameterKey.LENS_STATE: self._derive_state(),
                ParameterKey.LENS_MESSAGE: self._current_message(),
                ParameterKey.LENS_APERTURE_RANGE: (format_aperture_range(self._working)
                                                   if lens_present else ""),
                ParameterKey.FOCUS_POSITION: (str(data.focus_position_cur)
                                              if data and lens_present else ""),
            }
        for key, value in updates.items():
            self._redis_set(key, value)

    # ── thread plumbing ────────────────────────────────────────────────────

    def stop(self) -> None:
        """Ask the loop to end. Callers ``join(timeout=...)`` afterwards."""
        self._stop_event.set()
        self._wake.set()

    def run(self) -> None:
        logger.info("Lens controller started")
        try:
            while not self._stop_event.is_set():
                try:
                    self.poll_once()
                except Exception as exc:
                    self._on_unexpected_error(exc)
                self._pace(self._interval())
        finally:
            self._shutdown()

    def _interval(self) -> float:
        with self._lock:
            if not self._found:
                return min(self._detect_interval_s, 1.0 / self._idle_poll_hz)
            if self._calibration_job is not None:
                return 0.0          # a sweep is waiting: do not sleep before it
            if self._detector.armed:
                return 1.0 / self._fast_poll_hz
            if self._enabled:
                return 1.0 / self._poll_hz
            return 1.0 / self._idle_poll_hz

    def _pace(self, seconds: float) -> None:
        if seconds <= 0:
            return
        if self._sleep_override is not None:
            self._sleep_override(seconds)
        else:
            self._wake.wait(seconds)
            self._wake.clear()

    def _on_unexpected_error(self, exc: Exception) -> None:
        now = self._clock()
        if now - self._last_error_log_t >= ERROR_LOG_INTERVAL_S:
            self._last_error_log_t = now
            logger.exception("Lens controller iteration failed; dropping the adapter and retrying")
        else:
            logger.debug("Lens controller iteration failed again", exc_info=True)
        self._drop_backend(f"internal error: {exc}", now, error=f"Internal error: {exc}")
        self._publish_all()
        self._pace(1.0)

    def _shutdown(self) -> None:
        self._drop_backend("lens controller stopped", self._clock())
        try:
            self._publish_all()
        except Exception:
            logger.debug("final lens publish failed", exc_info=True)
        logger.info("Lens controller stopped")

    # ── one poll ───────────────────────────────────────────────────────────

    def poll_once(self) -> None:
        """One iteration of the loop: detect or read, react, publish. Public so
        tests (and nothing else) can drive the controller without a thread."""
        now = self._clock()
        self._sync_enabled()
        if self._backend is None and not self._try_detect(now):
            self._publish_all()
            return

        job = self._take_calibration_job()
        if job is not None:
            self._run_calibration_job(job)
            self._publish_all()
            return

        data = self._read(now)
        if data is not None:
            self._ingest(now, data)
        self._maintain(now)
        self._publish_all()

    def _sync_enabled(self) -> None:
        enabled = _truthy(self._redis_get(ParameterKey.LENS_CONTROL))
        with self._lock:
            self._enabled = enabled
            # Switching the toggle on re-applies the iris. Finding the adapter
            # or a lens does that on its own (_try_detect, _on_lens_detected),
            # so only the toggle's own edge is handled here -- otherwise the
            # iris would be written twice on the first poll.
            if enabled and not self._was_enabled and self._found:
                self._need_iris_apply = True
            self._was_enabled = enabled

    # ── detection ──────────────────────────────────────────────────────────

    def _try_detect(self, now: float) -> bool:
        with self._lock:
            if (self._last_detect_t is not None
                    and now - self._last_detect_t < self._detect_interval_s):
                return False
            self._last_detect_t = now
            self._error_text = None
        try:
            with self._io_lock:
                backend, reason = self._factory(self._port, self._cameras_provider())
        except Exception as exc:
            backend, reason = None, f"detection failed: {exc}"
            logger.exception("Lens adapter detection raised")
        if backend is None:
            with self._lock:
                changed = reason != self._absent_reason
                self._absent_reason = reason
                self._found = False
            if changed:
                # Said once per distinct reason: an adapter that is simply not
                # fitted must not fill the log every few seconds.
                logger.info("Lens adapter not found: %s", reason)
            return False
        with self._lock:
            self._backend = backend
            self._found = True
            self._fail_count = 0
            self._error_text = None
            self._absent_reason = ""
            if self._mounted_id is not None:
                self._need_iris_apply = True
        logger.info("Lens adapter found on %s", backend.describe())
        with self._lock:
            self._found_note = (f"adapter on {backend.describe()}", now + FOUND_NOTE_TTL_S)
        return True

    def _drop_backend(self, reason: str, now: float, *, error: Optional[str] = None) -> None:
        with self._io_lock:
            backend, self._backend = self._backend, None
            if backend is not None:
                try:
                    backend.close()
                except Exception:
                    logger.debug("closing the lens backend failed", exc_info=True)
        with self._lock:
            self._found = False
            self._absent_reason = reason
            self._error_text = error
            self._data = None
            self._last_detect_t = now
            self._calibration_job = None
            self._calibrating = False
            self._detector.reset()

    def _read(self, now: float) -> Optional[Cef168Data]:
        try:
            with self._io_lock:
                backend = self._backend
                if backend is None:
                    return None
                data = backend.read_data()
        except Cef168Error as exc:
            with self._lock:
                self._fail_count += 1
                count = self._fail_count
                if count == ERROR_AFTER_FAILURES:
                    self._error_text = f"The adapter is not answering reliably: {exc}"
            if count >= LOST_AFTER_FAILURES:
                logger.warning("Lens adapter stopped answering: %s", exc)
                self._drop_backend(f"the adapter stopped answering: {exc}", now)
            else:
                logger.debug("Lens read failed (%d): %s", count, exc)
            return None
        with self._lock:
            self._fail_count = 0
            self._error_text = None
        return data

    def _ingest(self, now: float, data: Cef168Data) -> None:
        with self._lock:
            self._data = data
            present = data.lens_id not in NO_LENS_IDS
            if present and self._mounted_id != data.lens_id:
                self._on_lens_detected(data.lens_id)
            elif not present and self._mounted_id is not None:
                self._on_lens_removed()

        effective = self.effective()
        if not (effective and present):
            self._detector.reset()
            return

        busy = self._calibrating or self._calibration_job is not None
        if not busy:
            af_active = self._af_active_unlocked()
            if af_active != self._detector.suspended:
                if af_active:
                    self._detector.reset()
                self._detector.set_suspended(af_active, now)
            for event in self._detector.feed(now, data):
                self._on_selftest_event(event)

        with self._lock:
            apply_iris = self._need_iris_apply and not (
                self._calibrating or self._calibration_job is not None)
        if apply_iris:
            self._apply_iris_on_detect(now)

    def _on_lens_detected(self, lens_id: int) -> None:
        """A different lens (or the first one) is mounted. Caller holds ``_lock``.

        D6b: one entry with this id selects itself; several select the one used
        most recently; none leaves a blank working entry (``unknown_lens``) for
        the operator to describe and save.
        """
        self._mounted_id = lens_id
        self._detector.reset()
        self._need_iris_apply = True
        matches = self._db.matching(lens_id)
        key: Optional[str] = None
        if len(matches) == 1:
            key = matches[0][0]
        elif matches:
            key = self._db.most_recent(lens_id)
        if self._dirty:
            logger.warning("Discarding unsaved lens changes: a different lens was mounted")
        if key is not None:
            self._select_locked(key, self._db.get(key))
            logger.info("Lens id %d detected: selected '%s'", lens_id, key)
        else:
            self._selected_key = None
            self._working = blank_entry(lens_id)
            self._dirty = False
            logger.info("Lens id %d detected: not in the database", lens_id)

    def _on_lens_removed(self) -> None:
        """The lens was taken off. Caller holds ``_lock``."""
        if self._dirty:
            logger.warning("Discarding unsaved lens changes: the lens was removed")
        self._mounted_id = None
        self._selected_key = None
        self._working = None
        self._dirty = False
        self._iris = None
        self._detector.reset()
        logger.info("Lens removed")

    def _select_locked(self, key: str, entry: Optional[dict]) -> None:
        """Make ``entry`` the working entry. Caller holds ``_lock``."""
        if entry is None:
            return
        self._selected_key = key
        self._working = entry
        self._dirty = False
        try:
            self._db.touch(key)
        except (KeyError, LensDatabaseError) as exc:
            logger.warning("Could not stamp last_used on '%s': %s", key, exc)

    # ── per-poll upkeep ────────────────────────────────────────────────────

    def _maintain(self, now: float) -> None:
        with self._lock:
            key = self._selected_key
            if key is not None and self._db.get(key) is None:
                # Deleted behind our back (the settings editor). Keep what we
                # have as an unsaved entry rather than lose a calibration.
                self._selected_key = None
                self._dirty = True
                logger.warning("Lens entry '%s' was deleted; keeping it as unsaved", key)
        self._check_af_restart(now)

    # ── self-test → calibration ────────────────────────────────────────────

    def _on_selftest_event(self, event: str) -> None:
        if event == EVENT_STARTED:
            logger.info("Lens self-test gesture detected")
            self._say("Self-test detected; calibration starts when it finishes")
        elif event == EVENT_FINISHED:
            with self._lock:
                no_focus = capability(self._working, "focus") is False
            if no_focus:
                # A lens already shown to report no focus position would fail
                # the same way again; do not sweep it on every gesture.
                self._say("Self-test seen; focus is marked unavailable for this lens, so no "
                          "calibration was started. Use Calibrate to try again.")
                logger.info("Lens self-test finished; focus is unavailable for this lens")
            elif not self._calibrate_on_selftest():
                self._say("Self-test seen; calibration on self-test is switched off "
                          "(lens_control.calibrate_on_selftest). Use Calibrate.")
                logger.info("Lens self-test finished; calibrate_on_selftest is off")
            elif self._recording():
                self._say("Self-test seen while recording; not calibrating")
                logger.info("Lens self-test finished while recording; not calibrating")
            elif self._af_active_unlocked():
                self._say("Self-test seen while autofocus is active; not calibrating")
            else:
                logger.info("Lens self-test finished; starting a calibration")
                self._queue_calibration(source="selftest")

    def _queue_calibration(self, *, source: str, mfd_m: Optional[float] = None) -> None:
        with self._lock:
            if self._calibrating or self._calibration_job is not None:
                return
            focus = (self._working or {}).get("focus")
            previous = focus.get("mfd_m") if isinstance(focus, dict) else None
            self._calibration_job = {"mfd_m": mfd_m, "fallback_mfd_m": previous,
                                     "source": source}
        self._wake.set()

    def _take_calibration_job(self) -> Optional[dict]:
        with self._lock:
            return self._calibration_job

    def _run_calibration_job(self, job: dict) -> None:
        if self._backend is None:
            with self._lock:
                self._calibration_job = None
            return
        if self._af_active_unlocked():
            self._af_hold()      # libcamera must not fight the sweep
        with self._lock:
            self._calibrating = True
            self._progress = {"elapsed_s": 0.0, "samples": 0, "position": None,
                              "source": job.get("source", "")}
            self._progress_published_t = float("-inf")
        self._say("Calibrating the lens", ttl=CALIBRATION_TIMEOUT_S + 30)
        self._publish_all()
        logger.info("Lens calibration started (%s)", job.get("source", "?"))

        try:
            with self._io_lock:
                backend = self._backend
                if backend is None:
                    result = CalibrationResult(
                        False, "The adapter went away before calibration could start.")
                else:
                    result = run_calibration(
                        backend, clock=self._clock, sleep=self._sleep,
                        timeout_s=self._calibration_timeout_s, mfd_m=job.get("mfd_m"),
                        fallback_mfd_m=job.get("fallback_mfd_m"),
                        on_sample=self._on_calibration_sample,
                        should_stop=self._stop_event.is_set,
                    )
        finally:
            with self._lock:
                self._calibrating = False
                self._calibration_job = None
                self._progress = None
            self._detector.reset()
            self._detector.note_host_command(self._clock())

        with self._lock:
            self._last_calibration = result
            if self._working is not None:
                caps = capabilities_of(self._working)
                if result.ok:
                    self._working["focus"] = result.focus
                    caps["focus"] = True
                    if caps.get("autofocus") is False:
                        caps["autofocus"] = None     # it was only false because focus was
                    self._dirty = True
                elif result.no_position_feedback:
                    caps["focus"] = False
                    caps["autofocus"] = False
                    self._dirty = True
                self._working["capabilities"] = caps
        if result.ok:
            focus = result.focus or {}
            points = len(focus.get("map", [])) // 2
            kind = "distance-encoder map" if focus.get("distance_encoder") else "2-point fallback map"
            text = (f"Calibrated: {kind}, {points} points, focus range "
                    f"{focus.get('position_min')}..{focus.get('position_max')}. "
                    "Not saved yet: save the lens to keep it.")
            logger.info("Lens calibration finished: %s", text)
            self._say(text, ttl=300.0)
        elif result.no_position_feedback:
            logger.warning("Lens calibration found no focus position: marking focus unavailable")
            self._say(f"{result.reason} Save the lens to keep this.", ttl=300.0)
        else:
            logger.warning("Lens calibration failed: %s", result.reason)
            self._say(result.reason, ttl=300.0)

    def _on_calibration_sample(self, sample: Sample) -> None:
        data = sample.data
        with self._lock:
            self._data = data
            self._progress = {
                "elapsed_s": round(sample.t, 2),
                "samples": (self._progress or {}).get("samples", 0) + 1,
                "position": data.focus_position_cur,
                "position_min": data.focus_position_min,
                "position_max": data.focus_position_max,
                "distance_m": (None if data.focus_distance_min == 0
                               else round(data.focus_distance_min / 100.0, 2)),
                "calibrating": data.calibrating,
                "source": (self._progress or {}).get("source", ""),
            }
        now = self._clock()
        if now - self._progress_published_t >= PROGRESS_PUBLISH_S:
            self._progress_published_t = now
            self._redis_set(ParameterKey.FOCUS_POSITION, str(data.focus_position_cur))
            self._redis_set(ParameterKey.LENS_MESSAGE,
                            f"Calibrating: position {data.focus_position_cur}, {sample.t:.1f} s")

    # ── guards ─────────────────────────────────────────────────────────────

    def _refusal(self, *, need_lens: bool = True, allow_busy: bool = False) -> Optional[str]:
        """Why a hardware command cannot run right now, or None."""
        with self._lock:
            if not self._found:
                return f"Lens adapter not found ({self._absent_reason})"
            if not self._enabled:
                return "Lens control is off"
            if need_lens and not self._lens_present():
                return "No lens is mounted"
            if not allow_busy and (self._calibrating or self._calibration_job is not None):
                return "The lens is calibrating"
            if not allow_busy and self._detector.running:
                return "The lens is running its self-test"
        return None

    def _focus_refusal(self) -> Optional[str]:
        """``_refusal`` plus the D20 gate: a lens shown to report no focus
        position gets no focus commands, with the reason."""
        reason = self._refusal()
        if reason:
            return reason
        with self._lock:
            working = self._working
        if capability(working, "focus") is False:
            return ("Focus is not available for this lens: it never reported a focus "
                    "position when it was calibrated")
        return None

    def _iris_refusal(self) -> Optional[str]:
        """``_refusal`` plus the D20 gate for iris: a lens whose entry says its
        iris does not engage gets no iris commands, with the reason."""
        reason = self._refusal()
        if reason:
            return reason
        with self._lock:
            working = self._working
        if capability(working, "iris") is False:
            return "The iris is not available for this lens: its entry says iris commands do nothing"
        return None

    def _command_failed(self, what: str, exc: Exception) -> tuple[bool, str]:
        message = f"{what} failed: {exc}"
        logger.warning("Lens: %s", message)
        with self._lock:
            self._error_text = message
        return False, message

    # ── operator toggle ────────────────────────────────────────────────────

    def set_enabled(self, enabled: bool) -> tuple[bool, str]:
        """The operator toggle (D1). Switching on is refused unless the adapter
        is found; switching off always works."""
        if enabled:
            with self._lock:
                if not self._found:
                    return False, (f"Lens control stays off: the adapter was not found "
                                   f"({self._absent_reason})")
        self._redis_set(ParameterKey.LENS_CONTROL, "1" if enabled else "0")
        with self._lock:
            self._enabled = bool(enabled)
        self._wake.set()
        return True, "Lens control on" if enabled else "Lens control off"

    # ── iris ───────────────────────────────────────────────────────────────

    def set_iris(self, fnumber: float) -> tuple[bool, str]:
        """Command an absolute f-number, clamped to the entry's aperture range."""
        reason = self._iris_refusal()
        if reason:
            return False, reason
        try:
            requested = float(fnumber)
        except (TypeError, ValueError):
            return False, f"{fnumber!r} is not an f-number"
        with self._lock:
            value = clamp_iris(requested, self._working)
        try:
            with self._io_lock:
                backend = self._backend          # stable while the I/O lock is held
                refusal = self._refusal()        # state may have moved while we waited
                if backend is None or refusal is not None:
                    return False, refusal or "Lens adapter not found"
                backend.set_iris(value)
        except (Cef168Error, ValueError) as exc:
            return self._command_failed("Setting the iris", exc)
        self._after_iris(value)
        note = "" if abs(value - requested) < 0.005 else f" (clamped from f/{_fmt_iris(requested)})"
        return True, f"f/{_fmt_iris(value)}{note}"

    def _after_iris(self, value: float) -> None:
        now = self._clock()
        with self._lock:
            self._iris = value
            key = self._selected_key
            if self._working is not None:
                # Not a "dirty" change: last_iris is operational state, not
                # something the operator has to decide to keep (D6c).
                self._working["last_iris"] = value
        self._detector.note_host_command(now)
        self._redis_set(ParameterKey.IRIS, _fmt_iris(value))
        if key is not None:
            try:
                self._db.update(key, last_iris=value)
            except (KeyError, LensDatabaseError) as exc:
                logger.warning("Could not store last_iris for '%s': %s", key, exc)

    def step_iris(self, count: int = 1) -> tuple[bool, str]:
        """``count`` third-stops along the entry's iris table; positive stops
        down (a higher f-number)."""
        with self._lock:
            current = self._iris
            working = self._working
        if current is None:
            current = self._parse_float(self._redis_get(ParameterKey.IRIS))
        if current is None and working is not None:
            current = self._parse_float(working.get("last_iris"))
        return self.set_iris(step_iris_value(current, int(count), working))

    def _apply_iris_on_detect(self, now: float) -> None:
        """D5: put the stored iris back on the lens, clamped to its range."""
        with self._lock:
            entry = self._working
            self._need_iris_apply = False
        if entry is None:
            return
        target = self._parse_float(entry.get("last_iris"))
        if target is None:
            target = self._parse_float(self._redis_get(ParameterKey.IRIS))
        if target is None:
            return
        value = clamp_iris(target, entry)
        try:
            with self._io_lock:
                backend = self._backend
                if backend is None:
                    return
                backend.set_iris(value)
        except (Cef168Error, ValueError) as exc:
            self._command_failed("Restoring the iris", exc)
            return
        with self._lock:
            self._iris = value
        self._detector.note_host_command(now)
        self._redis_set(ParameterKey.IRIS, _fmt_iris(value))
        logger.info("Lens iris restored to f/%s", _fmt_iris(value))

    @staticmethod
    def _parse_float(value: Any) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number == number else None

    # ── focus ──────────────────────────────────────────────────────────────

    def set_focus(self, position: float) -> tuple[bool, str]:
        """Focus to a motor position. With autofocus active the position is
        converted to dioptres and handed to libcamera (D16); otherwise it goes
        straight to the board, clamped to the range the board reports."""
        reason = self._focus_refusal()
        if reason:
            return False, reason
        try:
            target = float(position)
        except (TypeError, ValueError):
            return False, f"{position!r} is not a focus position"
        if self._af_active_unlocked():
            return self._set_focus_via_libcamera(target)
        with self._lock:
            data = self._data
        low, high = (data.focus_position_min, data.focus_position_max) \
            if data is not None and data.range_valid else (0, 0xFFFF)
        value = int(round(min(max(target, low), high)))
        try:
            with self._io_lock:
                backend = self._backend
                refusal = self._refusal()
                if backend is None or refusal is not None:
                    return False, refusal or "Lens adapter not found"
                backend.set_focus(value)
        except (Cef168Error, ValueError) as exc:
            return self._command_failed("Setting the focus", exc)
        self._detector.note_host_command(self._clock())
        return True, f"focus {value}"

    def step_focus(self, count: int = 1) -> tuple[bool, str]:
        """Move focus ``count`` steps (1 step = 1 % of the motor range); positive
        is towards infinity."""
        reason = self._focus_refusal()
        if reason:
            return False, reason
        with self._lock:
            data = self._data
            working = self._working
        if data is None:
            return False, "No focus reading from the lens yet"
        if data.range_valid:
            span = data.position_span
        else:
            focus = (working or {}).get("focus") or {}
            span = (focus.get("position_max", 0) or 0) - (focus.get("position_min", 0) or 0) or 100
        step = max(1, int(round(span * self._focus_step_fraction)))
        if self._af_active_unlocked():
            dioptre = (self._parse_float(self._redis_get(ParameterKey.LENS_POSITION_ACTUAL))
                       if self._redis_get(ParameterKey.LENS_POSITION_ACTUAL) not in (None, "")
                       else self._parse_float(self._redis_get(ParameterKey.LENS_POSITION)))
            current = (dioptre_to_position(self._af_entry(), dioptre)
                       if dioptre is not None else None)
            if current is None:
                current = data.focus_position_cur
        else:
            current = data.focus_position_cur
        return self.set_focus(current + int(count) * step)

    def _af_entry(self) -> Optional[dict]:
        """The entry whose focus map libcamera is using: the *saved* one, since
        the tuning was derived from the file. An unsaved recalibration in the
        working entry must not change how positions convert to dioptres until
        it has been saved and the camera restarted onto it."""
        with self._lock:
            key = self._selected_key
            working = self._working
        saved = self._db.get(key) if key else None
        return saved if saved is not None else working

    def _set_focus_via_libcamera(self, position: float) -> tuple[bool, str]:
        entry = self._af_entry()
        dioptre = position_to_dioptre(entry, position)
        if dioptre is None:
            return False, "Autofocus is active but this lens has no focus map"
        if str(self._redis_get(ParameterKey.AF_MODE) or "manual") != "manual":
            # A manual focus request takes the lens back from autofocus, the
            # way turning the ring does on a camera.
            self._redis_set(ParameterKey.AF_MODE, "manual")
        self._redis_set(ParameterKey.LENS_POSITION, f"{dioptre:.4f}")
        return True, f"focus {dioptre:.2f} dioptres (via autofocus)"

    # ── autofocus (D15-D17) ────────────────────────────────────────────────

    def af_active(self) -> bool:
        """True when cinepi-raw was launched with an AF tuning for the mounted
        lens's entry (``af_available == lens_key``) and lens control is on."""
        with self._lock:
            return self._af_active_unlocked()

    def _af_active_unlocked(self) -> bool:
        key = self._selected_key
        if not key or not (self._found and self._enabled):
            return False
        # Autofocus is paused (operator decision 2026-10-04): with the setting
        # off, which is the default, nothing below -- focus routing, detector
        # suspension, the af_* commands, the restart request -- does anything,
        # whatever af_available says.
        if not self._autofocus_enabled():
            return False
        return str(self._redis_get(ParameterKey.AF_AVAILABLE) or "") == key

    def _af_unavailable(self) -> str:
        """Why autofocus cannot be used, in the order an operator would fix it."""
        with self._lock:
            backend = self._backend
            key = self._selected_key
        if not self._autofocus_enabled():
            return "Autofocus is switched off in the settings"
        reason = self._af_capability_refusal()
        if reason:
            return reason
        if backend is not None and backend.provenance != "v4l2-subdev":
            return "Autofocus needs the cef168 kernel driver, which is not bound"
        if key is None:
            return "Save the lens under a name first"
        saved = self._db.get(key)
        if saved is None or not is_calibrated(saved):
            return "Calibrate the lens and save it first"
        return "The camera has not been restarted with an autofocus tuning for this lens yet"

    def _af_capability_refusal(self) -> Optional[str]:
        """D20: autofocus needs focus feedback, and can be ruled out on its own."""
        with self._lock:
            working = self._working
        if capability(working, "focus") is False:
            return "Autofocus needs a focus position, which this lens does not report"
        if capability(working, "autofocus") is False:
            return "Autofocus is marked unavailable for this lens"
        return None

    def _af_gate(self) -> Optional[str]:
        reason = self._refusal() or self._af_capability_refusal()
        if reason:
            return reason
        if not self.af_active():
            return f"Autofocus is not available: {self._af_unavailable()}"
        return None

    def af_once(self) -> tuple[bool, str]:
        """One-shot autofocus: libcamera scans once, then holds the position."""
        reason = self._af_gate()
        if reason:
            return False, reason
        self._redis_set(ParameterKey.AF_MODE, "auto")
        self._redis_set(ParameterKey.AF_TRIGGER, "start", force=True)
        return True, "Autofocus started"

    def set_af_mode(self, mode: str) -> tuple[bool, str]:
        """``manual`` / ``auto`` / ``continuous``. Manual holds the lens where
        it is."""
        text = str(mode).strip().lower()
        if text not in AF_MODES:
            return False, f"Unknown autofocus mode {mode!r} (use {', '.join(AF_MODES)})"
        reason = self._af_gate()
        if reason:
            return False, reason
        if text == "manual":
            self._af_hold()
        else:
            self._redis_set(ParameterKey.AF_MODE, text)
        return True, f"Autofocus mode {text}"

    def af_cancel(self) -> tuple[bool, str]:
        """Stop a scan and hold the lens where it is."""
        reason = self._af_gate()
        if reason:
            return False, reason
        self._redis_set(ParameterKey.AF_TRIGGER, "cancel", force=True)
        self._af_hold()
        return True, "Autofocus cancelled"

    def _af_hold(self) -> None:
        """Manual mode, with the position libcamera last reported, so the lens
        stays put instead of jumping to a stale setpoint."""
        self._redis_set(ParameterKey.AF_MODE, "manual")
        actual = self._parse_float(self._redis_get(ParameterKey.LENS_POSITION_ACTUAL))
        if actual is not None:
            self._redis_set(ParameterKey.LENS_POSITION, f"{actual:.4f}")

    def _calibrate_on_selftest(self) -> bool:
        try:
            value = self._calibrate_on_selftest_source()
        except Exception:
            logger.debug("calibrate_on_selftest setting unavailable", exc_info=True)
            return True
        return value if isinstance(value, bool) else _truthy(value)

    def _autofocus_enabled(self) -> bool:
        """The ``lens_control.autofocus`` setting. It may be a callable owned by
        someone else, so a failure in it must not take the poll loop down."""
        try:
            return bool(self._autofocus_enabled_source())
        except Exception:
            logger.debug("autofocus setting unavailable", exc_info=True)
            return False

    def set_autofocus_enabled(self, enabled: bool) -> None:
        """Follow the ``lens_control.autofocus`` setting if it changes live."""
        self._autofocus_enabled_source = lambda value=bool(enabled): value

    def _af_restart_reason(self) -> Optional[str]:
        """Why the running cinepi-raw has the wrong (or no) AF tuning for the
        mounted lens, or None if it is fine or cannot be fixed by a restart."""
        with self._lock:
            backend = self._backend
            key = self._selected_key
            usable = self._found and self._enabled and self._lens_present()
        if not (usable and key and backend is not None
                and backend.provenance == "v4l2-subdev"):
            return None
        saved = self._db.get(key)
        if saved is None or not is_calibrated(saved):
            return None     # a tuning is derived from the *saved* entry
        if capability(saved, "focus") is False or capability(saved, "autofocus") is False:
            return None     # D20: no tuning will be built for this lens
        available = str(self._redis_get(ParameterKey.AF_AVAILABLE) or "")
        if available != key:
            return (f"the autofocus tuning is not built for '{key}' "
                    f"(camera launched with '{available or 'none'}')")
        fingerprint = json.dumps(saved.get("focus"), sort_keys=True)
        with self._lock:
            if self._af_seen is None or self._af_seen[0] != key:
                self._af_seen = (key, fingerprint)
                return None
            if self._af_seen[1] != fingerprint:
                return f"the saved focus calibration for '{key}' changed since the camera started"
        return None

    def _check_af_restart(self, now: float) -> None:
        callback = self._request_restart
        reason = (self._af_restart_reason()
                  if callback is not None and self._autofocus_enabled() else None)
        with self._lock:
            self._restart_pending = reason
            if reason is None:
                self._restart_sent = None
                return
            key = self._selected_key
        if self._recording():
            return      # deferred: a restart mid-take would end the take
        signature = (key, str(self._redis_get(ParameterKey.AF_AVAILABLE) or ""), reason)
        with self._lock:
            sent = self._restart_sent
            if sent is not None and sent[0] == signature and now - sent[1] < RESTART_RETRY_S:
                return
            self._restart_sent = (signature, now)
        logger.info("Requesting a camera restart: %s", reason)
        try:
            callback(reason)
        except Exception:
            logger.exception("The camera restart request failed")
            return
        saved = self._db.get(key) if key else None
        if saved is not None:
            with self._lock:
                self._af_seen = (key, json.dumps(saved.get("focus"), sort_keys=True))

    # ── calibration (operator-initiated) ───────────────────────────────────

    def request_calibration(self, mfd_m: Optional[float] = None) -> tuple[bool, str]:
        """Queue a calibration sweep. Refused while recording (a sweep moves the
        focus ring through its whole range), and while lens control is not
        effective. ``mfd_m`` is the lens's minimum focus distance in metres, for
        a lens that reports none. The result lands in the working entry."""
        if self._recording():
            return False, "Cannot calibrate while recording"
        reason = self._refusal()
        if reason:
            return False, reason
        self._queue_calibration(source="request", mfd_m=mfd_m)
        self._publish_all()     # lens_state reads "calibrating" now, not a poll from now
        return True, "Calibration started"

    # ── lens selection and saving ──────────────────────────────────────────

    def select_lens(self, key: Optional[str] = None) -> tuple[bool, str]:
        """Select a database entry for the mounted lens (D6b). With no key, cycle
        through the entries recorded for the mounted lens id. Selecting an entry
        for a different id is allowed, with a warning. Unsaved changes to the
        working entry are discarded."""
        with self._lock:
            if self._working is None:
                return False, "No lens is mounted"
            mounted = self._mounted_id
            current = self._selected_key
        if key is None:
            matches = [k for k, _ in self._db.matching(mounted)]
            if not matches:
                return False, f"No saved lens matches lens id {mounted}"
            key = (matches[(matches.index(current) + 1) % len(matches)]
                   if current in matches else matches[0])
        entry = self._db.get(key)
        if entry is None:
            return False, f"No saved lens '{key}'"
        with self._lock:
            discarded = self._dirty
            self._select_locked(key, entry)
            self._need_iris_apply = True
        message = f"Selected {entry.get('name') or key}"
        if entry.get("lens_id") != mounted:
            message += (f" (warning: it was saved for lens id {entry.get('lens_id')}, "
                        f"the mounted lens is id {mounted})")
        if discarded:
            message += "; unsaved changes were discarded"
        self._say(message)
        self._publish_all()
        return True, message

    def save_lens(self, name: str, key: Optional[str] = None) -> tuple[bool, str]:
        """Write the working entry to the database. ``key=None`` saves it as a
        new entry named ``name`` (D6c "Save as new"); a key saves over that
        entry, renaming it to ``name`` ("Save over")."""
        name = str(name or "").strip()
        if not name:
            return False, "A lens needs a name"
        with self._lock:
            if self._working is None:
                return False, "No lens is mounted"
            entry = copy.deepcopy(self._working)
        entry["name"] = name
        try:
            if key is None:
                saved_key = self._db.add(entry)
            else:
                if self._db.get(key) is None:
                    return False, f"No saved lens '{key}' to save over"
                saved_key = self._db.replace(key, entry)
            with contextlib.suppress(KeyError):
                self._db.touch(saved_key)
        except (LensDatabaseError, ValueError, KeyError) as exc:
            return False, f"Could not save the lens: {exc}"
        stored = self._db.get(saved_key)
        with self._lock:
            self._selected_key = saved_key
            self._working = stored if stored is not None else entry
            self._dirty = False
        message = f"Saved as '{name}'" if key is None else f"Saved over '{key}' as '{name}'"
        self._say(message)
        self._publish_all()
        return True, message

    def set_aperture_range(self, minimum: Optional[float], maximum: Optional[float]
                           ) -> tuple[bool, str]:
        """Enter the lens's widest and narrowest f-number (the board cannot read
        them, F7). Changes the working entry and marks it dirty. ``None, None``
        clears the range."""
        with self._lock:
            if self._working is None:
                return False, "No lens is mounted"
        if minimum is None and maximum is None:
            aperture = None
        else:
            lo, hi = self._parse_float(minimum), self._parse_float(maximum)
            if lo is None or hi is None:
                return False, "Enter both the widest and the narrowest f-number"
            low_limit, high_limit = APERTURE_LIMITS
            if not (low_limit <= lo <= hi <= high_limit):
                return False, (f"The aperture range must satisfy {low_limit:g} <= widest <= "
                               f"narrowest <= {high_limit:g}")
            aperture = {"min": lo, "max": hi, "source": "manual"}
        with self._lock:
            self._working["aperture"] = aperture
            self._dirty = True
        text = format_aperture_range(self._working)
        self._publish_all()
        return True, f"Aperture range {text}" if text else "Aperture range cleared"
