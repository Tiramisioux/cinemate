"""Storage media pre-roll handling.

This module records a short clip at maximum FPS whenever CineMate
starts or new storage is mounted, then removes the clip so the media is
"warmed up" before the user records anything important.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, Optional

from module.redis_controller import ParameterKey


class StoragePreroll:
    """Handle automatic storage pre-roll recording."""

    def __init__(
        self,
        cinepi_controller,
        redis_controller,
        ssd_monitor,
        sensor_detect,
        duration: float = 2.0,
        settle_delay: float = 3.0,
    ) -> None:
        self.cinepi_controller = cinepi_controller
        self.redis_controller = redis_controller
        self.ssd_monitor = ssd_monitor
        self.sensor_detect = sensor_detect
        self.duration = max(0.0, float(duration))
        self.settle_delay = max(0.0, float(settle_delay))

        self._active_lock = threading.Lock()
        self._active = False

        # Ensure GUI defaults to normal state if CineMate crashed mid-preroll.
        try:
            self.redis_controller.set_value(
                ParameterKey.STORAGE_PREROLL_ACTIVE.value, 0
            )
        except Exception as exc:  # pragma: no cover - defensive
            logging.debug("Unable to reset storage preroll flag: %s", exc)

        # React to storage events.
        self.ssd_monitor.mount_event.subscribe(self._handle_mount_event)

        # Run a startup preroll once the system has had a moment to settle.
        threading.Thread(
            target=self._startup_preroll, name="StoragePrerollStart", daemon=True
        ).start()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def trigger_manual(self) -> None:
        """Trigger a manual pre-roll via CLI."""
        if self.trigger(reason="cli"):
            logging.info("Storage pre-roll started (CLI request)")
        else:
            logging.info("Storage pre-roll already in progress; CLI request ignored")

    def trigger(self, reason: str, delay: Optional[float] = None) -> bool:
        """Schedule a pre-roll run.

        Returns ``True`` if a new run was scheduled, ``False`` if one is
        already active.
        """

        with self._active_lock:
            if self._active:
                return False
            self._active = True

        if delay is None:
            delay = self.settle_delay

        thread = threading.Thread(
            target=self._run_with_delay,
            args=(max(0.0, float(delay)), reason),
            name="StoragePrerollWorker",
            daemon=True,
        )
        thread.start()
        return True

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _startup_preroll(self) -> None:
        # Give the rest of the system a head start before we try recording.
        time.sleep(self.settle_delay)
        if self.ssd_monitor.is_mounted:
            self.trigger(reason="startup")

    def _handle_mount_event(self, *_args) -> None:
        logging.info("Storage mounted – scheduling pre-roll warmup")
        self.trigger(reason="mount")

    def _run_with_delay(self, delay: float, reason: str) -> None:
        try:
            if delay:
                time.sleep(delay)
            self._execute_preroll(reason)
        finally:
            with self._active_lock:
                self._active = False

    # ------------------------------------------------------------------
    def _execute_preroll(self, reason: str) -> None:
        if not self.ssd_monitor.is_mounted:
            logging.info("Skipping storage pre-roll (%s): no media mounted", reason)
            return

        if str(self.redis_controller.get_value(ParameterKey.IS_RECORDING.value)) == "1":
            logging.info("Skipping storage pre-roll (%s): recording already active", reason)
            return

        logging.info("Starting storage pre-roll (%s)", reason)

        start_wall = time.time()
        baseline_paths: Dict[ParameterKey, Optional[str]] = {
            ParameterKey.LAST_DNG_CAM0: self.redis_controller.get_value(
                ParameterKey.LAST_DNG_CAM0.value
            ),
            ParameterKey.LAST_DNG_CAM1: self.redis_controller.get_value(
                ParameterKey.LAST_DNG_CAM1.value
            ),
        }

        prev_fps_user = self._get_float(ParameterKey.FPS_USER.value)
        if prev_fps_user is None:
            prev_fps_user = self._get_float(ParameterKey.FPS.value)

        fps_target = self._resolve_fps_max()

        # Tell the rest of the system that we are busy.
        self.cinepi_controller.set_preroll_active(True)
        self.redis_controller.set_value(
            ParameterKey.STORAGE_PREROLL_ACTIVE.value, 1
        )

        try:
            if fps_target is not None:
                self._apply_fps(fps_target)

            # Initiate recording.
            self.cinepi_controller.start_recording()
            self._wait_for_value(ParameterKey.REC.value, "1", timeout=5.0)

            time.sleep(self.duration)

            self.cinepi_controller.stop_recording()
            self._wait_for_value(ParameterKey.REC.value, "0", timeout=5.0)

            # Wait until buffers finish flushing to disk.
            self._wait_for_value(ParameterKey.IS_WRITING.value, "0", timeout=10.0)
            self._wait_for_value(ParameterKey.IS_WRITING_BUF.value, "0", timeout=10.0)

        except Exception as exc:
            logging.error("Storage pre-roll failed: %s", exc)
        finally:
            # Restore the user's FPS choice.
            if prev_fps_user is not None:
                self._apply_fps(prev_fps_user)

            # Mark completion before cleanup to unlock GUI/controls.
            try:
                self.redis_controller.set_value(
                    ParameterKey.STORAGE_PREROLL_ACTIVE.value, 0
                )
            except Exception as exc:  # pragma: no cover - defensive
                logging.debug("Unable to clear storage preroll flag: %s", exc)
            self.cinepi_controller.set_preroll_active(False)

            # Clean up any clip directories generated by the warm-up.
            try:
                self._cleanup_preroll(start_wall, baseline_paths.values())
            except Exception as exc:
                logging.warning("Storage pre-roll cleanup failed: %s", exc)

        logging.info("Storage pre-roll complete")

    # ------------------------------------------------------------------
    # redis helpers
    # ------------------------------------------------------------------
    def _get_float(self, key: str) -> Optional[float]:
        try:
            value = self.redis_controller.get_value(key)
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _wait_for_value(
        self, key: str, expected: str, timeout: float, poll: float = 0.1
    ) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        expected = str(expected)
        while time.monotonic() < deadline:
            value = self.redis_controller.get_value(key)
            if str(value) == expected:
                return True
            time.sleep(poll)
        return False

    def _resolve_fps_max(self) -> Optional[float]:
        camera_name = self.redis_controller.get_value(ParameterKey.SENSOR.value)
        if not camera_name:
            camera_name = self.sensor_detect.camera_model

        try:
            sensor_mode = int(
                self.redis_controller.get_value(ParameterKey.SENSOR_MODE.value) or 0
            )
        except (TypeError, ValueError):
            sensor_mode = 0

        if not camera_name:
            return None

        fps_max = self.sensor_detect.get_fps_max(camera_name, sensor_mode)
        if fps_max is None:
            fps_max = self._get_float(ParameterKey.FPS_MAX.value)
        return float(fps_max) if fps_max is not None else None

    def _apply_fps(self, value: float) -> None:
        prev_override = getattr(self.cinepi_controller, "lock_override", False)
        try:
            self.cinepi_controller.lock_override = True
            self.cinepi_controller.set_fps(float(value))
        except Exception as exc:
            logging.warning("Failed to set FPS to %.2f during pre-roll: %s", value, exc)
        finally:
            self.cinepi_controller.lock_override = prev_override

    # ------------------------------------------------------------------
    # filesystem cleanup
    # ------------------------------------------------------------------
    def _cleanup_preroll(self, start_ts: float, baseline: Iterable[Optional[str]]) -> None:
        mount_root = getattr(self.ssd_monitor, "mount_path", None)
        if mount_root is None:
            mount_root = getattr(self.ssd_monitor, "_mount_path", None)
        mount_root = Path(mount_root) if mount_root else None

        if mount_root is None:
            logging.debug("Storage pre-roll cleanup skipped: unknown mount path")
            return

        baseline_dirs = {
            parent
            for parent in (
                self._clip_parent(path)
                for path in baseline
                if path and "None" not in str(path)
            )
            if parent is not None
        }

        new_dirs = set()
        for key in (ParameterKey.LAST_DNG_CAM0, ParameterKey.LAST_DNG_CAM1):
            value = self.redis_controller.get_value(key.value)
            candidate = self._clip_parent(value)
            if candidate is None:
                continue
            if candidate in baseline_dirs:
                continue
            if not self._is_under_mount(candidate, mount_root):
                continue
            try:
                if candidate.stat().st_mtime + 1 < start_ts:
                    # Directory predates the pre-roll run.
                    continue
            except FileNotFoundError:
                continue
            new_dirs.add(candidate)

        for directory in sorted(new_dirs, key=lambda p: len(str(p)), reverse=True):
            self._remove_tree(directory, mount_root)

    def _clip_parent(self, path_str: Optional[str]) -> Optional[Path]:
        if not path_str or "None" in str(path_str):
            return None
        try:
            return Path(path_str).parent
        except Exception:
            return None

    def _is_under_mount(self, path: Path, mount_root: Path) -> bool:
        try:
            path = path.resolve()
        except FileNotFoundError:
            path = path.absolute()
        try:
            root = mount_root.resolve()
        except FileNotFoundError:
            root = mount_root.absolute()
        return root == path or root in path.parents

    def _remove_tree(self, directory: Path, mount_root: Path) -> None:
        if not directory.exists():
            return
        logging.info("Removing storage pre-roll clip directory %s", directory)
        try:
            shutil.rmtree(directory)
        except Exception as exc:
            logging.warning("Failed to remove %s: %s", directory, exc)
            return

        # Attempt to remove empty parent directories up to the mount root.
        parent = directory.parent
        while parent != mount_root and parent.is_dir():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

