"""F-257: populate_values() publishes fps_label/shutter_label/exposure_label/
iso_label/wb_label/res_label for the web GUI, but the template derived its
own -- six words hardcoded as static HTML markup, completely independent of
what Python sends. The web GUI is supposed to have no state of its own (it
consumes the HDMI GUI's value dictionary verbatim over Socket.IO); these six
were the exception, and the exception was never even read back client-side.

Fix: the six label spans now carry ids (l-fps, l-shutter, l-exp, l-iso,
l-wb, l-res) and renderTopRow() sets their text from V.*_label, the same
pattern already used for every value span (v-fps, v-iso, ...). This test
checks the wiring end to end: Python publishes the key, the HTML element
exists, and the JS actually reads that key into that element.
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIMPLE_GUI = ROOT / "src/module/simple_gui.py"
TEMPLATE = ROOT / "src/module/app/templates/template.html"

LABEL_KEYS = (
    "fps_label",
    "shutter_label",
    "exposure_label",
    "iso_label",
    "wb_label",
    "res_label",
)
LABEL_IDS = {
    "fps_label": "l-fps",
    "shutter_label": "l-shutter",
    "exposure_label": "l-exp",
    "iso_label": "l-iso",
    "wb_label": "l-wb",
    "res_label": "l-res",
}


class WebGuiLabelsFromPopulateValuesTests(unittest.TestCase):
    def setUp(self):
        self.simple_gui_src = SIMPLE_GUI.read_text(encoding="utf-8")
        self.template_src = TEMPLATE.read_text(encoding="utf-8")

    def test_populate_values_still_publishes_every_label_key(self):
        for key in LABEL_KEYS:
            with self.subTest(key=key):
                self.assertRegex(
                    self.simple_gui_src,
                    rf'"{key}":\s*"',
                    f"populate_values() no longer publishes {key}",
                )

    def test_every_label_span_has_an_id(self):
        for key, element_id in LABEL_IDS.items():
            with self.subTest(key=key):
                self.assertIn(
                    f'id="{element_id}"',
                    self.template_src,
                    f"label span for {key} lost its id={element_id}",
                )

    def test_render_top_row_sets_every_label_from_v(self):
        m = re.search(r"function renderTopRow\(\) \{(.*?)\n    \}", self.template_src, re.S)
        self.assertIsNotNone(m, "renderTopRow() not found")
        body = m.group(1)
        for key, element_id in LABEL_IDS.items():
            with self.subTest(key=key):
                self.assertIn(
                    f"text('{element_id}', V.{key})",
                    body,
                    f"renderTopRow() no longer sets {element_id} from V.{key}",
                )

    def test_no_static_fallback_text_remains_in_the_label_spans(self):
        # The whole point: the span must be empty in markup (JS fills it),
        # not carrying its own hardcoded word that V.*_label duplicates.
        for word in ("FPS", "SHUTTER", "EXP", "EI", "WB", "RES"):
            with self.subTest(word=word):
                self.assertNotRegex(
                    self.template_src,
                    rf'<span class="label"[^>]*>{word}</span>',
                    f'a label span still hardcodes "{word}" instead of being filled from V',
                )


if __name__ == "__main__":
    unittest.main()
