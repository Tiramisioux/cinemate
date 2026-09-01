#!/usr/bin/env python3
"""anchor.py — measure the MIDDLE SEGMENT'S ANCHOR, which is what the residual is.

    anchor.py [--section 3.2] [--json evidence/anchor.json]

WHAT THIS MEASURES AND WHY IT IS THE RIGHT QUANTITY.

The model's middle and high segments both hang off ONE number,

    a1 = P + T1*(1 - s1)/b          the companded code at which the middle
                                    segment would cross x = 0

and every one of P, T1 and b enters the middle segment ONLY through it. So on
the middle segment they are DEGENERATE -- no amount of mid-segment data can
separate a pedestal error from a threshold error from a binning error. What the
data does determine, and to +/-0.04 codes, is a1 itself. The table needs a1 and
nothing else, because the table inverts the curve.

The residual is fitted as a LINE IN x, not summarised as a mean:

    d(x) = delta_c + kappa * (x - t)          t = the segment's own knot

  delta_c   the offset AT THE KNOT -- the anchor error. Immune to the level-
            dependent term, which is what kappa absorbs.
  kappa     a level-dependent term. The transfer is phase-independent (§2), so
            a kappa that DIFFERS BETWEEN PHASES is not the curve and cannot be
            fixed by any LinearizationTable. Reported beside delta_c so the two
            are never confused.

Run on both segments. delta_c equal on mid and high means one anchor error and
no T2 error; delta_c differing means T2 as well, and the difference gives it:

    delta_c(high) - delta_c(mid) = -(s1 - s2) * dT2 / b

WHY THE IDENTITY SEGMENT IS THE REFERENCE. delta_c is quoted against the model
line P + x with P = 200 and slope exactly 1 -- the tag (§2, measured on all six
modes) and the only slope the hardware has no register for. Fitting the low
segment free instead is what §3.2c did, and over its short lever arm the free
slope and intercept are anticorrelated enough to put t1 anywhere in 497.4-502.0
-- a +/-2.5-code spread, which is +/-160 L on the middle segment. The anchor is
150x better determined than the knot it implies. Use it.
"""
import os, sys, json, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fitcurve import (model_A, PHASES, T1_REG, T2_REG,               # noqa: E402
                      S1_REG, S2_REG, wls_line)
from legcache import points, LEGS                                    # noqa: E402
from resid_profile import resid                                      # noqa: E402
from fit_all import SESSIONS                                         # noqa: E402

SEGN = {0: "low", 1: "mid", 2: "high"}


def anchor(P, b, seg=1, Pv=200.0, T1=T1_REG, T2=T2_REG, s1=S1_REG, s2=S2_REG):
    """delta_c and kappa for one segment of one leg-phase."""
    R = resid(P, Pv=Pv, bv=b, T1=T1, T2=T2, s1=s1, s2=s2)
    m = (R["seg"] == seg) & ~R["knee"]
    n = int(m.sum())
    t = {0: 0.0, 1: T1 / b, 2: T2 / b}[seg]
    if n < 40:
        return dict(n=n, dc=np.nan, se=np.nan, kappa=np.nan, m=np.nan,
                    xlo=np.nan, xhi=np.nan)
    x, d = R["x"][m] - t, R["rC"][m]
    A = np.vstack([np.ones_like(x), x]).T
    coef, *_ = np.linalg.lstsq(A, d, rcond=None)
    res = d - A @ coef
    cov = np.linalg.inv(A.T @ A) * (res @ res) / max(n - 2, 1)
    return dict(n=n, dc=float(coef[0]), se=float(np.sqrt(cov[0, 0])),
                kappa=float(coef[1]), m=float(np.mean(d)),
                xlo=float(R["x"][m].min()), xhi=float(R["x"][m].max()))


def run(section="3.2", **kw):
    legs = [(s, l[1], l[4]) for s, _, _ in SESSIONS for l in
            __import__("fit_all").ALL_LEGS if l[0] == section]
    out = {}
    print("delta_c = the residual AT THE KNOT, in companded code. kappa = its "
          "level-dependent part per unit x.")
    print("dL/dC is 64 on the middle segment and 16 on the high one, so "
          "delta_c is also delta_c*dL/dC in L.\n")
    print(f"  {'session':>7}{'leg':>16}{'ph':>4}{'seg':>6}{'n':>7}"
          f"{'x range':>16}{'slope err':>11}"
          f"{'delta_c':>10}{'+/-':>7}{'-> L':>8}{'kappa*1e5':>11}")
    for sess, leg, b_exp in legs:
        for ph in PHASES:
            Pp = points(sess, leg, ph)
            for seg in (0, 1, 2):
                a = anchor(Pp, b_exp, seg, **kw)
                if not np.isfinite(a["dc"]):
                    continue
                out[(sess, leg, ph, seg)] = a
                dLdC = {0: 1.0, 1: 1 / S1_REG, 2: 1 / S2_REG}[seg]
                print(f"  {sess:>7}{leg:>16}{ph:>4}{SEGN[seg]:>6}{a['n']:>7}"
                      f"{a['xlo']:>7.0f}..{a['xhi']:<7.0f}"
                      f"{'':>11}"
                      f"{a['dc']:>10.3f}{a['se']:>7.3f}{a['dc']*dLdC:>8.1f}"
                      f"{1e5*a['kappa']:>11.2f}")
        print()
    return out


def summary(out, section="3.2"):
    """The anchor per leg, and the effective T1 it implies."""
    print("=" * 112)
    print("THE ANCHOR, per leg. a1 = P + T1*(1-s1)/b, and P, T1, b are "
          "DEGENERATE in it (see the docstring).")
    print("T1_eff is what the whole offset looks like if it is assigned to T1 "
          "with P held at the measured tag 200.\n")
    print(f"  {'session':>7}{'leg':>20}{'b':>4}{'delta_c mid':>13}{'spread':>8}"
          f"{'delta_c high':>14}{'spread':>8}{'-> T1_eff':>11}{'dT2':>9}")
    rows = {}
    for (sess, leg, ph, seg), a in out.items():
        rows.setdefault((sess, leg), {}).setdefault(seg, []).append((ph, a))
    for (sess, leg) in sorted(rows):
        b = LEGS[(sess, leg)][2]
        mid = [a["dc"] for _, a in rows[(sess, leg)].get(1, [])]
        hi = [a["dc"] for _, a in rows[(sess, leg)].get(2, [])]
        if not mid:
            continue
        dcm = float(np.mean(mid))
        # a1 = P + T1*(1-s1)/b, so an offset dc on the anchor is T1_eff:
        t1e = (T1_REG * (1 - S1_REG) / b + dcm) * b / (1 - S1_REG)
        dt2 = ((float(np.mean(hi)) - dcm) * b / -(S1_REG - S2_REG)) if hi else np.nan
        print(f"  {sess:>7}{leg:>20}{b:>4.0f}{dcm:>13.3f}"
              f"{(max(mid)-min(mid)):>8.3f}"
              + (f"{float(np.mean(hi)):>14.3f}{(max(hi)-min(hi)):>8.3f}"
                 if hi else f"{'--':>14}{'--':>8}")
              + f"{t1e:>11.2f}"
              + (f"{dt2:>9.0f}" if np.isfinite(dt2) else f"{'--':>9}"))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--section", default="3.2")
    ap.add_argument("--T1", type=float, default=T1_REG)
    ap.add_argument("--P", dest="Pv", type=float, default=200.0)
    ap.add_argument("--json")
    a = ap.parse_args()
    out = run(a.section, Pv=a.Pv, T1=a.T1)
    rows = summary(out, a.section)
    if a.json:
        json.dump({"|".join(map(str, k)): v for k, v in out.items()},
                  open(a.json, "w"), indent=1,
                  default=lambda o: None if not np.isfinite(o) else float(o))
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
