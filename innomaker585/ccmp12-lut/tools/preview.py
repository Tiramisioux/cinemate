#!/usr/bin/env python3
"""preview.py — DNG -> RGB PNG, with the CCMP12 decode applied PER PIXEL.

    preview.py <take-glob> [<take-glob> ...] -o out.png [--decode auto|on|off]
               [--wb percentile|asn] [--panel 480]

One take renders one panel; several render a labelled strip, in the order given.

  ** DECODE PER PIXEL, THEN AVERAGE. NEVER THE LUT ON A MEAN. ** (handoff §4)
  The LUT is applied to the raw CFA plane at load, before the G1/G2 average,
  before the demosaic and before the downsample. Averaging does not commute
  with a bend: applying the table to an already-averaged value is wrong exactly
  where the curve bends, which is the only place that matters.

  ** --decode auto decodes only modes 2 and 3. ** The linear modes must never
  be decoded, and `auto` is the only setting that cannot get that backwards.

BLACK LEVEL. This tool hardcoded `blk = 229.0` until 2026-08-07. That was the
light-leaked figure from the deleted ccmp-c0 set, falsified in handoff §2 —
every mode sits on its tag. It now reads BlackLevel from the file, which is
also correct AFTER decoding: the KEEP_PEDESTAL output domain (§3.4c) leaves
BlackLevel at 200 precisely so nothing downstream has to know whether a table
was applied.

WHITE BALANCE.
  percentile  each channel to its own 99.5th pct — a crude WB on the white chip.
              What evidence/res2_clearhdr12.png used, so it is the comparable
              one. It FLATTERS a bad curve by neutralising the highlight.
  asn         the file's own AsShotNeutral (0.625 1 0.5263), one shared scale.
              What a converter actually does, and the honest render.
"""
import os
import sys
import glob
import argparse
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dngread                                                      # noqa: E402
import modes as M                                                   # noqa: E402
from ccmp_decode import for_mode, build, B_BINNED, B_FULL           # noqa: E402

_LUT = {}


def lut_for(b):
    if b not in _LUT:
        _LUT[b] = build(for_mode(b), "KEEP_PEDESTAL")["table"]
    return _LUT[b]


def mode_of(take):
    base = os.path.basename(take.rstrip("/"))
    for prefix, (m, label, linear) in M.ALL_MODES.items():
        if base.startswith(prefix):
            return m, label, linear
    raise SystemExit(f"unrecognised take {base!r} — not in modes.ALL_MODES")


def render(take, decode="auto", wb="percentile", panel=480):
    """One take -> (H, W, 3) uint8, plus a label."""
    path = sorted(glob.glob(os.path.join(take, "*.dng")))[0]
    d = dngread.load(path)
    m, label, linear = mode_of(take)
    b = B_BINNED if m in M.BINNED_MODES else B_FULL

    codes = d["codes"]
    do = {"auto": m in M.CCMP_MODES, "on": True, "off": False}[decode]
    if do and linear:
        raise SystemExit(f"refusing to decode mode {m} ({label}) — it is linear")
    if do:
        codes = lut_for(b)[codes]          # PER PIXEL, before any averaging
    plane = codes.astype(np.float64)

    # CFA is RGGB on all six takes; read it rather than assume it.
    cfa = d["cfa"]
    if cfa != [0, 1, 1, 2]:
        raise SystemExit(f"{path}: unexpected CFA {cfa}, expected RGGB")
    R = plane[0::2, 0::2]
    G = 0.5 * (plane[0::2, 1::2] + plane[1::2, 0::2])   # average AFTER decode
    B = plane[1::2, 1::2]

    # BlackLevel is unchanged by the decode — that is the point of §3.4c.
    rgb = np.clip(np.stack([R, G, B], -1) - float(d["black"][0]), 0, None)

    if wb == "asn":
        rgb = rgb / np.asarray(d["as_shot_neutral"], float)
        hi = np.percentile(rgb, 99.5)
        rgb = rgb / hi if hi > 0 else rgb
    else:
        for c in range(3):
            hi = np.percentile(rgb[..., c], 99.5)
            if hi > 0:
                rgb[..., c] /= hi

    rgb = np.clip(rgb, 0, 1) ** (1 / 2.2)
    step = max(1, rgb.shape[1] // panel)                # area-average, post-decode
    h, w = (rgb.shape[0] // step) * step, (rgb.shape[1] // step) * step
    rgb = rgb[:h, :w].reshape(h // step, step, w // step, step, 3).mean((1, 3))
    tag = f"mode {m}  {label}" + ("  DECODED" if do else "")
    return (rgb * 255).astype(np.uint8), tag


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("takes", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--decode", default="auto", choices=["auto", "on", "off"])
    ap.add_argument("--wb", default="percentile", choices=["percentile", "asn"])
    ap.add_argument("--panel", type=int, default=480)
    ap.add_argument("--label", default=None,
                    help="comma-separated panel captions, overriding the mode tag")
    a = ap.parse_args()

    from PIL import Image, ImageDraw
    caps = a.label.split(",") if a.label else [None] * len(a.takes)
    panels, tags = [], []
    for t, cap in zip(a.takes, caps):
        img, tag = render(t, a.decode, a.wb, a.panel)
        panels.append(img)
        tags.append(cap.strip() if cap else tag)
        print(f"  {tag:<34} {img.shape[1]}x{img.shape[0]}  from {os.path.basename(t.rstrip('/'))}")

    pad, bar = 8, 22
    h = max(p.shape[0] for p in panels)
    w = sum(p.shape[1] for p in panels) + pad * (len(panels) + 1)
    sheet = Image.new("RGB", (w, h + bar + pad * 2), (18, 18, 18))
    x = pad
    for p, tag in zip(panels, tags):
        sheet.paste(Image.fromarray(p), (x, bar + pad))
        ImageDraw.Draw(sheet).text((x + 2, 6), tag, fill=(235, 235, 235))
        x += p.shape[1] + pad
    sheet.save(a.out)
    print(f"-> {a.out}  {sheet.size[0]}x{sheet.size[1]}  wb={a.wb}")


if __name__ == "__main__":
    main()
