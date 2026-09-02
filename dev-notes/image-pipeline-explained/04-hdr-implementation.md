---
datum: 2026-07-22 22:34:05
kontext: Projekt
projekt: "#CINEMATE"
fritext: clearhdr_case_study
typ: ""
källa: cinepi-raw / cinemate / libcamera källkod
type: projektplanering
ursprung: dev-notes/image-pipeline-explained
samling: Image pipeline
---


# Case study: ClearHDR on the IMX585

> [!info] Image pipeline — 4-delad guide
> 1. [[20260722223402 CINEMATE IMAGE_PIPELINE_MAP sensor_to_storage|The image pipeline: sensor to storage]]
> 2. [[20260722223403 CINEMATE IMAGE_PIPELINE_MAP kernel_drivers_dtoverlays|Kernel, drivers and dtoverlays]]
> 3. [[20260722223404 CINEMATE IMAGE_PIPELINE_MAP tuning_files|Tuning files explained]]
> 4. **Case study: ClearHDR on the IMX585** *(denna not)*
>
> *Revised 2026-09-02 after an adversarial source-code review; updated to the `cinemate-7modes` driver and the shipped CCMP12 support.*

> [!tip] Relaterat i CINEMATE DEV
> [[20260709140810 CINEMATE DEV 16bit_HDR|CINEMATE DEV 16bit_HDR]] — arbetsanteckningarna bakom denna fallstudie.

One feature, every layer. This article follows the IMX585 ClearHDR work from the sensor register to the Cinemate menu, and tells the real bring-up story — including the day the whole thing turned out to be a kernel bug. It is the practical payoff of the previous three articles.


## What ClearHDR is

ClearHDR is Sony's **in-sensor** high-dynamic-range mode on STARVIS 2 sensors. The sensor captures high- and low-conversion-gain reads of the same frame and merges them on-chip, then emits either:

- **16-bit linear** Bayer (`SRGGB16`), or
- **12-bit companded** Bayer (`SRGGB12_CSI2P`, using Sony's on-sensor **CCMP** gradation compression — not to be confused with PiSP's **COMP1**, the *Pi-side* compression the CFE can apply to the 16-bit stream).

It is **not** ISP exposure-bracketing. The merge happens on the sensor die, before the data ever reaches the Pi. And it is IMX585-only in this stack: on any other sensor — the IMX477 included — `--hdr sensor` is a silent no-op (no control exists, no HDR modes appear).

Three consequences shape everything downstream:

- **One control turns it on**: `V4L2_CID_WIDE_DYNAMIC_RANGE = 1` on the sensor subdev.[^wdr]
- **Frame rate halves.** In HDR the sensor's frame-length register VMAX doubles (2250 → 4500), so each frame takes twice as long.[^vmax] The halved figures then flow up the stack: libcamera and cinepi-raw report half the max fps, and Cinemate labels these modes and relays the halved fps the `--hdr sensor` probe reports. (On the current `cinemate-7modes` driver there is one refinement: ClearHDR's dual HG+LG read also enforces a *minimum HMAX* of 550 × lane-scale, so at link rates ≥ 2079 Mbps/lane — where the 12-bit timing tables dip below the floor (HMAX 472) — those modes lose *more* than half their frame rate. At the default 720 MHz link the floor is inert and fps exactly halves.)
- **Gain is capped.** The analogue-gain ceiling in HDR is code 80 — about 15.8× — versus the full range in normal mode.[^gain]

The bring-up scoped v1 to **16-bit linear HDR DNG**; companded CCMP12 was deferred to a v2 — which has since shipped (August 2026, below). During the gap the mode table already listed the 12-bit HDR modes, and recording one produced companded DNGs with no decompanding metadata — non-linear tones with nothing in the file to undo them. That is precisely what the v2 work fixed.

---

## Layer by layer

The value of this case study is seeing one feature touch every layer from the previous articles.

| Layer | What ClearHDR required |
|-------|------------------------|
| **Kernel** (rp1-cfe) | correct 16-bit handling in the Front End — the actual root cause (below) |
| **Driver** (imx585) | the `wide_dynamic_range` control; new 16-bit + companded modes; VMAX×2 |
| **libcamera** | expose the 16-bit Bayer format; *don't* byte-swap the compressed stream |
| **cinepi-raw** | a `--hdr sensor` gate that flips the control at the right moment and drives 16-bit |
| **DNG writer** | already spoke 16-bit and COMP1 — needed one packing-decision fix (below) |
| **tuning / black level** | correct black and white points for the 16-bit range |
| **Cinemate** | a dual-probed mode table, HDR labels, halved-fps mode entries, gain cap, live knobs |

### The driver

Enabling `wide_dynamic_range` writes the sensor's WDMODE register (Clear HDR) and swaps the exposed format list to the HDR set — 16-bit first, then 12-bit companded. The same toggle doubles the minimum VMAX, which is where the halved frame rate comes from.[^driverregs]

### libcamera

The IMX585's raw stream arrives as a 16-bit container. One subtle fix was needed here: libcamera must **not** byte-swap the *compressed* (COMP1) buffers. The original swap logic keyed only on the sensor's bit depth, so it scrambled the compressed stream too. The fix makes the swap check the Front End's actual packing.[^endian]

### cinepi-raw — the gate

This is the core application change, and its ordering is the interesting part.[^gate] The `--hdr sensor` flag walks **every** `/dev/v4l-subdevN` and sets `V4L2_CID_WIDE_DYNAMIC_RANGE` wherever the control exists — no sensor-name filter on the walk, so it finds the IMX585 subdev on its own. Then:

1. **Disable** HDR on all subdevs (clean slate) and enumerate the cameras.
2. Read the camera model.
3. If HDR was requested **and** the enumerated model is an IMX585 (or IMX708), **enable** the control — and if the value actually changed, **reset the camera manager** and re-enumerate.

(So: the disable/enable *walk* is filterless; the *decision to enable* is model-gated. On any other sensor nothing is enabled and the run proceeds as plain SDR.)

Step 3's reset is essential: a sensor's mode list is fixed at enumeration time. Flip the HDR control *after* the camera is open and the HDR modes never appear. So the control must be set first, then the camera list rebuilt so the 16-bit and companded modes are visible.[^gate] The valid `--hdr` values are `off`, `single-exp`, `sensor`, and `auto`.

### A tuning subtlety: one merged frame, not two exposures

Sensor-side ClearHDR emits **one already-merged frame**. That is different from the ISP-side HDR the `rpi.hdr` tuning block was built for, which multiplexes *alternating* exposure streams across several AGC channels. Feeding a single-frame sensor through the multi-channel machinery is not just wasteful — it can misbehave.

Upstream (Will Whang's libcamera) made exactly this correction: it **removed the `rpi.hdr` block from the IMX585 tuning** and cut `rpi.agc.channels` from 4 to 1. Without the fix, a manual `--hdr single-exp` exposure could land on a phantom, inactive channel, so the exposure reverted to a default (~990 µs) regardless of what the user set.[^willhdr]

Two things worth knowing for the Cinemate stack:

- Cinemate's ClearHDR path uses `--hdr sensor` (the sensor merge), **not** `--hdr single-exp` (the ISP algorithm), so the phantom-channel bug is not on the normal HDR recording path. The upstream change is still worth porting — it removes dead AGC channels and is the cleanest illustration of the sensor-vs-ISP distinction. See also the [[20260722223404 CINEMATE IMAGE_PIPELINE_MAP tuning_files|tuning-file note]].
- **Status (2026-09-02): planned, not yet landed.** The `Tiramisioux/cinemate` libcamera still ships `imx585.json` / `imx585_mono.json` with `rpi.hdr` and 4 AGC channels, and no public branch shows the port in progress. The plan is unchanged (`rpi.agc.channels` 4 → 1, delete `rpi.hdr` in both files, then Pi verification that SDR and `--hdr sensor` do not regress); since Cinemate loads the libcamera checkout's tuning, the edit belongs in the libcamera repo.

> [!note] Deploying a tuning-only change
> A tuning JSON edit is a libcamera **data** change, not a code change. On the Pi, a `git pull` in `~/libcamera` already updates the file Cinemate actually loads — `src/ipa/rpi/pisp/data/imx585.json`, passed via `--tuning-file` — so pull + restart Cinemate is enough; no cinepi-raw rebuild. (`sudo meson install -C ~/libcamera/build` additionally refreshes the `/usr/share/...` copy, which only bare rpicam-apps read.)

### The DNG writer needed almost no change

The [[20260722223402 CINEMATE IMAGE_PIPELINE_MAP sensor_to_storage|DNG writer]]'s format table and COMP1 decode genuinely predate the feature — `SRGGB16` handling and the PiSP-compressed row path were already there.[^dngready] One real change was needed during bring-up: the writer's default had been "any 16-bit container gets packed down to 12-bit", which would have silently truncated a true 16-bit ClearHDR stream. Commit `2b248fe` taught the packing decision to distinguish a genuine 16-bit *sensor mode* from a 12-in-16 container (and fixed a black-level fallback for the 16-bit domain), so true-16 modes keep full depth automatically.[^dng16fix] Still a nice illustration of the fork's design: because the recorder was built around stride and format-driven packing, a new sensor format needed a decision fixed, not a path built.

---

## The bring-up story

This is the part worth studying, because the feature was blocked not by app code but by the lowest layer in the stack. The forensic trail is preserved in the project's state notes (author-local, not in the repos).[^state]

1. **First attempt.** `--mode 3856:2180:16:U` (true uncompressed 16-bit, on the then-current two-mode driver) produced **garbage** — noise, no image structure.
2. **Hypothesis: it must need compression.** The working reference DNGs from the sensor vendor showed quantisation steps growing with brightness (16 → 32 → 64), the signature of **PiSP COMP1** compression — so the reference product's "16-bit" was actually *compressed* raw the DNG writer decodes. cinepi-raw was changed to route the packed 16-bit mode to COMP1.
3. **Still garbage**, even with perfect negotiation and the correct decode path. The corruption was *upstream* of the app and libcamera.
4. **Suspect the driver.** A newly installed vendor driver used a different 16-bit mode geometry. Swapping back to the proven driver — **still garbage**. So the fault was below the driver too.
5. **Root cause: the kernel.** The Front End (rp1-cfe) had two 16-bit fixes the pinned kernel lacked: *"Avoid unpack operation for 16-bit formats"* (2025-06-27) and *"Workaround for 16-bit mismatch in the hardware"* (2025-07-04). The installer then pinned **6.12.25**, which predates both; the working reference image ran **6.12.75**. That one fact explained "12-bit fine, 16-bit garbage" on every driver and every app.[^state]
6. **The fix** was to upgrade the kernel and rebuild the DKMS sensor modules; libcamera and cinepi-raw needed no rebuild. The supported baseline settled on **6.12.93+rpt**, which the installer pins today.
7. **Result:** a real, pixel-verified **16-bit linear** capture — shadow floor sitting on the expected 3200 pedestal, cleaner than the compressed reference.

> [!note] The moral
> Four suspects were ruled out — the app's mode string, the compression routing, the new driver, the old driver — before the cause was found in the kernel's camera front-end. The layer you can edit fastest is not always the layer at fault. This is exactly why [[20260722223403 CINEMATE IMAGE_PIPELINE_MAP kernel_drivers_dtoverlays|Article 2]] spends time on kernel-version pinning.

### Two things that looked like bugs but weren't

- **The endian swap** scrambling the compressed stream (fixed in libcamera, above) was a real bug — but it was masking, not causing, the kernel problem.
- **Magenta highlights** on overexposed HDR frames are **not** a capture fault. They are an HDR blend plateau: at the merge knee the channels converge, and white balance pushes red and blue above green. Characterising the blend controls is ongoing work, not a defect.[^state]

---

## Cinemate integration

With capture working, the operator-facing layer was built out:[^round2]

- **Dual-probed mode table.** Cinemate runs `cinepi-raw --list-cameras` twice — plain, and with `--hdr sensor` — and merges them. A mode from the HDR probe counts as an HDR mode if its **(dimensions, bit depth, fps) tuple** wasn't in the plain list — in practice 16-bit modes are new by depth, and 12-bit HDR by its halved fps. Each mode gains an `hdr` flag.
- **Ordering and labels.** Plain modes first, then HDR, sorted by (hdr, bit depth, area). The GUI labels them `:12b HDR` and `:HDR`.
- **An `hdr` whitelist** in settings (`image_capture.hdr`, named form: `{"sdr": true, "imx585_clear_hdr": true}`) that can hide the HDR modes; the same block seeds the ClearHDR live-knob startup defaults. The legacy positional list (`"hdr": [false, true]`) is still parsed for compatibility.[^whitelist]
- **Live knobs** over Redis and `v4l2-ctl`: the data-selection threshold, blending mode, and gain adder — plus the `wide_dynamic_range` toggle. Grove Base HAT potentiometers can map to these.
- **A relaunch on change.** Switching bit depth or toggling HDR **restarts cinepi-raw**, because (as the gate showed) the mode list is fixed at enumeration.[^relaunch]
- **RP1 overclock** (Pi 5 only) to claw back some of the halved frame rate — measured at roughly 37.5 fps at 2K and 33.4 fps at 4K in HDR on the two-mode driver. (On `cinemate-7modes` the binned 2K mode shares the 4K modes' timing table outright, so expect the 2K HDR ceiling to land near the 4K figure — re-measure before quoting 37.5.)[^overclock]

---

## Shipped in v2: companded CCMP12 (August 2026)

What the v1 scope deferred has since landed, end to end:

- The **driver** (`cinemate-7modes`) ships spec-valid CCMP slopes and exposes 12-bit companded ClearHDR behind the `ccmp` dtoverlay parameter — default-on for the colour variant, opt-in on mono; the installer writes the parameter.
- **cinepi-raw** decompands: the DNG carries the CCMP decompand curve as its **LinearizationTable**, so the recorded file develops linearly; `--log-encode` composes with the decompand. Verified against real captures (2026-08-27).
- The **preview** got a dedicated `ccmpPreview` stage that re-renders the monitor image from the raw Bayer with the decompand applied — so the `-t 0` viewfinder now shows linear tones in 12-bit ClearHDR, not the companded signal. (Two residual caveats: use the unpacked `:12:U` raw token — with a CSI2-packed `:12:P` raw the stage disables itself and the monitor goes magenta while the DNGs stay correct — and stock rpicam previews still don't decompand.)[^ccmp]

Before this work (i.e. in the period this article was first written), the `:12b HDR` modes were visible and selectable but recorded companded DNGs with no decompand metadata — usable only with manual correction in post.

---

## What it teaches

Mapping the feature back to the earlier articles:

- **Sensor** ([[20260722223402 CINEMATE IMAGE_PIPELINE_MAP sensor_to_storage|Article 1]]) — HDR is a sensor mode; VMAX×2 halves fps (and on the current driver an HMAX floor can take more); new formats appear in the mode list.
- **Pi 5 / PiSP** ([[20260722223402 CINEMATE IMAGE_PIPELINE_MAP sensor_to_storage|Article 1]]) — the whole feature hinged on the Front End (CFE, in RP1) delivering 16-bit correctly.
- **Kernel** ([[20260722223403 CINEMATE IMAGE_PIPELINE_MAP kernel_drivers_dtoverlays|Article 2]]) — with an out-of-tree driver on a pinned kernel, the fix was a kernel upgrade, not app code.
- **cinepi-raw** ([[20260722223402 CINEMATE IMAGE_PIPELINE_MAP sensor_to_storage|Article 1]]) — a small options gate, plus a DNG writer that needed one packing decision fixed, not a new path.
- **Tuning** ([[20260722223404 CINEMATE IMAGE_PIPELINE_MAP tuning_files|Article 3]]) — the black point decides whether shadows land correctly (the white point is derived from bit depth, not tuned).

That is the point of the series: a real feature is never one layer. Knowing where the layers meet is what makes the next one tractable.

---

## Footnotes

[^wdr]: `cinepi-raw/core/options.cpp` — `set_subdev_hdr_ctrl()` sets `V4L2_CID_WIDE_DYNAMIC_RANGE`; driver side `imx585-v4l2-driver/imx585.c` WDMODE register `0x301a = 0x10` (Clear HDR).
[^vmax]: `imx585-v4l2-driver/imx585.c` — `imx585_update_hmax()`: minimum VMAX = `IMX585_VMAX_DEFAULT × (clear_hdr ? 2 : 1)` → 2250 doubles to 4500. On `6.12.y` HMAX is untouched by HDR, so the frame period exactly doubles; on `cinemate-7modes` the same function additionally floors HMAX at `IMX585_HMAX_MIN_CLEARHDR` (550) × lane-scale for the dual HG+LG read.
[^gain]: `imx585-v4l2-driver/imx585.c` — `IMX585_ANA_GAIN_MAX_HDR = 80`; the gain *law* `gain = 10^(0.015·code)` lives in libcamera's `cam_helper_imx585.cpp`, so code 80 ≈ 15.8×.
[^driverregs]: `imx585-v4l2-driver/imx585.c` — `common_clearHDR_mode[]` register block; `codes_clearhdr[]` (16-bit first, then 12-bit) replaces `codes_normal[]` when `clear_hdr` is set.
[^endian]: `libcamera` (branch `cinemate`), commit `bcdd7e1` — the 16-bit endian-swap gate now checks the Front End format packing, so PiSP-compressed buffers are not byte-swapped.
[^gate]: `cinepi-raw/core/options.cpp` — `set_subdev_hdr_ctrl()` (walks every `/dev/v4l-subdevN`) and the parse ordering: disable → `initCameraManager` → `GetCameras` → enable-if-imx585/imx708 → reset camera manager on change. Shipped in commit `b0bbd1a`; merged to `dev` at `eece268`.
[^dngready]: `cinepi-raw/cinepi/dng_encoder.cpp` — `SRGGB16` in the format table and the PiSP COMP1 decode path both predate the ClearHDR branch.
[^dng16fix]: `cinepi-raw` commit `2b248fe` (2026-07-12, on the ClearHDR branch; merged in `eece268`) — packing condition gains `sensor_mode_bit_depth_ != 16` so a true 16-bit sensor mode is not packed down to 12-bit, plus a 4096-domain black-level fallback fix.
[^state]: `innomaker585/CLEARHDR-STATE.md` (rev 4, 2026-07-14, "WORKING" — author-local notes, not in any repo) — the full forensic trail: 16:U garbage → COMP1 hypothesis → driver swap → kernel root cause (rp1-cfe fixes 2025-06-27 / 2025-07-04), the earlier 6.12.25 pin vs the 6.12.75 reference; plus the magenta-highlight blend-plateau analysis. Supported baseline now 6.12.93+rpt per `cinemate-install.sh` and `docs/clear-hdr.md`.
[^round2]: `cinemate` (branch `dev`) — ClearHDR round-2 commits `ee49253`…`0c39efd` (dual-probe mode table, HDR labels, whitelist, live knobs, pots, RP1 overclock docs); merged at `a635cbb`.
[^relaunch]: `cinemate` commit `1caf372` — relaunch cinepi-raw on bit-depth / ClearHDR change, because the sensor mode list is fixed at enumeration.
[^whitelist]: `cinemate` commit `862d1a3` (2026-07-20) — named-key whitelist `image_capture.hdr` `{sdr, imx585_clear_hdr}` in `settings.jsonc` (typed in `settings.schema.json`); `sensor_detect.py` still accepts the legacy list form.
[^overclock]: `cinemate/docs/overclocking.md` — 37.50 / 33.43 fps figures, measured on the two-mode (`6.12.y`-era) driver; on `imx585-7modes/imx585.c` the binned mode uses the same `HMAX_table_4lane_4K_12bit` (with `hmax_div = 1`) as the 4K modes, so its timing ceiling matches 4K's.
[^ccmp]: Driver: `imx585-7modes/imx585.c` (spec-valid CCMP slopes; `ccmp` overlay param; 12-bit CCMP default-on for colour). cinepi-raw `dev`: `dng_encoder.cpp` CCMP12 decompand + LinearizationTable (Aug 2026), `ccmpPreviewStage.cpp`, README "12-bit ClearHDR (CCMP12)". Cinemate: `docs/clear-hdr.md` (mode table incl. "HDR (CCMP)", verified 2026-08-27), `cinemate-install.sh` (writes `dtoverlay=imx585,<port>,ccmp`). The original v2 scoping notes are `innomaker585/CCMP12-HANDOFF.md` / `CCMP12-ACTION-PLAN.md` (author-local).
[^willhdr]: Will Whang's libcamera, commit `16f1e27` — "ipa: rpi/pisp: drop rpi.hdr from IMX585 tunings": <https://github.com/will127534/libcamera/commit/16f1e271b14dc3ec381cd98d6b237b7fd7c1ee19>. Sensor-side ClearHDR is a single merged frame, so the ISP HDR channel-muxing is removed and `rpi.agc.channels` reduced 4→1. Not present in the `Tiramisioux/cinemate` libcamera as of 2026-09-02.

---
#CINEMATE #IMAGE_PIPELINE_MAP

#CINEMATE
