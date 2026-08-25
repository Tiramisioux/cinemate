"""F-285. AnalogControls bypasses CommandExecutor._dispatch_lock entirely
and its debounce (new_X != last_X) compares against its own last-dispatched
value, not the live system value -- so it has no way to know an explicit
`set` command changed the parameter since its last write. Reproduced on
hardware: a stationary pot re-clobbered an explicit `set iso 6400` within a
second, with no error surfaced anywhere.

Fix, covered here:
- _has_moved() gates re-dispatch on genuine ADC movement since the last
  dispatch, not on whether the mapped step value differs from the pot's
  stale cache.
- _dispatch() takes the same lock CommandExecutor uses, if one is provided.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for name in ("smbus2", "grove", "grove.i2c"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["grove.i2c"].Bus = object
sys.modules["smbus2"].SMBus = object
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.analog_controls import AnalogControls


def make_analog_controls(dispatch_lock=None):
    ac = AnalogControls.__new__(AnalogControls)
    ac.cinepi_controller = mock.Mock()
    ac.dispatch_lock = dispatch_lock
    ac._last_dispatch_raw = {}
    return ac


class HasMovedTests(unittest.TestCase):
    def test_first_reading_always_allowed(self):
        ac = make_analog_controls()
        self.assertTrue(ac._has_moved("iso", 512))

    def test_stationary_reading_after_dispatch_is_blocked(self):
        ac = make_analog_controls()
        ac._record_dispatch("iso", 512)
        self.assertFalse(ac._has_moved("iso", 512))
        # Noise within the threshold still counts as stationary.
        self.assertFalse(ac._has_moved("iso", 513))
        self.assertFalse(ac._has_moved("iso", 514))

    def test_genuine_movement_is_allowed(self):
        ac = make_analog_controls()
        ac._record_dispatch("iso", 512)
        self.assertTrue(ac._has_moved("iso", 512 + AnalogControls.MOVEMENT_THRESHOLD_RAW))
        self.assertTrue(ac._has_moved("iso", 512 - AnalogControls.MOVEMENT_THRESHOLD_RAW))

    def test_none_reading_never_moved(self):
        ac = make_analog_controls()
        self.assertFalse(ac._has_moved("iso", None))

    def test_parameters_track_independently(self):
        ac = make_analog_controls()
        ac._record_dispatch("iso", 512)
        # A different parameter with no dispatch history yet is unaffected.
        self.assertTrue(ac._has_moved("fps", 512))


class IsolatedStationaryPotTests(unittest.TestCase):
    """The exact hardware symptom: pot sits at a fixed position, something
    else changes the live value, the pot's next poll must not clobber it."""

    def test_stationary_pot_does_not_redispatch_after_last_iso_goes_stale(self):
        ac = make_analog_controls()
        ac._record_dispatch("iso", 512)
        ac.last_iso = 800  # the pot's own last-dispatched mapped value

        # Simulate an explicit `set iso 6400` changing the live system
        # value without the pot's own bookkeeping knowing about it -- the
        # bug this replicates is that a *stale* last_iso alone used to be
        # enough to trigger a re-dispatch on the pot's very next poll, even
        # with the raw ADC reading completely unchanged.
        ac.last_iso = None  # forces new_iso != last_iso if the gate is absent

        self.assertFalse(ac._has_moved("iso", 512))
        # A caller checking `new_iso != self.last_iso and self._has_moved(...)`
        # will not dispatch here even though the first half of that
        # condition is true -- the movement gate is what closes the bug.


class DispatchLockTests(unittest.TestCase):
    def test_dispatch_takes_the_provided_lock(self):
        lock = mock.MagicMock()
        ac = make_analog_controls(dispatch_lock=lock)

        ac._dispatch("iso", 800)

        lock.__enter__.assert_called_once()
        lock.__exit__.assert_called_once()
        ac.cinepi_controller.set_iso.assert_called_once_with(800)

    def test_dispatch_without_a_lock_still_works(self):
        ac = make_analog_controls(dispatch_lock=None)
        ac._dispatch("iso", 800)
        ac.cinepi_controller.set_iso.assert_called_once_with(800)


if __name__ == "__main__":
    unittest.main()
