from enum import Enum
import redis
import logging
import threading
import RPi.GPIO as GPIO

class ParameterKey(Enum):
    ANAMORPHIC_FACTOR = "anamorphic_factor"
    BIT_DEPTH = "bit_depth"
    BUFFER = "buffer"
    CAM_INIT = "cam_init"
    CAMERAS = "cameras"
    CG_RB = "cg_rb"
    FILE_SIZE = "file_size"
    FPS = "fps"
    FPS_ACTUAL = "fps_actual"
    FPS_LAST = "fps_last"
    FPS_MAX = "fps_max"
    FPS_USER = "fps_user"
    FRAMECOUNT = "framecount"
    GUI_LAYOUT = "gui_layout"
    HEIGHT = "height"
    IR_FILTER = "ir_filter"
    IS_BUFFERING = "is_buffering"
    IS_MOUNTED = "is_mounted"
    IS_RECORDING = "is_recording"
    IS_WRITING = "is_writing"
    IS_WRITING_BUF = "is_writing_buf"
    ISO = "iso"
    LORES_HEIGHT = "lores_height"
    LORES_WIDTH = "lores_width"
    PI_MODEL = "pi_model"
    REC = "rec"
    SENSOR = "sensor"
    SENSOR_MODE = "sensor_mode"
    SHUTTER_A = "shutter_a"
    SHUTTER_A_NOM = "shutter_a_nom"
    SPACE_LEFT = "space_left"
    STORAGE_TYPE = "storage_type"
    TRIGGER_MODE = "trigger_mode"
    WB = "wb"
    WB_USER = "wb_user"
    WIDTH = "width"
    MEMORY_ALERT   = "memory_alert"
    # Add more as needed

class Event:
    def __init__(self):
        self._listeners = []

    def subscribe(self, listener):
        self._listeners.append(listener)
        #print("Listener added:", listener)

    def emit(self, data=None):
        for listener in self._listeners:
            listener(data)

class RedisController:

    def __init__(self, host='localhost', port=6379, db=0, channel_name="cp_controls"):
        self.redis_client = redis.StrictRedis(host=host, port=port, db=db)
        self.pubsub = self.redis_client.pubsub()
        self.channel_name = channel_name
        
        self.lock = threading.Lock()
        
        self.redis_parameter_changed = Event()
        
        self.local_updates = set()

        
        # Cache to store the values
        self.cache = {}

        # Subscribe to the channel
        self.pubsub.subscribe(channel_name)

        # Initialize the cache with initial values
        self.init_cache()
        
        # Start the listener thread
        self.listener_thread = threading.Thread(target=self.listen)
        self.listener_thread.daemon = True  # This makes sure the thread will exit when the main program exits
        self.listener_thread.start()

    def init_cache(self):
        with self.lock:
            logging.info("Initializing cache with Redis values...")
            all_keys = self.redis_client.keys('*')
            for key in all_keys:
                value = self.redis_client.get(key)
                key_str = key.decode('utf-8')
                value_str = value.decode('utf-8')
                self.cache[key_str] = value_str
                #logging.info(f"Cached: {key_str} = {value_str}")

    def listen(self):
        for message in self.pubsub.listen():
            if message["type"] == "message":
                changed_key = message["data"].decode('utf-8')
                with self.lock:
                    value = self.redis_client.get(changed_key)
                    value_str = value.decode('utf-8')
                    self.cache[changed_key] = value_str

                    # If we just set this key ourselves, skip logging
                    if changed_key in self.local_updates:
                        self.local_updates.remove(changed_key)
                        continue

                if changed_key != ParameterKey.FPS_ACTUAL.value:
                    logging.info(f"Changed value: {changed_key} = {value_str}")
                    self.redis_parameter_changed.emit({'key': changed_key, 'value': value_str})


    def get_value(self, key, default=None):
        with self.lock:
            return self.cache.get(key, default)
        
    def get_int_value(self, key):
        value = self.redis_client.get(key)
        return int(value) if value else 0

    def set_value(self, key, value):
        with self.lock:
            current = self.cache.get(key)
            if str(current) == str(value):
                return

            self.redis_client.set(key, value)
            self.redis_client.publish('cp_controls', key)
            self.cache[key] = value

            self.local_updates.add(key)  # Track locally updated key

            if key != ParameterKey.FPS_ACTUAL.value:
                logging.info(f"Changed value: {key} = {value}")



    def stop_listener(self):
        with self.lock:
            # Unsubscribe and close the pubsub connection
            self.pubsub.unsubscribe()
            self.pubsub.close()
            # Here, we're not putting the join() inside the lock to avoid potential deadlocks
        self.listener_thread.join()