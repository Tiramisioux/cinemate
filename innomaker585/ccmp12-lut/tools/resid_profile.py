#!/usr/bin/env python3
"""resid_profile.py — the closure residual as a DENSE FUNCTION OF LEVEL, in L.

    resid_profile.py [--leg "3<->5 full res"] [--nbin 40] [--spatial]

§3.2d asked "how big is the residual" and answered in codes. This asks "what
SHAPE is it", in L, which is the only domain the deliverable lives in. A shape
names a cause; an rms does not:

    flat, same sign on every segment, size ~ a fixed fraction of the local step
                                        -> a hardware ROUNDING convention
    zero on the low segment, a STEP at knee1, flat after
                                        -> the effective T1 is off
    zero at the knots, bulging between  -> a SOFT knee, not a corner
    proportional to L                   -> a per-channel GAIN difference
    flat in L on EVERY segment          -> an error in the 16-bit take's BLACK,
                                           i.e. in the reference, not the curve

The knee neighbourhoods are PRINTED, not excluded -- the fit never saw them, so
they are the only free test of the knee's shape the data contains.
"""
import os, sys, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fitcurve import (model_A, ccmp_inv, fit3, derive, PHASES,      # noqa: E402
                      T1_REG, T2_REG, S1_REG, S2_REG)
from legcache import points, LEGS                                   # noqa: E402
from fit_all import SESSIONS                                        # noqa: E402


def resid(P, Pv=200.0, bv=1.0, gv=1.0, T1=T1_REG, T2=T2_REG,
          s1=S1_REG, s2=S2_REG):
    """Per-block residual in BOTH domains, plus segment id and knee flag."""
    x, y, sx = P["x"], P["y"], P["sx"]
    rC = y - model_A(x, Pv, bv, gv, T1, T2, s1, s2)
    Ltrue = gv * x
    rL = ccmp_inv(bv * (y - Pv), T1, T2, s1, s2) / bv - Ltrue
    u = bv * Ltrue
    seg = np.where(u <= T1, 0, np.where(u <= T2, 1, 2))
    knee = ((np.abs(x - T1 / (bv * gv)) < 3 * sx)
            | (np.abs(x - T2 / (bv * gv)) < 3 * sx))
    return dict(rC=rC, rL=rL, L=Ltrue, seg=seg, knee=knee, x=x, y=y, sx=sx)


def profile(P, nbin=40, **kw):
    """Equal-count bins in L across the WHOLE range, knee blocks included."""
    R = resid(P, **kw)
    L = R["L"]
    o = np.argsort(L)
    rows = []
    for idx in np.array_split(o, nbin):
        if idx.size < 5:
            continue
        rows.append(dict(
            n=int(idx.size), L=float(L[idx].mean()),
            Llo=float(L[idx].min()), Lhi=float(L[idx].max()),
            seg=int(np.bincount(R["seg"][idx], minlength=3).argmax()),
            fknee=float(R["knee"][idx].mean()),
            rC=float(R["rC"][idx].mean()), rL=float(R["rL"][idx].mean()),
            seC=float(R["rC"][idx].std() / np.sqrt(idx.size)),
            seL=float(R["rL"][idx].std() / np.sqrt(idx.size)),
            code=float(R["y"][idx].mean())))
    return rows


def show(sess, leg, phase, nbin=40, **kw):
    b = LEGS[(sess, leg)][2]
    P = points(sess, leg, phase)
    kw.setdefault("bv", b)
    rows = profile(P, nbin, **kw)
    T1 = kw.get("T1", T1_REG)
    print(f"\n{sess}  {leg}  phase {phase}   b={kw['bv']:g}  "
          f"P={kw.get('Pv', 200.0):g}  T1={T1:g}  "
          f"knots in L at {T1/kw['bv']:.1f} and {kw.get('T2', T2_REG)/kw['bv']:.1f}")
    print(f"  {'n':>6}{'L':>9}{'code':>9}{'seg':>5}{'knee%':>7}"
          f"{'bias C':>9}{'+/-':>7}{'BIAS L':>9}{'+/-':>7}{'bias/L':>8}")
    for r in rows:
        mark = "  <-- knee" if r["fknee"] > 0.2 else ""
        print(f"  {r['n']:>6}{r['L']:>9.0f}{r['code']:>9.1f}{r['seg']:>5}"
              f"{100*r['fknee']:>7.0f}{r['rC']:>9.3f}{r['seC']:>7.3f}"
              f"{r['rL']:>9.1f}{r['seL']:>7.1f}"
              f"{100*r['rL']/max(r['L'],1):>7.2f}%{mark}")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leg", default="3<->5 full res")
    ap.add_argument("--session", default=None)
    ap.add_argument("--phase", default=None)
    ap.add_argument("--nbin", type=int, default=40)
    ap.add_argument("--T1", type=float, default=T1_REG)
    ap.add_argument("--P", dest="Pv", type=float, default=200.0)
    a = ap.parse_args()
    sess = [a.session] if a.session else [s for s, _, _ in SESSIONS]
    phs = [a.phase] if a.phase else list(PHASES)
    for s in sess:
        for p in phs:
            show(s, a.leg, p, a.nbin, Pv=a.Pv, T1=a.T1)


if __name__ == "__main__":
    main()
