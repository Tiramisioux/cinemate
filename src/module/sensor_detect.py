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
        
        # Define sensor resolutions and modes for different camera models
        # Add more entries as needed for additional camera models
        self.sensor_resolutions = {
            
            # Raspberry Pi HQ camera
            'imx477': {                                                             
                0: {'aspect': 1.87, 'width': 2028, 'height': 1080, 'fps_max': 50, 'gui_layout': 0, 'file_size': 3.2}, 
                1: {'aspect': 1.33, 'width': 2028, 'height': 1520, 'fps_max': 40, 'gui_layout': 1, 'file_size': 4.5}, 
            },
            
            #Raspberry Pi GS Camera
            'imx296': {                                                        
                0: {'aspect': 1.33, 'width': 1456, 'height': 1088, 'fps_max': 60, 'gui_layout': 1, 'file_size': 2},
                
            },
            # Add more camera models here..
            
        }
        
        self.detect_camera_model()

    def detect_camera_model(self):
        try:
            # Run the libcamera-vid command to list cameras
            result = subprocess.run(['libcamera-vid', '--list-cameras'], capture_output=True, text=True, check=True)

            # Extract the camera model from the output using a regular expression
            match = re.search(r'\d+\s*:\s*(\w+)\s*\[', result.stdout)
            if match:
                self.camera_model = match.group(1)
                self.load_sensor_resolutions()  # Call to load_sensor_resolutions
            else:
                # Reset camera_model and res_modes if no match is found
                self.camera_model = None
                self.res_modes = []

        except subprocess.CalledProcessError as e:
            logging.error(f"Error running libcamera-vid: {e}")
            
        if self.camera_model:
            logging.info(f"Detected sensor: {self.camera_model}")
        else:
            logging.info("Unable to detect sensor.")


    def load_sensor_resolutions(self):
        # Load resolutions and modes for the detected camera model
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

        # Return default values if not found
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
    
    def get_file_size(self, camera_name, sensor_mode):
        resolution_info = self.get_resolution_info(camera_name, sensor_mode)
        return resolution_info.get('file_size', None)