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


def _make_app(settings=None):
    app = flask.Flask(__name__)
    app.register_blueprint(settings_editor_bp)
    app.config["SETTINGS"] = settings if settings is not None else {}
    return app


class ProbeSafetyTests(unittest.TestCase):
    def test_absent_i2c_module_reports_nothing_attached_rather_than_raising(self):
        # A desktop checkout has no smbus2. The pane must render, not 500.
        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: None
        try:
            self.assertFalse(hardware_probe._ack(1, 0x08))
            devices = hardware_probe.detect_devices()
        finally:
            hardware_probe._smbus = original
        self.assertTrue(devices)
        self.assertTrue(all(d["present"] is False for d in devices))

    def test_a_refused_address_is_absence_not_an_error(self):
        class Bus:
            def __init__(self, _n): self.closed = False
            def read_byte(self, _a): raise OSError("no ack")
            def close(self): self.closed = True

        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: types.SimpleNamespace(SMBus=Bus)
        try:
            self.assertFalse(hardware_probe._ack(1, 0x08))
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

    def test_probing_never_writes_to_the_bus(self):
        writes = []

        class Bus:
            def __init__(self, _n): pass
            def read_byte(self, _a): return 0
            def write_byte(self, *a): writes.append(a)
            def close(self): pass

        original = hardware_probe._smbus
        hardware_probe._smbus = lambda: types.SimpleNamespace(SMBus=Bus)
        try:
            hardware_probe.detect_devices({"width": 128, "height": 64})
        finally:
            hardware_probe._smbus = original
        self.assertEqual(writes, [])


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


if __name__ == "__main__":
    unittest.main()
