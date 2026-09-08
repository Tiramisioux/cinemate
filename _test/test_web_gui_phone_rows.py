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


LANDSCAPE_QUERY = "@media (orientation: landscape) and (max-width: 950px)"


class LandscapeOneLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")
        cls.landscape = block(cls.html, LANDSCAPE_QUERY)

    def test_all_three_rows_stay_on_one_line(self):
        self.assertIn("#top-row, #bottom-row, #button-row { flex-wrap: nowrap; }",
                      self.landscape)

    def test_the_nowrap_rule_outranks_every_rows_own_flex_wrap(self):
        """Source order, not just presence -- the bug this test exists for.

        All four declarations are on id selectors, so they tie on specificity
        and the last one in the file wins. The media query used to sit up by
        the rails, above #bottom-row's and #button-row's own rules: #top-row
        obeyed it and the other two silently kept `wrap`. Every text assertion
        about the rule passed the whole time, because the rule was there --
        it just lost. Measured before the fix at 844x390: #bottom-row and
        #button-row both computed to `wrap`.
        """
        query_at = self.html.index(LANDSCAPE_QUERY)
        for row in ("#top-row", "#bottom-row", "#button-row"):
            with self.subTest(row=row):
                # The row's own rule, identified by its display:flex -- not
                # whichever "#row {" the media query happens to open with.
                base = block(self.html, "%s {\n            display: flex;" % row)
                self.assertIn("flex-wrap: wrap;", base,
                              "%s no longer declares its own flex-wrap; this "
                              "test's premise needs rechecking" % row)
                self.assertLess(
                    self.html.index(base), query_at,
                    "%s's own flex-wrap:wrap sits AFTER the landscape query, "
                    "ties it on specificity and silently wins" % row)

    def test_a_row_that_truly_cannot_fit_wraps_rather_than_hiding_a_reading(self):
        """The clip name is the only field with an ellipsis, so it is the only
        one that can be shrunk. Twelve fields at once -- MEDIA, write speed,
        BUF + bar, recording time, clip name, WAV, LOCK, VOLTAGE, CPU, TEMP,
        RAM, BATT -- do not fit a 667px phone even with the name reduced to
        nothing, and nowrap then pushed BATT off the side of the screen with
        nothing on the page to say so. Measured: BATT's right edge at 723 in a
        667px viewport.

        Shrinking any other field was tried and rejected: none of them
        ellipsizes, so they overlap instead -- "BUF 0%" ran straight through
        the recording time.

        A media query cannot ask this question (it knows the viewport, not how
        many warnings are lit), so it is measured, the way fitRails() measures
        the rails. Verified at 667 (wraps only once warnings are lit), and at
        844 and 932, where even every warning plus a battery stays on one
        line.
        """
        self.assertIn("#bottom-row.cramped { flex-wrap: wrap; }", self.html)
        body = block(self.html, "    function fitBottomRow() {")
        # Measure with the class off, or the row is measured in the wrapped
        # state the class itself caused and never comes back.
        self.assertLess(body.index("classList.remove('cramped')"),
                        body.index("getBoundingClientRect"))
        self.assertIn("row.classList.toggle('cramped',", body)

    def test_the_wrap_decision_has_hysteresis(self):
        """A single threshold flaps, and the flap is expensive.

        For roughly nine pixels of viewport width per warning state the row
        sits within one glyph of its own edge. There, a reading gaining a
        digit -- write speed 98 -> 101 MB/s -- crossed the threshold and back,
        and each crossing added or removed a line. That line comes off
        #stage, the only 1fr track, so the picture jumped about 25px (9% of
        its height) every time the number changed. Reproduced at 731x375 and
        800x375 with warnings lit; invisible to a fixed-content sweep, which
        measures each state once and settled.

        The release margin is derived from the rendered font size rather than
        hardcoded, because this row's text is 20% larger on a phone, and the
        band has to stay wider than a two-digit swing at whatever size it is.
        """
        body = block(self.html, "    function fitBottomRow() {")
        self.assertIn("const wasCramped = row.classList.contains('cramped');", body)
        self.assertIn("const settled = overflows === bottomFitLast;", body)
        self.assertIn("row.classList.toggle('cramped', settled ? overflows : wasCramped);",
                      body)

    def test_the_latch_needs_no_slack_to_measure(self):
        """Why agreement, and not a pixel hysteresis band.

        Near the narrow end the row is at capacity in every state -- it only
        fits because the clip name ellipsizes -- so there is no spare width
        for a release margin to measure against. A band sized in pixels was
        tried and measured: once a warning had lit at 667px the row never
        came back to one line after it cleared. Agreement between two
        consecutive measurements needs no slack at all.
        """
        body = block(self.html, "    function fitBottomRow() {")
        # Strip comments: the rejected approach is described in prose there,
        # and the point is that no code implements it.
        code = re.sub(r"//.*", "", body)
        for token in ("release", "clearance", "fontSize", ".spacer"):
            with self.subTest(token=token):
                self.assertNotIn(token, code)

    def test_the_fit_is_not_driven_by_an_observer_on_the_row_it_resizes(self):
        # .cramped changes #bottom-row's own height, so a ResizeObserver on
        # that row would re-enter on every toggle.
        self.assertNotIn("ResizeObserver(fitBottomRow)", self.html)
        self.assertIn("scheduleBottomFit();", self.html)
        # render() is where the row's contents change; resize covers rotation.
        render = block(self.html, "    function render() {")
        self.assertIn("scheduleBottomFit();", render)
        self.assertIn("window.addEventListener('resize', () => scheduleBottomFit());",
                      self.html)

    def test_the_rows_cannot_push_their_own_grid_track_wider_than_the_viewport(self):
        """A grid item's automatic minimum size is its content size.

        With the rows wrapping, each row's min-content width was small and
        this never bit. With nowrap it is the whole row, so #bottom grew to
        721px inside a 667px #app -- RAM's value off the right edge, and the
        clip name declining to ellipsize because from the row's point of view
        there was no shortfall to absorb. Width-axis twin of #stage's
        min-height:0.
        """
        self.assertIn("#app > * { min-width: 0; }", self.html)

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

    def test_the_wav_badge_sits_on_the_clip_names_line(self):
        # .badge is align-self:center, which parks the pill against a group
        # box whose height comes from the clip name's own line -- so it read
        # as a separate item beside the text rather than part of it.
        rule = block(self.html, "        .badge.wav {")
        self.assertIn("align-self: baseline;", rule)
        # Order matters: .badge and .badge.wav both set align-self, and
        # .badge.wav only wins by being later as well as more specific.
        self.assertLess(self.html.index("        .badge {"), self.html.index(rule))

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
