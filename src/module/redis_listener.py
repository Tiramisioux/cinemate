# redis_listener_dng_stats.py – buffer‑size broadcast + frame‑drop pulse (v15)
# 2025‑06‑27  «ignore leftover DNGs while flushing»
"""Drop‑in Redis listener for CinePi.

Revision v15 (27 Jun, 08 h45)
--------------------------------
* **Ignore stale DNGs during buffer flush** – when the user presses **stop** we
  now mark the take as *flushing* (`self.flush[cam] = True`). Any *new* `last_dng_*`
  notifications that arrive while this flag is true belong to the *previous* take
  that is being written out, so we **do not** toggle the per‑camera *REC* flag
  back to *high*.  This prevents the rapid *REC ↓↑* oscillation that could be
  seen when stopping a recording with a non‑empty buffer.
* **Behaviour summary** (unchanged otherwise):
  – *REC* ↑ on the first fresh DNG of a new take; *REC* ↓ exactly when the user
    stops, **even if the buffer is still flushing**.
  – *IS_WRITING* debounced (400 ms).
  – *FRAME_DROP* pulse on |fps‑inst − fps‑set| > 0.5.
"""
from __future__ import annotations

import datetime
import json
import logging
import threading
import time
from collections import defaultdict

import redis

from module.redis_controller import ParameterKey

__all__ = ["RedisListener"]


class RedisListener:
    """Watch ``cp_stats`` & ``cp_controls`` and keep high‑level flags in Redis."""

    # ──────────────────── init ─────────────────────────────────────
    def __init__(
        self,
        redis_controller,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        monitor_interval: float = 0.25,
        gap_factor: float = 8.0,
    ) -> None:
        # Redis ---------------------------------------------------------
        self.r = redis.StrictRedis(host=host, port=port, db=db)
        self.ps_stats = self.r.pubsub(); self.ps_stats.subscribe("cp_stats")
        self.ps_ctrl  = self.r.pubsub(); self.ps_ctrl.subscribe("cp_controls")

        # External handles ---------------------------------------------
        self.redis_ctl  = redis_controller
        self._callbacks = defaultdict(list)

        # Per‑camera bookkeeping ---------------------------------------
        self.cams        = ("cam0", "cam1")
        self.rec         = {c: False for c in self.cams}   # currently recording?
        self.flush       = {c: False for c in self.cams}   # buffer flushing?
        self.last_dng    = {c: None  for c in self.cams}
        self.t_dng       = {c: None  for c in self.cams}
        self.frames      = {c: 0     for c in self.cams}
        self.t_start     = {c: None  for c in self.cams}   # first DNG ts
        self.t_stop      = {c: None  for c in self.cams}   # REC↓ ts
        self.t_flush_end = {c: None  for c in self.cams}   # buffer empty ts

        # Global stats --------------------------------------------------
        self.bufferSize      = 0
        self.colorTemp       = 0
        self.last_framecount = 0
        self.t_fc: datetime.datetime | None = None  # last frameCount tick

        # Frame‑drop pulse helper --------------------------------------
        self._frame_drop_active = False
        self._frame_drop_lock   = threading.Lock()

        # Debounced IS_WRITING -----------------------------------------
        self.write_leeway   = 0.4  # seconds – keep flag high at least this long
        self._t_last_write: datetime.datetime | None = None
        self._is_writing   = 0  # cached Redis value (0/1)

        # Tunables ------------------------------------------------------
        self.monitor_interval = monitor_interval
        self.gap_factor       = gap_factor
        self._lock            = threading.Lock()

        # Threads -------------------------------------------------------
        threading.Thread(target=self._listen_ctrl,  daemon=True).start()
        threading.Thread(target=self._listen_stats, daemon=True).start()
        threading.Thread(target=self._watchdog,     daemon=True).start()

        logging.info("RedisListener ready (v15 – flush‑aware REC logic)")

    # ─────────────────── helpers / callbacks ──────────────────────────
    def on(self, evt: str, fn):
        self._callbacks[evt].append(fn)

    def _fire(self, evt: str, **kw):
        for fn in self._callbacks[evt]:
            try:
                fn(**kw)
            except Exception:
                logging.exception("RedisListener callback failed")

    # ─────────────────── CONTROL channel (DNG) ────────────────────────
    def _listen_ctrl(self):
        """Handle new DNG notifications (one per written file)."""
        for msg in self.ps_ctrl.listen():
            if msg["type"] != "message":
                continue
            key = msg["data"].decode()
            if not key.startswith("last_dng_cam"):
                continue
            cam   = "cam0" if "cam0" in key else "cam1"
            fname = (self.r.get(key) or b"").decode()
            if not fname:
                continue

            now = datetime.datetime.now()
            with self._lock:
                if fname == self.last_dng[cam]:
                    continue  # duplicate

                # still flushing previous take – ignore for REC purposes
                if self.flush[cam]:
                    self.last_dng[cam] = fname  # keep latest for diagnostics
                    self._touch_is_writing()
                    continue

                # bookkeeping -----------------------------------------
                self.last_dng[cam] = fname
                self.t_dng[cam]    = now

                # REC ↑ if this cam was idle (flush done) -------------
                if not self.rec[cam]:
                    self._toggle(cam, True)
                    self._update_REC()
                self.frames[cam] += 1

                self._touch_is_writing()

    # ─────────────────── STATS channel (buffer / frameCount / fps) ────
    def _listen_stats(self):
        for msg in self.ps_stats.listen():
            if msg["type"] != "message":
                continue
            try:
                payload = json.loads(msg["data"].decode().strip())
            except json.JSONDecodeError:
                continue

            buf  = payload.get("bufferSize")
            fc   = payload.get("frameCount")
            temp = payload.get("colorTemp")
            fr   = payload.get("framerate")  # instantaneous FPS

            if buf is not None:
                self.bufferSize = buf
                try:
                    self.redis_ctl.set_value(ParameterKey.BUFFER.value, buf)
                except Exception:
                    pass

            if temp is not None:
                self.colorTemp = temp
            if fc is not None and fc > self.last_framecount:
                self.last_framecount = fc
                self.t_fc = datetime.datetime.now()

            # frame‑drop detection ------------------------------------
            if fr is not None:
                try:
                    user_fps = float(self.redis_ctl.get_value(ParameterKey.FPS.value, 0) or 0)
                    if user_fps and abs(float(fr) - user_fps) > 0.5:
                        self._pulse_frame_drop()
                except Exception:
                    pass

            # live flags ----------------------------------------------
            try:
                self.redis_ctl.set_value(ParameterKey.IS_BUFFERING.value, int(bool(buf)))
            except Exception:
                pass
            rec_any = any(self.rec.values())
            try:
                self.redis_ctl.set_value(
                    ParameterKey.IS_WRITING_BUF.value,
                    1 if (buf and not rec_any) else 0,
                )
            except Exception:
                pass

            # flush completion per camera -----------------------------
            if buf == 0:
                for cam in self.cams:
                    if self.flush[cam]:
                        self.t_flush_end[cam] = datetime.datetime.now()
                        self._report_stats(cam)
                        self.flush[cam] = False

            # REC may change when user stopped earlier ----------------
            self._update_REC()

    # ─────────────────── WATCHDOG (user stop → REC ↓) ────────────────
    def _watchdog(self):
        while True:
            time.sleep(self.monitor_interval)
            try:
                user_rec_flag = int(self.redis_ctl.get_value(ParameterKey.IS_RECORDING.value, 0))
            except Exception:
                user_rec_flag = 0

            now = datetime.datetime.now()

            # debounce IS_WRITING low transition ----------------------
            if (
                self._is_writing == 1
                and self._t_last_write
                and (now - self._t_last_write).total_seconds() > self.write_leeway
            ):
                self._set_is_writing(0)

            # bring REC low when user pressed stop --------------------
            changed = False
            with self._lock:
                if user_rec_flag == 0:
                    for cam in self.cams:
                        if self.rec[cam]:
                            self._toggle(cam, False)
                            changed = True
                # ensure all timers reset for next take --------------
                if changed:
                    self.t_fc = None
            if changed:
                self._update_REC()

    # ─────────────────── frame‑drop pulse -----------------------------
    def _pulse_frame_drop(self):
        with self._frame_drop_lock:
            if self._frame_drop_active:
                return
            self._frame_drop_active = True
            try:
                self.redis_ctl.set_value(ParameterKey.FRAME_DROP.value, 1)
            except Exception:
                pass
            threading.Timer(0.5, self._clear_frame_drop).start()

    def _clear_frame_drop(self):
        try:
            self.redis_ctl.set_value(ParameterKey.FRAME_DROP.value, 0)
        except Exception:
            pass
        with self._frame_drop_lock:
            self._frame_drop_active = False

    # ─────────────────── state transitions ---------------------------
    def _toggle(self, cam: str, active: bool):
        if active == self.rec[cam]:
            return

        self.rec[cam] = active
        evt = "recording_started" if active else "recording_stopped"

        if active:
            now               = datetime.datetime.now()
            self.t_start[cam] = now
            self.frames[cam]  = 0
            self.flush[cam]   = False
        else:
            self.t_stop[cam]  = datetime.datetime.now()
            self.flush[cam]   = True
            # reset per‑take timers so next take starts clean
            self.t_dng[cam] = None

        self._fire(evt, cam=cam)

    # ─────────────────── REC aggregate flag --------------------------
    def _update_REC(self):
        try:
            flag = "1" if any(self.rec.values()) else "0"
            self.redis_ctl.set_value(ParameterKey.REC.value, flag)
        except Exception:
            pass

    # ─────────────────── debounced IS_WRITING helpers ----------------
    def _touch_is_writing(self):
        self._t_last_write = datetime.datetime.now()
        if not self._is_writing:
            self._set_is_writing(1)

    # ─────────────────── IS_WRITING convenience ----------------------
    def _set_is_writing(self, flag: int):
        try:
            self.redis_ctl.set_value(ParameterKey.IS_WRITING.value, flag)
        except Exception:
            pass
        self._is_writing = flag

    # ─────────────────── post‑take statistics -----------------------
    def _report_stats(self, cam: str):
        ts0, ts1 = self.t_start[cam], self.t_flush_end[cam]
        if not (ts0 and ts1):
            return
        duration = (ts1 - ts0).total_seconds()
        try:
            fps_set = float(self.redis_ctl.get_value(ParameterKey.FPS.value, 0) or 0)
        except Exception:
            fps_set = 0
        expected = int(round(duration * fps_set)) if fps_set else None
        written  = self.frames[cam]
        delta    = (expected - written) if expected is not None else "n/a"
        logging.info("[%s] Take %.2fs | expected %s | written %d | Δ %s",
                     cam, duration, expected if expected is not None else "?", written, delta)
