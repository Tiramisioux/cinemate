# C1 results (formerly B15) — long-take stability (5/10-minute takes, higher 12-bit modes)

Ledger for the C1 campaign. Protocol and all definitions: `RUNBOOK.md` (same
directory). Filled by the Sonnet session; reviewed in the Fable thread at each STOP gate.
Rules: append-per-phase, never rewrite a filled row, every number carries its source command.

Pre-flight verification of the runbook (2026-08-26, before any Pi time):
`VERIFICATION-2026-08-26.md` — blockers and the confirmed major defects fixed, minor tier
partly open.

Every cell below has a collection instruction in `RUNBOOK.md`. If a cell has no number
because the step could not run, write why — never leave it looking unfilled.

Status: **NOT STARTED** — update this line as phases complete.

- [ ] Phase 0 preflight
- [ ] Stage 1 — 5-minute takes
- [ ] STOP GATE 1 — Fable review done (date, verdict)
- [ ] Stage 2 — 10-minute takes
- [ ] STOP GATE 2 — final Fable review (date, verdict)

---

## Phase 0 — preflight

Run order is **0.1 → 0.2 → 0.2b → 0.4 → 0.3 → 0.5 → 0.6 → 0.7 → 0.8 → 0.9 → 0.10** (runbook
execution-order note). Fill each block when its step runs, not in section order.

### 0.1 Session + repo state

| Item | Value | Source |
|---|---|---|
| Pi cinemate branch @ commit | | `sync-status` |
| Pi cinepi-raw branch @ commit | | `sync-status` |
| Local ledger branch @ commit | | `git log -1` |
| Helper readiness | | `status --write-report` |
| Date / session start | | |

### 0.2 Sensor + selected modes

Detected sensor: — · Full 12-bit mode table (as reported live):

```
(paste)
```

| Mode | Resolution | Sensor fps_max | Redis index `<n>` | Readback W×H×bits |
|---|---|---|---|---|
| A | | | | |
| B | | | | |
| C (25 fps control) | | | | |

### 0.3–0.5 Measured rates + feasibility

`bytes/frame` is measured on a mid-take DNG of that mode's 25-frame validation take.
Provisional fps (0.3) = `min(floor(0.95 × sensor fps_max), 25)`; it exists only to make the
mode record. Test fps planned = the 0.5 formula. **Test fps applied = the Redis `fps`
readback after `set fps free 1`** — every downstream number uses the applied value.

| Mode | bytes/frame (measured) | provisional fps (0.3) | test fps planned (0.5) | test fps applied (readback) | data rate MB/s | frames 5 min | take size GB | free needed GB | feasible? | 0.3 validation (rec accepted / WAV present / 25 DNGs seq-continuous) |
|---|---|---|---|---|---|---|---|---|---|---|
| A | | | | | | | | | | |
| B | | | | | | | | | | |
| C | | | | | | | | | | |

If planned ≠ applied for any mode, stop and report before Stage 1 — a snapped fps invalidates
the take (runbook "Known context").

### 0.4 Storage identity + sustained write

| Item | Value | Source |
|---|---|---|
| `/media/RAW` source / fstype | | `findmnt -no SOURCE,FSTYPE /media/RAW` |
| Drive model | | `cat /sys/block/<dev>/device/model` |
| Free bytes | | `df -B1 /media/RAW` |
| dd run 1 MB/s | | `dd … bs=4M count=1024 oflag=direct conv=fsync` |
| dd run 2 MB/s | | same |
| dd run 3 MB/s (only if runs 1–2 differ > 25 %) | | same |
| **Sustained MB/s used downstream** (lower of the runs) | | |
| Runs differ > 25 %? (itself a finding) | | |

Caveats recorded alongside the number (runbook 0.4): 4 GiB of zeros may sit inside an SSD's
SLC cache and overstate sustained speed; `oflag=direct` bypasses the page cache while the real
DNG writer does not. Treat the figure as an optimistic ceiling: —

### 0.6 Audio preflight

| Check | Result | Source |
|---|---|---|
| Mic present | | `arecord -l` |
| Resolved helper path | | `readlink -f /proc/$(pgrep -f cinepi-audio-capture \| head -1)/exe` |
| `getcap` on that path (record only, not the decider) | | `getcap <path>` |
| limits.d grant `@audio - rtprio 80` | | `cat /etc/security/limits.d/cinemate-audio.conf` |
| `pi` in `audio` group | | `id pi` |
| Capture thread `rtprio` / `psr` during a 0.3 take | | `ps -eLo pid,comm,rtprio,psr` |
| Thread names seen verbatim (`comm` truncates at 15 chars) | | same |
| Encode/disk worker sharing the audio core? | | same |
| SCHED_FIFO / permission line in session log | | session log |
| Intervention applied? (what / when / how reversed) | | |

Raw `ps` output, verbatim, if any worker shares the audio core:

```
(paste)
```

An encode/disk worker on the audio core is a **finding, not a fix**: record it, flag every
later audio verdict as confounded, and raise it at STOP GATE 1.

### 0.7–0.9 RAM runway, thermals, instrumentation

Board RAM measured, not assumed. `MemTotal` (`free -b`): — · this is the figure every RAM
prediction in 0.10 must cite.

`buffer_size` is published once per encoder setup, at the first recorded frame — read it
during or right after that mode's 0.3 validation take and say which take it came from.

| Mode | MemAvailable at read | `buffer_size` (frames) | read from which take | runway_s = buffer_size / fps |
|---|---|---|---|---|
| A | | | | |
| B | | | | |
| C | | | | |

Any mode under ~2 s of runway (flag it in 0.10): —

Idle temp: — · `get_throttled` at idle: — · not `0x0` ⇒ flag, under-voltage invalidates
everything downstream.

0.9 instrumentation: `command -v exiftool` → — · `df -h /tmp` filesystem → — · `/tmp` on tmpfs
is a confound for buffer-pressure readings, note it here: —

### 0.10 Predictions (write BEFORE Stage 1 — Stage 1 rows only)

One row per selected mode. Stage 2's predictions are a separate table, filled after the Gate 1
review. If no 25 fps control mode was selected in 0.2, mark row C `n/a`.

| Mode × stage | Predicted class | Predicted audio | Data rate within 15 % of sustained? | Expected watchdog (required when yes) | Reasoning (one sentence, cite 0.3–0.7 numbers incl. the 0.7 RAM figure) |
|---|---|---|---|---|---|
| A × S1 | | | | | |
| B × S1 | | | | | |
| C × S1 | | | | | |

Expected watchdog must be one of: write-backlog 90 %, system RAM 80 %, encoder pool.

Config interventions log (each: what, why, when, how to reverse, re-verified?):

- (none yet)

---

## Stage 1 — 5-minute takes

One row per take. Class + audio verdict definitions: runbook "Outcome classes". Classes are
`COMPLETE-CLEAN`, `COMPLETE-WITH-LOSS`, `AUTO-STOP-GUARD`, `ABORTED-OTHER` — for
`AUTO-STOP-GUARD`, name the guard and quote its log line in the note.

| Take | Mode | fps target | `set fps free 1`? | fps readback | res readback OK? | frames req | DNGs on disk | seq gaps (missing_indices / first–last idx) | missing_frame_count | warnings in log (hit count; verbatim in note) | class (name the guard if AUTO-STOP-GUARD) | WAV Δ (ms) | padding lines / total silence ms | audio | buffer max / shape | temp max (sampler CSV) | verdict vs prediction |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1-C1 | | | | | | | | | | | | | | | | | |
| S1-C2 | | | | | | | | | | | | | | | | | |
| S1-C3 | | | | | | | | | | | | | | | | | |
| S1-B1 | | | | | | | | | | | | | | | | | |
| S1-B2 | | | | | | | | | | | | | | | | | |
| S1-B3 | | | | | | | | | | | | | | | | | |
| S1-A1 | | | | | | | | | | | | | | | | | |
| S1-A2 | | | | | | | | | | | | | | | | | |
| S1-A3 | | | | | | | | | | | | | | | | | |

Per-take notes (short; archive paths under `development/pi-test-takes/c1/<take-id>/`). Each
note carries: outcome class, audio verdict, buffer-pressure shape, the step-10 grep hits
verbatim (or "none"), the guard's log line if the take auto-stopped, and verdict vs
prediction. The full log stays in the archive's `session-log.txt`.

- S1-C1: —

### Stage 1 summary block (for the Fable review — fill at STOP GATE 1)

**Per-mode outcome:**

| Mode | takes clean / total | frames lost total (Σ `missing_frame_count`) | worst audio Δ | limiting factor (one line) |
|---|---|---|---|---|
| A | | | | |
| B | | | | |
| C | | | | |

**Sampler-curve narrative** (the three most informative curves, in words — shape, when
pressure started, what it correlates with):

—

**Prediction verdicts:** (CONFIRMED / CONTRADICTED each, one line why)

—

**Ranked hypotheses for every observed loss or sync deviation** (mechanism → evidence →
what would falsify it):

1. —

**Open questions for the Fable review:**

1. —

STOP GATE 1 sign-off: reviewed in Fable thread on — · outcome: — · fixes merged before
Stage 2: —

---

## Stage 2 — 10-minute takes

Preconditions recorded: operator go on — · Pi updated to (commits): — · rebuild done: —

Feasibility recompute for 10-minute takes (`frames_10min = applied fps × 600` — recompute per
runbook Stage 2; do not carry the Phase 0 5-minute numbers over):

| Mode | test fps applied | frames 10 min | take size GB | free needed GB | free at check GB | feasible? |
|---|---|---|---|---|---|---|
| A | | | | | | |
| B | | | | | | |
| C | | | | | | |

Predictions (written/re-confirmed after the Stage 1 review, before the first S2 take):

| Mode × stage | Predicted class | Predicted audio | Data rate within 15 % of sustained? | Expected watchdog (required when yes) | Reasoning (one sentence, cite 0.3–0.7 numbers incl. the 0.7 RAM figure) |
|---|---|---|---|---|---|
| A × S2 | | | | | |
| B × S2 | | | | | |
| C × S2 | | | | | |

| Take | Mode | fps target | `set fps free 1`? | fps readback | res readback OK? | frames req | DNGs on disk | seq gaps (missing_indices / first–last idx) | missing_frame_count | warnings in log (hit count; verbatim in note) | class (name the guard if AUTO-STOP-GUARD) | WAV Δ (ms) | padding lines / total silence ms | audio | buffer max / shape | temp max (sampler CSV) | verdict vs prediction |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S2-C1 | | | | | | | | | | | | | | | | | |
| S2-C2 | | | | | | | | | | | | | | | | | |
| S2-B1 | | | | | | | | | | | | | | | | | |
| S2-B2 | | | | | | | | | | | | | | | | | |
| S2-A1 | | | | | | | | | | | | | | | | | |
| S2-A2 | | | | | | | | | | | | | | | | | |

Per-take notes (short; archive paths under `development/pi-test-takes/c1/<take-id>/`), same
content as Stage 1's notes:

- S2-C1: —

Skipped modes + why: —

### Stage 2 summary block + campaign conclusion (fill at STOP GATE 2)

| Mode | drop-frame goal met? | audio-sync goal met? | single limiting factor |
|---|---|---|---|
| A | | | |
| B | | | |
| C | | | |

**Proposed `cinemate-handbook/lessons/hardware-log.md` entries** (drafted, NOT pushed —
Tested / Worked / Did not work / Why / Confirmed by):

—

STOP GATE 2 sign-off: reviewed in Fable thread on — · outcome: —
