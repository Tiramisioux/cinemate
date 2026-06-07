"""Audio-core isolation invariant for storage recorder profiles.

cinepi-audio-capture pins itself to the last CPU core of the Pi (core 3 on a
4-core Pi) at SCHED_FIFO priority 80. No recorder profile may place DNG encode
or disk workers on that core, or audio capture stalls at launch and the WAV
loses sync (observed as a garbage start timecode, e.g. 00:59:59:24, or a
missing WAV entirely). This locks that invariant so a future profile edit
cannot silently reintroduce the ext4 "2-3" regression.
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.modules.setdefault("redis", types.SimpleNamespace(StrictRedis=object))

from module.storage_profiles import (  # noqa: E402
    PI4_MAX_DISK_WORKERS,
    RECORDER_PROFILES,
    recorder_profile_args,
)

# On the 4-core Pi 4/5 the audio-capture helper owns the last core.
AUDIO_CORE_PI = 3


def _expand_affinity(spec: str) -> set[int]:
    """Expand a cpu-affinity spec ('2', '1-2', '0,1,2', '0-1,3') to a set."""
    cores: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            cores.update(range(int(lo), int(hi) + 1))
        else:
            cores.add(int(part))
    return cores


class AudioCoreInvariantTest(unittest.TestCase):
    def test_no_profile_pins_workers_to_audio_core(self):
        for name, prof in RECORDER_PROFILES.items():
            for key in ("encode_affinity", "disk_affinity"):
                cores = _expand_affinity(prof[key])
                self.assertNotIn(
                    AUDIO_CORE_PI,
                    cores,
                    f"profile {name!r} {key}={prof[key]!r} includes the audio "
                    f"core {AUDIO_CORE_PI}; audio capture would lose sync",
                )
                self.assertTrue(cores, f"profile {name!r} {key} pins no core")

    def test_recorder_profile_args_audio_safe(self):
        for fs in ("ext4", "exfat", "ntfs", "none", "definitely-not-a-fs"):
            args = recorder_profile_args(fs)
            for flag in ("--encode-affinity", "--disk-affinity"):
                self.assertIn(flag, args)
                cores = _expand_affinity(args[args.index(flag) + 1])
                self.assertNotIn(
                    AUDIO_CORE_PI,
                    cores,
                    f"{fs} {flag} includes audio core {AUDIO_CORE_PI}",
                )

    def test_ext4_disk_affinity_regression(self):
        # ext4 disk_affinity was "2-3"; core 3 collided with audio capture and
        # broke sync on ext4 takes while exFAT ("2") stayed clean.
        cores = _expand_affinity(RECORDER_PROFILES["ext4"]["disk_affinity"])
        self.assertNotIn(AUDIO_CORE_PI, cores)

    def test_pi4_caps_disk_workers(self):
        # Pi 4 shares the xHCI USB controller between storage and the mic, so
        # many disk writers congest the bus and stall audio. ext4's 8 workers
        # are capped on Pi 4; Pi 5 (NVMe over PCIe) keeps the full count.
        def disk_workers(fs, is_pi4):
            args = recorder_profile_args(fs, is_pi4=is_pi4)
            return int(args[args.index("--disk-workers") + 1])

        self.assertEqual(disk_workers("ext4", is_pi4=False), 8)
        self.assertEqual(disk_workers("ext4", is_pi4=True), PI4_MAX_DISK_WORKERS)
        # Already-low counts are untouched by the cap.
        self.assertEqual(disk_workers("exfat", is_pi4=True), 2)
        # Affinity stays audio-safe on both platforms.
        for is_pi4 in (False, True):
            args = recorder_profile_args("ext4", is_pi4=is_pi4)
            cores = _expand_affinity(args[args.index("--disk-affinity") + 1])
            self.assertNotIn(AUDIO_CORE_PI, cores)


if __name__ == "__main__":
    unittest.main()
