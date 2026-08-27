import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.web_api_settings import DEFAULT_WEB_API_SETTINGS, web_api_settings


class WebApiSettingsDefaultsTests(unittest.TestCase):
    """Plan section 5 / docs/web-api.md: a missing or partial web_api block
    must behave exactly like the documented defaults — users must not have
    to edit settings.jsonc to get a working, safe-by-default API."""

    def test_missing_settings_dict_uses_full_defaults(self):
        self.assertEqual(web_api_settings(None), DEFAULT_WEB_API_SETTINGS)

    def test_missing_system_key_uses_full_defaults(self):
        self.assertEqual(web_api_settings({}), DEFAULT_WEB_API_SETTINGS)

    def test_missing_web_api_block_uses_full_defaults(self):
        self.assertEqual(web_api_settings({"system": {"wifi_hotspot": {}}}), DEFAULT_WEB_API_SETTINGS)

    def test_partial_override_keeps_other_defaults(self):
        merged = web_api_settings({"system": {"web_api": {"token": "s3cret"}}})
        self.assertEqual(merged["token"], "s3cret")
        self.assertEqual(merged["allow_destructive"], False)
        self.assertEqual(merged["max_commands_per_sec"], 20)

    def test_allow_destructive_can_be_enabled_explicitly(self):
        merged = web_api_settings({"system": {"web_api": {"allow_destructive": True}}})
        self.assertTrue(merged["allow_destructive"])

    def test_partial_broadcast_override_keeps_other_broadcast_defaults(self):
        merged = web_api_settings({"system": {"web_api": {"broadcast": {"hz": 10}}}})
        self.assertEqual(merged["broadcast"]["hz"], 10)
        self.assertEqual(merged["broadcast"]["port"], 8888)
        self.assertEqual(merged["broadcast"]["keys"], DEFAULT_WEB_API_SETTINGS["broadcast"]["keys"])

    def test_full_broadcast_override_replaces_key_list(self):
        merged = web_api_settings({"system": {"web_api": {"broadcast": {"keys": ["iso"]}}}})
        self.assertEqual(merged["broadcast"]["keys"], ["iso"])

    def test_does_not_mutate_the_default_constant_via_override(self):
        merged = web_api_settings({"system": {"web_api": {"broadcast": {"keys": ["iso"]}}}})
        merged["broadcast"]["keys"].append("mutated")
        self.assertNotIn("mutated", DEFAULT_WEB_API_SETTINGS["broadcast"]["keys"])

    def test_does_not_mutate_the_default_constant_via_default_keys_list(self):
        # No override at all -- merged["broadcast"]["keys"] must not be the
        # *same list object* as the module-level default, or mutating one
        # settings() result corrupts every other caller process-wide.
        merged = web_api_settings({})
        merged["broadcast"]["keys"].append("mutated")
        self.assertNotIn("mutated", DEFAULT_WEB_API_SETTINGS["broadcast"]["keys"])


if __name__ == "__main__":
    unittest.main()
