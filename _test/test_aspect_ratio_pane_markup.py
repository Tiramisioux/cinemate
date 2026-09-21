"""WP-CM-7: source-level checks for the aspect pane's markup and JS wiring.

"Rendering is not testable here; the endpoint is" (WP-CM-7's own Tests
note) -- there is no DOM/JS execution harness in this suite (same
constraint test_settings_editor_crop_diagram_domain.py and
test_settings_editor_switchset.py were written against). This file covers
what a source-text check safely can: the per-camera ratio-toggle panel
exists ahead of the mode table, its copy comes from resources/gui-text/
rather than being hard-coded, the client state that feeds a save is wired
into buildState(), and the JS is syntactically valid (Jinja tags stripped
first, the same way a browser never sees them).
"""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/module/app/templates/settings_editor.html"
GUI_TEXT = ROOT / "resources/gui-text/03-settings-cameras.md"


class AspectRatioPanelMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_each_camera_has_a_ratio_panel_ahead_of_its_mode_panel(self):
        for slot in ("cam0", "cam1"):
            with self.subTest(slot=slot):
                ratio_idx = self.html.index(f'id="{slot}-ratio-panel"')
                mode_idx = self.html.index(f'id="{slot}-mode-panel"')
                self.assertLess(
                    ratio_idx, mode_idx,
                    f"{slot}'s ratio toggles must be above its mode table",
                )
                self.assertIn(f'id="{slot}-ratio-list"', self.html)

    def test_ratio_panel_copy_comes_from_gui_text_not_hard_coded(self):
        for slot in ("cam0", "cam1"):
            with self.subTest(slot=slot):
                self.assertIn(f"t('card.sensors.{slot}.aspect_ratios.label')", self.html)
                self.assertIn(f"t('card.sensors.{slot}.aspect_ratios.help')", self.html)

    def test_gui_text_defines_the_keys_the_template_asks_for(self):
        md = GUI_TEXT.read_text(encoding="utf-8")
        self.assertIn("<!-- key: card.sensors.cam0.aspect_ratios -->", md)
        self.assertIn("<!-- key: card.sensors.cam1.aspect_ratios -->", md)


class AspectRatioJsWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_inline_svg_not_an_image_asset(self):
        start = self.html.index("function aspectRatioSvg(")
        end = self.html.index("\n  }\n", start)
        fn = self.html[start:end]
        self.assertIn("<svg", fn)
        self.assertIn("<rect", fn)
        self.assertNotIn("<img", fn)

    def test_approximate_ratio_label_states_the_real_aspect(self):
        start = self.html.index("function aspectRatioToggleLabel(")
        end = self.html.index("\n  }\n", start)
        fn = self.html[start:end]
        self.assertIn("real_aspect", fn)
        self.assertIn("nearest", fn)

    def test_toggling_a_ratio_marks_the_form_dirty(self):
        start = self.html.index("function renderAspectRatioToggles(")
        end = self.html.index("\n  }\n", start)
        fn = self.html[start:end]
        self.assertIn("markDirty(btn", fn)
        self.assertIn("refreshModeRowVisibility(camera)", fn)

    def test_build_state_saves_the_per_camera_ratio_selection(self):
        start = self.html.index("function buildState(")
        end = self.html.index("\n  }\n", start)
        fn = self.html[start:end]
        self.assertIn("state.image_capture.aspect_ratios = buildAspectRatiosState();", fn)

    def test_build_aspect_ratios_state_preserves_cameras_it_did_not_touch(self):
        # Same convention as buildEnabledModesState(): start from what was
        # already on disk for every camera, only overwrite the ones this
        # page actually rendered toggles for. Un-owned by
        # EDITOR_OWNED_SUBTREES on the Python side (settings_editor.py) --
        # this is what makes that safe.
        start = self.html.index("function buildAspectRatiosState(")
        end = self.html.index("\n  }\n", start)
        fn = self.html[start:end]
        self.assertIn("lastLoadedSettings", fn)
        self.assertIn("selectedAspectRatiosByCamera", fn)

    def test_below_floor_rows_are_not_hard_coded_to_1280(self):
        start = self.html.index("function renderRecordingModes(")
        end = self.html.index("var smallCount=", start)
        fn = self.html[start:end]
        self.assertNotIn("< 1280", fn)
        self.assertIn("mode.below_width_floor", fn)

    @unittest.skipUnless(shutil.which("node"), "node not on PATH -- this repo's suite is Python-only in CI")
    def test_the_script_is_syntactically_valid_javascript(self):
        scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", self.html, re.S)
        self.assertTrue(scripts)
        main = max(scripts, key=len)
        # Strip Jinja -- a browser never sees {{ }}/{% %}, node --check would
        # reject them as JS syntax errors that have nothing to do with this
        # package's own code.
        main = re.sub(r"\{\{.*?\}\}", "null", main, flags=re.S)
        main = re.sub(r"\{%.*?%\}", "", main, flags=re.S)
        proc = subprocess.run(
            ["node", "--check", "/dev/stdin"], input=main,
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
