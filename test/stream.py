import logging
import os
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import redis
import time

class Stream:
    def __init__(self, redis_controller, cinepi_controller, simple_gui):
        self.app = Flask(__name__)
        self.socketio = SocketIO(self.app)
        self.redis_controller = redis_controller
        self.stream_url = "http://cinepi.local:8000/stream"
        self.cinepi_controller = cinepi_controller
        self.simple_gui = simple_gui
        
        self.background_color = self.simple_gui.get_background_color()
        
        # Set the absolute path to the templates folder
        template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
        self.app.template_folder = template_dir

        # Fetch current values from Redis and set them in RedisController instance
        self.set_initial_values()

        # Routes
        self.app.add_url_rule('/', 'index', self.index)
        
        self.app.add_url_rule('/iso_value', 'get_iso_value', self.get_iso_value)
        self.app.add_url_rule('/shutter_a_value', 'get_shutter_a_value', self.get_shutter_a_value)
        self.app.add_url_rule('/fps_value', 'get_fps_value', self.get_fps_value)
        self.app.add_url_rule('/background_color_value', 'get_background_color_value', self.get_background_color_value)
        
        self.app.add_url_rule('/set_iso', 'set_iso_value', self.set_iso_value, methods=['POST'])
        self.app.add_url_rule('/set_shutter_a', 'set_shutter_a_value', self.set_shutter_a_value, methods=['POST'])
        self.app.add_url_rule('/set_fps', 'set_fps_value', self.set_fps_value, methods=['POST'])

        # Route to handle background color toggle
        self.app.add_url_rule('/handle_container_tap', 'handle_container_tap', self.handle_container_tap, methods=['POST'])

    def set_initial_values(self):
        # Fetch current values from Redis and set them in RedisController instance
        iso_value = self.redis_controller.get_value("iso")
        if iso_value:
            self.redis_controller.set_value("iso", iso_value)

        shutter_a_value = self.redis_controller.get_value("shutter_a")
        if shutter_a_value:
            self.redis_controller.set_value("shutter_a", shutter_a_value)

        fps_value = self.redis_controller.get_value("fps")
        if fps_value:
            self.redis_controller.set_value("fps_actual", fps_value)
            
    def index(self):
        # Fetch current values from Redis
        iso_value = self.redis_controller.get_value("iso")
        shutter_a_value = self.redis_controller.get_value("shutter_a")
        fps_value = self.redis_controller.get_value("fps")
        background_color_value = self.simple_gui.get_background_color()
        
        # Initialize dynamic data with default values or fetched values
        dynamic_data = {
            "iso": iso_value if iso_value else "Initializing...",
            "shutter_a": shutter_a_value if shutter_a_value else "Initializing...",
            "fps": fps_value if fps_value else "Initializing...",
            "background_color": background_color_value if background_color_value else "Initializing...",
        }
        
        # Pass colors from simple_gui to template
        background_color = self.simple_gui.get_background_color()
        
        # Render the template with dynamic data, stream_url, and colors
        return render_template('template.html', stream_url=self.stream_url, dynamic_data=dynamic_data,
                               iso_values=self.cinepi_controller.iso_steps, shutter_speed_values=self.cinepi_controller.shutter_a_steps_trunc,
                               fps_values=self.cinepi_controller.fps_steps_trunc, background_color = background_color)

    def get_iso_value(self):
        iso_value = self.redis_controller.get_value("iso")  # Fetch ISO value from Redis
        return jsonify({"iso": iso_value})

    def get_shutter_a_value(self):
        shutter_a_value = self.redis_controller.get_value("shutter_a")  # Fetch Shutter Angle value from Redis
        return jsonify({"shutter_a": shutter_a_value})

    def get_fps_value(self):
        fps_value = self.redis_controller.get_value("fps_actual")  # Fetch FPS value from Redis
        return jsonify({"fps": fps_value})
    
    def get_background_color_value(self):
        background_color_value = self.simple_gui.get_background_color()  
        return jsonify({"background_color": background_color_value})

    def set_iso_value(self):
        iso = request.json.get('iso')
        if iso:
            self.cinepi_controller.set_iso(int(iso))
            return jsonify({"status": "success", "iso": iso})
        else:
            return jsonify({"status": "error", "message": "ISO value not provided"})

    def set_shutter_a_value(self):
        shutter_a = request.json.get('shutter_a')
        if shutter_a:
            self.cinepi_controller.set_shutter_a(float(shutter_a))
            return jsonify({"status": "success", "shutter_a": shutter_a})
        else:
            return jsonify({"status": "error", "message": "Shutter Angle value not provided"})

    def set_fps_value(self):
        fps = request.json.get('fps')
        if fps:
            self.cinepi_controller.set_fps(int(fps))
            return jsonify({"status": "success", "fps": fps})
        else:
            return jsonify({"status": "error", "message": "FPS value not provided"})


    def set_background_color_value(self):
        set_background_color = request.json.get('background_color')
        if background_color:
            return jsonify({"status": "success", "background_color": background_color})
        else:
            return jsonify({"status": "error", "message": "background_color value not provided"})

    def handle_container_tap(self):
        logging.info('Toggling')
        self.cinepi_controller.rec()
        return jsonify({"status": "success", "handle_container_tap": handle_container_tap})
    
    def run(self, host='0.0.0.0', port=5000):
        # Adjust Flask's internal log level to ERROR (or higher) to mute INFO messages
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        
        self.app.run(host=host, port=port)