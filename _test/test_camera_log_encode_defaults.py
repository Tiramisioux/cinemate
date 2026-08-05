import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.config_loader import _apply_settings_defaults


class CameraLogEncodeDefaultsTests(unittest.TestCase):
    def test_runtime_defaults_add_log_encode_off(self):
        """A settings.json with no camera block at all still gets log_encode
        defaulted to False (off) on both ports -- log changes recorded
        output, so it must be opt-in even for a from-scratch config."""
        settings = _apply_settings_defaults({})

        self.assertIs(settings["camera"]["cam0"]["log_encode"], False)
        self.assertIs(settings["camera"]["cam1"]["log_encode"], False)

    def test_runtime_defaults_preserve_an_existing_log_encode_choice(self):
        """_apply_settings_defaults runs on every launch (it fills gaps in a
        live Pi settings.json), so it must use setdefault -- never overwrite
        -- or every restart would silently reset the user's log choice back
        to off."""
        settings = _apply_settings_defaults(
            {"camera": {"cam0": {"log_encode": 10}, "cam1": {"log_encode": True}}}
        )

        self.assertEqual(settings["camera"]["cam0"]["log_encode"], 10)
        self.assertIs(settings["camera"]["cam1"]["log_encode"], True)

    def test_stock_settings_default_log_encode_off(self):
        """The shipped resources/settings/settings_default.json (the
        from-scratch stock file, distinct from the runtime-fill path above)
        also ships log_encode off on both ports."""
        settings = json.loads(
            (ROOT / "resources/settings/settings_default.json").read_text(encoding="utf-8")
        )

        self.assertIs(settings["camera"]["cam0"]["log_encode"], False)
        self.assertIs(settings["camera"]["cam1"]["log_encode"], False)


if __name__ == "__main__":
    unittest.main()
