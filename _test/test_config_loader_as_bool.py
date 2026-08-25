"""config_loader.as_bool is the one boolean decoder (F-126): it replaces four
independent `_as_bool` implementations (cinepi_controller, dynamic_resolution,
gpio_input, mediator) that genuinely disagreed -- `_as_bool(2)` was `True` in
gpio_input and `False` in the other three -- plus the same
`("1","true","yes","on")` truth-set re-typed standalone in half a dozen more
places (redis_controller, redis_listener, ssd_monitor, usb_monitor,
simple_gui, app/main/events).

This table is the decision record for the two questions the unification
raised:

1. What does a bare number mean? -- Python truthiness (`bool(value)`): 2 is
   True. This matches gpio_input's prior behaviour and config_loader's own
   settings-coercion helper, and no observed settings.jsonc value currently
   sends a non-0/1 number through any of the four call sites, so this is a
   forward-looking decision, not a fix to an observed bug.
2. What does an unrecognised string mean? -- NOT the same as an explicit
   false. It falls back to `default`, same as an absent value, distinguishing
   "the user wrote maybe" from "the user wrote off". This is a behaviour
   change from three of the four originals, which folded "unrecognised" into
   "false" by construction (a failed `in (...)` membership test has no third
   outcome). The recovery console's own standalone `_as_bool` (services/
   cinemate-recovery/cinemate-recovery.py) is deliberately NOT part of this
   unification -- it must import nothing from `module.*` so it can still run
   when the rest of the stack cannot (F-221).
"""

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.config_loader import as_bool, TRUE_VALUES, FALSE_VALUES


class AsBoolDecisionTableTests(unittest.TestCase):
    # (value, default, expected) -- the decision record in executable form.
    CASES = [
        # bool passes through untouched, default is irrelevant.
        (True, False, True),
        (False, True, False),
        # None means "not set": always the caller's default, never a warning.
        (None, False, False),
        (None, True, True),
        # int/float: Python truthiness. 2 is True (decision 1).
        (0, True, False),
        (1, False, True),
        (2, False, True),
        (-1, False, True),
        (0.0, True, False),
        (0.5, False, True),
        # Recognised strings, case- and whitespace-insensitive.
        ("1", False, True),
        ("0", True, False),
        ("true", False, True),
        ("False", True, False),
        ("  YES  ", False, True),
        ("no", True, False),
        ("on", False, True),
        ("Off", True, False),
        # Numeric strings fall back to int() truthiness, same as a bare
        # number -- three call sites (ssd_monitor, redis_listener,
        # redis_controller) already relied on exactly this before the merge.
        ("2", False, True),
        ("-3", False, True),
        ("0", False, False),
        # Empty string: not in either set, not a valid int -- unrecognised.
        ("", True, True),
        ("", False, False),
        # Unrecognised string is NOT coerced to False (decision 2): it is
        # indistinguishable from "not set" and returns default either way.
        ("maybe", True, True),
        ("maybe", False, False),
        ("banana", True, True),
        # Arbitrary object: not a real settings/Redis representation, falls
        # back to default rather than guessing via bool(obj).
        (object(), True, True),
        (object(), False, False),
    ]

    def test_decision_table(self):
        for value, default, expected in self.CASES:
            with self.subTest(value=value, default=default):
                self.assertIs(as_bool(value, default), expected)

    def test_default_parameter_defaults_to_false(self):
        self.assertIs(as_bool(None), False)
        self.assertIs(as_bool("maybe"), False)

    def test_true_and_false_value_sets_are_disjoint(self):
        self.assertEqual(TRUE_VALUES & FALSE_VALUES, set())

    def test_unrecognised_string_does_not_raise_or_warn_at_warning_level(self):
        # This runs on the 12 fps GUI redraw path (simple_gui.py). A stuck
        # bad value must not flood the log at warning level every frame --
        # it logs at debug instead. assertNoLogs would over-assert (debug
        # logging is fine); this just checks no exception and the right
        # answer, and that nothing escalates to WARNING+.
        with self.assertRaises(AssertionError):
            with self.assertLogs(level="WARNING"):
                as_bool("not-a-real-value")


if __name__ == "__main__":
    unittest.main()
