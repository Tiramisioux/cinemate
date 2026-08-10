#!/usr/bin/env python3
"""accept.py — THE ACCEPTANCE GATE. Decoded modes 2 and 3 against their own
linear references, patch by patch, with the same-class controls beside them.

    accept.py [--limit 6] [--json evidence/accept.json]

    2 vs 4   binned:   decoded CCMP against 16-bit linear, same resolution
    3 vs 5   full res: decoded CCMP against 16-bit linear, same resolution
    0 vs 1   control:  two linear takes, no compander in the path
    4 vs 5   control:  two linear takes, no compander in the path

WHY PAIRING AND NOT FLATNESS. §3.1 flatness measures spread WITHIN a take and is
blind to an error shared across the ramp: it put decoded mode 3 at 4.2%/7.1%
against its reference's 4.3%/7.0% -- an apparent pass -- while the pairing read
1.49%/1.74% against a 0.07% control (handoff §4, added by §3.5). Flatness is
reported here too, but it is not the gate.

** THE CONTROLS ARE PRINTED EVERY TIME. ** The gate is "inside the same-class
control band", not a fixed number: the 1.3%/0.9% of §3.1 is a FLATNESS figure
and the reference modes do not meet it as written in this run either. A result
without its control beside it is not a measurement.

Sampling is patches.py's, so the decode is PER PIXEL before any mean.
"""
import os, sys, json, argparse, subprocess, glob
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modes as M                                                    # noqa: E402
from modes import by_mode, rgb                                       # noqa: E402
from patches import RAMP, sample_take                                # noqa: E402
from ccmp_decode import T1_EFF, T1_REG, for_mode                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESS = [("17:05", "takes/ccmp-greycard", M.MODES),
        ("18:37", "takes/ccmp-greycard-1837", M.MODES_1837)]
PAIRS = [("2 vs 4  decoded", 2, 4), ("3 vs 5  decoded", 3, 5),
         ("0 vs 1  CONTROL", 0, 1), ("4 vs 5  CONTROL", 4, 5)]
# §3.1's mid-range window, BY PATCH NAME and not by level. A level window is not
# exposure-invariant: modes 0 and 1 at 18:37 are stopped down x6.3, so a
# 2000-12000 window on the reference's own G empties the control entirely and
# reports the gate with no control beside it -- which is the one thing this tool
# exists to prevent.
MIDRANGE = ("big2_lgrey", "grey3", "grey4", "grey5", "grey6")


def sample(root, mm, limit=6, decode="auto"):
    out = []
    for m in sorted(mm):
        d = [p for p in sorted(glob.glob(os.path.join(ROOT, root, "*")))
             if os.path.basename(p).startswith(mm[m][0])]
        if not d:
            raise SystemExit(f"no take for mode {m} under {root}")
        meta, agg = sample_take(d[0], limit=limit, decode=decode)
        out.append(dict(meta=meta, patches=agg))
    return by_mode(out)


def pair(E, a, b, window=None):
    """Per-patch dR/G and dB/G between two takes, in % of the ratio."""
    rows = []
    for nm in RAMP:
        if max(E[a]["patches"][nm]["sat_frac"],
               E[b]["patches"][nm]["sat_frac"]) > 0.01:
            continue
        if window and nm not in window:
            continue
        ra, ga, ba = rgb(E[a], nm)
        rb, gb, bb = rgb(E[b], nm)
        rows.append((nm, gb, 100 * ((ra / ga) / (rb / gb) - 1),
                     100 * ((ba / ga) / (bb / gb) - 1)))
    return rows


def rms(v):
    return float(np.sqrt(np.mean(np.square(v)))) if len(v) else float("nan")


def run(limit=6, decode="auto", verbose=True):
    res = {}
    for sess, root, mm in SESS:
        E = sample(root, mm, limit, decode)
        res[sess] = E
        if verbose:
            print("=" * 96)
            print(f"SESSION {sess}   decode {decode}   "
                  f"T1 full res {T1_EFF.get(1.0, T1_REG):.4f}  "
                  f"binned {T1_EFF.get(4.0, T1_REG):.4f}")
            print(f"  {'pair':<18}{'n':>3}{'FULL RAMP':>22}"
                  f"{'MID-RANGE (' + ', '.join(MIDRANGE) + ')':>52}")
            print(f"  {'':<18}{'':>3}{'dR/G rms':>11}{'dB/G rms':>11}"
                  f"{'n':>5}{'dR/G rms':>11}{'dB/G rms':>11}{'worst patch':>14}")
        for label, a, b in PAIRS:
            full = pair(E, a, b)
            mid = pair(E, a, b, MIDRANGE)
            key = (sess, label)
            res[key] = dict(full=full, mid=mid)
            if not verbose:
                continue
            wr = max(mid, key=lambda t: abs(t[2]) + abs(t[3]), default=None)
            print(f"  {label:<18}{len(full):>3}"
                  f"{rms([t[2] for t in full]):>10.2f}%"
                  f"{rms([t[3] for t in full]):>10.2f}%"
                  f"{len(mid):>5}{rms([t[2] for t in mid]):>10.2f}%"
                  f"{rms([t[3] for t in mid]):>10.2f}%"
                  + (f"{wr[0]:>14}" if wr else f"{'--':>14}"))
        if verbose:
            print()
            for label, a, b in PAIRS[:2]:
                print(f"  {label} — per patch")
                print(f"    {'patch':<12}{'G(ref)':>10}{'dR/G':>9}{'dB/G':>9}")
                for nm, g, dr, db in res[(sess, label)]["full"]:
                    print(f"    {nm:<12}{g:>10.0f}{dr:>8.2f}%{db:>8.2f}%")
            print()
    return res


def matrix(res):
    """All 15 pairs, mid-range, so the OUTLIER MODE names itself.

    A gate that only compares 2 against 4 and 3 against 5 can say a pair
    disagrees but not which of the two is wrong. With modes 0, 1, 4 and 5
    already agreeing (§3.0b), a mode that disagrees with ALL the others is the
    one carrying the defect.
    """
    print("=" * 96)
    print("PAIR MATRIX — dB/G rms %, mid-range, decoded modes 2 and 3 included. "
          "The outlier is a ROW that is\nlarge everywhere, not one cell.\n")
    for sess, _, _ in SESS:
        E = res[sess]
        ms = sorted(E)
        print(f"  {sess}   " + "".join(f"{'m'+str(m):>8}" for m in ms) + "     row mean")
        for a in ms:
            row = []
            for b in ms:
                row.append(np.nan if a == b else
                           rms([t[3] for t in pair(E, a, b, MIDRANGE)]))
            fin = [v for v in row if np.isfinite(v)]
            print(f"  {'m'+str(a):>7}   "
                  + "".join("      --" if not np.isfinite(v) else f"{v:>8.2f}"
                            for v in row)
                  + f"{np.mean(fin):>12.2f}")
        print()


def verdict(res):
    print("=" * 96)
    print("VERDICT — the gate is 'inside the same-class control band', measured "
          "in the same run.")
    print("The mid-range window is where §3.1 says the linear modes are flat; "
          "outside it, flare and chart")
    print("non-neutrality dominate and the CONTROLS show it too.\n")
    print("The two controls differ from each other by up to 3.5x, so the MULTIPLE "
          "of the band is the honest\nreading and the strict <=1.0x verdict is "
          "the conservative one. Both are printed; neither is rounded away.\n")
    print(f"  {'session':>7}{'quantity':>12}{'mode 2':>10}{'mode 3':>10}"
          f"{'ctrl 0v1':>10}{'ctrl 4v5':>10}{'m2 / band':>11}{'m3 / band':>11}"
          f"{'strict':>14}")
    for sess, _, _ in SESS:
        for tag, i in (("dR/G rms", 2), ("dB/G rms", 3)):
            v = [rms([t[i] for t in res[(sess, lab)]["mid"]])
                 for lab, _, _ in PAIRS]
            band = max(v[2], v[3])
            print(f"  {sess:>7}{tag:>12}{v[0]:>9.2f}%{v[1]:>9.2f}%"
                  f"{v[2]:>9.2f}%{v[3]:>9.2f}%"
                  f"{v[0]/band:>10.1f}x{v[1]/band:>10.1f}x"
                  f"{('  2 PASS' if v[0] <= band else '  2 fail'):>8}"
                  f"{(' 3 PASS' if v[1] <= band else ' 3 fail'):>6}")


def xval(limit=6, path=None):
    """OUT OF SAMPLE: fit the anchor on one session, measure the gate on the other.

    The anchor (§3.6c) is fitted on the same takes the gate is measured on, so
    "it passes" is worth exactly as much as the split-sample check behind it.
    The two instruments are already different -- thousands of blocks over the
    whole frame against nine hand-placed patch boxes decoded per pixel -- but
    the takes are shared, and only a cross-session split tests that.
    """
    import ccmp_decode as C
    import patches as P
    a = json.load(open(path or os.path.join(ROOT, "evidence", "anchor-3.2.json")))

    def dc(sess, leg):
        return float(np.mean([a[f"{sess}|{leg}|{p}|1"]["dc"]
                              for p in ("R", "G1", "G2", "B")]))
    s1 = 1.0 / 64
    fits = {s: {1.0: 500 + dc(s, "3<->5 full res") / (1 - s1),
                4.0: 500 + dc(s, "2<->4 binned") * 4 / (1 - s1)}
            for s, _, _ in SESS}
    keep = dict(C.T1_EFF)
    print("=" * 96)
    print("CROSS-VALIDATION — anchor fitted on ONE session, gate measured on "
          "the OTHER.\n")
    for s, t in fits.items():
        print(f"  anchor from {s}:  T1(b=1) {t[1.0]:.4f}   T1(b=4) {t[4.0]:.4f}")
    print(f"  shipped (both):   T1(b=1) {keep[1.0]:.4f}   T1(b=4) {keep[4.0]:.4f}\n")
    print(f"  {'anchor from':>12}{'gate on':>9}{'m2 dR/G':>10}{'m2 dB/G':>10}"
          f"{'m3 dR/G':>10}{'m3 dB/G':>10}{'ctrl 4v5 dB/G':>15}")
    try:
        for fs in fits:
            C.T1_EFF.update(fits[fs])
            P._LUT.clear()
            r = run(limit, verbose=False)
            for gs, _, _ in SESS:
                c = [rms([t[i] for t in r[(gs, lab)]["mid"]])
                     for lab in ("2 vs 4  decoded", "3 vs 5  decoded",
                                 "4 vs 5  CONTROL") for i in (2, 3)]
                print(f"  {fs:>12}{gs:>9}{c[0]:>9.3f}%{c[1]:>9.3f}%"
                      f"{c[2]:>9.3f}%{c[3]:>9.3f}%{c[5]:>14.3f}%"
                      + ("   <-- OUT OF SAMPLE" if gs != fs else ""))
    finally:
        C.T1_EFF.update(keep)
        P._LUT.clear()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--decode", default="auto", choices=["auto", "off"])
    ap.add_argument("--xval", action="store_true",
                    help="fit the anchor on one session, gate on the other")
    ap.add_argument("--json")
    a = ap.parse_args()
    if a.xval:
        xval(a.limit)
        return
    res = run(a.limit, a.decode)
    matrix(res)
    verdict(res)
    if a.json:
        json.dump({f"{k[0]}|{k[1]}": v for k, v in res.items()
                   if isinstance(k, tuple)}, open(a.json, "w"), indent=1)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
