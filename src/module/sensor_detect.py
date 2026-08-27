import os
import signal
import subprocess
import re
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

from module import rp1_regime
from module.sensor_database import load_sensor_database

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

# DNG frame-size model, calibrated against real captures (imx585 3856x2180
# linear/log at 10/12/16-bit -- see innomaker585/pi-2026-08-05-goodkernel/).
# cinepi-raw packs pixel data tightly at N bits/row ((width*bits+7)//8 bytes),
# so pixel_bytes scales exactly with the *effective* bit depth (the live
# --log-encode target when active, else the sensor mode's native depth).
# The remaining per-frame overhead (DNG header/tags, plus a LinearizationTable
# on log-encoded frames) is <0.07% of frame size across every measured case,
# so one flat constant is used rather than modelling it exactly.
DNG_HEADER_OVERHEAD_BYTES = 1024
# cinepi-raw writes DNGs uncompressed (COMPRESSION_NONE is hardcoded in
# dng_encoder.cpp; the vendored lj92 lossless codec is dead code) -- this is
# the seam to update once that changes, so the minutes-left math doesn't need
# a redesign when it does.
DNG_COMPRESSION_RATIO = 1.0


def compute_frame_size_mb(width: int, height: int, bit_depth: int,
                           compression_ratio: float = DNG_COMPRESSION_RATIO) -> float:
    """DNG frame size in decimal MB for a *bit_depth*-packed frame of *width*
    x *height*. See DNG_HEADER_OVERHEAD_BYTES/DNG_COMPRESSION_RATIO above."""
    row_bytes = (int(width) * int(bit_depth) + 7) // 8
    pixel_bytes = row_bytes * int(height)
    return round((pixel_bytes + DNG_HEADER_OVERHEAD_BYTES) / compression_ratio / 1_000_000, 2)


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
        res_cfg = self.settings.get("image_capture", {})
        self.k_steps = res_cfg.get("k_steps", [])
        self.bit_depths = res_cfg.get("bit_depths", [])
        self.custom_modes = res_cfg.get("custom_modes", {})
        # Optional ClearHDR (imx585) whitelist. settings.jsonc → resolutions.hdr
        # is {"sdr": bool, "imx585_clear_hdr": bool}; both true (default)
        # exposes plain and ClearHDR modes, turn a flag off to hide that class
        # of modes. Mirrors the bit_depths / k_steps whitelists above.
        self.hdr_modes = self._hdr_whitelist(res_cfg.get("hdr", {}))
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
        # Delegates to module.sensor_database, which boot_config also uses --
        # two loaders would mean two sets of fallback rules to keep in step,
        # which is the drift this database exists to prevent.
        return load_sensor_database(str(self._resolve_repo_path(self.sensor_database_file)))

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
        # Always computed from the packed-bytes model (compute_frame_size_mb).
        # sensors.json no longer carries a static file_size_mb -- it doesn't
        # know about --log-encode, which is a runtime toggle applied
        # dynamically in cinepi_controller instead.
        file_size = compute_frame_size_mb(width, height, bit_depth) if bit_depth else None
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
    def _hdr_whitelist(hdr_cfg: Any) -> List[bool]:
        """Normalize settings.jsonc resolutions.hdr into the internal
        [bool, ...] whitelist consumed by _finalize_modes.

        Accepts the named form {"sdr": bool, "imx585_clear_hdr": bool} (both
        default true) or the legacy [false, true] list form for old Pi
        settings.jsonc files.
        """
        if isinstance(hdr_cfg, dict):
            return [
                val for val, key in ((False, "sdr"), (True, "imx585_clear_hdr"))
                if hdr_cfg.get(key, True)
            ]
        return list(hdr_cfg or [])

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
        """Add custom modes, apply the settings.jsonc filters, order and index.

        F-298: a custom_modes entry whose (width, height, bit_depth, hdr)
        matches an already-detected mode overrides that mode's fps_max in
        place -- the sensor's advertised ceiling is an electrical property
        and says nothing about what this storage/CPU actually sustain, so
        it needs to be correctable, not just addable-to. Only fps_max is
        overridable this way; the rest of the detected mode (packing,
        gui_layout, aspect) is left alone. A non-matching entry still
        appends a brand-new mode exactly as before -- this only changes
        what happens when the dimensions already exist.
        """
        # ── add or correct user-defined custom modes ─────────────────
        for cam, extras in self.custom_modes.items():
            sensors.setdefault(cam, [])
            for extra in extras:
                w, h = int(extra["width"]), int(extra["height"])
                bd   = int(extra["bit_depth"])
                fps  = extra.get("fps_max")
                hdr_flag = bool(extra.get("hdr", False))
                existing = next(
                    (
                        m for m in sensors[cam]
                        if int(m.get("width") or 0) == w
                        and int(m.get("height") or 0) == h
                        and int(m.get("bit_depth") or 0) == bd
                        and bool(m.get("hdr")) == hdr_flag
                    ),
                    None,
                )
                if existing is not None:
                    if fps is not None:
                        detected_fps = existing.get("fps_max")
                        if detected_fps is not None and fps > detected_fps:
                            logging.warning(
                                "custom_modes override for %s %dx%d (%d-bit%s) raises "
                                "fps_max from the detected %s to %s -- the sensor did "
                                "not report this; if storage/CPU can't actually sustain "
                                "it, lower the value instead of raising it.",
                                cam, w, h, bd, " HDR" if hdr_flag else "",
                                detected_fps, fps,
                            )
                        # Stash the sensor's own value before overwriting it --
                        # the settings editor shows this as the "detected"
                        # placeholder next to the editable effective value.
                        existing.setdefault("fps_max_detected", detected_fps)
                        existing["fps_max"] = fps
                    continue
                sensors[cam].append(
                    self._mode_from_metadata_or_detected(
                        camera_name=cam,
                        width=w,
                        height=h,
                        bit_depth=bd,
                        fps_max=fps,
                        hdr=hdr_flag,
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
                # settings.jsonc → resolutions.hdr: {sdr, imx585_clear_hdr}
                # whitelist of the ClearHDR flag, normalized by _hdr_whitelist.
                if self.hdr_modes and bool(m.get("hdr")) not in self.hdr_modes:
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

    @staticmethod
    def _running_cinepi_raw_pids() -> List[str]:
        try:
            result = subprocess.run(
                ["pgrep", "-x", "cinepi-raw"], capture_output=True, text=True,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logging.debug("Could not check for a running cinepi-raw process: %s", exc)
            return []
        return [pid for pid in result.stdout.split() if pid.strip()]

    def _kill_stale_cinepi_raw(self, timeout: float = 3.0) -> None:
        """Kill any cinepi-raw process already running before probing sensor
        modes.

        detect_camera_model() runs once, at Cinemate startup -- before
        Cinemate has launched its own cinepi-raw child, so any cinepi-raw
        found here is orphaned (e.g. a botched previous restart, or a manual
        test session left running). If it isn't killed first, the
        ``--hdr sensor`` probe can't actually toggle wide_dynamic_range on a
        sensor subdev the orphan already holds (V4L2 reports the control as
        "grabbed"), so ClearHDR/16-bit modes silently vanish from this
        session's mode table instead of the probe failing loudly.
        """
        pids = self._running_cinepi_raw_pids()
        if not pids:
            return
        logging.warning(
            "Found stale cinepi-raw process(es) %s at startup -- killing before "
            "probing sensor modes so ClearHDR/16-bit detection isn't silently "
            "degraded by an already-held sensor subdev.", pids,
        )
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGKILL)
            except (ValueError, ProcessLookupError, PermissionError) as exc:
                logging.warning("Failed to kill stale cinepi-raw pid %s: %s", pid, exc)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._running_cinepi_raw_pids():
                return
            time.sleep(0.1)
        logging.warning(
            "Stale cinepi-raw process(es) %s did not exit within %.1fs -- "
            "ClearHDR/16-bit mode detection may still be degraded this session.",
            pids, timeout,
        )

    def _list_cameras(self, hdr: bool = False) -> str:
        """Run ``cinepi-raw --list-cameras`` (optionally with ``--hdr sensor``).

        Returns stdout, or "" when the run fails. The HDR run is best-effort:
        a cinepi-raw build without ClearHDR support just yields no extra modes.
        """
        # Probe under the same pixel-rate ceiling the real launch will use, so
        # the mode table cannot advertise a frame rate the configured RP1
        # regime could never sustain. Harmless if libcamera turns out to apply
        # the bound only at configure time rather than during enumeration --
        # that is what hardware gate G2 settles.
        max_pixel_rate = rp1_regime.pixel_rate()
        rate_arg = f" --max-pixel-rate {max_pixel_rate}" if max_pixel_rate is not None else ""
        cmd = "cinepi-raw --list-cameras" + rate_arg + (" --hdr sensor" if hdr else "")
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
            self._kill_stale_cinepi_raw()

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

            # The HDR probe "succeeding" (non-empty output) but adding zero new
            # modes means --hdr sensor couldn't actually change what the sensor
            # reports -- most commonly because another process (see
            # _kill_stale_cinepi_raw above) still held the subdev. Surface this
            # loudly instead of silently shipping a mode table missing ClearHDR.
            if hdr_out.strip():
                added = sum(
                    len(merged.get(cam, [])) - len(base_modes.get(cam, []))
                    for cam in merged
                )
                if added == 0:
                    logging.warning(
                        "ClearHDR probe (--hdr sensor) returned no modes beyond "
                        "the plain probe. If this sensor supports ClearHDR (e.g. "
                        "imx585), 16-bit modes are unavailable this session -- "
                        "likely because something already held the sensor "
                        "subdev when Cinemate started."
                    )

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

    def _log_encode_info(self, camera_name: str | None) -> dict[str, Any] | None:
        """Return sensors.json's ``log_encode`` block for *camera_name*, or
        None when absent. Absence means the sensor is unsupported — there is
        no special-casing here, mirroring how ``packing_by_platform`` absence
        just falls through to the default packing above.
        """
        sensor_info = self._sensor_database_entry(camera_name)
        if not sensor_info:
            return None
        log_encode = sensor_info.get('log_encode')
        return log_encode if isinstance(log_encode, dict) else None

    def supports_log_encode(self, camera_name: str | None) -> bool:
        """True when *camera_name* has a ``log_encode`` block in sensors.json."""
        return self._log_encode_info(camera_name) is not None

    def get_log_encode_targets(self, camera_name: str | None) -> dict[int, dict[str, Any]]:
        """Return ``{source_bit_depth: {'valid': [target, ...], 'default': target}}``
        for *camera_name*, or ``{}`` when the sensor has no ``log_encode`` block.

        This is capability data only. ``valid`` is every target whose spec
        matches this sensor's black level for that source depth (imx585
        16-bit has both a 16to10 and a 16to12 spec); ``default`` is the one
        a bare toggle picks. Resolving a live target from the camera's
        current mode is :meth:`resolve_log_encode_target`.
        """
        info = self._log_encode_info(camera_name)
        if not info:
            return {}
        targets = info.get('targets')
        if not isinstance(targets, dict):
            return {}
        result: dict[int, dict[str, Any]] = {}
        for source_bits, spec in targets.items():
            try:
                source_key = int(source_bits)
            except (TypeError, ValueError):
                continue
            if not isinstance(spec, dict):
                continue
            valid = [int(t) for t in (spec.get('valid') or [])]
            default = spec.get('default')
            result[source_key] = {
                'valid': valid,
                'default': int(default) if default is not None else None,
            }
        return result

    def get_log_encode_valid_targets(self, camera_name: str | None, source_bit_depth: int | None) -> list[int]:
        """Return the target depths *camera_name* supports from
        *source_bit_depth*, or ``[]`` when there is no matching spec (the
        sensor is unsupported, or this source depth has none)."""
        if source_bit_depth is None:
            return []
        entry = self.get_log_encode_targets(camera_name).get(int(source_bit_depth))
        return list(entry['valid']) if entry else []

    def get_log_encode_default_target(self, camera_name: str | None, source_bit_depth: int | None) -> int | None:
        """Return the default (bare-toggle) target for *camera_name* at
        *source_bit_depth*, or None when this source depth has no spec."""
        if source_bit_depth is None:
            return None
        entry = self.get_log_encode_targets(camera_name).get(int(source_bit_depth))
        return entry['default'] if entry else None

    def resolve_log_encode_target(
        self,
        camera_name: str | None,
        source_bit_depth: int | None,
        requested: int | None = None,
        hdr: bool = False,
    ) -> int | None:
        """Resolve the ``--log-encode`` target for *camera_name* currently
        running at *source_bit_depth*.

        ``requested=None`` (a bare ``set log`` toggle) resolves to this
        source depth's default (16-bit -> 12, 12-bit -> 10). An explicit
        ``requested`` (e.g. ``set log 10`` to force 16-bit down to 16to10
        instead of the 16to12 default) is returned only when it is one of
        this sensor/source-depth's valid targets; otherwise None — this
        never silently substitutes a different target than what was asked
        for or implied.

        *hdr* is whether the launch will carry ``--hdr sensor``. It is not
        used to refuse anything here (see below) — it is accepted so the
        call site never has to special-case ClearHDR itself.
        """
        # ── 12-bit ClearHDR (CCMP) is not a special case here ────────────
        #
        # 12-bit ClearHDR companies on-sensor (CCMP), so it is not a LINEAR
        # log source. That used to make this function refuse it outright
        # (return None whenever hdr and source_bit_depth == 12), because
        # cinepi-raw could only log-encode a linear 12-bit source and would
        # otherwise compand the already-companded data a second time.
        #
        # cinepi-raw now composes instead: decompand to 16-bit linear first
        # (the CCMP curve, itself gated), then apply the 16-to-target log
        # curve — see get_ccmp_composed_log_lut() / log_source_is_companded()
        # in cinepi-raw's cinepi/log_lut.hpp. From cinemate's side that is
        # invisible: it is still "12-bit source -> target 10", exactly what
        # sensors.json's imx585 "12": {"valid":[10],"default":10} already
        # says, hdr or not. So *hdr* no longer changes this function's
        # answer — it is kept as a parameter only so callers that pass it
        # (there is exactly one valid target either way) do not need editing.
        valid = self.get_log_encode_valid_targets(camera_name, source_bit_depth)
        if not valid:
            return None
        if requested is None:
            return self.get_log_encode_default_target(camera_name, source_bit_depth)
        try:
            requested_target = int(requested)
        except (TypeError, ValueError):
            return None
        return requested_target if requested_target in valid else None

    def resolve_effective_bit_depth(
        self,
        camera_name: str | None,
        native_bit_depth: int | None,
        *,
        log_requested: bool | int = False,
        hdr: bool = False,
    ) -> int | None:
        """Return the bit depth DNG frames are actually written at: the
        resolved --log-encode target when CineMate Log applies for this
        sensor/mode/request, else *native_bit_depth* unchanged.

        *log_requested* is the live `set log` request -- False/True/10/12,
        e.g. from redis_controller.decode_log_encode_request(). Mirrors the
        --log-encode resolution CinePiProcess._build_args() applies at
        launch (cinepi_multi.py) so file-size estimates always match what
        cinepi-raw will actually write.
        """
        if native_bit_depth is None:
            return None
        if not log_requested:
            return native_bit_depth
        target = self.resolve_log_encode_target(
            camera_name, native_bit_depth,
            requested=None if log_requested is True else log_requested,
            hdr=hdr,
        )
        return target if target is not None else native_bit_depth

    def get_log_encode_black_level_16bit(self, camera_name: str | None) -> int | None:
        """Return sensors.json's ``log_encode.black_level_16bit`` for
        *camera_name*, or None when the sensor has no ``log_encode`` block."""
        info = self._log_encode_info(camera_name)
        if not info:
            return None
        black_level = info.get('black_level_16bit')
        return int(black_level) if black_level is not None else None

    def get_file_size(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('file_size', None)


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
