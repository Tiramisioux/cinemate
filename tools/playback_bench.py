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
    hdr, encoding, label = dng_preview.describe_mode(meta)
    return {
        "width": int(meta.get("width", 0)),
        "height": int(meta.get("height", 0)),
        "bits": int(meta.get("bits", 0)),
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
            emit({
                "gate": "G1",
                "measurement": "decode",
                "take": take.name,
                "scale": scale,
                "workers": n,
                "iterations": iterations,
                "ms_per_frame_median": round(statistics.median(samples), 2),
                "ms_per_frame_min": round(min(samples), 2),
                "ms_per_frame_max": round(max(samples), 2),
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
            else:
                bench_render(take, args.scale, args.out_dir)
        except (dng_preview.DngError, OSError) as exc:
            note(f"{take.name}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
