"""Talking to the Pinefeat CEF168 lens board: frame format, two backends, discovery.

The board is an I2C device at 0x0d on the *camera's* I2C bus. It answers a plain
15-byte read (lens state) and takes 4-byte command frames (focus, iris,
calibrate). Pinefeat's kernel driver (cef168.ko) wraps exactly that in V4L2
controls, but the board is fully drivable without it -- calibrate.cpp's I2CDev
class is the reference -- so there are two backends behind one interface:

* ``Cef168Subdev``  -- V4L2 controls on the lens subdev, when the driver is bound
* ``Cef168Raw``     -- raw I2C (smbus2 ``i2c_rdwr``), when it is not

``open_adapter()`` picks one: "subdev if it exists, else raw" (PLAN D2). It is
*not* "raw until EBUSY": ``I2C_RDWR`` skips i2c-dev's address-busy check, so a
raw read works even with the driver bound. The rule is about which path the
operator's other tools (libcamera autofocus) are using, not about what the
kernel allows. The driver's probe does no I2C I/O (F4), so a subdev can exist
with no board fitted; presence therefore needs a real CRC-checked read, never
just the existence of a device node.

Which bus? Not a constant. ``ir_filter.CAM_PORT_TO_BUS`` (cam0 -> 6, cam1 -> 4)
is the Raspberry Pi 5 wiring; a CM4 measured 2026-10-04 has the sensor at
``imx477 0-001a`` and the lens at ``cef168 0-000d`` -- bus 0. So the bus is
derived, in this order, and the order is reported with the answer:

1. a ``cef168 N-000d`` subdev exists            -> bus N        ("cef168-subdev")
2. else the *sensor* subdev on that port        -> bus N        ("sensor-subdev")
   (name ``<model> N-00xx``, paired with CineMate's Redis CAMERAS entry for the
   port, because the lens sits on the sensor's own bus)
3. else a per-platform table (Pi 5 only, below) -> bus          ("platform-table")

Where none of those answers (cam1 on a Pi 4 / CM4, whose second port CineMate
does not drive) the reason says "unknown" rather than guessing a bus: a guessed
raw probe on someone else's I2C bus is not a harmless thing to do.

This module imports nothing outside the standard library at module level
(``smbus2`` lazily, guarded like ``app/hardware_probe._smbus``), so a desktop
checkout imports it. ``ir_filter`` cannot be imported for its table -- it needs
``smbus`` and ``redis`` at module top -- so the Pi 5 row is a copy, and
``_test/test_lens_cef168.py`` pins it against ``ir_filter.py``'s source.
"""
from __future__ import annotations

import ctypes
import errno
import logging
import math
import os
import re
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

try:  # POSIX only; a checkout on anything else must still import
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

logger = logging.getLogger(__name__)

# ── Board constants (cef168.h) ──────────────────────────────────────────────

I2C_ADDRESS = 0x0D
FRAME_LENGTH = 15            # struct cef168_data, __packed
INFINITY_CM = 65535          # focus_distance_* of 655.35 m means "infinity"

CRC8_POLYNOMIAL = 168        # 0xA8, MSB-first
CRC8_INIT = 0xFF

INP_CALIBRATE = 0x22
INP_SET_FOCUS = 0x80
INP_SET_FOCUS_P = 0x81
INP_SET_FOCUS_N = 0x82
INP_SET_APERTURE = 0x7A
INP_SET_APERTURE_P = 0x7B
INP_SET_APERTURE_N = 0x7C

# Value of `calibrating` while the board sweeps and reports distances
# (calibrate.cpp only records PWL points at exactly 2). Any non-zero value
# means "calibration in progress".
CALIBRATING_SWEEP = 2

# What the board reports for "no lens mounted". PLAN G0.4 predicts lens_id != 0
# with a lens and a failed read (EIO) with the board unplugged; whether a board
# with no lens reads 0 is the part still to confirm on hardware, so it is a
# set, in one place.
NO_LENS_IDS = frozenset({0})

# ── V4L2 (include/uapi/linux/videodev2.h, v4l2-controls.h) ─────────────────

V4L2_CTRL_CLASS_USER = 0x00980000
V4L2_CID_USER_BASE = V4L2_CTRL_CLASS_USER | 0x900
V4L2_CID_CAMERA_CLASS_BASE = 0x009A0000 | 0x900
V4L2_CID_FOCUS_ABSOLUTE = V4L2_CID_CAMERA_CLASS_BASE + 10
V4L2_CID_FOCUS_RELATIVE = V4L2_CID_CAMERA_CLASS_BASE + 11
V4L2_CID_IRIS_ABSOLUTE = V4L2_CID_CAMERA_CLASS_BASE + 17
V4L2_CID_IRIS_RELATIVE = V4L2_CID_CAMERA_CLASS_BASE + 18

# cef168.h: CEF168_V4L2_CID_CUSTOM(ctrl) = (V4L2_CID_USER_BASE | 168) + custom_<ctrl>
_CEF168_CID_BASE = V4L2_CID_USER_BASE | 168
CID_LENS_ID = _CEF168_CID_BASE + 0      # 0x009809a8
CID_DATA = _CEF168_CID_BASE + 1         # 0x009809a9, u8[15]
CID_CALIBRATE = _CEF168_CID_BASE + 2    # 0x009809aa, button


class _V4L2Control(ctypes.Structure):
    """struct v4l2_control."""
    _fields_ = [("id", ctypes.c_uint32), ("value", ctypes.c_int32)]


class _V4L2ExtControlValue(ctypes.Union):
    """The anonymous union in struct v4l2_ext_control. It is 8 bytes on both
    32- and 64-bit userland (it holds a __s64), which is what keeps the
    enclosing struct at 20 bytes either way -- a flat c_void_p would make it
    16 on 32-bit."""
    _pack_ = 1
    _fields_ = [
        ("value", ctypes.c_int32),
        ("value64", ctypes.c_int64),
        ("ptr", ctypes.c_void_p),
    ]


class _V4L2ExtControl(ctypes.Structure):
    """struct v4l2_ext_control. The kernel header marks it (and its union)
    ``__attribute__((packed))`` -- verified against raspberrypi/linux
    rpi-6.12.y videodev2.h, 2026-10-04 -- so id/size/reserved2 are followed by
    the union at offset 12 with no padding: 20 bytes."""
    _pack_ = 1
    _fields_ = [
        ("id", ctypes.c_uint32),
        ("size", ctypes.c_uint32),
        ("reserved2", ctypes.c_uint32 * 1),
        ("u", _V4L2ExtControlValue),
    ]


class _V4L2ExtControls(ctypes.Structure):
    """struct v4l2_ext_controls. NOT packed: the trailing pointer is aligned,
    so it is 32 bytes on a 64-bit userland and 24 on a 32-bit one. ctypes'
    natural alignment reproduces the C layout on whichever arch this runs on."""
    _fields_ = [
        ("which", ctypes.c_uint32),          # the union with ctrl_class
        ("count", ctypes.c_uint32),
        ("error_idx", ctypes.c_uint32),
        ("request_fd", ctypes.c_int32),
        ("reserved", ctypes.c_uint32 * 1),
        ("controls", ctypes.POINTER(_V4L2ExtControl)),
    ]


def _iowr(type_char: str, number: int, size: int) -> int:
    """_IOWR() for the Linux generic ioctl encoding (x86, arm, arm64 -- every
    Raspberry Pi). dir<<30 | size<<16 | type<<8 | nr, with dir = read|write."""
    return ((1 | 2) << 30) | (size << 16) | (ord(type_char) << 8) | number


VIDIOC_G_CTRL = _iowr("V", 27, ctypes.sizeof(_V4L2Control))
VIDIOC_S_CTRL = _iowr("V", 28, ctypes.sizeof(_V4L2Control))
VIDIOC_G_EXT_CTRLS = _iowr("V", 71, ctypes.sizeof(_V4L2ExtControls))

# ── Frame format ────────────────────────────────────────────────────────────

# u8 lens_id; u8 flags{moving:1, calibrating:2}; u16 moving_time;
# u16 position_min, position_max, position_cur; u16 distance_min, distance_max;
# u8 crc8 -- little endian, no padding (__packed).
_FRAME = struct.Struct("<BBHHHHHHB")
assert _FRAME.size == FRAME_LENGTH


class Cef168Error(OSError):
    """Any failure talking to the adapter: bus I/O, a bad CRC, a short frame.

    An OSError subclass so that code written against the bus layer's own
    exceptions keeps working, but the backends convert everything to this, so a
    caller only ever has to catch one type.
    """


def _wrap(exc: BaseException, what: str) -> Cef168Error:
    err = Cef168Error(f"{what}: {exc}")
    err.errno = getattr(exc, "errno", None)
    return err


def crc8(data: bytes, crc: int = CRC8_INIT) -> int:
    """CRC-8, MSB first, polynomial 168 (0xA8), initial value 0xFF.

    The board checks this on every command it receives and appends it to every
    frame it sends (calibrate.cpp ``crc8_msb``; cef168.c ``crc8_populate_msb``).
    """
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ CRC8_POLYNOMIAL) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def encode_command(cmd: int, value: int = 0) -> bytes:
    """One 4-byte command frame: ``{cmd, value lo, value hi, crc8(first 3)}``.

    ``value`` is an unsigned 16-bit integer (aperture is f-number x 100; the
    relative commands carry the magnitude and the sign is in the command byte).
    """
    value = int(value)
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"command value {value} does not fit in 16 bits")
    head = bytes((cmd & 0xFF, value & 0xFF, (value >> 8) & 0xFF))
    return head + bytes((crc8(head),))


@dataclass(frozen=True)
class Cef168Data:
    """One decoded board frame (struct cef168_data).

    ``moving`` is the board's "lens motor is active" flag and ``calibrating`` is
    its two-bit calibration state (0 = idle). Distances are centimetres, and
    ``INFINITY_CM`` means infinity. ``focus_position_min/max`` is the range the
    board stored for this lens id at its last calibration (F9); on a lens that
    was never calibrated it is not a usable range (see ``range_valid``).
    """
    lens_id: int
    moving: bool
    calibrating: int
    moving_time: int
    focus_position_min: int
    focus_position_max: int
    focus_position_cur: int
    focus_distance_min: int
    focus_distance_max: int
    crc8: int = 0

    @property
    def position_span(self) -> int:
        return self.focus_position_max - self.focus_position_min

    @property
    def range_valid(self) -> bool:
        """True when the board holds a plausible focus range for this lens.

        Pinefeat's troubleshooting guide: a focus range max of 0 or 32767 means
        the lens was never calibrated. 32767 is the V4L2 control's default
        ceiling, so it can only appear in the *control's* range, but it is cheap
        to refuse here as well.
        """
        return 0 < self.position_span < 32767

    def to_bytes(self) -> bytes:
        """Encode back to a wire frame with a correct CRC (for fakes and tests)."""
        flags = (1 if self.moving else 0) | ((self.calibrating & 0x3) << 1)
        body = _FRAME.pack(
            self.lens_id & 0xFF, flags, self.moving_time,
            self.focus_position_min, self.focus_position_max, self.focus_position_cur,
            self.focus_distance_min, self.focus_distance_max, 0,
        )[:-1]
        return body + bytes((crc8(body),))


def parse_data(raw: bytes, check_crc: bool = True) -> Cef168Data:
    """Decode a 15-byte board frame.

    ``check_crc`` is True for the raw backend. The subdev backend passes False:
    the kernel driver already verified the CRC (and returned EIO on a mismatch)
    before it copied the frame into the control.
    """
    raw = bytes(raw)
    if len(raw) != FRAME_LENGTH:
        raise Cef168Error(f"expected a {FRAME_LENGTH}-byte frame, got {len(raw)} bytes")
    if check_crc:
        computed = crc8(raw[:-1])
        if computed != raw[-1]:
            raise Cef168Error(
                f"CRC mismatch (computed 0x{computed:02x}, read 0x{raw[-1]:02x})"
            )
    (lens_id, flags, moving_time, pos_min, pos_max, pos_cur,
     dist_min, dist_max, crc) = _FRAME.unpack(raw)
    return Cef168Data(
        lens_id=lens_id,
        moving=bool(flags & 0x1),
        calibrating=(flags >> 1) & 0x3,
        moving_time=moving_time,
        focus_position_min=pos_min,
        focus_position_max=pos_max,
        focus_position_cur=pos_cur,
        focus_distance_min=dist_min,
        focus_distance_max=dist_max,
        crc8=crc,
    )


def iris_control_value(fnum: float) -> int:
    """f-number -> the board's aperture value (f x 100, as an integer).

    Out-of-range values are NOT clamped here: the lens silently ignores them
    (F8), and the caller knows the entry's range, this layer does not.
    """
    fnum = float(fnum)
    if not math.isfinite(fnum) or fnum <= 0 or fnum * 100 > 0xFFFF:
        raise ValueError(f"f-number {fnum!r} is not a valid aperture")
    return int(round(fnum * 100))


# ── Backends ────────────────────────────────────────────────────────────────

BUS_SOURCE_LABELS = {
    "cef168-subdev": "from the cef168 subdev name",
    "sensor-subdev": "from the camera's sensor subdev",
    "platform-table": "from the per-platform table",
}


def describe_bus(bus: Optional[int], source: str) -> str:
    """'i2c-0, from the cef168 subdev name' -- what status() and LENS_MESSAGE show."""
    if bus is None:
        return "bus unknown"
    label = BUS_SOURCE_LABELS.get(source, source)
    return f"i2c-{bus}, {label}" if label else f"i2c-{bus}"


class Cef168Backend:
    """The one interface both backends implement.

    Not thread-safe: LensController serialises every call behind one lock.
    Every failure surfaces as ``Cef168Error``.
    """

    provenance = ""
    bus: Optional[int] = None
    port: str = ""
    bus_source: str = ""

    def read_data(self) -> Cef168Data:  # pragma: no cover - interface
        raise NotImplementedError

    def set_iris(self, fnum: float) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def set_focus(self, position: int) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def calibrate(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def describe(self) -> str:
        where = self.port or "unknown port"
        return f"{where} ({describe_bus(self.bus, self.bus_source)}), {self.provenance}"


class Cef168Subdev(Cef168Backend):
    """V4L2 controls on the lens subdev (``/dev/v4l-subdevN``), driver bound.

    Focus, iris and the calibrate button are ``VIDIOC_S_CTRL``; the 15-byte
    ``data`` array control is read with ``VIDIOC_G_EXT_CTRLS`` (the same two
    ioctls calibrate.cpp's V4L2SubDev uses). No dependency beyond ctypes and
    fcntl.
    """

    provenance = "v4l2-subdev"

    def __init__(self, path: str, *, bus: Optional[int] = None, port: str = "",
                 bus_source: str = "cef168-subdev",
                 opener: Callable[[str, int], int] = os.open,
                 closer: Callable[[int], None] = os.close,
                 ioctl: Optional[Callable[..., Any]] = None):
        self.path = str(path)
        self.bus = bus
        self.port = port
        self.bus_source = bus_source
        self._closer = closer
        self._ioctl = ioctl if ioctl is not None else getattr(fcntl, "ioctl", None)
        if self._ioctl is None:
            raise Cef168Error("fcntl.ioctl is not available on this platform")
        try:
            self._fd: Optional[int] = opener(self.path, os.O_RDWR)
        except OSError as exc:
            raise _wrap(exc, f"cannot open {self.path}") from exc

    def _fd_or_raise(self) -> int:
        if self._fd is None:
            raise Cef168Error(f"{self.path} is closed")
        return self._fd

    def _set_ctrl(self, cid: int, value: int, what: str) -> None:
        ctrl = _V4L2Control(id=cid, value=int(value))
        try:
            self._ioctl(self._fd_or_raise(), VIDIOC_S_CTRL, ctrl)
        except OSError as exc:
            raise _wrap(exc, f"{what} on {self.path} failed") from exc

    def read_data(self) -> Cef168Data:
        fd = self._fd_or_raise()
        buf = (ctypes.c_uint8 * FRAME_LENGTH)()
        ext = _V4L2ExtControl()
        ext.id = CID_DATA
        ext.size = FRAME_LENGTH
        ext.u.ptr = ctypes.addressof(buf)
        request = _V4L2ExtControls()
        request.which = V4L2_CTRL_CLASS_USER
        request.count = 1
        request.controls = ctypes.pointer(ext)
        try:
            self._ioctl(fd, VIDIOC_G_EXT_CTRLS, request)
        except OSError as exc:
            # The driver returns -EIO when the board does not answer or fails
            # its own CRC check -- the "no board fitted" signature (F4).
            raise _wrap(exc, f"reading the data control on {self.path} failed") from exc
        return parse_data(bytes(buf), check_crc=False)

    def set_iris(self, fnum: float) -> None:
        self._set_ctrl(V4L2_CID_IRIS_ABSOLUTE, iris_control_value(fnum), "setting the iris")

    def set_focus(self, position: int) -> None:
        position = int(position)
        if position < 0:
            raise ValueError(f"focus position {position} is negative")
        self._set_ctrl(V4L2_CID_FOCUS_ABSOLUTE, position, "setting the focus")

    def calibrate(self) -> None:
        self._set_ctrl(CID_CALIBRATE, 0, "starting calibration")

    def close(self) -> None:
        fd, self._fd = self._fd, None
        if fd is not None:
            try:
                self._closer(fd)
            except OSError:
                logger.debug("closing %s failed", self.path, exc_info=True)


def _smbus2():
    """The smbus2 module, or None off-hardware (a desktop checkout, CI).

    Same guard as ``app/hardware_probe._smbus``: nothing else in src/ guards
    this import, and a Mac checkout has to be able to import this module.
    """
    try:
        import smbus2
    except ImportError:
        return None
    return smbus2


# The kernel driver retries a failed write three times on EIO/EREMOTEIO
# (cef168_i2c_write); the board's MCU can NACK while it is busy with a move.
_WRITE_RETRIES = 3
# EREMOTEIO is Linux-only (121); a desktop checkout must still import.
_RETRYABLE_ERRNOS = (errno.EIO, getattr(errno, "EREMOTEIO", 121))
_WRITE_RETRY_DELAY_S = 0.01


class Cef168Raw(Cef168Backend):
    """Raw I2C via smbus2 ``i2c_rdwr``, no kernel driver needed (F14).

    ``I2C_RDWR`` does not claim the slave address, so this works with or
    without cef168.ko bound -- see the module docstring for why that does not
    change which backend ``open_adapter`` prefers.
    """

    provenance = "i2c-raw"

    def __init__(self, bus: int, addr: int = I2C_ADDRESS, *, port: str = "",
                 bus_source: str = "", smbus_module: Any = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.bus = int(bus)
        self.addr = addr
        self.port = port
        self.bus_source = bus_source
        self._sleep = sleep
        self._smbus = smbus_module if smbus_module is not None else _smbus2()
        if self._smbus is None:
            raise Cef168Error("smbus2 is not installed")
        try:
            self._dev: Any = self._smbus.SMBus(self.bus)
        except OSError as exc:
            raise _wrap(exc, f"cannot open /dev/i2c-{self.bus}") from exc

    def _dev_or_raise(self) -> Any:
        if self._dev is None:
            raise Cef168Error(f"i2c-{self.bus} is closed")
        return self._dev

    def read_data(self) -> Cef168Data:
        dev = self._dev_or_raise()
        try:
            msg = self._smbus.i2c_msg.read(self.addr, FRAME_LENGTH)
            dev.i2c_rdwr(msg)
            raw = bytes(msg)
        except OSError as exc:
            raise _wrap(exc, f"reading 0x{self.addr:02x} on i2c-{self.bus} failed") from exc
        return parse_data(raw, check_crc=True)

    def _write(self, cmd: int, value: int, what: str) -> None:
        dev = self._dev_or_raise()
        frame = encode_command(cmd, value)
        last: Optional[OSError] = None
        for attempt in range(_WRITE_RETRIES):
            try:
                dev.i2c_rdwr(self._smbus.i2c_msg.write(self.addr, list(frame)))
                return
            except OSError as exc:
                last = exc
                if getattr(exc, "errno", None) not in _RETRYABLE_ERRNOS:
                    break
                if attempt + 1 < _WRITE_RETRIES:
                    self._sleep(_WRITE_RETRY_DELAY_S)
        assert last is not None
        raise _wrap(last, f"{what} (0x{self.addr:02x} on i2c-{self.bus}) failed")

    def set_iris(self, fnum: float) -> None:
        self._write(INP_SET_APERTURE, iris_control_value(fnum), "setting the iris")

    def set_focus(self, position: int) -> None:
        position = int(position)
        if not 0 <= position <= 0xFFFF:
            raise ValueError(f"focus position {position} does not fit in 16 bits")
        self._write(INP_SET_FOCUS, position, "setting the focus")

    def calibrate(self) -> None:
        self._write(INP_CALIBRATE, 0, "starting calibration")

    def close(self) -> None:
        dev, self._dev = self._dev, None
        if dev is not None:
            try:
                dev.close()
            except OSError:
                logger.debug("closing i2c-%s failed", self.bus, exc_info=True)


# ── Discovery: subdevs, sensors, buses ─────────────────────────────────────

SYSFS_V4L = "/sys/class/video4linux"
DEV_ROOT = "/dev"

# Camera ports CineMate names. Pi 4 / CM4 only ever drives cam0.
PORTS = ("cam0", "cam1")

# Last-resort bus per platform, used only when neither a cef168 subdev nor a
# matching sensor subdev answers the question. The Pi 5 row is a copy of
# ir_filter.CAM_PORT_TO_BUS (pinned by a test). The pi4 row has no cam1 on
# purpose: that bus has not been measured, and "unknown, say so" beats a guess.
PLATFORM_CAM_BUSES: dict[str, dict[str, int]] = {
    "pi5": {"cam0": 6, "cam1": 4},
    "pi4": {"cam0": 0},
}

# `<driver> <bus>-<addr>`: the entity name v4l2_i2c_subdev_init() gives an I2C
# subdev, e.g. "cef168 0-000d", "imx477 0-001a".
_SUBDEV_NAME = re.compile(r"^(?P<model>\S+) (?P<bus>\d+)-(?P<addr>[0-9a-fA-F]{4})$")
LENS_DRIVER_NAME = "cef168"


@dataclass(frozen=True)
class SubdevInfo:
    path: str       # /dev/v4l-subdevN
    name: str       # the raw entity name, "cef168 0-000d"
    model: str      # "cef168", "imx477", ...
    bus: int
    address: int
    port: str = ""  # "cam0"/"cam1" when the platform table knows the bus, else ""


def list_subdevs(sysfs_root: str = SYSFS_V4L, dev_root: str = DEV_ROOT) -> list[SubdevInfo]:
    """Every I2C subdev whose entity name parses as ``<driver> N-00xx``, sorted
    by node number. Unreadable or oddly named entries are skipped: this runs
    on every detection attempt and must not raise on a half-built sysfs."""
    found: list[tuple[int, SubdevInfo]] = []
    try:
        entries = sorted(Path(sysfs_root).glob("v4l-subdev*"))
    except OSError:
        return []
    for entry in entries:
        number = re.search(r"(\d+)$", entry.name)
        if not number:
            continue
        try:
            name = (entry / "name").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        match = _SUBDEV_NAME.match(name)
        if not match:
            continue
        found.append((int(number.group(1)), SubdevInfo(
            path=str(Path(dev_root) / entry.name),
            name=name,
            model=match.group("model").lower(),
            bus=int(match.group("bus")),
            address=int(match.group("addr"), 16),
        )))
    return [info for _, info in sorted(found, key=lambda item: item[0])]


def find_subdevs(sysfs_root: str = SYSFS_V4L, dev_root: str = DEV_ROOT, *,
                 platform: Optional[str] = None) -> list[SubdevInfo]:
    """The cef168 lens subdevs: PLAN F6/F4 -- present when the driver is bound,
    whether or not a board is actually fitted. The bus comes from the subdev's
    own name (``cef168 N-000d``); with ``platform`` given, ``port`` is filled
    from that platform's table (``open_adapter`` does better when it has the
    camera list, and pairs the bus with the sensor's)."""
    table = PLATFORM_CAM_BUSES.get(platform or "", {})
    by_bus = {bus: port for port, bus in table.items()}
    return [
        SubdevInfo(s.path, s.name, s.model, s.bus, s.address, by_bus.get(s.bus, ""))
        for s in list_subdevs(sysfs_root, dev_root)
        if s.model == LENS_DRIVER_NAME and s.address == I2C_ADDRESS
    ]


def detect_platform() -> str:
    """'pi5' / 'pi4' / 'other' / 'unknown' -- sensor_detect.pi_family(), imported
    lazily so this module stays importable on its own."""
    try:
        from module.sensor_detect import pi_family
    except Exception:  # an import-time failure elsewhere must not stop detection
        logger.debug("pi_family unavailable", exc_info=True)
        return "unknown"
    try:
        return pi_family()
    except Exception:
        logger.debug("pi_family failed", exc_info=True)
        return "unknown"


def _sensor_family(model: Any) -> str:
    """'imx585_mono' -> 'imx585', 'imx708_wide_noir' -> 'imx708': the kernel
    names the silicon, libcamera/CineMate the variant."""
    return str(model or "").strip().lower().split("_")[0]


def resolve_sensor_buses(cameras: Optional[list[dict]], sensors: list[SubdevInfo],
                         platform: str) -> dict[str, tuple[int, str]]:
    """Pair CineMate's CAMERAS entries with the sensors' subdevs: port -> (bus, source).

    One camera of a model and one sensor subdev of that model is unambiguous.
    Several identical sensors (two imx585) are paired only where the platform
    table agrees with a bus a sensor really is on -- otherwise the pairing is
    left out rather than guessed.
    """
    table = PLATFORM_CAM_BUSES.get(platform, {})
    by_family: dict[str, list[SubdevInfo]] = {}
    for sensor in sensors:
        by_family.setdefault(_sensor_family(sensor.model), []).append(sensor)
    cams_by_family: dict[str, list[dict]] = {}
    for cam in cameras or []:
        if isinstance(cam, dict) and cam.get("port") in PORTS:
            cams_by_family.setdefault(_sensor_family(cam.get("model")), []).append(cam)

    resolved: dict[str, tuple[int, str]] = {}
    for family, cams in cams_by_family.items():
        subs = by_family.get(family, [])
        if len(cams) == 1 and len(subs) == 1:
            resolved[cams[0]["port"]] = (subs[0].bus, "sensor-subdev")
        elif len(cams) > 1 and len(cams) == len(subs):
            buses = {s.bus for s in subs}
            for cam in cams:
                if table.get(cam["port"]) in buses:
                    resolved[cam["port"]] = (table[cam["port"]], "platform-table")
    return resolved


def _port_for_bus(bus: int, sensor_map: dict[str, tuple[int, str]], platform: str) -> str:
    """Which port a bus belongs to, for reporting: the sensor pairing first, the
    platform table second, '' when neither knows."""
    for port, (sensor_bus, _source) in sensor_map.items():
        if sensor_bus == bus:
            return port
    for port, table_bus in PLATFORM_CAM_BUSES.get(platform, {}).items():
        if table_bus == bus:
            return port
    return ""


_PROBE_ATTEMPTS = 2
_PROBE_RETRY_DELAY_S = 0.02


def _probe(backend: Cef168Backend, sleep: Callable[[float], None]) -> Optional[Cef168Error]:
    """One CRC-checked read, retried once. None on success, else the last error.

    A single NACK is not "no adapter": the board's MCU can be busy. Two in a
    row 20 ms apart is.
    """
    last: Optional[Cef168Error] = None
    for attempt in range(_PROBE_ATTEMPTS):
        try:
            backend.read_data()
            return None
        except Cef168Error as exc:
            last = exc
            if attempt + 1 < _PROBE_ATTEMPTS:
                sleep(_PROBE_RETRY_DELAY_S)
    return last


def open_adapter(port: Optional[str] = None, *, cameras: Optional[list[dict]] = None,
                 platform: Optional[str] = None,
                 sysfs_root: str = SYSFS_V4L, dev_root: str = DEV_ROOT,
                 subdev_factory: Optional[Callable[..., Cef168Backend]] = None,
                 raw_factory: Optional[Callable[..., Cef168Backend]] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 ) -> tuple[Optional[Cef168Backend], str]:
    """Find the adapter and open a backend: ``(backend, "")`` or ``(None, reason)``.

    ``port`` is ``"cam0"`` / ``"cam1"`` to look on one port, or None for all.
    ``cameras`` is CineMate's parsed Redis CAMERAS list (``[{"model", "port",
    ...}]``); it lets the bus come from the sensor subdev instead of a table.
    A backend is returned only after a CRC-checked read succeeded, so "found"
    always means "the board answered".

    The reason on failure is written for the operator (it ends up in
    LENS_MESSAGE): which paths were tried and what each said.
    """
    if port is not None and port not in PORTS:
        return None, f"unknown camera port {port!r} (expected cam0 or cam1)"
    platform = platform if platform is not None else detect_platform()
    subdev_factory = subdev_factory or Cef168Subdev
    raw_factory = raw_factory or Cef168Raw

    all_subdevs = list_subdevs(sysfs_root, dev_root)
    sensors = [s for s in all_subdevs if s.model != LENS_DRIVER_NAME]
    sensor_map = resolve_sensor_buses(cameras, sensors, platform)
    table = PLATFORM_CAM_BUSES.get(platform, {})
    reasons: list[str] = []
    unknown_buses: list[str] = []
    probed_buses: set[int] = set()

    # 1. The driver is bound: its subdev name carries the bus.
    for sub in find_subdevs(sysfs_root, dev_root):
        sub_port = _port_for_bus(sub.bus, sensor_map, platform)
        if port and sub_port and sub_port != port:
            continue
        probed_buses.add(sub.bus)
        try:
            backend = subdev_factory(sub.path, bus=sub.bus, port=sub_port,
                                     bus_source="cef168-subdev")
        except Cef168Error as exc:
            reasons.append(str(exc))
            continue
        error = _probe(backend, sleep)
        if error is None:
            return backend, ""
        backend.close()
        reasons.append(
            f"the cef168 driver is bound at {sub.path} (i2c-{sub.bus}) but the board "
            f"did not answer: {error}"
        )

    # 2/3. No driver: raw I2C on the bus the sensor (or, failing that, the
    # platform table) says is the camera's.
    for candidate in ([port] if port else list(PORTS)):
        if candidate in sensor_map:
            bus, source = sensor_map[candidate]
        elif candidate in table:
            bus, source = table[candidate], "platform-table"
        else:
            unknown_buses.append(
                f"{candidate}: its I2C bus is not known on this platform "
                f"({platform}) and no sensor subdev could be matched to it"
            )
            continue
        if bus in probed_buses:
            continue
        probed_buses.add(bus)
        try:
            backend = raw_factory(bus, port=candidate, bus_source=source)
        except Cef168Error as exc:
            reasons.append(f"{candidate}: {exc}")
            continue
        error = _probe(backend, sleep)
        if error is None:
            return backend, ""
        backend.close()
        reasons.append(
            f"{candidate} ({describe_bus(bus, source)}): no adapter answered at "
            f"0x{I2C_ADDRESS:02x}: {error}"
        )

    # A bus we could not name is only worth reporting when it is the whole
    # story, or the operator asked for that port: a Pi 4 has no cam1 to find.
    if unknown_buses and (port or not reasons):
        reasons.extend(unknown_buses)
    return None, "; ".join(reasons) or "no camera port to probe"
