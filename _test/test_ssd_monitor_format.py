import sys
import types
import unittest
from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import call, patch


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


class SSDMonitorFormatTests(unittest.TestCase):
    def _monitor(self):
        monitor = ssd_monitor.SSDMonitor.__new__(ssd_monitor.SSDMonitor)
        monitor._mount_path = Path("/tmp/cinemate-test-RAW")
        monitor._is_mounted = False
        monitor._device_name = None
        monitor._redis = None
        return monitor

    def test_format_remounts_with_requested_filesystem(self):
        monitor = self._monitor()
        monitor._is_mounted = True
        monitor._device_name = "sda2"

        with (
            patch.object(ssd_monitor.subprocess, "run") as run,
            patch.object(monitor, "_check_mount_status"),
            patch.object(monitor, "_settle_device_metadata") as settle,
            patch.object(monitor, "mount_drive", return_value=True) as mount_drive,
        ):
            self.assertTrue(monitor.format_drive("ext4"))

        run.assert_has_calls([
            call(["sudo", "umount", str(monitor._mount_path)], check=True),
            call(["sudo", "mkfs.ext4", "-F", "-L", "RAW", "/dev/sda2"], check=True),
        ])
        settle.assert_called_once_with("/dev/sda2")
        mount_drive.assert_called_once_with(filesystem="ext4", device="/dev/sda2")

    def test_mount_uses_filesystem_hint_over_stale_probe(self):
        monitor = self._monitor()

        with (
            patch.object(monitor, "_detect_device_filesystem", return_value="exfat"),
            patch.object(monitor, "_mount_raw_device", return_value=True) as mount_raw,
        ):
            self.assertTrue(monitor.mount_drive(filesystem="ext4", device="/dev/sda2"))

        mount_raw.assert_called_once_with("/dev/sda2", "ext4")

    def test_fresh_blkid_probe_falls_back_to_cacheless_query(self):
        calls = []

        def fake_check_output(cmd, **_kwargs):
            calls.append(cmd)
            if "-p" in cmd:
                raise CalledProcessError(2, cmd)
            if "-c" in cmd:
                return "ext4\n"
            raise AssertionError(f"unexpected fallback command: {cmd}")

        with patch.object(ssd_monitor.subprocess, "check_output", side_effect=fake_check_output):
            value = ssd_monitor.SSDMonitor._blkid_value("/dev/sda2", "TYPE", fresh=True)

        self.assertEqual(value, "ext4")
        self.assertEqual(calls[0], ["blkid", "-p", "-s", "TYPE", "-o", "value", "/dev/sda2"])
        self.assertEqual(calls[1], ["blkid", "-c", "/dev/null", "-s", "TYPE", "-o", "value", "/dev/sda2"])


if __name__ == "__main__":
    unittest.main()
