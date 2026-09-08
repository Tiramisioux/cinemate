"""feature/web-ui-combined shipped two independent folder-picker download
clients: fix/web-ui-round2's single bulk IIFE (res.body.pipeTo(w), no
?storage=, a 429 treated as fatal) and fix/web-ui-portrait's per-row client
(a progress bar, a cancel button, AbortController cleanup, a documented error
taxonomy, a pre-flight listed check, and ?storage= on every request). They
auto-merged with zero conflict markers because they occupy disjoint regions
of settings_editor.html.

Portrait's client survived; round2's was deleted and its multi-take
sequencing (pick the folder once, write takes one after another, "Saving N
of M" between them) was grafted onto portrait's per-take functions instead.
These tests pin that shape so a future merge or edit cannot silently bring
either half of the duplication back, or drop the reconciliation.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


class NoDuplicateClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_round2_bulk_iife_is_gone(self):
        for token in ("bulkDownloadFolder", "folderDownloadSupported", "pipeTo"):
            self.assertNotIn(token, self.html, f"round2 download client leftover: {token}")

    def test_only_one_showdirectorypicker_call_site(self):
        # pickFolder() is the sole caller; nothing else should invoke the
        # API directly, or the folder-picked-once invariant is bypassable.
        self.assertEqual(self.html.count("window.showDirectoryPicker("), 1)

    def test_no_duplicate_element_ids(self):
        ids = re.findall(r'id="([^"]+)"', self.html)
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(dupes, [])

    def test_the_file_stays_es5(self):
        # var + function + .then, never async/await/arrow -- the page
        # targets older iOS (see template.html's own comment on this).
        self.assertNotRegex(self.html, r"async function|await |=> *\{")


class MergedClientShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_folder_is_picked_once_and_shared(self):
        self.assertIn("function pickFolder(){", self.html)
        self.assertIn(
            "id: 'cinemate-raw-downloads', mode: 'readwrite', startIn: 'downloads',",
            self.html,
        )

    def test_per_take_save_is_a_reusable_function(self):
        self.assertIn(
            "function savePickedTakeIntoRow(dirRoot, name, storage, row){",
            self.html,
        )

    def test_single_row_path_still_owns_its_own_refresh_suppression(self):
        m = re.search(r"function startPickedDownload\(.*?\n  \}", self.html, re.S)
        self.assertIsNotNone(m)
        self.assertIn("refreshSuppressed = true;", m.group(0))
        self.assertIn("refreshSuppressed = false;", m.group(0))

    def test_bulk_path_picks_once_and_chains_sequentially(self):
        m = re.search(
            r"document\.getElementById\('bulkDownload'\)\.addEventListener\('click', function\(\).*?\n  \}\);",
            self.html, re.S,
        )
        self.assertIsNotNone(m, "bulkDownload click handler not found")
        body = m.group(0)
        self.assertIn("pickFolder().then(function(dirRoot){", body)
        self.assertIn("refreshSuppressed = true;", body)
        self.assertIn("names.reduce(function(chain, name, i){", body)
        self.assertIn("savePickedTakeIntoRow(dirRoot, name,", body)
        self.assertIn("Saving ' + (i + 1) + ' of ' + names.length", body)
        # Cleared once at the end, not per take -- a mid-batch refresh would
        # destroy the row the batch is currently writing progress into.
        self.assertEqual(body.count("refreshSuppressed = false;"), 2)  # success + failure arm

    def test_bulk_button_disables_only_on_the_non_picker_fallback(self):
        m = re.search(r"function updateBulkBar\(\).*?\n  \}", self.html, re.S)
        self.assertIsNotNone(m)
        self.assertIn("!CAN_PICK_FOLDER && names.length > 1", m.group(0))

    def test_the_footer_does_not_send_operators_to_a_switch_that_is_not_there(self):
        # It used to name two different reasons for the missing picker, one of
        # which told the operator to turn on system.https "in settings.jsonc".
        # That block exists in the file and has no field anywhere in this
        # editor, so the instruction could not be carried out from the page
        # giving it. Both branches are gone.
        self.assertNotIn("system.https in settings.jsonc", self.html)
        self.assertNotIn("Chromium only, today", self.html)
        # the empty case stays: an empty list alone cannot say whether there
        # are no takes or nothing is mounted
        self.assertIn("'No takes found on mounted storage.'", self.html)


class DeleteStorageAndReasonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_single_delete_sends_storage(self):
        self.assertIn(
            "deleteUrl += '?storage=' + encodeURIComponent(storage);",
            self.html,
        )

    def test_bulk_delete_distinguishes_the_409_from_a_partial_failure(self):
        self.assertIn("if (status === 409) {", self.html)
        self.assertIn("res.recording", self.html)
        self.assertNotIn("Some deletes failed — see console", self.html)


if __name__ == "__main__":
    unittest.main()
