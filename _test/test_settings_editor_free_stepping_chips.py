"""Free stepping must show the settings editor's step chips as a range.

Turning free stepping on for a parameter stops the interior stops being what
the control lands on: the sweep runs from the array's lowest entry to its
highest in increments of free_increment (parameters.steps_bounds and the
_rebuild_*_steps methods). The steplist says so by muting everything except
the two ends.

Only four steplists have a free toggle. The four HDR free toggles live in the
Pots section with no steplist beside them, and the remaining chip containers
(light_hz, anamorphic, k_steps, bit_depths, oled values) have no free stepping.

Numeric lists are also held in ascending order at all times, in both modes,
and in free stepping the two ends are pulled to the right of the row with an
arrow between them so it reads as the range it is. That move is done with
flex `order`, never by moving nodes: the DOM order is what the saved array is
read back from.

Verified in a browser against a harness built from the shipped functions, fed
chips in deliberately unsorted DOM order (800, 100, 3200, 400, 1600):
  DOM after sort  100 400 800 1600 3200      <- and this is what is saved
  free off        every chip lit, plain ascending row
  free on         400* 800* 1600*  100 -> 3200      (* = muted)
i.e. the ends are found by value, and the DOM is never reordered to show them.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


class FreeSteppingChipMutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_exactly_the_four_free_stepping_steplists_are_mapped(self):
        block = re.search(r"var FREE_STEP_TOGGLES = \{(.*?)\};", self.html, re.S)
        self.assertIsNotNone(block, "FREE_STEP_TOGGLES map is missing")
        pairs = dict(re.findall(r"'([\w.]+)':\s*'([\w.]+)'", block.group(1)))
        self.assertEqual(pairs, {
            "arrays.iso.steps": "arrays.iso.free",
            "arrays.shutter_a.steps": "arrays.shutter_a.free",
            "arrays.fps.steps": "arrays.fps.free",
            "arrays.wb.steps": "arrays.wb.free",
        })

    def test_every_mapped_steplist_and_toggle_actually_exists_in_the_markup(self):
        for chip_path, free_path in (
            ("arrays.iso.steps", "arrays.iso.free"),
            ("arrays.shutter_a.steps", "arrays.shutter_a.free"),
            ("arrays.fps.steps", "arrays.fps.free"),
            ("arrays.wb.steps", "arrays.wb.free"),
        ):
            with self.subTest(chip_path=chip_path):
                self.assertIn(f'data-chip-path="{chip_path}"', self.html)
                self.assertIn(f'data-path="{free_path}"', self.html)

    def test_the_ends_are_found_by_value_not_by_position(self):
        fn = re.search(r"function syncFreeSteppingChips\(container\)\{(.*?)\n  \}",
                       self.html, re.S).group(1)
        self.assertIn("Math.min.apply", fn)
        self.assertIn("Math.max.apply", fn)
        # chips are never sorted, so position-based CSS would mark the wrong ones
        self.assertNotIn(":first-child", fn)
        self.assertNotIn(":last-child", fn)

    def test_the_muted_rule_outranks_the_always_on_hud_skin(self):
        # #app.skin-hud .step-chip paints every chip white at (1,2,0); a bare
        # .step-chip.is-muted at (0,2,0) would lose to it
        self.assertRegex(self.html, r"\n  \.step-chip\.is-muted\{")
        self.assertRegex(self.html, r"#app\.skin-hud \.step-chip\.is-muted\{")

    def test_every_path_that_changes_chips_or_the_toggle_resyncs(self):
        # add / remove / drag-reorder all converge on onChipsChanged
        after_chips = re.search(r"function onChipsChanged\(container\)\{(.*?)\n  \}",
                                self.html, re.S).group(1)
        self.assertIn("syncFreeSteppingChips(container)", after_chips)

        # the wholesale repaint on load / revert / upload
        repaint = re.search(r"function populateChipContainer\(container, arr\)\{(.*?)\n  \}",
                            self.html, re.S).group(1)
        self.assertIn("syncFreeSteppingChips(container)", repaint)

        # a .toggle fires no change event, so the click handler has to do it
        toggle = re.search(r"\.toggle\[data-path\]'\)\.forEach\(function\(t\)\{(.*?)\n  \}\);",
                           self.html, re.S).group(1)
        self.assertIn("syncAllFreeSteppingChips()", toggle)

        # applyControlValue sets aria-checked without the click handler running
        populate = re.search(r"function populateSettingsForm\(settings\)\{(.*?)\n  \}",
                             self.html, re.S).group(1)
        self.assertIn("syncAllFreeSteppingChips()", populate)

    def test_numeric_lists_are_held_in_ascending_order(self):
        fn = re.search(r"function sortChipContainer\(container\)\{(.*?)\n  \}",
                       self.html, re.S).group(1)
        self.assertIn("chipsAreNumeric(container)", fn)
        # string lists (the OLED fields) keep author order -- there the sequence
        # is the content, not a range
        numeric_only = re.search(r"function chipsAreNumeric\(container\)\{(.*?)\n  \}",
                                 self.html, re.S).group(1)
        self.assertIn("data-chip-type", numeric_only)
        self.assertIn("'number'", numeric_only)

    def test_a_numeric_list_sorts_itself_so_drag_is_not_offered(self):
        wire = re.search(r"function wireChipContainer\(container\)\{(.*?)\n    container\.addEventListener",
                         self.html, re.S).group(1)
        self.assertIn("if (!chipsAreNumeric(container)) makeChipDraggable", wire)

    def test_the_repaint_sorts_before_writing_the_dirty_baseline(self):
        # otherwise a file that happens to be out of order loads looking edited
        fn = re.search(r"function populateChipContainer\(container, arr\)\{(.*?)\n  \}",
                       self.html, re.S).group(1)
        self.assertLess(fn.index(".sort("),
                        fn.index("setAttribute('data-chip-original'"))

    def test_the_ends_are_moved_by_flex_order_not_by_moving_nodes(self):
        fn = re.search(r"function syncFreeSteppingChips\(container\)\{(.*?)\n  \}",
                       self.html, re.S).group(1)
        self.assertIn("style.order", fn)
        # moving the chips would change what onChipsChanged reads back as the array
        for moving in ("insertBefore", "appendChild(chip", "append(chip"):
            self.assertNotIn(moving, fn)
        self.assertIn("step-range-arrow", fn)

    def test_the_range_arrow_sits_between_the_two_ends(self):
        fn = re.search(r"function syncFreeSteppingChips\(container\)\{(.*?)\n  \}",
                       self.html, re.S).group(1)
        self.assertRegex(fn, r"i === loIdx\) \? '1'")
        self.assertRegex(fn, r"i === hiIdx\) \? '3'")
        self.assertIn("arrow.style.order = '2'", fn)
        self.assertRegex(self.html, r"\.step-range-arrow\{")


if __name__ == "__main__":
    unittest.main()
