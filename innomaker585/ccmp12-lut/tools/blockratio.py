#!/usr/bin/env python3
"""blockratio.py — the acceptance metric on BLOCKS instead of nine patches.

    blockratio.py [--leg "3<->5 full res"] [--nbin 12]

§3.5 measured the decode against its linear reference on 9 chart patches, two of
them flare-exposed. This asks the same question of the same takes on 2-19 k
blocks, joined on the BLOCK GRID so all four CFA phases describe the same piece
of chart:

    for each block   R/G and B/G  from the DECODED CCMP take
                     R/G and B/G  from the LINEAR reference take
                     difference   <- the acceptance metric, per block

Joining on (gy, gx) is what makes "same patch" and "same channel" separable. A
residual that is the same for all four phases at one block is a property of the
SCENE or the position; one that differs between phases at one block is a
property of the CHANNEL. Comparing phases at the same L cannot tell those apart,
because at one L the four phases are looking at four different patches.

Both takes are co-registered and the same block mask is intersected across the
four phases, so nothing here pairs a block with a different piece of chart.
"""
import os, sys, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modes as M                                                      # noqa: E402
from fitcurve import ccmp_inv, PHASES, T1_REG, T2_REG, S1_REG, S2_REG  # noqa: E402
from legcache import points, LEGS                                      # noqa: E402
from fit_all import SESSIONS                                           # noqa: E402


def joined(sess, leg, **kw):
    """Blocks that survive in ALL FOUR phases, keyed on the block grid."""
    Ps = {p: points(sess, leg, p, **kw) for p in PHASES}
    keys = None
    for p in PHASES:
        k = Ps[p]["gy"].astype(np.int64) * 100000 + Ps[p]["gx"]
        keys = k if keys is None else np.intersect1d(keys, k)
    out = {}
    for p in PHASES:
        k = Ps[p]["gy"].astype(np.int64) * 100000 + Ps[p]["gx"]
        o = np.argsort(k)
        idx = o[np.searchsorted(k[o], keys)]
        out[p] = {n: Ps[p][n][idx] for n in ("x", "y", "sx", "gy", "gx")}
    out["n"] = keys.size
    out["shape"] = Ps["R"]["shape"]
    return out


def decode(y, b, P=200.0, T1=T1_REG, T2=T2_REG, s1=S1_REG, s2=S2_REG):
    return ccmp_inv(b * (np.asarray(y, float) - P), T1, T2, s1, s2) / b


def ratios(J, b, black=None, **kw):
    """Decoded and reference R/G, B/G per block.

    y here is a block MEAN of raw codes, so this is the linearised check, not
    the deliverable's own path -- legitimate only because the decode is linear
    within a segment and knee blocks are flagged. The acceptance gate decodes
    per pixel, in patches.py.

    black is a {phase: level} map: pass it for a LINEAR A take, where the right
    operation is subtract-black and nothing else. Running such a take through
    ccmp_inv would decompand data that was never companded.
    """
    if black is not None:
        A = {p: J[p]["y"] - black[p] for p in PHASES}
    else:
        A = {p: decode(J[p]["y"], b, **kw) for p in PHASES}
    B = {p: J[p]["x"] for p in PHASES}
    gA = 0.5 * (A["G1"] + A["G2"])
    gB = 0.5 * (B["G1"] + B["G2"])
    return dict(rgA=A["R"] / gA, bgA=A["B"] / gA, rgB=B["R"] / gB, bgB=B["B"] / gB,
                gA=gA, gB=gB, A=A, B=B)


def test_same_block(sess, leg, nb=10, **kw):
    """At ONE block, do the four phases share a residual, or not?"""
    b = LEGS[(sess, leg)][2]
    J = joined(sess, leg)
    d = {p: decode(J[p]["y"], b, **kw) - J[p]["x"] for p in PHASES}   # residual in L
    g = 0.5 * (J["G1"]["x"] + J["G2"]["x"])
    print(f"\n{sess}  {leg}  — RESIDUAL IN L AT THE SAME BLOCK, by phase "
          f"({J['n']} blocks in all four phases)")
    print(f"  {'G level':>9}{'n':>7}" + "".join(f"{p:>10}" for p in PHASES)
          + f"{'G1-G2':>9}{'B-R':>9}")
    o = np.argsort(g)
    for idx in np.array_split(o, nb):
        row = [float(d[p][idx].mean()) for p in PHASES]
        print(f"  {g[idx].mean():>9.0f}{idx.size:>7}"
              + "".join(f"{v:>10.1f}" for v in row)
              + f"{row[1]-row[2]:>9.1f}{row[3]-row[0]:>9.1f}")
    return d, g


def test_acceptance(sess, leg, nb=10, linear=False, **kw):
    """The acceptance metric per block: decoded R/G, B/G against the reference.

    linear=True skips the decode entirely -- for the ctrl legs, where BOTH takes
    are linear and the answer is the instrument's own floor. Ratios are
    scale-free, so no exposure ratio and no black-referred gain enter: a control
    leg needs no fitting at all.
    """
    am, _, b, _ = LEGS[(sess, leg)]
    J = joined(sess, leg)
    R = (ratios(J, 1.0, black=M.MEASURED_BLACK[am]) if linear
         else ratios(J, b, **kw))
    dRG = 100 * (R["rgA"] - R["rgB"]) / R["rgB"]
    dBG = 100 * (R["bgA"] - R["bgB"]) / R["bgB"]
    print(f"\n{sess}  {leg}  — {'CONTROL (both linear)' if linear else 'DECODED'}"
          f" vs REFERENCE, per block, % of the ratio")
    print(f"  {'G level':>9}{'n':>7}{'dR/G %':>9}{'+/-':>7}{'dB/G %':>9}{'+/-':>7}"
          f"{'refR/G':>9}{'refB/G':>9}")
    o = np.argsort(R["gB"])
    for idx in np.array_split(o, nb):
        print(f"  {R['gB'][idx].mean():>9.0f}{idx.size:>7}"
              f"{dRG[idx].mean():>9.3f}{dRG[idx].std()/np.sqrt(idx.size):>7.3f}"
              f"{dBG[idx].mean():>9.3f}{dBG[idx].std()/np.sqrt(idx.size):>7.3f}"
              f"{R['rgB'][idx].mean():>9.4f}{R['bgB'][idx].mean():>9.4f}")
    print(f"  ALL  rms  dR/G {np.sqrt((dRG**2).mean()):.3f}%   "
          f"dB/G {np.sqrt((dBG**2).mean()):.3f}%")
    return dRG, dBG, R


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leg", default="3<->5 full res")
    ap.add_argument("--session", default=None)
    ap.add_argument("--nbin", type=int, default=10)
    ap.add_argument("--linear", action="store_true",
                    help="both takes linear — the control; no decode is applied")
    ap.add_argument("--T1", type=float, default=T1_REG)
    ap.add_argument("--P", dest="Pv", type=float, default=200.0)
    a = ap.parse_args()
    for s in ([a.session] if a.session else [x for x, _, _ in SESSIONS]):
        if not a.linear:
            test_same_block(s, a.leg, a.nbin, P=a.Pv, T1=a.T1)
        test_acceptance(s, a.leg, a.nbin, linear=a.linear, P=a.Pv, T1=a.T1)


if __name__ == "__main__":
    main()
