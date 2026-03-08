import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from module.cli_commands import CommandExecutor


class TestAnalyzeCLI(unittest.TestCase):
    def setUp(self):
        self.controller = MagicMock()
        self.controller.ssd_monitor = MagicMock()
        self.app = MagicMock()
        self.analyzer = MagicMock()
        self.executor = CommandExecutor(
            self.controller,
            self.app,
            storage_preroll=None,
            performance_analyzer=self.analyzer,
        )

    def test_analyze_seconds_alias(self):
        self.executor.handle_received_data("analyze seconds 3")
        self.analyzer.start.assert_called_once_with("seconds", 3.0)

    def test_analyze_frames_alias(self):
        self.executor.handle_received_data("analyze frames 120")
        self.analyzer.start.assert_called_once_with("frames", 120)

    def test_analyze_rejects_non_positive(self):
        self.executor.handle_received_data("analyze s 0")
        self.analyzer.start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
