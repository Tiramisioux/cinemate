import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

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


class StoragePrerollTests(unittest.TestCase):
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
