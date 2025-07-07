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

        # --- watch storage-automount logs -----------------------------------
        self._jthread = threading.Thread(
            target=self._journal_loop, daemon=True, name="SSDJournal"
        )
        self._jthread.start()
        logging.info("SSDMonitor journal listener started.")


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
        """Detect CFE-Hat via I²C (0x34) or PCIe node."""
        try:
            bus = smbus.SMBus(1)
            bus.read_byte(0x34)        # any reply ≠ exception means “present”
            bus.close()
            logging.info("CFE-HAT detected via I²C @0x34")
            self.mount_drive()
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
        # detect and capture a safe device-type string
        detected = self._detect_device_type()
        self._device_type = detected if detected is not None else "Unknown"

        # update free-space (may transiently call unmount handlers, but we already captured `detected`)
        self._update_space_left(force=True)

        # always lower-case a non-None string (fallback to "unknown" if needed)
        dev_type_str = (self._device_type or "Unknown").lower()
        free_gb     = f"{(self._space_left or 0.0):.2f}"

        self._redis_set_many({
            ParameterKey.STORAGE_TYPE.value: dev_type_str,
            ParameterKey.IS_MOUNTED.value:   "1",
            ParameterKey.SPACE_LEFT.value:   free_gb,
        })

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
        # … Redis clean-up stays unchanged …
        self._redis_set_many({
            ParameterKey.STORAGE_TYPE.value: "none",
            ParameterKey.IS_MOUNTED.value:   "0",
            ParameterKey.SPACE_LEFT.value:   "0",
        })

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
        self._device_name  = None
        self._device_type  = None
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

        except OSError as exc:
            logging.error("statvfs failed: %s", exc)

            if exc.errno in (errno.EIO, errno.ENOENT):
                # EIO = I/O error (card yanked)
                # ENOENT = path vanished while we were looking
                logging.warning("Lost storage – forcing lazy unmount")
                self._force_lazy_unmount(self._mount_path)
                self._handle_unmount()            # update state & GUI
            return

        # ── normal path: update cached value & emit event ────────────
        if force or abs(gb - self._last_space) >= self._space_delta:
            self._space_left    = gb
            self._last_space    = gb
            self._last_space_ts = now
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

    def unmount_drive(self) -> None:
        if not self._is_mounted:
            return

        cmd = ["sudo", "umount", str(self._mount_path)]

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            logging.error("Failed to unmount: %s", exc)
            return
        
    def mount_drive(self) -> bool:
        """
        Mount the first partition whose LABEL is 'RAW'.
        Returns True if the mount succeeds or if it is already mounted.
        """
        if self._is_mounted:
            logging.info("mount_drive(): already mounted")
            return True

        # 1 — build a list of candidate device nodes, prioritised
        def _blkid_lines():
            try:
                out = subprocess.check_output(["blkid", "-s", "LABEL", "-o", "device"], text=True)
                return [ln.strip() for ln in out.splitlines()]
            except subprocess.CalledProcessError:
                return []

        candidates = [d for d in _blkid_lines() if Path(d).exists()]
        nvme = [d for d in candidates if "/nvme" in d]
        sdas = [d for d in candidates if "/sd" in d]
        others = [d for d in candidates if d not in nvme + sdas]
        ordered = nvme + sdas + others

        raw_dev = None
        for dev in ordered:
            try:
                label = subprocess.check_output(["blkid", "-s", "LABEL", "-o", "value", dev], text=True).strip()
                if label == "RAW":
                    raw_dev = dev
                    break
            except subprocess.CalledProcessError:
                continue

        if not raw_dev:
            logging.warning("mount_drive(): no partition labelled RAW found")
            return False

        # 2 — discover filesystem type
        try:
            fstype = subprocess.check_output(["blkid", "-s", "TYPE", "-o", "value", raw_dev], text=True).strip()
        except subprocess.CalledProcessError:
            logging.error("mount_drive(): blkid failed for %s", raw_dev)
            return False

        # 3 — create mountpoint and mount
        mount_path = self._mount_path
        try:
            mount_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logging.error("mount_drive(): cannot create %s (%s)", mount_path, exc)
            return False

        opts = {
            "ext4":  "rw,noatime",
            "ntfs":  f"uid=1000,gid=1000,rw,noatime,umask=000",
            "exfat": f"uid=1000,gid=1000,rw,noatime",
        }.get(fstype, "rw,noatime")

        cmd = ["sudo", "mount", "-t", fstype, "-o", opts, raw_dev, str(mount_path)]
        res = subprocess.call(cmd)
        if res != 0:
            logging.error("mount_drive(): mount failed, exit=%d", res)
            return False

        # 4 — ownership fix
        subprocess.call(["sudo", "chown", "pi:pi", str(mount_path)])

        logging.info("mount_drive(): mounted %s (%s) at %s", raw_dev, fstype, mount_path)

        # 5 — sync SSDMonitor state & emit events
        self._handle_mount()
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
