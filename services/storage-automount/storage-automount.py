#!/usr/bin/env python3
"""
Unified Storage Auto-Mount for Raspberry Pi 5
Combines label-based mounting with media-aware I/O tuning for real-time video recording.

Supports:
- CFE HAT (CFexpress via PCIe NVMe)
- USB NVMe (via UAS bridge)
- USB SSD (SATA via UAS)
- NVMe HAT (M.2 NVMe via HAT)

Features:
- Dynamic /media/LABEL mounting
- Per-media I/O tuning profiles
- Sysctl cushions for smooth writes
- Auto-repair on mount failures
- RAW drive arbitration
- Watchdogs for device health
- CFE HAT I2C button/LED control
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

try:
    import pyudev
except ImportError:
    print("ERROR: pyudev not found. Install with: sudo apt install python3-pyudev", file=sys.stderr)
    sys.exit(1)

try:
    import smbus
except ImportError:
    smbus = None

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("STORAGE_AUTOMOUNT_LOG", "INFO").upper()
PI_UID = int(os.getenv("PI_UID", "1000"))
PI_GID = int(os.getenv("PI_GID", "1000"))
MOUNT_BASE = Path("/media")
RAW_LABEL = "RAW"
RAW_ACTIVE_PATH = MOUNT_BASE / RAW_LABEL  # primary recorder target (/media/RAW)

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [storage-automount] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("storage-automount")

# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────
_mounts: dict[str, Path] = {}  # devnode → mountpoint
_active_mount_kinds: dict[str, str] = {}  # devnode → media kind
_failed_devices: dict[str, float] = {}  # devnode → timestamp (cooldown)
_raw_pool: list[str] = []  # devices with LABEL=RAW
_active_raw: str | None = None
_raw_lock = threading.RLock()  # Reentrant lock to allow nested acquisition
_sysctl_saved: dict[str, str | None] = {}
_udev_ctx = pyudev.Context()
YANK_ERRNOS = {
    errno.EIO,
    errno.ENOENT,
    errno.ENODEV,
    getattr(errno, "ENOTCONN", errno.EIO),
    getattr(errno, "ESTALE", errno.EIO),
}

# ─────────────────────────────────────────────────────────────────────────────
# Media Profiles (tuning per connection type)
# ─────────────────────────────────────────────────────────────────────────────
PROFILES = {
    "cfe_nvme": {  # CFexpress via PCIe (CFE HAT)
        "ext4_opts": "rw,noatime,nodiratime,commit=60",
        "dirty_bytes": 1 * 1024**3,  # 1 GiB
        "dirty_bg_bytes": 256 * 1024**2,  # 256 MiB
        "rq_affinity": "2",
        "scheduler": "none",
        "nr_requests": "512",
        "nvme_ps_latency_us": "0",
    },
    "usb_nvme": {  # USB NVMe (UAS bridge)
        "ext4_opts": "rw,noatime,nodiratime,commit=60",
        "dirty_bytes": 512 * 1024**2,  # 512 MiB
        "dirty_bg_bytes": 256 * 1024**2,  # 256 MiB
        "rq_affinity": "2",
        "scheduler": "none",
        "nr_requests": "256",
        "nvme_ps_latency_us": "0",
    },
    "usb_ssd": {  # USB SSD (SATA via UAS)
        "ext4_opts": "rw,noatime,nodiratime,commit=60",
        # Smaller dirty cushion than NVMe on purpose: a USB SSD's write speed
        # falls off a cliff once its SLC cache is exhausted (~90 s into a 4K
        # take). A large dirty buffer would then fill and block writers in one
        # long balance_dirty_pages stall — a burst of dropped frames. A smaller
        # cushion trades that for shorter, more frequent stalls (smoother).
        "dirty_bytes": 256 * 1024**2,
        "dirty_bg_bytes": 128 * 1024**2,
        "rq_affinity": "2",
        "scheduler": "none",
        "nr_requests": "256",
    },
    "nvme_hat": {  # NVMe HAT (M.2 via HAT)
        "ext4_opts": "rw,noatime,nodiratime,commit=60",
        "dirty_bytes": 1 * 1024**3,
        "dirty_bg_bytes": 256 * 1024**2,
        "rq_affinity": "2",
        "scheduler": "none",
        "nr_requests": "512",
        "nvme_ps_latency_us": "0",
    },
    "other": {  # Fallback
        "ext4_opts": "rw,noatime",
        "dirty_bytes": 256 * 1024**2,
        "dirty_bg_bytes": 128 * 1024**2,
        "rq_affinity": "1",
        "scheduler": "mq-deadline",
        "nr_requests": "128",
    },
}

# Filesystem mount profiles. ext4 uses the media profile above so faster media
# can get deeper dirty/writeback cushions while sharing one filesystem contract.
FS_MOUNT_PROFILES = {
    "ntfs": {"opts": f"uid={PI_UID},gid={PI_GID},dmask=022,fmask=133,rw,noatime"},
    "ntfs3": {"opts": f"uid={PI_UID},gid={PI_GID},dmask=022,fmask=133,rw,noatime"},
    "exfat": {"opts": f"uid={PI_UID},gid={PI_GID},dmask=022,fmask=133,rw,noatime"},
    "vfat": {"opts": f"uid={PI_UID},gid={PI_GID},dmask=022,fmask=133,rw,noatime"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────
def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except Exception:
        return None

def _write(path: str, val: str) -> bool:
    try:
        Path(path).write_text(str(val))
        return True
    except Exception:
        return False

def _sysctl_get(key: str) -> str | None:
    return _read(f"/proc/sys/{key.replace('.', '/')}")

def _sysctl_set(key: str, val: str) -> bool:
    return _write(f"/proc/sys/{key.replace('.', '/')}", val)

def _sanitize(label: str) -> str:
    """Sanitize filesystem label for use as directory name."""
    return re.sub(r"[^\w\-.]", "_", label)[:64] or "UNLABELED"

def _root_block_name(devnode: str) -> str:
    """nvme0n1p1 → nvme0n1 ; sda1 → sda"""
    name = Path(devnode).name
    if name.startswith("nvme") and "p" in name:
        return name.split("p", 1)[0]
    return re.sub(r"\d+$", "", name)

def _is_partition_of(part: str, disk: str) -> bool:
    """True if devnode `part` is a partition of whole-disk devnode `disk`.

    /dev/sda → /dev/sda1 ✓ ; /dev/nvme0n1 → /dev/nvme0n1p1 ✓ ;
    /dev/sda → /dev/sdaa1 ✗ (avoids the naive startswith false-match).
    """
    if part == disk or not part.startswith(disk):
        return False
    rest = part[len(disk):]
    return re.fullmatch(r"p?\d+", rest) is not None

def _get_filesystem_info(dev: str, retries: int = 5, delay: float = 0.5) -> tuple[str | None, str | None]:
    """Return (LABEL, FSTYPE) with retries for udev settle."""
    for i in range(retries):
        try:
            label = subprocess.check_output(
                ["blkid", "-s", "LABEL", "-o", "value", dev],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
        except subprocess.CalledProcessError:
            label = ""

        try:
            fstype = subprocess.check_output(
                ["blkid", "-s", "TYPE", "-o", "value", dev],
                text=True, stderr=subprocess.DEVNULL
            ).strip()
        except subprocess.CalledProcessError:
            fstype = ""

        if fstype:
            return (label or None), fstype
        time.sleep(delay)

    log.warning("blkid retries exhausted for %s", dev)
    return None, None

def _classify_media(devnode: str) -> str:
    """Classify device as: cfe_nvme, usb_nvme, usb_ssd, nvme_hat, or other."""
    try:
        device = pyudev.Devices.from_device_file(_udev_ctx, devnode)
    except Exception:
        return "other"

    # Check if it's NVMe
    if devnode.startswith("/dev/nvme"):
        # Check if it's connected via USB (USB NVMe)
        for parent in device.ancestors:
            if parent.subsystem == "usb":
                return "usb_nvme"

        # Check if it's PCIe CFE HAT or NVMe HAT
        # CFE HAT typically uses specific PCIe addresses; for now treat as nvme_hat
        # You can refine this based on PCIe bus topology if needed
        return "nvme_hat"  # Default NVMe to HAT, CFE will be detected via I2C

    # Check USB devices
    for parent in device.ancestors:
        if parent.subsystem == "usb":
            driver = (device.get("ID_USB_DRIVER") or "").lower()
            # UAS driver suggests better hardware
            if driver == "uas":
                return "usb_nvme"  # Treat UAS as potentially NVMe-backed
            return "usb_ssd"

    return "other"

def _is_device_mounted(dev: str) -> bool:
    """Check if device is mounted anywhere."""
    try:
        with open("/proc/self/mountinfo") as f:
            for line in f:
                parts = line.split(" - ")
                if len(parts) >= 2:
                    source = parts[1].split()[1]
                    if source == dev:
                        return True
    except Exception:
        pass
    return False

# ─────────────────────────────────────────────────────────────────────────────
# Tuning
# ─────────────────────────────────────────────────────────────────────────────
def _apply_block_tuning(devnode: str, kind: str):
    """Apply block layer tuning based on media profile."""
    root = _root_block_name(devnode)
    qpath = f"/sys/block/{root}/queue"
    prof = PROFILES.get(kind, PROFILES["other"])

    # I/O scheduler
    sched = prof.get("scheduler")
    if sched:
        _write(f"{qpath}/scheduler", sched)

    # Request affinity
    rq = prof.get("rq_affinity")
    if rq:
        _write(f"{qpath}/rq_affinity", rq)

    # Queue depth
    nr = prof.get("nr_requests")
    if nr:
        _write(f"{qpath}/nr_requests", nr)

    log.debug("Applied block tuning for %s (%s): sched=%s rq_aff=%s nr_req=%s",
              devnode, kind, sched, rq, nr)

def _apply_nvme_power_tuning(kind: str):
    """Configure NVMe power management for low latency."""
    target = "/sys/module/nvme_core/parameters/default_ps_max_latency_us"
    if not Path(target).exists():
        target = "/sys/module/nvme/parameters/default_ps_max_latency_us"

    val = PROFILES.get(kind, {}).get("nvme_ps_latency_us")
    if val and not _write(target, val):
        log.debug("NVMe power tuning not writable; add nvme_core.default_ps_max_latency_us=%s to cmdline.txt", val)

def _apply_sysctl_cushions(kind: str):
    """Apply dirty memory cushions for smooth writes."""
    if not _sysctl_saved:
        # Save original values
        for k in ("vm.dirty_bytes", "vm.dirty_background_bytes", "vm.dirty_ratio",
                  "vm.dirty_background_ratio", "vm.dirty_writeback_centisecs", "vm.dirty_expire_centisecs"):
            _sysctl_saved[k] = _sysctl_get(k)

    prof = PROFILES.get(kind, PROFILES["other"])
    _sysctl_set("vm.dirty_ratio", "0")
    _sysctl_set("vm.dirty_background_ratio", "0")
    _sysctl_set("vm.dirty_writeback_centisecs", "150")  # 1.5s flush
    _sysctl_set("vm.dirty_expire_centisecs", "3000")  # 30s max age
    _sysctl_set("vm.dirty_background_bytes", str(prof["dirty_bg_bytes"]))
    _sysctl_set("vm.dirty_bytes", str(prof["dirty_bytes"]))

    log.info("Applied sysctl for %s: dirty=%d MB, bg=%d MB",
             kind, prof["dirty_bytes"] // 1024**2, prof["dirty_bg_bytes"] // 1024**2)

    if kind == "usb_ssd":
        log.info("usb_ssd: sustained 4K can exceed this drive's post-SLC-cache "
                 "write rate; if frames drop ~90 s in, the SSD cannot sustain "
                 "the data rate (check NAND type, or use NVMe / a lower fps)")

def _mount_options(fstype: str, kind: str) -> str:
    if fstype == "ext4":
        return PROFILES.get(kind, PROFILES["other"])["ext4_opts"]
    profile = FS_MOUNT_PROFILES.get(fstype)
    if profile:
        return profile["opts"]
    return "rw,noatime"

def _restore_sysctls():
    """Restore original sysctl values when no mounts remain."""
    log.debug("_restore_sysctls called, checking if restore needed...")
    if _active_mount_kinds or not _sysctl_saved:
        log.debug("Skipping sysctl restore (active_kinds=%s, saved=%s)",
                 len(_active_mount_kinds), bool(_sysctl_saved))
        return
    log.debug("Restoring %d sysctl values...", len(_sysctl_saved))
    for k, v in _sysctl_saved.items():
        if v:
            _sysctl_set(k, v)
    log.info("Restored default sysctl values")
    log.debug("Sysctl restore complete")

def _apply_media_tuning(dev: str, kind: str, mount_path: "Path"):
    """Apply tuning for a freshly-mounted device.

    Per-device block-queue tuning is applied to every drive (it only touches
    that device's own queue). The *global* write-smoothing knobs — the VM dirty
    cushions and the NVMe power-latency parameter — are applied ONLY for the
    active RAW recording target (/media/RAW). Other drives (file-transfer disks,
    standbys, anything not labelled RAW) are accepted and mounted, but must not
    perturb the global tuning the recorder depends on.
    """
    _apply_block_tuning(dev, kind)
    if mount_path == RAW_ACTIVE_PATH:
        if dev.startswith("/dev/nvme"):
            _apply_nvme_power_tuning(kind)
        _apply_sysctl_cushions(kind)

# ─────────────────────────────────────────────────────────────────────────────
# Auto-repair
# ─────────────────────────────────────────────────────────────────────────────
def _auto_repair(dev: str, fstype: str) -> bool:
    """Attempt automatic filesystem repair."""
    if fstype == "ext4":
        log.warning("Repairing %s with e2fsck -p", dev)
        return subprocess.call(["e2fsck", "-f", "-p", dev],
                             stderr=subprocess.DEVNULL) in (0, 1, 2)
    elif fstype == "ntfs":
        log.warning("Repairing %s with ntfsfix", dev)
        return subprocess.call(["ntfsfix", dev],
                             stderr=subprocess.DEVNULL) == 0
    elif fstype == "exfat":
        log.warning("Repairing %s with fsck.exfat -a", dev)
        return subprocess.call(["fsck.exfat", "-a", dev],
                             stderr=subprocess.DEVNULL) == 0
    return False

# ─────────────────────────────────────────────────────────────────────────────
# Mount / Unmount
# ─────────────────────────────────────────────────────────────────────────────
def _purge_stale_mountpoints():
    """Clean up stale mount directories."""
    for entry in MOUNT_BASE.iterdir():
        if entry.is_dir() and not os.path.ismount(entry):
            try:
                if not any(entry.iterdir()):
                    entry.rmdir()
                    log.debug("Removed stale mountpoint: %s", entry)
            except OSError:
                pass

def _mount(dev: str, target: "Path | None" = None, *, force: bool = False) -> bool:
    """Mount `dev` at `target` (or a label-derived path) with media tuning.

    Returns True on success (or when already mounted by us). When `force` is
    True the failed-device cooldown is ignored — used by RAW promotion so a
    drive that briefly failed can be retried the instant it is needed.
    """
    global _failed_devices

    # Clean up failed device cooldowns (30s)
    current_time = time.time()
    _failed_devices = {k: v for k, v in _failed_devices.items() if current_time - v < 30}

    # Check cooldown (skipped on a forced/promotion mount)
    if not force and dev in _failed_devices:
        remaining = 30 - (time.time() - _failed_devices[dev])
        if remaining > 0:
            log.debug("%s in cooldown, %d seconds remaining", dev, int(remaining))
        return False
    _failed_devices.pop(dev, None)

    # Already mounted by us
    if dev in _mounts:
        log.debug("%s already mounted at %s", dev, _mounts[dev])
        return True

    # Get filesystem info
    label, fstype = _get_filesystem_info(dev)
    if not fstype:
        log.warning("%s: unknown filesystem, skipping", dev)
        _failed_devices[dev] = time.time()
        return False

    # Classify media type
    kind = _classify_media(dev)

    # Determine mount path
    if target is not None:
        mount_path = target
    elif label:
        mount_path = MOUNT_BASE / _sanitize(label)
    else:
        mount_path = MOUNT_BASE / Path(dev).name

    mount_path.mkdir(parents=True, exist_ok=True)

    # Determine mount options
    opts = _mount_options(fstype, kind)

    # Check if already mounted elsewhere
    if _is_device_mounted(dev):
        log.info("%s already mounted elsewhere, tracking it", dev)
        _mounts[dev] = mount_path
        _active_mount_kinds[dev] = kind
        _apply_media_tuning(dev, kind, mount_path)
        return True

    # Attempt mount
    cmd = ["mount", "-t", fstype, "-o", opts, dev, str(mount_path)]
    log.info("Mounting %s (%s, %s) → %s with opts=%s", dev, fstype, kind, mount_path, opts)

    if subprocess.call(cmd, stderr=subprocess.DEVNULL) == 0:
        _mounts[dev] = mount_path
        _active_mount_kinds[dev] = kind
        try:
            os.chown(mount_path, PI_UID, PI_GID)
        except OSError:
            pass

        _apply_media_tuning(dev, kind, mount_path)

        log.info("✓ Mounted %s successfully at %s", dev, mount_path)
        return True

    # Mount failed - try repair
    log.error("Mount failed for %s, attempting repair", dev)
    if _auto_repair(dev, fstype):
        log.info("Repair successful, retrying mount")
        if subprocess.call(cmd, stderr=subprocess.DEVNULL) == 0:
            _mounts[dev] = mount_path
            _active_mount_kinds[dev] = kind
            try:
                os.chown(mount_path, PI_UID, PI_GID)
            except OSError:
                pass
            _apply_media_tuning(dev, kind, mount_path)
            log.info("✓ Mounted %s after repair at %s", dev, mount_path)
            return True

    # Failed - cleanup and cooldown (never remove the primary /media/RAW dir)
    try:
        if mount_path != RAW_ACTIVE_PATH and not any(mount_path.iterdir()):
            mount_path.rmdir()
    except OSError:
        pass
    _failed_devices[dev] = time.time()
    log.error("✗ Failed to mount %s", dev)
    return False

def _unmount(dev: str):
    """Unmount device and clean up."""
    if dev not in _mounts:
        return

    mount_path = _mounts.pop(dev, None)
    _active_mount_kinds.pop(dev, None)

    if not mount_path:
        return

    log.info("Unmounting %s from %s", dev, mount_path)
    log.debug("Starting non-blocking lazy unmount...")

    # Use Popen for non-blocking unmount (umount can block for 30+ seconds)
    subprocess.Popen(["umount", "-l", str(mount_path)], stderr=subprocess.DEVNULL)

    # Leave mount point cleanup to startup purge. Directory scans can block on
    # yanked or erroring media, exactly when we need unmount handling to stay fast.

    # Restore sysctls if no mounts remain
    log.debug("Calling _restore_sysctls...")
    _restore_sysctls()
    log.debug("_unmount complete for %s", dev)

# ─────────────────────────────────────────────────────────────────────────────
# RAW Arbitration
# ─────────────────────────────────────────────────────────────────────────────
# Exactly one RAW drive is "active" (mounted at /media/RAW, the recorder
# target). Any additional RAW drives are mounted as standbys at /media/RAW1,
# /media/RAW2, … When the active drive is removed, ejected or yanked, the
# oldest mounted standby is promoted to /media/RAW so recording can continue.
#
# Mounting is event/promotion driven: a RAW device is only mounted in response
# to a udev add/change (or the initial scan), and only ever becomes active via
# promotion. The service never spontaneously re-grabs a device a user unmounted
# out-of-band (a GUI eject or a cinemate format) — that device is left alone
# until it produces a fresh add event.
def _register_raw_add(dev: str):
    """Register a device with LABEL=RAW (append to the arrival-ordered pool)."""
    with _raw_lock:
        if dev not in _raw_pool:
            _raw_pool.append(dev)

def _register_raw_remove(dev: str):
    """Unregister a RAW device."""
    with _raw_lock:
        if dev in _raw_pool:
            _raw_pool.remove(dev)

def _mountpoint_in_use(path: "Path") -> bool:
    """True if `path` is currently a mountpoint. Reads /proc, never blocks on I/O."""
    target = str(path)
    try:
        with open("/proc/self/mountinfo") as f:
            for line in f:
                fields = line.split()
                if len(fields) >= 5 and fields[4] == target:
                    return True
    except Exception:
        pass
    return False

def _next_standby_path() -> "Path":
    """Return the first free /media/RAW<n> standby mountpoint."""
    used = {str(p) for p in _mounts.values()}
    n = 1
    while True:
        candidate = MOUNT_BASE / f"{RAW_LABEL}{n}"
        if str(candidate) not in used and not _mountpoint_in_use(candidate):
            return candidate
        n += 1

def _mount_standby(dev: str):
    """Mount a RAW device at a free standby path (never touches /media/RAW)."""
    if dev in _mounts:
        return
    target = _next_standby_path()
    if _mount(dev, target):
        log.info("RAW standby %s mounted at %s", dev, target)

def _promote_to_active(dev: str) -> bool:
    """Make `dev` the active RAW drive mounted at /media/RAW. Returns success."""
    global _active_raw
    with _raw_lock:
        # A just-removed active drive is torn down with an async lazy umount, so
        # /media/RAW can linger as a mountpoint for a fraction of a second. Wait
        # briefly for it to free before promoting, so we don't have to rely on
        # the 3 s watchdog tick to retry. A mountpoint that persists past the
        # timeout is a legitimate foreign mount (e.g. cinemate mounted it) and
        # must not be stolen.
        waited = 0.0
        while _mountpoint_in_use(RAW_ACTIVE_PATH) and waited < 2.0:
            time.sleep(0.1)
            waited += 0.1
        if _mountpoint_in_use(RAW_ACTIVE_PATH):
            log.debug("%s still occupied; not promoting %s", RAW_ACTIVE_PATH, dev)
            return False
        RAW_ACTIVE_PATH.mkdir(parents=True, exist_ok=True)

        # Fast path: relocate an already-mounted standby with `mount --move`,
        # preserving the open filesystem (no unmount/remount cycle).
        src = _mounts.get(dev)
        if src is not None and src != RAW_ACTIVE_PATH:
            if subprocess.call(["mount", "--move", str(src), str(RAW_ACTIVE_PATH)],
                               stderr=subprocess.DEVNULL) == 0:
                _mounts[dev] = RAW_ACTIVE_PATH
                _active_raw = dev
                try:
                    os.chown(RAW_ACTIVE_PATH, PI_UID, PI_GID)
                except OSError:
                    pass
                try:
                    if not any(src.iterdir()):
                        src.rmdir()
                except OSError:
                    pass
                # Now the active recording target — apply the global cushions
                # (the standby mount only applied per-device block tuning).
                _apply_media_tuning(dev, _active_mount_kinds.get(dev, "other"), RAW_ACTIVE_PATH)
                log.info("✓ Promoted RAW %s: %s → %s", dev, src, RAW_ACTIVE_PATH)
                return True
            # `mount --move` is unsupported for FUSE mounts such as ntfs-3g:
            # drop the standby mount and fall back to a fresh mount at
            # /media/RAW below. Expected for NTFS drives, not an error.
            log.info("mount --move unsupported for %s (%s → %s, likely FUSE); remounting",
                     dev, src, RAW_ACTIVE_PATH)
            _unmount(dev)

        _failed_devices.pop(dev, None)
        if _mount(dev, RAW_ACTIVE_PATH, force=True):
            _active_raw = dev
            log.info("✓ Promoted RAW %s to %s", dev, RAW_ACTIVE_PATH)
            return True
        return False

def _promote_next() -> bool:
    """Promote the best available RAW device to active. Caller holds _raw_lock.

    Prefers already-mounted standbys (proven mountable, ordered by mountpoint),
    then falls back to any unmounted pool member.
    """
    if _active_raw is not None:
        return True
    standbys = sorted(
        ((str(p), d) for d, p in _mounts.items()
         if d in _raw_pool and p != RAW_ACTIVE_PATH),
        key=lambda t: t[0],
    )
    ordered = [d for _, d in standbys] + [d for d in _raw_pool if d not in _mounts]
    for d in ordered:
        if _promote_to_active(d):
            return True
    if ordered:
        log.warning("No RAW standby could be promoted to %s", RAW_ACTIVE_PATH)
    return False

def _add_raw(dev: str):
    """Handle a freshly-detected RAW device: become active if none, else standby."""
    _register_raw_add(dev)
    with _raw_lock:
        if dev == _active_raw:
            return
        if _active_raw is None and not _mountpoint_in_use(RAW_ACTIVE_PATH):
            if _promote_to_active(dev):
                return
        _mount_standby(dev)

def _handle_raw_gone(dev: str):
    """Active/standby RAW device removed, ejected or yanked → unmount + promote."""
    global _active_raw
    with _raw_lock:
        was_active = (dev == _active_raw)
        _register_raw_remove(dev)
        _failed_devices.pop(dev, None)   # let an immediate reconnect retry
        if dev in _mounts:
            _unmount(dev)
        if was_active:
            _active_raw = None
            _promote_next()

def _on_block_removed(devnode: str):
    """Handle removal of a partition or whole disk: unmount affected mounts and
    promote a RAW standby if the active drive went away."""
    affected = []
    for d in list(_mounts) + [x for x in _raw_pool if x not in _mounts]:
        if (d == devnode or _is_partition_of(d, devnode)) and d not in affected:
            affected.append(d)
    if _active_raw and (_active_raw == devnode or _is_partition_of(_active_raw, devnode)):
        if _active_raw not in affected:
            affected.append(_active_raw)
    for d in affected:
        if d in _raw_pool or d == _active_raw:
            _handle_raw_gone(d)
        else:
            _unmount(d)

def _safety_net_promote():
    """Periodic reconcile (called from the sanity watchdog): cover out-of-band
    unmounts such as a GUI eject by promoting a standby when /media/RAW is empty.
    Never re-grabs a device the user deliberately unmounted while it is still
    present — it only ever elevates a standby that is already mounted."""
    global _active_raw
    with _raw_lock:
        if _active_raw is not None and not _mountpoint_in_use(RAW_ACTIVE_PATH):
            # The active drive's mount disappeared without a removal event
            # (cinemate eject/format). Release it and let a standby take over if
            # one exists. Drop it from the promotion pool too, so we don't
            # immediately re-grab a drive the user deliberately unmounted — a
            # physical re-insert re-adds it via a fresh udev event.
            log.info("Active RAW %s no longer mounted at %s; releasing (out-of-band unmount)",
                     _active_raw, RAW_ACTIVE_PATH)
            _mounts.pop(_active_raw, None)
            _active_mount_kinds.pop(_active_raw, None)
            _register_raw_remove(_active_raw)
            _active_raw = None
        if _active_raw is None and not _mountpoint_in_use(RAW_ACTIVE_PATH):
            _promote_next()

# ─────────────────────────────────────────────────────────────────────────────
# Watchdogs
# ─────────────────────────────────────────────────────────────────────────────
def _nvme_watchdog():
    """Monitor NVMe controller state and lazy-unmount if dead."""
    log.debug("NVMe watchdog started")
    while True:
        for dev in list(_mounts.keys()):
            if not dev.startswith("/dev/nvme"):
                continue
            root = _root_block_name(dev)
            state_file = Path(f"/sys/block/{root}/device/state")
            if state_file.exists():
                try:
                    state = state_file.read_text().strip()
                    if state == "dead":
                        log.warning("NVMe controller dead for %s, lazy unmount", dev)
                        if dev in _raw_pool or dev == _active_raw:
                            _handle_raw_gone(dev)
                        else:
                            _unmount(dev)
                except OSError:
                    pass
        time.sleep(0.5)

def _sanity_watchdog():
    """Health check: detect yanked drives via statvfs errors and reconcile RAW."""
    while True:
        for dev, mp in list(_mounts.items()):
            # Skip SD card devices - they're not managed by this script
            # and statvfs can block for 30+ seconds on bad SD card mounts
            if dev.startswith("/dev/mmcblk"):
                continue

            try:
                os.statvfs(mp)
            except OSError as exc:
                if exc.errno in YANK_ERRNOS:
                    log.warning("I/O error on %s (%s) - device yanked, unmounting",
                              dev, os.strerror(exc.errno))
                    if dev in _raw_pool or dev == _active_raw:
                        # Unmount + promote a standby so recording can continue.
                        _handle_raw_gone(dev)
                    else:
                        subprocess.Popen(["umount", "-l", str(mp)],
                                         stderr=subprocess.DEVNULL)
                        _mounts.pop(dev, None)
                        _active_mount_kinds.pop(dev, None)
                        _restore_sysctls()

        # Reconcile RAW: promote a standby if /media/RAW went empty out-of-band
        # (e.g. a GUI eject) without a corresponding device-removal event.
        _safety_net_promote()

        time.sleep(3)

# ─────────────────────────────────────────────────────────────────────────────
# udev Event Handler
# ─────────────────────────────────────────────────────────────────────────────
def _udev_worker():
    """Monitor udev events for block devices."""
    monitor = pyudev.Monitor.from_netlink(_udev_ctx)
    monitor.filter_by(subsystem="block")
    log.info("udev event monitor started")

    for action, device in monitor:
        devnode = device.device_node
        devtype = device.get("DEVTYPE")

        if not devnode:
            continue

        # Partition added/changed
        if action in ("add", "change") and devtype == "partition":
            label, _ = _get_filesystem_info(devnode)
            if label == RAW_LABEL:
                _add_raw(devnode)
            else:
                _mount(devnode)

        # Whole disk added/changed (no partition table)
        elif action in ("add", "change") and devtype == "disk":
            # Skip SD cards, loop devices, and RAM disks
            if devnode.startswith(("/dev/mmcblk", "/dev/loop", "/dev/ram")):
                continue

            label, fstype = _get_filesystem_info(devnode)
            if fstype:  # Has a filesystem on whole disk
                log.info("Detected whole-disk filesystem on %s (%s)", devnode, fstype)
                if label == RAW_LABEL:
                    _add_raw(devnode)
                else:
                    _mount(devnode)

        # Partition or whole disk removed
        elif action == "remove" and devtype in ("partition", "disk"):
            log.debug("%s removed: %s", devtype, devnode)
            _on_block_removed(devnode)
            log.debug("Removal handling complete for %s", devnode)

# ─────────────────────────────────────────────────────────────────────────────
# CFE HAT I2C Worker
# ─────────────────────────────────────────────────────────────────────────────
def _cfe_hat_worker():
    """Monitor CFE HAT insert/eject buttons via I2C."""
    global _active_raw, _failed_devices
    if not smbus:
        log.debug("smbus not available, CFE HAT disabled")
        return

    I2C_CH, I2C_ADDR = 1, 0x34
    try:
        bus = smbus.SMBus(I2C_CH)
        bus.read_byte(I2C_ADDR)
    except OSError:
        log.info("CFE HAT not detected on I2C, skipping")
        return

    log.info("CFE HAT I2C control enabled")

    led_on = False
    def _set_led(state: bool):
        nonlocal led_on
        if state == led_on:
            return
        led_on = state
        try:
            bus.write_byte(I2C_ADDR, 0x01 if state else 0x00)
        except OSError:
            pass

    def _pcie(bind: bool):
        """Bind/unbind PCIe for CFE card."""
        path = "/sys/bus/platform/drivers/brcm-pcie"
        node = "1000110000.pcie"
        target = "bind" if bind else "unbind"
        try:
            with open(f"{path}/{target}", "w") as f:
                f.write(node)
        except OSError as e:
            if e.errno != errno.EBUSY:
                log.debug("PCIe %s error: %s", target, e)
        if bind:
            time.sleep(0.5)
            subprocess.call(["sh", "-c", "echo 1 > /sys/bus/pci/rescan"],
                          stderr=subprocess.DEVNULL)

    last_state = 0x00
    try:
        last_state = bus.read_byte(I2C_ADDR)
    except OSError:
        pass

    # Set LED based on initial state
    ins_state = last_state & 1
    _set_led(ins_state == 0)  # LED on if latch closed

    while True:
        try:
            raw = bus.read_byte(I2C_ADDR)
        except OSError as e:
            log.debug("I2C read error: %s", e)
            time.sleep(0.1)
            continue

        ins_now = raw & 1
        ej_now = (raw >> 1) & 1
        ins_prev = last_state & 1
        ej_prev = (last_state >> 1) & 1

        # Log state changes for debugging
        if raw != last_state:
            log.debug("Button state change: 0x%02x → 0x%02x (ins=%d, ej=%d)",
                     last_state, raw, ins_now, ej_now)

        last_state = raw

        # INSERT pressed (latch open) - pre-emptive unmount
        if ins_prev == 0 and ins_now == 1:
            log.info("CFexpress card status: REMOVED (latch opened)")
            nvme_devices = [dev for dev in list(_mounts) if dev.startswith("/dev/nvme")]
            for dev in nvme_devices:
                log.info("Unmounting CFE device %s from %s", dev, _mounts[dev])
                # _handle_raw_gone promotes a surviving standby (e.g. a USB SSD)
                # to /media/RAW so recording can continue after the card leaves.
                # It uses a non-blocking lazy unmount internally.
                if dev in _raw_pool or dev == _active_raw:
                    _handle_raw_gone(dev)
                else:
                    subprocess.Popen(["umount", "-l", str(_mounts[dev])],
                                   stderr=subprocess.DEVNULL)
                    _mounts.pop(dev, None)
                    _active_mount_kinds.pop(dev, None)
            log.debug("Powering down PCIe...")
            _pcie(False)
            log.debug("Setting LED off...")
            _set_led(False)
            log.debug("Restoring sysctls...")
            _restore_sysctls()
            log.debug("CFE latch open handling complete")
            # Note: Skip _purge_stale_mountpoints() here as os.path.ismount()
            # can block for 30+ seconds on stale mounts, freezing button detection

        # INSERT released - power up and mount
        if ins_prev == 1 and ins_now == 0:
            log.info("CFexpress card status: INSERTED (latch closed)")
            log.debug("Powering up PCIe...")
            _pcie(True)
            log.debug("Setting LED on...")
            _set_led(True)

            # Clear failed device cooldown for NVMe devices (explicit user action)
            _failed_devices = {k: v for k, v in _failed_devices.items()
                             if not k.startswith("/dev/nvme")}
            log.debug("Cleared NVMe device cooldowns")

            # Wait for device enumeration and manually scan for new NVMe devices
            log.debug("Waiting 0.8s for device enumeration...")
            time.sleep(0.8)

            log.debug("Scanning for NVMe devices...")
            # Collect partitions and whole disks separately
            nvme_partitions = []
            nvme_disks = []
            for device in _udev_ctx.list_devices(subsystem="block"):
                devnode = device.device_node
                if not devnode or not devnode.startswith("/dev/nvme"):
                    continue
                if devnode in _mounts:
                    continue

                devtype = device.get("DEVTYPE")
                if devtype == "partition":
                    log.debug("Found NVMe partition: %s", devnode)
                    nvme_partitions.append(devnode)
                elif devtype == "disk":
                    log.debug("Found NVMe disk: %s", devnode)
                    nvme_disks.append(devnode)

            log.debug("Found %d partitions, %d disks", len(nvme_partitions), len(nvme_disks))

            # Mount partitions first
            for devnode in nvme_partitions:
                log.debug("Checking filesystem on %s...", devnode)
                label, _ = _get_filesystem_info(devnode, retries=3, delay=0.3)
                log.debug("Label: %s", label)
                if label == RAW_LABEL:
                    _add_raw(devnode)
                else:
                    _mount(devnode)

            # Only check whole disks if no partitions were found
            if not nvme_partitions:
                log.debug("No partitions found, checking whole disks...")
                for devnode in nvme_disks:
                    log.debug("Checking filesystem on whole disk %s...", devnode)
                    label, fstype = _get_filesystem_info(devnode, retries=3, delay=0.3)
                    if fstype:
                        log.info("Detected whole-disk filesystem on %s (%s)", devnode, fstype)
                        if label == RAW_LABEL:
                            _add_raw(devnode)
                        else:
                            _mount(devnode)
            else:
                log.debug("Skipping whole disk check (partitions exist)")

            log.debug("CFE latch close handling complete")

        # EJECT released - unmount all
        if ej_prev == 1 and ej_now == 0:
            log.info("CFexpress card: EJECTING")
            for dev in list(_mounts):
                subprocess.Popen(["umount", "-l", str(_mounts[dev])],
                              stderr=subprocess.DEVNULL)
                _mounts.pop(dev, None)
                _active_mount_kinds.pop(dev, None)
                _register_raw_remove(dev)
            with _raw_lock:
                _active_raw = None
            _pcie(False)
            _set_led(False)
            _restore_sysctls()

        time.sleep(0.05)

# ─────────────────────────────────────────────────────────────────────────────
# Initial Scan
# ─────────────────────────────────────────────────────────────────────────────
def _initial_scan():
    """Scan and mount all existing devices at startup."""
    _purge_stale_mountpoints()
    log.info("Scanning for existing storage devices...")

    raws, others = [], []

    # Scan partitions
    for device in _udev_ctx.list_devices(subsystem="block", DEVTYPE="partition"):
        devnode = device.device_node
        if not devnode:
            continue
        label, fstype = _get_filesystem_info(devnode)
        if fstype:  # Has a filesystem
            if label == "RAW":
                raws.append(devnode)
            else:
                others.append(devnode)

    # Scan whole disks (for drives without partition tables)
    for device in _udev_ctx.list_devices(subsystem="block", DEVTYPE="disk"):
        devnode = device.device_node
        if not devnode:
            continue
        # Skip devices we already processed as partitions
        if any(devnode in d for d in others + raws):
            continue
        # Skip SD cards, loop devices, and RAM disks
        if devnode.startswith(("/dev/mmcblk", "/dev/loop", "/dev/ram")):
            continue

        label, fstype = _get_filesystem_info(devnode)
        if fstype:  # Has a filesystem on whole disk
            log.info("Found whole-disk filesystem on %s (%s)", devnode, fstype)
            if label == "RAW":
                raws.append(devnode)
            else:
                others.append(devnode)

    # Mount non-RAW drives
    for devnode in others:
        _mount(devnode)

    # Arbitrate RAW drives: lowest /dev path becomes the active /media/RAW, the
    # rest are mounted as standbys (/media/RAW1, …) ready for promotion.
    for devnode in sorted(raws):
        _add_raw(devnode)

    log.info("Initial scan complete: %d mount(s)", len(_mounts))

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def _cfe_hat_init():
    """Initialize CFE HAT PCIe based on current latch state (before initial scan)."""
    if not smbus:
        return False

    I2C_CH, I2C_ADDR = 1, 0x34
    try:
        bus = smbus.SMBus(I2C_CH)
        state = bus.read_byte(I2C_ADDR)
    except OSError:
        return False  # CFE HAT not detected

    def _pcie(bind: bool):
        """Bind/unbind PCIe for CFE card."""
        path = "/sys/bus/platform/drivers/brcm-pcie"
        node = "1000110000.pcie"
        target = "bind" if bind else "unbind"
        try:
            with open(f"{path}/{target}", "w") as f:
                f.write(node)
        except OSError as e:
            if e.errno != errno.EBUSY:
                log.debug("PCIe %s error: %s", target, e)
        if bind:
            time.sleep(0.5)
            subprocess.call(["sh", "-c", "echo 1 > /sys/bus/pci/rescan"],
                          stderr=subprocess.DEVNULL)

    # Initialize PCIe based on latch state
    ins_state = state & 1
    if ins_state == 0:  # Latch is closed (button released)
        log.info("CFexpress card detected at startup, initializing PCIe...")
        _pcie(True)
        time.sleep(0.8)  # Wait for device enumeration
    else:  # Latch is open (button pressed)
        log.info("CFexpress card slot empty at startup")
        _pcie(False)

    return True

def main():
    def _sigterm(_sig, _frame):
        log.info("SIGTERM received, unmounting all devices")
        for dev in list(_mounts):
            _unmount(dev)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm)

    log.info("=== Storage Auto-Mount Starting ===")
    log.info("Mount base: %s", MOUNT_BASE)
    log.info("User: %d:%d", PI_UID, PI_GID)
    log.info("Log level: %s", LOG_LEVEL)

    # Initialize CFE HAT PCIe before scanning
    _cfe_hat_init()

    _initial_scan()

    # Start worker threads
    threading.Thread(target=_udev_worker, daemon=True, name="udev").start()
    threading.Thread(target=_cfe_hat_worker, daemon=True, name="cfe-hat").start()
    threading.Thread(target=_nvme_watchdog, daemon=True, name="nvme-wd").start()
    threading.Thread(target=_sanity_watchdog, daemon=True, name="sanity-wd").start()

    log.info("All workers started, monitoring storage events...")

    # Keep main thread alive
    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
