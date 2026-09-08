import logging
import urllib.error
import urllib.request

from flask import (
    Blueprint,
    Response,
    current_app,
    render_template,
    request,
    stream_with_context,
    url_for,
)

from module.web_api_settings import web_api_settings

logger = logging.getLogger(__name__)

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


def _stream_url_for(cam):
    """Where the browser should fetch cam *cam*'s preview from.

    Over plain HTTP the browser talks straight to cinepi-raw on 8000/8001,
    which costs CineMate nothing.

    Over HTTPS it cannot: cinepi-raw's MJPEG server speaks only plain HTTP,
    and a secure page is not allowed to load an insecure subresource, so the
    direct URL is blocked outright and the preview goes black. The same-origin
    proxy below is the only way to keep a picture on an HTTPS page, so it is
    used exactly when the page was served over TLS and never otherwise.
    """
    if request.is_secure:
        return url_for('main.preview_stream', cam=cam)
    port = CAM0_STREAM_PORT if cam == 0 else CAM1_STREAM_PORT
    return f'http://{_stream_host()}:{port}/stream'


@main_routes.route('/preview/<int:cam>/stream')
def preview_stream(cam):
    """Relay cinepi-raw's MJPEG stream from this origin.

    Only reached on an HTTPS page (see _stream_url_for). Streamed straight
    through in multipart-sized chunks rather than buffered: the response never
    ends, so anything that accumulates it would grow without bound.
    """
    if cam not in (0, 1):
        return Response('Unknown camera', status=404, mimetype='text/plain')
    port = CAM0_STREAM_PORT if cam == 0 else CAM1_STREAM_PORT
    upstream_url = f'http://127.0.0.1:{port}/stream'

    try:
        upstream = urllib.request.urlopen(upstream_url, timeout=5)
    except (urllib.error.URLError, OSError) as exc:
        # A 404 here is cinepi-raw not having published a frame yet, which is
        # normal during boot; the page's <img> retries on error.
        logger.info('Preview proxy could not reach %s: %s', upstream_url, exc)
        return Response('Preview not available', status=503, mimetype='text/plain')

    content_type = upstream.headers.get(
        'Content-Type', 'multipart/x-mixed-replace; boundary=nadjiebmjpegstreamer')

    def relay():
        try:
            while True:
                chunk = upstream.read(16384)
                if not chunk:
                    break
                yield chunk
        except (OSError, GeneratorExit):
            pass
        finally:
            upstream.close()

    response = Response(stream_with_context(relay()), content_type=content_type)
    response.headers['Cache-Control'] = 'no-store'
    return response


@main_routes.route('/')
def index():
    simple_gui = current_app.config['SIMPLE_GUI']
    settings = current_app.config['SETTINGS']

    # First paint only. Every displayed value arrives over Socket.IO as
    # `initial_values` (the full populate_values() dict) the moment the
    # socket connects, and as `gui_data_change` deltas after that.
    return render_template(
        'template.html',
        stream_url=_stream_url_for(0),
        stream_url_cam1=_stream_url_for(1),
        background_color=simple_gui.get_background_color(),
        api_token=web_api_settings(settings).get('token') or '',
    )
