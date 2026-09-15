# ClearHDR (imx585)

ClearHDR is the imx585's on-sensor single-frame HDR. The sensor merges a high-gain (HG) and a low-gain (LG) readout internally and outputs one 16-bit linear Bayer frame. CineMate records it as true 16-bit CinemaDNGs — BlackLevel 3200, WhiteLevel 65535.

- Frame rates are lower than the plain modes. Per-mode figures are on the [sensors page](sensors.md#imx585-starlight-eye), measured at 1039.5 MHz with the stock and overclocked pixel-rate ceilings side by side; the [changelog](changelog.md#imx585-driver) is where those measurements were first recorded.
- CineMate caps ClearHDR ISO, at a different value per depth — **799** in 12-bit, **1585** in
  16-bit. See [ISO is capped, and not at the same place](#iso-is-capped-and-not-at-the-same-place).
- Each 3840×2200 16-bit DNG is ≈ 16.9 MB.
- Auto exposure and auto white balance cannot run in the 16-bit modes (ISP statistics are invalid at 16-bit). Set exposure manually.
- Highlights near the HG→LG hand-off can render magenta in flat greys. This is sensor-side merge
  behaviour, not a capture defect: where the merge clamps, the colour channels converge on one
  code and the white balance then drives them apart.
- A launch can record a flat black-level pedestal instead of real image data, on any ClearHDR mode. CineMate's shipped `blend` default of 5 avoids the sensor condition that causes it, so a stock camera does not hit this. See [Flat black-pedestal frames](#flat-black-pedestal-frames) if you have overridden `blend`.

## Which ClearHDR modes you are offered

Two switches, one per capture, in the settings editor's **Resolution & sensor** section
(`image_capture.hdr` in [settings.jsonc](settings-json.md#resolution--sensor)):

| Switch | Key | Default | Capture |
|---|---|---|---|
| Enable IMX585 ClearHDR 16-bit | `imx585_clear_hdr_16bit` | on | Linear, no compander in the path |
| Enable IMX585 ClearHDR 12-bit | `imx585_clear_hdr_12bit` | off | Companded on-sensor (CCMP); cinepi-raw decompands |

They decide **which captures exist**, not which frame sizes. **Resolutions offered**
(`image_capture.k_steps`) does that, for ClearHDR exactly as it does for SDR — so with `2` and
`4` both on, 16-bit ClearHDR gives you HD (1920×1100, binned) and 4K (3840×2200); turn `2` off
and you are offered 4K only.

Turning either switch on or off **renumbers** the modes that remain. That is safe: a
`sensor_mode` saved in Redis is re-resolved by what the capture actually was, not by its index,
so the camera does not wake up in a different mode.

12-bit ClearHDR is off by default because on this sensor it does not earn its place: the HG/LG
merge stops reaching the top of the container above analogue gain code ~60 (about ISO 800), so
highlight range collapses at the ISOs people actually shoot, while 16-bit ClearHDR holds across
the whole range. The 12-bit modes also carry the compander and a full-frame CPU preview
re-render. Every line of code that serves them is still here — turn the switch on to get them
back.

!!! note "Pink highlights: fixed in the DNG, still present in the preview"

    Where the merge clamps, the colour channels converge on one code well below the container's
    top. With WhiteLevel declared at the container's full scale, no converter saw a clipped
    pixel, white balance drove red and blue past white while green stayed short, and the
    highlight rendered magenta — in the **recorded DNG**, not only the preview.

    **The DNG is now correct.** cinepi-raw measures where the data actually stops on each take's
    first frame and writes that as WhiteLevel, so blown highlights render neutral white.
    Confirmed on hardware 2026-09-15 in all four ClearHDR modes; see
    `cinemate-handbook/lessons/hardware-log.md`.

    **The HDMI/web preview and the embedded DNG thumbnail still render pink.** They are a
    separate path that does not read the tag, and CineMate ships without the preview-side
    correction. The effect is strongest in the binned (HD) modes, whose clamp sits lowest —
    54.8% of the container against 83-89% at full res.

## ISO is capped, and not at the same place

In a ClearHDR mode CineMate stops offering ISO above a ceiling that depends on the **sensor's**
bit depth, not on the depth the file is stored at:

| ClearHDR mode | cap | what stops |
|---|---|---|
| **12-bit** (CCMP) | **799** | the sensor stops *combining* — the mode stops being HDR |
| **16-bit** | **1585** | the sensor stops *amplifying* — the recording stops getting brighter |

SDR modes are never capped, at either depth.

**Why 1585 in 16-bit.** The driver caps analogue gain in ClearHDR at code 80
(`IMX585_ANA_GAIN_MAX_HDR`), and CineMate's ISO steps reach that code at about ISO 1585.
Measured on the camera, reading the driver's own `ANALOG_GAIN` log lines:

| ISO | 800 | 1600 | 2500 | 3200 |
|---|---|---|---|---|
| analogue gain code | 60 | 80 | 80 | 80 |

So 1600, 2500 and 3200 **record the same exposure**. What changes above the cap is only the
preview: libcamera's AGC makes up the shortfall as ISP digital gain on the display path, so the
monitor brightens while the DNG does not. Judging exposure off that monitor would have you
believe in light the file never received, which is worse than a control that simply stops.

**Why 799 in 12-bit — a full stop lower, and a different failure.** The sensor only performs
built-in combination while `9.6dB ≤ GAIN + EXP_GAIN ≤ 29.1dB` (`imx585.c` line 167). ClearHDR's
default `EXP_GAIN` is +12 dB, which caps analogue gain at 17.1 dB — code 57:

| ISO | 640 | 700 | 799 | 800 | 900 | 1000 |
|---|---|---|---|---|---|---|
| analogue gain code | 51 | 56 | 56 | **60** | 63 | 66 |

ISO 799 is the last step inside the window; 800 is the first outside it. Past it the HG/LG merge
collapses — the measured ceiling falls to 3188 of 4095 at gain code 71 and 2408 at code 80 — so
12-bit ClearHDR hands back **less** highlight range than the SDR mode would have, while still
paying the compander and the full-frame CPU preview re-render for it. Lowering `EXP_GAIN` to stay
inside the window does not rescue it: that removes the HG/LG ratio, and with no ratio there is
nothing to merge (adder 0 at gain code 80 measures a ceiling of 1452 — worse again).

**What you see.** The first step above the cap stays selectable and lands *on* the cap — 800 →
799 in 12-bit, 1600 → 1585 in 16-bit — with ISO shown **green** in both the HDMI overlay and the
web GUI, the same tint they already use for a shutter angle that sync mode is driving, meaning
"the camera is holding this, not you". Steps beyond that one are dropped. Keeping the first one
matters: withholding every step above the cap would strand 12-bit at ISO 640 and throw away a
third of a stop the sensor really does deliver, since 700 and 799 both sit on code 56.

**Lifting it.** `image_capture.hdr.iso_max` takes any ISO, or `null` to remove the cap. It stays
a single override for both depths: an operator who writes a ceiling gets that ceiling, whichever
mode is engaged, rather than the camera quietly substituting a number they never wrote.

**ISO is also held for the length of a take.** In a ClearHDR mode CineMate ignores ISO changes
while recording, in both directions, and says so in the log. cinepi-raw measures where the merge
clamps on the take's *first* frame and writes it as the DNG's WhiteLevel, constant for the whole
take — it has to be constant, or the exposure would step mid-clip.

The clamp moves with analogue gain, and the direction catches people out: **more gain gives a
lower ceiling** (measured at full res, gain code 71 → 54100, code 80 → 48600). So raising ISO
mid-take merely drops the clamp below the declared white and the highlight goes magenta again —
the old behaviour, unpleasant but not destructive. *Lowering* ISO raises the real clamp **above**
the WhiteLevel already written, and every converter then crushes that entire band of genuine
sensor data to flat white. That one is unrecoverable, which is why the control is held both ways
rather than in the direction that looks dangerous.

Stop recording to change ISO. SDR is unaffected — nothing there latches a measured WhiteLevel.

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
  "imx585_clear_hdr_12bit": false,
  "imx585_clear_hdr_16bit": true,
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