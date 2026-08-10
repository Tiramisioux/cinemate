#!/usr/bin/env python3
"""blend.py — §3.3. IS THE CLEARHDR BLEND A PURE GAIN, OR DOES IT HAVE A KNEE?

    blend.py [--session 17:05|18:37|both] [--phase all] [--block 8] [--json out]

THE QUESTION THIS TOOL EXISTS FOR. §3.2's legs (2<->4, 3<->5) held ClearHDR
FIXED on both sides and changed only the output bit depth, so ClearHDR's own
dual-exposure blend was common mode and cancelled exactly. §3.3's legs (0<->2,
1<->3) are the only pair in the data set that can see the blend at all -- and
they see it multiplied INTO the three CCMP segments, where separating a fourth
breakpoint from the three known ones is precisely the kind of thing that fits a
knee to noise.

So do not ask §3.3's legs. Ask THIS pair. Modes 4 and 5 are ClearHDR LINEAR and
modes 0 and 1 are SDR linear, so pairing them puts the blend on its own with no
companding anywhere in the path:

    L = K + g*x            L = mode 4/5 code above black   (16-bit domain)
                           x = mode 0/1 code above black   (12-bit domain)
                           g = the SDR -> ClearHDR sensitivity ratio
                           K = mode 4/5's own black -- free, and a check

g is exactly the free parameter §3.3 adds to §3.2's model, because §3.2's model
is A = P + ccmp(b*L)/b and §3.3's is A = P + ccmp(b*g*x)/b. The two agree if and
only if L = g*x, which is the line fitted here. So this tool measures g without
touching a knee, and §3.3's three slope-derived estimates of g must then agree
with it.

THREE TESTS, in increasing order of what they can rule out:

 1. Single line, errors in both variables. Reports g and the intercept K.
 2. The residual profile about that line, binned in x. A breakpoint does not
    hide here: it shows as a systematic V or lambda across the bins, and the
    diagnose.py run on this same pair puts the per-bin noise floor at ~1, so
    any structure above that is real.
 3. A free breakpoint. Grid-search a split point, fit two lines, and compare
    the weighted chi2 against the single line's on 2 extra parameters. A blend
    knee would take a large bite out of chi2 at a repeatable x. Noise buys a
    small bite at an arbitrary x that moves between phases and sessions -- so
    the diagnostic is not the size of the improvement alone but whether the
    breakpoint LANDS IN THE SAME PLACE across the four phases and two sessions.

WHAT A POSITIVE RESULT WOULD MEAN, AND WHAT IT WOULD NOT. If the blend does have
a knee, it must be REPORTED and must NOT go into the LinearizationTable. The
table's job is to take modes 2 and 3 to where modes 4 and 5 already are, and
modes 4 and 5 carry the same blend. The table undoes CCMP and nothing else.
"""
import os, sys, json, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modes as M                                                   # noqa: E402
from fitcurve import leg_points, wls_line, PHASES                   # noqa: E402

SESSIONS = {"17:05": ("takes/ccmp-greycard", M.MODES),
            "18:37": ("takes/ccmp-greycard-1837", M.MODES_1837)}
# A = the ClearHDR LINEAR take, B = the SDR take of the same resolution.
LEGS = [("binned 0->4", 4, 0), ("full res 1->5", 5, 1)]


def take_dir(root, prefix):
    for d in sorted(os.listdir(root)):
        if d.startswith(prefix):
            return os.path.join(root, d)
    raise SystemExit(f"no take {prefix} under {root}")


def wchi2(fit, x, y, ex, ey):
    """Weighted chi2 of a fitted line, with B's error entering via the slope."""
    w = 1.0 / (ey ** 2 + (fit["m"] * ex) ** 2 + 1e-12)
    return float((w * (y - (fit["a"] + fit["m"] * x)) ** 2).sum())


def breakpoint_scan(x, y, ex, ey, nmin=40, ngrid=60):
    """Best free breakpoint, by weighted chi2 over a grid of split points.

    Returns the best split and the chi2 improvement over a single line. Two
    lines ALWAYS fit at least as well as one; the number that carries
    information is whether the best split lands in the same place across
    phases and sessions, not the size of the improvement on any one of them.
    """
    one = wls_line(x, y, ex, ey, 1.0)
    c1 = wchi2(one, x, y, ex, ey)
    lo, hi = np.percentile(x, 5), np.percentile(x, 95)
    best = None
    for xs in np.linspace(lo, hi, ngrid):
        m = x < xs
        if m.sum() < nmin or (~m).sum() < nmin:
            continue
        fa = wls_line(x[m], y[m], ex[m], ey[m], one["m"])
        fb = wls_line(x[~m], y[~m], ex[~m], ey[~m], one["m"])
        if not (np.isfinite(fa["m"]) and np.isfinite(fb["m"])):
            continue
        c2 = (wchi2(fa, x[m], y[m], ex[m], ey[m])
              + wchi2(fb, x[~m], y[~m], ex[~m], ey[~m]))
        if best is None or c2 < best[0]:
            best = (c2, float(xs), fa, fb)
    if best is None:
        return dict(ok=False)
    c2, xs, fa, fb = best
    dof = max(x.size - 4, 1)
    # F on the 2 extra parameters, against the 2-line fit's own chi2/dof
    F = ((c1 - c2) / 2.0) / (c2 / dof) if c2 > 0 else np.inf
    return dict(ok=True, xs=xs, chi2_1=c1, chi2_2=c2, F=float(F),
                m_lo=fa["m"], m_hi=fb["m"], n_lo=fa["n"], n_hi=fb["n"],
                ratio=float(fb["m"] / fa["m"]) if fa["m"] else np.nan,
                one_a=one["a"], one_m=one["m"], one_rms=one["rms"])


def resid_profile(x, y, fit, nb=14):
    """Residual about the single line, binned in x. A knee cannot hide here."""
    r = y - (fit["a"] + fit["m"] * x)
    e = np.geomspace(max(x.min(), 1.0), x.max(), nb + 1)
    out = []
    for i in range(nb):
        m = (x >= e[i]) & (x < e[i + 1])
        if m.sum() < 8:
            continue
        out.append(dict(xm=float(x[m].mean()), n=int(m.sum()),
                        mean=float(r[m].mean()),
                        se=float(r[m].std(ddof=1) / np.sqrt(m.sum()))))
    return out


def run(session, phases, bs, limit, satmax, verbose=True):
    root, mm = SESSIONS[session]
    rows = {}
    for lname, am, bm in LEGS:
        A, B = take_dir(root, mm[am][0]), take_dir(root, mm[bm][0])
        for ph in phases:
            P = leg_points(A, B, ph, bs=bs, limit=limit, satmax=satmax)
            m = P["meta"]
            x, ex, ey = P["x"], P["ex"], P["ey"]
            y = P["y"] - M.MEASURED_BLACK[am][ph]      # L above ITS OWN black
            one = wls_line(x, y, ex, ey, 1.0)
            bp = breakpoint_scan(x, y, ex, ey)
            prof = resid_profile(x, y, one)
            d = dict(session=session, leg=lname, phase=ph, meta=m,
                     g=one["m"], se_g=float(np.sqrt(one["vm"])),
                     K=one["a"], se_K=float(np.sqrt(one["va"])),
                     rms=one["rms"], noise=one["noise"], n=one["n"],
                     xlo=float(x.min()), xhi=float(x.max()),
                     Llo=float(y.min()), Lhi=float(y.max()),
                     bp=bp, prof=prof)
            rows[(lname, ph)] = d
    if verbose:
        report(session, rows)
    return rows


def report(session, rows):
    print("=" * 112)
    print(f"SESSION {session}   the blend on its own: L(mode 4/5, 16b linear) "
          f"against x(mode 0/1, 12b SDR).  No companding in this path.")
    print(f"  {'leg':>14}{'ph':>4}{'n':>7}{'x range':>16}{'L range':>16}"
          f"{'g':>10}{'+/-':>8}{'K (=3200?)':>12}{'+/-':>7}"
          f"{'rms':>8}{'noise':>7}{'rms/noise':>10}")
    for (lname, ph), d in rows.items():
        xr = "%.0f..%.0f" % (d["xlo"], d["xhi"])
        lr = "%.0f..%.0f" % (d["Llo"], d["Lhi"])
        print(f"  {lname:>14}{ph:>4}{d['n']:>7}{xr:>16}{lr:>16}"
              f"{d['g']:>10.4f}{d['se_g']:>8.4f}{d['K']:>12.1f}"
              f"{d['se_K']:>7.1f}{d['rms']:>8.2f}{d['noise']:>7.2f}"
              f"{d['rms']/max(d['noise'],1e-9):>10.2f}")

    print(f"\n  FREE BREAKPOINT — two lines against one. The number that carries "
          f"information is whether")
    print(f"  the best split lands in the SAME PLACE across phases and sessions, "
          f"not the size of the chi2 bite.")
    print(f"  {'leg':>14}{'ph':>4}{'best split x':>14}{'as frac of range':>18}"
          f"{'slope lo':>10}{'slope hi':>10}{'hi/lo':>9}{'F(2,dof)':>10}")
    for (lname, ph), d in rows.items():
        b = d["bp"]
        if not b.get("ok"):
            print(f"  {lname:>14}{ph:>4}      -- too few blocks either side --")
            continue
        frac = (b["xs"] - d["xlo"]) / max(d["xhi"] - d["xlo"], 1e-9)
        print(f"  {lname:>14}{ph:>4}{b['xs']:>14.1f}{frac:>17.2f} "
              f"{b['m_lo']:>10.4f}{b['m_hi']:>10.4f}{b['ratio']:>9.4f}"
              f"{b['F']:>10.1f}")

    print(f"\n  RESIDUAL PROFILE about the single line, binned in x "
          f"(codes; a knee shows as a systematic V or lambda)")
    for (lname, ph), d in rows.items():
        if ph != "G1":
            continue
        print(f"    {lname}  {ph}:")
        for p in d["prof"]:
            bar = "#" * int(min(abs(p["mean"]) / 2.0, 40))
            sig = abs(p["mean"]) / max(p["se"], 1e-9)
            print(f"      x {p['xm']:8.1f}  n {p['n']:5d}  resid "
                  f"{p['mean']:+8.2f} +/- {p['se']:5.2f}  ({sig:5.1f} sigma) {bar}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", default="both",
                    choices=list(SESSIONS) + ["both"])
    ap.add_argument("--phase", default="all", choices=list(PHASES) + ["all"])
    ap.add_argument("--block", type=int, default=8)
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--satmax", type=float, default=0.0)
    ap.add_argument("--json")
    a = ap.parse_args()
    phases = PHASES if a.phase == "all" else (a.phase,)
    sess = list(SESSIONS) if a.session == "both" else [a.session]
    allr = {}
    for s in sess:
        r = run(s, phases, a.block, a.limit, a.satmax)
        allr.update({f"{s}|{k[0]}|{k[1]}": v for k, v in r.items()})

    if len(sess) > 1:
        print("\n" + "=" * 112)
        print("SESSION AGREEMENT. The two sessions differ by the SDR exposure "
              "change, which moves g and nothing else.")
        print(f"  {'leg':>14}{'g 17:05':>12}{'g 18:37':>12}{'ratio':>10}"
              f"    (the SDR stop-down; ClearHDR did not move)")
        for lname, _, _ in LEGS:
            g = []
            for s in sess:
                v = [allr[f"{s}|{lname}|{p}"]["g"] for p in phases]
                g.append(float(np.mean(v)))
            print(f"  {lname:>14}{g[0]:>12.4f}{g[1]:>12.4f}"
                  f"{g[1]/g[0]:>10.4f}")

    if a.json:
        def clean(o):
            if isinstance(o, dict):
                return {k: clean(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [clean(v) for v in o]
            if isinstance(o, (np.floating, np.integer)):
                return float(o)
            if isinstance(o, float) and not np.isfinite(o):
                return None
            return o
        json.dump(clean(allr), open(a.json, "w"), indent=1, default=str)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
