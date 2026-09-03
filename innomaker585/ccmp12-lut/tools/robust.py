#!/usr/bin/env python3
"""robust.py — does the §3.2 answer survive the knobs?

    robust.py [--limit 6]

Every number in a fit is hostage to the choices made around it. This sweeps the
four that could plausibly manufacture the answer, on all four legs:

  kguard    how far from a knee a block must sit to be fitted. Too small and the
            knee rounding (§4) pulls the knots in; too large and the lever arm
            for the slope-1 segment disappears. The answer must sit on a plateau
            in between, and the plateau must be wide.
  seed      where the segmentation iteration starts. Started from deliberately
            wrong knot pairs, it must land on the same fixed point every time --
            otherwise the register values entered through the seed and the
            "confirmation" is circular.
  block     8x8 or 16x16 on the phase plane. A different block size is a
            different set of region means, a different within-block spread and a
            different set of edge blocks.
  black     the B take's black from the lens-cap measurement or from its tag.
            P is one-for-one sensitive to this, so it bounds P's systematic.

Plus a spatial-tile bootstrap, which is the only one of these that reports an
uncertainty rather than a sensitivity.
"""
import os, sys, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modes as M                                                    # noqa: E402
from fitcurve import (leg_points, fit3, derive, PHASES, seed_basin,    # noqa: E402
                      T1_REG, T2_REG, tile_bootstrap)
from fit_all import take_dir, SESSIONS, LEGS                          # noqa: E402


def solve(P, kguard, seed=None):
    s = seed or (P["x"].max() * 0.05, P["x"].max() * 0.5)
    return derive(fit3(P, s[0], s[1], kguard))


def key_numbers(d, leg):
    """The two numbers this leg/phase is actually responsible for."""
    if leg.startswith("2"):                       # binned: t2 -> b, seg1 -> P
        return d["b_from_t2"], d["P_seg1_anchored"]
    return d["b_from_t1"], d["P_seg0_unit"]       # full res: t1 -> b, seg0 -> P


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=6)
    a = ap.parse_args()
    KG = [2.0, 2.5, 3.0, 4.0, 5.0, 6.0]

    print("=" * 112)
    print("1. kguard — the knee guard, in units of the block's OWN within-block "
          "pixel spread")
    print("   binned leg reports b from t2 and P from seg1; full res reports b "
          "from t1 and P from seg0.")
    store = {}
    for sess, root, mm in SESSIONS:
        for lname, am, bm, b_exp in LEGS:
            A, B = take_dir(root, mm[am][0]), take_dir(root, mm[bm][0])
            print(f"\n  {sess}  {lname}   (b should be {b_exp:.0f}, P should be 200)")
            print(f"      {'phase':<6}" + "".join(f"{f'k={k:g}':>17}" for k in KG))
            for ph in PHASES:
                P = leg_points(A, B, ph, limit=a.limit)
                store[(sess, lname, ph)] = P
                cells = []
                for k in KG:
                    d = solve(P, k)
                    bb, pp = key_numbers(d, lname)
                    cells.append(f"{bb:.4f}/{pp:.1f}" if np.isfinite(bb)
                                 and np.isfinite(pp) else "--")
                print(f"      {ph:<6}" + "".join(f"{c:>17}" for c in cells))
            print(f"      (cells are  b / P)")

    print("\n" + "=" * 112)
    print("2. seed — the iteration started from a grid of deliberately wrong "
          "ORDERED knot pairs, spanning")
    print("   0.5%..40% of the data range for t1 and 10%..95% for t2. If the "
          "register values had entered")
    print("   through the seed, this would spread. Each leg is asked for the knot "
          "it is responsible for.")
    print(f"  {'session':>7}{'leg':>16}{'phase':>7}{'knot':>6}{'seeds':>7}"
          f"{'reached the mode':>18}{'value':>12}{'spread among those':>22}")
    for (sess, lname, ph), P in store.items():
        which = "t2" if lname.startswith("2") else ("t1" if ph in ("R", "B") else "t2")
        s = seed_basin(P, 3.0, which=which)
        span = ("%.4f" % (s["hi"] - s["lo"])) if s["nconv"] else "--"
        print(f"  {sess:>7}{lname:>16}{ph:>7}{which:>6}{s['n']:>7}"
              f"{("%d/%d" % (s["nconv"], s["n"])):>18}"
              f"{s['med']:>12.2f}{span:>22}")

    print("\n" + "=" * 112)
    print("3. block size and 4. which black level for the B take")
    print(f"  {'session':>7}{'leg':>16}{'phase':>7}{'8x8 meas':>18}{'16x16 meas':>18}"
          f"{'8x8 tag':>18}   (b / P)")
    for sess, root, mm in SESSIONS:
        for lname, am, bm, b_exp in LEGS:
            A, B = take_dir(root, mm[am][0]), take_dir(root, mm[bm][0])
            for ph in ("R", "G1"):
                cells = []
                for bs, mb in ((8, True), (16, True), (8, False)):
                    P = leg_points(A, B, ph, bs=bs, limit=a.limit,
                                   measured_black=mb)
                    d = solve(P, 3.0)
                    bb, pp = key_numbers(d, lname)
                    cells.append(f"{bb:.4f} / {pp:.2f}" if np.isfinite(bb)
                                 and np.isfinite(pp) else "--")
                print(f"  {sess:>7}{lname:>16}{ph:>7}" +
                      "".join(f"{c:>18}" for c in cells))

    print("\n" + "=" * 112)
    print("5. spatial-tile bootstrap, 150 draws — 1 sigma, not a sensitivity")
    print(f"  {'session':>7}{'leg':>16}{'phase':>7}{'sd(t1)':>10}{'sd(t2)':>10}"
          f"{'sd(P)':>9}{'sd(b), relevant knot':>26}")
    for (sess, lname, ph), P in store.items():
        if ph not in ("R", "G1"):
            continue
        s = (P["x"].max() * 0.05, P["x"].max() * 0.5)
        bo = tile_bootstrap(P, s[0], s[1], 3.0, ndraw=150)
        sdb = bo["b_from_t2"] if lname.startswith("2") else bo["b_from_t1"]
        print(f"  {sess:>7}{lname:>16}{ph:>7}{bo['t1']:>10.2f}{bo['t2']:>10.2f}"
              f"{bo['P']:>9.2f}{sdb:>26.4f}   {bo['ndegenerate']}/{bo['ndraw']} degenerate")


if __name__ == "__main__":
    main()
