#!/usr/bin/env python3
"""fitcurve.py — §3.2. SOLVE the CCMP transfer with the pedestal and b FREE.

    fitcurve.py A_TAKE B_TAKE [--phase all] [--block 8] [--json out.json]

A is the 12-bit ClearHDR take (mode 2 or 3), B the 16-bit linear ClearHDR take
of the SAME resolution (mode 4 or 5). Co-registration is mandatory and automatic
(handoff §2); the offset is measured off the edge maps, so it never assumes the
transfer curve that is under test.

THE MODEL, and every symbol in it

    A(x) = P + ccmp(b*x)/b            x = B_code - K   (16-bit, above black)
                                      P = the 12-bit pedestal      -- SOLVED
                                      b = the binning factor       -- SOLVED
    ccmp(u) = u                              u <= T1
            = T1 + (u-T1)*s1                 T1 < u <= T2
            = T1 + (T2-T1)*s1 + (u-T2)*s2    u > T2

which is three straight lines in x, with knots at t1 = T1/b and t2 = T2/b:

    seg 0   A = a0 + m0*x     m0 = 1       a0 = P
    seg 1   A = a1 + m1*x     m1 = s1      a1 = P + t1*(1-s1)
    seg 2   A = a2 + m2*x     m2 = s2      a2 = P + t1*(1-s1) + t2*(s1-s2)

NOTHING here is fixed. The three slopes are fitted free -- 1, 1/64 and 1/16 are
predictions to be checked, not inputs. The knots are NEVER measured from the
data directly; they FALL OUT of the slope intersections:

    t1 = (a0-a1)/(m1-m0)        t2 = (a1-a2)/(m2-m1)

and P and b then follow:

    P  = a0                          (seg 0 present: read straight off)
    P  = a1 - t1*(1-m1)              (seg 0 absent: from seg 1 and t1)
    b  = T1_reg/t1  and  T2_reg/t2   (registers 500 / 11500, read on hardware)

WHY THE KNOTS ARE NOT MEASURED DIRECTLY (handoff §4, last bullet). A region mean
is BIASED near a knee. Within-block photon noise straddles the bend even when
the block mean does not, and averaging does not commute with a bend, so the
transition is rounded over about the pixel noise width and any knot read off it
is pulled toward the middle segment. So the knee neighbourhood is EXCLUDED from
the fit and the knots are recovered from the segments either side.

THE GUARD IS PHYSICAL, NOT A FUDGE FACTOR. A block is contaminated exactly when
its pixels straddle the knee, i.e. when |x - t| is small compared with the
block's OWN within-block spread. So the guard is

    guard(block) = k * sx(block)         sx = within-block pixel std, measured

per block, not a fixed fraction of level. It widens by itself on a patch border
and at the bright end where photon noise is large, and it collapses to nothing
on a dark plateau. --kguard sweeps k; the answer must not move.

ANTI-CIRCULARITY. The knots are found by iterating segmentation -> fit ->
intersection to a fixed point. --seed-sweep starts that iteration from a grid of
deliberately wrong knot pairs and reports the basin: if every seed lands on the
same fixed point, the register values were not smuggled into the answer through
the seed.
"""
import os, sys, glob, json, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dngread import load                                          # noqa: E402
from diagnose import (measure_offset_luma, block_stats,            # noqa: E402
                      _edge_mask, _edge_map, _phase_planes)
import modes as M                                                 # noqa: E402

PHASES = ("R", "G1", "G2", "B")
T1_REG, T2_REG = 500.0, 11500.0        # hardware, --get-ctrl with ClearHDR live
S1_REG, S2_REG = 1.0 / 64, 1.0 / 16    # ACMP1 idx 6, ACMP2 idx 4; ratio = 1/2^idx
# Max fractional spread among the three independent estimates of g before the
# phase is declared a failed segmentation rather than a measurement. Set from
# what the §3.2 legs -- where g is 1 by construction -- actually deliver: their
# worst spread is 0.019 on a g of 1, i.e. 1.9%. 5% is that with room, and it is
# swept in robust.py.
G_TOL = 0.05




_OFF = {}


# ── data assembly ───────────────────────────────────────────────────────────
def _plateau(level, rel=0.02, absol=20.0):
    """Does the block sit INSIDE a flat region? Relative OR absolute tolerance.

    diagnose.py's version is relative-only, which at the dark end means a
    tolerance of a couple of codes and throws the whole low segment away -- and
    the low segment is where the pedestal lives. The absolute floor keeps it.
    """
    ok = np.ones(level.shape, bool)
    tol = np.maximum(rel * np.maximum(level, 0.0), absol)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == dx == 0:
                continue
            ok &= np.abs(np.roll(np.roll(level, dy, 0), dx, 1) - level) < tol
    ok[0] = ok[-1] = False
    ok[:, 0] = ok[:, -1] = False
    return ok


def _geom(take):
    """(w, h) of a take, from its first frame."""
    f = sorted(glob.glob(os.path.join(take, "*.dng")))
    if not f:
        raise SystemExit(f"no DNGs in {take}")
    d = load(f[0])
    return d["w"], d["h"]


def mode_of(take):
    name = os.path.basename(take.rstrip("/"))
    for prefix, (m, label, linear) in M.ALL_MODES.items():
        if name.startswith(prefix):
            return m, label
    raise SystemExit(f"unrecognised take {name!r}")


def leg_points(a_take, b_take, phase, bs=8, limit=None, flat=2.0, rel=0.02,
               absol=20.0, register=True, measured_black=True, satmax=0.0):
    """Co-registered block pairs for one leg and one CFA phase.

    y is the RAW A code -- the pedestal is what we are solving for, so nothing
    is subtracted from it. x is B above ITS OWN black.
    """
    ma_mode, ma_label = mode_of(a_take)
    mb_mode, mb_label = mode_of(b_take)
    dy = dx = 0
    r = margin = float("nan")
    # Geometry FIRST. measure_offset_luma correlates the two frames, so a
    # mispaired leg (mode 3 against mode 4, say) dies there with a numpy
    # broadcast error that names neither take.
    ga, gb = _geom(a_take), _geom(b_take)
    if ga != gb:
        raise SystemExit(
            f"geometry differs — not a leg:\n"
            f"  A {os.path.basename(a_take.rstrip('/'))}  mode {ma_mode}  "
            f"{ga[0]}x{ga[1]}\n"
            f"  B {os.path.basename(b_take.rstrip('/'))}  mode {mb_mode}  "
            f"{gb[0]}x{gb[1]}\n"
            f"  binned modes are {M.BINNED_MODES}, full res {M.FULL_MODES}")
    if register:
        key = (os.path.abspath(a_take), os.path.abspath(b_take))
        if key not in _OFF:
            _OFF[key] = measure_offset_luma(a_take, b_take)
        dy, dx, r, margin, top3 = _OFF[key]
    # Ask for all four phases so the memoised reader loads each DNG once per
    # leg instead of once per phase.
    ma, sa = block_stats(a_take, bs, limit, PHASES, shift=(-dy, -dx))
    mb, sb = block_stats(b_take, bs, limit, PHASES)
    if (ma["w"], ma["h"]) != (mb["w"], mb["h"]):
        raise SystemExit("geometry differs — not a leg")

    A, B = sa[phase], sb[phase]
    K = (M.MEASURED_BLACK[mb_mode][phase] if measured_black else mb["black"])
    x = B["mean"] - K
    y = A["mean"]                                   # raw code, pedestal intact

    # The plateau test is asked of the SCENE (the B plane) only. Asking it of A
    # as well double-counts and, worse, is segment-asymmetric: on the slope-1
    # segment a 20-code scene step is a 20-code A step and fails, while on the
    # 1/64 segment the same step is 0.3 codes and passes. That would filter the
    # low segment far harder than the middle one and bias exactly the comparison
    # this fit exists to make.
    keep = (_edge_mask(x, A["sstd"], k=flat) & _edge_mask(x, B["sstd"], k=flat)
            & _plateau(x, rel, absol))
    ny = int(np.ceil(abs(dy) / bs)) + 1             # np.roll wraps; those rows
    nx = int(np.ceil(abs(dx) / bs)) + 1             # are garbage
    keep[:ny] = keep[-ny:] = False
    keep[:, :nx] = keep[:, -nx:] = False
    # CLIPPING GUARD. `mean < white*0.999` does not reject a clipped block: a
    # block 30% pinned at white has a mean far below white and passes, with its
    # mean biased low, one-sided, and by more than the knee rounding of §4. In
    # the 17:05 set modes 0 and 1 have 8.8-11.3% of every CFA phase pinned at
    # 4095, so this matters on the §3.3 legs and not at all on §3.2's, where the
    # 16-bit take never approaches its ceiling. Reject on the measured fraction;
    # satmax=0 rejects any block containing a single pinned pixel.
    keep &= (A["satfrac"] <= satmax) & (B["satfrac"] <= satmax)
    nclip = int(((A["satfrac"] > satmax) | (B["satfrac"] > satmax)).sum())
    keep &= x > 0

    meta = dict(a_take=ma["take"], b_take=mb["take"], a_mode=ma_mode,
                b_mode=mb_mode, label=ma_label, phase=phase, bs=bs,
                w=ma["w"], h=ma["h"], a_bits=ma["bits"], b_bits=mb["bits"],
                a_black_tag=ma["black"], b_black_used=K, b_black_tag=mb["black"],
                nframes_a=ma["nframes"], nframes_b=mb["nframes"],
                dy=int(dy), dx=int(dx), corr=float(r), margin=float(margin),
                nblocks=int(x.size), nused=int(keep.sum()),
                satmax=float(satmax), nclipped=nclip)
    grid = np.indices(x.shape)
    return dict(meta=meta, x=x[keep], y=y[keep], sx=B["sstd"][keep],
                ex=B["se"][keep], ey=A["se"][keep],
                gy=grid[0][keep], gx=grid[1][keep], shape=x.shape)


# ── the fit ─────────────────────────────────────────────────────────────────
def wls_line(x, y, ex, ey, m_init=0.0, iters=12):
    """Line fit with errors in BOTH variables (B's error enters via the slope).

    Covariance is scaled by chi2/dof, so a segment whose scatter exceeds the
    propagated measurement noise reports a correspondingly larger uncertainty
    instead of a falsely tight one.
    """
    m = m_init
    a = 0.0
    w = None
    for _ in range(iters):
        w = 1.0 / (ey ** 2 + (m * ex) ** 2 + 1e-12)
        Sw, Sx, Sy = w.sum(), (w * x).sum(), (w * y).sum()
        Sxx, Sxy = (w * x * x).sum(), (w * x * y).sum()
        den = Sw * Sxx - Sx * Sx
        if abs(den) < 1e-30:
            return dict(a=np.nan, m=np.nan, n=x.size)
        mn = (Sw * Sxy - Sx * Sy) / den
        a = (Sy - mn * Sx) / Sw
        if abs(mn - m) < 1e-14:
            m = mn
            break
        m = mn
    res = y - (a + m * x)
    dof = max(x.size - 2, 1)
    chi2 = float((w * res ** 2).sum() / dof)
    Sw, Sx, Sxx = w.sum(), (w * x).sum(), (w * x * x).sum()
    den = Sw * Sxx - Sx * Sx
    return dict(a=float(a), m=float(m), n=int(x.size), chi2=chi2,
                va=float(Sxx / den * chi2), vm=float(Sw / den * chi2),
                cam=float(-Sx / den * chi2),
                rms=float(np.sqrt((res ** 2).mean())),
                xlo=float(x.min()), xhi=float(x.max()),
                noise=float(np.sqrt(np.median(ey) ** 2 + (m * np.median(ex)) ** 2)))


def _cross(sa, sb):
    """Where two fitted lines cross, or NaN if their slopes are not separated
    by more than the noise on them."""
    if not (np.isfinite(sa["m"]) and np.isfinite(sb["m"])):
        return np.nan
    v = sa.get("vm", np.nan) + sb.get("vm", np.nan)
    if not np.isfinite(v) or abs(sb["m"] - sa["m"]) <= 3 * np.sqrt(max(v, 0.0)):
        return np.nan
    return (sa["a"] - sb["a"]) / (sb["m"] - sa["m"])


def _between(sa, sb, t):
    """Does the crossing lie in the gap the two segments bracket?"""
    return bool(np.isfinite(t) and "xhi" in sa and "xlo" in sb
                and sa["xhi"] <= t <= sb["xlo"])


def _accept(sa, sb, t, knot_tol):
    """Is this crossing a KNOT? Two necessary tests, neither sufficient alone.

    1. It lies in the gap the two segments bracket (§3.2e). Two lines always
       cross somewhere; a crossing outside that gap is an extrapolation.
    2. Its own formal error is small compared with itself. Two chunks of the
       SAME real segment, split by a wandering iteration, ALSO cross inside
       their own gap -- at an arbitrary place, with an error bar the size of
       the answer. §3.2's knots came out to 0.02-0.16% of themselves and never
       needed this; §3.3's compressed x range throws up t1 = 121.2 +/- 51.2,
       and that 42% is the tool saying the segmentation failed.
    """
    if not _between(sa, sb, t):
        return False
    se = _knot_se(sa, sb, t)
    return bool(np.isfinite(se) and se <= knot_tol * abs(t))


def _identify(m_lo, m_hi):
    """WHICH knot separates two adjacent segments? Read it off the SLOPE RATIO.

    The three model slopes are g, g*s1 and g*s2, so the two possible adjacent
    pairs are separated by ratios that could hardly be further apart:

        (seg0, seg1)   m_hi/m_lo = (g*s1)/g     = s1     = 1/64 = 0.0156
        (seg1, seg2)   m_hi/m_lo = (g*s2)/(g*s1) = s2/s1 = 4

    Both are REGISTER values (ACMP1 menu idx 6, ACMP2 idx 4) and g cancels out
    of both, so this identification needs neither g nor b nor the thresholds --
    only that the two ratios differ by a factor of 256.

    It is needed because the iteration is seeded, and a seed that lands badly
    gives an off-by-one assignment that is entirely self-consistent as a
    piecewise-linear fit: on 17:05's full-res leg, phase G1, the slope-g segment
    landed in seg1 and the 1/64 segment in seg2, reporting g1 = 64*1.846 = 118
    and g2 = 16*0.0294 = 0.47 while phase R of the SAME leg got it right. The
    measured ratio there is 0.0294/1.846 = 1/62.8, which is 1/64 and not 4.
    Returns 1 if the knot is t1, 2 if it is t2, None if undecidable.
    """
    if not (np.isfinite(m_lo) and np.isfinite(m_hi)) or m_lo <= 0 or m_hi <= 0:
        return None
    r = np.log(m_hi / m_lo)
    return 1 if abs(r - np.log(S1_REG)) < abs(r - np.log(S2_REG / S1_REG)) else 2


def fit3(P, t1, t2, kguard=4.0, iters=60, minseg=25, damp=1.0, knot_tol=0.05):
    """Segment -> fit -> intersect, to a fixed point. Knots are never measured.

    Returns the three segment fits and the knots they intersect at. Segment 0 is
    allowed to be empty: mode 2's darkest patch sits above its own knee1, so the
    binned leg has no slope-1 data and P has to come from segment 1 instead.
    """
    x, y, ex, ey, sx = P["x"], P["y"], P["ex"], P["ey"], P["sx"]
    seg = [None, None, None]
    msk = [None, None, None]
    conv = False
    for it in range(iters):
        g = kguard * sx
        msk = [x < t1 - g, (x > t1 + g) & (x < t2 - g), x > t2 + g]
        init = (1.0, 1.0 / 64, 1.0 / 16)
        for i, mk in enumerate(msk):
            seg[i] = (wls_line(x[mk], y[mk], ex[mk], ey[mk], init[i])
                      if mk.sum() >= minseg else dict(a=np.nan, m=np.nan,
                                                      n=int(mk.sum())))
        s0, s1, s2 = seg
        # Driving the iteration: a crossing is usable if the two lines exist and
        # their slopes are separated by more than the noise on them. Two nearly
        # parallel lines cross at an arbitrary place, which is exactly what a
        # segment fitted entirely on one side of a bend produces.
        c1, c2 = _cross(s0, s1), _cross(s1, s2)
        t2n = c2 if np.isfinite(c2) else t2
        if np.isfinite(c1):
            t1n = c1
        elif np.isfinite(t2n):
            # No slope-1 data (the binned leg: mode 2's darkest patch sits above
            # its own knee1). t1 is not free -- hold it at the register ratio to
            # the knot that IS measured. This is the ONLY place a register value
            # enters the iteration, and only when segment 0 is absent.
            t1n = t2n * (T1_REG / T2_REG)
        else:
            t1n = t1
        t1n, t2n = t1 + damp * (t1n - t1), t2 + damp * (t2n - t2)
        conv = (abs(t1n - t1) < 1e-6 * max(t1, 1)
                and abs(t2n - t2) < 1e-6 * max(t2, 1))
        t1, t2 = t1n, t2n
        if conv:
            break

    # ACCEPTANCE, on the CONVERGED solution only -- never inside the loop.
    # THE INTERSECTION MUST LIE BETWEEN THE TWO SEGMENTS' DATA. Two lines always
    # cross somewhere; a crossing outside the gap they bracket is an
    # extrapolation, not a knot. Without this the binned leg -- which has no data
    # at all below its knee1 at x=125 -- could still populate segment 0 as the
    # iteration wandered, fit a line to it, pass the slope test, and return
    # t1 = 814 with a pedestal of -478. Applied as a gate INSIDE the loop it
    # instead freezes the iteration before it can converge, because the early
    # segments legitimately straddle a bend on the way to the fixed point.
    s0, s1, s2 = seg
    c1, c2 = _cross(s0, s1), _cross(s1, s2)
    t1_ok = _accept(s0, s1, c1, knot_tol)
    t2_ok = _accept(s1, s2, c2, knot_tol)

    # ── CONSOLIDATION ───────────────────────────────────────────────────────
    # A KNOT THAT IS NOT THERE MEANS THE TWO SEGMENTS EITHER SIDE OF IT ARE ONE
    # SEGMENT. Fitting them separately anyway throws away exactly the lever arm
    # that measures their common slope -- and in §3.3 the slope IS the answer,
    # because it carries g.
    #
    # The case that forces this: 17:05 full res has g = 1.885, so knee2 sits at
    # x = 11500/1.885 = 6101 while the data stops at 3596. There are TWO
    # segments in that leg and the tool was fitting three, splitting the middle
    # segment in half at an arbitrary place. One half then came back with 8
    # blocks and a slope that made g1 = 118. Merging is not a fallback, it is
    # what the rejected knot means.
    none = dict(a=np.nan, m=np.nan, n=0)
    for _ in range(4):
        if t1_ok and t2_ok:
            break                                   # three real segments
        t = t1 if t1_ok else (t2 if t2_ok else np.nan)
        if not np.isfinite(t):
            break                                   # neither knot: nothing to do
        gd = kguard * sx
        lo, hi = x < t - gd, x > t + gd
        if lo.sum() < minseg or hi.sum() < minseg:
            break
        f_lo = wls_line(x[lo], y[lo], ex[lo], ey[lo], 1.0)
        f_hi = wls_line(x[hi], y[hi], ex[hi], ey[hi], S1_REG)
        # WHICH knot this is comes from the slope ratio, not from where the
        # seeded iteration happened to leave it.
        which = _identify(f_lo["m"], f_hi["m"])
        if which is None:
            break
        if which == 1:
            ns, nm = [f_lo, f_hi, none], [lo, hi, np.zeros(x.shape, bool)]
            c = _cross(f_lo, f_hi)
            ok = _accept(f_lo, f_hi, c, knot_tol)
        else:
            ns, nm = [none, f_lo, f_hi], [np.zeros(x.shape, bool), lo, hi]
            c = _cross(f_lo, f_hi)
            ok = _accept(f_lo, f_hi, c, knot_tol)
        seg, msk = ns, nm
        moved = bool(ok and abs(c - t) > 1e-6 * max(abs(t), 1))
        if which == 1:
            t1, t1_ok = (c if ok else t), ok
            t2, t2_ok = np.nan, False
        else:
            t2, t2_ok = (c if ok else t), ok
            t1, t1_ok = np.nan, False
        if not moved:
            break

    t1 = t1 if t1_ok else (t2 * (T1_REG / T2_REG) if t2_ok else np.nan)
    t2 = t2 if t2_ok else np.nan
    return dict(seg=seg, msk=msk, x=x, y=y, ex=ex, ey=ey,
                t1=float(t1), t2=float(t2),
                t1_ok=bool(t1_ok), t2_ok=bool(t2_ok),
                iters=it + 1, converged=bool(conv),
                nseg=[int(s["n"]) for s in seg])


def _knot_se(sa, sb, t):
    """Formal 1-sigma on a knot, propagated from both intercepts and slopes."""
    dm = sb["m"] - sa["m"]
    if not np.isfinite(dm) or dm == 0 or not np.isfinite(t):
        return np.nan
    v = ((sa["va"] + sb["va"]) / dm ** 2 + (t / dm) ** 2 * (sa["vm"] + sb["vm"])
         + 2 * (t / dm ** 2) * (sa["cam"] - sb["cam"]))
    return float(np.sqrt(max(v, 0.0)))


def derive(fit):
    """P, b and g from the fitted segments and knots. Nothing hand-written.

    A knot that the data does not determine comes back NaN and takes its b, g
    and pedestal estimates with it. R and B never reach knee2 and the binned leg
    never reaches knee1; a tool that quietly reports the seed value there would
    hand back a fabricated number that looks exactly like a measurement.

    Acceptance of the knots (`_accept`) and consolidation of segments that a
    rejected knot shows to be one segment both happen in fit3; this reads the
    result and never second-guesses it.
    """
    s0, s1, s2 = fit["seg"]
    t1, t2 = fit["t1"], fit["t2"]
    t1_ok, t2_ok = bool(fit["t1_ok"]), bool(fit["t2_ok"])
    d = dict(seg=fit["seg"], t1=t1, t2=t2, m0=s0["m"], m1=s1["m"], m2=s2["m"],
             a0=s0["a"], a1=s1["a"], a2=s2["a"],
             t1_ok=t1_ok, t2_ok=t2_ok,
             se_t1=_knot_se(s0, s1, t1) if t1_ok else np.nan,
             se_t2=_knot_se(s1, s2, t2) if t2_ok else np.nan)

    # ── g, THE SENSITIVITY RATIO -- MEASURED THREE TIMES, NEVER ASSUMED ──────
    # In §3.2 both takes of a leg were ClearHDR at the same exposure, so g was 1
    # BY CONSTRUCTION and the slopes were only a check. In §3.3 the B take is
    # SDR, g is free, and the slopes CARRY it: the model's three slopes are g,
    # g*s1 and g*s2, and s1 = 1/64 and s2 = 1/16 are REGISTER values read on
    # hardware. So each segment yields an independent estimate of g:
    #
    #     g = m0        = m1/s1 = 64*m1        = m2/s2 = 16*m2
    #
    # They must agree. b then follows from a knot AND g together,
    # b = T1/(t1*g), which is what makes §3.3 an INDEPENDENT determination of b
    # rather than a second opinion on §3.2's arithmetic. Never take g from the
    # nominal 6.3x exposure ratio -- that is a setting, not a measurement, and
    # the 18:37 shutter change did not reach the ClearHDR modes.
    # A SEGMENT NOT BRACKETED BY A REAL KNOT IS NOT THAT SEGMENT, and must not
    # contribute an estimate of g. This is §3.2e's "a crossing outside the gap
    # the two segments bracket is an extrapolation, not a knot" applied to the
    # SLOPES instead of the knots, and it bites here for the first time because
    # in §3.2 the slopes were only a check and now they carry g.
    #
    # Phase R on the full-res leg is the case that shows it: x tops out at 8836
    # and knee2 is at 11500, so there is no 1/16 segment in the data at all --
    # yet the iteration still fills "seg2" with the upper part of the 1/64
    # segment and fits it a slope of 1/64.10. Ungated that enters as
    # g2 = 0.0156/0.0625 = 0.2496 and drags the combined g from 0.999 to 0.531,
    # b from 0.997 to 1.876 and the pedestal from 200 to 311. t2_ok already
    # knows the segment is not real; this just believes it.
    valid = dict(g0=bool(fit["t1_ok"]),
                 g1=bool(fit["t1_ok"] or fit["t2_ok"]),
                 g2=bool(fit["t2_ok"]))
    d["g_valid"] = valid
    gs, gv = {}, {}
    for nm, s, sc in (("g0", s0, 1.0), ("g1", s1, S1_REG), ("g2", s2, S2_REG)):
        if valid[nm] and np.isfinite(s["m"]) and "vm" in s:
            gs[nm], gv[nm] = s["m"] / sc, s["vm"] / sc ** 2
        else:
            gs[nm], gv[nm] = np.nan, np.nan
    d.update(gs)
    d.update({"se_" + k: float(np.sqrt(v)) if np.isfinite(v) and v >= 0
              else np.nan for k, v in gv.items()})
    fin = [(gs[k], gv[k]) for k in ("g0", "g1", "g2")
           if np.isfinite(gs[k]) and np.isfinite(gv[k]) and gv[k] > 0]
    vals = [q for q, _ in fin]
    d["g_spread"] = float(max(vals) - min(vals)) if len(vals) > 1 else 0.0
    d["n_g"] = len(fin)
    # THE THREE ESTIMATES MUST AGREE, AND DISAGREEMENT IS NOT SOMETHING TO
    # AVERAGE OVER. They measure the same quantity through three different
    # segments; if they disagree by more than g_tol, the segmentation is wrong
    # and the right answer is "this phase did not measure g", not the mean of a
    # good estimate and a broken one. Inverse-variance weighting makes that
    # worse, not better -- a spurious segment fitted over a long lever arm gets
    # the SMALLEST error bar and therefore the LARGEST weight, which is how
    # g0 = 0.177 outvoted g1 = 11.19 and g2 = 11.24 and dragged the combination
    # to 0.188. Weight is not evidence.
    if fin and (len(vals) == 1 or d["g_spread"] <= G_TOL * abs(np.median(vals))):
        w = np.array([1.0 / v for _, v in fin])
        d["g"] = float(np.sum(w * np.array([q for q, _ in fin])) / w.sum())
        d["se_g"] = float(np.sqrt(1.0 / w.sum()))
        d["g_ok"] = True
    else:
        d["g"] = d["se_g"] = np.nan
        d["g_ok"] = False

    d["b_from_t1"] = (T1_REG / (t1 * d["g"])
                      if fit["t1_ok"] and np.isfinite(d["g"]) else np.nan)
    d["b_from_t2"] = (T2_REG / (t2 * d["g"])
                      if fit["t2_ok"] and np.isfinite(d["g"]) else np.nan)
    d["b"] = d["b_from_t1"] if np.isfinite(d["b_from_t1"]) else d["b_from_t2"]
    # b and g enter the knots ONLY as the product b*g, so the knots alone can
    # never separate them. The slopes are what break that degeneracy.
    d["bg_from_t1"] = T1_REG / t1 if fit["t1_ok"] else np.nan
    d["bg_from_t2"] = T2_REG / t2 if fit["t2_ok"] else np.nan

    # Pedestal, three ways.
    #  seg0 free : the intercept with the slope fitted free. Honest, but over a
    #              short lever arm the slope and the intercept are strongly
    #              anticorrelated, so a 0.5% slope error is ~1.5 codes of P.
    #  seg0 unit : the same data with the slope CONSTRAINED to 1, i.e. the
    #              weighted mean of (A - x). Only legitimate because the free
    #              slope came out 1 first; quoted alongside, never instead.
    #  seg1      : from the middle segment's intercept and t1.
    # EVERY seg0-DERIVED QUANTITY IS GATED ON t1_ok, not just g0. If there is no
    # real slope-g segment the iteration still fills seg0 with the bottom of the
    # MIDDLE segment -- on 18:37's binned leg t1 is 11 and the data starts at 20,
    # and "seg0" came back as x=20..111 at slope 0.1767 against seg1's 0.1749,
    # i.e. the same segment twice. Its intercept is then a straight-line
    # extrapolation of the middle segment back to x=0, which is P + t1*(g-m1),
    # not P: -230.62 against a true 201.8. The knot test already knows; the
    # pedestal has to believe it too.
    d["P_seg0"] = (s0["a"] if valid["g0"] and np.isfinite(s0["a"]) else np.nan)
    # The constrained pedestal. In §3.2 the slope was constrained to 1 because
    # the model said so; here it is constrained to g -- and g is taken from the
    # OTHER TWO segments, never from seg0 itself, or this would just be the free
    # intercept under a different name. Legitimate for the same reason as §3.2's
    # version: the free slope is checked to come out at g first, and both are
    # quoted side by side.
    hi = [(gs[k], gv[k]) for k in ("g1", "g2")
          if np.isfinite(gs[k]) and np.isfinite(gv[k]) and gv[k] > 0]
    if hi:
        wh = np.array([1.0 / v for _, v in hi])
        g_hi = float(np.sum(wh * np.array([q for q, _ in hi])) / wh.sum())
    else:
        g_hi = d["g"]
    d["g_hi"] = g_hi
    m0mask = fit["msk"][0]
    if valid["g0"] and m0mask.sum() >= 5 and np.isfinite(g_hi):
        dv = fit["y"][m0mask] - g_hi * fit["x"][m0mask]
        w = 1.0 / (fit["ey"][m0mask] ** 2 + (g_hi * fit["ex"][m0mask]) ** 2)
        d["P_seg0_unit"] = float((w * dv).sum() / w.sum())
    else:
        d["P_seg0_unit"] = np.nan
    # a1 = P + t1*g*(1-s1) = P + t1*(g - m1), since m1 = g*s1. With g == 1 this
    # collapses to §3.2's P = a1 - t1*(1-m1), so the §3.2 legs are unaffected.
    d["P_seg1"] = (s1["a"] - t1 * (d["g"] - s1["m"])
                   if np.isfinite(s1["a"]) and np.isfinite(t1)
                   and np.isfinite(d["g"]) else np.nan)
    # The binned leg has NO slope-1 data -- its darkest patch sits above its own
    # knee1 -- so there P and t1 are degenerate: only the combination
    # a1 = P + t1*(1-m1) is measured. Anchoring t1 on the register ratio to the
    # knot that IS measured makes that explicit, and makes the binned pedestal
    # immune to a spurious segment 0 that a resampled draw may throw up. This is
    # NOT an independent measurement of P; it is P GIVEN the register T1. The
    # free measurement of P is the full-res leg's P_seg0_unit.
    # t1 = t2*T1/T2 is a RATIO of registers, so it is free of both b and g.
    d["P_seg1_anchored"] = (
        s1["a"] - (t2 * T1_REG / T2_REG) * (d["g"] - s1["m"])
        if np.isfinite(s1["a"]) and fit["t2_ok"] and np.isfinite(d["g"])
        else np.nan)
    d["P_seg2"] = (s2["a"] - t1 * (d["g"] - s1["m"]) - t2 * (s1["m"] - s2["m"])
                   if np.isfinite(s2["a"]) and np.isfinite(t1)
                   and np.isfinite(d["g"]) else np.nan)
    d["P"] = (d["P_seg0_unit"] if np.isfinite(d["P_seg0_unit"])
              else d["P_seg1_anchored"])

    return d


def model_A(x, P, b, g=1.0, T1=T1_REG, T2=T2_REG, s1=S1_REG, s2=S2_REG):
    """A = P + ccmp(b*g*x)/b.

    g is the SDR->ClearHDR sensitivity ratio and is 1 by construction on §3.2's
    legs (both takes ClearHDR), free on §3.3's (B take is SDR). x is always the
    B take's code above ITS OWN black.
    """
    u = b * g * x
    c = np.where(u <= T1, u,
                 np.where(u <= T2, T1 + (u - T1) * s1,
                          T1 + (T2 - T1) * s1 + (u - T2) * s2))
    return P + c / b


def ccmp_inv(u, T1=T1_REG, T2=T2_REG, s1=S1_REG, s2=S2_REG):
    """The compander's inverse, in its own pre-binning domain. Same arithmetic
    as ccmp_decode.Ccmp.ccmp_inv; kept here so fitcurve has no import cycle."""
    u = np.asarray(u, float)
    C2 = T1 + (T2 - T1) * s1
    return np.where(u <= T1, u,
                    np.where(u <= C2, T1 + (u - T1) / s1,
                             T2 + (u - C2) / s2))


def closure(P, pars, Pv=None, bv=None, gv=None, T1=T1_REG, T2=T2_REG,
            s1=S1_REG, s2=S2_REG, nbin=5):
    """Predict EVERY used block -- including the knee neighbourhoods the fit was
    never shown -- from (P, b) plus the REGISTER knots 500/11500.

    This is the test that matters. The segments were fitted away from the knees;
    if the solved pair also reproduces the blocks at the knees, the model is the
    curve. Knee blocks are reported separately because there the region mean is
    legitimately biased low by the bend, so a residual there is expected and its
    SIGN is diagnostic.

    ** REPORTED IN L, NOT IN CODE ** (handoff §4, added by §3.5). The table
    INVERTS this curve, so a code-domain residual lands in the delivered linear
    domain multiplied by the local dL/dC -- which is 64 on the middle segment.
    "0.37 codes rms" is 23.7 L there. A code-domain rms flatters a decompanding
    curve by exactly its compression ratio, so every residual below is given in
    L as well, per SEGMENT, with dL/dC printed beside it.

    ** SIGNED MEAN, NOT ONLY RMS. ** An rms cannot tell a model error from
    scatter. If the signed mean is structured by level the model is wrong; if it
    is zero-mean the scatter is noise. Both are reported, per segment and per
    level bin inside each segment.

    Pv/bv/gv override the solved parameters -- pass the tag and the register
    values for the genuinely zero-free-parameter form.
    """
    x, y, sx = P["x"], P["y"], P["sx"]
    Pp = pars["P"] if Pv is None else float(Pv)
    b = pars["b"] if bv is None else float(bv)
    g = pars.get("g", 1.0) if gv is None else float(gv)
    nan = dict(rms=np.nan, max=np.nan, med=np.nan, n=0, nknee=0,
               knee_rms=np.nan, knee_bias=np.nan, bias=np.nan, rms_L=np.nan,
               bias_L=np.nan, segs=[], bins=[], P=Pp, b=b, g=g)
    if not (np.isfinite(b) and np.isfinite(g) and np.isfinite(Pp)):
        return nan

    # code domain: what the old metric measured
    r = y - model_A(x, Pp, b, g, T1, T2, s1, s2)
    # L domain: what the TABLE delivers. Ltrue is the 16-bit take's own linear
    # signal scaled by g (g == 1 on §3.2's legs, by construction and measured).
    Ltrue = g * x
    Lhat = ccmp_inv(b * (y - Pp), T1, T2, s1, s2) / b
    rL = Lhat - Ltrue

    # segment membership on the TRUE level, so a block is classed by where it
    # sits on the curve rather than by where the model's error put it
    u = b * Ltrue
    seg_id = np.where(u <= T1, 0, np.where(u <= T2, 1, 2))
    # the knots sit at T/(b*g) in the B take's domain, not T/b
    knee = ((np.abs(x - T1 / (b * g)) < 3 * sx)
            | (np.abs(x - T2 / (b * g)) < 3 * sx))
    aw = ~knee
    if not aw.any():
        return nan

    dLdC = {0: 1.0, 1: 1.0 / s1, 2: 1.0 / s2}
    names = {0: "low  x1", 1: "mid  x%g" % (1.0 / s1), 2: "high x%g" % (1.0 / s2)}

    def stats(m, sid):
        n = int(m.sum())
        if not n:
            return None
        return dict(seg=sid, name=names[sid], n=n, dLdC=dLdC[sid],
                    Llo=float(Ltrue[m].min()), Lhi=float(Ltrue[m].max()),
                    Lmean=float(Ltrue[m].mean()),
                    bias=float(r[m].mean()), rms=float(np.sqrt((r[m] ** 2).mean())),
                    bias_L=float(rL[m].mean()),
                    rms_L=float(np.sqrt((rL[m] ** 2).mean())),
                    sd_L=float(rL[m].std()),
                    se_L=float(rL[m].std() / np.sqrt(n)),
                    frac=float(100 * np.mean(rL[m] / np.maximum(Ltrue[m], 1e-9))))

    segs, bins = [], []
    for sid in (0, 1, 2):
        m = aw & (seg_id == sid)
        s = stats(m, sid)
        if s is None:
            continue
        segs.append(s)
        # LEVEL BINS INSIDE THE SEGMENT. Quantile edges, so every bin carries
        # blocks; equal-width bins on a chart put 90% of them in one bin.
        Ls = Ltrue[m]
        k = min(nbin, max(1, s["n"] // 25))
        edges = np.quantile(Ls, np.linspace(0, 1, k + 1))
        edges[0], edges[-1] = -np.inf, np.inf
        for i in range(k):
            mb = m & (Ltrue >= edges[i]) & (Ltrue < edges[i + 1])
            sb = stats(mb, sid)
            if sb:
                bins.append(sb)

    return dict(rms=float(np.sqrt((r[aw] ** 2).mean())),
                max=float(np.abs(r[aw]).max()),
                med=float(np.median(np.abs(r[aw]))),
                bias=float(r[aw].mean()),
                rms_L=float(np.sqrt((rL[aw] ** 2).mean())),
                bias_L=float(rL[aw].mean()),
                n=int(aw.sum()), nknee=int(knee.sum()),
                knee_rms=float(np.sqrt((r[knee] ** 2).mean())) if knee.any() else np.nan,
                knee_bias=float(r[knee].mean()) if knee.any() else np.nan,
                segs=segs, bins=bins, P=Pp, b=b, g=g)


def tile_bootstrap(P, t1, t2, kguard, ntile=6, ndraw=200, seed=12345):
    """Spatial-tile bootstrap. Blocks inside one patch are NOT independent --
    they share flare, shading and the chart's own non-uniformity -- so resample
    TILES of the frame, which carries that correlation, not individual blocks."""
    rng = np.random.default_rng(seed)
    gy, gx = P["gy"], P["gx"]
    H, W = P["shape"]
    tid = (gy * ntile // H) * ntile + (gx * ntile // W)
    tiles = np.unique(tid)
    out = {k: [] for k in ("t1", "t2", "P", "b_from_t1", "b_from_t2", "m1", "m2",
                           "P_seg0_unit", "P_seg1_anchored", "g", "g0", "g1",
                           "g2", "bg_from_t1", "bg_from_t2")}
    ndeg = 0
    for _ in range(ndraw):
        pick = rng.choice(tiles, size=tiles.size, replace=True)
        idx = np.concatenate([np.flatnonzero(tid == t) for t in pick])
        Q = dict(P, x=P["x"][idx], y=P["y"][idx], ex=P["ex"][idx],
                 ey=P["ey"][idx], sx=P["sx"][idx])
        try:
            d = derive(fit3(Q, t1, t2, kguard))
        except Exception:
            ndeg += 1
            continue
        # A draw that lost the knot its pedestal depends on carries no pedestal.
        # Averaging its P in would report a spread that is really a count of
        # degenerate draws.
        if not np.isfinite(d["P"]):
            ndeg += 1
        for k in out:
            out[k].append(d[k])
    r = {k: (float(np.nanstd(v)) if np.isfinite(v).sum() > 3 else np.nan)
         for k, v in ((k, np.array(v, float)) for k, v in out.items())}
    r["ndegenerate"] = ndeg
    r["ndraw"] = ndraw
    return r


# ── reporting ───────────────────────────────────────────────────────────────
def run_leg(a_take, b_take, phases=PHASES, bs=8, limit=None, kguard=4.0,
            flat=2.0, rel=0.02, absol=20.0, boot=0, seed_sweep=False,
            verbose=True, measured_black=True, dumpn=0, dumphi=None):
    rows = []
    for ph in phases:
        P = leg_points(a_take, b_take, ph, bs, limit, flat, rel, absol,
                       measured_black=measured_black)
        m = P["meta"]
        if verbose:
            print("=" * 100)
            print(f"LEG  A = {m['a_take']}  (mode {m['a_mode']}, {m['w']}x{m['h']} "
                  f"{m['a_bits']}b)   B = {m['b_take']}  (mode {m['b_mode']}, "
                  f"{m['b_bits']}b)")
            print(f"     phase {ph}   co-reg dy={-m['dy']:+d} dx={-m['dx']:+d} "
                  f"phase steps (r={m['corr']:.3f}, margin {m['margin']:.3f})   B black used "
                  f"{m['b_black_used']:.2f} (tag {m['b_black_tag']:.0f})")
            print(f"     {m['nused']} of {m['nblocks']} blocks survive   "
                  f"x range {P['x'].min():.0f}..{P['x'].max():.0f}   "
                  f"within-block sx median {np.median(P['sx']):.1f} codes")
        if dumpn:
            dump(P, dumpn, hi=dumphi)

        # seed far from the register values on purpose
        seed_t1, seed_t2 = P["x"].max() * 0.05, P["x"].max() * 0.5
        f = fit3(P, seed_t1, seed_t2, kguard)
        d = derive(f)
        d["closure"] = closure(P, d)
        d["meta"] = m
        d["seed"] = (seed_t1, seed_t2)
        d["nseg"] = f["nseg"]
        d["converged"] = f["converged"]
        if boot:
            d["boot"] = tile_bootstrap(P, seed_t1, seed_t2, kguard, ndraw=boot)
        if seed_sweep:
            d["sweep"] = seed_basin(P, kguard)
        if verbose:
            report(d)
        rows.append(d)
    return rows


def seed_basin(P, kguard, n=6, which="t2"):
    """Start the iteration from a grid of deliberately wrong ORDERED knot pairs.

    The point of this test is anti-circularity: if every seed lands on the same
    fixed point, then the register values 500/11500 did not enter the answer
    through the seed. Seeds are drawn across the whole data range but must
    satisfy t1_seed < t2_seed -- a seed with the knots inverted is not a wrong
    starting guess, it is a different problem, and counting its failure against
    the fit would understate the basin.

    Reports the fraction of seeds reaching the modal answer, and the spread
    among those that do. A wide basin with a tight range is the pass.
    """
    hi = P["x"].max()
    vals = []
    for f1 in np.linspace(0.005, 0.40, n):
        for f2 in np.linspace(0.10, 0.95, n):
            if f2 <= f1 * 1.5:
                continue
            try:
                d = derive(fit3(P, hi * f1, hi * f2, kguard))
            except Exception:
                vals.append(np.nan)
                continue
            vals.append(d[which])
    v = np.array(vals, float)
    fin = v[np.isfinite(v)]
    if fin.size == 0:
        return dict(n=len(v), nconv=0, frac=0.0, med=np.nan, lo=np.nan, hi=np.nan)
    med = float(np.median(fin))
    conv = fin[np.abs(fin - med) < 0.005 * abs(med)]
    return dict(n=int(v.size), nconv=int(conv.size), frac=float(conv.size / v.size),
                med=med, lo=float(conv.min()), hi=float(conv.max()), which=which)


def dump(P, nb=44, lo=None, hi=None):
    """The raw instrument: binned A against x, with the local secant slope.

    Print this before believing any fitted number. A slope that walks instead of
    sitting on a plateau means the segmentation is wrong, not that the sensor is
    interesting."""
    x, y = P["x"], P["y"]
    m = np.ones(x.shape, bool)
    if lo is not None:
        m &= x >= lo
    if hi is not None:
        m &= x <= hi
    x, y = x[m], y[m]
    sx, ex, ey = P["sx"][m], P["ex"][m], P["ey"][m]
    e = np.geomspace(max(x.min(), 1.0), x.max(), nb + 1)
    print(f"\n  {'x lo':>9}{'x hi':>9}{'n':>7}{'x mean':>10}{'A mean':>10}"
          f"{'secant':>11}{'1/secant':>10}{'sx':>7}{'ex':>6}{'ey':>6}")
    prev = None
    for i in range(nb):
        k = (x >= e[i]) & (x < e[i + 1])
        if k.sum() < 4:
            continue
        xm, ym = float(x[k].mean()), float(y[k].mean())
        s = (ym - prev[1]) / (xm - prev[0]) if prev and xm > prev[0] else np.nan
        print(f"  {e[i]:9.1f}{e[i+1]:9.1f}{k.sum():7d}{xm:10.1f}{ym:10.2f}"
              f"{s:11.5f}{1/s if np.isfinite(s) and s else 0:10.2f}"
              f"{np.median(sx[k]):7.1f}{np.median(ex[k]):6.2f}{np.median(ey[k]):6.2f}")
        prev = (xm, ym)


def report(d):
    lbl = ("seg0  slope 1", "seg1  slope 1/64", "seg2  slope 1/16")
    print(f"\n  {'segment':<18}{'n':>7}{'x range':>21}{'slope':>12}{'1/slope':>10}"
          f"{'intercept':>12}{'rms':>8}{'noise':>8}")
    for i, nm in enumerate(("m0", "m1", "m2")):
        m, a = d[nm], d["a" + nm[1]]
        s = d["seg"][i]
        n = d["nseg"][i]
        if not np.isfinite(m):
            print(f"  {lbl[i]:<18}{n:>7}      -- no data, segment absent --")
            continue
        rng = f"{s['xlo']:.0f}..{s['xhi']:.0f}"
        print(f"  {lbl[i]:<18}{n:>7}{rng:>21}{m:12.6f}{1/m if m else 0:10.2f}"
              f"{a:12.3f}{s['rms']:8.2f}{s['noise']:8.2f}")
    print(f"\n  g, THE SENSITIVITY RATIO — three independent estimates, which "
          f"must agree:")
    for nm, how in (("g0", "seg0 slope        = g"),
                    ("g1", "seg1 slope * 64   = g"),
                    ("g2", "seg2 slope * 16   = g")):
        v, se = d.get(nm, np.nan), d.get("se_" + nm, np.nan)
        print(f"      {how}   " + (f"{v:9.4f}  +/- {se:.4f}"
                                   if np.isfinite(v) else "       --   "
                                   "segment absent"))
    if np.isfinite(d.get("g", np.nan)):
        print(f"      combined g = {d['g']:.4f} +/- {d['se_g']:.4f}   "
              f"(n={d['n_g']}, spread among them {d['g_spread']:.4f})")
    print(f"\n  KNOTS from slope intersections (never measured off the bend). "
          f"They give b*g; the SLOPES separate b from g:")
    for nm, T in (("t1", T1_REG), ("t2", T2_REG)):
        if d[nm + "_ok"]:
            bg = T / d[nm]
            b = d["b_from_" + nm]
            print(f"      {nm} = {d[nm]:9.2f}  +/- {d['se_'+nm]:6.2f}   ->  "
                  f"b*g = {T:.0f}/{nm} = {bg:8.4f}   ->  b = b*g/g = "
                  + (f"{b:7.4f}" if np.isfinite(b) else "   --"))
        else:
            print(f"      {nm} =        --   not determined by this phase "
                  f"(segment {'0' if nm=='t1' else '2'} has "
                  f"{d['nseg'][0 if nm=='t1' else 2]} blocks)")
    print(f"  PEDESTAL   seg0 free {d['P_seg0']:8.2f}   seg0 slope==1 "
          f"{d['P_seg0_unit']:8.2f}   seg1 {d['P_seg1']:8.2f}   seg2 {d['P_seg2']:8.2f}")
    c = d["closure"]
    print(f"  CLOSURE    P={d['P']:.2f}, b={d['b']:.4f}, g={d.get('g', 1.0):.4f}, "
          f"register knots 500/11500 "
          f"-> away from knees: rms {c['rms']:.2f} max {c['max']:.2f} codes "
          f"({c['n']} blocks)")
    print(f"             at the knees ({c['nknee']} blocks, never fitted): "
          f"rms {c['knee_rms']:.2f}, mean {c['knee_bias']:+.2f} codes "
          f"(negative = the bend rounding, as predicted)")
    if "boot" in d:
        b = d["boot"]
        print(f"  BOOTSTRAP  (spatial tiles)  t1 {b['t1']:.2f}  t2 {b['t2']:.2f}  "
              f"P {b['P']:.2f}  b(t2) {b['b_from_t2']:.4f}")
    if "sweep" in d:
        s = d["sweep"]
        print(f"  SEED BASIN {s['n']} seeds -> t1 [{s['t1'][0]:.2f}, {s['t1'][1]:.2f}]"
              f"  t2 [{s['t2'][0]:.2f}, {s['t2'][1]:.2f}]  P [{s['P'][0]:.2f}, "
              f"{s['P'][1]:.2f}]")
    if not d["converged"]:
        print("  ** DID NOT CONVERGE **")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--phase", default="all", choices=list(PHASES) + ["all"])
    ap.add_argument("--block", type=int, default=8)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--kguard", type=float, default=4.0)
    ap.add_argument("--flat", type=float, default=2.0)
    ap.add_argument("--rel", type=float, default=0.02)
    ap.add_argument("--abs", dest="absol", type=float, default=20.0)
    ap.add_argument("--boot", type=int, default=0)
    ap.add_argument("--seed-sweep", action="store_true")
    ap.add_argument("--tag-black", action="store_true",
                    help="use B's BlackLevel tag instead of the lens-cap measurement")
    ap.add_argument("--json")
    ap.add_argument("--dump", type=int, default=0,
                    help="print the binned A-vs-x curve with local secants first")
    ap.add_argument("--dump-hi", type=float)
    a = ap.parse_args()
    phases = PHASES if a.phase == "all" else (a.phase,)
    rows = run_leg(a.a, a.b, phases, a.block, a.limit, a.kguard, a.flat, a.rel,
                   a.absol, a.boot, a.seed_sweep, measured_black=not a.tag_black,
                   dumpn=a.dump, dumphi=a.dump_hi)
    if a.json:
        def clean(o):
            if isinstance(o, dict):
                return {k: clean(v) for k, v in o.items() if k != "hist"}
            if isinstance(o, (list, tuple)):
                return [clean(v) for v in o]
            if isinstance(o, (np.floating, np.integer)):
                return float(o)
            return o
        json.dump(clean(rows), open(a.json, "w"), indent=1)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
