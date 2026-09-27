"""Todo batch 2026-09-27, issue 5 ("resolution change loses the anamorphic
pin" -- actually a rendering bug, not a lost setting; see
ANAMORPHIC-FINDINGS.md). `renderPreview()` in template.html used to compute
`previewAspect = (measured || aspect) * ana`. `measured` is
`streamNaturalAspect()` -- the live MJPEG `<img>`'s own naturalWidth/Height,
i.e. the lores buffer's decoded size. That buffer is already desqueezed:
`module.sensor_detect.compute_preview_geometry()` bakes `anamorphic_factor`
into `lores_width` before cinepi-raw is ever launched (see its own
docstring). Multiplying `ana` into `measured` therefore applied the
desqueeze twice, and with `object-fit: contain` the white preview frame
ended up visibly wider than the (correctly-sized) picture inside it -- the
operator's report, word for word: "the white frame suggests [anamorphic]
but the image is normal".

`V.aspect`, the fallback used only before the first frame decodes, is a
different quantity -- simple_gui.py's `round(w_int / h_int, 2)` over the raw
sensor WIDTH/HEIGHT Redis keys -- and carries no anamorphic term at all, so
it still needs the multiply.

No JS execution harness exists in this suite (see test_b95_sync_box_crossed_
consistency.py for the established pattern), so this is a structural check
against the template source: the measured branch must not multiply by `ana`,
and the fallback branch must.
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/module/app/templates/template.html"


class WebPreviewAnamorphicDoubleApplyTests(unittest.TestCase):
    def setUp(self):
        self.src = TEMPLATE.read_text(encoding="utf-8")
        m = re.search(
            r"function renderPreview\(\)\s*\{.*?\n    \}",
            self.src,
            re.S,
        )
        self.assertIsNotNone(m, "renderPreview() not found in template.html")
        self.render_preview_src = m.group(0)

    def test_measured_branch_does_not_multiply_by_anamorphic_factor(self):
        # `measured` (streamNaturalAspect()) already carries the desqueeze --
        # baked into the lores buffer's own dimensions by
        # compute_preview_geometry() before cinepi-raw launches. Applying
        # `ana` again here is the double-apply bug (report 5).
        m = re.search(
            r"if\s*\(measured\)\s*\{\s*previewAspect\s*=\s*measured\s*\*\s*\(combined \? 2 : 1\);\s*\}",
            self.render_preview_src,
        )
        self.assertIsNotNone(
            m,
            "renderPreview()'s measured branch must set previewAspect from "
            "`measured` alone (times the combined-view doubling), with no "
            "`ana` multiply -- multiplying `ana` back in here reintroduces "
            "the double-apply that stretched the white preview frame past "
            "the picture it wraps",
        )

    def test_fallback_branch_still_multiplies_by_anamorphic_factor(self):
        # V.aspect (simple_gui.py's round(w/h, 2) over the raw sensor
        # WIDTH/HEIGHT keys) carries no anamorphic term, so the fallback
        # path -- used only before the first frame has decoded, or for a
        # combined dual-sensor view -- still needs the multiply.
        m = re.search(
            r"else if\s*\(aspect > 0\)\s*\{\s*"
            r"previewAspect\s*=\s*aspect\s*\*\s*\(ana > 0 \? ana : 1\)\s*\*\s*\(combined \? 2 : 1\);\s*\}",
            self.render_preview_src,
        )
        self.assertIsNotNone(
            m,
            "renderPreview()'s V.aspect fallback must still multiply by "
            "the anamorphic factor -- V.aspect carries no desqueeze of its "
            "own",
        )

    def test_the_pre_fix_shared_base_double_apply_shape_is_gone(self):
        # Pre-fix shape: `const base = measured || aspect;` then
        # `previewAspect = base * (ana > 0 ? ana : 1) * ...` -- one multiply
        # applied to both branches regardless of whether the value already
        # carried the desqueeze.
        self.assertNotIn(
            "const base = measured || aspect;",
            self.render_preview_src,
        )


if __name__ == "__main__":
    unittest.main()
