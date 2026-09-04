# ClearHDR (imx585)

ClearHDR is the imx585's on-sensor single-frame HDR. The sensor merges a high-gain (HG) and a low-gain (LG) readout internally and outputs one 16-bit linear Bayer frame. CineMate records it as true 16-bit CinemaDNGs — BlackLevel 3200, WhiteLevel 65535.

## The Clear HDR stack

CineMate image and install script ships with the following stack:

| Piece                    | Needed                                                     | Why                                                                                                                                |
| ------------------------ | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Kernel                   | ≥ 6.12.93+rpt (the CineMate baseline)                      | older `rp1-cfe` corrupts 16-bit CSI-2 capture; 10/12-bit is unaffected                                                             |
| Sensor driver            | Tiramisioux `imx585-v4l2-driver`, branch `cinemate-7modes` | exposes `wide_dynamic_range`, the 3840×2200 16-bit mode, and the `ccmp` overlay parameter; gates the invalid binned-ClearHDR combo |
| Overlay                  | `dtoverlay=imx585,...,ccmp` in config.txt                  | without `ccmp` the 12-bit CCMP ClearHDR mode does not exist on this driver (the installer writes it)                               |
| libcamera                | Tiramisioux `libcamera`, branch `cinemate`                 | 16-bit endian swap handling                                                                                                        |
| Kernel patch (mono only) | `scripts/patch-rp1-cfe.sh`                                 | the stock kernel's Y16 format entry misses the 16-bit workaround — see [Mono sensor](#mono-sensor-imx585_mono)                     |
| Exposure                 | manual                                                     | ISP statistics are invalid at 16-bit, so auto exposure and auto white balance cannot run                                           |

## ClearHDR features

- Frame rates halve versus the plain modes (≈ 33 fps at 4K, ≈ 37 fps at 2K on an overclocked RP1).
- Analogue gain caps at code 80 ≈ 15.8× (ISO 1580).
- Each 3840×2200 16-bit DNG is ≈ 16.9 MB.
- Auto exposure and auto white balance cannot run in the 16-bit modes (ISP statistics are invalid at 16-bit). Set exposure manually.
- Highlights near the HG→LG hand-off can render magenta in flat greys. This is sensor-side merge behaviour, not a capture defect.
- Occasionally a launch can record a flat black-level pedestal instead of real image data, on any ClearHDR mode — CineMate's shipped `blend` default avoids the sensor condition that causes it. See [Flat black-pedestal frames](#flat-black-pedestal-frames) if you still hit it.

## Flat black-pedestal frames

Occasionally a ClearHDR launch produces a black image. This seems to be a driver-side merge condition and underexposing the sensor briefly seems to "kick" it back into operation, either by covering the sensor with the lens cap or by briefly setting shutter angle to 1°.

## Default knob values

`image_capture.hdr` also carries the startup values for the four live knobs below — CineMate seeds them into Redis at launch, and cinepi-raw applies them whenever a ClearHDR mode is selected:

```jsonc
"hdr": {
  "sdr": true,
  "imx585_clear_hdr": true,
  "threshold_low": null,
  "threshold_high": null,
  "blend": 5,
  "gain_adder": 1,
  "self_heal": false
}
```

## Live knobs

The merge behaviour is tunable while streaming. Each command writes a Redis key that cinepi-raw applies to the sensor as a V4L2 control.

| CLI command                   | Redis key            | Range  | What it does                                                                                                                           | Visual impact                                                                                                                        |
| ----------------------------- | -------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `set hdr threshold low 500`   | `hdr_threshold_low`  | 0–4095 | raw level below which the sensor reads pure HG                                                                                         | lower = earlier hand-off, more highlight headroom, noisier mids; higher = more range stays clean HG                                  |
| `set hdr threshold high 3000` | `hdr_threshold_high` | 0–4095 | raw level above which the sensor reads pure LG                                                                                         | lower = highlight detail kicks in sooner; higher = highlights closer to the plateau before LG takes over                             |
| `set hdr blend 2`             | `hdr_blend`          | 0–8    | HG:LG mix inside the transition zone (0 = HG 1/2 + LG 1/2, per the driver menu)                                                        | HG-heavy = cleaner transition tones; LG-heavy = highlight detail holds longer through the zone, more grain there                     |
| `set hdr gain adder 2`        | `hdr_gain_adder`     | 0–5    | digital gain on the low-gain path in the merge (2 = +12 dB, the driver default); shifts where the blend knee lands in the output range | lower = highlights darker, flatter, cleaner — lift in the grade; higher = brighter highlight rendering, more grain in the highlights |

### Symptom → knob

| You see                                     | Try                                                                                                                                                       |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Magenta in bright flat areas                | try `set hdr threshold low 500`, `set hdr threshold high 3000`, `set hdr blend 2`, `set hdr gain adder 2` |
| Grainy mids or faces                        | higher thresholds, HG-heavier blend (3, 4), or a lower gain adder                                                                                         |
| A band or step where tones change character | widen the gap between the two threshold values                                                                                                            |
| Highlights too dark and flat out of camera  | higher gain adder — costs highlight grain                                                                                                                 |
| Grainy highlights                           | lower gain adder; lift in the grade instead                                                                                                               |
| Flat black-level pedestal, no image data    | manual shutter kick — `set shutter a 1` then back — see [Flat black-pedestal frames](#flat-black-pedestal-frames)                                         |

## Mono sensor (imx585_mono)

Verified working 2026-08-27 — all ClearHDR modes record real data on the mono
variant. Three mono-specific facts:

| Fact                             | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Kernel patch required for 16-bit | The stock rpi-6.12.y kernel gives every Bayer 16-bit format the "RP1 HW mismatch" workaround (`csi_dt = 0`) but missed the mono `Y16` entry. Unpatched, mono 16-bit records PiSP-COMP1-structured garbage (stripes on flat scenes, noise on detailed ones). The installer applies `scripts/patch-rp1-cfe.sh` automatically for `SENSOR_MODEL=imx585_mono`; rerun it after any kernel package upgrade (the upgrade silently restores the stock module). |
| 16-bit frames are 3840×2200      | The sensor prepends ~20 optical-black rows to its RAW16 output; the top rows of every 16-bit DNG sit at the 3200 pedestal. Expected geometry, not a defect.                                                                                                                                                                                                                                                                                            |
| No binned ClearHDR               | Binned (2K) ClearHDR is an invalid sensor configuration on mono — the sensor emits pure black-level regardless of exposure (AppNote §2 p.6). The `cinemate-7modes` driver removes the combination from the mode table; only full-res 12-bit CCMP and 16-bit ClearHDR are offered.                                                                                                                                                                      |
