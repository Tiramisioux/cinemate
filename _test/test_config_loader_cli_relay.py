import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from module.config_loader import load_settings


class TestConfigLoaderCliRelay(unittest.TestCase):
    def _write_settings(self, payload: dict) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(payload, tmp)
        return Path(tmp.name)

    def test_cli_relay_defaults(self):
        path = self._write_settings({})
        settings = load_settings(path)
        self.assertEqual(settings["cli_relay"], {
            "mode": "event",
            "level": "info",
            "filters": [],
            "frame_sample_n": 1,
        })

    def test_cli_relay_validation_and_clamp(self):
        path = self._write_settings({"cli_relay": {"mode": "nope", "level": "warn", "filters": "x", "frame_sample_n": 0}})
        settings = load_settings(path)
        self.assertEqual(settings["cli_relay"]["mode"], "event")
        self.assertEqual(settings["cli_relay"]["level"], "info")
        self.assertEqual(settings["cli_relay"]["filters"], [])
        self.assertEqual(settings["cli_relay"]["frame_sample_n"], 1)

    def test_stdout_relay_backcompat_mapping(self):
        path = self._write_settings({"stdout_relay": {"enabled": True, "level": "debug", "filters": ["DNG"]}})
        settings = load_settings(path)
        self.assertEqual(settings["cli_relay"]["mode"], "event")
        self.assertEqual(settings["cli_relay"]["level"], "debug")
        self.assertEqual(settings["cli_relay"]["filters"], ["DNG"])

    def test_cli_relay_trims_mode_and_level(self):
        path = self._write_settings({"cli_relay": {"mode": " OFF ", "level": " DEBUG "}})
        settings = load_settings(path)
        self.assertEqual(settings["cli_relay"]["mode"], "off")
        self.assertEqual(settings["cli_relay"]["level"], "debug")

if __name__ == "__main__":
    unittest.main()
