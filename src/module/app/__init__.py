import os
from flask import Flask
from flask_socketio import SocketIO
import logging

def create_app(redis_controller, cinepi_controller, simple_gui, sensor_detect):
    app = Flask(__name__)
    
    # Adjust the logging level for the internal Flask logger
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # Set to ERROR to mute INFO messages

    socketio = SocketIO(app)

    app.config['REDIS_CONTROLLER'] = redis_controller
    app.config['CINEPI_CONTROLLER'] = cinepi_controller
    app.config['SIMPLE_GUI'] = simple_gui
    app.config['SENSOR_DETECT'] = sensor_detect

    from .main.routes import main_routes
    from .main.events import register_events
    app.register_blueprint(main_routes)
    register_events(socketio, redis_controller, cinepi_controller, simple_gui, sensor_detect)

    return app, socketio