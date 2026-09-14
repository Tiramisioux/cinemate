# ClearHDR (imx585)

ClearHDR is the imx585's on-sensor single-frame HDR. The sensor merges a high-gain (HG) and a low-gain (LG) readout internally and outputs one 16-bit linear Bayer frame. CineMate records it as true 16-bit CinemaDNGs — BlackLevel 3200, WhiteLevel 65535.

- Frame rates are lower than the plain modes. Per-mode figures are on the [sensors page](sensors.md#imx585-starlight-eye), measured at 1039.5 MHz with the stock and overclocked pixel-rate ceilings side by side; the [changelog](changelog.md#imx585-driver) is where those measurements were first recorded.
- Analogue gain caps at code 80 ≈ 15.8× (ISO 1580). **CineMate caps ClearHDR ISO at 1585 for this
  reason**: measured on the rig, ISO 1600, 2500 and 3200 all map to code 80 and record the *same*
  exposure — above the cap only the preview brightens, because libcamera's AGC makes up the
  difference as ISP digital gain, so the monitor shows light the file never received. The 1600 step
  is kept and lands on 1585, shown **green** in both GUIs to say the camera is holding it. Lift it
  with `image_capture.hdr.iso_max: null`.
- Each 3840×2200 16-bit DNG is ≈ 16.9 MB.
- Auto exposure and auto white balance cannot run in the 16-bit modes (ISP statistics are invalid at 16-bit). Set exposure manually.
- Highlights near the HG→LG hand-off can render magenta in flat greys. This is sensor-side merge
  behaviour, not a capture defect: where the merge clamps, the colour channels converge on one
  code and the white balance then drives them apart. It is worst when the merge is being asked
  to work outside its gain window — see [12-bit ClearHDR is hidden](#12-bit-clearhdr-is-hidden)
  for the measurements, which apply to the 16-bit modes at high ISO too.
- A launch can record a flat black-level pedestal instead of real image data, on any ClearHDR mode. CineMate's shipped `blend` default of 5 avoids the sensor condition that causes it, so a stock camera does not hit this. See [Flat black-pedestal frames](#flat-black-pedestal-frames) if you have overridden `blend`.

## 12-bit ClearHDR is hidden

The driver exposes ClearHDR at **two** depths. CineMate offers only the 16-bit pair; the two
12-bit ClearHDR modes are hidden by default (`image_capture.hdr.imx585_clear_hdr_12bit`, or
"Expose 12-bit ClearHDR modes" in the settings editor).

**Why.** ClearHDR's extra range is the ratio between the sensor's high-gain and low-gain reads,
and that ratio only survives inside the sensor's documented combination window. Measured on the
rig, 12-bit ClearHDR HD, everything else fixed, reading the merge ceiling off the raw:

| ISO | 200 | 400 | 640 | 799 | 800 | 1200 | 1600+ |
|---|---|---|---|---|---|---|---|
| analogue gain code | 20 | 40 | 51 | 56 | 60 | 71 | 80 |
| merge ceiling (of 4095) | 4095 | 4095 | 4095 | 4095 | — | 3188 | 2408 |

Past gain code ~60 the merge stops reaching the top of the container: at code 80 it reaches 59%
of it, about a stop and a half of highlight range gone — and that lost range is precisely what
ClearHDR is for. The 16-bit modes hold up across the ISO range, so on this camera the 12-bit
pair is the mode that asks for the compander, a full-frame CPU preview re-render and the clamp
artefacts that come with both, and returns less highlight range than SDR at the ISOs people
actually shoot.

**Nothing has been removed.** The driver still has the modes, cinepi-raw still has the CCMP
decompand, the measured per-binning tables and the preview path that serves them. This switch
only keeps them out of the mode list. Set `imx585_clear_hdr_12bit` to `true` to get them back
for tinkering.

**Turning it on (or off) renumbers the modes.** With 12-bit ClearHDR hidden the table is 0-4,
with the 16-bit ClearHDR pair at 3 and 4; with it shown they move to 5 and 6. A `sensor_mode`
saved in Redis is re-resolved at startup from the capture it actually described — the stored
width/height/bit depth/HDR state — rather than from its index, so a camera parked on 4K 16-bit
ClearHDR comes back in 4K 16-bit ClearHDR either way. A camera parked on a 12-bit ClearHDR mode
that has just been hidden lands on the same resolution in 16-bit ClearHDR, which is the nearest
honest thing to what it was recording.

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