import subprocess
import re
import logging
from pathlib import Path
from typing import Tuple, Dict, Optional

class SensorDetect:
    def __init__(self, settings=None):
        self.camera_model = None
        self.res_modes = {}
        self.settings = settings or {}
        res_cfg = self.settings.get("resolutions", {})
        self.k_steps = res_cfg.get("k_steps", [])
        self.bit_depths = res_cfg.get("bit_depths", [])
        self.custom_modes = res_cfg.get("custom_modes", {})
        # Detected resolutions per camera will be stored here
        self.sensor_resolutions = {}

        # Packing information per sensor (U = unpacked, P = packed)
        self.packing_info = {
            "imx296": "U",
            "imx283": "U",
            "imx477": "U",
            "imx519": "P",
            "imx585": "U",
            "imx585_mono": "U",
        }

        # Optional fps correction factors per sensor and sensor mode
        self.fps_correction_factors = {
            "imx296": {0: 1.0, 1: 1.0, 2: 1.0},
            "imx286": {0: 1.0, 1: 1.0, 2: 1.0},
            "imx477": {0: 1.0, 1: 1.0, 2: 1.0},
            "imx519": {0: 1.0, 1: 1.0, 2: 1.0},
            "imx585": {0: 1.0, 1: 1.0, 2: 1.0},
            "imx585_mono": {0: 1.0, 1: 1.0, 2: 1.0},
        }

        # Cache detected sensor subdevice
        self._sensor_subdevice: Optional[str] = None

        # Populate camera model and modes on startup
        self.detect_camera_model()

    # ────────────────────────────────────────────────────────────────
    #  1.  Parse *all* cameras and all modes that cinepi-raw reports    
    # ────────────────────────────────────────────────────────────────
    def _parse_cinepi_output(self, output: str) -> Dict[str, Dict[int, Dict]]:
        """
        Return a mapping   {camera_model → {mode_index → mode_dict}}
        covering every camera found in the *cinepi-raw --list-cameras* output.
        A mono sensor is reported as “<model>_mono”.
        """

        sensors: Dict[str, List[Dict]] = {}
        current_cam = None
        current_bit_depth = None
        parsing_modes = False                     # inside a “Modes:” block?

        for raw in output.splitlines():
            line = raw.rstrip("\n")

            # ── camera header  e.g.  “0 : imx283 [5472x3648 …] (…)”
            m = re.match(r"^\s*\d+\s*:\s*([^\s]+)(?:\s*\[.*?(MONO)?\])?", line)
            if m:
                # flush state & start a new camera section
                current_cam = m.group(1)
                if m.group(2) == "MONO":
                    current_cam += "_mono"
                sensors.setdefault(current_cam, [])
                current_bit_depth = None
                parsing_modes = False
                continue

            # we can’t do anything without a current camera
            if current_cam is None:
                continue

            # ── “Modes:” line starts (or continues) a mode list
            if "Modes:" in line:
                parsing_modes = True  # don’t *continue* – this line may
                # already contain format + resolution

            if not parsing_modes:
                continue

            # ── format / bit-depth (may share the line with a resolution)
            fmt = re.search(r"'(?:SRGGB|R|GREY|Y)(\d+)", line)
            if fmt:
                current_bit_depth = int(fmt.group(1))

            # ── first resolution on the line (if any)
            res = re.search(r"(\d+)x(\d+)", line)
            if not res:
                continue

            width, height = map(int, res.groups())
            fps = re.search(r"\[(\d+(?:\.\d+)?)\s*fps", line)
            fps_max = int(float(fps.group(1))) if fps else None

            packing = self.packing_info.get(current_cam, "U")
            bpp = current_bit_depth / 8 if current_bit_depth else 2
            file_sz = round(width * height * bpp / (1024 * 1024), 1)

            sensors[current_cam].append({
                "aspect"    : round(width / height, 2),
                "width"     : width,
                "height"    : height,
                "bit_depth" : current_bit_depth,
                "packing"   : packing,
                "fps_max"   : fps_max,
                "gui_layout": 0,
                "file_size" : file_sz,
            })

        # ── add any user-defined custom modes ──────────────────────
        for cam, extras in self.custom_modes.items():
            sensors.setdefault(cam, [])
            for extra in extras:
                w, h = int(extra["width"]), int(extra["height"])
                bd   = int(extra["bit_depth"])
                fps  = extra.get("fps_max")
                pack = self.packing_info.get(cam, "U")
                file_sz = round(w * h * (bd / 8) / (1024 * 1024), 1)
                sensors[cam].append({
                    "aspect"    : round(w / h, 2),
                    "width"     : w,
                    "height"    : h,
                    "bit_depth" : bd,
                    "packing"   : pack,
                    "fps_max"   : fps,
                    "gui_layout": 0,
                    "file_size" : file_sz,
                })

        # ── filter & index (k-steps / bit depths) ───────────────────
        pruned: Dict[str, Dict[int, Dict]] = {}
        for cam, modes in sensors.items():
            selected = []
            for m in modes:
                if self.bit_depths and m["bit_depth"] not in self.bit_depths:
                    continue
                k_val = round(m["width"] / 1000 * 2) / 2
                if self.k_steps and k_val not in self.k_steps:
                    continue
                selected.append(m)

            # ⚑ NEW: never leave a camera without modes
            if not selected:
                logging.warning("No modes passed the filters for %s – "
                                "keeping full list instead", cam)
                selected = modes

            pruned[cam] = {i: m for i, m in enumerate(reversed(selected))}
        return pruned


    # ────────────────────────────────────────────────────────────────
    #  2.  Discover sensors once, cache every model’s modes
    # ────────────────────────────────────────────────────────────────
    def detect_camera_model(self):
        """
        Runs *cinepi-raw --list-cameras*, fills ``self.sensor_resolutions`` with
        **all** detected cameras, and chooses the first one as
        ``self.camera_model`` (the caller may later override this).
        """
        try:
            proc = subprocess.run(
                "cinepi-raw --list-cameras",
                shell=True, capture_output=True, text=True
            )
            out = proc.stdout or ""
            logging.info("cinepi-raw output:\n%s", out)

            if not out.strip():
                logging.warning("No output from cinepi-raw")
                self.camera_model = None
                self.res_modes = {}
                return

            # full parse → {model → {mode_idx → mode_dict}}
            sensors = self._parse_cinepi_output(out)

            if not sensors:
                logging.warning("No cameras parsed")
                self.camera_model = None
                self.res_modes = {}
                return

            # merge (allows hot-plug re-detect)
            self.sensor_resolutions.update(sensors)

            # choose a default model if the current one isn’t valid
            if self.camera_model not in sensors:
                self.camera_model = next(iter(sensors))

            logging.info("Detected camera models: %s (default: %s)",
                         list(sensors.keys()), self.camera_model)

            self.load_sensor_resolutions()      # sets self.res_modes

        except Exception as e:
            logging.error("detect_camera_model() failed: %s", e)
            self.camera_model = None
            self.res_modes = {}

    def check_camera(self):
        self.detect_camera_model()
        return self.camera_model

    def load_sensor_resolutions(self):
        if self.camera_model in self.sensor_resolutions:
            self.res_modes = self.sensor_resolutions[self.camera_model]
        else:
            logging.error(f"Unknown camera model: {self.camera_model}")
            self.res_modes = {}

    def get_sensor_resolution(self, mode):
        return self.res_modes.get(mode, {})
    
    def get_resolution_info(self, camera_name: str, sensor_mode: int) -> Dict:
        """
        Return mode dict for *camera_name* and *sensor_mode*.
        If the requested mode is missing, fall back to the first available
        mode so callers always get valid width/height/fps values.
        """
        if camera_name not in self.sensor_resolutions:
            logging.error("Unknown camera model: %s", camera_name)
            return {'width': None, 'height': None, 'fps_max': None,
                    'gui_layout': None}

        modes = self.sensor_resolutions[camera_name]
        sensor_mode = int(sensor_mode)

        if sensor_mode not in modes:
            logging.warning("Sensor mode %d not found for %s – "
                            "using mode 0 instead", sensor_mode, camera_name)
            return next(iter(modes.values()))  # first (usually 0)

        return modes[sensor_mode]


    def get_fps_max(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('fps_max', None)
    
    def get_gui_layout(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('gui_layout', None)
    
    def get_width(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('width', None)
    
    def get_height(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('height', None)
    
    def get_bit_depth(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('bit_depth', None)
    
    def get_packing(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('packing', None)

    
    def get_file_size(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('file_size', None)
    
    def get_lores_width(self, camera_name, sensor_mode):
        # Placeholder method, replace with actual implementation
        return 1280
    
    def get_lores_height(self, camera_name, sensor_mode):
        # Placeholder method, replace with actual implementation
        return 720
    
    def get_available_resolutions(self):
        resolutions = []
        for mode, info in self.res_modes.items():
            resolution = f"{info['width']} : {info['height']} : {info['bit_depth']}b"
            resolutions.append({'mode': mode, 'resolution': resolution})
        return resolutions

    # ────────────────────────────────────────────────────────────────
    #  Sensor timing helpers (v4l2 + media controller)
    # ────────────────────────────────────────────────────────────────
    def _run_command(self, command):
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            logging.error("Command not found: %s", command[0])
            return None

        if result.returncode != 0:
            logging.debug("Command failed (%s): %s", result.returncode, " ".join(command))
            return None

        return result.stdout.strip()

    def _find_sensor_subdevice(self) -> Optional[str]:
        if self._sensor_subdevice and Path(self._sensor_subdevice).exists():
            return self._sensor_subdevice

        for subdev in sorted(Path("/dev").glob("v4l-subdev*")):
            output = self._run_command(["v4l2-ctl", "-d", str(subdev), "-l"])
            if output and "vertical_blanking" in output:
                self._sensor_subdevice = str(subdev)
                logging.debug("Detected sensor subdevice: %s", self._sensor_subdevice)
                return self._sensor_subdevice

        logging.warning("Unable to locate sensor subdevice with vertical_blanking control")
        self._sensor_subdevice = None
        return None

    def _read_control_int(self, subdevice: str, control: str) -> Optional[int]:
        output = self._run_command(["v4l2-ctl", "-d", subdevice, f"--get-ctrl={control}"])
        if not output:
            return None

        match = re.search(r"(-?\d+)", output)
        if not match:
            logging.debug("Could not parse %s from output: %s", control, output)
            return None

        return int(match.group(1))

    def _get_active_sensor_size(self, subdevice: str) -> Tuple[Optional[int], Optional[int]]:
        output = self._run_command(["media-ctl", "-p"])
        if not output:
            return None, None

        subdev_name = Path(subdevice).name
        pattern = re.compile(rf"entity\s+\d+:.*\({re.escape(subdev_name)}\)(.*?)(?:\n\n|$)", re.DOTALL)
        match = pattern.search(output)
        if not match:
            logging.debug("media-ctl output did not contain block for %s", subdevice)
            return None, None

        block = match.group(1)
        fmt_match = re.search(r"fmt:\s*\S+\s+(\d+)x(\d+)", block)
        if not fmt_match:
            logging.debug("No format information found in media-ctl block for %s", subdevice)
            return None, None

        width, height = map(int, fmt_match.groups())
        return width, height

    def _calculate_dynamic_fps_factor(self, camera_name: str, sensor_mode: int) -> Optional[float]:
        subdevice = self._find_sensor_subdevice()
        if not subdevice:
            return None

        vblank = self._read_control_int(subdevice, "vertical_blanking")
        pixel_rate = self._read_control_int(subdevice, "pixel_rate")
        if vblank is None or pixel_rate in (None, 0):
            logging.debug("Missing vblank or pixel rate (vblank=%s, pixel_rate=%s)", vblank, pixel_rate)
            return None

        width, height = self._get_active_sensor_size(subdevice)
        if width is None:
            width = self.get_width(camera_name, sensor_mode)
        if height is None:
            height = self.get_height(camera_name, sensor_mode)

        if width in (None, 0) or height in (None, 0):
            logging.debug("Unable to determine sensor dimensions (width=%s, height=%s)", width, height)
            return None

        line_length = self._read_control_int(subdevice, "line_length_pixels")
        if line_length in (None, 0):
            hblank = self._read_control_int(subdevice, "horizontal_blanking")
            line_length = width + hblank if hblank not in (None, 0) else None

        if line_length in (None, 0):
            logging.debug("Unable to determine line length (width=%s)", width)
            return None

        frame_lines = height + vblank
        if frame_lines <= 0:
            logging.debug("Invalid frame lines computed: %s", frame_lines)
            return None

        fps_actual = pixel_rate / (line_length * frame_lines)
        if fps_actual <= 0:
            return None

        fps_nominal = self.get_fps_max(camera_name, sensor_mode)
        if not fps_nominal:
            return None

        factor = fps_actual / float(fps_nominal)
        if factor <= 0:
            return None

        # Guard against wildly inaccurate readings (e.g. when the sensor
        # reports stale blanking values during a mode switch).  A factor far
        # outside a reasonable ±50% window would push the controller to
        # extreme FPS requests which then cascade into dropped frames.
        if not 0.5 <= factor <= 1.5:
            logging.warning(
                "Discarding unrealistic FPS correction factor: camera=%s mode=%s "
                "actual=%.6f nominal=%s factor=%.8f",
                camera_name,
                sensor_mode,
                fps_actual,
                fps_nominal,
                factor,
            )
            return None

        logging.debug("Calculated FPS correction factor: camera=%s mode=%s actual=%.6f nominal=%s factor=%.8f",
                      camera_name, sensor_mode, fps_actual, fps_nominal, factor)

        return factor

    def get_fps_correction_factor(self, camera_name, sensor_mode):
        try:
            mode = int(sensor_mode)
        except (TypeError, ValueError):
            mode = sensor_mode

        dynamic_factor = self._calculate_dynamic_fps_factor(camera_name, mode)
        if dynamic_factor is not None:
            sensor_entry = self.fps_correction_factors.setdefault(camera_name, {})
            if isinstance(sensor_entry, dict):
                sensor_entry[mode] = dynamic_factor
            return dynamic_factor

        sensor_factors = self.fps_correction_factors.get(camera_name)
        if isinstance(sensor_factors, dict):
            return sensor_factors.get(mode, 1.0)

        # Fallback to scalar factors or the default 1.0 if no mapping is defined
        return sensor_factors if isinstance(sensor_factors, (int, float)) else 1.0
