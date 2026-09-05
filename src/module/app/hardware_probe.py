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
safe to re-run on every request.

Everything is scoped to bus 1 deliberately. 0x34 is the CFE Hat there, but it
is also the StarlightEye IR-cut filter on the camera buses (4 and 6 on a Pi
5), so an unscoped sweep would report one as the other.
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# The peripherals live on the Pi's main user bus.
I2C_BUS = 1

# The CFE Hat is the odd one out: the card itself is PCIe, and 0x34 is the
# hat's latch/LED microcontroller. Same two-step test as
# SsdMonitor._detect_cfe_hat -- I²C first, then the PCIe bridge node.
CFE_PCIE_NODE = Path("/sys/bus/platform/drivers/brcm-pcie/1000110000.pcie")

# /dev/rtc is what hwclock talks to. Without the overlay CineMate does not
# manage (see docs/hardware-controls.md), the chip can ACK on the bus while
# the kernel still has no RTC device -- so both are reported.
RTC_DEV = Path("/dev/rtc")

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


def _ack(bus_no: int, address: int) -> bool:
    """True when something answers a one-byte read at *address*."""
    smbus2 = _smbus()
    if smbus2 is None:
        return False
    bus = None
    try:
        bus = smbus2.SMBus(bus_no)
        bus.read_byte(address)
        return True
    except (OSError, TypeError, ValueError):
        # OSError covers both "no such bus" and "nobody home at that address".
        return False
    finally:
        # analog_controls closes only on the success path, which leaks the
        # handle every time the HAT is absent. Closing here either way.
        if bus is not None:
            try:
                bus.close()
            except OSError:
                pass


def _probe(addresses) -> int | None:
    """The first address that answers, or None."""
    for address in addresses:
        if _ack(I2C_BUS, address):
            return address
    return None


def detect_cfe_hat() -> dict:
    """Same two-step test as SsdMonitor._detect_cfe_hat, run live.

    The PCIe fallback is a bridge-present test rather than a hat-present one,
    so it is reported as a distinct route instead of being folded into a bare
    yes -- any Pi 5 with that node bound satisfies it.
    """
    address = _probe((0x34,))
    if address is not None:
        return {"present": True, "bus": f"i2c-{I2C_BUS}", "address": address, "via": "i2c"}
    try:
        if CFE_PCIE_NODE.exists():
            return {"present": True, "bus": "pcie", "address": None, "via": "pcie-node"}
    except OSError:
        pass
    return {"present": False, "bus": "pcie", "address": None, "via": None}


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
    for oled_type in OLED_TYPES:
        if _ack(I2C_BUS, oled_type["address"]):
            entry["present"] = True
            entry["address"] = oled_type["address"]
            entry["controller"] = " or ".join(oled_type["controllers"])
            entry["controllers"] = list(oled_type["controllers"])
            entry["note"] = oled_type["note"]
            break
    return entry


def detect_devices(oled_settings: dict | None = None) -> list[dict]:
    """Presence of every peripheral the pane lists, probed now."""
    found = []
    for spec in DEVICES:
        address = _probe(spec["addresses"])
        entry = {
            "key": spec["key"],
            "name": spec["name"],
            "hint": spec["hint"],
            "bus": f"i2c-{I2C_BUS}",
            "present": address is not None,
            "address": address,
            "expected": [f"0x{a:02x}" for a in spec["addresses"]],
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


def read_rtc_time() -> dict:
    """The RTC's own clock, as a value rather than a log line.

    `sudo -n` throughout: without -n a machine whose sudoers lacks a NOPASSWD
    rule would sit at a password prompt on the console until the request timed
    out. Failing fast and saying so is the better answer.
    """
    for argv in (["hwclock", "-r"], ["sudo", "-n", "hwclock", "-r"]):
        result = _run(argv)
        if result is not None and result.returncode == 0 and result.stdout.strip():
            return {"ok": True, "time": result.stdout.strip(), "error": None}
    detail = ""
    if result is not None:
        detail = (result.stderr or result.stdout or "").strip()
    return {"ok": False, "time": None, "error": detail or "hwclock could not read the clock"}


def system_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
