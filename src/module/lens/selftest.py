"""Spotting the board's own self-test gesture in the polled frames.

Toggling the lens's AF/MF switch three times within 15 seconds makes the control
board run its self-test: focus min -> infinity -> min in four steps, aperture
closed -> open (F12). CineMate uses that gesture as the "calibrate this lens"
button (PLAN D7a). The detector's whole difficulty is the opposite question:
what it must *not* mistake for the gesture, because the reaction is a calibration
sweep that moves the focus ring through its whole range.

The dangerous false positive is a hand on the focus ring. On many Canon lenses
turning the ring changes the position the board reports, so "any unsolicited
movement" would start a sweep mid-shot. The signature therefore has three parts:

* **The board must be driving the motor.** Only samples with ``moving`` set count.
  A hand turning the ring moves the position without the board's motor flag.
  (Assumption, to be settled by hardware gate G0.3; ``REQUIRE_MOTOR_FLAG``.)
* **A specific shape.** A lens whose position range is meaningful must be seen
  touching near ``position_min``, then near ``position_max``, then near
  ``position_min`` again, in that order, inside ``PATTERN_WINDOW_S``. A lens whose
  positions are meaningless (never calibrated: range 0..0 or nonsense) cannot be
  judged by position, so it needs several *separate* bursts of motor activity
  instead.
* **Nothing the host did.** Movement within ``HOST_COMMAND_GRACE_S`` of a command
  CineMate sent is its own, and also wipes any half-seen gesture (an operator
  using the controls is not doing the gesture). While libcamera autofocus is
  active the detector is suspended entirely: libcamera drives the lens through
  the kernel driver, where CineMate cannot see the commands.

When the signature completes it emits ``selftest_started``; when the lens has
then been quiet for ``SETTLE_S`` (the aperture half of the test is still running
for a few seconds) it emits ``selftest_finished`` -- always paired -- and that is
the moment to calibrate, with the lens idle.

Every threshold below is a named constant. They are finalised after hardware
gate G0.3 (poll ``data`` at 20 Hz while the operator flips AF/MF three times,
then pulls the focus ring by hand), which is the first time anyone sees what the
board actually reports during the test. Until then they are the conservative
reading of the readme.
"""
from __future__ import annotations

from typing import Optional

from module.lens.cef168 import Cef168Data

EVENT_STARTED = "selftest_started"
EVENT_FINISHED = "selftest_finished"

# The whole gesture (min -> max -> min, or the bursts) must fit in this window.
PATTERN_WINDOW_S = 15.0

# How close to an end of the range counts as "touching" it, as a fraction of the
# range. Generous on purpose: the test moves in four coarse steps and the poll
# is 4 Hz when idle.
NEAR_FRACTION = 0.15

# The board's stored range must span at least this many steps to be believed.
MIN_RANGE_SPAN = 50

# Movement this soon after a host command is the host's.
HOST_COMMAND_GRACE_S = 2.0

# Quiet time after the signature completes before the test counts as finished.
SETTLE_S = 1.5

# Give up waiting for quiet after this long and call it finished anyway.
FINISH_TIMEOUT_S = 20.0

# Count only samples where the board says its motor is active. See the module
# docstring; G0.3 decides whether this stays.
REQUIRE_MOTOR_FLAG = True

# Separate motor-activity bursts needed to recognise the test on a lens whose
# positions mean nothing. The test is four focus steps, one close and four
# opens: at least nine bursts at the board, of which a 4 Hz poll still sees
# several.
UNCALIBRATED_MIN_BURSTS = 4


class SelfTestDetector:
    """Feed it ``(t, Cef168Data)`` samples; it answers with events.

    ``t`` is any monotonic clock in seconds (the controller's). Not thread-safe:
    the controller calls it only from its own thread. Thresholds default to the
    module constants and can be overridden per instance (tests do).
    """

    def __init__(self, *, window_s: float = PATTERN_WINDOW_S,
                 near_fraction: float = NEAR_FRACTION,
                 min_range_span: int = MIN_RANGE_SPAN,
                 grace_s: float = HOST_COMMAND_GRACE_S,
                 settle_s: float = SETTLE_S,
                 finish_timeout_s: float = FINISH_TIMEOUT_S,
                 require_motor_flag: bool = REQUIRE_MOTOR_FLAG,
                 uncalibrated_min_bursts: int = UNCALIBRATED_MIN_BURSTS):
        self.window_s = window_s
        self.near_fraction = near_fraction
        self.min_range_span = min_range_span
        self.grace_s = grace_s
        self.settle_s = settle_s
        self.finish_timeout_s = finish_timeout_s
        self.require_motor_flag = require_motor_flag
        self.uncalibrated_min_bursts = uncalibrated_min_bursts
        self._suspended = False
        self.reset()

    # ── lifecycle ──────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Forget everything, including a confirmed-but-unfinished test. Called
        on a lens change and when autofocus takes over."""
        self._prev: Optional[Cef168Data] = None
        self._grace_until = float("-inf")
        self._running = False
        self._confirmed_t = 0.0
        self._last_active_t = 0.0
        self._clear_progress()

    def _clear_progress(self) -> None:
        self._stage = 0               # calibrated-lens signature: 0..3
        self._stage_t0 = 0.0
        self._bursts: list[float] = []   # uncalibrated-lens signature
        self._in_burst = False
        self._mode_calibrated: Optional[bool] = None

    @property
    def running(self) -> bool:
        """True from ``selftest_started`` until ``selftest_finished``."""
        return self._running

    @property
    def armed(self) -> bool:
        """True while part of the signature has been seen -- the moment to poll
        faster, so the rest is not missed between 4 Hz samples."""
        return self._running or self._stage > 0 or bool(self._bursts)

    @property
    def suspended(self) -> bool:
        return self._suspended

    def set_suspended(self, suspended: bool, t: float = 0.0) -> None:
        """Suspend while libcamera autofocus owns the lens. Coming back, the
        next ``grace_s`` is ignored: AF may still be settling the motor."""
        if suspended == self._suspended:
            return
        self._suspended = suspended
        self._clear_progress()
        self._running = False
        if not suspended:
            self._grace_until = max(self._grace_until, t + self.grace_s)

    def note_host_command(self, t: float) -> None:
        """CineMate just commanded the board: the movement that follows is its
        own, and any half-seen gesture is void."""
        self._grace_until = max(self._grace_until, t + self.grace_s)
        if not self._running:
            self._clear_progress()

    # ── the signature ──────────────────────────────────────────────────────

    def feed(self, t: float, data: Cef168Data) -> list[str]:
        """One polled frame. Returns the events it completes (usually none)."""
        events: list[str] = []
        prev, self._prev = self._prev, data
        if self._suspended:
            return events
        if data.calibrating != 0:
            # A calibration is running (ours, or someone's): not a self-test.
            if not self._running:
                self._clear_progress()
            return events

        in_grace = t < self._grace_until
        active = self._is_active(data, prev)

        if self._running:
            if not in_grace and active:
                self._last_active_t = t
            quiet = t - self._last_active_t >= self.settle_s
            timed_out = t - self._confirmed_t >= self.finish_timeout_s
            if quiet or timed_out:
                self._running = False
                self._clear_progress()
                events.append(EVENT_FINISHED)
            return events

        if in_grace:
            self._clear_progress()
            return events

        # Stale progress expires.
        started = self._stage_t0 if self._stage else (self._bursts[0] if self._bursts else None)
        if started is not None and t - started > self.window_s:
            self._clear_progress()

        if not active:
            self._in_burst = False
            return events

        calibrated = self._range_believable(data)
        if self._mode_calibrated is not None and calibrated != self._mode_calibrated:
            self._clear_progress()
        self._mode_calibrated = calibrated

        burst_start = not self._in_burst
        self._in_burst = True

        if calibrated:
            confirmed = self._advance_positions(t, data, prev)
        else:
            confirmed = self._count_bursts(t, burst_start)

        if confirmed:
            self._running = True
            self._confirmed_t = t
            self._last_active_t = t
            self._clear_progress()
            events.append(EVENT_STARTED)
        return events

    def _is_active(self, data: Cef168Data, prev: Optional[Cef168Data]) -> bool:
        if data.moving:
            return True
        if self.require_motor_flag or prev is None:
            return False
        return data.focus_position_cur != prev.focus_position_cur

    def _range_believable(self, data: Cef168Data) -> bool:
        return data.range_valid and data.position_span >= self.min_range_span

    def _near_min(self, data: Cef168Data, position: int) -> bool:
        return position <= data.focus_position_min + self.near_fraction * data.position_span

    def _near_max(self, data: Cef168Data, position: int) -> bool:
        return position >= data.focus_position_max - self.near_fraction * data.position_span

    def _advance_positions(self, t: float, data: Cef168Data, prev: Optional[Cef168Data]) -> bool:
        """Calibrated lens: min -> max -> min, in order, motor-driven. True when
        the third touch lands."""
        position = data.focus_position_cur
        if self._stage and t - self._stage_t0 > self.window_s:
            self._stage = 0
        if self._stage == 0:
            rested_at_min = (prev is not None and not prev.moving
                             and self._near_min(data, prev.focus_position_cur))
            if self._near_min(data, position) or rested_at_min:
                # The test starts from wherever the lens is and drives it to
                # min first -- or the lens was already resting at min and the
                # first motion we see is the move out, so the previous (idle)
                # sample is the touch.
                self._stage, self._stage_t0 = 1, t
        elif self._stage == 1:
            if self._near_max(data, position):
                self._stage = 2
        elif self._stage == 2:
            if self._near_min(data, position):
                self._stage = 3
        return self._stage >= 3

    def _count_bursts(self, t: float, burst_start: bool) -> bool:
        """Uncalibrated lens: enough separate bursts inside the window."""
        if burst_start:
            self._bursts.append(t)
        self._bursts = [b for b in self._bursts if t - b <= self.window_s]
        return len(self._bursts) >= self.uncalibrated_min_bursts
