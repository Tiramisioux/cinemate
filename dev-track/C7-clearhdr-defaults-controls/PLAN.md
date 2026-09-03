# C7 · ClearHDR: INNO-MAKER defaults, HCG toggle, and the remaining driver controls

!!! success "Status 2026-09-03 — ClearHDR works on hardware"
    The operator confirms ClearHDR is functioning on the rig, so the feature half of this
    step is closed. Recorded as a working-system confirmation, **not** a gate sweep: G0–G3
    below were never run under those labels and no per-knob A/B was reported, so each gate's
    specific claim stays unverified rather than passed. In particular G1 — what the threshold
    pair's ordering does to the hand-off — remains an open question about the sensor, not a
    task blocking this step.

    **What is still open is where the code lives, not whether it works.** The cinemate half
    (`8dfcd165`: the INNO defaults, the `hcg` key, the consistency test) is on **no pushed
    branch in this repo** and is absent from both `dev` and `main` — it exists only on the
    operator's own checkout, so nothing here is recoverable from GitHub if that machine is
    lost. The cinepi-raw half is pushed but unmerged, one commit ahead of `dev` on
    `feature/clearhdr-controls`. A fresh install therefore does not get this feature.
    Pushing the cinemate half, then merging both, is the whole of the remaining work.

!!! note "Status 2026-08-26 — implemented on branches at filing time, no Pi time yet (historical)"
    Like C5, the code shipped the same day this was filed: cinemate
    `feature/clearhdr-controls` @ `8dfcd165`, cinepi-raw `feature/clearhdr-controls`
    @ `399692f`, driver fork `imx585-v4l2-driver` `6.12.y` @ `cb7c7a6`. All four
    verification gates below are unrun. Research plan (driver-source survey, control
    catalogue, verdicts) lives in the external workspace:
    `development/clearhdr-innomaker-defaults/PLAN.md`.

## What this is

Operator request: ship the INNO-MAKER ClearHDR defaults as Cinemate's defaults, and
implement whatever else the imx585 driver exposes that is worth having.

The driver-source survey found the whole "InnoMaker defaults" delta is **one control**:
the data-selection threshold. INNO ships `{4095, 0}`; the upstream will127534 lineage (and
the Tiramisioux 6.12.y driver the Pi runs) ships `{512, 1024}`; Cinemate's seeding wrote
`{0, 0}` with a +6 dB gain adder — matching nobody. Blend, gain adder, gradation curve,
HCG and black level already agree between the two drivers.

## What shipped

| Change | Where |
|---|---|
| Knob defaults → INNO values: threshold `{4095, 0}` (positional: low → `EXP_TH_H`, high → `EXP_TH_L`), blend 0, gain adder +12 dB (menu 2) | cinemate: `settings.jsonc`, `settings_default.jsonc`, schema defaults, `main.py` fallbacks, settings-editor field defaults |
| Consistency test pinning all five default copies + the canonical values | cinemate: `_test/test_clearhdr_defaults_consistency.py` (B9.5 pattern) |
| Driver ground truth aligned: `hdr_thresh_def {512,1024}` → `{0x0FFF, 0}` | driver fork `6.12.y` @ `cb7c7a6` (fresh installs pick it up via the installer pin; existing Pi needs a DKMS rebuild) |
| HCG (SDR high conversion gain): `image_capture.hcg` setting, `hcg` Redis key, `set hcg` / `toggle hcg`, settings-editor action (both catalogue copies) + toggle card | cinemate @ `8dfcd165` |
| `hcg` key → `IMX585_CID_HCG_ENABLE` (CID base + 6), applied live in SDR, stored-only in ClearHDR, startup restore SDR-gated (mirror of the HDR-knob magenta guard) | cinepi-raw @ `399692f` |
| ISO-ceiling warning: ClearHDR caps analogue gain at code 80 (≈15.8×, ~ISO 1580); `set_iso` warns above 1600 when a ClearHDR mode is active | cinemate @ `8dfcd165` |
| Docs: clear-hdr.md (defaults provenance, register mapping, HCG, ISO ceiling), settings-json.md, redis-keys.md, controller-methods.md ClearHDR section (knob setters were previously undocumented) | cinemate @ `8dfcd165` |

Checks at commit time: 550 pytest green (incl. the new test), `docs_drift_check --strict`,
`gui_field_extract --max-unresolved 0`, `redis_key_diff` (hcg lands in the shared
contract) — all pass. The cinepi-raw side compiles only on the Pi; not yet built.

## Deliberately not exposed (decision record)

| Control | Verdict | Why |
|---|---|---|
| Gradation knees + ACMP ratios (CID +2/+3/+4) | locked | `ccmp_lut.hpp` hardcodes this exact curve (500/11500, 1/64, 1/16); the CCMP12 preview decompand + DNG LinearizationTable + goldens all assume it. A runtime change silently mis-decodes every 12-bit ClearHDR DNG. Reopen only as its own feature with LUT + tag regeneration. |
| Black level (`BRIGHTNESS` → `BLKLEVEL`) | locked | DNG BlackLevel tag comes from tuning (3200 = 50×64); a live change desyncs tag vs pedestal → silently wrong DNGs. |
| INNO-only direct VMAX/HMAX/SHR (CID +7/+8/+9) | skip | Redundant — VBLANK/HBLANK/EXPOSURE reach the same registers and libcamera owns frame timing. Adopting means a driver swap to the unproven 3840×2200 INNO lineage. |
| Sync mode (`sony,sync-mode`, overlay param exists) | future C-step candidate | Boot-config dropdown exactly like the link-frequency one; enables dual-cam genlock (XVS/XHS wiring, own hardware session). |

## Verification gates (never run as specified — superseded by the working confirmation)

ClearHDR is confirmed working on hardware (see the status note above), so these gates no
longer block the step. None of them was executed under its own label, so nothing below
should be read as passed — the open questions each gate was written to settle, especially
G1's threshold-pair ordering, are still unanswered. Kept as written for whoever revisits
the knobs.

Pre-checks first, per the hardware-session method: `free -g` (which CM5), `uname -r`
≥ 6.12.93, both repos on `feature/clearhdr-controls`, rebuild cinepi-raw, DKMS-rebuild the
driver if the fork patch is pulled.

- **G0 — seeding lands.** Start cinemate; `v4l2-ctl -d /dev/v4l-subdevN --list-ctrls-menus`
  shows threshold `{4095, 0}`, blend 0, gain adder 2 after a ClearHDR mode is selected.
  Prediction: values match the Redis keys exactly.
- **G1 — the defaults A/B.** Same bright-highlight scene, 16-bit ClearHDR take at
  `{512, 1024}` vs `{4095, 0}`. Open question it settles: what the pair's ordering
  actually does to the hand-off (the two lineages' defaults are ordered opposite ways and
  the Sony app-note semantics are unknown). Look at the highlight knee and the magenta
  plateau.
- **G2 — HCG behaves.** In a 12-bit SDR mode: `toggle hcg` mid-stream — image steps
  cleaner shadows / earlier highlight clip; AE (12-bit) re-converges. In a ClearHDR mode:
  toggle logs the stored-only warning and the image does not change. Open question: the
  driver calls `imx585_update_gain_limits()` on HCG toggle — whether libcamera tolerates
  the mid-stream gain-range change is unknown until tried.
- **G3 — SDR regression re-check.** After using ClearHDR + knobs, an SDR launch leaves
  `EXP_GAIN` at 0 (the magenta-shadow-noise guard still holds with seeded keys always
  present).

Record outcomes in `cinemate-handbook/lessons/hardware-log.md`, then merge the two
implementation branches to `dev`.
