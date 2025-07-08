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

# ─── RAW arbitration helpers ───────────────────────────────────────────
_raw_pool    = []          # list of /dev/… currently present and LABEL==RAW
_active_raw  = None        # the device node that is mounted at /media/RAW
_raw_lock    = threading.Lock()   # <── add this line


def _register_raw_add(dev: str):
    if dev not in _raw_pool:
        _raw_pool.append(dev)

def _register_raw_remove(dev: str):
    if dev in _raw_pool:
        _raw_pool.remove(dev)

def _switch_to_raw(dev: str | None):
    """Mount *dev* (LABEL=RAW) and unmount the previous one."""
    global _active_raw
    if dev == _active_raw:
        return                          # nothing to do
    if _active_raw is not None:
        _unmount(_active_raw)
    if dev is not None:
        _mount(dev)
    _active_raw = dev

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


def _get_fs(dev: str, retries: int = 3, delay: float = 0.5):
    """
    Return (LABEL, FSTYPE) of *dev*.  Retry a few times because NVMe
    partitions on the CFE-Hat can need a second or two to become readable.
    """
    for i in range(retries):
        try:
            label = subprocess.check_output(
                ["blkid", "-s", "LABEL", "-o", "value", dev], text=True
            ).strip()
            fstype = subprocess.check_output(
                ["blkid", "-s", "TYPE", "-o", "value", dev], text=True
            ).strip()
            if fstype:
                return label, fstype
        except subprocess.CalledProcessError:
            pass
        if i < retries - 1:
            time.sleep(delay)
    log.warning("blkid retries exhausted for %s", dev)
    return None, None

    
# ---------------------------------------------------------------------------
# Helpers to detect existing mounts / busy directories
# ---------------------------------------------------------------------------

def _is_dev_mounted(dev: str) -> bool:
    """
    Return True if *dev* already shows up in /proc/self/mountinfo.

    We split each line at the first ' - ' (kernel field separator).  The
    first token after that is the filesystem type, the second is the
    device node we want to compare with.
    """
    with open("/proc/self/mountinfo", "r") as f:
        for line in f:
            try:
                after_dash = line.split(" - ", 1)[1]
                source = after_dash.split()[1]      # fs-source (device node)
                if source == dev:
                    return True
            except IndexError:
                continue          # malformed line (should never happen)
    return False

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
# Watchdog that cleans up when the NVMe controller dies
# ────────────────────────────────────────────────────────────────
def _dead_nvme_cleanup():
    """
    If an NVMe controller reports state=dead, lazily unmount the RAW
    partition so user-space stops writing to a read-only mount.
    """
    for dev, mp in list(_mounts.items()):
        if not dev.startswith("/dev/nvme"):
            continue

        # ── translate /dev/nvme0n1p1 → nvme0n1 ───────────────────────────
        root = Path(dev).name          # nvme0n1p1
        if "p" in root:
            root = root.split("p", 1)[0]

        state_file = Path(f"/sys/block/{root}/device/state")
        if not state_file.exists():        # device already gone → ignore
            continue

        try:
            state = state_file.read_text().strip()
        except OSError:
            continue                       # transient read error – skip

        if state == "dead":
            log.warning(
                "NVMe controller for %s reported state=dead – "
                "forcing lazy unmount.  "
                "This usually means a power-dip or cable issue.",
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
        time.sleep(0.5)

                     # timed-out

# ---------------------------------------------------------------------------
# Guard against stale /media/RAW directories
# ---------------------------------------------------------------------------
def _purge_stale_mountpoints() -> None:
    """
    Ensure that an existing /media/RAW directory can never block a future
    mount attempt.  Empty → delete.  Non-empty → rename to RAW.STALE-YYYYmmdd-HHMMSS.
    """
    mp = MOUNT_BASE / "RAW"
    if not mp.exists():
        return

    if os.path.ismount(mp):
        return  # an actual drive is mounted – leave it alone

    if not any(mp.iterdir()):
        try:
            mp.rmdir()
            log.info("Removed empty stale mount-point %s", mp)
        except OSError as exc:
            log.warning("Unable to remove %s: %s", mp, exc)
        return

    ts  = time.strftime("%Y%m%d-%H%M%S")
    new = mp.with_name(f"RAW.STALE-{ts}")
    try:
        mp.rename(new)
        log.warning("%s existed but was not a mount-point → renamed to %s",
                    mp, new)
    except OSError as exc:
        log.error("Cannot rename busy directory %s (%s) — aborting start-up",
                  mp, exc)
        sys.exit(1)



# ---------------------------------------------------------------------------
# Mount / unmount
# ---------------------------------------------------------------------------

def _mount(dev: str):
    """
    Mount *dev* under /media/<LABEL> (or a sanitised fall-back name).

    Improvements vs. the original version
        •  Purges/renames any stale /media/RAW (or other) directory first.
        •  Cleans stale bookkeeping entries so a manual umount/yank never
           blocks the next mount.
        •  Falls straight through if some other process already mounted it.
        •  Replaces the slow recursive chown with a single os.chown() on
           the mount-point – fast enough but still guarantees pi can write.
    """
    # 0 ── one-time sanitation (kills blocking /media/RAW folders) ──────────
    _purge_stale_mountpoints()

    # 1 ── reconcile bookkeeping with reality ──────────────────────────────
    mp_prev = _mounts.get(dev)
    if mp_prev and not os.path.ismount(mp_prev):
        log.info("Cleaning up stale mount record for %s", dev)
        _mounts.pop(dev, None)

    if dev in _mounts:                    # already mounted by *us*
        log.debug("%s already mounted by this daemon – skipping", dev)
        return

    if _is_dev_mounted(dev):              # mounted by something else (fstab…)
        log.debug("%s is already mounted elsewhere – skipping", dev)
        return

    # 2 ── discover filesystem & label ──────────────────────────────────────
    label, fstype = _get_fs(dev)
    if not fstype:
        log.warning("%s: unknown filesystem – skipping", dev)
        return

    mp = MOUNT_BASE / _sanitize(label or Path(dev).name)
    mp.mkdir(parents=True, exist_ok=True)

    # 3 ── assemble mount command ───────────────────────────────────────────
    opts = FS_OPTS.get(fstype, "rw,noatime")
    cmd  = ["mount", "-t", fstype, "-o", opts, dev, str(mp)]

    log.info("Mounting %s (%s) → %s", dev, fstype, mp)
    if subprocess.call(cmd) == 0:
        # ── success ───────────────────────────────────────────────────────
        _mounts[dev] = mp
        try:
            os.chown(mp, int(PI_UID), int(PI_GID))   # fast, non-recursive
        except Exception as exc:
            log.debug("Unable to chown %s: %s (continuing)", mp, exc)
        log.info("Mounted %s OK", dev)
        return

    # 4 ── first try failed – attempt automatic repair once ────────────────
    log.error("Mount failed (%s)", " ".join(cmd))
    if _auto_repair(dev, fstype):
        log.info("%s: repair successful, retrying mount", dev)
        if subprocess.call(cmd) == 0:
            _mounts[dev] = mp
            try:
                os.chown(mp, int(PI_UID), int(PI_GID))
            except Exception as exc:
                log.debug("Unable to chown %s after repair: %s", mp, exc)
            log.info("Mounted %s OK after repair", dev)
            return

    # 5 ── still failing – clean up the empty directory so it won’t block ──
    log.error("%s: repair attempt did not resolve the problem", dev)
    try:
        mp.rmdir()
    except OSError as exc:
        log.debug("Mountpoint %s left in place (%s)", mp, exc)
        
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
# wait until /media/RAW is **not** a mount-point
# ---------------------------------------------------------------------------
def _wait_for_raw_unmount(timeout: float = 3.0) -> bool:
    mp = MOUNT_BASE / "RAW"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not os.path.ismount(mp):
            return True
        time.sleep(0.2)
    return False

def _unmount(dev: str):
    
    if dev not in _mounts:
        return          # already cleaned up – no need to log again

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
# helper: fast lazy-unmount of a RAW partition
# ---------------------------------------------------------------------------
def _force_lazy_unmount(dev: str, retries: int = 20) -> bool:
    """
    Immediately detach *dev* with  “umount -l <mountpoint>”.
    Poll up to `retries`×0.1 s until the kernel drops the entry.
    Returns True when the mount is gone.
    """
    mp = _mounts.get(dev)
    if mp is None:
        return False                            # nothing to do

    # one non-blocking lazy-umount
    subprocess.call(["umount", "-l", str(mp)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)

    for _ in range(retries):                    # ≤ 2 s total
        if not os.path.ismount(mp):
            _mounts.pop(dev, None)              # tidy table
            try:
                if not _is_mp_busy(mp):
                    mp.rmdir()
            except OSError:
                pass
            return True
        time.sleep(0.1)

    log.warning("Lazy unmount timeout for %s", dev)
    return False

# ---------------------------------------------------------------------------
# udev monitoring thread
# ---------------------------------------------------------------------------

def _udev_worker():
    """
    Handle all block-layer udev events, not just partitions.

    •  add/partition   → normal _mount() or RAW arbitration
    •  remove/partition→ _unmount() (current logic)
    •  remove/disk     → unmount every partition that belongs to the disk,
                         then run RAW arbitration fallback.
    """
    monitor = pyudev.Monitor.from_netlink(_udev_ctx)
    monitor.filter_by(subsystem="block")
    log.debug("udev worker started")

    for action, device in monitor:
        devnode = device.device_node           # e.g. /dev/nvme0n1p1
        dtype   = device.get("DEVTYPE")        # "disk" or "partition"

        # ---------- device appeared / became ready --------------------
        if action in ("add", "change") and dtype == "partition":
            label, _ = _get_fs(devnode)
            if label == "RAW":
                _register_raw_add(devnode)
                _switch_to_raw(devnode)
            else:
                _mount(devnode)
            continue


        # ---------- partition vanished ------------------------------
        if action == "remove" and dtype == "partition":
            _register_raw_remove(devnode)
            _unmount(devnode)

            if devnode == _active_raw:
                fallback = _raw_pool[-1] if _raw_pool else None
                _switch_to_raw(fallback)
            continue

        # ---------- whole disk vanished -----------------------------
        if action == "remove" and dtype == "disk":
            # unmount **every** partition we still track on that disk
            victims = [d for d in list(_mounts) if d.startswith(devnode)]
            for part in victims:
                _register_raw_remove(part)
                _unmount(part)

            if devnode in (_active_raw or ""):
                fallback = _raw_pool[-1] if _raw_pool else None
                _switch_to_raw(fallback)


# ---------------------------------------------------------------------------
# CFE-HAT worker  (robust edge-detector + thread-safe updates)
# ---------------------------------------------------------------------------
def _cfe_hat_worker():
    global _active_raw            # ★ declare once at function top

    if smbus is None:
        log.debug("No smbus module, CFE-HAT thread disabled")
        return

    I2C_CH, I2C_ADDR = 1, 0x34
    try:
        bus = smbus.SMBus(I2C_CH)
        bus.read_byte(I2C_ADDR)                # probe once
    except OSError:
        log.info("CFE-HAT not detected on I²C, skipping thread")
        return

    led_on     = False
    last_state = 0x00
    try:
        last_state = bus.read_byte(I2C_ADDR)   # current idle byte
    except OSError:
        pass

    log.info("CFE-HAT thread started — idle byte 0x%02X", last_state)

    # ── small helpers ──────────────────────────────────────────────────
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

    # ── polling loop (≈20 Hz) ─────────────────────────────────────────
    while True:
        try:
            raw = bus.read_byte(I2C_ADDR)
        except OSError as e:
            log.debug("I²C read error: %s", e)
            time.sleep(0.1)
            continue

        # bit0 = insert / latch, bit1 = eject
        ins_now  =  raw        & 1
        ej_now   = (raw >> 1)  & 1
        ins_prev =  last_state & 1
        ej_prev  = (last_state >> 1) & 1
        last_state = raw

        # ──────────────────────────────────────────────────────────────
        # INSERT DOWN  → latch opened  (yank about to happen)
        # ──────────────────────────────────────────────────────────────

        if ins_prev == 0 and ins_now == 1:
            log.debug("Insert pressed (latch open) – pre-emptive unmount")
            any_unmounted = False

            for dev in list(_mounts):
                if dev.startswith("/dev/nvme"):
                    if _force_lazy_unmount(dev):
                        any_unmounted = True
                        log.info("Pre-emptive unmount of %s OK", dev)   # NEW
                        with _raw_lock:
                            _register_raw_remove(dev)
                            if dev == _active_raw:
                                _active_raw = None

            if any_unmounted:
                _wait_for_raw_unmount()
                _pcie_bind(False)          # NEW – power down slot
                _set_led(False)

            _purge_stale_mountpoints()

        # ──────────────────────────────────────────────────────────────
        # INSERT UP  → power up + wait for mount
        # ──────────────────────────────────────────────────────────────
        if ins_prev == 1 and ins_now == 0:
            log.info("Insert released → powering up and waiting for udev mount")
            _pcie_bind(True)
            _set_led(True)

            if _wait_for_raw_mount(timeout=20.0):
                log.info("Insert: mount succeeded ✓")
            else:
                log.warning("Insert: mount FAILED (timeout) – check NVMe, cable, power")
                _set_led(False)

        # ──────────────────────────────────────────────────────────────
        # EJECT DOWN  → just debounce log
        # ──────────────────────────────────────────────────────────────
        if ej_prev == 0 and ej_now == 1:
            log.debug("Eject pressed (bit1 went 0→1)")

        # ──────────────────────────────────────────────────────────────
        # EJECT UP  → unmount everything, power down
        # ──────────────────────────────────────────────────────────────
        if ej_prev == 1 and ej_now == 0:
            log.info("Eject released → attempting unmount")
            any_unmounted = False
            for d in list(_mounts):
                if _force_lazy_unmount(d):
                    any_unmounted = True
                    # ★ cleanup arbitration table safely
                    with _raw_lock:
                        _register_raw_remove(d)
                        if d == _active_raw:
                            _active_raw = None

            if any_unmounted:
                if _wait_for_raw_unmount():
                    log.info("Eject: unmount succeeded ✓")
                else:
                    log.warning("Eject: unmount timed-out (busy) ✗")
                _pcie_bind(False)
                _set_led(False)
            else:
                log.warning("Eject: no RAW partition was mounted")

        time.sleep(0.05)          # ~20 Hz


def _initial_scan():
    _purge_stale_mountpoints()
    log.debug("Initial device scan")

    # Build an ordered list: first non-RAW, then RAW (so arbitration wins)
    raws, others = [], []
    for dev in _udev_ctx.list_devices(subsystem="block", DEVTYPE="partition"):
        label, _ = _get_fs(dev.device_node)
        (raws if label == "RAW" else others).append(dev.device_node)

    for dev in others + raws[:1]:      # at most one RAW
        _mount(dev)
        if label == "RAW":
            _register_raw_add(dev)
            _active_raw = dev


def _sanity_watchdog():
    """
    Every 3 s
        • reconcile _mounts with /proc/self/mountinfo (as before)
        • probe every mount with statvfs()
              ↳ on EIO/ENOENT we assume the medium was yanked and lazily
                un-mount it.
    """
    while True:
        # ── 1. normal bookkeeping cleanup ───────────────────────────────
        real = {line.split()[9] for line in open("/proc/self/mountinfo")}
        for dev in list(_mounts):
            if dev not in real:
                log.debug("Watchdog: %s vanished, cleaning up", dev)
                _mounts.pop(dev)

        # ── 2. yank detection via I/O error ─────────────────────────────
        for dev, mp in list(_mounts.items()):
            try:
                os.statvfs(mp)                      # cheap, cached in VFS
            except OSError as exc:
                if exc.errno in (errno.EIO, errno.ENOENT):
                    log.warning(
                        "Watchdog: I/O error on %s (%s) – assuming yank, "
                        "lazy-unmounting", dev, os.strerror(exc.errno)
                    )
                    _force_lazy_unmount(dev)

        time.sleep(3)


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
    threading.Thread(target=_sanity_watchdog, daemon=True).start()
   

    log.info("storage-automount started (log level %s)", LOG_LEVEL)
    while True:
        time.sleep(60)

# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()