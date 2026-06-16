import subprocess
import re
import logging
import json
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_SENSOR_DATABASE_FILE = "resources/sensors.json"
FALLBACK_PACKING_INFO = {
    "imx296": "U",
    "imx283": "U",
    "imx477": "U",
    "imx519": "P",
    "imx585": "U",
    "imx585_mono": "U",
}


class SensorDetect:
    def __init__(self, settings=None):
        self.camera_model = None
        self.res_modes = {}
        self.settings = settings or {}
        res_cfg = self.settings.get("resolutions", {})
        self.k_steps = res_cfg.get("k_steps", [])
        self.bit_depths = res_cfg.get("bit_depths", [])
        self.custom_modes = res_cfg.get("custom_modes", {})
        sensor_cfg = self.settings.get("sensors", {})
        self.sensor_database_file = sensor_cfg.get(
            "database_file",
            DEFAULT_SENSOR_DATABASE_FILE,
        )
        self.sensor_database = self._load_sensor_database()
        # Detected resolutions per camera will be stored here
        self.sensor_resolutions = {}

        # Packing information per sensor (U = unpacked, P = packed).
        self.packing_info = self._packing_info_from_database()

        # Populate camera model and modes on startup
        self.detect_camera_model()

    def _resolve_repo_path(self, path_value: str) -> Path:
        path = Path(path_value or DEFAULT_SENSOR_DATABASE_FILE)
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parents[2] / path

    def _load_sensor_database(self) -> dict[str, Any]:
        path = self._resolve_repo_path(self.sensor_database_file)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            logging.warning("Sensor database unavailable (%s): %s", path, exc)
            return {"schema_version": 1, "sensors": {}}
        except json.JSONDecodeError as exc:
            logging.warning("Sensor database is invalid JSON (%s): %s", path, exc)
            return {"schema_version": 1, "sensors": {}}

        if not isinstance(data.get("sensors"), dict):
            logging.warning("Sensor database %s has no sensors object", path)
            return {"schema_version": 1, "sensors": {}}
        return data

    def _packing_info_from_database(self) -> dict[str, str]:
        packing = dict(FALLBACK_PACKING_INFO)
        for sensor_id, sensor_info in self.sensor_database.get("sensors", {}).items():
            if not isinstance(sensor_info, dict):
                continue
            sensor_packing = sensor_info.get("packing")
            if not sensor_packing:
                continue
            sensor_key = str(sensor_id).strip().lower()
            packing[sensor_key] = str(sensor_packing)
            for alias in sensor_info.get("aliases", []) or []:
                packing[str(alias).strip().lower()] = str(sensor_packing)
        return packing

    def _sensor_database_entry(self, camera_name: str | None) -> dict[str, Any] | None:
        camera_key = str(camera_name or "").strip().lower()
        if not camera_key:
            return None

        sensors = self.sensor_database.get("sensors", {})
        direct = sensors.get(camera_key)
        if isinstance(direct, dict):
            return direct

        base_key = camera_key[:-5] if camera_key.endswith("_mono") else camera_key
        direct = sensors.get(base_key)
        if isinstance(direct, dict):
            return direct

        for sensor_info in sensors.values():
            if not isinstance(sensor_info, dict):
                continue
            aliases = {
                str(alias).strip().lower()
                for alias in sensor_info.get("aliases", []) or []
            }
            if camera_key in aliases:
                return sensor_info
        return None

    def _sensor_mode_metadata(
        self,
        camera_name: str | None,
        width: int,
        height: int,
        bit_depth: int | None,
    ) -> dict[str, Any]:
        sensor_info = self._sensor_database_entry(camera_name)
        if not sensor_info:
            return {}

        for mode_info in sensor_info.get("modes", []) or []:
            if not isinstance(mode_info, dict):
                continue
            if int(mode_info.get("width", 0) or 0) != int(width):
                continue
            if int(mode_info.get("height", 0) or 0) != int(height):
                continue
            mode_bit_depth = mode_info.get("bit_depth")
            if (
                bit_depth is not None
                and mode_bit_depth is not None
                and int(mode_bit_depth) != int(bit_depth)
            ):
                continue
            return mode_info
        return {}

    def _mode_from_metadata_or_detected(
        self,
        *,
        camera_name: str,
        width: int,
        height: int,
        bit_depth: int | None,
        fps_max: int | None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = self._sensor_mode_metadata(camera_name, width, height, bit_depth)
        sensor_info = self._sensor_database_entry(camera_name) or {}
        extra = extra or {}
        packing = (
            extra.get("packing")
            or metadata.get("packing")
            or sensor_info.get("packing")
            or self.packing_info.get(camera_name, "U")
        )
        bpp = bit_depth / 8 if bit_depth else 2
        file_size = extra.get("file_size_mb", round(width * height * bpp / (1024 * 1024), 1))
        fps_max_value = fps_max if fps_max is not None else extra.get("fps_max", metadata.get("max_fps"))
        mode = {
            "aspect": extra.get("aspect", metadata.get("aspect", round(width / height, 2))),
            "width": width,
            "height": height,
            "bit_depth": bit_depth,
            "packing": packing,
            "fps_max": fps_max_value,
            "gui_layout": extra.get("gui_layout", metadata.get("gui_layout", 0)),
            "file_size": file_size,
        }
        sustainable_fps = extra.get("sustainable_fps", metadata.get("sustainable_fps"))
        if sustainable_fps:
            mode["sustainable_fps"] = sustainable_fps
        return mode

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
            sensors[current_cam].append(
                self._mode_from_metadata_or_detected(
                    camera_name=current_cam,
                    width=width,
                    height=height,
                    bit_depth=current_bit_depth,
                    fps_max=fps_max,
                )
            )

        # ── add any user-defined custom modes ──────────────────────
        for cam, extras in self.custom_modes.items():
            sensors.setdefault(cam, [])
            for extra in extras:
                w, h = int(extra["width"]), int(extra["height"])
                bd   = int(extra["bit_depth"])
                fps  = extra.get("fps_max")
                sensors[cam].append(
                    self._mode_from_metadata_or_detected(
                        camera_name=cam,
                        width=w,
                        height=h,
                        bit_depth=bd,
                        fps_max=fps,
                        extra=extra,
                    )
                )

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

    def get_sustainable_fps(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('sustainable_fps', [])
    
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
