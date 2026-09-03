"""F-211: the web GUI showed the drop/sync warning *state* (a DROP or SYNC
box appears) but never the *count* behind it, even though
populate_values() already publishes drop_frame_count (an alias of
tc_hole_count -- see docs/redis-keys.md) into the same values dict the web
GUI receives verbatim.

Scope, deliberately: only the DROP box gains a count here. The framebuffer
GUI's on-camera boxes are untouched (fixed physical size, no verification
device available in this batch). frames_off_sync has no published numeric
companion today -- the frame-difference number that would latch it
(redis_listener.py's live/final sync analysis) is only ever logged, never
set_value()'d to Redis -- so adding a SYNC count would mean adding new
telemetry to a live recording-time code path with no Pi available to verify
it doesn't regress real takes. That's out of scope for a desk-only commit;
SYNC stays word-only on purpose, and this test checks that it stays that way
rather than growing silently.
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src/module/app/templates/template.html"


class WebGuiDropCountTests(unittest.TestCase):
    def setUp(self):
        self.template_src = TEMPLATE.read_text(encoding="utf-8")
        m = re.search(r"function warningBoxes\(\) \{(.*?)\n    \}", self.template_src, re.S)
        self.assertIsNotNone(m, "warningBoxes() not found")
        self.warning_boxes_body = m.group(1)

    def test_drop_box_reads_the_published_count(self):
        self.assertIn("V.drop_frame_count", self.warning_boxes_body)

    def test_drop_box_falls_back_to_plain_drop_when_count_is_zero(self):
        self.assertIn("'DROP'", self.warning_boxes_body)
        self.assertIn("DROP ${count}", self.warning_boxes_body)

    def test_drop_box_gets_the_small_class_when_it_carries_a_count(self):
        self.assertIn("' small'", self.warning_boxes_body)

    def test_sync_box_intentionally_stays_word_only(self):
        self.assertIn("box('SYNC', 'sync')", self.warning_boxes_body)
        self.assertNotIn("frames_off_sync_count", self.template_src)
        self.assertNotIn("sync_diff", self.template_src)


if __name__ == "__main__":
    unittest.main()
