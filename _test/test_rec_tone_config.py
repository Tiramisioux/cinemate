"""hardware_outputs.rec_tone must actually reach GPIOOutput.

Commit c171975e regrouped the flat `rec_tone_*` keys under a nested `rec_tone`
object and updated main.py's section name but not its leaf reads, so every
rec_tone value silently fell back to a hardcoded default:

  * the configured tone pin was ignored, and the pwm_pin fallback used instead
  * frequency_hz and duty_cycle could not be changed at all
  * relay_drop_frames could never be true, so
    GPIOOutput.relay_drop_frame_on_rec_tone() returned at its guard every time
    -- the "Drop a frame for the relay" toggle has never done anything on this
    settings shape

settings.schema.json declares rec_tone with additionalProperties:false, so the
flat keys cannot appear in a current settings file at all.
"""

import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))
sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=object))

from module.config_loader import (
    _apply_settings_defaults,
    rec_tone_config,
    strip_jsonc,
)


class RecToneConfigTests(unittest.TestCase):
    def test_nested_values_are_read(self):
        cfg = rec_tone_config(
            {"rec_tone": {"pin": [18], "frequency_hz": 440, "duty_cycle": 25,
                          "relay_drop_frames": True}}
        )
        self.assertEqual(cfg["pin"], [18])
        self.assertEqual(cfg["frequency_hz"], 440)
        self.assertEqual(cfg["duty_cycle"], 25)
        self.assertIs(cfg["relay_drop_frames"], True)

    def test_relay_drop_frames_can_now_be_true(self):
        # The whole point: the guard in relay_drop_frame_on_rec_tone() was
        # unreachable-by-configuration before this.
        cfg = rec_tone_config({"rec_tone": {"relay_drop_frames": True}})
        self.assertIs(cfg["relay_drop_frames"], True)

    def test_missing_block_falls_back_to_documented_defaults(self):
        cfg = rec_tone_config({})
        self.assertEqual(cfg["pin"], [])
        self.assertEqual(cfg["frequency_hz"], 1000)
        self.assertEqual(cfg["duty_cycle"], 50)
        self.assertIs(cfg["relay_drop_frames"], False)

    def test_pre_rename_flat_keys_still_work(self):
        cfg = rec_tone_config(
            {"rec_tone_pin": [12], "rec_tone_frequency_hz": 880,
             "rec_tone_duty_cycle": 10, "rec_tone_relay_drop_frames": True}
        )
        self.assertEqual(cfg["pin"], [12])
        self.assertEqual(cfg["frequency_hz"], 880)
        self.assertEqual(cfg["duty_cycle"], 10)
        self.assertIs(cfg["relay_drop_frames"], True)

    def test_nested_wins_over_a_stale_flat_key(self):
        cfg = rec_tone_config({"rec_tone": {"frequency_hz": 440},
                                "rec_tone_frequency_hz": 880})
        self.assertEqual(cfg["frequency_hz"], 440)

    def test_the_shipped_settings_file_reaches_gpio_output(self):
        raw = json.loads(strip_jsonc((ROOT / "settings.jsonc").read_text(encoding="utf-8")))
        gpio_cfg = _apply_settings_defaults(raw)["hardware_outputs"]
        cfg = rec_tone_config(gpio_cfg)
        self.assertEqual(cfg["pin"], gpio_cfg["rec_tone"]["pin"])
        self.assertEqual(cfg["frequency_hz"], gpio_cfg["rec_tone"]["frequency_hz"])
        self.assertEqual(cfg["duty_cycle"], gpio_cfg["rec_tone"]["duty_cycle"])

    def test_defaults_match_config_loader(self):
        from_loader = _apply_settings_defaults({})["hardware_outputs"]["rec_tone"]
        self.assertEqual(rec_tone_config({}), from_loader)


if __name__ == "__main__":
    unittest.main()
