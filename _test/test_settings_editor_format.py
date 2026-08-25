"""POST /settings-editor/api/raw/format -- the RAW pane's format-drive control.

The dispatcher discards handler return values, so a successful dispatch says
nothing about whether mkfs worked. These tests pin the endpoint's actual
success test: what filesystem is mounted at the active root once the
dispatch returns.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

# Same mechanism as test_web_api_blueprint.py: stub the parent package so the
# `settings_editor` submodule resolves via __path__ without executing
# module/app/__init__.py's flask_socketio import.
_APP_PKG = types.ModuleType("module.app")
_APP_PKG.__path__ = [str(ROOT / "src" / "module" / "app")]
sys.modules.setdefault("module.app", _APP_PKG)

from flask import Flask

from module.app import raw_files
from module.app.settings_editor import settings_editor_bp
from module.cli_commands import CommandExecutor
from module.redis_controller import ParameterKey


class FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)


def make_app(redis_values=None, with_executor=True):
    app = Flask(__name__)
    app.testing = True
    controller = mock.MagicMock()
    command_executor = CommandExecutor(controller, mock.MagicMock()) if with_executor else None
    if command_executor is not None:
        app.config["COMMAND_EXECUTOR"] = command_executor
    app.config["REDIS_CONTROLLER"] = FakeRedis(redis_values)
    app.config["SETTINGS"] = {}
    app.register_blueprint(settings_editor_bp)
    return app, controller, command_executor


def storage(filesystem, active=True):
    """One mounted-drive summary shaped like raw_files.storage_summary()."""
    return [{
        "label": "RAW",
        "active": active,
        "total_bytes": 500 * 1000 ** 3,
        "free_bytes": 500 * 1000 ** 3,
        "filesystem": filesystem,
        "device": "/dev/sda1",
        "take_count": 0,
    }]


def post(app, filesystem):
    return app.test_client().post("/settings-editor/api/raw/format", json={"filesystem": filesystem})


class FormatValidationTests(unittest.TestCase):
    def test_unsupported_filesystem_is_400_and_dispatches_nothing(self):
        app, controller, _ = make_app()
        res = post(app, "vfat")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["ok"])
        controller.format_drive.assert_not_called()

    def test_missing_filesystem_is_400(self):
        app, controller, _ = make_app()
        res = app.test_client().post("/settings-editor/api/raw/format", json={})
        self.assertEqual(res.status_code, 400)
        controller.format_drive.assert_not_called()

    def test_refuses_while_recording_with_409(self):
        app, controller, _ = make_app(redis_values={ParameterKey.IS_RECORDING.value: "1"})
        res = post(app, "ext4")
        self.assertEqual(res.status_code, 409)
        self.assertIn("recording", res.get_json()["message"].lower())
        controller.format_drive.assert_not_called()

    def test_missing_command_executor_is_503(self):
        app, controller, _ = make_app(with_executor=False)
        res = post(app, "ext4")
        self.assertEqual(res.status_code, 503)
        controller.format_drive.assert_not_called()

    def test_held_dispatch_lock_reports_busy_as_503(self):
        app, controller, command_executor = make_app()
        # Non-reentrant Lock, and the test client runs the request on this
        # thread, so the handler's 2 s acquire times out and returns "busy".
        self.assertTrue(command_executor._dispatch_lock.acquire())
        try:
            res = post(app, "ext4")
        finally:
            command_executor._dispatch_lock.release()
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.get_json()["message"], "busy")
        controller.format_drive.assert_not_called()


class FormatOutcomeTests(unittest.TestCase):
    def test_requested_filesystem_mounted_is_success(self):
        app, controller, _ = make_app()
        with mock.patch.object(raw_files, "storage_summary", return_value=storage("ext4")):
            res = post(app, "ext4")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["ok"])
        controller.format_drive.assert_called_once_with("ext4")

    def test_old_filesystem_still_mounted_is_500(self):
        app, controller, _ = make_app()
        with mock.patch.object(raw_files, "storage_summary", return_value=storage("exfat")):
            res = post(app, "ext4")
        self.assertEqual(res.status_code, 500)
        self.assertFalse(res.get_json()["ok"])
        self.assertIn("exfat", res.get_json()["message"])
        controller.format_drive.assert_called_once_with("ext4")

    def test_no_remount_is_500(self):
        app, _, _ = make_app()
        with mock.patch.object(raw_files, "storage_summary", return_value=[]):
            res = post(app, "ext4")
        self.assertEqual(res.status_code, 500)
        self.assertFalse(res.get_json()["ok"])
        self.assertIn("did not remount", res.get_json()["message"])

    def test_standby_only_mount_does_not_count_as_success(self):
        app, _, _ = make_app()
        with mock.patch.object(raw_files, "storage_summary",
                               return_value=storage("ext4", active=False)):
            res = post(app, "ext4")
        self.assertEqual(res.status_code, 500)
        self.assertFalse(res.get_json()["ok"])

    def test_ntfs3_counts_as_ntfs(self):
        app, controller, _ = make_app()
        with mock.patch.object(raw_files, "storage_summary", return_value=storage("ntfs3")):
            res = post(app, "ntfs")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["ok"])
        controller.format_drive.assert_called_once_with("ntfs")

    def test_fuseblk_counts_as_ntfs(self):
        app, _, _ = make_app()
        with mock.patch.object(raw_files, "storage_summary", return_value=storage("fuseblk")):
            res = post(app, "ntfs")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["ok"])

    def test_ntfs_alias_does_not_satisfy_an_ext4_request(self):
        app, _, _ = make_app()
        with mock.patch.object(raw_files, "storage_summary", return_value=storage("fuseblk")):
            res = post(app, "ext4")
        self.assertEqual(res.status_code, 500)
        self.assertFalse(res.get_json()["ok"])

    def test_filesystem_is_normalised_before_dispatch(self):
        app, controller, _ = make_app()
        with mock.patch.object(raw_files, "storage_summary", return_value=storage("exfat")):
            res = post(app, "  ExFAT  ")
        self.assertEqual(res.status_code, 200)
        controller.format_drive.assert_called_once_with("exfat")


if __name__ == "__main__":
    unittest.main()
