"""Phone layout: one line per row in landscape, bigger text, aligned clip name.

Three separate reports from the rig, all in the bottom half of the page:

* RAM still dropped to a second line in landscape. The landscape rule that
  fixed the top and button rows never named #bottom-row, so it kept wrapping
  -- and every wrapped row comes off the picture, which is the one flexible
  track on the page.
* The clip name floated between its neighbours' label and value lines.
  #bottom-row centred its items, and the clip name is ~0.44 the size of the
  readouts beside it, so centring is visibly not alignment.
* The top and bottom rows were sized for a mouse. The top row's values are
  the tap targets -- each .group carries a transparent native <select> -- so
  on a phone the text is the button.

Portrait deliberately keeps wrapping: it has the height to spend, and the
operator confirmed overflow there is fine.

Measured in a browser at 844x390 and 390x844 before these were written.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/module/app/templates/template.html"


def block(html, opener):
    """The body of the media query starting at *opener*."""
    start = html.index(opener)
    depth, i = 0, start
    while True:
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                return html[start:i + 1]
        i += 1


class LandscapeOneLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")
        cls.landscape = block(
            cls.html, "@media (orientation: landscape) and (max-width: 950px)")

    def test_all_three_rows_stay_on_one_line(self):
        self.assertIn("#top-row, #bottom-row, #button-row { flex-wrap: nowrap; }",
                      self.landscape)

    def test_the_clip_name_is_the_field_that_gives(self):
        # Everything else in the row is a short fixed readout; the clip name
        # already ellipsizes, so it is the only one that can absorb the
        # shortfall without a readout falling off the line.
        self.assertIn("#bottom-row .group { min-width: 0; flex: 0 0 auto; }", self.landscape)
        self.assertIn("#bottom-row .group.clip { flex: 0 1 auto;", self.landscape)

    def test_portrait_is_left_wrapping(self):
        portrait = block(self.html, "@media (orientation: portrait) and (max-width: 900px)")
        self.assertNotIn("nowrap", portrait)


class ClipNameAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_the_bottom_row_aligns_on_the_text_baseline(self):
        # The row's own rule, not the landscape override of the same
        # selector, which appears earlier in the file.
        rule = block(self.html, "#bottom-row {\n            display: flex;")
        self.assertIn("align-items: baseline;", rule)
        self.assertNotIn("align-items: center;", rule)

    def test_the_buffer_bar_opts_out(self):
        # A bar has no baseline; left in the baseline group it hangs off the
        # bottom of the row instead of sitting level with the readouts.
        self.assertIn("align-self: center;", block(self.html, "        #buffer-meter {"))


class PhoneTextSizeTests(unittest.TestCase):
    """+20%, applied to the rows' own --value-size/--label-size rather than
    to each font-size, so every size derived from them (the HDR badge, the
    WAV pill, the clip name, the buffer bar's height) scales with them."""

    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")
        cls.narrow = block(cls.html, "@media (max-width: 900px), (orientation: portrait)")

    # Where each row takes its unscaled sizes from: the top row inherits
    # the page-wide pair, the bottom row states its own.
    BASE = {
        ("#top-row", "--value-size"): (1.05, 2.05, 1.9),
        ("#top-row", "--label-size"): (0.72, 1.45, 1.35),
        ("#bottom-row", "--value-size"): (0.9, 1.5, 1.4),
        ("#bottom-row", "--label-size"): (0.65, 1.05, 1.0),
    }

    def _clamp(self, text, selector, prop):
        rule = re.search(re.escape(selector) + r"\s*\{(.*?)\}", text, re.S).group(1)
        found = re.search(re.escape(prop) + r":\s*clamp\(([^)]*)\)", rule).group(1)
        return [float(v.strip().rstrip("remvw")) for v in found.split(",")]

    def test_the_base_sizes_this_test_scales_from_are_still_the_real_ones(self):
        # If a clamp() upstream is retuned, the ratios below silently stop
        # meaning what they say. Pin the inputs too.
        self.assertEqual(tuple(self._clamp(self.html, ":root", "--value-size")),
                         self.BASE[("#top-row", "--value-size")])
        self.assertEqual(tuple(self._clamp(self.html, ":root", "--label-size")),
                         self.BASE[("#top-row", "--label-size")])
        bottom = block(self.html, "#bottom-row {\n            display: flex;")
        for prop in ("--value-size", "--label-size"):
            with self.subTest(prop=prop):
                self.assertEqual(tuple(self._clamp(bottom, "#bottom-row", prop)),
                                 self.BASE[("#bottom-row", prop)])

    def test_each_row_is_scaled_by_a_fifth(self):
        for (row, prop), base in self.BASE.items():
            with self.subTest(row=row, prop=prop):
                phone = self._clamp(self.narrow, row, prop)
                self.assertEqual(len(base), len(phone))
                for b, p in zip(base, phone):
                    self.assertAlmostEqual(p / b, 1.2, places=2)

    def test_only_the_two_rows_are_rescaled(self):
        # Nothing in the rails or the drawer is tapped to change a value, and
        # the rails are already fitted to the picture by fitRails().
        rescaled = set(re.findall(r"(#[\w-]+) \{\s*\n\s*--value-size:", self.narrow))
        self.assertEqual(rescaled, {"#top-row", "#bottom-row"})


if __name__ == "__main__":
    unittest.main()
