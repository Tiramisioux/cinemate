"""F-217: a fifth hand-sync comment. template.html:216 says
`/* _draw_status_box(crossed=True) strikes the SYNC box through */` --
CSS naming a Python method as the thing it must stay consistent with, with
no check (same mechanism as F-007's colour comments, which have
tools/design_token_diff.py; this pair didn't have anything).

The comment is accurate on this checkout, but accurate-today is not the
same as checked. Three things have to move together for the HDMI GUI and
the web GUI to show the same SYNC state the same way:

1. simple_gui.py draws the SYNC box with crossed=True, gated on
   values.get("frames_off_sync").
2. template.html's JS only adds the 'sync' CSS class to the SYNC box when
   the same V.frames_off_sync flag is set.
3. The .box.sync::after CSS rule actually renders a strike-through, so
   adding the class has a visible effect.

A change to any one of these without the others would desync the two GUIs
silently -- exactly what this batch's other hand-sync-comment findings
turned out to hide.
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIMPLE_GUI = ROOT / "src/module/simple_gui.py"
TEMPLATE = ROOT / "src/module/app/templates/template.html"


class SyncBoxCrossedConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.simple_gui_src = SIMPLE_GUI.read_text(encoding="utf-8")
        self.template_src = TEMPLATE.read_text(encoding="utf-8")

    def test_simple_gui_draws_the_sync_box_crossed_and_gated_on_frames_off_sync(self):
        # The SYNC box's _draw_status_box(...) call, up to its closing paren,
        # must both request crossed=True and sit under an
        # `if values.get("frames_off_sync")` guard immediately above it.
        m = re.search(
            r'if values\.get\("frames_off_sync"\):\s*'
            r"self\._draw_status_box\((?:[^()]|\([^()]*\))*?\"SYNC\"(?:[^()]|\([^()]*\))*?crossed=True",
            self.simple_gui_src,
            re.S,
        )
        self.assertIsNotNone(
            m,
            "simple_gui.py no longer draws the SYNC box with crossed=True "
            "gated on frames_off_sync -- update template.html's comment and "
            "CSS (or this test) to match the new behaviour",
        )

    def test_template_js_gates_the_sync_class_on_frames_off_sync(self):
        self.assertIn(
            "if (V.frames_off_sync) { out.push(box('SYNC', 'sync')); }",
            self.template_src,
            "the web GUI no longer gates the SYNC box's 'sync' class on "
            "V.frames_off_sync -- it will disagree with the HDMI GUI's "
            "crossed=True condition",
        )

    def test_template_css_actually_renders_a_strike_through_for_the_sync_class(self):
        self.assertIn(".box.sync::after", self.template_src)
        # The rule must exist and not be empty/no-op -- a linear-gradient
        # background is the actual diagonal-line mechanism.
        m = re.search(r"\.box\.sync::after\s*\{([^}]*)\}", self.template_src, re.S)
        self.assertIsNotNone(m, ".box.sync::after rule not found")
        self.assertIn("linear-gradient", m.group(1))

    def test_the_hand_sync_comment_still_names_the_right_python_call(self):
        # If this ever goes stale, it should say so explicitly rather than
        # silently describe the wrong thing.
        self.assertIn(
            "_draw_status_box(crossed=True) strikes the SYNC box through",
            self.template_src,
        )


if __name__ == "__main__":
    unittest.main()
