# Lenses and image circles

!!! note ""
    A lens must draw an image circle at least as large as the sensor diagonal. The inch fraction on the lens (`1/2.7"`, `1"`) tells you the circle size. The megapixel number tells you sharpness — but only over that circle.

CCTV and machine-vision lenses are marked with a compact code. A typical label:

`3MP 2.8-12mm 1/2.7" F1.4 IR CS`

| Marking | Meaning |
| --- | --- |
| `1/2.7"` | Optical format. Image circle ≈ 6.7 mm across. |
| `3MP` | Resolving power: sharp enough for a 3-megapixel sensor of `1/2.7"` size. |
| `2.8-12mm` | Varifocal: focal length is adjustable, refocus after every change. |
| `F1.4` | Maximum aperture. |
| `IR` | IR-corrected: visible and infrared light focus on the same plane. |
| `CS` | CS-mount thread. |

## The inch fractions

The fraction is not the sensor diagonal. It is a 1950s TV-tube convention: a "1-inch" camera tube had a 25.4 mm glass envelope, but its usable image area was only about two thirds of that. Sensor makers kept the naming.

Rule of thumb: real image circle ≈ fraction × 16 mm.

| Lens marking | Image circle (mm) | Covers (Cinemate sensors) |
| --- | --- | --- |
| `1/3"` | 6.0 | none fully — marginal on IMX296 |
| `1/2.9"` | 6.2 | IMX296 (exact, no margin) |
| `1/2.7"` | 6.7 | IMX296 |
| `1/2.5"` | 7.2 | IMX296 |
| `1/2.3"` | 7.7 | IMX296 — marginal on IMX477 (7.9 mm) |
| `1/2"` | 8.0 | IMX296, IMX477 |
| `1/1.8"` | 8.9 | IMX296, IMX477 |
| `2/3"` | 11.0 | IMX296, IMX477 |
| `1/1.2"` | 12.8–13.3 | + IMX585 |
| `1"` | 15.9–16.0 | + IMX283 — all four sensors |
| `4/3"` | 21.6 | all four sensors |

What happens on a mismatch:

| Lens format vs sensor | Result |
| --- | --- |
| Smaller | Dark or black corners (vignetting). |
| Same | Full coverage. The lens maker's field-of-view figures apply. |
| Larger | Full coverage, tighter field of view. The sensor uses the sharp center of the circle. |

A larger-format lens is always safe. The picture is cropped, never degraded — corners are usually sharper than on the lens's native format. Multiply the focal length by the crop factor in [camera sensors and frame rates](sensors.md#sensor-size-crop-factor-and-film-format-equivalents) to see what you get.

!!! info ""
    The marked format is a nominal claim, not a guaranteed circle. Good datasheets state the image circle in mm (e.g. Kowa LM35HC: "Imager format 1 inch, image circle diameter 16 mm"). When the sensor sits between standard formats, compare millimetres, not fractions.

## Megapixel ratings

"3MP" and "5MP" ratings are marketing shorthand, not a standard. The real spec is resolving power in line pairs per millimetre (lp/mm). The rating means: sharp enough for that many pixels **spread over the lens's rated format**.

Two consequences:

- The same MP number on a smaller format demands a sharper lens.
- A high MP number does not fix a too-small image circle.

To resolve a pixel of a given size, a lens needs (Nyquist limit):

`required lp/mm = 1000 / (2 × pixel size in µm)`

| Pixel size | Lens must resolve |
| --- | --- |
| 5.0 µm | 100 lp/mm |
| 3.45 µm (IMX296) | 145 lp/mm |
| 2.9 µm (IMX585) | 172 lp/mm |
| 2.4 µm (IMX283) | 208 lp/mm |
| 1.55 µm (IMX477, unbinned) | 323 lp/mm |

To interpret an MP rating, convert it to the pixel size the lens was designed for: divide the rated format's area by the MP count.

| Lens label | Designed for pixels of about |
| --- | --- |
| `2MP 1/3"` | 2.9 µm |
| `3MP 1/2.7"` | 2.7 µm |
| `5MP 1/2.7"` | 2.1 µm |
| `5MP 1/1.8"` | 2.8 µm |
| `8MP (4K) 1/1.8"` | 2.2 µm |
| `10MP 2/3"` | 2.4 µm |
| `12MP 1.1"` | 3.5 µm |

If that number is equal to or smaller than your sensor's pixel size, the lens keeps up.

!!! info ""
    Many lenses are rated from the center of the image only. Corner resolution can be half the center figure. Machine-vision datasheets that state center and corner lp/mm (e.g. "200 lp/mm center, 160 corner") are the trustworthy ones; unbranded "5MP" CCTV lenses often are not.

## Mounts

| Mount | Thread | Flange distance | Used for |
| --- | --- | --- | --- |
| C | 1"-32 UN | 17.526 mm | Cine/TV and machine-vision lenses, circles up to ~22 mm |
| CS | 1"-32 UN | 12.526 mm | Compact CCTV lenses, mostly small formats |
| M12 (S-mount) | M12 × 0.5 | none — focus by thread | Board lenses, mostly small formats |

C and CS share the same thread. Only the flange distance differs:

| Combination | Works? |
| --- | --- |
| C lens on CS camera | Yes, with a 5 mm C-CS adapter ring |
| CS lens on C camera | No — can never reach focus |

The HQ and Global Shutter cameras have an adjustable back-focus ring (12.5–22.4 mm). After a lens change, set the lens to infinity and turn the ring until a distant subject is sharp.

## Other markings

| Marking | Meaning | On a Cinemate rig |
| --- | --- | --- |
| `8mm` | Fixed focal length | Fine |
| `2.8-12mm` | Varifocal — refocus after zooming | Fine; not for zooming during a take |
| `F1.4` | Maximum aperture | Lower = faster |
| `IR`, `IR corrected`, `day/night` | Visible and near-IR focus on the same plane | Only matters with the IR-cut filter removed or switched off |
| manual iris | Aperture ring on the lens | Use this |
| fixed iris | No aperture control, usually wide open | Works; control exposure with shutter/ISO/ND |
| `DC` (auto iris) | Camera-driven iris, 4-pin cable | Avoid — stays closed without drive electronics, image goes black |
| `P-iris` | Stepper-motor iris, needs camera support | Avoid — no P-iris support |

All four Cinemate camera boards sit behind an IR-cut filter by default, so IR correction is optional. The StarlightEye can switch its filter off electronically — for IR shooting there, an IR-corrected lens holds focus.

## What each sensor needs

| Sensor | Board | Mount | Sensor diagonal | Minimum lens format |
| --- | --- | --- | --- | --- |
| IMX296 | Pi Global Shutter Camera | CS (C ring included) | 6.3 mm | `1/2.5"` — `1/3"` risks corner shading |
| IMX477 | Pi HQ Camera | CS (C ring included); M12 variant | 7.9 mm | `1/2"` — `1/2.3"` is exact, no margin |
| IMX585 | StarlightEye | C only — CS lenses do not fit | 12.8 mm | `1/1.2"` or `1"` — `2/3"` vignettes |
| IMX283 | OneInchEye | CS, C adapter included | 15.9 mm | `1"` |

Cropped sensor modes read a smaller area, so smaller-format lenses can still cover them:

| Mode | Read-out diagonal | Still covered by |
| --- | --- | --- |
| IMX283 3840×2160 (UHD crop) | 10.6 mm | `2/3"` lens |
| IMX477 1332×990 (crop) | 5.1 mm | `1/3"` lens |

All other modes use roughly the full sensor area — the main table applies. Read-out areas per mode are listed in [camera sensors and frame rates](sensors.md#sensor-size-crop-factor-and-film-format-equivalents).

Sharpness needed per recording mode:

| Sensor / mode | Recording pixel pitch | Needs | Look for |
| --- | --- | --- | --- |
| IMX296 | 3.45 µm | 145 lp/mm | Any megapixel-class lens (`2MP`+) |
| IMX477 binned modes | 3.1 µm | 161 lp/mm | `5MP`-class, rated `1/2"` or larger |
| IMX585 4K | 2.9 µm | 172 lp/mm | 4K/`8MP`-class 1-inch lens; for full pixel-level sharpness, a machine-vision lens specified for ≤3 µm pixels |
| IMX283 2.7K (binned) | 4.8 µm | 104 lp/mm | `5MP`-class 1-inch lens |
| IMX283 UHD crop | 2.4 µm | 208 lp/mm | `10MP`-class `2/3"` machine-vision lens |

!!! note ""
    Vintage C-mount lenses made for 16mm film draw a circle of about 12.7 mm. That covers the IMX283 UHD crop, is borderline on the IMX585 (test your copy), and does not cover the full IMX283. Lenses made for Super 16 (~14.5 mm) get closer but still fall short of the full 1-inch sensor.

## Buying checklist

1. Format first: image circle ≥ sensor diagonal (table above).
2. Mount second: C or CS, and whether the board accepts it.
3. Manual or fixed iris only — no `DC`/`P-iris`.
4. MP rating last: convert to pixel size and compare with your sensor.
5. Focal length: multiply by the crop factor in [camera sensors and frame rates](sensors.md#focal-length-examples) for the full-frame equivalent look.
