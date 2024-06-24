import os
from flask import Flask
from flask_socketio import SocketIO

def create_app(redis_controller, cinepi_controller, simple_gui):
    app = Flask(__name__)
    socketio = SocketIO(app)

    app.config['REDIS_CONTROLLER'] = redis_controller
    app.config['CINEPI_CONTROLLER'] = cinepi_controller
    app.config['SIMPLE_GUI'] = simple_gui

    from .main.routes import main_routes
    from .main.events import register_events
    app.register_blueprint(main_routes)
    register_events(socketio, redis_controller, cinepi_controller, simple_gui)

    return app, socketio
