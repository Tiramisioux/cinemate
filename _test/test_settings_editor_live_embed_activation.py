"""The live iframe must be made visible before its lazy source is restored.

Otherwise a browser is allowed to defer loading ``/?xp=1`` because its parent
is ``display:none``. The tab looks active before the embedded page has bound
its controls, so the first tap(s) appear to do nothing.
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


class LiveEmbedActivationTests(unittest.TestCase):
    def test_live_source_is_restored_after_the_pane_is_visible(self):
        html = TEMPLATE.read_text(encoding="utf-8")
        start = html.index("function setActivePage(page, opts){")
        end = html.index("  /* ---------- search ---------- */", start)
        body = html[start:end]

        self.assertLess(
            body.index("updateGroupVisibility();"),
            body.index("syncLiveEmbed(page);"),
            "restore the lazy live iframe only after its parent is visible",
        )


if __name__ == "__main__":
    unittest.main()
