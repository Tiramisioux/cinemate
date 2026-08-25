# C1 results (formerly B15) — long-take stability (5/10-minute takes, higher 12-bit modes)

Ledger for the C1 campaign. Protocol and all definitions: `RUNBOOK.md` (same
directory). Filled by the Sonnet session; reviewed in the Fable thread at each STOP gate.
Rules: append-per-phase, never rewrite a filled row, every number carries its source command.

Status: **NOT STARTED** — update this line as phases complete.

- [ ] Phase 0 preflight
- [ ] Stage 1 — 5-minute takes
- [ ] STOP GATE 1 — Fable review done (date, verdict)
- [ ] Stage 2 — 10-minute takes
- [ ] STOP GATE 2 — final Fable review (date, verdict)

---

## Phase 0 — preflight

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

| Mode | bytes/frame (measured) | test fps | data rate MB/s | frames 5 min | take size GB | free needed GB | feasible? |
|---|---|---|---|---|---|---|---|
| A | | | | | | | |
| B | | | | | | | |
| C | | | | | | | |

Storage: source/fstype — · free bytes — · sustained write (dd ×2, lower): — MB/s

### 0.6 Audio preflight

| Check | Result | Source |
|---|---|---|
| Mic present | | `arecord -l` |
| `getcap` on cinepi-audio-capture | | |
| rtprio 80 on core 3 during take | | `ps -eLo …` |
| No dng-enc/dng-dsk on core 3 | | `ps -eLo …` |
| Intervention applied? (setcap) | | |

### 0.7–0.8 RAM runway + thermals

| Mode | `buffer_size` | runway s at test fps |
|---|---|---|
| A | | |
| B | | |
| C | | |

Idle temp: — · `get_throttled` at idle: —

### 0.10 Predictions (write BEFORE Stage 1)

| Mode × stage | Predicted class | Predicted audio | Reasoning (one sentence, cite 0.3–0.7 numbers) |
|---|---|---|---|
| A × S1 | | | |
| B × S1 | | | |
| C × S1 | | | |

Config interventions log (each: what, why, when, reversible-how):

- (none yet)

---

## Stage 1 — 5-minute takes

One row per take. Class + audio verdict definitions: runbook "Outcome classes".

| Take | Mode | fps | frames req | DNGs on disk | seq gaps | missing_frame_count | warnings in log | class | WAV Δ (ms) | xruns | audio | buffer max / shape | temp max | verdict vs prediction |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1-C1 | | | | | | | | | | | | | | |
| S1-C2 | | | | | | | | | | | | | | |
| S1-C3 | | | | | | | | | | | | | | |
| S1-B1 | | | | | | | | | | | | | | |
| S1-B2 | | | | | | | | | | | | | | |
| S1-B3 | | | | | | | | | | | | | | |
| S1-A1 | | | | | | | | | | | | | | |
| S1-A2 | | | | | | | | | | | | | | |
| S1-A3 | | | | | | | | | | | | | | |

Per-take notes (short; archive paths under `development/pi-test-takes/c1/<take-id>/`):

- S1-C1: —

### Stage 1 summary block (for the Fable review — fill at STOP GATE 1)

**Per-mode outcome:**

| Mode | takes clean / total | frames lost total | worst audio Δ | limiting factor (one line) |
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

Predictions (written/re-confirmed after the Stage 1 review, before the first S2 take):

| Mode × stage | Predicted class | Predicted audio | Reasoning |
|---|---|---|---|
| A × S2 | | | |
| B × S2 | | | |
| C × S2 | | | |

| Take | Mode | fps | frames req | DNGs on disk | seq gaps | missing_frame_count | warnings in log | class | WAV Δ (ms) | xruns | audio | buffer max / shape | temp max | verdict vs prediction |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S2-C1 | | | | | | | | | | | | | | |
| S2-C2 | | | | | | | | | | | | | | |
| S2-B1 | | | | | | | | | | | | | | |
| S2-B2 | | | | | | | | | | | | | | |
| S2-A1 | | | | | | | | | | | | | | |
| S2-A2 | | | | | | | | | | | | | | |

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
