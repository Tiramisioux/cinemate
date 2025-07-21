import subprocess
import re
import logging
from typing import Tuple, Dict

class SensorDetect:
    def __init__(self):
        self.camera_model = None
        self.res_modes = []
        self.sensor_resolutions = {

            'imx296': {                                                        
                0: {'aspect': 1.33, 'width': 1456, 'height': 1088, 'bit_depth': 12, 'packing': 'P', 'fps_max': 60, 'gui_layout': 0, 'file_size': 2},
            },
            'imx283': {             
                0: {'aspect': 1.80, 'width': 2736, 'height': 1538, 'bit_depth': 12, 'packing': 'U', 'fps_max': 40, 'gui_layout': 0, 'file_size': 7.1}, # driver fps max 40
                1: {'aspect': 1.53, 'width': 2736, 'height': 1824, 'bit_depth': 12, 'packing': 'U', 'fps_max': 34, 'gui_layout': 0, 'file_size': 8.2}, # driver fps max 34
                2: {'aspect': 1.77, 'width': 3936, 'height': 2176, 'bit_depth': 10, 'packing': 'U', 'fps_max': 60, 'gui_layout': 0, 'file_size': 8.2}, # driver fps max 21
                #3: {'aspect': 1.52, 'width': 5568, 'height': 3664, 'bit_depth': 10, 'packing': 'U', 'fps_max': 17, 'gui_layout': 0, 'file_size': 31}, # driver fps max 17
                #4: {'aspect': 1.52, 'width': 5568, 'height': 3664, 'bit_depth': 12, 'packing': 'U', 'fps_max': 17, 'gui_layout': 0, 'file_size': 31}, # driver fps max 17
                #5: {'aspect': 1.80, 'width': 5568, 'height': 3094, 'bit_depth': 10, 'packing': 'U', 'fps_max': 21, 'gui_layout': 0, 'file_size': 2}, # driver fps max 21                                      
            },

            'imx477': {                                                             
                0: {'aspect': 1.87, 'width': 2028, 'height': 1080, 'bit_depth': 12, 'packing': 'U', 'fps_max': 50, 'gui_layout': 0, 'file_size': 4.3, 'fps_correction_factor': 0.9995}, # driver fps max 50
                1: {'aspect': 1.33, 'width': 2028, 'height': 1520, 'bit_depth': 12, 'packing': 'U', 'fps_max': 40, 'gui_layout': 0, 'file_size': 5.3, 'fps_correction_factor': 0.9995}, # driver fps max 40
                2: {'aspect': 1.34, 'width': 1332, 'height': 990, 'bit_depth': 10, 'packing': 'U', 'fps_max': 120, 'gui_layout': 0, 'file_size': 2.7, 'fps_correction_factor': 0.9995}, # driver fps max 120 
            },
            'imx519': {             
                0: {'aspect': 1.77, 'width': 1280, 'height': 720, 'bit_depth': 10, 'packing': 'P', 'fps_max': 80, 'gui_layout': 0, 'file_size': 7.1}, # driver fps max 80
                1: {'aspect': 1.77, 'width': 1920, 'height': 1080, 'bit_depth': 10, 'packing': 'P', 'fps_max': 60, 'gui_layout': 0, 'file_size': 8.2}, # driver fps max 60
                2: {'aspect': 1.77, 'width': 2328, 'height': 1748, 'bit_depth': 10, 'packing': 'P', 'fps_max': 30, 'gui_layout': 0, 'file_size': 8.2}, # driver fps max 30
                3: {'aspect': 1.77, 'width': 3840, 'height': 2160, 'bit_depth': 10, 'packing': 'P', 'fps_max': 18, 'gui_layout': 0, 'file_size': 31}, # driver fps max 18                   
            },
            'imx585': {             
                0: {'aspect': 1.77, 'width': 1928, 'height': 1090, 'bit_depth': 12, 'packing': 'U', 'fps_max': 87, 'gui_layout': 0, 'file_size': 4.1}, # driver fps max 87
                1: {'aspect': 1.77, 'width': 3856, 'height': 2180, 'bit_depth': 12, 'packing': 'U', 'fps_max': 34, 'gui_layout': 0, 'file_size': 13.5}, # driver fps max 34
               # 2: {'aspect': 1.77, 'width': 1928, 'height': 1090, 'bit_depth': 16, 'packing': 'U', 'fps_max': 30, 'gui_layout': 0, 'file_size': 13.5}, # driver fps max 30

                #3: {'aspect': 1.77, 'width': 3856, 'height': 2180, 'bit_depth': 16, 'packing': 'U', 'fps_max': 21, 'gui_layout': 0, 'file_size': 8},                                      
            },
            'imx585_mono': {             
                0: {'aspect': 1.77, 'width': 1928, 'height': 1090, 'bit_depth': 12, 'packing': 'U', 'fps_max': 87, 'gui_layout': 0, 'file_size': 4.1, 'fps_correction_factor': 0.9980},  # driver fps max 87
                1: {'aspect': 1.77, 'width': 3856, 'height': 2180, 'bit_depth': 12, 'packing': 'U', 'fps_max': 34, 'gui_layout': 0, 'file_size': 13.5, 'fps_correction_factor': 0.9980}, # driver fps max 34
                #2: {'aspect': 1.77, 'width': 1928, 'height': 1090, 'bit_depth': 16, 'packing': 'U', 'fps_max': 30, 'gui_layout': 0, 'file_size': 13.5, 'fps_correction_factor': 0.9980}, # driver fps max 30

                #3: {'aspect': 1.77, 'width': 3856, 'height': 2180, 'bit_depth': 16, 'packing': 'U', 'fps_max': 21, 'gui_layout': 0, 'file_size': 8},                                      
            },
        }
        # Populate camera model and modes on startup
        self.detect_camera_model()

    def _parse_cinepi_output(self, output: str) -> Tuple[str, Dict[int, Dict]]:
        """Parse ``cinepi-raw --list-cameras`` output and return the camera
        model along with a dictionary of resolution modes."""

        camera_model = None
        modes_list = []
        current_bit_depth = None
        parsing = False

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if camera_model is None:
                match = re.search(r"\d+\s*:\s*([^\s]+)\s*\[", line)
                if match:
                    camera_model = match.group(1)

            if "Modes:" in line:
                parsing = True
                line = line.split("Modes:", 1)[1].strip()
                if not line:
                    continue

            if not parsing:
                continue

            if line.startswith("'"):
                depth_match = re.search(r"'(?:[^']*?)(\d+)", line)
                if depth_match:
                    current_bit_depth = int(depth_match.group(1))
                if ':' in line:
                    line = line.split(':', 1)[1].strip()

            width_height = re.search(r"(\d+)x(\d+)", line)
            if not width_height:
                continue

            width = int(width_height.group(1))
            height = int(width_height.group(2))
            fps_match = re.search(r"\[(\d+(?:\.\d+)?)\s*fps", line)
            fps_max = int(float(fps_match.group(1))) if fps_match else None

            modes_list.append({
                'aspect': round(width / height, 2),
                'width': width,
                'height': height,
                'bit_depth': current_bit_depth,
                'packing': 'U',
                'fps_max': fps_max,
                'gui_layout': 0,
                'file_size': round(width * height * 2 / 1024 / 1024, 1)
            })

        modes = {i: m for i, m in enumerate(reversed(modes_list))}
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
                    self.res_modes = []
            else:
                logging.warning("No output from cinepi-raw")

        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            self.camera_model = None
            self.res_modes = []

    def check_camera(self):
        self.detect_camera_model()
        return self.camera_model

    def load_sensor_resolutions(self):
        if self.camera_model in self.sensor_resolutions:
            self.res_modes = self.sensor_resolutions[self.camera_model]
        else:
            logging.error(f"Unknown camera model: {self.camera_model}")
            self.res_modes = []

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
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('fps_correction_factor', 1.0)