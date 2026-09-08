"""Every page tab has to bring its own markup, and the topbar has to know it.

The settings editor's pages are wired by five separate hand-maintained
mechanisms, none of which reference each other: a `data-page-tab` button, a
`[data-page-lede]` intro, one or more `.group[data-page]` sections, a
`.rail-group[data-page]` sidebar block, and a page-kind predicate inside
`syncTopbarForPage()` that decides whether the Save / Revert / Download /
Upload controls belong on that page at all.

Nothing checks that a new tab did all five. Miss the lede and the page opens
with no heading; miss the rail group and the sidebar keeps showing the
previous page's; miss the predicate and the page offers to save a
settings.jsonc it does not edit -- which is what the playback tab did before
the current predicate was written, and it fails silently in every case,
because a missing tab-to-page association is indistinguishable from a page
with nothing in it.

ADR-001's standing rule is that no GUI step lands without its check landing
on the same commit. C9 owed this one: `design_token_diff.py` reads
`template.html` only and never opens this file, and `gui_field_extract.py`
looks at it only through an action-catalogue regex, so the fifth tab landed
with no drift check of any kind.

Reads the template as text, the way test_action_catalogues_agree.py reads it
-- the point is to check what is actually written in the file, and a DOM
parser would have to be told the same expectations twice.
"""

import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TEMPLATE = ROOT / "src/module/app/templates/settings_editor.html"

# Pages that really do edit a file on disk, and therefore SHOULD carry the
# Save / Revert / Download / Upload controls. Everything else must be named in
# syncTopbarForPage()'s predicate instead. A sixth tab has to join one list or
# the other, which is the whole point: neither default is safe to inherit.
FILE_BACKED_PAGES = {"settings", "config"}


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def page_tabs(html: str) -> set[str]:
    return set(re.findall(r'data-page-tab="([a-z0-9_-]+)"', html))


def attribute_pages(html: str, attribute: str) -> set[str]:
    return set(re.findall(rf'{attribute}="([a-z0-9_-]+)"', html))


def rail_group_pages(html: str) -> set[str]:
    return set(re.findall(r'class="rail-group"\s+data-page="([a-z0-9_-]+)"', html))


def group_pages(html: str) -> set[str]:
    """Pages named by a `.group` section (the page's actual content)."""
    return set(re.findall(r'class="group[^"]*"[^>]*\sdata-page="([a-z0-9_-]+)"', html))


def topbar_no_file_pages(html: str) -> set[str]:
    """The pages syncTopbarForPage() treats as not file-backed."""
    match = re.search(r"var noFilePage\s*=\s*(.+?);", html, re.S)
    assert match, "syncTopbarForPage's noFilePage predicate not found"
    return set(re.findall(r"activePage\s*===\s*'([a-z0-9_-]+)'", match.group(1)))


class PageTabMarkupTests(unittest.TestCase):
    def setUp(self):
        self.html = _template()
        self.tabs = page_tabs(self.html)

    def test_there_are_tabs_to_check(self):
        # Guards the regexes themselves: if the markup shape changes, every
        # other test here would pass vacuously on an empty set.
        self.assertGreaterEqual(len(self.tabs), 5, f"found only {self.tabs}")

    def test_every_tab_has_a_lede(self):
        missing = sorted(self.tabs - attribute_pages(self.html, "data-page-lede"))
        self.assertEqual(missing, [], f"tabs with no [data-page-lede]: {missing}")

    def test_every_tab_has_at_least_one_group(self):
        missing = sorted(self.tabs - group_pages(self.html))
        self.assertEqual(missing, [], f"tabs with no .group[data-page]: {missing}")

    def test_every_tab_has_a_rail_group(self):
        missing = sorted(self.tabs - rail_group_pages(self.html))
        self.assertEqual(missing, [], f"tabs with no .rail-group[data-page]: {missing}")

    def test_no_orphan_page_markup(self):
        """Markup for a page with no tab is dead weight nothing can reach."""
        for name, pages in (("lede", attribute_pages(self.html, "data-page-lede")),
                            ("rail group", rail_group_pages(self.html)),
                            ("group", group_pages(self.html))):
            with self.subTest(name):
                orphans = sorted(pages - self.tabs)
                self.assertEqual(orphans, [], f"{name} markup with no tab: {orphans}")

    def test_the_topbar_predicate_classifies_every_tab(self):
        """Each tab either edits a file or is named in the predicate.

        A tab in neither set falls through as a file page and offers to save a
        file it does not edit -- silently, because the buttons look normal.
        """
        classified = topbar_no_file_pages(self.html) | FILE_BACKED_PAGES
        unclassified = sorted(self.tabs - classified)
        self.assertEqual(
            unclassified, [],
            f"tabs neither file-backed nor in syncTopbarForPage's predicate: "
            f"{unclassified}")

    def test_the_predicate_does_not_name_a_page_that_edits_a_file(self):
        both = sorted(topbar_no_file_pages(self.html) & FILE_BACKED_PAGES)
        self.assertEqual(both, [],
                         f"pages claimed as both file-backed and not: {both}")


if __name__ == "__main__":
    unittest.main()
