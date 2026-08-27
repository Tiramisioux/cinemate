import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.parameters import REGISTRY, get, menu_parameters


EXPECTED_NAMES = {
    "iso", "shutter_a", "shutter_a_nom", "fps", "wb", "zoom",
    "hdr_blend", "hdr_gain_adder", "hdr_threshold_low", "hdr_threshold_high",
}


class StubController:
    """Duck-typed stand-in exposing every attribute a steps callable reads."""

    def __init__(self):
        self.iso_steps = [100, 200, 400, 800, 1600, 3200]
        self.fps_steps = [1, 12, 24, 25, 50]
        self.wb_steps = [2800, 3200, 4000, 5600, 6500]
        self.current_fps = 25
        self.light_hz = [50.0]
        self.shutter_a_steps = [45.0, 90.0, 180.0, 270.0, 360.0]
        self.shutter_a_steps_dynamic = []
        self.settings = {"preview": {"zoom_steps": [0.5, 1.0, 1.5, 2.0]}}
        self.hdr_threshold_low_steps = [0, 512, 1024, 1536, 2048, 2560, 3072, 3584, 4095]
        self.hdr_threshold_high_steps = [0, 512, 1024, 1536, 2048, 2560, 3072, 3584, 4095]
        self.hdr_blend_steps = [0, 1, 2, 3, 4, 5, 6, 7, 8]
        self.hdr_gain_adder_steps = [0, 1, 2, 3, 4, 5]

    # Mirrors CinePiController.calculate_dynamic_shutter_angles enough for
    # the steps callable to have something real to call.
    def calculate_dynamic_shutter_angles(self, fps):
        dynamic = set(self.shutter_a_steps)
        for hz in self.light_hz:
            for multiple in range(1, 10):
                angle = (hz / (fps * multiple)) * 360
                if 1 <= angle <= 360:
                    dynamic.add(round(angle, 1))
        self.shutter_a_steps_dynamic = sorted(dynamic)
        return self.shutter_a_steps_dynamic


class RegistryCompletenessTests(unittest.TestCase):
    def test_registry_has_exactly_the_expected_parameters(self):
        self.assertEqual(set(REGISTRY.keys()), EXPECTED_NAMES)

    def test_every_entry_keyed_by_its_own_name(self):
        for name, param in REGISTRY.items():
            self.assertEqual(param.name, name)

    def test_every_entry_has_a_setter_and_valid_cycle_kind(self):
        for param in REGISTRY.values():
            self.assertTrue(param.setter)
            self.assertIn(param.cycle, ("steps", "direction"))

    def test_default_redis_key_and_setter_follow_the_naming_convention(self):
        # wb and shutter_a_nom are the documented exceptions.
        exceptions = {"wb": "wb_user", "shutter_a_nom": "shutter_angle_nom"}
        for name, param in REGISTRY.items():
            expected_redis_key = exceptions.get(name, name)
            self.assertEqual(param.redis_key, expected_redis_key)
            self.assertEqual(param.setter, f"set_{name}")


class GetLookupTests(unittest.TestCase):
    def test_get_returns_the_registered_parameter(self):
        param = get("iso")
        self.assertIsNotNone(param)
        self.assertEqual(param.name, "iso")

    def test_get_returns_none_for_unknown_name(self):
        self.assertIsNone(get("not_a_real_setting"))

    def test_get_warns_naming_the_source_on_unknown_name(self):
        with self.assertLogs("module.parameters", level="WARNING") as cm:
            get("not_a_real_setting", source="quad_rotary_controller")
        self.assertTrue(
            any("not_a_real_setting" in line and "quad_rotary_controller" in line
                for line in cm.output)
        )

    def test_get_does_not_warn_on_known_name(self):
        with self.assertNoLogs("module.parameters", level="WARNING"):
            get("iso", source="quad_rotary_controller")


class StepsCallableTests(unittest.TestCase):
    def setUp(self):
        self.controller = StubController()

    def test_every_steps_callable_resolves_against_a_stub_controller(self):
        for name, param in REGISTRY.items():
            with self.subTest(name=name):
                steps = param.steps(self.controller)
                self.assertIsInstance(steps, list)
                self.assertTrue(len(steps) > 0)

    def test_iso_steps_reads_the_live_controller_table(self):
        self.assertEqual(REGISTRY["iso"].steps(self.controller), self.controller.iso_steps)

    def test_fps_steps_reads_the_raw_uncapped_table(self):
        # increment_setting's fps branch uses whatever list inc_fps/dec_fps
        # pass in verbatim (self.fps_steps) - clamping happens later, inside
        # set_fps itself, not in the step-table resolution.
        self.assertEqual(REGISTRY["fps"].steps(self.controller), self.controller.fps_steps)

    def test_shutter_a_steps_recomputes_flicker_free_angles(self):
        steps = REGISTRY["shutter_a"].steps(self.controller)
        self.assertEqual(steps, self.controller.calculate_dynamic_shutter_angles(25))

    def test_shutter_a_nom_borrows_the_static_shutter_a_steps_attribute(self):
        # NOT shutter_a's own steps() callable: that one recomputes the
        # flicker-free-augmented table, but shutter_a_nom has only ever
        # cycled through the plain configured list (inc_shutter_a_nom
        # passes self.shutter_a_steps straight through to increment_setting).
        self.assertEqual(
            REGISTRY["shutter_a_nom"].steps(self.controller),
            self.controller.shutter_a_steps,
        )

    def test_shutter_a_nom_steps_do_not_include_flicker_free_additions(self):
        nom_steps = REGISTRY["shutter_a_nom"].steps(self.controller)
        dynamic_steps = REGISTRY["shutter_a"].steps(self.controller)
        self.assertLess(len(nom_steps), len(dynamic_steps))
        self.assertTrue(set(nom_steps).issubset(set(dynamic_steps)))

    def test_shutter_a_nom_borrows_shutter_a_policy(self):
        self.assertEqual(REGISTRY["shutter_a_nom"].policy_key, "shutter_a")
        self.assertEqual(REGISTRY["shutter_a_nom"].free_attr, "shutter_a_free")

    def test_shutter_a_nom_keeps_its_own_lock(self):
        self.assertEqual(REGISTRY["shutter_a_nom"].lock_attr, "shutter_a_nom_lock")
        self.assertNotEqual(REGISTRY["shutter_a_nom"].lock_attr, REGISTRY["shutter_a"].lock_attr)

    def test_zoom_steps_reads_preview_zoom_steps_not_an_arrays_key(self):
        self.assertEqual(REGISTRY["zoom"].steps(self.controller), [0.5, 1.0, 1.5, 2.0])

    def test_zoom_steps_falls_back_when_preview_settings_absent(self):
        self.controller.settings = {}
        self.assertEqual(REGISTRY["zoom"].steps(self.controller), [0.5, 1.0, 1.5, 2.0])

    def test_hdr_threshold_steps_read_the_live_controller_table(self):
        # Settings-driven now (arrays.hdr_threshold_low/high), rebuilt by
        # CinePiController._rebuild_hdr_threshold_low_steps/_high_steps -
        # the registry just reads whatever the controller last computed.
        self.assertEqual(
            REGISTRY["hdr_threshold_low"].steps(self.controller),
            self.controller.hdr_threshold_low_steps,
        )
        self.assertEqual(
            REGISTRY["hdr_threshold_high"].steps(self.controller),
            self.controller.hdr_threshold_high_steps,
        )

    def test_hdr_blend_and_gain_adder_steps_read_the_live_controller_table(self):
        self.assertEqual(REGISTRY["hdr_blend"].steps(self.controller), self.controller.hdr_blend_steps)
        self.assertEqual(
            REGISTRY["hdr_gain_adder"].steps(self.controller), self.controller.hdr_gain_adder_steps
        )


class LockAndFreeAttrTests(unittest.TestCase):
    def test_only_iso_fps_and_shutter_a_nom_declare_a_lock(self):
        locked = {name for name, p in REGISTRY.items() if p.lock_attr}
        self.assertEqual(locked, {"iso", "fps", "shutter_a_nom"})

    def test_hdr_parameters_declare_no_lock_but_do_declare_a_free_attr(self):
        for name in ("hdr_blend", "hdr_gain_adder", "hdr_threshold_low", "hdr_threshold_high"):
            with self.subTest(name=name):
                self.assertIsNone(REGISTRY[name].lock_attr)
                self.assertEqual(REGISTRY[name].free_attr, f"{name}_free")


class MenuParametersTests(unittest.TestCase):
    def test_returns_registry_order(self):
        result = menu_parameters(settings={})
        self.assertEqual([p.name for p in result], list(REGISTRY.keys()))

    def test_only_returns_menu_eligible_entries(self):
        result = menu_parameters(settings={})
        self.assertTrue(all(p.menu for p in result))


if __name__ == "__main__":
    unittest.main()
