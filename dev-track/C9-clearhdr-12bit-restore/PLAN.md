# C9 · Restore working 12-bit ClearHDR

!!! note "Status 2026-08-31 — target is `dev`; one fix pushed, gates unrun"
    **Goal: 12-bit ClearHDR working on `dev` again.** Written against cinemate `origin/dev`
    @ `db2f483` and cinepi-raw `origin/dev` @ `24fd76a`. No Pi time. Every prediction below
    is stated in advance so a hardware session can falsify it, per the C5/C7 method.

    One fix is implemented: the probe-failure diagnostic in §R. Everything else is analysis.

## What this is

12-bit ClearHDR worked on `dev` at the `milestone-mono-clearhdr-2026-08-27` tag and does not
now. This step is the restore path, targeting `dev`.

The important finding up front: **this is not one defect.** It is four independent problems,
and they have to be cleared in order, because the earlier ones make the later ones impossible
to observe.

| Layer | Problem | State |
|---|---|---|
| R | A ClearHDR probe failure is swallowed, so the HDR modes vanish silently | **fix pushed**, needs the Pi to confirm the cause |
| L0 | `dev` is not what a camera runs unless it is explicitly asked for | not fixed — one-line operator config |
| L1 | Three ClearHDR defects, root-caused and fixed **on `dev`** | fixed; `main` does not have them |
| L2 | A boot-latched combiner pedestal fill | **root cause unknown** |
| L3 | Four regression traps that can silently re-break it | one fixed below, three open |

---

## R — The regression on `dev` since the milestone

This is the new finding, and it is the leading explanation for "it worked and now it doesn't".

**What changed.** cinepi-raw `58cf8cc` (2026-08-29, `dev` only — after the milestone tag)
made `Options::Parse()` **throw** when the sensor does not confirm `wide_dynamic_range=1`
within its retry window (5 attempts, ~200 ms), rather than launching against a combiner that
is off. That was the right call — it replaced silent pedestal-fill recordings with a loud
refusal.

**Why it fires.** The subdev is under contention at exactly that moment. cinemate's own
`CinePiController._set_wide_dynamic_range()` writes the same control from
`_publish_resolution_gui_state()`, before the relaunch that will own the new mode — and its
docstring records the round-6 hardware finding verbatim: it "logged 'no subdev accepted' on
effectively every resolution change all session". Two independent writers, one control, and
cinepi-raw's own re-enable is the one that now has a hard deadline.

**Why nobody saw it.** `sensor_detect._list_cameras()` ran the probe and returned
`proc.stdout or ""` — **the exit code was never checked and stderr was discarded**. A thrown
HDR probe exits non-zero with an empty stdout, which was byte-for-byte indistinguishable from
the legitimate "this build has no ClearHDR" case the function was written for. So:

    probe throws -> stdout "" -> parsed as {} -> _merge_mode_lists adds nothing
                 -> the ClearHDR modes are simply absent from the mode table, silently

The operator sees a camera that no longer offers 12-bit ClearHDR, with nothing in the log.
On a real launch (not the probe) the same throw kills the process outright.

This fits the symptom change exactly: before `58cf8cc` the failure produced bad images
(pedestal fill); after it, the modes disappear or the launch dies. The milestone tag predates
the throw.

**Fixed here:** `_list_cameras()` now checks the exit code and logs stderr, and on the HDR run
names the likely cause and its consequence. Behaviour is deliberately unchanged — still `""`,
still best-effort, because a genuine no-ClearHDR build must keep working. The difference is
that it now says so. `_test/test_sensor_detect_probe_failure.py` pins both directions,
including that a healthy probe stays silent.

**This is a diagnostic, not a cure.** It does not fix the race. It converts an invisible
failure into a visible one, which is the prerequisite for every gate below — without it, G0
and G4 cannot distinguish "no ClearHDR support" from "ClearHDR refused to start".

### What still needs doing on the cinepi-raw side

I have read-only access to cinepi-raw, so these are recommendations, not pushed changes:

1. **Widen or back off the retry.** 5 × 50 ms is short against a process teardown. Either
   extend it, or have cinemate stop writing `wide_dynamic_range` altogether and leave the
   control to cinepi-raw, which forces it off and back on anyway — cinemate's write is
   discarded by design at `Options::Parse()`, so it buys nothing and supplies the contention.
   *Removing cinemate's writer is the cleaner fix and is cinemate-side, so it can be done here.*
2. **The empty-guard asymmetry in `apply_hdr_thresholds`.** The startup restore path is
   correctly gated (`cinepi_controller.cpp:297`: skip when both keys are empty). The live
   handler is not: `build_hdr_threshold_pair` turns `""` into `0`, and `{0,0}` passes its own
   `high < low` guard, so a publish of an unset threshold **writes the degenerate pair** that
   `bfea0be` exists to prevent. `22a1845` says the two handlers "share one applier so the
   guard cannot drift" — the `high >= low` guard is shared, the empty check is not.

---

## L0 — `dev` is not what a camera runs

`cinemate-install.sh:84` and `:82` leave `CINEPI_RAW_REPO_REF` and `CINEMATE_REPO_REF` empty.
`ensure_repo()` (`:397-409`) with an empty ref runs a plain `git clone`, landing on each
repo's default branch — **`main`**.

That matters more for cinepi-raw than for cinemate. cinepi-raw `main` is `774402c`
(2026-07-08), 59 commits behind `dev`, and `core/options.cpp:211` gates sensor HDR to
`imx708` — imx585 is not in it, so there is no ClearHDR at all. cinemate `main` is closer but
still lacks every end-of-August fix: `git diff origin/dev..origin/main` shows it missing
`test_clearhdr_threshold_defaults.py`, `test_wide_dynamic_range_retry.py`,
`test_clearhdr_self_heal.py` and 58 lines of `config_loader.py`.

Note `main` and `dev` have **diverged** — `main` is 3 merge commits ahead of `dev` as well as
24 behind, so this is not a fast-forward.

**For the stated goal, L0 is one line of operator config**, not a merge:

```sh
CINEMATE_REPO_REF=dev CINEPI_RAW_REPO_REF=dev ./cinemate-install.sh
```

Merging `dev` → `main` is the separate release question and is deliberately **not** part of
this step. But `versions.env:36` still reads `Last verified pairing: (none recorded yet)`, and
that should be filled in the moment a working combination is found — it is the whole point of
the file.

---

## L1 — Root-caused and fixed on `dev`

Three separate defects, each hardware-motivated, each already closed:

**1. The WDR enable write silently failed.** `Options::Parse()` forces
`wide_dynamic_range` off, calls `initCameraManager()`, then tries to turn it back on —
and that write can lose an EBUSY race against the `initCameraManager()` that just ran.
`set_subdev_hdr_ctrl()` returned `false` for both "already at target" and "wrote but the
sensor didn't take it", so the caller could not tell them apart; it forced `hdr = "sensor"`
anyway and launched, **requesting a 12-bit ClearHDR pixel format from a sensor whose
combiner was never turned on**. That is the driver's documented invalid combo: a BLC
pedestal fill (~200) with every knob inert against it.
Fixed: cinepi-raw `58cf8cc` (retry, then throw) + `4ff1174` (report at startup too).
Reproduced on hardware: plain 12-bit → 12-bit ClearHDR hits it reliably; HDR→HDR does not,
consistent with only a real 0→1 transition having a write to race.

**2. Cinemate seeded the one threshold pair the driver deliberately avoids.**
`threshold_low: 0, threshold_high: 0` went into Redis on every boot, and cinepi-raw applied
it to the sensor on every ClearHDR selection. `EXP_TH_H == EXP_TH_L` selects the AppNote's
weighted-blend fallback, where the combiner output stays clamped near black — measured at a
16-bit DNG maxing around 4200 against ~36000 with the rule-based range. The shipped default
overwrote a deliberately-chosen good driver value with the rejected one, on every startup,
and nothing logged it.
Fixed: cinemate `bfea0be`/`9f744fb` — thresholds default to `null`, seeding `""` = "write
nothing, keep the driver's own pair". **Still `0/0` on `main`.**

**3. The threshold pair went out backwards.** The driver takes a `u16[2]` and writes
`th[0] → EXP_TH_H`, `th[1] → EXP_TH_L`; all three call sites built `{low, high}`. Born at
cinepi-raw `4e9850a` (2026-07-14), so it was wrong for six weeks. The spec marks
`EXP_TH_H < EXP_TH_L` as Prohibited — the sensor "enters an invalid state and only outputs
the BLC pedestal" — which means `docs/clear-hdr.md`'s own advice (`low 500`, `high 3000`)
was writing the prohibited state as documented.
Fixed: cinepi-raw `22a1845` — order corrected, pair validated before any write, violating
pair refused with a warning. Confirmed over I2C on hardware before changing anything.

**L1 needs no new code on `dev`.** It needs L0 (be running `dev`) and R (be able to
see it when ClearHDR refuses to start).

---

## L2 — The boot-latched pedestal fill (root cause unknown)

What rounds 6–9 established, on hardware:

- The combiner can start up latched into a flat pedestal at ~4.9% of full scale
  (3200/65535 — exactly `BlackLevel`).
- **Identical in 12-bit CCMP and 16-bit linear ClearHDR**, which rules out the decompand
  path and every software cause downstream of the sensor.
- Every sensor register reads correct while it is happening.
- `22a1845`'s scope note is explicit that this is **not** the threshold bug: during every
  fill measured on 2026-08-30 the registers read the valid driver defaults
  (`EXP_TH_H=0x0FFF`, `EXP_TH_L=0x0000`), and setting a valid mid-scale pair did not clear
  it. Same symptom, different route.

What clears it, and what does not:

| Action | Result | Source |
|---|---|---|
| Covering the sensor by hand | **clears it** | round 8, live 2026-08-29 |
| Flashing a light at the sensor | **clears it** | round 8 |
| Shutter angle → 1° and back (manual) | **clears it** | round 8, operator-confirmed |
| Analogue-gain shock (min→max) | does **not** clear it | live-tested, `f7cedba` |
| Mode bounce (away and back) | does **not** clear it | live-tested, `65e60a8` |

### Hypotheses (mine, from the recorded evidence — not established)

**H2 — the latch is signal-dependent, not register-dependent.**
Every confirmed recovery drives the *photoelectron count* toward zero: covering the sensor,
a 1° shutter, and a light flash all do. The one action that changes an amplifier setting
without changing integrated signal — the gain shock — is also the one that failed. If that
holds, the combiner re-converges when it sees a near-black frame, and no register write can
substitute for one.
*Prediction:* any action that drives integrated signal to near zero clears it; any action
that only changes gain does not. Falsified if a gain shock ever clears it, or if a 1°
shutter ever fails to.

**H3 — the latched state survives a process restart.**
Neither a cinepi-raw relaunch nor a mode bounce power-cycles the sensor, so a combiner latch
would persist across both — which is exactly what the mode-bounce failure looks like. If so,
**any test of an L1 fix that does not power-cycle the sensor can still show the fill**, and
several round 6–9 observations may have been measuring a latch entered before the fix.
*Prediction:* full power removal clears it; `sudo reboot` may not, if the sensor rail stays
up. This is cheap to test and, if true, changes how every subsequent gate must be run.

H3 is the higher-value one to test first, because if it holds it partially invalidates the
round 6–9 negative results and L2 may be smaller than it currently looks.

### The self-heal is correctly disabled — leave it off

`24ee25f` gated the self-heal behind `image_capture.hdr.self_heal`, default false, and
`53bec8b` records why in the docstring: on the bench rig a healthy low-contrast ClearHDR
stream and a genuine pedestal fill **both** measure 1 unique value in the preview body.
Same reading, opposite sensor states. The detector cannot justify an automatic recovery
action, and it fires from `start_all()`, which every cold start and every resolution switch
funnels through.

One inconsistency to fix while here: `cinepi_multi.py:44-58` says the shutter kick cleared
it "live on 2026-08-29", while `24ee25f` and `clearhdr_self_heal_enabled()`'s docstring both
say only the *manual* shutter change is operator-confirmed and the automated form has never
run on the rig. The module comment overstates it; the docstring is right.

---

## L3 — Regression traps

**1. Saving the Boot config page strips `,ccmp` from the overlay.**
The installer writes `dtoverlay=imx585,${cam_port},ccmp` (`cinemate-install.sh:1010,1014`),
and `docs/clear-hdr.md` states that without `ccmp` the 12-bit CCMP mode does not exist on
this driver. But `boot_config.overlay_line_for()` (`src/module/app/boot_config.py:139-161`)
emits `dtoverlay={base},{port}{mono}{link}` with no `ccmp`, and
`_model_from_overlay_value()` (`:163-191`) filters the token away without ever reading it
back. So **one save from the web settings editor silently deletes the 12-bit ClearHDR mode
at the next reboot.** This is a strong candidate for "it was working and then it wasn't".

**2. A kernel package upgrade silently restores the stock `rp1-cfe`**, reverting the mono
Y16 patch — mono 16-bit then records PiSP-COMP1-structured garbage.
`docs/clear-hdr.md` says to rerun `scripts/patch-rp1-cfe.sh` after any kernel upgrade;
nothing enforces it.

**3. No recorded pairing.** L0's `versions.env` gap means any working combination found is
not reproducible by anyone else.

**4. `docs/clear-hdr.md` still teaches the broken configuration** — it documents `0,0` as
"Cinemate's shipped default", and its Symptom→knob table still recommends `set hdr
threshold low 500 / high 3000`, the pair whose order was inverted until `22a1845`. Neither
`bfea0be` nor `22a1845` touched it.

---

## Verification gates

Run in order; stop at the first failure. Gates 0–3 need no chart and no operator at the
camera. Pre-checks first, per the hardware-session method: `uname -r` ≥ 6.12.93,
`free -g`, both repos' shas recorded, `v4l2-ctl --list-ctrls-menus` captured **before**
anything is changed.

- **G0 — the camera is running `dev`.** `git -C ~/cinepi-raw rev-parse --abbrev-ref HEAD`
  and the same for `~/cinemate`. The cinepi-raw tree must contain `imx585` in
  `core/options.cpp`'s HDR gate and have `cinepi/ccmp_lut.hpp`.
  *Prediction: on an install that never set the REPO_REFs, both are on `main` and both
  checks fail.* This gate exists to make L0 visible rather than assumed.
- **GR — the probe failure is now visible (tests R).** Start cinemate and read the log.
  *Prediction: either the ClearHDR modes are present, or there is now a `cinepi-raw
  --list-cameras ... --hdr sensor' exited N` warning naming `wide_dynamic_range`.* The
  outcome that falsifies R's hypothesis is modes missing **with no warning** — that would
  mean the probe exited 0 and something else drops them. Run this before G2/G3: it is the
  instrument the rest depend on.
- **G1 — the stack builds and its own tests pass.** `ninja -C ~/cinepi-raw/build` then
  `meson test -C ~/cinepi-raw/build` — 8 suites including `ccmp_lut`, `ccmp_log_compose`,
  `ccmp_preview`, `ccmp_gate`. Float determinism against the golden tables is not automatic
  on the Pi's compiler and this is one command.
- **G2 — H3, the power-cycle discriminator.** Provoke the fill, then in order:
  (a) mode bounce, (b) `sudo reboot`, (c) full power removal for 10 s. Record which clears
  it. *Prediction: (a) fails, (c) works; (b) is the informative one.* If (b) fails and (c)
  works, the latch outlives a warm reboot and every earlier negative result needs re-reading.
- **G3 — H2, the signal discriminator.** In the fill state, with the lens capped:
  gain shock, then shutter → 1°, then uncap and cover by hand. *Prediction: gain fails,
  both signal-side actions work.* Falsifying this kills H2 cleanly.
- **G4 — the L1 fixes hold.** Cold start into 12-bit ClearHDR from a plain 12-bit mode
  (the transition `58cf8cc` says reliably hit the WDR race). *Prediction: it either launches
  with a confirmed WDR enable or throws loudly — never a silent pedestal launch.* Then
  `v4l2-ctl` readback shows the driver's own `EXP_TH_H=0x0FFF / EXP_TH_L=0x0000` pair, not
  `0/0`.
- **G5 — the DNG is correct.** Record ~2 s at both resolutions; run
  `tools/verify_dng_table.py` from the `ccmp12-lut` workspace against both goldens.
  *Prediction: byte-identical to the b=1 golden at 3856×2180 and the b=4 golden at
  1928×1090, BlackLevel 200, WhiteLevel 63265 / 62704.* A `b=1` reading on **both** modes
  means `PixelArrayActiveAreas` is not reporting what the binning derivation assumes —
  stop and report.
- **G6 — the overlay trap.** Save the Boot config page unchanged from the web editor, then
  `grep dtoverlay /boot/firmware/config.txt`. *Prediction: `,ccmp` is gone.* Fix before
  closing this step.

Record outcomes in `cinemate-handbook/lessons/hardware-log.md`.

---

## Not in scope

- **The gradation curve and black level stay locked** (C7's decision record). `ccmp_lut.hpp`
  hardcodes the 500/11500, 1/64, 1/16 curve and the DNG `LinearizationTable` and goldens all
  assume it; a runtime change silently mis-decodes every 12-bit ClearHDR DNG.
- **C7's own deliverables** (INNO knob defaults, HCG, ISO-ceiling warning) are a separate
  step and depend on this one. Note that C7's cinemate branch `feature/clearhdr-controls`
  **does not exist on the remote** — only the cinepi-raw half (`399692f`) was pushed, so
  C7's "implemented on branches" status is half-true and its cinemate work may be lost.
- **The 16-bit optical-black rows** (20 rows, no `ActiveArea`/`MaskedAreas` tags, black bar
  across the top of every 16-bit ClearHDR DNG) — a real defect, raised in the ccmp12
  workspace, deliberately not bundled here.

## Provenance

The measurement behind the decompand curve lives on cinemate branch
`docs/ccmp12-workspace` @ `21f1f1b`, in `innomaker585/ccmp12-lut/` — 40 analysis tools, the
emitted golden tables, and `CCMP12-ANALYSIS-HANDOFF.md`. Start there before touching the
curve. Note the takes themselves (159 DNGs, 1.3 GB) are gitignored and live only on the
operator's machine.

`system-review/deliverables/SKILL-PAYLOAD.md` — the LLM-facing working reference — contains
**zero** ClearHDR content (grep for `ccmp|clearhdr|wide_dynamic|linearization|decompand`
returns 0). It froze 2026-08-23, four days before the milestone tag. Any agent handed that
file as its briefing will not know this subsystem exists.
