#!/usr/bin/env python3
"""fit_all.py — §3.2 across the board: every leg, every phase, both sessions.

    fit_all.py [--kguard 3] [--sweep] [--boot 120] [--json out.json]

Runs fitcurve on all four legs (2<->4 and 3<->5, 17:05 and 18:37) and all four
CFA phases, then answers the three questions §3.2 exists to answer:

  1. Does the PEDESTAL land on the tag on its own?   (solved, never assumed)
  2. Does b come out 4 binned and 1 full res on its own?
  3. Do the two sessions agree?

NEVER MERGES THE SESSIONS (handoff §4, first bullet). Each is fitted alone and
agreement is a result, not an input.

The phases are not interchangeable and the table says so. AsShotNeutral is
0.625 1 0.5263, so raw R and B sit at 0.63 and 0.53 of G for the same patch:
R and B reach far below knee1 and own t1 and the pedestal, while only G reaches
above knee2 and owns t2. A phase that does not reach a knot reports "--" for it
rather than a number it did not measure.
"""
import os, sys, json, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modes as M                                                   # noqa: E402
from fitcurve import (leg_points, fit3, derive, closure, PHASES,     # noqa: E402
                      T1_REG, T2_REG, tile_bootstrap, seed_basin)

SESSIONS = [("17:05", "takes/ccmp-greycard", M.MODES),
            ("18:37", "takes/ccmp-greycard-1837", M.MODES_1837)]
# (section, name, A mode, B mode, expected b)
#
# §3.2's legs hold ClearHDR FIXED on both sides and change only the output bit
# depth, so g is 1 BY CONSTRUCTION and the slopes are only a check.
# §3.3's legs hold resolution and output depth fixed and change ClearHDR, so g
# is free and the SLOPES CARRY IT. That makes §3.3 an independent determination
# of b -- b = T1/(t1*g) rather than T1/t1 -- and not a second opinion on §3.2.
#
# The "ctrl" legs hold the CURVE fixed -- both takes linear, no compander
# anywhere -- and change everything else a leg can change: the take, the output
# bit depth, ClearHDR. They are the SAME-CLASS CONTROL for any block-level
# instrument, and §3.0b's 0.07% patch floor is their patch-level version. A
# residual that a control leg reproduces is a property of the takes, not of the
# transfer curve, and no LinearizationTable can remove it. They are matched in
# GEOMETRY so the block grid can be joined; 0<->1 and 4<->5 cannot be, which is
# why §3.0b had to use normalised patch boxes.
ALL_LEGS = [("3.2", "2<->4 binned", 2, 4, 4.0),
            ("3.2", "3<->5 full res", 3, 5, 1.0),
            ("3.3", "0<->2 binned", 2, 0, 4.0),
            ("3.3", "1<->3 full res", 3, 1, 1.0),
            ("ctrl", "0<->4 binned ctrl", 0, 4, 1.0),
            ("ctrl", "1<->5 full res ctrl", 1, 5, 1.0)]
# robust.py imports this and sweeps the knobs on §3.2's legs, where g is 1 by
# construction. Its key_numbers() dispatches on the leg NAME, so leave this as
# §3.2's two legs -- it is what produced the §3.2e robustness evidence.
LEGS = [l[1:] for l in ALL_LEGS if l[0] == "3.2"]


def take_dir(root, prefix):
    for d in sorted(os.listdir(root)):
        if d.startswith(prefix):
            return os.path.join(root, d)
    raise SystemExit(f"no take {prefix} under {root}")


def one(a, b, phase, kguard, bs, limit, boot, sweep, satmax=0.0):
    P = leg_points(a, b, phase, bs=bs, limit=limit, satmax=satmax)
    seed = (P["x"].max() * 0.05, P["x"].max() * 0.5)   # deliberately wrong
    d = derive(fit3(P, seed[0], seed[1], kguard))
    d["closure"] = closure(P, d)
    d["meta"] = P["meta"]
    d["xlo"], d["xhi"] = float(P["x"].min()), float(P["x"].max())
    if boot:
        d["boot"] = tile_bootstrap(P, seed[0], seed[1], kguard, ndraw=boot)
    if sweep:
        d["sweep"] = seed_basin(P, kguard)
    return d


def fmt(v, w=8, p=2, dash="--"):
    return f"{dash:>{w}}" if v is None or not np.isfinite(v) else f"{v:{w}.{p}f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kguard", type=float, default=3.0)
    ap.add_argument("--block", type=int, default=8)
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--boot", type=int, default=0)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--section", default="both",
                    choices=["3.2", "3.3", "both", "ctrl"],
                    help="which set of legs to run; 'both' is 3.2+3.3 and does "
                         "NOT include the linear ctrl legs, which have no curve "
                         "to fit")
    ap.add_argument("--satmax", type=float, default=0.0,
                    help="max saturated-pixel fraction per block; 0 rejects a "
                         "block with a single pinned pixel")
    ap.add_argument("--json")
    a = ap.parse_args()
    legs = [l[1:] for l in ALL_LEGS
            if (l[0] in ("3.2", "3.3") if a.section == "both"
                else l[0] == a.section)]

    res = {}
    for sess, root, mm in SESSIONS:
        for lname, am, bm, b_exp in legs:
            A = take_dir(root, mm[am][0])
            B = take_dir(root, mm[bm][0])
            print("=" * 118)
            print(f"SESSION {sess}   LEG {lname}   mode {am} (12b CCMP) against "
                  f"mode {bm} (16b linear)   b should come out {b_exp:.0f}")
            print(f"  {'ph':<3}{'x range':>13}"
                  f"{'g0=m0':>9}{'g1=64m1':>9}{'g2=16m2':>9}{'g':>9}{'spr':>7}"
                  f"{'t1':>9}{'+/-':>6}{'t2':>10}{'+/-':>6}"
                  f"{'b(t1)':>8}{'b(t2)':>8}"
                  f"{'P(s0,g)':>9}{'P(seg1)':>9}{'clos':>8}")
            for ph in PHASES:
                d = one(A, B, ph, a.kguard, a.block, a.limit, a.boot, a.sweep,
                        a.satmax)
                res[(sess, lname, ph)] = d
                xr = "%.0f..%.0f" % (d["xlo"], d["xhi"])
                print(f"  {ph:<3}{xr:>13}"
                      f"{fmt(d['g0'],9,4)}{fmt(d['g1'],9,4)}{fmt(d['g2'],9,4)}"
                      f"{fmt(d['g'],9,4)}{fmt(d['g_spread'],7,4)}"
                      f"{fmt(d['t1'],9,1)}{fmt(d['se_t1'],6,1)}"
                      f"{fmt(d['t2'],10,1)}{fmt(d['se_t2'],6,1)}"
                      f"{fmt(d['b_from_t1'],8,4)}{fmt(d['b_from_t2'],8,4)}"
                      f"{fmt(d['P_seg0_unit'],9)}"
                      f"{fmt(d['P_seg1_anchored'],9)}"
                      f"{fmt(d['closure']['rms'],8)}")
                if "boot" in d:
                    bo = d["boot"]
                    print(f"     {'bootstrap 1s':<11}{'':>19}{fmt(bo['t1'],10)}{'':>7}"
                          f"{fmt(bo['t2'],11)}{'':>7}{fmt(bo['b_from_t1'],10,4)}"
                          f"{fmt(bo['b_from_t2'],12,4)}{fmt(bo['P'],11)}")
                if "sweep" in d:
                    s = d["sweep"]
                    print(f"     seed basin ({s['n']} deliberately wrong seeds): "
                          f"t1 [{s['t1'][0]:.2f},{s['t1'][1]:.2f}]  "
                          f"t2 [{s['t2'][0]:.2f},{s['t2'][1]:.2f}]  "
                          f"P [{s['P'][0]:.2f},{s['P'][1]:.2f}]")

    # ── the questions ──────────────────────────────────────────────────────
    print("\n" + "=" * 118)
    print("ANSWER 0 — g, the sensitivity ratio, measured three ways per phase. "
          "On §3.2's legs g is 1 BY CONSTRUCTION")
    print("           (both takes ClearHDR) and this is a check. On §3.3's legs "
          "g is FREE and the slopes carry it,")
    print("           which is what makes §3.3's b independent rather than a "
          "second opinion on §3.2's arithmetic.")
    print(f"  {'session':>8}{'leg':>16}{'g0 (seg0)':>22}{'g1 (64*m1)':>22}"
          f"{'g2 (16*m2)':>22}{'combined':>11}")
    for sess, _, _ in SESSIONS:
        for lname, _, _, _ in legs:
            cols = []
            for k in ("g0", "g1", "g2"):
                v = [res[(sess, lname, p)][k] for p in PHASES]
                v = [z for z in v if np.isfinite(z)]
                cols.append(("%.4f (n=%d, %.4f..%.4f)" % (np.mean(v), len(v),
                             min(v), max(v))) if v else "-- absent --")
            allg = [res[(sess, lname, p)]["g"] for p in PHASES]
            allg = [z for z in allg if np.isfinite(z)]
            print(f"  {sess:>8}{lname:>16}{cols[0]:>22}{cols[1]:>22}"
                  f"{cols[2]:>22}{np.mean(allg) if allg else float('nan'):>11.4f}")

    print("\nANSWER 1 — b, solved per leg.  t1 from R and B (they reach below knee1); "
          "t2 from G1 and G2 (only they reach above knee2).")
    print("           b = T/(t*g), NOT T/t: the knots alone give only the product "
          "b*g, and the slopes are what separate them.")
    print(f"  {'session':>8}{'leg':>16}{'b from t1':>26}{'b from t2':>26}")
    bs_ = {}
    for sess, _, _ in SESSIONS:
        for lname, _, _, b_exp in legs:
            v1 = [res[(sess, lname, p)]["b_from_t1"] for p in PHASES]
            v2 = [res[(sess, lname, p)]["b_from_t2"] for p in PHASES]
            v1 = [v for v in v1 if np.isfinite(v)]
            v2 = [v for v in v2 if np.isfinite(v)]
            bs_[(sess, lname)] = (v1, v2)
            f = lambda v: (("%.4f  (n=%d, %.4f..%.4f)" % (np.mean(v), len(v),   # noqa
                            min(v), max(v))) if v else "-- not reached --")
            print(f"  {sess:>8}{lname:>16}  {f(v1):>28}  {f(v2):>28}   expect {b_exp:.0f}")

    print("\nANSWER 1b — the same b WITHOUT any register value: the ratio of the "
          "two legs' knots.")
    print("  On §3.2's legs g is 1 on both, so t2(full)/t2(binned) is the ratio "
          "of b directly. On §3.3's legs")
    print("  each knot carries its own g, so the ratio must be divided by "
          "g(full)/g(binned) to leave b.")
    names = [l[0] for l in legs]
    for bn, fn in (("2<->4 binned", "3<->5 full res"),
                   ("0<->2 binned", "1<->3 full res")):
        if bn not in names or fn not in names:
            continue
        for sess, _, _ in SESSIONS:
            tb = [res[(sess, bn, p)]["t2"] for p in PHASES]
            tf = [res[(sess, fn, p)]["t2"] for p in PHASES]
            gb = [res[(sess, bn, p)]["g"] for p in PHASES]
            gf = [res[(sess, fn, p)]["g"] for p in PHASES]
            pair = [(a_, b_, c_, d_) for a_, b_, c_, d_ in zip(tb, tf, gb, gf)
                    if all(np.isfinite(z) for z in (a_, b_, c_, d_))]
            if not pair:
                continue
            r = [(b_ / a_) * (d_ / c_) for a_, b_, c_, d_ in pair]
            print(f"  {sess}  {bn} vs {fn}:  t2 {np.mean([p[0] for p in pair]):8.1f}"
                  f" / {np.mean([p[1] for p in pair]):9.1f}   "
                  f"b ratio {np.mean(r):.4f}  "
                  f"({', '.join(f'{v:.4f}' for v in r)})   expect 4")

    print("\nANSWER 2 — the pedestal, solved. Only R, G1, G2, B on the FULL RES leg "
          "have slope-1 data; the")
    print("           binned leg's darkest patch sits above its own knee1, so there "
          "P comes from segment 1.")
    print(f"  {'session':>8}{'leg':>16}{'P (seg0, slope==1)':>34}"
          f"{'P (seg1)':>26}   tag")
    for sess, _, _ in SESSIONS:
        for lname, am, _, _ in legs:
            p0 = [res[(sess, lname, p)]["P_seg0_unit"] for p in PHASES]
            p1 = [res[(sess, lname, p)]["P_seg1_anchored"] for p in PHASES]
            p0 = [v for v in p0 if np.isfinite(v)]
            p1 = [v for v in p1 if np.isfinite(v)]
            f = lambda v: (("%.2f  (%.2f..%.2f)" % (np.mean(v), min(v), max(v)))  # noqa
                           if v else "-- no slope-1 data --")
            print(f"  {sess:>8}{lname:>16}  {f(p0):>32}  {f(p1):>24}   200")

    print("\nANSWER 3 — session agreement. Fitted separately, never merged.")
    print(f"  {'leg':>16}{'quantity':>12}{'17:05':>12}{'18:37':>12}{'diff':>10}")
    for lname, _, _, _ in legs:
        for key, lbl in (("t1", "t1"), ("t2", "t2"), ("P_seg0_unit", "P seg0"),
                         ("P_seg1", "P seg1")):
            v = []
            for sess, _, _ in SESSIONS:
                q = [res[(sess, lname, p)][key] for p in PHASES]
                q = [z for z in q if np.isfinite(z)]
                v.append(np.mean(q) if q else np.nan)
            if np.isfinite(v[0]) or np.isfinite(v[1]):
                dd = v[1] - v[0]
                pc = 100 * dd / v[0] if v[0] else np.nan
                print(f"  {lname:>16}{lbl:>12}{fmt(v[0],12)}{fmt(v[1],12)}"
                      f"{fmt(dd,10)}   ({pc:+.2f}%)")

    if a.json:
        def clean(o):
            if isinstance(o, dict):
                return {k: clean(v) for k, v in o.items()
                        if k not in ("seg", "msk", "x", "y", "ex", "ey")}
            if isinstance(o, (list, tuple)):
                return [clean(v) for v in o]
            if isinstance(o, (np.floating, np.integer)):
                return float(o)
            if isinstance(o, float) and not np.isfinite(o):
                return None
            return o
        json.dump({f"{k[0]}|{k[1]}|{k[2]}": clean(v) for k, v in res.items()},
                  open(a.json, "w"), indent=1, default=str)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
