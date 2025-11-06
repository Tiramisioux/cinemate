#!/usr/bin/env python3
"""
Consolidated, media-aware automounter for Raspberry Pi 5.
- PCIe (CFE-HAT) NVMe, USB NVMe, USB SSD (and fallback).
- Per-media mount+I/O tuning, sysctl cushions, watchdogs, RAW arbitration.
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
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    redis = None

import shutil

import pyudev  # sudo apt install python3-pyudev
try:
    import smbus  # sudo apt install python3-smbus
except Exception:
    smbus = None

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("STORAGE_AUTOMOUNT_LOG", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [storage-automount] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("storage-automount")


# ─────────────────────────────────────────────────────────────────────────────
# Redis integration (optional)
# ─────────────────────────────────────────────────────────────────────────────
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB", "0"))

REDIS_KEY_IS_MOUNTED          = os.getenv("REDIS_KEY_IS_MOUNTED", "is_mounted")
REDIS_KEY_STORAGE_TYPE        = os.getenv("REDIS_KEY_STORAGE_TYPE", "storage_type")
REDIS_KEY_MECHANICAL_STATUS   = os.getenv("REDIS_KEY_MECHANICAL_STATUS", "storage_mechanical_status")
REDIS_KEY_STATUS_MESSAGE      = os.getenv("REDIS_KEY_STATUS_MESSAGE", "storage_status_message")
REDIS_KEY_SPACE_LEFT          = os.getenv("REDIS_KEY_SPACE_LEFT", "space_left")

REDIS_LOG_LIST    = os.getenv("REDIS_STORAGE_LOG_LIST", "storage_automount:log")
REDIS_LOG_LAST    = os.getenv("REDIS_STORAGE_LOG_LAST", "storage_automount:last")
REDIS_LOG_CHANNEL = os.getenv("REDIS_STORAGE_LOG_CHANNEL", "storage_automount.log")
REDIS_LOG_MAX     = int(os.getenv("REDIS_STORAGE_LOG_MAX", "200"))

_redis_client = None
_redis_lock = threading.Lock()


def _redis_connect():
    global _redis_client
    if redis is None:
        return None
    with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
            client.ping()
        except Exception as exc:  # pragma: no cover - connectivity failure
            log.debug("Redis unavailable (%s:%s/%s): %s", REDIS_HOST, REDIS_PORT, REDIS_DB, exc)
            _redis_client = None
        else:
            _redis_client = client
        return _redis_client


def _redis_safe_call(fn, *args, **kwargs) -> None:
    client = _redis_connect()
    if client is None:
        return
    try:
        fn(client, *args, **kwargs)
    except Exception as exc:  # pragma: no cover - runtime connectivity failure
        log.debug("Redis call failed: %s", exc)


def _redis_set_value(key: str, value: str) -> None:
    def _set(client, k, v):
        client.set(k, v)
    _redis_safe_call(_set, key, value)


def _redis_pipeline_exec(cmds) -> None:
    client = _redis_connect()
    if client is None:
        return
    try:
        pipe = client.pipeline()
        for fn, args, kwargs in cmds:
            getattr(pipe, fn)(*args, **kwargs)
        pipe.execute()
    except Exception as exc:  # pragma: no cover - runtime connectivity failure
        log.debug("Redis pipeline failed: %s", exc)


class RedisLogHandler(logging.Handler):
    """Forward log lines to Redis so the CLI/UI can mirror service output."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - logging side-effect
        msg = self.format(record)
        client = _redis_connect()
        if client is None:
            return
        try:
            pipe = client.pipeline()
            pipe.lpush(REDIS_LOG_LIST, msg)
            pipe.ltrim(REDIS_LOG_LIST, 0, REDIS_LOG_MAX - 1)
            pipe.set(REDIS_LOG_LAST, msg)
            pipe.publish(REDIS_LOG_CHANNEL, msg)
            pipe.execute()
        except Exception as exc:  # pragma: no cover - runtime connectivity failure
            log.debug("Redis log emit failed: %s", exc)


if redis is not None:
    redis_handler = RedisLogHandler()
    redis_handler.setLevel(logging.INFO)
    redis_handler.setFormatter(logging.Formatter("%(asctime)s [storage-automount] %(levelname)s: %(message)s",
                                               datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(redis_handler)


def _redis_update_state(*, mounted: bool | None = None,
                        storage_type: str | None = None,
                        mechanical: str | None = None,
                        message: str | None = None,
                        space_left: float | None = None) -> None:
    cmds = []
    if mounted is not None:
        cmds.append(("set", (REDIS_KEY_IS_MOUNTED, "1" if mounted else "0"), {}))
    if storage_type is not None:
        cmds.append(("set", (REDIS_KEY_STORAGE_TYPE, storage_type), {}))
    if mechanical is not None:
        cmds.append(("set", (REDIS_KEY_MECHANICAL_STATUS, mechanical), {}))
    if message is not None:
        cmds.append(("set", (REDIS_KEY_STATUS_MESSAGE, message), {}))
    if space_left is not None:
        cmds.append(("set", (REDIS_KEY_SPACE_LEFT, f"{space_left:.2f}"), {}))
    if cmds:
        _redis_pipeline_exec(cmds)


def _storage_type_from_kind(kind: str) -> str:
    return MECHANICAL_KIND_MAP.get(kind, "other")


def _space_left_gb(mp: Path) -> float | None:
    try:
        usage = shutil.disk_usage(mp)
        return usage.free / (1024 ** 3)
    except Exception:
        return None


def _redis_record_mount(kind: str, label: str | None, mp: Path) -> None:
    storage_type = _storage_type_from_kind(kind)
    message = f"Mounted {label or mp.name} at {mp}" if label else f"Mounted {mp}"
    space_left = _space_left_gb(mp)
    mechanical = f"{storage_type}:mounted"
    mounted_flag = label == "RAW"
    _redis_update_state(
        mounted=mounted_flag,
        storage_type=storage_type if mounted_flag else None,
        mechanical=mechanical,
        message=message,
        space_left=space_left if mounted_flag and space_left is not None else None,
    )


def _redis_record_unmount(kind: str | None, label: str | None) -> None:
    storage_type = _storage_type_from_kind(kind or "other")
    mechanical = f"{storage_type}:unmounted"
    mounted_flag = label == "RAW"
    _redis_update_state(
        mounted=False if mounted_flag else None,
        storage_type="none" if mounted_flag else None,
        mechanical=mechanical,
        message=f"Unmounted {label or storage_type}",
        space_left=0.0 if mounted_flag else None,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Globals
# ─────────────────────────────────────────────────────────────────────────────
PI_UID = int(os.getenv("PI_UID", "1000"))
PI_GID = int(os.getenv("PI_GID", "1000"))

MOUNT_BASE = Path("/media")

# Active mounts and kinds (devnode → mountpoint / kind)
_mounts: dict[str, Path] = {}
_active_mount_kinds: dict[str, str] = {}
_mount_labels: dict[str, str] = {}

# RAW arbitration
_raw_pool: list[str] = []     # list of /dev/… that have LABEL==RAW (present)
_active_raw: str | None = None
_raw_lock = threading.Lock()

# pyudev context
_udev_ctx = pyudev.Context()

# Saved sysctl values for restoration
_sysctl_saved: dict[str, str | None] = {}

# Optional override (debugging): cfe_nvme | usb_nvme | usb_ssd | other
PROFILE_OVERRIDE = (os.getenv("STORAGE_AUTOMOUNT_PROFILE_OVERRIDE") or "").strip()

MECHANICAL_KIND_MAP = {
    "cfe_nvme": "cfe",
    "usb_nvme": "nvme",
    "usb_ssd": "ssd",
    "other": "other",
}

# ─────────────────────────────────────────────────────────────────────────────
# Media profiles (mount + kernel/block I/O cushions)
# ─────────────────────────────────────────────────────────────────────────────
PROFILES = {
    "cfe_nvme": {  # PCIe NVMe (CFE-HAT)
        "ext4_opts": "rw,noatime,nodiratime,commit=60",
        "dirty_bytes":        1 * 1024**3,      # 1 GiB
        "dirty_bg_bytes":   256 * 1024**2,      # 256 MiB
        "rq_affinity": "2",
        "scheduler":   "none",
        "nr_requests": "512",
        "nvme_ps_latency_us": "0",              # prefer lowest latency
    },
    "usb_nvme": {  # UAS bridge → NVMe
        "ext4_opts": "rw,noatime,nodiratime,commit=60",
        "dirty_bytes":      512 * 1024**2,      # 512 MiB
        "dirty_bg_bytes":   256 * 1024**2,      # 256 MiB
        "rq_affinity": "2",
        "scheduler":   "none",
        "nr_requests": "256",
        "nvme_ps_latency_us": "0",
    },
    "usb_ssd": {   # UAS/SATA SSD
        "ext4_opts": "rw,noatime,nodiratime,commit=60",
        "dirty_bytes":      512 * 1024**2,
        "dirty_bg_bytes":   256 * 1024**2,
        "rq_affinity": "2",
        "scheduler":   "none",
        "nr_requests": "256",
    },
    "other": {     # fallback: safe, not too aggressive
        "ext4_opts": "rw,noatime",
        "dirty_bytes":      256 * 1024**2,
        "dirty_bg_bytes":   128 * 1024**2,
        "rq_affinity": "1",
        "scheduler":   "mq-deadline",
        "nr_requests": "128",
    },
}

# Non-ext4 base opts
FS_OPTS_BASE = {
    "ntfs":  f"uid={PI_UID},gid={PI_GID},rw,noatime,umask=000",
    "exfat": f"uid={PI_UID},gid={PI_GID},rw,noatime",
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
    except Exception as e:
        log.debug("write(%s=%s) failed: %s", path, val, e)
        return False

def _sysctl_get(key: str) -> str | None:
    return _read(f"/proc/sys/{key.replace('.', '/')}")

def _sysctl_set(key: str, val: str) -> bool:
    return _write(f"/proc/sys/{key.replace('.', '/')}", val)

def _sanitize(label: str) -> str:
    return re.sub(r"[^\w\-.]", "_", label)[:64] or "RAW"

def _root_block_name(devnode: str) -> str:
    """nvme0n1p1 → nvme0n1 ; sda1 → sda"""
    name = Path(devnode).name
    if name.startswith("nvme") and "p" in name:
        return name.split("p", 1)[0]
    return re.sub(r"\d+$", "", name)

def _ext4_opts_for(kind: str) -> str:
    return PROFILES.get(kind, PROFILES["other"])["ext4_opts"]

def _current_mount_opts(mp: Path) -> str:
    """Return current comma-joined option string for mountpoint (best effort)."""
    try:
        with open("/proc/self/mountinfo") as f:
            for line in f:
                # fields: ... mountpoint ... - fstype source options
                if f" {mp} " in line or line.rstrip().endswith(f" {mp}"):
                    after_dash = line.split(" - ", 1)[1]
                    # e.g. "ext4 /dev/root rw,noatime"
                    parts = after_dash.split()
                    return parts[2] if len(parts) >= 3 else ""
    except Exception:
        pass
    return ""

def _is_dev_mounted(dev: str) -> bool:
    with open("/proc/self/mountinfo", "r") as f:
        for line in f:
            try:
                after_dash = line.split(" - ", 1)[1]
                source = after_dash.split()[1]
                if source == dev:
                    return True
            except IndexError:
                continue
    return False

def _is_mp_busy(mp: Path) -> bool:
    try:
        mp.rmdir()
        mp.mkdir(parents=True, exist_ok=True)
        return False
    except OSError:
        return True

def _get_fs(dev: str, retries: int = 5, delay: float = 0.5):
    """
    Return (LABEL, FSTYPE). Retries to let udev/blkid settle (CFE NVMe needs a moment).
    """
    for i in range(retries):
        try:
            label = subprocess.check_output(
                ["blkid", "-s", "LABEL", "-o", "value", dev], text=True
            ).strip()
        except subprocess.CalledProcessError:
            label = ""
        try:
            fstype = subprocess.check_output(
                ["blkid", "-s", "TYPE", "-o", "value", dev], text=True
            ).strip()
        except subprocess.CalledProcessError:
            fstype = ""
        if fstype:
            return (label or None), fstype
        time.sleep(delay)
    log.warning("blkid retries exhausted for %s", dev)
    return None, None

def _classify(devnode: str) -> str:
    """Return one of: 'cfe_nvme', 'usb_nvme', 'usb_ssd', 'other' (env override wins)."""
    if PROFILE_OVERRIDE:
        return PROFILE_OVERRIDE

    try:
        u = pyudev.Device.from_device_file(_udev_ctx, devnode)
    except Exception:
        return "other"

    if devnode.startswith("/dev/nvme"):
        for p in u.ancestors:
            if p.subsystem == "usb":
                return "usb_nvme"
        return "cfe_nvme"

    # sdX class
    for p in u.ancestors:
        if p.subsystem == "usb":
            drv = (u.get("ID_USB_DRIVER") or "").lower()
            # Heuristic: treat UAS storage with NVMe bridges as usb_nvme
            if drv == "uas":
                return "usb_nvme"
            return "usb_ssd"
    return "other"

# ─────────────────────────────────────────────────────────────────────────────
# Tuning
# ─────────────────────────────────────────────────────────────────────────────
def _apply_block_tuning(devnode: str, kind: str):
    root = _root_block_name(devnode)
    qpath = f"/sys/block/{root}/queue"
    prof  = PROFILES.get(kind, PROFILES["other"])

    # I/O scheduler
    sched = prof.get("scheduler")
    if sched:
        _write(f"{qpath}/scheduler", sched)

    # Completion affinity
    rq = prof.get("rq_affinity")
    if rq:
        _write(f"{qpath}/rq_affinity", rq)

    # Queue depth hint
    nr = prof.get("nr_requests")
    if nr:
        _write(f"{qpath}/nr_requests", nr)

def _apply_nvme_power_saver(kind: str):
    """Lower NVMe APST latency target when writable; otherwise log a hint."""
    target = "/sys/module/nvme_core/parameters/default_ps_max_latency_us"
    if not Path(target).exists():
        target = "/sys/module/nvme/parameters/default_ps_max_latency_us"
    val = PROFILES.get(kind, PROFILES["other"]).get("nvme_ps_latency_us")
    if val is None:
        return
    if not _write(target, val):
        log.debug(
            "NVMe APST knob not writable; consider adding "
            "nvme_core.default_ps_max_latency_us=%s to /boot/firmware/cmdline.txt",
            val,
        )

def _apply_sysctl_profile(kind: str):
    """Apply dirty_* cushions; save originals on first application."""
    if not _sysctl_saved:
        for k in (
            "vm.dirty_bytes",
            "vm.dirty_background_bytes",
            "vm.dirty_writeback_centisecs",
            "vm.dirty_expire_centisecs",
            "vm.dirty_ratio",
            "vm.dirty_background_ratio",
        ):
            _sysctl_saved[k] = _sysctl_get(k)

    prof = PROFILES.get(kind, PROFILES["other"])
    _sysctl_set("vm.dirty_ratio", "0")
    _sysctl_set("vm.dirty_background_ratio", "0")
    _sysctl_set("vm.dirty_writeback_centisecs", "150")  # 1.5 s flush cadence
    _sysctl_set("vm.dirty_expire_centisecs", "3000")    # 30 s max age
    _sysctl_set("vm.dirty_background_bytes", str(prof["dirty_bg_bytes"]))
    _sysctl_set("vm.dirty_bytes", str(prof["dirty_bytes"]))
    log.info(
        "Applied sysctl cushions for %s: dirty=%s BG=%s",
        kind,
        prof["dirty_bytes"],
        prof["dirty_bg_bytes"],
    )

def _maybe_restore_sysctls():
    """Restore saved sysctl values when no active mounts remain."""
    if _active_mount_kinds:
        return
    if not _sysctl_saved:
        return
    for k, v in _sysctl_saved.items():
        if v is not None:
            _sysctl_set(k, v)
    log.info("Restored sysctl defaults (no active media)")

# ─────────────────────────────────────────────────────────────────────────────
# RAW arbitration helpers
# ─────────────────────────────────────────────────────────────────────────────
def _register_raw_add(dev: str):
    with _raw_lock:
        if dev not in _raw_pool:
            _raw_pool.append(dev)

def _register_raw_remove(dev: str):
    with _raw_lock:
        if dev in _raw_pool:
            _raw_pool.remove(dev)

def _switch_to_raw(dev: str | None):
    """Mount *dev* (LABEL=RAW) and unmount the previous one."""
    global _active_raw
    with _raw_lock:
        if dev == _active_raw:
            return
        if _active_raw is not None:
            _unmount(_active_raw)
        if dev is not None:
            _mount(dev)
        _active_raw = dev

# ─────────────────────────────────────────────────────────────────────────────
# Stale mountpoint cleanup
# ─────────────────────────────────────────────────────────────────────────────
def _purge_stale_mountpoints() -> None:
    """Ensure stale /media/RAW dirs never block future mounts."""
    mp = MOUNT_BASE / "RAW"
    if not mp.exists():
        return
    if os.path.ismount(mp):
        return
    if not any(mp.iterdir()):
        try:
            mp.rmdir()
            log.info("Removed empty stale mount-point %s", mp)
        except OSError as exc:
            log.warning("Unable to remove %s: %s", mp, exc)
        return
    ts = time.strftime("%Y%m%d-%H%M%S")
    new = mp.with_name(f"RAW.STALE-{ts}")
    try:
        mp.rename(new)
        log.warning("%s existed but was not a mount-point → renamed to %s", mp, new)
    except OSError as exc:
        log.error("Cannot rename busy directory %s (%s) — aborting start-up", mp, exc)
        sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Mount / unmount
# ─────────────────────────────────────────────────────────────────────────────
def _auto_repair(dev: str, fstype: str) -> bool:
    """Try one non-interactive repair; return True if FS is OK afterward."""
    if fstype == "ext4":
        log.warning("Repairing %s with e2fsck -p", dev)
        res = subprocess.call(["e2fsck", "-f", "-p", dev])
        ok = res in (0, 1, 2)
    elif fstype == "ntfs":
        log.warning("Repairing %s with ntfsfix", dev)
        ok = subprocess.call(["ntfsfix", dev]) == 0
    elif fstype == "exfat":
        log.warning("Repairing %s with fsck.exfat -a", dev)
        ok = subprocess.call(["fsck.exfat", "-a", dev]) == 0
    else:
        ok = False
    return ok

def _remount_with_opts(dev: str, mp: Path, opts: str) -> bool:
    """Try to remount with new options when something else mounted it."""
    try:
        res = subprocess.call(["mount", "-o", f"remount,{opts}", str(mp)])
        if res == 0:
            log.info("Remounted %s at %s with opts='%s'", dev, mp, opts)
            return True
    except Exception as e:
        log.debug("remount failed for %s: %s", mp, e)
    return False

def _mount(dev: str):
    """
    Mount *dev* under /media/<LABEL>, apply media-specific tunings, sysctls,
    and attempt to remount if already mounted with sub-optimal options.
    """
    _purge_stale_mountpoints()

    # Reconcile stale table entries
    mp_prev = _mounts.get(dev)
    if mp_prev and not os.path.ismount(mp_prev):
        log.info("Cleaning up stale mount record for %s", dev)
        _mounts.pop(dev, None)

    if dev in _mounts:
        log.debug("%s already mounted by this daemon – skipping", dev)
        return

    label, fstype = _get_fs(dev)
    if not fstype:
        log.warning("%s: unknown filesystem – skipping", dev)
        return

    kind = _classify(dev)
    mp = MOUNT_BASE / _sanitize(label or Path(dev).name)
    mp.mkdir(parents=True, exist_ok=True)

    if fstype == "ext4":
        opts = _ext4_opts_for(kind)
    else:
        opts = FS_OPTS_BASE.get(fstype, "rw,noatime")

    # Already mounted elsewhere? Try to tune/remount; otherwise fall through to mount.
    if _is_dev_mounted(dev):
        log.debug("%s is already mounted (elsewhere) – checking opts", dev)
        # Best effort: find mountpoint from /proc/self/mountinfo
        mpt = None
        with open("/proc/self/mountinfo") as f:
            for line in f:
                if f" - {fstype} {dev} " in line:
                    mpt = Path(line.split()[4])
                    break
        if mpt:
            current = _current_mount_opts(mpt)
            if current and current != opts:
                _remount_with_opts(dev, mpt, opts)
            _mounts[dev] = mpt
            _active_mount_kinds[dev] = kind
            _mount_labels[dev] = label or Path(dev).name
            _redis_record_mount(kind, label, mpt)
            _apply_block_tuning(dev, kind)
            if dev.startswith("/dev/nvme"):
                _apply_nvme_power_saver(kind)
            _apply_sysctl_profile(kind)
            return
        else:
            # Unknown mpt; skip double-mounting
            log.warning("%s already mounted but mountpoint unknown – skipping", dev)
            return

    # Normal mount path
    cmd = ["mount", "-t", fstype, "-o", opts, dev, str(mp)]
    log.info("Mounting %s (%s, kind=%s) → %s  opts='%s'", dev, fstype, kind, mp, opts)

    if subprocess.call(cmd) == 0:
        _mounts[dev] = mp
        _active_mount_kinds[dev] = kind
        _mount_labels[dev] = label or Path(dev).name
        try:
            os.chown(mp, PI_UID, PI_GID)
        except Exception as exc:
            log.debug("Unable to chown %s: %s (continuing)", mp, exc)

        _apply_block_tuning(dev, kind)
        if dev.startswith("/dev/nvme"):
            _apply_nvme_power_saver(kind)
        _apply_sysctl_profile(kind)

        log.info("Mounted %s OK", dev)
        _redis_record_mount(kind, label, mp)
        return

    # First attempt failed → auto-repair once
    log.error("Mount failed (%s)", " ".join(cmd))
    if _auto_repair(dev, fstype):
        log.info("%s: repair successful, retrying mount", dev)
        if subprocess.call(cmd) == 0:
            _mounts[dev] = mp
            _active_mount_kinds[dev] = kind
            _mount_labels[dev] = label or Path(dev).name
            try:
                os.chown(mp, PI_UID, PI_GID)
            except Exception as exc:
                log.debug("Unable to chown %s after repair: %s", mp, exc)
            _apply_block_tuning(dev, kind)
            if dev.startswith("/dev/nvme"):
                _apply_nvme_power_saver(kind)
            _apply_sysctl_profile(kind)
            log.info("Mounted %s OK after repair", dev)
            _redis_record_mount(kind, label, mp)
            return

    # Still failing — clean up empty dir
    try:
        if not any(mp.iterdir()):
            mp.rmdir()
    except Exception:
        pass
    log.error("%s: mount failed; leaving mountpoint in place", dev)

def _lazy_umount_mp(mp: Path, retries: int = 10) -> bool:
    for _ in range(retries):
        if not os.path.ismount(mp):
            return True
        subprocess.call(["umount", "-l", str(mp)])
        time.sleep(0.2)
    return False

def _wait_for_raw_mount(timeout: float = 8.0) -> bool:
    mp = MOUNT_BASE / "RAW"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.ismount(mp):
            return True
        time.sleep(0.2)
    return False

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
        return

    mp = _mounts.pop(dev, None)
    kind = _active_mount_kinds.pop(dev, None)
    label = _mount_labels.pop(dev, None)

    if not mp:
        return

    log.info("Unmounting %s from %s", dev, mp)
    res = subprocess.call(["umount", dev])
    if res != 0:
        log.warning("umount %s failed (exit=%d) – retrying lazy by mount-point", dev, res)
        if not _lazy_umount_mp(mp):
            log.error("Lazy umount also failed, mount is still busy")
            _mounts[dev] = mp  # keep it tracked
            return

    if not _is_mp_busy(mp):
        try:
            mp.rmdir()
        except OSError:
            pass
    log.info("Unmounted %s OK", dev)

    if not _active_mount_kinds:
        _maybe_restore_sysctls()

    _redis_record_unmount(kind, label)

def _force_lazy_unmount(dev: str, retries: int = 20) -> bool:
    mp = _mounts.get(dev)
    if mp is None:
        return False
    subprocess.call(["umount", "-l", str(mp)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(retries):
        if not os.path.ismount(mp):
            _mounts.pop(dev, None)
            kind = _active_mount_kinds.pop(dev, None)
            label = _mount_labels.pop(dev, None)
            try:
                if not _is_mp_busy(mp):
                    mp.rmdir()
            except OSError:
                pass
            if not _active_mount_kinds:
                _maybe_restore_sysctls()
            _redis_record_unmount(kind, label)
            return True
        time.sleep(0.1)
    log.warning("Lazy unmount timeout for %s", dev)
    return False

# ─────────────────────────────────────────────────────────────────────────────
# Watchdogs
# ─────────────────────────────────────────────────────────────────────────────
def _dead_nvme_cleanup():
    """If NVMe controller is 'dead', lazily unmount RAW to stop writes."""
    for dev, mp in list(_mounts.items()):
        if not dev.startswith("/dev/nvme"):
            continue
        root = _root_block_name(dev)
        state_file = Path(f"/sys/block/{root}/device/state")
        if not state_file.exists():
            continue
        try:
            state = state_file.read_text().strip()
        except OSError:
            continue
        if state == "dead":
            log.warning("NVMe controller for %s reported state=dead – lazy unmount", dev)
            _unmount(dev)

def _nvme_watchdog():
    log.debug("NVMe watchdog thread started")
    while True:
        _dead_nvme_cleanup()
        time.sleep(0.5)

def _sanity_watchdog():
    """
    Every 3 s:
      • reconcile _mounts with /proc/self/mountinfo
      • statvfs() each mount; on EIO/ENOENT assume yank and lazy-unmount
      • auto-recover: ensure RAW arbitration still holds (if multiple RAW present)
    """
    while True:
        # Reconcile table with reality
        real_sources = {line.split(" - ", 1)[1].split()[1] for line in open("/proc/self/mountinfo")}
        for dev in list(_mounts):
            if dev not in real_sources:
                log.debug("Watchdog: %s vanished from mountinfo, cleaning up", dev)
                _mounts.pop(dev, None)
                _active_mount_kinds.pop(dev, None)
        # Yank detection
        for dev, mp in list(_mounts.items()):
            try:
                os.statvfs(mp)
            except OSError as exc:
                if exc.errno in (errno.EIO, errno.ENOENT):
                    log.warning("Watchdog: I/O error on %s (%s) – assuming yank, lazy-unmounting",
                                dev, os.strerror(exc.errno))
                    _force_lazy_unmount(dev)

        # RAW arbitration self-heal (if multiple RAW present, pick the last seen)
        with _raw_lock:
            if len(_raw_pool) > 1:
                preferred = _raw_pool[-1]
                if preferred != _active_raw:
                    _switch_to_raw(preferred)

        time.sleep(3)

# ─────────────────────────────────────────────────────────────────────────────
# udev worker
# ─────────────────────────────────────────────────────────────────────────────
def _udev_worker():
    """
    Handle block-layer udev events (disk + partitions).
      • add/change partition → normal _mount() or RAW arbitration
      • remove partition     → _unmount(), RAW fallback
      • remove disk          → unmount all partitions under it, RAW fallback
    """
    monitor = pyudev.Monitor.from_netlink(_udev_ctx)
    monitor.filter_by(subsystem="block")
    log.debug("udev worker started")

    # pyudev yields Device objects; some versions yield (action, device).
    # Normalize to (action, device).
    def _iter_events():
        for evt in monitor:
            try:
                action = evt.action
                yield (action, evt)
            except AttributeError:
                # Older style: (action, device)
                try:
                    action, dev = evt
                    yield (action, dev)
                except Exception:
                    continue

    for action, device in _iter_events():
        devnode = device.device_node
        dtype   = device.get("DEVTYPE")  # "disk" or "partition"
        if not devnode:
            continue

        if action in ("add", "change") and dtype == "partition":
            label, _ = _get_fs(devnode)
            if label == "RAW":
                _register_raw_add(devnode)
                _switch_to_raw(devnode)
            else:
                _mount(devnode)
            continue

        if action == "remove" and dtype == "partition":
            _register_raw_remove(devnode)
            _unmount(devnode)
            with _raw_lock:
                if devnode == _active_raw:
                    fallback = _raw_pool[-1] if _raw_pool else None
                    _switch_to_raw(fallback)
            continue

        if action == "remove" and dtype == "disk":
            victims = [d for d in list(_mounts) if d.startswith(devnode)]
            for part in victims:
                _register_raw_remove(part)
                _unmount(part)
            with _raw_lock:
                if _active_raw and _active_raw.startswith(devnode):
                    fallback = _raw_pool[-1] if _raw_pool else None
                    _switch_to_raw(fallback)

# ─────────────────────────────────────────────────────────────────────────────
# CFE-HAT worker (new mechanics)
# ─────────────────────────────────────────────────────────────────────────────
def _cfe_hat_worker():
    global _active_raw
    if smbus is None:
        log.debug("No smbus module, CFE-HAT thread disabled")
        return

    I2C_CH, I2C_ADDR = 1, 0x34
    try:
        bus = smbus.SMBus(I2C_CH)
        bus.read_byte(I2C_ADDR)
    except OSError:
        log.info("CFE-HAT not detected on I²C, skipping thread")
        return

    log.info("=" * 80)
    log.info("CFE Hat Auto Mount worker initialising")
    log.info("=" * 80)

    led_state = False

    def _set_led(state: bool) -> None:
        nonlocal led_state
        if state == led_state:
            return
        try:
            bus.write_byte(I2C_ADDR, 0x01 if state else 0x00)
            led_state = state
            log.debug("CFE LED set to %s", "ON" if state else "OFF")
        except OSError as exc:
            log.debug("CFE-HAT LED write error: %s", exc)

    def _redis_mech(status: str, message: str | None = None) -> None:
        _redis_update_state(mechanical=status, message=message)

    def _read_buttons() -> tuple[int, int]:
        try:
            while True:
                data = bus.read_byte(I2C_ADDR)
                if data != 0x69:
                    break
                time.sleep(0.1)
        except OSError as exc:
            log.error("CFE I2C read failed: %s", exc)
            return (0, 0)
        insert_button = 1 if (data & 0x01) else 0
        eject_button = 1 if (data & 0x02) else 0
        log.debug("CFE buttons → insert=%d eject=%d raw=0x%02X", insert_button, eject_button, data)
        return (insert_button, eject_button)

    def _pcie_bind(bind: bool) -> None:
        node = "1000110000.pcie"
        driver_path = "/sys/bus/platform/drivers/brcm-pcie"
        target = "bind" if bind else "unbind"
        try:
            with open(f"{driver_path}/{target}", "w") as fh:
                fh.write(node)
            log.info("PCIe %s request for %s", target, node)
        except OSError as exc:
            if exc.errno != errno.EBUSY:
                log.error("PCIe %s error: %s", target, exc)
        if bind:
            time.sleep(0.5)
            subprocess.call(["sh", "-c", "echo 1 > /sys/bus/pci/rescan"])

    def _check_for_device(device_name: str) -> str | None:
        try:
            output = subprocess.check_output("lspci -mm", shell=True, text=True)
        except subprocess.CalledProcessError as exc:
            log.error("lspci failed: %s", exc)
            return None
        for line in output.splitlines():
            if device_name in line:
                addr = line.split()[0]
                if len(addr) <= 7:
                    addr = "0000:" + addr
                log.debug("Found PCIe device %s at %s", device_name, addr)
                return addr
        return None

    def _remove_pcie_device(addr: str | None) -> None:
        if not addr:
            return
        path = f"/sys/bus/pci/devices/{addr}/remove"
        if not Path(path).exists():
            return
        try:
            subprocess.check_call(["sh", "-c", f"echo 1 > {path}"])
            log.info("Removed PCIe device %s", addr)
        except subprocess.CalledProcessError as exc:
            log.warning("Failed to remove PCIe device %s: %s", addr, exc)

    def _nvme_partitions() -> list[str]:
        names = []
        for entry in os.listdir("/dev"):
            if re.match(r"nvme\d+n\d+p\d+", entry):
                names.append(f"/dev/{entry}")
        return sorted(names)

    def _mount_last_partition(device_addr: str | None) -> tuple[bool, str | None]:
        # Wait for partitions to appear
        for attempt in range(5):
            parts = _nvme_partitions()
            if parts:
                dev_path = parts[-1]
                log.info("Detected NVMe partition %s (attempt %d)", dev_path, attempt + 1)
                _mount(dev_path)
                if dev_path in _mounts:
                    return True, dev_path
                log.debug("Partition %s not mounted yet, retrying", dev_path)
            time.sleep(0.5)
        log.warning("No NVMe partitions found after PCIe rescan")
        return False, None

    def _force_unmount_all_nvme() -> bool:
        any_unmounted = False
        for dev in list(_mounts):
            if dev.startswith("/dev/nvme"):
                if _force_lazy_unmount(dev):
                    any_unmounted = True
                    with _raw_lock:
                        _register_raw_remove(dev)
                        if dev == _active_raw:
                            _active_raw = None
        if any_unmounted:
            _wait_for_raw_unmount()
        return any_unmounted

    def _mount_pcie() -> tuple[bool, str | None, str | None]:
        log.info("=" * 60)
        log.info("MOUNT REQUEST - Starting CFE mount sequence")
        log.info("=" * 60)
        _redis_mech("cfe:mounting", "CFE mount requested")
        time.sleep(0.5)

        driver_path = Path('/sys/devices/platform/axi/1000110000.pcie/driver')
        if driver_path.exists():
            log.info("PCIe driver already bound – rescanning bus")
            subprocess.call(["sh", "-c", "echo 1 > /sys/bus/pci/rescan"])
        else:
            log.info("Binding PCIe driver for CFE Hat")
            _pcie_bind(True)

        time.sleep(0.5)
        addr = _check_for_device("Non-Volatile memory controller")
        if not addr:
            log.warning("No NVMe controller detected after PCIe init")
            _set_led(False)
            _redis_mech("cfe:error", "NVMe controller not detected")
            return False, None, None

        ok, dev_path = _mount_last_partition(addr)
        if not ok:
            _set_led(False)
            _redis_mech("cfe:error", "Failed to mount NVMe partition")
            return False, addr, None

        if _wait_for_raw_mount(timeout=20.0):
            log.info("CFE mount succeeded")
            _set_led(True)
            _redis_mech("cfe:mounted", "CFE card mounted")
            return True, addr, dev_path

        log.warning("CFE mount timed out waiting for /media/RAW")
        _set_led(False)
        _redis_mech("cfe:error", "Timeout waiting for RAW mount")
        return False, addr, dev_path

    def _unmount_pcie(current_addr: str | None, is_yank: bool = False) -> None:
        log.info("=" * 60)
        log.info("UNMOUNT REQUEST - Starting CFE unmount sequence")
        log.info("=" * 60)
        _redis_mech("cfe:unmounting", "CFE unmount requested")

        removed = _force_unmount_all_nvme()
        if not removed and not is_yank:
            log.warning("CFE unmount requested but no NVMe mounts were active")

        if is_yank:
            log.info("Card yanked – performing lazy cleanup")
            subprocess.call(["umount", "-l", str(MOUNT_BASE / "RAW")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        _remove_pcie_device(current_addr)
        _set_led(False)
        _redis_mech("cfe:ejected", "CFE card unmounted")
        log.info("CFE unmount sequence complete")
        _purge_stale_mountpoints()

    def _check_for_yank(mounted_dev: str | None, addr: str | None) -> bool:
        if not mounted_dev:
            return False
        try:
            with open('/proc/partitions', 'r') as fh:
                if os.path.basename(mounted_dev) not in fh.read():
                    log.critical("CFE card removed – device missing from /proc/partitions")
                    _unmount_pcie(addr, is_yank=True)
                    return True
        except Exception as exc:
            log.debug("/proc/partitions check failed: %s", exc)

        try:
            fd = os.open(mounted_dev, os.O_RDONLY | os.O_DIRECT)
            os.close(fd)
        except OSError as exc:
            log.critical("Direct read failed on %s: %s", mounted_dev, exc)
            _unmount_pcie(addr, is_yank=True)
            return True

        mp = _mounts.get(mounted_dev)
        if mp:
            try:
                entries = os.listdir(mp)
                if entries:
                    os.stat(os.path.join(mp, entries[0]))
            except OSError as exc:
                log.critical("Mount point %s inaccessible: %s", mp, exc)
                _unmount_pcie(addr, is_yank=True)
                return True
        return False

    last_insert, last_eject = _read_buttons()
    card_present = (last_insert == 0)
    mounted_flag = False
    current_addr: str | None = None
    mounted_dev: str | None = None

    _redis_mech("cfe:present" if card_present else "cfe:absent",
                "CFE card present on startup" if card_present else "CFE slot empty")

    if card_present:
        log.info("Card detected at startup – attempting automatic mount")
        mounted_flag, current_addr, mounted_dev = _mount_pcie()

    log.info("CFE Hat worker entering monitoring loop")

    while True:
        insert_button, eject_button = _read_buttons()
        card_now_present = (insert_button == 0)

        if card_now_present and not card_present:
            log.info(">>> CARD INSERTION DETECTED <<<")
            _redis_mech("cfe:inserted", "CFE card inserted")
            mounted_flag, current_addr, mounted_dev = _mount_pcie()

        if not card_now_present and card_present:
            if mounted_flag:
                log.critical("!!! CARD YANKED - physical removal detected !!!")
                _unmount_pcie(current_addr, is_yank=True)
            else:
                log.info("CFE slot opened")
            mounted_flag = False
            current_addr = None
            mounted_dev = None
            _redis_mech("cfe:absent", "CFE card removed")

        if last_eject == 1 and eject_button == 0:
            log.info(">>> EJECT BUTTON PRESSED <<<")
            _unmount_pcie(current_addr, is_yank=False)
            mounted_flag = False
            current_addr = None
            mounted_dev = None

        if mounted_flag:
            if _check_for_yank(mounted_dev, current_addr):
                mounted_flag = False
                current_addr = None
                mounted_dev = None

        last_insert, last_eject = insert_button, eject_button
        card_present = card_now_present
        time.sleep(0.1)

# ─────────────────────────────────────────────────────────────────────────────
# Initial scan + auto-mount
# ─────────────────────────────────────────────────────────────────────────────
def _initial_scan():
    _purge_stale_mountpoints()
    log.debug("Initial device scan")

    raws, others = [], []
    for dev in _udev_ctx.list_devices(subsystem="block", DEVTYPE="partition"):
        devnode = dev.device_node
        if not devnode:
            continue
        label, _fst = _get_fs(devnode)
        (raws if label == "RAW" else others).append(devnode)

    # Mount non-RAW first
    for devnode in others:
        _mount(devnode)

    # Then arbitrate one RAW
    if raws:
        # take the latest raw by path sort (heuristic); _switch_to_raw will unmount previous
        devnode = sorted(raws)[-1]
        _register_raw_add(devnode)
        _switch_to_raw(devnode)

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    def _sigterm(_sig, _frm):
        log.info("SIGTERM received, unmounting everything")
        for dev in list(_mounts):
            _unmount(dev)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm)

    _initial_scan()

    threading.Thread(target=_udev_worker,     daemon=True).start()
    threading.Thread(target=_cfe_hat_worker,  daemon=True).start()
    threading.Thread(target=_nvme_watchdog,   daemon=True).start()
    threading.Thread(target=_sanity_watchdog, daemon=True).start()

    log.info("storage-automount started (log level %s)", LOG_LEVEL)
    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
