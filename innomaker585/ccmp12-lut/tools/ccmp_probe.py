#!/usr/bin/env python3
"""Probe a 12-bit CCMP take for the knee at code 500.

Under the §13.3 curve the interval [500, 671.9) of stored codes covers internal
linear 500..11500 at 1/64 - i.e. 11000 linear LSB squeezed into 172 codes. A scene
with real content must therefore pile up hard in 500..672 and thin out above it.
A linear (CCMP-off) frame shows no such structure.
"""
import sys, glob
import numpy as np

OFF = 8


def unpack_tiff(buf, W, H):
    b = buf.reshape(-1, 3).astype(np.uint16)
    p0 = (b[:, 0] << 4) | (b[:, 1] >> 4)
    p1 = ((b[:, 1] & 0x0F) << 8) | b[:, 2]
    return np.stack([p0, p1], axis=1).reshape(H, W)


def load(path, W, H):
    with open(path, "rb") as f:
        f.seek(OFF)
        return unpack_tiff(np.frombuffer(f.read(W * H * 3 // 2), dtype=np.uint8), W, H)


W, H = int(sys.argv[2]), int(sys.argv[3])
files = sorted(glob.glob(sys.argv[1]))
img = load(files[0], W, H)
g = img[0::2, 1::2]          # G1 plane, RGGB

print(f"{len(files)} frames, {W}x{H}\n")
print(f"G1 plane: mean {g.mean():.2f}  std {g.std():.2f}  min {g.min()}  max {g.max()}")
print(f"percentiles: " + "  ".join(
    f"p{p}={np.percentile(g, p):.0f}" for p in (0.1, 1, 5, 25, 50, 75, 95, 99, 99.9, 100)))

full = img
print(f"\nfull frame: min {full.min()}  max {full.max()}  "
      f"frac at 4095 = {(full == 4095).mean()*100:.4f}%")

# Occupancy either side of the predicted knee.
print("\n--- code occupancy around the predicted knee (all channels) ---")
bands = [(0, 200), (200, 400), (400, 500), (500, 560), (560, 620), (620, 672),
         (672, 800), (800, 1200), (1200, 2000), (2000, 3000), (3000, 4096)]
tot = full.size
for lo, hi in bands:
    n = int(((full >= lo) & (full < hi)).sum())
    mark = ""
    if lo == 500:
        mark = "  <- 1/64 segment starts (knee1)"
    if lo == 672:
        mark = "  <- 1/16 segment starts (knee2 = C2 671.9)"
    print(f"  [{lo:4d},{hi:4d})  {n:10d}  {100*n/tot:7.3f}%{mark}")

# Density per code: the 1/64 segment should be ~64x denser per code than a
# linear frame of the same content, and the step at 671.9 should show a 4x drop.
print("\n--- mean pixels per code (density) ---")
for lo, hi in [(300, 500), (500, 672), (672, 1000), (1000, 2000), (2000, 4000)]:
    n = int(((full >= lo) & (full < hi)).sum())
    print(f"  codes {lo:4d}-{hi:4d}: {n/(hi-lo):12.1f} px/code")

if len(files) > 1:
    print("\n--- frame-to-frame G1 means (motion / exposure check) ---")
    for p in files[:6]:
        gg = load(p, W, H)[0::2, 1::2]
        print(f"  {p.split('_')[-1][:9]}  mean {gg.mean():8.2f}  max {gg.max():5d}")
