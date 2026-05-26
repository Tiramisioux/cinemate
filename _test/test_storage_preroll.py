import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.config_loader import _apply_settings_defaults, auto_storage_preroll_enabled
from module.storage_preroll import StoragePreroll


class FakeController:
    def __init__(self):
        self.lock_override = False
        self.dynamic_resolution_suspended = False
        self.calls = []

    def set_fps(self, value):
        self.calls.append(
            {
                "value": value,
                "lock_override": self.lock_override,
                "dynamic_resolution_suspended": self.dynamic_resolution_suspended,
            }
        )


class FakeRedis:
    def __init__(self):
        self.values = {}

    def set_value(self, key, value):
        self.values[key] = value


class FakeMountEvent:
    def __init__(self):
        self.subscribers = []

    def subscribe(self, callback):
        self.subscribers.append(callback)


class FakeSsdMonitor:
    def __init__(self):
        self.mount_event = FakeMountEvent()


class StoragePrerollTests(unittest.TestCase):
    def test_settings_default_to_enabled(self):
        settings = _apply_settings_defaults({})

        self.assertTrue(settings["settings"]["auto_storage_preroll"])
        self.assertTrue(auto_storage_preroll_enabled(settings))

    def test_settings_can_disable_auto_preroll(self):
        settings = _apply_settings_defaults({"settings": {"auto_storage_preroll": False}})

        self.assertFalse(settings["settings"]["auto_storage_preroll"])
        self.assertFalse(auto_storage_preroll_enabled(settings))

    def test_legacy_top_level_setting_still_disables_auto_preroll(self):
        settings = _apply_settings_defaults({"storage_preroll": False})

        self.assertNotIn("storage_preroll", settings)
        self.assertFalse(settings["settings"]["auto_storage_preroll"])
        self.assertFalse(auto_storage_preroll_enabled(settings))

    def test_auto_disabled_preroll_does_not_subscribe_or_schedule(self):
        ssd_monitor = FakeSsdMonitor()
        preroll = StoragePreroll(
            cinepi_controller=FakeController(),
            redis_controller=FakeRedis(),
            ssd_monitor=ssd_monitor,
            sensor_detect=object(),
            auto_enabled=False,
        )

        self.assertEqual(ssd_monitor.mount_event.subscribers, [])
        self.assertFalse(preroll.mark_startup_ready())
        self.assertFalse(preroll.trigger(reason="test", delay=0.0))

    def test_manual_preroll_can_bypass_auto_disabled(self):
        ssd_monitor = FakeSsdMonitor()
        preroll = StoragePreroll(
            cinepi_controller=FakeController(),
            redis_controller=FakeRedis(),
            ssd_monitor=ssd_monitor,
            sensor_detect=object(),
            auto_enabled=False,
        )
        calls = []
        preroll.trigger = lambda **kwargs: calls.append(kwargs) or True

        preroll.trigger_manual()

        self.assertEqual(calls, [{"reason": "cli", "force": True}])

    def test_max_capacity_step_suspends_dynamic_resolution_only_temporarily(self):
        controller = FakeController()
        preroll = StoragePreroll.__new__(StoragePreroll)
        preroll.cinepi_controller = controller

        preroll._apply_fps(43, allow_dynamic_resolution=False)
        preroll._apply_fps(43, allow_dynamic_resolution=True)

        self.assertEqual(controller.calls[0]["value"], 43.0)
        self.assertTrue(controller.calls[0]["lock_override"])
        self.assertTrue(controller.calls[0]["dynamic_resolution_suspended"])
        self.assertEqual(controller.calls[1]["value"], 43.0)
        self.assertTrue(controller.calls[1]["lock_override"])
        self.assertFalse(controller.calls[1]["dynamic_resolution_suspended"])
        self.assertFalse(controller.lock_override)
        self.assertFalse(controller.dynamic_resolution_suspended)


if __name__ == "__main__":
    unittest.main()
