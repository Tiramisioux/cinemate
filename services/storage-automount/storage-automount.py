#!/usr/bin/env python3
"""
Consolidated automounter for Raspberry Pi 5.

Extensive logging version.
"""

import errno
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pyudev                    # sudo apt install python3-pyudev
try:
    import smbus                 # sudo apt install python3-smbus
except ImportError:
    smbus = None

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv("STORAGE_AUTOMOUNT_LOG", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [storage-automount] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,            # journald captures stderr into the journal
)
log = logging.getLogger("storage-automount")

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

PI_UID     = "1000"
PI_GID     = "1000"
MOUNT_BASE = Path("/media")

FS_OPTS = {
    "ext4":  "rw,noatime",
    "ntfs":  f"uid={PI_UID},gid={PI_GID},rw,noatime,umask=000",
    "exfat": f"uid={PI_UID},gid={PI_GID},rw,noatime",
}

_udev_ctx = pyudev.Context()
_mounts   = {}          # devnode -> Path


def _sanitize(label: str) -> str:
    return re.sub(r"[^\w\-.]", "_", label)[:64] or "RAW"


def _get_fs(dev: str):
    try:
        label  = subprocess.check_output(
            ["blkid", "-s", "LABEL", "-o", "value", dev], text=True
        ).strip()
        fstype = subprocess.check_output(
            ["blkid", "-s", "TYPE", "-o", "value", dev], text=True
        ).strip()
        return label, fstype
    except subprocess.CalledProcessError as e:
        log.warning("blkid failed on %s: %s", dev, e)
        return None, None
    
# ---------------------------------------------------------------------------
# Helpers to detect existing mounts / busy directories
# ---------------------------------------------------------------------------

def _is_dev_mounted(dev: str) -> bool:
    """Return True if the device node is already mounted somewhere."""
    with open("/proc/self/mountinfo", "r") as f:
        return any(line.split()[9] == dev for line in f)

def _is_mp_busy(mp: Path) -> bool:
    """Return True if some process still holds the directory open."""
    try:
        mp.rmdir()                      # succeeds only if not busy / empty
        mp.mkdir(parents=True, exist_ok=True)
        return False
    except OSError:
        return True

def _auto_repair(dev: str, fstype: str) -> bool:
    """Try once to repair a dirty filesystem.  Return True if repair *and*
    subsequent fsck indicate the FS is OK enough to retry the mount."""
    if fstype == "ext4":
        log.warning("Repairing %s with e2fsck -p", dev)
        res = subprocess.call(["e2fsck", "-f", "-p", dev])
        ok  = res in (0, 1, 2)          # 0=clean, 1/2=repaired
    elif fstype == "ntfs":
        log.warning("Repairing %s with ntfsfix", dev)
        ok = subprocess.call(["ntfsfix", dev]) == 0
    elif fstype == "exfat":
        log.warning("Repairing %s with fsck.exfat -a", dev)
        ok = subprocess.call(["fsck.exfat", "-a", dev]) == 0
    else:
        ok = False

    if ok:
        log.info("%s: repair successful", dev)
    else:
        log.error("%s: repair failed (filesystem still dirty)", dev)
    return ok

# ────────────────────────────────────────────────────────────────
# NEW: watchdog that cleans up when the NVMe controller dies
# ────────────────────────────────────────────────────────────────
def _dead_nvme_cleanup():
    """
    Kernel marks a failed PCIe/NVMe endpoint as  ‘dead’.
    When that happens we force-unmount the corresponding RAW partition so
    user-space does not continue to write to a read-only / stale mount.
    """
    for dev, mp in list(_mounts.items()):
        if not dev.startswith("/dev/nvme"):
            continue

        state_file = Path(f"/sys/block/{Path(dev).name}/device/state")
        try:
            state = state_file.read_text().strip()
        except (OSError, FileNotFoundError):
            # sysfs node disappeared already → treat like “dead”
            state = "dead"

        if state == "dead":
            log.warning(
                "NVMe controller for %s reported state=dead – "
                "forcing lazy unmount.  "
                "This *usually* means a power-dip or cable issue.",
                dev
            )
            _unmount(dev)
# ────────────────────────────────────────────────────────────────

# ---------------------------------------------------------------------------
# Watchdog thread
# ---------------------------------------------------------------------------
def _nvme_watchdog():
    log.debug("NVMe watchdog thread started")
    while True:
        _dead_nvme_cleanup()
        time.sleep(1.0)

                     # timed-out

# ---------------------------------------------------------------------------
# Guard against stale /media/RAW directories
# ---------------------------------------------------------------------------
def _purge_stale_mountpoints() -> None:
    """
    Remove or rename any RAW mount-point that is *not* a real mount.
    Called once at startup, and used by _mount() as a last-second check.
    """
    mp = MOUNT_BASE / "RAW"
    if not mp.exists():
        return            # nothing to do

    if os.path.ismount(mp):
        return            # an actual drive is already mounted

    try:
        # empty → safe to delete
        mp.rmdir()
        log.info("Removed empty stale mount-point %s", mp)
    except OSError:
        # not empty → rename so the user notices, but we never write there
        ts   = time.strftime("%Y%m%d-%H%M%S")
        new  = mp.with_name(f"RAW.STALE-{ts}")
        try:
            mp.rename(new)
            log.warning("%s existed but was not a mount-point → renamed to %s",
                        mp, new)
        except OSError as exc:
            log.error("Cannot rename busy directory %s (%s) — aborting start-up",
                      mp, exc)
            sys.exit(1)   # hard fail: better to stop than risk data loss


# ---------------------------------------------------------------------------
# Mount / unmount
# ---------------------------------------------------------------------------

def _mount(dev: str):
    if dev in _mounts:
        log.debug("%s already mounted by this daemon – skipping", dev)
        return

    # Skip partitions the system already mounted (e.g. /boot/firmware)
    if _is_dev_mounted(dev):
        log.debug("%s is already mounted elsewhere – skipping", dev)
        return

    label, fstype = _get_fs(dev)
    if not fstype:
        log.warning("%s: unknown filesystem – skipping", dev)
        return

    mp = MOUNT_BASE / _sanitize(label or Path(dev).name)
    
    # Safety: if RAW exists already and is not a mount-point, abort
    if mp.exists() and not os.path.ismount(mp):
        log.error("%s already exists and is not a mount-point — refusing to mount "
                  "to avoid data loss.  Remove/rename it manually.", mp)
        return

    mp.mkdir(parents=True, exist_ok=True)

    opts = FS_OPTS.get(fstype, "rw,noatime")
    cmd  = ["mount", "-t", fstype, "-o", opts, dev, str(mp)]

    log.info("Mounting %s (%s) → %s", dev, fstype, mp)
    res = subprocess.call(cmd)
    if res == 0:
        _mounts[dev] = mp
        subprocess.call(["chown", "-R", f"{PI_UID}:{PI_GID}", str(mp)])
        log.info("Mounted %s OK", dev)
    else:
        log.error("Mount failed (%s) exit=%d", " ".join(cmd), res)
        # ONE automatic repair attempt
        if _auto_repair(dev, fstype):
            log.info("%s: repair successful, retrying mount", dev)
            if subprocess.call(cmd) == 0:
                _mounts[dev] = mp
                subprocess.call(["chown", "-R", f"{PI_UID}:{PI_GID}", str(mp)])
                log.info("Mounted %s OK after repair", dev)
                return
        log.error("%s: repair attempt did not resolve the problem", dev)
        try:
            mp.rmdir()

        except OSError as e:
            log.debug("Mountpoint %s left in place (%s)", mp, e)
# ---------------------------------------------------------------------------
# helper: lazy-umount by mount-point when /dev node is already gone
# ---------------------------------------------------------------------------
def _lazy_umount_mp(mp: Path, retries: int = 10) -> bool:
    """
    Issue “umount -l <mountpoint>” repeatedly until the kernel drops the entry
    (or until *retries* attempts have been made).  Returns True on success.
    """
    for _ in range(retries):
        if not os.path.ismount(mp):
            return True
        subprocess.call(["umount", "-l", str(mp)])
        time.sleep(0.2)
    return False

# ---------------------------------------------------------------------------
# tiny helper — wait up to `timeout` s until RAW is mounted
# ---------------------------------------------------------------------------
def _wait_for_raw_mount(timeout: float = 8.0) -> bool:
    mp = MOUNT_BASE / "RAW"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.ismount(mp):
            return True                 # success
        time.sleep(0.2)
    return False   

# ---------------------------------------------------------------------------
# helpers – wait for RAW to appear / disappear
# ---------------------------------------------------------------------------
def _wait_for_raw_mount(timeout: float = 8.0) -> bool:
    """Return True as soon as /media/RAW becomes a mount-point (≤ timeout s)."""
    mp = MOUNT_BASE / "RAW"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.ismount(mp):
            return True
        time.sleep(0.2)
    return False


def _wait_for_raw_unmount(timeout: float = 5.0) -> bool:
    """Return True once /media/RAW is no longer mounted (≤ timeout s)."""
    mp = MOUNT_BASE / "RAW"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not os.path.ismount(mp):
            return True
        time.sleep(0.2)
    return False


def _unmount(dev: str):
    mp = _mounts.pop(dev, None)
    if not mp:
        log.debug("Unmount requested for %s but not tracked", dev)
        return

    log.info("Unmounting %s from %s", dev, mp)

    # first try the normal way (might fail if /dev vanished)
    res = subprocess.call(["umount", dev])

    if res != 0:                      # e.g. ENOENT or EBUSY
        log.warning("umount %s failed (exit=%d) – retrying lazy by mount-point",
                    dev, res)
        if not _lazy_umount_mp(mp):
            log.error("Lazy umount also failed, mount is still busy")
            return                    # give up, keep it in _mounts

    # success – tidy up
    if not _is_mp_busy(mp):
        try:
            mp.rmdir()
        except OSError:
            pass
    log.info("Unmounted %s OK", dev)

    
# ---------------------------------------------------------------------------
# helper: force a lazy unmount of a RAW partition
# ---------------------------------------------------------------------------
def _force_lazy_unmount(dev: str, retries: int = 10) -> bool:
    """
    Try to unmount *dev* cleanly; if that fails, repeatedly issue
        umount -l <mountpoint>
    until the kernel drops the entry or *retries* attempts were made.

    Returns True when the mount is gone, False otherwise.
    """
    mp = _mounts.get(dev)
    if mp is None:
        return False                         # not tracked → nothing to do

    # 1️⃣  normal umount first (may fail with ENOENT / EBUSY)
    if subprocess.call(["umount", dev]) == 0:
        ok = True
    else:
        # 2️⃣  fall back to lazy unmount by mount-point
        ok = False
        for _ in range(retries):
            if not os.path.ismount(mp):
                ok = True
                break
            subprocess.call(["umount", "-l", str(mp)])
            time.sleep(0.2)

    if ok:
        _mounts.pop(dev, None)               # remove from our table
        try:
            if not os.path.ismount(mp) and not _is_mp_busy(mp):
                mp.rmdir()
        except OSError:
            pass
    return ok



# ---------------------------------------------------------------------------
# udev monitoring thread
# ---------------------------------------------------------------------------

def _udev_worker():
    monitor = pyudev.Monitor.from_netlink(_udev_ctx)
    # watch both whole disks *and* partitions
    monitor.filter_by(subsystem="block")
    log.debug("udev worker started")

    for action, device in monitor:
        devnode = device.device_node
        dtype   = device.get('DEVTYPE')  # "disk" or "partition"

        if action == "add" and dtype == "partition":
            log.info("Partition connected: %s", devnode)
            time.sleep(0.2)
            _mount(devnode)

        elif action == "remove":
            log.info("Block device removed: %s", devnode)

            # <── NEW: if we still see a RAW mount but the /dev node just vanished
            for d, p in list(_mounts.items()):
                if not Path(d).exists():          # /dev/nvme… gone
                    _unmount(d)

# ---------------------------------------------------------------------------
# CFE-HAT worker  (robust edge-detector + verbose debug)
# ---------------------------------------------------------------------------
def _cfe_hat_worker():
    if smbus is None:
        log.debug("No smbus module, CFE-HAT thread disabled")
        return

    I2C_CH, I2C_ADDR = 1, 0x34
    try:
        bus = smbus.SMBus(I2C_CH)
        bus.read_byte(I2C_ADDR)           # probe once
    except OSError:
        log.info("CFE-HAT not detected on I²C, skipping thread")
        return

    led_on = False
    last_state = 0x00                     # initialise with *current* state
    try:
        last_state = bus.read_byte(I2C_ADDR)
    except OSError:
        pass                               # keep 0x00 if read failed

    log.info("CFE-HAT thread started — idle byte 0x%02X", last_state)

    # helper -----------------------------------------------------------
    def _set_led(state: bool):
        nonlocal led_on
        if state == led_on:
            return
        led_on = state
        try:
            bus.write_byte(I2C_ADDR, 0x01 if state else 0x00)
            log.debug("LED %s", "ON" if state else "OFF")
        except OSError as e:
            log.warning("CFE-HAT LED write error: %s", e)

    def _pcie_bind(bind: bool):
        path, node = "/sys/bus/platform/drivers/brcm-pcie", "1000110000.pcie"
        target = "bind" if bind else "unbind"
        try:
            with open(f"{path}/{target}", "w") as f:
                f.write(node)
            log.debug("PCIe %s OK", target)
        except OSError as e:
            if e.errno != errno.EBUSY:
                log.warning("PCIe %s error: %s", target, e)
        if bind:
            time.sleep(0.5)
            subprocess.call(["sh", "-c", "echo 1 > /sys/bus/pci/rescan"])

    # main loop --------------------------------------------------------
    while True:
        try:
            state = bus.read_byte(I2C_ADDR)
        except OSError as e:
            log.debug("I²C read error: %s", e)
            time.sleep(0.1)
            continue

        # bits: 0x01 = insert, 0x02 = eject
        ins_now, ej_now   = state & 1, (state >> 1) & 1
        ins_prev, ej_prev = last_state & 1, (last_state >> 1) & 1
        last_state = state                                          # update

        # ---------- INSERT -------------------------------------------
        if ins_prev == 0 and ins_now == 1:          # button down
            log.debug("Insert pressed")

        if ins_prev == 1 and ins_now == 0:          # button released
            log.info("Insert released → attempt mount")
            _pcie_bind(True)                        # power up PCIe
            _set_led(True)                          # LED immediately on

            if _wait_for_raw_mount():               # <── NEW
                log.info("Insert: mount succeeded ✓")
            else:
                log.warning("Insert: mount FAILED (timeout) ✗  – "
                            "check NVMe, cable, power")
                _set_led(False)                     # leave LED off if failed

        # ---------- EJECT --------------------------------------------
        if ej_prev == 0 and ej_now == 1:
            log.debug("Eject pressed")

        if ej_prev == 1 and ej_now == 0:
            log.info("Eject released → unmount request")
            any_ok = False
            for dev in list(_mounts):
                if _force_lazy_unmount(dev):
                    any_ok = True

            if any_ok:
                if _wait_for_raw_unmount():         # <── NEW
                    log.info("Eject: unmount succeeded ✓")
                else:
                    log.warning("Eject: unmount timed-out (busy) ✗")
                _pcie_bind(False)
                _set_led(False)
            else:
                log.warning("Eject: no RAW partition was mounted")

        time.sleep(0.05)        # 20 Hz polling is plenty

# ---------------------------------------------------------------------------
# Initial scan
# ---------------------------------------------------------------------------

def _initial_scan():
    _purge_stale_mountpoints()
    log.debug("Initial device scan")
    for dev in _udev_ctx.list_devices(subsystem="block", DEVTYPE="partition"):
        _mount(dev.device_node)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    def _sigterm(_sig, _frm):
        log.info("SIGTERM received, unmounting everything")
        for dev in list(_mounts):
            _unmount(dev)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm)

    _initial_scan()

    threading.Thread(target=_udev_worker,   daemon=True).start()
    threading.Thread(target=_cfe_hat_worker, daemon=True).start()
    threading.Thread(target=_nvme_watchdog,   daemon=True).start()   

    log.info("storage-automount started (log level %s)", LOG_LEVEL)
    while True:
        time.sleep(60)

# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
