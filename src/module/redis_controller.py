import redis
import logging
import threading
import RPi.GPIO as GPIO

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
                    # Update cache with new value
                    self.cache[changed_key] = value_str
                if changed_key != "fps_actual":
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
            if key == 'fps':
                if value >= 1:
                    fps_new = float(value)
                    frame_duration_new = int((1/fps_new) * 1000000)
                    self.redis_client.set('frame_duration', frame_duration_new)
                    self.redis_client.publish('cp_controls', 'frame_duration')
                    
                    self.redis_client.set('fps', value)
                    self.redis_client.publish('cp_controls', 'fps')
                    
                    self.redis_client.set('fps_user', value)
                    self.redis_client.publish('cp_controls', 'fps_user')
                    
                    # self.redis_client.set('cam_init', '1')
                    # self.redis_client.publish('cp_controls', 'cam_init')
                    self.redis_client.set(key, value)
                    # Notify about the key change via the cp_controls channel
                    self.redis_client.publish('cp_controls', key)
            else:
                self.redis_client.set(key, value)
                # Notify about the key change via the cp_controls channel
                self.redis_client.publish('cp_controls', key)
                
            # Update cache immediately
            self.cache[key] = value

    def stop_listener(self):
        with self.lock:
            # Unsubscribe and close the pubsub connection
            self.pubsub.unsubscribe()
            self.pubsub.close()
            # Here, we're not putting the join() inside the lock to avoid potential deadlocks
        self.listener_thread.join()