#!/usr/bin/env python3
"""modes.py — the six-mode map for takes/ccmp-greycard, and the black levels.

The mode map is confirmed from the FILES: dimensions and BitsPerSample identify
each take, and the capture order in the take name separates the two 12-bit pairs
(SDR first, ClearHDR second). AsShotNeutral is identical (0.625 1 0.5263) across
all six, so white balance cannot explain any difference between modes.
"""

# mode -> (take-name prefix, label, is_linear)
MODES = {
    0: ("CINEPI_26-08-06_170554", "1928 12b SDR",      True),
    1: ("CINEPI_26-08-06_170608", "3856 12b SDR",      True),
    2: ("CINEPI_26-08-06_170626", "1928 12b ClearHDR", False),
    3: ("CINEPI_26-08-06_170638", "3856 12b ClearHDR", False),
    4: ("CINEPI_26-08-06_170653", "1928 16b ClearHDR", True),
    5: ("CINEPI_26-08-06_170710", "3856 16b ClearHDR", True),
}
# Second chart session, 18:37, takes/ccmp-greycard-1837. Same order, same
# framing. Modes 0 and 1 are stopped down x6.3 (-2.66 stops) and are now
# UNCLIPPED across the whole ramp; modes 2-5 did NOT move (+0.7 to +1.5%, i.e.
# ~1% of lamp drift over the 1.5 h between sessions). Whatever shutter change
# was made reached the SDR modes only — that is itself a finding.
MODES_1837 = {
    0: ("CINEPI_26-08-06_183719", "1928 12b SDR",      True),
    1: ("CINEPI_26-08-06_183742", "3856 12b SDR",      True),
    2: ("CINEPI_26-08-06_183759", "1928 12b ClearHDR", False),
    3: ("CINEPI_26-08-06_183819", "3856 12b ClearHDR", False),
    4: ("CINEPI_26-08-06_183837", "1928 16b ClearHDR", True),
    5: ("CINEPI_26-08-06_183854", "3856 16b ClearHDR", True),
}
# Lens-cap set, takes/ccmp-c0-6mode, one capped take per mode, same order.
MODES_C0 = {
    0: ("CINEPI_26-08-06_183919", "1928 12b SDR",      True),
    1: ("CINEPI_26-08-06_183930", "3856 12b SDR",      True),
    2: ("CINEPI_26-08-06_183946", "1928 12b ClearHDR", False),
    3: ("CINEPI_26-08-06_183954", "3856 12b ClearHDR", False),
    4: ("CINEPI_26-08-06_184003", "1928 16b ClearHDR", True),
    5: ("CINEPI_26-08-06_184027", "3856 16b ClearHDR", True),
}
SESSIONS = dict(greycard=MODES, greycard_1837=MODES_1837, c0_6mode=MODES_C0)
# Keyed by take PREFIX, not by mode: all three sessions use modes 0-5, so a
# dict keyed by mode would silently keep only the last session.
ALL_MODES = {prefix: (m, label, linear)
             for s in SESSIONS.values() for m, (prefix, label, linear) in s.items()}

CCMP_MODES = (2, 3)
LINEAR_MODES = (0, 1, 4, 5)
BINNED_MODES = (0, 2, 4)          # 1928x1090, 2x2 binned
FULL_MODES = (1, 3, 5)            # 3856x2180, full readout

# Lens-cap black, per mode, per CFA phase, measured from takes/ccmp-c0-6mode
# (2026-08-06 18:39, one capped take per mode, 5-7 frames each).
#
# EVERY MODE SITS ON ITS TAG. Max deviation -1.3 codes; per-channel spread inside
# a mode <= 0.3 codes; sigma/px 1.0-2.9. libcamera's imx585.json carries
# rpi.black_level 3200, which scales to 200 in the 12-bit domain, and that is
# correct for all six.
#
# ** Handoff §2's "defect A — BlackLevel is wrong, measured 224.5-232.5" is
# FALSIFIED. ** Those figures came from takes/ccmp-c0* which had sigma/px
# 22.7-49.0 against 1.0-2.9 here — the signature of a light leak, not a dark
# frame. Those takes have since been deleted and cannot be re-checked.
MEASURED_BLACK = {
    0: dict(R=201.06, G1=201.05, G2=201.14, B=201.15),
    1: dict(R=200.99, G1=200.98, G2=201.08, B=201.08),
    2: dict(R=201.39, G1=201.36, G2=201.63, B=201.65),
    3: dict(R=198.70, G1=198.73, G2=198.75, B=198.71),
    4: dict(R=3201.66, G1=3201.63, G2=3201.99, B=3201.98),
    5: dict(R=3199.15, G1=3199.17, G2=3199.19, B=3199.16),
}


def by_mode(results):
    """[{meta, patches}, ...] from patches.py --json  ->  {mode: entry}."""
    out = {}
    for r in results:
        take = r["meta"]["take"]
        for prefix, (m, label, linear) in ALL_MODES.items():
            if take.startswith(prefix):
                out[m] = dict(r, mode=m, label=label, linear=linear)
                break
        else:
            raise SystemExit(f"unrecognised take {take!r} — not in modes.ALL_MODES")
    return out


def black_for(entry, phase, measured=False):
    """Black level for one CFA phase of one take.

    measured=True uses the lens-cap per-phase black; measured=False uses the
    tag. The two differ by at most 1.3 codes, so this switch no longer changes
    any conclusion — it is kept only so the difference stays checkable.
    """
    if measured and entry["mode"] in MEASURED_BLACK:
        return MEASURED_BLACK[entry["mode"]][phase]
    return float(entry["meta"]["black"][0])


def rgb(entry, patch, measured=False):
    """(R, G, B) above black for one patch. G is the mean of the two greens."""
    p = entry["patches"][patch]
    r = p["R"]["mean"] - black_for(entry, "R", measured)
    g1 = p["G1"]["mean"] - black_for(entry, "G1", measured)
    g2 = p["G2"]["mean"] - black_for(entry, "G2", measured)
    b = p["B"]["mean"] - black_for(entry, "B", measured)
    return r, 0.5 * (g1 + g2), b
