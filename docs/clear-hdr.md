# ClearHDR (imx585)

ClearHDR is the imx585's on-sensor single-frame HDR.

- Frame rates are lower than the plain modes. Per-mode figures are on the [sensors page].

- CineMate caps ClearHDR ISO, at a different value per depth — **799** in 12-bit and **1585** in
  16-bit. See [ISO is capped, and not at the same place](#iso-is-capped-and-not-at-the-same-place).

- Auto exposure and auto white balance cannot run in the 16-bit modes (ISP statistics are invalid at 16-bit). Set exposure manually.

## Live knobs

The Clear HDR merge behaviour is tunable while streaming. Each command writes a Redis key that cinepi-raw applies to the sensor as a V4L2 control.

| CLI command                   | Redis key            | Range  | What it does                                                                                                                           | Visual impact                                                                                                                        |
| ----------------------------- | -------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `set hdr threshold low 500`   | `hdr_threshold_low`  | 0–4095 | raw level below which the sensor reads pure HG                                                                                         | lower = earlier hand-off, more highlight headroom, noisier mids; higher = more range stays clean HG                                  |
| `set hdr threshold high 3000` | `hdr_threshold_high` | 0–4095 | raw level above which the sensor reads pure LG                                                                                         | lower = highlight detail kicks in sooner; higher = highlights closer to the plateau before LG takes over                             |
| `set hdr blend 2`             | `hdr_blend`          | 0–8    | HG:LG mix inside the transition zone (0 = HG 1/2 + LG 1/2, per the driver menu)                                                        | HG-heavy = cleaner transition tones; LG-heavy = highlight detail holds longer through the zone, more grain there                     |
| `set hdr gain adder 2`        | `hdr_gain_adder`     | 0–5    | digital gain on the low-gain path in the merge (2 = +12 dB, the driver default); shifts where the blend knee lands in the output range | lower = highlights darker, flatter, cleaner — lift in the grade; higher = brighter highlight rendering, more grain in the highlights |

## Known issues

### Flat black-pedestal frames

A ClearHDR launch can come up with a flat black frame instead exposed image. For the time being, the solution I have found to work is to briefly underexpose the sensor to "kick" it back to normal operation. This can be done by quickly covering the lens with your hand/lens cap or `set shutter a 1` and then back.