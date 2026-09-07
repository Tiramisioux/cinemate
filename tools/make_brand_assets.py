#!/usr/bin/env python3
"""Generate the CineMate brand assets in resources/branding/.

The mark is the settings editor's `.brand .mark` -- a record dot inside a
ring, which is the whole idea: a record button, and a hostname you reach over
your own hotspot. Its geometry is taken from that CSS rather than redrawn, so
the two cannot drift:

    .brand .mark        22x22 border-box, border: 2px solid var(--ink)
    .brand .mark::after position:absolute; inset:5px

    -> border box 22x22, padding box 18x18 offset (2,2)
    -> ring:  cx=cy=11, r=10, stroke-width=2   (spans 9..11)
    -> dot:   cx=cy=11, r=4                    (the 8x8 inset box)

Run it after changing either the CSS or the palette:

    python3 tools/make_brand_assets.py

The wordmark is converted to OUTLINES, not left as <text>: a logo has to
render identically on a machine that has never heard of DIN 2014, and
shipping the font itself inside an SVG is a licensing question outlining
does not raise. resources/fonts/DIN2014-*.ttf is the source, the same files
the HDMI GUI already draws with.

Standard library plus fonttools (pip install fonttools). PNGs are drawn with
Pillow from the same numbers rather than by rasterizing the SVGs; the SVGs
are the masters either way. See _render_png() for why.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont


ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "resources/fonts"
OUT = ROOT / "resources/branding"

# settings_editor.html's :root. One source for these too -- a logo that has
# quietly stopped matching the interface it stands for is worse than no logo.
INK = "#f9f9f9"        # --ink
INK_LIGHT = "#0c0b09"  # --panel, used as the ink on a light ground
MUTED = "#8a8a8a"      # --muted
DANGER = "#ff4136"     # --danger
PANEL = "#0c0b09"      # --panel

# .brand .mark, in its own 22-unit coordinate system.
MARK_SIZE = 22.0
RING_R = 10.0
RING_STROKE = 2.0
DOT_R = 4.0
CENTRE = MARK_SIZE / 2.0

# .brand: gap:10px between the mark and the name block.
GAP = 10.0
# .brand-name / .brand-name small
NAME_SIZE, NAME_TRACK = 15.0, 0.02      # font-size, letter-spacing in em
SUB_SIZE, SUB_TRACK = 10.0, 0.12
# Leading between the two lines, chosen so the block optically balances the
# 22-unit mark rather than copying the browser's line boxes.
LINE_GAP = 3.0


def outline(text: str, font_path: Path, size: float, tracking_em: float):
    """(svg path data, advance width) for *text* set at *size*, y-down, with
    the pen origin on the baseline at x=0."""
    font = TTFont(font_path)
    upem = font["head"].unitsPerEm
    scale = size / upem
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    tracking = tracking_em * size

    parts: list[str] = []
    x = 0.0
    for index, char in enumerate(text):
        name = cmap.get(ord(char))
        if name is None:
            raise SystemExit(f"{font_path.name} has no glyph for {char!r}")
        pen = SVGPathPen(glyph_set)
        # y is negated: font units are y-up, SVG user space is y-down.
        glyph_set[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, 0)))
        data = pen.getCommands()
        if data:
            parts.append(data)
        x += hmtx[name][0] * scale
        if index < len(text) - 1:
            x += tracking
    # A trailing letter-space is part of neither the ink nor the lockup.
    return " ".join(parts), x


def cap_height(font_path: Path, size: float) -> float:
    font = TTFont(font_path)
    upem = font["head"].unitsPerEm
    os2 = font.get("OS/2")
    cap = getattr(os2, "sCapHeight", None) if os2 else None
    if not cap:
        # Fall back to the H outline; sCapHeight is optional in OS/2 v2-.
        cap = font["glyf"]["H"].yMax if "glyf" in font else upem * 0.7
    return cap * size / upem


def _ring_path(cx: float, cy: float) -> str:
    """The ring as a FILLED annulus rather than a stroked circle.

    Same shape either way, but a stroke is a rendering instruction and a fill
    is geometry -- and renderers disagree about strokes. ImageMagick's
    internal MSVG renderer (the fallback when librsvg is absent, which is how
    this repo's own machine is set up) drops `fill="none"` + stroke entirely
    and rasterizes a mark with no ring at all. Outlining it is the same fix
    applied to the wordmark, for the same reason: geometry travels,
    instructions do not.
    """
    outer = RING_R + RING_STROKE / 2.0
    inner = RING_R - RING_STROKE / 2.0
    return " ".join(
        f"M{cx - r:g},{cy:g} a{r:g},{r:g} 0 1,0 {2 * r:g},0 "
        f"a{r:g},{r:g} 0 1,0 {-2 * r:g},0 Z"
        for r in (outer, inner)
    )


def mark_svg(ink: str, *, size: float = MARK_SIZE, x: float = 0.0, y: float = 0.0) -> str:
    cx, cy = x + CENTRE, y + CENTRE
    return (
        f'  <path fill="{ink}" fill-rule="evenodd" d="{_ring_path(cx, cy)}"/>\n'
        f'  <circle cx="{cx:g}" cy="{cy:g}" r="{DOT_R:g}" fill="{DANGER}"/>\n'
    )


def write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    print(f"  {path.relative_to(ROOT)}")


def build_mark(pad: float = 2.0) -> None:
    box = MARK_SIZE + pad * 2
    for name, ink in (("cinemate-mark", INK), ("cinemate-mark-light", INK_LIGHT)):
        write(OUT / f"{name}.svg",
              f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {box:g} {box:g}" '
              f'width="{box:g}" height="{box:g}" role="img" aria-label="CineMate">\n'
              f'  <title>CineMate</title>\n'
              + mark_svg(ink, x=pad, y=pad) +
              '</svg>\n')


def build_favicon(pad: float = 5.0) -> None:
    """The mark on its own ground, so it reads against any browser chrome."""
    box = MARK_SIZE + pad * 2
    write(OUT / "cinemate-favicon.svg",
          f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {box:g} {box:g}" '
          f'width="{box:g}" height="{box:g}" role="img" aria-label="CineMate">\n'
          f'  <title>CineMate</title>\n'
          f'  <rect width="{box:g}" height="{box:g}" rx="{box * 0.22:g}" fill="{PANEL}"/>\n'
          + mark_svg(INK, x=pad, y=pad) +
          '</svg>\n')


def build_lockup(ink: str, sub_ink: str, suffix: str, *, ground: str | None = None,
                 pad: float = 6.0) -> None:
    bold = FONTS / "DIN2014-Bold.ttf"
    regular = FONTS / "DIN2014-Regular.ttf"
    name_path, name_w = outline("CINEMATE", bold, NAME_SIZE, NAME_TRACK)
    sub_path, sub_w = outline("CINEPI.LOCAL", regular, SUB_SIZE, SUB_TRACK)

    name_cap = cap_height(bold, NAME_SIZE)
    sub_cap = cap_height(regular, SUB_SIZE)
    # Both lines are all-caps, so the ink runs from the first baseline minus
    # its cap height to the second baseline. Centre THAT against the mark --
    # not the font's line boxes, which carry descender space no glyph here uses.
    block_h = name_cap + LINE_GAP + sub_cap
    top = pad + (MARK_SIZE - block_h) / 2.0
    name_baseline = top + name_cap
    sub_baseline = name_baseline + LINE_GAP + sub_cap

    text_x = pad + MARK_SIZE + GAP
    width = text_x + max(name_w, sub_w) + pad
    height = MARK_SIZE + pad * 2

    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" '
        f'width="{width:g}" height="{height:g}" role="img" '
        f'aria-label="CineMate — cinepi.local">',
        '  <title>CineMate — cinepi.local</title>',
    ]
    if ground:
        body.append(f'  <rect width="{width:g}" height="{height:g}" fill="{ground}"/>')
    body.append(mark_svg(ink, x=pad, y=pad).rstrip("\n"))
    body.append(f'  <path transform="translate({text_x:g} {name_baseline:g})" '
                f'fill="{ink}" d="{name_path}"/>')
    body.append(f'  <path transform="translate({text_x:g} {sub_baseline:g})" '
                f'fill="{sub_ink}" d="{sub_path}"/>')
    body.append('</svg>')
    write(OUT / f"cinemate-logo-{suffix}.svg", "\n".join(body) + "\n")


def _draw_text(draw, xy, text, font, fill, tracking_px):
    """Pillow has no letter-spacing, so the lockup is set glyph by glyph."""
    x, y = xy
    for index, char in enumerate(text):
        draw.text((x, y), char, font=font, fill=fill, anchor="ls")
        x += draw.textlength(char, font=font)
        if index < len(text) - 1:
            x += tracking_px


def _render_png(path: Path, width_units: float, height_units: float, target_w: int,
                ink: str, sub_ink: str, *, ground=None, corner: float = 0.0,
                wordmark: bool = False, supersample: int = 8) -> None:
    """Draw the asset directly with Pillow at *target_w* pixels wide.

    Not by rasterizing the SVG: the only SVG renderer on this machine is
    ImageMagick's internal MSVG fallback, which tessellates arcs coarsely
    enough to show on a circle this size. Pillow is already a dependency (the
    HDMI GUI's raster path) and draws the same geometry from the same numbers,
    supersampled and downscaled for clean edges. The SVGs remain the masters;
    these are conveniences for anything that cannot take one.
    """
    from PIL import Image, ImageDraw, ImageFont

    scale = (target_w / width_units) * supersample
    W = round(width_units * scale)
    H = round(height_units * scale)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if ground:
        if corner:
            draw.rounded_rectangle([0, 0, W - 1, H - 1],
                                   radius=round(corner * scale), fill=ground)
        else:
            draw.rectangle([0, 0, W - 1, H - 1], fill=ground)

    pad = 6.0 if wordmark else (5.0 if ground else 2.0)
    cx = (pad + CENTRE) * scale
    cy = (pad + CENTRE) * scale
    outer = (RING_R + RING_STROKE / 2.0) * scale
    inner = (RING_R - RING_STROKE / 2.0) * scale
    dot = DOT_R * scale
    draw.ellipse([cx - outer, cy - outer, cx + outer, cy + outer], fill=ink)
    # Punch the ring's hole rather than painting it: over a ground of any
    # colour (or none), repainting it would be wrong.
    hole = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(hole).ellipse(
        [cx - inner, cy - inner, cx + inner, cy + inner], fill=(0, 0, 0, 255))
    cleared = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.paste(cleared, (0, 0), hole)
    if ground:
        ring_fill = Image.new("RGBA", (W, H), ground)
        img.paste(ring_fill, (0, 0), hole)
    draw = ImageDraw.Draw(img)
    draw.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=DANGER)

    if wordmark:
        bold = ImageFont.truetype(str(FONTS / "DIN2014-Bold.ttf"),
                                  round(NAME_SIZE * scale))
        regular = ImageFont.truetype(str(FONTS / "DIN2014-Regular.ttf"),
                                     round(SUB_SIZE * scale))
        name_cap = cap_height(FONTS / "DIN2014-Bold.ttf", NAME_SIZE)
        sub_cap = cap_height(FONTS / "DIN2014-Regular.ttf", SUB_SIZE)
        block_h = name_cap + LINE_GAP + sub_cap
        top = pad + (MARK_SIZE - block_h) / 2.0
        text_x = (pad + MARK_SIZE + GAP) * scale
        _draw_text(draw, (text_x, (top + name_cap) * scale), "CINEMATE",
                   bold, ink, NAME_TRACK * NAME_SIZE * scale)
        _draw_text(draw, (text_x, (top + name_cap + LINE_GAP + sub_cap) * scale),
                   "CINEPI.LOCAL", regular, sub_ink, SUB_TRACK * SUB_SIZE * scale)

    img = img.resize((target_w, max(1, round(H / supersample))), Image.LANCZOS)
    img.save(path)
    print(f"  {path.relative_to(ROOT)}")


def rasterize() -> None:
    bold = FONTS / "DIN2014-Bold.ttf"
    regular = FONTS / "DIN2014-Regular.ttf"
    _, name_w = outline("CINEMATE", bold, NAME_SIZE, NAME_TRACK)
    _, sub_w = outline("CINEPI.LOCAL", regular, SUB_SIZE, SUB_TRACK)
    lock_w = 6.0 + MARK_SIZE + GAP + max(name_w, sub_w) + 6.0
    lock_h = MARK_SIZE + 12.0
    mark_box = MARK_SIZE + 4.0
    fav_box = MARK_SIZE + 10.0

    for w in (16, 32, 64, 128, 256, 512):
        _render_png(OUT / f"cinemate-mark-{w}.png", mark_box, mark_box, w, INK, MUTED)
        _render_png(OUT / f"cinemate-mark-light-{w}.png", mark_box, mark_box, w,
                    INK_LIGHT, MUTED)
    for w in (32, 64, 180, 512):
        _render_png(OUT / f"cinemate-favicon-{w}.png", fav_box, fav_box, w, INK, MUTED,
                    ground=PANEL, corner=fav_box * 0.22)
    for w in (512, 1024, 2048):
        _render_png(OUT / f"cinemate-logo-dark-{w}.png", lock_w, lock_h, w, INK, MUTED,
                    wordmark=True)
        _render_png(OUT / f"cinemate-logo-light-{w}.png", lock_w, lock_h, w,
                    INK_LIGHT, MUTED, wordmark=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svg-only", action="store_true",
                        help="write the SVG masters and skip the PNGs")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    print("SVG masters:")
    build_mark()
    build_favicon()
    build_lockup(INK, MUTED, "dark")
    build_lockup(INK_LIGHT, MUTED, "light")
    if not args.svg_only:
        print("PNG:")
        rasterize()
    return 0


if __name__ == "__main__":
    sys.exit(main())
