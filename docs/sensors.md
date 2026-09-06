# Camera sensors and frame rates

## Compatible sensors

Higher frame rates need fast storage. If you see a purple/magenta `DROP` indicator while recording, lower the FPS or switch to faster media.

### IMX477 (Raspberry Pi HQ Camera)

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|--------------------------|
| 0    | 2028 x 1080      | 1.87         | 12        | 50      | 3.29                     |
| 1    | 2028 x 1520      | 1.33         | 12        | 40      | 4.62                     |
| 2    | 1332 x 990       | 1.34         | 10        | 120     | 1.65                     |

### IMX296 (Raspberry Pi Global Shutter Camera)

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|--------------------------|
| 0    | 1456 x 1088      | 1.33         | 10        | 60      | 1.98                     |

### IMX585 (Starlight Eye)

The `cinemate-7modes` driver the installer ships exposes seven modes: three SDR and four ClearHDR,
at 10-, 12- and 16-bit.

| Mode | Type | Resolution | Bit Depth | Readout | Max FPS | Max FPS overclocked | DNG Frame File Size (MB) |
|---|---|---|---|---|---|---|---|
| 0 | SDR | 3840 x 2160 | 10 | all-pixel | 44.98 | 68.66 | 10.4 |
| 1 | SDR | 1920 x 1080 | 12 | binned | 69.92 | 69.92 | 3.15 |
| 2 | SDR | 3840 x 2160 | 12 | all-pixel | 43.98 | 67.13 | 12.61 |
| 3 | ClearHDR | 1920 x 1080 | 12 | binned | 30.00 | 30.00 | 3.15 |
| 4 | ClearHDR | 3840 x 2160 | 12 | all-pixel | 21.99 | 30.00 | 12.61 |
| 5 | ClearHDR | 1920 x 1100 | 16 | binned | 30.00 | 30.00 | 4.2 |
| 6 | ClearHDR | 3840 x 2200 | 16 | all-pixel | 21.99 | 30.00 | 16.9 |

Both fps columns are the [changelog](changelog.md#imx585-driver)'s measured figures for 3.4.0, taken
at the sensor's highest link frequency, 1039.5 MHz. "Max FPS" is the stock RP1 pixel-rate ceiling
(`--max-pixel-rate 380`); "overclocked" is the same mode with the `rp1-overclock` overlay's 580. Both
move with the link frequency, which is set per port on the [config.txt tab](config-txt.md). See
[Overclocking the Pi](overclocking.md) for the overlay, and [ClearHDR](clear-hdr.md) for what the HDR
modes do and how to tune the merge.

!!! note "Mode numbers are not fixed sensor properties"

    CineMate filters the sensor's modes by the crop-factor, bit-depth and ClearHDR whitelists in
    [`settings.jsonc`](settings-json.md#image_capture), then numbers whatever survives. The table
    above is the stock whitelist. Narrow any of those lists and the modes renumber, so `set
    resolution 3` will not mean the same thing on a camera with a different `bit_depths` or
    `k_steps`. The same applies to every mode table on this page.

Resolutions here are the active area. `resources/sensors.json` and the GUI quote the readout size for
the 12-bit modes, which is slightly larger — 1928 x 1090 and 3856 x 2180 — because it includes the
optical-black rows.

### IMX283 (OneInchEye)

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|--------------------------|
| 0    | 2736 x 1824      | 1.50         | 12        | 36      | 7.1                      |
| 1    | 2736 x 1538      | 1.78         | 12        | 41      | 6.0                      |
| 2    | 3840 x 2160      | 1.78         | 10        | 44      | 9.9                      |

!!! info "Raspberry Pi 4 raw packing"

    CineMate handles the CinePi-RAW packing choice automatically. On Raspberry Pi 4 / Pi 400 / CM4, IMX296 and IMX477 use packed raw mode (`P`). On Raspberry Pi 5 / CM5 they stay on unpacked mode (`U`). For IMX296 this means `1456:1088:10:P` on Raspberry Pi 4-family boards and `1456:1088:10:U` on Raspberry Pi 5 / CM5.
## CineMate Log support

[CineMate Log](cinemate-log.md) is supported on **IMX585 and IMX283 only**. Support is decided by the sensor's black level, not chosen: the two shipped log DNG specs (12→10 and 16→10/16→12) are built for BlackLevel 3200, which is exactly what IMX585 and IMX283 report and no other sensor does.

| Sensor                     | Live mode                       | `set log` (default) | `set log 10` / `set log 12`   |
| -------------------------- | ------------------------------- | ------------------- | ----------------------------- |
| IMX585                     | ClearHDR 16-bit                 | on → **LOG12**      | 10 or 12, either works        |
| IMX585                     | 12-bit (SDR or 12-bit ClearHDR) | on → **LOG10**      | only 10 works — no 12→12 spec |
| IMX283                     | 12-bit modes                    | on → **LOG10**      | only 10 works                 |
| IMX283                     | 10-bit modes                    | not supported       | — no 10-bit source spec       |
| IMX477, IMX296, all others | any                             | not supported       | — black level doesn't match   |

IMX477 is not a hardware limitation — its 12-bit modes would work the same way — it needs sensor-aware spec selection on the `cinepi-raw` side that hasn't been built yet.

## CSI-2 link frequency

How fast the sensor pushes pixels down the MIPI lanes, and so what frame rate a mode can reach.
Where it is selectable, CineMate offers it per port on the settings editor's
[config.txt tab](config-txt.md). `resources/sensors.json` is the source of truth for the values.

| Sensor | Lanes | Default | Selectable |
| --- | --- | --- | --- |
| IMX585 | 4 | 720 MHz | yes — 297 / 360 / 445.5 / 594 / 720 / 891 / 1039.5 MHz |
| IMX283 | 4 | 720 MHz | yes — 360 or 720 MHz, where 720 is also the ceiling |
| IMX477 | 2 | 450 MHz | not yet |
| IMX296 | 1 | 594 MHz | no |
| IMX519 | 2 | 408 MHz | no |

How far a raise pays off depends on the mode: the wide all-pixel modes hit the RP1's pixel-rate
bound before the link bound, so on a Pi 5 they also need the receiver overclocked — see
[Overclocking the Pi](overclocking.md).

??? note "Why the other sensors are fixed"
    **IMX283** — Sony ships register sequences for only these two values, and 720 MHz is both the
    default and the silicon ceiling, so the alternative is slower. Selecting it needs the
    `link-frequency` overlay parameter added in `Tiramisioux/imx283-v4l2-driver` `6.12.y` at
    `257c9cf`.

    **IMX477** — not a hardware limit. The driver accepts any exact multiple of 3 MHz and
    Raspberry Pi's own testing found ~909 MHz stable, but no upper bound is vouched for, so
    CineMate keeps the menu hidden until the values are verified on this stack.

    **IMX296** — its 60 fps cap is readout-limited, not link-limited. A faster link buys nothing.

    **IMX585** — 1188 MHz exists in the driver and is deliberately not offered: frame drops on
    Pi 5, unsupported on Pi 4.

## Sensor size, crop factor and film-format equivalents

Each mode reads out a physical area of the sensor. Binned modes keep the full field of view. Cropped modes use a smaller area, so the same lens frames tighter.

| Sensor | Mode | Active area (mm) | Diagonal (mm) | Crop factor* | Closest film format |
|--------|------|------------------|---------------|--------------|---------------------|
| IMX283 | 2736 x 1824 (2.7K 3:2, binned) | 13.13 x 8.76 | 15.8 | 2.7 | Super 16, slightly larger (3:2) |
| IMX283 | 2736 x 1538 (2.7K 16:9, binned) | 13.13 x 7.38 | 15.1 | 2.9 | Super 16 (16:9) |
| IMX283 | 3840 x 2160 (4K UHD, native crop) | 9.22 x 5.18 | 10.6 | 4.1 | Between Super 8 and 16mm (~2/3-inch broadcast) |
| IMX283 | 5472 x 3648 (5K 3:2, hidden) | 13.13 x 8.76 | 15.8 | 2.7 | Super 16, slightly larger (3:2) |
| IMX283 | 5472 x 3078 (5K 16:9, hidden) | 13.13 x 7.39 | 15.1 | 2.9 | Super 16 (16:9) |
| IMX585 | 3856 x 2180 (4K) | 11.18 x 6.32 | 12.8 | 3.4 | 16mm (16:9) |
| IMX585 | 1928 x 1090 (2K, binned) | 11.18 x 6.32 | 12.8 | 3.4 | 16mm (16:9) |
| IMX477 | 2028 x 1080 (binned) | 6.29 x 3.35 | 7.1 | 6.1 | Super 8 (16:9) |
| IMX477 | 2028 x 1520 (binned) | 6.29 x 4.71 | 7.9 | 5.5 | Super 8, slightly larger (4:3) |
| IMX477 | 1332 x 990 (crop) | 4.13 x 3.07 | 5.1 | 8.4 | Standard 8mm, slightly smaller |
| IMX296 | 1456 x 1088 | 5.02 x 3.75 | 6.3 | 6.9 | Standard 8mm, slightly larger |

*Crop factor = 43.3 mm / mode diagonal, relative to 35 mm full-frame stills. Multiply the lens focal length by it for the full-frame-equivalent focal length. For depth-of-field equivalence, multiply the f-stop by the same factor.

### Focal-length examples:

- 25 mm on IMX283 2.7K 16:9 ~ 72 mm full-frame look
- 25 mm on IMX585 ~ 84 mm; 12.5 mm ~ 42 mm
- 12 mm on IMX477 (2028 x 1080) ~ 73 mm
- 8 mm on IMX296 ~ 55 mm

## Dynamic resolution

CineMate remembers the mode you selected as the *desired* mode. If you raise FPS above what that mode's own sensor-reported maximum can sustain, it switches to the highest-resolution mode that can, and returns to your desired mode once you dial back down. There is no separate performance table -- the ceiling always comes from the sensor's own reported numbers (the "Max FPS" columns above, the same values `cinepi-raw --list-cameras` reports).

**Resolution is the only thing it changes.** Substitution is confined to the desired mode's own family, where a family is one bit depth and one SDR/ClearHDR class -- the three blocks the imx585 mode table is laid out in. A 12-bit request never lands on a 10-bit mode, and a ClearHDR request never lands on an SDR one, however well those would serve the frame rate: those are trades you make deliberately, not ones a frame-rate dial makes for you. If nothing in the family can sustain the requested FPS, the resolution holds and FPS is capped instead.

Changing mode mid-take is allowed. cinepi-raw splits the recording around the camera reconfigure, so the take continues in a new clip folder and the clip list shows where the change happened. There is a short gap in frames across the split: the sensor has to be reprogrammed for the new mode, which means stopping and restarting the stream. cinepi-raw itself is *not* restarted.

### Turning it off

| Where | What it does |
| --- | --- |
| `image_capture.dynamic_resolution` in `settings.jsonc` | The startup default. `true` out of the box. |
| `set dynamic resolution 0` / `1` (or the settings page switch) | Overrides it for the session, and persists -- the next boot reads this back in preference to the file. |

With it off, the mode you select is the mode you get, and `fps_max` is that one mode's own limit rather than the best any mode in its family could do. Turning it off also adopts whatever mode is currently on screen as your selection, so turning it back on later does not jump you somewhere you have since moved away from.

Storage pre-roll is intentionally different: it uses the live sensor maximum for the currently selected mode and temporarily suspends dynamic resolution so the mounted media is stress-tested before CineMate restores the user's FPS and applies the dynamic-resolution choice.

The resolution readout turns green -- in the HDMI overlay and the web GUI alike -- whenever the mode on screen is one dynamic resolution chose rather than one you did. It stays white when the active mode is your desired resolution.

Actual achievable FPS without dropped frames depends on your storage device and filesystem, which the sensor's own reported numbers don't account for -- a purple `DROP` indicator means you're above what your setup can sustain. Test your own setup and pick FPS values accordingly.
