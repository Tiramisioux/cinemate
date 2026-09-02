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

    def test_frequency_has_a_card_bound_to_the_settings_key(self):
        self.assertIn('id="f-tonehz"', self.html)
        self.assertIn('data-path="hardware_outputs.rec_tone.frequency_hz"', self.html)

    def test_frequency_card_is_labelled_in_hertz(self):
        m = re.search(r'id="f-tonehz".*?</div>', self.html, re.S)
        self.assertIsNotNone(m)
        self.assertIn("Hz", m.group(0))

    def test_duty_cycle_card_still_bound(self):
        self.assertIn('data-path="hardware_outputs.rec_tone.duty_cycle"', self.html)

    def test_both_tone_cards_share_a_container_that_can_be_retired(self):
        self.assertIn('id="toneCards"', self.html)
        self.assertIn("function syncToneCards()", self.html)
        self.assertIn("cards.hidden = !anyTone;", self.html)

    def test_frequency_is_synced_both_ways(self):
        self.assertIn("function syncToneHz(", self.html)
        # The card seeds from settings, and the row fields mirror it.
        self.assertIn("syncToneHz(loadedHz)", self.html)
        self.assertIn("syncToneHz(v, freqInput)", self.html)
        self.assertIn("syncToneHz(v, card)", self.html)

    def test_removing_the_last_tone_row_retires_the_cards(self):
        # Rows are removed by a generic button that knows nothing about tones.
        self.assertIn("MutationObserver(syncToneCards)", self.html)


if __name__ == "__main__":
    unittest.main()
