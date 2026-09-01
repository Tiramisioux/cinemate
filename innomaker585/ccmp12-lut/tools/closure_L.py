#!/usr/bin/env python3
"""closure_L.py — §3.2d's closure re-expressed in L, per SEGMENT, per PHASE.

    closure_L.py [--regs] [--section 3.2] [--bins] [--json out.json]

WHY THIS EXISTS. §3.2d reported its closure as an rms in the CODE domain --
"0.37 codes binned, 1.43-1.91 full res" -- and 0.37 codes reads like a closed
case. It is not. The deliverable INVERTS this curve, so the same error lands in
the delivered linear domain multiplied by the local dL/dC:

    low segment   dL/dC =  1
    mid segment   dL/dC = 64        <- 0.37 codes is 23.7 L here
    high segment  dL/dC = 16

That is the whole of the §3.5 residual, and the code-domain rms concealed it for
two passes (handoff §4, added by §3.5). So: report in L, per segment, with
dL/dC beside it, and report the SIGNED MEAN as well as the rms -- an rms cannot
tell a model error from scatter.

  signed mean structured by level  -> the MODEL is wrong
  signed mean ~ zero               -> scatter, and §3.5's residual is something
                                      else entirely

--regs runs the genuinely zero-free-parameter form: P = 200 (the tag), b = 4/1
(the design values), g = 1, knots and slopes from the registers. Without it the
solved P and b are used, which is what fit_all has always done.

⚠ --anchored WITHOUT --regs IS NOT §3.6c. The anchor is a correction to the
REGISTER curve, so reading it requires holding P, b and g at their register/tag
values -- otherwise the per-phase fit re-absorbs it through its own solved P and
b and the number means nothing. §3.6c's table is `--regs --anchored`. Run bare
`--anchored` and mode 2's middle segment reads -14.8 L instead of -0.7..+1.5,
which looks like the anchor made it worse by an order of magnitude. It did not.
This warns if you ask for it.

NEVER MERGES THE SESSIONS (handoff §4).
"""
import os, sys, json, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modes as M                                                   # noqa: E402
from fitcurve import (leg_points, fit3, derive, closure, PHASES,     # noqa: E402
                      T1_REG, T2_REG, S1_REG, S2_REG)
from fit_all import SESSIONS, ALL_LEGS, take_dir                    # noqa: E402
from ccmp_decode import T1_EFF                                      # noqa: E402


def fmt(v, w=8, p=2, dash="--"):
    return f"{dash:>{w}}" if v is None or not np.isfinite(v) else f"{v:{w}.{p}f}"


def run(section="3.2", regs=False, kguard=3.0, bs=8, limit=6, satmax=0.0,
        show_bins=True, T1=T1_REG, T2=T2_REG, s1=S1_REG, s2=S2_REG,
        quiet=False, anchored=False):
    legs = [l[1:] for l in ALL_LEGS
            if (l[0] in ("3.2", "3.3") if section == "both" else l[0] == section)]
    if anchored and not regs and not quiet:
        print("!" * 116)
        print("!! --anchored WITHOUT --regs IS NOT §3.6c AND THE NUMBERS BELOW ARE NOT COMPARABLE TO IT.")
        print("!! The anchor corrects the REGISTER curve. Without --regs the per-phase fit re-absorbs it")
        print("!! through its own solved P and b, and the residual is not the anchor's. Use --regs --anchored.")
        print("!" * 116)
    out = {}
    for sess, root, mm in SESSIONS:
        for lname, am, bm, b_exp in legs:
            # anchored: the measured per-mode T1 (§3.6), which is the whole
            # point of a re-run. Never one T1 for both modes -- the anchor does
            # not scale as 1/b, so a single value cannot serve them.
            t1v = T1_EFF.get(b_exp, T1_REG) if anchored else T1
            A = take_dir(root, mm[am][0])
            B = take_dir(root, mm[bm][0])
            if not quiet:
                print("=" * 116)
                print(f"SESSION {sess}   LEG {lname}   mode {am} against mode {bm}"
                      f"   {'REGISTER/TAG values' if regs else 'solved P, b, g'}"
                      f"   T1={t1v:g} T2={T2:g} s1=1/{1/s1:g} s2=1/{1/s2:g}")
                print(f"  {'ph':<4}{'segment':<10}{'n':>6}{'dL/dC':>7}"
                      f"{'L range':>17}"
                      f"{'bias C':>9}{'rms C':>8}   "
                      f"{'BIAS L':>10}{'+/-':>8}{'rms L':>9}{'bias/L':>9}")
            for ph in PHASES:
                P = leg_points(A, B, ph, bs=bs, limit=limit, satmax=satmax)
                seed = (P["x"].max() * 0.05, P["x"].max() * 0.5)
                d = derive(fit3(P, seed[0], seed[1], kguard))
                kw = dict(T1=t1v, T2=T2, s1=s1, s2=s2)
                if regs:
                    kw.update(Pv=200.0, bv=b_exp, gv=1.0)
                c = closure(P, d, **kw)
                out[(sess, lname, ph)] = dict(closure=c, t1=d["t1"], t2=d["t2"],
                                              b=d["b"], P=d["P"], g=d["g"],
                                              xlo=float(P["x"].min()),
                                              xhi=float(P["x"].max()))
                if quiet:
                    continue
                for s in c["segs"]:
                    lr = f"{s['Llo']:.0f}..{s['Lhi']:.0f}"
                    print(f"  {ph:<4}{s['name']:<10}{s['n']:>6}{s['dLdC']:>7.0f}"
                          f"{lr:>17}"
                          f"{s['bias']:>9.3f}{s['rms']:>8.3f}   "
                          f"{s['bias_L']:>10.1f}{s['se_L']:>8.1f}{s['rms_L']:>9.1f}"
                          f"{s['frac']:>8.2f}%")
                    if show_bins:
                        for b_ in c["bins"]:
                            if b_["seg"] != s["seg"]:
                                continue
                            lr = f"{b_['Llo']:.0f}..{b_['Lhi']:.0f}"
                            print(f"  {'':<4}{'  bin':<10}{b_['n']:>6}{'':>7}"
                                  f"{lr:>17}{b_['bias']:>9.3f}{'':>8}   "
                                  f"{b_['bias_L']:>10.1f}{b_['se_L']:>8.1f}"
                                  f"{'':>9}{b_['frac']:>8.2f}%")
                print(f"  {ph:<4}{'ALL':<10}{c['n']:>6}{'':>7}{'':>17}"
                      f"{c['bias']:>9.3f}{c['rms']:>8.3f}   "
                      f"{c['bias_L']:>10.1f}{'':>8}{c['rms_L']:>9.1f}"
                      f"      knee n={c['nknee']} bias {c['knee_bias']:+.2f} C")
    return out


def summary(out):
    """The one question: is the signed mean structured by level, or zero-mean?"""
    print("\n" + "=" * 116)
    print("SIGNED MEAN residual in L, per segment. A model error is a nonzero "
          "signed mean; scatter is not.")
    print(f"  {'session':>7}{'leg':>16}{'phase':>7}"
          f"{'low (x1)':>22}{'mid (x64)':>22}{'high (x16)':>22}")
    keys = sorted({(k[0], k[1]) for k in out})
    for sess, lname in keys:
        for ph in PHASES:
            d = out.get((sess, lname, ph))
            if not d:
                continue
            cells = []
            for sid in (0, 1, 2):
                s = next((z for z in d["closure"]["segs"] if z["seg"] == sid), None)
                cells.append("--" if s is None
                             else f"{s['bias_L']:+9.1f} +/-{s['se_L']:5.1f} L")
            print(f"  {sess:>7}{lname:>16}{ph:>7}"
                  f"{cells[0]:>22}{cells[1]:>22}{cells[2]:>22}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--section", default="3.2", choices=["3.2", "3.3", "both"])
    ap.add_argument("--regs", action="store_true",
                    help="zero free parameters: P=200, b=4/1, g=1")
    ap.add_argument("--kguard", type=float, default=3.0)
    ap.add_argument("--block", type=int, default=8)
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--satmax", type=float, default=0.0)
    ap.add_argument("--no-bins", dest="bins", action="store_false")
    ap.add_argument("--anchored", action="store_true",
                    help="use the measured per-mode T1 (ccmp_decode.T1_EFF)")
    ap.add_argument("--T1", type=float, default=T1_REG)
    ap.add_argument("--json")
    a = ap.parse_args()
    out = run(a.section, a.regs, a.kguard, a.block, a.limit, a.satmax, a.bins,
              T1=a.T1, anchored=a.anchored)
    summary(out)
    if a.json:
        def clean(o):
            if isinstance(o, dict):
                return {k: clean(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [clean(v) for v in o]
            if isinstance(o, (np.floating, np.integer)):
                o = float(o)
            if isinstance(o, float) and not np.isfinite(o):
                return None
            return o
        json.dump({f"{k[0]}|{k[1]}|{k[2]}": clean(v) for k, v in out.items()},
                  open(a.json, "w"), indent=1, default=str)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
