# redis_listener_dng_stats.py
import redis, threading, datetime, json, time, logging
from collections import defaultdict
from module.redis_controller import ParameterKey


class RedisListener:
    """
    Recording detection driven by the encoder’s “DNG written:” messages,
    plus a stats subscriber to report buffer activity.

    •  REC  = 1 while *any* cam records       (legacy flag for GPIO / UI)
    •  IS_WRITING = 1 while any new DNG hits the disk
    •  IS_WRITING_BUF = 1 after REC→0 *but* bufferSize > 0  (flushing)
    """

    # ───────────────────────── INITIALISATION ──────────────────────────
    def __init__(
        self,
        redis_controller,
        host="localhost",
        port=6379,
        db=0,
        monitor_interval=0.25,      # watchdog wake-up (sec)
        gap_factor=8.0,             # leeway: consider stopped when >gap_factor/fps sec idle
    ):
        # Redis -----------------------------------------------------------
        self.r               = redis.StrictRedis(host=host, port=port, db=db)
        self.ps_stats        = self.r.pubsub()
        self.ps_ctrl         = self.r.pubsub()
        self.ps_stats.subscribe("cp_stats")
        self.ps_ctrl .subscribe("cp_controls")

        # External API ----------------------------------------------------
        self.redis_ctl       = redis_controller
        self._callbacks      = defaultdict(list)

        # Per-camera bookkeeping -----------------------------------------
        self.cams            = ("cam0", "cam1")
        self.rec_state       = {c: False               for c in self.cams}
        self.last_fname      = {c: None                for c in self.cams}
        self.last_time       = {c: None                for c in self.cams}
        self.frames_written  = {c: 0                   for c in self.cams}
        self.t_start         = {c: None                for c in self.cams}
        self.t_end           = {c: None                for c in self.cams}
        
        self.colorTemp   = 0           
        self.bufferSize  = 0           

        # Tunables & helpers ---------------------------------------------
        self.monitor_interval = monitor_interval
        self.gap_factor       = gap_factor
        self._lock            = threading.Lock()

        # Threads ---------------------------------------------------------
        threading.Thread(target=self._listen_controls, daemon=True).start()
        threading.Thread(target=self._listen_stats,    daemon=True).start()
        threading.Thread(target=self._watchdog,        daemon=True).start()

        logging.info("RedisListener ready (DNG + stats)")

    # ───────────────────────── PUBLIC API ───────────────────────────────
    def on(self, event, fn):
        """Register callback:  on('recording_started', fn(cam='cam0'))"""
        self._callbacks[event].append(fn)

    # ───────────────────────── REDIS FEEDS ──────────────────────────────
    def _listen_controls(self):
        """Watch `last_dng_cam*` keys for every freshly written DNG."""
        for msg in self.ps_ctrl.listen():
            if msg["type"] != "message":
                continue
            key = msg["data"].decode()
            if not key.startswith("last_dng_cam"):
                continue

            cam  = "cam0" if "cam0" in key else "cam1"
            val  = self.r.get(key)
            if not val:
                continue
            fname = val.decode()

            with self._lock:
                # new file → count frame & remember when it arrived
                if fname != self.last_fname[cam]:
                    self.last_fname[cam]   = fname
                    self.last_time [cam]   = datetime.datetime.now()
                    if self.rec_state[cam]:
                        self.frames_written[cam] += 1
                    self._set_is_writing(1)          # LED / UI

    def _listen_stats(self):
        """Track buffer usage and raise IS_BUFFERING / IS_WRITING_BUF."""
        for msg in self.ps_stats.listen():
            if msg["type"] != "message":
                continue
            try:
                payload = json.loads(msg["data"].decode().strip())
            except json.JSONDecodeError:
                continue

            buf = payload.get("bufferSize")
            
            color_temp  = payload.get("colorTemp")     # ← extract WB temp
            
            if buf is not None:
                self.bufferSize = buf
            if color_temp is not None:
                self.colorTemp  = color_temp
            
            # ----- global: somebody’s buffering? -------------------------
            is_buf = 1 if buf else 0
            self.redis_ctl.set_value(ParameterKey.IS_BUFFERING.value, is_buf)

            # ----- still flushing to disk after record stop? -------------
            rec_any = any(self.rec_state.values())
            self.redis_ctl.set_value(
                ParameterKey.IS_WRITING_BUF.value,
                1 if (not rec_any and buf) else 0,
            )

    # ───────────────────────── WATCHDOG LOOP ────────────────────────────
    def _watchdog(self):
        while True:
            time.sleep(self.monitor_interval)

            fps      = float(self.redis_ctl.get_value(ParameterKey.FPS.value, 24) or 24)
            max_gap  = self.gap_factor / fps
            now      = datetime.datetime.now()
            changed  = False

            with self._lock:
                buffering = self.bufferSize > 0          # ← NEW
    
                for cam in self.cams:
                    recently_written = (
                        self.last_time[cam]
                        and (now - self.last_time[cam]).total_seconds() < max_gap
                    )

                    # ----- NEW RULE -----
                    # keep REC high while buffer not empty, even
                    # if no fresh file was written in the last
                    # <max_gap> seconds
                active = recently_written or (self.rec_state[cam] and buffering)
                if active != self.rec_state[cam]:
                        self._toggle_state(cam, active)
                        changed = True

            if changed:
                self._update_global_rec_flag()

            if not any(self.rec_state.values()):
                self._set_is_writing(0)

    # ───────────────────────── STATE CHANGES ────────────────────────────
    def _toggle_state(self, cam, active: bool):
        self.rec_state[cam] = active
        event = "recording_started" if active else "recording_stopped"

        if active:        # ----- REC started -----
            self.t_start[cam]        = datetime.datetime.now()
            self.frames_written[cam] = 0
            self._fire(event, cam=cam)

        else:             # ----- REC stopped ----
            self.t_end[cam] = datetime.datetime.now()
            self._fire(event, cam=cam)
            self._report_stats(cam)          # ← post-take report

    def _update_global_rec_flag(self):
        flag = "1" if any(self.rec_state.values()) else "0"
        self.redis_ctl.set_value(ParameterKey.REC.value, flag)

    def _set_is_writing(self, flag: int):
        try:
            self.redis_ctl.set_value(ParameterKey.IS_WRITING.value, flag)
        except Exception:
            pass

    # ───────────────────────── POST-TAKE REPORT ────────────────────────
    def _report_stats(self, cam):
        ts0, ts1 = self.t_start[cam], self.t_end[cam]
        if not (ts0 and ts1):
            return
        secs   = (ts1 - ts0).total_seconds()
        fps    = float(self.redis_ctl.get_value(ParameterKey.FPS.value, 0) or 0)
        expect = int(round(fps * secs)) if fps else None
        got    = self.frames_written[cam]
        diff   = (expect - got) if expect is not None else "n/a"

        logging.info(
            "[%s] Recording stats ─ duration %.2fs | expected %s | "
            "written %d | Δ %s",
            cam, secs, expect if expect is not None else "?", got, diff,
        )

    # ───────────────────────── CALLBACK HELPER ─────────────────────────
    def _fire(self, event, **kw):
        for fn in self._callbacks[event]:
            try:
                fn(**kw)
            except Exception:
                logging.exception("RedisListener callback failed")
