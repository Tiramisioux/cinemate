"""The GPIO-out pane must hide what it says it hides, and show the tone's Hz.

Three operator reports, one shared root cause and one real one.

1. `[hidden]` did nothing. The page hides 15 elements with `el.hidden`, and
   every one of them carries an author `display` rule -- .card is grid, .pill
   and .btn are flex, .action-args is inline-flex. An author display
   declaration beats the UA stylesheet's `[hidden]{display:none}` at any
   specificity, and the file declared no `[hidden]` rule of its own. Measured
   in a browser on this page: a hidden #saveBtn stayed 109px wide, the
   unsaved-count pill 98px, a .card 834px. For GPIO out this meant the REC
   tone's "at [1000] Hz" field rendered on every tally row, where a frequency
   is meaningless -- gpio_output.py never gives a tally pin a PWM object, it
   writes a bare level.

2. The slate tone's frequency had no card, only a per-row widget carried in a
   module-global, so the duty-cycle card showed a pulse width with no pitch
   beside it.

3. Under both: main.py read flat rec_tone_* keys that have not existed since
   c171975e -- see test_rec_tone_config.py.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


class HiddenAttributeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_the_page_declares_its_own_hidden_rule(self):
        self.assertRegex(self.html, r"\[hidden\]\{\s*display:none\s*!important;\s*\}")

    def test_el_hidden_is_still_used_enough_to_need_it(self):
        # If this ever drops to zero the rule above can go too.
        self.assertGreater(len(re.findall(r"\.hidden\s*=", self.html)), 5)


class SlateToneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_the_pitch_is_edited_in_the_row_and_nowhere_else(self):
        # It used to have a card as well, which made one value editable in two
        # places. The row field sits next to the pin it applies to.
        self.assertNotIn('id="f-tonehz"', self.html)
        self.assertIn("var freqInput = document.createElement('input')", self.html)
        self.assertIn("'Tone frequency in hertz'", self.html)

    def test_the_pitch_still_reaches_the_file_from_the_row(self):
        self.assertIn("state.hardware_outputs.rec_tone.frequency_hz = currentToneHz;", self.html)

    def test_duty_cycle_has_no_field_but_is_still_written(self):
        # 50% and staying there, so the card was noise -- but buildState's
        # [data-path] walk cannot produce a key with no field behind it, and a
        # save that omits it would let config_loader's setdefault decide it.
        self.assertNotIn('data-path="hardware_outputs.rec_tone.duty_cycle"', self.html)
        self.assertIn("prevTone.duty_cycle !== undefined", self.html)
        self.assertIn("state.hardware_outputs.rec_tone.duty_cycle = prevTone.duty_cycle;",
                      self.html)

    def test_what_remains_shares_a_container_that_can_be_retired(self):
        self.assertIn('id="toneCards"', self.html)
        self.assertIn("function syncToneCards()", self.html)
        self.assertIn("cards.hidden = !anyTone;", self.html)

    def test_frequency_is_synced_both_ways(self):
        self.assertIn("function syncToneHz(", self.html)
        # Seeded from settings on load, and every tone row's field mirrors it.
        self.assertIn("syncToneHz(loadedHz)", self.html)
        self.assertIn("syncToneHz(v, freqInput)", self.html)
        self.assertIn("syncToneHz(v, card)", self.html)

    def test_removing_the_last_tone_row_retires_the_cards(self):
        # Rows are removed by a generic button that knows nothing about tones.
        self.assertIn("MutationObserver(syncToneCards)", self.html)


if __name__ == "__main__":
    unittest.main()
