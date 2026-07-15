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
- Highlights near the HG→LG hand-off can render magenta in flat greys: the two readouts converge there and white balance lifts red/blue above green. Tune the knobs below for the scene or grade it out — it is not a capture defect.

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
  "hdr": [false]
}
```

`[false, true]` (the default) exposes both; `[false]` hides the HDR modes;
`[true]` shows only them. It works like the neighbouring `bit_depths` and
`k_steps` whitelists. Frame rates depend on the RP1 clock — see
[Overclocking the Pi](overclocking.md).

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

The merge behaviour is tunable **while streaming** — no restart. Each command writes a Redis key that cinepi-raw applies to the sensor as a V4L2 control:

| CLI command | Redis key | Range | What it does |
|-------------|-----------|-------|--------------|
| `set hdr threshold 500,3000` | `hdr_threshold` | two values, each 0–4095 | raw levels that steer the per-pixel hand-off from the high-gain to the low-gain readout; earlier hand-off = more highlight headroom, more mid-tone noise |
| `set hdr blend 2` | `hdr_blend` | 0–8 | how HG and LG are mixed across the transition zone (0 = HG 1/2 + LG 1/2, per the driver menu) |
| `set hdr gain adder 2` | `hdr_gain_adder` | 0–5 | digital gain applied to the low-gain path in the merge (2 = +12 dB, the driver default); shifts where the blend knee lands in the output range |

The same keys work directly over Redis, e.g. from a custom controller:

```bash
redis-cli set hdr_blend 2 && redis-cli publish cp_controls hdr_blend
```

## Exposure workflow

Auto exposure and auto white balance are off in 16-bit modes (the ISP cannot compute statistics on 16-bit data). Set ISO, shutter and white balance manually — the normal Cinemate controls (`set iso`, `set shutter a`, `set wb`) keep working; they are always manual values in Cinemate anyway. A practical 4K indoor starting point: ISO 800, shutter 8 ms, 15 fps.
