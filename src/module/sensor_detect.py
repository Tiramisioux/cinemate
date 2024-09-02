import subprocess
import re
import logging

class SensorDetect:
    def __init__(self):
        self.camera_model = None
        self.res_modes = []

        self.sensor_resolutions = {

            'imx296': {                                                        
                0: {'aspect': 1.33, 'width': 1456, 'height': 1088, 'bit_depth': 12, 'fps_max': 60, 'gui_layout': 0, 'file_size': 2},
            },
            'imx283': {             
                0: {'aspect': 1.80, 'width': 2736, 'height': 1538, 'bit_depth': 12, 'fps_max': 40, 'gui_layout': 0, 'file_size': 7.1}, # ok
                1: {'aspect': 1.53, 'width': 2736, 'height': 1824, 'bit_depth': 12, 'fps_max': 34, 'gui_layout': 0, 'file_size': 8.2}, # ok

                #3: {'aspect': 1.52, 'width': 5568, 'height': 3664, 'bit_depth': 10, 'fps_max': 17, 'gui_layout': 0, 'file_size': 31},
                #4: {'aspect': 1.52, 'width': 5568, 'height': 3664, 'bit_depth': 12, 'fps_max': 17, 'gui_layout': 0, 'file_size': 31},
                #5: {'aspect': 1.80, 'width': 5568, 'height': 3094, 'bit_depth': 10, 'fps_max': 21, 'gui_layout': 0, 'file_size': 2},                                        
            },
            'imx477': {                                                             
                0: {'aspect': 1.87, 'width': 2028, 'height': 1080, 'bit_depth': 12, 'fps_max': 50, 'gui_layout': 0, 'file_size': 3.2}, 
                1: {'aspect': 1.33, 'width': 2028, 'height': 1520, 'bit_depth': 12, 'fps_max': 40, 'gui_layout': 0, 'file_size': 4.5},
                2: {'aspect': 1.34, 'width': 1332, 'height': 990, 'bit_depth': 10, 'fps_max': 120, 'gui_layout': 0, 'file_size': 2.8}, 
            },
            'imx519': {             
                0: {'aspect': 1.77, 'width': 1280, 'height': 720, 'bit_depth': 10, 'fps_max': 80, 'gui_layout': 0, 'file_size': 7.1}, # ok
                1: {'aspect': 1.77, 'width': 1920, 'height': 1080, 'bit_depth': 10, 'fps_max': 60, 'gui_layout': 0, 'file_size': 8.2}, # ok
                2: {'aspect': 1.77, 'width': 2328, 'height': 1748, 'bit_depth': 10, 'fps_max': 30, 'gui_layout': 0, 'file_size': 8.2}, # ok
                3: {'aspect': 1.77, 'width': 3840, 'height': 2160, 'bit_depth': 10, 'fps_max': 18, 'gui_layout': 0, 'file_size': 31},                                       
            },
            'imx585': {             
                0: {'aspect': 1.77, 'width': 1928, 'height': 1090, 'bit_depth': 12, 'fps_max': 87, 'gui_layout': 0, 'file_size': 4}, # ok
                1: {'aspect': 1.77, 'width': 3856, 'height': 2180, 'bit_depth': 12, 'fps_max': 34, 'gui_layout': 0, 'file_size': 13}, # ok
                2: {'aspect': 1.77, 'width': 1928, 'height': 1090, 'bit_depth': 16, 'fps_max': 30, 'gui_layout': 0, 'file_size': 13},

                #3: {'aspect': 1.77, 'width': 3856, 'height': 2180, 'bit_depth': 16, 'fps_max': 21, 'gui_layout': 0, 'file_size': 8},                                      
            },
        }
        
        #self.detect_camera_model()

    def detect_camera_model(self):
        try:
            #logging.info("Running cinepi-raw to detect cameras")
            result = subprocess.run('cinepi-raw --list-cameras', shell=True, capture_output=True, text=True)
            logging.info(f"cinepi-raw output: {result.stdout}")

            # Process the standard output even if the command fails
            if result.stdout:
                match = re.search(r'\d+\s*:\s*(\w+)\s*\[', result.stdout)
                if match:
                    self.camera_model = match.group(1)
                    logging.info(f"Detected camera model: {self.camera_model}")
                    self.load_sensor_resolutions()
                else:
                    logging.warning("No camera model detected")
                    self.camera_model = None
                    self.res_modes = []
            else:
                logging.warning("No output from cinepi-raw")

            if result.returncode != 0:
                #logging.error(f"cinepi-raw command failed with stderr: {result.stderr}")
                pass
            
        except subprocess.CalledProcessError as e:
            #logging.error(f"Error running cinepi-raw: {e}")
            #logging.error(f"Standard output: {e.stdout}")
            #logging.error(f"Standard error: {e.stderr}")
            self.camera_model = None
            self.res_modes = []
        except Exception as e:
            #logging.error(f"Unexpected error: {e}")
            self.camera_model = None
            self.res_modes = []

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
    
    def get_available_resolutions(self):
        resolutions = []
        for mode, info in self.res_modes.items():
            resolution = f"{info['width']} : {info['height']} : {info['bit_depth']}b"
            resolutions.append({'mode': mode, 'resolution': resolution})
        return resolutions

                # 0: {'aspect': 1.81, 'width': 3936, 'height': 2176, 'bit_depth': 10, 'fps_max': 42, 'gui_layout': 0, 'file_size': 14}, # ok
                # 1: {'aspect': 1.80, 'width': 2736, 'height': 1538, 'bit_depth': 12, 'fps_max': 40, 'gui_layout': 0, 'file_size': 7.1}, # ok
                # 2: {'aspect': 1.53, 'width': 2736, 'height': 1824, 'bit_depth': 12, 'fps_max': 34, 'gui_layout': 0, 'file_size': 8.2}, # ok