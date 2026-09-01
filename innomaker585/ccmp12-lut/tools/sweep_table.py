#!/usr/bin/env python3
"""sweep_table.py — can ANY table parameter remove what is left on mode 3?

    sweep_table.py [--leg "3<->5 full res"]

The argument first, because it is arithmetic and the sweep only confirms it.
Above knee1 the decode is AFFINE and SHARED BY EVERY CHANNEL:

    Lhat = (C - P - a1) / s1        a1 = P + T1*(1-s1)/b

so the two knobs do exactly two things to a channel ratio:

    T1 (or P, or b)  ->  an ADDITIVE shift, common to all channels. In a ratio
                         that is d*(1/B - 1/G), which DECAYS with level.
    s1               ->  a MULTIPLICATIVE scale, common to all channels. A ratio
                         is scale-free, so it does not move at all.

A residual that is FLAT in level and DIFFERENT PER CHANNEL is orthogonal to
both. No LinearizationTable can produce it and none can remove it -- a table
takes the stored code and nothing else, and knows no channel.

The sweep is the numerical check on that argument. If some (T1, s1) did bring
mode 3 inside the control band, the argument would be wrong and worth finding
out cheaply. Run on the BLOCK data, which is where the model is fixed (this
pass's brief), with the patch ratios kept as the independent check.
"""
import os, sys, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fitcurve import PHASES, T1_REG, T2_REG, S1_REG, S2_REG          # noqa: E402
from legcache import LEGS                                            # noqa: E402
from blockratio import joined, decode                                # noqa: E402
from resid_neutral import neutral_mask                               # noqa: E402
from fit_all import SESSIONS                                         # noqa: E402
from ccmp_decode import T1_EFF                                       # noqa: E402


def score(J, m, b, T1, s1, glo=2000.0, ghi=12000.0):
    """dR/G and dB/G rms over neutral mid-range blocks, one (T1, s1)."""
    A = {p: decode(J[p]["y"], b, T1=T1, s1=s1) for p in PHASES}
    B = {p: J[p]["x"] for p in PHASES}
    gA = 0.5 * (A["G1"] + A["G2"])
    gB = 0.5 * (B["G1"] + B["G2"])
    k = m & (gB >= glo) & (gB <= ghi)
    if k.sum() < 50:
        return np.nan, np.nan, 0
    dr = 100 * ((A["R"][k] / gA[k]) / (B["R"][k] / gB[k]) - 1)
    db = 100 * ((A["B"][k] / gA[k]) / (B["B"][k] / gB[k]) - 1)
    return (float(np.sqrt((dr ** 2).mean())), float(np.sqrt((db ** 2).mean())),
            int(k.sum()))


def run(leg="3<->5 full res", nT1=13, ns1=11):
    b = LEGS[(SESSIONS[0][0], leg)][2]
    for sess, _, _ in SESSIONS:
        J = joined(sess, leg)
        m, _ = neutral_mask(J)
        print(f"\n{sess}  {leg}  b={b:g}   neutral mid-range blocks; "
              f"dB/G rms %, best in each row marked")
        # Fine in T1: the minimum is SHARP -- 5 codes of T1 costs 8 points of
        # dB/G -- so a coarse grid would report a floor it never reached and
        # make the conclusion look like a failure to search.
        s1s = S1_REG * np.linspace(0.98, 1.02, ns1)
        T1s = np.linspace(T1_REG - 3, T1_REG + 3, nT1)
        print("       s1 =" + "".join(f"{'1/%.2f' % (1/s):>9}" for s in s1s))
        best = (np.inf, None)
        for T1 in T1s:
            row = [score(J, m, b, T1, s)[1] for s in s1s]
            j = int(np.nanargmin(row))
            if row[j] < best[0]:
                best = (row[j], (T1, s1s[j]))
            print(f"  T1 {T1:7.1f}" + "".join(
                (f"{v:>8.2f}*" if i == j else f"{v:>9.2f}")
                for i, v in enumerate(row)))
        r0, b0, n = score(J, m, b, T1_EFF.get(b, T1_REG), S1_REG)
        print(f"  shipping (T1={T1_EFF.get(b, T1_REG):.4f}, s1=1/64): "
              f"dR/G {r0:.2f}%  dB/G {b0:.2f}%  on {n} blocks")
        print(f"  BEST anywhere in the sweep: dB/G {best[0]:.2f}% at "
              f"T1={best[1][0]:.1f}, s1=1/{1/best[1][1]:.3f}"
              f"   — against a same-class control of 0.06-0.07%")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leg", default="3<->5 full res")
    a = ap.parse_args()
    run(a.leg)


if __name__ == "__main__":
    main()
