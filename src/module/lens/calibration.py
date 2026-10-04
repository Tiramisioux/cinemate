"""Calibrating a lens: sweep it, check it really moved, build the focus section.

This is Pinefeat's ``calibrate.cpp`` done in Python, so CineMate needs no
``calibrate`` binary and can report *why* it failed. The board does the sweep
itself (one ``calibrate`` command); the host's job is to poll its state while
``calibrating`` is non-zero and collect (distance, position) pairs from the
frames the board reports while it sweeps.

Two things differ from the reference on purpose.

**It checks that the lens moved.** calibrate.cpp has no such check: on the
camera's first run (PLAN F13) the position stayed 0 for a ~100 ms "sweep" while
the distance read a constant 0.28 m, and the only output was "No PWL points for
output". The lens never moved -- almost certainly the AF/MF switch was left on
MF, which blocks the board's focus commands. ``build_focus_section`` turns that
signature into a reason that tells the operator what to do.

**It always produces a map when the lens moved.** Lenses with a distance encoder
vary ``focus_distance_min`` as the position changes, giving a multi-point
piecewise-linear map. Lenses without one report a constant distance (or 0), and
the reference gives up. Pinefeat's own troubleshooting guide (section 6) gives
the manual workaround -- ``[0.0, 0.97 * pos_max, 1 / MFD, pos_min]`` -- and that
is built automatically here (PLAN D8), using the minimum focus distance the
board reports, or one the operator supplies.

``build_focus_section`` is pure (samples in, dict out) so the failing real run
and every other shape can be unit-tested without a lens.
"""
from __future__ import annotations

import bisect
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, NamedTuple, Optional, Sequence

from module.lens.cef168 import (
    CALIBRATING_SWEEP,
    INFINITY_CM,
    Cef168Backend,
    Cef168Data,
    Cef168Error,
)

logger = logging.getLogger(__name__)

# Poll interval during the sweep. calibrate.cpp sleeps 500 microseconds; 20 ms is
# plenty (a sweep is seconds long, the board reports one distance per position
# step) and does not saturate a shared camera bus.
SAMPLE_INTERVAL_S = 0.02

# calibrate.cpp keeps polling for at least 100 ms even while `calibrating` still
# reads 0: the board takes a moment to enter the state after the command.
GRACE_S = 0.1

DEFAULT_TIMEOUT_S = 60.0

# Consecutive failed reads tolerated mid-sweep before giving up.
MAX_READ_FAILURES = 5

# "The lens moved": the positions seen while calibrating must span at least this
# many motor steps, for at least this long, AND at least this fraction of the
# range the board stored afterwards. Real lenses report ranges of hundreds to
# thousands of steps and sweeps of seconds; the F13 run had a span of 0.
MIN_POSITION_SPAN = 50
MIN_SWEEP_S = 0.2
MIN_OBSERVED_FRACTION = 0.5

# Distinct distances (after discarding points that run the wrong way) needed to
# call the distance encoder real and build a multi-point map.
MULTI_POINT_MIN_DISTINCT = 3

# Pinefeat troubleshooting section 6: stay off the very end of the range near
# infinity, where the lens bumps its limiter.
FALLBACK_INFINITY_FRACTION = 0.97

DIOPTRE_DECIMALS = 4

# calibrate.cpp: <300 ms -> 4, <350 ms -> 5, else 6 (DC-motor lenses need more
# frames to settle between focusing steps).
STEP_FRAMES_THRESHOLDS = ((300, 4), (350, 5))
STEP_FRAMES_SLOW = 6

AF_ADVICE = "Set the lens's AF/MF switch to AF and try again."

# PLAN D20 / G0.2: some lenses (the Sigma 18-35 f/1.8 Art, board lens id 112) run
# the sweep but never report a focus position -- position and range stay 0, the
# distance stays constant. That is a property of the lens, not of the switch, so
# it is reported separately and the controller records it in the entry.
NO_POSITION_REASON = (
    "The lens never reported a focus position: the board's focus range stayed at "
    "0..0 and the position never left 0. Focus and autofocus are marked "
    "unavailable for this lens (iris is unaffected). If the lens's AF/MF switch "
    "is on MF, set it to AF and calibrate again."
)


class Sample(NamedTuple):
    """One polled frame: seconds since the calibrate command, and the data."""
    t: float
    data: Cef168Data


class CalibrationResult:
    """The outcome of one calibration run.

    ``ok`` with ``focus`` set (the dict that goes into the lens entry), or not
    ok with ``reason`` written for the operator. ``stats`` carries the numbers
    the settings editor shows next to it.
    """

    def __init__(self, ok: bool, reason: str = "", focus: Optional[dict] = None,
                 samples: Optional[list[Sample]] = None, duration_s: float = 0.0,
                 stats: Optional[dict] = None, no_position_feedback: bool = False):
        self.ok = ok
        self.reason = reason
        self.focus = focus
        self.samples = samples if samples is not None else []
        self.duration_s = duration_s
        self.stats = stats if stats is not None else {}
        # True when the sweep ran but no focus position ever came back (D20).
        self.no_position_feedback = no_position_feedback

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"CalibrationResult(ok={self.ok}, reason={self.reason!r}, samples={len(self.samples)})"


def distance_cm_to_dioptre(distance_cm: int) -> Optional[float]:
    """Board distance (cm) -> dioptres. 0 means "no distance reported" (None);
    65535 means infinity (0.0 dioptres)."""
    if distance_cm <= 0:
        return None
    if distance_cm >= INFINITY_CM:
        return 0.0
    return 100.0 / distance_cm


def _step_frames(max_moving_time_ms: int) -> int:
    for limit, frames in STEP_FRAMES_THRESHOLDS:
        if max_moving_time_ms < limit:
            return frames
    return STEP_FRAMES_SLOW


def _longest_descending(points: list[tuple[float, int]]) -> list[tuple[float, int]]:
    """The longest subsequence of ``points`` (dioptre-ascending) whose positions
    strictly descend.

    A focus map must run one way: more dioptres (nearer) means a lower position.
    A single noisy reading would otherwise drop every good point after it under
    a greedy filter; this keeps the largest consistent set instead.
    """
    if not points:
        return []
    # Patience sorting on negated positions: strictly *increasing* in -position.
    tails: list[int] = []            # -position at the end of each pile
    tail_index: list[int] = []       # index into points of that element
    previous: list[Optional[int]] = [None] * len(points)
    for i, (_, position) in enumerate(points):
        neg = -position
        slot = bisect.bisect_left(tails, neg)
        if slot == len(tails):
            tails.append(neg)
            tail_index.append(i)
        else:
            tails[slot] = neg
            tail_index[slot] = i
        previous[i] = tail_index[slot - 1] if slot > 0 else None
    chain: list[tuple[float, int]] = []
    cursor: Optional[int] = tail_index[-1]
    while cursor is not None:
        chain.append(points[cursor])
        cursor = previous[cursor]
    chain.reverse()
    return chain


def _summarise(samples: Sequence[Sample]) -> dict:
    sweeping = [s for s in samples if s.data.calibrating != 0]
    stats: dict[str, Any] = {
        "samples": len(samples),
        "sweep_samples": len(sweeping),
        "max_moving_time_ms": max((s.data.moving_time for s in samples), default=0),
    }
    if sweeping:
        positions = [s.data.focus_position_cur for s in sweeping]
        stats["observed_position_min"] = min(positions)
        stats["observed_position_max"] = max(positions)
        stats["sweep_s"] = round(sweeping[-1].t - sweeping[0].t, 3)
    return stats


def lens_reports_no_position(samples: Sequence[Sample], final_data: Cef168Data) -> bool:
    """True when the board swept but no focus position ever came back: the
    position never moved off one value while calibrating AND the range the board
    stored afterwards is empty. A lens that is merely switched to MF usually
    still has a stored range from an earlier calibration, which keeps it out of
    this class (the operator is told to flip the switch instead)."""
    sweeping = [s for s in samples if s.data.calibrating != 0]
    if not sweeping:
        return False
    positions = [s.data.focus_position_cur for s in sweeping]
    return (max(positions) - min(positions) < MIN_POSITION_SPAN
            and final_data.position_span < MIN_POSITION_SPAN)


def build_focus_section(samples: Sequence[Sample], final_data: Cef168Data, *,
                        mfd_m: Optional[float] = None,
                        fallback_mfd_m: Optional[float] = None,
                        calibrated_at: Optional[str] = None,
                        ) -> tuple[Optional[dict], str]:
    """The ``focus`` section of a lens entry from a calibration's frames.

    Returns ``(focus, "")`` or ``(None, reason)``; the reason is written for the
    operator. ``samples`` are the frames read while calibrating, ``final_data``
    the last frame (it carries the position range the board stored). ``mfd_m``
    is a minimum focus distance in metres the operator *supplied*: it beats
    whatever the board reports. ``fallback_mfd_m`` (say, from an earlier
    calibration of the same lens) is used only when the board reports none.

    Pure: no I/O, no clock.
    """
    samples = list(samples)
    if not samples:
        return None, "No frames were read from the adapter during calibration."

    stats = _summarise(samples)
    if stats["sweep_samples"] == 0:
        return None, (
            "The adapter never started a calibration sweep (its calibrating flag "
            f"never went high). {AF_ADVICE}"
        )

    if lens_reports_no_position(samples, final_data):
        return None, NO_POSITION_REASON

    sweep_s = stats["sweep_s"]
    span = stats["observed_position_max"] - stats["observed_position_min"]
    if span < MIN_POSITION_SPAN or sweep_s < MIN_SWEEP_S:
        return None, (
            f"The lens did not move: its focus position changed by {span} steps "
            f"over a {int(round(sweep_s * 1000))} ms sweep. {AF_ADVICE}"
        )

    pos_min, pos_max = final_data.focus_position_min, final_data.focus_position_max
    board_span = pos_max - pos_min
    if board_span < MIN_POSITION_SPAN:
        return None, (
            f"The adapter reported no usable focus range after the sweep "
            f"(min {pos_min}, max {pos_max}). {AF_ADVICE}"
        )
    if span < MIN_OBSERVED_FRACTION * board_span:
        return None, (
            f"The lens moved only part of its range (saw {span} of {board_span} "
            f"steps). {AF_ADVICE}"
        )

    # (dioptre, lowest position seen at that dioptre) -- calibrate.cpp's update().
    lowest: dict[float, int] = {}
    for sample in samples:
        data = sample.data
        if data.calibrating != CALIBRATING_SWEEP or data.focus_distance_min == 0:
            continue
        dioptre = distance_cm_to_dioptre(data.focus_distance_min)
        if dioptre is None:
            continue
        key = round(dioptre, DIOPTRE_DECIMALS)
        position = data.focus_position_cur
        if key not in lowest or position < lowest[key]:
            lowest[key] = position
    consistent = _longest_descending(sorted(lowest.items()))

    if len(consistent) >= MULTI_POINT_MIN_DISTINCT:
        flat: list[float] = []
        for dioptre, position in consistent:
            flat.extend((dioptre, position))
        encoder = True
        nearest = consistent[-1][0]
        mfd = round(1.0 / nearest, 3) if nearest > 0 else None
    else:
        encoder = False
        mfd = mfd_m
        if mfd is None:
            mfd = _reported_mfd_m(samples, final_data)
        if mfd is None:
            mfd = fallback_mfd_m
        if mfd is None or mfd <= 0:
            return None, (
                "This lens reports no focus distance, so the focus map cannot be "
                "built. Enter its minimum focus distance (printed on the lens "
                "barrel) and calibrate again."
            )
        flat = [0.0, round(pos_max * FALLBACK_INFINITY_FRACTION),
                round(1.0 / mfd, 2), pos_min]

    return {
        "calibrated_at": calibrated_at,
        "position_min": pos_min,
        "position_max": pos_max,
        "mfd_m": round(float(mfd), 3) if mfd is not None else None,
        "distance_encoder": encoder,
        "map": flat,
        "dioptre_min": flat[0],
        "dioptre_max": flat[-2],
        "step_frames": _step_frames(max(stats["max_moving_time_ms"], final_data.moving_time)),
    }, ""


def _reported_mfd_m(samples: Sequence[Sample], final_data: Cef168Data) -> Optional[float]:
    """The nearest real distance the board reported, in metres -- the lens's
    minimum focus distance as stored in its ROM, which a lens with no distance
    encoder still reports (the F13 run read a constant 0.28 m)."""
    reported = [
        d.focus_distance_min
        for d in [s.data for s in samples] + [final_data]
        if 0 < d.focus_distance_min < INFINITY_CM
    ]
    return min(reported) / 100.0 if reported else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_calibration(backend: Cef168Backend, *,
                    clock: Callable[[], float] = time.monotonic,
                    sleep: Callable[[float], None] = time.sleep,
                    timeout_s: float = DEFAULT_TIMEOUT_S,
                    mfd_m: Optional[float] = None,
                    fallback_mfd_m: Optional[float] = None,
                    on_sample: Optional[Callable[[Sample], None]] = None,
                    should_stop: Optional[Callable[[], bool]] = None,
                    now: Callable[[], datetime] = _utc_now) -> CalibrationResult:
    """Send ``calibrate``, poll until the board is done, and build the result.

    Never raises for a bus problem -- a failure is a ``CalibrationResult`` with a
    reason, because the caller is a controller that has to keep running.
    ``on_sample`` sees every frame (the live-progress hook); ``should_stop``
    aborts early. Poll cadence and the 100 ms grace follow calibrate.cpp.
    """
    start = clock()
    samples: list[Sample] = []

    def finish(ok: bool, reason: str = "", focus: Optional[dict] = None,
               no_position_feedback: bool = False) -> CalibrationResult:
        return CalibrationResult(ok, reason, focus, samples, round(clock() - start, 3),
                                 _summarise(samples), no_position_feedback)

    try:
        backend.calibrate()
    except Cef168Error as exc:
        return finish(False, f"Could not start calibration: {exc}")

    failures = 0
    while True:
        sleep(SAMPLE_INTERVAL_S)
        elapsed = clock() - start
        if should_stop is not None and should_stop():
            return finish(False, "Calibration was stopped before it finished.")
        if elapsed > timeout_s:
            return finish(False, f"Calibration did not finish within {timeout_s:g} s.")
        try:
            data = backend.read_data()
        except Cef168Error as exc:
            failures += 1
            if failures > MAX_READ_FAILURES:
                return finish(False, f"Lost contact with the adapter during calibration: {exc}")
            continue
        failures = 0
        sample = Sample(elapsed, data)
        samples.append(sample)
        if on_sample is not None:
            try:
                on_sample(sample)
            except Exception:
                logger.debug("calibration progress callback failed", exc_info=True)
        if data.calibrating == 0 and elapsed >= GRACE_S:
            break

    focus, reason = build_focus_section(
        samples, samples[-1].data, mfd_m=mfd_m, fallback_mfd_m=fallback_mfd_m,
        calibrated_at=_iso(now()),
    )
    if focus is None:
        return finish(False, reason,
                      no_position_feedback=lens_reports_no_position(samples, samples[-1].data))
    return finish(True, "", focus)


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
