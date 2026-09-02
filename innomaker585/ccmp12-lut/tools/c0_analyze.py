#!/usr/bin/env python3
"""C0 go/no-go: mean stored 12-bit code per CFA channel from a lens-cap ClearHDR take.

Unpacks both candidate 12-bit orderings and reports which one is self-consistent,
so the packing convention is measured rather than assumed.
"""
import sys, glob
import numpy as np

W, H, OFF = 1928, 1090, 8
NBYTES = W * H * 3 // 2


def unpack_tiff(buf):
    """TIFF/DNG big-endian bitstream: b0=p0[11:4], b1=p0[3:0]<<4|p1[11:8], b2=p1[7:0]."""
    b = buf.reshape(-1, 3).astype(np.uint16)
    p0 = (b[:, 0] << 4) | (b[:, 1] >> 4)
    p1 = ((b[:, 1] & 0x0F) << 8) | b[:, 2]
    return np.stack([p0, p1], axis=1).reshape(H, W)


def unpack_mipi(buf):
    """MIPI CSI-2 RAW12: b0=p0[11:4], b1=p1[11:4], b2=p1[3:0]<<4|p0[3:0]."""
    b = buf.reshape(-1, 3).astype(np.uint16)
    p0 = (b[:, 0] << 4) | (b[:, 2] & 0x0F)
    p1 = (b[:, 1] << 4) | (b[:, 2] >> 4)
    return np.stack([p0, p1], axis=1).reshape(H, W)


def cfa_stats(img):
    """CFAPattern 0 1 1 2 = RGGB."""
    return {
        "R":  img[0::2, 0::2],
        "G1": img[0::2, 1::2],
        "G2": img[1::2, 0::2],
        "B":  img[1::2, 1::2],
    }


def neighbour_corr(img):
    """Horizontal same-channel correlation. Garbage unpacking destroys it."""
    a = img[0::2, 0::2].astype(np.float64)
    x, y = a[:, :-1].ravel(), a[:, 1:].ravel()
    if x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


files = sorted(glob.glob(sys.argv[1]))
print(f"{len(files)} frames, {W}x{H}, 12-bit packed, strip offset {OFF}\n")

for name, fn in (("TIFF/DNG MSB-first", unpack_tiff), ("MIPI RAW12", unpack_mipi)):
    with open(files[0], "rb") as f:
        f.seek(OFF)
        raw = np.frombuffer(f.read(NBYTES), dtype=np.uint8)
    img = fn(raw)
    ch = cfa_stats(img)
    print(f"--- unpacking as {name} ---")
    for c, v in ch.items():
        print(f"  {c:2s}  mean {v.mean():9.3f}   std {v.std():7.3f}   "
              f"min {v.min():5d}  max {v.max():5d}")
    print(f"  horizontal neighbour corr (R plane): {neighbour_corr(img):+.4f}\n")

# All frames, using the TIFF interpretation (confirmed below in the report).
print("--- per-frame means, TIFF/DNG unpacking ---")
allmeans = []
for p in files:
    with open(p, "rb") as f:
        f.seek(OFF)
        raw = np.frombuffer(f.read(NBYTES), dtype=np.uint8)
    ch = cfa_stats(unpack_tiff(raw))
    m = {c: float(v.mean()) for c, v in ch.items()}
    allmeans.append(m)
    print(f"  {p.split('_')[-1][:9]}  " + "  ".join(f"{c} {m[c]:8.3f}" for c in "R G1 G2 B".split()))

print("\n--- take aggregate ---")
for c in "R G1 G2 B".split():
    vals = np.array([m[c] for m in allmeans])
    print(f"  {c:2s}  mean of frame means {vals.mean():9.4f}   spread {vals.max()-vals.min():.4f}")
grand = np.mean([v for m in allmeans for v in m.values()])
print(f"\n  GRAND MEAN (all channels, all frames): {grand:.4f}")

print("\n--- candidate models ---")
for label, pred in [("542  §13.3, 16-bit knee domain", 542.19),
                    ("505  14-bit knee domain", 504.69),
                    ("200  threshold seed {0,0}, or 12-bit scaling", 200.0),
                    ("1175 pre-fix ratios (middle 1/4)", 1175.0),
                    ("3200 CCMP off", 3200.0),
                    ("0    BLC clamp / degenerate", 0.0)]:
    print(f"  {label:46s}  delta {grand - pred:+10.3f}")
