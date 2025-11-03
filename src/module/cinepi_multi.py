import subprocess
import logging
import re
import json
import time
from queue import Queue
from threading import Thread
from typing import List, Optional
from threading import Event as ThreadEvent
from typing import List
import os, signal
import shutil

from module.config_loader import load_settings
from module.redis_controller import ParameterKey

# Path to settings file
SETTINGS_FILE = "/home/pi/cinemate/src/settings.json"
# Load global settings
_SETTINGS = load_settings(SETTINGS_FILE)

_READY_RX   = re.compile(r"Encoder configured")      # line printed by DngEncoder
_READY_WAIT = 2.0                                   # seconds to wait for all cams

def _rt_permitted():
    if shutil.which("chrt") is None:
        return False
    try:
        # Will only succeed if this user has CAP_SYS_NICE
        subprocess.run(["chrt", "-f", "70", "/bin/true"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

# ───────────────────────── zoom default ──────────────────────────
def _seed_default_zoom(redis_ctl):
    """
    Write preview.default_zoom to Redis once per boot, but
    only if the key doesn’t exist yet.
    """
    preview_cfg  = _SETTINGS.get("preview", {})
    default_zoom = float(preview_cfg.get("default_zoom", 1.0))

    if redis_ctl.get_value(ParameterKey.ZOOM.value) is None:
        redis_ctl.set_value(ParameterKey.ZOOM.value, default_zoom)
        # wake cinepi-raw controller
        redis_ctl.r.publish("cp_controls", ParameterKey.ZOOM.value)
        logging.info("[init] preview zoom defaulted to %.1f×", default_zoom)
        
# ───────────────────────── Event ─────────────────────────
class Event:
    def __init__(self):
        self._listeners = []
    def subscribe(self, listener):
        self._listeners.append(listener)
    def emit(self, data=None):
        for l in self._listeners:
            l(data)

# ───────────────────── Camera Discovery ──────────────────
class CameraInfo:
    def __init__(self, index: int, name: str, fmt: str, path: str):
        self.index = index
        self.name = name
        self.fmt = fmt
        self.path = path
        self.is_mono = 'MONO' in fmt

    @property
    def port(self):
        # Pi 4 / Zero 2 W
        if 'i2c@1a0000' in self.path or 'i2c@10' in self.path:
            return 'cam0'

        # Pi 5 / CM4 / CM3
        if 'i2c@88000' in self.path:
            return 'cam0'
        if 'i2c@80000' in self.path or 'i2c@70000' in self.path:
            return 'cam1'

        # Fallback: assume cam0
        return 'cam0'

    def as_dict(self):
        return {
            'index': self.index,
            'model': self.name,
            'mono': self.is_mono,
            'port': self.port,
        }

    def __repr__(self):
        typ = 'mono' if self.is_mono else 'colour'
        return f'CameraInfo(idx={self.index}, {self.name}, {typ}, {self.port})'


    

# ──────────────────────── camera discovery ────────────────────────
def discover_cameras(timeout: float = 10.0, interval: float = 1.0) -> List[CameraInfo]:
    rx = re.compile(r'^\s*(\d+)\s*:\s*(\w+)\s*\[([^]]+)\]\s*\(([^)]+)\)')
    end = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < end:
        attempt += 1
        proc = subprocess.run(['cinepi-raw', '--list-cameras'],
                              text=True, capture_output=True)
        cams: List[CameraInfo] = []
        for line in (proc.stdout or '').splitlines():
            m = rx.match(line)
            if m:
                idx, name, fmt, path = m.groups()

                # ───── create → log → append ─────
                cam = CameraInfo(int(idx), name, fmt, path)
                logging.info("Detected %s on %s (%s)",
                             cam.name, cam.port, cam.path)
                cams.append(cam)

        if cams:
            logging.info('Discovered cameras on attempt %d: %s', attempt, cams)
            return cams
        logging.warning('Attempt %d failed (%s); retrying', attempt, proc.returncode)
        time.sleep(interval)
    logging.error('Camera discovery timed out')
    return []



# ────────────────── cinepi‑raw subprocess wrapper ─────────
class CinePiProcess(Thread):
    def __init__(
        self,
        redis_controller,
        sensor_detect,
        cam: CameraInfo,
        primary: bool,
        multi: bool,
    ):
        super().__init__(daemon=True)
        self.redis_controller = redis_controller
        self.sensor_detect = sensor_detect
        self.cam = cam
        self.primary = primary
        self.multi = multi
        self.proc: Optional[subprocess.Popen] = None
        self.message = Event()
        self.out_q, self.err_q = Queue(), Queue()
        self.log_filters = {
            'frame': re.compile(r'Frame Number'),
            'agc': re.compile(r'RPiAgc'),
            'ccm': re.compile(r'RPiCcm'),
            'vu': re.compile(r'\[VU\]'),
        }
        self.active_filters = set(self.log_filters)
        
        # ── NEW: detect the “DNG written:” line that dng_encoder now prints
        self.dng_rx = re.compile(r'DNG written:\s*(\S+\.dng)')
        self.redis_channel = 'cinepi.last_dng'          # publish JSON here
        
        # load per-camera geometry from settings
        geo = _SETTINGS.get('geometry', {})
        self.geometry = geo.get(self.cam.port, {})
        
        # load per-camera output settings (e.g., HDMI port)
        out_cfg = _SETTINGS.get('output', {})
        self.output = out_cfg.get(self.cam.port, {})


    def run(self):
        cine_cmd = ['cinepi-raw'] + self._build_args()

        prefix = []
        if _rt_permitted():
            # SCHED_FIFO 70 for the whole process (capture threads benefit most)
            prefix += ["chrt", "-f", "70"]
        else:
            logging.warning("[%s] RT scheduling not permitted; running without chrt", self.cam.port)

        # Best-effort I/O (no CAP_SYS_ADMIN needed)
        if shutil.which("ionice"):
            prefix += ["ionice", "-c2", "-n0"]

        # Keep the entire process off CPU0; allow 1–3 (GUI/OS left on 0)
        if shutil.which("taskset"):
            prefix += ["taskset", "-c", "1-3"]

        cmd = (prefix + cine_cmd) if prefix else cine_cmd
        logging.info('[%s] Launch: %s', self.cam, cmd)
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        Thread(target=self._pump, args=(self.proc.stdout, self.out_q)).start()
        Thread(target=self._pump, args=(self.proc.stderr, self.err_q)).start()
        self.proc.wait()
        logging.info('[%s] exited %s', self.cam, self.proc.returncode)


        
    def _log(self, text):
        for name, rx in self.log_filters.items():
            if name in self.active_filters and rx.search(text):
                pass #logging.info('[%s] %s', self.cam, text)
                break
        logging.info('[%s] %s', self.cam.port, text)   # DEBUG → all lines
        pass
        
    # ─────────────────────────────────────────────────────────────
    #  Stream one pipe from cinepi-raw, relay lines, intercept the
    #  “DNG written:” message, and update a per-camera Redis key.
    # ─────────────────────────────────────────────────────────────
    def _pump(self, pipe, q):
        dng_rx    = re.compile(r'DNG written:\s*(\S+\.dng)')
        redis_key = f'last_dng_{self.cam.port}'   # cam0 → last_dng_cam0 …

        for raw in iter(pipe.readline, b''):
            # 1. canonicalise ---------------------------------------------------
            line = raw.decode('utf-8', 'replace').rstrip()

            # 2. forward raw text exactly as before ----------------------------
            q.put(line)
            self.message.emit(line)
            self._log(line)

            # 3. special-case the new encoder message --------------------------
            m = dng_rx.search(line)
            if m:
                fname   = m.group(1)
                payload = {
                    'type': 'dng',
                    'cam' : self.cam.index,
                    'file': fname,
                    'time': time.time(),
                }

                # 3a. supervisor log (human readable)
                #logging.info('[%s] Last DNG written → %s', self.cam, fname)

                # 3b. structured in-process event
                self.message.emit(payload)

                # 3c. store per-camera key in Redis
                try:
                    self.redis_controller.set_value(redis_key, fname)
                except Exception as e:
                    logging.warning('[%s] Redis set_value failed: %s',
                                    self.cam, e)

        pipe.close()

    def _is_pi4(self) -> bool:
        """Return True on any Raspberry Pi 4/400/CM4‐lite platform."""
        try:
            with open("/proc/device-tree/model") as f:
                return "Raspberry Pi 4" in f.read()
        except FileNotFoundError:
            return False

    def _build_args(self):
        # base resolution
        sensor_mode = int(self.redis_controller.get_value(ParameterKey.SENSOR_MODE.value) or 0)
        model_key = self.cam.name + ('_mono' if self.cam.is_mono else '')
        res = self.sensor_detect.get_resolution_info(model_key, sensor_mode)
        width = res.get('width', 1920)
        height = res.get('height', 1080)
        bit_depth = res.get('bit_depth', 12)
        packing = res.get('packing', 'U')
        
        # # packing override
        # pi_model = self.redis_controller.get_value('pi_model') or ''
        # if self.cam.is_mono or (pi_model == 'pi4' and model_key == 'imx477'):
        #     packing = 'P'
        
        # lores & preview
        aspect = width / height
        anam = float(self.redis_controller.get_value(ParameterKey.ANAMORPHIC_FACTOR.value) or 1.0)
        fw, fh = 1920, 1080
        px, py = 94, 50
        aw, ah = fw - 2*px, fh - 2*py
        lh = min(720, ah)
        lw = int(lh * aspect * anam)
        if lw > aw:
            lw, lh = aw, int(round(aw / (aspect * anam)))
        self.redis_controller.set_value(ParameterKey.LORES_WIDTH.value, lw)
        self.redis_controller.set_value(ParameterKey.LORES_HEIGHT.value, lh)
        if (aw/ah) > aspect:
            ph = ah; pw = int(ph * aspect)
        else:
            pw = aw; ph = int(pw / aspect)
        
        ox, oy = (fw-pw)//2, (fh-ph)//2
        
        # gains, shutter
        cg_rb = self.redis_controller.get_value(ParameterKey.CG_RB.value) or '2.5,2.2'
        
        # file paths\
        tune = f'/home/pi/libcamera/src/ipa/rpi/pisp/data/{model_key}.json'
        post = f'/home/pi/post-processing{self.cam.index}.json'
        
        # geometry flags
        rot = 180 if self.geometry.get('rotate_180', False) else 0
        hf = 1 if self.geometry.get('horizontal_flip', False) else 0
        vf = 1 if self.geometry.get('vertical_flip', False) else 0
        
        # anamorphic factor
        self.anamorphic_factor = self.redis_controller.get_value(ParameterKey.ANAMORPHIC_FACTOR.value)
        if self.anamorphic_factor is None:
            self.anamorphic_factor = 1.0
        else:
            self.anamorphic_factor = float(self.anamorphic_factor)
        
        # determine HDMI port: override from settings if provided
        default_hd = '0' if self.cam.port == 'cam0' else '1'
        hd = str(self.output.get('hdmi_port', default_hd))

        args = [
            "--cam-port", str(self.cam.port),
            "--mode",   f"{width}:{height}:{bit_depth}:{packing}",
            "--width",  str(width),
            "--height", str(height),
            "--lores-width",  str(lw),
            "--lores-height", str(lh),
            "--hdmi-port",    hd,
            "--rotation",     str(rot),
            "--hflip",        str(hf),
            "--vflip",        str(vf),
            "--post-process-file", post,
            "--shutter", "20000",
            "--awb", "auto",
            "--awbgains", cg_rb,
        ]

        # * Skip --tuning-file on Pi 4.  All other models keep it. *
        if not self._is_pi4():
            args += ["--tuning-file", tune]
            
        zoom_init = self.redis_controller.get_value(ParameterKey.ZOOM.value)
        
        if zoom_init and float(zoom_init) != 1.0:
            args += ['--zoom', str(zoom_init)]

        # ── if running in multi-camera mode, pass --sync server/client ──
        if self.multi:
            args += ["--cam-port", self.cam.port]
            if self.primary:
                args += ['--sync', 'server']
            else:
                args += ['--sync', 'client']
        
        if not (self.multi and not self.primary):
            args += ['-p', f'{ox},{oy},{pw},{ph}']
        else:
            args += ['--nopreview']
            
        # ───── Option A: Stable 24p (3 enc, 1 writer; keep CPU3 mostly free for capture) ─────
        args += [
            "--encode-workers",  "4",
            "--disk-workers",    "2",
            "--encode-affinity", "1-2",   # encoders on CPUs 1–2
            "--disk-affinity",   "2",     # writer on CPU 2 (near NVMe IRQs you’ll pin)
            "--encode-nice",     "-10",
            "--disk-nice",       "-5",
        ]
        
        return args

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

# ───────────────────────── Manager ───────────────────────
class CinePiManager:
    """
    Spin up one ``cinepi-raw`` process per detected sensor and return only
    when **all** encoders report “Encoder configured”.  This guarantees that
    the very first REC edge is seen by every camera.
    """

    def __init__(self, redis_controller, sensor_detect):
        self.redis_controller = redis_controller
        self.sensor_detect    = sensor_detect
        self.processes: List[CinePiProcess] = []
        self.message = Event()                        # fan-out for log relay

    # ───────────────────────── public api ──────────────────────────
    start_cinepi_process = lambda self: self.start_all()
    restart              = lambda self: (self.stop_all(), self.start_all())
    shutdown             = lambda self: self.stop_all()
        
    # ────────────────────────── start / stop ──────────────────────────
    def start_all(self) -> None:
        """Discover sensors, launch one *cinepi-raw* each, wait for readiness."""
        self.stop_all()                              # clean previous run
        
        # ------------------------------------------------------------------
        # Seed the zoom factor before cinepi-raw processes read it
        # ------------------------------------------------------------------
        _seed_default_zoom(self.redis_controller)

        # ── 1. discovery ───────────────────────────────────────────
        cams = discover_cameras()                    # helper unchanged


        # ── Pi 4 sanity check ────────────────────────────────────────────
        try:
            with open("/proc/device-tree/model", "r") as f:
                model_str = f.read()
        except FileNotFoundError:
            model_str = ""

        if "Raspberry Pi 4" in model_str:
            for cam in cams:
                if cam.port != "cam0":          # Pi 4 has only CSI-0
                    logging.warning(
                        "[init] Sensor on %s but this is a Pi 4 – forcing cam0",
                        cam.port,
                    )
                    cam._port = "cam0"          # override in place


        cams.sort(key=lambda c: c.port)              # cam0, cam1, …
        self.redis_controller.set_value(
            ParameterKey.CAMERAS.value,
            json.dumps([c.as_dict() for c in cams])
        )
        if not cams:
            logging.error("No cameras found – aborting start_all()")
            return
        
        self.redis_controller.set_value(ParameterKey.IS_RECORDING.value, 0)  # reset recording flag
        
        if self.redis_controller.get_value(ParameterKey.FPS) is not None:
            self.redis_controller.set_value(ParameterKey.FPS.value, self.redis_controller.get_value(ParameterKey.FPS))          # reset FPS

        # ── 2. per-model resolution info ──────────────────────────
        sensor_mode = int(self.redis_controller.get_value(
            ParameterKey.SENSOR_MODE.value) or 0)
        pk = cams[0].name + ("_mono" if cams[0].is_mono else "")
        self.sensor_detect.camera_model = pk
        self.sensor_detect.load_sensor_resolutions()
        self.redis_controller.set_value(ParameterKey.SENSOR.value, pk)

        res = self.sensor_detect.get_resolution_info(pk, sensor_mode)
        for k in (
            ParameterKey.WIDTH.value,
            ParameterKey.HEIGHT.value,
            ParameterKey.BIT_DEPTH.value,
            ParameterKey.FPS_MAX.value,
            ParameterKey.GUI_LAYOUT.value,
        ):
            self.redis_controller.set_value(k, res.get(k))

        # ── 3. launch all cinepi-raw instances ───────────────────────────
        multi = len(cams) > 1
        for i, cam in enumerate(cams):
            proc = CinePiProcess(
                self.redis_controller,
                self.sensor_detect,
                cam,
                primary=(i == 0),
                multi=multi,
            )
            proc.message.subscribe(self.message.emit)
            proc.start()
            self.processes.append(proc)
            time.sleep(0.5)                       # stagger start

        # ── 4. wait until *all* cameras announced “ready” via Redis ──────
        want = {f"cinepi_ready_{c.port}" for c in cams}
        deadline = time.monotonic() + _READY_WAIT          # e.g. 10 s total

        while time.monotonic() < deadline:
            # raw Redis handle (adjust if your wrapper exposes it differently)
            have = {k.decode() for k in self.redis_controller.r.keys("cinepi_ready_*")}
            if want.issubset(have):
                logging.info("All cinepi-raw encoders ready — starting supervisor.")
                break
            time.sleep(0.05)
        else:
            missing = ", ".join(sorted(want - have)) or "<??>"
            logging.warning("start_all(): timeout waiting for %s", missing)

        self.redis_controller.set_value(ParameterKey.LAST_DNG_CAM0.value, "None")
        self.redis_controller.set_value(ParameterKey.LAST_DNG_CAM1.value, "None"),   
        
        # ── 4. wait until *all* cameras announced “ready” via Redis ──────
        want = {f"cinepi_ready_{c.port}" for c in cams}
        deadline = time.monotonic() + _READY_WAIT          # e.g. 10 s

        while time.monotonic() < deadline:
            have = {k.decode() for k in
                    self.redis_controller.r.keys("cinepi_ready_*")}
            if want.issubset(have):
                logging.info("All cinepi-raw encoders ready — starting supervisor.")
                break
            time.sleep(0.05)
        else:
            missing = ", ".join(sorted(want - have)) or "<??>"
            logging.warning("start_all(): timeout waiting for %s", missing)

        # ────────────────────────────────────────────────────────────────
        # NEW ✱ 5.  Kick the initial zoom once everything is alive
        # ────────────────────────────────────────────────────────────────
        try:
            z = float(self.redis_controller.get_value(ParameterKey.ZOOM.value) or 1.0)
        except (TypeError, ValueError):
            z = 1.0                                  # fallback

        if abs(z - 1.0) > 1e-3:                      # only if not default
            logging.info("Applying startup preview zoom %.1f×", z)
            # write the value again (no change) **and** publish the key so the
            # C++ controller’s handler runs and pushes the ScalerCrop.
            self.redis_controller.r.publish("cp_controls", ParameterKey.ZOOM.value)

        # record-path housekeeping that was already there
        self.redis_controller.set_value(ParameterKey.LAST_DNG_CAM0.value, "None")
        self.redis_controller.set_value(ParameterKey.LAST_DNG_CAM1.value, "None")  

    # ───────────────────────── teardown ────────────────────────────
    def stop_all(self) -> None:
        for p in self.processes:
            p.stop()
        for p in self.processes:
            p.join()
        self.processes.clear()
        
        # ── tidy up “ready” flags ──────────────────────────────────
        raw_keys = self.redis_controller.r.keys("cinepi_ready_*")   # list[bytes]
        if raw_keys:                                               # only if any
            self.redis_controller.r.delete(*raw_keys)

    # ────────────────────── logging helpers ────────────────────────
    def set_log_level(self, lvl: str) -> None:
        logging.getLogger().setLevel(getattr(logging, lvl.upper(), logging.INFO))

    def set_active_filters(self, filters) -> None:
        for p in self.processes:
            p.active_filters = set(filters)