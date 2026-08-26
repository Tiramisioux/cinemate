"""Regression cover for the three B9/B11 review findings.

B9.1  a deliberate unmount must claim the device before unmounting, so
      storage-automount does not remount it out from under the operator.
B9.4  the SMPTE frame base must round half-up, matching the C++ side.
B11.4 both getty-start sites must use --job-mode=fail, so a getty start
      cannot cancel an in-flight cinemate-autostart restart.
"""

import os
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class _DummyBus:
    def read_byte(self, *_args):
        raise OSError

    def close(self):
        pass


sys.modules.setdefault("smbus", types.SimpleNamespace(SMBus=lambda *_args: _DummyBus()))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module import ssd_monitor
from module.redis_controller import smpte_frame_base


# ─────────────────────────── B9.4 — frame base ───────────────────────────
class SmpteFrameBaseTests(unittest.TestCase):
    def test_half_integer_rates_round_up_like_cxx(self):
        """Python's built-in round() is banker's rounding and would give 24."""
        self.assertEqual(smpte_frame_base(24.5), 25)
        self.assertEqual(smpte_frame_base(23.5), 24)
        self.assertEqual(smpte_frame_base(29.5), 30)

    def test_matches_std_lround_on_ordinary_rates(self):
        for fps, expected in (
            (23.976, 24),
            (24.0, 24),
            (25.0, 25),
            (29.97, 30),
            (30.0, 30),
            (47.952, 48),
            (50.0, 50),
            (59.94, 60),
        ):
            with self.subTest(fps=fps):
                self.assertEqual(smpte_frame_base(fps), expected)

    def test_accepts_strings_because_redis_values_are_strings(self):
        self.assertEqual(smpte_frame_base("24.5"), 25)
        self.assertEqual(smpte_frame_base("25"), 25)

    def test_degenerate_input_clamps_to_one_and_never_raises(self):
        for bad in (0, -1, 0.4, None, "", "not-a-number", float("nan"), float("inf")):
            with self.subTest(value=bad):
                self.assertGreaterEqual(smpte_frame_base(bad), 1)

    def test_timecode_uses_the_shared_base(self):
        """A 24.5 fps clip must show frames 0..24, not 0..23."""
        controller = object.__new__(sys.modules["module.redis_controller"].RedisController)
        controller.conform_frame_rate = 24.5
        # One second in: the frame field must have wrapped exactly once at 25.
        self.assertEqual(controller._format_timecode(1.0, 24.5), "00:00:01:00")
        # The last frame before the wrap is 24, which base 24 could never reach.
        self.assertTrue(controller._format_timecode(24 / 25, 24.5).endswith(":24"))


# ─────────────────────────── B9.1 — eject intent ─────────────────────────
class EjectIntentTests(unittest.TestCase):
    def _monitor(self, tmpdir):
        monitor = ssd_monitor.SSDMonitor.__new__(ssd_monitor.SSDMonitor)
        monitor._mount_path = Path(tmpdir) / "RAW"
        monitor._is_mounted = True
        monitor._device_name = "nvme0n1p1"
        monitor._redis = None
        return monitor

    def test_unmount_flags_the_device_before_unmounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            flag_dir = Path(tmp) / "eject"
            monitor = self._monitor(tmp)
            order = []

            def fake_run(cmd, **_kw):
                order.append(("umount", (flag_dir / "nvme0n1p1").exists()))
                return types.SimpleNamespace(returncode=0)

            with (
                patch.object(ssd_monitor, "EJECT_FLAG_DIR", flag_dir),
                patch.object(ssd_monitor.subprocess, "call"),
                patch.object(ssd_monitor.subprocess, "run", side_effect=fake_run),
            ):
                monitor.unmount_drive()

            self.assertTrue((flag_dir / "nvme0n1p1").exists(),
                            "device should stay flagged after a deliberate eject")
            # The flag has to exist *at the moment umount runs*, not merely
            # afterwards -- storage-automount remounts in well under a second.
            self.assertEqual(order, [("umount", True)])

    def test_successful_mount_clears_the_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            flag_dir = Path(tmp) / "eject"
            flag_dir.mkdir(parents=True)
            (flag_dir / "nvme0n1p1").touch()
            monitor = self._monitor(tmp)
            monitor._is_mounted = False

            with (
                patch.object(ssd_monitor, "EJECT_FLAG_DIR", flag_dir),
                patch.object(monitor, "_find_raw_device", return_value="/dev/nvme0n1p1"),
                patch.object(monitor, "_detect_device_filesystem", return_value="ext4"),
                patch.object(monitor, "_mount_raw_device", return_value=True),
            ):
                self.assertTrue(monitor.mount_drive())

            self.assertFalse((flag_dir / "nvme0n1p1").exists())

    def test_failed_mount_leaves_the_drive_ejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            flag_dir = Path(tmp) / "eject"
            flag_dir.mkdir(parents=True)
            (flag_dir / "nvme0n1p1").touch()
            monitor = self._monitor(tmp)
            monitor._is_mounted = False

            with (
                patch.object(ssd_monitor, "EJECT_FLAG_DIR", flag_dir),
                patch.object(monitor, "_find_raw_device", return_value="/dev/nvme0n1p1"),
                patch.object(monitor, "_detect_device_filesystem", return_value="ext4"),
                patch.object(monitor, "_mount_raw_device", return_value=False),
            ):
                self.assertFalse(monitor.mount_drive())

            self.assertTrue((flag_dir / "nvme0n1p1").exists(),
                            "a failed mount must not silently un-eject the drive")

    def test_unwritable_flag_dir_does_not_block_the_unmount(self):
        """Degrades to the old racy behaviour rather than refusing to unmount."""
        with tempfile.TemporaryDirectory() as tmp:
            monitor = self._monitor(tmp)
            with (
                patch.object(ssd_monitor, "EJECT_FLAG_DIR", Path("/proc/nope/eject")),
                patch.object(ssd_monitor.subprocess, "call"),
                patch.object(ssd_monitor.subprocess, "run") as run,
            ):
                monitor.unmount_drive()
            run.assert_any_call(["sudo", "umount", str(monitor._mount_path)], check=True)


class StorageAutomountEjectTests(unittest.TestCase):
    """The service half of the protocol, loaded straight from the service file."""

    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "services" / "storage-automount"
                      / "storage-automount.py").read_text()

    def test_change_events_are_ignored_for_flagged_devices(self):
        # The udev worker must screen the flag before the add/change split --
        # umount's own "change" event is what used to undo a deliberate eject.
        self.assertIn('if action in ("add", "change") and _is_eject_flagged(devnode):',
                      self.source)

    def test_add_raw_screens_the_flag(self):
        add_raw = self.source.split("def _add_raw(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("_is_eject_flagged(dev)", add_raw)

    def test_promotion_skips_flagged_devices(self):
        promote = self.source.split("def _promote_next(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("_is_eject_flagged", promote)

    def test_removal_clears_the_flag_so_replug_automounts(self):
        self.assertIn("_clear_eject_flags_for(devnode", self.source)

    def test_flag_dir_is_created_at_startup(self):
        main = self.source.split("def main(", 1)[1]
        self.assertIn("_init_eject_dir()", main)

    def test_both_sides_agree_on_the_flag_location(self):
        self.assertIn('CINEMATE_STORAGE_RUN_DIR", "/run/cinemate-storage"', self.source)
        self.assertIn('CINEMATE_STORAGE_RUN_DIR", "/run/cinemate-storage"',
                      (ROOT / "src" / "module" / "ssd_monitor.py").read_text())


# ────────────────────────── B11.4 — getty job mode ───────────────────────
class GettyJobModeTests(unittest.TestCase):
    """Both getty-start sites on the stop path need --job-mode=fail.

    In systemd's default "replace" job mode a getty start may reverse an
    already-queued start job for cinemate-autostart (they Conflict), cancelling
    a restart's own start half and leaving the unit inactive/dead with
    Result=success -- so Restart= never fires and nothing retries it.
    """

    def test_console_handoff_script_uses_fail_job_mode(self):
        script = (ROOT / "services" / "cinemate-autostart"
                  / "cinemate-console-handoff.sh").read_text()
        getty_lines = [ln for ln in script.splitlines()
                       if "getty@tty1.service" in ln and not ln.lstrip().startswith("#")]
        self.assertTrue(getty_lines, "expected a getty start in the handoff script")
        for line in getty_lines:
            with self.subTest(line=line):
                self.assertIn("--job-mode=fail", line)

    def test_main_py_console_restore_uses_fail_job_mode(self):
        source = (ROOT / "src" / "main.py").read_text()
        body = source.split("def restore_local_console_prompt(", 1)[1]
        body = body.split("\ndef ", 1)[0]
        commands = re.findall(r"\[[^\]]*getty@tty1\.service[^\]]*\]", body)
        self.assertTrue(commands, "expected getty restart commands in main.py")
        for command in commands:
            with self.subTest(command=command):
                self.assertIn("--job-mode=fail", command)

    def test_unit_still_declares_the_conflict_it_relies_on(self):
        # Dropping Conflicts= was tried on hardware and made things worse
        # (TTYVHangup then SIGHUPs this unit's own ExecStartPre). The job-mode
        # fix assumes the conflict is still declared.
        unit = (ROOT / "services" / "cinemate-autostart"
                / "cinemate-autostart.service").read_text()
        self.assertIn("Conflicts=getty@tty1.service", unit)


if __name__ == "__main__":
    unittest.main()
