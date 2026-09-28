"""WP-CM-7 / per-sensor settings (2026-09-28): source-level checks for the
aspect pane's markup and JS wiring.

"Rendering is not testable here; the endpoint is" (WP-CM-7's own Tests
note) -- there is no DOM/JS execution harness in this suite (same
constraint test_settings_editor_crop_diagram_domain.py and
test_settings_editor_switchset.py were written against). This file covers
what a source-text check safely can: the per-camera ratio-toggle panel
exists ahead of the mode table, its copy comes from resources/gui-text/
rather than being hard-coded, the client state that feeds a save is wired
into buildState(), and the JS is syntactically valid (Jinja tags stripped
first, the same way a browser never sees them).

Per-sensor settings (PLAN.md, 2026-09-28) changed three things this file
must now assert instead of the old WP-CM-7 behaviour:

1. `available` only ever carries ratios the sensor actually offers -- no
   more "closest" substitution, so the approximate-ratio rendering (the
   "-- nearest x.xx" label, the dashed swatch) is gone, not merely unused.
2. The save payload moves aspect_ratios/enabled_modes/custom_modes out of
   the whole-file image_capture dict and into a top-level sensor_settings
   entry, sent only for cameras the operator actually touched this
   page-load.
3. The pane shows where a camera's settings currently live (stock/file/
   legacy) and offers a per-camera Reset to stock.

A full DOM/browser-driven verification of the exact PUT bodies this
produces lives in W2-PANE-FINDINGS.md, run against a stub harness outside
this suite (no backend exists on this branch to test against for real --
W1 owns settings_editor.py in parallel).
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
        """The card's label comes from gui-text, and nothing is hard-coded beside it.

        The help paragraph was removed at the operator's request (2026-09-21): the
        toggles and the mode table under them carry their own meaning, and the card
        was the only one in this pane with a three-sentence explanation. That
        invariant still holds -- no `class="card-help"` inside this panel -- even
        though per-sensor settings (2026-09-28) adds real content below the
        toggles again: the source line, the dropped-ratios notice and the Reset
        button. All three read their prose from resources/gui-text/ (or, for the
        Reset button, are a short control label, the same carve-out the Revert/
        Upload buttons already use -- see resources/gui-text/README.md), not from
        literal markup, which this test also checks.
        """
        for slot in ("cam0", "cam1"):
            with self.subTest(slot=slot):
                self.assertIn(f"t('card.sensors.{slot}.aspect_ratios.label')", self.html)
                panel = self.html[self.html.index(f'id="{slot}-ratio-panel"'):
                                  self.html.index(f'id="{slot}-mode-panel"')]
                self.assertNotIn('class="card-help"', panel,
                                 f"{slot}'s ratio card has help markup again; it must come "
                                 f"from resources/gui-text/, not the template")
                self.assertIn(f'id="{slot}-ratio-source"', panel)
                self.assertIn(f'id="{slot}-ratio-dropped"', panel)
                self.assertIn(f'id="{slot}-ratio-reset"', panel)
                # The reset button and the dropped notice start hidden -- shown
                # only once renderSensorSourceMeta() has real data to react to.
                reset_idx = panel.index(f'id="{slot}-ratio-reset"')
                self.assertIn("hidden", panel[reset_idx:reset_idx + 80])
                dropped_idx = panel.index(f'id="{slot}-ratio-dropped"')
                self.assertIn("hidden", panel[dropped_idx:dropped_idx + 80])

    def test_gui_text_defines_the_keys_the_template_asks_for(self):
        md = GUI_TEXT.read_text(encoding="utf-8")
        self.assertIn("<!-- key: card.sensors.cam0.aspect_ratios -->", md)
        self.assertIn("<!-- key: card.sensors.cam1.aspect_ratios -->", md)
        for key in (
            "text.sensors.aspect_ratios.source_stock",
            "text.sensors.aspect_ratios.source_file",
            "text.sensors.aspect_ratios.source_legacy",
            "text.sensors.aspect_ratios.dropped",
        ):
            with self.subTest(key=key):
                self.assertIn(f"<!-- key: {key} -->", md)

    def test_sensor_source_text_is_read_from_gui_text_not_hard_coded(self):
        """The stock/file/legacy/dropped sentences are gui-text, looked up once.

        The file name and the dropped ratio ids are data, not prose -- appended
        by renderSensorSourceMeta() at render time -- so only the four
        sentences themselves need to come from t(); see
        resources/gui-text/README.md's "what is not in here" for why a runtime
        value never goes through it.
        """
        for key, tpl_id in (
            ("text.sensors.aspect_ratios.source_stock.body", "tpl-sensor-source-stock"),
            ("text.sensors.aspect_ratios.source_file.body", "tpl-sensor-source-file"),
            ("text.sensors.aspect_ratios.source_legacy.body", "tpl-sensor-source-legacy"),
            ("text.sensors.aspect_ratios.dropped.body", "tpl-sensor-dropped-notice"),
        ):
            with self.subTest(key=key):
                self.assertIn(f"t('{key}')", self.html)
                self.assertIn(f'id="{tpl_id}"', self.html)


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

    def test_ratio_label_has_no_approximate_variant_left(self):
        """Per-sensor settings, 2026-09-28: `available` never carries a ratio
        this sensor does not offer any more (no "closest" substitution), so
        every entry is exact and there is nothing left for the label to
        qualify. Was test_approximate_ratio_label_states_the_real_aspect,
        which asserted the opposite -- that a "-- nearest x.xx" qualifier
        existed -- back when an approximate match was still possible."""
        start = self.html.index("function aspectRatioToggleLabel(")
        end = self.html.index("\n  }\n", start)
        fn = self.html[start:end]
        self.assertNotIn("info.real_aspect", fn)
        self.assertNotIn("info.exact", fn)
        self.assertIn("return info.label || id;", fn)

    def test_swatch_has_no_dashed_approximate_variant(self):
        """Companion to the label check above: aspectRatioSvg() used to take
        an `exact` flag and draw a dashed rectangle when it was false. There
        is no approximate ratio left to draw that way, so the parameter and
        the dash branch are gone, not merely unused."""
        sig_start = self.html.index("function aspectRatioSvg(")
        sig_end = self.html.index(")", sig_start)
        self.assertEqual(self.html[sig_start:sig_end + 1], "function aspectRatioSvg(value)")
        start = self.html.index("function aspectRatioSvg(")
        end = self.html.index("\n  }\n", start)
        fn = self.html[start:end]
        self.assertNotIn("stroke-dasharray", fn)
        self.assertNotIn("aspect-ratio-approx", self.html)

    def test_toggling_a_ratio_marks_the_form_dirty_and_the_camera(self):
        start = self.html.index("function renderAspectRatioToggles(")
        end = self.html.index("\n  }\n", start)
        fn = self.html[start:end]
        self.assertIn("markDirty(btn", fn)
        self.assertIn("dirtySensorCameras.add(camera)", fn)
        self.assertIn("refreshModeRowVisibility(camera)", fn)

    def test_mode_row_and_fps_edits_mark_the_camera_dirty(self):
        start = self.html.index("function renderRecordingModes(")
        end = self.html.index("function loadFpsCeilings(", start)
        fn = self.html[start:end]
        self.assertEqual(
            fn.count("dirtySensorCameras.add(camera)"), 2,
            "expected one dirtySensorCameras.add(camera) for the mode-row "
            "toggle and one for the fps-override input",
        )

    def test_clear_settings_dirty_state_resets_per_camera_dirtiness(self):
        start = self.html.index("function clearSettingsDirtyState(")
        end = self.html.index("\n  }\n", start)
        fn = self.html[start:end]
        self.assertIn("dirtySensorCameras.clear()", fn)

    def test_build_state_sends_sensor_settings_only_for_dirty_cameras(self):
        """Replaces test_build_state_saves_the_per_camera_ratio_selection.

        The old rule: buildState() always wrote a whole-file
        image_capture.aspect_ratios (every camera, one big dict). The new
        rule (PLAN.md's W1<->W2 contract): the page stops sending
        image_capture.aspect_ratios/enabled_modes/custom_modes at all, and
        instead sends a top-level sensor_settings entry, built per camera,
        only for cameras in dirtySensorCameras -- so a save that touches no
        camera's ratios/modes/fps carries no sensor_settings key at all.
        """
        start = self.html.index("function buildState(")
        end = self.html.index("\n  }\n", start)
        fn = self.html[start:end]
        self.assertNotIn("state.image_capture.aspect_ratios =", fn)
        self.assertNotIn("state.image_capture.enabled_modes =", fn)
        self.assertNotIn("state.image_capture.custom_modes =", fn)
        self.assertIn("delete state.image_capture.aspect_ratios;", fn)
        self.assertIn("delete state.image_capture.enabled_modes;", fn)
        self.assertIn("delete state.image_capture.custom_modes;", fn)
        # Cleared unconditionally before the dirty loop repopulates it, so a
        # later, unrelated save can't carry a stale sensor forward forever.
        self.assertIn("delete state.sensor_settings;", fn)
        self.assertIn("dirtySensorCameras.forEach(function(camera){", fn)
        self.assertIn("aspect_ratios: buildAspectRatiosStateFor(camera)", fn)
        self.assertIn("enabled_modes: buildEnabledModesStateFor(camera)", fn)
        self.assertIn("custom_modes: buildCustomModesStateFor(camera)", fn)
        self.assertIn("if (Object.keys(sensorSettings).length) state.sensor_settings = sensorSettings;", fn)

    def test_per_camera_builders_read_only_that_cameras_own_rows(self):
        """Replaces test_build_aspect_ratios_state_preserves_cameras_it_did_not_touch.

        The old builders (buildEnabledModesState/buildAspectRatiosState/
        buildCustomModesState) seeded from lastLoadedSettings for every
        camera and overwrote only the one(s) this page rendered -- needed
        because the old payload replaced the whole per-camera dict in one
        PUT. Per-sensor settings sends a sensor_settings entry only for a
        dirty camera, so that merge-in-the-page no longer has a job: each
        *_For(camera) builder must read only that camera's current DOM rows
        (or selectedAspectRatiosByCamera[camera]) and must NOT read
        lastLoadedSettings -- doing so would seed a fresh per-sensor file
        from whatever this page happened to load with, not from what the
        operator is looking at.
        """
        for name in ("buildEnabledModesStateFor", "buildCustomModesStateFor"):
            with self.subTest(builder=name):
                start = self.html.index(f"function {name}(")
                end = self.html.index("\n  }\n", start)
                fn = self.html[start:end]
                self.assertNotIn("lastLoadedSettings", fn)
                self.assertIn('data-camera="\'+camera+\'"', fn)
        # The ratio builder alone doesn't touch the DOM rows -- it just
        # returns this camera's own slice of the toggle state, still without
        # ever reading lastLoadedSettings.
        start = self.html.index("function buildAspectRatiosStateFor(")
        end = self.html.index("\n  }\n", start)
        fn = self.html[start:end]
        self.assertNotIn("lastLoadedSettings", fn)
        self.assertIn("selectedAspectRatiosByCamera[camera]", fn)
        # The three old whole-file builders must be gone outright, not just
        # unused -- their names are no longer part of the contract.
        for old_name in ("buildEnabledModesState(", "buildAspectRatiosState(", "buildCustomModesState("):
            with self.subTest(old_name=old_name):
                self.assertNotIn(f"function {old_name})", self.html)

    def test_reset_button_confirms_and_deletes_the_sensor_file(self):
        self.assertIn("function resetSensorToStock(camera){", self.html)
        start = self.html.index("function resetSensorToStock(")
        end = self.html.index("\n  }\n", start)
        fn = self.html[start:end]
        self.assertIn("window.confirm(", fn)
        self.assertIn("method:'DELETE'", fn.replace(" ", ""))
        self.assertIn("/settings-editor/api/sensor-settings/", fn)
        # Same restarting-toast idiom the settings PUT handler already uses,
        # reused rather than reinvented.
        self.assertIn("res.restarting", fn)

    def test_reset_button_is_wired_once_not_per_render(self):
        """The reset buttons are static template elements (one per camera
        slot), never recreated -- unlike the ratio toggles and mode rows,
        which are rebuilt from scratch on every render and so can safely add
        a fresh listener each time. Wiring resetSensorToStock() inside the
        per-render function would stack a duplicate listener on every
        loadFpsCeilings() call (e.g. every "show smaller modes" toggle)."""
        render_start = self.html.index("function renderAspectRatioToggles(")
        render_end = self.html.index("function renderSensorSourceMeta(", render_start)
        self.assertNotIn("resetSensorToStock", self.html[render_start:render_end])
        self.assertIn("['cam0','cam1'].forEach(function(slot){", self.html)

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
