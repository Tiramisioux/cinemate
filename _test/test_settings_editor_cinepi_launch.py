"""Guard the persistent shortcut from Settings to the CinePi live view.

main added this shortcut as a single floating anchor to http://cinepi.local:5000
(PR #192). dev had already grown the same control into the cinepi-live-launcher:
the same floating button, targeting the live view by a relative URL so it works
on any hostname or address, plus per-camera and combined links on a dual rig.
When main was merged into dev (2026-09-25) the launcher was kept and this test
moved with it: what it guards is that the shortcut stays, floats above the
editor, and has an accessible name -- not the one absolute URL main used.
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


class CinePiLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_launch_control_targets_the_live_view(self):
        self.assertIn(
            'class="cinepi-live-launcher" id="cinepiLiveLauncher"', self.html
        )
        self.assertIn('class="cinepi-launch" id="cinepiLiveDefault" href="/"', self.html)
        self.assertIn('href="/?preview=cam0"', self.html)
        self.assertIn('href="/?preview=cam1"', self.html)

    def test_launch_control_has_an_accessible_name(self):
        self.assertIn('aria-label="Open CinePi live view"', self.html)
        self.assertIn('aria-label="Open camera 0 live view"', self.html)

    def test_launch_control_remains_floating_above_the_editor(self):
        self.assertIn('.cinepi-launch{\n    position:fixed;', self.html)
        self.assertIn('z-index:40;', self.html)
        self.assertIn('.cinepi-live-launcher{ position:fixed;', self.html)


if __name__ == "__main__":
    unittest.main()
