import subprocess
import logging
import re
import json
import time
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import List, Optional
from threading import Event as ThreadEvent
from typing import List
import os, signal
import shutil

from module.config_loader import load_settings
from module.redis_controller import ParameterKey
from module.framebuffer import Framebuffer
from module.storage_profiles import (
    DEFAULT_RECORDER_PROFILE,
    recorder_profile_args,
    recorder_profile_for_filesystem,
    recorder_profile_name_for_filesystem,
)

# Path to settings file
SETTINGS_FILE = "/home/pi/cinemate/src/settings.json"
_SETTINGS: dict | None = None


def _settings() -> dict:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = load_settings(SETTINGS_FILE)
    return _SETTINGS

_READY_RX   = re.compile(r"Encoder configured")      # line printed by DngEncoder
_READY_WAIT = 2.0                                   # seconds to wait for all cams
_PI4_MODEL_MARKERS = (
    "Raspberry Pi 4",
    "Raspberry Pi 400",
    "Compute Module 4",
)
_PI4_PACKED_MODE_SENSORS = {"imx296", "imx296_mono", "imx477"}


def _read_pi_model() -> str:
    try:
        with open("/proc/device-tree/model", "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _is_pi4_family() -> bool:
    model = _read_pi_model()
    return any(marker in model for marker in _PI4_MODEL_MARKERS)


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


def _active_framebuffer_size(device_no: int = 0):
    fb = Framebuffer(device_no)
    if fb.usable:
        return fb.size
    return None

# ───────────────────────── zoom default ──────────────────────────
def _seed_default_zoom(redis_ctl):
    """
    Write preview.default_zoom to Redis once per boot, but
    only if the key doesn’t exist yet.
    """
    preview_cfg  = _settings().get("preview", {})
    default_zoom = float(preview_cfg.get("default_zoom", 1.0))

    if redis_ctl.get_value(ParameterKey.ZOOM.value) is None:
        redis_ctl.set_value(ParameterKey.ZOOM.value, default_zoom)
        # wake cinepi-raw controller
        redis_ctl.r.publish("cp_controls", ParameterKey.ZOOM.value)
        logging.info("[init] preview zoom defaulted to %.1f×", default_zoom)


def _plain_arecord_timecode_offset_frames(settings: dict | None = None) -> int:
    """Return the timecode offset for the 16-bit plain-arecord fallback path."""
    audio_cfg = (settings if settings is not None else _settings()).get("audio", {})
    # New nested format: audio.16bit.timecode_offset_frames
    # Fallback: old flat key plain_arecord_timecode_offset_frames
    raw_value = (
        audio_cfg.get("16bit", {}).get("timecode_offset_frames")
        if "16bit" in audio_cfg
        else audio_cfg.get("plain_arecord_timecode_offset_frames", 0)
    )
    if raw_value is None:
        raw_value = 0
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        logging.warning(
            "Invalid audio.16bit.timecode_offset_frames=%r; using 0",
            raw_value,
        )
        return 0


def _audio_timecode_offset_frames(settings: dict | None = None) -> int:
    """Return the timecode offset for the 24-bit USB dsnoop capture path."""
    audio_cfg = (settings if settings is not None else _settings()).get("audio", {})
    # New nested format: audio.24bit.timecode_offset_frames
    # Fallback: old flat key timecode_offset_frames
    raw_value = (
        audio_cfg.get("24bit", {}).get("timecode_offset_frames")
        if "24bit" in audio_cfg
        else audio_cfg.get("timecode_offset_frames", 0)
    )
    if raw_value is None:
        raw_value = 0
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        logging.warning(
            "Invalid audio.24bit.timecode_offset_frames=%r; using 0",
            raw_value,
        )
        return 0


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
        preview_enabled: bool = True,
    ):
        super().__init__(daemon=True)
        self.redis_controller = redis_controller
        self.sensor_detect = sensor_detect
        self.cam = cam
        self.primary = primary
        self.multi = multi
        self.preview_enabled = preview_enabled
        self.proc: Optional[subprocess.Popen] = None
        self.message = Event()
        self.out_q, self.err_q = Queue(), Queue()
        self.log_filters = {
            'frame': re.compile(r'Frame Number'),
            'stats': re.compile(r'^#\d+\s+\([^)]+ fps\)\s+exp\b'),
            'agc': re.compile(r'RPiAgc'),
            'ccm': re.compile(r'RPiCcm'),
            'vu': re.compile(r'\[VU\]'),
        }
        self.active_filters = set(self.log_filters)
        
        # ── NEW: detect the “DNG written:” line that dng_encoder now prints
        self.dng_rx = re.compile(r'DNG written:\s*(\S+\.dng)')
        self.redis_channel = 'cinepi.last_dng'          # publish JSON here
        
        # load per-camera geometry from settings
        settings = _settings()
        geo = settings.get('geometry', {})
        self.geometry = geo.get(self.cam.port, {})
        
        # load per-camera output settings (e.g., HDMI port)
        out_cfg = settings.get('output', {})
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
                return
        logging.info('[%s] %s', self.cam.port, text)
        
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
        return _is_pi4_family()

    def _build_args(self):
        # base resolution
        sensor_mode = int(self.redis_controller.get_value(ParameterKey.SENSOR_MODE.value) or 0)
        model_key = self.cam.name + ('_mono' if self.cam.is_mono else '')
        res = self.sensor_detect.get_resolution_info(model_key, sensor_mode)
        width = res.get('width', 1920)
        height = res.get('height', 1080)
        bit_depth = res.get('bit_depth', 12)
        packing = res.get('packing', 'U')

        if self._is_pi4() and model_key in _PI4_PACKED_MODE_SENSORS:
            logging.info(
                "[%s] Pi 4-family raw path detected for %s; using packed mode",
                self.cam.port,
                model_key,
            )
            packing = 'P'
        
        # lores & preview
        aspect = width / height
        anam = float(self.redis_controller.get_value(ParameterKey.ANAMORPHIC_FACTOR.value) or 1.0)
        
        # Get HDMI resolution from settings, but prefer the active
        # framebuffer mode when HDMI is already attached.
        hdmi_config = _settings().get("hdmi_display", {})
        fw, fh = hdmi_config.get("width", 1920), hdmi_config.get("height", 1080)
        try:
            fw = int(fw)
            fh = int(fh)
        except (TypeError, ValueError):
            fw, fh = 1920, 1080

        active_fb_size = _active_framebuffer_size()
        if active_fb_size is not None and active_fb_size != (fw, fh):
            logging.info(
                "[%s] Active framebuffer %sx%s overrides configured HDMI canvas %sx%s",
                self.cam.port,
                active_fb_size[0],
                active_fb_size[1],
                fw,
                fh,
            )
            fw, fh = active_fb_size
        
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

        plain_arecord_timecode_offset = _plain_arecord_timecode_offset_frames()
        if plain_arecord_timecode_offset != 0:
            logging.info(
                "[%s] Plain arecord WAV timecode offset: %+d frames",
                self.cam.port,
                plain_arecord_timecode_offset,
            )
            args += [
                "--plain-arecord-timecode-offset-frames",
                str(plain_arecord_timecode_offset),
            ]

        audio_timecode_offset = _audio_timecode_offset_frames()
        if audio_timecode_offset != 0:
            logging.info(
                "[%s] Audio WAV timecode offset (24-bit path): %+d frames",
                self.cam.port,
                audio_timecode_offset,
            )
            args += [
                "--audio-timecode-offset-frames",
                str(audio_timecode_offset),
            ]

        # ── DNG-writer CPU isolation ────────────────────────────────────────
        # The audio capture helper (cinepi-audio-capture) pins itself to the
        # last CPU core and raises to SCHED_FIFO priority 80 so USB audio
        # interrupts are always serviced on a core that DNG writers never touch.
        # Tell the DNG encode and disk workers to stay off that last core so
        # the isolation is complete. On a Pi 4/5 (4 cores): audio→CPU3,
        # DNG workers→CPUs 0-2.
        n_cpus = os.cpu_count() or 4
        if n_cpus > 1:
            dng_cpus = ",".join(str(i) for i in range(n_cpus - 1))
            args += [
                "--encode-affinity", dng_cpus,
                "--disk-affinity",   dng_cpus,
            ]
            logging.info(
                "[%s] DNG worker affinity: CPUs %s (audio capture on CPU %d)",
                self.cam.port, dng_cpus, n_cpus - 1,
            )

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
        
        if self.preview_enabled and not (self.multi and not self.primary):
            args += ['-p', f'{ox},{oy},{pw},{ph}']
        else:
            args += ['--nopreview']
            
        storage_fs = self.redis_controller.get_value(
            ParameterKey.STORAGE_FILESYSTEM.value,
            "none",
        )
        profile_name = recorder_profile_name_for_filesystem(storage_fs)
        profile = recorder_profile_for_filesystem(storage_fs)
        if self.redis_controller.get_value(ParameterKey.STORAGE_RECORDER_PROFILE.value) != profile_name:
            self.redis_controller.set_value(
                ParameterKey.STORAGE_RECORDER_PROFILE.value,
                profile_name if profile_name != DEFAULT_RECORDER_PROFILE else "default",
            )
        logging.info(
            "[%s] Storage recorder profile: filesystem=%s profile=%s label=%s "
            "encode_workers=%s disk_workers=%s",
            self.cam.port,
            storage_fs,
            profile_name,
            profile["label"],
            profile["encode_workers"],
            profile["disk_workers"],
        )
        args += recorder_profile_args(storage_fs)

        # ── Camera raw-buffer headroom ────────────────────────────────────
        # More in-flight camera buffers absorb transient disk-write latency
        # spikes that would otherwise starve the sensor and drop a single frame
        # (visible as a one-tick hole in the DNG timecode). The base value is
        # per storage profile — slower/spikier filesystems (exFAT, NTFS) get
        # more headroom than ext4 — and can be overridden globally via
        # settings.json camera.raw_buffer_count. Each extra buffer is ~25 MB of
        # CMA at 4K; too high exhausts CMA and the camera fails to start, so
        # confirm headroom with `grep Cma /proc/meminfo` before raising.
        try:
            buffer_count = int(profile.get("buffer_count", 8))
        except (TypeError, ValueError):
            buffer_count = 8
        try:
            override = int(
                (_settings().get("camera", {}) or {}).get("raw_buffer_count", 0) or 0
            )
            if override > 0:
                buffer_count = override
        except (TypeError, ValueError):
            logging.warning(
                "[%s] Invalid camera.raw_buffer_count in settings; using profile default %d",
                self.cam.port,
                buffer_count,
            )
        logging.info(
            "[%s] Camera raw-buffer headroom: --buffer-count %d (profile %s)",
            self.cam.port,
            buffer_count,
            profile_name,
        )
        args += ["--buffer-count", str(buffer_count)]

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
        self.preview_enabled = True

    # ───────────────────────── public api ──────────────────────────
    def start_cinepi_process(self, preview_enabled: Optional[bool] = None):
        self.start_all(preview_enabled=preview_enabled)

    def restart(self, preview_enabled: Optional[bool] = None):
        self.stop_all()
        self.start_all(preview_enabled=preview_enabled)

    def shutdown(self):
        self.stop_all()
        
    # ────────────────────────── start / stop ──────────────────────────
    def start_all(self, preview_enabled: Optional[bool] = None) -> None:
        """Discover sensors, launch one *cinepi-raw* each, wait for readiness."""
        if preview_enabled is not None:
            self.preview_enabled = bool(preview_enabled)

        self.stop_all()                              # clean previous run
        
        # ------------------------------------------------------------------
        # Seed the zoom factor before cinepi-raw processes read it
        # ------------------------------------------------------------------
        _seed_default_zoom(self.redis_controller)

        # ── 1. discovery ───────────────────────────────────────────
        cams = discover_cameras()                    # helper unchanged


        # ── Pi 4 sanity check ────────────────────────────────────────────
        if _is_pi4_family():
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
            ParameterKey.PACKING.value,
            ParameterKey.FPS_MAX.value,
            ParameterKey.GUI_LAYOUT.value,
        ):
            self.redis_controller.set_value(k, res.get(k))
        self.redis_controller.set_value(
            ParameterKey.MODE.value,
            f"{res.get('width')}:{res.get('height')}:{res.get('bit_depth')}:{res.get('packing', 'U')}",
        )

        # ── 3. launch all cinepi-raw instances ───────────────────────────
        multi = len(cams) > 1
        for i, cam in enumerate(cams):
            proc = CinePiProcess(
                self.redis_controller,
                self.sensor_detect,
                cam,
                primary=(i == 0),
                multi=multi,
                preview_enabled=self.preview_enabled,
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
            p.join(timeout=1.0)
            if p.is_alive():
                logging.warning("[%s] cinepi-raw wrapper thread did not stop within 1.0s", p.cam)
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
