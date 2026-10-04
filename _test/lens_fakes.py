"""Fakes shared by the module/lens tests: a clock, a Redis, a backend, a bus.

Not a test module (no ``test_`` prefix, so pytest does not collect it). The
test files put ``_test/`` on ``sys.path`` themselves before importing it.
"""
from __future__ import annotations

import sys
import types
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# module.redis_controller (imported by the controller for ParameterKey) needs a
# `redis` name at import; every other test in the suite does the same.
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.lens.cef168 import Cef168Backend, Cef168Data, Cef168Error  # noqa: E402


class FakeClock:
    """A monotonic clock that only moves when told to, or when something sleeps."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeRedis:
    """The two RedisController methods the lens code uses, with the real
    set_value's same-value dedup (and its force escape hatch)."""

    def __init__(self, initial: dict | None = None):
        self.cache: dict[str, str] = {k: str(v) for k, v in (initial or {}).items()}
        self.writes: list[tuple[str, str, bool]] = []

    def get_value(self, key, default=None):
        key = getattr(key, "value", key)
        return self.cache.get(key, default)

    def set_value(self, key, value, *, force=False):
        key = getattr(key, "value", key)
        if value is None:
            return
        if not force and str(self.cache.get(key)) == str(value):
            return
        self.cache[key] = str(value)
        self.writes.append((key, str(value), force))

    def published(self, key: str) -> list[str]:
        return [v for k, v, _ in self.writes if k == key]


def frame(**overrides) -> Cef168Data:
    """A board frame for lens id 235 resting mid-range, unless told otherwise."""
    fields = dict(lens_id=235, moving=False, calibrating=0, moving_time=0,
                  focus_position_min=0, focus_position_max=1069, focus_position_cur=500,
                  focus_distance_min=100, focus_distance_max=65535)
    fields.update(overrides)
    return Cef168Data(**fields)


# The calibration output printed in Pinefeat's readme (a lens with a distance
# encoder): flat [dioptre, position, ...] with positions descending.
README_MAP = [0.00153, 1069, 0.154, 1042, 0.446, 996, 0.719, 969, 0.971, 941, 1.2, 901,
              1.45, 860, 1.72, 805, 2.04, 764, 2.44, 682, 2.86, 559, 3.45, 388, 3.85, 252,
              4.35, 0]


def _dioptre_at(position: float, flat=README_MAP) -> float:
    pairs = [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
    for (d0, p0), (d1, p1) in zip(pairs, pairs[1:]):
        if position >= p1:
            return d0 + (position - p0) * (d1 - d0) / (p1 - p0)
    return pairs[-1][0]


def encoder_sweep(step: int = 20) -> list[Cef168Data]:
    """What a lens with a distance encoder reports while the board sweeps min
    -> infinity: the position climbs, the reported distance grows, ending at the
    65535 cm 'infinity' marker; then idle frames at the far end."""
    frames = []
    for position in range(0, 1070, step):
        dioptre = _dioptre_at(position)
        cm = 65535 if position >= 1069 or dioptre < 0.0016 else max(1, int(round(100 / dioptre)))
        frames.append(frame(moving=True, calibrating=2, moving_time=210,
                            focus_position_cur=position, focus_distance_min=cm,
                            focus_distance_max=65535))
    frames.append(frame(moving=True, calibrating=2, moving_time=210, focus_position_cur=1069,
                        focus_distance_min=65535))
    for _ in range(3):
        frames.append(frame(focus_position_cur=1069, moving_time=210, focus_distance_min=65535))
    return frames


def no_encoder_sweep(step: int = 20, mfd_cm: int = 28) -> list[Cef168Data]:
    """A lens that moves and reports its range but a constant distance (its
    minimum focus distance): the Pinefeat troubleshooting-section-6 case."""
    frames = [frame(moving=True, calibrating=2, moving_time=210, focus_position_cur=p,
                    focus_distance_min=mfd_cm, focus_distance_max=mfd_cm)
              for p in range(0, 1070, step)]
    for _ in range(3):
        frames.append(frame(focus_position_cur=1069, moving_time=210,
                            focus_distance_min=mfd_cm, focus_distance_max=mfd_cm))
    return frames


def sigma_no_feedback_sweep() -> list[Cef168Data]:
    """The real G0.2 run on the Sigma 18-35 f/1.8 Art (board lens id 112), PLAN
    2026-10-04: calibrating==2 for ~100 ms with the motor flag set, position and
    range stuck at 0, distance stuck at 0.28 m (28 cm); then calibrating==0 with
    focus_position_max still 0."""
    busy = dict(lens_id=112, moving=True, calibrating=2, moving_time=98,
                focus_position_min=0, focus_position_max=0, focus_position_cur=0,
                focus_distance_min=28, focus_distance_max=28)
    frames = [frame(**busy) for _ in range(5)]
    frames += [frame(**{**busy, "moving": False, "calibrating": 0}) for _ in range(2)]
    return frames


class FakeBackend(Cef168Backend):
    """A scripted adapter. ``data`` is what reads return once ``queue`` is
    empty; ``sweep`` is loaded into the queue by ``calibrate()``."""

    def __init__(self, data: Cef168Data | None = None, *, provenance: str = "v4l2-subdev",
                 bus: int = 0, port: str = "cam0", bus_source: str = "cef168-subdev"):
        self.provenance = provenance
        self.bus = bus
        self.port = port
        self.bus_source = bus_source
        self.data = data if data is not None else frame()
        self.queue: deque[Cef168Data] = deque()
        self.sweep: list[Cef168Data] = []
        self.read_errors = 0            # fail this many upcoming reads
        self.read_fails_forever = False
        self.iris_error: str | None = None
        self.iris_calls: list[float] = []
        self.focus_calls: list[int] = []
        self.calibrate_calls = 0
        self.closed = False
        self.reads = 0

    def read_data(self) -> Cef168Data:
        self.reads += 1
        if self.read_fails_forever or self.read_errors > 0:
            self.read_errors = max(0, self.read_errors - 1)
            raise Cef168Error("simulated EIO")
        if self.queue:
            self.data = self.queue.popleft()
        return self.data

    def set_iris(self, fnum: float) -> None:
        if self.iris_error:
            raise Cef168Error(self.iris_error)
        self.iris_calls.append(fnum)

    def set_focus(self, position: int) -> None:
        self.focus_calls.append(position)

    def calibrate(self) -> None:
        self.calibrate_calls += 1
        self.queue.extend(self.sweep)

    def close(self) -> None:
        self.closed = True


# ── smbus2 stand-in for the raw backend ────────────────────────────────────

class FakeI2cMsg:
    def __init__(self, address, length=None, data=None, is_read=False):
        self.addr = address
        self.is_read = is_read
        self.data = bytes(data) if data is not None else b"\x00" * (length or 0)

    @classmethod
    def read(cls, address, length):
        return cls(address, length=length, is_read=True)

    @classmethod
    def write(cls, address, data):
        return cls(address, data=data)

    def __bytes__(self):
        return self.data


class FakeSMBus:
    """One simulated board. ``frame_bytes`` is what a read returns; every write
    is recorded; ``errors`` is a list of exceptions to raise on the next calls."""

    instances: list["FakeSMBus"] = []

    def __init__(self, bus):
        self.bus = bus
        self.frame_bytes = b""
        self.writes: list[bytes] = []
        self.errors: list[Exception] = []
        self.closed = False
        FakeSMBus.instances.append(self)

    def i2c_rdwr(self, msg):
        if self.errors:
            raise self.errors.pop(0)
        if msg.is_read:
            msg.data = self.frame_bytes[:len(msg.data)].ljust(len(msg.data), b"\x00")
        else:
            self.writes.append(msg.data)

    def close(self):
        self.closed = True


def fake_smbus_module(board: FakeSMBus | None = None):
    """A module-like object with SMBus and i2c_msg. With ``board`` given every
    SMBus(...) opened returns that same simulated board."""
    def factory(bus):
        if board is not None:
            board.bus = bus
            return board
        return FakeSMBus(bus)
    return types.SimpleNamespace(SMBus=factory, i2c_msg=FakeI2cMsg)
