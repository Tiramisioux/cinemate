#!/usr/bin/env python3
"""patches.py — chart sampler for the six-mode ccmp-greycard set.

Patch boxes live in NORMALISED frame coordinates, so one definition samples both
1928x1090 and 3856x2180 takes. Verified: the two resolutions are the same field
of view to within a pixel, so a normalised box lands on the same physical chip
in every take, and lens shading and flare are therefore COMMON MODE between
takes and cancel when the same patch is compared across modes.

Reports RAW CFA CODE means per phase (R, G1, G2, B). Nothing is black-subtracted,
gained or white-balanced here — that is the caller's job, so the numbers stay
auditable. Frame-to-frame spread is reported as the measurement precision.

  patches.py TAKE_DIR...  [--json out.json] [--limit N]
  patches.py TAKE_DIR...  --overlay DIR       # LOOK AT THIS before believing a number
  patches.py FRAME.dng    --profile X0,X1     # vertical G profile: find plateaus
"""
import os, sys, glob, json, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dngread import load  # noqa: E402
import modes as M  # noqa: E402
from ccmp_decode import for_mode, build, B_BINNED, B_FULL  # noqa: E402

# ── the CCMP12 decode ───────────────────────────────────────────────────────
# ** PER PIXEL, THEN AVERAGE. NEVER THE LUT ON A MEAN. ** (handoff §4)
# The table is applied to the raw CFA plane before the box is sliced and before
# any mean is taken. Applying it to a patch mean instead is wrong exactly where
# the curve bends — the same reason region means are biased near a knee — and it
# would look almost right everywhere else.
#
# Black is NOT re-stated here. The KEEP_PEDESTAL output domain (§3.4c) leaves
# BlackLevel at 200, and the table is the identity below knee1 (code 325 / 700),
# so modes.MEASURED_BLACK stays valid after decoding, unchanged.
_LUT = {}


def lut_for(b):
    if b not in _LUT:
        _LUT[b] = build(for_mode(b), "KEEP_PEDESTAL")["table"]
    return _LUT[b]


def decode_for(take, decode="auto"):
    """(b, new_white) for this take, or (None, None) if it must not be decoded."""
    if decode == "off":
        return None, None
    base = os.path.basename(take.rstrip("/"))
    hit = [(m, lab, lin) for pre, (m, lab, lin) in M.ALL_MODES.items()
           if base.startswith(pre)]
    if not hit:
        raise SystemExit(f"unrecognised take {base!r} — not in modes.ALL_MODES")
    m, lab, linear = hit[0]
    if m not in M.CCMP_MODES:
        if decode == "on":
            raise SystemExit(f"refusing to decode mode {m} ({lab}) — it is linear")
        return None, None
    b = B_BINNED if m in M.BINNED_MODES else B_FULL
    return b, build(for_mode(b), "KEEP_PEDESTAL")["white"]

# ── geometry ────────────────────────────────────────────────────────────────
# Boxes were read off take 5 (3856x2180) and then confirmed two ways: a vertical
# profile down each column (--profile), which puts every box on a flat plateau,
# and --overlay at BOTH resolutions.
W0, H0 = 3856.0, 2180.0


def _b(x0, y0, x1, y1):
    return (x0 / W0, y0 / H0, x1 / W0, y1 / H0)


PATCHES = {
    # illumination-check pairs, diagonal opposite corners (§3.0)
    "ill_W_TR": _b(3105, 195, 3265, 345),
    "ill_K_TR": _b(2820, 195, 2970, 345),
    "ill_W_BL": _b(775, 1850, 935, 2010),
    "ill_K_BL": _b(480, 1850, 640, 2010),
    # neutral ladder: second column of the left block, dark -> light
    "grey1": _b(760, 200, 930, 360),
    "grey2": _b(760, 475, 930, 630),
    "grey3": _b(760, 750, 930, 915),
    "grey4": _b(760, 1025, 930, 1185),
    "grey5": _b(760, 1300, 930, 1455),
    "grey6": _b(760, 1575, 930, 1745),
    # the four large chips, top to bottom. big4 is the HIGH-GLOSS BLACK: it
    # returns a specular image of the room, so it is a flare probe and never a
    # calibration anchor (§3.1).
    "big1_white": _b(1100, 220, 2650, 520),
    "big2_lgrey": _b(1100, 700, 2650, 1000),
    "big3_dgrey": _b(1100, 1180, 2650, 1480),
    "big4_gloss": _b(1100, 1680, 2650, 1980),
    # skin column, context only
    "skin1": _b(460, 200, 640, 360),
    "skin6": _b(460, 1575, 640, 1745),
}

# The §3.1 neutral ramp: the 6 ladder steps plus 3 of the 4 large chips, gloss
# black excluded. Ordered dark -> light by measured level.
RAMP = ["grey1", "grey2", "big3_dgrey", "big2_lgrey", "grey3", "grey4",
        "grey5", "grey6", "big1_white"]
PHASES = ["R", "G1", "G2", "B"]          # CFAPattern 0 1 1 2 = RGGB

# Shrink every box toward its centre before sampling, so patch borders, print
# registration slop and any residual error in the read-off coordinates stay out
# of the statistics.
INSET = 0.80


def box_px(spec, w, h):
    """Normalised box -> even-aligned pixel box, so the CFA phase mapping holds."""
    u0, v0, u1, v1 = spec
    mu, mv = (u1 - u0) * (1 - INSET) / 2, (v1 - v0) * (1 - INSET) / 2
    x0 = int(round((u0 + mu) * w)) & ~1
    y0 = int(round((v0 + mv) * h)) & ~1
    x1 = int(round((u1 - mu) * w)) & ~1
    y1 = int(round((v1 - mv) * h)) & ~1
    return x0, y0, max(x1, x0 + 2), max(y1, y0 + 2)


def sample_frame(path, names=None, b=None):
    names = names or list(PATCHES)
    d = load(path)
    raw = d["codes"]                       # saturation is a RAW-code property
    white = d["white"][0] if d["white"] else (1 << d["bits"]) - 1
    c = lut_for(b)[raw] if b else raw      # PER PIXEL, before any slice or mean
    out = {}
    for nm in names:
        x0, y0, x1, y1 = box_px(PATCHES[nm], d["w"], d["h"])
        sub = c[y0:y1, x0:x1].astype(np.float64)
        ph = dict(R=sub[0::2, 0::2], G1=sub[0::2, 1::2],
                  G2=sub[1::2, 0::2], B=sub[1::2, 1::2])
        rec = {k: dict(mean=float(v.mean()), std=float(v.std()), n=int(v.size))
               for k, v in ph.items()}
        rec["sat_frac"] = float((raw[y0:y1, x0:x1] >= white * 0.999).mean())
        rec["box"] = [x0, y0, x1, y1]
        out[nm] = rec
    return d, out


def sample_take(take, names=None, limit=None, decode="off"):
    """Per-patch means averaged over the take's frames, plus frame-to-frame spread."""
    names = names or list(PATCHES)
    files = sorted(glob.glob(os.path.join(take, "*.dng")))[:limit]
    if not files:
        raise SystemExit(f"no DNGs in {take}")
    b, new_white = decode_for(take, decode)
    per, d0 = [], None
    for f in files:
        d, s = sample_frame(f, names, b)
        d0 = d0 or d
        per.append(s)
    agg = {}
    for nm in names:
        agg[nm] = dict(box=per[0][nm]["box"],
                       sat_frac=float(np.mean([p[nm]["sat_frac"] for p in per])))
        for k in PHASES:
            m = np.array([p[nm][k]["mean"] for p in per])
            agg[nm][k] = dict(mean=float(m.mean()),
                              frame_spread=float(m.max() - m.min()),
                              px_std=float(np.mean([p[nm][k]["std"] for p in per])),
                              n=per[0][nm][k]["n"])
        agg[nm]["G"] = 0.5 * (agg[nm]["G1"]["mean"] + agg[nm]["G2"]["mean"])
    meta = dict(take=os.path.basename(take.rstrip("/")), nframes=len(files),
                w=d0["w"], h=d0["h"], bits=d0["bits"], black=d0["black"],
                white=d0["white"] if b is None else [new_white],
                has_lut=d0["has_lut"], decoded_b=b,
                as_shot_neutral=d0["as_shot_neutral"])
    return meta, agg


# ── visual verification ─────────────────────────────────────────────────────
def overlay(path, out_png, names=None):
    """Draw the sampling boxes on the green channel. Look at this first."""
    from PIL import Image, ImageDraw
    names = names or list(PATCHES)
    d = load(path)
    bl = d["black"][0] if d["black"] else 0
    g = np.clip(d["codes"][0::2, 1::2].astype(np.float64) - bl, 0, None)
    g = np.clip(g / max(np.percentile(g, 99.0), 1e-9), 0, 1) ** (1 / 2.2)
    im = Image.fromarray((g * 255).astype(np.uint8)).convert("RGB")
    dr = ImageDraw.Draw(im)
    for nm in names:
        x0, y0, x1, y1 = box_px(PATCHES[nm], d["w"], d["h"])
        dr.rectangle([x0 // 2, y0 // 2, x1 // 2, y1 // 2], outline=(255, 40, 40))
        dr.text((x0 // 2 + 3, y0 // 2 + 3), nm, fill=(255, 230, 40))
    sc = 1300 / im.width
    im.resize((int(im.width * sc), int(im.height * sc)), Image.BILINEAR).save(out_png)
    return out_png


def profile(path, x0, x1, step=40):
    """Vertical G profile down a column: finds patch plateaus without guessing."""
    d = load(path)
    bl = d["black"][0] if d["black"] else 0
    p = d["codes"][0::2, 1::2].astype(np.float64)[:, x0 // 2:x1 // 2].mean(axis=1) - bl
    print(f"{d['w']}x{d['h']} {d['bits']}-bit  col {x0}..{x1}  black {bl}")
    for i in range(0, len(p), max(1, step // 2)):
        print(f"  y={i*2:5d}  {p[i]:9.1f}  " + "#" * int(40 * max(p[i], 0) / max(p.max(), 1)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json"); ap.add_argument("--overlay"); ap.add_argument("--profile")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--decode", default="off", choices=["auto", "on", "off"],
                    help="apply the CCMP12 decode PER PIXEL before averaging; "
                         "'auto' decodes only modes 2 and 3")
    a = ap.parse_args()

    if a.profile:
        x0, x1 = (int(v) for v in a.profile.split(","))
        return profile(a.paths[0], x0, x1)
    if a.overlay:
        os.makedirs(a.overlay, exist_ok=True)
        for t in a.paths:
            f = sorted(glob.glob(os.path.join(t, "*.dng")))[0]
            print(overlay(f, os.path.join(a.overlay,
                          os.path.basename(t.rstrip("/"))[:24] + ".png")))
        return

    out = []
    for t in a.paths:
        meta, agg = sample_take(t, limit=a.limit, decode=a.decode)
        out.append(dict(meta=meta, patches=agg))
        dec = (f"  DECODED b={meta['decoded_b']:g}" if meta["decoded_b"] else "")
        print(f"\n=== {meta['take']}  {meta['w']}x{meta['h']} {meta['bits']}-bit  "
              f"black {meta['black'][0]:.0f}  white {meta['white'][0]}  "
              f"{meta['nframes']} frames  LUT {'yes' if meta['has_lut'] else 'NO'}{dec}")
        print(f"  {'patch':<12}{'R':>9}{'G1':>9}{'G2':>9}{'B':>9}{'G':>9}"
              f"{'sat%':>7}{'fspread':>9}{'pxstd':>8}")
        for nm in PATCHES:
            p = agg[nm]
            print(f"  {nm:<12}{p['R']['mean']:9.1f}{p['G1']['mean']:9.1f}"
                  f"{p['G2']['mean']:9.1f}{p['B']['mean']:9.1f}{p['G']:9.1f}"
                  f"{100*p['sat_frac']:7.2f}"
                  f"{max(p[k]['frame_spread'] for k in PHASES):9.2f}"
                  f"{p['G1']['px_std']:8.1f}")
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
