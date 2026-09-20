"""The settings editor's i2c pane -- probe, route and markup.

The pane answers "what is attached right now". It must answer it without
going through any of the drivers, each of which detects presence as a side
effect of a full initialisation: grove_base_hat_adc raises SystemExit from
every read path, and the seesaw and SSD1306 drivers sleep 0.1 s and then
reset/blank a device that may be in use.

The addresses are the ones the existing code already probes -- 0x08
(analog_controls), 0x49 (quad_rotary_controller), 0x34 (ssd_monitor) -- so
those are pinned here against their sources. The SSD1306 pair is the one set
this repo never states anywhere, which is exactly why it lives in a table.
"""

import re
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

import flask

from module.app import hardware_probe
from module.app.settings_editor import settings_editor_bp

TEMPLATE = ROOT / "src" / "module" / "app" / "templates" / "settings_editor.html"


def _make_app(settings=None, peripherals=None):
    app = flask.Flask(__name__)
    app.register_blueprint(settings_editor_bp)
    app.config["SETTINGS"] = settings if settings is not None else {}
    app.config["PERIPHERALS"] = peripherals or {}
    return app


class ProbeSafetyTests(unittest.TestCase):
    def test_absent_i2c_module_reports_nothing_attached_rather_than_raising(self):
        # A desktop checkout has no smbus2. The pane must render, not 500.
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: None
        try:
            ok, err = hardware_probe._ack(1, 0x08)
            self.assertFalse(ok)
            self.assertIsNone(err)
            devices = hardware_probe.detect_devices()
        finally:
            hardware_probe._smbus = original
        self.assertTrue(devices)
        self.assertTrue(all(d["present"] is False for d in devices))

    def test_a_refused_address_is_absence_not_an_error(self):
        class Bus:
            def __init__(self, _n): self.closed = False
            def read_byte(self, _a): raise OSError(121, "no ack")
            def close(self): self.closed = True

        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: types.SimpleNamespace(SMBus=Bus)
        try:
            ok, err = hardware_probe._ack(1, 0x08)
            self.assertFalse(ok)
            self.assertEqual(err, 121)
        finally:
            hardware_probe._smbus = original

    def test_the_bus_handle_is_closed_even_when_nothing_answers(self):
        # analog_controls closes only on the success path, leaking a handle
        # every time the HAT is absent.
        opened = []

        class Bus:
            def __init__(self, _n): opened.append(self); self.closed = False
            def read_byte(self, _a): raise OSError("no ack")
            def close(self): self.closed = True

        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: types.SimpleNamespace(SMBus=Bus)
        try:
            hardware_probe._ack(1, 0x08)
        finally:
            hardware_probe._smbus = original
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].closed)

    def test_probing_never_writes_to_the_bus_except_the_documented_seesaw_read(self):
        # Every bare-ACK device (grove, rtc, oled, cfe_hat) must still see no
        # write at all. The quad rotary encoder is the one documented
        # exception -- see hardware_probe's module docstring and
        # _seesaw_present -- so this pins that it writes exactly the
        # STATUS/HW_ID register address, once, and nothing else.
        writes = []
        register_writes = []

        class Bus:
            def __init__(self, _n): pass
            def read_byte(self, _a): return 0x87  # a known seesaw hw id
            def write_byte(self, *a): writes.append(a)
            def write_i2c_block_data(self, addr, register, data):
                register_writes.append((addr, register, tuple(data)))
            def close(self): pass

        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: types.SimpleNamespace(SMBus=Bus)
        try:
            hardware_probe.detect_devices({"width": 128, "height": 64})
        finally:
            hardware_probe._smbus = original
        self.assertEqual(writes, [])
        self.assertEqual(register_writes, [(0x49, 0x00, (0x01,))])


class ProbeErrorTests(unittest.TestCase):
    """_probe_error's errno -> name/hint mapping, rendered in the pane's card help."""

    def test_a_nack_is_named_and_hinted(self):
        err = hardware_probe._probe_error(121)  # EREMOTEIO -- the seesaw's own NACK, measured on the rig
        self.assertEqual(err, {"errno": 121, "name": "EREMOTEIO", "hint": "not found (NACK)"})

    def test_enxio_is_the_same_nobody_home_hint_as_eremoteio(self):
        import errno
        err = hardware_probe._probe_error(errno.ENXIO)
        self.assertEqual(err["hint"], "not found (NACK)")

    def test_a_bus_timeout_is_distinguished_from_a_plain_nack(self):
        import errno
        err = hardware_probe._probe_error(errno.ETIMEDOUT)
        self.assertEqual(err["name"], "ETIMEDOUT")
        self.assertIn("timeout", err["hint"])

    def test_a_kernel_owned_address_is_named_busy_not_absent(self):
        import errno
        err = hardware_probe._probe_error(errno.EBUSY)
        self.assertIn("busy", err["hint"])

    def test_no_error_is_none_not_an_empty_dict(self):
        self.assertIsNone(hardware_probe._probe_error(None))

    def test_absence_carries_an_errno_the_pane_can_render(self):
        class Bus:
            def __init__(self, _n): pass
            def read_byte(self, _a): raise OSError(121, "remote i/o error")
            def write_i2c_block_data(self, *a): raise OSError(121, "remote i/o error")
            def close(self): pass

        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: types.SimpleNamespace(SMBus=Bus)
        try:
            devices = hardware_probe.detect_devices()
        finally:
            hardware_probe._smbus = original
        grove = next(d for d in devices if d["key"] == "grove")
        self.assertFalse(grove["present"])
        self.assertEqual(grove["probe_error"], {"errno": 121, "name": "EREMOTEIO", "hint": "not found (NACK)"})


class SeesawProbeTests(unittest.TestCase):
    """_seesaw_present -- the register read that replaces the bare ACK for 0x49."""

    def _bus_answering(self, hw_id, on_read_raise=None):
        calls = {"writes": [], "reads": 0}

        class Bus:
            def __init__(self, _n): pass
            def write_i2c_block_data(self, addr, register, data):
                calls["writes"].append((addr, register, tuple(data)))
            def read_byte(self, _a):
                calls["reads"] += 1
                if on_read_raise is not None:
                    raise on_read_raise
                return hw_id
            def close(self): pass

        return types.SimpleNamespace(SMBus=Bus), calls

    def test_a_recognised_attiny8xx_id_is_present(self):
        smbus, calls = self._bus_answering(0x87)
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: smbus
        try:
            present, hw_id, err = hardware_probe._seesaw_present(1, 0x49)
        finally:
            hardware_probe._smbus = original
        self.assertTrue(present)
        self.assertEqual(hw_id, 0x87)
        self.assertIsNone(err)
        self.assertEqual(calls["writes"], [(0x49, 0x00, (0x01,))])

    def test_a_recognised_samd09_id_is_present(self):
        smbus, _ = self._bus_answering(0x55)
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: smbus
        try:
            present, hw_id, err = hardware_probe._seesaw_present(1, 0x49)
        finally:
            hardware_probe._smbus = original
        self.assertTrue(present)
        self.assertEqual(hw_id, 0x55)

    def test_a_zero_id_is_not_accepted_as_presence(self):
        # Measured on the rig: 2 of 40 successful reads against a present,
        # working board came back 0x00, not a real id. "No exception" alone
        # must not be read as presence.
        smbus, _ = self._bus_answering(0x00)
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: smbus
        try:
            present, hw_id, err = hardware_probe._seesaw_present(1, 0x49)
        finally:
            hardware_probe._smbus = original
        self.assertFalse(present)
        self.assertEqual(hw_id, 0x00)
        self.assertIsNone(err)

    def test_an_unrecognised_id_is_not_accepted_as_presence(self):
        smbus, _ = self._bus_answering(0x42)
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: smbus
        try:
            present, hw_id, err = hardware_probe._seesaw_present(1, 0x49)
        finally:
            hardware_probe._smbus = original
        self.assertFalse(present)
        self.assertEqual(hw_id, 0x42)

    def test_a_nack_is_absence_with_the_errno_carried(self):
        smbus, _ = self._bus_answering(0x87, on_read_raise=OSError(121, "remote i/o error"))
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: smbus
        try:
            present, hw_id, err = hardware_probe._seesaw_present(1, 0x49)
        finally:
            hardware_probe._smbus = original
        self.assertFalse(present)
        self.assertIsNone(hw_id)
        self.assertEqual(err, 121)

    def test_absent_smbus_reports_absence_with_no_errno_and_no_bus_touch(self):
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: None
        try:
            present, hw_id, err = hardware_probe._seesaw_present(1, 0x49)
        finally:
            hardware_probe._smbus = original
        self.assertFalse(present)
        self.assertIsNone(hw_id)
        self.assertIsNone(err)


class DetectQuadRotaryTests(unittest.TestCase):
    """_detect_quad_rotary -- the driver-confirmed / probed preference order."""

    SPEC = {"key": "quad_rotary", "name": "Adafruit quad rotary encoder",
            "hint": "four dials and push buttons on one board", "addresses": (0x49,)}

    def test_driver_connected_short_circuits_the_bus_probe_entirely(self):
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: (_ for _ in ()).throw(AssertionError("must not touch the bus"))
        try:
            entry = hardware_probe._detect_quad_rotary(
                self.SPEC,
                {"enabled": True, "connected": True, "ever_connected": True,
                 "last_error": None, "last_change_epoch": 1.0},
            )
        finally:
            hardware_probe._smbus = original
        self.assertTrue(entry["present"])
        self.assertEqual(entry["provenance"], "driver-confirmed")
        self.assertEqual(entry["address"], 0x49)
        self.assertIsNone(entry["probe_error"])

    def test_driver_disabled_falls_back_to_the_seesaw_probe(self):
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: None
        try:
            entry = hardware_probe._detect_quad_rotary(
                self.SPEC, {"enabled": False, "connected": False, "ever_connected": False,
                             "last_error": None, "last_change_epoch": None},
            )
        finally:
            hardware_probe._smbus = original
        self.assertEqual(entry["provenance"], "probed")
        self.assertFalse(entry["present"])
        # the driver's own state is still reported, just not trusted for presence
        self.assertEqual(entry["driver"]["enabled"], False)

    def test_driver_enabled_but_not_yet_connected_falls_back_to_the_seesaw_probe(self):
        # A driver that never connected has no opinion worth trusting over a
        # fresh probe -- e.g. still retrying its first RECONNECT_INTERVAL.
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: None
        try:
            entry = hardware_probe._detect_quad_rotary(
                self.SPEC, {"enabled": True, "connected": False, "ever_connected": False,
                             "last_error": "no ack", "last_change_epoch": None},
            )
        finally:
            hardware_probe._smbus = original
        self.assertEqual(entry["provenance"], "probed")

    def test_no_driver_registered_falls_back_to_the_seesaw_probe(self):
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: None
        try:
            entry = hardware_probe._detect_quad_rotary(self.SPEC, None)
        finally:
            hardware_probe._smbus = original
        self.assertEqual(entry["provenance"], "probed")
        self.assertIsNone(entry["driver"])


class AddressTableTests(unittest.TestCase):
    def test_addresses_match_the_probes_already_in_the_codebase(self):
        by_key = {d["key"]: d["addresses"] for d in hardware_probe.DEVICES}
        self.assertEqual(by_key["grove"], (0x08,))        # analog_controls.py
        self.assertEqual(by_key["quad_rotary"], (0x49,))  # quad_rotary_controller.py

    def test_the_cfe_hat_is_present_only_when_it_answers_on_i2c(self):
        # SsdMonitor also accepts the Pi 5 PCIe bridge node, which every Pi 5
        # has whether or not a hat is fitted -- that is a bridge test, not a
        # hat test, so this pane does not use it.
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: None
        try:
            cfe = hardware_probe.detect_cfe_hat()
        finally:
            hardware_probe._smbus = original
        self.assertFalse(cfe["present"])
        self.assertIsNone(cfe["via"])
        self.assertNotIn("PCIE", dir(hardware_probe))

    def test_the_bus_is_scoped_because_0x34_is_two_different_devices(self):
        # 0x34 is the CFE Hat on bus 1 and the StarlightEye IR-cut filter on
        # the camera buses; an unscoped sweep would report one as the other.
        self.assertEqual(hardware_probe.I2C_BUS, 1)

    def test_display_types_are_a_table_so_new_ones_are_data(self):
        self.assertTrue(hardware_probe.OLED_TYPES)
        for entry in hardware_probe.OLED_TYPES:
            self.assertIn("address", entry)
            self.assertIn("controllers", entry)
            self.assertIn("SSD1309", entry["controllers"])


class OledGeometryTests(unittest.TestCase):
    def _found_at(self, address):
        class Bus:
            def __init__(self, _n): pass
            def read_byte(self, a):
                if a != address: raise OSError("no ack")
                return 0
            def close(self): pass
        return types.SimpleNamespace(SMBus=Bus)

    def test_geometry_comes_from_settings_and_says_so(self):
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: self._found_at(0x3C)
        try:
            entry = hardware_probe.detect_oled({"enabled": True, "width": 128, "height": 32})
        finally:
            hardware_probe._smbus = original
        self.assertTrue(entry["present"])
        self.assertEqual(entry["address"], 0x3C)
        # the two parts share an address and neither has an ID register, so
        # the pane names both rather than guessing
        self.assertEqual(entry["controller"], "SSD1306 or SSD1309")
        self.assertEqual((entry["width"], entry["height"]), (128, 32))
        # a display cannot be asked its own size -- the pane must not imply it was
        self.assertEqual(entry["geometry_source"], "settings")

    def test_the_alternate_address_is_recognised_too(self):
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: self._found_at(0x3D)
        try:
            entry = hardware_probe.detect_oled({})
        finally:
            hardware_probe._smbus = original
        self.assertTrue(entry["present"])
        self.assertEqual(entry["address"], 0x3D)

    def test_geometry_defaults_hold_when_settings_are_empty(self):
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: None
        try:
            entry = hardware_probe.detect_oled({})
        finally:
            hardware_probe._smbus = original
        self.assertEqual((entry["width"], entry["height"]), (128, 64))


class RtcTests(unittest.TestCase):
    def test_a_failed_hwclock_is_reported_rather_than_swallowed(self):
        # `set rtc time` runs os.system and discards the exit status, so it
        # logs success with no RTC attached. This must not.
        original = hardware_probe._run
        hardware_probe._run = lambda argv, timeout=5.0: types.SimpleNamespace(
            returncode=1, stdout="", stderr="hwclock: cannot access the Hardware Clock")
        try:
            result = hardware_probe.sync_rtc_to_system()
        finally:
            hardware_probe._run = original
        self.assertFalse(result["ok"])
        self.assertIn("Hardware Clock", result["message"])

    def test_a_sudo_password_prompt_is_named_for_what_it_is(self):
        original = hardware_probe._run
        hardware_probe._run = lambda argv, timeout=5.0: types.SimpleNamespace(
            returncode=1, stdout="", stderr="sudo: a password is required")
        try:
            result = hardware_probe.sync_rtc_to_system()
        finally:
            hardware_probe._run = original
        self.assertFalse(result["ok"])
        self.assertIn("sudoers", result["message"])

    def test_sync_runs_sudo_non_interactively(self):
        # without -n a machine lacking a NOPASSWD rule blocks on a console
        # prompt until the request times out
        seen = []
        original = hardware_probe._run
        hardware_probe._run = lambda argv, timeout=5.0: (
            seen.append(argv) or types.SimpleNamespace(returncode=0, stdout="", stderr=""))
        try:
            hardware_probe.sync_rtc_to_system()
        finally:
            hardware_probe._run = original
        self.assertIn(["sudo", "-n", "hwclock", "--systohc"], seen)

    def test_sync_reads_the_clock_back_to_verify(self):
        calls = []
        original = hardware_probe._run

        def fake(argv, timeout=5.0):
            calls.append(argv)
            if argv[-1] == "--systohc":
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")
            return types.SimpleNamespace(returncode=0, stdout="2026-09-05 21:00:00", stderr="")

        hardware_probe._run = fake
        try:
            result = hardware_probe.sync_rtc_to_system()
        finally:
            hardware_probe._run = original
        self.assertTrue(result["ok"])
        self.assertTrue(result["rtc"]["ok"])
        self.assertTrue(any("-r" in c for c in calls), "the clock was never read back")


class HardwareRouteTests(unittest.TestCase):
    def test_the_endpoint_reports_every_device_and_both_clocks(self):
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: None
        try:
            res = _make_app({"output_peripherals": {"oled": {"width": 128, "height": 32}}}) \
                .test_client().get("/settings-editor/api/hardware")
            body = res.get_json()
        finally:
            hardware_probe._smbus = original

        self.assertEqual(res.status_code, 200)
        self.assertTrue(body["ok"])
        keys = {d["key"] for d in body["devices"]}
        self.assertEqual(keys, {"grove", "quad_rotary", "rtc", "oled", "cfe_hat"})
        # both carry an epoch so the page can tick between polls rather than
        # forking hwclock once a second
        self.assertIn("epoch", body["clocks"]["system"])
        self.assertIn("epoch", body["clocks"]["rtc"])

    def test_oled_geometry_is_taken_from_the_running_settings(self):
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: None
        try:
            body = _make_app({"output_peripherals": {"oled": {"width": 64, "height": 48}}}) \
                .test_client().get("/settings-editor/api/hardware").get_json()
        finally:
            hardware_probe._smbus = original
        oled = next(d for d in body["devices"] if d["key"] == "oled")
        self.assertEqual((oled["width"], oled["height"]), (64, 48))

    def test_a_failed_sync_answers_500_rather_than_a_cheerful_200(self):
        original = hardware_probe.sync_rtc_to_system
        hardware_probe.sync_rtc_to_system = lambda: {
            "ok": False, "message": "no RTC", "rtc": {"ok": False, "time": None, "error": "x"}}
        try:
            res = _make_app().test_client().post("/settings-editor/api/hardware/rtc/sync")
        finally:
            hardware_probe.sync_rtc_to_system = original
        self.assertEqual(res.status_code, 500)
        self.assertFalse(res.get_json()["ok"])

    def test_a_connected_driver_answers_present_with_no_seesaw_register_write(self):
        # app.config["PERIPHERALS"]["quad_rotary"] is the running controller
        # instance (or None) -- create_app publishes it, main.py passes it.
        # When it reports connected, the route must use that answer directly
        # rather than issuing the seesaw register probe of its own -- the
        # other bare-ACK devices in the same response still probe normally.
        class FakeController:
            def state(self):
                return {"enabled": True, "connected": True, "ever_connected": True,
                         "last_error": None, "last_change_epoch": 123.0}

        class Bus:
            def __init__(self, _n): pass
            def read_byte(self, _a): raise OSError(121, "no ack")
            def write_i2c_block_data(self, *a):
                raise AssertionError("driver-confirmed must not touch the seesaw")
            def close(self): pass

        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: types.SimpleNamespace(SMBus=Bus)
        try:
            body = _make_app(peripherals={"quad_rotary": FakeController()}) \
                .test_client().get("/settings-editor/api/hardware").get_json()
        finally:
            hardware_probe._smbus = original
        quad = next(d for d in body["devices"] if d["key"] == "quad_rotary")
        self.assertTrue(quad["present"])
        self.assertEqual(quad["provenance"], "driver-confirmed")
        self.assertEqual(quad["driver"]["connected"], True)
        # the other devices in the same response are unaffected -- still probed
        grove = next(d for d in body["devices"] if d["key"] == "grove")
        self.assertFalse(grove["present"])

    def test_no_registered_driver_falls_back_to_the_seesaw_probe(self):
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: None  # off-hardware: must render, not 500
        try:
            body = _make_app().test_client().get("/settings-editor/api/hardware").get_json()
        finally:
            hardware_probe._smbus = original
        quad = next(d for d in body["devices"] if d["key"] == "quad_rotary")
        self.assertFalse(quad["present"])
        self.assertEqual(quad["provenance"], "probed")
        self.assertIsNone(quad["driver"])


class PaneMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text(encoding="utf-8")

    def test_the_pane_sits_between_config_and_settings(self):
        order = [m for m in ("config", "i2c", "settings")]
        positions = [self.html.index(f'data-page-tab="{p}"') for p in order]
        self.assertEqual(positions, sorted(positions))

    def test_the_pane_edits_no_file_so_the_save_controls_stay_hidden(self):
        # a page absent from this predicate silently offers Save/Revert for
        # settings.jsonc, which this pane does not edit
        self.assertIn("activePage === 'i2c'", self.html)

    def test_the_pane_is_reprobed_on_every_arrival(self):
        self.assertIn("if (page === 'i2c'){ i2cRefresh(); i2cStartTicking(); }", self.html)

    def test_the_clocks_stop_ticking_when_the_pane_is_left(self):
        # a 1 Hz interval must not outlive the pane that shows it
        self.assertIn("else { i2cStopTicking(); }", self.html)

    def test_ticking_uses_the_cameras_timezone_not_the_browsers(self):
        # the offset is recovered from the camera's own formatted string, so a
        # browser in another zone still reads the camera's wall clock
        fn = re.search(r"function i2cAnchor\(epoch, display\)\{(.*?)\n  \}",
                       self.html, re.S).group(1)
        self.assertIn("offsetMs", fn)
        self.assertIn("Date.parse", fn)

    def test_the_pane_uses_cards_so_search_cannot_empty_it(self):
        # updateGroupVisibility hides any group with no .card/.actionrow/.cliprow
        # descendant as soon as the search box has text
        self.assertIn('<div class="cards" id="i2cDeviceList"></div>', self.html)
        self.assertIn('id="i2cClockCards"', self.html)

    def test_a_pi5_onboard_clock_is_not_reported_as_a_fault(self):
        # no DS3231 on the bus but /dev/rtc present is the normal Pi 5 case,
        # and the two clocks below it will plainly be working
        fn = re.search(r"function i2cDeviceDetail\(d\)\{(.*?)\n  \}", self.html, re.S).group(1)
        self.assertIn("d.key === 'rtc' && d.kernel_device", fn)
        self.assertIn("only needed on a Pi 4", fn)

    def test_the_rail_group_carries_no_nav_links(self):
        # the scrollspy's section list is global, so links here would compete
        # with the settings rail's for the active-link computation
        rail = self.html[self.html.index('<div class="rail-group" data-page="i2c">'):]
        rail = rail[:rail.index("</div>")]
        self.assertNotIn("data-nav", rail)

    def test_a_driver_confirmed_reading_says_no_probe_was_issued(self):
        # the pane must say WHY a present reading needed no bus traffic,
        # rather than rendering it identically to a probed one
        fn = re.search(r"function i2cDeviceDetail\(d\)\{(.*?)\n  \}", self.html, re.S).group(1)
        self.assertIn("driver-confirmed", fn)
        self.assertIn("no bus probe issued", fn)

    def test_an_absent_reading_carries_the_probe_error_hint(self):
        # NACK/timeout/busy/no-bus render differently -- not just "not found"
        fn = re.search(r"function i2cDeviceDetail\(d\)\{(.*?)\n  \}", self.html, re.S).group(1)
        self.assertIn("i2cProbeErrorHint", fn)

    def test_the_driver_state_is_a_separate_line_never_blended_into_present(self):
        # handbook rule: report provenance beside the value, never blend a
        # driver flag into "present" itself -- so this is its own function
        # and its own <p>, not folded into i2cDeviceDetail's return value
        detail_fn = re.search(r"function i2cDeviceDetail\(d\)\{(.*?)\n  \}", self.html, re.S).group(1)
        self.assertNotIn("d.driver", detail_fn)
        driver_fn = re.search(r"function i2cDriverDetail\(d\)\{(.*?)\n  \}", self.html, re.S).group(1)
        self.assertIn("never connected", driver_fn)
        self.assertIn("lost", driver_fn)
        self.assertIn("connected", driver_fn)
        self.assertIn("driverLine", self.html)


if __name__ == "__main__":
    unittest.main()
