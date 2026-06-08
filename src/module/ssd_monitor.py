import os
import logging
import threading
import time
import subprocess
import smbus
from pathlib import Path
from typing import Optional, Tuple, List
import datetime
import re
import errno

try:
    from systemd import journal            # python3-systemd package
    _HAVE_JOURNAL = True
except ImportError:
    _HAVE_JOURNAL = False    # fallback will use `journalctl -f`


try:
    import pyudev           # Hot-plug backend (falls back to polling)
    _HAVE_PYUDEV = True
except ImportError:
    _HAVE_PYUDEV = False

# ----------------------------------------------------------------------
# project-local imports
# ----------------------------------------------------------------------
from module.redis_controller import ParameterKey
from module.storage_profiles import (
    DEFAULT_RECORDER_PROFILE,
    NO_STORAGE_FILESYSTEM,
    normalize_filesystem,
    normalize_storage_filesystem,
    recorder_profile_name_for_filesystem,
    supported_filesystem_text,
)

# ----------------------------------------------------------------------
# If your recorder uses a different Redis flag, change it here.
# ----------------------------------------------------------------------
REDIS_KEY_IS_RECORDING = ParameterKey.IS_RECORDING.value     # "1" while cinepi-raw is running
REDIS_KEY_FSCK_STATUS  = "FSCK_STATUS"      # "OK …"  |  "FAIL …"
EXT4_MOUNT_OPTIONS = "rw,noatime,nodiratime,commit=60"
YANK_ERRNOS = {
    errno.EIO,
    errno.ENOENT,
    errno.ENODEV,
    getattr(errno, "ENOTCONN", errno.EIO),
    getattr(errno, "ESTALE", errno.EIO),
}


# ----------------------------------------------------------------------
# Event helper
# ----------------------------------------------------------------------
class Event:
    def __init__(self) -> None:
        self._listeners = []

    def subscribe(self, fn):
        self._listeners.append(fn)

    def emit(self, *args):
        for cb in list(self._listeners):     # shallow copy – safe against rm
            try:
                cb(*args)
            except Exception as exc:
                logging.exception("Mount-event listener failed: %s", exc)


# ----------------------------------------------------------------------
# SSDMonitor
# ----------------------------------------------------------------------
class SSDMonitor:
    """
    Watches `/media/RAW` for mounts, unmounts and free-space changes.

    Supports
        • USB SSDs
        • NVMe (PCIe) adapters
        • Will Whang's CFExpress Hat

    Added features
        • Daily read-only fsck (and once right after mount)
        • Ownership fix-up (chown -R pi:pi) on every mount
    """
    
    # ------------------------------------------------------------------
    # ctor / dtor
    # ------------------------------------------------------------------
    def __init__(self,
                 mount_path: str  = "/media/RAW",
                 redis_controller=None,
                 poll_interval: float = 1.0,
                 space_interval: float = 1.0,
                 space_delta_gb: float = 0.1):
        self._mount_path  = Path(mount_path)
        self._redis       = redis_controller
        self._poll_int    = poll_interval
        self._space_int   = space_interval
        self._space_delta = space_delta_gb

        self._is_mounted  = False
        self._device_name = None        # "sda1" | "nvme0n1p1" | …
        self._device_type = None        # "SSD" | "NVMe" | "CFE" | "Unknown"
        self._filesystem_type = NO_STORAGE_FILESYSTEM
        self._mount_options = ""
        self._recorder_profile = DEFAULT_RECORDER_PROFILE
        self._space_left  = None        # float (GB)
        self._last_space  = 0.0
        self._last_space_ts = 0.0
        self._write_speed   = 0.0       # current write speed in MB/s
        
        self._last_cfe_mount_try = 0.
        self._last_recording_log = {}

        # next fsck schedule (run once right after boot/mount)
        self._next_fsck_ts = time.time()
        self._fsck_lock    = threading.Lock()   # only one fsck at a time

        # events
        self.mount_event   = Event()
        self.unmount_event = Event()
        self.space_event   = Event()

        self._stop_evt = threading.Event()
        self._thread   = threading.Thread(
            target=self._run, daemon=True, name="SSDMonitor"
        )

        # --- watch storage-automount logs -----------------------------------
        # self._jthread = threading.Thread(
        #     target=self._journal_loop, daemon=True, name="SSDJournal"
        # )
        # self._jthread.start()
        # logging.info("SSDMonitor journal listener started.")


        self._cfe_hat_present = self._detect_cfe_hat()
        self._init_redis_defaults()
        self._thread.start()
        logging.info("SSD monitoring thread started.")

    def stop(self) -> None:
        self._stop_evt.set()
        self._thread.join()
        self._jthread.join()
        logging.info("SSD monitoring stopped.")

    # ------------------------------------------------------------------
    # read-only properties
    # ------------------------------------------------------------------
    @property
    def is_mounted(self) -> bool:
        return self._is_mounted

    @property
    def space_left_gb(self) -> Optional[float]:
        return self._space_left

    @property
    def device_type(self) -> Optional[str]:
        return self._device_type

    @property
    def filesystem_type(self) -> str:
        return self._filesystem_type

    @property
    def mount_options(self) -> str:
        return self._mount_options

    @property
    def recorder_profile(self) -> str:
        return self._recorder_profile
    
    @property
    def space_left(self) -> Optional[float]:
        """Alias for legacy external code — returns free space in GB."""
        return self._space_left
    
    @property
    def device_name(self) -> Optional[str]:
        """Returns e.g. 'sda1' or 'nvme0n1p1' (legacy API)."""
        return self._device_name

    @property
    def mount_path(self) -> Path:
        """Return the mount path as a :class:`pathlib.Path`."""
        return self._mount_path

    @property
    def write_speed_mb_s(self) -> float:
        """Current write speed in megabytes per second."""
        return self._write_speed
    # ------------------------------------------------------------------
    # backward-compat shim (old code expects .cfe_hat_present)
    # ------------------------------------------------------------------
    @property
    def cfe_hat_present(self) -> bool:
        """True when a Core-FPG CF-Express Hat is detected."""
        return self._cfe_hat_present


    # ------------------------------------------------------------------
    # convenience: multi-key Redis update that works even without .pipeline()
    # ------------------------------------------------------------------
    def _redis_set_many(self, kv: dict) -> None:
        if not self._redis:
            return
        # Always go through set_value() so the RedisController local cache
        # stays coherent. The pipeline path (pipe.set / pipe.execute) bypasses
        # set_value() and leaves the cache stale, causing _build_args() to read
        # the old "none" value for STORAGE_FILESYSTEM and select the wrong
        # recorder profile at cinepi-raw launch time.
        for k, v in kv.items():
            self._redis.set_value(k, v)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _detect_cfe_hat(self) -> bool:
        """Detect CFE-Hat via I²C (0x34) or PCIe node."""
        try:
            bus = smbus.SMBus(1)
            bus.read_byte(0x34)        # any reply ≠ exception means “present”
            bus.close()
            logging.info("CFE-HAT detected via I²C @0x34")
            return True
        except OSError:
            pass

        # ---- PCIe bridge present? ------------------------------------
        pcie_node = Path("/sys/bus/platform/drivers/brcm-pcie/1000110000.pcie")
        if pcie_node.exists():
            logging.info("CFE HAT detected via platform PCIe node")
            return True

        logging.info("No CFE HAT detected")
        return False


    def _init_redis_defaults(self) -> None:
        if not self._redis:
            return
        self._redis.set_value(ParameterKey.STORAGE_TYPE.value, "none")
        self._redis.set_value(ParameterKey.STORAGE_FILESYSTEM.value, NO_STORAGE_FILESYSTEM)
        self._redis.set_value(ParameterKey.STORAGE_MOUNT_OPTIONS.value, "")
        self._redis.set_value(ParameterKey.STORAGE_RECORDER_PROFILE.value, DEFAULT_RECORDER_PROFILE)
        self._redis.set_value(ParameterKey.IS_MOUNTED.value,   "0")
        self._redis.set_value(ParameterKey.SPACE_LEFT.value,   "0")
        self._redis.set_value(REDIS_KEY_FSCK_STATUS,           "unknown")
        self._redis.set_value(ParameterKey.WRITE_SPEED_TO_DRIVE.value, "0")

 
    # ------------------------------------------------------------------
    # main loop (udev or polling)
    # ------------------------------------------------------------------
    def _run(self) -> None:
        # -------- initial sync (covers drives mounted before startup) ------
        self._check_mount_status()   # detect current state immediately
        self._maybe_run_fsck()       # kick off health-check if needed

        # -------- choose backend ------------------------------------------
        if _HAVE_PYUDEV:
            self._udev_loop()
        else:
            self._poll_loop()
    # ---------- pyudev backend ----------------------------------------
    def _udev_loop(self) -> None:
        """
        Wait for udev events **and** fall back to periodic checks so
        drives that were already mounted before startup are detected.
        """
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem="block")
        monitor.start()                         # non-blocking

        while not self._stop_evt.is_set():
            dev = monitor.poll(self._poll_int)  # returns None on timeout
            # In either case we resync; if an event arrived, dev is not None.
            self._check_mount_status()
            self._maybe_run_fsck()

    # ---------- polling backend ---------------------------------------
    def _poll_loop(self) -> None:
        while not self._stop_evt.wait(self._poll_int):
            self._check_mount_status()
            self._maybe_run_fsck()

    # ------------------------------------------------------------------
    # state changes
    # ------------------------------------------------------------------
    def _check_mount_status(self) -> None:
        mounted_now = os.path.ismount(self._mount_path)

        if mounted_now and not self._is_mounted:
            self._handle_mount()
        elif not mounted_now and self._is_mounted:
            self._handle_unmount()
        elif self._is_mounted:
            self._update_space_left()

    def _handle_mount(self) -> None:
        self._is_mounted  = True
        self._device_name = self._get_device_name()
        self._device_type = self._detect_device_type()
        self._filesystem_type = self._detect_filesystem_type()
        self._mount_options = self._detect_mount_options()
        self._recorder_profile = recorder_profile_name_for_filesystem(
            self._filesystem_type
        )
        self._update_space_left(force=True)
        if not self._is_mounted or self._space_left is None:
            return

        self._redis_set_many({
            ParameterKey.STORAGE_TYPE.value: self._device_type.lower(),
            ParameterKey.STORAGE_FILESYSTEM.value: self._filesystem_type,
            ParameterKey.STORAGE_MOUNT_OPTIONS.value: self._mount_options,
            ParameterKey.STORAGE_RECORDER_PROFILE.value: self._recorder_profile,
            ParameterKey.IS_MOUNTED.value:    "1",
            ParameterKey.SPACE_LEFT.value:    f"{self._space_left:.2f}",
        })
        if self._redis:
            self._redis.set_value(ParameterKey.WRITE_SPEED_TO_DRIVE.value, "0")

        logging.info(
            "RAW drive mounted at %s (%s, %s, opts %s, recorder profile %s)",
            self._mount_path,
            self._device_type,
            self._filesystem_type,
            self._mount_options,
            self._recorder_profile,
        )
        self.mount_event.emit(
            self._mount_path,
            self._device_type,
            self._filesystem_type,
            self._recorder_profile,
        )


        # run fsck once right after mount
        self._next_fsck_ts = 0

    def _handle_unmount(self) -> None:
        # … Redis clean-up stays unchanged …
        self._redis_set_many({
            ParameterKey.STORAGE_TYPE.value: "none",
            ParameterKey.STORAGE_FILESYSTEM.value: NO_STORAGE_FILESYSTEM,
            ParameterKey.STORAGE_MOUNT_OPTIONS.value: "",
            ParameterKey.STORAGE_RECORDER_PROFILE.value: DEFAULT_RECORDER_PROFILE,
            ParameterKey.IS_MOUNTED.value:   "0",
            ParameterKey.SPACE_LEFT.value:   "0",
        })
        if self._redis:
            self._redis.set_value(ParameterKey.WRITE_SPEED_TO_DRIVE.value, "0")
            
        # ─── switch off CFE-Hat LED (if we still have the I²C bus) ───
        if self._device_type == "CFE":
            try:
                bus = smbus.SMBus(1)
                bus.write_byte(0x34, 0x00)     # LED off
                bus.close()                    # <-- explicit close
            except OSError:
                # HAT already gone → ignore
                pass
            except Exception as exc:
                logging.debug("CFE-HAT LED off failed: %s", exc)

        logging.info("RAW drive unmounted from %s", self._mount_path)
        self._is_mounted   = False
        self._space_left   = None
        self._last_space   = 0.0
        self._last_space_ts = 0.0
        self._write_speed  = 0.0
        self._device_name  = None
        self._device_type  = None
        self._filesystem_type = NO_STORAGE_FILESYSTEM
        self._mount_options = ""
        self._recorder_profile = DEFAULT_RECORDER_PROFILE
        self._last_recording_log.clear()
        self.unmount_event.emit(self._mount_path)


    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _get_device_name(self) -> Optional[str]:
        try:
            out = subprocess.check_output(
                ["findmnt", "--noheadings", "--output", "SOURCE",
                 str(self._mount_path)],
                text=True, timeout=1.0).strip()
            return os.path.basename(out)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            logging.warning("findmnt failed for %s", self._mount_path)
            return None

    def _detect_filesystem_type(self) -> str:
        try:
            out = subprocess.check_output(
                ["findmnt", "--noheadings", "--output", "FSTYPE", str(self._mount_path)],
                text=True,
                timeout=1.0,
            ).strip()
            if out:
                return normalize_storage_filesystem(out)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            logging.warning("findmnt fstype failed for %s", self._mount_path)

        if self._device_name:
            out = self._blkid_value(f"/dev/{self._device_name}", "TYPE", fresh=True)
            if out:
                return normalize_storage_filesystem(out)
            logging.warning("blkid fstype failed for /dev/%s", self._device_name)

        return "unknown"

    def _detect_mount_options(self) -> str:
        try:
            return subprocess.check_output(
                ["findmnt", "--noheadings", "--output", "OPTIONS", str(self._mount_path)],
                text=True,
                timeout=1.0,
            ).strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            logging.warning("findmnt mount options failed for %s", self._mount_path)
            return ""

   # ------------------------------------------------------------------
    # device-type classification  (SSD / CFE / NVMe / Unknown)
    # ------------------------------------------------------------------
    def _detect_device_type(self) -> str:
        """
        Robustly classify the mounted /dev node.

        Returns one of  'SSD' | 'CFE' | 'NVMe' | 'Unknown'
        """
        if not self._device_name:                # shouldn’t happen
            return "Unknown"

        # ── derive root block device for sysfs lookup ────────────────
        root = self._device_name                 # e.g. nvme0n1p3
        if root.startswith("nvme"):
            if "p" in root:                      # keep nvme0n1, strip pN
                root = root.rsplit("p", 1)[0]
        else:
            root = root.rstrip("0123456789")
            if root.endswith("p"):
                root = root[:-1]

        uevent_path = Path(f"/sys/block/{root}/device/uevent")
        try:
            txt = uevent_path.read_text().lower()
        except Exception:
            txt = ""                             # path not ready yet

        # real sysfs path (USB shows “…/usb/…”, CFE Hat has “…/1000110000.pcie/…”)
        dev_real = os.path.realpath(f"/sys/block/{root}/device")

        # ───────────────── classification rules ──────────────────────
        if ("/usb/" in dev_real
                or "driver=usb-storage" in txt
                or "driver=uas" in txt):
            return "SSD"

        # CF-Express Hat: PCIe endpoint appears under 1000110000.pcie
        if "1000110000.pcie" in dev_real:
            return "CFE"

        # Generic NVMe controller on PCIe
        if ("driver=nvme"      in txt or
            "pci_driver=nvme"  in txt or
            "nvme"             in txt):
            return "CFE" if self._cfe_hat_present else "NVMe"

        # Rare SATA / AHCI bridges
        if ("driver=ahci" in txt
                or "sata" in txt
                or "class=0x0106" in txt):
            return "SSD"

        # Last-chance heuristic from the name itself
        if self._device_name.startswith("nvme"):
            return "CFE" if self._cfe_hat_present else "NVMe"
        if self._device_name.startswith(("sd", "usb")):
            return "SSD"

        logging.debug("Unclassified block device %s → %s\n%s",
                      root, dev_real, txt.strip())
        return "Unknown"

    # ------------------------------------------------------------------
    # static helper: robust lazy-unmount (used from multiple methods)
    # ------------------------------------------------------------------
    @staticmethod
    def _force_lazy_unmount(path: Path | str, retries: int = 20) -> bool:
        """
        Repeatedly issue “umount -l <path>” until the kernel releases the
        mount-point, or `retries` attempts are exhausted.

        Returns **True** when the directory is no longer a mount-point.
        """
        for _ in range(retries):
            if not os.path.ismount(path):
                return True
            subprocess.call(["sudo", "umount", "-l", str(path)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
            time.sleep(0.2)
        return False

    @staticmethod
    def _blkid_value(dev: str, tag: str, *, fresh: bool = False) -> str:
        """
        Return one blkid tag value.

        The normal blkid path can briefly report cached pre-format metadata.
        Fresh probes first ask blkid to read the device directly and then fall
        back to the cache-backed query used elsewhere.
        """
        commands = []
        if fresh:
            commands.extend([
                ["blkid", "-p", "-s", tag, "-o", "value", dev],
                ["blkid", "-c", "/dev/null", "-s", tag, "-o", "value", dev],
            ])
        commands.append(["blkid", "-s", tag, "-o", "value", dev])

        for cmd in commands:
            try:
                return subprocess.check_output(
                    cmd,
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                ).strip()
            except (
                FileNotFoundError,
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
            ):
                continue
        return ""

    @staticmethod
    def _settle_device_metadata(device: str) -> None:
        """Give the kernel and udev a moment to forget pre-format metadata."""
        for cmd in (
            ["sync"],
            ["udevadm", "settle", "--timeout=5"],
            ["blkid", "-g"],
        ):
            try:
                subprocess.run(
                    cmd,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=6.0,
                )
            except (
                FileNotFoundError,
                subprocess.SubprocessError,
            ) as exc:
                logging.debug("Device metadata settle command failed (%s): %s", cmd, exc)

    @staticmethod
    def _mount_options_for_filesystem(fstype: str) -> str:
        return {
            "ext4":  EXT4_MOUNT_OPTIONS,
            "ntfs":  "uid=1000,gid=1000,dmask=022,fmask=133,rw,noatime",
            "exfat": "uid=1000,gid=1000,dmask=022,fmask=133,rw,noatime",
        }.get(fstype, "rw,noatime")

    def _detect_device_filesystem(self, device: str) -> str:
        fstype = self._blkid_value(device, "TYPE", fresh=True)
        return normalize_storage_filesystem(fstype) if fstype else "unknown"

    def _find_raw_device(self) -> Optional[str]:
        def _blkid_lines():
            try:
                out = subprocess.check_output(
                    ["blkid", "-s", "LABEL", "-o", "device"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                )
                return [ln.strip() for ln in out.splitlines()]
            except (
                FileNotFoundError,
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
            ):
                return []

        candidates = [d for d in _blkid_lines() if Path(d).exists()]
        nvme = [d for d in candidates if "/nvme" in d]
        sdas = [d for d in candidates if "/sd" in d]
        others = [d for d in candidates if d not in nvme + sdas]
        ordered = nvme + sdas + others

        for dev in ordered:
            label = self._blkid_value(dev, "LABEL", fresh=True)
            if label == "RAW":
                return dev
        return None

    def _mount_raw_device(self, raw_dev: str, fstype: str, *, retries: int = 3) -> bool:
        mount_path = self._mount_path
        try:
            mount_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logging.error("mount_drive(): cannot create %s (%s)", mount_path, exc)
            return False

        opts = self._mount_options_for_filesystem(fstype)
        cmd = ["sudo", "mount", "-t", fstype, "-o", opts, raw_dev, str(mount_path)]

        for attempt in range(1, retries + 1):
            res = subprocess.call(cmd)
            if res == 0:
                subprocess.call(["sudo", "chown", "pi:pi", str(mount_path)])
                logging.info("mount_drive(): mounted %s (%s) at %s", raw_dev, fstype, mount_path)
                self._handle_mount()
                return True

            if attempt < retries:
                logging.warning(
                    "mount_drive(): mount attempt %d/%d failed for %s as %s, exit=%d",
                    attempt,
                    retries,
                    raw_dev,
                    fstype,
                    res,
                )
                self._settle_device_metadata(raw_dev)
                time.sleep(0.2)

        logging.error("mount_drive(): mount failed for %s as %s", raw_dev, fstype)
        return False

    def _handle_storage_error(self, exc: OSError, *, action: str) -> bool:
        """
        Convert media-removal filesystem errors into one clean unmount flow.

        Returns True when the error was recognized as lost storage and the
        monitor state was transitioned to "unmounted".
        """
        if exc.errno not in YANK_ERRNOS:
            return False

        # ENOENT on a path inside the volume (e.g. a subdirectory deleted
        # mid-scan during an erase) should not trigger a false unmount when
        # the mount point itself is still intact.
        if exc.errno == errno.ENOENT and os.path.ismount(self._mount_path):
            return False

        logging.warning(
            "RAW drive became unavailable while trying to %s %s: %s",
            action,
            self._mount_path,
            exc,
        )

        if self._is_mounted:
            self._force_lazy_unmount(self._mount_path)
            self._handle_unmount()

        return True

    # ---------- free-space tracking -----------------------------------
    def _update_space_left(self, *, force: bool = False) -> None:
        """
        Refresh the cached free-space value and emit GUI / Redis updates.

        If `statvfs` fails with EIO (card yanked) or ENOENT (mount-point
        disappeared) we trigger a forced lazy-unmount and clean up our
        internal state.
        """
        now = time.time()
        if not force and (now - self._last_space_ts) < self._space_int:
            return

        try:
            st = os.statvfs(self._mount_path)
            gb = (st.f_bavail * st.f_frsize) / (1024 ** 3)

            if self._last_space_ts > 0:
                delta_gb = self._last_space - gb
                delta_t = now - self._last_space_ts
                if delta_t > 0 and delta_gb > 0:
                    self._write_speed = delta_gb * 1024 / delta_t
                else:
                    self._write_speed = 0.0
            else:
                self._write_speed = 0.0

            if self._redis:
                self._redis.set_value(
                    ParameterKey.WRITE_SPEED_TO_DRIVE.value,
                    f"{self._write_speed:.2f}")

            prev_left = self._space_left if self._space_left is not None else self._last_space

        except OSError as exc:
            logging.error("statvfs failed: %s", exc)
            if self._handle_storage_error(exc, action="check free space on"):
                return
            return

        # Always advance the baseline so write-speed and throttle stay accurate.
        self._last_space    = gb
        self._last_space_ts = now

        # Emit Redis / UI update when space changes significantly or when forced.
        if force or abs(gb - prev_left) >= self._space_delta:
            self._space_left = gb
            logging.info("Free space: %.2f GB", gb)
            if self._redis:
                self._redis.set_value(ParameterKey.SPACE_LEFT.value,
                                      f"{gb:.2f}")
            self.space_event.emit(gb)


    # ---------- fsck (read-only) --------------------------------------
    def _maybe_run_fsck(self) -> None:
        if (not self._is_mounted) or (time.time() < self._next_fsck_ts):
            return
        # avoid running during a take
        if self._redis and self._redis.get_value(REDIS_KEY_IS_RECORDING) == "1":
            return
        if not self._fsck_lock.acquire(blocking=False):
            return  # already running

        fstype = self._filesystem_type

        def _worker(devnode: str, fstype: str):
            try:
                # NTFS has no read-only check tool on Linux (ntfsfix is
                # repair-only); skip the check and report OK so the UI does
                # not show a spurious FAIL for every NTFS drive.
                if fstype == "ntfs":
                    msg = f"OK {datetime.datetime.now().isoformat()} | ntfs: fsck skipped (no read-only checker on Linux)"
                    logging.info("fsck result: %s", msg)
                    if self._redis:
                        self._redis.set_value(REDIS_KEY_FSCK_STATUS, msg)
                    return

                cmd = ["sudo", "nice", "-n", "19", "ionice", "-c3",
                    "fsck", "-n", devnode]

                proc = subprocess.run(cmd, capture_output=True, text=True)
                tail = (proc.stdout or proc.stderr).strip().splitlines()[-1]
                status = "OK" if proc.returncode == 0 else "FAIL"
                msg = f"{status} {datetime.datetime.now().isoformat()} | {tail}"
                logging.info("fsck result: %s", msg)
                if self._redis:
                    self._redis.set_value(REDIS_KEY_FSCK_STATUS, msg)
            except Exception as exc:
                logging.warning("fsck worker failed: %s", exc)
            finally:
                self._next_fsck_ts = time.time() + 24*3600   # 24 h
                self._fsck_lock.release()

        threading.Thread(
            target=_worker,
            args=(f"/dev/{self._device_name}", fstype),
            name="fsck",
            daemon=True
        ).start()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
                     # still not mounted
    def toggle_mount_drive(self) -> None:  
        """
        Single-toggle helper for a push-button or CLI call:
            – If /media/RAW is mounted → unmount.
            – Otherwise               → mount the first RAW partition.
        """
        if self._is_mounted:
            logging.info("toggle_mount(): RAW is mounted — unmounting")
            self.unmount_drive()
        else:
            logging.info("toggle_mount(): RAW not mounted — trying to mount")
            if not self.mount_drive():
                logging.warning("toggle_mount(): mount attempt failed")

    def refresh(self) -> bool:
        """Synchronously refresh mount, filesystem and free-space state."""
        self._check_mount_status()
        return self._is_mounted

    def unmount_drive(self) -> None:
        if not self._is_mounted:
            return

        # Try a clean unmount first; if the mount-point is busy (EBUSY = exit 32)
        # fall back to lazy unmount so the kernel detaches it once all file
        # handles are released. This handles the case where cinepi-raw or ffmpeg
        # still has a file open on the drive at the moment of the request.
        try:
            subprocess.run(["sudo", "umount", str(self._mount_path)], check=True)
        except subprocess.CalledProcessError as exc:
            logging.warning(
                "umount failed (%s), retrying with lazy unmount", exc
            )
            if not self._force_lazy_unmount(self._mount_path):
                logging.error(
                    "Failed to unmount %s even with lazy unmount", self._mount_path
                )
                return
        
    def mount_drive(self, filesystem: Optional[str] = None, device: Optional[str] = None) -> bool:
        """
        Mount the first partition whose LABEL is 'RAW'.
        Returns True if the mount succeeds or if it is already mounted.
        """
        if self._is_mounted:
            logging.info("mount_drive(): already mounted")
            return True

        fs_hint = normalize_filesystem(filesystem) if filesystem else None
        raw_dev = device or self._find_raw_device()

        if not raw_dev:
            logging.warning("mount_drive(): no partition labelled RAW found")
            return False

        probed_fstype = self._detect_device_filesystem(raw_dev)
        fstype = fs_hint or probed_fstype
        if not fstype or fstype == "unknown":
            logging.error("mount_drive(): unable to detect filesystem for %s", raw_dev)
            return False

        if fs_hint and probed_fstype and probed_fstype != "unknown" and probed_fstype != fs_hint:
            logging.warning(
                "mount_drive(): blkid reports %s for %s after requested %s; using requested filesystem",
                probed_fstype,
                raw_dev,
                fs_hint,
            )

        return self._mount_raw_device(raw_dev, fstype)

    def erase_drive(self) -> bool:
        """Erase all files from the mounted RAW volume."""
        if not self._is_mounted:
            logging.error("erase_drive(): RAW drive is not mounted")
            return False

        if self._redis and self._redis.get_value(REDIS_KEY_IS_RECORDING) == "1":
            logging.error("erase_drive(): cannot erase while recording is active")
            return False

        try:
            items = list(self._mount_path.iterdir())
        except OSError as exc:
            logging.error("erase_drive(): cannot list %s: %s", self._mount_path, exc)
            return False

        errors = []

        def _rm(path: Path) -> None:
            result = subprocess.run(
                ["sudo", "rm", "-rf", str(path)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                errors.append(result.stderr.strip() or str(path))

        threads = [threading.Thread(target=_rm, args=(p,), daemon=True) for p in items]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if errors:
            logging.error("erase_drive(): errors: %s", "; ".join(errors))
            self._update_space_left(force=True)
            return False

        subprocess.call(["sync"])
        logging.info("erase_drive(): removed all files from %s", self._mount_path)
        self._update_space_left(force=True)
        return True

    def format_drive(self, filesystem: Optional[str] = None) -> bool:
        """Format the RAW drive with the requested filesystem."""
        if not self._is_mounted:
            logging.error("format_drive(): RAW drive is not mounted")
            return False

        fs = normalize_filesystem(filesystem or "exfat")

        if fs not in {"ext4", "exfat", "ntfs"}:
            logging.error(
                "format_drive(): unsupported filesystem '%s' (expected %s)",
                filesystem,
                supported_filesystem_text(),
            )
            return False

        dev_name = self._device_name or self._get_device_name()
        if not dev_name:
            logging.error("format_drive(): unable to determine device node")
            return False

        device = f"/dev/{dev_name}"

        # Unmount robustly: clean first, lazy fallback on EBUSY, then kill
        # processes holding the device as a last resort so mkfs never hits
        # "Device or resource busy".
        clean_unmount = False
        try:
            subprocess.run(["sudo", "umount", str(self._mount_path)], check=True)
            clean_unmount = True
        except subprocess.CalledProcessError:
            logging.warning(
                "format_drive(): umount busy, trying lazy unmount of %s", self._mount_path
            )
            clean_unmount = self._force_lazy_unmount(self._mount_path)

        if not clean_unmount:
            # Last resort: fuser -km evicts all processes holding the device,
            # then attempt one final lazy unmount.
            logging.warning(
                "format_drive(): lazy unmount failed, evicting processes from %s", device
            )
            subprocess.call(
                ["sudo", "fuser", "-km", device],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            if not self._force_lazy_unmount(self._mount_path):
                logging.error(
                    "format_drive(): could not unmount %s after eviction; aborting format",
                    self._mount_path,
                )
                return False

        # Brief settle so the kernel releases all block-layer references before
        # mkfs opens the device.
        time.sleep(0.5)

        # refresh monitor state after unmount
        self._check_mount_status()

        # If the partition is significantly smaller than its parent disk
        # (e.g. only 190 MB on a 500 GB drive because a previous external
        # format left a tiny partition), repartition first so mkfs uses the
        # full available capacity.
        root = dev_name
        if root.startswith("nvme"):
            if "p" in root:
                root = root.rsplit("p", 1)[0]
        else:
            root = root.rstrip("0123456789")
            if root.endswith("p"):
                root = root[:-1]
        disk_dev = f"/dev/{root}"
        if disk_dev != device:
            try:
                part_bytes = int(subprocess.check_output(
                    ["sudo", "blockdev", "--getsize64", device],
                    text=True, timeout=5).strip())
                disk_bytes = int(subprocess.check_output(
                    ["sudo", "blockdev", "--getsize64", disk_dev],
                    text=True, timeout=5).strip())
                fill_ratio = part_bytes / disk_bytes if disk_bytes else 1.0
            except Exception as exc:
                logging.warning("format_drive(): could not compare partition/disk sizes (%s)", exc)
                fill_ratio = 1.0
            if fill_ratio < 0.9:
                logging.info(
                    "format_drive(): %s uses only %.1f%% of %s (%.2f GB / %.2f GB) — repartitioning",
                    device, fill_ratio * 100, disk_dev,
                    part_bytes / 1e9, disk_bytes / 1e9,
                )
                try:
                    subprocess.run(
                        ["sudo", "parted", "-s", disk_dev, "mklabel", "gpt"],
                        check=True, timeout=30)
                    subprocess.run(
                        ["sudo", "parted", "-s", disk_dev, "mkpart", "RAW", "0%", "100%"],
                        check=True, timeout=30)
                    # Set Microsoft Basic Data GUID so macOS auto-mounts the partition.
                    subprocess.run(
                        ["sudo", "parted", "-s", disk_dev, "set", "1", "msftdata", "on"],
                        check=False, timeout=10,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    subprocess.run(
                        ["sudo", "partprobe", disk_dev],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                    time.sleep(1.5)
                    logging.info(
                        "format_drive(): repartitioned %s; %s now covers full disk",
                        disk_dev, device)
                except subprocess.CalledProcessError as exc:
                    logging.error(
                        "format_drive(): repartition failed for %s (%s) — proceeding with mkfs on existing partition",
                        disk_dev, exc)

        if fs == "ext4":
            mkfs_cmd = ["sudo", "mkfs.ext4", "-F", "-L", "RAW", device]
        elif fs == "exfat":
            # Do not pass -c (cluster size): the default chosen by mkfs.exfat
            # (~256 KB for large drives) is compatible with macOS and Windows.
            # Forcing 1 MB clusters was tried for write-latency but breaks
            # the macOS exFAT driver on most versions.
            mkfs_cmd = ["sudo", "mkfs.exfat", "-L", "RAW", device]
        else:
            mkfs_cmd = ["sudo", "mkfs.ntfs", "-F", "-L", "RAW", device]

        try:
            subprocess.run(mkfs_cmd, check=True)
        except subprocess.CalledProcessError as exc:
            logging.error("format_drive(): mkfs failed for %s (%s)", device, exc)
            return False

        logging.info("format_drive(): formatted %s as %s", device, fs)
        self._settle_device_metadata(device)

        if not self.mount_drive(filesystem=fs, device=device):
            logging.error("format_drive(): failed to remount RAW after formatting")
            return False

        return True


    # ------------------------------------------------------------------
    # recording-finder helpers (unchanged)
    # ------------------------------------------------------------------
    def get_latest_recording_infos(self, window_seconds: int = 1
                                   ) -> List[Tuple[str, int, int]]:
        if not self._is_mounted:
            logging.debug("RAW drive not mounted — skipping folder scan.")
            return []
        try:
            subdirs = [p for p in self._mount_path.iterdir() if p.is_dir()]
        except OSError as exc:
            if not self._handle_storage_error(exc, action="scan"):
                logging.warning("Unable to scan %s: %s", self._mount_path, exc)
            return []
        if not subdirs:
            return []
        try:
            stamped_subdirs = [(p, p.stat().st_mtime) for p in subdirs]
        except OSError as exc:
            if not self._handle_storage_error(exc, action="inspect recordings on"):
                logging.warning("Unable to inspect recordings on %s: %s", self._mount_path, exc)
            return []
        latest_ts = max(mtime for _, mtime in stamped_subdirs)
        cutoff = latest_ts - window_seconds
        candidates = [(p, mtime) for p, mtime in stamped_subdirs if mtime >= cutoff]
        candidates.sort(key=lambda item: item[1])
        preroll_active = False
        if self._redis:
            try:
                raw_value = self._redis.get_value(ParameterKey.STORAGE_PREROLL_ACTIVE.value)
                text = str(raw_value or "0").strip().lower()
                preroll_active = text in ("1", "true", "yes", "on")
                if not preroll_active:
                    preroll_active = bool(int(text))
            except (TypeError, ValueError, AttributeError):
                preroll_active = False
        infos = []
        for d, _mtime in candidates:
            dng = wav = 0
            max_frame_idx = -1
            try:
                for f in d.rglob("*"):
                    if not f.is_file():
                        continue
                    suf = f.suffix.lower()
                    if suf == ".dng":
                        dng += 1
                        stem = f.stem
                        underscore = stem.rfind("_")
                        if underscore >= 0:
                            try:
                                idx = int(stem[underscore + 1:])
                                if idx > max_frame_idx:
                                    max_frame_idx = idx
                            except ValueError:
                                pass
                    elif suf == ".wav":
                        wav += 1
            except OSError as exc:
                if not self._handle_storage_error(exc, action="count files on"):
                    logging.warning("Unable to count files on %s: %s", d, exc)
                return []
            last_logged = self._last_recording_log.get(d.name)
            if not preroll_active and last_logged != (dng, wav):
                logging.info("Latest recording “%s”: %d DNG | %d WAV",
                             d.name, dng, wav)
                self._last_recording_log[d.name] = (dng, wav)
            infos.append((str(d), dng, wav, max_frame_idx))
        return infos

    def get_latest_recording_info(self) -> Tuple[Optional[str], int, int, int]:
        multi = self.get_latest_recording_infos()
        return multi[-1] if multi else (None, 0, 0, -1)

    # ------------------------------------------------------------------
    # legacy helpers still referenced by cinepi_controller
    # ------------------------------------------------------------------
    def get_space_left(self) -> Optional[float]:
        """Old API – returns the last cached free-space value in GB."""
        return self._space_left

    def get_mount_status(self) -> bool:   # just in case other code uses it
        """Old API – true if /media/RAW is currently mounted."""
        return self._is_mounted

    # ---------- journal subscriber --------------------------------------
    def _journal_loop(self) -> None:
        """
        Listen to storage-automount.service log lines and translate them
        into SSDMonitor events.  Works with python-systemd if available,
        otherwise falls back to running `journalctl -fu`.
        """
        def _process_line(line: str) -> None:
            """
            Parse one message coming from the `storage-automount.service`
            and update our state – while forwarding every message verbatim.
            """
            msg = line.strip()

            # ── state-changing lines we care about ───────────────────────────
            if   "Mounted /dev"             in msg and "OK" in msg:
                self._handle_mount()

            elif "Unmounted /dev"           in msg:
                self._handle_unmount()

            elif "Insert: mount succeeded"  in msg:
                self._handle_mount()

            elif "Eject: unmount succeeded" in msg:
                self._handle_unmount()

            elif "NVMe controller" in msg and "state=dead" in msg:
                # service already tried to lazy-unmount – reflect that instantly
                self._handle_unmount()

            # ── forward *every* message so it appears in the SSDMonitor log ──
            #    (makes debugging easier – you see everything in one place)
            level = "INFO"                  # sensible default
            m = re.search(r"\] (\w+):", msg)  # ] DEBUG:, ] WARNING:, …
            if m:
                level = m.group(1).upper()

            if level == "DEBUG":
                logging.info("%s", msg)
            elif level == "INFO":
                logging.info ("%s", msg)
            elif level == "WARNING":
                logging.warning("%s", msg)
            else:                            # ERROR, CRITICAL, …
                logging.error("%s", msg)

            # small optimisation: keep our cached state in sync right now
            self._check_mount_status()


        if _HAVE_JOURNAL:
            j = journal.Reader()
            j.add_match(_SYSTEMD_UNIT="storage-automount.service")
            j.seek_tail()
            j.get_previous()                  # position at last entry
            j.seek_tail()
            while not self._stop_evt.is_set():
                if j.wait(1000) == journal.APPEND:
                    for entry in j:
                        _process_line(entry["MESSAGE"])
        else:
            # Portable fallback using journalctl -fu …
            cmd = ["journalctl", "-fu", "storage-automount", "-n", "0", "-o", "cat"]
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as proc:
                while not self._stop_evt.is_set():
                    line = proc.stdout.readline()
                    if not line:              # EOF (service stopped)
                        time.sleep(0.5)
                        continue
                    _process_line(line)
