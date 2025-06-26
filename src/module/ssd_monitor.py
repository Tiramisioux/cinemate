import os
import logging
import threading
import time
import subprocess
import smbus
from pathlib import Path
from typing import Optional, Tuple, List
import datetime

try:
    import pyudev           # Hot-plug backend (falls back to polling)
    _HAVE_PYUDEV = True
except ImportError:
    _HAVE_PYUDEV = False

# ----------------------------------------------------------------------
# project-local imports
# ----------------------------------------------------------------------
from module.redis_controller import ParameterKey

# ----------------------------------------------------------------------
# If your recorder uses a different Redis flag, change it here.
# ----------------------------------------------------------------------
REDIS_KEY_IS_RECORDING = "IS_RECORDING"     # "1" while cinepi-raw is running
REDIS_KEY_FSCK_STATUS  = "FSCK_STATUS"      # "OK …"  |  "FAIL …"

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
        • Core-FPG CFExpress Hat

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
                 space_interval: float = 5.0,
                 space_delta_gb: float = 0.1):
        self._mount_path  = Path(mount_path)
        self._redis       = redis_controller
        self._poll_int    = poll_interval
        self._space_int   = space_interval
        self._space_delta = space_delta_gb

        self._is_mounted  = False
        self._suppress_auto_mount = False 
        self._device_name = None        # "sda1" | "nvme0n1p1" | …
        self._device_type = None        # "SSD" | "NVMe" | "CFE" | "Unknown"
        self._space_left  = None        # float (GB)
        self._last_space  = 0.0
        self._last_space_ts = 0.0
        
        self._last_cfe_mount_try = 0.

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

        self._cfe_hat_present = self._detect_cfe_hat()
        self._init_redis_defaults()
        self._thread.start()
        logging.info("SSD monitoring thread started.")

    def stop(self) -> None:
        self._stop_evt.set()
        self._thread.join()
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
    def space_left(self) -> Optional[float]:
        """Alias for legacy external code — returns free space in GB."""
        return self._space_left
    
    @property
    def device_name(self) -> Optional[str]:
        """Returns e.g. 'sda1' or 'nvme0n1p1' (legacy API)."""
        return self._device_name
    
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
        if hasattr(self._redis, "pipeline"):
            pipe = self._redis.pipeline()
            for k, v in kv.items():
                pipe.set(k, v)
            pipe.execute()
        else:
            for k, v in kv.items():
                self._redis.set_value(k, v)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _detect_cfe_hat(self) -> bool:
        """Detect CFE Hat either via I²C (addr 0x34) or PCIe node."""
        # ---- I²C probe ------------------------------------------------
        try:
            with smbus.SMBus(1) as bus:
                _ = bus.read_byte(0x34)       # any value is fine (often 0x69)
            logging.info("CFE HAT detected via I²C @0x34")
            return True
        except Exception:
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
        self._redis.set_value(ParameterKey.IS_MOUNTED.value,   "0")
        self._redis.set_value(ParameterKey.SPACE_LEFT.value,   "0")
        self._redis.set_value(REDIS_KEY_FSCK_STATUS,           "unknown")

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
            self._maybe_auto_mount_cfe()

    # ---------- polling backend ---------------------------------------
    def _poll_loop(self) -> None:
        while not self._stop_evt.wait(self._poll_int):
            self._check_mount_status()
            self._maybe_run_fsck()
            self._maybe_auto_mount_cfe()

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
        self._update_space_left(force=True)

        self._redis_set_many({
            ParameterKey.STORAGE_TYPE.value: self._device_type.lower(),
            ParameterKey.IS_MOUNTED.value:    "1",
            ParameterKey.SPACE_LEFT.value:    f"{self._space_left:.2f}",
        })

        # If the NVMe device is still present, the user probably did a
        # plain "umount /media/RAW".  Suppress auto-mount until the
        # device disappears (i.e. they eject the card).
        if any(p.startswith("nvme") for p in os.listdir("/dev")):
            self._suppress_auto_mount = True        # ← NEW

        logging.info("RAW drive mounted at %s (%s)",
                     self._mount_path, self._device_type)
        self.mount_event.emit(self._mount_path, self._device_type)

        # kick off chown (detached)
        try:
            subprocess.Popen(
                ["sudo", "nice", "-n", "19", "chown", "-R", "pi:pi",
                str(self._mount_path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            logging.info("Started chown -R pi:pi on %s", self._mount_path)
        except Exception as exc:
            logging.warning("Unable to launch chown: %s", exc)


        # run fsck once right after mount
        self._next_fsck_ts = 0

    def _handle_unmount(self) -> None:
        self._redis_set_many({
            ParameterKey.STORAGE_TYPE.value: "none",
            ParameterKey.IS_MOUNTED.value:   "0",
            ParameterKey.SPACE_LEFT.value:   "0",
        })


        logging.info("RAW drive unmounted from %s", self._mount_path)
        self._is_mounted = False
        self._space_left = None
        self._device_name = None
        self._device_type = None
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

    # ------------------------------------------------------------------
    # device-type classification
    # ------------------------------------------------------------------
    def _detect_device_type(self) -> str:
        """
        Return one of  'SSD' | 'CFE' | 'NVMe' | 'Unknown'

        Robust against:
            • USB bridges that omit uevent fields
            • NVMe devices whose uevent is still empty right after hot-plug
            • Root-device parsing (nvme0n1p3  vs  sda2  vs  mmcblk1p1)
        """
        if not self._device_name:                     # shouldn’t happen
            return "Unknown"

        # ── derive root block device for sysfs lookup ─────────────────
        root = self._device_name                      # e.g. nvme0n1p3

        if root.startswith("nvme"):
            # keep nvme0n1, strip only trailing 'p\d+'
            if "p" in root:
                root = root.rsplit("p", 1)[0]
        else:
            # sda3 → sda   |  mmcblk1p2 → mmcblk1
            root = root.rstrip("0123456789")
            if root.endswith("p"):
                root = root[:-1]

        # ── read uevent (may be empty <1 s after plug-in) ─────────────
        uevent_path = Path(f"/sys/block/{root}/device/uevent")
        try:
            txt = uevent_path.read_text().lower()
        except Exception:
            txt = ""                                   # path not ready yet

        # ── helper: real sysfs path (USB bridges show /usb/…) ─────────
        dev_real = os.path.realpath(f"/sys/block/{root}/device")

        # ── USB mass-storage of any flavour ───────────────────────────
        if ("driver=usb-storage" in txt
                or "driver=uas" in txt
                or "/usb/" in dev_real):
            return "SSD"

        # ── NVMe & CF-Express (driver string sometimes missing) ───────
        if ("driver=nvme" in txt
                or "pci_driver=nvme" in txt
                or "nvme" in txt):                 # fall-back keyword
            return "CFE" if self._cfe_hat_present else "NVMe"

        # ── SATA / AHCI on PCIe bridges (rare on Pi) ──────────────────
        if ("driver=ahci" in txt
                or "sata" in txt
                or "class=0x0106" in txt):
            return "SSD"

        # ── last-chance: decide from the device name itself ───────────
        if self._device_name.startswith("nvme"):
            return "CFE" if self._cfe_hat_present else "NVMe"
        if self._device_name.startswith(("sd", "usb")):
            return "SSD"

        # ── still unknown: log once for diagnostics  ──────────────────
        logging.debug("Unclassified block device %s → %s\n%s",
                      root, dev_real, txt.strip())
        return "Unknown"

    # ---------- free-space tracking -----------------------------------
    def _update_space_left(self, *, force=False) -> None:
        now = time.time()
        if not force and (now - self._last_space_ts) < self._space_int:
            return
        try:
            st = os.statvfs(self._mount_path)
            gb = (st.f_bavail * st.f_frsize) / (1024**3)
        except OSError as exc:
            logging.error("statvfs failed: %s", exc)
            return
        if force or abs(gb - self._last_space) >= self._space_delta:
            self._space_left   = gb
            self._last_space   = gb
            self._last_space_ts = now
            logging.info("Free space: %.2f GB", gb)
            if self._redis:
                self._redis.set_value(ParameterKey.SPACE_LEFT.value, f"{gb:.2f}")
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

        def _worker(devnode: str):
            try:
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
            args=(f"/dev/{self._device_name}",),
            name="fsck",
            daemon=True
        ).start()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def mount_cfe(self, retries: int = 3, wait: float = 2.0) -> bool:
            """
            Trigger `cfe-hat-automount mount`.

            Returns True **only if /media/RAW is actually mounted** within
            `wait` seconds (default 2 s).  Otherwise returns False so the
            auto-mount loop will retry later.
            """
            if not self._cfe_hat_present:
                return False

            for attempt in range(retries):
                try:
                    subprocess.run(
                        ["sudo", "cfe-hat-automount", "mount"],
                        check=True, capture_output=True, text=True
                    )
                except subprocess.CalledProcessError as exc:
                    logging.debug("CFE mount helper failed: %s", exc.stderr)
                    continue  # try again (up to *retries*)

                # helper exited OK → give the kernel a moment to create /dev/*
                t_end = time.time() + wait
                while time.time() < t_end:
                    if os.path.ismount(self._mount_path):
                        return True          # SUCCESS: card is mounted
                    time.sleep(0.1)

            return False                      # still not mounted
    
    def _maybe_auto_mount_cfe(self) -> None:
        """
        Auto-mount the CF-Express card when appropriate.

        ▸ Preconditions
            • Hat detected
            • /media/RAW not currently mounted
            • auto-mount not suppressed by a manual umount

        ▸ Suppression
            • When the user manually umounts the card while the NVMe
              device is still present, _handle_unmount() sets
              self._suppress_auto_mount = True.
            • Suppression is lifted automatically once the NVMe device
              node disappears (card removed or controller unbound).
        """
        # lift suppression if the only remaining block nodes are loop/mmcblk
        if self._suppress_auto_mount:
            live_disks = [p for p in os.listdir('/dev') if p[:2] in ('sd', 'nv', 'hd')]
            if not live_disks:                      # all real disks gone
                self._suppress_auto_mount = False
                logging.debug("Suppression cleared (all disks removed)")


        # ── lift suppression when the card has really gone ────────────
        if self._suppress_auto_mount and not any(
                p.startswith("nvme") for p in os.listdir("/dev")):
            self._suppress_auto_mount = False
            logging.debug("Auto-mount suppression cleared (card removed)")

        # ── exit early if we must not / need not mount ────────────────
        if self._suppress_auto_mount or not self._cfe_hat_present or self._is_mounted:
            return

        # ── back-off: max one attempt every 5 s ───────────────────────
        now = time.time()
        if now - self._last_cfe_mount_try < 5:
            return
        self._last_cfe_mount_try = now

        # ── try the helper once ───────────────────────────────────────
        if not self.mount_cfe(retries=1):
            logging.debug("Auto-mount attempt failed; will retry")
            return

        logging.info("Auto-mounted CF-Express card via helper")

        # ── commit the mount immediately (no polling delay) ───────────
        self._device_name = self._get_device_name()
        if not self._device_name:           # kernel still busy? → one retry
            time.sleep(0.2)
            self._device_name = self._get_device_name()

        if self._device_name and not self._is_mounted:
            self._handle_mount()



    def unmount_drive(self) -> None:
        if not self._is_mounted:
            return
        self._suppress_auto_mount = True          # <- NEW
        cmd = ["sudo", "umount", str(self._mount_path)]
        if self._device_type == "CFE":
            cmd = ["sudo", "cfe-hat-automount", "unmount"]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            logging.error("Failed to unmount: %s", exc)
            self._suppress_auto_mount = False     # rollback on error
            return
        self._handle_unmount()

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
            logging.warning("Unable to scan %s: %s", self._mount_path, exc)
            return []
        if not subdirs:
            return []
        latest_ts = max(p.stat().st_mtime for p in subdirs)
        cutoff = latest_ts - window_seconds
        candidates = [p for p in subdirs if p.stat().st_mtime >= cutoff]
        candidates.sort(key=lambda p: p.stat().st_mtime)
        infos = []
        for d in candidates:
            dng = wav = 0
            for f in d.rglob("*"):
                if not f.is_file():
                    continue
                suf = f.suffix.lower()
                if suf == ".dng":
                    dng += 1
                elif suf == ".wav":
                    wav += 1
            logging.info("Latest recording “%s”: %d DNG | %d WAV",
                         d.name, dng, wav)
            infos.append((d.name, dng, wav))
        return infos

    def get_latest_recording_info(self) -> Tuple[Optional[str], int, int]:
        multi = self.get_latest_recording_infos()
        return multi[-1] if multi else (None, 0, 0)

    # ------------------------------------------------------------------
    # legacy helpers still referenced by cinepi_controller
    # ------------------------------------------------------------------
    def get_space_left(self) -> Optional[float]:
        """Old API – returns the last cached free-space value in GB."""
        return self._space_left

    def get_mount_status(self) -> bool:   # just in case other code uses it
        """Old API – true if /media/RAW is currently mounted."""
        return self._is_mounted
