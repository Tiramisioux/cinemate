import subprocess
import re
import logging
from typing import Tuple, Dict

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
            "imx296": "P",
            "imx283": "U",
            "imx477": "U",
            "imx519": "P",
            "imx585": "U",
            "imx585_mono": "U",
        }

        # Optional fps correction factors per sensor
        self.fps_correction_factors = {
            "imx477": 0.9995,
            "imx585_mono": 0.9980,
        }

        # Populate camera model and modes on startup
        self.detect_camera_model()

    def _parse_cinepi_output(self, output: str) -> Tuple[str, Dict[int, Dict]]:
        """Parse `cinepi-raw --list-cameras` output and return the camera
        model along with a dictionary of resolution modes."""

        camera_model = None
        modes_list = []
        current_bit_depth = None
        parsing = False

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Extract camera model and handle mono override
            if camera_model is None:
                match = re.search(r"\d+\s*:\s*([^\s]+)\s*\[.*?(MONO)?\]", line)
                if match:
                    camera_model = match.group(1)
                    if match.group(2) == "MONO":
                        camera_model += "_mono"

            if "Modes:" in line:
                parsing = True
                line = line.split("Modes:", 1)[1].strip()
                if not line:
                    continue

            if not parsing:
                continue

            # Detect bit depth from format name like 'R12_CSI2P' or 'R16'
            if line.startswith("'"):
                format_match = re.match(r"'R(\d+)", line)
                if format_match:
                    current_bit_depth = int(format_match.group(1))
                if ':' in line:
                    line = line.split(':', 1)[1].strip()

            width_height = re.search(r"(\d+)x(\d+)", line)
            if not width_height:
                continue

            width = int(width_height.group(1))
            height = int(width_height.group(2))
            fps_match = re.search(r"\[(\d+(?:\.\d+)?)\s*fps", line)
            fps_max = int(float(fps_match.group(1))) if fps_match else None

            packing = self.packing_info.get(camera_model, 'U')
            bytes_per_pixel = current_bit_depth / 8
            file_size = round(width * height * bytes_per_pixel / (1024 * 1024), 1)

            modes_list.append({
                'aspect': round(width / height, 2),
                'width': width,
                'height': height,
                'bit_depth': current_bit_depth,
                'packing': packing,
                'fps_max': fps_max,
                'gui_layout': 0,
                'file_size': file_size
            })

        # Add custom modes from settings
        for extra in self.custom_modes.get(camera_model, []):
            width = int(extra.get("width"))
            height = int(extra.get("height"))
            bit_depth = int(extra.get("bit_depth"))
            fps_max = extra.get("fps_max")

            packing = self.packing_info.get(camera_model, 'U')
            bytes_per_pixel = bit_depth / 8
            file_size = round(width * height * bytes_per_pixel / (1024 * 1024), 1)

            modes_list.append({
                'aspect': round(width / height, 2),
                'width': width,
                'height': height,
                'bit_depth': bit_depth,
                'packing': packing,
                'fps_max': fps_max,
                'gui_layout': 0,
                'file_size': file_size,
            })

        # Filter by desired bit depths and K-steps
        filtered = []
        for m in modes_list:
            if self.bit_depths and m['bit_depth'] not in self.bit_depths:
                continue
            k_val = round(m['width'] / 1000 * 2) / 2
            if self.k_steps and k_val not in self.k_steps:
                continue
            filtered.append(m)

        modes = {i: m for i, m in enumerate(reversed(filtered))}
        return camera_model, modes


    def detect_camera_model(self):
        try:
            result = subprocess.run('cinepi-raw --list-cameras', shell=True, capture_output=True, text=True)
            logging.info(f"cinepi-raw output: {result.stdout}")

            if result.stdout:
                model, modes = self._parse_cinepi_output(result.stdout)
                if model:
                    self.camera_model = model
                    self.sensor_resolutions[self.camera_model] = modes
                    logging.info(f"Detected camera model: {self.camera_model}")
                    self.load_sensor_resolutions()
                else:
                    logging.warning("No camera model detected")
                    self.camera_model = None
                    self.res_modes = {}
            else:
                logging.warning("No output from cinepi-raw")

        except Exception as e:
            logging.error(f"Unexpected error: {e}")
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
    
    def get_resolution_info(self, camera_name, sensor_mode):
        #logging.info(f"Checking resolution for camera: {camera_name}, sensor mode: {sensor_mode}")
        #logging.info(f"Available cameras: {list(self.sensor_resolutions.keys())}")

        if camera_name in self.sensor_resolutions:
            #logging.info(f"Available sensor modes for {camera_name}: {list(self.sensor_resolutions[camera_name].keys())}")
            # Explicitly convert sensor_mode to integer if it’s not already an integer
            sensor_mode = int(sensor_mode)
            if sensor_mode in self.sensor_resolutions[camera_name]:
                return self.sensor_resolutions[camera_name][sensor_mode]
            else:
                logging.error(f"Unknown sensor mode {sensor_mode} for camera {camera_name}")
        else:
            logging.error(f"Unknown camera model: {camera_name}")
        return {'width': None, 'height': None, 'fps_max': None, 'gui_layout': None}
    
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
    
    def get_fps_correction_factor(self, camera_name, sensor_mode):
        return self.fps_correction_factors.get(camera_name, 1.0)