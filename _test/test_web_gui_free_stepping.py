"""Free stepping must grey the picker only where greying is true.

Free stepping swaps a preset table for a fine grid -- shutter_a.free ships
true with increment 1, so the SHUTTER picker carries ~360 entries -- AND
changes what the setter does with them. For SHUTTER and FPS the setter stops
snapping to the table ("In sync mode, or free-stepping, just accept it
verbatim"; the fps branch clamps to 1..fps_max), so the interior entries are a
sample of a continuum rather than the legal set, and greying them is honest.

It is NOT honest for the other two, which is why they are excluded:

  * WB  -- set_wb() picks the closest entry of wb_steps unconditionally, and
           initialize_wb_cg_rb_array() gives every entry a real cg_rb pair, so
           under wb_free the interior IS the exact legal set.
  * ISO -- set_iso() clamps to the ends and never snaps, in every mode, so
           iso_free changes what is offered, not what is accepted.

Verified in a browser against a harness fed the shipped free-stepping default:
  free on : SHUTTER 361 options / 358 disabled, ends live; FPS 5 / 3 disabled
            ISO 0 disabled, WB 0 disabled
  free off: SHUTTER 7 options / 0 disabled, ISO/WB/FPS 0 disabled
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "template.html"


class FreeSteppingSelectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")
        m = re.search(r"function renderSelectors\(\).*?\n    \}", cls.html, re.S)
        assert m, "renderSelectors not found"
        cls.render = m.group(0)

    def test_shutter_and_fps_are_gated_on_their_free_flags(self):
        self.assertIn("freeStepBounds(steps.shutter_a, truthy(V.shutter_a_free)", self.render)
        self.assertIn("freeStepBounds(steps.fps, truthy(V.fps_free)", self.render)

    def test_wb_and_iso_are_not_gated(self):
        # Greying either would state something the setters do not do.
        for line in self.render.splitlines():
            if "s-wb" in line or "s-iso" in line:
                self.assertNotIn("freeStepBounds", line, line.strip())

    def test_only_the_interior_is_disabled(self):
        m = re.search(r"function freeStepBounds\(.*?\n    \}", self.html, re.S)
        self.assertIsNotNone(m)
        self.assertIn("i > 0 && i < list.length - 1", m.group(0))
        # A two-entry list has no interior to grey.
        self.assertIn("list.length > 2", m.group(0))

    def test_the_live_value_is_carried_into_a_grid_that_lacks_it(self):
        # Toggling free on at a preset 172.8 leaves a 1-degree grid with no
        # such entry; without this the picker reads 1 while the camera runs
        # at 172.8.
        m = re.search(r"function freeStepBounds\(.*?\n    \}", self.html, re.S)
        body = m.group(0)
        self.assertIn("!list.some((v) => Number(v) === live)", body)
        self.assertIn("opts.splice(", body)

    def test_disabled_state_is_part_of_the_fill_cache_key(self):
        # fillSelect skips a repaint when the value list is unchanged; a free
        # toggle can change only which entries are selectable.
        m = re.search(r"function fillSelect\(.*?\n    \}", self.html, re.S)
        self.assertIn("(o.disabled ? '!' : '')", m.group(0))


if __name__ == "__main__":
    unittest.main()
