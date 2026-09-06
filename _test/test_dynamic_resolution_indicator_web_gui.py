"""Both GUIs go green when the resolution on screen is not the one chosen.

The HDMI overlay has always recoloured RES while dynamic resolution holds a
substitute mode. The web GUI, which renders populate_values()' dictionary
verbatim, had no such signal at all -- so a browser showed a substituted mode
in exactly the same white as a mode the operator selected, with nothing to say
the system had picked it.

The indicator is computed once, in populate_values(), rather than twice: the
framebuffer path now reads the published value instead of recomputing it, so
the two GUIs cannot disagree about when the readout is green.
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIMPLE_GUI = ROOT / "src/module/simple_gui.py"
TEMPLATE = ROOT / "src/module/app/templates/template.html"

KEY = "dynamic_resolution_indicator"


class DynamicResolutionIndicatorWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gui = SIMPLE_GUI.read_text(encoding="utf-8")
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_populate_values_publishes_the_indicator(self):
        self.assertIn(f'"{KEY}": self._dynamic_resolution_indicator_active()', self.gui)

    def test_the_framebuffer_gui_reads_the_published_value(self):
        # Not a second call to _dynamic_resolution_indicator_active(): the
        # value the browser is told and the colour the panel is drawn in have
        # to come from the same evaluation.
        self.assertIn(f'elif values["{KEY}"]:', self.gui)

    def test_the_web_gui_tints_res_from_that_key(self):
        self.assertIn(f"truthy(V.{KEY})", self.html)
        self.assertIn("$('g-res').classList.toggle('tinted'", self.html)

    def test_switching_orange_outranks_the_green(self):
        # .group.switching and .group.tinted both colour .value, so letting
        # both classes land at once would leave the winner to stylesheet
        # order. A reconfigure in progress is the more urgent state.
        block = self.html[self.html.index("$('g-res').classList.toggle('tinted'"):]
        block = block[:block.index(";")]
        self.assertIn("!truthy(V.resolution_switching)", block)

    def test_the_tint_class_is_the_one_the_stylesheet_defines(self):
        self.assertIn(".group.tinted .value { color: var(--sync-tint); }", self.html)


if __name__ == "__main__":
    unittest.main()
