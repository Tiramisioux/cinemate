import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

fake = types.ModuleType("module.redis_controller")
class _Key:
    def __init__(self, value):
        self.value = value
class ParameterKey:
    ZOOM = _Key("zoom")
fake.ParameterKey = ParameterKey
sys.modules.setdefault("module.redis_controller", fake)

from module.cinepi_multi import _resolve_launch_policy, _resolve_recording_profile


class TestCinePiLaunchAndProfile(unittest.TestCase):
    def test_profile_b_default(self):
        name, profile = _resolve_recording_profile({
            "recording_profiles": {
                "active": "B",
                "profiles": {"B": {"encode_workers": 2, "disk_workers": 1}},
            }
        })
        self.assertEqual(name, "B")
        self.assertEqual(profile["encode_workers"], 2)

    def test_launch_policy_defaults(self):
        policy = _resolve_launch_policy({})
        self.assertEqual(policy["rt_mode"], "off")
        self.assertEqual(policy["rt_priority"], 20)
        self.assertEqual(policy["cpu_affinity"], "1-3")


if __name__ == "__main__":
    unittest.main()
