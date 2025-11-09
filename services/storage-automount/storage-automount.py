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
        "dirty_bytes": 512 * 1024**2,
        "dirty_bg_bytes": 256 * 1024**2,
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

# Non-ext4 filesystem options
FS_OPTS_BASE = {
    "ntfs": f"uid={PI_UID},gid={PI_GID},dmask=022,fmask=133,rw,noatime",
    "exfat": f"uid={PI_UID},gid={PI_GID},dmask=022,fmask=133,rw,noatime",
    "vfat": f"uid={PI_UID},gid={PI_GID},dmask=022,fmask=133,rw,noatime",
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

def _mount(dev: str):
    """Mount device with label-based path and tuning."""
    global _failed_devices

    # Clean up failed device cooldowns (30s)
    current_time = time.time()
    _failed_devices = {k: v for k, v in _failed_devices.items() if current_time - v < 30}

    # Check cooldown
    if dev in _failed_devices:
        remaining = 30 - (time.time() - _failed_devices[dev])
        if remaining > 0:
            log.debug("%s in cooldown, %d seconds remaining", dev, int(remaining))
        return

    # Already mounted by us
    if dev in _mounts:
        log.debug("%s already mounted", dev)
        return

    # Get filesystem info
    label, fstype = _get_filesystem_info(dev)
    if not fstype:
        log.warning("%s: unknown filesystem, skipping", dev)
        _failed_devices[dev] = time.time()
        return

    # Classify media type
    kind = _classify_media(dev)

    # Determine mount path
    if label:
        mount_path = MOUNT_BASE / _sanitize(label)
    else:
        mount_path = MOUNT_BASE / Path(dev).name

    mount_path.mkdir(parents=True, exist_ok=True)

    # Determine mount options
    if fstype == "ext4":
        opts = PROFILES.get(kind, PROFILES["other"])["ext4_opts"]
    else:
        opts = FS_OPTS_BASE.get(fstype, "rw,noatime")

    # Check if already mounted elsewhere
    if _is_device_mounted(dev):
        log.info("%s already mounted elsewhere, tracking it", dev)
        _mounts[dev] = mount_path
        _active_mount_kinds[dev] = kind
        _apply_block_tuning(dev, kind)
        if dev.startswith("/dev/nvme"):
            _apply_nvme_power_tuning(kind)
        _apply_sysctl_cushions(kind)
        return

    # Attempt mount
    cmd = ["mount", "-t", fstype, "-o", opts, dev, str(mount_path)]
    log.info("Mounting %s (%s, %s) → %s", dev, fstype, kind, mount_path)

    if subprocess.call(cmd, stderr=subprocess.DEVNULL) == 0:
        _mounts[dev] = mount_path
        _active_mount_kinds[dev] = kind
        try:
            os.chown(mount_path, PI_UID, PI_GID)
        except OSError:
            pass

        _apply_block_tuning(dev, kind)
        if dev.startswith("/dev/nvme"):
            _apply_nvme_power_tuning(kind)
        _apply_sysctl_cushions(kind)

        log.info("✓ Mounted %s successfully", dev)
        return

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
            _apply_block_tuning(dev, kind)
            if dev.startswith("/dev/nvme"):
                _apply_nvme_power_tuning(kind)
            _apply_sysctl_cushions(kind)
            log.info("✓ Mounted %s after repair", dev)
            return

    # Failed - cleanup and cooldown
    try:
        if not any(mount_path.iterdir()):
            mount_path.rmdir()
    except OSError:
        pass
    _failed_devices[dev] = time.time()
    log.error("✗ Failed to mount %s", dev)

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

    # Clean up mount point (may fail if still mounted, that's OK)
    try:
        if not any(mount_path.iterdir()):
            mount_path.rmdir()
            log.debug("Removed mount point: %s", mount_path)
    except OSError:
        pass

    # Restore sysctls if no mounts remain
    log.debug("Calling _restore_sysctls...")
    _restore_sysctls()
    log.debug("_unmount complete for %s", dev)

# ─────────────────────────────────────────────────────────────────────────────
# RAW Arbitration
# ─────────────────────────────────────────────────────────────────────────────
def _register_raw_add(dev: str):
    """Register a device with LABEL=RAW."""
    with _raw_lock:
        if dev not in _raw_pool:
            _raw_pool.append(dev)

def _register_raw_remove(dev: str):
    """Unregister a RAW device."""
    with _raw_lock:
        if dev in _raw_pool:
            _raw_pool.remove(dev)

def _switch_to_raw(dev: str | None):
    """Mount dev (LABEL=RAW) and unmount previous RAW."""
    global _active_raw
    with _raw_lock:
        if dev == _active_raw:
            return
        if _active_raw:
            _unmount(_active_raw)
        if dev:
            _mount(dev)
        _active_raw = dev

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
                        _unmount(dev)
                except OSError:
                    pass
        time.sleep(0.5)

def _sanity_watchdog():
    """Health check: detect yanked drives via statvfs errors."""
    while True:
        for dev, mp in list(_mounts.items()):
            # Skip SD card devices - they're not managed by this script
            # and statvfs can block for 30+ seconds on bad SD card mounts
            if dev.startswith("/dev/mmcblk"):
                continue

            try:
                os.statvfs(mp)
            except OSError as exc:
                if exc.errno in (errno.EIO, errno.ENOENT):
                    log.warning("I/O error on %s (%s) - device yanked, unmounting",
                              dev, os.strerror(exc.errno))
                    subprocess.call(["umount", "-l", str(mp)],
                                  stderr=subprocess.DEVNULL)
                    _mounts.pop(dev, None)
                    _active_mount_kinds.pop(dev, None)

                    # Clean up RAW arbitration state
                    _register_raw_remove(dev)
                    with _raw_lock:
                        global _active_raw
                        if dev == _active_raw:
                            _active_raw = None
                            # Try to mount another RAW if available
                            fallback = _raw_pool[-1] if _raw_pool else None
                            if fallback:
                                _switch_to_raw(fallback)

                    _restore_sysctls()

        # RAW arbitration self-heal
        with _raw_lock:
            if len(_raw_pool) > 1 and _raw_pool:
                preferred = _raw_pool[-1]
                if preferred != _active_raw:
                    _switch_to_raw(preferred)

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
            if label == "RAW":
                _register_raw_add(devnode)
                _switch_to_raw(devnode)
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
                if label == "RAW":
                    _register_raw_add(devnode)
                    _switch_to_raw(devnode)
                else:
                    _mount(devnode)

        # Partition removed
        elif action == "remove" and devtype == "partition":
            log.debug("Partition removed: %s", devnode)
            _register_raw_remove(devnode)
            log.debug("Calling _unmount for %s", devnode)
            _unmount(devnode)
            log.debug("Unmount call returned")
            with _raw_lock:
                if devnode == _active_raw:
                    log.debug("Was active RAW, checking for fallback...")
                    fallback = _raw_pool[-1] if _raw_pool else None
                    log.debug("Fallback device: %s", fallback)
                    _switch_to_raw(fallback)
                    log.debug("RAW switch complete")
            log.debug("Partition removal handling complete")

        # Whole disk removed
        elif action == "remove" and devtype == "disk":
            victims = [d for d in list(_mounts) if d.startswith(devnode)]
            for part in victims:
                _register_raw_remove(part)
                _unmount(part)
            with _raw_lock:
                if _active_raw and _active_raw.startswith(devnode):
                    fallback = _raw_pool[-1] if _raw_pool else None
                    _switch_to_raw(fallback)

# ─────────────────────────────────────────────────────────────────────────────
# CFE HAT I2C Worker
# ─────────────────────────────────────────────────────────────────────────────
def _cfe_hat_worker():
    """Monitor CFE HAT insert/eject buttons via I2C."""
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
                log.debug("Starting non-blocking lazy unmount...")
                # Use Popen to not wait for umount completion (it can block for 30+ seconds)
                subprocess.Popen(["umount", "-l", str(_mounts[dev])],
                               stderr=subprocess.DEVNULL)
                log.debug("Umount started, cleaning up state...")
                _mounts.pop(dev, None)
                _active_mount_kinds.pop(dev, None)
                _register_raw_remove(dev)
                with _raw_lock:
                    global _active_raw
                    if dev == _active_raw:
                        _active_raw = None
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
            global _failed_devices
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
                if label == "RAW":
                    _register_raw_add(devnode)
                    _switch_to_raw(devnode)
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
                        if label == "RAW":
                            _register_raw_add(devnode)
                            _switch_to_raw(devnode)
                        else:
                            _mount(devnode)
            else:
                log.debug("Skipping whole disk check (partitions exist)")

            log.debug("CFE latch close handling complete")

        # EJECT released - unmount all
        if ej_prev == 1 and ej_now == 0:
            log.info("CFexpress card: EJECTING")
            for dev in list(_mounts):
                subprocess.call(["umount", "-l", str(_mounts[dev])],
                              stderr=subprocess.DEVNULL)
                _mounts.pop(dev, None)
                _active_mount_kinds.pop(dev, None)
                _register_raw_remove(dev)
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

    # Arbitrate RAW drives
    if raws:
        devnode = sorted(raws)[-1]  # Use last one
        _register_raw_add(devnode)
        _switch_to_raw(devnode)

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