"""Hotspot credential ladder, state files and reconciliation.

Covers the hotspot credential ladder and write discipline documented in
docs/recovery-console.md. Every rung is exercised, including the ones that
only fire when something else is already broken -- a fallback nobody has
run is not a fallback.

No hardware and no subprocess: nmcli and systemctl are faked.
"""

import json
import stat
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from module.wifi_hotspot import (  # noqa: E402
    DEFAULT_PASS,
    DEFAULT_SSID,
    RUNG_CACHE,
    RUNG_DEFAULTS,
    RUNG_SETTINGS,
    SETTINGS_ABSENT,
    SETTINGS_OK,
    SETTINGS_UNPARSEABLE,
    WiFiHotspotManager,
    atomic_write_bytes,
    hotspot_service_active,
    probe_settings,
    read_last_good,
    resolve_credentials,
    split_terse,
    terse_value,
    write_last_good,
    write_state,
)

VALID = """{
  // a comment, because settings.jsonc is JSONC
  "system": {
    "wifi_hotspot": {
      "name": "MyCamera",
      "password": "supersecret",
      "enabled": true,
    }
  }
}
"""

BROKEN = """{
  "system": {
    "wifi_hotspot": {
      "name": "MyCamera"
      "password": "supersecret"
    }
  }
}
"""


class LadderTestCase(unittest.TestCase):
    """Gives each test an isolated settings file, cache and state file."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.settings = self.tmp / "settings.jsonc"
        self.cache = self.tmp / "state" / "hotspot.last-good.json"
        self.state = self.tmp / "state" / "hotspot.state"
        self.addCleanup(self._tmp.cleanup)

    def write_settings(self, text):
        self.settings.write_text(text, encoding="utf-8")

    def seed_cache(self, ssid="CachedNet", password="cachedpass", enabled=True):
        write_last_good(ssid, password, enabled, self.cache)

    def resolve(self, **kw):
        return resolve_credentials(self.settings, self.cache, **kw)


# ---------------------------------------------------------------------------
# 4.2 rung 1 -- settings.jsonc parses
# ---------------------------------------------------------------------------

class RungOneSettingsTests(LadderTestCase):
    def test_valid_settings_win(self):
        self.write_settings(VALID)
        creds = self.resolve()
        self.assertEqual(creds.rung, RUNG_SETTINGS)
        self.assertEqual(creds.ssid, "MyCamera")
        self.assertEqual(creds.password, "supersecret")
        self.assertTrue(creds.enabled)
        self.assertEqual(creds.settings_status, SETTINGS_OK)

    def test_jsonc_comments_and_trailing_commas_are_not_corruption(self):
        # The whole point of F4: annotating settings.jsonc must not rename
        # the operator's network.
        self.write_settings(VALID)
        self.assertEqual(self.resolve().ssid, "MyCamera")

    def test_rung_one_refreshes_the_cache(self):
        self.write_settings(VALID)
        self.resolve()
        self.assertEqual(read_last_good(self.cache), ("MyCamera", "supersecret", True))

    def test_persist_false_does_not_write_the_cache(self):
        self.write_settings(VALID)
        self.resolve(persist=False)
        self.assertFalse(self.cache.exists())

    def test_missing_wifi_block_uses_documented_defaults(self):
        self.write_settings('{"system": {}}')
        creds = self.resolve()
        self.assertEqual(creds.rung, RUNG_SETTINGS)
        self.assertEqual(creds.ssid, DEFAULT_SSID)
        self.assertEqual(creds.password, DEFAULT_PASS)

    def test_short_password_falls_back_to_default_within_rung_one(self):
        # NetworkManager rejects < 8 chars. Correcting it is not a rung change.
        self.write_settings(
            '{"system": {"wifi_hotspot": {"name": "Cam", "password": "abc"}}}'
        )
        creds = self.resolve()
        self.assertEqual(creds.rung, RUNG_SETTINGS)
        self.assertEqual(creds.ssid, "Cam")
        self.assertEqual(creds.password, DEFAULT_PASS)

    def test_enabled_false_is_honoured_and_cached(self):
        self.write_settings(
            '{"system": {"wifi_hotspot": {"name": "Cam", "password": "longenough",'
            ' "enabled": false}}}'
        )
        creds = self.resolve()
        self.assertFalse(creds.enabled)
        self.assertEqual(read_last_good(self.cache), ("Cam", "longenough", False))


# ---------------------------------------------------------------------------
# 4.2 rung 2 -- settings.jsonc does not parse, cache is usable
# ---------------------------------------------------------------------------

class RungTwoCacheTests(LadderTestCase):
    def test_broken_settings_fall_back_to_cache_not_cinepi(self):
        self.seed_cache()
        self.write_settings(BROKEN)
        creds = self.resolve()
        self.assertEqual(creds.rung, RUNG_CACHE)
        self.assertEqual(creds.ssid, "CachedNet")
        self.assertEqual(creds.password, "cachedpass")
        self.assertNotEqual(creds.ssid, DEFAULT_SSID)

    def test_reason_names_the_actual_parse_error(self):
        self.seed_cache()
        self.write_settings(BROKEN)
        creds = self.resolve()
        self.assertEqual(creds.settings_status, SETTINGS_UNPARSEABLE)
        self.assertIn("line", creds.reason)
        self.assertIn("last-good", creds.reason)

    def test_absent_settings_also_prefer_the_cache(self):
        self.seed_cache()
        creds = self.resolve()
        self.assertEqual(creds.rung, RUNG_CACHE)
        self.assertEqual(creds.ssid, "CachedNet")
        self.assertEqual(creds.settings_status, SETTINGS_ABSENT)

    def test_cached_disabled_flag_survives_a_broken_file(self):
        self.seed_cache(enabled=False)
        self.write_settings(BROKEN)
        self.assertFalse(self.resolve().enabled)

    def test_broken_settings_do_not_overwrite_the_cache(self):
        self.seed_cache()
        self.write_settings(BROKEN)
        self.resolve()
        self.assertEqual(read_last_good(self.cache), ("CachedNet", "cachedpass", True))

    def test_restoring_settings_returns_to_rung_one(self):
        # The second half of the Phase 1 gate.
        self.seed_cache()
        self.write_settings(BROKEN)
        self.assertEqual(self.resolve().rung, RUNG_CACHE)
        self.write_settings(VALID)
        creds = self.resolve()
        self.assertEqual(creds.rung, RUNG_SETTINGS)
        self.assertEqual(creds.ssid, "MyCamera")


# ---------------------------------------------------------------------------
# 4.2 rung 3 -- no usable cache
# ---------------------------------------------------------------------------

class RungThreeDefaultsTests(LadderTestCase):
    def test_broken_settings_and_no_cache_give_compiled_defaults(self):
        self.write_settings(BROKEN)
        creds = self.resolve()
        self.assertEqual(creds.rung, RUNG_DEFAULTS)
        self.assertEqual(creds.ssid, DEFAULT_SSID)
        self.assertEqual(creds.password, DEFAULT_PASS)
        self.assertTrue(creds.enabled)
        self.assertIn("built-in defaults", creds.reason)

    def test_nothing_at_all_gives_compiled_defaults(self):
        creds = self.resolve()
        self.assertEqual(creds.rung, RUNG_DEFAULTS)
        self.assertEqual(creds.ssid, DEFAULT_SSID)

    def test_corrupt_cache_is_treated_as_absent(self):
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        self.cache.write_text("{not json", encoding="utf-8")
        self.write_settings(BROKEN)
        self.assertEqual(self.resolve().rung, RUNG_DEFAULTS)

    def test_cache_with_unusable_password_is_rejected(self):
        # A cache NM would refuse is worse than no cache: it would fail to
        # bring the AP up at all.
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        self.cache.write_text(json.dumps({"ssid": "X", "password": "short"}), "utf-8")
        self.write_settings(BROKEN)
        self.assertEqual(self.resolve().rung, RUNG_DEFAULTS)

    def test_cache_missing_ssid_is_rejected(self):
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        self.cache.write_text(json.dumps({"password": "longenough"}), "utf-8")
        self.assertIsNone(read_last_good(self.cache))

    def test_cache_that_is_a_list_is_rejected(self):
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        self.cache.write_text("[]", encoding="utf-8")
        self.assertIsNone(read_last_good(self.cache))


# ---------------------------------------------------------------------------
# probe_settings -- absent vs unparseable (the F4 fix)
# ---------------------------------------------------------------------------

class ProbeSettingsTests(LadderTestCase):
    def test_absent_is_distinguishable_from_unparseable(self):
        absent = probe_settings(self.settings)
        self.assertEqual(absent.status, SETTINGS_ABSENT)

        self.write_settings(BROKEN)
        broken = probe_settings(self.settings)
        self.assertEqual(broken.status, SETTINGS_UNPARSEABLE)
        self.assertNotEqual(absent.detail, broken.detail)

    def test_unparseable_detail_matches_what_tty1_would_show(self):
        self.write_settings(BROKEN)
        detail = probe_settings(self.settings).detail
        self.assertIn("not valid JSON", detail)
        self.assertIn("line", detail)

    def test_unterminated_block_comment_is_reported(self):
        self.write_settings('{"system": {} /* never closed')
        probe = probe_settings(self.settings)
        self.assertEqual(probe.status, SETTINGS_UNPARSEABLE)
        self.assertIn("comment", probe.detail)

    def test_non_object_root_is_unparseable(self):
        self.write_settings("[1, 2, 3]")
        self.assertEqual(probe_settings(self.settings).status, SETTINGS_UNPARSEABLE)


# ---------------------------------------------------------------------------
# 4.5 write discipline
# ---------------------------------------------------------------------------

class AtomicWriteTests(LadderTestCase):
    def test_creates_parent_directories(self):
        target = self.tmp / "a" / "b" / "c.txt"
        atomic_write_bytes(target, b"hello")
        self.assertEqual(target.read_bytes(), b"hello")

    def test_replaces_existing_content(self):
        target = self.tmp / "f.txt"
        atomic_write_bytes(target, b"first")
        atomic_write_bytes(target, b"second")
        self.assertEqual(target.read_bytes(), b"second")

    def test_leaves_no_temp_files_behind(self):
        target = self.tmp / "f.txt"
        atomic_write_bytes(target, b"data")
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["f.txt"])

    def test_honours_the_requested_mode(self):
        target = self.tmp / "secret"
        atomic_write_bytes(target, b"x", mode=0o600)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_temp_file_is_cleaned_up_when_the_write_fails(self):
        target = self.tmp / "f.txt"
        with unittest.mock.patch("os.replace", side_effect=OSError("nope")):
            with self.assertRaises(OSError):
                atomic_write_bytes(target, b"data")
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_cache_is_written_private(self):
        write_last_good("Net", "longenough", True, self.cache)
        self.assertEqual(stat.S_IMODE(self.cache.stat().st_mode), 0o600)


class StateFileTests(LadderTestCase):
    def test_state_records_rung_and_reason(self):
        self.write_settings(BROKEN)
        creds = self.resolve()
        write_state(creds, self.state)
        payload = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(payload["rung"], RUNG_DEFAULTS)
        self.assertEqual(payload["rung_name"], "defaults")
        self.assertIn("not valid JSON", payload["reason"])
        self.assertEqual(payload["settings_status"], SETTINGS_UNPARSEABLE)
        self.assertIn("updated", payload)

    def test_state_never_contains_the_password(self):
        # /var/lib/cinemate/hotspot.state is rendered on an unauthenticated
        # recovery-console route.
        self.write_settings(VALID)
        creds = self.resolve()
        write_state(creds, self.state)
        text = self.state.read_text(encoding="utf-8")
        self.assertIn("MyCamera", text)
        self.assertNotIn("supersecret", text)
        self.assertNotIn("password", json.loads(text))

    def test_state_write_failure_is_survivable(self):
        # /var/lib/cinemate may not exist yet, and the AP still has to come up.
        blocked = self.tmp / "blocked"
        blocked.write_text("i am a file, not a directory", encoding="utf-8")
        self.write_settings(VALID)
        self.assertFalse(write_state(self.resolve(), blocked / "sub" / "state"))

    def test_cache_write_failure_is_survivable(self):
        blocked = self.tmp / "blocked2"
        blocked.write_text("not a directory", encoding="utf-8")
        self.assertFalse(write_last_good("N", "longenough", True, blocked / "x" / "y"))

    def test_ladder_still_resolves_when_the_state_dir_is_unwritable(self):
        # Section 10's named regression: a unit that predates
        # /var/lib/cinemate must still get credentials.
        blocked = self.tmp / "blocked3"
        blocked.write_text("not a directory", encoding="utf-8")
        self.write_settings(VALID)
        creds = resolve_credentials(self.settings, blocked / "nope" / "cache.json")
        self.assertEqual(creds.rung, RUNG_SETTINGS)
        self.assertEqual(creds.ssid, "MyCamera")


# ---------------------------------------------------------------------------
# nmcli terse parsing
# ---------------------------------------------------------------------------

class TerseParsingTests(unittest.TestCase):
    def test_plain_split(self):
        self.assertEqual(split_terse("Hotspot:802-11-wireless"),
                         ["Hotspot", "802-11-wireless"])

    def test_escaped_colon_in_an_ssid_is_preserved(self):
        # nmcli renders a literal ':' as '\:'. A naive split corrupts it.
        self.assertEqual(split_terse(r"My\:Net:802-11-wireless"),
                         ["My:Net", "802-11-wireless"])

    def test_escaped_backslash(self):
        self.assertEqual(split_terse(r"a\\b:wifi"), [r"a\b", "wifi"])

    def test_terse_value_splits_key_from_value(self):
        self.assertEqual(terse_value("802-11-wireless.ssid:CinePi"),
                         ("802-11-wireless.ssid", "CinePi"))

    def test_terse_value_keeps_colons_in_the_value(self):
        self.assertEqual(terse_value(r"connection.id:Guest\:AP"),
                         ("connection.id", "Guest:AP"))

    def test_terse_value_tolerates_a_valueless_line(self):
        self.assertEqual(terse_value("orphan"), ("orphan", ""))


# ---------------------------------------------------------------------------
# Single owner (F5)
# ---------------------------------------------------------------------------

class ServiceActiveTests(unittest.TestCase):
    def test_active_service_reports_true(self):
        def runner(cmd, **kw):
            self.assertEqual(cmd[:3], ["systemctl", "is-active", "--quiet"])
            return subprocess.CompletedProcess(cmd, 0, "", "")

        self.assertTrue(hotspot_service_active(runner=runner))

    def test_inactive_service_reports_false(self):
        def runner(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 3, "", "")

        self.assertFalse(hotspot_service_active(runner=runner))

    def test_missing_systemctl_reports_false(self):
        # No systemd in the test environment must not disable in-app creation.
        def runner(cmd, **kw):
            raise FileNotFoundError("systemctl")

        self.assertFalse(hotspot_service_active(runner=runner))


# ---------------------------------------------------------------------------
# Reconciliation, with nmcli faked
# ---------------------------------------------------------------------------

class FakeNmcli:
    """Records nmcli invocations and replays canned output."""

    def __init__(self, *, profile="Hotspot", mode="ap", iface="wlan0",
                 ssid="CinePi", psk="11111111", active=True):
        self.profile = profile
        self.mode = mode
        self.iface = iface
        self.ssid = ssid
        self.psk = psk
        self.active = active
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *, check=True, capture_output=True):
        self.calls.append(list(cmd))
        out = ""
        if cmd[:5] == ["nmcli", "-t", "-f", "NAME,TYPE", "con"]:
            out = f"{self.profile}:802-11-wireless\nWired connection 1:802-3-ethernet\n"
        elif cmd[:2] == ["nmcli", "-t"] and "802-11-wireless.mode," in " ".join(cmd):
            out = (f"802-11-wireless.mode:{self.mode}\n"
                   f"connection.interface-name:{self.iface}\n")
        elif cmd[:3] == ["nmcli", "-s", "-t"]:
            out = (f"802-11-wireless.ssid:{self.ssid}\n"
                   f"802-11-wireless-security.psk:{self.psk}\n")
        elif cmd[:4] == ["nmcli", "con", "show", "--active"]:
            out = f"{self.profile} uuid wifi wlan0\n" if self.active else ""
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def issued(self, *fragments):
        """True when some call contains all *fragments* in order."""
        for call in self.calls:
            joined = " ".join(call)
            if all(f in joined for f in fragments):
                return True
        return False


class ReconcileTests(LadderTestCase):
    def manager(self, fake):
        mgr = WiFiHotspotManager(
            settings_path=self.settings,
            cache_path=self.cache,
            state_path=self.state,
        )
        mgr._run = fake
        mgr.is_hotspot_active = lambda: fake.active
        return mgr

    def test_matching_credentials_are_left_alone(self):
        self.write_settings(
            '{"system": {"wifi_hotspot": {"name": "CinePi", "password": "11111111"}}}'
        )
        fake = FakeNmcli()
        self.manager(fake).reconcile()
        self.assertFalse(fake.issued("con", "modify", "802-11-wireless.ssid"))

    def test_drifted_ssid_is_corrected_without_a_reboot(self):
        self.write_settings(VALID)
        fake = FakeNmcli(ssid="CinePi")
        self.manager(fake).reconcile()
        self.assertTrue(fake.issued("con", "modify", "802-11-wireless.ssid", "MyCamera"))
        self.assertTrue(fake.issued("con", "up", "Hotspot"))

    def test_inactive_hotspot_is_created(self):
        self.write_settings(VALID)
        fake = FakeNmcli(active=False)
        mgr = self.manager(fake)
        mgr.ensure_wifi_ready = lambda timeout_s=20.0: True
        mgr.reconcile()
        self.assertTrue(fake.issued("d", "wifi", "hotspot", "MyCamera"))

    def test_autoconnect_is_asserted_when_enabled(self):
        # Phase 0 found the shipped profile carries autoconnect=false, so the
        # AP only ever existed because Python had run. This is layer 0.
        self.write_settings(VALID)
        fake = FakeNmcli()
        self.manager(fake).reconcile()
        self.assertTrue(fake.issued("con", "modify", "connection.autoconnect", "yes"))

    def test_autoconnect_is_cleared_when_disabled(self):
        self.write_settings(
            '{"system": {"wifi_hotspot": {"name": "Cam", "password": "longenough",'
            ' "enabled": false}}}'
        )
        fake = FakeNmcli()
        self.manager(fake).reconcile()
        self.assertTrue(fake.issued("con", "modify", "connection.autoconnect", "no"))

    def test_disabled_hotspot_is_never_torn_down(self):
        # An operator may be connected over it right now.
        self.write_settings(
            '{"system": {"wifi_hotspot": {"name": "Cam", "password": "longenough",'
            ' "enabled": false}}}'
        )
        fake = FakeNmcli()
        self.manager(fake).reconcile()
        self.assertFalse(fake.issued("con", "down"))
        self.assertFalse(fake.issued("d", "wifi", "hotspot"))

    def test_reconcile_publishes_the_state_file(self):
        self.write_settings(BROKEN)
        fake = FakeNmcli()
        self.manager(fake).reconcile()
        payload = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(payload["rung"], RUNG_DEFAULTS)

    def test_ap_profile_is_found_by_mode_not_by_name(self):
        self.write_settings(VALID)
        fake = FakeNmcli(profile="Hotspot 1")
        mgr = self.manager(fake)
        self.assertEqual(mgr.ap_profile_name(), "Hotspot 1")

    def test_client_mode_profile_is_not_mistaken_for_the_ap(self):
        self.write_settings(VALID)
        fake = FakeNmcli(mode="infrastructure")
        mgr = self.manager(fake)
        self.assertIsNone(mgr.ap_profile_name())

    def test_profile_on_another_interface_is_ignored(self):
        self.write_settings(VALID)
        fake = FakeNmcli(iface="wlan1")
        mgr = self.manager(fake)
        self.assertIsNone(mgr.ap_profile_name())


if __name__ == "__main__":
    unittest.main()
