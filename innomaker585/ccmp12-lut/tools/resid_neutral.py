#!/usr/bin/env python3
"""resid_neutral.py — is the decode residual a FUNCTION OF L, on one patch class?

    resid_neutral.py [--leg "3<->5 full res"]

THE CONFOUND THIS REMOVES. Comparing the four CFA phases at the same L compares
FOUR DIFFERENT PATCHES: at L = 7000, phase G is looking at a mid grey and phase
B at the white band, because B sits at 0.53 of G. So a phase disagreement at
matched L is ambiguous between "the curve is channel-dependent" (impossible --
§2) and "the residual depends on the patch".

Restricting to blocks whose REFERENCE ratios are neutral fixes the patch class.
Inside it the three channels still span overlapping L ranges -- R covers
0.625*[Gmin,Gmax] and B 0.526*[...] -- so the question becomes well posed:

    at the same L, on the same class of patch, do the channels agree?

  agree     -> the residual is a function of L. It IS the curve, and a curve
               parameter can remove it.
  disagree  -> it is not the curve. No LinearizationTable can fix it, because a
               table takes the stored code and nothing else.

Reference ratios are used for the selection, never the decoded ones, so the
thing under test cannot select its own blocks.
"""
import os, sys, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fitcurve import PHASES, T1_REG, T2_REG, S1_REG, S2_REG          # noqa: E402
from legcache import points, LEGS                                    # noqa: E402
from blockratio import joined, decode                                # noqa: E402
from fit_all import SESSIONS                                         # noqa: E402

CH = dict(R="R", G1="G", G2="G", B="B")


def neutral_mask(J, rtol=0.04, btol=0.04):
    """Blocks whose REFERENCE R/G and B/G sit on AsShotNeutral's 0.625/0.5263."""
    g = 0.5 * (J["G1"]["x"] + J["G2"]["x"])
    rg, bg = J["R"]["x"] / g, J["B"]["x"] / g
    return (np.abs(rg - 0.625) < rtol) & (np.abs(bg - 0.5263) < btol), g


def run(sess, leg, nb=14, rtol=0.04, btol=0.04, **kw):
    b = LEGS[(sess, leg)][2]
    J = joined(sess, leg)
    m, g = neutral_mask(J, rtol, btol)
    d = {p: decode(J[p]["y"], b, **kw) - J[p]["x"] for p in PHASES}
    L = {p: J[p]["x"] for p in PHASES}
    k1 = T1_REG / b
    print(f"\n{sess}  {leg}  — NEUTRAL BLOCKS ONLY "
          f"({int(m.sum())} of {J['n']}; G {g[m].min():.0f}..{g[m].max():.0f})"
          f"   knee1 at L={k1:.0f}")
    print(f"  residual in L, binned on EACH CHANNEL'S OWN L. If the residual is "
          f"the curve, the three columns")
    print(f"  must agree row by row -- same L, same class of patch, same "
          f"transfer.")
    print(f"  {'L':>8}" + "".join(f"{c:>9}{'n':>6}" for c in ("R", "G", "B")))
    lo = max(min(L[p][m].min() for p in ("R", "B")), 1.0)
    hi = min(L["G1"][m].max(), max(L["R"][m].max(), L["B"][m].max()))
    edges = np.exp(np.linspace(np.log(lo), np.log(hi), nb + 1))
    rows = []
    for i in range(nb):
        cells, ns, Ls = [], [], []
        for ch, ps in (("R", ["R"]), ("G", ["G1", "G2"]), ("B", ["B"])):
            v, n = [], 0
            for p in ps:
                s = m & (L[p] >= edges[i]) & (L[p] < edges[i + 1])
                if s.sum() >= 15:
                    v.append(d[p][s].mean())
                    Ls.append(L[p][s].mean())
                    n += int(s.sum())
            cells.append(np.mean(v) if v else np.nan)
            ns.append(n)
        if not np.isfinite(cells).any():
            continue
        fin = [c for c in cells if np.isfinite(c)]
        rows.append((np.mean(Ls) if Ls else np.nan, cells, ns,
                     (max(fin) - min(fin)) if len(fin) > 1 else np.nan))
        print(f"  {np.mean(Ls) if Ls else float('nan'):>8.0f}"
              + "".join(("       --     0" if not np.isfinite(c)
                         else f"{c:>9.1f}{n:>6}") for c, n in zip(cells, ns))
              + (f"   spread {rows[-1][3]:6.1f} L" if np.isfinite(rows[-1][3]) else ""))
    sp = [r[3] for r in rows if np.isfinite(r[3])]
    if sp:
        print(f"  channel spread at matched L: median {np.median(sp):.1f} L, "
              f"max {max(sp):.1f} L")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leg", default="3<->5 full res")
    ap.add_argument("--session", default=None)
    ap.add_argument("--nbin", type=int, default=14)
    ap.add_argument("--rtol", type=float, default=0.04)
    ap.add_argument("--btol", type=float, default=0.04)
    ap.add_argument("--T1", type=float, default=T1_REG)
    ap.add_argument("--P", dest="Pv", type=float, default=200.0)
    a = ap.parse_args()
    for s in ([a.session] if a.session else [x for x, _, _ in SESSIONS]):
        run(s, a.leg, a.nbin, a.rtol, a.btol, P=a.Pv, T1=a.T1)


if __name__ == "__main__":
    main()
