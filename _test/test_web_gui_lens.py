"""The web GUI's lens surface: the IRIS group between EXP and EI, the EF/CAL
boxes, and the lens picker. The page has no state of its own -- every decision
(hidden / dim / normal) arrives in populate_values() as `iris_state`, tested in
test_simple_gui_lens.py -- so this pins that the page draws from those fields
and follows the same three states. Behaviour in a browser was checked against
a harness driven by the real populate_values() (see the WP4 report).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "src" / "module" / "app" / "templates" / "template.html").read_text(encoding="utf-8")


class WebGuiLensTests(unittest.TestCase):
    def test_iris_sits_between_exp_and_ei_in_the_top_row(self):
        row = HTML[HTML.index('<div id="top-row">'):HTML.index('<div id="stage">')]
        order = [row.index(f'id="{i}"') for i in ("g-exp", "g-iris", "g-iso")]
        self.assertEqual(order, sorted(order))

    def test_the_group_is_hidden_until_the_adapter_is_found(self):
        self.assertRegex(HTML, r'class="group selectable hidden" id="g-iris"')
        self.assertIn("show($('g-iris'), V.iris_state === 'grey' || V.iris_state === 'normal');", HTML)

    def test_grey_is_dim_and_normal_is_not(self):
        self.assertIn("$('g-iris').classList.toggle('dim', V.iris_state === 'grey');", HTML)
        self.assertIn(".group.dim .label, .group.dim .value { color: var(--dim); }", HTML)

    def test_a_tap_on_a_dim_group_says_why_instead_of_commanding(self):
        handler = re.search(r"\$\('s-iris'\)\.addEventListener\('change'.*?\n    \}\);", HTML, re.S).group(0)
        self.assertIn("V.iris_state !== 'normal'", handler)
        self.assertIn("V.iris_grey_reason", handler)
        self.assertIn("cmd('set iris ' + e.target.value)", handler)

    def test_the_picker_offers_the_selected_lenses_own_table(self):
        self.assertIn("iris_steps: 'iris'", HTML)
        self.assertIn("steps.iris", HTML)

    def test_the_lens_picker_uses_the_existing_command_path_and_only_shows_when_found(self):
        self.assertIn("cmd('set lens ' + e.target.value)", HTML)
        self.assertIn("const found = V.iris_state === 'grey' || V.iris_state === 'normal';", HTML)
        self.assertIn('id="s-lens" class="hidden"', HTML)

    def test_ef_and_cal_boxes_follow_lens_ef_state(self):
        self.assertIn("V.lens_ef_state === 'off' ? 'dim' : ''", HTML)
        self.assertIn("'no_lens' || V.lens_ef_state === 'error' ? ' crossed' : ''", HTML)
        self.assertIn("if (V.lens_calibrating) { sys.push(box('CAL'", HTML)

    def test_the_sync_strike_rule_is_untouched_and_ef_has_its_own(self):
        self.assertIn(".box.sync::after {", HTML)
        self.assertIn(".box.crossed::after {", HTML)

    def test_no_autofocus_controls(self):
        for word in ("af_once", "af_mode", "autofocus"):
            self.assertNotIn(word, HTML)


if __name__ == "__main__":
    unittest.main()
