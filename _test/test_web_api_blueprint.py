import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from flask import Flask

# module.app.api itself only imports flask (not flask_socketio), but
# `import module.app.api` first executes module/app/__init__.py, which does
# import flask_socketio -- not installed in this environment. Stub the
# parent package in sys.modules so Python's import machinery resolves the
# `api` submodule via __path__ without running the real __init__.py.
_APP_PKG = types.ModuleType("module.app")
_APP_PKG.__path__ = [str(ROOT / "src" / "module" / "app")]
sys.modules.setdefault("module.app", _APP_PKG)

from module.app import api as api_module
from module.cli_commands import CommandExecutor
from module.redis_controller import ParameterKey


class FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)


def make_app(settings=None, redis_values=None):
    app = Flask(__name__)
    app.testing = True
    controller = mock.MagicMock()
    command_executor = CommandExecutor(controller, mock.MagicMock())
    app.config['SETTINGS'] = settings or {}
    app.config['COMMAND_EXECUTOR'] = command_executor
    app.config['REDIS_CONTROLLER'] = FakeRedis(redis_values)
    app.register_blueprint(api_module.api_v1)
    # Reset the module-level SSE client counter between tests.
    api_module._sse_client_count = 0
    return app, controller, command_executor


class CmdEndpointTests(unittest.TestCase):
    def test_post_rec_dispatches_and_returns_plain_ok(self):
        app, controller, _ = make_app()
        client = app.test_client()
        resp = client.post('/api/v1/cmd', data='rec', content_type='text/plain')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), 'ok')
        controller.rec.assert_called_once_with(record_override=None)

    def test_get_cmd_with_query_param(self):
        app, controller, _ = make_app()
        client = app.test_client()
        resp = client.get('/api/v1/cmd?c=set+iso+800')
        self.assertEqual(resp.status_code, 200)
        controller.set_iso.assert_called_once_with(800)

    def test_get_cmd_accepts_percent20(self):
        app, controller, _ = make_app()
        client = app.test_client()
        resp = client.get('/api/v1/cmd?c=set%20iso%20800')
        self.assertEqual(resp.status_code, 200)
        controller.set_iso.assert_called_once_with(800)

    def test_unknown_command_is_400(self):
        app, _, _ = make_app()
        client = app.test_client()
        resp = client.post('/api/v1/cmd', data='nonsense', content_type='text/plain')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_data(as_text=True), 'err unknown command')

    def test_bad_argument_is_400(self):
        app, _, _ = make_app()
        client = app.test_client()
        resp = client.post('/api/v1/cmd', data='set iso notanumber', content_type='text/plain')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_data(as_text=True), 'err bad argument')

    def test_empty_body_is_400_unknown_command(self):
        app, _, _ = make_app()
        client = app.test_client()
        resp = client.post('/api/v1/cmd', data='', content_type='text/plain')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_data(as_text=True), 'err unknown command')

    def test_json_flag_returns_structured_body(self):
        app, _, _ = make_app()
        client = app.test_client()
        resp = client.post('/api/v1/cmd?json=1', data='rec', content_type='text/plain')
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.get_data(as_text=True))
        self.assertEqual(body, {"ok": True, "cmd": "rec", "message": ""})

    def test_json_flag_error_body(self):
        app, _, _ = make_app()
        client = app.test_client()
        resp = client.post('/api/v1/cmd?json=1', data='nonsense', content_type='text/plain')
        self.assertEqual(resp.status_code, 400)
        body = json.loads(resp.get_data(as_text=True))
        self.assertEqual(body, {"ok": False, "cmd": "nonsense", "message": "unknown command"})


class DestructiveGatingTests(unittest.TestCase):
    def test_format_blocked_by_default(self):
        app, controller, _ = make_app()
        client = app.test_client()
        resp = client.post('/api/v1/cmd', data='format', content_type='text/plain')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_data(as_text=True), 'err blocked')
        controller.format_drive.assert_not_called()

    def test_reboot_blocked_by_default(self):
        app, controller, _ = make_app()
        client = app.test_client()
        resp = client.post('/api/v1/cmd', data='reboot', content_type='text/plain')
        self.assertEqual(resp.status_code, 403)
        controller.reboot.assert_not_called()

    def test_unmount_is_not_destructive(self):
        # plan section 5: unmount stays allowed -- it is routine and reversible.
        app, controller, _ = make_app()
        client = app.test_client()
        resp = client.post('/api/v1/cmd', data='unmount', content_type='text/plain')
        self.assertEqual(resp.status_code, 200)
        controller.unmount.assert_called_once()

    def test_allow_destructive_true_permits_format(self):
        app, controller, _ = make_app(settings={"system": {"web_api": {"allow_destructive": True}}})
        client = app.test_client()
        resp = client.post('/api/v1/cmd', data='format', content_type='text/plain')
        self.assertEqual(resp.status_code, 200)
        controller.format_drive.assert_called_once()


class TokenAuthTests(unittest.TestCase):
    def test_no_token_configured_allows_all_requests(self):
        app, _, _ = make_app()
        client = app.test_client()
        resp = client.get('/api/v1/hello')
        self.assertEqual(resp.status_code, 200)

    def test_wrong_token_is_401(self):
        app, _, _ = make_app(settings={"system": {"web_api": {"token": "s3cret"}}})
        client = app.test_client()
        resp = client.get('/api/v1/hello')
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_data(as_text=True), 'err unauthorized')

    def test_correct_token_is_allowed(self):
        app, _, _ = make_app(settings={"system": {"web_api": {"token": "s3cret"}}})
        client = app.test_client()
        resp = client.get('/api/v1/hello', headers={"X-Cinemate-Token": "s3cret"})
        self.assertEqual(resp.status_code, 200)

    def test_token_applies_to_cmd_endpoint_too(self):
        app, controller, _ = make_app(settings={"system": {"web_api": {"token": "s3cret"}}})
        client = app.test_client()
        resp = client.post('/api/v1/cmd', data='rec', content_type='text/plain')
        self.assertEqual(resp.status_code, 401)
        controller.rec.assert_not_called()


class RateLimitTests(unittest.TestCase):
    def test_over_limit_returns_429(self):
        app, controller, _ = make_app(settings={"system": {"web_api": {"max_commands_per_sec": 3}}})
        client = app.test_client()
        statuses = []
        for _ in range(6):
            resp = client.post('/api/v1/cmd', data='inc iso', content_type='text/plain')
            statuses.append(resp.status_code)
        self.assertIn(429, statuses)
        self.assertLessEqual(controller.inc_iso.call_count, 3)

    def test_rate_limit_is_disabled_when_zero(self):
        app, controller, _ = make_app(settings={"system": {"web_api": {"max_commands_per_sec": 0}}})
        client = app.test_client()
        for _ in range(10):
            resp = client.post('/api/v1/cmd', data='inc iso', content_type='text/plain')
            self.assertEqual(resp.status_code, 200)
        self.assertEqual(controller.inc_iso.call_count, 10)


class GetKeyEndpointTests(unittest.TestCase):
    def test_known_key_returns_raw_value(self):
        app, _, _ = make_app(redis_values={"is_recording": "1"})
        client = app.test_client()
        resp = client.get('/api/v1/get/is_recording')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), '1')
        self.assertEqual(resp.mimetype, 'text/plain')

    def test_unknown_key_is_404(self):
        app, _, _ = make_app()
        client = app.test_client()
        resp = client.get('/api/v1/get/not_a_real_key')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_data(as_text=True), 'err unknown key')


class StatusEndpointTests(unittest.TestCase):
    def test_no_keys_returns_every_parameter(self):
        app, _, _ = make_app(redis_values={"iso": "800"})
        client = app.test_client()
        resp = client.get('/api/v1/status')
        body = json.loads(resp.get_data(as_text=True))
        self.assertEqual(set(body.keys()), {p.value for p in ParameterKey})
        self.assertEqual(body["iso"], "800")

    def test_keys_filter_returns_only_requested(self):
        app, _, _ = make_app(redis_values={"iso": "800", "fps": "24.0"})
        client = app.test_client()
        resp = client.get('/api/v1/status?keys=iso,fps')
        body = json.loads(resp.get_data(as_text=True))
        self.assertEqual(body, {"iso": "800", "fps": "24.0"})

    def test_unknown_keys_in_filter_are_silently_omitted(self):
        app, _, _ = make_app(redis_values={"iso": "800"})
        client = app.test_client()
        resp = client.get('/api/v1/status?keys=iso,not_a_real_key')
        body = json.loads(resp.get_data(as_text=True))
        self.assertEqual(body, {"iso": "800"})

    def test_fmt_text_returns_key_value_lines(self):
        app, _, _ = make_app(redis_values={"iso": "800", "fps": "24.0"})
        client = app.test_client()
        resp = client.get('/api/v1/status?keys=iso,fps&fmt=text')
        self.assertEqual(resp.mimetype, 'text/plain')
        lines = resp.get_data(as_text=True).splitlines()
        self.assertEqual(set(lines), {"iso=800", "fps=24.0"})


class CommandsEndpointTests(unittest.TestCase):
    def test_lists_every_registered_command(self):
        app, _, command_executor = make_app()
        client = app.test_client()
        resp = client.get('/api/v1/commands')
        body = json.loads(resp.get_data(as_text=True))
        names = {entry["name"] for entry in body}
        self.assertEqual(names, set(command_executor.commands.keys()))

    def test_rec_has_null_arg_and_set_iso_has_int_arg(self):
        app, _, _ = make_app()
        client = app.test_client()
        resp = client.get('/api/v1/commands')
        body = {entry["name"]: entry["arg"] for entry in json.loads(resp.get_data(as_text=True))}
        self.assertIsNone(body["rec"])
        self.assertEqual(body["set iso"], "int")

    def test_fmt_text_returns_one_name_per_line(self):
        app, _, command_executor = make_app()
        client = app.test_client()
        resp = client.get('/api/v1/commands?fmt=text')
        lines = set(resp.get_data(as_text=True).splitlines())
        self.assertEqual(lines, set(command_executor.commands.keys()))


class EventsEndpointTests(unittest.TestCase):
    def test_over_cap_returns_503_without_opening_a_stream(self):
        app, _, _ = make_app(settings={"system": {"web_api": {"max_sse_clients": 0}}})
        client = app.test_client()
        resp = client.get('/api/v1/events')
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.get_data(as_text=True), 'err too many clients')

    def test_emits_one_data_line_per_changed_key_and_cleans_up_on_close(self):
        from module.redis_controller import Event

        app, _, _ = make_app()
        redis_controller = app.config['REDIS_CONTROLLER']
        redis_controller.redis_parameter_changed = Event()

        with app.test_request_context('/api/v1/events'):
            resp = api_module.events()

        self.assertEqual(api_module._sse_client_count, 1)
        self.assertEqual(len(redis_controller.redis_parameter_changed._handlers), 1)

        gen = iter(resp.response)
        redis_controller.redis_parameter_changed.emit({"key": "iso", "value": "800"})
        self.assertEqual(next(gen), "data: iso=800\n\n")

        gen.close()
        self.assertEqual(api_module._sse_client_count, 0)
        self.assertEqual(len(redis_controller.redis_parameter_changed._handlers), 0)


class HelloEndpointTests(unittest.TestCase):
    def test_hello_reports_identity_from_redis(self):
        app, _, _ = make_app(redis_values={"sensor": "imx585", "cameras": "1", "is_recording": "0"})
        client = app.test_client()
        resp = client.get('/api/v1/hello')
        self.assertEqual(resp.status_code, 200)
        text = resp.get_data(as_text=True)
        self.assertTrue(text.startswith(f"cinemate {api_module.CINEMATE_VERSION} api=1 "))
        self.assertIn("sensor=imx585", text)
        self.assertIn("cams=1", text)
        self.assertIn("rec=0", text)


if __name__ == "__main__":
    unittest.main()
