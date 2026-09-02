---
datum: 2026-07-22 22:34:04
kontext: Projekt
projekt: "#CINEMATE"
fritext: tuning_files
typ: ""
källa: cinepi-raw / cinemate / libcamera källkod
type: projektplanering
ursprung: dev-notes/image-pipeline-explained
samling: Image pipeline
---

# Tuning files explained

> [!info] Image pipeline — 4-delad guide
> 1. [[20260722223402 CINEMATE IMAGE_PIPELINE_MAP sensor_to_storage|The image pipeline: sensor to storage]]
> 2. [[20260722223403 CINEMATE IMAGE_PIPELINE_MAP kernel_drivers_dtoverlays|Kernel, drivers and dtoverlays]]
> 3. **Tuning files explained** *(denna not)*
> 4. [[20260722223405 CINEMATE IMAGE_PIPELINE_MAP clearhdr_case_study|Case study: ClearHDR on the IMX585]]
>
> *Revised 2026-09-02 after an adversarial source-code review.*

What the per-sensor JSON files contain, and the question that trips up every RAW shooter: *if I record RAW, why does tuning matter at all?* This article answers that with the code.


## What a tuning file is

A tuning file is a **per-sensor JSON** the [[20260722223402 CINEMATE IMAGE_PIPELINE_MAP sensor_to_storage|IPA]] loads at runtime. It parameterises the 3A algorithms (auto-exposure, white balance, lens-shading) and the ISP blocks that process the preview.

```json
{ "version": 2.0, "target": "pisp", "algorithms": [ { "rpi.black_level": … }, … ] }
```

Two things to know up front:

- It is **platform-specific**. The Pi 5 files live in the `pisp/` folder and carry `target: pisp`; the Pi 4 files live in `vc4/` — but their JSON `target` field is the literal string **`bcm2835`**, and the vc4 IPA validates against exactly that string (a Pi 4 file authored with `target: vc4` refuses to load). The same sensor name resolves to a different file per board — this is why the [[20260722223402 CINEMATE IMAGE_PIPELINE_MAP sensor_to_storage|Pi 5 stage]] has separate `pisp/` and `vc4/` folders. Installed copies land under `/usr/share/libcamera/ipa/rpi/pisp/`.[^dirs]
- It is chosen by **sensor name** at camera open. A custom file is passed with `--tuning-file` or the `LIBCAMERA_RPI_TUNING_FILE` environment variable — and note that under Cinemate, the launcher *always* passes `--tuning-file` (next section).

---

## Anatomy: the blocks

The stock IMX585 pisp file contains 14 algorithm blocks.[^blocks] The IMX477 file is nearly the same set. Here is what each does — and, crucially, whether it reaches your **DNG** or only your **preview**.

| Block | Job | Reaches the DNG? |
|-------|-----|------------------|
| `rpi.black_level` | the sensor's black pedestal (IMX585: `black_level: 3200`) | **Yes — as metadata** (the DNG BlackLevel tag) |
| `rpi.lux` | estimate scene brightness from stats | No (feeds other algorithms) |
| `rpi.dpc` | defective-pixel correction | Preview only |
| `rpi.noise` | the sensor's noise model per ISO | No (feeds denoise/AGC) |
| `rpi.geq` | green-channel equalisation | Preview only |
| `rpi.denoise` | spatial/temporal noise reduction | **Preview only** |
| `rpi.awb` | auto white balance | **Yes — as metadata** (white-balance gains → AsShotNeutral) |
| `rpi.agc` | auto exposure and gain, metering | **Yes — as sensor settings** (unless you shoot manual) |
| `rpi.alsc` | auto lens-shading correction | Preview only |
| `rpi.contrast` | gamma / tone curve | **Preview only** |
| `rpi.ccm` | colour correction matrix (per colour temperature) | **Yes — as metadata** (reported as ColourCorrectionMatrix → the DNG ColorMatrix1/2 tags) |
| `rpi.cac` | chromatic-aberration correction | Preview only |
| `rpi.sharpen` | sharpening | **Preview only** |
| `rpi.hdr` | ISP-side HDR: AGC channel muxing + tone mapping | Preview normally — but see the note below for HDR sensors |

---

## The RAW question

**"I record RAW DNG. Why does a tuning file matter at all?"**

Because a tuning file does two different jobs, and only one of them is about the preview.

### What tuning does NOT do to your DNG

The Bayer pixels written to your DNG are the sensor's raw output. **Denoise, sharpening, contrast/gamma, lens-shading, chromatic-aberration and defective-pixel correction never modify them.** Those blocks shape only the **preview** — the processed YUV image from the Back End that you monitor on. Your recorded pixels are untouched.

> [!info] A useful debugging heuristic — with two exceptions
> A bad-looking preview (soft, odd shading, wrong contrast) with RAW recording usually means your **DNGs are fine** — the Bayer data does not pass through the preview's processing. Two cases break the rule:
> 1. **A wrong black level or white balance in the tuning corrupts DNG *metadata***: `rpi.black_level` and `rpi.awb` are exactly what land in the DNG's BlackLevel and AsShotNeutral tags (and `rpi.ccm` in ColorMatrix1/2), so those values follow your files into post.
> 2. **A missing or unloadable tuning file doesn't degrade the monitor — it stops the camera.** The rpi pipeline has no fallback: if `<sensor>.json` can't be read (or its `target` doesn't match the board), IPA init fails and the camera never comes up. Loud failure, no recording — not "fine DNGs, broken preview".

### What tuning DOES contribute to your DNG

A few blocks write **metadata** — the numbers a RAW developer relies on to interpret the file:

- **Black level** (`rpi.black_level`) → the DNG BlackLevel tag. cinepi-raw scales the sensor's black-level metadata into the tag; if the metadata is absent it falls back to a standard pedestal.[^blacklevel]
- **White balance** (`rpi.awb`) → AsShotNeutral, the "as shot" white balance your editor opens with.
- **Colour matrix** (`rpi.ccm`) → ColorMatrix1/ColorMatrix2, the calibration your editor uses to map camera RGB to real colour. A divergent CCM in a custom tuning changes how every RAW developer renders the file.
- **Exposure and gain** (`rpi.agc`) → the actual sensor settings. In manual ISO/shutter, Cinemate overrides the AGC's choice, but the resulting values are still recorded.

(One tag that is *not* tuned: **WhiteLevel**. cinepi-raw derives it from the stored bit depth — `(1 << bits) − 1`, so 65535 for 16-bit ClearHDR, 4095 for 12-bit — or from the linearization table's output white. No tuning file carries a white level.)

So for a RAW shooter, tuning is mostly about **what you see while monitoring**, plus a handful of **metadata anchors** in the file. It is not about baking a look into the pixels. That separation is the whole point of shooting RAW on this stack.

---

## Custom tuning files in the Cinemate stack

First, which file actually loads. On any Pi 5-family board, Cinemate's launcher **always** passes `--tuning-file /home/pi/libcamera/src/ipa/rpi/pisp/data/<sensor>.json` — the libcamera *source checkout's* data file — and cinepi-raw turns that flag into the `LIBCAMERA_RPI_TUNING_FILE` environment variable, which overrides the installed `/usr/share/...` copy entirely.[^whichfile] Three consequences:

- **Editing `/usr/share/libcamera/ipa/rpi/pisp/imx585.json` does nothing while Cinemate drives the camera.** It affects only bare libcamera apps (`rpicam-hello` etc.). Don't debug a tuning change there.
- **The persistent edit point is the libcamera checkout**: `/home/pi/libcamera/src/ipa/rpi/pisp/data/<sensor>.json`. A `git pull` in the checkout is enough to change what loads; restart Cinemate to pick it up.
- **The supported per-project mechanism is `tuning_file_override`** in `settings.json` (`{ "enabled": true, "path": "/path/to/your.json" }`), which swaps the path the launcher passes. It is disabled by default.

For a quick experiment outside Cinemate: `--tuning-file /path/to/file.json` on a manual cinepi-raw run, or set `LIBCAMERA_RPI_TUNING_FILE`. Always match the board: a `target: bcm2835` (vc4) file on a Pi 5, or a `pisp` file on a Pi 4, fails to load.

About the repo's own file: `resources/tuning_files/imx585.json` in the Cinemate repo is a **minimal 5-block file** (black_level, awb, agc, ccm, contrast) — an override *template*, not a copy of the shipped 14-block tuning, and with `tuning_file_override` off it never loads. (An earlier draft of this article described a local working file, `imx585(3.2).json`, said to match the shipped tuning block-for-block; that file lives outside the repos, so treat that comparison as unverified.)[^custom]

---

## HDR hooks

Two things connect tuning to the [[20260722223405 CINEMATE IMAGE_PIPELINE_MAP clearhdr_case_study|ClearHDR case study]]:

- The `rpi.hdr` block is **ISP-side** HDR — it sets up alternating-exposure AGC channels, tone mapping, and (in its `SingleExposure`/`MultiExposure` modes) a spatial gain. Sensor **ClearHDR** is different: the *sensor* does the HDR merge and emits one 16-bit or companded Bayer frame. Don't confuse the two.
- **Black level matters more in HDR.** A true 16-bit ClearHDR frame spans all 16 bits, so its black pedestal and white level differ from the 12-bit path. On the IMX585 the pedestal is the black-level register × 64, so the default register value of 50 gives the familiar 3200.[^hdrblack] The white point needs no tuning — the DNG WhiteLevel is derived from the stored bit depth (65535 in 16-bit, 4095 in 12-bit). A wrong black level shows up as lifted or crushed shadows — exactly the class of problem the HDR bring-up had to settle.

> [!warning] `rpi.hdr` on a sensor-HDR sensor is not just tone mapping
> On an HDR-capable sensor the `rpi.hdr` block wires up **multi-channel AGC** for alternating exposures — machinery meant for sensors that emit two exposure streams, not the single merged frame ClearHDR produces. Upstream (Will Whang's libcamera) therefore **removed `rpi.hdr` from the IMX585 tuning** and cut `rpi.agc.channels` from 4 to 1, because the phantom extra channels could misroute a manual `--hdr single-exp` exposure onto an inactive channel (exposure reverting to ~990 µs).[^willhdr] Cinemate's own ClearHDR uses `--hdr sensor`, not `--hdr single-exp`, so normal HDR recording is not affected — but this is the exception to the clean "tuning only shapes preview" rule, and worth knowing before you rely on the ISP HDR modes.
>
> **Status in the Cinemate stack (as of 2026-09-02):** adopting this fix is *planned but has not landed* — the `Tiramisioux/cinemate` libcamera (branch `cinemate`) still ships `imx585.json` and `imx585_mono.json` with the `rpi.hdr` block and 4 AGC channels, and no public branch shows the port in progress. The intended change is unchanged: reduce `rpi.agc.channels` 4 → 1 and delete the `rpi.hdr` block in both files. Because Cinemate loads the libcamera checkout's tuning (see above), the change belongs in the libcamera repo. It needs Pi verification that SDR and `--hdr sensor` capture do not regress, and note the trade-off: removing the block also drops `spatial_gain: 2.0` and `tonemap_enable: 1` from the ISP HDR modes.

---

## Recap

- A tuning file is per-sensor, per-platform JSON the IPA loads at runtime; `pisp` for Pi 5, the `vc4/` folder (target string `bcm2835`) for Pi 4.
- Most blocks (denoise, sharpen, contrast, lens-shading) shape **only the preview**.
- A few blocks write **DNG metadata**: black level, white balance (AsShotNeutral), the colour matrix (ColorMatrix1/2), and the AGC-chosen exposure/gain. WhiteLevel is derived from bit depth, never tuned.
- A bad preview usually does not mean bad DNGs — but a wrong black level/AWB/CCM taints DNG metadata, and a missing tuning file stops the camera entirely.
- Under Cinemate the loaded tuning is the **libcamera checkout's** data file (via `--tuning-file`), not the installed `/usr/share` copy; `tuning_file_override` in settings.json is the supported way to point elsewhere.

Continue with [[20260722223405 CINEMATE IMAGE_PIPELINE_MAP clearhdr_case_study|Case study: ClearHDR →]].

---

## Footnotes

[^dirs]: Raspberry Pi camera software docs — tuning-file locations `/usr/share/libcamera/ipa/rpi/pisp/` (Pi 5) vs `.../vc4/` (Pi 4): <https://www.raspberrypi.com/documentation/computers/camera_software.html>. Target validation: `libcamera/src/ipa/rpi/vc4/vc4.cpp` accepts only `"bcm2835"`; `src/ipa/rpi/pisp/pisp.cpp` expects `"pisp"`.
[^blocks]: `libcamera/src/ipa/rpi/pisp/data/imx585.json` — 14 `rpi.*` algorithm blocks (`black_level`, `lux`, `dpc`, `noise`, `geq`, `denoise`, `awb`, `agc`, `alsc`, `contrast`, `ccm`, `cac`, `sharpen`, `hdr`).
[^blacklevel]: `cinepi-raw/cinepi/dng_encoder.cpp` — the DNG BlackLevel tag is scaled from `controls::SensorBlackLevels`; a standard pedestal is used as a fallback when the metadata is absent. CCM: the IPA reports `controls::ColourCorrectionMatrix` (`ipa_base.cpp`), which cinepi-raw bakes into the ColorMatrix1/2 tags. WhiteLevel: `dng_info.white = (1u << bits) − 1`, or the linearization table's output white.
[^whichfile]: Cinemate `src/module/cinepi_multi.py` — `tune = f"/home/pi/libcamera/src/ipa/rpi/pisp/data/{model}.json"`, passed as `--tuning-file` on every non-Pi4 board (the override setting only swaps the path); `cinepi-raw/core/options.cpp` — `setenv("LIBCAMERA_RPI_TUNING_FILE", …, 1)`; `libcamera/src/libcamera/ipa_proxy.cpp` — the env var short-circuits the install-dir search.
[^custom]: `cinemate/resources/tuning_files/imx585.json` (branch `dev`) — version 2.0, target pisp, 5 blocks (black_level 3200, awb, agc, ccm, contrast). The author-local `_tuning files/imx585 cinemate v3.2/imx585(3.2).json` is not in any repo; its block-by-block match to the shipped tuning could not be independently verified.
[^hdrblack]: `innomaker585/CLEARHDR-STATE.md` (author-local notes) — pedestal = BLKLEVEL × 64 (darkframe-verified); corroborated by the driver default (BLKLEVEL 50) and the tuning/DNG value 3200.
[^willhdr]: Will Whang's libcamera, commit `16f1e27` — "ipa: rpi/pisp: drop rpi.hdr from IMX585 tunings" (sensor-side ClearHDR delivers a single merged frame; removes the `rpi.hdr` block and reduces `rpi.agc.channels` 4→1 so manual exposure lands on channel 0): <https://github.com/will127534/libcamera/commit/16f1e271b14dc3ec381cd98d6b237b7fd7c1ee19>. Not present in the `Tiramisioux/cinemate` libcamera as of 2026-09-02.

---
#CINEMATE #IMAGE_PIPELINE_MAP

#CINEMATE
