"""Read-only presence probes for the optional I²C peripherals.

The settings editor's i2c pane answers one question -- what is actually
plugged in right now -- and it has to answer it without disturbing anything.
That rules out reusing the drivers, each of which detects presence as a side
effect of a full initialisation:

* ``grove_base_hat_adc.ADC`` calls ``sys.exit(2)`` on an IOError, from
  read_raw/read/read_voltage/read_register/name/version alike -- and even its
  constructor can raise, since it builds a bus. SystemExit only unwinds the
  calling thread, so on a Flask worker that surfaces as a 500 rather than
  taking the process down, but either way it is not a probe primitive.
* ``QuadRotaryController._initialize_device`` sleeps 0.1 s, resets the seesaw
  and writes its NeoPixels -- re-running it would stamp on a controller that
  is live and being turned by an operator.
* ``I2cOled._initialize_display`` sleeps 0.1 s and re-runs the SSD1306 init
  sequence, which blanks whatever is on the screen.

So this module does the cheapest thing that answers the question: a one-byte
ACK read at a known address, the same primitive ``AnalogControls`` already
uses to find the Grove HAT (analog_controls.py) and ``SsdMonitor`` to find the
CFE Hat (ssd_monitor.py). Nothing here writes to a bus, and every probe is
safe to re-run on every request -- with one exception, stated where it lives:
the quad rotary encoder's seesaw does not reliably ACK that bare receive-byte
(measured on the rig 2026-09-20: a live, working board NACKed roughly a third
of them, `EREMOTEIO`), so it alone is probed with a real register read
instead. See ``_seesaw_present`` for why that one write is safe.

Everything is scoped to bus 1 deliberately. 0x34 is the CFE Hat there, but it
is also the StarlightEye IR-cut filter on the camera buses (4 and 6 on a Pi
5), so an unscoped sweep would report one as the other.
"""
from __future__ import annotations

import errno
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# The peripherals live on the Pi's main user bus.
I2C_BUS = 1

# The CFE Hat's card is PCIe, but 0x34 -- its latch/LED microcontroller -- is
# what actually says a hat is fitted. SsdMonitor also falls back to the Pi 5
# PCIe bridge node, and that fallback is a bridge-present test rather than a
# hat-present one: every Pi 5 with brcm-pcie bound satisfies it, hat or no hat.
# This pane reports what is attached, so it goes on the I²C answer alone.

# /dev/rtc is what hwclock talks to. Without the overlay CineMate does not
# manage (see docs/hardware-controls.md), the chip can ACK on the bus while
# the kernel still has no RTC device -- so both are reported.
RTC_DEV = Path("/dev/rtc")

# Both clocks are shown in one format so they can be compared at a glance.
CLOCK_FORMAT = "%Y-%m-%d %H:%M:%S"

# Known display types, and the extension point for the rest. i2c_oled.py
# constructs SSD1306_I2C without an address and takes the library default, so
# the repo never states one; both addresses an SSD1306 board can be strapped
# to are listed here. Recognising another controller later is a new row rather
# than new code -- which is also why the matched row is reported back, not just
# a bare yes.
# The SSD1309 takes the same command set and the same addresses as the
# SSD1306 and is driven by the same adafruit_ssd1306 code, so it needs no
# support of its own -- but the two cannot be told apart on the bus either.
# Neither has a readable ID register, so an address that answers could be
# either part, and the pane says exactly that rather than picking one.
OLED_CONTROLLERS = ("SSD1306", "SSD1309")

OLED_TYPES = (
    {"address": 0x3C, "controllers": OLED_CONTROLLERS, "note": "default address"},
    {"address": 0x3D, "controllers": OLED_CONTROLLERS, "note": "ADDR strapped high"},
)

DEVICES = (
    {
        "key": "grove",
        "name": "Grove Base HAT",
        "addresses": (0x08,),
        "hint": "analog inputs for potentiometers",
    },
    {
        "key": "quad_rotary",
        "name": "Adafruit quad rotary encoder",
        "addresses": (0x49,),
        "hint": "four dials and push buttons on one board",
    },
    {
        "key": "rtc",
        "name": "Real-time clock",
        "addresses": (0x68,),
        "hint": "keeps the clock across a power cycle",
    },
)


def _smbus():
    """The i2c module, or None off-hardware.

    Nothing else in src/ guards this import, which is why the test suite has
    to stuff fakes into sys.modules. A web request must not 500 on a desktop
    checkout, so this one does guard it.
    """
    try:
        import smbus2
    except ImportError:
        return None
    return smbus2


def _ack(bus_no: int, address: int) -> tuple[bool, int | None]:
    """(True, None) when something answers a one-byte read at *address*;
    (False, errno) otherwise -- errno is None when smbus2 itself is absent."""
    smbus2 = _smbus()
    if smbus2 is None:
        return False, None
    bus = None
    try:
        bus = smbus2.SMBus(bus_no)
        bus.read_byte(address)
        return True, None
    except (OSError, TypeError, ValueError) as exc:
        # OSError covers both "no such bus" and "nobody home at that address".
        return False, getattr(exc, "errno", None)
    finally:
        # analog_controls closes only on the success path, which leaks the
        # handle every time the HAT is absent. Closing here either way.
        if bus is not None:
            try:
                bus.close()
            except OSError:
                pass


# EREMOTEIO (121) is Linux-only -- it is what the Pi's i2c-dev driver
# actually raises for a NACK (confirmed on the rig 2026-09-20), but the
# constant does not exist in Python's errno module on macOS/BSD, so it is
# written as a literal here rather than errno.EREMOTEIO -- that attribute
# lookup would crash this module's import on a desktop checkout.
_EREMOTEIO = 121

# Errno names this pane knows how to explain, mapped to the reading an
# operator can act on. errno.errorcode already gives us the symbolic name
# (e.g. 121 -> "EREMOTEIO"); this is only the subset worth a plain-English
# hint. ENXIO/EREMOTEIO both mean "nobody home" (the two kernel I2C drivers
# disagree on which one a plain NACK raises); ETIMEDOUT is a clock-stretch or
# bus timeout; EBUSY means a kernel driver already owns the address; ENOENT
# means the bus itself doesn't exist.
_PROBE_ERROR_HINTS = {
    errno.ENXIO: "not found (NACK)",
    _EREMOTEIO: "not found (NACK)",
    errno.ETIMEDOUT: "bus timeout (clock stretch)",
    errno.EBUSY: "address busy (a kernel driver owns it)",
    errno.ENOENT: "no such bus",
}


def _probe_error(err_no: int | None) -> dict | None:
    """Errno name + a plain-English hint, or None when there was nothing to report."""
    if err_no is None:
        return None
    # errno.errorcode is built from the platform's own errno.h, so a desktop
    # checkout (no EREMOTEIO) would otherwise report "errno 121" instead of
    # the name the Pi itself would give it.
    name = "EREMOTEIO" if err_no == _EREMOTEIO else errno.errorcode.get(err_no, f"errno {err_no}")
    return {
        "errno": err_no,
        "name": name,
        "hint": _PROBE_ERROR_HINTS.get(err_no, "not found"),
    }


def _probe(addresses) -> tuple[int | None, int | None]:
    """The first address that answers, plus the last errno seen if none did."""
    last_errno = None
    for address in addresses:
        ok, err = _ack(I2C_BUS, address)
        if ok:
            return address, None
        last_errno = err
    return None, last_errno


# Seesaw hardware-id register: STATUS module base (0x00), HW_ID function
# (0x01) -- the exact transaction adafruit_seesaw.Seesaw.__init__ performs
# via its own read(reg_base, reg) helper. 0x55 is the SAMD09 seesaw, 0x87 the
# ATtiny8xx seesaw that answered on this rig; both ship on different Adafruit
# boards. A board that never answers this returns 0x00 or raises -- measured
# on the rig, 2 of 40 successful reads against a present board came back
# 0x00 rather than a real id, so "no exception" is not accepted as presence.
_SEESAW_STATUS_BASE = 0x00
_SEESAW_HW_ID_REGISTER = 0x01
_SEESAW_READ_DELAY = 0.008  # matches adafruit_seesaw.Seesaw.read()'s own default
_SEESAW_HW_IDS = (0x55, 0x87)


def _seesaw_present(bus_no: int, address: int) -> tuple[bool, int | None, int | None]:
    """(present, hw_id, errno) for an Adafruit seesaw at *address*.

    Every other device in this module is probed with a bare receive-byte
    specifically so nothing here ever writes to a bus a driver might be
    using. The quad rotary encoder's seesaw is the one exception: it does not
    reliably ACK that receive-byte (measured on the rig 2026-09-20, a live
    working board NACKed about a third of them), because that isn't the
    question a seesaw answers -- it answers a *register* read. So this writes
    the STATUS/HW_ID register address, waits out the seesaw's own read
    turnaround, and reads the id back, accepting only a known one.

    This is safe to add as the one write in the module because it is not a
    new kind of bus traffic: it is the identical two-byte-write-then-read
    QuadRotaryController.update() already performs, over and over, ten times
    a second, for as long as the driver runs.
    """
    smbus2 = _smbus()
    if smbus2 is None:
        return False, None, None
    bus = None
    try:
        bus = smbus2.SMBus(bus_no)
        bus.write_i2c_block_data(address, _SEESAW_STATUS_BASE, [_SEESAW_HW_ID_REGISTER])
        time.sleep(_SEESAW_READ_DELAY)
        hw_id = bus.read_byte(address)
        return hw_id in _SEESAW_HW_IDS, hw_id, None
    except (OSError, TypeError, ValueError) as exc:
        return False, None, getattr(exc, "errno", None)
    finally:
        if bus is not None:
            try:
                bus.close()
            except OSError:
                pass


def _detect_quad_rotary(spec: dict, driver_state: dict | None) -> dict:
    """Prefer the driver's own state when it has one; probe the seesaw otherwise.

    QuadRotaryController polls this exact board at 10 Hz, so when it reports
    connected that answer is both more accurate than a fresh probe and free
    of adding to whatever contention already exists between the two. Whether
    that contention is even the cause of the seesaw's NACK rate is not
    settled (hardware log 2026-09-20) -- which is exactly why, when the
    driver has no opinion (disabled, or never connected), this falls back to
    the proper register read in ``_seesaw_present`` rather than the bare ACK
    every other device here uses.
    """
    address = spec["addresses"][0]
    driver_state = driver_state or None
    driver_confirmed = bool(
        driver_state and driver_state.get("enabled") and driver_state.get("connected")
    )
    if driver_confirmed:
        present, hw_id, err = True, None, None
        provenance = "driver-confirmed"
    else:
        present, hw_id, err = _seesaw_present(I2C_BUS, address)
        provenance = "probed"
    entry = {
        "key": spec["key"],
        "name": spec["name"],
        "hint": spec["hint"],
        "bus": f"i2c-{I2C_BUS}",
        "present": present,
        "address": address if present else None,
        "expected": [f"0x{a:02x}" for a in spec["addresses"]],
        "provenance": provenance,
        "probe_error": None if present else _probe_error(err),
        "driver": driver_state,
    }
    if hw_id is not None:
        entry["hw_id"] = f"0x{hw_id:02x}"
    return entry


def detect_cfe_hat() -> dict:
    """Present when 0x34 answers on the bus, and only then."""
    address, err = _probe((0x34,))
    return {
        "present": address is not None,
        "bus": f"i2c-{I2C_BUS}",
        "address": address,
        "via": "i2c" if address is not None else None,
        "probe_error": None if address is not None else _probe_error(err),
    }


def detect_oled(oled_settings: dict | None = None) -> dict:
    """Which display answered, and how big it is configured to be.

    Geometry is NOT probed, because it cannot be: an SSD1306 has no size or ID
    register, so nothing on the bus can be asked how many pixels it has.
    i2c_oled.py takes width/height from output_peripherals.oled and tells the
    driver, rather than the other way round -- so the numbers here are reported
    as configured, and the pane says so.
    """
    settings = oled_settings or {}
    entry = {
        "key": "oled",
        "name": "I²C OLED display",
        "hint": "status screen",
        "bus": f"i2c-{I2C_BUS}",
        "present": False,
        "address": None,
        "expected": [f"0x{t['address']:02x}" for t in OLED_TYPES],
        "controller": None,
        "note": None,
        "width": int(settings.get("width", 128) or 128),
        "height": int(settings.get("height", 64) or 64),
        "geometry_source": "settings",
        "enabled": bool(settings.get("enabled", False)),
    }
    last_errno = None
    for oled_type in OLED_TYPES:
        ok, err = _ack(I2C_BUS, oled_type["address"])
        if ok:
            entry["present"] = True
            entry["address"] = oled_type["address"]
            entry["controller"] = " or ".join(oled_type["controllers"])
            entry["controllers"] = list(oled_type["controllers"])
            entry["note"] = oled_type["note"]
            break
        last_errno = err
    entry["probe_error"] = None if entry["present"] else _probe_error(last_errno)
    return entry


def detect_devices(oled_settings: dict | None = None, quad_rotary_driver: dict | None = None) -> list[dict]:
    """Presence of every peripheral the pane lists, probed now.

    *quad_rotary_driver* is the running ``QuadRotaryController``'s own state
    snapshot (``{enabled, connected, ever_connected, last_error,
    last_change_epoch}``), or None when the controller was never started --
    see ``_detect_quad_rotary`` for how it changes what gets probed.
    """
    found = []
    for spec in DEVICES:
        if spec["key"] == "quad_rotary":
            found.append(_detect_quad_rotary(spec, quad_rotary_driver))
            continue
        address, err = _probe(spec["addresses"])
        entry = {
            "key": spec["key"],
            "name": spec["name"],
            "hint": spec["hint"],
            "bus": f"i2c-{I2C_BUS}",
            "present": address is not None,
            "address": address,
            "expected": [f"0x{a:02x}" for a in spec["addresses"]],
            "probe_error": None if address is not None else _probe_error(err),
        }
        if spec["key"] == "rtc":
            entry["kernel_device"] = _rtc_device_present()
        found.append(entry)

    found.append(detect_oled(oled_settings))

    cfe = detect_cfe_hat()
    found.append({
        "key": "cfe_hat",
        "name": "CFE Hat",
        "hint": "CFexpress storage (Raspberry Pi 5)",
        "bus": cfe["bus"],
        "present": cfe["present"],
        "address": cfe["address"],
        "expected": ["0x34"],
        "via": cfe["via"],
        "probe_error": cfe.get("probe_error"),
    })
    return found


def _rtc_device_present() -> bool:
    try:
        return RTC_DEV.exists()
    except OSError:
        return False


def _run(argv: list[str], timeout: float = 5.0):
    """subprocess.run with the guards cli_commands' os.popen/os.system lack.

    Those two never raise and never check an exit status, which is why
    `set rtc time` logs success even with no RTC attached. Everything here
    reports what actually happened.
    """
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.info("hardware probe: %s failed: %s", " ".join(argv), exc)
        return None


def _parse_clock(text: str):
    """hwclock -r prints e.g. 2026-09-05 22:10:32.723857+02:00."""
    try:
        return datetime.fromisoformat(text.strip().replace(" ", "T", 1))
    except ValueError:
        return None


def read_rtc_time() -> dict:
    """The RTC's own clock, as a value rather than a log line.

    `sudo -n` throughout: without -n a machine whose sudoers lacks a NOPASSWD
    rule would sit at a password prompt on the console until the request timed
    out. Failing fast and saying so is the better answer.

    Reported in the same shape as the system clock -- seconds, no microseconds,
    no offset -- so the two can be read against each other at a glance, with an
    epoch alongside so the page can tick between polls instead of forking
    hwclock once a second.
    """
    result = None
    for argv in (["hwclock", "-r"], ["sudo", "-n", "hwclock", "-r"]):
        result = _run(argv)
        if result is not None and result.returncode == 0 and result.stdout.strip():
            raw = result.stdout.strip()
            parsed = _parse_clock(raw)
            return {
                "ok": True,
                "time": parsed.strftime(CLOCK_FORMAT) if parsed else raw,
                "epoch": parsed.timestamp() if parsed else None,
                "raw": raw,
                "error": None,
            }
    detail = ""
    if result is not None:
        detail = (result.stderr or result.stdout or "").strip()
    return {
        "ok": False, "time": None, "epoch": None, "raw": None,
        "error": detail or "hwclock could not read the clock",
    }


def system_time() -> dict:
    now = datetime.now()
    return {"time": now.strftime(CLOCK_FORMAT), "epoch": now.timestamp()}


def sync_rtc_to_system() -> dict:
    """Copy the system clock onto the RTC, and verify it took.

    `set rtc time` in the CLI runs the same hwclock call through os.system,
    which discards the exit status -- it reports success whether or not there
    is an RTC. This checks the status and then reads the clock back, the same
    act-then-verify shape format_raw_drive uses.
    """
    result = _run(["sudo", "-n", "hwclock", "--systohc"], timeout=10.0)
    if result is None:
        return {"ok": False, "message": "could not run hwclock", "rtc": read_rtc_time()}
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if "password" in detail.lower() or "sudo:" in detail.lower():
            detail = "hwclock needs sudo without a password prompt; it is not in CineMate's sudoers rule"
        return {
            "ok": False,
            "message": detail or f"hwclock exited {result.returncode}",
            "rtc": read_rtc_time(),
        }
    return {"ok": True, "message": "RTC set from system time", "rtc": read_rtc_time()}
