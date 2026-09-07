# Adversarial review prompt — Image pipeline docs (for Fable, run in the cloud)

**How to use:** paste everything below the line into a cloud session running **Claude Fable 5**. Before running, make sure the target material is reachable (see "Setup" in the prompt). If you have one specific file in mind as "the LLM manual", replace the `<<LLM_MANUAL_PATH>>` placeholder with it; otherwise the agent will locate it.

---

You are an **adversarial technical reviewer**. Your job is to break a four-part documentation set — to find factual errors, overclaims, internal contradictions, and mismatches against the real source code and the project's own docs. Assume the documentation is wrong until each claim survives scrutiny. Finding nothing on a solid claim is a valid result; inventing problems is not.

## What you are reviewing

A four-article learning guide on the Cinemate camera image pipeline (Raspberry Pi 5 cinema camera: `libcamera → cinepi-raw → cinemate`, sensors IMX477 and IMX585):

1. `dev-notes/image-pipeline-explained/01-image-pipeline.md` — sensor → CSI-2 → CFE/PiSP → libcamera → cinepi-raw DNG → storage; includes **stride** and the rpicam-apps lineage.
2. `dev-notes/image-pipeline-explained/02-linux-camera-stack.md` — kernel, drivers, device-tree overlays, DKMS, kernel-version pinning.
3. `dev-notes/image-pipeline-explained/03-tuning-files.md` — libcamera tuning JSON; what reaches the DNG vs only the preview.
4. `dev-notes/image-pipeline-explained/04-hdr-implementation.md` — ClearHDR case study on the IMX585.

Each article uses footnotes that cite either a `repo/path:line` in the source or an external URL.

## Setup (do this first)

1. **The four articles are untracked working files** — a fresh clone will NOT contain them. Confirm they are present; if not, ask the operator to provide them (commit to a branch or paste them in). Do not proceed without the actual article text.
2. Make these **source-of-truth repos** available and note the branch each claim must be checked against:
   - `libcamera` — branch **`cinemate`** (`github.com/Tiramisioux/libcamera`)
   - `cinepi-raw` — branch **`dev`** (`github.com/Tiramisioux/cinepi-raw`)
   - `cinemate` — branch **`dev`** (`github.com/Tiramisioux/cinemate`)
   - `imx585-v4l2-driver` — branch **`6.12.y`** (`github.com/Tiramisioux/imx585-v4l2-driver`)
   - IMX477 driver: `raspberrypi/linux` `rpi-6.12.y` `drivers/media/i2c/imx477.c`
3. **Cross-check corpus** (tracked, in a normal clone):
   - Published Cinemate docs: `docs/*.md` (esp. `sensors.md`, `storage-preroll.md`, `config-txt.md`, `redis-keys.md`, `redis-guide.md`, `changelog.md`).
   - Cinemate **LLM / control manual**: `<<LLM_MANUAL_PATH>>` — if unset, locate it among `docs/cli-user-guide.md`, `docs/cli-commands.md`, `docs/controller-methods.md`, `docs/redis-guide.md`, `docs/web-api.md`; treat whichever is the command/API/control reference an automation or LLM would use to drive the camera as "the LLM manual." State which file you used.

## Method — launch adversarial agents

Use a fan-out of subagents. Each works to **refute**, not confirm. Suggested lenses (spawn one or more per lens; scale breadth to the material):

- **Per-article correctness (×4):** re-derive every factual claim in one article from the actual code/driver. For each footnote with a `path:line`, open the file and confirm the line still exists and says what the article claims. Flag anything you cannot verify.
- **Cross-doc consistency:** compare the four articles against `docs/*.md` and the LLM manual. Hunt for contradictions — sensor modes, bit depths, fps numbers, storage/filesystem claims, Redis keys, CLI/`--hdr` flags, control names. A number that disagrees between two docs is a finding.
- **Footnote & source auditor:** every external URL must resolve and actually support the claim (kernel.org rp1-cfe / pisp-be, RPi datasheets, DNG spec, MIPI, FRAMOS/Sony, libcamera.org). Flag dead links, version drift, or citations that don't say what's claimed.
- **Overclaim / hedge auditor:** flag any statement more certain than its evidence supports, and any hedge that hides a real error.
- **Completeness critic:** what would mislead or confuse an intermediate reader; what important step or caveat is missing.

**Adversarial verification gate:** every candidate finding must be checked by at least one independent skeptic agent that tries to *refute the finding* (default: "not a real problem" unless proven). Only findings that survive refutation go in the report. Prefer perspective-diverse skeptics (one checks the code, one checks whether the doc's own hedge already covers it, one checks the cross-doc source).

## High-risk claims to attack specifically

These are the load-bearing or self-flagged-uncertain claims. Attack them hardest:

1. **CFE vs Front End** (art. 1): the raw Bayer is written by the CSI-2 receiver's DMA; statistics/downscale are the Front End's. Verify against the kernel rp1-cfe doc — is the attribution correct and not conflated?
2. **fps halves via VMAX×2** (art. 1 & 4): verify in `imx585-v4l2-driver/imx585.c` `imx585_update_hmax()` that HDR doubles VMAX (2250→4500) and does **not** scale HMAX.
3. **Two-stage writer** (art. 1): confirm `cinepi-raw/cinepi/dng_encoder.cpp` has separate encode-worker and disk-worker pools (and the stated fallback counts). Is "encode builds, disk writes" accurate?
4. **DNG 12-bit packing + data-rate table** (art. 1): verify the default packs 16-bit containers down to 12-bit (`write12bit_`), and scrutinize the MB/s table — the measured per-frame sizes do **not** equal `W×H×1.5B`; is the article's "illustrative, includes overhead" framing honest, or does it mislead?
5. **`rpi.hdr` inert on `--hdr sensor`** (art. 3 & 4): verify `cinepi-raw/core/rpicam_app.cpp` sets `controls::HdrMode = SingleExposure` **only** for `hdr == "auto" || "single-exp"`, and that `core/options.cpp` rewrites `auto → sensor` for the IMX585 — i.e. that the ISP HDR block genuinely does not touch the `--hdr sensor` capture. If this is wrong, the "not affected" claim is wrong.
6. **Custom tuning file identical to shipped** (art. 3): independently diff `_tuning files/imx585 cinemate v3.2/imx585(3.2).json` against `libcamera/src/ipa/rpi/pisp/data/imx585.json`. Confirm "byte-identical, all 14 blocks" or refute it.
7. **Kernel-version gating of HDR** (art. 2 & 4): the pinned baseline (`6.12.25` in `cinemate-install.sh`) vs the claim that 16-bit HDR needs ≥`6.12.75` (bring-up `6.12.93`). Are the version numbers stated consistently and not overclaimed as permanent?
8. **Stride** (art. 1): is the explanation (`stride ≥ W×bpp`, `buffer = H×stride`, `raw + y*stride`) correct, and does it match `dng_encoder.cpp` and `pisp.cpp` (`image.stride = planes[0].bpl`)?
9. **Sensor & link facts** (art. 1 & 2): IMX585 1/1.2″ / 2.9 µm / 4-lane default / 720 MHz link / I2C `0x1a`; IMX477 1/2.3″ / 1.55 µm / 2-lane / 450 MHz. Verify each against the driver/overlay and the cited datasheet.
10. **CCMP12 / will127534 `rpi.hdr` patch** (art. 3 & 4): confirm CCMP12 is described only as planned/unverified, and that the patch is framed as cleanup/upstream-alignment (not a functional fix for `--hdr sensor`). Refute if the docs overstate the benefit.

## Output

Produce one report:

- **Findings**, most-severe first. Each: severity (Critical / Major / Minor / Nit); article + section/line; the exact claim; why it is wrong or unsupported; the correct value **with evidence** (`repo/path:line` or URL); suggested fix. Mark each **CONFIRMED** (proven against code/source) or **PLAUSIBLE** (suspected, needs a human check).
- **Cross-check contradictions** table: `claim | article says | docs/LLM-manual says | which is right | evidence`.
- **Per-article verdict**: a one-line confidence rating and the count of surviving findings.
- **What you could not verify** and the exact next check for each.

## Rules

- **Read-only.** Do not edit the docs or the code.
- Verify against the **actual files on the stated branches**, never from memory or plausibility.
- Cite evidence for every finding; unsupported assertions are not findings.
- Keep CONFIRMED separate from PLAUSIBLE. Do not pad the report — a short, high-signal list beats a long speculative one.
- If a doc's own hedge already covers a concern, say so and drop it.
