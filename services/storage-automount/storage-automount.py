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


def _unmount(dev: str):
    mp = _mounts.pop(dev, None)
    if not mp:
        log.debug("Unmount requested for %s but not tracked", dev)
        return

    log.info("Unmounting %s from %s", dev, mp)
    res = subprocess.call(["umount", "-l", dev])
    if res == 0:
        if not _is_mp_busy(mp):
            try:
                mp.rmdir()
            except OSError as e:
                log.debug("Could not remove %s (%s)", mp, e)
        log.info("Unmounted %s OK", dev)
    else:
        log.error("umount %s failed with exit=%d", dev, res)


# ---------------------------------------------------------------------------
# udev monitoring thread
# ---------------------------------------------------------------------------

def _udev_worker():
    monitor = pyudev.Monitor.from_netlink(_udev_ctx)
    monitor.filter_by(subsystem="block", device_type="partition")
    log.debug("udev worker started")

    for action, device in monitor:
        devnode = device.device_node
        if action == "add":
            log.info("Device connected: %s", devnode)
            time.sleep(0.2)
            _mount(devnode)
        elif action == "remove":
            log.info("Device disconnected: %s", devnode)
            _unmount(devnode)



# ---------------------------------------------------------------------------
# CFE-HAT worker (edge-triggered buttons)
# ---------------------------------------------------------------------------
def _cfe_hat_worker():
    if smbus is None:
        log.debug("No smbus module, CFE-HAT thread disabled")
        return

    I2C_CH   = 1
    I2C_ADDR = 0x34
    try:
        bus = smbus.SMBus(I2C_CH)
        bus.read_byte(I2C_ADDR)          # probe once
    except OSError:
        log.info("CFE-HAT not detected on I²C, skipping thread")
        return

    led_on          = False
    consecutive_err = 0
    last_insert     = 0
    last_eject      = 0

    def _set_led(state: bool):
        nonlocal led_on
        led_on = state
        try:
            bus.write_byte(I2C_ADDR, 0x01 if state else 0x00)
        except OSError as e:
            log.error("CFE-HAT LED write error: %s", e)

    def _pcie_bind(bind: bool):
        path   = "/sys/bus/platform/drivers/brcm-pcie"
        node   = "1000110000.pcie"
        target = "bind" if bind else "unbind"
        try:
            with open(f"{path}/{target}", "w") as f:
                f.write(node)
            log.debug("PCIe %s OK", target)
        except OSError as e:
            if e.errno != errno.EBUSY:
                log.error("PCIe %s error: %s", target, e)
        if bind:
            time.sleep(0.5)
            subprocess.call(["sh", "-c", "echo 1 > /sys/bus/pci/rescan"])

    log.info("CFE-HAT thread started")
    while True:
        try:
            data = bus.read_byte(I2C_ADDR)
            consecutive_err = 0
        except OSError as e:
            if consecutive_err == 0:
                log.warning("CFE-HAT I²C read failed (%s) – retrying", e)
            consecutive_err = (consecutive_err + 1) % 300
            time.sleep(0.1)
            continue

        insert = 1 if (data & 0x01) else 0
        eject  = 1 if (data & 0x02) else 0

        # -------- insert button released (edge 1→0) -----------------
        if last_insert == 1 and insert == 0 and not led_on:
            log.info("CFE-HAT: insert button released → mount")
            _pcie_bind(True)
            _set_led(True)     # turns on immediately; unmount switches off

        # -------- eject button released (edge 1→0) ------------------
        if last_eject == 1 and eject == 0 and led_on:
            log.info("CFE-HAT: eject button released → unmount")
            for dev, mp in list(_mounts.items()):
                if mp.name == "RAW":
                    _unmount(dev)
            _pcie_bind(False)
            _set_led(False)

        last_insert, last_eject = insert, eject
        time.sleep(0.1)



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

    log.info("storage-automount started (log level %s)", LOG_LEVEL)
    while True:
        time.sleep(60)

# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
