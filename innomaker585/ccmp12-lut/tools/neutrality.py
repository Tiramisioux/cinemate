#!/usr/bin/env python3
"""neutrality.py — §3.1, the primary instrument: neutrality vs level.

  neutrality.py patches.json [--csv out.csv]

The Video chart's greyscale is spectrally neutral, so any R:G:B divergence
measured along it is the pipeline's, not the chart's.

    R/G and B/G must be FLAT across the neutral ramp
    if and only if the decode is correct.

No reference values, no exposure ratio, no Y column, no published chart data —
it is a within-frame ratio, so it is immune to the scene drift that voided the
earlier shutter-bracket experiment, and it sidesteps the anchor problem.

Wrong knee position BENDS these curves. Wrong slope TILTS them.

Each take is decoded through its OWN tags. None of the six carries a
LinearizationTable, so that means: subtract BlackLevel, treat as linear. For the
12-bit ClearHDR modes that is exactly the shipping bug, and the tables below are
what it costs. Those two modes are also reported with the MEASURED per-phase
black, which separates defect A (wrong BlackLevel) from defect B (companded data
decoded as linear).
"""
import os, sys, json, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modes import by_mode, rgb, CCMP_MODES  # noqa: E402
from patches import RAMP  # noqa: E402


def table(entry, measured, note=""):
    rows = []
    for nm in RAMP:
        r, g, b = rgb(entry, nm, measured)
        sat = entry["patches"][nm]["sat_frac"]
        rows.append((nm, g, r / g if g else np.nan, b / g if g else np.nan, sat))
    rows.sort(key=lambda t: t[1])
    print(f"\n  mode {entry['mode']}  {entry['label']:<18} "
          f"black={'measured per-phase' if measured and entry['mode'] in CCMP_MODES else 'tag ' + str(entry['meta']['black'][0])}{note}")
    print(f"    {'patch':<12}{'G above blk':>12}{'R/G':>9}{'B/G':>9}{'sat':>7}")
    ok = [t for t in rows if t[4] <= 0.01]
    for nm, g, rg, bg, sat in rows:
        mark = "  CLIPPED" if sat > 0.01 else ""
        print(f"    {nm:<12}{g:12.1f}{rg:9.4f}{bg:9.4f}{100*sat:6.1f}%{mark}")
    if len(ok) >= 2:
        rgv = np.array([t[2] for t in ok]); bgv = np.array([t[3] for t in ok])
        print(f"    {'FLATNESS':<12}{'(unclipped)':>12}"
              f"{100*(rgv.max()-rgv.min())/rgv.mean():8.1f}%"
              f"{100*(bgv.max()-bgv.min())/bgv.mean():8.1f}%"
              f"   <- 0% = decode correct")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json"); ap.add_argument("--csv")
    a = ap.parse_args()
    M = by_mode(json.load(open(a.json)))

    print("=" * 78)
    print("§3.1  NEUTRALITY vs LEVEL — every take decoded through its own tags")
    print("=" * 78)
    out = {}
    for m in sorted(M):
        out[m] = table(M[m], measured=False)

    print("\n" + "=" * 78)
    print("  Defect A vs defect B: the two CCMP modes again, with the MEASURED")
    print("  per-phase black instead of the wrong 200 tag. If the ramp goes flat,")
    print("  the fault was the black level alone. If it does not, the residual is")
    print("  the transfer curve — companded data decoded as linear.")
    print("=" * 78)
    for m in CCMP_MODES:
        table(M[m], measured=True, note="   (defect A corrected)")

    if a.csv:
        with open(a.csv, "w") as f:
            f.write("mode,label,patch,G_above_black,R_over_G,B_over_G,sat_frac\n")
            for m, rows in out.items():
                for nm, g, rg, bg, sat in rows:
                    f.write(f"{m},{M[m]['label']},{nm},{g:.2f},{rg:.5f},{bg:.5f},{sat:.4f}\n")
        print(f"\nwrote {a.csv}")


if __name__ == "__main__":
    main()
