"""Guard the persistent shortcut from Settings to the CinePi control UI."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


class CinePiLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_launch_control_targets_the_cinepi_ui(self):
        self.assertIn(
            'class="cinepi-launch" href="http://cinepi.local:5000"', self.html
        )

    def test_launch_control_has_an_accessible_name_and_fullscreen_icon(self):
        self.assertIn('aria-label="Open CinePi control interface"', self.html)
        self.assertIn('<path d="M9 3H3v6M15 3h6v6M21 15v6h-6M3 15v6h6"/>', self.html)

    def test_launch_control_remains_floating_above_the_editor(self):
        self.assertIn('.cinepi-launch{\n    position:fixed;', self.html)
        self.assertIn('z-index:40;', self.html)


if __name__ == "__main__":
    unittest.main()
