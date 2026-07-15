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

# Raspberry Pi models that run the VC4/Unicam camera receiver. On these the
# packed CSI2 modes are preferred (lower DMA/CMA than unpacked). This is the
# single canonical platform check; cinepi_multi and cinepi_controller both reach
# it through SensorDetect so the launch command and the GUI/telemetry agree.
PI4_MODEL_MARKERS = (
    "Raspberry Pi 4",
    "Raspberry Pi 400",
    "Compute Module 4",
)


def read_pi_model() -> str:
    try:
        with open("/proc/device-tree/model", "r") as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return ""


def is_pi4_family() -> bool:
    """True on any Raspberry Pi 4 / 400 / CM4 (VC4/Unicam) platform."""
    model = read_pi_model()
    return any(marker in model for marker in PI4_MODEL_MARKERS)


class SensorDetect:
    def __init__(self, settings=None):
        self.camera_model = None
        self.res_modes = {}
        self.settings = settings or {}
        res_cfg = self.settings.get("resolutions", {})
        self.k_steps = res_cfg.get("k_steps", [])
        self.bit_depths = res_cfg.get("bit_depths", [])
        # Modes slower than this (max fps) are dropped from the mode table.
        # Default 20 keeps the imx585 4K ClearHDR modes (~21.9 fps) visible.
        self.min_frame_rate = res_cfg.get("min_frame_rate", 20)
        self.custom_modes = res_cfg.get("custom_modes", {})
        # Optional ClearHDR (imx585) whitelist. Empty list = expose both the
        # plain and the HDR sensor modes; set to [false] in settings.json to
        # hide the HDR modes, or [true] to show only them. Mirrors the
        # bit_depths / k_steps whitelists above.
        self.hdr_modes = res_cfg.get("hdr", [])
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
        hdr: bool = False,
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
        if bit_depth == 16:
            # 16-bit modes (imx585 ClearHDR) are written as unpacked DNGs:
            # 2 bytes/pixel payload + ~100 KB header, in decimal MB so the
            # minutes-left math matches on-disk sizes (3856×2180 → 16.9 MB).
            file_size = extra.get(
                "file_size_mb", round((width * height * 2 + 100_000) / 1e6, 1)
            )
        else:
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
            # ClearHDR flag (imx585). A mode is HDR when it is reported only
            # by `cinepi-raw --list-cameras --hdr sensor`; selecting it makes
            # cinepi-raw launch with --hdr sensor. See detect_camera_model().
            "hdr": bool(extra.get("hdr", hdr)),
        }
        sustainable_fps = extra.get("sustainable_fps", metadata.get("sustainable_fps"))
        if sustainable_fps:
            mode["sustainable_fps"] = sustainable_fps
        return mode

    # ────────────────────────────────────────────────────────────────
    #  1.  Parse *all* cameras and all modes that cinepi-raw reports    
    # ────────────────────────────────────────────────────────────────
    def _parse_cinepi_output(self, output: str, hdr: bool = False) -> Dict[str, List[Dict]]:
        """
        Return a mapping   {camera_model → [mode_dict, …]}   covering every
        camera found in a single *cinepi-raw --list-cameras* run. A mono sensor
        is reported as “<model>_mono”. ``hdr`` tags every mode parsed from a
        ``--hdr sensor`` run; the caller merges the plain and HDR runs.
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
                    hdr=hdr,
                )
            )

        return sensors

    @staticmethod
    def _mode_key(mode: Dict) -> tuple:
        """Identity used to dedupe a mode across the plain and HDR runs."""
        return (
            int(mode.get("width") or 0),
            int(mode.get("height") or 0),
            int(mode.get("bit_depth") or 0),
            mode.get("fps_max"),
        )

    def _merge_mode_lists(
        self,
        base: Dict[str, List[Dict]],
        hdr: Dict[str, List[Dict]],
    ) -> Dict[str, List[Dict]]:
        """Combine the plain (non-HDR) and ``--hdr sensor`` mode lists.

        A mode reported by the HDR run is kept as HDR only when the plain run
        did not already report an identical (width, height, bit_depth, fps)
        mode. Sensors that ignore ``--hdr sensor`` therefore return the same
        modes twice and collapse back to a single non-HDR list, so only real
        ClearHDR sensors (imx585) gain HDR modes.
        """
        merged: Dict[str, List[Dict]] = {cam: list(modes) for cam, modes in base.items()}
        for cam, hdr_modes in hdr.items():
            base_keys = {self._mode_key(m) for m in merged.get(cam, [])}
            for mode in hdr_modes:
                if self._mode_key(mode) in base_keys:
                    continue
                merged.setdefault(cam, []).append(mode)
        return merged

    def _order_modes(self, selected: List[Dict]) -> List[Dict]:
        """Order a camera's filtered modes for the GUI mode table.

        Sensors that expose ClearHDR modes use the HDR-aware hierarchy the
        operator sees on an imx585: the plain modes first (12-bit, ascending
        resolution), then the 12-bit HDR modes, then the 16-bit HDR modes —
        i.e. ordered by (hdr, bit_depth, resolution). Sensors without HDR keep
        their long-standing order (reversed detection order) so imx477 / imx283
        / imx296 mode indices are unchanged.
        """
        if any(m.get("hdr") for m in selected):
            return sorted(
                selected,
                key=lambda m: (
                    bool(m.get("hdr")),
                    int(m.get("bit_depth") or 0),
                    int(m.get("width") or 0),
                    int(m.get("height") or 0),
                ),
            )
        return list(reversed(selected))

    def _finalize_modes(
        self,
        sensors: Dict[str, List[Dict]],
    ) -> Dict[str, Dict[int, Dict]]:
        """Add custom modes, apply the settings.json filters, order and index."""
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
                        hdr=bool(extra.get("hdr", False)),
                        extra=extra,
                    )
                )

        # ── filter & index (k-steps / bit depths / hdr) ─────────────
        pruned: Dict[str, Dict[int, Dict]] = {}
        for cam, modes in sensors.items():
            selected = []
            for m in modes:
                if self.bit_depths and m["bit_depth"] not in self.bit_depths:
                    continue
                # settings.json → resolutions.hdr: optional whitelist of the
                # ClearHDR flag. Empty = expose both; [false] hides HDR modes.
                if self.hdr_modes and bool(m.get("hdr")) not in self.hdr_modes:
                    continue
                # settings.json → resolutions.min_frame_rate: drop modes whose
                # max frame rate is below the floor (default 20 keeps the
                # imx585 4K ClearHDR modes at ~21.9 fps).
                fps_cap = m.get("fps_max")
                if self.min_frame_rate and fps_cap and fps_cap < self.min_frame_rate:
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

            pruned[cam] = {i: m for i, m in enumerate(self._order_modes(selected))}
        return pruned

    def _list_cameras(self, hdr: bool = False) -> str:
        """Run ``cinepi-raw --list-cameras`` (optionally with ``--hdr sensor``).

        Returns stdout, or "" when the run fails. The HDR run is best-effort:
        a cinepi-raw build without ClearHDR support just yields no extra modes.
        """
        cmd = "cinepi-raw --list-cameras" + (" --hdr sensor" if hdr else "")
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        except Exception as exc:  # pragma: no cover - defensive
            logging.warning("'%s' failed: %s", cmd, exc)
            return ""
        return proc.stdout or ""


    # ────────────────────────────────────────────────────────────────
    #  2.  Discover sensors once, cache every model’s modes
    # ────────────────────────────────────────────────────────────────
    def detect_camera_model(self):
        """
        Runs *cinepi-raw --list-cameras* twice — once plain and once with
        ``--hdr sensor`` — fills ``self.sensor_resolutions`` with **all**
        detected cameras (plain + ClearHDR modes), and chooses the first one as
        ``self.camera_model`` (the caller may later override this).
        """
        try:
            out = self._list_cameras(hdr=False)
            logging.info("cinepi-raw output:\n%s", out)

            if not out.strip():
                logging.warning("No output from cinepi-raw")
                self.camera_model = None
                self.res_modes = {}
                return

            # Second pass exposes the imx585 ClearHDR (16-bit + 12-bit HDR)
            # modes; sensors that ignore --hdr sensor collapse back to the
            # plain list in _merge_mode_lists().
            hdr_out = self._list_cameras(hdr=True)
            if hdr_out.strip():
                logging.info("cinepi-raw --hdr sensor output:\n%s", hdr_out)

            base_modes = self._parse_cinepi_output(out, hdr=False)
            hdr_modes = self._parse_cinepi_output(hdr_out, hdr=True) if hdr_out.strip() else {}
            merged = self._merge_mode_lists(base_modes, hdr_modes)

            # full assembly → {model → {mode_idx → mode_dict}}
            sensors = self._finalize_modes(merged)

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

    def get_packing_for_platform(self, camera_name, sensor_mode, is_pi4=None):
        """Return the packing token ('P'/'U') for *camera_name*/*sensor_mode* on
        the current platform.

        Resolution order (most specific wins):
          1. the matching mode's ``packing_by_platform[platform]`` in sensors.json
          2. the sensor's ``packing_by_platform[platform]`` in sensors.json
          3. the sensor's default packing (mode/sensor ``packing`` or fallback)

        ``is_pi4`` selects the platform key ('pi4' vs 'pi5'); when left as None it
        is auto-detected with :func:`is_pi4_family`, so callers that do not track
        the Pi model still get the right answer. Data-driving this from
        sensors.json replaces the old hardcoded per-sensor Pi-4 override.
        """
        res = self.get_resolution_info(camera_name, sensor_mode)
        base = str(res.get('packing') or 'U').upper()

        if is_pi4 is None:
            is_pi4 = is_pi4_family()
        platform = 'pi4' if is_pi4 else 'pi5'

        sensor_info = self._sensor_database_entry(camera_name) or {}
        mode_meta = self._sensor_mode_metadata(
            camera_name,
            res.get('width') or 0,
            res.get('height') or 0,
            res.get('bit_depth'),
        )
        for source in (mode_meta, sensor_info):
            overrides = source.get('packing_by_platform') if isinstance(source, dict) else None
            if isinstance(overrides, dict):
                value = overrides.get(platform)
                if value:
                    return str(value).strip().upper()
        return base

    
    def get_file_size(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('file_size', None)

    def get_sustainable_fps(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('sustainable_fps', [])
    
    def _calc_lores(self, sensor_w: int, sensor_h: int) -> tuple[int, int]:
        """Return (lores_width, lores_height) preserving sensor aspect ratio within the preview area."""
        fw, fh = 1920, 1080
        px, py = 94, 50
        aw, ah = fw - 2 * px, fh - 2 * py
        aspect = sensor_w / sensor_h
        lh = min(720, ah)
        lw = int(lh * aspect)
        if lw > aw:
            lw, lh = aw, int(round(aw / aspect))
        lw &= ~1
        lh &= ~1
        return lw, lh

    def get_lores_width(self, camera_name, sensor_mode):
        res = self.get_resolution_info(camera_name, sensor_mode)
        w = res.get('width') or 1920
        h = res.get('height') or 1080
        return self._calc_lores(w, h)[0]

    def get_lores_height(self, camera_name, sensor_mode):
        res = self.get_resolution_info(camera_name, sensor_mode)
        w = res.get('width') or 1920
        h = res.get('height') or 1080
        return self._calc_lores(w, h)[1]
    
    def get_hdr(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return bool(resolution_info.get('hdr', False))

    def get_available_resolutions(self):
        resolutions = []
        for mode, info in self.res_modes.items():
            resolution = f"{info['width']} : {info['height']} : {info['bit_depth']}b"
            # imx585 ClearHDR modes are tagged in the web GUI dropdown so the
            # 12-bit HDR modes are distinguishable from the plain 12-bit ones.
            if info.get('hdr'):
                resolution += " :HDR"
            resolutions.append({'mode': mode, 'resolution': resolution})
        return resolutions
