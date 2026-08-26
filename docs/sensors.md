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

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|--------------------------|
| 0    | 1928 x 1090      | 1.77         | 12        | 87      | 3.15                     |
| 1    | 3856 x 2180      | 1.77         | 12        | 40      | 12.61                    |

### IMX283 (OneInchEye)

| Mode | Resolution       | Aspect Ratio | Bit Depth | Max FPS | DNG Frame File Size (MB) |
|------|------------------|--------------|-----------|---------|--------------------------|
| 0    | 2736 x 1824      | 1.50         | 12        | 36      | 7.1                      |
| 1    | 2736 x 1538      | 1.78         | 12        | 41      | 6.0                      |
| 2    | 3840 x 2160      | 1.78         | 10        | 44      | 9.9                      |

!!! info ""

    Only IMX283 modes that sustain **25 fps or more** are exposed by default. To bring them back, add `5.5` to `k_steps`.

Max FPS is the sensor's own reported ceiling for each mode (the same value `cinepi-raw --list-cameras` reports). Actual achievable FPS without dropped frames also depends on your storage device and filesystem -- make test recordings on your own setup and monitor the output. Purple background in the monitor/web browser indicates drop frames.

!!! note ""

    The bit-depth column above describes the sensor mode reported by the camera stack. The IMX296 sensor mode is 10 bit. Cinemate's CinePi-RAW DNG writer may still save captures through its 12 bit DNG output path, so a correctly saved IMX296 DNG does not mean the sensor itself has a 12 bit mode.

!!! info "Raspberry Pi 4 raw packing"

    Cinemate handles the CinePi-RAW packing choice automatically. On Raspberry Pi 4 / Pi 400 / CM4, IMX296 and IMX477 use packed raw mode (`P`). On Raspberry Pi 5 / CM5 they stay on unpacked mode (`U`). For IMX296 this means `1456:1088:10:P` on Raspberry Pi 4-family boards and `1456:1088:10:U` on Raspberry Pi 5 / CM5.

## Frame size and recording time

DNG frame size is calculated dynamically, not read from a fixed table: `ceil(width × effective_bit_depth / 8) × height`, plus a small fixed per-frame header overhead. *Effective bit depth* is the sensor mode's native bit depth, or the live [`--log-encode`](cinemate-log.md) target (10 or 12) when CineMate Log is on -- so the same mode gets smaller on disk once log encoding is enabled. `resources/sensors.json` no longer carries a static file-size number; Cinemate always computes it from the mode's resolution and the live log state (`module/sensor_detect.py`'s `compute_frame_size_mb()`).

Recording time assumes a 1 TB drive (1,000,000 MB decimal, matching Cinemate's own free-space math) recording continuously at 25 fps, with no other files on the drive. Actual time left depends on your drive's free space and the FPS you're recording at -- see the `disk_space` readout in the GUI for the live estimate on your setup.

| Sensor | Mode | Resolution | Native bit depth | CineMate Log | Frame size (MB) | Time on 1 TB @ 25 fps |
|--------|------|------------|-------------------|--------------|------------------|------------------------|
| IMX477 | 0 | 2028 x 1080 | 12 | not supported | 3.29 | 3h 23m |
| IMX477 | 1 | 2028 x 1520 | 12 | not supported | 4.62 | 2h 24m |
| IMX477 | 2 | 1332 x 990 | 10 | not supported | 1.65 | 6h 44m |
| IMX296 | 0 | 1456 x 1088 | 10 | not supported | 1.98 | 5h 37m |
| IMX585 | 0 | 1928 x 1090 | 12 | off | 3.15 | 3h 32m |
| IMX585 | 0 | 1928 x 1090 | 12 | on (→10) | 2.63 | 4h 13m |
| IMX585 | 1 | 3856 x 2180 | 12 | off | 12.61 | 53m |
| IMX585 | 1 | 3856 x 2180 | 12 | on (→10) | 10.51 | 1h 03m |
| IMX585 | 1, ClearHDR | 3856 x 2180 | 16 | off | 16.81 | 40m |
| IMX585 | 1, ClearHDR | 3856 x 2180 | 16 | on, default (→12) | 12.61 | 53m |
| IMX585 | 1, ClearHDR | 3856 x 2180 | 16 | on, forced (→10) | 10.51 | 1h 03m |
| IMX585 | 1, ClearHDR + 12-bit (CCMP12) | 3856 x 2180 | 12 | on (→10 only)* | 10.51 | 1h 03m |
| IMX283 | 0 | 5568 x 3664 | 12 | off | 30.60 | 22m |
| IMX283 | 0 | 5568 x 3664 | 12 | on (→10) | 25.50 | 26m |
| IMX283 | 1 | 2784 x 1828 | 12 | off | 7.63 | 1h 27m |
| IMX283 | 1 | 2784 x 1828 | 12 | on (→10) | 6.36 | 1h 45m |
| IMX283 | 2 | 2784 x 1542 | 12 | off | 6.44 | 1h 44m |
| IMX283 | 2 | 2784 x 1542 | 12 | on (→10) | 5.37 | 2h 04m |
| IMX283 | 3 | 5568 x 3664 | 10 | not supported (10-bit mode) | 25.50 | 26m |
| IMX283 | 4 | 5568 x 3094 | 10 | not supported (10-bit mode) | 21.54 | 31m |
| IMX283 | 5 | 3936 x 2176 | 10 | not supported (10-bit mode) | 10.71 | 1h 02m |

*12-bit ClearHDR is CCMP-companded on-sensor, so it cannot take a linear 12→10 curve. `set log` still works: cinepi-raw decompands to 16-bit linear first, then applies the 16→10 curve as one composed table. Only target 10 exists on this path — `set log 12` is refused. See [CineMate Log support](#cinemate-log-support) below.

The IMX283 rows in this table and in [Compatible sensors](#compatible-sensors) above come from different sources and have not been reconciled: the Compatible sensors table lists what the live driver reports (`cinepi-raw --list-cameras` on the Tiramisioux `6.12.y` fork), this table lists the entries in `resources/sensors.json`. Reconciling them needs a `--list-cameras` capture from the Pi.

## CineMate Log support

[CineMate Log](cinemate-log.md) is supported on **IMX585 and IMX283 only**. Support is decided by the sensor's black level, not chosen: the two shipped log DNG specs (12→10 and 16→10/16→12) are built for BlackLevel 3200, which is exactly what IMX585 and IMX283 report and no other sensor does.

| Sensor | Live mode | `set log` (default) | `set log 10` / `set log 12` |
|--------|-----------|----------------------|------------------------------|
| IMX585 | ClearHDR 16-bit | on → **LOG12** | 10 or 12, either works |
| IMX585 | 12-bit (SDR or 12-bit ClearHDR) | on → **LOG10** | only 10 works — no 12→12 spec |
| IMX283 | 12-bit modes | on → **LOG10** | only 10 works |
| IMX283 | 10-bit modes | not supported | — no 10-bit source spec |
| IMX477, IMX296, all others | any | not supported | — black level doesn't match |

IMX477 is not a hardware limitation — its 12-bit modes would work the same way — it needs sensor-aware spec selection on the `cinepi-raw` side that hasn't been built yet.

## CSI-2 link frequency

The link frequency sets how fast the sensor pushes pixels down the MIPI lanes,
and so what frame rate a mode can reach. Where it is selectable, Cinemate
offers it per port in the settings editor's Boot config pane — see
[Overclocking the Pi](overclocking.md), because on a Pi 5 the receiver has to
be overclocked before the higher rates buy anything.

`resources/sensors.json` is the source of truth for the values below.

| Sensor | Lanes | Default | Selectable | Values |
|--------|-------|---------|------------|--------|
| IMX585 | 4 | 720 MHz | **yes** | 297 / 360 / 445.5 / 594 / 720 / 891 / 1039.5 MHz |
| IMX283 | 4 | 720 MHz | **yes** | 360 / 720 MHz — 720 is also the ceiling |
| IMX477 | 2 | 450 MHz | not yet | driver computes any ~3 MHz multiple (kernel ≥ 6.12.49) |
| IMX296 | 1 | 594 MHz | no | fixed |
| IMX519 | 2 | 408 MHz | no | fixed |

**IMX585** carries per-value frame rates in
[Overclocking the Pi](overclocking.md#imx585). 1188 MHz exists in the driver
and is deliberately not offered: frame drops on Pi 5, unsupported on Pi 4.

**IMX283**'s two values are the only two Sony ships register sequences for.
720 MHz is both the default and the silicon ceiling, so the only selectable
alternative is slower. The 4K modes' 44/41 fps are the link ceiling at those
bit depths — more frame rate means a lower bit depth, not a faster link.
Selecting the non-default value needs the `link-frequency` overlay parameter
added in `Tiramisioux/imx283-v4l2-driver` `6.12.y` at `257c9cf`.

**IMX477** is not a hardware limitation. Its driver accepts any exact multiple
of 3 MHz and RPi's own testing found ~909 MHz stable, but it vouches for no
upper bound, so Cinemate keeps the menu hidden until the values are verified
on this stack.

**IMX296**'s 60 fps cap is readout-limited, not link-limited; a faster link
would buy nothing.

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

Cinemate always runs dynamic resolution: it remembers the mode you selected as the desired mode, and if you raise FPS above what that mode's own sensor-reported maximum can sustain, it switches to the highest-resolution mode that can. FPS returns to your desired mode once you dial back down. There is no setting for this and no separate performance table -- the ceiling always comes from the sensor's own reported numbers (the "Max FPS" columns above, the same values `cinepi-raw --list-cameras` reports).

Storage pre-roll is intentionally different: it uses the live sensor maximum for the currently selected mode and temporarily suspends dynamic resolution so the mounted media is stress-tested before Cinemate restores the user's FPS and applies the dynamic-resolution choice.

The active resolution numbers turn green in the simple GUI only while dynamic resolution is actively substituting a lower-resolution mode for the current FPS instead of your desired mode. They stay white when the active mode is your desired resolution.

Actual achievable FPS without dropped frames depends on your storage device and filesystem, which the sensor's own reported numbers don't account for -- a purple `DROP` indicator means you're above what your setup can sustain. Test your own setup and pick FPS values accordingly.
