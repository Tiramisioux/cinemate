#!/usr/bin/env python3
"""resid_why.py — separate the candidate causes of the closure residual.

    resid_why.py [--leg ...] [--test all]

Four tests, each of which a different cause passes and the others fail. Run them
before proposing a parameter change; a change that is not traceable to one of
these is a fit to the answer (handoff, this pass's brief).

  phase   The transfer is per PIXEL and phase-independent -- §2 measured it and
          "no colour-dependent term is needed, and none is permitted". So at the
          SAME L the four CFA phases must show the SAME residual. If they do
          not, the cause is NOT the curve, and no reparameterisation of the
          curve can remove it.

  round   Sub-code rounding in the hardware's forward quantisation shows up as a
          SAWTOOTH in the fractional part of the predicted code, amplitude <= 0.5
          codes, and it survives block averaging only when the within-block
          spread is small compared with one code -- which on the 1/64 segment
          means sigma_L << 64. Printed with sigma_v so the two are judged
          together.

  space   Flare, shading and a mis-registration are properties of POSITION, not
          of level. Split each narrow L bin by frame quadrant: a curve error is
          flat across quadrants, a scene error is not.

  patch   A chart patch is ~one level, so a per-PATCH offset and a per-LEVEL
          offset are almost the same picture. They separate on SPREAD: at one
          level a curve error has none, and a patch error has the patch-to-patch
          scatter. Blocks are clustered into patches spatially.
"""
import os, sys, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fitcurve import model_A, PHASES, T1_REG, T2_REG, S1_REG, S2_REG  # noqa: E402
from legcache import points, LEGS                                     # noqa: E402
from resid_profile import resid                                       # noqa: E402
from fit_all import SESSIONS                                          # noqa: E402


def _bins(L, nb, lo=None, hi=None):
    m = np.ones(L.shape, bool)
    if lo is not None:
        m &= L >= lo
    if hi is not None:
        m &= L <= hi
    idx = np.flatnonzero(m)
    return np.array_split(idx[np.argsort(L[idx])], nb)


def test_phase(sess, leg, nb=12, seg=1):
    """Same L, four phases. A curve error cannot be phase-dependent."""
    b = LEGS[(sess, leg)][2]
    R = {p: resid(points(sess, leg, p), bv=b) for p in PHASES}
    # common L range covered by all four phases on this segment
    lo = max(float(R[p]["L"][R[p]["seg"] == seg].min()) for p in PHASES)
    hi = min(float(R[p]["L"][R[p]["seg"] == seg].max()) for p in PHASES)
    print(f"\n{sess}  {leg}  seg {seg}  — SAME L, FOUR PHASES   "
          f"(common L {lo:.0f}..{hi:.0f})")
    print(f"  {'L':>8}" + "".join(f"{p+' rC':>10}" for p in PHASES)
          + f"{'spread C':>10}{'spread L':>10}")
    edges = np.exp(np.linspace(np.log(lo), np.log(hi), nb + 1))
    out = []
    for i in range(nb):
        row, Ls = [], []
        for p in PHASES:
            r = R[p]
            m = (r["seg"] == seg) & ~r["knee"] & (r["L"] >= edges[i]) & (r["L"] < edges[i + 1])
            row.append(float(r["rC"][m].mean()) if m.sum() >= 20 else np.nan)
            if m.sum() >= 20:
                Ls.append(float(r["L"][m].mean()))
        if not np.isfinite(row).all():
            continue
        sp = max(row) - min(row)
        dLdC = 1.0 / (S1_REG if seg == 1 else (S2_REG if seg == 2 else 1.0))
        print(f"  {np.mean(Ls):>8.0f}" + "".join(f"{v:>10.3f}" for v in row)
              + f"{sp:>10.3f}{sp*dLdC:>10.1f}")
        out.append(sp)
    if out:
        print(f"  phase spread, median {np.median(out):.3f} codes = "
              f"{np.median(out)/S1_REG if seg==1 else np.median(out):.1f} L "
              f"— the curve is phase-independent, so this is a FLOOR on what "
              f"re-parameterising it can fix")
    return out


def test_round(sess, leg, phase, seg=1, nb=10):
    """Residual against the fractional part of the predicted code."""
    b = LEGS[(sess, leg)][2]
    P = points(sess, leg, phase)
    R = resid(P, bv=b)
    m = (R["seg"] == seg) & ~R["knee"]
    pred = model_A(R["x"][m], 200.0, b, 1.0)
    fr = pred - np.floor(pred)
    rC = R["rC"][m]
    sv = R["sx"][m] * (S1_REG if seg == 1 else S2_REG) * 1.0   # sigma of pred, codes
    print(f"\n{sess}  {leg}  {phase}  seg {seg}  — RESIDUAL vs frac(predicted code)"
          f"   (sigma_v median {np.median(sv):.2f} codes)")
    print(f"  {'frac':>8}{'n':>7}{'bias C':>9}{'+/-':>7}")
    o = np.argsort(fr)
    for idx in np.array_split(o, nb):
        print(f"  {fr[idx].mean():>8.2f}{idx.size:>7}{rC[idx].mean():>9.3f}"
              f"{rC[idx].std()/np.sqrt(idx.size):>7.3f}")
    print(f"  sawtooth amplitude (max-min of the bins): "
          f"{max(rC[i].mean() for i in np.array_split(o, nb)) - min(rC[i].mean() for i in np.array_split(o, nb)):.3f}"
          f" codes; a rounding convention gives <= 1.0 and correlates with frac")


def test_space(sess, leg, phase, seg=1, nb=6):
    """Same L, four frame quadrants. A curve error is flat across position."""
    b = LEGS[(sess, leg)][2]
    P = points(sess, leg, phase)
    R = resid(P, bv=b)
    H, W = P["shape"]
    q = (P["gy"] * 2 // max(H, 1)) * 2 + (P["gx"] * 2 // max(W, 1))
    m = (R["seg"] == seg) & ~R["knee"]
    print(f"\n{sess}  {leg}  {phase}  seg {seg}  — SAME L, FOUR QUADRANTS")
    print(f"  {'L':>8}{'n':>7}" + "".join(f"{'q%d' % i:>9}" for i in range(4))
          + f"{'spread':>9}")
    for idx in _bins(R["L"], nb):
        idx = idx[m[idx]]
        if idx.size < 80:
            continue
        row = [float(R["rC"][idx][q[idx] == i].mean())
               if (q[idx] == i).sum() >= 15 else np.nan for i in range(4)]
        fin = [v for v in row if np.isfinite(v)]
        print(f"  {R['L'][idx].mean():>8.0f}{idx.size:>7}"
              + "".join("       --" if not np.isfinite(v) else f"{v:>9.3f}" for v in row)
              + f"{(max(fin)-min(fin)) if len(fin) > 1 else np.nan:>9.3f}")


def test_patch(sess, leg, phase, seg=1, nb=8):
    """Within a narrow L bin: how much of the spread is BETWEEN patches?

    Patches are found spatially -- connected blocks of similar level -- so this
    does not need the patch box definitions and works on any framing.
    """
    b = LEGS[(sess, leg)][2]
    P = points(sess, leg, phase)
    R = resid(P, bv=b)
    H, W = P["shape"]
    # crude patch id: quantise position to a 6x6 grid of the chart, which is
    # coarser than a patch, then split further by level
    pid = (P["gy"] * 8 // H) * 8 + (P["gx"] * 8 // W)
    m = (R["seg"] == seg) & ~R["knee"]
    print(f"\n{sess}  {leg}  {phase}  seg {seg}  — WITHIN an L bin, "
          f"BETWEEN-patch scatter vs within-patch")
    print(f"  {'L':>8}{'n':>7}{'npatch':>8}{'bias C':>9}{'between sd':>12}"
          f"{'within sd':>11}")
    for idx in _bins(R["L"], nb):
        idx = idx[m[idx]]
        if idx.size < 100:
            continue
        means, wsd = [], []
        for p in np.unique(pid[idx]):
            s = idx[pid[idx] == p]
            if s.size >= 12:
                means.append(R["rC"][s].mean())
                wsd.append(R["rC"][s].std())
        if len(means) < 2:
            continue
        print(f"  {R['L'][idx].mean():>8.0f}{idx.size:>7}{len(means):>8}"
              f"{np.mean(means):>9.3f}{np.std(means):>12.3f}{np.mean(wsd):>11.3f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leg", default="3<->5 full res")
    ap.add_argument("--session", default=None)
    ap.add_argument("--phase", default="G1")
    ap.add_argument("--seg", type=int, default=1)
    ap.add_argument("--test", default="all",
                    choices=["all", "phase", "round", "space", "patch"])
    a = ap.parse_args()
    sess = [a.session] if a.session else [s for s, _, _ in SESSIONS]
    for s in sess:
        if a.test in ("all", "phase"):
            test_phase(s, a.leg, seg=a.seg)
        if a.test in ("all", "round"):
            test_round(s, a.leg, a.phase, a.seg)
        if a.test in ("all", "space"):
            test_space(s, a.leg, a.phase, a.seg)
        if a.test in ("all", "patch"):
            test_patch(s, a.leg, a.phase, a.seg)


if __name__ == "__main__":
    main()
