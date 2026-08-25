"""Which RP1 clock regime this board is in, and the pixel rate that goes with it.

The PiSP CSI2-to-ISP-FE bottleneck scales with the RP1 clock. libcamera cannot
work the rate out for itself -- both obvious probes were tried on the target
and fail:

  * A CM5 on 6.12.93 has no ``rp1`` node in ``/proc/device-tree`` at all, so
    there is no ``assigned-clock-rates`` array to read.
  * The ``rp1-overclock`` overlay *requests* 300 MHz and the clock driver
    delivers **333.33 MHz**, so a table keyed on the requested value misses.

Both failures are silent and land on the stock rate, which costs frame rate
rather than correctness -- safe, but wrong and invisible. So Cinemate decides,
and passes the answer down: ``--max-pixel-rate`` to cinepi-raw, which forwards
it to the IPA as ``LIBCAMERA_RPI_MAX_PIXEL_RATE``. One value, sourced from the
same switch that enables the overlay, so the ceiling and the hardware cannot
describe different regimes.

Direction of error matters and is not symmetric. Under-stating the rate makes
the IPA pad the line length further: slower, nothing else. Over-stating it
overruns the FIFO mid-line and corrupts every mode wide enough for this bound
to be what limits the line time -- with nothing logged, because the one warning
on that path fires when the *sensor* cannot supply enough blanking, which a
too-high rate makes less likely to trigger. Everything here therefore fails
towards the stock rate.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_TXT_PATH = "/boot/firmware/config.txt"
CLK_SUMMARY_PATH = "/sys/kernel/debug/clk/clk_summary"

# Measured on a CM5: stock 200 MHz -> 380 MPix/s, overlay -> 580 MPix/s.
PIXEL_RATE_STOCK = 380.0
PIXEL_RATE_OVERCLOCKED = 580.0

# The overlay asks for 300 MHz and the hardware lands on 333.33 MHz, so this is
# a threshold rather than an equality test. Anything meaningfully above stock
# counts as the overclocked regime.
OVERCLOCK_CLK_THRESHOLD_HZ = 250_000_000

_OVERLAY_LINE_RE = re.compile(r"^\s*dtoverlay=rp1-overclock\s*$", re.MULTILINE)
_CLK_SYS_RE = re.compile(r"^\s+clk_sys\s+\S+\s+\S+\s+\S+\s+(\d+)", re.MULTILINE)


def is_rp1_platform() -> bool:
    """BCM2712 (Pi 5 / CM5) is the only family with an RP1."""
    try:
        return "bcm2712" in Path("/proc/device-tree/compatible").read_bytes().decode("ascii", "ignore")
    except OSError:
        return False


def overlay_enabled(config_txt: str | None = None) -> bool:
    """True when config.txt carries an *uncommented* rp1-overclock line."""
    if config_txt is None:
        try:
            config_txt = Path(CONFIG_TXT_PATH).read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read %s (%s); assuming stock clocks", CONFIG_TXT_PATH, exc)
            return False
    return bool(_OVERLAY_LINE_RE.search(config_txt))


def measured_clk_sys_hz() -> int | None:
    """Live RP1 ``clk_sys`` in Hz, or None when it cannot be read.

    debugfs is root-only, so this goes through sudo -- the same non-interactive
    sudo the storage and service paths already rely on. Failure is not an
    error: it just means the config.txt answer stands on its own.
    """
    try:
        result = subprocess.run(
            ["sudo", "-n", "grep", "-E", r"^\s+clk_sys\s", CLK_SUMMARY_PATH],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    match = _CLK_SYS_RE.search(result.stdout)
    return int(match.group(1)) if match else None


def pixel_rate() -> float | None:
    """MPix/s ceiling to hand cinepi-raw, or None when the question is moot.

    None on any board without an RP1 -- the vc4 platforms carry an
    unconstrained (zero) bound in libcamera, and passing a number there would
    invent a limit that does not exist.

    config.txt is the operator's stated intent and the switch that sets it
    forces a reboot, so it is normally authoritative. Where the live clock can
    also be read, it is used to *veto* an overclocked answer the hardware does
    not support -- the dangerous direction is claiming 580 on a board running
    stock clocks, which is exactly what a config.txt edited but not yet
    rebooted looks like.
    """
    if not is_rp1_platform():
        return None

    requested_overclock = overlay_enabled()
    measured = measured_clk_sys_hz()

    if requested_overclock and measured is not None:
        if measured < OVERCLOCK_CLK_THRESHOLD_HZ:
            logger.warning(
                "config.txt enables rp1-overclock but clk_sys reads %d Hz -- "
                "using the stock %.0f MPix/s ceiling. Reboot for the overlay to take effect.",
                measured, PIXEL_RATE_STOCK,
            )
            return PIXEL_RATE_STOCK

    rate = PIXEL_RATE_OVERCLOCKED if requested_overclock else PIXEL_RATE_STOCK
    logger.info(
        "RP1 regime: %s (clk_sys %s) -> %.0f MPix/s",
        "overclocked" if requested_overclock else "stock",
        f"{measured} Hz" if measured is not None else "unreadable",
        rate,
    )
    return rate
