"""Storage filesystem profiles used by Cinemate and cinepi-raw launch."""

from __future__ import annotations

from typing import Dict


SUPPORTED_STORAGE_FILESYSTEMS = ("ext4", "exfat", "ntfs")
# NTFS is supported (it mounts and records) but NOT recommended: the Linux NTFS
# drivers (ntfs-3g/FUSE and the in-kernel ntfs3) fail or short-write under
# sustained 4K DNG throughput far more readily than exFAT/ext4, losing frames at
# the write() syscall with no inter-frame timing gap. cinepi-raw now counts those
# write failures (writeFailures stat) so they surface live, but exFAT or ext4
# remains the right choice for sustained recording.
RECOMMENDED_STORAGE_FILESYSTEMS = ("ext4", "exfat")
NO_STORAGE_FILESYSTEM = "none"
UNKNOWN_STORAGE_FILESYSTEM = "unknown"
DEFAULT_RECORDER_PROFILE = "default"

FILESYSTEM_ALIASES = {
    "": NO_STORAGE_FILESYSTEM,
    "none": NO_STORAGE_FILESYSTEM,
    "no disk": NO_STORAGE_FILESYSTEM,
    "ex4": "ext4",
    # "vfat" is FAT32 (not exFAT) — do not alias; FAT32 is unsupported for
    # recording and should surface as "unknown" so the correct profile fallback
    # and a clear UI label are used instead of the exFAT profile.
    "ntfs3": "ntfs",
    "fuseblk": "ntfs",
}

# buffer_count: camera in-flight raw buffers passed to cinepi-raw as
# --buffer-count. libcamera's base for the video+raw path is 6. More buffers
# absorb transient disk-write latency spikes that would otherwise starve the
# sensor and drop a frame. Slower / spikier filesystems (exFAT, NTFS) get more
# headroom than ext4, which has flatter write latency. Each extra buffer costs
# ~25 MB of CMA at 4K (raw + video streams share the count), so values stay
# conservative; raise per profile (or via settings.json camera.raw_buffer_count)
# only after confirming CMA headroom with `grep Cma /proc/meminfo`.
#
# AUDIO-CORE INVARIANT: cinepi-audio-capture pins itself to the last CPU core
# (N-1) at SCHED_FIFO priority 80 so USB-audio interrupts are serviced on an
# uncontested core (see cinepi_audio_capture.cpp). No profile's encode_affinity
# or disk_affinity may include that core, or audio capture stalls at launch and
# the WAV loses sync (wrong/garbage start timecode, or no WAV at all). On a
# 4-core Pi the audio core is 3, so worker affinity must stay within 0-2
# (practically 1-2, leaving core 0 for the camera pipeline and IRQs).
# cinepi-raw strips the audio core from any requested set as a backstop, but
# profiles must not rely on that. test_storage_profiles.py locks this invariant.
RECORDER_PROFILES: Dict[str, Dict[str, str]] = {
    DEFAULT_RECORDER_PROFILE: {
        "label": "default-safe",
        "encode_workers": "4",
        "disk_workers": "2",
        "encode_affinity": "1-2",
        "disk_affinity": "2",
        "encode_nice": "-10",
        "disk_nice": "-5",
        "buffer_count": "8",
    },
    "ext4": {
        "label": "ext4-throughput",
        "encode_workers": "4",
        "disk_workers": "8",
        "encode_affinity": "1-2",
        # Was "2-3" — core 3 is the audio-capture core (see invariant above).
        # Spreading the 8 disk workers across cores 1-2 keeps ext4 throughput
        # headroom while leaving core 3 for SCHED_FIFO audio capture.
        "disk_affinity": "1-2",
        "encode_nice": "-10",
        "disk_nice": "-5",
        "buffer_count": "8",
    },
    "exfat": {
        "label": "exfat-conservative",
        "encode_workers": "4",
        "disk_workers": "2",
        "encode_affinity": "1-2",
        "disk_affinity": "2",
        "encode_nice": "-10",
        "disk_nice": "-5",
        "buffer_count": "10",
    },
    "ntfs": {
        "label": "ntfs-conservative",
        "encode_workers": "4",
        "disk_workers": "2",
        "encode_affinity": "1-2",
        # Was "2-3" — core 3 is the audio-capture core (see invariant above).
        "disk_affinity": "2",
        "encode_nice": "-10",
        "disk_nice": "-5",
        "buffer_count": "10",
    },
}


def normalize_filesystem(value, *, default: str = NO_STORAGE_FILESYSTEM) -> str:
    text = str(value or "").strip().lower()
    text = FILESYSTEM_ALIASES.get(text, text)
    if not text:
        return default
    return text


def normalize_storage_filesystem(value) -> str:
    fs = normalize_filesystem(value)
    if fs in SUPPORTED_STORAGE_FILESYSTEMS or fs == NO_STORAGE_FILESYSTEM:
        return fs
    return UNKNOWN_STORAGE_FILESYSTEM


def filesystem_is_recommended(filesystem) -> bool:
    """True for filesystems recommended for sustained recording (exFAT/ext4).

    A supported-but-not-recommended filesystem (NTFS) returns False so callers
    can warn the operator without blocking the take.
    """
    return normalize_storage_filesystem(filesystem) in RECOMMENDED_STORAGE_FILESYSTEMS


def filesystem_recording_advisory(filesystem) -> str | None:
    """Operator advisory for a supported-but-not-recommended filesystem.

    Returns None for recommended filesystems, no-disk, or unknown (those are
    handled elsewhere). NTFS records but can lose frames under sustained 4K.
    """
    fs = normalize_storage_filesystem(filesystem)
    if fs in SUPPORTED_STORAGE_FILESYSTEMS and fs not in RECOMMENDED_STORAGE_FILESYSTEMS:
        return (
            f"{fs.upper()} is supported but not recommended for recording: the "
            "Linux NTFS drivers can drop frames under sustained 4K writes. "
            "Use exFAT or ext4 for reliable sustained recording."
        )
    return None


def recorder_profile_name_for_filesystem(filesystem) -> str:
    fs = normalize_storage_filesystem(filesystem)
    if fs in SUPPORTED_STORAGE_FILESYSTEMS:
        return fs
    return DEFAULT_RECORDER_PROFILE


def recorder_profile_for_filesystem(filesystem) -> Dict[str, str]:
    return RECORDER_PROFILES[recorder_profile_name_for_filesystem(filesystem)]


# On Pi 4 the USB host controller (xHCI) is shared by storage and the USB
# microphone, so many concurrent disk writers congest the bus and stall ALSA
# capture (audio sample loss). Pi 5 routes NVMe over PCIe — a separate bus from
# USB — so it keeps the full worker count. Cap disk workers on Pi 4 only.
PI4_MAX_DISK_WORKERS = 4


def recorder_profile_args(filesystem, *, is_pi4: bool = False) -> list[str]:
    profile = recorder_profile_for_filesystem(filesystem)
    disk_workers = profile["disk_workers"]
    if is_pi4:
        try:
            disk_workers = str(min(int(disk_workers), PI4_MAX_DISK_WORKERS))
        except (TypeError, ValueError):
            disk_workers = str(PI4_MAX_DISK_WORKERS)
    return [
        "--encode-workers", profile["encode_workers"],
        "--disk-workers", disk_workers,
        "--encode-affinity", profile["encode_affinity"],
        "--disk-affinity", profile["disk_affinity"],
        "--encode-nice", profile["encode_nice"],
        "--disk-nice", profile["disk_nice"],
    ]


def supported_filesystem_text() -> str:
    return "|".join(SUPPORTED_STORAGE_FILESYSTEMS)
