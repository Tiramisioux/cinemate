"""QuadRotaryController's reconnect fix and the state() snapshot the i2c pane reads.

Three things fixed alongside the hardware_probe seesaw-register probe (see
test_i2c_hardware_pane.py and the handbook's working/probing-i2c-peripherals.md):

* A reconnect used to overwrite self.i2c with a brand new busio.I2C() every
  time, leaking the previous handle -- this ran every RECONNECT_INTERVAL
  seconds for as long as a board stayed absent.
* The Seesaw constructor's default reset=True software-resets the board on
  every (re)connect, which stamps on a controller a operator may be turning
  at that moment. reset=False skips that but the constructor still reads
  the HW_ID register itself and raises if the chip is wrong, so an absent
  board is still caught.
* connected/last_error/last_change_epoch are exposed via state() so
  hardware_probe.get_hardware() can report the driver's own answer
  alongside its bus probe, with provenance, instead of the pane silently
  guessing from a bare ACK.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class FakeI2C:
    instances = []

    def __init__(self, scl, sda):
        self.deinited = False
        FakeI2C.instances.append(self)

    def deinit(self):
        self.deinited = True


class FakeEncoder:
    fail = False

    def __init__(self, seesaw, n):
        self._n = n

    @property
    def position(self):
        if FakeEncoder.fail:
            raise OSError(5, "bus glitch")
        return 0


class FakeSwitch:
    def __init__(self, seesaw, pin):
        self.value = True  # not pressed

    def switch_to_input(self, pull):
        pass


class FakePixels:
    def __init__(self, seesaw, n, bpp):
        self.brightness = 0

    def __setitem__(self, idx, value):
        pass


class FakeSeesaw:
    calls = []

    def __init__(self, i2c_bus, addr=0x49, reset=True):
        FakeSeesaw.calls.append({"i2c_bus": i2c_bus, "addr": addr, "reset": reset})


for name in ("board", "busio", "digitalio"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["board"].SCL = "SCL"
sys.modules["board"].SDA = "SDA"
sys.modules["digitalio"].Pull = types.SimpleNamespace(UP=1)

for name in (
    "adafruit_seesaw", "adafruit_seesaw.seesaw", "adafruit_seesaw.rotaryio",
    "adafruit_seesaw.digitalio", "adafruit_seesaw.neopixel",
):
    sys.modules.setdefault(name, types.ModuleType(name))
# sys.modules.setdefault() alone doesn't do what a real `import a.b` does --
# it never sets `a.b` as an attribute of module `a`. quad_rotary_controller.py
# references adafruit_seesaw.seesaw.Seesaw etc. through that attribute chain
# after its own `import adafruit_seesaw.seesaw`, so it has to be wired here too.
# This part is stable module-object wiring, not the swappable fake classes
# below, so it only needs to run once.
for sub in ("seesaw", "rotaryio", "digitalio", "neopixel"):
    setattr(sys.modules["adafruit_seesaw"], sub, sys.modules[f"adafruit_seesaw.{sub}"])


def _install_fakes():
    """(Re)point the stubbed hardware modules' classes at the fakes above.

    Hardware stubs are process-wide (see testing.md): a sibling test file's
    own stub setup -- test_quad_rotary_controller_setting_names.py sets
    Seesaw = object, deliberately never a working fake, since it never
    constructs with enabled=True -- runs at COLLECTION time (import), before
    any test method here runs, and would silently overwrite these. So this
    is called again from setUp() rather than trusted to have survived from
    module import time.
    """
    sys.modules["busio"].I2C = FakeI2C
    sys.modules["adafruit_seesaw.seesaw"].Seesaw = FakeSeesaw
    sys.modules["adafruit_seesaw.rotaryio"].IncrementalEncoder = FakeEncoder
    sys.modules["adafruit_seesaw.digitalio"].DigitalIO = FakeSwitch
    sys.modules["adafruit_seesaw.neopixel"].NeoPixel = FakePixels


_install_fakes()

from module.i2c.quad_rotary_controller import QuadRotaryController


def enabled_settings():
    return {"input_peripherals": {"quad_rotary_controller": {"enabled": True, "encoders": {}}}}


class QuadRotaryReconnectTests(unittest.TestCase):
    def setUp(self):
        _install_fakes()
        FakeI2C.instances = []
        FakeSeesaw.calls = []
        FakeEncoder.fail = False

    def test_seesaw_is_constructed_with_reset_false_so_a_live_board_is_not_reset(self):
        QuadRotaryController(mock.Mock(), enabled_settings())
        self.assertEqual(len(FakeSeesaw.calls), 1)
        self.assertIs(FakeSeesaw.calls[0]["reset"], False)

    def test_a_reconnect_deinits_the_previous_i2c_handle_instead_of_leaking_it(self):
        controller = QuadRotaryController(mock.Mock(), enabled_settings())
        first = controller.i2c
        self.assertFalse(first.deinited)

        controller._initialize_device()  # what RECONNECT_INTERVAL triggers

        self.assertTrue(first.deinited)
        self.assertIsNot(controller.i2c, first)
        self.assertEqual(len(FakeI2C.instances), 2)


class QuadRotaryStateTests(unittest.TestCase):
    def setUp(self):
        _install_fakes()
        FakeI2C.instances = []
        FakeSeesaw.calls = []
        FakeEncoder.fail = False

    def test_state_reports_connected_with_no_error_after_a_clean_init(self):
        controller = QuadRotaryController(mock.Mock(), enabled_settings())
        state = controller.state()
        self.assertEqual(
            state,
            {
                "enabled": True,
                "connected": True,
                "ever_connected": True,
                "last_error": None,
                "last_change_epoch": state["last_change_epoch"],
            },
        )
        self.assertIsInstance(state["last_change_epoch"], float)

    def test_state_reflects_disabled_without_touching_the_bus(self):
        settings = {"input_peripherals": {"quad_rotary_controller": {"enabled": False, "encoders": {}}}}
        controller = QuadRotaryController(mock.Mock(), settings)
        self.assertEqual(FakeSeesaw.calls, [])
        state = controller.state()
        self.assertEqual(state["enabled"], False)
        self.assertEqual(state["connected"], False)
        self.assertEqual(state["ever_connected"], False)

    def test_a_never_connected_board_reports_no_change_epoch(self):
        # connected starts False and _initialize_device's failure path sets
        # it False again -- not a transition, so no epoch is invented.
        original = sys.modules["adafruit_seesaw.seesaw"].Seesaw
        sys.modules["adafruit_seesaw.seesaw"].Seesaw = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no ack"))
        try:
            controller = QuadRotaryController(mock.Mock(), enabled_settings())
        finally:
            sys.modules["adafruit_seesaw.seesaw"].Seesaw = original
        state = controller.state()
        self.assertFalse(state["connected"])
        self.assertFalse(state["ever_connected"])
        self.assertIn("no ack", state["last_error"])
        self.assertIsNone(state["last_change_epoch"])

    def test_a_lost_connection_updates_last_error_and_the_change_epoch(self):
        controller = QuadRotaryController(mock.Mock(), enabled_settings())
        self.assertTrue(controller.state()["connected"])
        epoch_after_connect = controller.state()["last_change_epoch"]

        FakeEncoder.fail = True
        try:
            controller.update()
        finally:
            FakeEncoder.fail = False

        state = controller.state()
        self.assertFalse(state["connected"])
        self.assertIn("bus glitch", state["last_error"])
        self.assertTrue(state["ever_connected"])
        self.assertGreaterEqual(state["last_change_epoch"], epoch_after_connect)


if __name__ == "__main__":
    unittest.main()
