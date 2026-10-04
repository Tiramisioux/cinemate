"""module/lens/cef168.py: frame format, both backends, and finding the board.

The reference for everything byte-level is Pinefeat's own source (cef168.h,
cef168.c, calibrate.cpp at e3abfb2). The CRC is checked against an independent
implementation (the kernel's table-driven crc8_populate_msb), and one command
frame is pinned to the literal bytes calibrate.cpp hard-codes.

Bus discovery is tested against the hardware that actually exists: the CM4 dev
unit (sensor at ``imx477 0-001a``, lens at ``cef168 0-000d``, bus 0), and a Pi 5.
"""
import ast
import ctypes
import errno
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lens_fakes import FakeBackend, FakeSMBus, fake_smbus_module, frame  # noqa: E402

from module.lens import cef168  # noqa: E402
from module.lens.cef168 import (  # noqa: E402
    Cef168Error,
    Cef168Raw,
    Cef168Subdev,
    crc8,
    encode_command,
    parse_data,
)

ROOT = Path(__file__).resolve().parents[1]


def reference_crc8(data: bytes) -> int:
    """cef168.c: crc8_populate_msb(table, 168) then crc8(table, data, len, 0xFF)."""
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = ((crc << 1) ^ 168) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
        table.append(crc)
    crc = 0xFF
    for byte in data:
        crc = table[crc ^ byte]
    return crc


class Crc8Tests(unittest.TestCase):
    def test_matches_the_kernels_table_driven_crc(self):
        for sample in (b"", b"\x00", b"\x22\x00\x00", bytes(range(14)), b"\xff" * 14,
                       b"\x7a\xd4\x08"):
            self.assertEqual(crc8(sample), reference_crc8(sample), sample)

    def test_empty_input_is_the_initial_value(self):
        self.assertEqual(crc8(b""), 0xFF)

    def test_calibrate_frame_is_the_literal_calibrate_cpp_uses(self):
        # calibrate.cpp I2CDev::calibrate(): { INP_CALIBRATE, 0, 0, 0x30 }
        self.assertEqual(encode_command(cef168.INP_CALIBRATE, 0), bytes([0x22, 0, 0, 0x30]))


class FrameTests(unittest.TestCase):
    def _raw(self, flags=0, **fields):
        base = dict(lens_id=235, moving_time=210, pmin=0, pmax=1069, pcur=500,
                    dmin=100, dmax=65535)
        base.update(fields)
        body = struct.pack("<BBHHHHHH", base["lens_id"], flags, base["moving_time"],
                           base["pmin"], base["pmax"], base["pcur"], base["dmin"], base["dmax"])
        return body + bytes((reference_crc8(body),))

    def test_frame_is_fifteen_little_endian_bytes(self):
        raw = self._raw()
        self.assertEqual(len(raw), 15)
        data = parse_data(raw, check_crc=True)
        self.assertEqual((data.lens_id, data.moving_time, data.focus_position_min,
                          data.focus_position_max, data.focus_position_cur,
                          data.focus_distance_min, data.focus_distance_max),
                         (235, 210, 0, 1069, 500, 100, 65535))

    def test_flags_byte_is_moving_bit0_and_calibrating_bits_1_and_2(self):
        # GCC little-endian bitfields: moving:1 is the low bit, calibrating:2 the next two.
        self.assertFalse(parse_data(self._raw(flags=0b000)).moving)
        self.assertTrue(parse_data(self._raw(flags=0b001)).moving)
        self.assertEqual(parse_data(self._raw(flags=0b100)).calibrating, 2)
        both = parse_data(self._raw(flags=0b101))
        self.assertTrue(both.moving)
        self.assertEqual(both.calibrating, 2)
        self.assertEqual(parse_data(self._raw(flags=0b110)).calibrating, 3)

    def test_a_corrupted_frame_is_refused_when_the_crc_is_checked(self):
        raw = bytearray(self._raw())
        raw[5] ^= 0x01
        with self.assertRaises(Cef168Error) as caught:
            parse_data(bytes(raw), check_crc=True)
        self.assertIn("CRC", str(caught.exception))

    def test_the_subdev_path_trusts_the_kernels_crc_check(self):
        raw = bytearray(self._raw())
        raw[5] ^= 0x01
        self.assertEqual(parse_data(bytes(raw), check_crc=False).lens_id, 235)

    def test_a_short_frame_is_an_error_not_a_struct_error(self):
        with self.assertRaises(Cef168Error):
            parse_data(b"\x00" * 14, check_crc=False)

    def test_to_bytes_round_trips_with_a_valid_crc(self):
        original = frame(moving=True, calibrating=2, moving_time=98)
        again = parse_data(original.to_bytes(), check_crc=True)
        self.assertEqual((again.moving, again.calibrating, again.moving_time),
                         (True, 2, 98))

    def test_range_valid_distinguishes_a_stored_range_from_nothing(self):
        self.assertTrue(frame().range_valid)
        self.assertFalse(frame(focus_position_max=0).range_valid)
        self.assertFalse(frame(focus_position_max=32767).range_valid)


class CommandTests(unittest.TestCase):
    def test_aperture_command_carries_f_times_100_little_endian(self):
        # f/22.6 -> 2260 = 0x08D4
        raw = encode_command(cef168.INP_SET_APERTURE, cef168.iris_control_value(22.6))
        self.assertEqual(raw[:3], bytes([0x7A, 0xD4, 0x08]))
        self.assertEqual(raw[3], reference_crc8(raw[:3]))

    def test_iris_control_value_is_f_number_times_100(self):
        self.assertEqual(cef168.iris_control_value(2.8), 280)
        self.assertEqual(cef168.iris_control_value(1.8), 180)
        self.assertEqual(cef168.iris_control_value(22.6), 2260)

    def test_nonsense_apertures_are_refused(self):
        for bad in (0, -1.0, float("nan"), float("inf"), 700.0):
            with self.assertRaises(ValueError):
                cef168.iris_control_value(bad)

    def test_a_value_that_does_not_fit_sixteen_bits_is_refused(self):
        with self.assertRaises(ValueError):
            encode_command(cef168.INP_SET_FOCUS, 0x10000)
        with self.assertRaises(ValueError):
            encode_command(cef168.INP_SET_FOCUS, -1)


class V4L2LayoutTests(unittest.TestCase):
    """The ctypes mirrors of the kernel structs, checked against the header
    (raspberrypi/linux rpi-6.12.y, videodev2.h) for the arch this runs on."""

    def test_custom_control_ids_are_cef168_h_s(self):
        self.assertEqual(cef168.CID_LENS_ID, 0x009809A8)
        self.assertEqual(cef168.CID_DATA, 0x009809A9)
        self.assertEqual(cef168.CID_CALIBRATE, 0x009809AA)

    def test_standard_control_ids(self):
        self.assertEqual(cef168.V4L2_CID_FOCUS_ABSOLUTE, 0x009A090A)
        self.assertEqual(cef168.V4L2_CID_FOCUS_RELATIVE, 0x009A090B)
        self.assertEqual(cef168.V4L2_CID_IRIS_ABSOLUTE, 0x009A0911)
        self.assertEqual(cef168.V4L2_CID_IRIS_RELATIVE, 0x009A0912)

    def test_ext_control_is_packed_to_twenty_bytes(self):
        # __attribute__((packed)): id, size, reserved2[1], then the union at offset 12.
        self.assertEqual(ctypes.sizeof(cef168._V4L2ExtControl), 20)
        self.assertEqual(cef168._V4L2ExtControl.u.offset, 12)

    def test_ext_control_bytes_match_the_c_layout(self):
        if ctypes.sizeof(ctypes.c_void_p) != 8 or sys.byteorder != "little":
            self.skipTest("byte-level check is written for 64-bit little endian")
        ext = cef168._V4L2ExtControl()
        ext.id, ext.size = 0x009809A9, 15
        ext.u.ptr = 0x1122334455667788
        self.assertEqual(bytes(ext), struct.pack("<III", 0x009809A9, 15, 0)
                         + struct.pack("<Q", 0x1122334455667788))

    def test_ext_controls_is_not_packed(self):
        # which, count, error_idx, request_fd, reserved[1], then an aligned pointer.
        pointer = ctypes.sizeof(ctypes.c_void_p)
        self.assertEqual(ctypes.sizeof(cef168._V4L2ExtControls), 24 if pointer == 4 else 32)
        self.assertEqual(cef168._V4L2ExtControls.controls.offset, 20 if pointer == 4 else 24)

    def test_ioctl_numbers(self):
        self.assertEqual(cef168.VIDIOC_S_CTRL, 0xC008561C)
        self.assertEqual(cef168.VIDIOC_G_CTRL, 0xC008561B)
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            self.assertEqual(cef168.VIDIOC_G_EXT_CTRLS, 0xC0205647)


class FakeKernel:
    """Stands in for fcntl.ioctl on a subdev: records S_CTRL, answers G_EXT_CTRLS."""

    def __init__(self, data_bytes: bytes = b"", error: OSError | None = None):
        self.data_bytes = data_bytes
        self.error = error
        self.set_ctrls = []
        self.opened = []
        self.closed = []

    def ioctl(self, fd, request, arg):
        if self.error is not None:
            raise self.error
        if request == cef168.VIDIOC_S_CTRL:
            self.set_ctrls.append((arg.id, arg.value))
        elif request == cef168.VIDIOC_G_EXT_CTRLS:
            assert arg.which == cef168.V4L2_CTRL_CLASS_USER
            assert arg.count == 1
            control = arg.controls[0]
            assert control.id == cef168.CID_DATA
            assert control.size == 15
            ctypes.memmove(control.u.ptr, self.data_bytes, 15)
        else:  # pragma: no cover
            raise AssertionError(f"unexpected ioctl {request:#x}")


class SubdevBackendTests(unittest.TestCase):
    def _backend(self, kernel, **kwargs):
        return Cef168Subdev(
            "/dev/v4l-subdev1", bus=0, port="cam0",
            opener=lambda path, flags: (kernel.opened.append(path), 7)[1],
            closer=kernel.closed.append, ioctl=kernel.ioctl, **kwargs)

    def test_read_data_reads_the_data_control_through_extended_controls(self):
        kernel = FakeKernel(frame(lens_id=112, focus_position_cur=321).to_bytes())
        data = self._backend(kernel).read_data()
        self.assertEqual((data.lens_id, data.focus_position_cur), (112, 321))

    def test_iris_is_an_absolute_write_of_f_times_100(self):
        kernel = FakeKernel()
        self._backend(kernel).set_iris(2.8)
        self.assertEqual(kernel.set_ctrls, [(cef168.V4L2_CID_IRIS_ABSOLUTE, 280)])

    def test_focus_is_an_absolute_write(self):
        kernel = FakeKernel()
        self._backend(kernel).set_focus(640)
        self.assertEqual(kernel.set_ctrls, [(cef168.V4L2_CID_FOCUS_ABSOLUTE, 640)])

    def test_calibrate_presses_the_calibrate_button(self):
        kernel = FakeKernel()
        self._backend(kernel).calibrate()
        self.assertEqual(kernel.set_ctrls, [(cef168.CID_CALIBRATE, 0)])

    def test_an_ioctl_failure_is_a_cef168_error_carrying_errno(self):
        kernel = FakeKernel(error=OSError(errno.EIO, "I/O error"))
        backend = self._backend(kernel)
        with self.assertRaises(Cef168Error) as caught:
            backend.read_data()
        self.assertEqual(caught.exception.errno, errno.EIO)
        with self.assertRaises(Cef168Error):
            backend.set_iris(2.8)

    def test_provenance_and_description(self):
        backend = self._backend(FakeKernel())
        self.assertEqual(backend.provenance, "v4l2-subdev")
        self.assertIn("i2c-0", backend.describe())
        self.assertIn("cef168 subdev", backend.describe())

    def test_close_is_idempotent_and_blocks_further_use(self):
        kernel = FakeKernel()
        backend = self._backend(kernel)
        backend.close()
        backend.close()
        self.assertEqual(kernel.closed, [7])
        with self.assertRaises(Cef168Error):
            backend.set_iris(2.8)

    def test_an_unopenable_node_is_a_cef168_error(self):
        def refuse(path, flags):
            raise PermissionError(errno.EACCES, "denied")
        with self.assertRaises(Cef168Error):
            Cef168Subdev("/dev/v4l-subdev1", opener=refuse, ioctl=lambda *a: None)


class RawBackendTests(unittest.TestCase):
    def _backend(self, board=None, **kwargs):
        board = board or FakeSMBus(0)
        board.frame_bytes = frame(lens_id=112).to_bytes()
        backend = Cef168Raw(0, port="cam0", bus_source="sensor-subdev",
                            smbus_module=fake_smbus_module(board), sleep=lambda s: None,
                            **kwargs)
        return backend, board

    def test_read_is_a_crc_checked_fifteen_byte_frame(self):
        backend, _ = self._backend()
        self.assertEqual(backend.read_data().lens_id, 112)

    def test_a_bad_crc_is_refused(self):
        backend, board = self._backend()
        bad = bytearray(board.frame_bytes)
        bad[-1] ^= 0xFF
        board.frame_bytes = bytes(bad)
        with self.assertRaises(Cef168Error):
            backend.read_data()

    def test_iris_writes_the_four_byte_command_frame(self):
        backend, board = self._backend()
        backend.set_iris(2.8)
        self.assertEqual(board.writes, [encode_command(cef168.INP_SET_APERTURE, 280)])

    def test_focus_and_calibrate_frames(self):
        backend, board = self._backend()
        backend.set_focus(1000)
        backend.calibrate()
        self.assertEqual(board.writes, [encode_command(cef168.INP_SET_FOCUS, 1000),
                                        bytes([0x22, 0, 0, 0x30])])

    def test_a_busy_board_is_retried_like_the_kernel_driver_retries(self):
        backend, board = self._backend()
        board.errors = [OSError(errno.EIO, "nack"), OSError(121, "remote io")]
        backend.set_iris(4.0)
        self.assertEqual(len(board.writes), 1)

    def test_three_failures_in_a_row_are_an_error(self):
        backend, board = self._backend()
        board.errors = [OSError(errno.EIO, "nack")] * 3
        with self.assertRaises(Cef168Error):
            backend.set_iris(4.0)

    def test_an_error_that_is_not_a_nack_is_not_retried(self):
        backend, board = self._backend()
        board.errors = [OSError(errno.ENODEV, "gone"), OSError(errno.EIO, "unused")]
        with self.assertRaises(Cef168Error):
            backend.set_iris(4.0)
        self.assertEqual(len(board.errors), 1)

    def test_a_read_failure_is_a_cef168_error(self):
        backend, board = self._backend()
        board.errors = [OSError(errno.EIO, "nack")]
        with self.assertRaises(Cef168Error):
            backend.read_data()

    def test_missing_smbus2_is_a_cef168_error_not_an_import_error(self):
        original = cef168._smbus2
        cef168._smbus2 = lambda: None
        try:
            with self.assertRaises(Cef168Error) as caught:
                Cef168Raw(0)
        finally:
            cef168._smbus2 = original
        self.assertIn("smbus2", str(caught.exception))

    def test_close_releases_the_bus_once(self):
        backend, board = self._backend()
        backend.close()
        backend.close()
        self.assertTrue(board.closed)
        with self.assertRaises(Cef168Error):
            backend.read_data()

    def test_provenance(self):
        backend, _ = self._backend()
        self.assertEqual(backend.provenance, "i2c-raw")


# ── discovery ───────────────────────────────────────────────────────────────

def make_sysfs(tmp: Path, names: dict[int, str]) -> tuple[str, str]:
    """A /sys/class/video4linux with v4l-subdevN/name files; returns (sysfs, dev)."""
    sysfs = tmp / "video4linux"
    for number, name in names.items():
        node = sysfs / f"v4l-subdev{number}"
        node.mkdir(parents=True)
        (node / "name").write_text(name + "\n")
    return str(sysfs), "/dev"


# What the CM4 dev unit reported (kernel 6.12.96, dtoverlay=imx477,cam0).
CM4_SUBDEVS = {0: "imx477 0-001a", 1: "cef168 0-000d"}
CM4_CAMERAS = [{"index": 0, "model": "imx477", "mono": False, "port": "cam0"}]


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_cm4_lens_subdev_gives_bus_zero(self):
        sysfs, dev = make_sysfs(self.tmp, CM4_SUBDEVS)
        found = cef168.find_subdevs(sysfs, dev)
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].path, found[0].bus, found[0].address),
                         ("/dev/v4l-subdev1", 0, 0x0D))

    def test_the_port_is_filled_from_the_platform_table_when_asked(self):
        sysfs, dev = make_sysfs(self.tmp, CM4_SUBDEVS)
        self.assertEqual(cef168.find_subdevs(sysfs, dev)[0].port, "")
        self.assertEqual(cef168.find_subdevs(sysfs, dev, platform="pi4")[0].port, "cam0")
        self.assertEqual(cef168.find_subdevs(sysfs, dev, platform="pi5")[0].port, "")

    def test_pi5_lens_subdev_gives_its_own_bus(self):
        sysfs, dev = make_sysfs(self.tmp, {0: "imx585 6-001a", 1: "cef168 6-000d"})
        self.assertEqual([s.bus for s in cef168.find_subdevs(sysfs, dev)], [6])

    def test_sensor_subdevs_are_listed_but_are_not_lens_subdevs(self):
        sysfs, dev = make_sysfs(self.tmp, CM4_SUBDEVS)
        self.assertEqual([s.model for s in cef168.list_subdevs(sysfs, dev)], ["imx477", "cef168"])

    def test_oddly_named_entries_are_skipped_not_fatal(self):
        sysfs, dev = make_sysfs(self.tmp, {0: "something else", 1: "cef168 0-000d", 2: ""})
        self.assertEqual(len(cef168.list_subdevs(sysfs, dev)), 1)

    def test_a_missing_sysfs_is_an_empty_list(self):
        self.assertEqual(cef168.list_subdevs(str(self.tmp / "nope")), [])

    def test_a_cef168_at_another_address_is_not_the_lens_board(self):
        sysfs, dev = make_sysfs(self.tmp, {0: "cef168 0-0050"})
        self.assertEqual(cef168.find_subdevs(sysfs, dev), [])

    def test_the_pi5_row_matches_ir_filters_table(self):
        # ir_filter imports smbus and redis at module top, so it cannot be
        # imported for its table; this pins the copy against its source.
        tree = ast.parse((ROOT / "src" / "module" / "ir_filter.py").read_text())
        table = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "CAM_PORT_TO_BUS" for t in node.targets):
                table = ast.literal_eval(node.value)
        self.assertEqual(cef168.PLATFORM_CAM_BUSES["pi5"], table)

    def test_the_pi4_table_does_not_guess_cam1(self):
        self.assertEqual(cef168.PLATFORM_CAM_BUSES["pi4"], {"cam0": 0})


class OpenAdapterTests(unittest.TestCase):
    """open_adapter: which bus, how it was derived, subdev before raw."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.subdev_calls = []
        self.raw_calls = []
        self.answers = True            # does the board answer a read?
        self.raw_raises: Cef168Error | None = None

    def _subdev_factory(self, path, **kwargs):
        self.subdev_calls.append((path, kwargs))
        backend = FakeBackend(provenance="v4l2-subdev", bus=kwargs.get("bus"),
                              port=kwargs.get("port", ""), bus_source=kwargs.get("bus_source", ""))
        if not self.answers:
            backend.read_fails_forever = True
        return backend

    def _raw_factory(self, bus, **kwargs):
        self.raw_calls.append((bus, kwargs))
        if self.raw_raises is not None:
            raise self.raw_raises
        backend = FakeBackend(provenance="i2c-raw", bus=bus, port=kwargs.get("port", ""),
                              bus_source=kwargs.get("bus_source", ""))
        if not self.answers:
            backend.read_fails_forever = True
        return backend

    def _open(self, names, port=None, cameras=None, platform="pi4"):
        sysfs, dev = make_sysfs(self.tmp / str(len(list(self.tmp.iterdir()))), names)
        return cef168.open_adapter(
            port, cameras=cameras, platform=platform, sysfs_root=sysfs, dev_root=dev,
            subdev_factory=self._subdev_factory, raw_factory=self._raw_factory,
            sleep=lambda s: None)

    # -- the CM4 dev unit ----------------------------------------------------

    def test_cm4_with_the_driver_bound_uses_the_subdev_on_bus_zero(self):
        backend, reason = self._open(CM4_SUBDEVS, cameras=CM4_CAMERAS)
        self.assertEqual(reason, "")
        self.assertEqual(backend.provenance, "v4l2-subdev")
        self.assertEqual(self.subdev_calls[0][0], "/dev/v4l-subdev1")
        self.assertEqual((backend.bus, backend.port, backend.bus_source),
                         (0, "cam0", "cef168-subdev"))
        self.assertEqual(self.raw_calls, [])

    def test_cm4_subdev_wins_even_without_a_camera_list(self):
        backend, _ = self._open(CM4_SUBDEVS, cameras=None)
        self.assertEqual(backend.provenance, "v4l2-subdev")
        self.assertEqual(backend.bus, 0)
        # No sensor pairing to name the port, but the platform table knows bus 0.
        self.assertEqual(backend.port, "cam0")

    def test_cm4_without_the_driver_derives_the_bus_from_the_sensor_subdev(self):
        backend, reason = self._open({0: "imx477 0-001a"}, cameras=CM4_CAMERAS)
        self.assertEqual(reason, "")
        self.assertEqual(backend.provenance, "i2c-raw")
        self.assertEqual(self.raw_calls[0][0], 0)
        self.assertEqual((backend.bus, backend.port, backend.bus_source),
                         (0, "cam0", "sensor-subdev"))

    def test_sensor_derivation_beats_the_platform_table(self):
        # A sensor on bus 3 says bus 3 whatever the table thinks cam0 is.
        backend, _ = self._open({0: "imx477 3-001a"}, cameras=CM4_CAMERAS, platform="pi4")
        self.assertEqual((backend.bus, backend.bus_source), (3, "sensor-subdev"))

    def test_with_nothing_else_the_cm4_table_gives_cam0_bus_zero(self):
        backend, _ = self._open({}, cameras=[], platform="pi4")
        self.assertEqual((backend.bus, backend.port, backend.bus_source),
                         (0, "cam0", "platform-table"))
        self.assertEqual([call[0] for call in self.raw_calls], [0])    # cam1 not guessed

    def test_cam1_on_a_pi4_is_unknown_not_guessed(self):
        backend, reason = self._open({}, port="cam1", cameras=[], platform="pi4")
        self.assertIsNone(backend)
        self.assertEqual(self.raw_calls, [])
        self.assertIn("cam1", reason)
        self.assertIn("not known", reason)

    def test_a_camera_of_another_model_does_not_pair_with_the_sensor(self):
        cameras = [{"model": "imx585", "port": "cam0"}]
        backend, _ = self._open({0: "imx477 3-001a"}, cameras=cameras, platform="pi4")
        self.assertEqual((backend.bus, backend.bus_source), (0, "platform-table"))

    def test_mono_and_wide_variants_pair_with_the_silicon_name(self):
        cameras = [{"model": "imx585_mono", "port": "cam0"}]
        backend, _ = self._open({0: "imx585 5-001a"}, cameras=cameras, platform="pi5")
        self.assertEqual((backend.bus, backend.bus_source), (5, "sensor-subdev"))

    # -- Pi 5 ---------------------------------------------------------------

    def test_pi5_table_gives_cam0_6_and_cam1_4(self):
        self.answers = False
        backend, reason = self._open({}, cameras=[], platform="pi5")
        self.assertIsNone(backend)
        self.assertEqual([call[0] for call in self.raw_calls], [6, 4])
        self.assertIn("i2c-6", reason)
        self.assertIn("i2c-4", reason)

    def test_two_identical_sensors_are_paired_through_the_table(self):
        cameras = [{"model": "imx585", "port": "cam0"}, {"model": "imx585", "port": "cam1"}]
        names = {0: "imx585 6-001a", 1: "imx585 4-001a"}
        self.answers = False
        self._open(names, port="cam1", cameras=cameras, platform="pi5")
        self.assertEqual(self.raw_calls[0][0], 4)

    def test_two_identical_sensors_on_an_unknown_platform_stay_unpaired(self):
        cameras = [{"model": "imx585", "port": "cam0"}, {"model": "imx585", "port": "cam1"}]
        names = {0: "imx585 6-001a", 1: "imx585 4-001a"}
        backend, reason = self._open(names, port="cam0", cameras=cameras, platform="other")
        self.assertIsNone(backend)
        self.assertIn("not known", reason)

    def test_a_port_filter_skips_the_other_ports_subdev(self):
        names = {0: "imx585 6-001a", 1: "cef168 6-000d", 2: "imx585 4-001a"}
        cameras = [{"model": "imx585", "port": "cam0"}, {"model": "imx585", "port": "cam1"}]
        self.answers = False
        self._open(names, port="cam1", cameras=cameras, platform="pi5")
        self.assertEqual(self.subdev_calls, [])
        self.assertEqual(self.raw_calls[0][0], 4)

    # -- failure shapes ------------------------------------------------------

    def test_a_bound_driver_with_no_board_is_reported_and_raw_is_not_tried_on_it(self):
        # F4: the driver's probe does no I/O, so the subdev exists with no board fitted.
        self.answers = False
        backend, reason = self._open(CM4_SUBDEVS, cameras=CM4_CAMERAS, platform="pi4")
        self.assertIsNone(backend)
        self.assertIn("did not answer", reason)
        self.assertIn("/dev/v4l-subdev1", reason)
        self.assertEqual(self.raw_calls, [])

    def test_no_adapter_on_the_bus_says_which_bus_and_how_it_was_found(self):
        self.answers = False
        backend, reason = self._open({0: "imx477 0-001a"}, cameras=CM4_CAMERAS)
        self.assertIsNone(backend)
        self.assertIn("i2c-0", reason)
        self.assertIn("sensor subdev", reason)

    def test_missing_smbus2_comes_back_as_a_reason(self):
        self.raw_raises = Cef168Error("smbus2 is not installed")
        backend, reason = self._open({}, cameras=[], platform="pi4")
        self.assertIsNone(backend)
        self.assertIn("smbus2 is not installed", reason)

    def test_a_single_failed_read_is_retried_before_giving_up(self):
        reads = {"n": 0}

        def flaky_factory(bus, **kwargs):
            backend = FakeBackend(provenance="i2c-raw", bus=bus, port=kwargs.get("port", ""))
            backend.read_errors = 1
            reads["n"] += 1
            return backend

        sysfs, dev = make_sysfs(self.tmp / "flaky", {})
        backend, reason = cef168.open_adapter(
            "cam0", cameras=[], platform="pi4", sysfs_root=sysfs, dev_root=dev,
            raw_factory=flaky_factory, sleep=lambda s: None)
        self.assertIsNotNone(backend)
        self.assertEqual(reason, "")

    def test_a_probe_that_fails_closes_the_backend(self):
        closed = []

        def factory(bus, **kwargs):
            backend = FakeBackend(provenance="i2c-raw", bus=bus)
            backend.read_fails_forever = True
            backend.close = lambda: closed.append(bus)
            return backend

        sysfs, dev = make_sysfs(self.tmp / "closing", {})
        cef168.open_adapter("cam0", cameras=[], platform="pi4", sysfs_root=sysfs,
                            dev_root=dev, raw_factory=factory, sleep=lambda s: None)
        self.assertEqual(closed, [0])

    def test_an_unknown_port_name_is_refused(self):
        backend, reason = self._open({}, port="cam7")
        self.assertIsNone(backend)
        self.assertIn("cam7", reason)

    def test_description_reports_the_bus_and_how_it_was_derived(self):
        backend, _ = self._open({0: "imx477 0-001a"}, cameras=CM4_CAMERAS)
        text = backend.describe()
        self.assertIn("cam0", text)
        self.assertIn("i2c-0", text)
        self.assertIn("sensor subdev", text)


if __name__ == "__main__":
    unittest.main()
