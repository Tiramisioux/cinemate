"""Markup-level check that the Reverse/Wrap toggles exist on both rotary
row builders and are serialized by both state builders.

The settings editor's client JS (over a thousand lines, only partly mapped
-- see the handbook's entry-points.md) has no test harness that executes
it; every existing test that touches settings_editor.html (e.g.
test_settings_editor_switchset.py) reads the template source as text and
asserts on it instead. This follows the same pattern: extract each
function's body by brace-counting from `function <name>(` and check the
Reverse/Wrap wiring is actually inside it, not just present somewhere in
the 615 KB file.

07-rotary-encoder-reverse-and-wrap.md: buildRotaryRow gets its own two
.gesture rows (name | toggle); buildEncoderRow stacks both toggles the same way, under the
Turn line beside the setting select. Both state builders must read them
back with toggleIsChecked() and write real reverse/wrap booleans.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TEMPLATE = ROOT / "src/module/app/templates/settings_editor.html"


def extract_function(html, name):
    """The body of `function <name>(...){ ... }`, matched by brace-counting
    rather than a regex so nested `{}` inside the function (object literals,
    control flow) don't truncate it early."""
    marker = f"function {name}("
    start = html.index(marker)
    brace = html.index("{", start)
    depth = 0
    i = brace
    while True:
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return html[start:i + 1]
        i += 1


class RotaryReverseWrapMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_build_rotary_row_renders_both_toggles(self):
        body = extract_function(self.html, "buildRotaryRow")
        self.assertIn("prefix + '-reverse'", body)
        self.assertIn("prefix + '-wrap'", body)
        self.assertIn("Reverse", body)
        self.assertIn("Wrap around", body)

    def test_build_encoder_row_stacks_both_toggles_as_their_own_rows(self):
        body = extract_function(self.html, "buildEncoderRow")
        self.assertIn("prefix + '-reverse'", body)
        self.assertIn("prefix + '-wrap'", body)
        # Each toggle gets its own .gesture row, the same shape buildRotaryRow
        # uses, so the identical pair reads the same in both sections. They
        # used to sit inline on the Turn line; the operator asked for them
        # stacked to match the single rotary encoder.
        self.assertIn("makeToggleGestureRow(prefix + '-reverse'", body)
        self.assertIn("makeToggleGestureRow(prefix + '-wrap'", body)
        self.assertNotIn("turnControls", body)
        # Reverse sits ABOVE Wrap around in the DOM, same order as the GPIO
        # row. Source order is the reverse of DOM order here -- wrapRow is
        # built first so Reverse can be inserted before it -- so pin the
        # insertion, not the position of the strings in the file.
        self.assertIn("wrapRow", body)
        self.assertRegex(
            body,
            r"makeToggleGestureRow\(prefix \+ '-reverse'[\s\S]*?\n\s*wrapRow\s*\)",
        )

    def test_hardware_controls_state_serializes_both_keys_for_rotary(self):
        body = extract_function(self.html, "buildHardwareControlsState")
        self.assertIn("reverse: toggleIsChecked(prefix + '-reverse')", body)
        self.assertIn("wrap: toggleIsChecked(prefix + '-wrap')", body)

    def test_quad_rotary_state_serializes_both_keys_per_channel(self):
        body = extract_function(self.html, "buildQuadRotaryState")
        self.assertIn("entry.reverse = toggleIsChecked(prefix + '-reverse')", body)
        self.assertIn("entry.wrap = toggleIsChecked(prefix + '-wrap')", body)

    def test_toggle_is_checked_reads_aria_checked_and_defaults_off(self):
        # Loading must round-trip an absent key as off: a row with no
        # -reverse/-wrap element (an old save, or this feature simply never
        # having run) must read as false, not throw.
        self.assertIn("function toggleIsChecked(id){", self.html)
        body = extract_function(self.html, "toggleIsChecked")
        self.assertIn("!!el", body)
        self.assertIn("aria-checked", body)


if __name__ == "__main__":
    unittest.main()
