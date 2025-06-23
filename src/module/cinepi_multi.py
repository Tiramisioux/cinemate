import subprocess
import logging
import re
import json
import time
from queue import Queue
from threading import Thread
from typing import List, Optional

from module.config_loader import load_settings
from module.redis_controller import ParameterKey

# Path to settings file
SETTINGS_FILE = "/home/pi/cinemate/src/settings.json"
# Load global settings
_SETTINGS = load_settings(SETTINGS_FILE)

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
        
        # map physical camera ports: i2c@88000 => cam0, i2c@80000 => cam1
        if 'i2c@88000' in self.path:
            return 'cam0'
        else:
            return 'cam1'

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
        
        # load per-camera geometry from settings
        geo = _SETTINGS.get('geometry', {})
        self.geometry = geo.get(self.cam.port, {})
        
        # load per-camera output settings (e.g., HDMI port)
        out_cfg = _SETTINGS.get('output', {})
        self.output = out_cfg.get(self.cam.port, {})

    def run(self):
        cmd = ['cinepi-raw'] + self._build_args()
        logging.info('[%s] Launch: %s', self.cam, cmd)
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        Thread(target=self._pump, args=(self.proc.stdout, self.out_q)).start()
        Thread(target=self._pump, args=(self.proc.stderr, self.err_q)).start()
        self.proc.wait()
        logging.info('[%s] exited %s', self.cam, self.proc.returncode)

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
                pass #logging.info('[%s] %s', self.cam, text)
                break

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
            '--camera', str(self.cam.index),
            '--mode', f'{width}:{height}:{bit_depth}:{packing}',
            '--width', str(width),
            '--height', str(height),
            '--lores-width', str(lw),
            '--lores-height', str(lh),
            '--hdmi-port', hd,
            '-p', f'{ox},{oy},{pw},{ph}',
            '--rotation', str(rot),
            '--hflip', str(hf),
            '--vflip', str(vf),
            '--tuning-file', tune,
            #'--post-process-file', post,
            '--shutter', '20000',
            '--awb', 'auto',
            '--awbgains', cg_rb,
        ]
        
        # if not (self.multi and not self.primary):
        #     args += ['-p', f'{ox},{oy},{pw},{ph}']
        # else:
        #     args += ['--nopreview']
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
    def __init__(self, redis_controller, sensor_detect):
        self.redis_controller = redis_controller
        self.sensor_detect = sensor_detect
        self.processes: List[CinePiProcess] = []
        self.message = Event()

    def start_all(self):
        self.stop_all()
        cams = discover_cameras()
        cams.sort(key=lambda c: c.port)
        self.redis_controller.set_value(ParameterKey.CAMERAS.value, json.dumps([c.as_dict() for c in cams]))
        if not cams:
            logging.error('No cameras - abort')
            return
        sensor_mode = int(self.redis_controller.get_value(ParameterKey.SENSOR_MODE.value) or 0)
        pk = cams[0].name + ('_mono' if cams[0].is_mono else '')
        self.sensor_detect.camera_model = pk
        self.sensor_detect.load_sensor_resolutions()
        self.redis_controller.set_value(ParameterKey.SENSOR.value, pk)
        res = self.sensor_detect.get_resolution_info(pk, sensor_mode)

        for k in (ParameterKey.WIDTH.value, ParameterKey.HEIGHT.value, ParameterKey.BIT_DEPTH.value, ParameterKey.FPS_MAX.value, ParameterKey.GUI_LAYOUT.value):
            self.redis_controller.set_value(k, res.get(k))
        multi = len(cams)>1

        for i, cam in enumerate(cams):
            proc = CinePiProcess(self.redis_controller, self.sensor_detect, cam, primary=(i==0), multi=multi)
            proc.message.subscribe(self.message.emit)
            proc.start()
            time.sleep(0.5)
            self.processes.append(proc)

    def stop_all(self):
        for p in self.processes: p.stop()
        for p in self.processes: p.join()
        self.processes.clear()
    
    start_cinepi_process = start_all
    restart = lambda self: (self.stop_all(), self.start_all())
    shutdown = stop_all
    
    def set_log_level(self, lvl: str):
        logging.getLogger().setLevel(getattr(logging, lvl.upper(), logging.INFO))
    
    def set_active_filters(self, filters):
        for p in self.processes: p.active_filters = set(filters)
