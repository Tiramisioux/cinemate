# CineMate brand assets

A record dot inside a ring, next to the hostname you reach it on. The mark is
the record button; `cinepi.local` is the point — this is a camera you talk to
over its own hotspot, on hardware you built.

**Everything here is generated.** Do not hand-edit these files:

```bash
python3 tools/make_brand_assets.py
```

The generator takes the mark's geometry from the settings editor's
`.brand .mark` CSS and its colours from that file's `:root`, so the logo and
the interface it stands for cannot drift apart. Change the CSS, re-run it.

## Files

| File | Use |
|---|---|
| `cinemate-logo-dark.svg` | The full lockup, for dark backgrounds. The master. |
| `cinemate-logo-light.svg` | The same, for light backgrounds |
| `cinemate-logo-badge.svg` | The lockup carrying its own dark ground — README headers, social cards, stickers, anywhere you cannot rely on what is behind it |
| `cinemate-logo-badge-light.svg` | The same on a light ground |
| `cinemate-mark.svg` | The mark alone, light ink — favicons, avatars, watermarks |
| `cinemate-mark-light.svg` | The mark alone, dark ink |
| `cinemate-favicon.svg` | The mark on its own rounded ground, so it reads against any browser chrome |
| `*-<width>.png` | Raster fallbacks at the widths in the generator's `rasterize()` |

The SVGs are the masters. The PNGs are conveniences for anything that cannot
take one — pick the width at or above what you need and let it scale down.

## Colours

| Token | Value | Where |
|---|---|---|
| `--danger` | `#ff4136` | The dot. Never change this one — it is the record colour. |
| `--ink` | `#f9f9f9` | Ring and wordmark on dark |
| `--panel` | `#0c0b09` | Ring and wordmark on light; the favicon's ground |
| `--muted` | `#8a8a8a` | `CINEPI.LOCAL` |

## Geometry

In the mark's own 22-unit square: ring centred at (11, 11), outer radius 11,
inner radius 9; dot radius 4, same centre. That is exactly a 22 px box with a
2 px border and a dot `inset: 5px` inside it — the CSS, in other words.

The ring is a filled annulus rather than a stroked circle, and the wordmark is
outlined rather than live text. Both for the same reason: geometry renders the
same everywhere, instructions do not.

## Clear space and minimum size

Leave at least the width of the ring's stroke (2 units, ~9% of the mark's
width) clear on every side. Below about 24 px the wordmark stops being
legible — use the mark on its own there.

## Type

`CINEMATE` is DIN 2014 Bold, `CINEPI.LOCAL` is DIN 2014 Regular, both from
`resources/fonts/` — the same files the HDMI GUI draws with. The lockup
carries them as outlines, so nothing here depends on the font being installed
and no font data is redistributed in these files.
