# ClearHDR (imx585)

ClearHDR is the imx585's on-sensor single-frame HDR. The sensor merges a high-gain (HG) and a low-gain (LG) readout internally and outputs one 16-bit linear Bayer frame. CineMate records it as true 16-bit CinemaDNGs — BlackLevel 3200, WhiteLevel 65535.

- Frame rates are lower than the plain modes. Per-mode figures are on the [sensors page](sensors.md#imx585-starlight-eye), measured at 1039.5 MHz with the stock and overclocked pixel-rate ceilings side by side; the [changelog](changelog.md#imx585-driver) is where those measurements were first recorded.
- Analogue gain caps at code 80 ≈ 15.8× (ISO 1580), which is why CineMate caps ClearHDR ISO — see
  [ISO is capped at 1585](#iso-is-capped-at-1585).
- Each 3840×2200 16-bit DNG is ≈ 16.9 MB.
- Auto exposure and auto white balance cannot run in the 16-bit modes (ISP statistics are invalid at 16-bit). Set exposure manually.
- Highlights near the HG→LG hand-off can render magenta in flat greys. This is sensor-side merge
  behaviour, not a capture defect: where the merge clamps, the colour channels converge on one
  code and the white balance then drives them apart.
- A launch can record a flat black-level pedestal instead of real image data, on any ClearHDR mode. CineMate's shipped `blend` default of 5 avoids the sensor condition that causes it, so a stock camera does not hit this. See [Flat black-pedestal frames](#flat-black-pedestal-frames) if you have overridden `blend`.

## ISO is capped at 1585

In a ClearHDR mode CineMate stops offering ISO above **1585**. SDR modes are never capped.

**Why.** The driver caps analogue gain in ClearHDR at code 80 (`IMX585_ANA_GAIN_MAX_HDR`), and
CineMate's ISO steps reach that code at about ISO 1585. Measured on the camera, reading the
driver's own `ANALOG_GAIN` log lines in 16-bit ClearHDR:

| ISO | 800 | 1600 | 2500 | 3200 |
|---|---|---|---|---|
| analogue gain code | 60 | 80 | 80 | 80 |

So 1600, 2500 and 3200 **record the same exposure**. What changes above the cap is only the
preview: libcamera's AGC makes up the shortfall as ISP digital gain on the display path, so the
monitor brightens while the DNG does not. Judging exposure off that monitor would have you
believe in light the file never received, which is worse than a control that simply stops.

**What you see.** The 1600 step stays selectable and lands on 1585, with ISO shown **green** in
both the HDMI overlay and the web GUI — the same tint they already use for a shutter angle that
sync mode is driving, meaning "the camera is holding this, not you". 2500 and 3200 are dropped.

**Lifting it.** `image_capture.hdr.iso_max` takes any ISO, or `null` to remove the cap. Nothing
stops you shooting at 3200; you simply get the 1585 recording with a brighter preview.

## Live knobs

The merge behaviour is tunable while streaming. Each command writes a Redis key that cinepi-raw applies to the sensor as a V4L2 control.

| CLI command                   | Redis key            | Range  | What it does                                                                                                                           | Visual impact                                                                                                                        |
| ----------------------------- | -------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `set hdr threshold low 500`   | `hdr_threshold_low`  | 0–4095 | raw level below which the sensor reads pure HG                                                                                         | lower = earlier hand-off, more highlight headroom, noisier mids; higher = more range stays clean HG                                  |
| `set hdr threshold high 3000` | `hdr_threshold_high` | 0–4095 | raw level above which the sensor reads pure LG                                                                                         | lower = highlight detail kicks in sooner; higher = highlights closer to the plateau before LG takes over                             |
| `set hdr blend 2`             | `hdr_blend`          | 0–8    | HG:LG mix inside the transition zone (0 = HG 1/2 + LG 1/2, per the driver menu)                                                        | HG-heavy = cleaner transition tones; LG-heavy = highlight detail holds longer through the zone, more grain there                     |
| `set hdr gain adder 2`        | `hdr_gain_adder`     | 0–5    | digital gain on the low-gain path in the merge (2 = +12 dB, the driver default); shifts where the blend knee lands in the output range | lower = highlights darker, flatter, cleaner — lift in the grade; higher = brighter highlight rendering, more grain in the highlights |

### Default knob values

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

## Known issues

### Flat black-pedestal frames

A ClearHDR launch can come up with a flat black frame instead exposed image. For the time being, the solution I have found to work is to briefly underexpose the sensor to "kick" it back to normal operation. This can be done by quickly covering the lens with your hand/lens cap or `set shutter a 1` and then back.