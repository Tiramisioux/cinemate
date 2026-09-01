#!/usr/bin/env python3
"""verify_dng_table.py — is the table in this DNG the golden one?

    verify_dng_table.py <take-dir-or-dng> [...]

THE P2 GATE, AUTOMATED. A 12-bit ClearHDR DNG off the Pi must carry a
LinearizationTable byte-identical to the one ccmp_decode.py generates for its
binning, with BlackLevel 200 and the matching WhiteLevel. This reads the tag
straight out of IFD0 and diffs it.

** IT COMPARES AGAINST BOTH TABLES, NOT JUST THE EXPECTED ONE. ** That is the
whole point. The most likely way the C++ is wrong is a BINNING MIX-UP — the two
modes' knees sit 4x apart and selecting on the wrong one is wrong by 2.6x at
knee1 while still looking like a plausible curve. Diffing only against the
expected table would report "mismatch, 7684 codes" and leave you guessing;
diffing against both reports "this file carries the BINNED table but its
geometry is full res", which names the bug.

Binning is derived from geometry the same way cinepi-raw's CinePIRecorder does
it — round(active/mode) per axis, multiplied — so if the sensor reports an
active area this tool does not expect, that shows up here as a refusal rather
than as a silently wrong expectation.

Exit status is 0 only if every file passes.
"""
import argparse, glob, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dngread                                                     # noqa: E402
from ccmp_decode import for_mode, build, B_FULL, B_BINNED, P_TAG   # noqa: E402

# imx585 PixelArrayActiveAreas, the same quantity the C++ reads from libcamera.
ACTIVE_W, ACTIVE_H = 3856, 2180


def binning_from_geometry(w, h):
    """b = pixels summed per output sample. Mirrors CinePIRecorder::SensorBinning."""
    if not w or not h:
        return None
    hb, vb = round(ACTIVE_W / w), round(ACTIVE_H / h)
    if hb < 1 or vb < 1:
        return None
    return float(hb * vb)


def golden_tables():
    """{b: (table, black, white)} straight from the generator, not from disk."""
    out = {}
    for b in (B_FULL, B_BINNED):
        r = build(for_mode(b), "KEEP_PEDESTAL")
        out[b] = (r["table"].astype(int), r["black"], r["white"])
    return out


def check(path, goldens, verbose=True):
    d = dngread.load(path)
    name = os.path.basename(path)
    w, h, bits = d["w"], d["h"], d["bits"]
    b_geom = binning_from_geometry(w, h)
    black = d["black"]
    white = d["white"][0] if d["white"] else None

    if verbose:
        print(f"\n{name}")
        print(f"  {w}x{h}  {bits}-bit   BlackLevel {black}   WhiteLevel {white}")
        print(f"  binning from geometry: "
              f"{'b = %g' % b_geom if b_geom else 'UNKNOWN — unexpected geometry'}")

    fails = []

    if not d["has_lut"]:
        print("  FAIL  no LinearizationTable (tag 0xC618) in this file.")
        print("        Either the mode is not 12-bit ClearHDR, or the encoder did")
        print("        not resolve a table — check cinepi-raw's launch log for the")
        print("        'CCMP12 decompand' line or the warning that replaces it.")
        return ["no table"]

    lut = np.asarray(d["lut"], int)
    if verbose:
        print(f"  LinearizationTable present, {len(lut)} entries")

    # Which golden does it actually equal? Ask both.
    matched = None
    for b, (tbl, _, _) in goldens.items():
        if len(lut) == len(tbl) and np.array_equal(lut, tbl):
            matched = b
            break

    if matched is None:
        print("  FAIL  the table matches NEITHER golden.")
        for b, (tbl, _, _) in sorted(goldens.items()):
            if len(lut) != len(tbl):
                print(f"        vs b={b:g}: length {len(lut)} against {len(tbl)}")
                continue
            diff = np.abs(lut - tbl)
            n = int((diff > 0).sum())
            i = int(np.argmax(diff))
            print(f"        vs b={b:g}: {n} entries differ, worst at code {i} "
                  f"(file {lut[i]}, golden {tbl[i]}, delta {lut[i] - tbl[i]:+d})")
        fails.append("table matches no golden")
    elif b_geom is not None and matched != b_geom:
        print(f"  FAIL  ** BINNING MIX-UP. ** The file carries the b={matched:g} table "
              f"but its geometry says b={b_geom:g}.")
        print(f"        {'Binned table in a full-res file' if matched == B_BINNED else 'Full-res table in a binned file'}"
              f" — wrong by 2.6x at knee1. Check CinePIRecorder::SensorBinning and")
        print("        what PixelArrayActiveAreas actually reports for this sensor.")
        fails.append("binning mix-up")
    else:
        print(f"  ok    table is BYTE-IDENTICAL to the b={matched:g} golden "
              f"({len(lut)} entries)")

    # The two level tags, against the generator for whichever table is in there.
    b_tags = matched if matched is not None else b_geom
    if b_tags in goldens:
        _, want_black, want_white = goldens[b_tags]
        if black and not all(int(x) == want_black for x in black):
            print(f"  FAIL  BlackLevel {black}, expected {want_black} on all four channels")
            fails.append("black")
        elif black:
            print(f"  ok    BlackLevel {want_black}, unchanged")
        if white != want_white:
            print(f"  FAIL  WhiteLevel {white}, expected {want_white}")
            print("        The two modes' WhiteLevels differ because their knee2 codes")
            print("        do. If this reads like the other mode's, see the mix-up note.")
            fails.append("white")
        else:
            print(f"  ok    WhiteLevel {want_white}")

    # The identity segment is the cheapest structural check there is.
    if matched is not None:
        c = for_mode(matched)
        n1 = int(np.floor(c.knee_codes[0]))
        if np.array_equal(lut[:n1 + 1], np.arange(n1 + 1)):
            print(f"  ok    identity on codes 0..{n1}")
        else:
            print(f"  FAIL  not the identity below knee1 (codes 0..{n1})")
            fails.append("identity")

    return fails


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="DNG files, or directories of them")
    ap.add_argument("--limit", type=int, default=1,
                    help="DNGs per directory (default 1 — the table is per file "
                         "but identical across a take)")
    a = ap.parse_args()

    files = []
    for p in a.paths:
        if os.path.isdir(p):
            got = sorted(glob.glob(os.path.join(p, "*.dng")) +
                         glob.glob(os.path.join(p, "*.DNG")))
            if not got:
                print(f"{p}: no DNGs")
            files += got[:a.limit]
        else:
            files.append(p)

    if not files:
        raise SystemExit("nothing to check")

    goldens = golden_tables()
    print("golden tables regenerated from ccmp_decode.py (not read from disk):")
    for b, (tbl, blk, wht) in sorted(goldens.items()):
        print(f"  b={b:g}  {len(tbl)} entries  BlackLevel {blk}  WhiteLevel {wht}")

    bad = 0
    for f in files:
        try:
            if check(f, goldens):
                bad += 1
        except Exception as e:                                    # noqa: BLE001
            print(f"\n{os.path.basename(f)}\n  FAIL  {type(e).__name__}: {e}")
            bad += 1

    print(f"\n{'=' * 60}")
    print(f"{len(files) - bad}/{len(files)} passed"
          + ("" if bad == 0 else f"   ** {bad} FAILED **"))
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
