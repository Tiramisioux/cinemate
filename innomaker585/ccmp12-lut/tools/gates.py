#!/usr/bin/env python3
"""gates.py — §3.0 uniformity gate and §3.0b scope test.

  gates.py patches.json

§3.0  Do the chart's illumination-check chips read the same at opposite corners?
      If not, every number measured on that chart is contaminated.
§3.0b Do the four LINEAR modes (0, 1, 4, 5) already agree with each other?
      If not, there is a defect the handoff does not cover, and a correct
      ccmp_decode cannot make modes 2 and 3 match an inconsistent target.

R/G and B/G are within-frame ratios, so they are exposure- and binning-invariant
and need no normalisation. AsShotNeutral is identical across all six takes and
would cancel anyway, so no white balance is applied.
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modes import by_mode, rgb, LINEAR_MODES  # noqa: E402
from patches import RAMP  # noqa: E402

M = by_mode(json.load(open(sys.argv[1])))

print("=" * 76)
print("§3.0  UNIFORMITY GATE — illumination chips, diagonal opposite corners")
print("=" * 76)
print("  The white pair is the illumination probe. The black pair sits at 2-4% of")
print("  white and is dominated by LOCAL FLARE — the top-right chip is boxed in by")
print("  the big white band and the white chip, the bottom-left one is not — so it")
print("  probes flare, not lighting. A lighting gradient moves both the same way.\n")
print(f"  {'mode':<22}{'W_TR':>10}{'W_BL':>10}{'W disp':>9}"
      f"{'K disp':>9}{'K as % of white':>17}")
for m in sorted(M):
    e = M[m]
    wt, wb = rgb(e, "ill_W_TR")[1], rgb(e, "ill_W_BL")[1]
    kt, kb = rgb(e, "ill_K_TR")[1], rgb(e, "ill_K_BL")[1]
    sat = max(e["patches"][n]["sat_frac"] for n in ("ill_W_TR", "ill_W_BL"))
    flag = "  CLIPPED - cannot gate" if sat > 0.01 else ""
    print(f"  {m} {e['label']:<19}{wt:10.1f}{wb:10.1f}{100*(wb/wt-1):8.2f}%"
          f"{100*(kb/kt-1):8.1f}%{100*(kb-kt)/wt:16.2f}%{flag}")

print("\n" + "=" * 76)
print("§3.0b SCOPE TEST — do the four LINEAR modes already agree?")
print("=" * 76)
print("  Raw CFA ratios, black-subtracted with each take's own BlackLevel tag.")
print("  sat = worst saturated fraction across the four modes at that patch.\n")

for tag, idx in (("R/G", 0), ("B/G", 2)):
    print(f"  --- {tag} ---")
    print(f"  {'patch':<12}{'level(m4)':>10}" +
          "".join(f"{'m'+str(m):>9}" for m in LINEAR_MODES) + f"{'spread':>9}{'sat':>7}")
    for nm in RAMP + ["big4_gloss"]:
        v, sat = [], 0.0
        for m in LINEAR_MODES:
            t = rgb(M[m], nm)
            v.append(t[idx] / t[1])
            sat = max(sat, M[m]["patches"][nm]["sat_frac"])
        v = np.array(v)
        print(f"  {nm:<12}{rgb(M[4], nm)[1]:10.0f}" + "".join(f"{x:9.4f}" for x in v)
              + f"{100*(v.max()-v.min())/v.mean():8.2f}%{100*sat:6.1f}%")
    print()

print("  Measurement floor — same-class pairs, which differ only in binning:")
for a, b in ((0, 1), (4, 5)):
    d = []
    for nm in RAMP:
        if max(M[a]["patches"][nm]["sat_frac"], M[b]["patches"][nm]["sat_frac"]) > 0.01:
            continue
        ta, tb = rgb(M[a], nm), rgb(M[b], nm)
        d += [abs(ta[0] / ta[1] - tb[0] / tb[1]) / (ta[0] / ta[1]),
              abs(ta[2] / ta[1] - tb[2] / tb[1]) / (ta[2] / ta[1])]
    print(f"    mode {a} vs {b}:  max {100*max(d):.2f}%   rms {100*np.sqrt(np.mean(np.square(d))):.2f}%")
