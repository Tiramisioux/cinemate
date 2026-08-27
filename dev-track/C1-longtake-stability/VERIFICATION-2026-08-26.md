# C1 verification pass — findings (2026-08-26)

Adversarial pre-flight verification of `RUNBOOK.md`, run **before any Pi time**.
7 dimensions checked in parallel against the real sources, then **every** non-OK finding
was independently re-verified by a second agent instructed to refute it.

**Result: 49 claims verified correct; 72 problems raised; 59 upheld, 13 refuted.**
Upheld: **4 blocker · 35 major · 20 minor**.

A finding is listed only if a skeptical second reviewer reproduced it against the source.
`FIX` text is the **adjudicated** fix (the second reviewer's), which sometimes corrects or
replaces the original critic's proposal — apply these, not the raw critique.

> Status: **not yet applied to RUNBOOK.md** except where noted in the runbook's own
> changelog. Work through this file top-down; blockers first.


---

## BLOCKERS — campaign cannot run / data would be invalid (4)

### B1 · [helper-commands] 

**Claim checked:** Step 8 evidence capture: "`session-tail 400` → save to the archive as `session-log.txt`; separately grep the take window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory`"

**Evidence:** cinepi-raw logs one line per recorded frame: /Users/patrikeriksson/Documents/cinemate/cinepi-raw/cinepi/dng_encoder.cpp:1529 `console->info("DNG written: {}", filename);`. cinemate forwards every cinepi-raw stdout/stderr line into the root logger: src/module/cinepi_multi.py:271-282 (`_pump` -> `_log` -> `logging.info`), and the default filter set (cinepi_multi.py:211-218: frame/stats/agc/ccm/vu) does NOT match "DNG written". The console handler (src/module/logger.py:137, StreamHandler -> stderr) is redirected into the session log by cinemate_dev.py:590 (`nohup bash -lc ... >/tmp/cinemate_cli.log 2>&1 &`). Verified live on the Pi: `grep -c 'DNG written' /home/pi/cinemate/src/logs/system.log` -> 95 for a 95-frame take, each line ~210 chars. At the campaign's fps cap of 25 (Phase 0.5), a 5-min take emits 25*300 = 7,500 DNG lines (~1.6 MB) and a Stage-2 10-min take 15,000. `tail -n 400` therefore covers only the last ~16 s of a 300 s take, so the mandated grep over "the take window" is impossible and every take's session-log.txt is truncated evidence.

**Fix (adjudicated):**

Replace the first bullet of Stage 1 step 8 (RUNBOOK.md lines 255-257) with:

```
   - Copy the **whole** session log, not a tail. `cinepi-raw` logs one `DNG written:` INFO
     line per frame (`dng_encoder.cpp:1529`) and cinemate relays it into the session log
     unfiltered (`cinepi_multi.py:211-218` filters only frame/stats/agc/ccm/vu), so a
     5-minute take is 3,300 lines (mode A @ 11 fps) to 7,500 (mode C @ 25 fps) and
     `session-tail 400` would cover only its last 16-36 s. Copy it **now**, before the next
     `session-start` — that command `rm -f`s `/tmp/cinemate_cli.log` and cinemate's own
     startup wipes `/home/pi/cinemate/src/logs/*.log`, so nothing survives it:
     `~/.claude/skills/cinemate-dev/scripts/pi_expect.exp "$PI_PASSWORD" scp -o StrictHostKeyChecking=accept-new pi@cinepi.local:/tmp/cinemate_cli.log <archive>/session-log.txt`
     Then grep the **copied file** (not the Pi, not a tail) with
     `grep -Ein 'write.*fail|FAILED|xrun|overrun|drop|SYNC|memory' <archive>/session-log.txt`
     and record every hit in the ledger with its line number and timestamp. Always record
     the copied file's total line count alongside the hit count, so a genuine "0 hits" is
     distinguishable from a truncated log. `wc -l` should be within ~10% of
     `frames_requested`; if it is far below, the copy is incomplete — re-copy before
     classifying the take. The `session-tail 100` polling in step 6 is live progress only
     and is never evidence.
```

Two knock-on edits required for consistency:

1. RUNBOOK.md line 98 — change `per-take analysis JSON, sampler CSV, session-log excerpt, the WAV, and first/last 3 DNGs.` to `per-take analysis JSON, sampler CSV, the full session log (~2-4 MB of text; gzip it if you prefer), the WAV, and first/last 3 DNGs.`

2. Phase 0.4 — append after the `df -B1 /media/RAW` sentence: `Also record ``df -h /tmp`` — if ``/tmp`` is a tmpfs rather than the boot media, the per-take session log (thousands of ``DNG written`` lines, a few MB) is competing with the DNG RAM buffer on this 2 GB unit; note it in the ledger as a confound and copy the log off promptly after every take.`

### B2 · [redis-and-cli] 

**Claim checked:** Audio PASS/WARN/FAIL: "zero xrun/overrun lines in the session log for the take window" (and the per-take grep includes xrun|overrun)

**Evidence:** Neither token is ever emitted for an actual audio loss. The only line in either repo containing "xrun" is the OPPOSITE condition — /Users/patrikeriksson/Documents/cinemate/cinepi-raw/cinepi/cinepi_sound.cpp:864 `"cinepi-audio-capture helper not found; falling back to plain arecord without precise audio-start markers or xrun silence-fill"`; "overrun" appears only in comments. The real loss marker is cinepi_audio_capture.cpp:663-668 `Inserted <N> silent frame(s) to cover a capture shortfall of <X>s; WAV stays aligned to wall clock`, relayed into the session log as `Audio capture helper: Inserted ...` (cinepi_sound.cpp:1237, helper stdout+stderr merged by the `2>&1` at cinepi_sound.cpp:862). This makes the audio verdict self-defeating: the silence-fill exists precisely to keep the WAV wall-clock length, so the runbook's duration check ALSO passes when samples were lost — every take would score PASS regardless of real audio loss.

**Fix (adjudicated):**

TWO edits are required — fixing the criteria alone leaves the evidence uncaptured by the step-8 grep.

EDIT 1 — replace RUNBOOK.md lines 152-156 (the three audio verdict bullets) with:

- **PASS** — WAV present; `|wav_duration − dng_count/fps_target| ≤ 0.5 frame period`; and **zero
  silence-fill lines** in the session log for the take window.
- **WARN** — deviation ≤ 1 frame period, or ≤ 2 silence-fill lines totalling < 20 ms.
- **FAIL** — deviation > 1 frame period, missing WAV, silence-fill totalling ≥ 20 ms or any
  single fill ≥ 1 s, or any of: `Capture read failed`, `WAV writer: disk write failed`,
  `Stopping capture after WAV writer disk error`, `Audio capture helper exited before capture
  actually started`. On FAIL, run the sync-matrix deep-dive method before writing the verdict.

**Why duration alone proves nothing.** `cinepi-audio-capture` reconciles against a running
wall-clock anchor and pads any shortfall with silence
(`cinepi_audio_capture.cpp:656-668`), so the WAV keeps its wall-clock length *whether or not
samples were lost*. `<SAMPLES_CAPTURED>` is padded too (`framesCaptured` includes the inserted
silence, `cinepi_audio_capture.cpp:662,712`), and the analyzer does no waveform analysis. The
silence-fill log line is the **only** loss signal in the stack. Note also that the strings
`xrun` and `overrun` are never emitted for a loss — the one `xrun` line in the codebase
(`cinepi_sound.cpp:864`) is the helper-*missing* fallback warning.

The marker, emitted at `cinepi_audio_capture.cpp:663` and relayed to the session log as
`Audio capture helper: ...` (`cinepi_sound.cpp:1237`, helper stderr merged by the `2>&1` at
`cinepi_sound.cpp:862`), reads:

    Audio capture helper: Inserted <N> silent frame(s) to cover a capture shortfall of <X>s; WAV stays aligned to wall clock

Per take, extract and record **both** the fill-line count and the summed inserted seconds:

```bash
grep -Eo 'Inserted [0-9]+ silent frame\(s\) to cover a capture shortfall of [0-9.]+s' session-log.txt \
  | awk '{n++; s+=$(NF)} END {printf "silence_fills=%d total_inserted_s=%.4f\n", n+0, s+0}'
```

Calibration: the helper runs a 10 ms ALSA period and only fills shortfalls larger than
`periodFrames/4` (~2.5 ms at 48 kHz), a threshold chosen specifically so SCHED_FIFO scheduling
jitter does *not* trigger spurious fills — so on a healthy rig the expected count is **zero**,
and any nonzero count is a real capture stall. A single fill is capped at 5 s
(`maxGapFrames = rate*5`), so a stall longer than that also shortens the WAV and will show up
in the duration term as well.

**A nonzero fill count with a clean duration is the campaign's key audio datum** — it is the
exact signature of storage-contention sample loss, the historical root cause named above.
Record it for every take even when the verdict is PASS-adjacent.

EDIT 2 — RUNBOOK.md line 256, the per-take evidence grep. Replace the pattern
`write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` with:

    write.*fail|FAILED|silent frame\(s\)|Capture read failed|WAV writer|Stopping capture after|exited before capture|drop|SYNC|memory

The old pattern matches none of the silence-fill, WAV-writer-abort, or helper-early-exit
lines (verified against the emitted strings), so the primary audio evidence was never being
collected.

ALSO: in `RESULTS.md`, rename the `xruns` column in both take tables (lines 91 and 152) to
`silence fills / inserted ms` — as written that column is structurally guaranteed to read zero.

### B3 · [executability] 

**Claim checked:** OVERALL VERDICT: a cold Sonnet session can execute this runbook top-to-bottom without inventing anything.

**Evidence:** Walking the runbook as the executing session, I hit ≥7 blocker-class points where I would have to invent a value, a command, or a decision rule. The most consequential: (a) no rule for deriving the take directory that steps 8/9/10 depend on; (b) the fps values the 0.5 formula produces are silently snapped to a different value by `set fps`; (c) dynamic resolution silently overrides `set resolution` in the prescribed C→B→A order; (d) `session-tail 400` cannot cover a take; (e) the session log is deleted by the next take before it is archived; (f) the referenced sync-matrix deep-dive method does not exist on disk; (g) no archive mechanism is named. Each is detailed as its own finding below.

**Fix (adjudicated):**

Five edits, all runbook text. Findings 1–3 are mandatory before any Pi time; 7 (session-log deletion order) must be dropped from the critic's list.

(1) INSERT a new Phase 0 step after 0.2, and reference it from Stage 1 step 2:

0.2b **Pin the two runtime behaviours that would otherwise rewrite your test conditions.** Both are shipping defaults, both are session state (not file edits), and `session-start` resets them — so re-apply and re-verify **after every `session-start`**, before step 2 of every take. Log both once in the interventions table.
  - `set dynamic resolution 0` — dynamic resolution is on by default (`docs/sensors.md`: "Cinemate always runs dynamic resolution"). While it is on, `set resolution <n>` is silently replaced by the largest mode that can sustain the *current* `fps_user`: after any 25 fps take, both `set resolution <B>` and `set resolution <A>` land back on the 25 fps control mode. Verify: `redis-cli GET dynamic_resolution_enabled` must read `0`.
  - `set fps free 1` — with free mode off, `set fps` snaps to the nearest entry of `arrays.fps.steps` (`[25, 33, 50]` in `settings.jsonc`), and every entry above the mode's `fps_max` collapses to `fps_max` itself. For any mode with `fps_max < 25` — modes A and B on this sensor — *every* `set fps <n>` returns exactly `fps_max`, so the 0.5 formula cannot be applied at all. Verify: `redis-cli GET fps` after each `set fps` must equal the 0.5 test fps, not `fps_max`.
  If either verification fails, STOP and report — do not proceed with a substituted mode or a snapped fps.

(2) REPLACE Stage 1 steps 2–3 with:

2. Re-apply the 0.2b pins for this session (`set dynamic resolution 0`, `set fps free 1`), then set the mode: `set resolution <n>`.
3. Set the mode's 0.5 test fps: `set fps <test_fps>`. **Then** verify all four readbacks together — `resolution_target_width`, `resolution_target_height`, `resolution_target_bit_depth`, and `fps` — against the plan. If `fps` came back as the mode's `fps_max`, free mode did not take; if the resolution readbacks name a different mode, dynamic resolution is still on. Either one: STOP, do not record the take. Confirm the rate again from two `framecount` samples ~10 s apart during the take (step 6), never from `fps_actual`.

(3) REPLACE the first bullet of Stage 1 step 8 with:

  - Session log — **do not use `session-tail` for this**. The helper log `/tmp/cinemate_cli.log` carries one `DNG written:` line per frame, so a 5-minute take is 3,500–7,500+ lines and `session-tail 400` covers only the last 15–35 seconds. Copy the whole file to the archive as `session-log.txt`, then run the warning grep on the Pi against the whole file:
    `grep -inE 'write.*fail|FAILED|xrun|overrun|drop|SYNC|memory' /tmp/cinemate_cli.log | grep -v 'DNG written'`
    Record every hit with its line number and the wall-clock second, so it can be aligned to the sampler CSV. `session-tail <n>` stays a progress-polling tool (step 6) only; it is never the evidence source. `/tmp/cinemate_cli.log` is deleted by the next `session-start`, so this copy must complete before step 1 of the next take.

(4) REPLACE the "Prior sync-analysis method" bullet in "Tools you drive", and the FAIL line under the audio verdict, with:

  - Sync deep-dive on an audio FAIL: **the `sync-matrix.md` notes referenced by earlier campaigns are not on this machine** (`development/pi-test-takes/` is empty) — do not go looking for them. Use this method and record it as the method: (a) recompute the deviation against `dng_count × mean_frame_interval` from the analyzer JSON's DNG timestamps and report it alongside the coarse number; (b) `grep -inE 'xrun|overrun|ALSA|snd_pcm' /tmp/cinemate_cli.log` and align each hit to the sampler CSV row at the same second; (c) state which of the two known mechanisms — ALSA capture xrun under storage contention vs. genuine frame loss — the evidence supports, and what would falsify it. Then STOP and put it to the operator; do not extend the method mid-campaign.

(5) ADD two bullets to "Tools you drive":

  - Pi↔Mac file transfer: `cinemate_dev.py` has **no** selective copy subcommand (`copy-latest-take` copies the entire take — never use it here). Use scp through the password wrapper:
    `~/.claude/skills/cinemate-dev/scripts/pi_expect.exp "$PI_PASSWORD" scp -o StrictHostKeyChecking=accept-new <src> <dst>`
    (`pi_ssh.sh` beside it is the same wrapper for plain `ssh`; the path given in `references/workspace-contract.md` under "Pi runtime" is stale — use the skill-scripts path.) `PI_PASSWORD` must already be exported in your environment before Phase 0; if it is unset, STOP and ask the operator to set it. Create the archive directory first: `mkdir -p development/pi-test-takes/c1/<take-id>/`.
  - Take directory: derive it, never guess. `take_dir = dirname($(redis-cli GET last_dng_cam0))` — that key holds the full path to the most recent DNG. Confirm the name matches `CINEPI_YY-MM-DD_HHMMSS_*_cam0` and that its DNG count matches `framecount` before step 10's `rm -rf`.

DROP from the critic's list: the claim that the session log is deleted by the next take before archiving. It is not — deletion happens in the next take's `session-start` (step 1), after steps 8–10 have already captured and archived it. No edit needed.

### B4 · [executability] 

**Claim checked:** Phase 0.5 test-fps formula: `min(highest integer ≤ 0.95 × sensor fps_max, highest integer with data-rate ≤ 0.85 × sustained MB/s, 25)` — and Stage 1 step 3 "Set fps to the mode's test fps".

**Evidence:** The value cannot be set. settings.jsonc:146-150 has `"fps": {"steps": [25, 33, 50], "free": false}`. src/module/cinepi_controller.py:984-990: with `fps_free` off and `shutter_a_sync_mode != 1`, set_fps does `snapped_user_fps = min(self.fps_steps_dynamic, key=lambda x: abs(x - requested_user_fps))`. `_fps_steps_capped_at_max` (cinepi_controller.py:455-475) drops every step above fps_max and appends fps_max, and fps_max is truncated to int (cinepi_controller.py:882, 978). Worked example with the runbook's own imx477 table: mode B = 4056x2160@16.39 → fps_max 16 → step table [16] → the formula's 15 snaps to 16. The take then runs 6.7 % ABOVE the 0.95 margin the formula exists to create, and every 0.5 feasibility number (data rate, take size, free-space requirement) is wrong. Mode A gets 11 only by coincidence. The runbook never mentions `set fps free 1` and never has the session read back `fps` from Redis — step 3 defers verification to framecount deltas taken DURING the take (step 6), i.e. after the mistake is unrecoverable.

**Fix (adjudicated):**

Three edits. All quoted paths/line numbers are for RUNBOOK.md.

(1) ADD a bullet to "Known context you must carry in", after the `SensorDetect` renumbering bullet (:64-66):

- **`set fps` snaps; it does not take your number.** With `arrays.fps.free = false`
  (settings.jsonc:146-150, the shipped default) `set_fps` snaps the request to the nearest
  entry of `arrays.fps.steps` = `[25, 33, 50]`, capped at `fps_max` — and `fps_max` is
  **truncated** to an int, not rounded. For any mode whose `fps_max` is below 25 that table
  collapses to the single value `[fps_max]`, so **every** `set fps` lands on `fps_max`
  regardless of what you asked for (imx477: 4056x2160@16.39 → always 16; 4056x3040@11.72 →
  always 11). Free mode is a **runtime flag on the controller instance** — it is re-read from
  settings.jsonc on every controller start, so `session-start` resets it to off. Re-issue it
  every take. Setting fps can also trigger a dynamic-resolution change *before* the fps is
  applied (dynamic resolution is on by default), so the resolution readback must be taken
  **after** the fps is set, not before.

(2) REPLACE Phase 0.5 (:195-200) in full with:

0.5 **Per-mode fps + feasibility.** Planned test fps for each mode =
`min( highest integer ≤ 0.95 × sensor fps_max , highest integer with data-rate ≤ 0.85 × sustained MB/s , 25 )`.
This value is only reachable in **free fps mode** — see the known-context bullet. For each
mode, in this order: `set fps free 1` → `set fps <planned>` → `redis-cli GET fps`. Record the
planned value and the applied readback as two separate numbers. **If the readback is not equal
to the planned integer, stop and report to the operator — do not proceed to Stage 1 with that
mode.** Also record `redis-cli GET fps_max` per mode (with dynamic resolution enabled this is a
dynamic-context value and need not equal the mode's own cap). Then per mode, using the
**applied** fps: `frames_5min = applied_fps × 300`, take size = frames × bytes/frame, required
free space = take size × 1.2, and `runway_s` (0.7). If a mode cannot fit or cannot stay under
the storage cap at any usable fps, record it as `INFEASIBLE-ON-THIS-RIG` with the arithmetic —
that is a finding, not a failure. Every downstream number in this runbook — data rate, take
size, free-space requirement, `runway_s`, `frames_5min`/`frames_10min`, and the audio
`fps_target` — uses the **applied** fps, never the planned one.

Apply the same correction to 0.3 (:184): change "set the test fps (rule in 0.5)" to
"set the test fps per 0.5 **including `set fps free 1` and the `fps` readback**".

(3) REPLACE Stage 1 per-take steps 2 and 3 (:242-245) with:

2. Set the mode: `set resolution <n>`.
3. Set fps: `set fps free 1` (mandatory every take — `session-start` resets it), then
   `set fps <applied fps from 0.5>`, then `redis-cli GET fps`. **The readback must equal the
   0.5 applied value exactly; if it does not, abort the take, do not record it, and report to
   the operator.** Only now verify the three `resolution_target_width/height/bit_depth`
   readbacks against the plan (setting fps can move the resolution, and `set resolution`
   renumbers per process — re-check both every session). Record in the ledger for this take:
   `fps` readback, `fps_free` state, and the three resolution readbacks. Confirm the achieved
   rate independently via two `framecount` samples ~10 s apart during the take (step 6), not
   via `fps_actual`; if that derived rate differs from the readback by more than 2 %, note it
   and treat the take as `COMPLETE-WITH-LOSS` pending analysis.

Ledger: add an `fps applied (readback)` column and an `fps_free` column next to the existing
`fps` column in the Stage 1 and Stage 2 tables (RESULTS.md:91 and :152), and add
`test fps (planned)` / `test fps (applied)` as two columns in the 0.5 feasibility table
(RESULTS.md:45). Stage 2 (:308) inherits this: `frames_10min = applied_fps × 600`.


---

## MAJOR — wrong numbers or wasted Pi time (35)

### M1 · [helper-commands] 

**Claim checked:** "Tools you drive" lists only cinemate_dev.py and analyze_cinepi_media.py; 0.9 says "scp `c1_sampler.sh` (chmod +x) and `analyze_cinepi_media.py` to `/home/pi/c1/`", and ~20 further steps issue raw Pi shell commands (findmnt, df, dd, arecord -l, getcap, ps, free, vcgencmd, dmesg, redis-cli, mkdir, rm -rf, nohup, python3 analyze).

**Evidence:** cinemate_dev.py has no generic ssh/scp/exec subcommand (`python3 cinemate_dev.py --help` -> status, sync-status, stop, session-start, session-send, session-tail, session-stop, pull-local, push-local, sync-files, build-raw, pull-pi, repo-status, repo-commit, repo-push, note, manual-take, copy-latest-take, roundtrip-take). `sync-files` cannot reach /home/pi/c1: `normalize_repo_file` raises `"<path> is not inside <local repo root>"` for anything outside the local repo, and `command_sync_files` writes only to `REMOTE_REPO_ROOTS[repo] + '/' + relative` (cinemate_dev.py:1273-1284, REMOTE_REPO_ROOTS at :38-41 = /home/pi/cinemate, /home/pi/cinepi-raw). The only PI_PASSWORD-aware transport is /Users/patrikeriksson/.claude/skills/cinemate-dev/scripts/pi_ssh.sh (which execs pi_expect.exp when $PI_PASSWORD is set); bare `ssh`/`scp` will block on `pi@cinepi.local's password:` and stall an unsupervised session indefinitely (pi_expect.exp sets `set timeout -1`). Note also that workspace-contract.md:66's `/Users/patrikeriksson/Documents/cinemate/scripts/pi_ssh.sh` does not exist — only the skill copy does.

**Fix (adjudicated):**

Add as a third bullet in "Tools you drive" (after the `analyze_cinepi_media.py` bullet, before "Archive root on the Mac"):

- **Ad-hoc Pi shell and file transfer** — everything in this runbook that is not a
  `cinemate_dev.py` subcommand (`findmnt`, `df`, `dd`, `arecord -l`, `getcap`, `ps`, `free`,
  `vcgencmd`, `dmesg`, `redis-cli`, `mkdir`, `rm -rf`, `nohup`, `python3 …`):
  - Shell: `~/.claude/skills/cinemate-dev/scripts/pi_ssh.sh '<command>'`. It picks up
    `PI_PASSWORD` from the environment automatically, and falls back to key auth if unset.
  - Mac → Pi (0.9):
    `~/.claude/skills/cinemate-dev/scripts/pi_expect.exp "$PI_PASSWORD" scp -o StrictHostKeyChecking=accept-new <local> pi@cinepi.local:<remote>`
  - Pi → Mac (step 9 archival): the same form with source and destination swapped; add `-r`
    only when the source is a directory. Do **not** reach for `copy-latest-take` or
    `roundtrip-take` for archival — both pull the entire take directory (30–70 GB).
  - **Never call bare `ssh` or `scp`.** They prompt for the password on a tty this session
    does not have; the call burns its timeout and does nothing.
  - `cinemate_dev.py sync-files` cannot do 0.9. It rejects any source outside a local repo
    root and writes only under `/home/pi/cinemate` or `/home/pi/cinepi-raw`
    (`cinemate_dev.py:38-41`, `:831-847`, `:1273-1284`), and `analyze_cinepi_media.py` lives
    in the skill, not in a repo.
  - Ignore `references/workspace-contract.md` line 66: its
    `/Users/patrikeriksson/Documents/cinemate/scripts/pi_ssh.sh` is a stale path that does not
    exist. The live copies are the skill path above (used by `cinemate_dev.py` itself) and
    `/Users/patrikeriksson/Documents/cinemate/cinemate/scripts/pi_ssh.sh`.

Then change 0.9 from "scp `c1_sampler.sh` (chmod +x) and `analyze_cinepi_media.py` to
`/home/pi/c1/`" to name the transport explicitly:

0.9 **Install instrumentation.** `pi_ssh.sh 'mkdir -p /home/pi/c1/samples /home/pi/c1/results'`.
Write `c1_sampler.sh` locally (it does not exist yet — author it verbatim from the
Instrumentation section above), then push both files with the `pi_expect.exp … scp` form from
"Tools you drive": `c1_sampler.sh` and
`~/.claude/skills/cinemate-dev/scripts/analyze_cinepi_media.py` → `/home/pi/c1/`. Then
`pi_ssh.sh 'chmod +x /home/pi/c1/c1_sampler.sh'` and confirm both land with
`pi_ssh.sh 'ls -l /home/pi/c1/'`.

### M2 · [helper-commands] 

**Claim checked:** "Known context you must carry in": "The dev Pi is a **2 GB CM5 Lite**" — and 0.10: "The 2 GB RAM-guard confound must appear explicitly in the reasoning for any mode whose data rate is within 15 % of the sustained speed." (Out of my assigned dimension, but verified live and campaign-invalidating.)

**Evidence:** Live on pi@cinepi.local: `grep MemTotal /proc/meminfo` -> `MemTotal: 4146928 kB` (~3.96 GiB); `grep Revision /proc/cpuinfo` -> `c041a0`; `/proc/device-tree/model` -> `Raspberry Pi Compute Module 5 Lite Rev 1.0`. Revision memory-size field = bits 20-22: 0xc041a0>>20 = 0xc, &0x7 = 4 -> 4 GB. The 2 GB variant is 0xb041a0 (0xb&0x7 = 3 -> 2 GB), which is what the prior session recorded. The board is 4 GB, so every 2 GB-anchored prediction, runway calculation, and RAM-guard confound statement in the runbook starts from a wrong premise.

**Fix (adjudicated):**

Three edits to /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md.

EDIT 1 — replace lines 51-54 (the first bullet under "Known context you must carry in"):

- **Measure the board's RAM in 0.7 before you reason about it — `cinepi.local` is whichever
  CM5 is plugged in, and there is more than one.** Last measured **4 GB** (2026-08-24,
  PI-016, operator-confirmed: `MemTotal` 4146928 kB, `Revision c041a0`), but the same
  hostname was a **2 GB** unit (`b041a0`) on 2026-08-04. Record `MemTotal` and `Revision`
  in the 0.7 table and reason from *that*, never from a remembered figure. Two independent
  auto-stop guards exist (`src/module/cinepi_controller.py:262-266`, watchdog polls at 4 Hz):
  **primary** `BUFFER_LIMIT_PERCENT = 90` on cinepi-raw's frame-buffer fill
  (`buffer` / `buffer_size`) — this is the one a write backlog actually trips — and
  **backstop** `RAM_LIMIT_PERCENT = 80` on whole-system `psutil.virtual_memory().percent`.
  They log different lines (`RAM frame buffer NN% ≥ 90%! Stopping recording.` vs
  `RAM NN.N% ≥ 80%! Stopping recording.`) and both set `memory_alert`; record which one
  fired. `buffer_size` is not a constant — cinepi-raw sizes the pool at encoder-configure
  time as `0.90 × MemAvailable / bytes_per_frame`
  (`cinepi/dng_encoder.cpp:831-849`), so it scales with the board *and* with whatever else
  is resident, which is why 0.7 re-reads it per mode. Either auto-stop is a *distinct
  outcome class* (drive can't sustain the data rate), not a drop-frame bug — classify it as
  such, never as "dropped frames".

EDIT 2 — in 0.7 (line 211), replace `**RAM runway.** `free -b`;` with:

0.7 **RAM runway.** `free -b`, `grep MemTotal /proc/meminfo`, `grep Revision /proc/cpuinfo`
— record all three verbatim in the ledger and flag immediately if `MemTotal` is not ~4146928
kB; then, after setting each mode, read `buffer_size` from Redis and record
`runway_s = buffer_size / fps` — how long a full disk stall can last before the buffer guard
ends the take.

EDIT 3 — in 0.10, replace the final sentence (lines 224-225) "The 2 GB RAM-guard confound must appear explicitly in the reasoning for any mode whose data rate is within 15 % of the sustained speed." with:

The measured `buffer_size` and `runway_s` from 0.7 must appear explicitly in the reasoning
for any mode whose data rate is within 15 % of the sustained speed, along with which of the
two guards (90 % buffer-fill or 80 % system-RAM) you expect to trip first, and why.

EDIT 4 — in the Phase 0 STOP-check (lines 229-231), add RAM to the enumeration:

**Phase 0 STOP-check (not a gate):** if any of 0.1–0.9 contradicts the "known context"
section in a way that changes the test design (different sensor, **board RAM other than the
4 GB last measured**, exFAT instead of ext4, missing mic, throttling at idle), report to the
operator and wait before Stage 1.

### M3 · [helper-commands] 

**Claim checked:** "Media analyzer: `~/.claude/skills/cinemate-dev/scripts/analyze_cinepi_media.py`. It is stdlib-only — scp it to the Pi (`/home/pi/c1/`) and run it there"

**Evidence:** The import list IS stdlib-only — analyze_cinepi_media.py:4-14 = `__future__`, argparse, json, os, re, shutil, subprocess, dataclasses, pathlib, typing (all confirmed present in `sys.stdlib_module_names`), and the Pi runs Python 3.11.2, so no pip install is needed. But "stdlib-only" does not mean self-contained: the analyzer shells out to two external binaries (analyze_cinepi_media.py:69-73 `shutil.which("ffprobe")`/`shutil.which("exiftool")`, :114-125 exiftool call, :147-158 ffprobe call). Live on the Pi: `command -v ffprobe` -> `/usr/bin/ffprobe` (present), `command -v exiftool` -> MISSING. So `dng.sample_metadata` will be `{}` in every take's JSON — no TimeCode, DateTimeOriginal, FrameRate, ImageWidth, ImageHeight or BitsPerSample — while the `wav.ffprobe` block will populate.

**Fix (adjudicated):**

TWO edits are required.

EDIT 1 — replace the "Media analyzer" bullet, RUNBOOK.md lines 93-95:

- Media analyzer: `~/.claude/skills/cinemate-dev/scripts/analyze_cinepi_media.py`. Its
  **imports** are stdlib-only (Pi `python3` is 3.11.x, no `pip install` needed), so **scp it
  to the Pi** (`/home/pi/c1/`) and run it there, directly against `/media/RAW/<take>`; full
  takes are 30–70 GB and must never be copied to the Mac. It is *not* self-contained: it
  shells out to `ffprobe` and `exiftool` (`analyze_cinepi_media.py:69-73`). On this Pi
  `ffprobe` is installed (it arrives with `ffmpeg` from `cinemate-install.sh`) but
  **`exiftool` is not** — recorded absent on this device in the 2026-08-23 Pi session,
  `system-review/PI-VERIFICATION-QUEUE.md` PI-010. Consequence:
  `takes[].dng.sample_metadata` will be `{}` on **every** take — no TimeCode,
  DateTimeOriginal, FrameRate, ImageWidth, ImageHeight or BitsPerSample — while
  `takes[].wav.ffprobe` populates normally. Treat the analyzer's authoritative fields as
  `dng.count`, `dng.first_index`, `dng.last_index`, `dng.missing_indices`, `wav.exists` and
  `wav.ffprobe.format.duration` only; width/height/bit-depth come from the Phase 0.3
  `resolution_target_*` Redis readbacks. **Do not install `exiftool`** — installing packages
  is not a sanctioned intervention (ground rule 2; the 0.6 `setcap` is the only one).

EDIT 2 — replace the fps-offset recompute paragraph, RUNBOOK.md lines 158-160:

If the coarse deviation is dominated by sensor-vs-target fps offset, recompute against
`dng_count × mean_frame_interval` — but do **not** try to get `mean_frame_interval` from the
analyzer JSON. The analyzer carries no per-frame timestamps: `sample_metadata` is `{}`
without `exiftool` (absent here), and even with `exiftool` it reads only the *first* DNG
(`analyze_cinepi_media.py:112-115`), which cannot yield an interval. Derive the measured rate
from the sampler CSV instead — `Δframecount / Δts` across the take's steady-state window in
`/home/pi/c1/samples/<take-id>.csv` — so `mean_frame_interval = 1 / fps_measured`. This is the
same `framecount`-delta method the "Known context" section already mandates over `fps_actual`.
Record both numbers: the target-fps deviation and the measured-fps deviation.

SUPPORTING EDIT (optional but recommended) — append to step 0.9:

Then run the analyzer once against any 0.3 validation take and record its `"tools"` block
(`{"ffprobe": …, "exiftool": …}`) verbatim in the ledger. That block is the live proof of
which analyzer fields will be populated for the rest of the campaign.

### M4 · [helper-commands] 

**Claim checked:** "If the coarse deviation is dominated by sensor-vs-target fps offset, recompute against `dng_count × mean_frame_interval` using the DNG timestamps from the analyzer JSON, and record both numbers."

**Evidence:** The analyzer never produces per-frame timestamps. analyze_cinepi_media.py:112-130 runs exiftool on exactly one file — `sample_file = str(dng_files[0])` — and stores the result as `DngSummary.sample_metadata`; the JSON payload (`:246-251`, `asdict(r)`) contains `first_file`/`last_file`/`first_index`/`last_index`/`missing_indices` plus that single-file metadata dict. There is no timestamp array, so no mean interval is derivable — and on this Pi exiftool is missing, so even that one DateTimeOriginal is absent (verified: `command -v exiftool` -> MISSING). The instruction cannot be executed as written.

**Fix (adjudicated):**

If the coarse deviation is dominated by sensor-vs-target fps offset, **do not look for frame
timestamps in the analyzer JSON — it has none.** `analyze_cinepi_media.py` runs `exiftool` on
`dng_files[0]` only and stores that single result as `sample_metadata`; the JSON carries
`first_file`/`last_file`/`first_index`/`last_index`/`missing_indices` and nothing per-frame.
`exiftool` is not installed on this Pi, so `sample_metadata` will be `{}` on every take — and
even with it installed the DNG `FrameRate` tag is the *configured* fps (`dng_encoder.cpp`
writes `round(fps × 1000) / 1000` and deliberately does **not** write the sensor's quantised
rate), so it can never show the offset you are trying to measure.

Derive the real rate from the sampler CSV instead. Restrict to the take window — the rows
where `framecount` is strictly increasing (`framecount` is per-take and sits flat outside a
take) — and least-squares fit `framecount` against `ts`. The slope is the measured fps;
`mean_frame_interval = 1 / slope`. Recompute the expected duration as
`dng_count × mean_frame_interval`, and record four numbers in the ledger: the target-fps
expectation, the fitted-fps expectation, the fitted fps itself, and the residual against
`wav_duration`.

State the fit's resolution alongside them. The sampler writes `ts` at whole-second resolution
on a 2 s cadence, so the fitted rate is good to roughly ±0.03 % — about ±0.1 s of expected
duration on a 5-minute take, ±0.06 s on a 10-minute one. That is enough to attribute a
multi-frame-period deviation to fps offset; it is **not** enough to move a take across the
0.5- or 1.0-frame-period PASS/WARN/FAIL boundary. If the residual falls inside that band,
record "consistent with fps offset, at the fit's resolution floor" rather than a precise value.

### M5 · [helper-commands] 

**Claim checked:** Outcome class `COMPLETE-CLEAN`: "DNG count == requested; no filename-sequence gaps; ..." evidenced by the analyzer JSON (step 8).

**Evidence:** `missing_indices` only counts holes strictly inside the observed range: analyze_cinepi_media.py:106-109 `expected = set(range(min(indices), max(indices)+1)); missing = len(expected.difference(indices))`. Frames lost before the first surviving index or after the last are invisible. Confirmed on real media: `/media/RAW/CINEPI_26-08-25_210341_F31_C00000_cam0` holds 33 DNGs spanning `000000002`..`000000093` — the analyzer reports `missing_indices=59` and silently omits the two lost at the head. (The index itself is a sound drop metric: `index_++` at cinepi-raw/cinepi/dng_encoder.cpp:424 is a per-clip contiguous counter, and 16 of the 20 takes now on /media/RAW run exactly `000000000..count-1`. The metric is correct, just blind at the edges.)

**Fix (adjudicated):**

TWO edits, both required — the row alone does not close the hole because the step-8 grep cannot surface cinemate's own index-gap warning.

(1) Replace the `COMPLETE-CLEAN` row in "Outcome classes and pass thresholds":

| `COMPLETE-CLEAN` | Stopped at the requested frame count; from the analyzer JSON **all** of `dng.count == requested`, `dng.first_index == 0`, `dng.last_index == dng.count - 1`, `dng.missing_indices == 0`; Redis `missing_frame_count` == 0 **and** `drop_frame_during_last_take` == 0; no write-failure, drop/sync, or DNG-index-gap warnings in the session log. (`missing_indices` alone is blind at the edges — it only counts holes inside `min..max`, so frames lost before the first or after the last surviving index are invisible. The `first_index`/`last_index` checks close that hole and match cinemate's own live formula `last_idx + 1 - count` in `redis_listener.py:1729`. A frame that is indexed and then dropped still advances `framecount`, so an over-long frame-limit landing can otherwise mask edge loss behind a correct-looking count.) |

(2) In Stage 1 step 8, extend the session-log grep so the index-gap warning is actually captured. Replace:

     window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` (case-insensitive) and

with:

     window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory|missing|index gap` (case-insensitive) and

Rationale for (2), verified by running the original pattern: cinemate emits `DNG index gaps: N missing file slot(s) in sequence (...)` (`redis_listener.py:1942-1948`) and `<cam> appears to be missing N DNG index slot(s) (count=..., last idx=...)` (`:1745-1752`) for exactly this condition, and the current pattern matches neither — it returns zero hits on both lines.

### M6 · [helper-commands] 

**Claim checked:** "Prior sync-analysis method: check `/Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/` for the sync-matrix notes from the audio-sync campaign (`sync-matrix.md`, possibly under a phase subfolder). If a WAV fails the coarse sync check, use that method" — and the audio FAIL rule "On FAIL, run the sync-matrix deep-dive method before writing the verdict."

**Evidence:** `ls -la /Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/` -> the directory contains only `.DS_Store`; there are no subfolders and no `sync-matrix.md`. `find /Users/patrikeriksson -maxdepth 6 -iname '*sync-matrix*' -not -path '*/Library/*'` returns nothing. `grep -rl "sync-matrix" /Users/patrikeriksson/Documents/cinemate` matches exactly one file: the RUNBOOK itself. The archive root the runbook writes to, `development/pi-test-takes/c1/<take-id>/`, also does not exist yet.

**Fix (adjudicated):**

THREE edits to /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md.

=== EDIT A — replace the bullet at lines 100–103 ("Prior sync-analysis method: check ...") with: ===

- Prior sync-analysis method: **there is none on disk.** The audio-sync campaign's
  `sync-matrix.md` no longer exists anywhere in this workspace
  (`development/pi-test-takes/` holds only a `.DS_Store`, and it is not in git history) —
  do not spend session time looking for it. What survives is the method summary: drift was
  measured by the **clap-delta** method (3 claps per take, audio−video offset at each,
  clock-correction OFF, `timecode_offset_frames` and `plain_arecord_timecode_offset_frames`
  both 0). Clap-delta needs claps recorded *in* the take, so it is not available
  retroactively and is not part of this campaign. Use the artifact-based deep dive in the
  audio-verdict section below instead. Carry one finding forward: the duration-ratio
  comparison this runbook uses as its coarse check was shown to be **noise-dominated** at
  the margin (the audio capture window ≠ the video frame window), so never promote a
  duration delta to a root cause on its own.

=== EDIT B — replace lines 152–156 (the PASS/WARN/FAIL bullets) with: ===

- **PASS** — WAV present; `|wav_duration − dng_count/fps_target| ≤ 0.5 frame period`; **and**
  zero silence-fill lines in the session log for the take window (see below).
- **WARN** — deviation ≤ 1 frame period, or total inserted silence ≤ 1 frame period.
- **FAIL** — deviation > 1 frame period, total inserted silence > 1 frame period, any WAV
  discontinuity, or missing WAV.

**Read this before scoring any take.** On `dev` (`cinepi-raw`, `cinepi/cinepi_audio_capture.cpp`)
the capture helper runs a wall-clock reconciliation that pads every shortfall with silence
"so the WAV stays aligned to wall clock". Two consequences you must not trip over:

1. **WAV duration is not a sensitive loss indicator.** A take that lost real audio is padded
   back to the right length and will pass the duration test. Duration can only fail a take,
   never clear one.
2. **Nothing logs the word "xrun".** `recoverCaptureError` handles `-EPIPE` with a bare
   `snd_pcm_prepare` and prints nothing. Do not count xrun lines — there will be none.
   Record the `xruns` ledger column as `n/a (no such log line on this build)` unless you
   actually observe one.

The real signal is this line, emitted once per padded gap:

    Inserted <N> silent frame(s) to cover a capture shortfall of <X>s; WAV stays aligned to wall clock

Deep dive on FAIL (do this instead of hunting for `sync-matrix.md`):

1. Grep the take window for the fill line and total it:
   `grep -c 'silent frame(s)' session-log.txt` and
   `grep -o 'shortfall of [0-9.]*s' session-log.txt | awk '{s+=$3} END {print s+0}'`.
   Report **count and total seconds** — that is the take's real audio loss, whatever the
   duration test said.
2. Classify the shape: fills clustered at one moment = a single storage stall; fills spread
   across the take = sustained contention. Cross-reference the fill timestamps against the
   sampler CSV's `buffer`, `dirty_kb` and `write_speed_to_drive` columns at the same seconds
   and state whether they coincide.
3. Only if the duration delta is large **and** there are no fill lines: recompute against
   `dng_count × mean_frame_interval` from the analyzer JSON's DNG timestamps (note below)
   and record both numbers — that pattern points at fps offset or start-of-take latency,
   not sample loss.
4. Confirm the WAV is continuous with the stdlib `wave` snippet above.
5. Write the verdict with the mechanism named: `sample-loss (N fills, X.XXX s)`,
   `fps-offset`, `start-latency`, or `undetermined`. Never write FAIL without one of these.

=== EDIT C — make the deep dive executable (two one-line changes) ===

C1. In Stage 1 step 8, the archived log must contain the fill lines. Replace the grep pattern
    `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory`
    with
    `write.*fail|FAILED|silent frame|shortfall|xrun|overrun|drop|SYNC|memory`

C2. In 0.9, add the Mac-side archive root — it does not exist yet (minor on its own):
    "On the Mac, before the first take:
    `mkdir -p /Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/c1`"

Optional ledger tidy: in RESULTS.md, relabel the `xruns` column in the Stage 1 and Stage 2
tables to `silence fills (n / s)` so the ledger records the signal that actually exists.

### M7 · [helper-commands] 

**Claim checked:** Per-take step 1 implies `session-start` failing means a hung/failed session that should be retried.

**Evidence:** `storage_preroll.py:_arm_startup_preroll` returns early when no media is mounted (`if not self.ssd_monitor.is_mounted: ... return`, storage_preroll.py:140-147) WITHOUT ever logging "Storage pre-roll complete". The helper then burns its whole `--ready-timeout-seconds` (default 120, cinemate_dev.py:1499) and exits 1 with `Timed out waiting for storage pre-roll completion.` (:614-621). An unmounted or hot-swapped-out /media/RAW is therefore indistinguishable from a hung session, and blind retries will each cost 2 minutes. This is a live risk in this campaign because Phase 0.4 runs a `dd` test on /media/RAW and step 10 does `rm -rf` on it.

**Fix (adjudicated):**

Replace per-take step 1 of Stage 1 (RUNBOOK.md line 241) with:

1. `session-start`. The helper **blocks internally** until `Storage pre-roll complete` appears
   in `/tmp/cinemate_cli.log`, and already applies the +1 s settle — do not add your own poll
   loop. **Check the exit code.**

   Non-zero with `Timed out waiting for storage pre-roll completion` does **not** mean a hung
   session. The marker is emitted only after a pre-roll actually records, and pre-roll is
   skipped outright when `/media/RAW` is not mounted — so an unmounted drive and a hung
   session look identical. The session is also left **running** (the helper writes the pid
   file before it waits), so `session-send "rec f …"` will still be accepted, will log
   `No disk.`, and will never record — step 6's poll would then never terminate. Before
   retrying anything:

   `~/.claude/skills/cinemate-dev/scripts/pi_ssh.sh 'findmnt -no SOURCE,FSTYPE /media/RAW'`

   - No output → `/media/RAW` is not mounted. `session-stop`, report to the operator, and do
     **not** retry: each blind retry burns the full 120 s `--ready-timeout-seconds`.
   - NVMe + ext4 as recorded in 0.4 → a real startup fault. `session-stop`,
     `cinemate_dev.py stop`, retry once. Keep the helper's 80-line stderr log tail as
     evidence. A second failure is a STOP — report and wait.

   Phase 0.2 carries the same "wait for `Storage pre-roll complete` → +1 s" wording; the same
   exit-code rule applies there.

### M8 · [helper-commands] 

**Claim checked:** Implicit in step 6 ("Do not send anything else to the session while recording") and the abort rule ("If a session dies mid-take, classify `ABORTED-OTHER`") — that the helper will tell you the session died.

**Evidence:** The liveness guard is `kill -0` on the PID in /tmp/cinemate_cli.pid (cinemate_dev.py:663-667 in `send_helper_session_command`; the same check drives `status`'s `helper_session.running` at :786-796). That PID belongs to the outer `bash -lc` running the whole pipeline `tail -n0 -f /tmp/cinemate_cli.in | bash -lic cinemate` (:49, :590-592), not to cinemate itself. If cinemate/main.py dies mid-take, `tail -f` stays blocked on a file nobody is writing and never takes SIGPIPE, so the outer bash survives and both `session-send` and `status` keep reporting the session as running.

**Fix (adjudicated):**

Two edits to /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md.

EDIT 1 — replace step 6 of the Stage 1 per-take procedure (lines 250-251), currently:

6. `session-send "rec f <frames_5min>"`. Poll `session-tail 100` every 60 s. The take must
   stop itself at the frame count. Do not send anything else to the session while recording.

with:

6. `session-send "rec f <frames_5min>"`. Poll `session-tail 100` every 60 s. The take must
   stop itself at the frame count. Do not send anything else to the session while recording.
   **Liveness during a take is judged from exactly two things: new lines appearing in
   `session-tail`, and `framecount` still advancing in the sampler CSV.** Never judge it from
   `session-send`'s exit code or from `status`'s `Helper session: running` / `Ready: True`.
   Both check the PID of the wrapper pipeline
   (`tail -n0 -f /tmp/cinemate_cli.in | bash -lic cinemate`), and that wrapper outlives a dead
   cinemate — `tail -f` stays blocked on a file nobody is writing, so it never takes SIGPIPE.
   After a crash, plain `status` prints `running` and `Ready: True` with nothing on screen to
   contradict it (`Ready` is a grep over the whole log file, so it never goes false), and the
   first `session-send` returns `sent` with exit 0 while silently discarding the command —
   only the send after that reports `stale`.
   If two consecutive polls show no new log lines **and** a flat `framecount`, settle it on
   the Pi with `pgrep -af '/home/pi/cinemate/src/main.py|cinepi-raw'`: processes present =
   stall, keep polling and record it as buffer pressure; processes absent = the session died,
   go to the abort rule in the sequencing rules below.
   Bound the loop: if `Stopped recording` has not appeared by `1.5 × frames_5min / fps`
   seconds, stop polling and run the same `pgrep` check.

EDIT 2 — replace the abort rule (line 280-281), currently:

- If a session dies mid-take, classify `ABORTED-OTHER`, capture logs, `cinemate_dev.py stop`,
  and restart the sequence at the same rep once.

with:

- If a session dies mid-take, classify `ABORTED-OTHER`, capture logs, `cinemate_dev.py stop`,
  and restart the sequence at the same rep once. Death is established by the `pgrep` check in
  step 6, never by the helper's reported session state. A crash is `ABORTED-OTHER` even if
  `memory_alert` is set: the RAM guard stops the *take* and leaves cinemate alive and logging
  (it always writes `Stopping recording.` then `Stopped recording` to the session log), so a
  log that simply went silent is a crash, not `AUTO-STOP-RAM-GUARD`.

### M9 · [redis-and-cli] 

**Claim checked:** 0.7: "after setting each mode, read buffer_size from Redis and record runway_s = buffer_size / fps"

**Evidence:** buffer_size is published ONCE per camera init and only from inside the per-frame callback: cinepi_controller.cpp:393-398 guards on `!buffer_size_sent_ && app_->GetEncoder()->initialized()`, and buffer_size_sent_ is only reset by the cam_init control (cinepi_controller.cpp:719-721; CONTROL_KEY_CAMERAINIT == "cam_init", cinepi_state.hpp:44). CineMate sets cam_init AFTER publishing the target state and after a paced sleep (cinemate src/module/cinepi_controller.py:1713-1722). So a GET issued right after `set resolution <n>` returns the PREVIOUS mode's capacity — and because max_ram_buffers_ scales inversely with bytes/frame, that is exactly the number that changes between modes. Every runway_s in 0.7 would be wrong.

**Fix (adjudicated):**

Replace 0.7 with:

0.7 **RAM runway (measured inside the 0.3 take of each mode — not in a separate pass).**
`buffer_size` is not a live key. cinepi-raw publishes it once per encoder setup from the per-frame path (`cinepi/cinepi_controller.cpp:393-398`, guarded on `!buffer_size_sent_ && GetEncoder()->initialized()`), and the only thing that computes `max_ram_buffers_` and sets `initialized()` is `setup_encoder()` (`cinepi/dng_encoder.cpp:840-855`), whose only caller is `EncodeBuffer()` (`cinepi/cinepi_recorder.hpp:49-62`) — invoked only under `nowRecording && folderOpen` in `cinepi/cinepi_raw.cpp`. `reset_encoder()` clears the flag on every camera reconfigure and every record start (`cinepi_raw.cpp:145,155,207`), and nothing in CineMate ever writes the key. **A `redis-cli GET buffer_size` issued after `set resolution <n>` but before recording returns the previous recorded take's capacity — possibly another mode's, or another day's — and waiting does not fix it.**

So, for each selected mode, during that mode's 0.3 validation take:

1. Immediately before its `rec f 25`, record `MemAvailable` (`grep MemAvailable /proc/meminfo`). `max_ram_buffers_ = 0.90 x MemAvailable / frame_buffer_bytes`, both sampled at setup time, so the runway is a function of the memory state as well as the mode.
2. From the session log for that take, capture the two `setup_encoder` lines:
   `RAM pool: up to <N> frames  (~<M> MB)` and
   `Encoder configured - <W>x<H> <bits>-bit, buffer <S> MB`.
   Confirm `<W>x<H>` and `<bits>` are the mode you set. If they are not, the camera has not re-inited yet — wait for the next pair. These lines print at the **first recorded frame**, not at `set resolution` and not at launch.
3. Then `redis-cli GET buffer_size` and confirm it equals `<N>`. The publish lands on the frame after the first encoded frame, so re-read if it lags. **Never record a `buffer_size` that disagrees with `<N>` — a disagreement means you are reading a stale key.**
4. Ledger row per mode: `MemAvailable`, `<S>` MB/frame, `<N>` frames (= `buffer_size`), and
   `runway_s = 0.9 x N / fps` — how long a full disk stall can last before the take is force-stopped. The 0.9 is CineMate's `BUFFER_LIMIT_PERCENT = 90` (`src/module/cinepi_controller.py:260`, `_buffer_fill_percent`); cinepi-raw's own stop is at `N - 2` (`dng_encoder.hpp buffer_full()`), so 0.9 is the binding one.

Sampler caveat (applies to every Stage 1/2 CSV): `c1_sampler.sh`'s `buffer_size` column is stale for every sample taken before the take's first recorded frame, for the same reason. When reading a take's CSV, use the first sample **after** `framecount` starts advancing, and note it in the ledger if it differs from that mode's 0.3 figure — it legitimately can, because `MemAvailable` differs between a cold session and one following a 5-minute take.

### M10 · [redis-and-cli] 

**Claim checked:** runway_s = buffer_size / fps is "how long a full disk stall can last before the RAM guard ends the take"

**Evidence:** The auto-stop does not wait for 100 % of the pool. /Users/patrikeriksson/Documents/cinemate/cinemate/src/module/cinepi_controller.py:260 `self.BUFFER_LIMIT_PERCENT = 90` and :2596-2601 stop as soon as `buffer_pct >= 90`. (The 80 % figure in the runbook's "known context" is RAM_LIMIT_PERCENT at :256, a separate psutil system-RAM backstop at :2605-2610, not the write-backlog guard.) cinepi-raw additionally hard-blocks the encode thread two slots early (dng_encoder.hpp:154 `ram_buffers_ + 2 >= max_ram_buffers_`).

**Fix (adjudicated):**

Replace step 0.7 in full (RUNBOOK.md:211-213) with:

0.7 **RAM runway.** `free -b` at idle.

**Read `buffer_size` at the right moment.** cinepi-raw publishes `buffer_size` (the frame-pool slot count) **only at the first recorded frame after an encoder setup** — `cinepi_recorder.hpp:53-61` calls `setup_encoder()` from `EncodeBuffer`, and `cinepi_raw.cpp:218-231` calls `EncodeBuffer` only while recording; `reset_encoder()` runs at every record start (`cinepi_raw.cpp:207`). Redis is never flushed, so reading the key straight after `set resolution` returns the **previous** mode's — or a previous session's — value. Read it **during each mode's 0.3 validation take** (the sampler already logs it) and record it per mode. The pool is sized at 90 % of `MemAvailable` sampled at that take's first frame (`dng_encoder.cpp:829-852`), so it legitimately varies take to take — it is not a Phase 0 constant.

Then record, per mode:

`runway_s ≈ 0.9 × buffer_size / fps` — an **upper bound** on how long a full disk stall can last before a guard ends the take. Three independent guards can end it, whichever trips first, and all three sit near 90 % of the pool:

| Guard | Trips at | Log line | Sets `memory_alert`? |
|---|---|---|---|
| cinemate write-backlog guard | `buffer / buffer_size ≥ BUFFER_LIMIT_PERCENT = 90` (`cinepi_controller.py:260`, `:2596-2601`), polled 4 Hz | `RAM frame buffer NN% ≥ 90%! Stopping recording.` | yes |
| cinemate system-RAM backstop | `psutil.virtual_memory().percent ≥ RAM_LIMIT_PERCENT = 80` (`cinepi_controller.py:256`, `:2605-2610`) | `RAM NN.N% ≥ 80%! Stopping recording.` | yes |
| cinepi-raw pool guard | `ram_buffers_ + 2 ≥ max_ram_buffers_` (`dng_encoder.hpp:151-155`, `cinepi_raw.cpp:220-229`) | `RAM pool exhausted — recording stopped` | **no** |

Note on the numerator: Redis `buffer` is the **peak disk-write backlog** since the last stats message (`redis_listener.py:923-931`, `max(bufferSize, bufferSizeMax)`) — the disk half only, excluding `encode_queue_`. Read the sampler's `buffer` column with that in mind.

For every `AUTO-STOP-RAM-GUARD` take, record **which** of the three fired, quoting the log line verbatim. `memory_alert == 0` does **not** rule out a RAM auto-stop: cinepi-raw's guard never writes that key (the only writers are `cinepi_controller.py:1450` clear and `:2627` set).

---

Two supporting one-line corrections elsewhere in the same document:

1. RUNBOOK.md:51-54 — replace "the **80 % RAM guard force-stops recording** when the write backlog fills it" with: "a RAM guard force-stops recording when the write backlog fills it. **Three** distinct guards can do this at different thresholds — see 0.7. The 80 % figure is the system-RAM backstop (`RAM_LIMIT_PERCENT`), *not* the write-backlog guard, which trips at 90 % of the cinepi-raw frame pool (`BUFFER_LIMIT_PERCENT`)."

2. RUNBOOK.md:147 — replace the `AUTO-STOP-RAM-GUARD` definition with: "cinemate **or** cinepi-raw force-stopped the take on one of the three RAM guards (0.7). Name the guard and quote its log line. `memory_alert` fires for the two cinemate guards only — cinepi-raw's `RAM pool exhausted` stop leaves it at 0."

### M11 · [redis-and-cli] 

**Claim checked:** A frame-limited take will always stop itself (no watchdog needed in the runbook)

**Evidence:** The stop is driven ONLY by incoming cp_stats messages: _maybe_stop_for_frame_limit is called from listen_stats (redis_listener.py:946) and from check_framecount_changing, itself called from listen_stats (redis_listener.py:1105, 1328). There is no timer thread. _current_expected_frame_slots (redis_listener.py:793-821) returns framecount+drops whenever self.framecount is not None, so the wall-clock anchor fallback is dead once the first frame lands. If cinepi-raw hangs or its stats stop, framecount freezes and the take never reaches the threshold — it rolls indefinitely. The only backstops are the 4 Hz RAM/buffer guard (cinepi_controller.py:2585-2611), which also reads frozen Redis values, and psutil system RAM.

**Fix (adjudicated):**

Replace Stage-1 per-take step 6 (RUNBOOK.md lines 250-251) in its entirety with:

6. `session-send "rec f <frames_5min>"`. Poll `session-tail 100` every 60 s. The take is
   *expected* to stop itself at the frame count. Do not send anything else to the session
   while recording — with the single exception of the stall watchdog below.

   **Stall watchdog (mandatory).** `rec f` has no wall-clock timeout. The stop is driven
   only by incoming `cp_stats` messages (`_maybe_stop_for_frame_limit` is reachable only
   from `listen_stats`), the wall-clock anchor fallback in `_current_expected_frame_slots`
   is unreachable because `framecount` is never `None`, and the `rec f` branch explicitly
   cancels the seconds-path timer. If cinepi-raw stalls or its stats stop, `framecount`
   freezes and the take rolls indefinitely — and the RAM/buffer guard cannot save you,
   because it reads the same frozen Redis keys.

   Before starting, record `expected_wall_s = frames_5min / test_fps` (≈ 300 s by
   construction) and set the deadline at `expected_wall_s × 1.2 + 60 s`. At each 60 s poll
   also read `framecount`, `buffer`, `is_writing_buf` and `is_recording` from Redis, and
   note whether `framecount` rose since the previous poll.

   If the deadline passes and the take has not stopped, it will not stop by itself:

   a. Record the last `framecount` / `buffer` / `is_writing_buf` / `is_recording` values and
      the `framecount`-rising history in the ledger.
   b. **Read `is_recording` first.** Send `rec` once **only if `is_recording` == 1**. Bare
      `rec` is a toggle: sending it while `is_recording` is already 0 starts a *new*
      unbounded take and fills the drive. If `is_recording` is already 0, do not send `rec` —
      go straight to step 7's flush wait.
   c. Classify the take `ABORTED-OTHER` and record which stall it was: `framecount` frozen
      (cinepi-raw pipeline stall) or `framecount` still rising (frame-limit accounting or
      target mismatch — a separate, reportable finding for the Fable gate).
   d. Continue with steps 7-10 so the partial take is still flushed, analysed and archived,
      then treat it as this mode's rep-1 failure under the sequencing rules below.

### M12 · [redis-and-cli] 

**Claim checked:** Stage-1 step 7: "After `Stopped recording`" — treating that marker as the take's stop signal

**Evidence:** The marker is not unique to the take. Storage pre-roll calls cinepi_controller.stop_recording() (storage_preroll.py:241), so "Stopped recording" is already in the log before the first take of every session; the RAM-guard auto-stop emits it too (cinepi_controller.py:2632); and framecount log lines are SUPPRESSED during pre-roll (redis_controller.py:279-282), so nothing pushes the pre-roll line out of a short tail. For the Phase 0.3 `rec f 25` takes a `session-tail 100 | grep "Stopped recording"` hits the pre-roll line immediately and the agent will "confirm" a stop that has not happened. (The same whole-file-grep bug exists in the helper's own build_recording_stop_wait_script, cinemate_dev.py:636 — do not use `roundtrip-take`/take for this.)

**Fix (adjudicated):**

Two edits to /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md.

EDIT 1 — insert this new subsection immediately after the "Instrumentation (install once in Phase 0)" section, before "## Outcome classes and pass thresholds":

## Detecting a take's stop (binds every `rec` in this runbook)

`Stopped recording` is **not** unique to your take. It is logged by
`cinepi_controller.stop_recording()` (`src/module/cinepi_controller.py:1492` on `dev`), and
**storage pre-roll calls that function at every session start**
(`src/module/storage_preroll.py:242`) — so the string is already in
`/tmp/cinemate_cli.log` before your first `rec`, sitting only ~10–25 lines from the tail
(`session-start` truncates the log, framecount logging is suppressed during pre-roll at
`src/module/redis_controller.py:308-312`, and unchanged Redis writes log nothing). A
whole-log `grep`, or a `session-tail <n>` window not yet flushed by per-frame logging, will
therefore report a stop that has not happened. This bites hardest on the 25-frame takes in
0.3, which last 0.25–2.1 s — less than one ssh round-trip.

Use this sequence for **every** `rec` in this runbook:

1. Immediately **before** `session-send "rec ..."`, capture the log anchor:
   `A=$(ssh pi@cinepi.local 'wc -l < /tmp/cinemate_cli.log')`
2. Send the command, then confirm it was accepted — the anchored region must show your own
   echo `Received: rec f <N>` (`src/module/cli_commands.py:237`) followed by
   `Armed exact frame-limited stop: <N> additional frame slots ...`
   (`src/module/redis_listener.py:258`). If the `Armed` line never appears the frame limit
   was not set: abort the take, do not let it run unbounded.
3. Poll **only** the region after the anchor, never the whole file:
   `ssh pi@cinepi.local "tail -n +\$((A+1)) /tmp/cinemate_cli.log | grep -nE 'Exact frame-limited stop reached|Stopped recording'"`
4. The take has genuinely stopped only when that region contains
   `Exact frame-limited stop reached: slot <x>/<N>; stopping recording.`
   (`src/module/redis_listener.py:826`) **followed by** `Stopped recording`, **and**
   `redis-cli GET is_recording` returns `0`.
5. If `Stopped recording` appears in the anchored region **without** a preceding
   `Exact frame-limited stop reached`, the take ended on the RAM guard
   (`src/module/cinepi_controller.py:2702`), not the frame limit — classify
   `AUTO-STOP-RAM-GUARD` and record `memory_alert`.

The same whole-file grep is baked into the helper's own
`build_recording_stop_wait_script` (`~/.claude/skills/cinemate-dev/scripts/cinemate_dev.py:636`),
which returns `stopped:` on its first poll every session. That is one more reason "Tools you
drive" forbids `roundtrip-take` here — do not fall back to it.

EDIT 2a — replace the 0.3 sentence "then `rec f 25`, wait for `Stopped recording`, and record:" with:

then take the log anchor and `rec f 25`, wait for the stop **using "Detecting a take's stop"
above** (never a whole-log grep — the pre-roll marker is still inside a 100-line tail at this
point), confirm the on-disk DNG count is exactly 25 before measuring, and record:

EDIT 2b — replace Stage 1 steps 6 and 7 with:

6. Capture the log anchor `A`, then `session-send "rec f <frames_5min>"`. Confirm the
   `Received:` echo and the `Armed exact frame-limited stop` line in the anchored region.
   Poll the anchored region every 60 s per "Detecting a take's stop". The take must stop
   itself at the frame count. Do not send anything else to the session while recording.
7. Once the anchored region shows `Exact frame-limited stop reached` → `Stopped recording`
   **and** `redis-cli GET is_recording` is `0`: poll Redis until `is_writing` = 0 **and**
   `is_writing_buf` = 0. Then stop the sampler (`kill $(cat /tmp/c1_sampler.pid)`).
   If the sequence restarts a rep in a fresh session, re-capture the anchor — every
   `session-start` adds another pre-roll `Stopped recording`.

### M13 · [redis-and-cli] 

**Claim checked:** Stage-1 step 7: "poll Redis until is_writing = 0 and is_writing_buf = 0" proves the flush finished

**Evidence:** is_writing is not a flush indicator: mediator.py:125-129 forces it to 0 the moment recording intent drops, and it is only ever raised by a per-frame last_dng_* notification WHILE recording (mediator.py:135-142). So the conjunction reduces to is_writing_buf. is_writing_buf is raised synchronously on the is_recording=0 edge only if the LAST stats message showed framesInFlight>0 or bufferSize>0 (redis_listener.py:1438-1440) — if that stale snapshot read zero, both keys sit at 0 while frames are still in flight, and the agent proceeds to analyse/copy/delete. CineMate's own flush gate uses a different signal (_storage_is_still_flushing, polled by _final_analysis_worker, redis_listener.py:1258-1282).

**Fix (adjudicated):**

Replace step 7 of the Stage 1 per-take procedure (RUNBOOK.md:252-253) with:

7. After the take's own `Stopped recording`, wait for CineMate's post-take **analysis** to finish. Do **not** gate on `is_writing`: `mediator.py` forces it to 0 the moment recording intent drops and only ever re-raises it *while* recording, so it is always 0 here and proves nothing. `is_writing_buf` alone is also insufficient — on the stop edge `redis_listener.py` raises it only if the *last* stats message already showed `framesInFlight > 0` or `bufferSize > 0`, so a stale zero snapshot leaves it at 0 while frames are still in flight. Most importantly, `missing_frame_count` and `drop_frame_during_last_take` (which you read in step 8) are written by `analyze_frames()`, which runs *after* the flush gate — so any flush-only gate releases you before those keys are updated, and `missing_frame_count` is never reset between takes, so you would silently record the **previous** take's number.

   Poll `session-tail 100` every 5 s until exactly one of these terminal analysis lines appears for this take. Exactly one always prints for a non-preroll take:
   - `✓ All frames accounted for.`
   - `Frames within final tolerance:`
   - `Sensor ran fast:`
   - `Frame count low:`
   - `Skipping frame-sync warning because FPS or resolution changed during this take.`

   If `Waiting for buffered frames to finish writing before frame-sync analysis.` appears first, that is normal — the analysis is queued behind the flush. Keep polling for the terminal line above; it is preceded by `Buffered frame write complete; running final frame-sync analysis.`, or by `Buffered frame flush did not go idle within 30.0s; analyzing with stable on-disk count.` if the flush timed out. **Record that timeout warning in the ledger as a finding** — it means the on-disk count was taken while writes were still draining.

   Cap the wait at 90 s (CineMate's own flush timeout is 30 s). If no terminal line has appeared by then, do **not** proceed to step 8: classify the take `ABORTED-OTHER`, capture the logs, and keep the take directory.

   Secondary corroboration only, never a substitute for the terminal log line: `buffer`, `is_writing_buf` **and** `is_buffering` all read 0 on three consecutive 2 s samples.

   **Only then** stop the sampler (`kill $(cat /tmp/c1_sampler.pid)`). Stopping it at the flush edge truncates the buffer-decay tail that step 11 asks you to describe.

Additionally, in step 8, widen the session-log grep so a shortfall verdict cannot be missed — the current pattern does not match `Missing frames: … not written to disk`. Use:
`write.*fail|FAILED|xrun|overrun|drop|SYNC|memory|Missing frames|DNG index gaps|Frame count low|Sensor ran fast|did not go idle`

### M14 · [redis-and-cli] 

**Claim checked:** Stage-1 step 8: read Redis framecount, missing_frame_count, drop_frame_during_last_take, memory_alert, last_dng_cam0 as the take's evidence

**Evidence:** missing_frame_count is written in exactly one place — the post-take analysis, redis_listener.py:1897-1899 inside analyze_frames — and it is NEVER reset at record start (the record-start reset block at redis_listener.py:1382-1400 clears drop_frame, drop_frame_count, drop_frame_during_last_take and is_writing_buf, but not missing_frame_count). analyze_frames runs on a worker that first waits up to final_analysis_timeout_s = 30.0 s for the flush (redis_listener.py:150, 1258-1289). Read before that worker finishes and you silently record the PREVIOUS take's missing_frame_count against this take — the exact number the outcome class turns on.

**Fix (adjudicated):**

Replace RUNBOOK.md Stage 1 step 7 and the Redis bullet + grep clause of step 8 with the following. (Stage 2 inherits automatically — it says "Protocol = Stage 1's per-take procedure with:".)

Replace step 7 in full:

7. After `Stopped recording`, wait in two stages — do not collapse them.
   **7a — flush idle.** Poll Redis until `is_writing` = 0, `is_writing_buf` = 0 **and
   `is_buffering` = 0`. All three are required: the listener's own flush gate
   (`redis_listener.py :: _storage_is_still_flushing`, ~:1173-1191) checks all three plus a
   `framesInFlight` fallback, so polling only the first two can clear while the listener is
   still waiting.
   **7b — post-take analysis finished.** Keep polling `session-tail 60` until both of these
   lines have appeared for this take:
   `Calculated expected number of frames:` and `Actual number of recorded frames:`
   (`redis_listener.py :: analyze_frames`, ~:1846-1847). That analysis is what writes the
   take's verdict keys. Allow up to 60 s: the listener waits up to
   `final_analysis_timeout_s` = 30 s for the flush (~:150) before it even starts
   (`_final_analysis_worker`, ~:1257-1289), and the stable-DNG-count settle adds seconds more
   on a 13k-30k-file take directory.
   Only after 7b: stop the sampler (`kill $(cat /tmp/c1_sampler.pid)`).
   **If the two lines have not appeared after 60 s**, do not read the Redis verdict keys.
   Record them as `UNVERIFIED — analysis line absent`, classify the take from the analyzer
   JSON alone (`dng.count` vs frames requested; `missing_indices`), and log the anomaly — a
   missing analysis is itself a finding.

Replace the Redis bullet of step 8:

   - Redis — **only after step 7b**: `framecount`, `missing_frame_count`,
     `drop_frame_during_last_take`, `memory_alert`, `last_dng_cam0`. Two of these are written
     *only* by the post-take analysis and are unsafe to read early, in opposite directions:
     `missing_frame_count` has exactly one write site (`redis_listener.py :: analyze_frames`,
     ~:1897-1899) and is **never** cleared at record start — the record-start block
     (~:1381-1401) clears `drop_frame_count`, `drop_frame_during_last_take` and
     `is_writing_buf` but not this key — so an early read silently returns the **previous**
     take's number. That is the false-alarm direction, and it is most likely straight after an
     `AUTO-STOP-RAM-GUARD` take. `drop_frame_during_last_take` is cleared to 0 at record start
     (~:1400) and raised only by the same analysis (~:1883-1886), so an early read silently
     reads 0 = "clean" — the false-negative direction, which no other ledger column catches.
     Cross-check before writing the row: `expected − actual` from the two step-7b lines must
     equal `missing_frame_count`. If it does not, the read was early — re-read, and if they
     still disagree prefer the log numbers and note the discrepancy.

And amend the grep clause of step 8's first bullet — the current pattern does not match the
analysis lines this cross-check depends on. Use:

     `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory|Missing frames|index gaps|Frame count low|Sensor ran fast|expected number of frames|Actual number of recorded|frames accounted for`

### M15 · [redis-and-cli] 

**Claim checked:** Stage-1 step 8's evidence grep: `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` (case-insensitive) captures the take's warnings

**Evidence:** Verified against the actual emitters, the pattern misses the campaign's most important lines: the post-take loss verdict `Missing frames: %d frame(s) not written to disk (%d TC gap event(s) during recording).` (redis_listener.py:1936-1941 — the variant with no confirmed write failure contains none of the tokens); `DNG index gaps: %d missing file slot(s) in sequence` (redis_listener.py:1943-1948); `Sensor ran fast: recorded %d extra frame(s) vs %d expected` (redis_listener.py:1972-1979); both RAM-guard lines `RAM frame buffer NN% ≥ 90%! Stopping recording.` (cinepi_controller.py:2598-2600) and `RAM NN.N% ≥ 80%! Stopping recording.` (:2607-2608) — the AUTO-STOP-RAM-GUARD outcome class depends on these; and every audio-helper line (`Audio capture helper: Inserted ...`, `Audio capture helper exited before capture actually started`). It correctly catches `Disk write failure`, `DNG write FAILED`, `Drop frame detected`, `Live frame sync warning`, `Frame count low` and `Capture read failed`.

**Fix (adjudicated):**

TWO exact replacements in /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md. The grep fix alone is insufficient — without the second edit the new hits have no scoring rule and the audio verdict stays unfireable.

(1) Step 8, first bullet (currently lines 255-257). REPLACE:

   - `session-tail 400` → save to the archive as `session-log.txt`; separately grep the take
     window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` (case-insensitive) and
     record every hit in the ledger.

WITH:

   - `session-tail 400` → save to the archive as `session-log.txt`; separately grep the take
     window and record every hit in the ledger:
     ```bash
     grep -inE 'write.*fail|failed|xrun|overrun|drop|sync|memory|missing frame|index gap|ran fast|frame count low|silent frame|disk error|%! stopping recording|audio capture helper exited|tc timing' session-log.txt
     ```
     Keep `xrun|overrun` even though no xrun *event* emits those words — the only line that
     does is `cinepi-audio-capture helper not found; falling back to plain arecord without
     … xrun silence-fill`, and if that appears the take has no silence-fill protection and
     its audio verdict is void. `%! stopping recording` is the RAM-guard anchor (both guard
     lines end `%! Stopping recording.`); do not loosen it to `RAM [0-9]` — under `-i` that
     matches inside "Histogram 0" and "parameters 12".

(2) Audio verdict, PASS bullet (currently lines 152-153). REPLACE:

- **PASS** — WAV present; `|wav_duration − dng_count/fps_target| ≤ 0.5 frame period`; zero
  xrun/overrun lines in the session log for the take window.

WITH:

- **PASS** — WAV present; `|wav_duration − dng_count/fps_target| ≤ 0.5 frame period`; **and
  zero `Audio capture helper: Inserted N silent frame(s)` lines** in the session log for the
  take window. The duration check alone cannot establish PASS: the helper pads capture
  shortfalls with silence *specifically to keep the WAV aligned to wall clock*, so a take
  that lost real samples still measures the right length. Those `Inserted …` lines are the
  only evidence when the USB device under-delivers silently (no `Capture read failed` is
  emitted in that path). Any such line ⇒ WARN if the summed padding is < 1 frame period,
  FAIL otherwise; record the total padded duration either way.

### M16 · [sampler-shell] 

**Claim checked:** 0.6: `ps -eLo pid,comm,rtprio,psr | grep -Ei 'audio|dng-'` — "verify cinepi-audio-capture at rtprio 80 on core 3 ... If SCHED_FIFO is not active (rtprio `-`), that is the known pending `setcap` item" (RUNBOOK.md:204-207)

**Evidence:** cinepi-raw/cinepi/cinepi_audio_capture.cpp:534 calls `tryElevateRealtimePriority()` from main() only, and only `if (!options.discardOutput)`. That function (line 246-296) calls `sched_setscheduler(0, SCHED_FIFO, &param)` and `sched_setaffinity(0, ...)` — both act on the CALLING THREAD only. Line 564 spawns a separate `std::thread writerThread` which is never named (grep for pthread_setname_np in that file returns 0 hits) and never elevated. With `-L`, ps therefore emits TWO rows whose comm is `cinepi-audio-ca` (kernel comm limit truncates the 20-char name to 15): one at rtprio 80 / psr 3, and one at rtprio `-` on an arbitrary core. On a perfectly healthy rig the runbook's own trigger condition ("rtprio `-`") is satisfied — so it fires the config intervention on a correct install and mutates the system being measured.

**Fix (adjudicated):**

Replace RUNBOOK.md lines 202-209 (all of step 0.6) with:

0.6 **Audio preflight.** `arecord -l` (mic must be present — if absent, STOP and ask the
operator to attach it). `getcap $(command -v cinepi-audio-capture)`.

**The authoritative SCHED_FIFO signal is the session log, not `ps`.** During one of the 0.3
validation takes, grep the session log (`session-tail`, or `/tmp/cinemate_cli.log`) for
`Audio capture helper: Capture thread`. A healthy rig prints both of these once per take, at
record start:

- `Audio capture helper: Capture thread elevated to SCHED_FIFO priority 80`
- `Audio capture helper: Capture thread pinned to CPU 3 (of 4 available)` (the core number is
  `nCpus-1`)

The failure form is `Audio capture helper: Could not set SCHED_FIFO capture priority
(Operation not permitted); continuing at default scheduling`. **That line, and only that
line, is the known pending `setcap` item.**

**`ps` is corroboration only, and it has a designed-in decoy row.**
`ps -eLo pid,tid,comm,rtprio,psr | grep -Ei 'audio|dng-'`. The binary name is truncated to
`cinepi-audio-ca` by the 15-char kernel comm limit, and the process runs **two** threads:

- the ALSA capture thread (`tid` == `pid`) — MUST show `rtprio` 80 and `psr` 3;
- the WAV writer thread — deliberately left unelevated and unpinned, so it legitimately shows
  `rtprio -` on an arbitrary core. **Ignore it. It is not a fault and it is always there.**

A stray `cinepi-audio-capture --discard-output` idle-VU monitor, if one is still alive, is
also never elevated by design — ignore that row too. The `ps` check FAILS only if **no**
`cinepi-audio-ca` row shows `rtprio` 80. Separately verify **no `dng-enc-*`/`dng-dsk-*`
thread on core 3** — those threads are properly named, so that half of the grep is reliable.

If **and only if** the log shows the `Could not set SCHED_FIFO capture priority` line: log it
in the ledger, apply the documented fix
(`sudo setcap cap_sys_nice+ep <path-to-cinepi-audio-capture>`), restart the session, and
re-verify **against the log line** (not against the `ps` table — the `rtprio -` writer row
survives a successful fix and will otherwise make re-verification loop forever). This is the
one sanctioned config intervention. Never apply it on the basis of an `rtprio -` row alone.

### M17 · [sampler-shell] 

**Claim checked:** 0.6: "apply the documented fix (`sudo setcap cap_sys_nice+ep <path-to-cinepi-audio-capture>`) ... This is the one sanctioned config intervention." (RUNBOOK.md:207-209); and `getcap $(command -v cinepi-audio-capture)` as the preflight probe (RUNBOOK.md:203)

**Evidence:** `grep -rn -I setcap` over cinemate/, cinepi-raw/, cinemate-handbook/ and development/ returns ZERO hits outside this RUNBOOK itself and its RESULTS.md. There is no documented setcap fix. The actual installed mechanism is cinemate-install.sh:1527-1545 `configure_audio_rtprio()`, which writes /etc/security/limits.d/cinemate-audio.conf containing `@audio - rtprio 80` + `@audio - memlock unlimited` and runs `sudo usermod -aG audio "$PI_USER"`, plus services/cinemate-autostart/cinemate-autostart.service:27 `LimitRTPRIO=80`. Consequently `getcap` returning EMPTY is the NORMAL, correct state on every properly installed Pi — the runbook treats the healthy state as the failure signature. (cinepi_audio_capture.cpp:273 does mention CAP_SYS_NICE, but as one of two alternatives: "Grant CAP_SYS_NICE or raise the rtprio ulimit". Note also cinemate-install.sh:1532's comment says `LimitRTPRIO=30` — that comment is stale; the unit really carries 80.)

**Fix (adjudicated):**

Replace RUNBOOK.md lines 202-209 (all of 0.6) with:

0.6 **Audio preflight.** `arecord -l` (mic must be present — if absent, STOP and ask the
operator to attach it). Then verify the RT-scheduling grant. `cinepi-audio-capture` raises
itself to SCHED_FIFO 80 in `tryElevateRealtimePriority()`; the permission that lets it comes
from the installer's `configure_audio_rtprio()` (`cinemate-install.sh`), not from file
capabilities. Note that `session-start` runs cinemate **outside systemd** (it stops
`cinemate-autostart`, then launches `tail -f … | bash -lic cinemate` over SSH), so the unit's
`LimitRTPRIO=80` does **not** apply to this campaign — the limits.d drop-in is the only grant
in play. Check all three:

  1. `cat /etc/security/limits.d/cinemate-audio.conf` → must contain `@audio - rtprio 80`.
  2. `id pi` → must list the `audio` group.
  3. `ulimit -r` (run through the same helper SSH transport) → must return `80`.

During one of the 0.3 validation takes: `ps -eLo pid,comm,rtprio,psr | grep -Ei 'audio|dng-'`
— verify `cinepi-audio-capture` at `rtprio` 80 on core 3, and **no `dng-enc`/`dng-dsk` thread
on core 3**. Cross-check the session log: `Capture thread elevated to SCHED_FIFO priority 80`
= granted; `Could not set SCHED_FIFO capture priority` = not granted.

If `rtprio` shows `-`, log it in the ledger, then re-apply the **installer's own** step for
whichever of 1-3 failed:

  - drop-in missing/wrong →
    `printf '@audio - rtprio 80\n@audio - memlock unlimited\n' | sudo tee /etc/security/limits.d/cinemate-audio.conf`
  - `pi` not in `audio` → `sudo usermod -aG audio pi`

Then `session-stop` and `session-start` — the helper opens a **fresh SSH login** per command,
so PAM re-reads group membership and limits; no reboot is normally needed. Re-verify all of
1-3 and the `ps` readout. Only if `ulimit -r` is still not 80 after a fresh login, reboot and
re-verify. This is the one sanctioned config intervention.

**Do not run `setcap`.** It appears nowhere in `cinemate`, `cinepi-raw`, `cinemate-handbook`
or the installer — it is not this stack's mechanism (the `CAP_SYS_NICE` wording in
`cinepi_audio_capture.cpp` is one of two alternatives, and this stack chose the ulimit).
Beyond leaving the rig in a configuration no shipped install has — which would make every
audio number in this campaign describe something users do not run — `cinemate_dev.py
build-raw` executes `sudo meson install`, which replaces `/usr/local/bin/cinepi-audio-capture`
and silently drops any file capability. A cap applied in Phase 0 would therefore vanish before
Stage 2 and change the audio scheduling regime mid-campaign with nothing to detect it.

---

Three companion edits, required or the document still contradicts itself:

RUNBOOK.md:32 — replace "(e.g. a missing `setcap`)" with
"(e.g. a missing RT-scheduling grant — see 0.6)".

RUNBOOK.md:70-71 — replace "A **pending item from that fix chain: the SCHED_FIFO `setcap` may
never have been applied on this Pi** — Phase 0 checks it." with
"The SCHED_FIFO grant comes from the installer's `/etc/security/limits.d/cinemate-audio.conf`
(`@audio - rtprio 80`) plus `pi` in the `audio` group. Older notes call this a pending
`setcap` item — that is stale; `setcap` is not used anywhere in this stack. Phase 0 verifies
the limits.d grant."

RESULTS.md:53-61 — replace the two rows
"| `getcap` on cinepi-audio-capture | | |" and "| Intervention applied? (setcap) | | |" with:

| limits.d shows `@audio - rtprio 80` | | `cat /etc/security/limits.d/cinemate-audio.conf` |
| `pi` in `audio` group | | `id pi` |
| `ulimit -r` over helper SSH | | `ulimit -r` |
| SCHED_FIFO line in session log | | session log |
| Intervention applied? (limits.d / usermod) | | |

### M18 · [sampler-shell] 

**Claim checked:** One CSV per take at `/home/pi/c1/samples/<take-id>.csv` (RUNBOOK.md:125-126) is a clean per-take record, given the sampler appends its header with `>>` (RUNBOOK.md:115) and always uses the single fixed pidfile `/tmp/c1_sampler.pid` (line 113)

**Evidence:** The runbook itself prescribes a retry path — line 280-281: "If a session dies mid-take, classify ABORTED-OTHER, capture logs, `cinemate_dev.py stop`, and restart the sequence at the same rep once." Same rep = same take-id = same CSV path. I ran the stubbed sampler twice against one file: the result is a 4-line CSV with a duplicate header at line 3 and two takes' samples concatenated. Any max-`buffer` / curve-shape analysis over that file is silently wrong, and a header row in the middle breaks naive parsers — and this hits precisely the aborted takes that most need forensic reading. Separately, the fixed pidfile means a sampler that was never killed (aborted take) is orphaned the moment the next one overwrites the pidfile: it keeps appending to its own CSV for the rest of the campaign and can never be killed via the documented command.

**Fix (adjudicated):**

Five edits. (1)-(2) replace the sampler; (3)-(6) close the orphan and the take-id reuse.

(1) RUNBOOK.md lines 110-123 — replace the sampler body with:

```bash
#!/bin/bash
# c1_sampler.sh OUTFILE [PIDFILE] — 2 s cadence recorder-state sampler.
# Stop with: kill $(cat <PIDFILE>)   (default /tmp/c1_sampler.pid)
OUT="$1"
PIDF="${2:-/tmp/c1_sampler.pid}"
# Never touch an existing take CSV: a second run means a colliding take-id, and the
# existing file is an earlier take's evidence. Fail loud rather than append or truncate.
# This guard MUST come before the pidfile write, so a refused start cannot clobber the
# pidfile of a sampler that is still running.
if [ -e "$OUT" ]; then
  echo "c1_sampler: $OUT already exists — use a distinct take-id (e.g. <take-id>r1)" >&2
  exit 1
fi
echo $$ > "$PIDF"
g() { redis-cli GET "$1" 2>/dev/null | head -c 32; }
echo "ts,buffer,buffer_size,framecount,fps_actual,is_writing_buf,write_speed_to_drive,space_left,memory_alert,dirty_kb,writeback_kb,temp,throttled" > "$OUT"
while true; do
  d=$(awk '/^Dirty:/{a=$2} /^Writeback:/{b=$2} END{print a","b}' /proc/meminfo)
  t=$(vcgencmd measure_temp | tr -d "temp='C")
  th=$(vcgencmd get_throttled | cut -d= -f2)
  echo "$(date +%s),$(g buffer),$(g buffer_size),$(g framecount),$(g fps_actual),$(g is_writing_buf),$(g write_speed_to_drive),$(g space_left),$(g memory_alert),$d,$t,$th" >> "$OUT"
  sleep 2
done
```

(2) RUNBOOK.md lines 125-126 — replace with:

Start it right before each `rec`, stop it after the post-take flush. One CSV per take:
`/home/pi/c1/samples/<take-id>.csv`. The sampler refuses to write a file that already
exists — if it exits with `already exists`, you have a take-id collision (see the retry
rule in Stage 1), not a sampler bug. Never resolve it by deleting the old CSV.

(3) RUNBOOK.md line 237 — replace with:

Take IDs: `S1-<mode-letter><rep>` (e.g. `S1-A1`, `S1-A2`, `S1-A3`, `S1-B1`, …). A re-run of a
rep after an abort gets a **new** id with an `r<n>` suffix (`S1-A1` → `S1-A1r1`). Never reuse
an aborted take's id: the sampler CSV (step 5), the analyzer JSON (step 8, a truncating `>`
redirect) and the Mac archive directory (step 9) are all keyed on the take-id, so reuse
appends to or overwrites the aborted take's evidence. Add the retry as its own row in the
Stage 1 table, directly beneath the aborted one.

(4) RUNBOOK.md lines 248-249 (step 5) — replace with:

5. Start the sampler. Reap any orphan from an earlier aborted take first — `cinemate_dev.py
   stop` does not kill samplers:
   `pkill -f /home/pi/c1/c1_sampler.sh || true`
   `nohup /home/pi/c1/c1_sampler.sh /home/pi/c1/samples/<take-id>.csv /tmp/c1_sampler_<take-id>.pid >/dev/null 2>&1 &`
   Then confirm exactly one is running: `pgrep -fc /home/pi/c1/c1_sampler.sh` must print `1`.
   If the sampler exited with `already exists`, stop and fix the take-id — do not proceed.

(5) RUNBOOK.md lines 252-253 (step 7) — replace the last sentence with:

   Then stop the sampler (`kill $(cat /tmp/c1_sampler_<take-id>.pid)`) and confirm it is gone:
   `pgrep -fc /home/pi/c1/c1_sampler.sh` must print `0`.

(6) RUNBOOK.md line 268 (step 11) — insert before "Ledger:":

11. Validate the CSV before archiving. Both checks must pass:
    `grep -c '^ts,' /home/pi/c1/samples/<take-id>.csv` must print `1`, **and** timestamps must
    be strictly increasing:
    `awk -F, 'NR>2 && $1<=p {print "DUP/OUT-OF-ORDER ts at line "NR; e=1} NR>1{p=$1} END{exit e}' /home/pi/c1/samples/<take-id>.csv`
    must exit 0. The second check is the load-bearing one — a duplicate header is only
    visible when two samplers started fresh; interleaved rows from an orphan show up only as
    repeated timestamps. Either failure means two samplers wrote one file: the buffer curve
    and any `framecount`-delta fps from it are invalid, so mark the take's sampler data
    UNUSABLE in the ledger rather than reporting numbers from it.

(7) RUNBOOK.md lines 280-281 — replace with:

- If a session dies mid-take: classify `ABORTED-OTHER`; **kill the sampler first**
  (`pkill -f /home/pi/c1/c1_sampler.sh`) — the abort path never reaches step 7 and
  `cinemate_dev.py stop` does not touch samplers, so it would otherwise keep appending to
  that take's CSV for the rest of the campaign and be unkillable via the documented pidfile;
  capture logs; archive the partial CSV under the aborted take-id; `cinemate_dev.py stop`;
  then restart that rep **once** under a new `r<n>` take-id (e.g. `S1-A1` → `S1-A1r1`).

### M19 · [sampler-shell] 

**Claim checked:** 0.6: "During one of the 0.3 validation takes: `ps -eLo pid,comm,rtprio,psr | grep -Ei 'audio|dng-'`" (RUNBOOK.md:203-205) is runnable as sequenced

**Evidence:** Ordering conflict inside Phase 0: step 0.3 (RUNBOOK.md:184-188) completes all its validation takes and ends with "Delete each 25-frame validation take after recording its numbers" BEFORE the agent ever reaches 0.6. There is no take running at 0.6. Worse, even if interleaved the window is ~1-2 s: cinemate/src/module/cli_commands.py:345-355 confirms `rec f <n>` is a frame-count-limited record, so `rec f 25` lasts 25/fps s = 1.0 s at the 25 fps control mode and 2.1 s at 4056x3040@11.72. And the check cannot be moved to idle: cinepi_audio_capture.cpp:534 gates `tryElevateRealtimePriority()` behind `if (!options.discardOutput)`, so the idle monitor instance is NEVER elevated — only a live recording instance is. As written the audio-core invariant goes unverified for the entire campaign, or the agent gets a false negative and applies the (already-wrong) setcap remedy.

**Fix (adjudicated):**

Replace RUNBOOK.md lines 202-209 (all of step 0.6) with:

0.6 **Audio preflight.** `arecord -l` (mic must be present — if absent, STOP and ask the
operator to attach it).

Helper path first: cinepi-raw resolves the helper as the sibling of its own executable,
then `/usr/local/bin`, then `/usr/bin` (`locateAudioCaptureHelper()`,
cinepi_sound.cpp:50-71), so `command -v cinepi-audio-capture` can name a binary that is
never executed. Run `getcap` on every candidate that exists and record each result.

**The rtprio/core check requires its own live take — an idle sample is a guaranteed false
negative.** `cinepi-audio-capture` elevates itself only when it is writing a WAV:
`tryElevateRealtimePriority()`, which sets *both* SCHED_FIFO 80 *and* the pin to the last
core, is gated behind `if (!options.discardOutput)` (cinepi_audio_capture.cpp:533-534,
246-295). The always-running idle VU monitor is launched with `--discard-output`
(cinepi_sound.cpp:1119), so at idle the process appears in `ps` with `rtprio -` and no
pinning — both assertions below fail at idle even on a perfectly healthy rig. Never check
this outside a recording. The 0.3 validation takes cannot be used either: `rec f 25` is
frame-count-limited, so the window is 25/fps ≈ 1.0-2.3 s, and they are deleted by the end
of 0.3.

So, after 0.5 has fixed each mode's test fps, run one dedicated preflight take on **mode C**
(or B if there is no C — pick the lowest data rate; this check needs a live recording, not
load): `session-send "rec f <test_fps × 30>"`. While it runs, sample the thread table three
times ~8 s apart:

```bash
ps -eLo pid,tid,comm,rtprio,psr,args | grep -Ei '[c]inepi-audio|dng-(enc|dsk)'
```

Record from those samples:

- Exactly **one** `cinepi-audio-capture` thread at `rtprio 80` with `psr` = the last core
  (3 on this 4-core unit). Its WAV-writer thread is deliberately not elevated
  (cinepi_audio_capture.cpp:565) — one non-RT thread in that process is expected, not a
  fault.
- **No** `dng-enc-*` / `dng-dsk-*` thread on the audio core. `psr` is only a last-CPU
  sample, so confirm the mask deterministically for one encode and one disk thread:
  `taskset -pc <tid>` — neither mask may contain the audio core.
- `readlink /proc/<audio-pid>/exe` — this is the binary that must carry the capability.

Then wait for `Stopped recording`, poll until `is_writing_buf` = 0, and delete the preflight
take (`rm -rf` the named directory only, never a wildcard).

If the capture thread reads `rtprio -` **during that take**, that is the known pending
`setcap` item: log it in the ledger, apply `sudo setcap cap_sys_nice+ep <the
readlink /proc/<pid>/exe path>`, restart the session, and **re-verify with a second
preflight take** — not at idle. This is the one sanctioned config intervention. If rtprio is
still `-` after the setcap, STOP and report to the operator rather than attempting further
remedies.

### M20 · [sampler-shell] 

**Claim checked:** Lines 100-103 + 156: "check `/Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/` for the sync-matrix notes from the audio-sync campaign (`sync-matrix.md`, possibly under a phase subfolder) ... On FAIL, run the sync-matrix deep-dive method before writing the verdict"

**Evidence:** `ls -la /Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/` returns only `.DS_Store` — the directory is empty. `find /Users/patrikeriksson/Documents /Users/patrikeriksson/.claude -iname '*sync*matrix*'` returns nothing, and `grep -rn 'sync-matrix' --include='*.md'` across the whole workspace hits only RUNBOOK.md:101, 102 and 156 — i.e. the runbook is the sole reference to a file that does not exist anywhere. The mandatory deep-dive method for every audio FAIL verdict is therefore unreachable, and a Sonnet session will either stall at the first FAIL or invent a method (which the runbook explicitly forbids: "before inventing one").

**Fix (adjudicated):**

Two edits. Do NOT apply the critic's proposed text.

EDIT 1 — replace RUNBOOK.md lines 100-103 (the "Prior sync-analysis method" bullet) with:

- Audio deep-dive method (self-contained). There is no external sync-matrix file — do not go
  looking for one. The firmware already computes and logs every number you need, once per
  take. Run these three greps against the take's session log:
  1. `honest WAV timecode` → one line per take:
     `... video <V>s, input <I>s, start delta <D>s, capture rate <R> Hz ...`
     (`cinepi_sound.cpp:1386/1393`). `<V>` is computed from the encoder's real per-frame
     timestamps (`(last − first) + mean frame duration`), so it already IS the
     `dng_count × mean_frame_interval` figure. **`I − V` is the authoritative deviation** —
     use it, not `wav_duration − dng_count/fps_target`. Record V, I, D, R.
     If you instead find `No audio start marker received` (`cinepi_sound.cpp:1506`) or
     `Audio capture helper exited before capture actually started`, the helper never started
     cleanly: record that and classify the audio FAIL-NO-MARKER.
  2. `Audio capture helper: Inserted` → each hit reads
     `Inserted <N> silent frame(s) to cover a capture shortfall of <X>s`
     (`cinepi_audio_capture.cpp:663`, reaching the log because the helper is launched with
     `2>&1` and this line matches no marker prefix). Count the events and sum the seconds.
     **This is the sample-loss evidence on this firmware — a take can lose real audio with
     zero occurrences of the words "xrun" or "overrun".** Also grep
     `Audio capture helper: Capture read failed` for hard ALSA aborts.
  3. `Attached WAV metadata without altering PCM` → the final
     `audio start offset <D>s (<F> frames, <S> samples)` (`cinepi_sound.cpp:1571`).
  Interpretation: the helper reconciles against wall clock and pads shortfalls with silence,
  so a WAV of the right length can still be full of inserted silence. The sum from (2) is the
  loss magnitude; `I − V` from (1) is the residual the padding failed to cover. Non-zero (2)
  with near-zero (1) = contention sample loss that the fill absorbed (report it — it is the
  finding, even though the length is right). Both non-zero = the fill under-covered.
  Record all three numbers (V/I/D, fill events + summed seconds, final offset) in the ledger.
  Do **not** try to derive any of this from `<SAMPLES_CAPTURED:>`, `TS_START` or
  `TS_CLOSE_FILE`: those markers are consumed by `cinepi_sound.cpp`'s pipe parser and never
  reach the log, and `SAMPLES_CAPTURED` counts inserted silence, so it matches `wav_frames`
  even after heavy loss.

EDIT 2 — line 156 and the paragraph at lines 157-160 must both change, or the same dead end
returns via the analyzer JSON (which contains no per-frame timestamps — only count,
first/last index, missing_indices, and exiftool metadata for DNG #0).

Line 156, replace:
  `  On FAIL, run the sync-matrix deep-dive method before writing the verdict.`
with:
  `  On FAIL, run the audio deep-dive method above before writing the verdict.`

Lines 157-160, replace the whole "If the coarse deviation is dominated by sensor-vs-target
fps offset, recompute against `dng_count × mean_frame_interval` using the DNG timestamps from
the analyzer JSON, and record both numbers." paragraph with:

If the coarse deviation is dominated by sensor-vs-target fps offset, do not try to recompute
from the analyzer JSON — it carries no per-frame timestamps. Take `video`/`input` from the
`honest WAV timecode` log line instead (step 1 above) and record both the coarse number and
`I − V`.

RECOMMENDED (not required for this finding): line 153's PASS criterion "zero xrun/overrun
lines in the session log" should become "zero `Audio capture helper: Inserted ... silent
frame(s)` lines and zero xrun/overrun lines", since the real sample-loss string contains
neither word and a degraded take would otherwise score PASS.

### M21 · [claims-audit] 

**Claim checked:** "The DNG encoder's RAM buffer is small on this unit and the **80 % RAM guard force-stops recording** when the write backlog fills it" (RUNBOOK.md:51-53), plus the outcome class "cinepi-raw force-stopped the take on the RAM guard" (RUNBOOK.md:147)

**Evidence:** The number 80 appears nowhere in cinepi-raw: `grep -rn -E '0\.8|80 ?%|MemAvailable' /Users/patrikeriksson/Documents/cinemate/cinepi-raw/cinepi/` returns only the MemAvailable read at dng_encoder.cpp:833-837. dng_encoder.cpp:831 and :846 read `Dynamic RAM limit: 90 % of current MemAvailable` / `constexpr double RAM_FRACTION = 0.90;`. It is also not in the handbook: cinemate-handbook/architecture/cinepi-raw.md:32-33 says only "If the DNG encoder's buffer fills, recording is force-stopped and a warning is logged" — no percentage. 80 is a cinemate constant: cinepi_controller.py:256 `self.RAM_LIMIT_PERCENT = 80` — and it is the *coarse system-RAM backstop*, explicitly labelled so at :257-260, where the write-backlog guard is `self.BUFFER_LIMIT_PERCENT = 90` (cinepi_controller.py:2596-2604, computed as `buffer`/`buffer_size` from Redis by `_buffer_fill_percent`, :2573-2583). There are two independent auto-stops, not one, and neither is at 80 % of the encoder buffer: (a) cinepi-raw, cinepi_raw.cpp:220-229, fires on `buffer_full()` = `ram_buffers_ + 2 >= max_ram_buffers_` (dng_encoder.hpp:151-155, i.e. pool exhausted, not a percentage) and logs `RAM pool exhausted — recording stopped`; (b) cinemate, cinepi_controller.py:2597/2606, logs `RAM frame buffer NN% ≥ 90%! Stopping recording.` or `RAM NN.N% ≥ 80%! Stopping recording.` and sets `memory_alert` (:2626-2631). "Small on this unit" is also wrong: the pool is 90 % of MemAvailable / buffer_size; at 4056x3040 12-bit buffer_size is 18 MiB (dng_encoder.cpp:803-806) and PI-016 measured MemAvailable ~2970-3113 MB, giving order 150 frames (~13 s of runway at 11.72 fps), and `memory_alert` never fired across a full 60 s take at that mode (PI-VERIFICATION-QUEUE.md:1286-1292).

**Fix (adjudicated):**

Four edits, all in the same commit. Sources: cinepi_raw.cpp:220-230, dng_encoder.hpp:151-155, dng_encoder.cpp:803-806/846, cinepi_state.hpp:67-69, cinepi_controller.py:256-260/2573-2583/2596-2610/2627, cinepi_controller.cpp:395-396, PI-VERIFICATION-QUEUE.md:15 and :1286-1300.

EDIT 1 — replace RUNBOOK.md:51-54 (the whole first bullet) with:

- **Three independent auto-stops exist and they are not the same thing.** (1) *cinepi-raw* stops
  when its DNG RAM pool is exhausted — `buffer_full()` is `ram_buffers_ + 2 >= max_ram_buffers_`
  (`dng_encoder.hpp:151`), fired at `cinepi_raw.cpp:220`, log `RAM pool exhausted — recording
  stopped` (relayed into the cinemate log with a `[cam0]` prefix). The pool is sized once at
  encoder setup as 90 % of `MemAvailable` / per-frame buffer (`dng_encoder.cpp:846`) — order
  150 frames ≈ 13 s of runway at 4056x3040 12-bit on this board. **Read the real number from
  Redis `buffer_size` in 0.7; never assume it.** This path is nasty: `setRecording(false)`
  (`cinepi_state.hpp:67`) only flips a local bool — it does **not** set `memory_alert` and does
  **not** clear cinemate's `is_recording`, so it presents as a *hang* (framecount frozen,
  `is_recording` still 1, the frame-limit stop never reached). Its only signature is that log
  line. (2) *cinemate's watchdog* (`cinepi_controller.py:2596-2602`) stops at RAM-frame-buffer
  fill ≥ **90 %** (`BUFFER_LIMIT_PERCENT`, used/total slots — this is the real write-backlog
  signal), log `RAM frame buffer NN% ≥ 90%! Stopping recording.` (3) The same watchdog's coarse
  backstop (`:2604-2610`) stops at system RAM ≥ **80 %** (`RAM_LIMIT_PERCENT`), log
  `RAM NN.N% ≥ 80%! Stopping recording.` Paths (2) and (3) both write `memory_alert` (`:2627`);
  path (1) does not. Because cinemate polls at 4 Hz and trips at 90 % of the pool, **(2) fires
  before (1)** — expect cinemate's guard, not cinepi-raw's.
- **The dev Pi is a 4 GB CM5 Lite, not 2 GB.** `PI-VERIFICATION-QUEUE.md:15` measured 4048 MB
  total; PI-016 (`:1286-1300`) ran a full 60 s take at 4056x3040 12-bit with `available` never
  below ~2970 MB and `memory_alert` never firing. Older notes saying 2 GB are stale. Re-confirm
  with `free -b` in 0.7 and record it; do not carry the 2 GB figure into any prediction.
- A RAM-guard auto-stop is a *distinct outcome class* (drive can't sustain the data rate), not
  a drop-frame bug — classify it as such, never as "dropped frames".

EDIT 2 — replace RUNBOOK.md:147 with:

| `AUTO-STOP-RAM-GUARD` | Any of the three guards ended the take early: cinemate's buffer guard or system-RAM backstop (`memory_alert` non-zero, log `... Stopping recording.`), or cinepi-raw's pool exhaustion (log `RAM pool exhausted`, `memory_alert` stays 0 and the take *hangs* with `is_recording`=1 and framecount frozen). Record which one, quoting the log line |

EDIT 3 — replace RUNBOOK.md:211-213 (0.7) with:

0.7 **RAM runway.** `free -b` — record `MemTotal` and `MemAvailable` (this settles the board
size; see the known-context bullet). After setting each mode, read `buffer_size` from Redis
(it is the pool size in **frames**, `maxRamBuffers()`, `cinepi_controller.cpp:395`) and record
both `pool_runway_s = buffer_size / fps` (cinepi-raw's exhaustion point) and
`guard_runway_s = 0.9 × buffer_size / fps` (cinemate's 90 % buffer guard — the one that
actually fires first). `guard_runway_s` is how long a full disk stall can last before the take
is auto-stopped.

EDIT 4 — replace RUNBOOK.md:224-225 (the last sentence of 0.10) with:

The RAM-guard confound must appear explicitly in the reasoning for any mode whose data rate is
within 15 % of the sustained speed — name **which** guard you expect (cinemate's 90 % buffer
guard is the expected one on this 4 GB board; the 80 % system-RAM backstop is not) and cite the
`guard_runway_s` from 0.7.

EDIT 5 (consequential, same commit) — replace the grep pattern at RUNBOOK.md:257 with:

     window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory|RAM pool exhausted|Stopping recording` (case-insensitive) and

(Match on the ASCII substrings `RAM pool exhausted` and `Stopping recording` — the real log
lines contain an em-dash and `≥`, which are fragile to type into a shell pattern.)

### M22 · [claims-audit] 

**Claim checked:** "The dev Pi is a **2 GB CM5 Lite**" (RUNBOOK.md:51), and the Phase 0.10 requirement that "The 2 GB RAM-guard confound must appear explicitly in the reasoning" (RUNBOOK.md:224)

**Evidence:** Directly contradicted by measurement in the runbook's own cited source chain. PI-RESULTS-2026-08-24.md:27 (PI-016 row): "available memory never dropped below ~2970MB of 4048MB total. The ~300MB-free-at-peak argument does not hold on this (4GB, not 2GB) board". PI-VERIFICATION-QUEUE.md:15-17 session header: "kernel `6.12.93+rpt-rpi-2712`, **4048 MB RAM total** (prior notes on this unit say 2 GB — that's stale or wrong)". PI-016's result block, PI-VERIFICATION-QUEUE.md:1286-1292: across a full 60 s take at 4056x3040 12-bit (the most demanding mode on the sensor), "available" stayed at 2969-3113 MB of 4048 MB and "memory_alert never fired", with write_speed_to_drive sustained at 170-190 MB/s. The handbook records the same correction as a headline lesson: cinemate-handbook/lessons/hardware-log.md:69-70 "— the resource argument an architecture decision partly relied on does not hold on this (4 GB, not 2 GB as assumed) board (PI-016)", and :76-78 names "measuring instead of arguing from assumed board specs (PI-016)" as one of the three widest lessons of the review. Why this is a blocker rather than cosmetic: (a) 0.10 mandates writing the false 2 GB confound into the prediction reasoning for every mode within 15 % of sustained speed, so every prediction row is anchored on a falsified premise; (b) the encoder pool scales with MemAvailable (dng_encoder.cpp:846), so the runway computed in 0.7 is ~2.5x what a 2 GB board would give and the campaign's headline hypothesis is mis-sized; (c) the Phase 0 STOP-check list (RUNBOOK.md:229-231) enumerates "different sensor, exFAT instead of ext4, missing mic, throttling at idle" but NOT a RAM mismatch, so 0.7's `free -b` will surface 4048 MB and the session has no instruction to treat it as design-changing — the wrong number survives into the ledger.

**Fix (adjudicated):**

Four edits. The first two are the finding proper; the third and fourth are required for internal coherence, since fixing the RAM figure without fixing the guard mechanics leaves the session expecting a guard it has no threshold or log line for.

(1) RUNBOOK.md:51-54 — replace the whole bullet:

- The dev Pi is a **CM5 Lite with 4048 MB RAM total** (measured — `PI-VERIFICATION-QUEUE.md:15`,
  PI-016; earlier notes on this unit saying 2 GB are stale and were corrected on hardware).
  There are **two** recording auto-stops, both in cinemate's `_recording_worker`
  (`cinepi_controller.py`), and both write `memory_alert`:
  - **Primary — encoder-buffer guard, `BUFFER_LIMIT_PERCENT = 90`.** Trips when the DNG
    encoder's RAM frame pool is 90 % full (Redis `buffer` / `buffer_size`). Log line:
    `RAM frame buffer <pct>% ≥ 90%! Stopping recording.` The pool is sized at encoder
    config as `0.90 × MemAvailable / bytes_per_frame` (`dng_encoder.cpp:846`), so on this
    4 GB board it is roughly 2.5x what a 2 GB board would give. **This is the guard a
    sustained write backlog actually trips — the one this campaign is here to study.**
  - **Backstop — system-RAM guard, `RAM_LIMIT_PERCENT = 80`.** Trips on total system RAM.
    PI-016 measured available RAM never below ~2970 MB of 4048 MB (~25 % used) across a
    full 60 s take at 4056x3040 12-bit with `memory_alert` never firing, so this guard is
    effectively unreachable on this rig. If it fires, something is wrong beyond the take.
  cinepi-raw itself does **not** force-stop: `ram_cv_.wait()` (`dng_encoder.cpp:1389`) is
  blocking backpressure, not an abort. An auto-stop is a *distinct outcome class* (drive
  can't sustain the data rate), not a drop-frame bug — classify it as such, never as
  "dropped frames", and record **which** guard fired from the log line.

(2) RUNBOOK.md:224-225 — replace "The 2 GB RAM-guard confound must appear explicitly in the reasoning for any mode whose data rate is within 15 % of the sustained speed." with:

  The **encoder-buffer-guard** confound must appear explicitly in the reasoning for any mode
  whose data rate is within 15 % of the sustained speed, sized from the actual `buffer_size`
  frame count read in 0.7 (`runway_s = buffer_size / fps`) — never from an assumed board RAM
  figure.

(3) RUNBOOK.md:147 — replace the `AUTO-STOP-RAM-GUARD` row definition with:

| `AUTO-STOP-RAM-GUARD` | **cinemate** force-stopped the take on one of the two memory guards. Record which, from the session log: `RAM frame buffer <pct>% ≥ 90%` (encoder-buffer guard, expected) or `RAM <pct>% ≥ 80%` (system-RAM backstop, unexpected on this board). `memory_alert` fires for both and does not disambiguate them |

(4) RUNBOOK.md:230 — extend the STOP-check example list to name the RAM case:

  section in a way that changes the test design (different sensor, exFAT instead of ext4,
  missing mic, throttling at idle, **a `free -b` total other than ~4048 MB**), report to the
  operator and wait before Stage 1.

### M23 · [math-audit] 

**Claim checked:** Phase 0.4: `dd if=/dev/zero of=/media/RAW/c1_speedtest bs=4M count=1024 oflag=direct conv=fsync` measures 'Sustained write speed' (RUNBOOK.md:190-193), and that number feeds the 0.85 x sustained term of the fps formula.

**Evidence:** bs=4M count=1024 = 4 GiB = 4.295 GB. python3: at 500/400/300 MB/s that is 8.59/10.74/14.32 s per run (17-29 s for both runs) - the TIME is fine. But the takes it must predict are 34.7-61.0 GB (Stage 1) and 69.4-122.1 GB (Stage 2), i.e. 8-28x the dd sample, and run for 300-600 s vs dd's ~11 s. A 4 GiB O_DIRECT burst lands entirely inside a consumer NVMe pSLC write cache (typically 3-12% of capacity = 30-120 GB on a 1 TB drive), so dd reports BURST speed, not sustained. 'Run it twice, keep the lower number' does not help: 8 GiB total is still far inside the cache. The inflated S then inflates cap = 0.85 x S in the RUNBOOK.md:196 formula, selecting an fps the drive cannot hold for 5 minutes - manufacturing exactly the AUTO-STOP-RAM-GUARD / dropped-frame outcomes the campaign exists to characterize, and making every Stage 1 result uninterpretable.

**Fix (adjudicated):**

Replace RUNBOOK.md lines 190-193 (section 0.4) with:

0.4 **Storage identity + sustained write speed.** `findmnt -no SOURCE,FSTYPE /media/RAW`
(expect the NVMe, ext4), `df -B1 /media/RAW`, and identify the drive itself:
`cat /sys/block/nvme0n1/device/model` plus capacity and current % used. The burst-vs-sustained
gap is a property of the NAND, so the number below is uninterpretable without knowing which
drive produced it.

Sustained speed. Confirm at least 40 GB free, then:
`dd if=/dev/zero of=/media/RAW/c1_speedtest bs=4M count=8192 oflag=direct conv=fsync status=progress`
then `rm /media/RAW/c1_speedtest`. That is 32 GiB / 34.4 GB — about one Stage-1 take, and long
enough to run out of the drive's pSLC write cache. `oflag=direct` bypasses the Pi's page cache
but **not** the SSD's internal cache, so a short run measures burst, not sustained. Expect
roughly 76 s at 450 MB/s, 172 s at 200 MB/s, 344 s at 100 MB/s.

**Take the result from `status=progress`, not from dd's final average.** If the rate steps DOWN
partway through and stays down, that step is the pSLC cache exhausting: record the **trailing
rate after the step** as sustained MB/s, and record the pre-step rate as `burst MB/s @ NN GB`.
If no step appears, record the final average and write "no cache step observed".

Do **not** run it twice and keep the lower number. After a 32 GiB run the drive is
cache-depleted and still folding, so a back-to-back second run under-reports steady state. If
you want a confirmation run, idle 5 minutes first; it should agree with the trailing rate, not
with the average.

Leave the drive idle 5 minutes after the test before any 0.3 validation take or Stage 1 take,
so no take starts mid-fold in a state normal use never produces.

Do not repeat this test for Stage 2. Steady-state write speed is a property of the drive, not
of take length — reuse the Phase 0 trailing number.

Also make these three threading edits, without which the above changes nothing:

- RUNBOOK.md:196 — change `0.85 × sustained MB/s` to
  `0.85 × the 0.4 trailing sustained MB/s (never the burst figure)`.
- RUNBOOK.md:225 — change `within 15 % of the sustained speed` to
  `within 15 % of the 0.4 trailing sustained speed`.
- RESULTS.md:51 — replace `Storage: source/fstype — · free bytes — · sustained write (dd ×2, lower): — MB/s`
  with `Storage: source/fstype — · drive model/capacity/%used — · free bytes — · burst MB/s @ GB — · **trailing sustained MB/s** — · cache step observed? —`

### M24 · [math-audit] 

**Claim checked:** 'The DNG encoder's RAM buffer is small on this unit and the 80 % RAM guard force-stops recording when the write backlog fills it' (RUNBOOK.md:52-53) and outcome class `AUTO-STOP-RAM-GUARD` = 'cinepi-raw force-stopped the take on the RAM guard' (RUNBOOK.md:147).

**Evidence:** There are TWO guards, both in cinemate (not cinepi-raw), in `_recording_worker` at /Users/patrikeriksson/Documents/cinemate/cinemate/src/module/cinepi_controller.py:2585-2612. (1) PRIMARY backlog guard: `BUFFER_LIMIT_PERCENT = 90` (cinepi_controller.py:260, comment: 'Stop recording when the cinepi-raw RAM frame buffer is this full ... the direct about-to-drop-frames signal'), tripping on buffer/buffer_size >= 90% (cinepi_controller.py:2596-2602). (2) BACKSTOP: `RAM_LIMIT_PERCENT = 80` (cinepi_controller.py:256) on `psutil.virtual_memory().percent` (cinepi_controller.py:2605-2610) - a system-RAM check with no connection to the write backlog. So the guard the runbook names (80%) is not the backlog guard, and the process it names (cinepi-raw) is not the one that stops the take. The warning lines are Python `logging.warning` from cinemate ('RAM frame buffer NN% >= 90%! Stopping recording.' / 'RAM NN.N% >= 80%! Stopping recording.'), so a Sonnet grepping cinepi-raw's output for the evidence will find nothing and misclassify the take.

**Fix (adjudicated):**

Three edits. Do NOT use the critic's text — it omits cinepi-raw's guard and hard-codes the falsified 2 GB premise.

(1) REPLACE RUNBOOK.md:51-54 (the whole first "known context" bullet) with:

- **Three independent watchdogs can force-stop a take** — never write "the RAM guard" as if it
  were one thing. In cinemate's `_recording_worker` (`src/module/cinepi_controller.py:2585-2612`):
  (a) the **backlog guard**, `BUFFER_LIMIT_PERCENT = 90` on `buffer / buffer_size` — the real
  about-to-drop-frames signal; (b) the **system-RAM backstop**, `RAM_LIMIT_PERCENT = 80` on
  `psutil.virtual_memory().percent` — total system memory, *not* a backlog measurement. Both set
  `memory_alert` to the tripping percentage. In cinepi-raw (`cinepi/cinepi_raw.cpp:219-232`):
  (c) `buffer_full()` (`ram_buffers_ + 2 >= max_ram_buffers_`, pool exhaustion) →
  `setRecording(false)`, which sets **no** `memory_alert`.
  Firing order is fixed by arithmetic, not by board size: the encoder pool is sized once at
  configure time at 90 % of `MemAvailable` (`cinepi/dng_encoder.cpp:846-849`), so with the pool
  as the dominant growing allocation (b) needs pool bytes ≥ `MemAvailable − 0.2 × MemTotal`,
  which is always less than (a)'s `0.81 × MemAvailable` — **(b) trips first, then (a), then (c)**.
  An auto-stop is a *distinct outcome class*, never "dropped frames" — but only (a) licenses the
  conclusion "the drive can't sustain the data rate"; for (b) and (c) you must show it from the
  sampler's `buffer` curve.
  **Do not assume 2 GB.** The 2026-08-23 hardware session measured **4048 MB total**
  (`system-review/PI-VERIFICATION-QUEUE.md:15`, which flags the older 2 GB note as stale), and
  PI-016 held `available` at 2969–3113 MB through a full 4056x3040 12-bit take with
  `memory_alert` never firing. Read `MemTotal` in Phase 0 and use the measured number everywhere.

(2) REPLACE the `AUTO-STOP-RAM-GUARD` row at RUNBOOK.md:147 with:

| `AUTO-STOP-RAM-GUARD` | A watchdog force-stopped the take. Record **which one** — all three land in `/tmp/cinemate_cli.log`: `RAM frame buffer NN% ... 90%! Stopping recording.` = cinemate backlog guard; `RAM NN.N% ... 80%! Stopping recording.` = cinemate system-RAM backstop; `RAM pool exhausted` = cinepi-raw pool exhaustion. Also record `memory_alert` (set by the two cinemate guards only — cinepi-raw's stop leaves it at its previous value) and the max `buffer`/`buffer_size` sample. "A RAM guard fired" without naming the guard is not an acceptable ledger entry. |

(3) COMPANION EDITS — without these the classification is not actionable:
  - RUNBOOK.md:256, extend the grep to
    `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory|Stopping recording|RAM pool exhausted`.
    Match ASCII substrings only: the warnings contain non-ASCII `≥` and `—`, so never put those
    characters in a grep pattern.
  - RUNBOOK.md:211-214 (0.7), replace the runway formula with: `runway_s_raw = buffer_size / fps`
    (runway to 100 % pool fill) **and** `runway_s_effective = 0.8 × runway_s_raw` — the first
    guard fires at roughly `(MemTotal_frac) → (MemAvailable − 0.2 × MemTotal) / (0.9 × MemAvailable)`
    of the pool, ≈ 0.81 on this board. Record both; use the effective number in the 0.10 predictions.

### M25 · [math-audit] 

**Claim checked:** 'If the coarse deviation is dominated by sensor-vs-target fps offset, recompute against `dng_count x mean_frame_interval` using the DNG timestamps from the analyzer JSON' (RUNBOOK.md:158-160).

**Evidence:** `mean_frame_interval` cannot be computed from that JSON - it contains no per-frame timestamps. /Users/patrikeriksson/.claude/skills/cinemate-dev/scripts/analyze_cinepi_media.py:112-113 runs exiftool on `dng_files[0]` only ('sample_file = str(dng_files[0])'), and the JSON payload (lines 246-251, dataclasses at 28-53) is exactly: count, first_file, last_file, first_index, last_index, missing_indices, sample_metadata (one file), plus the WAV block. There is no timestamp array anywhere. Additionally that single-file metadata is empty unless `exiftool` is installed on the Pi (detect_tools(), line 69-73) and the WAV block is empty without `ffprobe` - so the runbook's description of the script as 'stdlib-only' (RUNBOOK.md:94) is true of its Python imports but not of its output, which silently degrades to a bare file count. The prescribed fallback arithmetic is therefore unrunnable exactly when it is needed (an audio FAIL).

**Fix (adjudicated):**

TWO COORDINATED EDITS. Edit 2 alone is not sufficient — without Edit 1 the recomputed number is ~50x coarser than the threshold it feeds.

--- EDIT 1: sampler, RUNBOOK.md line 120 (Instrumentation block) ---

REPLACE this line:

  echo "$(date +%s),$(g buffer),$(g buffer_size),$(g framecount),$(g fps_actual),$(g is_writing_buf),$(g write_speed_to_drive),$(g space_left),$(g memory_alert),$d,$t,$th" >> "$OUT"

WITH these two lines (column order and header unchanged):

  ts=$(date +%s.%N); fc=$(g framecount)
  echo "$ts,$(g buffer),$(g buffer_size),$fc,$(g fps_actual),$(g is_writing_buf),$(g write_speed_to_drive),$(g space_left),$(g memory_alert),$d,$t,$th" >> "$OUT"

(Sub-second `ts`, read immediately adjacent to `framecount`, is what makes every fps-derived number in this campaign admissible — including the rate confirmation in Stage 1 step 3.)

--- EDIT 2: replace RUNBOOK.md lines 158-160 in full with ---

If the coarse deviation exceeds the PASS threshold, check whether it is explained by
sensor-vs-target fps offset before writing WARN or FAIL. Derive the measured mean frame
interval from the sampler CSV over the widest in-take window — the first and last samples where
`framecount` is advancing, excluding pre-roll and the post-take flush:

`mean_frame_interval = (ts_last − ts_first) / (framecount_last − framecount_first)`

Recompute the deviation as `|wav_duration − dng_count × mean_frame_interval|`. Record **both**
deviations and `1 / mean_frame_interval` next to the target fps.

Precision rule — do not skip. Quote the recomputed deviation with its uncertainty
`± dng_count × ts_resolution / (ts_last − ts_first)`. With the sub-second sampler clock over a
5-minute window this is a few milliseconds. **If the CSV was recorded with 1-second timestamps,
the uncertainty is ~±1 s ≈ 25 frame periods at 25 fps — far coarser than the 0.5-frame-period
threshold. That number is not admissible: log the coarse verdict, note the sampler defect, and
re-run the take with the corrected sampler.**

The analyzer JSON cannot supply the frame interval — it carries no per-frame timestamps, only
one sample DNG's exiftool tags. Neither can the DNG tags themselves: `FrameRate` is written from
the *requested* framerate (circular for this test), `DateTimeOriginal` has 1-second resolution
with no sub-second tag, and `TimeCode` is a frame counter at integer nominal fps, not an
independent clock.

--- EDIT 3 (optional, cheap): append to 0.9 ---

Also run `command -v exiftool ffprobe` and record which are present. Neither gates any pass/fail
rule here: DNG count, index range and sequence gaps come from the analyzer's stdlib path, and
WAV duration comes from the `wave` snippet above. If they are absent, the analyzer's
`sample_metadata` and `wav.ffprobe` blocks are empty `{}` and the JSON's own `tools` block says
so — record that as tooling state, not as a media defect.

### M26 · [math-audit] 

**Claim checked:** Rule 5 (RUNBOOK.md:43-46): all of Stage 1 runs to completion before the agent ends its turn - i.e. 9 takes, each with `session-tail 100` every 60 s plus `session-tail 400` and `dmesg | tail -150` for evidence, in one session.

**Evidence:** Wall clock itself is fine: Stage 1 = 9 x 5 min = 45 min of recording plus per-take overhead (pre-roll, mode readback, flush wait, evidence capture, ~200 MB archive copy, rm -rf, cool-down to <70 C) -> 1.5 h at 5 min/take overhead, 2.5 h at 12 min. Stage 2 = 6 x 10 min = 60 min recording -> 1.5-2.2 h. The runbook states no time budget, so no numeric conflict there. The conflict is log volume in the single mandated turn: 9 x (5 polls x 100 lines + 400 + 150) = 9,450 lines of raw log pulled into context, ~113k-170k tokens at 12-18 tokens/line, and `session-tail` re-sends overlapping text on every poll. Stage 2 adds ~9,300 lines. A Sonnet session will run out of context mid-Stage-1 and start losing the earlier takes' evidence - after which the Stage 1 summary block it is required to write at STOP GATE 1 is written from a truncated record.

**Fix (adjudicated):**

Three edits to /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md.

(1) REPLACE lines 250-251 (Stage 1 step 6):

6. `session-send "rec f <frames_5min>"`. The take must stop itself at the frame count. Do not
   send anything else to the session while recording. **Poll the sampler CSV, never the session
   log**: every 60 s run `tail -n 1 /home/pi/c1/samples/<take-id>.csv` — that one line carries
   framecount, buffer, temp and `memory_alert`, which is the entire liveness check.
   Do **not** `session-tail` during a take. `dng_encoder` prints one `DNG written:` line *per
   frame* at INFO and `cinepi_multi.log_filters` does not drop it, so a 5-minute take puts
   3,300 lines (mode A @11 fps) to 7,500 lines (mode C @25 fps) into `/tmp/cinemate_cli.log`.
   `session-tail 100` therefore shows 4–9 s of a 300 s take (1–3 % of it) at ~5k tokens a poll;
   5 polls x 9 takes is ~240k tokens, more than the whole context window. If context still runs
   short mid-stage, apply Rule 5.

(2) REPLACE lines 255-257 and line 260 (the first and third bullets of step 8):

   - **Session log — grep the whole file on the Pi, never a tail.** `session-start` truncates
     `/tmp/cinemate_cli.log`, so that file *is* this take's window. On the Pi:
     `grep -inE 'write.*fail|FAILED|xrun|overrun|drop|SYNC|memory' /tmp/cinemate_cli.log | tee /home/pi/c1/results/<take-id>-warnings.txt | wc -l`
     Read the hits file only when the count is non-zero (the real strings are
     `DNG write FAILED (...)` and `dng_save failed for frame N ... frame dropped`). Record the
     count in the ledger — a measured `0` is the evidence for "no warnings", an unexamined tail
     is not — plus every hit. Then copy the full log to the archive **without printing it into
     the conversation**: `scp pi@cinepi.local:/tmp/cinemate_cli.log <archive>/session-log.txt`
     (~0.6–1.4 MB per take); verify it with `wc -l`, not by reading it.
   - `dmesg | grep -iE 'nvme|ext4|usb|xhci|snd|alsa|error|reset|timeout' | tail -n 50 > /home/pi/c1/results/<take-id>-dmesg.txt`
     on the Pi; read that filtered file (not raw `dmesg`) and copy it to the archive.

(3) APPEND to Rule 5, after line 46:

   Stage 1 does not have to be one turn. If context is running short mid-stage, finish the take
   you are in, complete its archive and ledger row, commit, tell the operator which take IDs are
   done and which remain, and end your turn. A resumed Stage 1 is fine; a Stage 1 summary
   written from a compacted transcript is not. On resume, rebuild state from `RESULTS.md`,
   `/home/pi/c1/results/` and the archive — never from recollection of earlier takes.

### M27 · [executability] 

**Claim checked:** Stage 1 step 8/9/10: `analyze_cinepi_media.py /media/RAW/<take-dir>` … `rm -rf /media/RAW/<exact-take-dir>` — the session can obtain the take directory.

**Evidence:** RUNBOOK.md:261 and :266 use `<take-dir>`/`<exact-take-dir>` as placeholders and the runbook never says how to resolve them. The only lead is `last_dng_cam0` listed as a value to *record* (RUNBOOK.md:259). /Users/patrikeriksson/Documents/cinemate/cinemate/docs/redis-keys.md:79 confirms `last_dng_cam0` = "Full path to the most recently written DNG", and /Users/patrikeriksson/Documents/cinemate/cinepi-raw/cinepi/utils.cpp:93-105 confirms the take dir is `mediaDest + "/" + folder` i.e. `/media/RAW/CINEPI_<date>_<time>_F<ff>_C<clip>_cam0`. So `dirname` works — but the session has to infer it, and a session that instead reaches for `ls -t /media/RAW | head -1` gets a different (and on a hotswap rig, wrong) answer.

**Fix (adjudicated):**

Insert as a new step between current steps 7 and 8 of the Stage 1 per-take procedure (renumber 8-11 to 9-12), and replace the two placeholders with `$TAKE_DIR`:

---

8. **Resolve the take directory once.** Steps 9-12 (analysis, archive, delete) all use this one
   variable. Never re-derive it, never use a wildcard, never `ls -t`.

   ```bash
   CAM=cam0                       # use cam1 if 0.2 detected the sensor on the CAM1 port —
                                  # the port comes from the I2C path, not the camera count
   LAST_DNG=$(redis-cli GET last_dng_$CAM)
   TAKE_DIR=$(dirname "$LAST_DNG")
   ```

   Assert all three before touching anything:

   - `$LAST_DNG` is non-empty and is **not** the literal string `None`. Storage pre-roll writes
     `None` back into `last_dng_cam*` when there is no prior take, so an unguarded `dirname`
     yields `.` and step 12 would `rm -rf` the ssh working directory.
   - `$TAKE_DIR` matches `/media/RAW/CINEPI_*_$CAM` **and** `[ -d "$TAKE_DIR" ]`.
   - `$TAKE_DIR` is *this* take: its mtime falls inside this take's window, and its basename is
     not one already recorded as deleted in the ledger. Pre-roll snapshots and restores
     `last_dng_cam*` around its warm-up take, so on a take that wrote zero DNGs the key still
     points at the **previous** take.

   If any assertion fails: classify the take `ABORTED-OTHER`, archive whatever exists,
   **delete nothing**, and report to the operator before starting the next take.

   Optional cross-check, must agree: `cinemate_dev.py status` prints `Latest take: <path>`.
   Record `$TAKE_DIR` in the per-take note.

---

Then in the (renumbered) evidence-capture step, replace the analysis line with:

   - On-Pi analysis: `python3 /home/pi/c1/analyze_cinepi_media.py "$TAKE_DIR" --json > /home/pi/c1/results/<take-id>.json`.

And replace the delete step with:

12. **Only then** delete the take: `rm -rf "$TAKE_DIR"` — the directory resolved in step 8 and
    verified in step 11, never a wildcard, never a freshly re-derived path.

### M28 · [executability] 

**Claim checked:** Stage 1 step 2: `set resolution <n>` → verify the three `resolution_target_*` readbacks match the plan.

**Evidence:** `set_resolution` itself applies a dynamic-resolution substitution before applying the mode: src/module/cinepi_controller.py:1825-1834 — `if self.dynamic_resolution_enabled: … choice = self._dynamic_resolution_choice_for_fps(current_user_fps); if choice is not None: value = choice.mode`. docs/redis-keys.md:38 says `dynamic_resolution_enabled` defaults to ON when unset. The runbook's mandated run order (RUNBOOK.md:274, "C (control) → B → A") guarantees this fires: after mode C at 25 fps, `set resolution <B>` is evaluated with current_user_fps 25 against B's fps_max ~16, so a lower mode is substituted. `set_fps` calls the same hook (cinepi_controller.py:974), so step 3 can move the resolution again AFTER step 2 verified it. The readback in step 2 will catch the first case — but the runbook states no remedy, so the session must invent one (`set dynamic resolution 0`? lower fps first? re-issue?), and ground rule 2 (RUNBOOK.md:29-34) arguably forbids it since dynamic resolution is not a "Phase 0 preflight check failing against a documented invariant".

**Fix (adjudicated):**

FOUR edits to /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md. Keep the resolution-then-fps order everywhere; do NOT adopt the proposed fps-first reorder.

=== EDIT 1 — insert a new item after 0.2 (RUNBOOK.md:182), before any test mode is selected ===

0.2b **Pin the two silent mode/fps rewriters OFF, and log both.**

*Dynamic resolution.* It is ON by default (`docs/redis-keys.md`: "persisted and read back at
startup, defaulting to on when unset") and silently substitutes a **different, lower** sensor
mode inside **both** `set resolution` and `set fps`
(`src/module/cinepi_controller.py` `set_resolution` / `set_fps` → `_maybe_apply_dynamic_resolution_for_fps`).
`resolution_target_*` then reports the substitute, not what you asked for. With the run order
below this is not hypothetical: `set resolution <B>` issued while `fps_user` is still 25 from
the mode-C takes lands on the largest mode that sustains 25 fps — for the imx477 table that is
2028x1520, i.e. mode C itself. It can also fire unprompted during the `session-start` pre-roll,
which restores the persisted `fps_user` with dynamic resolution allowed
(`src/module/storage_preroll.py`).

*FPS step table.* With `arrays.fps.free = false` (the `settings.jsonc` default, steps
`[25, 33, 50]`) `set fps` snaps the request to the nearest allowed step, so `set fps 15` does
not give you 15.

Before selecting any test mode:

    session-send "set dynamic resolution 0"     # exact command; "set dynamic_resolution_enabled" is rejected
    session-send "set fps free 1"
    redis-cli GET dynamic_resolution_enabled    # must read 0

Record the before and after values of `dynamic_resolution_enabled` in the config-interventions
log. These are **sanctioned config interventions** (ground rule 2): a mechanism that rewrites
the mode or the fps mid-campaign confounds every comparison in the ledger, and both are recorded
so the campaign is reproducible.

Neither survives a restart the same way, so **re-issue both after every `session-start`**:
`dynamic_resolution_enabled` persists in Redis but is re-read at process start, and `fps_free`
is not persisted at all — it is re-read from `settings.jsonc` each time and never written to
Redis, so confirm it from the session log (`FPS Free Mode set to True`) and from the `fps`
readback, not from a Redis key.

=== EDIT 2 — replace the second sentence of 0.3 (RUNBOOK.md:185) ===

Replace:
  For each selected mode: `set resolution <n>`, read back
  `resolution_target_width/height/bit_depth`, set the test fps (rule in 0.5), then
With:
  For each selected mode, in this order: `set resolution <n>` → read back
  `resolution_target_width/height/bit_depth` → set the test fps (rule in 0.5) → read back `fps`
  → re-read `resolution_target_width/height/bit_depth` to confirm the fps step did not move the
  mode. Record the readbacks in the 0.2 table only after this second confirmation. Then

=== EDIT 3 — replace Stage 1 steps 2 and 3 (RUNBOOK.md:242-245) ===

2. Confirm the 0.2b pins survived the restart: `redis-cli GET dynamic_resolution_enabled` == 0,
   and re-issue `set fps free 1`. Both are re-read at process start; a missed re-issue silently
   rewrites the mode or the fps below.
3. Set the mode: `set resolution <n>` → verify the three `resolution_target_*` readbacks match
   the plan (renumbering gotcha — re-check every session).
4. Set fps to the mode's test fps, then read back `fps` (must equal the test fps) **and re-read
   the three `resolution_target_*` values** — `set fps` can move the resolution too. Confirm the
   rate again from two `framecount` samples ~10 s apart during the take (step 7), not from
   `fps_actual`.

   If any readback disagrees with the plan: **do not improvise and do not re-issue the same
   command** — the substitution is deterministic and will repeat, and a mode is never
   `INFEASIBLE-ON-THIS-RIG` on this evidence. Check 0.2b first (`dynamic_resolution_enabled`
   must be 0, `fps_free` on). If both pins are correct and the readback still disagrees, stop
   and report to the operator before recording anything.

(Renumber the remaining Stage 1 steps 4-11 to 5-12, and update the "step 6" cross-reference in
the run-order/`rec` step accordingly.)

=== EDIT 4 — append to ground rule 2 (RUNBOOK.md:34) ===

  The 0.2b pins (`set dynamic resolution 0`, `set fps free 1`) are pre-authorized under this
  rule and must be applied and logged before the first test mode is selected.

### M29 · [executability] 

**Claim checked:** Stage 1 step 8: "`session-tail 400` → save to the archive as `session-log.txt`; separately grep the take window for … and record every hit."

**Evidence:** 400 lines cannot reach the take window. Three log lines are emitted per recorded frame: (1) src/module/redis_controller.py:296-301 logs `Frame {n} ┃rec=…` on every FRAMECOUNT change; (2) src/module/cinepi_multi.py:263-265 `_log` forwards every cinepi-raw line that does not match the five filters at cinepi_multi.py:211-216, and cinepi-raw prints `DNG written: {}` per frame (/Users/patrikeriksson/Documents/cinemate/cinepi-raw/cinepi/dng_encoder.cpp:1529) — "DNG written" matches none of those filters; (3) redis_controller.py:303-310 logs `Changed value: last_dng_cam0 = … ┃RAM: xx%` per frame. A 5-minute take at 25 fps therefore writes ~22,500 lines; `tail -n 400` covers roughly the last 5 seconds. Everything Gate 1 needs to diagnose a CAUSE — the RAM% trace, mid-take write errors, the audio shortfall lines — is outside the window. cinemate_dev.py:676 confirms `session-tail` is exactly `tail -n <lines> /tmp/cinemate_cli.log`.

**Fix (adjudicated):**

In /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md, replace the FIRST BULLET of Stage 1 step 8 (currently: "- `session-tail 400` → save to the archive as `session-log.txt`; separately grep the take window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` (case-insensitive) and record every hit in the ledger.") with:

  - Session log — capture it **whole, and before the next `session-start`**. `session-start`
    runs `rm -f /tmp/cinemate_cli.log` (`cinemate_dev.py:588`), so a log you did not copy is
    gone for good. On the Pi:
    `gzip -c /tmp/cinemate_cli.log > /home/pi/c1/results/<take-id>-session-log.txt.gz`
    then copy that file to the archive.
    **Do not use `session-tail` for evidence.** The log carries ~3 lines per recorded frame —
    `Frame <n> ┃rec=…` (`redis_controller.py:295`), `[cam0] DNG written: …`
    (`cinepi_multi.py:282`, unfiltered), and `Changed value: last_dng_cam0 = … ┃RAM: …%`
    (`redis_controller.py:302`) — so a 5-minute take at 25 fps is ~22,500 lines and
    `session-tail 400` shows only the last ~5 s.
    Grep the **whole file on the Pi**, not the tail:
    `grep -inE 'write.*fail|FAILED|xrun|overrun|drop|SYNC|memory' /tmp/cinemate_cli.log`
    Record every hit in the ledger. To locate a hit inside the take, quote the nearest
    **preceding** `Frame <n> ┃rec=<secs>s` line — that gives the exact frame and elapsed
    record time. Do not infer position from line-number arithmetic: two threads interleave,
    so 3 lines/frame is an average, not a fixed stride. If there are no hits, record "none"
    explicitly — that is the evidence backing a `COMPLETE-CLEAN` class and an audio `PASS`.

Two knock-on edits required for consistency:

1. Step 9 — replace `session-log.txt` in the archive list with `<take-id>-session-log.txt.gz`.
2. Line 98 (archive root description) — replace "session-log excerpt" with "gzipped full
   session log".

Optional but recommended, same root cause: in step 6, change "Poll `session-tail 100` every
60 s" to "Poll `session-tail 40` every 60 s just to confirm the take is alive and
`framecount` is climbing — this is a liveness check only; warnings between polls are caught
by the step 8 full-file grep, not here."

### M30 · [executability] 

**Claim checked:** "Prior sync-analysis method: check `/Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/` for the sync-matrix notes … (`sync-matrix.md`, possibly under a phase subfolder). If a WAV fails the coarse sync check, use that method for the deep dive before inventing one."

**Evidence:** The file does not exist. `ls -la /Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/` returns only `.DS_Store` — the directory is empty. `find /Users/patrikeriksson/Documents/cinemate -iname '*sync-matrix*' -not -path '*/.git/*'` and `find /Users/patrikeriksson/Documents -maxdepth 6 -iname 'sync-matrix*'` both return nothing. The audio-FAIL branch (RUNBOOK.md:155-156) is the branch this campaign most expects to take, and its method is a dangling pointer — the session will do exactly what the sentence forbids and invent one.

**Fix (adjudicated):**

Three edits to /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md. Do NOT touch lines 96-98 or line 263 — that archive root is the campaign's evidence destination and is empty only because C1 has not run yet.

EDIT 1 — DELETE lines 100-103 entirely (the "Prior sync-analysis method" bullet). No replacement bullet; the method moves inline to where it is used. The referenced notes do not exist in any working tree or any branch of any repo, and the method they described (3 claps + clap-delta, clock-correction off, `timecode_offset_frames=0` set on the Pi) cannot be run on unattended takes and would require a Pi config change that ground rule 2 forbids.

EDIT 2 — REPLACE lines 155-156:

- **FAIL** — deviation > 1 frame period, any WAV discontinuity, or missing WAV.

On FAIL, run exactly these four steps. Do not invent a deeper method, and do not re-shoot the
take to investigate.

1. **Video duration.** `dng_count / fps_measured`, where `fps_measured` comes from your
   `framecount` deltas during the take — not `fps_actual`, not the requested fps. Record
   `dng_count`, `fps_measured`, and the quotient.
2. **Audio duration.** From the stdlib `wave` snippet above: `frames / rate`. Record frames,
   rate, sampwidth, and the quotient.
3. **Reconciliation events.** Grep the take window of the session log for these exact strings:
   `grep -EI 'Inserted [0-9]+ silent frame|Capture read failed|Stopping capture after WAV writer disk error|Could not set SCHED_FIFO|Capture thread elevated to SCHED_FIFO|xrun|overrun'`
   The fill line already prints its shortfall in seconds — sum those values directly, and note
   the largest single fill.
4. **Report the triple + classify.** Δ = video duration − audio duration; total padded seconds
   from step 3; largest single fill. Then pick one:
   - Δ ≈ 0 with padded seconds > 0 → the wall-clock fill worked. Samples were lost to storage
     contention but WAV *length* is correct; the loss is silence gaps in content. Report padded
     seconds as the contention metric, not as a sync error.
   - Δ > 0 (audio short) and largest single fill ≈ 5.000 s → the fill hit its `maxGapFrames`
     clamp (`rate * 5`, cinepi_audio_capture.cpp:605). A stall exceeded 5 s and could not be
     fully padded. This is the headline finding — say so explicitly.
   - Δ > 0 with padded seconds ≈ 0, plus `Capture read failed` or a WAV-writer disk error →
     capture terminated early. Classify the WAV as discontinuous.
   - Δ > 0 with none of the above → the deviation is video-side: dropped DNGs shrink
     `dng_count / fps_measured` while the WAV stays wall-clock aligned. Cross-check against
     `missing_frame_count` and the sequence gaps before calling it an audio fault.

Write those numbers in the ledger row and stop there. Root-causing an audio FAIL is a STOP-gate
decision for the Fable thread, not a mid-stage task.

EDIT 3 — REPLACE lines 158-160 (the `mean_frame_interval` paragraph, which cites a source that
does not exist):

For an independent cross-check on step 1, take the take's wall-clock span from the first and
last DNG on the Pi — `stat -c %Y` (or `%.3Y` for sub-second) on the `dng.first_file` and
`dng.last_file` paths in the analyzer JSON — and divide by `dng_count − 1` for the mean frame
interval. Record both that number and the step-1 quotient. Note: the analyzer JSON's
`sample_metadata` block is exiftool output for the **first DNG only**, so it carries no
per-frame timestamps and no mean interval can be derived from it.

### M31 · [executability] 

**Claim checked:** "If the coarse deviation is dominated by sensor-vs-target fps offset, recompute against `dng_count × mean_frame_interval` using the DNG timestamps from the analyzer JSON."

**Evidence:** The analyzer JSON contains no per-frame timestamps and no interval. /Users/patrikeriksson/.claude/skills/cinemate-dev/scripts/analyze_cinepi_media.py:111-130 runs exiftool on `dng_files[0]` ONLY, for a fixed tag set (TimeCode, DateTimeOriginal, FrameRate, ImageWidth, ImageHeight, BitsPerSample), and stores it as `sample_metadata`. There is exactly one timestamp in the whole payload, so no mean interval is derivable. Worse, both metadata paths are conditional on host tools: `sample_metadata` requires exiftool (line 112) and the WAV block requires ffprobe (line 146) — analyze_cinepi_media.py:69-73. The runbook calls the script "stdlib-only" (RUNBOOK.md:93), which is true of its imports but not of its output.

**Fix (adjudicated):**

Replace RUNBOOK.md lines 158-160 with:

If the coarse deviation is dominated by sensor-vs-target fps offset, do **not** try to derive a frame interval from the analyzer JSON. `analyze_cinepi_media.py` runs exiftool on `dng_files[0]` only, so the JSON holds metadata for the first DNG and no interval — and the DNG tags cannot answer it anyway: `DateTimeOriginal` is 1-second resolution, `TimeCode` is derived from the frame count, and the `FrameRate` tag is the *configured* fps, not the measured one. For the same reason, never substitute `dng_count / fps_readback`: the Redis `fps` key is the target, so that just reproduces the coarse number.

The measured value is already in the session log. At end of take cinepi-raw derives the mean frame interval from the encoder's nanosecond sensor timestamps and prints the resulting duration:

```bash
grep -E "honest WAV timecode" session-log.txt
# Using precise audio-start marker for honest WAV timecode: video 299.868123s,
# input 299.867004s, start delta +0.001119s, capture rate 48000 Hz; leaving PCM untouched
```

`video` **is** `frame_count x mean_frame_interval`; `input` is the WAV's own duration; `start delta` is the measured A/V start offset. Record the refined deviation `|input - video|` next to the coarse `|wav_duration - dng_count/fps_target|`, plus `start delta`.

Expect this to fire on most takes, not as an exception: sensor VMAX/HMAX quantisation makes a 25 fps target run at ~25.011, which alone puts a clean 7500-frame take 0.132 s (= 3.3 frame periods) out on the coarse rule with zero audio loss.

Three things to record whenever you use it:

- The line prints in two variants, `precise audio-start marker` and `estimated audio-start metadata`. `video` and `input` are trustworthy in both; only `start delta` carries a fixed capture-latency bias in the estimated variant. Note which variant you got.
- If the log instead says `No audio start marker received`, these numbers were **not** printed. Say so in the ledger and go to the sync-matrix deep dive — do not invent a substitute.
- `video` is built from the frames the encoder saw, which can exceed the DNGs on disk. If it implies a different frame count than `dng_count`, that gap is drop/write-failure evidence: record both numbers, do not reconcile them silently.

`session-tail 400` may not reach back past a long take's log volume — grep the saved `session-log.txt`, and widen the tail before concluding the line never printed. No extra tool preflight is needed for this: the analyzer JSON's `tools` block already reports whether exiftool and ffprobe were found, and the WAV duration comes from the stdlib `wave` snippet above, not from ffprobe.

### M32 · [executability] 

**Claim checked:** Phase 0 is executable as written, 0.1 → 0.10 in order.

**Evidence:** Three ordering defects. (1) Circular: 0.3 says "set the test fps (rule in 0.5)", but 0.5's rule needs bytes/frame — measured in 0.3 — and sustained MB/s — measured in 0.4. The session must invent an evaluation order. (2) Retroactive: 0.6 says "During one of the 0.3 validation takes: `ps -eLo pid,comm,rtprio,psr …`" (RUNBOOK.md:204-205), but 0.6 is written after 0.3, and 0.3 ends with "Delete each 25-frame validation take after recording its numbers" — a session executing in order has already finished and deleted them. (3) 0.7 says "after setting each mode, read `buffer_size`", also referring back to mode-setting that happened in 0.3.

**Fix (adjudicated):**

Four edits to RUNBOOK.md. Numbering and all cross-references are preserved.

EDIT 1 - insert immediately after RUNBOOK.md:170 ("Ledger: fill the Phase 0 tables in `RESULTS.md` as you go; commit when the phase is done."):

**Execution order (the step numbers are topical, not sequential):** run **0.1 → 0.2 → 0.4 →
0.3 → 0.5 → 0.6 → 0.7 → 0.8 → 0.9 → 0.10**. 0.4's sustained MB/s is an input to the fps rule
0.3's takes need, and 0.3's validation takes are the only moment at which the 0.6 and 0.7
observations can be made at all. File every number in the ledger under its own step heading
regardless of the order you ran it in.

EDIT 2 - replace RUNBOOK.md:183-188 (all of step 0.3) with:

0.3 **Mode validation + measured bytes/frame + the live observations.** Run this after 0.4.
For each selected mode, in one pass:
a. `set resolution <n>`, read back `resolution_target_width/height/bit_depth`.
b. Set fps. DNG frames are uncompressed, so **bytes/frame is a function of width × height ×
   bit depth only and does not depend on fps** — use `min(0.95 × sensor fps_max, 25)` as this
   pass's provisional fps and finalise it in 0.5.
c. `rec f 25`. **While it records and flushes**, capture the 0.6 thread snapshot from a second
   ssh: `while :; do ps -eLo pid,comm,rtprio,psr | grep -Ei 'audio|dng-'; sleep 0.5; done`
   — a 25-frame take is only 1–3 s of capture plus the flush, so start the loop first.
d. Wait for `Stopped recording`, then poll until `is_writing_buf` = 0. Record: actual DNG file
   size (`stat -c%s` on one mid-take DNG), WAV presence, and that the 25 DNGs are
   sequence-continuous.
e. **Now** read `buffer_size` from Redis for 0.7. cinepi-raw publishes `buffer_size` only from
   the first *recorded* frame of a take onward and never clears the key, so reading it after a
   bare `set resolution` silently returns the **previous mode's** value — it is valid for this
   mode only after this take.
f. **Measured bytes/frame × final test fps = the mode's data rate** (computed in 0.5).
g. **Do not delete the validation take until the 0.3, 0.6 and 0.7 observations for that mode
   are all recorded in the ledger.** Then delete it.
If 0.5's final test fps differs from the provisional one, re-run a single `rec f 25` at the
final fps to reconfirm sequence continuity; bytes/frame and `buffer_size` do not change with
fps and need no re-measuring.

EDIT 3 - in step 0.6, replace the sentence at RUNBOOK.md:203-206 that begins "During one of the 0.3 validation takes:" and ends "**no `dng-enc`/`dng-dsk` thread on core 3**." with:

From the 0.3c thread snapshot — it must have been captured *during* a take; an idle `ps` shows
each thread's stale last-run CPU and will read as a false PASS — verify `cinepi-audio-capture`
at `rtprio` 80 on core 3, and **no `dng-enc`/`dng-dsk` thread on core 3**.

and append to the end of that step's remediation sentence (after "restart the session, and re-verify"):

The restart renumbers the resolution indices and voids every `buffer_size` reading, so re-run
0.3 for all modes after it.

EDIT 4 - replace RUNBOOK.md:211-213 (all of step 0.7) with:

0.7 **RAM runway.** `free -b`. Per mode, use the `buffer_size` read in step 0.3e — it is a
frame count (cinepi-raw sets it to 0.90 × MemAvailable ÷ per-frame buffer bytes at the take's
first frame, so it is mode-specific and only valid once that mode has recorded). Record
`runway_s = buffer_size / test fps` — how long a full disk stall can last before the RAM guard
ends the take. If a mode's row is missing, record another `rec f 25` for it; do not carry a
value read without a take in between.

### M33 · [executability] 

**Claim checked:** Phase 0.3 runs several `rec f 25` validation takes inside one session, waiting for `Stopped recording` each time.

**Evidence:** Two traps inside one session. (1) `rec` is silently ignored while the previous take's buffer is still flushing: src/module/cinepi_controller.py:1444-1447 — `if not self.is_preroll_active() and self._buffered_frames_flushing(): logging.info("rec ignored – previous take's buffered frames are still flushing to disk"); return`. 0.3 never waits for `is_writing_buf` = 0 between validation takes (Stage 1 step 7 does, but 0.3 does not). (2) Stop detection is not per-take: the helper's wait greps the WHOLE log (`grep -q "Stopped recording" /tmp/cinemate_cli.log`, cinemate_dev.py:636), and the runbook's manual equivalent polls `session-tail`, so from validation take 2 onward the string from take 1 is already present and the wait returns immediately. Stage 1 is safe from (2) only because each take does a fresh `session-start` that wipes the log.

**Fix (adjudicated):**

Replace RUNBOOK.md lines 185-188 (all of section 0.3) with:

0.3 **Mode validation + measured bytes/frame.** All validation takes share the single session
started in 0.2, so the two per-take guards Stage 1 gets for free from its fresh `session-start`
must be applied by hand here.

For each selected mode:

1. `set resolution <n>`, read back `resolution_target_width/height/bit_depth`.
2. Set the test fps (rule in 0.5).
3. **Before sending `rec`**, poll Redis until `is_writing_buf` = 0 **and** `is_buffering` = 0.
   `start_recording()` silently refuses a new take while either key is 1
   (`cinepi_controller.py` `_buffered_frames_flushing` — it reads `is_writing_buf` and
   `is_buffering`, *not* `is_writing`). The only trace is the log line
   `rec ignored - previous take's buffered frames are still flushing to disk`, followed by
   `Unable to start recording; frame-limited stop not scheduled.` Grep for both after every
   `rec`; if either appears, redo this wait and resend.
4. Record the current session-log length: `LINES=$(wc -l < /tmp/cinemate_cli.log)`.
5. `session-send "rec f 25"`.
6. Wait for `Stopped recording` **only in the lines added after that offset**:
   `tail -n +$((LINES+1)) /tmp/cinemate_cli.log | grep -q "Stopped recording"`.
   Never grep the whole file and never rely on a fixed-depth `session-tail` here: the previous
   validation take's `Stopped recording` is still in this log (`session-start` truncates it
   once, back in 0.2), so a whole-file match returns true instantly and you will measure a take
   that is still being written. This is also why `roundtrip-take` is banned — its internal wait
   is exactly that whole-file grep.
7. Then poll Redis until `is_writing` = 0, `is_writing_buf` = 0 and `is_buffering` = 0, and
   record: actual DNG file size (`stat -c%s` on one mid-take DNG), WAV presence, and that the
   25 DNGs are sequence-continuous.

**Measured bytes/frame x test fps = the mode's data rate.** Delete each 25-frame validation
take after recording its numbers (the named directory only, never a wildcard).

### M34 · [executability] 

**Claim checked:** Step 8: "grep the take window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` (case-insensitive) and record every hit" is sufficient evidence capture; and the audio PASS criterion "zero xrun/overrun lines in the session log for the take window".

**Evidence:** The pattern misses the only real xrun evidence, so 'zero xrun lines' is true by construction even on a badly xrunning take. cinepi_audio_capture.cpp:626-635: on a genuine ALSA xrun the code recovers and `continue`s WITHOUT printing anything. The only emitted line is at cinepi_audio_capture.cpp:658-661: `"Inserted " << gapFrames << " silent frame(s) to cover a capture shortfall of " …`. It does reach the session log (the helper is launched with `2>&1`, cinepi_sound.cpp:862, and unrecognised lines are re-emitted as `console->warn("Audio capture helper: {}", line)` at cinepi_sound.cpp:1236) — but it contains none of `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory`. Same gap for disk errors: dng_encoder.cpp:1548 emits `perror("Error writing to file")`, which matches nothing in the pattern ("Error writing to file: …" has no "fail" after "write"). The end-of-take verdict line at redis_listener.py:1925-1930 does match via "disk-write failure", so the summary survives — but the mid-take cause evidence does not.

**Fix (adjudicated):**

TWO EDITS to /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md.

=== EDIT 1 — Step 8, first bullet (lines 255-257) ===

REPLACE:
   - `session-tail 400` → save to the archive as `session-log.txt`; separately grep the take
     window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` (case-insensitive) and
     record every hit in the ledger.

WITH:
   - Grep the **whole** session log on the Pi. `session-start` truncates
     `/tmp/cinemate_cli.log` (helper `start_helper_session`), so it holds exactly this take —
     grep the file, not the tail:
     ```bash
     grep -niE 'write.*fail|failed|xrun|overrun|drop|sync|memory|silent frame|capture shortfall|RAM pool exhausted|Missing frames|TC timing|DNG index gaps|Error writing to file|WAV writer' \
       /tmp/cinemate_cli.log > /home/pi/c1/results/<take-id>-events.txt
     ```
     Record every hit in the ledger and archive `<take-id>-events.txt`. Then `session-tail 400`
     → archive as `session-log.txt`, understanding it is a **tail only**: `DNG written:` prints
     once per frame, so 400 lines is roughly the last 9 s of the take. The grep above, not that
     tail, is the take-window evidence — and the log is deleted at the next `session-start`, so
     capture it before step 1 of the following take.
     Two reading rules: `…raise the rtprio ulimit for xrun-resistant capture` is the
     SCHED_FIFO/setcap startup warning (`cinepi_audio_capture.cpp:272-274`), **not** an xrun —
     do not count it; and `Inserted N silent frame(s) to cover a capture shortfall of X.XXXs`
     is the only line an actual capture shortfall prints (see the audio verdict).

=== EDIT 2 — Audio verdict block (lines 152-156) ===

REPLACE:
- **PASS** — WAV present; `|wav_duration − dng_count/fps_target| ≤ 0.5 frame period`; zero
  xrun/overrun lines in the session log for the take window.
- **WARN** — deviation ≤ 1 frame period, or 1–2 xrun lines with no audible-scale loss.
- **FAIL** — deviation > 1 frame period, any WAV discontinuity, or missing WAV.
  On FAIL, run the sync-matrix deep-dive method before writing the verdict.

WITH:
Audio-loss evidence — read this before scoring. The ALSA xrun path is **silent**:
`cinepi_audio_capture.cpp:626-635` recovers the PCM and `continue`s without printing anything,
so the word "xrun" never appears for a real xrun. The only line a lost-sample event prints is
the wall-clock reconciliation at `cinepi_audio_capture.cpp:663-667`, which reaches the session
log as `Audio capture helper: Inserted N silent frame(s) to cover a capture shortfall of
X.XXXs; WAV stays aligned to wall clock`. That silence-fill is *designed* to hold the WAV at
wall-clock length (see the comment at 599-611), so **duration alone cannot detect audio loss** —
a take that lost 3 s of samples still passes the duration check. Score the silence-fill first.

Per take, record two numbers from `<take-id>-events.txt`: `silence_fill_events` (count of
`Inserted … silent frame(s)` lines) and `silence_fill_total_s` (sum of their inserted seconds).

- **PASS** — WAV present; `silence_fill_events` == 0; and
  `|wav_duration − dng_count/fps_target| ≤ 0.5 frame period`.
- **WARN** — `silence_fill_total_s` < 1 frame period, or deviation ≤ 1 frame period.
- **FAIL** — `silence_fill_total_s` ≥ 1 frame period; or any of `Capture read failed`,
  `WAV writer: disk write failed`, `Stopping capture after WAV writer disk error` in the take
  window; or deviation > 1 frame period; or missing WAV.
  On FAIL, run the sync-matrix deep-dive method before writing the verdict.

### M35 · [executability] 

**Claim checked:** Step 9: "Archive to the Mac (`development/pi-test-takes/c1/<take-id>/`): the analyzer JSON, the sampler CSV, `session-log.txt`, the WAV, and the first 3 + last 3 DNGs."

**Evidence:** No mechanism is named and every named tool is either forbidden or wrong. RUNBOOK.md:90-92 forbids `roundtrip-take`. The helper's only pull command is `copy-latest-take` (cinemate_dev.py `--dest-root`, documented in references/workspace-contract.md:143) which copies the ENTIRE take — 30–70 GB, explicitly forbidden at RUNBOOK.md:95. So the session must hand-roll `scp`, and the auth path is non-obvious: with `PI_PASSWORD` set, plain `scp` will hang on a password prompt; the working invocation is `~/.claude/skills/cinemate-dev/scripts/pi_expect.exp "$PI_PASSWORD" scp -o StrictHostKeyChecking=accept-new pi@cinepi.local:<remote> <local>` (pattern from cinemate_dev.py:119-132, pi_ssh.sh). The destination `development/pi-test-takes/c1/` also does not exist yet and no mkdir is specified.

**Fix (adjudicated):**

Add a fourth bullet to the "Tools you drive" section (after the "Media analyzer" bullet, before "Archive root on the Mac"):

- **Talking to the Pi directly.** The helper has no generic remote-shell or selective-copy
  command, and most of this runbook (0.3-0.9, step 8, step 10) is plain shell. Use:
  - **Commands:** `~/.claude/skills/cinemate-dev/scripts/pi_ssh.sh '<command>'` — it wraps
    `pi_expect.exp` automatically when `PI_PASSWORD` is set and falls back to plain `ssh`
    when it isn't. (The path in `references/workspace-contract.md`'s "Pi runtime" section,
    `Documents/cinemate/scripts/pi_ssh.sh`, does **not** exist — use the skill path above.)
  - **Files, both directions:**
    `~/.claude/skills/cinemate-dev/scripts/pi_expect.exp "$PI_PASSWORD" scp -o StrictHostKeyChecking=accept-new <src> <dst>`
    with `pi@cinepi.local:<path>` on whichever side is remote. Drop the `pi_expect.exp
    "$PI_PASSWORD"` prefix if `PI_PASSWORD` is unset. Write `$PI_PASSWORD` as the variable,
    never its value (ground rule 6). This is also how 0.9 pushes `c1_sampler.sh` and
    `analyze_cinepi_media.py`.
  - **Never `cinemate_dev.py copy-latest-take`.** It scp's the whole take directory
    recursively (30-70 GB) — same reason `roundtrip-take` is out. `workspace-contract.md`
    lists it under "Session commands" and its take contract step 7 tells you to run it into
    `pi-test-takes/`; that contract is written for 25-frame takes and does not apply here.
    This campaign copies named files only.

Then replace step 9 of the Stage 1 per-take procedure with:

9. Archive to the Mac. `mkdir -p /Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/c1/<take-id>` first (the `c1/` root does not exist yet). Write `session-log.txt` locally — `session-tail 400` prints to stdout, so redirect it into the archive dir; no copy needed. scp the remaining four items with the invocation above:
   - `/home/pi/c1/results/<take-id>.json`
   - `/home/pi/c1/samples/<take-id>.csv`
   - `/media/RAW/<take-dir>/<take-dir>.wav`
   - the first 3 + last 3 DNGs, chosen on the Pi (frame numbers are 9-digit zero-padded, so
     lexical order is frame order):
     `pi_ssh.sh 'ls /media/RAW/<take-dir>/*.dng | head -3; ls /media/RAW/<take-dir>/*.dng | tail -3'`
   Verify every copy is non-empty (`ls -l`) and that the JSON parses (`python3 -m json.tool`) **before** step 10 deletes the take.


---

## MINOR — clarity and robustness (20)

### M1 · [helper-commands] 

**Claim checked:** "Deterministic helper: `~/.claude/skills/cinemate-dev/scripts/cinemate_dev.py` (`stop`, ...)" — invoked as written.

**Evidence:** The file is not executable: `ls -l` -> `-rw-r--r-- 1 patrikeriksson staff 65358 ... cinemate_dev.py`, and invoking it directly returns `permission denied: /Users/patrikeriksson/.claude/skills/cinemate-dev/scripts/cinemate_dev.py`. (analyze_cinepi_media.py IS `-rwxr-xr-x`, and the runbook already prefixes it with `python3` in step 8, so only the helper is affected.) The skill's own contract uses the prefixed form: references/workspace-contract.md:86 `python3 <helper>/scripts/cinemate_dev.py stop`.

**Fix (adjudicated):**

Two edits to /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md.

EDIT 1 — replace lines 88-92:

OLD:
- Deterministic helper: `~/.claude/skills/cinemate-dev/scripts/cinemate_dev.py`
  (`stop`, `session-start`, `session-send "<cmd>"`, `session-tail <n>`, `session-stop`,
  `status --write-report`, `sync-status --repo <repo>`). Use the **explicit session
  commands**, not `roundtrip-take` — these takes are far too long and too large for the
  convenience wrapper's copy step.

NEW:
- Deterministic helper: `python3 ~/.claude/skills/cinemate-dev/scripts/cinemate_dev.py`
  (`stop`, `session-start`, `session-send "<cmd>"`, `session-tail <n>`, `session-stop`,
  `status --write-report`, `sync-status --repo <repo>`). The script has a `python3` shebang
  but is **not** mode +x and is not on `PATH` — always invoke it through `python3` with the
  full path. If you see `permission denied` on it, that is the missing exec bit, **not** a
  sudo/`PI_PASSWORD` failure; do not `chmod` it — it is a governed skill file, outside this
  campaign's sanctioned interventions. Everywhere below, `cinemate_dev.py <sub>` is shorthand
  for that full command. Use the **explicit session commands**, not `roundtrip-take` — these
  takes are far too long and too large for the convenience wrapper's copy step.

EDIT 2 — line 303, replace:

OLD:
(`cinemate_dev.py build-raw` if cinepi-raw changed), and record the new commits in the ledger

NEW:
(`python3 ~/.claude/skills/cinemate-dev/scripts/cinemate_dev.py build-raw` if cinepi-raw
changed), and record the new commits in the ledger

(Lines 172 and 280 need no edit — the shorthand sentence added in Edit 1 covers them. Edit 2
is still worth making because Stage 2 begins in a separate turn, possibly a separate session,
where the reader may copy that line without re-reading the tools section.)

### M2 · [helper-commands] 

**Claim checked:** Implicit: the analyzer's parsed take-name fields are safe to record in the ledger.

**Evidence:** `TAKE_RE` (analyze_cinepi_media.py:16-18) exposes the folder's `F##` group as `parsed_name.ff`, which reads like a frame rate but is not. cinepi-raw/cinepi/utils.cpp:84-86 formats the folder as `"CINEPI_%s_F%02d_C%05d_%s"` with `frameNumber`, computed at utils.cpp:74-76 as `llround(microseconds * frameRate / 1e6) % frameRate` — a sub-second timecode frame index. Real takes on this Pi from the same rig confirm it varies arbitrarily: `..._F03_...`, `..._F31_...`, `..._F45_...`, `..._F47_...`. (Separately, `%02d` widens to three digits above 99 fps, which would break `F\d{2}` — not reachable here because Phase 0.5 caps test fps at 25.)

**Fix (adjudicated):**

Add as a new bullet under "## Ledger discipline (applies to every phase)" in RUNBOOK.md (after the "Every number in the ledger carries its source" bullet):

- The `fps` column in the Stage 1/2 take tables comes from the mode's **Phase 0.5 test fps**, confirmed against the **`framecount` slope** from the sampler — never from `fps_actual` (dead-emit history) and never from the take folder's `F##` field, which the analyzer JSON exposes as `parsed_name.ff`. That field is a sub-second timecode frame index (cinepi-raw `cinepi/utils.cpp:74-86`), not a frame rate: it ranges `0 … fps-1`, so at this campaign's ≤ 25 fps it produces plausible-looking values like `24` that are silently wrong. Takes recorded seconds apart at one fps show unrelated values (`F22`, `F03`, `F00`, `F19`).

### M3 · [helper-commands] 

**Claim checked:** Step 8: `session-tail 400` output can be saved directly as a clean `session-log.txt`.

**Evidence:** `command_session_tail` prints `result.stdout` verbatim (cinemate_dev.py:1233-1239), and `run_local` captures the stdout of pi_ssh.sh -> pi_expect.exp, which is a PTY. Every capture in this review shows two injected header lines — `spawn ssh -o StrictHostKeyChecking=accept-new pi@cinepi.local <cmd>` and `pi@cinepi.local's password:` — and `od -c` on a 114-char test line confirms the PTY rewrites terminators as `\r\n` (no column wrapping occurs, and no password is echoed). So a redirected session-log.txt gets 2 junk lines plus CRLF throughout.

**Fix (adjudicated):**

In /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md, replace the first bullet of step 8 (currently lines 255-257):

    - `session-tail 400` → save to the archive as `session-log.txt`; separately grep the take
      window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` (case-insensitive) and
      record every hit in the ledger.

with:

    - `session-tail 400` → save to the archive as `session-log.txt`. **Do not redirect it
      raw.** When `PI_PASSWORD` is set the helper reaches the Pi through `pi_expect.exp`,
      which spawns `ssh` on a local PTY, so stdout carries an injected `spawn ssh …` line,
      the `pi@cinepi.local's password:` prompt line, and CRLF on every line (the password
      itself is never echoed — `pi_expect.exp` excludes it from the spawn list). Redirect
      through a cleaner; it is a no-op if you are on key auth:

      ```bash
      python3 ~/.claude/skills/cinemate-dev/scripts/cinemate_dev.py session-tail 400 \
        | tr -d '\r' \
        | sed -e '/^spawn ssh /d' -e "s/^pi@[^ ]*'s password: *//" \
        > <archive>/<take-id>/session-log.txt
      ```

      Use `sed` as written, not a `grep -v password:` filter — a blanket `password:` filter
      silently deletes real log lines and this file is evidence. Then separately grep the
      take window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` (case-insensitive)
      and record every hit in the ledger.

Keep the tail depth at 400. Do not change it to 60000 as part of this fix — log-coverage depth is a separate question, and a 60000-line tail conflicts with the archive rule at RUNBOOK.md:96-99 ("session-log excerpt … Nothing larger").

### M4 · [redis-and-cli] 

**Claim checked:** Every session-start reaches "Storage pre-roll complete" (Stage-1 step 1 and 0.2 both wait on it)

**Evidence:** The line is unreachable on three paths, all of which log something else instead: auto pre-roll disabled in settings.jsonc → "Automatic storage pre-roll disabled by settings.jsonc" (storage_preroll.py:61) and no run is ever scheduled; no media mounted at startup → early return at :181-183 ("Skipping storage pre-roll (%s): no media mounted"); recording already active → :185-187. In those cases cinemate_dev.py session-start exits non-zero with "Timed out waiting for storage pre-roll completion." (cinemate_dev.py:615) after ready_timeout — it does not hang, but the agent gets a failure it has no rule for.

**Fix (adjudicated):**

Insert as a sub-block immediately under Stage-1 step 1 in RUNBOOK.md (currently line 241), and add the cross-reference to 0.2.

REPLACE (line 241):
1. `session-start` → wait for `Storage pre-roll complete` → +1 s.

WITH:
1. `session-start` → wait for `Storage pre-roll complete` → +1 s.
   **If `session-start` exits non-zero with `Timed out waiting for storage pre-roll
   completion.`** — do not retry blindly. The session is still running (`started:<pid>` was
   already printed); a retry kills a healthy session and burns another 120 s. On three
   configurations the marker is unreachable by design and no wait will ever satisfy it.
   Diagnose in this order:
   - `findmnt -no SOURCE,FSTYPE /media/RAW` — no output means the RAW media never mounted, so
     the pre-roll never ran. **The log is silent in this case**; only the deferred variant
     prints (`Storage pre-roll remained deferred through startup, but no media is mounted`),
     so absence of a "Skipping storage pre-roll" line proves nothing.
   - `session-tail 200 | grep -i "storage pre-roll"` — `Automatic storage pre-roll disabled by
     settings.jsonc` means `auto_preroll` is off on this Pi; `Skipping storage pre-roll (…):
     recording already active` means a stale `is_recording=1` is left in Redis from a killed
     session (`session-send "redis-cli SET is_recording 0"` is not sanctioned — report it).
   In all three cases: **do not change `auto_preroll`** (known-context rule above — it
   confounds the comparison). Report the matching line to the operator and stop.
   Only with explicit operator approval may you proceed without the warm-up: use
   `--- Initialization Complete ---` as the readiness marker instead, record the deviation in
   the ledger, and flag every take started that way as `no-preroll` in the Stage 1 table.

AND REPLACE in 0.2 (lines 177-178):
0.2 **Sensor + mode table.** `session-start`, wait for `Storage pre-roll complete` in
`/tmp/cinemate_cli.log`, +1 s.

WITH:
0.2 **Sensor + mode table.** `session-start`, wait for `Storage pre-roll complete` in
`/tmp/cinemate_cli.log`, +1 s. If it times out, follow the ready-timeout rule in Stage 1
step 1 — this is the first place it can bite, and `status`'s `helper_session.ready` flag uses
the same marker, so it will read `false` for the same reason.

### M5 · [sampler-shell] 

**Claim checked:** The WAV duration snippet's output can be trusted as the audio-verdict input for every outcome class, including AUTO-STOP-RAM-GUARD and ABORTED-OTHER (RUNBOOK.md:131-136 + 152-156)

**Evidence:** cinepi_audio_capture.cpp:457 writes the header with `dataBytes = 0` at open, and it is only rewritten with the true size at line 715-721, on the normal shutdown path after `writerThread.join()`. If the capture process is killed or dies (exactly the AUTO-STOP-RAM-GUARD / ABORTED-OTHER classes this campaign exists to characterise), the on-disk `data` chunk header still says 0. Python's wave module trusts the chunk header, so `getnframes()` returns 0 and the snippet prints `frames=0 ... duration_s=0.000000` — it does NOT raise. The runbook's FAIL rule ("deviation > 1 frame period, any WAV discontinuity, or missing WAV") would be reached, but with a completely wrong diagnosis: the agent would report a huge sync deviation when the real fact is an unfinalised header sitting on top of a full-length data payload.

**Fix (adjudicated):**

Replace RUNBOOK.md lines 128-137 (the "WAV duration check" block) with:

WAV duration check (on the Pi, stdlib). The WAV always sits inside the take directory and its
basename equals that directory's name (`cinepi_sound.cpp:835`), so set the path explicitly
first — the snippet has no default and will die with `FileNotFoundError` on an empty argument:

```bash
TAKE_DIR=/media/RAW/<exact-take-dir>          # e.g. /media/RAW/CINEPI_250825_1432_C0001
WAV="$TAKE_DIR/$(basename "$TAKE_DIR").wav"
python3 - "$WAV" <<'EOF'
import sys, wave, os
p = sys.argv[1]
size = os.path.getsize(p)
w = wave.open(p, 'rb')
n, rate, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
print(f"frames={n} rate={rate} ch={ch} sampwidth={sw} "
      f"duration_s={n/rate:.6f} filesize={size}")
# Hard-abort guard: the header's data size is written as 0 at open and only
# rewritten with the true size on the graceful shutdown path. A frames=0 result
# on a large file means the capture process was hard-killed (power loss, OOM,
# cinepi-raw crash), NOT that audio was lost.
if n == 0 and size > 1024:
    with open(p, 'rb') as f:
        buf = f.read()
    ds = buf.find(b'data') + 8
    ix = buf.rfind(b'iXML')            # parent appends iXML after the data chunk
    payload = (ix if ix > ds else size) - ds
    print(f"UNFINALISED-WAV: data chunk header says 0 but {payload} payload bytes "
          f"are present; byte-derived duration_s={payload/(ch*sw)/rate:.6f} (estimate)")
EOF
```

If the snippet prints an `UNFINALISED-WAV` line, record the byte-derived duration as the real
one, note both numbers, and classify it as **UNFINALISED-WAV — not a sync deviation**. This
cannot happen on a `COMPLETE-*` or `AUTO-STOP-RAM-GUARD` take: the RAM guard only flips an
in-process flag (`cinepi_raw.cpp:228`), and the eventual stop goes through
`sound.record_stop()` → SIGTERM → graceful finalise. Treat it as evidence of a hard abort and
cross-check against the parent's `WAV ready for metadata update: <n> bytes` log line.

Do NOT add a blanket `(filesize-44)/(channels*sampwidth)` cross-check against `frames`: the
parent appends an iXML chunk after the data chunk and repairs only the RIFF size, so that
arithmetic disagrees with `frames` on every healthy take and would false-positive on all of
them. The `frames == 0` test above is the unambiguous signal.

### M6 · [sampler-shell] 

**Claim checked:** Stage 1 step 9: "Archive to the Mac (`development/pi-test-takes/c1/<take-id>/`)" (RUNBOOK.md:96-98, 264-265) — the destination path is usable when first referenced

**Evidence:** `ls -d /Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/c1` → "No such file or directory"; the parent contains only `.DS_Store`. No step in the runbook creates it — 0.9 (RUNBOOK.md:219) only does `mkdir -p /home/pi/c1/samples /home/pi/c1/results` on the Pi side. A multi-file `scp pi@cinepi.local:... <dest>/` into a non-existent directory fails outright (and a single-file scp silently creates a FILE named `c1` instead, which then breaks every subsequent take). By contrast the Pi-side ordering is correct: 0.9's `mkdir -p` creates `/home/pi/c1` as the parent of samples/results before the scp on the same line, and both `samples/` and `results/` exist before their first use in Stage 1 steps 5 and 8.

**Fix (adjudicated):**

Two edits (the step 9 one is load-bearing; the 0.9 one makes it fail fast in preflight).

EDIT 1 — RUNBOOK.md:219-220. Replace:

0.9 **Install instrumentation.** `mkdir -p /home/pi/c1/samples /home/pi/c1/results`; scp
`c1_sampler.sh` (chmod +x) and `analyze_cinepi_media.py` to `/home/pi/c1/`.

with:

0.9 **Install instrumentation.** On the Pi: `mkdir -p /home/pi/c1/samples /home/pi/c1/results`;
scp `c1_sampler.sh` (chmod +x) and `analyze_cinepi_media.py` to `/home/pi/c1/`. On the Mac,
create the archive root now — it does not exist yet:
`mkdir -p /Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/c1`.

EDIT 2 — RUNBOOK.md:263-265 (Stage 1 step 9). Replace:

9. Archive to the Mac (`development/pi-test-takes/c1/<take-id>/`): the analyzer JSON, the
   sampler CSV, `session-log.txt`, the WAV, and the first 3 + last 3 DNGs. Verify the copies
   are non-empty and the JSON parses.

with:

9. Archive to the Mac. Create the per-take directory first — `scp` will not create it, and an
   `scp` into a missing directory fails outright:
   `mkdir -p /Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/c1/<take-id>`.
   Then copy into it — always with a trailing `/` on the destination, so a stray copy can never
   land as a file named after the directory — the analyzer JSON, the sampler CSV,
   `session-log.txt`, the WAV, and the first 3 + last 3 DNGs. Verify the copies are non-empty
   and the JSON parses.

OPTIONAL EDIT 3 (cheap, prevents the same misread at first mention) — RUNBOOK.md:96-98, change
"Archive root on the Mac:" to "Archive root on the Mac (created in 0.9 — it does not exist
yet):".

### M7 · [math-audit] 

**Claim checked:** Phase 0.7: 'record `runway_s = buffer_size / fps` - how long a full disk stall can last before the RAM guard ends the take' (RUNBOOK.md:211-213).

**Evidence:** Dimensionally the formula IS correct: Redis `buffer_size` is a FRAME COUNT, not bytes. cinepi_controller.cpp:395-396 sets it from `maxRamBuffers()` (dng_encoder.hpp:164) = `max_ram_buffers_` = 0.90 x MemAvailable / dng_info.buffer_size (dng_encoder.cpp:847-849); redis_controller.py:22-23 documents BUFFER='number of raw frames in RAM', BUFFER_SIZE='RAM pool size'. frames/(frames/s) = s. But the MAGNITUDE is overstated because the take ends well before the pool is 100 % full. Pool slot = align_up(W*H*1.5 + 64 KiB, 1 MiB) (dng_encoder.cpp:803-806) = 18/13/5 MiB for A/B/C. At MemAvailable 1.1-1.5 GB: buffer_size = 52-71 (A), 72-99 (B), 188-257 (C); runbook runway = 4.7-6.5 s (A), 4.8-6.6 s (B), 7.5-10.3 s (C) - single-digit seconds, as expected. The 90 % backlog guard cuts that to 0.9x. Worse, since the pool is sized at 0.90 x MemAvailable, filling it drives psutil percent past 80 % first: solving (1 - 0.20 x MemTotal/MemAvail)/0.90 for MemTotal 1.85-2.0 GiB and MemAvail 1.1-1.5 GB gives a trip at f = 68-82 % of buffer_size in EVERY case. So true runway ~= 0.7 x buffer_size/fps, i.e. ~3.3-4.6 s (A), ~3.4-4.6 s (B), ~5.3-7.2 s (C). The runbook's number is 25-45 % optimistic.

**Fix (adjudicated):**

Replace RUNBOOK.md:211-213 with:

0.7 **RAM runway.** `free -b` — record `MemTotal` and `MemAvailable`. After setting each mode,
wait for the encoder to finish reconfiguring, then read `buffer_size` from Redis. It is a
**frame count**, not bytes: cinepi-raw sizes its pool as `0.90 x MemAvailable / slot_bytes`
where `slot_bytes = align_up(ceil(W x bits / 8) x H + 64 KiB, 1 MiB)`
(`dng_encoder.cpp:803-806`, `:845-849`), and republishes it on every `cam_init`, so a read
taken too soon returns the previous mode's value.

A take can be ended by RAM at three different fill fractions of that pool. Record all three
runways per mode and quote **the smallest** as the mode's real runway:

| Stop | Fires at pool fill `f` | Runway |
|---|---|---|
| cinemate system-RAM backstop (`RAM_LIMIT_PERCENT = 80`, `cinepi_controller.py:256`, `:2605`) | `f = (1 - 0.20 x MemTotal / MemAvailable) / 0.90` | `f x buffer_size / fps` |
| cinemate backlog guard (`BUFFER_LIMIT_PERCENT = 90`, `cinepi_controller.py:260`, `:2597`) | `0.90` | `0.90 x buffer_size / fps` |
| cinepi-raw pool exhaustion (`buffer_full()`, logs "RAM pool exhausted", `cinepi_raw.cpp:220-229`) | `~1.0` | `buffer_size / fps` |

Because the pool is itself 90 % of `MemAvailable`, `f` is below 0.90 for any
`MemAvailable <= MemTotal` — so unless available memory rises materially between the mode set
and the take, **the 80 % system backstop fires first, and the process that stops the take is
cinemate, not cinepi-raw**. Compute `f` from the live `free -b`; do not assume a board size.
(Last measured on this unit: 4048 MB total, ~2970-3110 MB available under load —
`system-review/PI-VERIFICATION-QUEUE.md` PI-016. That contradicts the "2 GB" line in the
known-context section above; trust `free -b`.)

### M8 · [math-audit] 

**Claim checked:** Phase 0.5: 'If a mode cannot fit or cannot stay under the storage cap at any usable fps, record it as INFEASIBLE-ON-THIS-RIG' - i.e. the fps formula `min(floor(0.95 x fps_max), highest int with data-rate <= 0.85 x sustained, 25)` (RUNBOOK.md:195-200) is safe at its lower end.

**Evidence:** The formula has no lower clamp and 'usable fps' is never defined. python3, mode A (4056x3040, 18.496 MB/frame): at S=400 MB/s the formula picks 11 fps; at S=150 MB/s (a USB SSD, or an NVMe whose SLC cache has been exhausted - see the dd finding) it picks 6 fps, which is 51 % of the mode's 11.72 fps cap. Mode B likewise drops 15 -> 9. A 6 fps 'long take' at 4056x3040 does not test the campaign's stated goal ('eliminate dropped frames ... at the higher 12-bit resolutions', RUNBOOK.md:19-20) - it under-drives the drive by design and will return COMPLETE-CLEAN with no information. At the true bottom the formula returns 0: the rate term hits 0 when sustained < MB-per-frame/0.85, i.e. < 21.76 MB/s for 4056x3040, < 15.46 for 4056x2160, < 5.44 for 2028x1520 - reachable if the RAW volume comes back as an SD card, which the runbook explicitly warns may have changed (RUNBOOK.md:56-59). `rec f 0` is then silently ignored (cinepi_controller.py:1212-1214: 'Timed recording frame count must be greater than zero.' then return) - no take, no error the agent will notice.

**Fix (adjudicated):**

Append to RUNBOOK.md after line 200 (end of section 0.5):

"The rate term has no floor — inspect it before using the result. If it is 0, no fps keeps the mode under the storage cap: that is the `INFEASIBLE-ON-THIS-RIG` case above — record the arithmetic and skip the mode. Never send `rec f 0`; cinemate logs `Timed recording frame count must be greater than zero.` and does nothing, so you would wait on a `Stopped recording` that never comes.

If the fps the camera actually accepted (the readback, not the computed value) is below 60 % of that mode's sensor `fps_max`, the drive set the rate, not the sensor. Run the mode anyway, but write `STORAGE-LIMITED (<fps> of <fps_max>, <n> %)` in the `feasible?` column of the 0.3–0.5 table, carry the label into the Stage 1 `limiting factor` column and the Stage 2 `drop-frame goal met?` cell, and never answer that cell a bare 'yes' — a clean take at that fps does not clear the mode at its native rate."

Note for whoever applies this: the threshold must be a percentage of the raw sensor `fps_max`, not of `floor(0.95 x fps_max)` as originally proposed — the derated value is already the number being tested, so comparing against it understates the gap.

### M9 · [consistency] 

**Claim checked:** Step 11's per-take note has a home in the ledger for Stage 2 as well as Stage 1.

**Evidence:** RUNBOOK.md:306 says 'Protocol = Stage 1's per-take procedure with:' — so step 11's per-take note applies to Stage 2 takes too. The ledger's Stage 1 section has a notes area (RESULTS.md:103-105 'Per-take notes (short; archive paths under `development/pi-test-takes/c1/<take-id>/`): / - S1-C1: —'). The Stage 2 section (RESULTS.md:140-161) has preconditions, a predictions table, the take table, and 'Skipped modes + why' — and no per-take-notes area at all. A session following 'append-per-phase, never rewrite a filled row' (RESULTS.md:5) has nowhere to append the Stage 2 notes.

**Fix (adjudicated):**

EDIT 1 (required) — file: /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RESULTS.md

Find this exact text (lines 159-161):

| S2-A2 | | | | | | | | | | | | | | |

Skipped modes + why: —

Replace with:

| S2-A2 | | | | | | | | | | | | | | |

Per-take notes (short; archive paths under `development/pi-test-takes/c1/<take-id>/`):

- S2-C1: —

Skipped modes + why: —


EDIT 2 (optional, fixes the ambiguity at its source) — file: /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md

Find this exact text (lines 268-270):

11. Ledger: one row in the Stage 1 table + a short per-take note (outcome class, audio
    verdict, buffer-pressure shape, verdict vs prediction). Commit after each mode's three
    reps.

Replace with:

11. Ledger: one row in the stage's take table + a short per-take note in that stage's
    "Per-take notes" list (outcome class, audio verdict, buffer-pressure shape, verdict vs
    prediction, and the take's archive path). Commit after each mode's three
    reps.

Rationale for Edit 2: step 11 currently hard-codes "the Stage 1 table", which Stage 2 must silently generalize anyway. Saying "the stage's take table" and naming the "Per-take notes" list makes the Stage 2 inheritance explicit and reads correctly in Stage 1. "three reps" is left untouched — the Stage 2 delta at RUNBOOK.md:310 already overrides it with "Two reps per mode".

### M10 · [consistency] 

**Claim checked:** The rest of the runbook's recorded fields (step 8 grep hits, Phase-0 0.3 validation results, 0.9, Stage-2 feasibility recompute) have a ledger home.

**Evidence:** Four smaller gaps, all direction runbook→ledger: (1) RUNBOOK.md:255-257 'record every hit in the ledger' for the `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` grep — the only surfaces are two single table cells, 'warnings in log' and 'xruns' (RESULTS.md:91), which cannot hold 'every hit'. (2) RUNBOOK.md:186-188 orders recording, per validation mode, 'WAV presence, and that the 25 DNGs are sequence-continuous' — the ledger's 0.3–0.5 table (RESULTS.md:45-49) has columns for bytes/frame, test fps, data rate, frames, size, free needed, feasible? and nothing for WAV presence or sequence continuity. (3) RUNBOOK.md:219-220 (0.9, install instrumentation) has no ledger sub-section; RESULTS.md jumps from '### 0.7–0.8' (line 63) to '### 0.10' (line 73), while RUNBOOK.md:170 says 'fill the Phase 0 tables in `RESULTS.md` as you go'. (4) RUNBOOK.md:307-308 Stage 2 'recompute the space feasibility (take sizes double … recompute, don't assume)' — the Stage 2 ledger section has no feasibility table, and the Phase-0 table's column is hardcoded 'frames 5 min' / 'take size GB' (RESULTS.md:45).

**Fix (adjudicated):**

Two ledger edits (RESULTS.md) plus one optional one-line runbook clarification. Do NOT add a 0.9 section or checkbox.

=== EDIT 1 — RESULTS.md, replace lines 45-49 verbatim (the delimiter row MUST also gain a group; the critic's version omitted this and would break the table) ===

| Mode | bytes/frame (measured) | test fps | data rate MB/s | frames 5 min | take size GB | free needed GB | feasible? | 0.3 validation (WAV present? 25 DNGs seq-continuous?) |
|---|---|---|---|---|---|---|---|---|
| A | | | | | | | | |
| B | | | | | | | | |
| C | | | | | | | | |

=== EDIT 2 — RESULTS.md, insert immediately after line 142 ("Preconditions recorded: ...") and before the line "Predictions (written/re-confirmed after the Stage 1 review, before the first S2 take):" ===

Feasibility recompute for 10-minute takes (`frames_10min = fps × 600` — recompute per
RUNBOOK Stage 2; do not carry the Phase-0 5-minute numbers over):

| Mode | test fps | frames 10 min | take size GB | free needed GB | free at check GB | feasible? |
|---|---|---|---|---|---|---|
| A | | | | | | |
| B | | | | | | |
| C | | | | | | |

=== EDIT 3 (optional, clarity only) — RUNBOOK.md, replace lines 268-270 ===

11. Ledger: one row in the Stage 1 table + a short per-take note (outcome class, audio
    verdict, buffer-pressure shape, the step-8 grep hits — verbatim lines, or "none" —
    and verdict vs prediction; the full log stays in the archive's `session-log.txt`).
    Commit after each mode's three reps.

### M11 · [consistency] 

**Claim checked:** The ledger demands no data the runbook never collects (direction 2: ledger column with no collection instruction).

**Evidence:** Checked every Stage-1 column (RESULTS.md:91) against the runbook. Collectible and correctly instructed: 'DNGs on disk' and 'seq gaps' — verified against the real analyzer, `~/.claude/skills/cinemate-dev/scripts/analyze_cinepi_media.py:29-36` emits `DngSummary.count` and `DngSummary.missing_indices`, and RUNBOOK.md:261 invokes it with `--json` (flag exists, script line 237). 'buffer max / shape' is instructed at RUNBOOK.md:163-164. 'warnings in log'/'xruns' at :255-257. 'class'/'audio'/'verdict vs prediction' at :268-269. The one genuine orphan is **'temp max'**: nothing in the runbook tells the session to derive it. RUNBOOK.md:246-247 (step 4) captures a *pre-take* temp, and the sampler CSV has a `temp` column (RUNBOOK.md:115), but step 7-8 (:252-261) never says to post-process the CSV for a maximum. Also cross-checked and clean: the Stage-2 gate's handbook-entry draft (RUNBOOK.md:321-323, 'Tested / Worked / Did not work / Why / Confirmed by') has an exactly matching home at RESULTS.md:171-172.

**Fix (adjudicated):**

Insert as the first bullet of step 8, i.e. between RUNBOOK.md line 254 ("8. Evidence capture, per take, before anything is deleted:") and line 255 (the `session-tail 400` bullet):

   - From the stopped sampler CSV (`/home/pi/c1/samples/<take-id>.csv`, schema at the top of
     this file — `temp` is field 12, `buffer` is field 2):
     `awk -F, 'NR>1{if($12+0>t)t=$12; if($2+0>b)b=$2} END{print "temp_max="t, "buffer_max="b}' /home/pi/c1/samples/<take-id>.csv`
     → ledger columns **temp max** and the max half of **buffer max / shape**; classify the
     curve shape per the buffer-pressure note above. Step 4's pre-take temp is a go/no-go
     check only — never write it into `temp max`.

### M12 · [consistency] 

**Claim checked:** Runbook 0.10's prediction instruction matches the ledger's prediction tables.

**Evidence:** RUNBOOK.md:222 says '0.10 **Predictions — written before Stage 1 starts.** One row per (mode × stage)' — literally 6 rows (A/B/C × S1 and × S2) before Stage 1 begins. The ledger's 0.10 table (RESULTS.md:73-79) has only 3 rows: `A × S1`, `B × S1`, `C × S1`. The Stage 2 predictions live in a separate table (RESULTS.md:144-150) whose caption is 'written/re-confirmed after the Stage 1 review, before the first S2 take', matching RUNBOOK.md:314-315 — which directly contradicts 0.10's 'per (mode × stage) … before Stage 1 starts'. A literal-minded session will either add three S2 rows to the 0.10 table or pre-fill the Stage 2 table, and then collide with the append-only rule at RUNBOOK.md:331 / RESULTS.md:5 ('never rewrite a filled row') when it later 're-confirms' them.

**Fix (adjudicated):**

Replace RUNBOOK.md lines 222-225 (the whole 0.10 paragraph, not 222-223) with:

0.10 **Predictions — written before Stage 1 starts.** One row per selected mode, **Stage 1
only** — the `A × S1` / `B × S1` / `C × S1` rows already present in the ledger's 0.10 table
(if no 25 fps control mode was selected in 0.2, mark row C `n/a`). Stage 2's predictions are
a separate table, filled later — see Stage 2; do not pre-fill it here. Per row: predicted
outcome class + audio verdict, with one sentence of reasoning anchored in the 0.3–0.7
numbers. The 2 GB RAM-guard confound must appear explicitly in the reasoning for any mode
whose data rate is within 15 % of the sustained speed.

Note the final sentence is carried over verbatim from the current line 224-225 and must not
be dropped. Line 226 (blank) and line 227 (`session-stop`. Commit the ledger …) are
unchanged. No change is needed at RUNBOOK.md:314-315 or in RESULTS.md.

### M13 · [consistency] 

**Claim checked:** The runbook keeps the feature plan's C1 State cell current as the campaign progresses.

**Evidence:** dev-track/README.md:21 carries a live State cell, 'Runbook ready, campaign not started'. The runbook's ledger-discipline section (RUNBOOK.md:329-336) and both STOP-gate sections (:283-294, :317-325) only ever name `RESULTS.md`; RUNBOOK.md:38 even pins the commit set to 'git add dev-track/C1-longtake-stability/RESULTS.md (plus any file you deliberately created)'. So the README's State cell will still read 'campaign not started' after Stage 1 and Stage 2 complete, while RESULTS.md:7 says otherwise — the feature plan goes stale against its own ledger with no instruction that would prevent it.

**Fix (adjudicated):**

Append as a fourth bullet at the end of RUNBOOK.md's "Ledger discipline (applies to every phase)" section (after line 336):

- The plan table mirrors this ledger: whenever you change the **Status** line at the top of
  `RESULTS.md` (Phase 0 complete, STOP GATE 1, STOP GATE 2), edit the **State** cell of the
  **C1 row only** in `dev-track/README.md` to match, in the same commit
  (`git add dev-track/README.md dev-track/C1-longtake-stability/RESULTS.md`). That cell is
  overwritten in place — the append-only / strike-through rule above governs `RESULTS.md`,
  not the plan table. Leave the C0 and C2 rows alone.

### M14 · [consistency] 

**Claim checked:** Nothing in the runbook references the system review as if C1 were still part of it.

**Evidence:** One live leftover. RUNBOOK.md:333-334: '- Every number in the ledger carries its source (command or file), same as the PI-RESULTS files **this review** already uses.' 'This review' frames C1 as a system-review workstream, directly contradicting RUNBOOK.md:17-18 (C1 is 'of the CineMate development track') and README.md:6-8 ('deliberately separate from the system-review project: `system-review/` owns remediation of review findings; this track owns **features**'). Risk to an unsupervised session: it may conclude it should also update the review's ledgers (`system-review/STATE.md`, `PI-VERIFICATION-QUEUE.md`) or commit to `claude/cinemate-system-review-kickoff-cilicc`, neither of which the runbook sanctions. The referenced files do exist and are reachable on this branch (`system-review/PI-RESULTS-2026-08-24.md`, `system-review/PI-RESULTS-2026-08-25.md`; `git ls-files system-review` → 63 tracked files on `feature/dev-track`), but the runbook never gives their path. Everything else checked clean: RUNBOOK.md:18's pointer ('its `README.md` explains how the track relates to the system review') is correct and matches README.md:41-52; the twelve 'Fable review/thread' mentions (:33, :44, :45, :72, :283, :291, :292, :298, :301, :315, :317, :324) all refer to the operator's review thread, not the system review; the runbook never instructs writing to any `system-review/` file.

**Fix (adjudicated):**

Replace RUNBOOK.md lines 333-334 (currently: "- Every number in the ledger carries its source (command or file), same as the PI-RESULTS\n  files this review already uses.") with exactly:

- Every number in the ledger carries its source (command or file). Same convention as
  `cinemate/system-review/PI-RESULTS-2026-08-25.md` on this branch — skim it if you want a
  worked example of the format. That file belongs to the system review, which C1 is **not**
  part of: read from `cinemate/system-review/` if useful, never write to it.

Note the `cinemate/` prefix is load-bearing — the session's working directory is
`/Users/patrikeriksson/Documents/cinemate` (RUNBOOK.md:4-5), one level above the repo root,
so the bare `system-review/...` form does not resolve.

### M15 · [executability] 

**Claim checked:** Ground rule 2 / 0.6: the setcap fix is "the one sanctioned config intervention", so a session that sees dropped frames will not start editing source.

**Evidence:** The boundary is well drawn for CODE (RUNBOOK.md:29-34 is explicit), but 0.6 states TWO invariants and sanctions a fix for only one. RUNBOOK.md:205-206 requires "`cinepi-audio-capture` at `rtprio` 80 on core 3, and no `dng-enc`/`dng-dsk` thread on core 3". The second is the known ext4 disk-worker/audio-core collision (src/module/storage_profiles.py:41 documents the invariant). If it fails, the runbook gives no action at all — and because ground rule 2 permits "configuration-level corrections when a Phase 0 preflight check fails against its documented invariant", a session could reasonably read a `storage_profiles.py` / `settings.jsonc` affinity edit as sanctioned. That is a source-code edit dressed as configuration.

**Fix (adjudicated):**

Append to RUNBOOK.md section 0.6, immediately after the existing sentence "This is the one sanctioned config intervention." (line 209). Do not alter the preceding setcap text.

Exact text to add:

> A `dng-enc`/`dng-dsk` thread showing `psr` 3 is a **finding, not something you fix**. No recorder profile requests core 3 and cinepi-raw strips the audio core from any requested affinity as a backstop (`dng_encoder.cpp`), so a hit here means the Pi's build or profile is not what `dev` says it is — which also puts 0.1's recorded commits in doubt. Record the raw `ps` output verbatim in the ledger, STOP and report to the operator, and end your turn. Do not edit `storage_profiles.py`, or any other file, to correct the affinity yourself: `setcap` above is the only fix you may apply, and every code-level affinity change is a Fable-thread decision. If the operator clears you to proceed regardless, flag the audio verdict of every take that follows as confounded.

Three deliberate departures from the original proposal:
1. The confound clause is forward-looking ("every take that follows") and conditioned on an operator override, not retroactive over a campaign that has not yet produced any audio verdicts.
2. `settings.jsonc` is not named, because it exposes no affinity setting — naming it would document a knob that does not exist.
3. The backstop is cited so the session understands why a core-3 sighting is evidence of a stale or hand-built binary rather than a tunable, which is what makes reporting the correct response and links it back to the 0.1 commit record.

### M16 · [executability] 

**Claim checked:** The other stop points (0.1 repos not on `dev`, 0.6 mic absent, Phase 0 STOP-check) are as clear as Gate 1.

**Evidence:** They say STOP but never "end your turn", unlike Gate 1 which does (RUNBOOK.md:294). RUNBOOK.md:174-175 "if not, STOP and report — do not switch them yourself"; :202-203 "if absent, STOP and ask the operator to attach it"; :229-231 "report to the operator and wait before Stage 1". "Wait" is the weakest — a session can read it as polling and continuing in-turn, which for the mic case means running the whole campaign with no audio, and for the Phase 0 STOP-check means running an invalidated test design.

**Fix (adjudicated):**

Apply ONE edit, at RUNBOOK.md:229-231 only. Leave :175 and :203 unchanged (their capitalized STOP matches house style in C0/C2 SONNET-PROMPT.md and is sufficient).

Replace lines 229-231, currently:

**Phase 0 STOP-check (not a gate):** if any of 0.1–0.9 contradicts the "known context"
section in a way that changes the test design (different sensor, exFAT instead of ext4,
missing mic, throttling at idle), report to the operator and wait before Stage 1.

with:

**Phase 0 STOP-check (conditional — it fires only when triggered, unlike the scheduled
Gates 1 and 2, but when it fires it is just as hard a stop):** if any of 0.1–0.9 contradicts
the "known context" section in a way that changes the test design (different sensor, exFAT
instead of ext4, missing mic, throttling at idle), report the contradiction to the operator
with its ledger row and source command, then **end your turn**. Do not begin Stage 1 in the
same turn — Stage 1 resumes only on the operator's explicit go.

Rationale for the two changes: "(not a gate)" is replaced rather than merely supplemented, because leaving it in place next to a new "end your turn" is self-contradicting and preserves the exact non-binding reading that causes the defect; the replacement keeps the author's genuine distinction (conditional vs. scheduled) while removing the inference that ground rule 5 and the launch prompt's "Stop at every STOP gate" do not reach this check.

### M17 · [executability] 

**Claim checked:** Stage 1 step 4 / sequencing: "if temp > 70 °C, cool down before starting" and "Between takes: wait for temp < 70 °C and `Dirty` in `/proc/meminfo` back under ~50 MB."

**Evidence:** Neither wait is bounded and neither has an escalation rule. On a 2 GB CM5 under sustained 12-bit write load, `Dirty` may never fall under 50 MB if the drive is the bottleneck (the exact condition the campaign is measuring), and there is no fan/cooling action available to an agent — so "cool down" is an operator-physical action stated as if it were an agent action. A cold session has two bad options: poll forever, or invent a timeout.

**Fix (adjudicated):**

Three edits. Splits the two waits (different physics, different failure meaning), fixes the kB/MB unit trap, and catches an unsatisfiable gate at preflight.

EDIT 1 — replace the bullet at RUNBOOK.md line 279 ("- Between takes: wait for temp < 70 °C and `Dirty` in `/proc/meminfo` back under ~50 MB.") with:

- Between takes, return the rig to a known state before the next `rec`. Poll every 30 s with
  `vcgencmd measure_temp` and `awk '/^Dirty:/{print $2" kB"}' /proc/meminfo`. **`/proc/meminfo`
  is in kB — the ~50 MB gate is ~51200 kB**, the same unit as the sampler's `dirty_kb` column.
  - **`Dirty` under ~51200 kB.** This should clear within about a minute: recording has stopped
    and step 7 already confirmed `is_writing_buf` = 0, so nothing is adding to the backlog and
    kernel writeback only has to drain it. If it is *still* above ~51200 kB after **5 minutes**,
    that is an I/O fault, not thermal soak. Capture `dmesg | tail -150` and
    `grep -E '^(Dirty|Writeback):' /proc/meminfo` to the archive, log it in the ledger as a
    durability-relevant finding (it bears directly on the "no end-of-take durability barrier"
    item in Known context), and do not start another take on a drive that is not retiring its
    writes — report to the operator and end your turn.
  - **Temp < 70 °C.** Idling the Pi is the only cooling action available to you. If temp is
    still > 70 °C after **10 minutes** of idle, it will not get there on its own. Do **not**
    start the next take and do **not** proceed hot. Record the last three readings plus the
    completed/remaining take list in the ledger, then tell the operator — paste-ready, same
    pattern as the STOP gates — that the rig needs physical cooling (a fan, opening the
    enclosure, or a cooler ambient), and **end your turn**. Resume at the next un-run take when
    they say so.

EDIT 2 — replace the trailing clause of step 4 (RUNBOOK.md line 247), "if temp > 70 °C, cool down before starting.", with:

   space ≥ required (0.5); if temp > 70 °C, apply the between-takes cooldown rule in
   "Sequencing rules" below before starting. Never start a take hot.

EDIT 3 — append to 0.8 Thermals (after RUNBOOK.md line 218):

If idle temp is already ≥ 70 °C, the between-takes gate is unsatisfiable on this rig as
configured — raise it at the Phase 0 STOP-check and wait for the operator, rather than
discovering it between takes with nine takes queued.

### M18 · [executability] 

**Claim checked:** Outcome classes are exhaustive — every take gets exactly one class.

**Evidence:** Formally exhaustive but two cases land in a misleading bucket. (a) MORE DNGs than requested: `COMPLETE-CLEAN` requires "DNG count == requested" (RUNBOOK.md:145), so an overshoot falls to `COMPLETE-WITH-LOSS` (RUNBOOK.md:146, "any of the above is violated") — deterministic, but it files an overshoot as a loss and will pollute the Gate 1 "frames lost total" column in RESULTS.md:111-115. Note the frame limit counts SLOTS not files (docs/cli-commands.md:82: "Dropped frames still count toward that limit"), so DNG count should never exceed the request — an overshoot means something is wrong and deserves its own flag. (b) WAV missing on an otherwise clean take: class = COMPLETE-CLEAN, audio = FAIL, and RUNBOOK.md:156 then instructs "run the sync-matrix deep-dive method before writing the verdict" — impossible with no WAV, and the method file does not exist anyway.

**Fix (adjudicated):**

Two edits to /Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md.

EDIT 1 — replace lines 145-146 (the COMPLETE-CLEAN and COMPLETE-WITH-LOSS rows) with these three rows:

| `COMPLETE-CLEAN` | Stopped at the requested frame count; DNG count == requested; no filename-sequence gaps; `missing_frame_count` == 0; no write-failure or drop/sync warnings in the session log |
| `COMPLETE-OVERSHOOT` | Every `COMPLETE-CLEAN` condition holds except that DNG count is **greater** than requested. Expected and benign, not a fault: `arm_frame_limited_stop` deliberately stops `min(2, frames-1)` slots early to compensate for pipeline lead (`src/module/redis_listener.py`; the take's `Armed exact frame-limited stop: ... pipeline lead compensation N` line), so landing exactly on the request is a calibrated estimate that can land over. cinemate agrees nothing was lost: `missing_frame_count` is 0, and the log reads `Frames within final tolerance: -1 frame difference...` (+1 over — inside the default ±1 final tolerance, so **no warning is emitted at all**) or `Sensor ran fast: recorded N extra frame(s)` (+2 or more). Count the take as **clean** in the Gate 1 `takes clean / total`, note the surplus in the per-take note, and put **0** — never a negative number — in `frames lost total`. |
| `COMPLETE-WITH-LOSS` | Reached the requested count / duration but a `COMPLETE-CLEAN` condition **other than a pure DNG-count overshoot** is violated — i.e. DNG count *below* requested, filename-sequence gaps, `missing_frame_count` > 0, or write-failure/drop/sync warnings in the session log |

Then add this sentence immediately after the outcome-class table (before "Audio verdict per take"):

`frames lost total` in the Gate 1 summary is the sum of the per-take `missing_frame_count`, **not** `frames requested − DNGs on disk`. The two diverge whenever the frame-limited stop lands off the request in either direction; only `missing_frame_count` reflects frames the system considers absent.

EDIT 2 — replace line 156 with:

  On FAIL, run the sync-matrix deep-dive method before writing the verdict — **except when the WAV is missing entirely**, where there is nothing to analyse. For a missing WAV, record `FAIL (no WAV)` and grep the take's session log for `helper not found`, `Failed to launch audio capture helper`, `Audio capture helper exited before capture actually started`, and `Audio capture helper:`; cinepi-raw (`cinepi/cinepi_sound.cpp`) emits each of these and deliberately continues the take without audio. Quote the matching line in the ledger and carry it to the STOP gate. Do not re-run the take on that basis alone, and do not change the video outcome class — the audio verdict is independent of it.

### M19 · [executability] 

**Claim checked:** Phase 0.7: "read `buffer_size` from Redis and record `runway_s = buffer_size / fps` — how long a full disk stall can last before the RAM guard ends the take"; and the known-context claim that "the 80 % RAM guard force-stops recording when the write backlog fills it".

**Evidence:** The backlog guard is 90 %, not 80 %, so the runway formula overstates the real runway by ~11 %. src/module/cinepi_controller.py:260 `self.BUFFER_LIMIT_PERCENT = 90` is the primary trip on `buffer/buffer_size` (cinepi_controller.py:2597-2602); `self.RAM_LIMIT_PERCENT = 80` (cinepi_controller.py:256) is a separate SYSTEM-RAM backstop (cinepi_controller.py:2606-2610), not the write-backlog guard. There is also a third, independent stop inside cinepi-raw: `console->warn("RAM pool exhausted — recording stopped")` when the encoder pool (90 % of MemAvailable at configure time, dng_encoder.cpp:846) is full — cinepi_raw.cpp:225-230. The runbook's single AUTO-STOP-RAM-GUARD class collapses all three, which is fine for classification but loses the distinction Gate 1 needs.

**Fix (adjudicated):**

Three exact replacements in `/Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C1-longtake-stability/RUNBOOK.md`.

=== 1. Known-context bullet (lines 50-54) ===

REPLACE:
- The dev Pi is a **2 GB CM5 Lite**. The DNG encoder's RAM buffer is small on this unit and
  the **80 % RAM guard force-stops recording** when the write backlog fills it. A RAM-guard
  auto-stop is a *distinct outcome class* (drive can't sustain the data rate), not a
  drop-frame bug — classify it as such, never as "dropped frames".

WITH:
- The dev Pi is a **2 GB CM5 Lite**. There are **three independent auto-stops**, not one.
  They are different guards on different quantities — always record *which* one fired:

  | # | Guard | Trips on | Log line |
  |---|---|---|---|
  | 1 | **Write-backlog (primary)** `BUFFER_LIMIT_PERCENT = 90` (`cinepi_controller.py:260`, checked first at `:2597`) | `buffer / buffer_size` ≥ 90 % — the RAM frame-buffer slots | `RAM frame buffer <n>% ≥ 90%! Stopping recording.` |
  | 2 | **System-RAM backstop** `RAM_LIMIT_PERCENT = 80` (`:256`, checked second at `:2606`) | `psutil.virtual_memory().percent` ≥ 80 % — whole-board RAM, *not* the backlog | `RAM <n.n>% ≥ 80%! Stopping recording.` |
  | 3 | **cinepi-raw pool stop** (independent of Cinemate) | encoder pool full — pool = 90 % of `MemAvailable` at configure time (`dng_encoder.cpp:846`), `buffer_full()` trips 2 slots short (`cinepi_raw.cpp:225-230`) | `RAM pool exhausted — recording stopped` |

  Guards 1 and 2 both write their tripping percentage to `memory_alert`
  (`cinepi_controller.py:2627`), so the value alone does **not** identify which fired; guard 3
  never sets it at all. Both Cinemate guards then log the generic `Stopped recording` — the
  warning line above it is the only discriminator. All three map to the single
  `AUTO-STOP-RAM-GUARD` outcome class, which is a *distinct outcome class* (drive can't sustain
  the data rate), not a drop-frame bug — classify it as such, never as "dropped frames".

=== 2. Phase 0.7 (lines 211-213) ===

REPLACE:
0.7 **RAM runway.** `free -b`; after setting each mode, read `buffer_size` from Redis and
record `runway_s = buffer_size / fps` — how long a full disk stall can last before the RAM
guard ends the take.

WITH:
0.7 **RAM runway.** `free -b`; after setting each mode, read `buffer_size` from Redis (slot
count, not bytes) and record `runway_s = 0.90 × buffer_size / fps` — how long a full disk
stall can last before **guard 1**, the 90 % write-backlog guard, ends the take. Treat this as
an **upper bound**: guard 2 (80 % system RAM) and guard 3 (cinepi-raw's pool) can preempt it.
Record `MemAvailable` from `free -b` at the same moment so the ledger shows how much headroom
guard 2 had.

=== 3. Stage 1 step 8, first two bullets (lines 255-259) ===

REPLACE:
   - `session-tail 400` → save to the archive as `session-log.txt`; separately grep the take
     window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` (case-insensitive) and
     record every hit in the ledger.
   - Redis: `framecount`, `missing_frame_count`, `drop_frame_during_last_take`,
     `memory_alert`, `last_dng_cam0`.

WITH:
   - `session-tail 400` → save to the archive as `session-log.txt`; separately grep the take
     window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` (case-insensitive) and
     record every hit in the ledger.
   - **Auto-stop grep — the pattern above matches none of the three guard lines.** Grep the
     window a second time: `grep -Ei 'RAM frame buffer|RAM [0-9]|RAM pool exhausted'`
     (POSIX ERE — `\d` does not work in `grep -E`). Record the matching line verbatim and
     which guard number it is. No match + a short take = look harder before classifying.
   - Redis: `framecount`, `missing_frame_count`, `drop_frame_during_last_take`,
     `memory_alert`, `last_dng_cam0`. `memory_alert` carries the tripping percentage for
     guards 1 and 2 only, and does not say which — guard 3 leaves it unchanged.

### M20 · [executability] 

**Claim checked:** Ground rule 3: bookkeeping commits with `git add dev-track/C1-longtake-stability/RESULTS.md`, never `git add -A`.

**Evidence:** The path is relative to the wrong root. The session's working directory is `/Users/patrikeriksson/Documents/cinemate` (RUNBOOK.md:4-5) but the git repo containing `dev-track/` is `/Users/patrikeriksson/Documents/cinemate/cinemate` (confirmed: `git -C /Users/patrikeriksson/Documents/cinemate/cinemate rev-parse --abbrev-ref HEAD` → `feature/dev-track`). `git add dev-track/…` from the stated working directory fails, and `cd` does not persist between tool calls in this harness. The no-`git add -A` guard is correct and important (LFS pointer trap) and is well stated.

**Fix (adjudicated):**

Replace RUNBOOK.md ground rule 3 (lines 35-39) with:

3. **All bookkeeping goes to `cinemate/dev-track/C1-longtake-stability/RESULTS.md`** on the
   local branch `feature/dev-track` (cinemate repo, root
   `/Users/patrikeriksson/Documents/cinemate/cinemate`). Commit after every phase and every
   take batch. `cd` does not persist between shell calls — use `git -C` and absolute paths:
   `git -C /Users/patrikeriksson/Documents/cinemate/cinemate add dev-track/C1-longtake-stability/RESULTS.md`,
   then `git -C /Users/patrikeriksson/Documents/cinemate/cinemate commit -m "c1: …"`.
   **Never `git add -A` in this repo** (LFS pointer trap) — stage the named files only (the
   ledger, plus any file you deliberately created). Do not push without asking the operator.

Notes on the replacement: the `cd`/`git -C` sentence is copied verbatim from the track's own
C0 and C2 SONNET-PROMPT.md files so the three documents agree. Line 35's
`cinemate/dev-track/...` reference is deliberately left unchanged — it is a
working-directory-relative file path, not a git pathspec, and is correct as written. The
`git add -A` prohibition and the no-push rule are preserved unchanged. No other line in the
runbook needs editing; line 290's repo-relative path is prose in the operator paste-message,
not an executed command.


---

## REFUTED (13) — do NOT act on these

Raised by a first-pass reviewer, then falsified on re-check. Recorded so nobody re-raises them.

**R1** [redis-and-cli] COMPLETE-CLEAN = "Stopped at the requested frame count; DNG count == requested"; Phase 0.3 expects `rec f 25` to yield exactly 25 sequence-continuous DNGs

> Why refuted: The critic reads the source correctly but draws the wrong conclusion, and the empirical premise of the second half is falsified.

MECHANISM — what I confirmed:
- redis_listener.py:799-803: `_current_expected_frame_slots` returns `framecount + drop_frame_count_current_take`. Dropped slots DO count toward N. Also documented at docs/cli-commands.md:82.
- redis_listener.py:250-254: `stop_lead_slots = min(2, max(frames_target - 1, 0))` — a fixed 2-slot pipeline lead, as claimed.
- redis_listener.py:652-654 and :1867: for a frame-limited take `expected_frames_total = frame_limit_requested_slots` (= N) and `missing_frames_count = max(0, expected - recorded)`, where `recorded_frames_total` (redis_listener.py:1734) is the on-disk DNG count. So missing_frame_count is measured against the full requested N, as claimed.

WHY THE FINDING STILL FAILS:

(1) The drop-slot accounting is the discriminator 

**R2** [sampler-shell] 0.4: `oflag=direct` will work on whatever filesystem /media/RAW actually is (RUNBOOK.md:190-193 expects "the NVMe, ext4", but the Phase 0 STOP-check at line 231 explicitly contemplates "exFAT instead of ext4")

> Why refuted: I tried to reproduce the critic's mechanism against the actual kernel source for the kernel this Pi runs, and it is falsified on all three of its technical legs. The runbook also already handles the FSTYPE branch the critic says is unhandled.

**1. The exFAT "silent buffered fallback" was removed before this Pi's kernel.**
The critic describes the `exfat_direct_IO` guard that returns 0 for extending writes. That guard is real — but only on old kernels. I pulled both versions:

- Linux **v6.6** `fs/exfat/inode.c:409-439` still has it:
  `if (EXFAT_I(inode)->i_size_aligned < size) return 0;` with the comment `Return 0, and fallback to normal buffered write.`
- Linux **v6.12** `fs/exfat/inode.c:468-507` has **no such guard**. It goes straight to `ret = blockdev_direct_IO(iocb, inode, iter, exfat_get_block);`. The `i_size_aligned` bookkeeping was replaced by `valid_size` tracking, and `exfat

**R3** [sampler-shell] 0.6 `getcap $(command -v cinepi-audio-capture)` and Stage 1 step 8 `dmesg | tail -150` (RUNBOOK.md:203, 260) run successfully as the `pi` user

> Why refuted: The critic's two greps are correct — I reproduced both against /Users/patrikeriksson/Documents/cinemate/cinemate/cinemate-install.sh: `grep -nE 'libcap|getcap|setcap'` returns 0 hits and `grep -nE 'dmesg_restrict|sysctl'` returns 0 hits. But "the installer doesn't provision it" is not the same as "unverifiable," and the conclusion fails on three independent grounds.

1. dmesg-as-pi is PROVEN to work on this exact stack, from in-repo evidence — it is not unverifiable.
The chain is architectural, not circumstantial:
- services/cinemate-autostart/cinemate-autostart.service:23 → `User=pi` / `Group=pi`
- src/main.py:625-626 constructs and starts `DmesgMonitor`
- src/module/dmesg_monitor.py:64-69 → `subprocess.Popen(["dmesg", "--follow", "--human"], ...)`
- src/module/simple_gui.py:1054 → `values["low_voltage"] = "VOLTAGE" if self.dmesg_monitor.undervoltage_flag else ""`
That is a shipped, use

**R4** [claims-audit] Phase 0.4's "`findmnt -no SOURCE,FSTYPE /media/RAW` (expect the NVMe, ext4)" (RUNBOOK.md:190-191) — the ext4 half of the storage identity carried in as established

> Why refuted: See structured reasoning above.

**R5** [math-audit] Audio PASS threshold: '|wav_duration - dng_count/fps_target| <= 0.5 frame period' (RUNBOOK.md:152-153), fixed for the whole campaign including Stage 2's 10-minute takes.

> Why refuted: The critic's arithmetic is exactly right, and the structural observation is real — but the finding does not survive, on four independent grounds, the strongest being that the proposed fix reproduces the very defect it claims to remove.

1. WHAT I CONFIRMED. RUNBOOK.md:139 states thresholds are "fixed for the whole campaign"; they appear once at :152-155; Stage 2 (:298-315) never restates them and changes only `frames_10min = fps × 600` and rep count. So the same absolute tolerance does apply to 2x-longer takes. Every ppm figure the critic cites reproduces: 11 fps -> 45.45 ms = 151.5/75.8 ppm; 15 fps -> 33.33 ms = 111.1/55.6 ppm; 25 fps -> 20.00 ms = 66.7/33.3 ppm. The mode letters and test fps are right too (0.5's `min(0.95×fps_max, ..., 25)` on the :58 mode table gives A=11, B=15, C=25).

2. THE FIX DOES NOT FIX IT. The proposed PASS is `<=150 ppm AND absolute <= 1 frame period`. The co

**R6** [math-audit] 'full takes are 30-70 GB and must never be copied to the Mac' (RUNBOOK.md:95), stated unqualified for the whole campaign.

> Why refuted: The critic's arithmetic is correct, but the defect it alleges is not.

WHAT I CONFIRMED. I recomputed from scratch off the RUNBOOK.md:58 mode table and the 0.5 fps formula and reproduced the critic's figures exactly: Stage 1 = 34.68 GB (C, 7500 x 4.624 MB), 59.14 GB (B, 4500 x 13.141 MB), 61.03 GB (A, 3300 x 18.495 MB); Stage 2 doubles to 69.36 / 118.27 / 122.07 GB. I also verified the packed-12 basis is real rather than assumed — cinepi-raw genuinely packs (`pack_row_16_to_12bit` and `unpack_pisp_comp1_row_to_packed12` in cinepi/dng_pack.hpp), so 1.5 bytes/px is right for the payload. I swept sustained write speed from 300 to 1500 MB/s; fps stays sensor-limited at 11/15/25 above ~240 MB/s, so the sizes are not sensitive to the critic's assumed 400 MB/s. So yes, taken literally, "30-70 GB" is honest for Stage 1 and roughly 2x low for Stage 2.

WHY IT IS STILL NOT A DEFECT. The critic's l

**R7** [consistency] Mode letter C and take IDs like 'S1-C1' vs the batch name 'C1' are unambiguous enough for an unsupervised executing session.

> Why refuted: The critic's line citations are all factually accurate, but the inference from them collapses under verification. The decisive test is a left-context grep of every `C1` occurrence across both files. The split is perfectly bimodal with zero exceptions:

- Batch sense: `# C1`, `tch C1`, `h **C1`, `the C1`, `ack/C1` (x4, i.e. the path `dev-track/C1-longtake-stability`).
- Mode-C-rep-1 sense: ` S1-C1` (x2), ` S2-C1` (x1).

Every single take-sense occurrence carries the mandatory stage prefix. A bare `C1` never denotes a take anywhere in either file. This is not an accident — RUNBOOK.md:237 defines the grammar explicitly ("Take IDs: `S1-<mode-letter><rep>`"), and RUNBOOK.md:180 separately defines the mode letters. The document already declares both namespaces and makes them structurally disjoint. That IS the disambiguation mechanism, and compliance is 100%.

Now each of the critic's three "co

**R8** [consistency] Every field runbook step 8 says to record has a home in the ledger's Stage-1 table (direction 1: runbook collects → ledger has nowhere to put it). Specifically the Redis readouts.

> Why refuted: The critic's column-counting is accurate but their load-bearing claim is not. They assert the four uncolumned keys "are Redis-transient — after `session-stop` and the next take they are gone, so a value not written into the ledger at step 11 is lost permanently." I checked each against the runbook's own instrumentation and against the cinemate source. Three of the four are durably archived, and the fourth carries no information.

1. `framecount` — IS captured. It is column 4 of the sampler CSV (RUNBOOK.md:115), sampled every 2 s. Step 7 keeps the sampler running until after `Stopped recording` and until `is_writing`/`is_writing_buf` reach 0, so the settled end-of-take value is in the file; step 9 archives the CSV to the Mac and verifies it is non-empty. The CSV is strictly more informative than one ledger cell: `redis_listener.py:1358` (`reset_framecount`, invoked at :1384 on `is_recordi

**R9** [consistency] The ledger's WAV column matches the units the runbook's audio verdict is defined in.

> Why refuted: Not reproduced. The critic quotes both files correctly but misreads what the ledger column is for and misses the note mechanism both files define.

(1) Units are not mismatched. RUNBOOK.md:152 defines the deviation as `|wav_duration − dng_count/fps_target|` — a time quantity. The threshold ("0.5 frame period", "1 frame period") is also a time, just expressed as a multiple of 1/fps. Milliseconds is the correct raw unit for the measurement; "frame periods" is the normalizer, not a rival unit. The source instrument (the WAV snippet at RUNBOOK.md:131-137) emits `duration_s` to 6 decimals, so ms is the natural ledger granularity.

(2) The "converted figure has no cell" claim is false in substance — the conversion factor is column 3 of the very same row. RESULTS.md:91 and :152 read `Take | Mode | fps | frames req | ... | class | WAV Δ (ms) | xruns | audio | ...`. Frame period ms = 1000/fps; Δ_

**R10** [executability] Step 10: `rm -rf /media/RAW/<exact-take-dir>` — the named directory only, never a wildcard — is a safe deletion.

> Why refuted: The critic's supporting fact is real, but the load-bearing premise is false and the proposed fix is inert against the very scenario it targets.

WHAT CHECKS OUT
- `docs/storage-preroll.md:19` does say pre-roll writes the saved `last_dng_*` values back to Redis, and the source confirms it: `src/module/storage_preroll.py:195-199` snapshots `LAST_DNG_CAM0/1`, and `_restore_preroll_state` (lines 356-377) writes them back after the warm-up, defaulting to the literal string `"None"` when the baseline was empty.
- The runbook genuinely never states how to derive `<take-dir>` / `<exact-take-dir>`. Grepping RUNBOOK.md yields only three hits (lines 259, 261, 266), none of which is a derivation instruction.

WHY THE FINDING FAILS — the premise is falsified
"The only obtainable source for the directory name is `last_dng_cam0`" is wrong. The runbook already puts at least four Redis-independent source

**R11** [executability] Evidence ordering: step 8 capture → step 9 archive → step 10 delete, "per take, before anything is deleted".

> Why refuted: The critic read cinemate_dev.py correctly but misread the runbook, and the severity claim fails on its own rubric.

VERIFIED AS TRUE: /Users/patrikeriksson/.claude/skills/cinemate-dev/scripts/cinemate_dev.py:588 (build_session_start_script) does `rm -f /tmp/cinemate_cli.in /tmp/cinemate_cli.log /tmp/cinemate_cli.pid`. Same deletion at :690 (stop_helper_session) and :1200 (command_stop). I found an additional path the critic missed: session-start launches main.py, whose setup_logging() at /Users/patrikeriksson/Documents/cinemate/cinemate/src/main.py:563-567 globs `*.log` in /home/pi/cinemate/src/logs/ and os.remove()s each, so the persistent system.log mirror (logger.py:145, DEFAULT_LOG_DIR=/home/pi/cinemate/src/logs) is destroyed too. Log volatility is real and doubly confirmed.

WHY THE FINDING STILL FAILS:

1. The ordering assertion is correct — the critic's "before" is inverted. Destr

**R12** [executability] "'Higher 12-bit resolutions' = the two largest 12-bit modes of the attached sensor, plus — if any 12-bit mode supports ≥ 25 fps — one mid-resolution mode at 25 fps." (0.2: give each a letter A/B/C.)

> Why refuted: The critic's central inference is falsified by the runbook's own data, and the two failure cases it describes are already handled in the document.

1. WRONG DATA SOURCE — this is fatal to the finding. The critic derives mode COUNTS from `resources/sensors.json` and asserts "those are sensor-physical." They are not. `/Users/patrikeriksson/Documents/cinemate/cinemate/src/module/sensor_detect.py` builds the live table purely by regex-parsing `cinepi-raw --list-cameras` stdout (`_list_cameras`, lines 467-479; the parser at lines 237-296 reads width/height from `(\d+)x(\d+)`, bit depth from `'(?:SRGGB|R|GREY|Y)(\d+)`, fps from `\[(\d+\.?\d*) fps`), and merges a second `--hdr sensor` run. sensors.json is consulted only for per-mode metadata enrichment (`_mode_from_metadata_or_detected`) and packing/file-size — never for the mode count.

The proof is inside the runbook itself. sensors.json list

**R13** [executability] Ground rule 6: "`PI_PASSWORD` lives only in the environment, never in any file you write."

> Why refuted: The critic's textual observation is correct but every consequence it rests on is falsified against the real sources, and the proposed fix contradicts the governing contract.

WHAT IS TRUE: RUNBOOK.md:47 states only the secrecy rule, and neither the runbook nor `~/.claude/skills/cinemate-dev/SKILL.md` (line 98, same secrecy-only wording) tells the session to verify `PI_PASSWORD` is set. That is the whole of the accurate part.

CLAIM C (load-bearing): "`build_best_effort_service_stop_lines` silently SKIPS stopping `cinemate-autostart` ... producing exactly the `bindSocket() failed - Error Code: 98`". Falsified three independent ways:

1. The skip branch does not fire on this Pi. cinemate_dev.py:551 gates on `sudo -n true`. The project's own installer documents this exact hardware: cinemate-install.sh:220-226 says the hang was "observed ... on a stock Raspberry Pi OS image where the pi user

