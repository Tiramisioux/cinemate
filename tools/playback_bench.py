#!/usr/bin/env python3
"""Measure what C9's playback gates ask about, on the machine that matters.

G1 (--decode), G2 (--io) and G9 (--render) are all questions about the Pi, and
none of them can be answered from a laptop: the decode budget is per-core
speed, the storage question is what the *device* transfers rather than what the
decoder consumes, and the render question is whether a companded frame comes
out looking like anything. This runs each of them against a real take, from the
repo checkout, over SSH, with no services running and nothing to set up.

    python3 tools/playback_bench.py --decode /media/RAW/<take>
    python3 tools/playback_bench.py --io     /media/RAW/<take>
    python3 tools/playback_bench.py --render /media/RAW/<take> [more takes...]
    python3 tools/playback_bench.py --meta   /media/RAW/<take> [more takes...]

--meta (G0/G10) walks the IFD chain of one frame per take and reports it --
IFD count, which one carries the raw image, and the thumbnail's own
dimensions/samples-per-pixel/bit depth/photometric/byte count when a
second IFD (cinepi-raw's embedded DNG thumbnail, C9 Phase 0) is present.
Both gates ask for exactly this: "dump the IFD structure ... with the C9
metadata reader."

Output is one JSON object per line on stdout and nothing else, so a run pastes
into GATES.md as-is. Progress and complaints go to stderr.

Dependencies are numpy and Pillow, which every camera already has -- they are
unconditional runtime dependencies imported on main.py's own boot path. That
constraint is load-bearing, not stylistic: cinemate-update.sh never re-runs
pip, so anything new here would break every deployed camera on update with a
bare ImportError and no diagnostic.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np                                    # noqa: E402
from PIL import Image                                 # noqa: E402

from module.app import dng_preview                    # noqa: E402

SECTOR_BYTES = 512          # /proc/diskstats counts 512-byte sectors always,
                            # whatever the device's own logical block size is.
DEFAULT_ITERATIONS = 15
DEFAULT_SCALES = (2, 4, 8)
DEFAULT_WORKERS = (1, 2, 4)


def emit(record: dict) -> None:
    """One measurement, one line, stdout only."""
    print(json.dumps(record, sort_keys=True), flush=True)


def note(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def frames_in(take: Path) -> list[Path]:
    frames = sorted(take.glob("*.dng"))
    if not frames:
        raise SystemExit(f"no .dng frames in {take}")
    return frames


def take_meta(frames: list[Path]) -> dict:
    meta = dng_preview.read_metadata(frames[0])
    hdr, encoding, label, display_bits, log10 = dng_preview.describe_mode(meta)
    return {
        "width": int(meta.get("width", 0)),
        "height": int(meta.get("height", 0)),
        # The literal stored BitsPerSample, not describe_mode()'s
        # display_bits substitution -- this is a diagnostic tool, and what
        # the decoder actually reads off disk is the useful number here.
        "bits": int(meta.get("bits", 0)),
        "source_bits": display_bits,
        "log10": log10,
        "fps": dng_preview.frame_rate(meta),
        "mode_label": label,
        "encoding": encoding,
        "has_linearization_table": bool(meta.get("linearization_table")),
    }


# ---------------------------------------------------------------- G1: decode

def decode_once(path: Path, scale: int) -> None:
    dng_preview.decode_frame(path, None, scale=scale)


def bench_decode(take: Path, scales, workers, iterations) -> None:
    """Median ms per frame at each (scale x workers), G1.

    Reports the median of `iterations` runs rather than a mean: a single
    scheduler excursion on a busy Pi otherwise moves the number more than the
    thing being measured. Each run decodes `workers` distinct frames so the
    pool has real work per thread, and the reported figure is per frame.
    """
    frames = frames_in(take)
    meta = take_meta(frames)
    for scale in scales:
        for n in workers:
            if len(frames) < n:
                note(f"skipping workers={n}: take has only {len(frames)} frames")
                continue
            samples = []
            for i in range(iterations):
                batch = [frames[(i * n + k) % len(frames)] for k in range(n)]
                start = time.perf_counter()
                if n == 1:
                    decode_once(batch[0], scale)
                else:
                    with ThreadPoolExecutor(max_workers=n) as pool:
                        list(pool.map(lambda p: decode_once(p, scale), batch))
                samples.append((time.perf_counter() - start) * 1000.0 / n)
            out_w, out_h = dng_preview.output_size(
                dng_preview.read_metadata(frames[0]), scale)
            # decode_once() -> decode_frame() reads the file itself
            # (_load_rows() opens and seeks it), so this figure is decode
            # wall-clock INCLUDING that read, not CPU-only -- and whether
            # each read came off the OS page cache or the device is not
            # something this process controls or can drop on demand
            # without root. `batch` cycles through `frames` every len(frames)
            # iterations, so later iterations at len(frames) < workers*
            # iterations are increasingly likely to be page-cache-warm even
            # on a cold-booted Pi. Reporting the first iteration separately
            # from the rest of the distribution is what lets a reader see
            # that difference instead of it hiding inside one median.
            emit({
                "gate": "G1",
                "measurement": "decode",
                "take": take.name,
                "scale": scale,
                "workers": n,
                "iterations": iterations,
                "ms_per_frame_first": round(samples[0], 2),
                "ms_per_frame_median": round(statistics.median(samples), 2),
                "ms_per_frame_min": round(min(samples), 2),
                "ms_per_frame_max": round(max(samples), 2),
                "includes_file_io": True,
                "output": f"{out_w}x{out_h}",
                "numpy": np.__version__,
                "python": sys.version.split()[0],
                **meta,
            })


# -------------------------------------------------------------------- G2: io

def diskstats_device(path: Path) -> tuple[str, str] | tuple[None, None]:
    """(device name, source) for the block device backing `path`.

    Matched by major:minor through /sys rather than by name: the take lives on
    a mounted filesystem whose device is what st_dev names, and mapping that
    back to a /proc/diskstats line by string is guesswork on NVMe.
    """
    try:
        st = os.stat(path)
    except OSError as exc:
        return None, f"cannot stat {path}: {exc}"
    major, minor = os.major(st.st_dev), os.minor(st.st_dev)
    sysfs = Path(f"/sys/dev/block/{major}:{minor}")
    if not sysfs.exists():
        return None, f"no /sys/dev/block/{major}:{minor} (not Linux?)"
    return sysfs.resolve().name, f"{major}:{minor}"


def sectors_read(device: str) -> int | None:
    """Sectors read since boot: the 6th column of /proc/diskstats, which is
    stat field 3 in the kernel's own numbering (it starts counting after
    major/minor/name)."""
    try:
        with open("/proc/diskstats") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) >= 7 and parts[2] == device:
                    return int(parts[5])
    except OSError:
        return None
    return None


def bench_io(take: Path, scale: int, count: int) -> None:
    """Device bytes read per decoded frame, G2.

    The point of measuring here rather than with dd: nothing in this stack
    tunes read_ahead_kb, so a ~5.8 kB row stride under the default 128 kB
    readahead may transfer the whole frame however few rows the decoder asks
    for. If it does, the plan's per-frame I/O figures -- and the storage
    headroom derived from them -- are wrong by the ratio this prints.
    """
    frames = frames_in(take)[:count]
    meta = take_meta(frames)
    device, source = diskstats_device(take)

    if device is None:
        note(f"--io needs Linux /proc/diskstats and /sys/dev/block: {source}")
        note("wall clock is still measured; device bytes are reported as null.")

    before = sectors_read(device) if device else None
    start = time.perf_counter()
    for path in frames:
        decode_once(path, scale)
    elapsed = time.perf_counter() - start
    after = sectors_read(device) if device else None

    record = {
        "gate": "G2",
        "measurement": "io",
        "take": take.name,
        "scale": scale,
        "frames": len(frames),
        "device": device,
        "ms_per_frame_wall": round(elapsed * 1000.0 / max(len(frames), 1), 2),
        "file_bytes_per_frame": frames[0].stat().st_size,
        **meta,
    }
    if before is not None and after is not None:
        read_bytes = (after - before) * SECTOR_BYTES
        per_frame = read_bytes / max(len(frames), 1)
        record.update({
            "device_bytes_per_frame": int(per_frame),
            "device_bytes_total": int(read_bytes),
            # What the card must sustain to hold the take's own rate.
            "implied_mb_per_s_at_fps": round(
                per_frame * (meta["fps"] or 0) / 1e6, 1),
            # >1 means readahead moved more than the file itself; <1 means the
            # row-selective read really did save bytes.
            "device_vs_file_ratio": round(
                per_frame / max(frames[0].stat().st_size, 1), 2),
        })
        # read_bytes == 0 means the block device transferred NOTHING for
        # `count` decoded frames -- every row-selective read still moves at
        # least a few KB off a real device, so this is the OS page cache
        # serving the read, not the row-selective decode being free. A
        # naive read of device_vs_file_ratio would score this the best
        # possible outcome (0.0, "less than the row-selective ideal")
        # when it is actually a measurement of nothing. Cannot be
        # corrected for without root (no way to drop caches from here) --
        # flagged so a reader doesn't mistake it for a storage result.
        # Same confound `--decode` documents via ms_per_frame_first.
        if read_bytes == 0:
            record["cache_warm_suspected"] = True
            note(f"{take.name}: 0 device bytes read for {len(frames)} frames -- "
                "page cache is almost certainly warm; this run says nothing "
                "about device bandwidth. Re-run after a reboot, or on a take "
                "not touched by an earlier --decode/--render pass.")
    else:
        record["device_bytes_per_frame"] = None
        record["skipped"] = f"/proc/diskstats unavailable ({source})"
    emit(record)


# ---------------------------------------------------------------- G9: render

def bench_render(take: Path, scale: int, out_dir: Path) -> None:
    """Is the decoded frame actually an image? G9.

    Exists because no other gate looks at a pixel. A decoder that skips the
    LinearizationTable does not raise, log, or slow down -- it just renders a
    companded take crushed toward black, so the only way to catch it is to
    measure what came out. The percentiles matter more than the mean: a frame
    can average plausibly while being almost entirely black.

    A black render has two possible causes and this gate has to separate them,
    because the interesting one is not the likely one: the decoder can be
    wrong, or the take can be flat. Flat takes really exist here -- the
    ClearHDR pedestal-fill defect writes frames whose every sample equals
    BlackLevel -- and rendering those black is correct behaviour. So the
    stored codes are reported alongside the rendered luma: raw_unique_codes 1
    with raw_min == raw_max == BlackLevel is a flat source and says nothing
    about the decoder, while a black render over a wide raw range is the
    decoder's fault.
    """
    frames = frames_in(take)
    meta = take_meta(frames)
    raw = dng_preview._load_rows(frames[0], dng_preview.read_metadata(frames[0]),
                                 row_step=max(scale // 2, 1))
    jpeg, (width, height) = dng_preview.decode_frame(frames[0], None, scale=scale)

    image = Image.open(io.BytesIO(jpeg))
    array = np.asarray(image.convert("L"), dtype=np.float64)
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{take.name}_scale{scale}.png"
    image.save(png)

    p5, p95 = np.percentile(array, (5, 95))
    emit({
        "gate": "G9",
        "measurement": "render",
        "take": take.name,
        "scale": scale,
        "output": f"{width}x{height}",
        "luma_mean": round(float(array.mean()), 1),
        "luma_p5": round(float(p5), 1),
        "luma_p95": round(float(p95), 1),
        "zero_pixel_fraction": round(float((array == 0).mean()), 4),
        # Source-side evidence, so a black render is attributable. See above.
        "raw_min": int(raw.min()),
        "raw_max": int(raw.max()),
        "raw_unique_codes": int(np.unique(raw).size),
        "source_is_flat": bool(np.unique(raw).size == 1),
        "png": str(png),
        **meta,
    })


# ------------------------------------------------------------------ metadata

def walk_ifd_chain(path: Path) -> list[dict]:
    """Every IFD in ``path``, in file order, each as a plain dict of its tags
    plus ``_offset`` and ``_next_ifd_offset``.

    What G0 and G10 both ask for -- "dump the IFD structure of one frame,
    extended to walk every IFD" -- and dng_preview.read_metadata() alone
    cannot answer, because it merges IFD1 into meta["thumbnail"] rather
    than reporting it as a separate structure with its own offset. Reuses
    dng_preview._parse_ifd() (the same tag table, the same next-IFD
    field) rather than re-implementing IFD parsing a second time.
    """
    import struct as _struct

    ifds = []
    with open(path, "rb") as handle:
        header = handle.read(8)
        if len(header) < 8 or header[:2] not in (b"II", b"MM"):
            raise dng_preview.DngError("not a TIFF/DNG file")
        end = "<" if header[:2] == b"II" else ">"
        magic, offset = _struct.unpack(end + "HI", header[2:8])
        if magic != 42:
            raise dng_preview.DngError("not a TIFF/DNG file")

        seen = set()
        while offset and offset not in seen:
            seen.add(offset)   # guard against a corrupt chain looping forever
            handle.seek(offset)
            tail = handle.read(dng_preview._IFD_TAIL_BYTES)
            if not tail:
                break
            tags, next_offset = dng_preview._parse_ifd(tail, offset, base=offset)
            tags["_offset"] = offset
            tags["_next_ifd_offset"] = next_offset
            ifds.append(tags)
            offset = next_offset

    return ifds


def bench_meta(take: Path, frame_index: int) -> None:
    """G0 / G10: the full IFD chain of one frame, exactly as a DNG reader
    would walk it -- IFD count, which one carries the raw image (samples_
    per_pixel==1, photometric CFA == 32803), and the thumbnail's own
    dimensions/samples_per_pixel/bit depth/photometric/byte count when a
    second IFD is present.
    """
    frames = frames_in(take)
    if not 0 <= frame_index < len(frames):
        raise SystemExit(f"frame {frame_index} outside 0..{len(frames) - 1} for {take}")
    path = frames[frame_index]

    ifds = walk_ifd_chain(path)
    emit({
        "gate": "G0/G10",
        "measurement": "meta",
        "take": take.name,
        "frame": path.name,
        "file_bytes": path.stat().st_size,
        "ifd_count": len(ifds),
        "ifds": [
            {
                "index": i,
                "offset": tags["_offset"],
                "next_ifd_offset": tags["_next_ifd_offset"],
                "width": tags.get("width"),
                "height": tags.get("height"),
                "bits": tags.get("bits"),
                "samples_per_pixel": tags.get("samples_per_pixel"),
                "photometric": tags.get("photometric"),
                "compression": tags.get("compression"),
                "strip_offset": tags.get("strip_offset"),
                "strip_bytes": tags.get("strip_bytes"),
                "rows_per_strip": tags.get("rows_per_strip"),
                "has_linearization_table": bool(tags.get("linearization_table")),
            }
            for i, tags in enumerate(ifds)
        ],
    })


# ------------------------------------------------------------------- driving

def int_list(text: str) -> list[int]:
    return [int(part) for part in text.split(",") if part.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--decode", action="store_true", help="G1: decode throughput")
    mode.add_argument("--io", action="store_true", help="G2: device bytes per frame")
    mode.add_argument("--render", action="store_true", help="G9: rendered-pixel sanity")
    mode.add_argument("--meta", action="store_true", help="G0/G10: dump the IFD chain")
    parser.add_argument("takes", nargs="+", type=Path, help="take directories")
    parser.add_argument("--scales", type=int_list, default=list(DEFAULT_SCALES))
    parser.add_argument("--workers", type=int_list, default=list(DEFAULT_WORKERS))
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--scale", type=int, default=4,
                        help="single scale for --io and --render (default 4)")
    parser.add_argument("--count", type=int, default=20,
                        help="frames to decode for --io (default 20)")
    parser.add_argument("--out-dir", type=Path, default=Path("playback_bench_out"),
                        help="where --render writes its PNGs")
    parser.add_argument("--frame", type=int, default=0,
                        help="frame index for --meta (default 0, the first frame)")
    args = parser.parse_args(argv)

    for take in args.takes:
        if not take.is_dir():
            note(f"not a directory, skipping: {take}")
            continue
        try:
            if args.decode:
                bench_decode(take, args.scales, args.workers, args.iterations)
            elif args.io:
                bench_io(take, args.scale, args.count)
            elif args.meta:
                bench_meta(take, args.frame)
            else:
                bench_render(take, args.scale, args.out_dir)
        except (dng_preview.DngError, OSError) as exc:
            note(f"{take.name}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
