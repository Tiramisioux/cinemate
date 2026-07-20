# ClearHDR (imx585)

ClearHDR is the imx585's on-sensor single-frame HDR. The sensor merges a high-gain (HG) and a low-gain (LG) readout internally and outputs one 16-bit linear Bayer frame. Cinemate records it as true 16-bit CinemaDNGs — BlackLevel 3200, WhiteLevel 65535, no LUT needed in post.

## Requirements

| Piece | Needed | Why |
|-------|--------|-----|
| Kernel | ≥ 6.12.93+rpt (the Cinemate baseline) | older `rp1-cfe` corrupts 16-bit CSI-2 capture; 10/12-bit is unaffected |
| Sensor driver | Tiramisioux `imx585-v4l2-driver`, branch `6.12.y` | exposes `wide_dynamic_range` and the 16-bit modes |
| libcamera | Tiramisioux `libcamera`, branch `cinemate` | 16-bit endian swap handling |
| Exposure | manual | ISP statistics are invalid at 16-bit, so auto exposure and auto white balance cannot run |

## What changes when ClearHDR is on

- Frame rates halve versus the plain modes (≈ 33 fps at 4K, ≈ 37 fps at 2K on an overclocked RP1). `min_frame_rate` in `settings.json` defaults to 20 so the 4K ClearHDR mode stays selectable.
- Analogue gain caps at code 80 ≈ 15.8× (ISO 1580).
- Each 3856×2180 DNG is ≈ 16.9 MB. Storage bandwidth: 15 fps ≈ 252 MB/s, 20 fps ≈ 336 MB/s — plan drives accordingly. The minutes-left display uses the 16.9 MB figure automatically.
- Auto exposure and auto white balance cannot run in the 16-bit modes (ISP statistics are invalid at 16-bit). Set exposure manually.
- Highlights near the HG→LG hand-off can render magenta in flat greys — sensor-side merge behaviour, not a capture defect. See [Magenta highlights](#magenta-highlights).

## ClearHDR modes in the mode table

Cinemate probes the sensor **twice** at startup — `cinepi-raw --list-cameras`
and `cinepi-raw --list-cameras --hdr sensor` — and merges both results, so the
plain and the ClearHDR modes live in the same mode table. Selecting a ClearHDR
mode launches cinepi-raw with `--hdr sensor`; selecting a plain mode launches
without it. No separate toggle is needed.

The imx585 exposes ClearHDR at **both** 12-bit and 16-bit, so the table is
ordered plain modes first, then 12-bit HDR, then 16-bit HDR:

| Mode | Resolution | Bit depth | HDR | ~fps (overclocked) |
|------|-----------|-----------|-----|--------------------|
| 0 | 1928×1090 | 12-bit | — | 75 |
| 1 | 3856×2180 | 12-bit | — | 66.85 |
| 2 | 1928×1090 | 12-bit | HDR | 37.50 |
| 3 | 3856×2180 | 12-bit | HDR | 33.43 |
| 4 | 1928×1090 | 16-bit | HDR | 37.50 |
| 5 | 3856×2180 | 16-bit | HDR | 33.43 |

HDR modes are labelled so they read distinctly from the plain modes:

- **Simple (HDMI) GUI** — `HDR` after the bit depth, e.g. `1928×1090 :12b HDR`.
- **Web GUI** — `:HDR` appended in the resolution dropdown, e.g. `1928 : 1090 : 12b :HDR`.

To hide the ClearHDR modes entirely, set the `hdr` whitelist in
`settings.json` → `resolutions`:

```json
"resolutions": {
  "hdr": {"sdr": true, "imx585_clear_hdr": false}
}
```

Both `true` (the default) exposes both; `"imx585_clear_hdr": false` hides
the HDR modes; `"sdr": false` shows only them. It works like the
neighbouring `bit_depths` and `k_steps` whitelists (the legacy
`[false, true]` list form still works too). Frame rates depend on the RP1
clock — see [Overclocking the Pi](overclocking.md).

## HDR profiles

Presets live in `resources/HDR_profiles.json`. Each profile sets ClearHDR on or off plus optional knob values, and applying one restarts the camera (the `wide_dynamic_range` control changes the sensor's mode list, so a restart is required).

CLI:

```text
set hdr profile        # cycle to the next profile
set hdr profile 0      # apply profile 0 (sdr)
set hdr profile 1      # apply profile 1 (hdr-default)
set hdr profile 2      # apply profile 2 (hdr-highlight)
```

Shipped profiles:

| # | Name | ClearHDR | Knobs |
|---|------|----------|-------|
| 0 | `sdr` | off | — |
| 1 | `hdr-default` | on | threshold 0,0 · blend 0 · gain adder +6 dB (menu 1 — lower noise than the driver's +12 dB) |
| 2 | `hdr-highlight` | on | threshold 500,3000 · blend 2 · gain adder +12 dB |

Profile fields: `hdr` (bool), `threshold` (`[low, high]`, 0–4095 each), `blend_mode` (0–8), `gain_adder` (0–5). Knob fields are optional, but explicit values keep profiles deterministic — sensor controls persist until reboot. The active profile index is stored in the Redis key `hdr_profile`, and the stored knob keys are re-applied by cinepi-raw at every start.

## Live knobs

The merge behaviour is tunable **while streaming** — no restart. Each command writes a Redis key that cinepi-raw applies to the sensor as a V4L2 control.

Per pixel, the sensor picks a source by level: HG below the first threshold, LG (lifted by the gain adder) above the second, a blend of both in between. HG carries the clean shadows and mids; LG carries the highlight headroom. Both readouts share one exposure, so no setting here can introduce motion ghosting.

| CLI command | Redis key | Range | What it does | Visual impact |
|-------------|-----------|-------|--------------|---------------|
| `set hdr threshold low 500` | `hdr_threshold_low` | 0–4095 | raw level below which the sensor reads pure HG | lower = earlier hand-off, more highlight headroom, noisier mids; higher = more range stays clean HG |
| `set hdr threshold high 3000` | `hdr_threshold_high` | 0–4095 | raw level above which the sensor reads pure LG | lower = highlight detail kicks in sooner; higher = highlights closer to the plateau before LG takes over |
| `set hdr blend 2` | `hdr_blend` | 0–8 | HG:LG mix inside the transition zone (0 = HG 1/2 + LG 1/2, per the driver menu) | HG-heavy = cleaner transition tones; LG-heavy = highlight detail holds longer through the zone, more grain there |
| `set hdr gain adder 2` | `hdr_gain_adder` | 0–5 | digital gain on the low-gain path in the merge (2 = +12 dB, the driver default); shifts where the blend knee lands in the output range | lower = highlights darker, flatter, cleaner — lift in the grade; higher = brighter highlight rendering, more grain in the highlights |

`hdr_threshold_low` and `hdr_threshold_high` are two Redis keys, but the sensor
control underneath is a single hardware pair — cinepi-raw always reads both
keys and writes them together, so either one applies the pair live regardless
of which changed.

The same keys work directly over Redis, e.g. from a custom controller:

```bash
redis-cli set hdr_threshold_low 500 && redis-cli publish cp_controls hdr_threshold_low
redis-cli set hdr_blend 2 && redis-cli publish cp_controls hdr_blend
```

### Threshold — where the hand-off sits

Both values are raw 12-bit levels compared against the HG signal (the vendor manual calls them the HG saturation cutoff). The pair brackets the transition zone:

- **First value** — below it, pure HG. Raising it keeps more of the range on the clean high-gain data.
- **Second value** — above it, pure LG. Lowering it protects highlights earlier.
- **The gap** — the blend zone. Wide (`500,3000`) = gradual hand-off. Narrow = abrupt seam that can show as a band or colour step in smooth gradients.
- `0,0` — no explicit bracket (vendor default, used by the `hdr-default` profile); the sensor applies its internal hand-off.

### Blend — the mix inside the zone

Driver menu values, HG : LG weight in the transition zone:

| Value | Mix | Value | Mix |
|-------|-----|-------|-----|
| 0 | HG 1/2, LG 1/2 | 5 | HG 1/2, LG 1/2 (2nd) |
| 1 | HG 3/4, LG 1/4 | 6 | HG 1/16, LG 15/16 |
| 2 | HG 1/2, LG 1/2 | 7 | HG 1/8, LG 7/8 |
| 3 | HG 7/8, LG 1/8 | 8 | HG 1/4, LG 3/4 |
| 4 | HG 15/16, LG 1/16 | | |

The datasheet lists three 50/50 entries — 0, 2 and 5 behave the same.

- **HG-heavy (1, 3, 4)** — transition tones stay on the cleaner high-gain data. Smoothest choice when the zone lands on faces or detailed mids.
- **LG-heavy (6, 7, 8)** — highlight data dominates through the zone. Maximum highlight separation near the top; the low-gain grain shows earlier.

### Gain adder — where the knee lands

Menu 0–5 = **+0, +6, +12, +18, +24, +29.1 dB** of digital gain on the low-gain path. 2 (+12 dB) is the driver default; the `hdr-default` profile uses 1 (+6 dB) for a lower noise floor.

- Lower values place highlights lower in the output range: darker and flatter out of camera, but cleanest — bring them up in the grade.
- Higher values render highlights brighter and push the blend knee up the range, amplifying low-gain read noise in exactly the tones ClearHDR is protecting.

### Symptom → knob

| You see | Try |
|---------|-----|
| Magenta in bright flat areas | start from the `hdr-highlight` profile — see [Magenta highlights](#magenta-highlights) |
| Grainy mids or faces | higher thresholds, HG-heavier blend (3, 4), or a lower gain adder |
| A band or step where tones change character | widen the gap between the two threshold values |
| Highlights too dark and flat out of camera | higher gain adder — costs highlight grain |
| Grainy highlights | lower gain adder; lift in the grade instead |

## Magenta highlights

Bright flat areas near the hand-off can render pink. The band comes from the sensor's merge, not from Cinemate — it shows in plain `libcamera-still` raws on a stock Pi stack too, and a Raspberry Pi engineer confirmed it sits in the raw data: the sensor combines the two readouts inconsistently when some colour channels saturate before others ([forum thread](https://forums.raspberrypi.com/viewtopic.php?t=388520)).

What happens:

- At the hand-off the merged channels converge to a plateau **below** WhiteLevel. On an overexposed Cinemate test frame the plateau measured ≈ 20 000 of 65 535, and the level moves with gain.
- A raw developer desaturates clipped highlights only at WhiteLevel. The plateau never reaches it, so white-balance gains stay applied — red and blue land above green and the patch reads pink instead of white.

Handling it:

| Approach | How |
|----------|-----|
| Exposure | keep important neutrals out of the hand-off band; in HDR modes err darker rather than brighter |
| Knobs | start from the `hdr-highlight` profile (threshold 500,3000 · blend 2 · +12 dB) and move the hand-off away from the affected tones |
| Grade | treat the plateau as the clip point: highlight reconstruction/desaturation, or pull the shot's effective white level down to the plateau |

The plateau level depends on gain and knob settings, so handle it per shot in the grade — the DNG WhiteLevel tag stays 65535.

## Exposure workflow

Auto exposure and auto white balance are off in 16-bit modes (the ISP cannot compute statistics on 16-bit data). Set ISO, shutter and white balance manually — the normal Cinemate controls (`set iso`, `set shutter a`, `set wb`) keep working; they are always manual values in Cinemate anyway. A practical 4K indoor starting point: ISO 800, shutter 8 ms, 15 fps.
