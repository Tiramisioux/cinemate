import errno
import sys
import types
import unittest
from pathlib import Path
from subprocess import CalledProcessError
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

        # assert_any_call (not assert_has_calls): format_drive now interleaves
        # `blockdev --getsize64` size probes between the umount and the mkfs, so
        # the two commands are no longer consecutive in the call list.
        run.assert_any_call(["sudo", "umount", str(monitor._mount_path)], check=True)
        run.assert_any_call(
            ["sudo", "mkfs.ext4", "-F", "-L", "RAW", "/dev/sda2"], check=True, timeout=120
        )
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


class SSDMonitorStorageErrorTests(unittest.TestCase):
    """A corrupt clip dir on a dirty NTFS volume must not unmount a healthy drive.

    Regression guard for the hotswap flap: an EIO while counting files in one
    leftover recording directory was misread as a yanked card, unmounting the
    drive in a loop. Only a root-level failure is a genuine device loss.
    """

    def _monitor(self):
        monitor = ssd_monitor.SSDMonitor.__new__(ssd_monitor.SSDMonitor)
        monitor._mount_path = Path("/tmp/cinemate-test-RAW")
        monitor._is_mounted = True
        monitor._redis = None
        monitor._unreadable_dirs = set()
        return monitor

    def test_path_is_inside_mount(self):
        m = self._monitor()
        self.assertTrue(m._path_is_inside_mount("/tmp/cinemate-test-RAW/CINEPI_x_cam1"))
        self.assertTrue(m._path_is_inside_mount("/tmp/cinemate-test-RAW/a/b/c.dng"))
        # The mount root itself and a sibling-prefix path are NOT "inside".
        self.assertFalse(m._path_is_inside_mount("/tmp/cinemate-test-RAW"))
        self.assertFalse(m._path_is_inside_mount("/tmp/cinemate-test-RAW/"))
        self.assertFalse(m._path_is_inside_mount("/tmp/cinemate-test-RAWZ/other"))
        self.assertFalse(m._path_is_inside_mount(None))

    def test_eio_on_subpath_does_not_unmount(self):
        m = self._monitor()
        exc = OSError(
            errno.EIO, "Input/output error",
            "/tmp/cinemate-test-RAW/CINEPI_26-06-10_011338_F20_C00002_cam1",
        )
        with (
            patch.object(m, "_force_lazy_unmount") as flu,
            patch.object(m, "_handle_unmount") as hu,
        ):
            handled = m._handle_storage_error(exc, action="count files on")
        self.assertFalse(handled)        # not treated as lost storage
        flu.assert_not_called()
        hu.assert_not_called()
        self.assertTrue(m._is_mounted)   # drive stays mounted

    def test_eio_on_mount_root_unmounts(self):
        m = self._monitor()
        exc = OSError(errno.EIO, "Input/output error", "/tmp/cinemate-test-RAW")
        with (
            patch.object(m, "_force_lazy_unmount") as flu,
            patch.object(m, "_handle_unmount") as hu,
        ):
            handled = m._handle_storage_error(exc, action="check free space on")
        self.assertTrue(handled)         # genuine device loss
        flu.assert_called_once()
        hu.assert_called_once()

    def test_eio_with_no_filename_unmounts(self):
        # statvfs failures may not carry a filename — stay conservative (unmount).
        m = self._monitor()
        exc = OSError(errno.EIO, "Input/output error")
        with (
            patch.object(m, "_force_lazy_unmount"),
            patch.object(m, "_handle_unmount") as hu,
        ):
            handled = m._handle_storage_error(exc, action="check free space on")
        self.assertTrue(handled)
        hu.assert_called_once()

    def test_non_yank_errno_is_ignored(self):
        m = self._monitor()
        exc = OSError(errno.EACCES, "Permission denied", "/tmp/cinemate-test-RAW/x")
        with patch.object(m, "_handle_unmount") as hu:
            handled = m._handle_storage_error(exc, action="count files on")
        self.assertFalse(handled)
        hu.assert_not_called()


if __name__ == "__main__":
    unittest.main()
