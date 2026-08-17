from flask import Blueprint, current_app, render_template, request

from module.web_api_settings import web_api_settings

main_routes = Blueprint('main', __name__)

# cinepi-raw serves the clean MJPEG preview on 8000 (cam0) and 8001 (cam1).
CAM0_STREAM_PORT = 8000
CAM1_STREAM_PORT = 8001


def _stream_host():
    """Host the browser reached us on, without the :5000 port.

    Hardcoding cinepi.local breaks on the hotspot, where the camera is
    10.42.0.1 and mDNS is not guaranteed (see docs/web-api.md "Address").
    Whatever host resolved for this page also resolves for the stream.
    """
    host = request.host.rsplit(':', 1)[0]
    return host or 'cinepi.local'


@main_routes.route('/')
def index():
    simple_gui = current_app.config['SIMPLE_GUI']
    settings = current_app.config['SETTINGS']

    host = _stream_host()

    # First paint only. Every displayed value arrives over Socket.IO as
    # `initial_values` (the full populate_values() dict) the moment the
    # socket connects, and as `gui_data_change` deltas after that.
    return render_template(
        'template.html',
        stream_url=f'http://{host}:{CAM0_STREAM_PORT}/stream',
        stream_url_cam1=f'http://{host}:{CAM1_STREAM_PORT}/stream',
        background_color=simple_gui.get_background_color(),
        api_token=web_api_settings(settings).get('token') or '',
    )
