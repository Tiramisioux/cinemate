"""WP-CM-10 desk check: the crop diagram's client-side JS must agree with the
same sensor-domain contract as the Python side (test_settings_editor_crop_domain.py
covers the backend fields it draws from). There is no JS execution harness in
this suite, so this is a source-level check, in the same style
test_settings_editor_switchset.py uses for its own source-text assertions.

cropDiagram() used to scale the crop by binning again ("mode.crop_width*bx")
on the assumption that crop_width/crop_height was the mode's *output*
domain. Under the WP-CM-10 contract it is already sensor-domain at any
binning, so that second multiplication would now double the crop rectangle
out of the diagram frame.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/module/app/templates/settings_editor.html"


class CropDiagramDomainTests(unittest.TestCase):
    def setUp(self):
        self.html = TEMPLATE.read_text(encoding="utf-8")
        start = self.html.index("function cropDiagram(mode){")
        end = self.html.index("\n  }\n", start)
        self.fn = self.html[start:end]

    def test_crop_geometry_is_not_rescaled_by_binning(self):
        self.assertNotIn("mode.crop_width*bx", self.fn)
        self.assertNotIn("mode.crop_height*by", self.fn)
        self.assertNotIn("mode.crop_x || 0)*bx", self.fn)
        self.assertNotIn("mode.crop_y || 0)*by", self.fn)

    def test_crop_geometry_is_used_directly(self):
        self.assertRegex(self.fn, r"\bsw\s*=\s*mode\.crop_width\b")
        self.assertRegex(self.fn, r"\bsh\s*=\s*mode\.crop_height\b")
        self.assertRegex(
            self.fn,
            r"\bsx\s*=\s*mode\.crop_x\s*\|\|\s*0\s*,\s*sy\s*=\s*mode\.crop_y\s*\|\|\s*0\b",
        )


if __name__ == "__main__":
    unittest.main()
