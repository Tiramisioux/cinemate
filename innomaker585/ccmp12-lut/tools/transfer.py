#!/usr/bin/env python3
"""Direct transfer measurement from a 1-stop shutter pair (COLORCHECKER 8.9 in miniature).

Same scene, tripod, exposure ratio exactly 2. For every spatial region we hold
(code_A, code_B) = (f(2L), f(L)). No chart, no reference data, no register semantics.

If f is linear:            code_A - blk = 2*(code_B - blk)
If f has a knee at 500:    the relation bends hard there.
"""
import sys, glob
import numpy as np

OFF = 8
W, H = 3856, 2180


def unpack_tiff(buf):
    b = buf.reshape(-1, 3).astype(np.uint16)
    p0 = (b[:, 0] << 4) | (b[:, 1] >> 4)
    p1 = ((b[:, 1] & 0x0F) << 8) | b[:, 2]
    return np.stack([p0, p1], axis=1).reshape(H, W)


def load_avg(pattern, nmax=12):
    """Average N frames to cut read noise ~sqrt(N)."""
    files = sorted(glob.glob(pattern))[:nmax]
    acc = np.zeros((H, W), dtype=np.float64)
    for p in files:
        with open(p, "rb") as f:
            f.seek(OFF)
            acc += unpack_tiff(np.frombuffer(f.read(W * H * 3 // 2), dtype=np.uint8))
    return acc / len(files), len(files)


A, nA = load_avg(sys.argv[1])   # normal shutter  (2x the light)
B, nB = load_avg(sys.argv[2])   # half shutter    (1x)
print(f"A = {nA} frames averaged (normal shutter)")
print(f"B = {nB} frames averaged (half shutter)\n")

for label, X in (("A normal", A), ("B half", B)):
    print(f"{label}:  mean {X.mean():8.2f}  min {X.min():7.2f}  max {X.max():7.2f}   "
          + "  ".join(f"p{p}={np.percentile(X, p):.0f}" for p in (50, 90, 99, 99.9, 99.99)))

print("\n--- top of range: where does it clip? ---")
for label, X in (("A normal", A), ("B half", B)):
    for thr in (4095, 4090, 4049, 4040, 3900, 2000, 1000, 672, 556):
        n = int((X >= thr).sum())
        if n:
            print(f"  {label}: {n:9d} px >= {thr}  ({100*n/X.size:.4f}%)")
            break
    print(f"  {label}: absolute max = {X.max():.2f}")

# --- Region pairs: tile into blocks, one CFA channel (G1), means per block ---
BS = 16
g_a = A[0::2, 1::2]
g_b = B[0::2, 1::2]
h, w = (g_a.shape[0] // BS) * BS, (g_a.shape[1] // BS) * BS
ra = g_a[:h, :w].reshape(h // BS, BS, w // BS, BS).mean(axis=(1, 3)).ravel()
rb = g_b[:h, :w].reshape(h // BS, BS, w // BS, BS).mean(axis=(1, 3)).ravel()
print(f"\n{ra.size} regions of {BS}x{BS} G1 pixels")

# Black from the dark take, same channel.
BLK = 228.4
print(f"using black = {BLK} (measured, lens-cap take, G1)\n")

print("--- transfer: region code in B (1x) -> region code in A (2x) ---")
print("  if LINEAR, A-blk should be exactly 2.00x (B-blk)\n")
print(f"  {'B code':>9} {'n':>7} {'A code':>9} {'A-blk':>9} {'B-blk':>9} {'ratio':>7}")
edges = [230, 240, 260, 300, 350, 400, 450, 500, 550, 600, 672, 800,
         1000, 1400, 2000, 2800, 3600, 4096]
for lo, hi in zip(edges[:-1], edges[1:]):
    m = (rb >= lo) & (rb < hi)
    if m.sum() < 8:
        continue
    bm, am = rb[m].mean(), ra[m].mean()
    ratio = (am - BLK) / (bm - BLK) if bm > BLK + 1 else float("nan")
    flag = ""
    if lo <= 500 < hi:
        flag = "  <- knee1 (500) predicted here"
    if lo <= 672 < hi:
        flag = "  <- knee2 (C2 671.9) predicted here"
    print(f"  {lo:4d}-{hi:4d} {m.sum():7d} {am:9.2f} {am-BLK:9.2f} {bm-BLK:9.2f} {ratio:7.3f}{flag}")

print("\n--- global linear fit over unclipped regions ---")
m = (rb > BLK + 5) & (ra < 4000)
slope, icept = np.polyfit(rb[m] - BLK, ra[m] - BLK, 1)
resid = (ra[m] - BLK) - (slope * (rb[m] - BLK) + icept)
print(f"  A-blk = {slope:.4f} * (B-blk) + {icept:.2f}   over {m.sum()} regions")
print(f"  residual std {resid.std():.3f} codes, max |resid| {np.abs(resid).max():.2f}")
print(f"  -> a pure linear sensor response gives slope 2.000")
