"""The settings editor's copy is read from markdown, so the reading must hold.

The editor's prose moved out of `templates/settings_editor.html` and into
`resources/gui-text/*.md`, which the template looks up by key at startup. That
buys one home for the copy and costs a parser, and a parser is a new way for
the page to go wrong quietly:

- a key that silently resolves to nothing leaves a blank space in a pane, and
  a blank space is not something anyone reports;
- a sentence containing a `<` would become markup if it were not escaped;
- an anchor that loses its `data-nav` or `data-open-config` still looks like a
  link and does nothing when clicked, which is the shape of F-291 all over
  again.

`tools/gui_text_check.py` gates the template and the markdown against each
other in CI. This covers the reader underneath it.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.app.gui_text import load_gui_text, lookup, render_inline  # noqa: E402

GUI_TEXT = ROOT / "resources" / "gui-text"

# The shipped copy is 274 strings. A floor rather than the exact number: a
# real edit may add or drop a card, but a parser that stops matching the file
# shape drops to nearly nothing, and that has to fail rather than pass with an
# empty dict (see conventions/checks-and-ci.md, "a check that finds nothing
# must fail").
MINIMUM_STRINGS = 200


class ShippedCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = load_gui_text(GUI_TEXT)

    def test_the_shipped_markdown_actually_parses(self):
        self.assertGreaterEqual(len(self.text), MINIMUM_STRINGS)

    def test_no_string_comes_back_empty(self):
        for key, value in self.text.items():
            with self.subTest(key=key):
                self.assertTrue(value.strip(), f"{key} parsed to nothing")

    def test_the_editors_notes_are_not_mistaken_for_copy(self):
        # "_(no pane description)_" marks a string that is deliberately
        # absent. It is a note to whoever edits the file, not text to render.
        for key, value in self.text.items():
            with self.subTest(key=key):
                self.assertNotIn("_(no ", value)

    def test_link_attributes_survive_the_round_trip(self):
        # Both of the editor's inline links are attribute-carrying JS hooks.
        self.assertIn('<a href="#steps" data-nav>', self.text["note.controls.0.body"])
        self.assertIn('<a href="#" data-open-config>', self.text["note.bootconfig.1.body"])

    def test_mono_runs_become_the_class_the_stylesheet_styles(self):
        self.assertIn(
            '<span class="mono">hardware_controls</span>', self.text["pane.controls.sub"]
        )

    def test_captions_split_into_one_string_per_control(self):
        self.assertEqual(self.text["caption.arrays.iso.free.0"], "Free stepping")
        self.assertEqual(self.text["caption.arrays.iso.free.1"], "Increment")


class RenderingTests(unittest.TestCase):
    def test_a_sentence_with_markup_in_it_is_escaped(self):
        rendered = render_inline("Set it to <b>0</b> & see.")
        self.assertNotIn("<b>", rendered)
        self.assertIn("&lt;b&gt;", rendered)
        self.assertIn("&amp;", rendered)

    def test_emphasis_and_mono(self):
        self.assertEqual(render_inline("`x` **y** *z*"),
                         '<span class="mono">x</span> <strong>y</strong> <em>z</em>')

    def test_a_link_carries_the_attributes_it_was_given(self):
        self.assertEqual(render_inline("[go](#steps){data-nav}"),
                         '<a href="#steps" data-nav>go</a>')
        self.assertEqual(render_inline("[go](#steps)"), '<a href="#steps">go</a>')


class MissingKeyTests(unittest.TestCase):
    def test_a_miss_is_visible_rather_than_blank(self):
        rendered = lookup({}, "card.nothing.here")
        self.assertIn("gui-text-missing", rendered)
        self.assertIn("card.nothing.here", rendered)

    def test_the_marker_the_page_styles_is_the_marker_produced(self):
        # A class the stylesheet does not know about is an invisible miss.
        template = (ROOT / "src/module/app/templates/settings_editor.html").read_text(
            encoding="utf-8"
        )
        self.assertIn(".gui-text-missing{", template)


class MalformedInputTests(unittest.TestCase):
    def test_an_empty_directory_warns_rather_than_raising(self):
        import tempfile

        with tempfile.TemporaryDirectory() as empty:
            with self.assertLogs("module.app.gui_text", level="WARNING"):
                self.assertEqual(load_gui_text(empty), {})

    def test_a_missing_directory_warns_rather_than_raising(self):
        with self.assertLogs("module.app.gui_text", level="WARNING"):
            self.assertEqual(load_gui_text(ROOT / "no" / "such" / "place"), {})

    def test_a_duplicate_key_warns_and_keeps_the_first(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "a.md").write_text(
                "### First\n<!-- key: card.x -->\n\nOne.\n"
                "### Second\n<!-- key: card.x -->\n\nTwo.\n",
                encoding="utf-8",
            )
            with self.assertLogs("module.app.gui_text", level="WARNING"):
                text = load_gui_text(directory)
            self.assertEqual(text["card.x.label"], "First")
            self.assertEqual(text["card.x.help"], "One.")


if __name__ == "__main__":
    unittest.main()
