#!/usr/bin/env python3
"""diagnose.py — IS THE A-vs-B REGION RELATION A FUNCTION?

    diagnose.py A_TAKE_DIR B_TAKE_DIR [--phase G1|all] [--block 8] [--limit N]

If two regions of the frame share a B code but land on different A codes, the
pair is not measuring a transfer curve — something spatial (motion, framing
shift, a moving specular, a blend that depends on more than the local level) is
in the way, and every downstream fit on that pair is void. Run this on a pair
BEFORE fitting it (handoff §3.2, §4).

Geometry, bit depth, black and white all come from `dngread.load`, so one
invocation serves 1928x1090 and 3856x2180, 12-bit and 16-bit. The two takes of a
leg must share geometry; they need not share bit depth — 2<->4 and 3<->5 are
exactly a 12-bit take against a 16-bit one.

CO-REGISTRATION IS NOT OPTIONAL. Every 12-bit take sits 20 sensor rows above the
16-bit take of the same resolution (handoff §2). That is invisible on a patch
plateau and worth 300 to 660 codes at a patch border — enough to make a
perfectly good pair look like it is not a function. `measure_offset` reads it
off the edge maps and `leg` applies it. Pass --no-register to see the damage.

THE TEST. Blocks are binned by B-above-black into narrow geometric bins. Inside
a bin a QUADRATIC is fitted, A = a + s*B + c*B^2, which removes the part of the
A spread that the B spread inside the bin legitimately explains -- including the
curvature, which a straight line would leave behind as a fake residual wherever
a bin straddles a knee. What is left is the residual, compared against the
measurement noise, propagated from the frame-to-frame scatter of both block
means. Photon noise is independent between the two takes, so B's own error
enters through the local slope:

    noise = sqrt( seA^2 + (s*seB)^2 )       se = temporal std / sqrt(nframes)

    resid_rms / noise  ~ 1     the relation is a function, at this precision
    resid_rms / noise  >> 1    it is not; do not fit this pair

Edge blocks straddle a patch border, so a sub-pixel framing difference between
the two takes puts them far off the curve for a reason that has nothing to do
with the transfer -- and block-averaging across a step turns mean(f(B)) into
something that is not f(mean(B)) as soon as f bends. They are excluded, counted,
never silently dropped. The filter is LEVEL-FAIR: a block is compared against
the median within-block spread of blocks at ITS OWN level, not against a fixed
fraction, because a fixed fraction throws away the dark end of the ramp and
keeps only the white chip. The left/right and top/bottom splits are the second,
independent question: at matched B, does A depend on WHERE in the frame it is?
"""
import os, sys, glob, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dngread import load  # noqa: E402

PHASES = ("R", "G1", "G2", "B")          # CFAPattern 0 1 1 2 = RGGB


def _phase_planes(codes):
    return dict(R=codes[0::2, 0::2], G1=codes[0::2, 1::2],
                G2=codes[1::2, 0::2], B=codes[1::2, 1::2])


def _reduce(plane, bs, sat=None):
    """Block mean, within-block pixel std, and SATURATED-PIXEL FRACTION.

    The fraction is the third plane because a mean cannot report clipping. A
    block that is 30% pinned at white has a mean well below white and passes a
    `mean >= white*0.999` test untouched -- while its mean is biased, one-sided,
    and by far more than the knee rounding of §4 ever was. Measured on the 17:05
    set, modes 0 and 1 have 8.8-11.3% of every CFA phase pinned at exactly 4095,
    with no soft roll-off (>=4090 and >=4095 differ by 0.01 points), so the
    threshold is the white level itself and its exact value is not delicate.
    """
    p = plane.astype(np.float64)
    h, w = (p.shape[0] // bs) * bs, (p.shape[1] // bs) * bs
    r = p[:h, :w].reshape(h // bs, bs, w // bs, bs)
    m = r.mean(axis=(1, 3))
    s = np.sqrt(np.maximum((r ** 2).mean(axis=(1, 3)) - m ** 2, 0.0))
    f = (r >= sat).mean(axis=(1, 3)) if sat is not None else np.zeros_like(m)
    return m, s, f


def _edge_map(plane, smooth=1):
    """Normalised gradient magnitude, moving-average smoothed.

    Peak r is ~0.98 on the binned pair and only ~0.14 on the full-res pair, and
    more smoothing does not move it. That is not a weak measurement: companding
    divides the 12-bit take's gradients by 64 through the middle segment, so the
    two edge maps genuinely differ in amplitude even where they agree in
    position. The POSITION is what is being read, and it is corroborated
    model-free by locating the white band's top edge in each take.
    """
    gy = np.abs(np.diff(plane, axis=0))[:, :-1]
    gx = np.abs(np.diff(plane, axis=1))[:-1, :]
    e = np.hypot(gx, gy)
    for _ in range(smooth):
        # A moving average, NOT a block average. Block-averaging is not shift
        # invariant, so it quietly biases the search toward offsets that are
        # multiples of the block size — it moved leg1 from -5 to -6 steps.
        s = np.zeros_like(e)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                s += np.roll(e, (dy, dx), (0, 1))
        e = s / 9.0
    return (e - e.mean()) / max(e.std(), 1e-9)


def measure_offset(a_take, b_take, phase="G1", r=16):
    """DEPRECATED -- per-phase offset. Use measure_offset_luma.

    Kept because it is what produced the offsets recorded in handoff §3.2a. It
    FAILS on the full-res leg's R and B planes: one phase plane of the 12-bit
    take carries a quarter of the photons and has its gradients divided by 64
    through the middle segment, so the correlation peak (r=0.14 even on G1)
    drops into the noise and the search walks to the corner of its box at
    r=-0.29. It does not raise; it returns a wrong offset.

    Vertical/horizontal offset between two takes, in PHASE-PLANE steps.

    THE 12-BIT AND 16-BIT TAKES ARE NOT CO-REGISTERED. Measured on both chart
    sessions: every 12-bit take (modes 0,1,2,3) sits exactly 20 SENSOR ROWS
    above its 16-bit counterpart (modes 4,5) -- 10 raw rows binned, 20 raw rows
    full res, dx = 0, replicated to 0.1 px. Confirmed model-free by locating the
    top edge of the white band: raw row 155.04 in mode 3 against 174.87 in mode
    5. Left uncorrected it does nothing to a patch plateau and everything to a
    patch BORDER, which is why the unfiltered residual runs to hundreds of codes.

    Correlates edge maps, so it is indifferent to the transfer curve between the
    two takes -- which is the thing under test and must not be assumed here.
    The offset is even in raw pixels, so the CFA phase is preserved.
    """
    def emap(take):
        f = sorted(glob.glob(os.path.join(take, "*.dng")))[0]
        d = load(f)
        return _edge_map(_phase_planes(d["codes"])[phase].astype(np.float64)
                         - d["black"][0])
    EA, EB = emap(a_take), emap(b_take)
    H, W = EA.shape
    best = (-2.0, 0, 0)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            u = EA[r + dy:H - r + dy, r + dx:W - r + dx]
            v = EB[r:H - r, r:W - r]
            c = float((u * v).mean() / (u.std() * v.std()))
            if c > best[0]:
                best = (c, dy, dx)
    return best[1], best[2], best[0]


def _luma(take, limit=3):
    """Frame-averaged 4-phase mean: the scene at half resolution, no CFA comb.

    One phase plane is a quarter of the photons and, on the 12-bit take, has its
    gradients divided by 64 through the middle segment. Averaging the four
    phases restores the signal and removes the CFA modulation, which is periodic
    at 2 raw px and therefore contributes the SAME correlation at every even
    shift -- pure dilution of the peak.
    """
    files = sorted(glob.glob(os.path.join(take, "*.dng")))[:limit]
    acc = None
    for f in files:
        d = load(f)
        pl = _phase_planes(d["codes"])
        L = (pl["R"].astype(np.float64) + pl["G1"] + pl["G2"] + pl["B"]) / 4.0
        acc = L - d["black"][0] if acc is None else acc + (L - d["black"][0])
    return acc / len(files)


def measure_offset_luma(a_take, b_take, r=24, limit=3):
    """Take offset in PHASE-PLANE steps, measured once per LEG, not per phase.

    The 12-bit crop origin sits 20 sensor rows off the 16-bit one (handoff §2) --
    10 phase steps at full res, 5 binned, dx = 0, replicated to 0.1 px on both
    sessions and corroborated model-free by the white band's top edge. That is a
    property of the READOUT, so one offset serves all four CFA phases.

    diagnose.measure_offset searches per phase off a single phase plane. On G1
    that peaks at r = 0.14; on R it walks to the corner of the search box at
    r = -0.29, i.e. it fails, silently, and every number fitted after it is void.
    Correlating the luma instead lifts the peak by an order of magnitude and
    makes the margin over the runner-up visible so a failure cannot pass unseen.

    Returns (dy, dx, peak, margin, top3). Correlating EDGE MAPS keeps this
    indifferent to the transfer curve between the takes -- the thing under test.
    """
    EA, EB = _edge_map(_luma(a_take, limit)), _edge_map(_luma(b_take, limit))
    H, W = EA.shape
    scores = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            u = EA[r + dy:H - r + dy, r + dx:W - r + dx]
            v = EB[r:H - r, r:W - r]
            scores.append((float((u * v).mean() / (u.std() * v.std())), dy, dx))
    scores.sort(reverse=True)
    best = scores[0]
    # margin over the best candidate that is not a near neighbour of the peak
    far = [s for s in scores if abs(s[1] - best[1]) > 2 or abs(s[2] - best[2]) > 2]
    margin = best[0] - (far[0][0] if far else 0.0)
    return best[1], best[2], best[0], margin, scores[:3]


_CACHE = {}


def block_stats(take, bs=16, limit=None, phases=PHASES, shift=(0, 0)):
    """Per-block mean, temporal std and within-block std for one take.

    Memory-light: only the per-frame BLOCK arrays are kept, never the frames.
    Memoised, because --phase all would otherwise re-read every DNG four times.
    Returns (meta, {phase: dict(mean, tstd, sstd, se)}).
    """
    key = (os.path.abspath(take), bs, limit, tuple(sorted(phases)), shift)
    for k, v in _CACHE.items():
        if k[:3] == key[:3] and k[4] == shift and set(phases) <= set(k[3]):
            return v[0], {p: v[1][p] for p in phases}
    files = sorted(glob.glob(os.path.join(take, "*.dng")))[:limit]
    if not files:
        raise SystemExit(f"no DNGs in {take}")
    per = {k: [] for k in phases}
    sstd = {k: [] for k in phases}
    satf = {k: [] for k in phases}
    d0 = None
    for f in files:
        d = load(f)
        if d0 is None:
            d0 = d
            satlvl = float(d0["white"][0] if d0["white"]
                           else (1 << d0["bits"]) - 1)
        elif (d["w"], d["h"], d["bits"]) != (d0["w"], d0["h"], d0["bits"]):
            raise SystemExit(f"{f}: geometry changes inside a take")
        pl = _phase_planes(d["codes"])
        if shift != (0, 0):        # co-register; offset is even in raw px, so
            pl = {k: np.roll(v, shift, (0, 1))      # the CFA phase is preserved
                  for k, v in pl.items()}
        for k in phases:
            m, s, sf = _reduce(pl[k], bs, satlvl)
            per[k].append(m)
            sstd[k].append(s)
            satf[k].append(sf)
    n = len(files)
    out = {}
    for k in phases:
        a = np.stack(per[k])
        mean = a.mean(axis=0)
        tstd = a.std(axis=0, ddof=1) if n > 1 else np.zeros_like(mean)
        # MAX over frames, not mean: a block that clipped in any frame has a
        # biased time-average, so averaging the fraction would dilute exactly
        # the evidence the guard exists to act on.
        out[k] = dict(mean=mean, tstd=tstd, se=tstd / np.sqrt(n),
                      sstd=np.mean(sstd[k], axis=0),
                      satfrac=np.max(satf[k], axis=0))
    meta = dict(take=os.path.basename(take.rstrip("/")), nframes=n, bs=bs,
                w=d0["w"], h=d0["h"], bits=d0["bits"],
                black=float(d0["black"][0]), white=satlvl,
                grid=out[phases[0]]["mean"].shape, shift=shift)
    _CACHE[key] = (meta, out)
    return meta, out


def _fit_resid(x, y, deg=2):
    """Local polynomial fit; returns the slope at the bin centre and residuals.

    Quadratic, not linear: a bin that straddles a knee has real curvature, and a
    straight line would report that curvature as a residual it did not earn.
    """
    if x.size < deg + 3 or x.max() - x.min() < 1e-12:
        return np.nan, y - y.mean()
    xm = x.mean()
    c = np.polyfit(x - xm, y, deg)
    return float(c[-2]), y - np.polyval(c, x - xm)


def _edge_mask(level, sstd, nlev=24, k=2.0):
    """Level-fair flatness filter.

    A block is an edge block if its interior spread is far above what blocks at
    ITS OWN level normally show. Comparing against a fixed fraction of level
    instead would reject the dark half of the ramp on principle and keep the
    white chip -- which is what a fixed 2% threshold did, 171 blocks of 2040,
    all of them the big white band.
    """
    ok = np.zeros(level.shape, bool)
    pos = level > 0
    if pos.sum() < nlev * 4:
        return sstd <= k * np.median(sstd[pos]) if pos.any() else ok
    q = np.quantile(level[pos], np.linspace(0, 1, nlev + 1))
    for i in range(nlev):
        lo, hi = q[i], q[i + 1]
        m = pos & (level >= lo) & (level <= hi)
        if m.sum() < 4:
            continue
        ok |= m & (sstd <= k * np.median(sstd[m]))
    return ok


def _plateau(level, tol=0.02):
    """Does the block sit INSIDE a flat region, not merely look flat itself?

    A chart border is soft — lens MTF spreads it over more than one block — so
    the block just inside the border passes a within-block spread test while
    still covering part of the step. Those blocks are exactly the ones that came
    out 3 to 10 codes low, because averaging across a step of a curve with a
    knee in it does not commute with the curve. Require every 8-neighbour to
    share the level.
    """
    ok = np.ones(level.shape, bool)
    lv = np.maximum(level, 1.0)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ok &= np.abs(np.roll(np.roll(level, dy, 0), dx, 1) - level) / lv < tol
    ok[0] = ok[-1] = False
    ok[:, 0] = ok[:, -1] = False
    return ok


def leg(a_take, b_take, phase="G1", bs=8, limit=None, nbins=20, flat=2.0,
        plateau=0.02, verbose=True, nofilter=False, register=True, satmax=0.0):
    dy = dx = 0
    r = float("nan")
    if register:
        # ONE offset per LEG, off the luma -- not one per CFA phase. The crop
        # origin is a property of the readout, so a per-phase answer that
        # disagrees across phases is a failed search, not four measurements.
        # measure_offset on a single phase plane peaks at r=0.14 on G1 of the
        # full-res leg and WALKS TO THE CORNER of its search box at r=-0.29 on
        # R and B -- silently returning dy=+16 dx=-16 instead of dy=-10 dx=0.
        # Every number fitted downstream of that is void.
        dy, dx, r, _margin, _top = measure_offset_luma(a_take, b_take)
    ma, sa = block_stats(a_take, bs, limit, (phase,), shift=(-dy, -dx))
    mb, sb = block_stats(b_take, bs, limit, (phase,))
    if (ma["w"], ma["h"]) != (mb["w"], mb["h"]):
        raise SystemExit(f"geometry differs: A {ma['w']}x{ma['h']} vs "
                         f"B {mb['w']}x{mb['h']} — not a leg")

    A, B = sa[phase], sb[phase]
    a = A["mean"] - ma["black"]
    b = B["mean"] - mb["black"]
    seA, seB = A["se"], B["se"]

    # Edge blocks: level-fair filter, each block judged against the blocks that
    # share its level. A sub-pixel framing difference throws an edge block off
    # the curve for a reason that is not the curve.
    flatmask = np.ones(a.shape, bool) if nofilter else (
        _edge_mask(b, A["sstd"], k=flat) & _edge_mask(b, B["sstd"], k=flat)
        & _plateau(b, plateau) & _plateau(a, plateau))
    # np.roll wraps, so the block rows/cols the shift dragged round are garbage
    wrap = np.zeros(a.shape, bool)
    ny, nx = int(np.ceil(abs(dy) / bs)) + 1, int(np.ceil(abs(dx) / bs)) + 1
    wrap[:ny] = wrap[-ny:] = True
    wrap[:, :nx] = wrap[:, -nx:] = True
    flatmask &= ~wrap
    # and never let a CLIPPED block into the test. `mean >= white*0.999` does
    # not do this: a block 30% pinned at white has a mean far below white and
    # passes, carrying a one-sided bias larger than the knee rounding. Reject on
    # the measured saturated-pixel fraction. satmax=0 rejects a block containing
    # a single pinned pixel; --satmax sweeps it and the answer must not move.
    sat = (A["satfrac"] > satmax) | (B["satfrac"] > satmax)
    keep = flatmask & ~sat & (b > 0)

    if verbose:
        print("=" * 92)
        print(f"LEG  A = {ma['take']}   ({ma['w']}x{ma['h']} {ma['bits']}b, "
              f"black {ma['black']:.0f}, {ma['nframes']} frames)")
        print(f"     B = {mb['take']}   ({mb['w']}x{mb['h']} {mb['bits']}b, "
              f"black {mb['black']:.0f}, {mb['nframes']} frames)")
        print(f"     co-registration: A shifted dy={-dy:+d} dx={-dx:+d} phase steps "
              f"(= {-2*dy:+d} raw rows, r={r:.3f}) — the 12-bit takes sit 20 sensor "
              f"rows off the 16-bit ones")
        print(f"     phase {phase}, {bs}x{bs} blocks on the phase plane "
              f"(= {2*bs}x{2*bs} raw px), grid {ma['grid'][0]}x{ma['grid'][1]}")
        print(f"     blocks {a.size}   flat+plateau {int(flatmask.sum())}   "
              f"clipped {int(sat.sum())} (satfrac > {satmax:g}; A "
              f"{int((A['satfrac'] > satmax).sum())}, B "
              f"{int((B['satfrac'] > satmax).sum())})   USED {int(keep.sum())}")
        print(f"     block-mean standard error: A {np.median(seA[keep]):.3f}  "
              f"B {np.median(seB[keep]):.3f} codes (median over used blocks)")

    if keep.sum() < 50:
        raise SystemExit(f"only {int(keep.sum())} blocks survive the filters — "
                         f"loosen --flat or shrink --block; refusing to judge on this")
    x, y = b[keep], a[keep]
    ex, ey = seB[keep], seA[keep]
    order = np.argsort(x)
    x, y, ex, ey = x[order], y[order], ex[order], ey[order]

    # GEOMETRIC bins, not equal-count. Equal-count bins put half the bins inside
    # the big white chip, because that chip is a third of the frame; geometric
    # bins walk the ramp.
    lo0, hi0 = np.percentile(x, 0.5), np.percentile(x, 99.8)
    edges = np.geomspace(max(lo0, 1.0), hi0, nbins + 1)
    rows = []
    if verbose:
        print(f"\n  geometric bins on B-above-black, quadratic fitted inside each bin")
        print(f"  {'B lo':>9}{'B hi':>9}{'w%':>6}{'n':>6}{'A mean':>10}{'slope':>9}"
              f"{'resid rms':>11}{'resid p5-95':>12}{'noise':>8}{'RATIO':>8}")
    for i in range(nbins):
        m = (x >= edges[i]) & (x < edges[i + 1])
        if m.sum() < 8:
            continue
        xb, yb, exb, eyb = x[m], y[m], ex[m], ey[m]
        s, res = _fit_resid(xb, yb)
        rms = float(np.sqrt((res ** 2).mean()))
        spread = float(np.percentile(res, 95) - np.percentile(res, 5))
        noise = float(np.sqrt(np.median(eyb) ** 2 + (s * np.median(exb)) ** 2)) \
            if np.isfinite(s) else float(np.median(eyb))
        ratio = rms / noise if noise > 0 else np.inf
        w = 100 * (xb.max() - xb.min()) / max(xb.mean(), 1e-9)
        rows.append(dict(lo=float(xb.min()), hi=float(xb.max()), n=int(xb.size),
                         amean=float(yb.mean()), slope=float(s), rms=rms,
                         spread=spread, noise=noise, ratio=float(ratio)))
        if verbose:
            print(f"  {xb.min():9.1f}{xb.max():9.1f}{w:6.1f}{xb.size:6d}"
                  f"{yb.mean():10.1f}{s:9.4f}{rms:11.3f}{spread:12.3f}"
                  f"{noise:8.3f}{ratio:8.1f}")
    return dict(meta_a=ma, meta_b=mb, rows=rows, x=x, y=y, keep=keep,
                a=a, b=b, seA=seA, seB=seB)


def global_curve(b, a, keep, nk=80):
    """Monotone reference curve A(B) from the used blocks: median per geometric
    knot, then linear interpolation. Only a yardstick for the split test."""
    x, y = b[keep], a[keep]
    o = np.argsort(x)
    x, y = x[o], y[o]
    e = np.geomspace(max(x[0], 1e-6), x[-1], nk + 1)
    kx, ky = [], []
    for i in range(nk):
        m = (x >= e[i]) & (x < e[i + 1])
        if m.sum() >= 3:
            kx.append(np.median(x[m])); ky.append(np.median(y[m]))
    return np.array(kx), np.array(ky)


def spatial_split(res, nbins=8):
    """At matched B, does A depend on WHERE in the frame the block is?

    Compare RESIDUALS about the global curve, not raw A means. Raw means inside
    a band are worthless here: the two halves do not hold the same distribution
    of B inside the band, and on a steep part of the curve that alone produces a
    50% apparent difference that has nothing to do with position.
    """
    a, b, keep = res["a"], res["b"], res["keep"]
    kx, ky = global_curve(b, a, keep)
    resid = a - np.interp(b, kx, ky)
    lvl = np.interp(b, kx, ky)

    gh, gw = a.shape
    halves = dict(left=np.zeros_like(keep), right=np.zeros_like(keep),
                  top=np.zeros_like(keep), bottom=np.zeros_like(keep))
    halves["left"][:, :gw // 2] = True
    halves["right"][:, gw // 2:] = True
    halves["top"][:gh // 2, :] = True
    halves["bottom"][gh // 2:, :] = True

    q = np.quantile(b[keep], np.linspace(0, 1, nbins + 1))
    print(f"\n  same question, spatially — residual about the global curve, per half")
    print(f"  {'B range':>21}{'A':>8}{'left':>8}{'right':>8}{'L-R':>8}"
          f"{'top':>8}{'bottom':>8}{'T-B':>8}   codes, and L-R/T-B as % of A")
    worst = 0.0
    for i in range(nbins):
        lo, hi = q[i], q[i + 1]
        band = keep & (b >= lo) & (b < hi)
        if band.sum() < 12:
            continue
        v = {}
        for k, m in halves.items():
            sel = band & m
            v[k] = resid[sel].mean() if sel.sum() >= 5 else np.nan
        al = lvl[band].mean()
        lr, tb = v["left"] - v["right"], v["top"] - v["bottom"]
        for d in (lr, tb):
            if np.isfinite(d):
                worst = max(worst, abs(100 * d / max(al, 1e-9)))
        print(f"  {lo:9.1f}-{hi:9.1f}{al:8.1f}{v['left']:8.2f}{v['right']:8.2f}"
              f"{100*lr/al:7.2f}%{v['top']:8.2f}{v['bottom']:8.2f}{100*tb/al:7.2f}%")
    print(f"  worst half-to-half disparity at matched B: {worst:.2f}% of A")
    return worst


def static_check(take, bs=16, limit=None, phase="G1"):
    """Is the scene static WITHIN the take? Drift here voids the take, not the pair."""
    files = sorted(glob.glob(os.path.join(take, "*.dng")))[:limit]
    m0 = None
    d = []
    for i, f in enumerate(files):
        pl = _phase_planes(load(f)["codes"])
        m, _, _ = _reduce(pl[phase], bs)
        if i == 0:
            m0 = m
        else:
            d.append(float(np.abs(m - m0).mean()))
    lvl = float(m0.mean())
    return d, lvl


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--phase", default="G1", choices=list(PHASES) + ["all"])
    ap.add_argument("--block", type=int, default=8)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--bins", type=int, default=20)
    ap.add_argument("--flat", type=float, default=2.0,
                    help="edge filter: reject a block whose within-block spread "
                         "exceeds this multiple of the median at its own level")
    ap.add_argument("--plateau", type=float, default=0.02,
                    help="max relative level step to an 8-neighbour block")
    ap.add_argument("--no-split", action="store_true")
    ap.add_argument("--no-register", action="store_true",
                    help="skip co-registration — shows what the 20-row offset costs")
    ap.add_argument("--satmax", type=float, default=0.0,
                    help="reject a block whose saturated-pixel fraction exceeds "
                         "this; 0 rejects any block with a single pinned pixel")
    args = ap.parse_args()

    print("--- is the scene static WITHIN each take? (mean |block_i - block_0|) ---")
    for lbl, t in (("A", args.a), ("B", args.b)):
        d, lvl = static_check(t, args.block, args.limit)
        if d:
            print(f"  {lbl}: {min(d):.2f}..{max(d):.2f} codes over {len(d)+1} frames "
                  f"= {100*max(d)/max(lvl,1):.3f}% of the take's mean level")

    phases = PHASES if args.phase == "all" else (args.phase,)
    for ph in phases:
        r = leg(args.a, args.b, ph, args.block, args.limit, args.bins,
                args.flat, args.plateau, register=not args.no_register,
                satmax=args.satmax)
        rr = [q["ratio"] for q in r["rows"]]
        rel = [100 * q["spread"] / max(q["amean"], 1e-9) for q in r["rows"]]
        print(f"\n  VERDICT ({ph}): resid/noise  median {np.median(rr):.1f}  "
              f"max {max(rr):.1f}   over {len(rr)} bins")
        print(f"    A-spread inside a bin, B-spread removed: "
              f"max {max(q['spread'] for q in r['rows']):.2f} codes "
              f"= {max(rel):.2f}% of A   "
              f"(§4's void bracket: 10-114 codes against ~1 code of precision)")
        # The filter must not be what produces the pass. Same test, every block.
        for lbl, kw in (("co-registered", {}), ("NOT co-registered", dict(register=False))):
            u = leg(args.a, args.b, ph, args.block, args.limit, args.bins,
                    verbose=False, nofilter=True, satmax=args.satmax, **kw)
            ur = [q["ratio"] for q in u["rows"]]
            print(f"    UNFILTERED ({lbl}), all {u['a'].size} blocks incl. every "
                  f"patch border: resid/noise median {np.median(ur):.0f} "
                  f"max {max(ur):.0f}, max spread "
                  f"{max(q['spread'] for q in u['rows']):.1f} codes")
        if not args.no_split:
            spatial_split(r)


if __name__ == "__main__":
    main()
