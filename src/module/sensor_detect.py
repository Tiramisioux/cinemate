import subprocess
import re
import logging

import subprocess
import re
import logging

class SensorDetect:
    def __init__(self):
        self.camera_model = None
        self.res_modes = []

        self.sensor_resolutions = {
            'imx477': {                                                             
                0: {'aspect': 1.87, 'width': 2028, 'height': 1080, 'bit_depth': 12, 'fps_max': 50, 'gui_layout': 0, 'file_size': 3.2}, 
                1: {'aspect': 1.33, 'width': 2028, 'height': 1520, 'bit_depth': 12, 'fps_max': 40, 'gui_layout': 0, 'file_size': 4.5},
                2: {'aspect': 1.34, 'width': 1332, 'height': 990, 'bit_depth': 10, 'fps_max': 120, 'gui_layout': 0, 'file_size': 2.8}, 
            },
            'imx296': {                                                        
                0: {'aspect': 1.33, 'width': 1456, 'height': 1088, 'bit_depth': 12, 'fps_max': 60, 'gui_layout': 0, 'file_size': 2},
            },
            'imx283': {                                                        
                0: {'aspect': 1.81, 'width': 3936, 'height': 2176, 'bit_depth': 10, 'fps_max': 43, 'gui_layout': 0, 'file_size': 14}, # ok
                1: {'aspect': 1.80, 'width': 2736, 'height': 1538, 'bit_depth': 12, 'fps_max': 41, 'gui_layout': 0, 'file_size': 7.1}, # ok
                2: {'aspect': 1.53, 'width': 2736, 'height': 1824, 'bit_depth': 12, 'fps_max': 35, 'gui_layout': 0, 'file_size': 8.2}, # ok

                3: {'aspect': 1.52, 'width': 5568, 'height': 3664, 'bit_depth': 10, 'fps_max': 17, 'gui_layout': 0, 'file_size': 31},
                4: {'aspect': 1.52, 'width': 5568, 'height': 3664, 'bit_depth': 12, 'fps_max': 17, 'gui_layout': 0, 'file_size': 31},
                5: {'aspect': 1.80, 'width': 5568, 'height': 3094, 'bit_depth': 10, 'fps_max': 21, 'gui_layout': 0, 'file_size': 2},
            },
        }
        
        self.detect_camera_model()

    def detect_camera_model(self):
        try:
            result = subprocess.run(['libcamera-vid', '--list-cameras'], capture_output=True, text=True, check=True)
            match = re.search(r'\d+\s*:\s*(\w+)\s*\[', result.stdout)
            if match:
                self.camera_model = match.group(1)
                self.load_sensor_resolutions()
            else:
                self.camera_model = None
                self.res_modes = []

        except subprocess.CalledProcessError as e:
            logging.error(f"Error running libcamera-vid: {e}")
            
        if self.camera_model:
            logging.info(f"Detected sensor: {self.camera_model}")
        else:
            logging.info("Unable to detect sensor.")

    def load_sensor_resolutions(self):
        if self.camera_model in self.sensor_resolutions:
            self.res_modes = self.sensor_resolutions[self.camera_model]
        else:
            logging.error(f"Unknown camera model: {self.camera_model}")
            self.res_modes = []

    def get_sensor_resolution(self, mode):
        return self.res_modes.get(mode, {})
    
    def get_resolution_info(self, camera_name, sensor_mode):
        if camera_name in self.sensor_resolutions:
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
    
    def bit_depth(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('bit_depth', None)
    
    def get_fps_max(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('fps_max', None)
    
    def get_file_size(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('file_size', None)
    
    def get_lores_width(self, camera_name, sensor_mode):
        # Placeholder method, replace with actual implementation
        return 1280
    
    def get_lores_height(self, camera_name, sensor_mode):
        # Placeholder method, replace with actual implementation
        return 720
