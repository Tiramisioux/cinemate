"""Cinemate Web API — /api/v1.

Thin HTTP/SSE adapter over CommandExecutor.handle_received_data(). This
module never parses command lines, coerces arguments, or special-cases
`rec` itself — that dispatch logic lives in module.cli_commands, shared
with the CLI and serial paths. See docs/web-api.md for the wire contract
and dev-notes/web-api/IMPLEMENTATION-PLAN.md for the internals.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from module.redis_controller import ParameterKey
from module.web_api_settings import web_api_settings

logger = logging.getLogger(__name__)

api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1')

CINEMATE_VERSION = "3.3.2"

# The only commands `allow_destructive: false` blocks (plan section 5). All
# four are single, no-prefix-collision words in CommandExecutor.commands,
# so matching the first token of the line is exact, not a re-parse of the
# dispatcher's longest-prefix table.
DESTRUCTIVE_COMMANDS = frozenset({"reboot", "shutdown", "erase", "format"})

_PARAMETER_KEY_VALUES = [p.value for p in ParameterKey]

_DISPATCH_ERROR_STATUS = {
    "unknown command": 400,
    "bad argument": 400,
    "missing argument": 400,
    "busy": 503,
}


class _RateLimiter:
    """In-memory sliding-window per-client limit. Resets on process
    restart — acceptable for a hotspot with a handful of controllers."""

    def __init__(self):
        self._hits = {}
        self._lock = threading.Lock()

    def allow(self, client_key, max_per_sec):
        if max_per_sec is None or max_per_sec <= 0:
            return True
        now = time.monotonic()
        window_start = now - 1.0
        with self._lock:
            hits = [t for t in self._hits.get(client_key, ()) if t > window_start]
            if len(hits) >= max_per_sec:
                self._hits[client_key] = hits
                return False
            hits.append(now)
            self._hits[client_key] = hits
            return True


_rate_limiter = _RateLimiter()
_sse_lock = threading.Lock()
_sse_client_count = 0


def _wants_json():
    return request.args.get("json") == "1"


def _respond(ok, cmd_line, message, error_status=400):
    if _wants_json():
        return jsonify({"ok": ok, "cmd": cmd_line, "message": message}), (200 if ok else error_status)
    if ok:
        body = "ok" if not message else f"ok {message}"
        return Response(body, status=200, mimetype="text/plain")
    return Response(f"err {message}", status=error_status, mimetype="text/plain")


@api_v1.before_request
def _enforce_token():
    settings = current_app.config['SETTINGS']
    token = web_api_settings(settings).get("token") or ""
    if not token:
        return None
    if request.headers.get("X-Cinemate-Token", "") != token:
        if _wants_json():
            return jsonify({"ok": False, "cmd": "", "message": "unauthorized"}), 401
        return Response("err unauthorized", status=401, mimetype="text/plain")
    return None


def _extract_command_line():
    if request.method == "POST":
        return (request.get_data(as_text=True) or "").strip()
    return (request.args.get("c") or "").strip()


@api_v1.route('/cmd', methods=['GET', 'POST'])
def cmd():
    settings = current_app.config['SETTINGS']
    command_executor = current_app.config['COMMAND_EXECUTOR']
    cfg = web_api_settings(settings)

    line = _extract_command_line()
    if not line:
        return _respond(False, "", "unknown command", error_status=400)

    first_token = line.split()[0].lower()
    if first_token in DESTRUCTIVE_COMMANDS and not cfg.get("allow_destructive", False):
        return _respond(False, line, "blocked", error_status=403)

    client_key = request.remote_addr or "unknown"
    if not _rate_limiter.allow(client_key, cfg.get("max_commands_per_sec")):
        return _respond(False, line, "rate limited", error_status=429)

    ok, message = command_executor.handle_received_data(line)
    error_status = _DISPATCH_ERROR_STATUS.get(message, 400)
    return _respond(ok, line, message, error_status=error_status)


@api_v1.route('/get/<key>')
def get_value(key):
    redis_controller = current_app.config['REDIS_CONTROLLER']
    try:
        param = ParameterKey(key)
    except ValueError:
        return Response("err unknown key", status=404, mimetype="text/plain")
    return Response(str(redis_controller.get_value(param.value, "")), status=200, mimetype="text/plain")


@api_v1.route('/status')
def status():
    redis_controller = current_app.config['REDIS_CONTROLLER']
    keys_param = request.args.get('keys')
    if keys_param:
        requested = [k.strip() for k in keys_param.split(',') if k.strip()]
        keys = [k for k in requested if k in _PARAMETER_KEY_VALUES]
    else:
        keys = _PARAMETER_KEY_VALUES

    data = {k: redis_controller.get_value(k, "") for k in keys}

    if request.args.get('fmt') == 'text':
        body = "\n".join(f"{k}={v}" for k, v in data.items())
        return Response(body, status=200, mimetype="text/plain")
    return jsonify(data)


@api_v1.route('/commands')
def commands():
    command_executor = current_app.config['COMMAND_EXECUTOR']
    entries = []
    for name, (_func, expected_types) in command_executor.commands.items():
        if expected_types is None:
            arg = None
        elif isinstance(expected_types, list):
            type_names = [t.__name__ for t in expected_types if t is not None]
            arg = "|".join(type_names) if type_names else None
        else:
            arg = expected_types.__name__
        entries.append({"name": name, "arg": arg})

    if request.args.get('fmt') == 'text':
        return Response("\n".join(e["name"] for e in entries), status=200, mimetype="text/plain")
    return jsonify(entries)


@api_v1.route('/hello')
def hello():
    redis_controller = current_app.config['REDIS_CONTROLLER']
    sensor = redis_controller.get_value(ParameterKey.SENSOR.value, "unknown")
    cams = redis_controller.get_value(ParameterKey.CAMERAS.value, "1")
    rec = redis_controller.get_value(ParameterKey.IS_RECORDING.value, "0")
    body = f"cinemate {CINEMATE_VERSION} api=1 sensor={sensor} cams={cams} rec={rec}"
    return Response(body, status=200, mimetype="text/plain")


@api_v1.route('/events')
def events():
    global _sse_client_count

    settings = current_app.config['SETTINGS']
    redis_controller = current_app.config['REDIS_CONTROLLER']
    max_clients = web_api_settings(settings).get('max_sse_clients', 4)

    with _sse_lock:
        if _sse_client_count >= max_clients:
            return Response("err too many clients", status=503, mimetype="text/plain")
        _sse_client_count += 1

    # Bounded so a stalled-but-not-yet-closed connection (e.g. Wi-Fi drops
    # without a clean FIN) can't grow this queue unbounded on the Pi.
    q = queue.Queue(maxsize=200)

    def on_change(data):
        try:
            q.put_nowait(f"data: {data['key']}={data['value']}\n\n")
        except queue.Full:
            pass

    redis_controller.redis_parameter_changed.subscribe(on_change)

    def gen():
        global _sse_client_count
        try:
            last_heartbeat = time.monotonic()
            while True:
                try:
                    yield q.get(timeout=1.0)
                except queue.Empty:
                    pass
                now = time.monotonic()
                if now - last_heartbeat >= 15.0:
                    yield ": ping\n\n"
                    last_heartbeat = now
        finally:
            redis_controller.redis_parameter_changed.unsubscribe(on_change)
            with _sse_lock:
                _sse_client_count -= 1

    return Response(stream_with_context(gen()), mimetype='text/event-stream')
