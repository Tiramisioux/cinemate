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

THE CONFIG.TXT LINE IS THE ONLY AUTHORITY. An earlier revision of this module
also read the live ``clk_sys`` rate and used it to veto an enabled overlay back
down to stock when the measured clock looked too low for the switch to have
taken effect yet. That veto assumed ``clk_sys`` reads distinctly per regime
(measured ~200 MHz stock / ~333 MHz overclocked on an earlier 6.12.93 session).
A later session on the same kernel measured ``clk_sys`` at ~333 MHz in *both*
regimes -- the reading no longer discriminates stock from overclocked at all,
which silently defeated the veto's threshold (a stock board reads as if the
overlay had already taken effect) without ever tripping it visibly. Rather than
carry a veto that can no longer distinguish the case it exists for, ``clk_sys``
is read for the info log line only and has no effect on the decision in either
direction -- config.txt's overlay line decides, full stop.
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

    config.txt's overlay line is the operator's stated intent and the only
    input to this decision, in either direction: enabled means the overclocked
    rate, commented out or absent means stock, unreadable falls to stock (see
    overlay_enabled()). The live clock is read below and logged alongside the
    answer, but never changes it -- see the module docstring for why a value
    that no longer discriminates stock from overclocked on this kernel cannot
    be allowed to override the switch either way.
    """
    if not is_rp1_platform():
        return None

    requested_overclock = overlay_enabled()
    measured = measured_clk_sys_hz()

    rate = PIXEL_RATE_OVERCLOCKED if requested_overclock else PIXEL_RATE_STOCK
    logger.info(
        "RP1 regime: %s (clk_sys %s, observation only) -> %.0f MPix/s",
        "overclocked" if requested_overclock else "stock",
        f"{measured} Hz" if measured is not None else "unreadable",
        rate,
    )
    return rate
