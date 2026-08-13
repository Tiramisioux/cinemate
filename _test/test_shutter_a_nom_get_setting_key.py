import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.cinepi_controller import CinePiController
from module.redis_controller import ParameterKey


class FakeRedis:
    def __init__(self, values):
        self.values = dict(values)

    def get_value(self, key, default=None):
        key = key.value if isinstance(key, ParameterKey) else key
        return self.values.get(key, default)


class GetSettingKeyResolutionTests(unittest.TestCase):
    """Unit-level coverage for get_setting() itself. The wiring-level
    consequences of this (increment_setting/decrement_setting no longer
    raising TypeError for shutter_a_nom) are covered by
    test_increment_decrement_setting.ShutterANomWiringTests.
    """

    def controller(self, redis_values):
        controller = CinePiController.__new__(CinePiController)
        controller.redis_controller = FakeRedis(redis_values)
        return controller

    def test_get_setting_resolves_shutter_a_nom_to_its_registry_redis_key(self):
        # Every writer (set_shutter_a_nom / update_shutter_angle_nom) persists
        # under ParameterKey.SHUTTER_A_NOM.value ("shutter_angle_nom"), which
        # is also the redis_key the parameters registry declares for the
        # "shutter_a_nom" name -- never the literal setting_name itself.
        controller = self.controller({ParameterKey.SHUTTER_A_NOM.value: "172.5"})

        self.assertEqual(controller.get_setting("shutter_a_nom"), "172.5")

    def test_get_setting_still_resolves_unmapped_keys_directly(self):
        controller = self.controller({ParameterKey.ISO.value: "800"})

        self.assertEqual(controller.get_setting("iso"), "800")


if __name__ == "__main__":
    unittest.main()
