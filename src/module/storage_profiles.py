"""Storage filesystem profiles used by Cinemate and cinepi-raw launch."""

from __future__ import annotations

from typing import Dict


SUPPORTED_STORAGE_FILESYSTEMS = ("ext4", "exfat", "ntfs")
NO_STORAGE_FILESYSTEM = "none"
UNKNOWN_STORAGE_FILESYSTEM = "unknown"
DEFAULT_RECORDER_PROFILE = "default"

FILESYSTEM_ALIASES = {
    "": NO_STORAGE_FILESYSTEM,
    "none": NO_STORAGE_FILESYSTEM,
    "no disk": NO_STORAGE_FILESYSTEM,
    "ex4": "ext4",
    "vfat": "exfat",
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
        "disk_affinity": "2-3",
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
        "disk_affinity": "2-3",
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


def recorder_profile_name_for_filesystem(filesystem) -> str:
    fs = normalize_storage_filesystem(filesystem)
    if fs in SUPPORTED_STORAGE_FILESYSTEMS:
        return fs
    return DEFAULT_RECORDER_PROFILE


def recorder_profile_for_filesystem(filesystem) -> Dict[str, str]:
    return RECORDER_PROFILES[recorder_profile_name_for_filesystem(filesystem)]


def recorder_profile_args(filesystem) -> list[str]:
    profile = recorder_profile_for_filesystem(filesystem)
    return [
        "--encode-workers", profile["encode_workers"],
        "--disk-workers", profile["disk_workers"],
        "--encode-affinity", profile["encode_affinity"],
        "--disk-affinity", profile["disk_affinity"],
        "--encode-nice", profile["encode_nice"],
        "--disk-nice", profile["disk_nice"],
    ]


def supported_filesystem_text() -> str:
    return "|".join(SUPPORTED_STORAGE_FILESYSTEMS)
