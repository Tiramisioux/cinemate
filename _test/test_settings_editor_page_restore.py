"""A reload must land on the page the operator was on, not always Settings.

The editor used to bootstrap with a literal setActivePage('settings'), so every
reload dropped the operator back on the Settings pane -- including the reloads
the page triggers itself after a resolution change. The rail already writes a
section id into the hash and every section declares its page via data-page, so
the hash already carried the answer; nothing read it.

These are structural guards. The behaviour itself is JavaScript and was
verified in a browser against the desk harness at 1440x800:
  reload #bootconfig -> config pane, section at 74px (its scroll-margin-top)
  reload #live       -> live pane
  reload #clips      -> raw pane
  stale/absent hash  -> settings (the default)
  tab click          -> pushState, so a rail deep-link is not destroyed
  back / forward     -> pane restored, section back at 74px
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


class PageRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_bootstrap_no_longer_hardcodes_the_settings_page(self):
        self.assertNotIn("setActivePage('settings');", self.html)

    def test_bootstrap_restores_the_page_from_the_hash(self):
        self.assertIn("setActivePage(pageFromHash()", self.html)

    def test_every_page_has_a_landing_section_that_exists(self):
        m = re.search(r"var PAGE_LANDING = \{([^}]*)\}", self.html)
        self.assertIsNotNone(m, "PAGE_LANDING table missing")
        landings = dict(re.findall(r"(\w+):\s*'([^']+)'", m.group(1)))

        pages = set(re.findall(r'data-page-tab="([a-z]+)"', self.html))
        self.assertTrue(pages, "no page tabs found")
        self.assertEqual(set(landings) , pages, "a page has no landing section")

        for page, section_id in landings.items():
            self.assertRegex(
                self.html,
                rf'id="{re.escape(section_id)}"[^>]*data-page="{re.escape(page)}"',
                f"landing section #{section_id} for page {page} is missing "
                f"or does not belong to that page",
            )

    def test_page_switches_push_history_rather_than_replacing_it(self):
        # replaceState would overwrite the rail deep-link the operator is
        # standing on, silently eating one entry from the back button.
        self.assertIn("history.pushState(null, '', '#' + PAGE_LANDING[page])", self.html)
        self.assertNotIn("history.replaceState(null, '', '#' + PAGE_LANDING[page])", self.html)

    def test_hashchange_scrolls_after_the_pane_is_visible(self):
        # The browser's own fragment scroll fires before hashchange, when the
        # target section is still display:none and therefore box-less.
        self.assertIn("addEventListener('hashchange'", self.html)
        self.assertIn("scrollIntoView({ behavior: 'auto', block: 'start' })", self.html)


if __name__ == "__main__":
    unittest.main()
