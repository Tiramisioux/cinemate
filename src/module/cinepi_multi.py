import subprocess
import logging
import re
import json
import time
from queue import Queue
from threading import Thread
from typing import List, Optional

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
        return 'cam0' if 'i2c@80000' in self.path else 'cam1'

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


def discover_cameras(timeout: float = 10.0, interval: float = 1.0) -> List[CameraInfo]:
    """Run `cinepi-raw --list-cameras` repeatedly until at least one sensor is found or the timeout expires."""
    rx = re.compile(r'^\s*(\d+)\s*:\s*(\w+)\s*\[([^]]+)\]\s*\(([^)]+)\)')
    end = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < end:
        attempt += 1
        proc = subprocess.run(['cinepi-raw', '--list-cameras'], text=True, capture_output=True)
        cams: List[CameraInfo] = []
        for line in (proc.stdout or '').splitlines():
            m = rx.match(line)
            if m:
                idx, name, fmt, path = m.groups()
                cams.append(CameraInfo(int(idx), name, fmt, path))
        if cams:
            logging.info('Discovered cameras on attempt %d: %s', attempt, cams)
            return cams
        logging.warning('Attempt %d failed (%s); retrying', attempt, proc.returncode)
        time.sleep(interval)
    logging.error('Camera discovery timed out')
    return []

# ────────────────── cinepi‑raw subprocess wrapper ─────────
class CinePiProcess(Thread):
    """Wrap one cinepi‑raw process bound to a single sensor."""

    def __init__(self, redis, sensor_detect, cam: CameraInfo, primary: bool, multi: bool):
        super().__init__(daemon=True)
        self.redis = redis
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

    # ---------------------------------------------------------------- Thread
    def run(self):
        cmd = ['cinepi-raw'] + self._build_args()
        logging.info('[%s] Launch: %s', self.cam, cmd)
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        Thread(target=self._pump, args=(self.proc.stdout, self.out_q)).start()
        Thread(target=self._pump, args=(self.proc.stderr, self.err_q)).start()
        self.proc.wait()
        logging.info('[%s] exited %s', self.cam, self.proc.returncode)

    # ------------------------------------------------------ log/queue helpers
    def _pump(self, pipe, q):
        for raw in iter(pipe.readline, b''):
            line = raw.decode('utf-8', 'replace').rstrip()
            q.put(line)
            self.message.emit(line)
            self._log(line)
        pipe.close()

    def _log(self, text):
        for name, rx in self.log_filters.items():
            if name in self.active_filters and rx.search(text):
                logging.info('[%s] %s', self.cam, text)
                break

    # ------------------------------------------------------ argument builder
    def _build_args(self):
        # ---- base resolution info (from redis + SensorDetect)
        sensor_mode = int(self.redis.get_value('sensor_mode') or 0)
        model_key = self.cam.name + ('_mono' if self.cam.is_mono else '')
        res = self.sensor_detect.get_resolution_info(model_key, sensor_mode)
        width = res.get('width', 1920)
        height = res.get('height', 1080)
        bit_depth = res.get('bit_depth', 12)
        packing = res.get('packing', 'U')

        # Force packed data for mono sensors or special Pi‑4/imx477 override
        pi_model = self.redis.get_value('pi_model') or ''
        if self.cam.is_mono:
            packing = 'P'
        if pi_model == 'pi4' and model_key == 'imx477':
            packing = 'P'

        # ---- lores / preview geometry (mirrors original get_default_args)
        aspect_ratio = width / height
        anamorphic = float(self.redis.get_value('anamorphic_factor') or 1.0)
        frame_w, frame_h = 1920, 1080
        pad_x, pad_y = 94, 50
        avail_w, avail_h = frame_w - 2 * pad_x, frame_h - 2 * pad_y

        lores_h = min(720, avail_h)
        lores_w = int(lores_h * aspect_ratio * anamorphic)
        if lores_w > avail_w:
            lores_w = avail_w
            lores_h = int(round(lores_w / (aspect_ratio * anamorphic)))

        self.redis.set_value('lores_width', lores_w)
        self.redis.set_value('lores_height', lores_h)

        prev_w, prev_h = lores_w, lores_h  # same heuristic as original
        if (avail_w / avail_h) > aspect_ratio:
            prev_h = avail_h
            prev_w = int(prev_h * aspect_ratio)
        else:
            prev_w = avail_w
            prev_h = int(prev_w / aspect_ratio)
        prev_x = (frame_w - prev_w) // 2
        prev_y = (frame_h - prev_h) // 2

        # ---- colour gains / shutter etc.
        cg_rb = self.redis.get_value('cg_rb') or '2.5,2.2'

        # ---- HDMI port mapping
        hdmi_port = '0' if self.cam.port == 'cam0' else '1'

        # ---- Build final arg list
        args = [
            '--camera', str(self.cam.index),
            '--mode', f'{width}:{height}:{bit_depth}:{packing}',
            '--width', str(width), '--height', str(height),
            '--lores-width', str(lores_w), '--lores-height', str(lores_h),
            '--hdmi-port', hdmi_port,
            '--awb', 'auto', '--awbgains', cg_rb,
            '--post-process-file', '/home/pi/post-processing.json',
            '--shutter', '20000',
        ]

        args += ['-p', f'{prev_x},{prev_y},{prev_w},{prev_h}']

        # if not (self.multi and not self.primary):
        #     args += ['-p', f'{prev_x},{prev_y},{prev_w},{prev_h}']
        # else:
        #     pass
        #     # args += ['--nopreview']

        return args

    # ------------------------------------------------------ stop helper
    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

# ───────────────────────── Manager ───────────────────────
class CinePiManager:
    def __init__(self, redis, sensor_detect):
        self.redis = redis
        self.sensor_detect = sensor_detect
        self.processes: List[CinePiProcess] = []
        self.message = Event()

    # ------------------------------------------------ start/stop helpers
    def start_all(self):
        self.stop_all()
        cams = discover_cameras()
        cams.sort(key=lambda c: c.port)  # cam0 first, then cam1
        self.redis.set_value('cameras', json.dumps([c.as_dict() for c in cams]))
        if not cams:
            logging.error('No cameras – abort')
            return

        primary_key = cams[0].name + ('_mono' if cams[0].is_mono else '')
        self.sensor_detect.camera_model = primary_key
        self.sensor_detect.load_sensor_resolutions()
        self.redis.set_value('sensor', primary_key)

        multi = len(cams) > 1
        for i, cam in enumerate(cams):
            proc = CinePiProcess(self.redis, self.sensor_detect, cam, primary=(i == 0), multi=multi)
            proc.message.subscribe(self.message.emit)
            proc.start()
            # short stagger before launching next camera
            time.sleep(0.5)
            self.processes.append(proc)

    def stop_all(self):
        for p in self.processes:
            p.stop()
        for p in self.processes:
            p.join()
        self.processes.clear()

    # legacy API compatibility
    start_cinepi_process = start_all
    restart = lambda self: (self.stop_all(), self.start_all())
    shutdown = stop_all

    # ------------------------------------------------ misc helpers
    def set_log_level(self, lvl: str):
        logging.getLogger().setLevel(getattr(logging, lvl.upper(), logging.INFO))

    def set_active_filters(self, filters):
        for p in self.processes:
            p.active_filters = set(filters)
