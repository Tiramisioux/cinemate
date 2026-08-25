from flask import Flask
from module.redis_controller import ParameterKey
from flask_socketio import SocketIO
import logging

def create_app(redis_controller, cinepi_controller, simple_gui, sensor_detect,
                command_executor, settings):
    app = Flask(__name__)
    
    # Adjust the logging level for the internal Flask logger
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # Set to ERROR to mute INFO messages

    socketio = SocketIO(app)
    if hasattr(simple_gui, 'set_socketio'):
        simple_gui.set_socketio(socketio)
    else:
        simple_gui.socketio = socketio

    if hasattr(cinepi_controller, 'add_resolution_change_callback'):
        def emit_resolution_change(sensor_mode):
            # Fires when the switch *starts* -- lets the browser show a
            # "switching..." state immediately. Must not carry reload_stream:
            # cinepi-raw is still restarting at this point, so the preview
            # <img> would reconnect to a stream that doesn't exist yet (F-290).
            socketio.emit('resolution_change', {
                'sensor_mode': sensor_mode,
                'resolution_switching': redis_controller.get_value(
                    ParameterKey.RESOLUTION_SWITCHING.value,
                    "0",
                ),
            })

        cinepi_controller.add_resolution_change_callback(emit_resolution_change)

    if hasattr(cinepi_controller, 'add_resolution_switch_complete_callback'):
        def emit_reload_stream():
            # Fires when the switch actually *completes* -- either evidence
            # from cinepi-raw's own "Raw stream: WxH" log line, or (if that
            # never arrives) the switching-hold fallback timer. Either way
            # the new stream exists by the time this runs (F-290).
            socketio.emit('reload_stream')

        cinepi_controller.add_resolution_switch_complete_callback(emit_reload_stream)

    app.config['REDIS_CONTROLLER'] = redis_controller
    app.config['CINEPI_CONTROLLER'] = cinepi_controller
    app.config['SIMPLE_GUI'] = simple_gui
    app.config['SENSOR_DETECT'] = sensor_detect
    app.config['COMMAND_EXECUTOR'] = command_executor
    app.config['SETTINGS'] = settings

    from .main.routes import main_routes
    from .main.events import register_events
    from .api import api_v1
    from .settings_editor import settings_editor_bp
    from module.web_api_settings import web_api_settings
    app.register_blueprint(main_routes)
    app.register_blueprint(settings_editor_bp)
    register_events(socketio, redis_controller, cinepi_controller, simple_gui, sensor_detect)

    if web_api_settings(settings).get('enabled', True):
        app.register_blueprint(api_v1)
        logging.info("Web API enabled at /api/v1")
    else:
        logging.info("Web API disabled (system.web_api.enabled=false)")

    return app, socketio
