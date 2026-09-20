"""Resolutions and bit depths were a closed catalogue, offered as switches.

Both were free-form chip lists before that: type a number, get a chip. But
neither is a value the operator invents -- a sensor either reports a mode at
a given size and depth or it does not, and typing "5" only narrowed the
filter to nothing. So the chip editors were replaced with a row of on/off
switches, one per known category.

9e0ed32f ("Replace resolution filters with dynamic recording mode table")
retired the switches in turn: k_steps/bit_depths are now the legacy fallback
used only while a camera has no `image_capture.enabled_modes` entry (see
settings.schema.json's description of `enabled_modes`), and the operator-
facing control is the per-camera recording-mode table on each Camera pane
instead -- one row per driver-reported mode, not one switch per size/depth
category. `test_sensor_modes_endpoint.py` covers that table's backend today;
what remains here is the one claim that outlived the switches themselves.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TEMPLATE = ROOT / "src/module/app/templates/settings_editor.html"
SETTINGS = ROOT / "settings.jsonc"
SCHEMA = ROOT / "settings.schema.json"

# Every K category the shipped sensor database can produce, since a mode's
# category is round(width/1000*2)/2 and nothing else is reachable. 5.5 is the
# imx283's 5568-wide modes; it is absent from the default k_steps, which is
# why the switch exists at all -- without it those modes are unreachable from
# this page.
SETS = {
    "image_capture.k_steps": ["1.5", "2", "3", "4", "5.5"],
    "image_capture.bit_depths": ["10", "12", "16"],
}


class SwitchSetMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_the_free_form_chip_editors_are_gone(self):
        for path in SETS:
            with self.subTest(path=path):
                self.assertNotIn(f'data-chip-path="{path}"', self.html)


class SwitchSetWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_build_state_collects_the_switched_on_members(self):
        self.assertIn("document.querySelectorAll('[data-set-path]')", self.html)
        self.assertIn("if (t.getAttribute('aria-checked') !== 'true') return;", self.html)
        self.assertIn("setPath(state, container.getAttribute('data-set-path'), arr);", self.html)

    def test_loading_a_file_flips_the_switches_and_resets_their_baseline(self):
        block = self.html[self.html.index("function populateSimpleFields"):]
        block = block[:block.index("function populateChipContainer")]
        self.assertIn("data-set-path", block)
        self.assertIn("t.setAttribute('aria-checked', String(isOn));", block)
        # Without this the card loads permanently dirty.
        self.assertIn("t.setAttribute('data-original', String(isOn));", block)

    def test_a_switch_is_clickable_and_keyboard_operable(self):
        block = self.html[self.html.index(".toggle[data-set-item]')"):]
        block = block[:block.index("/* ---------- text / number / select inputs")]
        self.assertIn("addEventListener('click'", block)
        self.assertIn("checkDirty(t);", block)
        self.assertIn("e.key === ' ' || e.key === 'Enter'", block)


class ModeAvailabilityTests(unittest.TestCase):
    """A category the attached sensor has no mode for is greyed, not removed.

    Same rule the i2c pane applies to an absent Grove HAT: a rig can be
    configured before its hardware is fitted, and swapping a camera must not
    silently rewrite the file describing it. So the switch dims and keeps
    working.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")
        cls.py = (ROOT / "src/module/app/settings_editor.py").read_text(encoding="utf-8")
        cls.detect = (ROOT / "src/module/sensor_detect.py").read_text(encoding="utf-8")

    def test_availability_is_read_from_the_unfiltered_mode_table(self):
        # sensor_resolutions is what survived the k_steps/bit_depths filters.
        # Deriving availability from it would grey out whichever switch was
        # just turned off, which is circular.
        self.assertIn("sensor_modes_unfiltered", self.detect)
        self.assertIn(
            'getattr(sensor_detect, "sensor_modes_unfiltered", None)', self.py)

    def test_the_unfiltered_table_is_filled_before_the_filters_run(self):
        pre = self.detect.index("self.sensor_modes_unfiltered = dict(")
        post = self.detect.index("if self.bit_depths and m[\"bit_depth\"] not in self.bit_depths:")
        self.assertLess(pre, post)

    def test_the_endpoint_reports_both_sets_and_whether_it_knows_anything(self):
        for key in ('"k_steps": sorted(k_values)', '"bit_depths": sorted(bit_depths)',
                    '"known": bool(k_values or bit_depths)'):
            with self.subTest(key=key):
                self.assertIn(key, self.py)

    def test_no_camera_greys_nothing(self):
        block = self.html[self.html.index("function applyModeAvailability"):]
        block = block[:block.index("\n  }")]
        self.assertIn("if (!available || !available.known) return;", block)

    def test_an_unavailable_row_is_dimmed_but_stays_operable(self):
        block = self.html[self.html.index("function applyModeAvailability"):]
        block = block[:block.index("\n  }")]
        self.assertIn("row.classList.toggle('hw-absent', absent);", block)
        # Dimming only. A disabled switch could not be set ahead of the
        # hardware, which is the whole point of dimming instead.
        self.assertNotIn("disabled", block)

    def test_the_dim_class_is_the_one_the_stylesheet_defines(self):
        self.assertIn(".hw-absent{ opacity:.45; }", self.html)

    # test_the_availability_note_exists_for_the_script_to_fill was removed:
    # 5c964a16 ("Remove obsolete resolution filter availability UI") deleted
    # both #modeAvailabilityNote and the applyModeAvailability(res.available)
    # call site as part of retiring the switchset this note dimmed. The
    # function body above is now unreachable from any call site -- left in
    # place by that commit, not by this one; noted rather than removed here,
    # since nothing in this PR's scope calls for a JS cleanup pass.


class DynamicResolutionSettingTests(unittest.TestCase):
    """The feature had no settings.jsonc key at all -- only a Redis value and
    a hardcoded True behind it, so a camera that wanted it off had to be told
    so again after every reflash."""

    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_the_settings_page_offers_it(self):
        self.assertIn('data-path="image_capture.dynamic_resolution"', self.html)
        self.assertIn('id="f-dynres"', self.html)

    def test_settings_jsonc_carries_it_on_by_default(self):
        from module.config_loader import load_settings  # noqa: PLC0415
        settings = load_settings(str(SETTINGS))
        self.assertIs(settings["image_capture"]["dynamic_resolution"], True)

    def test_the_schema_knows_the_key(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        prop = schema["properties"]["image_capture"]["properties"]["dynamic_resolution"]
        self.assertEqual(prop["type"], "boolean")
        self.assertIs(prop["default"], True)

    def test_the_schema_still_refuses_unknown_image_capture_keys(self):
        # additionalProperties:false is what makes the schema a real gate;
        # adding a property must not have relaxed it.
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertIs(
            schema["properties"]["image_capture"]["additionalProperties"], False)


if __name__ == "__main__":
    unittest.main()
