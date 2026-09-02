---
datum: 2026-07-22 22:34:02
kontext: Projekt
projekt: "#CINEMATE"
fritext: sensor_to_storage
typ: ""
källa: cinepi-raw / cinemate / libcamera källkod
type: projektplanering
ursprung: dev-notes/image-pipeline-explained
samling: Image pipeline
---

# The image pipeline: sensor to storage

> [!info] Image pipeline — 4-delad guide
> 1. **The image pipeline: sensor to storage** *(denna not)*
> 2. [[20260722223403 CINEMATE IMAGE_PIPELINE_MAP kernel_drivers_dtoverlays|Kernel, drivers and dtoverlays]]
> 3. [[20260722223404 CINEMATE IMAGE_PIPELINE_MAP tuning_files|Tuning files explained]]
> 4. [[20260722223405 CINEMATE IMAGE_PIPELINE_MAP clearhdr_case_study|Case study: ClearHDR on the IMX585]]
>
> *Revised 2026-09-02 after an adversarial source-code review; verified against cinepi-raw `dev`, cinemate `dev`, libcamera `cinemate`, imx585-v4l2-driver `cinemate-7modes`.*

How a photon becomes a DNG on your card. This guide follows one frame through every layer of the Cinemate stack on a Raspberry Pi 5, using the IMX477 (HQ Camera) and IMX585 (Starlight Eye) as the two running examples.


## The map

One frame passes through eight stages. Some are silicon, some are software.

| # | Stage | Where it runs | What it produces |
|---|-------|---------------|------------------|
| 1 | Sensor | IMX477 / IMX585 chip | Bayer pixels, streamed row by row |
| 2 | CSI-2 link | wires to the Pi | serialized pixel packets |
| 3 | CFE (Camera Front End) | RP1 chip on the Pi 5 | raw Bayer written to RAM + statistics |
| 4 | libcamera + IPA | Pi CPU | sensor control, per-frame metadata, ISP config |
| 5 | PiSP Back End | Pi 5 ISP block | processed YUV/RGB (the preview stream) |
| 6 | cinepi-raw | Pi CPU | DNG files, MJPEG/HDMI preview outputs |
| 7 | Storage | SD / NVMe / SSD | the take folder on your card |
| 8 | Cinemate | Pi CPU (Python) | control + UI over Redis |

```
        ┌─ raw Bayer in RAM ─┬─► cinepi-raw DNG writer ──► /media/RAW/CINEPI_.../*.dng
sensor ─┤  (Front End DMA)   └─► PiSP Back End ─► YUV ─► preview (MJPEG :8000 / HDMI)
(CSI-2) └─ stats in RAM ─► libcamera IPA ─┬─► sensor controls (next frame)
                                          └─► Back End parameters
```

The single most important idea: **the recorded image and the preview image split early.** Your DNG is the sensor's raw Bayer, captured by the Front End before any colour processing. The preview is a separate, fully-processed copy made by the Back End — its pixel input is that same raw Bayer in RAM; the IPA only hands it parameters. They come from the same exposure, and the preview's processing never feeds back into the recording.[^cfe][^be]

---

## Stage 1 — The sensor

A camera sensor is a grid of light buckets. Each pixel sits under one colour of a **Bayer** filter (one red, one blue, two green per 2×2 tile), so a raw frame is a mosaic, not a colour image. Turning that mosaic into RGB (demosaicing) happens much later — and for your DNG, in your editor, not on the Pi.

### A "mode" is a readout recipe

A sensor does not have one resolution. It has **modes** — different ways of reading the pixel grid:

- **Binning** combines neighbouring pixels on-chip (e.g. 2×2), keeping the full field of view at lower resolution and higher speed.
- **Cropping** reads only a central region, giving a tighter frame from the same lens.

| Sensor | Mode | Readout | Bit depth |
|--------|------|---------|-----------|
| IMX477 | 2028×1080 | 2×2 binned + 16:9 crop | 12-bit |
| IMX477 | 1332×990 | 2×2 binned + cropped, fast (120 fps) | 10-bit |
| IMX585 | 1920×1080 | 2×2 binned | 12-bit |
| IMX585 | 3840×2160 | all-pixel (native 4K) | 12-bit |

Note the 1332×990 row: the driver reads a 2664×1980 central crop and bins it 2×2, so the field of view is that of the 2664×1980 region, not a native 1332-pixel crop — and it is a **10-bit** mode, which is exactly why it is the fast one (the 12-bit variant of that geometry needs thousands of pixels of extra blanking per line).[^imx477src]

The IMX585 driver Cinemate now ships (branch `cinemate-7modes`) defines a **seven-mode matrix** around a 3840×2160 active area: the two 12-bit SDR modes above, a 10-bit RAW10 4K mode (up to 90 fps at high link rates), 12-bit companded ClearHDR variants, and 16-bit linear ClearHDR entries at 1920×1100 / 3840×2200 (the extra rows are optical-black padding — they are recorded in the DNG and sit at the black pedestal; it is the preview path's centered crop that skips them).[^imx585modes] The legacy `6.12.y` branch had exactly two modes at the older readout dims 1928×1090 / 3856×2180 — numbers you will still meet in older docs. The IMX477 driver defines several modes, of which Cinemate exposes the fast ones. See Camera sensors and frame rates for the full tables.

### Frame rate is a frame-*length* setting

This surprises people. On these Sony sensors, fps is not a "speed" dial — it is set by how many blank lines pad each frame.

- **HMAX** sets the time to read one line.
- **VMAX** sets the total number of lines per frame (real + blank). Default on the IMX585 is 2250.[^vmax]
- Frame period ≈ VMAX × HMAX. To go faster, you *shorten* the frame by lowering VMAX (fewer blank lines). That "blank line" count is the `vblank` control.

**Exposure** is likewise counted in lines, not milliseconds. The sensor exposes for `VMAX − SHR` lines, where SHR is a shutter register.[^shr] So exposure and frame rate share the same ruler — which is why very long exposures force lower frame rates.

> [!note] What ISO and shutter really change
> Setting ISO changes the sensor's **analogue gain** register (and digital gain past its ceiling). Setting shutter angle changes the **exposure line count**. Neither changes the pixels' colour — they change how the sensor reads charge before it ships the Bayer data out.

### The two sensors, side by side

| | IMX477 (HQ Camera) | IMX585 (Starlight Eye) |
|---|---|---|
| Type / pixel | 1/2.3", 1.55 µm | 1/1.2", 2.9 µm |
| Resolution | 12.3 MP | 8.3 MP |
| CSI-2 lanes | 2 | 4 (default) |
| Link frequency | 450 MHz | 720 MHz (default) |
| Metadata to libcamera | embedded per-frame | none (frame-counted) |
| In-sensor HDR (ClearHDR) | **no** — `--hdr sensor` is a no-op | **yes** |

Bigger pixels and a larger sensor are why the IMX585 is the low-light choice.[^framos][^hqbrief] The metadata difference matters later (Stage 4). The HDR row matters if you own an HQ Camera: the in-tree imx477 driver exposes no wide-dynamic-range control and cinepi-raw's HDR gate only ever enables it on the IMX585 (or IMX708), so enabling HDR on the IMX477 silently does nothing — no HDR modes will appear, and that is expected, not a broken install.

---

## Stage 2 — The wire: MIPI CSI-2

The sensor ships pixels to the Pi over **MIPI CSI-2**, a serial camera link.[^csi2] Two numbers decide how fast it can go:

- **Lanes** — parallel data pairs. IMX477 uses 2; the IMX585 default is 4.[^overlay]
- **Link frequency** — the bit clock per lane. Higher link + more lanes = more pixels per second.

The raw bytes travel in one of a few **packings**: RAW10 packs 4 pixels into 5 bytes, RAW12 packs 2 pixels into 3 bytes. This is a transport format only; it gets unpacked on the Pi.

> [!info] Why 4K frame rate has a ceiling
> The CSI-2 link sets how fast Bayer can leave the sensor. At a given lane count and link frequency there is a minimum line time (HMAX), so there is a maximum frame rate for a given resolution — before the card is even involved. This "link-limited" ceiling is separate from the "can my storage keep up" ceiling in Stage 7. The IMX585 driver keeps a table of minimum HMAX per link frequency, doubled for 2-lane wiring.[^hmax]

---

## Stage 3 — The Pi 5: RP1, the CFE, and the PiSP

Here is where Pi 5 differs sharply from Pi 4, and where the pipeline splits in two.

On the Pi 5, camera input is handled by **RP1**, the Pi's I/O controller chip, which contains the **CFE (Camera Front End)**. The kernel describes the CFE as "a module which combines a CSI-2 receiver with a simple ISP, called the Front End."[^cfe] In the pipeline libcamera actually programs for cinepi-raw:

- the **CSI-2 receiver** takes the pixel stream off the wire and feeds it into the Front End (its own DMA engines *can* write streams straight to RAM, but this pipeline uses that path only for sensors' embedded-metadata streams — which the IMX585 doesn't even emit);
- the **Front End** passes the Bayer through essentially unmodified — no colour processing — and **writes the raw frame to RAM through its image output** (the `fe_image0` node, optionally PiSP-compressed), while simultaneously producing **statistics** (brightness histograms etc.) for auto-exposure and white balance.[^cfe][^feimage]

So every recorded frame does pass *through* the Front End — the point is that the FE does not reshape it: your DNG's pixels are the sensor's Bayer values, black-level-aligned at most (see the tuning caveat in Stage 4).

A second block, the **PiSP Back End**, is a **memory-to-memory** ISP: it reads that raw Bayer back out of RAM, demosaics and processes it, and writes YUV/RGB back to RAM through two output channels.[^be] It is *offline* — decoupled from the sensor's timing.

```
sensor ─CSI-2─► [RP1: CSI-2 receiver ─► Front End] ─► raw Bayer in RAM ─┐
                                        └► stats in RAM (→ IPA)         │
                          ┌─────────────────────────────────────────────┘
                          ▼
             [PiSP Back End, memory-to-memory] ─► YUV in RAM (→ preview)
```

**This split is why recording and preview are independent.** cinepi-raw records the Front End's raw Bayer; the preview uses the Back End's YUV. (Stage 6.)

### Pi 4 vs Pi 5

| | Pi 4 / CM4 | Pi 5 / CM5 |
|---|---|---|
| CSI-2 receiver | Unicam | inside the CFE (RP1) |
| ISP | VideoCore VC4 | PiSP (Front End + Back End) |
| libcamera pipeline | `rpi/vc4` | `rpi/pisp` |
| Tuning folder | `.../ipa/rpi/vc4/` | `.../ipa/rpi/pisp/` |

libcamera on the Cinemate Pi is built with **both** pipelines, so one build runs on either board; it picks `pisp` or `vc4` at runtime.[^rpicamdoc] This is why tuning files come in two flavours (see [[20260722223404 CINEMATE IMAGE_PIPELINE_MAP tuning_files|Tuning files]]).

### Packed vs unpacked in memory

On the **Pi 5**, cinepi-raw keeps raw **unpacked** (`U`): each 12- or 16-bit pixel sits in whole bytes in RAM — simple to read, larger. On **Pi 4-family** boards the same data arrives **MIPI-packed** (`P`) and must be unpacked before use. Cinemate picks the right packing automatically per board.[^packing] This choice feeds directly into the next idea.

---

## Stride — the concept everyone trips on

A row of pixels in memory is usually **wider than the image**.

**Stride** (also called *bytes-per-line*) is the number of bytes from the start of one pixel row to the start of the next. Hardware likes rows to begin on aligned addresses, so it pads the end of each row. That padding means:

```
stride  ≥  width × bytes-per-pixel      (rounded up to an alignment)
buffer  =  height × stride              (NOT width × height × bytes-per-pixel)
```

If you walk a frame assuming rows are `width × bpp` apart, every row drifts by the padding and the image comes out **diagonally sheared**. The DNG writer avoids this by reading each row from its true offset, `raw + y × stride`:[^stride]

```cpp
for (uint32_t y = 0; y < info.height; ++y)
    ...  raw + y * info.stride  ...     // one row, honoring stride
```

libcamera hands cinepi-raw the stride for each buffer (it comes from the plane's `bytes-per-line`).[^bpl] Stride is also where bit-packing lives: the same writer, in per-depth row loops in the same function, unpacks MIPI RAW12/RAW10 on Pi 4 and reads unpacked 16-bit containers on Pi 5, then packs to the DNG's contiguous layout.[^packrows]

> [!note] One-line takeaway
> Buffer size is `height × stride`, not `width × height × bytes-per-pixel`. Always step rows by stride.

---

## Stage 4 — libcamera and the IPA

**libcamera** is the Linux framework that drives the camera hardware. Its core object is the **Request**: one Request equals one frame's worth of work. cinepi-raw hands libcamera buffers to fill; libcamera programs the sensor and CFE, captures the frame, and completes the Request with buffers + metadata.[^request]

A Request can carry **two streams from the same exposure**:

- a **raw** Bayer stream → the DNG,
- a **processed** stream (the Back End's YUV) → the preview.

### Where per-frame metadata comes from

Every completed Request carries a metadata dictionary. The key entry for us is **`SensorTimestamp`** — the capture time on the Pi's monotonic clock.[^timestamp] This one number becomes:

- the DNG timecode and `DateTimeOriginal`,
- the Redis timecode Cinemate displays.

Other per-frame metadata (exposure, analogue gain, white-balance gains, black level) rides along too and lands in the DNG.

### The IPA: the camera's brain

The **IPA** (Image Processing Algorithms) runs the "3A" loop — auto-exposure/gain, auto white balance, auto lens-shading — plus black level and colour.[^ipa] Each frame it outputs two things:

1. **sensor settings** to apply next (exposure lines, gain code, frame duration), and
2. **Back End parameters** (the tuning applied to the preview).

> [!info] What the IPA does for a RAW shooter
> For your DNG, only the IPA's **sensor-facing decisions** (exposure, gain) and the **metadata it records** (white-balance gains, black level, colour matrix) matter. Its image-shaping output — sharpening, denoise, contrast — only touches the **preview**. No tuning block reshapes your recorded image; the two caveats worth knowing are narrow: the Front End applies a tuning-fed black-level *alignment* (an identity for the shipped uniform tunings), and in PiSP-compressed raw modes the compression itself quantises. In the normal unpacked modes, your Bayer is untouched. This is the heart of [[20260722223404 CINEMATE IMAGE_PIPELINE_MAP tuning_files|Tuning files]].

### The per-sensor translator: cam_helper

libcamera can't know every sensor's quirks, so each sensor has a **cam_helper** that converts real units to register values: gain multiplier ↔ register code, exposure time ↔ lines, and the blanking needed to hit a frame rate.[^camhelper] Here the two sensors diverge:

| | IMX477 | IMX585 |
|---|---|---|
| Emits embedded metadata? | Yes — libcamera **reads back** the exact exposure/gain used | No — libcamera **predicts** it by counting frames |
| Mechanism | SMIA metadata parser | frame counter + delayed-control tracking |

**DelayedControls** — a helper for "controls that take effect with a delay" — schedules the delayed register writes for *every* sensor: a new gain or exposure written now lands on the sensor a few frames later, and DelayedControls tracks which value belongs to which future frame.[^delayed] What is IMX585-specific is the *reporting*: because the IMX585 sends nothing back per frame, libcamera derives the reported exposure/gain from DelayedControls' per-frame tracking instead of reading it out of embedded data — so the metadata still matches the frame it actually shaped. (This detail returns in the [[20260722223405 CINEMATE IMAGE_PIPELINE_MAP clearhdr_case_study|ClearHDR case study]].)

### A control's journey: Redis `iso` → sensor register

1. Cinemate writes `iso` to Redis.
2. cinepi-raw maps ISO to a libcamera gain control on the next Request.
3. The IPA passes it through (manual mode); the cam_helper converts it to the sensor's register code.
4. libcamera writes it over I2C; DelayedControls aligns it to the right frame.
5. The frame completes with the applied gain + `SensorTimestamp` in its metadata.

---

## Stage 5 — the preview stream

The Back End's job in this stack is exactly one thing: turn the recorded exposure's raw Bayer into a processed YUV stream the operator can look at. It reads the frame from RAM, applies the IPA's parameters (demosaic, white balance, denoise, sharpening, tone curve), and writes YUV back to RAM.[^be] cinepi-raw then consumes that stream for its preview outputs — which are cinepi-raw components, so they live in Stage 6 below.

Because the preview is a separate consumer of the same Request, it keeps running through recording, and preview quality never affects your DNGs.

---

## Stage 6 — cinepi-raw: the recorder

### What cinepi-raw is (and its rpicam-apps heritage)

cinepi-raw is a **fork of rpicam-apps**, Raspberry Pi's camera app suite, built "upon the rpicam-raw app."[^readme] That heritage is visible in the source tree:

| Folder | Origin | Contents |
|--------|--------|----------|
| `core/`, `apps/` | inherited from rpicam-apps | buffer/DMA management, option parsing, the encoder path, the post-processing-stage system |
| `cinepi/` | CinePi's additions | the event loop, the Redis bridge, the DNG writer, the preview stages, audio |

The division of labour: the **previews** plug into rpicam-apps' existing **post-processing-stage** hook (each preview is a registered stage that sees every completed frame), while the **DNG recorder** reuses rpicam-apps' *encoder* path — `EncodeBuffer()` and the output-ready callbacks — driven from cinepi-raw's own event loop, which is adapted from rpicam-raw's.[^stage][^encoderpath] So when you read Raspberry Pi's rpicam-apps documentation, you are reading about cinepi-raw's `core/`; the event loop, Redis control layer and DNG output are the CinePi delta. The fork tracks "libcamera 0.5 / rpicam-apps 1.7."[^readme]

### Frame → file

1. On a recording frame, cinepi-raw pushes an **encode job** — a reference to the camera's raw buffer — onto a queue.[^encodequeue]
2. An **encode worker thread** pops the job, takes a slot in the **RAM pool**, and builds the DNG into that pooled buffer (TIFF header, packed pixels, tags). The camera buffer is released back to libcamera only once the build is done.[^workers]
3. The finished DNG is handed to a **separate pool of disk-writer threads**, which write the file to the card.[^disk]
4. The RAM pool between encode and disk decouples capture rate from write rate — it is the "buffer" Cinemate shows (Stage 7).

The two pools have independent sizes and CPU affinities (encode vs disk), which is why heavy recording and audio capture can be kept off each other's cores.[^workers]

### Inside a CinePi DNG

A DNG is a TIFF file with camera-raw extensions. cinepi-raw writes it by hand.[^dngsave] The tags that matter:

| Field | Purpose | Source |
|-------|---------|--------|
| ImageWidth/Length, BitsPerSample | geometry, depth | stream info |
| CFAPattern | the Bayer order | sensor format |
| BlackLevel | the sensor's black point | frame metadata + tuning |
| WhiteLevel | the sensor's white point | derived from the stored bit depth — `(1 << bits) − 1` — or from the linearization table's output white; it is not a tuned value |
| ColorMatrix1/2, AsShotNeutral | colour calibration + as-shot white balance | tuning (CCM) / frame metadata |
| **FrameRate** (0xC764) | the CinemaDNG frame rate | the configured fps |
| **TimeCode** (0xC763) | SMPTE timecode, per frame | stepped from `SensorTimestamp` |
| DateTimeOriginal | wall-clock date/time | `SensorTimestamp` |

> [!note] Where timecode comes from
> Timecode is stepped **per frame from each frame's own `SensorTimestamp`**, in encode order under a lock. This replaced an older shared-clock approach that produced phantom timecode gaps when more than one encode worker ran.[^tcstep] Frame rate uses the *configured* value rather than the sensor's slightly-rounded register period, so a 25 fps take reads exactly 25.000.[^fpsrate]

DNG frames are **uncompressed** (`COMPRESSION_NONE`, unconditionally). A vendored lossless-JPEG source (`lj92.c`) sat dormant in the tree for a while and was deleted as dead code in August 2026.[^comp]

### The preview outputs

Preview is a separate consumer of the same Request. Two outputs exist, both fed by the **processed** (Back End) stream:

- **MJPEG over HTTP** on port **8000** — the web GUI and phone view. It JPEG-compresses the **main** processed stream (the full sensor-mode resolution, quality 60) and serves it; the low-res stream feeds the on-camera HDMI composite instead.[^mjpeg]
- **HDMI via DRM** — the on-camera monitor, including the dual-sensor side-by-side view.[^hdmi]

One deliberate exception to "preview never reads the raw": in **12-bit companded ClearHDR** mode, a `ccmpPreview` stage re-renders the low-res preview *from the raw Bayer* with the decompanding curve applied, so the monitor shows linear tones instead of the companded signal.[^ccmpprev] The DNG main image is unaffected either way — preview processing still never touches your recording.

> [!info] The port 8000 gotcha
> If cinepi-raw ever fails at startup with `bindSocket() failed - Error Code: 98`, something else already holds port 8000 — often a docs `mkdocs serve` or a leftover helper process. It is a port clash, not a camera fault.

---

## Stage 7 — Storage: buffer, DROP, and data rate

### The buffer model

Capture rate is fixed by fps; card write speed varies. The RAM pool absorbs the gap:

- Card keeps up → pool stays near empty → **buffer** low.
- Card falls behind → built DNGs pile up waiting for disk → **buffer** climbs. Encode workers start blocking for pool slots, camera buffers starve upstream, and frames begin to miss — visible as sensor-timestamp gaps (the purple/magenta **DROP** state).
- Pool actually exhausted → cinepi-raw **stops the take** outright, with a "RAM pool exhausted — recording stopped" warning. It does not silently keep recording with holes.[^drop][^poolstop]

Two independent drop signals feed the DROP indicator: a timing gap between frames, and an actual disk write that failed. Write failures used to be silent; they are now surfaced as a live warning.[^writefail]

### Data rate

Data rate = frame size × fps, and frame size is arithmetic, not folklore:

```
frame size ≈ ceil(width × bit-depth ÷ 8) × height   + a few KB of header
```

A 12-bit DNG therefore stores 1.5 bytes per pixel. The published sensor tables compute sizes exactly this way; three worked examples:

| Config | Frame size | fps | ≈ write rate |
|--------|-----------|-----|--------------|
| IMX477 2028×1080, 12-bit | 3.29 MB | 50 | ~165 MB/s |
| IMX585 2K binned, 12-bit | 3.15 MB | 50 | ~158 MB/s |
| IMX585 4K all-pixel, 12-bit | 12.61 MB | 40 | ~504 MB/s |
| IMX585 4K ClearHDR, 16-bit | 16.81 MB | 33 | ~555 MB/s |

(Sizes from the published tables, which still use the legacy 1928×1090 / 3856×2180 readout dims; on the current `cinemate-7modes` driver the 12-bit frames come out about 1% smaller (1920×1080 / 3840×2160), while the 16-bit 4K frame grows slightly — 3840×2200 with its OB rows, ≈ 16.9 MB. CineMate Log shrinks frames by re-encoding to 10 or 12 bits.)[^sizes]

Mind the 4K rows: ~500 MB/s sustained is fast-NVMe territory. When the required rate exceeds what the card sustains, the buffer fills, frames drop, and eventually the take stops.

**Sustainable fps is often lower than the sensor's maximum** — thousands of separate files add real filesystem overhead, and slow media falls behind long before the sensor does. Fast NVMe over the CFE *can* sustain full rate at 4K; an SSD or SD card generally cannot. Storage limits show up as buffer/DROP, nothing else: the **dynamic resolution** feature reacts only to the sensor's own per-mode fps ceiling, never to storage speed.

> [!note] 12-bit vs 16-bit DNG size
> A 12-bit sensor mode arrives on the Pi 5 as a 16-bit container. cinepi-raw packs it down to 12-bit in the DNG unconditionally — the 4 extra bits are padding, so nothing is lost. A true 16-bit mode (IMX585 ClearHDR) keeps the full 2 bytes per pixel automatically. (An older `--keep16` flag that could disable the packing was removed in August 2026; output depth is now controlled only by `--log-encode 10|12`.)[^pack]

### Filesystems

- **ext4** — fastest and most consistent; best for high-fps 4K.
- **exFAT** — Cinemate's default (mounts everywhere); slightly slower.
- **NTFS** — not recommended; write-failure-prone in testing.

At startup and when media is attached, Cinemate runs a **storage pre-roll** — a short warm-up recording (~2 s at max fps) that it deletes afterwards. It conditions the media so your first real take doesn't hit cold-media latency. It does **not** verify that your card can sustain your fps — drop warnings are deliberately suppressed while it runs — so make a test recording on your own setup and watch for DROP before trusting a card. See Storage pre-roll.[^preroll]

---

## Stage 8 — Cinemate's seat

Cinemate is the Python control and UI layer. It touches no pixels; it drives cinepi-raw through **Redis**:

- writes control keys (`is_recording`, `iso`, `fps`, `shutter_a`, `wb`, `zoom`, …),
- reads status/time keys (`framecount`, `buffer`, `is_writing`, `tc_cam0/1`, `last_dng_cam0/1`).

The record gate is **edge-driven**: only an `is_recording` 0→1 or 1→0 transition starts or stops a take. The full key list lives in the Redis API and Redis key reference.

---

## Where audio fits (placeholder)

Audio is recorded alongside the DNGs as a WAV file in the take folder, captured by cinepi-raw's sound path. Its central challenge is aligning the WAV's start to the same `SensorTimestamp` origin the DNG timecode uses — so the two share one clock. A dedicated **audio pipeline** article will slot in here, following the same layer-by-layer structure.

---

## Recap

- The pipeline splits at the Front End: **raw Bayer → DNG**, **processed YUV → preview**. The raw passes *through* the FE (its `fe_image0` output) but is not reshaped by it.
- **fps is a frame-length setting**; exposure and frame rate share the "lines" ruler.
- The **Pi 5's CFE (RP1) + PiSP Back End** replace the Pi 4's Unicam + VC4.
- **Stride** — step rows by `stride`, size buffers as `height × stride`.
- cinepi-raw is an **rpicam-apps fork**; its previews are post-processing stages, its recorder rides the encoder path from its own event loop.
- One clock, `SensorTimestamp`, drives DNG timecode, `DateTimeOriginal`, and Redis TC.
- **DROP** is signalled by frame-timing gaps and failed writes; a fully exhausted RAM pool stops the take.

Continue with [[20260722223403 CINEMATE IMAGE_PIPELINE_MAP kernel_drivers_dtoverlays|Kernel, drivers and dtoverlays →]].

---

## Footnotes

[^cfe]: Raspberry Pi PiSP Camera Front End (rp1-cfe) — Linux kernel docs: <https://docs.kernel.org/admin-guide/media/raspberrypi-rp1-cfe.html>. "combines a CSI-2 receiver with a simple ISP, called the Front End (FE)." Note this admin-guide page is mainline 6.13+ documentation; the Pi's own `rpi-6.12.y` tree carries the driver (`drivers/media/platform/raspberrypi/rp1_cfe/`) but not this doc.
[^feimage]: libcamera `src/libcamera/pipeline/rpi/pisp/pisp.cpp` — the pipeline disables the CSI-2 → memory link and enables CSI-2 → `pisp-fe`; the application-visible raw stream ("CFE Image") is the Front End's output-0 node `rp1-cfe-fe_image0`. Kernel side: `rp1_cfe/cfe.c` starts the CSI-2 channel in `CSI2_MODE_FE_STREAMING` with no buffer of its own; `pisp_fe.c` writes the FE's image + stats buffer addresses.
[^be]: Raspberry Pi PiSP Back End (pisp-be) — Linux kernel docs: <https://docs.kernel.org/admin-guide/media/raspberrypi-pisp-be.html>. "memory-to-memory Image Signal Processor (ISP) which reads image data from DRAM memory."
[^imx585modes]: `imx585-v4l2-driver`, branch `cinemate-7modes` — `supported_modes[]` + `supported_10bit_modes[]` (1920×1080 / 3840×2160 12-bit SDR, RAW10 4K, 12-bit CCMP ClearHDR, 16-bit ClearHDR at 1920×1100 / 3840×2200); see the README's mode matrix. Legacy branch `6.12.y`: exactly two modes, 1928×1090 binned and 3856×2180 all-pixel.
[^imx477src]: raspberrypi/linux `drivers/media/i2c/imx477.c`: <https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.12.y/drivers/media/i2c/imx477.c>. The 1332×990 entry is commented "120fps. 2x2 binned and cropped" (crop 2664×1980); the RPi camera docs list it as SRGGB10 @ 120 fps.
[^vmax]: `imx585.c` — `IMX585_REG_VMAX` (0x3028), `IMX585_VMAX_DEFAULT 2250`; `IMX585_REG_HMAX` (0x302c).
[^shr]: `imx585.c` — exposure in lines, `SHR = (VMAX − exposure) & ~1` (multiple of 2).
[^framos]: FRAMOS — Sony STARVIS 2 IMX585 (1/1.2", 12.84 mm diagonal, 2.9 µm, 8.3 MP): <https://framos.com/products/sensors/area-sensors/sony-starvis-2-imx585aaqj1-c-25437/>.
[^hqbrief]: Raspberry Pi HQ Camera product brief (IMX477, 12.3 MP, 1/2.3", 1.55 µm): <https://datasheets.raspberrypi.com/hq-camera/hq-camera-product-brief.pdf>.
[^csi2]: MIPI Alliance — Camera Serial Interface 2 (CSI-2): <https://www.mipi.org/specifications/csi-2>.
[^overlay]: `imx585-v4l2-driver/imx585-overlay.dts` — `data-lanes = <1 2 3 4>` (default), 2-lane held dormant; `link-frequencies = <720000000>`.
[^hmax]: `imx585.c` — per-mode HMAX tables (per-link-frequency minimum HMAX), ×2 for 2-lane.
[^rpicamdoc]: Raspberry Pi camera software docs (pisp vs vc4 tuning folders, libcamera role): <https://www.raspberrypi.com/documentation/computers/camera_software.html>.
[^packing]: Cinemate sensor docs — Raspberry Pi 4 raw packing note (`P` on Pi 4-family, `U` on Pi 5/CM5).
[^stride]: `cinepi-raw/cinepi/dng_encoder.cpp` — every row read in `dng_save()`'s row loops is `raw + y * info.stride` (line numbers drift as the file grows; cite the function, not a line).
[^bpl]: `libcamera/src/libcamera/pipeline/rpi/pisp/pisp.cpp:136` — `image.stride = format.planes[0].bpl`.
[^packrows]: `cinepi-raw/cinepi/dng_encoder.cpp` — `dng_save()` handles unpacked 16-bit (Pi 5), CSI2-packed RAW12/RAW10 (Pi 4), and PiSP-compressed input in per-depth row loops within the one function.
[^request]: libcamera project documentation: <https://libcamera.org/>. Request/stream model.
[^timestamp]: `libcamera/src/libcamera/pipeline/rpi/common/pipeline_base.cpp` — `request->metadata().set(controls::SensorTimestamp, …)`.
[^ipa]: `libcamera/src/ipa/rpi/common/ipa_base.cpp` — 3A control ranges and application.
[^camhelper]: `libcamera/src/ipa/rpi/cam_helper/cam_helper.h` — `gainCode`/`exposureLines`/`getBlanking`/`sensorEmbeddedDataPresent`.
[^delayed]: `libcamera/src/libcamera/pipeline/rpi/common/delayed_controls.h` — "Helper to deal with controls that take effect with a delay." Instantiated for every sensor in `pipeline_base.cpp`.
[^readme]: `cinepi-raw/README.md` — "fork of rpicam-apps that builds upon the rpicam-raw app"; "Adapted to libcamera 0.5 / rpicam-apps 1.7."
[^stage]: `cinepi-raw/cinepi/mjpegPreviewStage.cpp` — `class mjpegStreamStage : public PostProcessingStage` (the previews register via `RegisterStage`; the DNG recorder does not).
[^encoderpath]: `cinepi-raw/cinepi/cinepi_raw.cpp` — `event_loop()` calls `app.EncodeBuffer(...)`; `cinepi_recorder.hpp` routes it to `DngEncoder::EncodeBuffer2`; `dng_encoder.hpp` — `class DngEncoder : public Encoder`.
[^encodequeue]: `cinepi-raw/cinepi/dng_encoder.cpp` — `EncodeBuffer2()` builds an `EncodeItem` (holding a pointer into the camera buffer) and pushes it to `encode_queue_`; no copy happens at enqueue.
[^workers]: `cinepi-raw/cinepi/dng_encoder.cpp` — separate `encode_worker_count_` and `disk_worker_count_` pools with independent affinity/nice settings (fallback 2 encode / 8 disk); `encodeThread` acquires a RAM-pool slot and builds, `diskThread` writes.
[^disk]: `cinepi-raw/cinepi/dng_encoder.cpp` — `diskThread()` consumes `DiskItem`s from `disk_buffer_` and writes each DNG to storage, decoupled from the encode stage.
[^dngsave]: `cinepi-raw/cinepi/dng_encoder.cpp` — `dng_save()` builds a little-endian TIFF/DNG in memory. Tag definitions: Adobe DNG Specification 1.7: <https://helpx.adobe.com/camera-raw/digital-negative.html>.
[^tcstep]: `cinepi-raw/cinepi/dng_encoder.cpp` — timecode stepped in `encodeThread` under `encode_mutex_` from each frame's `SensorTimestamp`.
[^fpsrate]: `cinepi-raw/cinepi/dng_encoder.cpp` — FrameRate tag (0xC764) uses `options_->framerate`, denominator 1000.
[^comp]: `cinepi-raw/cinepi/dng_encoder.cpp` — `dng_info.compression = COMPRESSION_NONE`; the vendored `lj92.c` was deleted 2026-08-23 (commit 50fa70b).
[^mjpeg]: `cinepi-raw/cinepi/mjpegPreviewStage.cpp` — MJPEG HTTP streamer, default port 8000; compresses `GetMainStream()` since 2025-07-03.
[^hdmi]: `cinepi-raw/cinepi/dualHdmiPreviewStage.cpp` — DRM HDMI preview (dual-sensor composite).
[^ccmpprev]: `cinepi-raw/cinepi/ccmpPreviewStage.cpp` — re-renders the lores preview from the raw Bayer with the CCMP decompand applied (12-bit ClearHDR only); force-inserted first in `cinepi_raw.cpp`.
[^drop]: `cinepi-raw/cinepi/dng_encoder.cpp` — a frame is dropped in the encoder only on RAM-pool *allocation failure* (`posix_memalign`), a `dng_save()` throw, or a failed disk write; workers otherwise block for a pool slot.
[^poolstop]: `cinepi-raw/cinepi/cinepi_raw.cpp` — `buffer_full()` ⇒ `controller.setRecording(false)`, warning "RAM pool exhausted — recording stopped".
[^writefail]: `cinepi-raw/cinepi/dng_encoder.cpp` — `write_failures_` counter surfaced as a live warning.
[^pack]: `cinepi-raw/cinepi/dng_encoder.cpp` — `write12bit_` set when a trusted sensor mode delivers ≤12-bit data in a 16-bit container (`sensor_mode_trusted_ && bits==16 && sensor_mode_bit_depth_ != 16`); true-16 modes keep full depth. `--keep16` removed 2026-08-05 (commit 599ceca) in favour of `--log-encode`.
[^sizes]: Cinemate `docs/sensors.md` — per-mode frame sizes computed as `ceil(width × bit-depth / 8) × height` plus a small header ("calculated dynamically, not read from a fixed table"); ClearHDR 16-bit 4K: 16.81 MB (legacy 3856×2180) per `docs/sensors.md`; the current 3840×2200 frame is ≈ 16.9 MB per `docs/clear-hdr.md`.
[^preroll]: Cinemate `src/module/storage_preroll.py` (records then deletes a ~2 s clip "so the media is 'warmed up'"); `docs/storage-preroll.md` ("Storage pre-roll warm-up"; drop/SYNC warnings suppressed while active).

---
#CINEMATE #IMAGE_PIPELINE_MAP
