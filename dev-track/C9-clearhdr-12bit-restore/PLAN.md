# C9 · Restore 12-bit ClearHDR with working CCMP tone mapping

!!! note "Status 2026-08-31 — target is the mid-August CCMP state on `dev`; gates unrun"
    **Goal: 12-bit ClearHDR with correct CCMP tone mapping, as it worked in early-to-mid
    August** — not the 2026-08-27 mono milestone. The last known-good CCMP state is cinepi-raw
    `4b9c9f6` (2026-08-13); nothing touched the CCMP path between then and 2026-08-26.

    Two fixes are pushed (§S), but they address ClearHDR *starting*, not the tone mapping.
    The tone-mapping regression in §R is analysis only — nothing implemented, no Pi time.

    **Revised 2026-08-31** after the operator retargeted from the 08-27 mono milestone to the
    July / early-August functionality. An earlier audit also falsified §S's original causal
    claim; that correction stands.

## What this is

The target is the state in which **12-bit ClearHDR DNGs carry their CCMP12 decompand
`LinearizationTable` and the preview is decompanded** — the chart renders neutral instead of
purple. That was reached on cinepi-raw between `4aef539` (2026-08-09, the curve) and `4b9c9f6`
(2026-08-13, CCMP composed with CineMate Log), and evidenced in the measurement workspace by
`evidence/decode_anchored_asn.png`: *"the after. The purple is gone and the greys match."*

Restoring it is a different problem from the one this plan originally addressed. There are two
independent failures, and they need separating because they have different symptoms:

| | Symptom | Section |
|---|---|---|
| **Tone mapping lost** | ClearHDR records, but 12-bit takes render **magenta / purple** — companded data with no table | **§R** — the target |
| **ClearHDR won't start** | the HDR modes are absent from the table, or the launch dies | §S — two fixes pushed |
| **Pedestal fill** | ClearHDR starts, frames are flat at black level | §L2 — root cause unknown |

Everything else (§L0, §L1, §L3) is ground that has to be solid for any of the three.

---

## R — The tone-mapping regression (the target)

**Last known good: cinepi-raw `4b9c9f6`, 2026-08-13.** Between that and `bd39389` (08-26)
nothing touched the CCMP path — only docs, a dead-source deletion, CI, and a Redis perf change.
Then **three changes landed on 2026-08-27**, all of which bear on the same relationship: the
sensor's reported dimensions decide whether a CCMP table is attached at all.

### R1 — The CCMP gate now fails closed, and cannot disambiguate a mono sensor

`1f3383d` (the `milestone-mono-clearhdr-2026-08-27` tag itself) added `mode_trusted` to the gate:

```cpp
// cinepi/ccmp_gate.hpp
return (hdr == "sensor" || hdr == "auto") && sensor_mode_bit_depth == 12 && sensor_mode_trusted;
```

with `mode_trusted = (requested_width == cfg.size.width && requested_height == cfg.size.height)`
(`cinepi_raw.cpp:146`). When it is false, **no `LinearizationTable` is written**, and
`ccmpPreviewStage` returns instead of decompanding.

That was a deliberate, defensible choice — the commit reasons that a linear take mislabelled
with a decompand table is silently wrong everywhere, while a companded take missing its table
"renders magenta but is recoverable in post". **The magenta is the accepted cost of the guard.**
It is also exactly the symptom being reported.

And the gate's own header says it cannot do the job on this sensor:

> *"The R16 container is ambiguous between true 16-bit and mono 12-in-16, and dims alone cannot
> disambiguate it either (both land on 3856x2180 on this driver) — reading the sensor subdev's
> actual media-bus code would settle it and is a later, separate fix, out of scope here."*

So on `imx585_mono` the trusted check is known-insufficient by its own author, and its failure
mode is the reported symptom. **This is the leading hypothesis.**

### R2 — The driver changed the geometry out from under it, the same day

`02b2bec` (cinemate, 2026-08-27) flipped `IMX585_DRIVER_REPO_REF` from `6.12.y` to
`innomaker-v1.0`. Those drivers report **different dimensions**:

| | 6.12.y (what CCMP was measured on) | innomaker-v1.0 (what ships now) |
|---|---|---|
| full-res 12-bit | 3856×2180 | 3840×2160 (active-area dims) |
| binned 12-bit | 1928×1090 | **binned ClearHDR removed** — driver gates the combo out |
| 16-bit | — | 3840×2200 |

The workspace's 159 takes, both golden tables and `verify_dng_table.py`'s expectations are all
on the **left** column. `resources/sensors.json` still carries the left column's static modes
(1928×1090, 3856×2180). Anything comparing a requested dimension against a configured one is
now comparing across that change.

The compander itself is in the sensor, so the *curve* should be unaffected by a geometry change
— but three things that gate its use are not: `SensorBinning()` (derived from
`PixelArrayActiveAreas` ratios), `mode_trusted` (a dims equality), and the b=4 table (whose
mode no longer exists).

### R3 — The binning/bit-depth snapshot changed source

`042c68f` moved `SensorBinning()` and the encoder's bit-depth snapshot off `options->mode` and
onto the validated stream, to close a real race ("observed on hardware: a CCMP12 decompand b=4
table attached while the sensor actually ran a full-res (b=1) mode"). Correct in itself, but it
is the third same-day change to how dims reach the CCMP decision.

### The discriminator

One measurement separates all of this, and it is offline:

**Record ~2 s of 12-bit ClearHDR, copy one DNG off the Pi, and run
`tools/verify_dng_table.py` from `origin/docs/ccmp12-workspace`.**

| Result | Meaning |
|---|---|
| No `LinearizationTable` (tag 0xC618) at all | R1 — the gate refused. Look for the `Requested mode WxH does not match the configured raw stream` WARN in the cinepi-raw log; it names the reason. |
| Table present, matches a golden | Tone mapping is fine — the complaint is §S or §L2, not §R |
| Table present, matches the *other* golden (b=1 vs b=4) | R3 — binning derived wrong |
| Table present, matches neither | R2 — geometry changed the curve's inputs; the goldens need re-measuring on `innomaker-v1.0` |

Note `verify_dng_table.py` needs numpy, which is not on the Pi — run it on the machine that
holds the workspace. And the workspace is on a branch that is **not an ancestor of `dev`**
(`origin/docs/ccmp12-workspace` @ `21f1f1b`); check it out first.

### If the gate is the cause

Three options, cheapest first:

1. **Make the request match.** If cinemate is asking for dimensions the `innomaker-v1.0` driver
   does not deliver, the fix is in cinemate's mode table, not cinepi-raw's gate. Cheapest and
   most likely.
2. **Disambiguate properly.** Read the sensor subdev's media-bus code (`Y12_1X12` vs `Y16_1X16`)
   instead of comparing dims — the fix `1f3383d` explicitly deferred. cinepi-raw-side.
3. **Pin the old driver.** `IMX585_DRIVER_REPO_REF=6.12.y` restores the geometry the goldens
   were measured on. A diagnostic, not a destination — it gives up the `ccmp` overlay parameter
   and the mono gating that `02b2bec` was added for.

### Bisect anchor

If the discriminator is ambiguous, the range is short: **`4b9c9f6..origin/dev` contains only
six commits that touch CCMP** (`bd39389`, `042c68f`, `13155a6`, `1f3383d`, plus `58cf8cc` and
`22a1845` which do not). Building `4b9c9f6` on the Pi and recording one take answers "did the
tone mapping survive the driver change" directly.

---

## S — ClearHDR will not start (a separate failure, two fixes pushed)

This is the new finding, and it is the leading explanation for "it worked and now it doesn't".

**What changed.** cinepi-raw `58cf8cc` (2026-08-29, `dev` only — after the milestone tag)
made `Options::Parse()` **throw** when the sensor does not confirm `wide_dynamic_range=1`
within its retry window (5 attempts, ~200 ms), rather than launching against a combiner that
is off. That was the right call — it replaced silent pedestal-fill recordings with a loud
refusal.

**Why it fires.** cinepi-raw throws when **no subdev confirms the control**, which covers
several unrelated causes: the imx585 driver not bound or not the branch that exposes
`wide_dynamic_range`; every `open(/dev/v4l-subdevN, O_RDWR)` failing on permissions; a stale
cinepi-raw still holding the subdev; or a genuine sensor refusal. G0 and GR exist to tell
these apart — the driver-branch case is the most likely and the cheapest to check.

⚠ **`58cf8cc` does less than its title says.** It is titled *"verify wide_dynamic_range
actually landed before trusting it"*, but `set_subdev_hdr_ctrl` (`core/options.cpp:141-148`)
sets `confirmed` on a successful `VIDIOC_S_CTRL` and **never reads the control back** — the
only `G_CTRL` is the pre-write one. So "wrote but the sensor didn't take it" still passes
silently; the throw covers ioctl errors and no-subdev-found, not a sensor that ignored the
write. §R's earlier wording and gate G4 both assumed a confirmation the code does not
perform. A `VIDIOC_G_CTRL` read-back after the write is the cinepi-raw-side fix.

⚠ **Correction, 2026-08-31.** This section first claimed cinemate's own
`_set_wide_dynamic_range()` supplied the contention that trips the throw, and that it raced
the `--hdr sensor` probe. **The probe half is impossible** and the launch half is unproven:

- `_list_cameras()` is reached only from `detect_camera_model()`, which runs from
  `SensorDetect.__init__` — constructed at `main.py:621`. `CinePiController`, which owned the
  writer, is constructed at `main.py:754`. At probe time the writer did not exist.
  (`check_camera()` is the only other caller of `detect_camera_model()` and has zero callers.)
- On the launch path the two writes are separated by `_pace_resolution_change` (≥0.25 s),
  a `time.sleep(0.12)`, and `CinePiManager.restart()`, which itself shells out a full
  `cinepi-raw --list-cameras` (`cinepi_multi.py:186`) that runs `set_subdev_hdr_ctrl(0)`.
  cinemate's write is overwritten well before the launch that throws.

The removal in 87fa315 is still right — the writer was dead weight, it fired mid-take without
a relaunch, and it was a second writer on a control with no declared owner (see §P1 below).
But it is **a cleanup, not the identified cause of the regression.** The commit messages of
7097e3d and 87fa315 state the superseded story; this section is the correction of record.

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

1. ~~**Remove cinemate's second writer.**~~ **Done.** `CinePiController._set_wide_dynamic_range()`
   and its call from `_publish_resolution_gui_state()` are gone. cinepi-raw owns the control
   end to end — `Options::Parse()` forces it to 0, enumerates, sets it back to 1 for
   `--hdr sensor` and re-enumerates — so cinemate's write was discarded at the next launch
   anyway, and every SDR↔HDR transition is a relaunch by `_resolution_change_needs_restart()`.
   It bought nothing and supplied the contention. `set_resolution()`'s remaining contract is
   the `hdr` Redis key, which decides the launch flag.
   *This also removes a write that fired mid-take: `_is_recording()` short-circuits the
   restart decision but did not short-circuit the WDR write, so a mode change during a
   recording toggled the sensor's mode list with no relaunch to match it.*
   `_test/test_no_cinemate_wide_dynamic_range_writer.py` guards against it coming back —
   across all of `src/`, not just the one call path.
2. **Widen the retry, if the race persists.** 5 × 50 ms is short against a process teardown.
   With cinemate's writer gone the only remaining contender is a stale cinepi-raw, which
   `sensor_detect._kill_stale_cinepi_raw()` already handles — so if GR still shows refusals,
   the retry window is the next thing to look at. cinepi-raw-side, unpushed.
3. **The empty-guard asymmetry in `apply_hdr_thresholds`.** The startup restore path is
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

**On a Pi 5 / CM5 a main+main install does not produce a camera at all — never mind ClearHDR.**
cinemate `main` passes `--max-pixel-rate` on both probes (`sensor_detect.py:511`) and on every
launch (`cinepi_multi.py:533`), from `24a3968` (2026-08-29). cinepi-raw `main` has been frozen
since 2026-07-08 and has **no such option** (`git show origin/main:core/options.cpp | grep
max.pixel.rate` → nothing) and no `allow_unregistered`, so boost throws `unknown_option` and
every `cinepi-raw` invocation exits 255 before printing anything. `rp1_regime.pixel_rate()` is
non-`None` on any bcm2712 board, so the flag is always passed. This is a two-day-old break and
a better candidate than anything in §R for a recent "it worked and now it doesn't" on a
default install.

Beneath that: cinepi-raw `main` gates sensor HDR to `imx708` (`core/options.cpp:211`), so
there is no imx585 ClearHDR even if the flag problem is removed. cinemate `main` is closer but
lacks every end-of-August fix — `git diff origin/dev..origin/main` shows it missing
`test_clearhdr_threshold_defaults.py`, `test_wide_dynamic_range_retry.py`,
`test_clearhdr_self_heal.py` and 58 lines of `config_loader.py`, and still shipping
`threshold_low/high = 0/0`.

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

## P — Why this keeps breaking

Four independent ClearHDR outages in seven weeks is a pattern, not bad luck. The patterns
below are ranked by how much breakage they actually caused, each with instances.

### P1 — Every piece of ClearHDR-deciding state lives outside both programs, and no repo names an owner

Four things decide whether 12-bit ClearHDR works, and **not one of them is in either repo**:

| State | Where it really lives | How it broke |
|---|---|---|
| `wide_dynamic_range` | the sensor subdev | cinepi-raw took ownership at `b0bbd1a` (07-12); cinemate added a second writer at `ee49253` (07-14), **two days later**. It survived 48 days and three repairs (`c1831a1` added a retry to a write that should not have existed; `a05c97e` then restored a log line that retry had silenced) before `87fa315` deleted it. |
| the `dtoverlay` line | `/boot/firmware/config.txt` | `02b2bec` taught the installer to write `,ccmp` and never taught `boot_config.overlay_line_for()` to keep it. One settings-editor save deletes the 12-bit mode. Still open (L3-1). |
| the threshold pair | the driver's own defaults | cinemate re-seeded `0/0` over them on every boot until `bfea0be`. |
| the imx585 driver branch | a DKMS build on the Pi | `02b2bec` flipped the pin to `innomaker-v1.0`; every later fix assumes it, and **neither repo pins or tests the driver sha**. The ccmp12 workspace measured the *other* branch. |

This one pattern accounts for three of the four mechanisms in this plan.

### P2 — Cross-repo contracts are unpinned, untested, and currently broken

`versions.env:36` still reads `Last verified pairing: (none recorded yet)`. CI clones
cinepi-raw at a hardcoded `--branch dev` (`.github/workflows/checks.yml`), not from
`versions.env`, so no recorded pairing is ever what CI tests. The live consequence is L0's
`--max-pixel-rate` break: the same fix (`bfea0be`/`9f744fb`) was even authored twice and
reached `main` zero times.

### P3 — Silent failure is the default, and the guard written against it was gated onto the wrong branch

`05d896b` (08-17) added a fail-loudly guard **for exactly this failure mode** and gated it on
`if hdr_out.strip():` (`sensor_detect.py:634`). Twelve days later `58cf8cc` made the probe
throw — which returns empty stdout, which skips the guard. Same shape still open elsewhere:
`_finalize_modes` prunes ClearHDR modes with a bare `continue`, warning only if *every* mode
goes; `cinepi_multi.py:277` logs a launch exit at INFO and inspects no return code, so G4's
"throws loudly" prediction is currently uncheckable on the cinemate side.

### P4 — Causal stories get asserted without a discriminating measurement, then encoded as fact

`58cf8cc` turned a tolerated failure fatal with no audit of the other repo — and does not do
what its title claims (no read-back). `22a1845` rediscovered the prohibited-pair mechanism,
noted that escaping it "needs a large light transient at the sensor, which no software path
can produce" — the exact recovery signature rounds 8/9 recorded — then declared "same symptom,
different route" on a single register read. **And this plan did it too**: §R's first version
asserted a probe-contention story that `main.py:621` vs `:754` falsifies in a minute. Each of
these becomes a load-bearing premise for the next session.

### P5 — Mitigation-first debugging with no instrument that separates the defect from health

Six commits in 36 hours (`db3b4d4` → `65e60a8` → `f7cedba` → `e3963cb` → `24ee25f` →
`53bec8b`), ending with the discovery that the detector reads **1 unique value for a healthy
stream and 1 for a filling one** — it could not tell them apart — and the feature shipping
disabled. G2 and G3 are the work that should have preceded `db3b4d4`.

### P6 — The answer was already written down, on a branch no session sees

`origin/docs/ccmp12-workspace` @ `21f1f1b` (committed 08-10) records the prohibited
`EXP_TH_H < EXP_TH_L` state and that the sensor "only outputs the BLC pedestal", with a stated
next action. That branch forked at `9c57ef4` (07-07) and is not an ancestor of `dev`.
`22a1845` rediscovered it **20 days later**, after four hardware rounds spent on mitigations.
Reinforcing it: `SKILL-PAYLOAD.md`, the LLM-facing briefing, returns **zero** hits for
`ccmp|clearhdr|wide_dynamic|linearization|decompand`; `FINDINGS.md` (228 rows), both
`PI-RESULTS` files and `PI-VERIFICATION-QUEUE.md` contain no ClearHDR entry. **"Verified" in
this project has never once meant ClearHDR was verified.**

### P7 — Duplicated facts drift apart

Five-plus copies of the ClearHDR defaults. `app/main/events.py:73-74` still hardcodes
`threshold_low: 0` under a comment claiming it matches `main.py`. `overlay_line_for()`'s
docstring says it "matches concept.html's `cfgOverlayLine()` exactly" — so the `,ccmp` fix
has to land in two languages. C7's cinemate half is simply gone: `8dfcd165` is not a valid
object and no `feature/clearhdr-controls` exists on the cinemate remote.

---

## Prevention — what to add, beyond fixing this instance

The machinery already exists: `checks.yml` runs the full pytest suite, `docs_drift_check.py`,
`design_token_diff.py`, `link_frequency_drift_check.py`, and clones cinepi-raw to run
`redis_key_diff.py`. This class of fact just sits outside its reach.

| # | Add | Closes |
|---|---|---|
| 1 | `docs/state-ownership.md` in both repos: one table naming the single writer of `wide_dynamic_range`, `IMX585_CID_HDR_DATASEL_TH`, `hdr_blend`, `hdr_gain_adder`, `hcg`, the `dtoverlay` line, the driver branch | P1 |
| 2 | `tools/control_ownership_check.py` in CI — generalise `test_no_cinemate_wide_dynamic_range_writer.py` from one control to "no sensor subdev control has two writers" | P1 |
| 3 | `_test/test_boot_config_overlay_roundtrip.py` — every `DTO_OVERLAY=` literal in the installer must round-trip through `_model_from_overlay_value()` → `overlay_line_for()`. **Fails today.** | L3-1, P1 |
| 4 | Make CI clone cinepi-raw at `CINEPI_RAW_REPO_REF` and **fail when it is empty** — the only check that would have caught the `--max-pixel-rate` break | P2 |
| 5 | A launch-side mirror of `7097e3d`: non-zero `returncode` in `CinePiProcess.run()` logs at ERROR with stderr tail, plus a Redis key the GUI surfaces | P3 |
| 6 | A `VIDIOC_G_CTRL` read-back in cinepi-raw's `set_subdev_hdr_ctrl` before setting `confirmed` | P4 |
| 7 | `dev-track/C9-clearhdr-12bit-restore/RESULTS.md` as the gate-outcome destination — `cinemate-handbook/lessons/hardware-log.md` exists in neither repo | P6 |
| 8 | Merge `innomaker585/ccmp12-lut/` forward, and add a ClearHDR section to `SKILL-PAYLOAD.md` with a `docs_drift_check` assertion so it cannot silently freeze again. G5 depends on `tools/verify_dng_table.py` from that branch and never says to check it out | P6 |
| 9 | Add GT/G0/GR/G1–G6 to `PI-VERIFICATION-QUEUE.md` | P6 |
| 10 | **Pin the imx585 driver sha in `versions.env`** and record it beside the cinemate/cinepi-raw pairing. `02b2bec` changed the sensor's reported geometry with nothing recording which driver the CCMP goldens were measured against — the single largest untracked variable in this subsystem | P1, P2, §R2 |
| 11 | Re-measure or re-validate the CCMP goldens against whichever driver is pinned, and record the geometry they assume in `ccmp_decode.py`'s manifest | §R2, P7 |

---

## Verification gates

**Gate GT is the one that matters for this target — run it first.** The rest establish the
ground it stands on. Stop at the first failure. None of these need a chart.

Pre-checks first, per the hardware-session method: `uname -r` ≥ 6.12.93, `free -g`, both
repos' shas recorded, the **imx585 driver branch and sha recorded** (§R2 — this is now a
first-class variable, not background), and `v4l2-ctl --list-ctrls-menus` captured **before**
anything is changed.

- **GT — is a CCMP table being written at all? (tests §R, the target)** Record ~2 s of
  12-bit ClearHDR; copy one DNG off the Pi; run `tools/verify_dng_table.py` from
  `origin/docs/ccmp12-workspace` (needs numpy — run it where the workspace lives, not on the
  Pi). Read the cinepi-raw log for `Requested mode {}x{} does not match the configured raw
  stream` at the same time.
  *Prediction, if R1 is right: no `LinearizationTable` in the DNG, and that WARN present with
  the two dimension pairs that disagree.* The outcomes that falsify R1: a table present and
  matching a golden (then the complaint is §S or §L2, not §R), or no table **and no WARN**
  (then the gate is not the refuser and something else drops it).
  This is the whole diagnosis in one measurement; everything below is context for reading it.
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
  instrument the rest depend on. A refusal here names one of §R's causes; G0 settles the
  driver-branch one.
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
- **G5 — the DNG is correct at both resolutions.** GT covers one mode; this repeats it at
  the other, if the driver still offers one. Run `tools/verify_dng_table.py` against both
  goldens.
  *Prediction on the 6.12.y geometry: byte-identical to the b=1 golden at 3856×2180 and the
  b=4 golden at 1928×1090, BlackLevel 200, WhiteLevel 63265 / 62704.* ⚠ On
  `innomaker-v1.0` there is **no binned ClearHDR mode**, so the b=4 golden is unreachable and
  the full-res dims are 3840×2160, not 3856×2180 — see §R2. A `b=1` reading on both modes (if
  two exist) means `PixelArrayActiveAreas` is not reporting what the binning derivation
  assumes; stop and report.
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
