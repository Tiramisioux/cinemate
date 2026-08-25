"""config.txt reader/writer for the settings editor's Boot Config pane.

There is no existing Python plumbing for config.txt anywhere in this
codebase. Cinemate supports independent dual-port sensor selection --
cam0 and cam1 each get their own `dtoverlay=<model>,camN[,mono]` line,
any of the known models on either port -- confirmed against
templates/settings_editor.html's cfgOverlayLine()/currentConfigText(),
which already define the canonical shape this module reads and writes:

    camera_auto_detect=<0 or 1>
    dtoverlay=<model>,cam0            # only if cam0 has a sensor selected
    dtoverlay=<model>,cam1[,mono]     # only if cam1 has a sensor selected

imx585 lines may also carry a link-frequency parameter, which is why the
overlay line is built and parsed rather than string-matched:

    dtoverlay=imx585,cam0,link-frequency=1039500000

Only the "# ---- Camera section ----" ... "# ---- End camera section ----"
sub-region and the standalone i2c/i2s/spi/audio/RP1-overclock toggle lines
are ever rewritten -- everything else in the managed block (and everything
outside it) is left byte-identical. A live boot config is not a safe place
to regenerate wholesale from a from-scratch template on every save.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

CONFIG_TXT_PATH = "/boot/firmware/config.txt"

# /boot/firmware is root-owned; the settings editor runs as an unprivileged
# user (F-288). STAGED_CONFIG_TXT_PATH is a fixed, pi-writable location the
# privileged helper below reads from -- fixed so the sudoers rule installed
# by configure_sudoers() can be scoped to one exact command with no
# arguments, rather than a general "write anywhere as root" grant.
STAGED_CONFIG_TXT_PATH = "/home/pi/cinemate/.settings-editor-config-txt.staged"
APPLY_CONFIG_TXT_HELPER = "/usr/local/bin/cinemate-apply-config-txt"

MANAGED_BEGIN = "# >>> cinemate-install >>>"
MANAGED_END = "# <<< cinemate-install <<<"
CAMERA_SECTION_BEGIN = "# ---- Camera section ----"
CAMERA_SECTION_END = "# ---- End camera section ----"

# Selectable models per port (templates/settings_editor.html's
# CFG_SENSOR_LABELS) -- only imx585 has a distinct mono variant key; other
# sensors don't get a separate "_mono" option here.
SENSOR_MODELS = ["none", "imx477", "imx296", "imx283", "imx585", "imx585_mono"]

_TOGGLE_LINES = {
    "i2c": "dtparam=i2c_arm=on",
    "i2s": "dtparam=i2s=on",
    "spi": "dtparam=spi=on",
    "audio": "dtparam=audio=on",
}
RP1_OVERCLOCK_LINE = "dtoverlay=rp1-overclock"

# CSI-2 link frequency, settable per port as a dtoverlay parameter:
#   dtoverlay=imx585,cam0,link-frequency=1039500000
#
# imx585 only. The other three sensors cannot offer this menu:
#   imx283  driver accepts 360/720 MHz, but its overlay exposes no
#           link-frequency override -- would need a patch to the driver fork
#   imx477  imx477_check_link_freq() accepts *any* exact multiple of 3 MHz
#           with no upper bound, so there is no list to offer that the driver
#           would actually vouch for. Only its 450 MHz default is proven.
#   imx296  no link-frequencies property at all; the sensor derives its own
#           MIPI timing (1122-1198 Mbps)
#
# Values and frame rates from will127534/imx585-v4l2-driver's README, which
# match link_freqs[] in the driver the installer builds. The driver also
# defines 1188000000, deliberately not offered: the README reports the Pi 4
# cannot do it and the Pi 5 drops frames.
#
# Anything above the 720 MHz default needs the RP1 overclock to be useful --
# a stock RP1 caps out around 43.8 fps at 4K no matter what the sensor sends.
# fps figures are the README's 4K 12-bit 4-lane column; halve for 2-lane, and
# again for ClearHDR. They are shipped to the settings editor rather than
# restated in JavaScript -- the ACTION_METHODS catalogue already demonstrates
# what a second hand-maintained copy costs.
IMX585_DEFAULT_LINK_FREQUENCY = 720000000
IMX585_LINK_FREQUENCY_TABLE = [
    {"hz": 297000000, "mbps_per_lane": 594, "fps_4k_4lane": 20.8},
    {"hz": 360000000, "mbps_per_lane": 720, "fps_4k_4lane": 25.0},
    {"hz": 445500000, "mbps_per_lane": 891, "fps_4k_4lane": 30.0},
    {"hz": 594000000, "mbps_per_lane": 1188, "fps_4k_4lane": 41.7},
    {"hz": 720000000, "mbps_per_lane": 1440, "fps_4k_4lane": 50.0},
    {"hz": 891000000, "mbps_per_lane": 1782, "fps_4k_4lane": 60.0},
    {"hz": 1039500000, "mbps_per_lane": 2079, "fps_4k_4lane": 75.0},
]
IMX585_LINK_FREQUENCIES = [entry["hz"] for entry in IMX585_LINK_FREQUENCY_TABLE]
LINK_FREQUENCY_MODELS = ("imx585", "imx585_mono")

_LINK_FREQUENCY_TOKEN = "link-frequency="

_DTOVERLAY_LINE_RE = re.compile(r"^(#?)dtoverlay=(\S+)\s*$", re.MULTILINE)


def supports_link_frequency(model: str) -> bool:
    return model in LINK_FREQUENCY_MODELS


def is_rpi2712_platform() -> bool:
    """Mirrors cinemate-install.sh's is_rpi2712_platform() (line ~414):
    RP1 overclock only applies to BCM2712 boards (Pi 5 / CM5)."""
    try:
        return "bcm2712" in Path("/proc/device-tree/compatible").read_bytes().decode("ascii", "ignore")
    except OSError:
        return False


def overlay_line_for(model: str, port: str, link_frequency: int | None = None) -> str | None:
    """dtoverlay line text (no leading '#') for *model* on *port*
    ('cam0'/'cam1'), or None for 'none'. Matches concept.html's
    cfgOverlayLine() exactly, plus the optional link-frequency parameter.

    *link_frequency* is only emitted for a model that supports it and only
    when it differs from that model's default -- the overlay's own default
    is the same value, so writing it out adds a number to config.txt that
    the reader then has to look up to discover means "unchanged"."""
    if model == "none":
        return None
    base = model[:-len("_mono")] if model.endswith("_mono") else model
    mono_suffix = ",mono" if model == "imx585_mono" else ""
    link_suffix = ""
    if (
        supports_link_frequency(model)
        and link_frequency is not None
        and link_frequency != IMX585_DEFAULT_LINK_FREQUENCY
    ):
        link_suffix = f",{_LINK_FREQUENCY_TOKEN}{link_frequency}"
    return f"dtoverlay={base},{port}{mono_suffix}{link_suffix}"


def _model_from_overlay_value(value: str) -> tuple[str | None, str | None, int | None]:
    """Parse a dtoverlay value (everything after 'dtoverlay=') into
    (model, port, link_frequency), or (None, None, None) if it doesn't target
    cam0/cam1 at all (e.g. vc4-kms-v3d, dwc2, disable-bt, rp1-overclock --
    unrelated overlays that also live in this file)."""
    tokens = value.split(",")
    port = "cam0" if "cam0" in tokens else "cam1" if "cam1" in tokens else None
    if port is None:
        return None, None, None
    mono = "mono" in tokens

    link_frequency = None
    for token in tokens:
        if token.startswith(_LINK_FREQUENCY_TOKEN):
            raw = token[len(_LINK_FREQUENCY_TOKEN):]
            # A hand-edited config.txt can hold anything. An unparseable value
            # means "we don't know", not zero -- reporting 0 back to the editor
            # would let a save quietly overwrite whatever the operator wrote.
            link_frequency = int(raw) if raw.isdigit() else None

    model_tokens = [
        t for t in tokens
        if t not in ("cam0", "cam1", "mono") and not t.startswith(_LINK_FREQUENCY_TOKEN)
    ]
    if not model_tokens:
        return None, None, None
    base = model_tokens[0]
    model = f"{base}_mono" if (base == "imx585" and mono) else base
    return model, port, link_frequency


def default_config_state() -> dict:
    """The clean-install default shape: IMX477 active on cam0, cam1 empty,
    i2c on, i2s/spi off, audio on, RP1 overclock off."""
    return {
        "cam0_sensor": "imx477",
        "cam1_sensor": "none",
        "cam0_link_frequency": None,
        "cam1_link_frequency": None,
        "i2c": True,
        "i2s": False,
        "spi": False,
        "audio": True,
        "rp1_overclock": False,
        "rp1_available": is_rpi2712_platform(),
        "link_frequencies": IMX585_LINK_FREQUENCY_TABLE,
        "link_frequency_default": IMX585_DEFAULT_LINK_FREQUENCY,
    }


def _extract(text: str, begin: str, end: str) -> tuple[str | None, int, int]:
    start = text.find(begin)
    if start == -1:
        return None, -1, -1
    stop = text.find(end, start)
    if stop == -1:
        return None, -1, -1
    stop += len(end)
    return text[start:stop], start, stop


def parse_config_txt(full_text: str) -> dict:
    block, _start, _end = _extract(full_text, MANAGED_BEGIN, MANAGED_END)
    if block is None:
        state = default_config_state()
        state["found"] = False
        return state

    cam_section, _cs, _ce = _extract(block, CAMERA_SECTION_BEGIN, CAMERA_SECTION_END)
    cam0_sensor = "none"
    cam1_sensor = "none"
    cam0_link_frequency = None
    cam1_link_frequency = None
    if cam_section:
        for commented, value in _DTOVERLAY_LINE_RE.findall(cam_section):
            if commented:
                continue
            model, port, link_frequency = _model_from_overlay_value(value)
            if model is None:
                continue
            if port == "cam0":
                cam0_sensor = model
                cam0_link_frequency = link_frequency
            elif port == "cam1":
                cam1_sensor = model
                cam1_link_frequency = link_frequency

    def _line_on(marker: str) -> bool:
        return bool(re.search(r"^" + re.escape(marker) + r"\s*$", block, re.MULTILINE))

    rp1_present = bool(re.search(
        r"^#?" + re.escape(RP1_OVERCLOCK_LINE) + r"\s*$", block, re.MULTILINE,
    ))

    return {
        "found": True,
        "cam0_sensor": cam0_sensor,
        "cam1_sensor": cam1_sensor,
        # None means "the overlay default", which is what an absent parameter
        # means to the driver too -- don't substitute the number here, or a
        # later save would write it out as if the operator had chosen it.
        "cam0_link_frequency": cam0_link_frequency,
        "cam1_link_frequency": cam1_link_frequency,
        "i2c": _line_on(_TOGGLE_LINES["i2c"]),
        "i2s": _line_on(_TOGGLE_LINES["i2s"]),
        "spi": _line_on(_TOGGLE_LINES["spi"]),
        "audio": _line_on(_TOGGLE_LINES["audio"]),
        "rp1_overclock": _line_on(RP1_OVERCLOCK_LINE),
        "rp1_available": rp1_present,
        "link_frequencies": IMX585_LINK_FREQUENCY_TABLE,
        "link_frequency_default": IMX585_DEFAULT_LINK_FREQUENCY,
    }


def _render_camera_section(
    cam0_sensor: str,
    cam1_sensor: str,
    cam0_link_frequency: int | None = None,
    cam1_link_frequency: int | None = None,
) -> str:
    lines = [
        overlay_line_for(cam0_sensor, "cam0", cam0_link_frequency),
        overlay_line_for(cam1_sensor, "cam1", cam1_link_frequency),
    ]
    lines = [l for l in lines if l]
    auto_detect = "1" if lines else "0"
    if not lines:
        lines = ["# no camera overlay selected"]
    return "\n".join([
        CAMERA_SECTION_BEGIN,
        "",
        f"camera_auto_detect={auto_detect}",
        *lines,
        "",
        CAMERA_SECTION_END,
    ])


def _validated_link_frequency(value, model: str, port: str) -> int | None:
    """Coerce an editor-supplied link frequency for *port*, or raise.

    A wrong value here doesn't fail loudly on the Pi -- the sensor either
    refuses to probe at boot or streams at a rate the receiver can't hold,
    both of which surface as "the camera stopped working" long after the
    save. Reject at the point the operator can still see why.
    """
    if value is None or value == "":
        return None

    # An empty port has nothing to configure. The form can still be carrying a
    # frequency from the sensor that was selected a moment ago; that is not a
    # mismatch worth failing a save over, since no overlay line is emitted.
    if model == "none":
        return None

    try:
        frequency = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{port} link frequency must be a whole number of Hz, got {value!r}")

    if not supports_link_frequency(model):
        raise ValueError(
            f"{port} is set to {model}, which has no selectable link frequency. "
            f"Only {' / '.join(LINK_FREQUENCY_MODELS)} does."
        )

    if frequency not in IMX585_LINK_FREQUENCIES:
        allowed = ", ".join(str(f) for f in IMX585_LINK_FREQUENCIES)
        raise ValueError(
            f"{frequency} is not a supported imx585 link frequency. Supported: {allowed}."
        )

    return frequency


def apply_config_txt_state(full_text: str, state: dict) -> str:
    """Return *full_text* with only the editor-exposed lines touched inside
    the existing managed block. Raises ValueError if no managed block is
    present (this module never synthesizes one from scratch on a live
    file -- see module docstring)."""
    block, start, end = _extract(full_text, MANAGED_BEGIN, MANAGED_END)
    if block is None:
        raise ValueError(
            f"No managed block ({MANAGED_BEGIN} ... {MANAGED_END}) found in "
            f"{CONFIG_TXT_PATH} -- refusing to synthesize one on a live file."
        )

    cam0_sensor = state.get("cam0_sensor", "none")
    cam1_sensor = state.get("cam1_sensor", "none")
    cam0_link = _validated_link_frequency(state.get("cam0_link_frequency"), cam0_sensor, "cam0")
    cam1_link = _validated_link_frequency(state.get("cam1_link_frequency"), cam1_sensor, "cam1")

    cam_section, cs, ce = _extract(block, CAMERA_SECTION_BEGIN, CAMERA_SECTION_END)
    new_block = block
    if cam_section is not None:
        replacement = _render_camera_section(cam0_sensor, cam1_sensor, cam0_link, cam1_link)
        new_block = block[:cs] + replacement + block[ce:]

    for key, marker in _TOGGLE_LINES.items():
        if key not in state:
            continue
        prefix = "" if state[key] else "#"
        new_block = re.sub(
            r"^#?" + re.escape(marker) + r"\s*$",
            f"{prefix}{marker}",
            new_block,
            flags=re.MULTILINE,
        )

    if "rp1_overclock" in state:
        prefix = "" if state["rp1_overclock"] else "#"
        new_block, substitutions = re.subn(
            r"^#?" + re.escape(RP1_OVERCLOCK_LINE) + r"\s*$",
            f"{prefix}{RP1_OVERCLOCK_LINE}",
            new_block,
            flags=re.MULTILINE,
        )
        # No line to comment or uncomment. Turning the overclock *off* is
        # still honest -- absent means off. Turning it *on* is not: the
        # substitution changed nothing, but put_config_txt would report
        # success and reboot, and the operator would come back to a Pi still
        # on stock clocks with nothing explaining why. Only Pi 5 / CM5
        # installs get this line (configure_boot_config), so this is also
        # what a Pi 4 asking for an overclock hits.
        if substitutions == 0 and state["rp1_overclock"]:
            raise ValueError(
                f"Cannot enable the RP1 overclock: no '{RP1_OVERCLOCK_LINE}' line in "
                f"{CONFIG_TXT_PATH}. cinemate-install.sh writes it on Pi 5 / CM5 boards "
                f"only -- re-run the installer to add it."
            )

    return full_text[:start] + new_block + full_text[end:]


def _atomic_write(dest: Path, text: str) -> None:
    fd, tmp_path = tempfile.mkstemp(
        dir=str(dest.parent), prefix=".settings-editor-", suffix=dest.suffix + ".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(text)
        os.replace(tmp_path, dest)
    except Exception:
        os.unlink(tmp_path)
        raise


def write_config_txt(text: str) -> None:
    """Atomically replace CONFIG_TXT_PATH with *text* (F-288).

    /boot/firmware is root-owned and the settings editor runs as an
    unprivileged user, so the direct write below only succeeds when this
    process already has root (tests, or a root-run dev shell) -- on a real
    install it raises PermissionError before writing a byte. Only that
    specific failure falls back to staging the text somewhere pi-writable
    and handing it to APPLY_CONFIG_TXT_HELPER, a narrowly-scoped privileged
    helper installed by cinemate-install.sh's configure_sudoers(). Any other
    OSError (full disk, missing directory) is left to surface directly
    rather than being redirected into the harder-to-debug sudo path.
    """
    dest = Path(CONFIG_TXT_PATH)
    try:
        _atomic_write(dest, text)
        return
    except PermissionError:
        pass

    staged = Path(STAGED_CONFIG_TXT_PATH)
    _atomic_write(staged, text)
    try:
        result = subprocess.run(
            ["sudo", "-n", APPLY_CONFIG_TXT_HELPER],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        staged.unlink(missing_ok=True)
        raise PermissionError(f"could not invoke privileged helper: {exc}") from exc

    if result.returncode != 0:
        staged.unlink(missing_ok=True)
        detail = (result.stderr or result.stdout or "").strip()
        raise PermissionError(f"privileged helper exited {result.returncode}: {detail}")
