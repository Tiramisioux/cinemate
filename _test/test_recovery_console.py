"""Recovery console: config ladder, validation ladder, write discipline,
confirm-or-revert, service allowlist and ANSI rendering.

Covers the config/validation ladders, write discipline, confirm-or-revert
flow and service allowlist documented in docs/recovery-console.md. All pure
logic -- no hardware, no server socket, no real subprocess.

The console is loaded by path because its filename contains a hyphen and is
therefore not a legal module name.
"""

import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = ROOT / "services" / "cinemate-recovery"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SERVICE_DIR))


def _load_console():
    spec = importlib.util.spec_from_file_location(
        "cinemate_recovery", SERVICE_DIR / "cinemate-recovery.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rc = _load_console()


def fake_run(returncode=0, stdout="", stderr=""):
    calls = []

    def runner(cmd, **kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

    runner.calls = calls
    return runner


class TempCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


# ---------------------------------------------------------------------------
# 4.3 console config ladder
# ---------------------------------------------------------------------------

class ConfigLadderTests(TempCase):
    def setUp(self):
        super().setUp()
        self.settings = self.tmp / "settings.jsonc"
        self.conf = self.tmp / "cinemate-recovery.conf"

    def load(self, **kw):
        return rc.load_config(self.settings, self.conf, **kw)

    def test_rung_one_reads_system_recovery(self):
        self.settings.write_text(json.dumps({
            "system": {"recovery": {
                "enabled": True, "port": 9090, "token": "sekrit",
                "allow_config_txt": True, "config_confirm_timeout_s": 120,
            }}
        }), encoding="utf-8")
        cfg = self.load()
        self.assertEqual(cfg.rung, rc.CONFIG_RUNG_SETTINGS)
        self.assertEqual(cfg.port, 9090)
        self.assertEqual(cfg.token, "sekrit")
        self.assertTrue(cfg.allow_config_txt)
        self.assertEqual(cfg.config_confirm_timeout_s, 120)

    def test_rung_one_tolerates_jsonc_comments(self):
        self.settings.write_text(
            '{\n // comment\n "system": {"recovery": {"port": 9091,}}\n}',
            encoding="utf-8",
        )
        self.assertEqual(self.load().port, 9091)

    def test_missing_recovery_block_gives_documented_defaults(self):
        # Requiring an edit to settings.jsonc to get a working recovery
        # console would be circular.
        self.settings.write_text('{"system": {}}', encoding="utf-8")
        cfg = self.load()
        self.assertEqual(cfg.rung, rc.CONFIG_RUNG_SETTINGS)
        self.assertEqual(cfg.port, rc.DEFAULTS["port"])
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.token, "")
        self.assertFalse(cfg.allow_config_txt)

    def test_partial_block_fills_the_rest_from_defaults(self):
        self.settings.write_text(
            '{"system": {"recovery": {"token": "x"}}}', encoding="utf-8"
        )
        cfg = self.load()
        self.assertEqual(cfg.token, "x")
        self.assertEqual(cfg.port, 8080)
        self.assertFalse(cfg.allow_config_txt)

    def test_rung_two_used_when_settings_will_not_parse(self):
        self.settings.write_text('{"system": {', encoding="utf-8")
        self.conf.write_text(
            "# installer-written\nport=8081\ntoken=fallback\n"
            "allow_config_txt=true\nenabled=true\n",
            encoding="utf-8",
        )
        cfg = self.load()
        self.assertEqual(cfg.rung, rc.CONFIG_RUNG_CONF)
        self.assertEqual(cfg.port, 8081)
        self.assertEqual(cfg.token, "fallback")
        self.assertTrue(cfg.allow_config_txt)

    def test_rung_two_used_when_settings_is_absent(self):
        self.conf.write_text("port=8082\n", encoding="utf-8")
        cfg = self.load()
        self.assertEqual(cfg.rung, rc.CONFIG_RUNG_CONF)
        self.assertEqual(cfg.port, 8082)

    def test_rung_three_when_nothing_is_readable(self):
        cfg = self.load()
        self.assertEqual(cfg.rung, rc.CONFIG_RUNG_DEFAULTS)
        self.assertEqual(cfg.port, 8080)
        self.assertTrue(cfg.enabled)
        self.assertFalse(cfg.allow_config_txt)
        self.assertEqual(cfg.token, "")
        self.assertIn("built-in defaults", cfg.reason)

    def test_rung_three_when_both_files_are_corrupt(self):
        self.settings.write_text("{{{", encoding="utf-8")
        self.conf.write_bytes(b"\xff\xfe\x00binary")
        cfg = self.load()
        # A conf file that decodes but has no '=' lines yields an empty dict,
        # which still merges to the defaults; either rung is acceptable so
        # long as the values are the documented ones.
        self.assertEqual(cfg.port, 8080)
        self.assertFalse(cfg.allow_config_txt)

    def test_rung_three_when_the_vendored_stripper_is_gone(self):
        # The fail-open path if jsonc.py itself is missing.
        self.settings.write_text('{"system": {"recovery": {"port": 9}}}', "utf-8")
        cfg = self.load(jsonc_module=None)
        # Plain JSON still parses without the stripper.
        self.assertEqual(cfg.port, 9)

    def test_non_object_root_falls_through(self):
        self.settings.write_text("[]", encoding="utf-8")
        self.conf.write_text("port=8083\n", encoding="utf-8")
        self.assertEqual(self.load().rung, rc.CONFIG_RUNG_CONF)

    def test_reason_explains_the_fallback(self):
        self.settings.write_text("{{{", encoding="utf-8")
        self.conf.write_text("port=8084\n", encoding="utf-8")
        self.assertIn("settings.jsonc unusable", self.load().reason)


class ConfParsingTests(unittest.TestCase):
    def test_comments_and_blanks_ignored(self):
        parsed = rc.parse_conf("# c\n\nport=8080\n  token = abc  \n")
        self.assertEqual(parsed, {"port": "8080", "token": "abc"})

    def test_quotes_are_stripped(self):
        self.assertEqual(rc.parse_conf('token="quoted"')["token"], "quoted")

    def test_line_without_equals_is_ignored(self):
        self.assertEqual(rc.parse_conf("garbage\nport=1"), {"port": "1"})

    def test_value_containing_equals_survives(self):
        self.assertEqual(rc.parse_conf("token=a=b")["token"], "a=b")


class CoercionTests(unittest.TestCase):
    def test_string_booleans_from_the_flat_file(self):
        for text, expected in (("true", True), ("yes", True), ("on", True),
                               ("1", True), ("false", False), ("no", False),
                               ("off", False), ("0", False)):
            self.assertIs(rc._as_bool(text, None), expected, text)

    def test_unparseable_boolean_uses_the_default(self):
        self.assertTrue(rc._as_bool("banana", True))
        self.assertFalse(rc._as_bool(None, False))

    def test_unparseable_int_uses_the_default(self):
        self.assertEqual(rc._as_int("banana", 8080), 8080)
        self.assertEqual(rc._as_int(None, 8080), 8080)
        self.assertEqual(rc._as_int(" 9090 ", 8080), 9090)


# ---------------------------------------------------------------------------
# 4.4 settings validation ladder
# ---------------------------------------------------------------------------

class ValidationLadderTests(TempCase):
    def test_rung_one_reports_the_exact_tty1_text(self):
        runner = fake_run(returncode=2, stdout="File: x\nProblem: bad thing at line 4")
        result = rc.validate_settings_text(
            "{bad", python_bin=Path(sys.executable), src_dir=ROOT / "src",
            runner=runner,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.rung, rc.VALIDATE_RUNG_INTERPRETER)
        self.assertIn("line 4", result.message)
        self.assertTrue(result.validated)

    def test_rung_one_accepts_valid_content(self):
        runner = fake_run(returncode=0)
        result = rc.validate_settings_text(
            '{"a": 1}', python_bin=Path(sys.executable), src_dir=ROOT / "src",
            runner=runner,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.rung, rc.VALIDATE_RUNG_INTERPRETER)

    def test_rung_one_really_does_use_config_loader(self):
        # End-to-end through a real interpreter, proving the embedded validator
        # script imports and reports the same error Cinemate would.
        result = rc.validate_settings_text(
            '{"system": {"a": 1 "b": 2}}',
            python_bin=Path(sys.executable), src_dir=ROOT / "src",
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.rung, rc.VALIDATE_RUNG_INTERPRETER)
        self.assertIn("Problem:", result.message)

    def test_falls_to_rung_two_when_the_interpreter_is_missing(self):
        result = rc.validate_settings_text(
            '{"a": 1,}', python_bin=self.tmp / "no-such-python",
            src_dir=self.tmp,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.rung, rc.VALIDATE_RUNG_STDLIB)

    def test_rung_two_rejects_broken_content(self):
        result = rc.validate_settings_text(
            '{"a": 1 "b": 2}', python_bin=self.tmp / "gone", src_dir=self.tmp,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.rung, rc.VALIDATE_RUNG_STDLIB)

    def test_rung_two_accepts_jsonc(self):
        result = rc.validate_settings_text(
            '{ // ok\n "a": 1,\n}', python_bin=self.tmp / "gone", src_dir=self.tmp,
        )
        self.assertTrue(result.ok)

    def test_falls_to_rung_two_when_the_interpreter_validator_itself_breaks(self):
        runner = fake_run(returncode=3, stdout="ImportError: no module")
        result = rc.validate_settings_text(
            '{"a": 1}', python_bin=Path(sys.executable), src_dir=ROOT / "src",
            runner=runner,
        )
        self.assertEqual(result.rung, rc.VALIDATE_RUNG_STDLIB)
        self.assertTrue(result.ok)

    def test_rung_three_fails_open_and_labels_the_write(self):
        # The rung that only fires when everything else is already broken.
        result = rc.validate_settings_text(
            "total garbage {{{", python_bin=self.tmp / "gone", src_dir=self.tmp,
            jsonc_module=None,
        )
        self.assertTrue(result.ok, "rung 3 must fail OPEN")
        self.assertEqual(result.rung, rc.VALIDATE_RUNG_NONE)
        self.assertFalse(result.validated)
        self.assertIn("UNVALIDATED", result.message)

    def test_rung_three_never_refuses_even_valid_looking_input(self):
        result = rc.validate_settings_text(
            '{"a": 1}', python_bin=self.tmp / "gone", src_dir=self.tmp,
            jsonc_module=None,
        )
        self.assertTrue(result.ok)
        self.assertFalse(result.validated)


# ---------------------------------------------------------------------------
# 4.5 write discipline and backup rotation
# ---------------------------------------------------------------------------

class WriteDisciplineTests(TempCase):
    def setUp(self):
        super().setUp()
        self.backups = self.tmp / "backups"
        self.target = self.tmp / "settings.jsonc"

    def test_backup_then_write(self):
        self.target.write_text("original", encoding="utf-8")
        backup = rc.write_config_file(self.target, "replacement", self.backups)
        self.assertEqual(self.target.read_text(), "replacement")
        self.assertEqual(Path(backup).read_text(), "original")

    def test_write_when_the_target_does_not_exist(self):
        backup = rc.write_config_file(self.target, "new", self.backups)
        self.assertIsNone(backup)
        self.assertEqual(self.target.read_text(), "new")

    def test_backups_are_private(self):
        self.target.write_text("secret", encoding="utf-8")
        backup = rc.backup_file(self.target, self.backups)
        self.assertEqual(stat.S_IMODE(Path(backup).stat().st_mode), 0o600)

    def test_two_writes_in_one_second_do_not_collide(self):
        self.target.write_text("a", encoding="utf-8")
        first = rc.backup_file(self.target, self.backups)
        self.target.write_text("b", encoding="utf-8")
        second = rc.backup_file(self.target, self.backups)
        self.assertNotEqual(first, second)
        self.assertEqual(Path(first).read_text(), "a")
        self.assertEqual(Path(second).read_text(), "b")

    def test_rotation_keeps_ten_and_never_the_oldest(self):
        # "Keep the last 10 backups per file. Never delete the oldest."
        # The oldest is the pristine original -- what you want after ten
        # bad edits in a row.
        self.backups.mkdir(parents=True)
        for i in range(1, 16):
            (self.backups / f"settings.jsonc.202601{i:02d}T000000Z.bak").write_text(
                f"gen{i}", encoding="utf-8"
            )
        rc.prune_backups("settings.jsonc", self.backups, keep=10)
        survivors = sorted(p.name for p in self.backups.iterdir())
        self.assertEqual(len(survivors), 10)
        self.assertIn("settings.jsonc.20260101T000000Z.bak", survivors)  # oldest
        self.assertIn("settings.jsonc.20260115T000000Z.bak", survivors)  # newest
        # The pristine original is still readable, ten bad edits later.
        self.assertEqual(
            (self.backups / "settings.jsonc.20260101T000000Z.bak").read_text(), "gen1"
        )

    def test_rotation_leaves_a_small_set_alone(self):
        self.backups.mkdir(parents=True)
        for i in range(3):
            (self.backups / f"settings.jsonc.2026010{i}T000000Z.bak").write_text("x")
        self.assertEqual(rc.prune_backups("settings.jsonc", self.backups, 10), [])
        self.assertEqual(len(list(self.backups.iterdir())), 3)

    def test_rotation_is_per_file(self):
        self.backups.mkdir(parents=True)
        for i in range(12):
            (self.backups / f"settings.jsonc.2026010{i:02d}T000000Z.bak").write_text("s")
        for i in range(3):
            (self.backups / f"config.txt.2026010{i}T000000Z.bak").write_text("c")
        rc.prune_backups("settings.jsonc", self.backups, keep=10)
        remaining = [p.name for p in self.backups.iterdir()]
        self.assertEqual(sum(1 for n in remaining if n.startswith("config.txt")), 3)

    def test_atomic_write_leaves_no_temp_files(self):
        rc.atomic_write_bytes(self.target, b"data")
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["settings.jsonc"])

    def test_atomic_write_creates_parents(self):
        deep = self.tmp / "x" / "y" / "z.txt"
        rc.atomic_write_bytes(deep, b"ok")
        self.assertEqual(deep.read_bytes(), b"ok")

    def test_backup_paths_are_sorted_oldest_first(self):
        self.backups.mkdir(parents=True)
        for stamp in ("20260103", "20260101", "20260102"):
            (self.backups / f"f.{stamp}T000000Z.bak").write_text("x")
        names = [p.name for p in rc.backup_paths("f", self.backups)]
        self.assertEqual(names[0], "f.20260101T000000Z.bak")
        self.assertEqual(names[-1], "f.20260103T000000Z.bak")


# ---------------------------------------------------------------------------
# 4.6 confirm-or-revert
# ---------------------------------------------------------------------------

class ConfirmOrRevertTests(TempCase):
    def setUp(self):
        super().setUp()
        self.marker = self.tmp / "config-pending.json"
        self.backup = self.tmp / "config.txt.bak"
        self.target = self.tmp / "config.txt"
        self.backup.write_text("good config", encoding="utf-8")
        self.target.write_text("risky config", encoding="utf-8")

    def test_arm_writes_a_readable_marker(self):
        rc.arm_pending(self.backup, self.target, 300, self.marker, now=lambda: 1000.0)
        pending = rc.read_pending(self.marker)
        self.assertEqual(pending.backup, str(self.backup))
        self.assertEqual(pending.timeout_s, 300)
        self.assertEqual(pending.armed_at, 1000.0)

    def test_no_marker_reads_as_none(self):
        self.assertIsNone(rc.read_pending(self.marker))

    def test_corrupt_marker_reads_as_none(self):
        self.marker.write_text("not json", encoding="utf-8")
        self.assertIsNone(rc.read_pending(self.marker))

    def test_marker_missing_a_field_reads_as_none(self):
        self.marker.write_text(json.dumps({"backup": "x"}), encoding="utf-8")
        self.assertIsNone(rc.read_pending(self.marker))

    def test_confirm_clears_the_marker(self):
        rc.arm_pending(self.backup, self.target, 300, self.marker)
        self.assertTrue(rc.clear_pending(self.marker))
        self.assertIsNone(rc.read_pending(self.marker))

    def test_confirm_twice_is_harmless(self):
        rc.arm_pending(self.backup, self.target, 300, self.marker)
        rc.clear_pending(self.marker)
        self.assertFalse(rc.clear_pending(self.marker))

    def test_remaining_counts_down(self):
        pending = rc.arm_pending(
            self.backup, self.target, 300, self.marker, now=lambda: 1000.0
        )
        self.assertEqual(rc.pending_remaining(pending, now=lambda: 1000.0), 300)
        self.assertEqual(rc.pending_remaining(pending, now=lambda: 1250.0), 50)

    def test_remaining_never_goes_negative(self):
        pending = rc.arm_pending(
            self.backup, self.target, 300, self.marker, now=lambda: 1000.0
        )
        self.assertEqual(rc.pending_remaining(pending, now=lambda: 99999.0), 0)

    def test_expiry_restores_the_backup_and_reboots(self):
        pending = rc.arm_pending(self.backup, self.target, 1, self.marker)
        rebooted = []
        restored = rc.revert_pending(
            pending, self.marker, reboot=lambda: rebooted.append(True)
        )
        self.assertTrue(restored)
        self.assertEqual(self.target.read_text(), "good config")
        self.assertEqual(rebooted, [True])
        self.assertIsNone(rc.read_pending(self.marker))

    def test_reboot_still_happens_when_the_restore_fails(self):
        # A half-reverted Pi that never reboots is the worst outcome.
        pending = rc.arm_pending(self.tmp / "gone.bak", self.target, 1, self.marker)
        rebooted = []
        restored = rc.revert_pending(
            pending, self.marker, reboot=lambda: rebooted.append(True)
        )
        self.assertFalse(restored)
        self.assertEqual(rebooted, [True])
        self.assertIsNone(rc.read_pending(self.marker))

    def test_marker_survives_a_process_restart(self):
        # The watchdog inherits Restart=always; the countdown resumes from
        # the marker rather than restarting from zero.
        rc.arm_pending(self.backup, self.target, 300, self.marker, now=lambda: 500.0)
        reread = rc.read_pending(self.marker)
        self.assertEqual(rc.pending_remaining(reread, now=lambda: 700.0), 100)


# ---------------------------------------------------------------------------
# Section 5 service allowlist
# ---------------------------------------------------------------------------

class ServiceAllowlistTests(unittest.TestCase):
    def test_allowed_service_and_action(self):
        runner = fake_run()
        rc.systemctl("restart", "cinemate-autostart", runner=runner)
        self.assertEqual(
            runner.calls, [["systemctl", "restart", "cinemate-autostart.service"]]
        )

    def test_unknown_service_is_refused(self):
        runner = fake_run()
        with self.assertRaises(rc.ServiceError):
            rc.systemctl("restart", "sshd", runner=runner)
        self.assertEqual(runner.calls, [])

    def test_injection_attempt_is_refused(self):
        runner = fake_run()
        for evil in ("cinemate-autostart; rm -rf /", "../../etc/passwd",
                     "cinemate-autostart\nsshd", "*", ""):
            with self.assertRaises(rc.ServiceError):
                rc.systemctl("restart", evil, runner=runner)
        self.assertEqual(runner.calls, [])

    def test_unknown_action_is_refused(self):
        with self.assertRaises(rc.ServiceError):
            rc.systemctl("mask", "cinemate-autostart", runner=fake_run())

    def test_hotspot_may_not_be_stopped(self):
        # It is the operator's only way back in (section 4.7).
        runner = fake_run()
        with self.assertRaises(rc.ServiceError):
            rc.systemctl("stop", "wifi-hotspot", runner=runner)
        self.assertEqual(runner.calls, [])

    def test_hotspot_may_be_restarted(self):
        runner = fake_run()
        rc.systemctl("restart", "wifi-hotspot", runner=runner)
        self.assertEqual(len(runner.calls), 1)

    def test_cinemate_may_be_stopped(self):
        runner = fake_run()
        rc.systemctl("stop", "cinemate-autostart", runner=runner)
        self.assertEqual(len(runner.calls), 1)

    def test_state_query_is_allowlisted_too(self):
        with self.assertRaises(rc.ServiceError):
            rc.service_state("sshd", runner=fake_run())

    def test_state_of_missing_systemctl_is_unknown(self):
        def boom(cmd, **kw):
            raise FileNotFoundError("systemctl")

        self.assertEqual(rc.service_state("wifi-hotspot", runner=boom), "unknown")

    def test_journal_is_allowlisted(self):
        with self.assertRaises(rc.ServiceError):
            rc.journal_tail("sshd", runner=fake_run())

    def test_journal_line_count_is_capped(self):
        runner = fake_run(stdout="log")
        rc.journal_tail("cinemate-autostart", 99999, runner=runner)
        self.assertIn(str(rc.MAX_LOG_LINES), runner.calls[0])

    def test_journal_line_count_has_a_floor(self):
        runner = fake_run(stdout="log")
        rc.journal_tail("cinemate-autostart", -5, runner=runner)
        self.assertIn("1", runner.calls[0])


# ---------------------------------------------------------------------------
# ANSI -> HTML
# ---------------------------------------------------------------------------

class AnsiRenderingTests(unittest.TestCase):
    def test_plain_text_passes_through(self):
        self.assertEqual(rc.ansi_to_html("hello"), "hello")

    def test_html_is_escaped(self):
        self.assertEqual(rc.ansi_to_html("<script>"), "&lt;script&gt;")

    def test_escaping_happens_inside_a_colour_run(self):
        out = rc.ansi_to_html("\033[1;31m<b>\033[0m")
        self.assertIn("&lt;b&gt;", out)
        self.assertNotIn("<b>", out)

    def test_colour_becomes_a_span(self):
        out = rc.ansi_to_html("\033[1;31mProblem\033[0m")
        self.assertIn("color:#cc0000", out)
        self.assertIn("font-weight:bold", out)
        self.assertIn("Problem", out)

    def test_spans_are_balanced(self):
        out = rc.ansi_to_html("\033[1;31ma\033[0m\033[1;36mb\033[0m")
        self.assertEqual(out.count("<span"), out.count("</span>"))

    def test_unclosed_span_is_still_balanced(self):
        out = rc.ansi_to_html("\033[1;33mdangling")
        self.assertEqual(out.count("<span"), out.count("</span>"))

    def test_real_config_loader_output_renders(self):
        from module.config_loader import SettingsLoadError
        err = SettingsLoadError(
            Path("/x/settings.jsonc"), "summary", "detail at line 3, column 5",
            "do the thing", line=3, column=5, context="  3 | broken",
        )
        out = rc.ansi_to_html(err.format_for_cli(use_color=True))
        self.assertIn("detail at line 3, column 5", out)
        self.assertIn("do the thing", out)
        self.assertNotIn("\033", out)
        self.assertEqual(out.count("<span"), out.count("</span>"))

    def test_unknown_sgr_codes_are_dropped_silently(self):
        self.assertNotIn("\033", rc.ansi_to_html("\033[48;5;200mx\033[0m"))


# ---------------------------------------------------------------------------
# System facts
# ---------------------------------------------------------------------------

class SystemFactTests(TempCase):
    def test_missing_failure_file_is_none_not_an_error(self):
        # Absent is the healthy case, not an error.
        self.assertIsNone(rc.read_failure_block(self.tmp / "nope"))

    def test_failure_file_is_read_verbatim(self):
        path = self.tmp / "startup-failure.ansi"
        path.write_text("\033[1;31mboom\033[0m", encoding="utf-8")
        self.assertIn("boom", rc.read_failure_block(path))

    def test_hotspot_state_is_parsed(self):
        path = self.tmp / "hotspot.state"
        path.write_text(json.dumps({"rung": 2, "ssid": "Cached"}), encoding="utf-8")
        self.assertEqual(rc.read_hotspot_state(path)["ssid"], "Cached")

    def test_missing_hotspot_state_is_none(self):
        self.assertIsNone(rc.read_hotspot_state(self.tmp / "nope"))

    def test_corrupt_hotspot_state_is_none(self):
        path = self.tmp / "hotspot.state"
        path.write_text("{{{", encoding="utf-8")
        self.assertIsNone(rc.read_hotspot_state(path))

    def test_uptime_is_formatted(self):
        path = self.tmp / "uptime"
        path.write_text("90061.5 12345.6", encoding="utf-8")
        self.assertEqual(rc.read_uptime(str(path)), "1d 1h 1m")

    def test_uptime_minutes_only(self):
        path = self.tmp / "uptime"
        path.write_text("300.0 1.0", encoding="utf-8")
        self.assertEqual(rc.read_uptime(str(path)), "5m")

    def test_missing_uptime_is_unknown(self):
        self.assertEqual(rc.read_uptime(str(self.tmp / "nope")), "unknown")

    def test_disk_free_is_formatted(self):
        self.assertIn("GB free", rc.read_disk_free("/"))

    def test_missing_disk_path_is_unknown(self):
        self.assertEqual(rc.read_disk_free(str(self.tmp / "nope")), "unknown")


# ---------------------------------------------------------------------------
# The one rule
# ---------------------------------------------------------------------------

class StdlibOnlyTests(unittest.TestCase):
    """The single most important constraint in the plan."""

    #: Everything the console is allowed to import. Stdlib, plus the vendored
    #: sibling. Adding to this list is a design decision, not a formality:
    #: every entry is another way for the console to fail to start.
    ALLOWED = {
        "argparse", "hmac", "html", "http", "json", "logging", "os", "re",
        "shutil", "subprocess", "sys", "tempfile", "threading", "time",
        "datetime", "pathlib", "typing", "urllib", "__future__",
        "jsonc",  # the vendored sibling
    }

    def _imported_roots(self, path):
        """Top-level module names actually imported, via AST.

        Deliberately not a text scan: the console embeds a validator script as
        a string literal, and that script legitimately contains
        'from module.config_loader import ...' because it is executed by the
        *venv* interpreter in a subprocess, not imported here.
        """
        import ast

        roots = set()
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    roots.add(node.module.split(".")[0])
        return roots

    def test_console_imports_nothing_outside_the_stdlib(self):
        roots = self._imported_roots(SERVICE_DIR / "cinemate-recovery.py")
        self.assertTrue(roots, "no imports found - did the parse fail?")
        self.assertEqual(roots - self.ALLOWED, set())

    def test_console_does_not_import_from_the_cinemate_source_tree(self):
        roots = self._imported_roots(SERVICE_DIR / "cinemate-recovery.py")
        self.assertNotIn("module", roots)

    def test_vendored_stripper_imports_nothing_at_all(self):
        self.assertEqual(self._imported_roots(SERVICE_DIR / "jsonc.py"), set())

    def test_console_does_not_put_the_cinemate_source_tree_on_sys_path(self):
        source = (SERVICE_DIR / "cinemate-recovery.py").read_text(encoding="utf-8")
        self.assertNotIn('sys.path.insert(0, "/home/pi/cinemate/src")', source)

    def test_unit_has_no_dependency_on_cinemate_autostart(self):
        # The coupling being fixed. A regression here reintroduces the bug.
        unit = (SERVICE_DIR / "cinemate-recovery.service").read_text(encoding="utf-8")
        for line in unit.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith(("Wants=", "After=", "Requires=", "BindsTo=",
                                    "PartOf=", "Requisite=")):
                self.assertNotIn("cinemate-autostart", stripped)

    def test_unit_restarts_always(self):
        unit = (SERVICE_DIR / "cinemate-recovery.service").read_text(encoding="utf-8")
        self.assertIn("Restart=always", unit)
        self.assertIn("User=root", unit)

    def test_unit_runs_system_python_not_the_venv(self):
        unit = (SERVICE_DIR / "cinemate-recovery.service").read_text(encoding="utf-8")
        self.assertIn("/usr/bin/python3", unit)
        self.assertNotIn(".cinemate-env", unit)

    def test_service_is_registered_with_the_umbrella_makefile(self):
        makefile = (ROOT / "services" / "Makefile").read_text(encoding="utf-8")
        self.assertIn("cinemate-recovery", makefile)


if __name__ == "__main__":
    unittest.main()
