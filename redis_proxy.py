import redis
import os

r = redis.Redis(host='localhost', port=6379, db=0)

class Control:
    def __init__(self, device):
        self.device = device

    def get_control_value(self, control):
        res = r.get(control)
        return res.decode() if res is not None else None

    def set_control_value(self, control, value):
        r.set(control, value)
        r.publish("cp_controls", control)
        return True

class CameraParameters:
    def __init__(self, type):
        self.type = type
        self.controls = Control('/dev/video0')

    def __repr__(self):
        return self.value

    def __str__(self):
        return str(self.value)

    def __convert__(self, value=None):

        if self.type == "ISO":
            if not value:
                iso_value = self.controls.get_control_value("iso")
                return iso_value
            else:
                self.controls.set_control_value("iso", value)

        elif self.type == "SHUTTER":
            if not value:
                shutter_angle_value = r.get("shutter_a").decode()
                return shutter_angle_value
                
            else:
                shutter_angle = self.controls.set_control_value("shutter_a", value)
        
        elif self.type == "FPS":
            if not value:
                fps = self.controls.get_control_value("fps")
                return fps
            else:
                self.controls.set_control_value("fps", value)
                return True
        
        elif self.type == "SHUTTER_FPS_SYNCED": # shutter_angle changes with fps, keeping exposure constant
            if not value:    
                shutter_angle = r.get("shutter_a").decode()
                return shutter_angle
            else:
                exposure_time = (value / 360) / 24
                angle_to_set = int(exposure_time * int(r.get("fps").decode()) * 360)
                if angle_to_set > 360:
                    angle_to_set = 360
                shutter_angle = self.controls.set_control_value("shutter_a", angle_to_set)
                return True
            
        elif self.type == "RESOLUTION":
            if not value:
                resolution_value = r.get("height").decode()
                return resolution_value
            else:
                self.controls.set_control_value("height", value)
                cam_init = self.controls.set_control_value("cam_init", 1)
                return True
            
        elif self.type == "IS_RECORDING":
            if not value:
                is_recording_value = r.get("is_recording").decode()
                return is_recording_value
            else:
                self.controls.set_control_value("is_recording", value)
                return True
        


    def get(self):
        self.value = self.__convert__()
        return self.value

    def set(self, value):
        self.__convert__(value=value)
        self.value = value
        return self.value
    
    
class RedisMonitor:
    
    def __init__(self, channel):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
        self.redis_sub = self.redis_client.pubsub()
        self.redis_sub.subscribe(channel)
        self.last_number = None
        self.increasing_number = None
        self.is_increasing = False

    def check_number(self):
        return self.increasing_number

    def is_number_increasing(self):
        return self.is_increasing

    def listen(self):
        counter = 0
        self.is_increasing = False
        for message in self.redis_sub.listen():
            if counter >= 4:
                break
            
            message_data = message['data']
            
            if isinstance(message_data, bytes):
                decoded_message = message_data.decode()
                message_str = (f'{decoded_message}')
            else:
                message_str = (f'{message_data}')
            
            if message_str.startswith('F:'):
                number_str = message_str.split(':')[1]
                number = int(number_str)
                if self.last_number is not None and number > self.last_number:
                    self.last_number = number
                    if self.increasing_number is None or number > self.increasing_number:
                        self.increasing_number = number
                        self.is_increasing = True
                    else:
                        self.is_increasing = False
                elif self.last_number is None:
                    self.last_number = number
                
                counter += 1