#!/usr/bin/env python3
"""Does colour drift with LEVEL? That is the signature of decoding companded data
as if it were linear: WB gains are right at one level and wrong everywhere else.

Also separates the two candidate causes:
  (a) wrong BlackLevel tag  -> error concentrated at the bottom, fixed by using
      the measured per-channel black instead of the written 200
  (b) missing LinearizationTable -> error grows through the curve's bend, and
      subtracting the right black does NOT fix it
"""
import sys, glob
import numpy as np

OFF = 8
W, H = 3856, 2180
AS_SHOT = (0.625, 1.0, 0.5263)          # AsShotNeutral from the DNG


def unpack(buf):
    b = buf.reshape(-1, 3).astype(np.uint16)
    p0 = (b[:, 0] << 4) | (b[:, 1] >> 4)
    p1 = ((b[:, 1] & 0x0F) << 8) | b[:, 2]
    return np.stack([p0, p1], axis=1).reshape(H, W)


def avg(pattern, n=13):
    fs = sorted(glob.glob(pattern))[:n]
    acc = np.zeros((H, W))
    for p in fs:
        with open(p, "rb") as f:
            f.seek(OFF)
            acc += unpack(np.frombuffer(f.read(W * H * 3 // 2), dtype=np.uint8))
    return acc / len(fs)


def planes(X):
    return X[0::2, 0::2], X[0::2, 1::2], X[1::2, 0::2], X[1::2, 1::2]   # R G1 G2 B


dark = avg(sys.argv[1])
lit = avg(sys.argv[2])

dR, dG1, dG2, dB = (p.mean() for p in planes(dark))
print("--- measured black, UHD 12-bit ClearHDR, per CFA channel ---")
print(f"  R {dR:7.2f}   G1 {dG1:7.2f}   G2 {dG2:7.2f}   B {dB:7.2f}")
print(f"  DNG writes BlackLevel 200 200 200 200  -> error "
      f"R {dR-200:+.1f}  G1 {dG1-200:+.1f}  G2 {dG2-200:+.1f}  B {dB-200:+.1f}")

print("\n--- what the wrong black alone does to a black pixel, after AsShotNeutral ---")
for name, blk in (("written 200", (200, 200, 200, 200)),
                  ("measured", (dR, dG1, dG2, dB))):
    r = (dR - blk[0]) / AS_SHOT[0]
    g = ((dG1 - blk[1]) + (dG2 - blk[2])) / 2 / AS_SHOT[1]
    b = (dB - blk[3]) / AS_SHOT[2]
    if abs(g) < 1e-9:
        print(f"  black subtracted with {name:12s}: R {r:8.2f}  G {g:8.2f}  B {b:8.2f}   -> neutral")
    else:
        print(f"  black subtracted with {name:12s}: R/G {r/g:6.2f}   B/G {b/g:6.2f}"
              f"   {'MAGENTA' if r/g > 1.1 and b/g > 1.1 else ''}")

# --- colour vs level across the lit scene ---
BS = 24
R, G1, G2, B = planes(lit)
h, w = (R.shape[0]//BS)*BS, (R.shape[1]//BS)*BS
sh = (h//BS, BS, w//BS, BS)
rr = R[:h, :w].reshape(sh).mean(axis=(1, 3)).ravel()
gg = ((G1[:h, :w].reshape(sh).mean(axis=(1, 3)) +
       G2[:h, :w].reshape(sh).mean(axis=(1, 3))) / 2).ravel()
bb = B[:h, :w].reshape(sh).mean(axis=(1, 3)).ravel()

print(f"\n--- colour vs level, {rr.size} regions, lit take ---")
print("  ratios are WB-applied (AsShotNeutral); 1.00 = neutral\n")
print(f"  {'G level':>12} {'n':>6} | {'--- black=200 ---':^18} | {'--- black=measured ---':^22}")
print(f"  {'':>12} {'':>6} | {'R/G':>8} {'B/G':>8} | {'R/G':>10} {'B/G':>10}")
edges = [240, 300, 380, 460, 540, 620, 700, 780, 900, 1200, 2000, 3000]
for lo, hi in zip(edges[:-1], edges[1:]):
    m = (gg >= lo) & (gg < hi)
    if m.sum() < 10:
        continue
    out = []
    for blk in ((200, 200, 200), (dR, (dG1+dG2)/2, dB)):
        r = (rr[m].mean() - blk[0]) / AS_SHOT[0]
        g = (gg[m].mean() - blk[1]) / AS_SHOT[1]
        b = (bb[m].mean() - blk[2]) / AS_SHOT[2]
        out += [r/g, b/g]
    print(f"  {lo:5d}-{hi:5d} {m.sum():6d} | {out[0]:8.3f} {out[1]:8.3f} "
          f"| {out[2]:10.3f} {out[3]:10.3f}")
