# C1 — Long-take stability runbook (the Sonnet session prompt)

This file IS the prompt for the Sonnet session that runs batch C1. The operator launches a
Claude Code session with **model = Sonnet**, working directory
`/Users/patrikeriksson/Documents/cinemate`, and gives it this instruction:

> Invoke the `/cinemate-dev` skill, then open
> `cinemate/dev-track/C1-longtake-stability/RUNBOOK.md` on branch `feature/dev-track`
> and execute it exactly. Start at Phase 0. Stop at every STOP gate.

Everything below is addressed to that Sonnet session.

---

## Who you are and what this is

You are running batch **C1** (formerly B15) of the CineMate development track (`dev-track/` — its
`README.md` explains how the track relates to the system review): a staged, instrumented
live-test campaign on the dev Pi (`pi@cinepi.local`) whose goal is to **eliminate dropped
frames and keep audio in sync on long takes at the higher 12-bit resolutions**.

Non-negotiable ground rules:

1. **Invoke the `/cinemate-dev` skill first** if you have not already. Read
   `cinemate-handbook/README.md`, `cinemate-handbook/working/hardware-session.md`, and
   `cinemate-handbook/lessons/hardware-log.md` before touching the Pi. The hardware-session
   method binds every phase here: state the **prediction before running**, record the
   **verdict after** (CONFIRMED / CONTRADICTED), never the verdict alone.
2. **This is a measurement campaign, not a fix session.** No source-code changes in
   `cinemate` or `cinepi-raw` during a stage. The only permitted interventions are
   configuration-level corrections when a Phase 0 preflight check fails against its
   documented invariant (e.g. a missing `setcap`), and each one must be logged in the ledger
   before you apply it. Fixes to code are decided at the STOP-gate reviews in the Fable
   thread, not by you mid-stage.
3. **All bookkeeping goes to `cinemate/dev-track/C1-longtake-stability/RESULTS.md`** on the
   local branch `feature/dev-track` (cinemate repo). Commit after every phase and every take
   batch. **Never `git add -A` in this repo** (LFS pointer trap) — add the named files only:
   `git add dev-track/C1-longtake-stability/RESULTS.md` (plus any file you deliberately
   created). Do not push without asking the operator.
4. **The Pi's repos stay on `dev`.** You do not switch branches on the Pi. Record the exact
   Pi-side commits in the ledger during preflight. The local
   `feature/dev-track` branch is bookkeeping only.
5. **STOP gates are hard stops.** After Stage 1 (5-minute takes) you write the summary block,
   commit, tell the operator it is ready for review in the Fable thread, and end your turn.
   Stage 2 (10-minute takes) only starts when the operator explicitly says the Fable review
   is done and Stage 2 is a go. Same again after Stage 2.
6. `PI_PASSWORD` lives only in the environment, never in any file you write.

## Known context you must carry in (do not re-derive, do verify)

- The dev Pi is a **2 GB CM5 Lite**. The DNG encoder's RAM buffer is small on this unit and
  the **80 % RAM guard force-stops recording** when the write backlog fills it. A RAM-guard
  auto-stop is a *distinct outcome class* (drive can't sustain the data rate), not a
  drop-frame bug — classify it as such, never as "dropped frames".
- As of the 2026-08-25 Pi session, the attached sensor was an **imx477**, storage was an
  **NVMe with `LABEL=RAW` directly on `/dev/nvme0n1` (no partition table)**, and the measured
  12-bit mode table was:
  `1332x990@101.68 · 2028x1080@62.81 · 2028x1520@45.19 · 4056x2160@16.39 · 4056x3040@11.72`.
  **Verify all of this live in Phase 0** — do not assume it survived the week.
- "Higher 12-bit resolutions" for this campaign = the **two largest 12-bit modes** of the
  attached sensor, plus — if any 12-bit mode supports ≥ 25 fps — **one mid-resolution mode at
  25 fps** as the production-realistic control. For imx477 that means 4056x3040, 4056x2160,
  and 2028x1520@25.
- `SensorDetect` renumbers resolution indices **per process**. Never trust a cached
  `set resolution <n>` index: set it, then read back `resolution_target_width`,
  `resolution_target_height`, `resolution_target_bit_depth` from Redis and record all three.
- Historical audio-drift root cause on this stack: **ALSA capture xruns from storage
  contention**, not clock drift (the RØDE 24-bit clock measured ~0 ppm). The ext4
  disk-worker/audio-core collision is fixed; `cinepi-audio-capture` pins itself to the last
  CPU core (core 3 on this 4-core unit) at SCHED_FIFO 80. A **pending item from that fix
  chain: the SCHED_FIFO `setcap` may never have been applied on this Pi** — Phase 0 checks it.
- From the 2026-08-25 Fable storage review (context for what you're instrumenting, not tasks):
  there is **no end-of-take durability barrier** (`write()` success ≠ on media; data can sit
  dirty in the page cache after `is_writing_buf` clears), the "DNG written" log line prints
  *before* the write and even on failure (don't trust it as evidence), and storage pre-roll
  runs at session start (leave `auto_preroll` exactly as configured — changing it mid-campaign
  confounds the comparison).
- `fps_actual` has a known dead-emit history. Log it, but derive real frame rate from
  `framecount` deltas in your sampler, not from `fps_actual`.
- Web GUI is port **5000**; port **8000** is cinepi-raw's MJPEG preview. If cinepi-raw logs
  `bindSocket() failed - Error Code: 98`, suspect a stale process on 8000 (see
  the workspace contract in the skill for the confirmed causes).
- If `systemctl restart cinemate-autostart` hangs and the unit lands in `failed`:
  `systemctl reset-failed` then `start`.

## Tools you drive

- Deterministic helper: `~/.claude/skills/cinemate-dev/scripts/cinemate_dev.py`
  (`stop`, `session-start`, `session-send "<cmd>"`, `session-tail <n>`, `session-stop`,
  `status --write-report`, `sync-status --repo <repo>`). Use the **explicit session
  commands**, not `roundtrip-take` — these takes are far too long and too large for the
  convenience wrapper's copy step.
- Media analyzer: `~/.claude/skills/cinemate-dev/scripts/analyze_cinepi_media.py`. It is
  stdlib-only — **scp it to the Pi** (`/home/pi/c1/`) and run it there, directly against
  `/media/RAW/<take>`; full takes are 30–70 GB and must never be copied to the Mac.
- Archive root on the Mac:
  `/Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/c1/<take-id>/` —
  per-take analysis JSON, sampler CSV, session-log excerpt, the WAV, and first/last 3 DNGs.
  Nothing larger.
- Prior sync-analysis method: check
  `/Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/` for the sync-matrix
  notes from the audio-sync campaign (`sync-matrix.md`, possibly under a phase subfolder). If
  a WAV fails the coarse sync check, use that method for the deep dive before inventing one.

## Instrumentation (install once in Phase 0)

Create `/home/pi/c1/c1_sampler.sh` on the Pi, verbatim:

```bash
#!/bin/bash
# c1_sampler.sh OUTFILE — 2 s cadence recorder-state sampler. Stop with: kill $(cat /tmp/c1_sampler.pid)
OUT="$1"
echo $$ > /tmp/c1_sampler.pid
g() { redis-cli GET "$1" 2>/dev/null | head -c 32; }
echo "ts,buffer,buffer_size,framecount,fps_actual,is_writing_buf,write_speed_to_drive,space_left,memory_alert,dirty_kb,writeback_kb,temp,throttled" >> "$OUT"
while true; do
  d=$(awk '/^Dirty:/{a=$2} /^Writeback:/{b=$2} END{print a","b}' /proc/meminfo)
  t=$(vcgencmd measure_temp | tr -d "temp='C")
  th=$(vcgencmd get_throttled | cut -d= -f2)
  echo "$(date +%s),$(g buffer),$(g buffer_size),$(g framecount),$(g fps_actual),$(g is_writing_buf),$(g write_speed_to_drive),$(g space_left),$(g memory_alert),$d,$t,$th" >> "$OUT"
  sleep 2
done
```

Start it right before each `rec`, stop it after the post-take flush. One CSV per take:
`/home/pi/c1/samples/<take-id>.csv`.

WAV duration check (on the Pi, stdlib):

```bash
python3 - "$WAV" <<'EOF'
import sys, wave
w = wave.open(sys.argv[1], 'rb')
print(f"frames={w.getnframes()} rate={w.getframerate()} ch={w.getnchannels()} "
      f"sampwidth={w.getsampwidth()} duration_s={w.getnframes()/w.getframerate():.6f}")
EOF
```

## Outcome classes and pass thresholds (fixed for the whole campaign)

Every take gets exactly one outcome class:

| Class | Definition |
|---|---|
| `COMPLETE-CLEAN` | Stopped at the requested frame count; DNG count == requested; no filename-sequence gaps; `missing_frame_count` == 0; no write-failure or drop/sync warnings in the session log |
| `COMPLETE-WITH-LOSS` | Reached the requested count / duration but any of the above is violated |
| `AUTO-STOP-RAM-GUARD` | cinepi-raw force-stopped the take on the RAM guard (session log says so, or `memory_alert` fired and recording ended early) |
| `ABORTED-OTHER` | Anything else (crash, storage yank, operator abort) — attach the evidence |

Audio verdict per take (independent of the class above):

- **PASS** — WAV present; `|wav_duration − dng_count/fps_target| ≤ 0.5 frame period`; zero
  xrun/overrun lines in the session log for the take window.
- **WARN** — deviation ≤ 1 frame period, or 1–2 xrun lines with no audible-scale loss.
- **FAIL** — deviation > 1 frame period, any WAV discontinuity, or missing WAV.
  On FAIL, run the sync-matrix deep-dive method before writing the verdict.

If the coarse deviation is dominated by sensor-vs-target fps offset, recompute against
`dng_count × mean_frame_interval` using the DNG timestamps from the analyzer JSON, and record
both numbers.

Buffer-pressure note per take (early-warning even when nothing drops): max `buffer` sample,
and whether the curve is flat, sawtooth, or monotonically climbing. A monotonic climb that
didn't hit the guard yet = the mode is over the drive's sustained rate; say so.

---

## Phase 0 — Preflight (no long recordings)

Ledger: fill the Phase 0 tables in `RESULTS.md` as you go; commit when the phase is done.

0.1 **Session + repo state.** `cinemate_dev.py stop`, then `status --write-report`, then
`sync-status` for both repos. Record: Pi-side `cinemate` and `cinepi-raw` branches + commits,
local branch, helper readiness. Both Pi repos must be on `dev`; if not, STOP and report —
do not switch them yourself.

0.2 **Sensor + mode table.** `session-start`, wait for `Storage pre-roll complete` in
`/tmp/cinemate_cli.log`, +1 s. From the session log / Redis, record the detected sensor and
the full 12-bit mode list with fps caps. Select the test modes per the rule above and give
each a letter: **A** = largest 12-bit, **B** = second-largest 12-bit, **C** = 25 fps control
(if available).

0.3 **Mode validation + measured bytes/frame.** For each selected mode: `set resolution <n>`,
read back `resolution_target_width/height/bit_depth`, set the test fps (rule in 0.5), then
`rec f 25`, wait for `Stopped recording`, and record: actual DNG file size (`stat -c%s` on one
mid-take DNG), WAV presence, and that the 25 DNGs are sequence-continuous. **Measured
bytes/frame × test fps = the mode's data rate.** Delete each 25-frame validation take after
recording its numbers.

0.4 **Storage identity + sustained write speed.** `findmnt -no SOURCE,FSTYPE /media/RAW`
(expect the NVMe, ext4), `df -B1 /media/RAW`. Sustained speed:
`dd if=/dev/zero of=/media/RAW/c1_speedtest bs=4M count=1024 oflag=direct conv=fsync status=progress`
then delete the file. Run it twice, keep the lower number. Record MB/s.

0.5 **Per-mode fps + feasibility.** Test fps for each mode =
`min( highest integer ≤ 0.95 × sensor fps_max , highest integer with data-rate ≤ 0.85 × sustained MB/s , 25 )`.
Then per mode: `frames_5min = fps × 300`, take size = frames × bytes/frame, and required free
space = take size × 1.2. If a mode cannot fit or cannot stay under the storage cap at any
usable fps, record it as `INFEASIBLE-ON-THIS-RIG` with the arithmetic — that is a finding,
not a failure.

0.6 **Audio preflight.** `arecord -l` (mic must be present — if absent, STOP and ask the
operator to attach it). `getcap $(command -v cinepi-audio-capture)`. During one of the 0.3
validation takes: `ps -eLo pid,comm,rtprio,psr | grep -Ei 'audio|dng-'` — verify
`cinepi-audio-capture` at `rtprio` 80 on core 3, and **no `dng-enc`/`dng-dsk` thread on
core 3**. If SCHED_FIFO is not active (rtprio `-`), that is the known pending `setcap` item:
log it in the ledger, apply the documented fix
(`sudo setcap cap_sys_nice+ep <path-to-cinepi-audio-capture>`), restart the session, and
re-verify. This is the one sanctioned config intervention.

0.7 **RAM runway.** `free -b`; after setting each mode, read `buffer_size` from Redis and
record `runway_s = buffer_size / fps` — how long a full disk stall can last before the RAM
guard ends the take.

0.8 **Thermals.** `vcgencmd measure_temp` and `vcgencmd get_throttled` at idle. If
`get_throttled` ≠ `0x0` at rest, record it and flag — under-voltage invalidates everything
downstream.

0.9 **Install instrumentation.** `mkdir -p /home/pi/c1/samples /home/pi/c1/results`; scp
`c1_sampler.sh` (chmod +x) and `analyze_cinepi_media.py` to `/home/pi/c1/`.

0.10 **Predictions — written before Stage 1 starts.** One row per (mode × stage): predicted
outcome class + audio verdict, with one sentence of reasoning anchored in the 0.3–0.7
numbers. The 2 GB RAM-guard confound must appear explicitly in the reasoning for any mode
whose data rate is within 15 % of the sustained speed.

`session-stop`. Commit the ledger (`plan/results only, named files`).

**Phase 0 STOP-check (not a gate):** if any of 0.1–0.9 contradicts the "known context"
section in a way that changes the test design (different sensor, exFAT instead of ext4,
missing mic, throttling at idle), report to the operator and wait before Stage 1.

---

## Stage 1 — three 5-minute takes per mode

Take IDs: `S1-<mode-letter><rep>` (e.g. `S1-A1`, `S1-A2`, `S1-A3`, `S1-B1`, …).

Per-take procedure (identical every time):

1. `session-start` → wait for `Storage pre-roll complete` → +1 s.
2. Set the mode: `set resolution <n>` → verify the three `resolution_target_*` readbacks
   match the plan (renumbering gotcha — re-check every session).
3. Set fps to the mode's test fps; confirm rate via two `framecount` samples ~10 s apart
   during the take (step 6), not via `fps_actual`.
4. Pre-take snapshot: `df -B1 /media/RAW` free bytes; `vcgencmd measure_temp`; confirm free
   space ≥ required (0.5); if temp > 70 °C, cool down before starting.
5. Start the sampler:
   `nohup /home/pi/c1/c1_sampler.sh /home/pi/c1/samples/<take-id>.csv >/dev/null 2>&1 &`
6. `session-send "rec f <frames_5min>"`. Poll `session-tail 100` every 60 s. The take must
   stop itself at the frame count. Do not send anything else to the session while recording.
7. After `Stopped recording`: poll Redis until `is_writing` = 0 **and** `is_writing_buf` = 0.
   Then stop the sampler (`kill $(cat /tmp/c1_sampler.pid)`).
8. Evidence capture, per take, before anything is deleted:
   - `session-tail 400` → save to the archive as `session-log.txt`; separately grep the take
     window for `write.*fail|FAILED|xrun|overrun|drop|SYNC|memory` (case-insensitive) and
     record every hit in the ledger.
   - Redis: `framecount`, `missing_frame_count`, `drop_frame_during_last_take`,
     `memory_alert`, `last_dng_cam0`.
   - `dmesg | tail -150` → append any storage/USB/ALSA lines to the archive.
   - On-Pi analysis: `python3 /home/pi/c1/analyze_cinepi_media.py /media/RAW/<take-dir> --json > /home/pi/c1/results/<take-id>.json`.
   - WAV duration check (snippet above) on the take's WAV.
9. Archive to the Mac (`development/pi-test-takes/c1/<take-id>/`): the analyzer JSON, the
   sampler CSV, `session-log.txt`, the WAV, and the first 3 + last 3 DNGs. Verify the copies
   are non-empty and the JSON parses.
10. **Only then** delete the take: `rm -rf /media/RAW/<exact-take-dir>` — the named directory
    only, never a wildcard.
11. Ledger: one row in the Stage 1 table + a short per-take note (outcome class, audio
    verdict, buffer-pressure shape, verdict vs prediction). Commit after each mode's three
    reps.

Sequencing rules:

- Run order: C (control, if present) → B → A, three reps each, so the easiest mode
  establishes the healthy baseline shape of the sampler curves first.
- If rep 1 of a mode is `AUTO-STOP-RAM-GUARD` or loses > 1 % of frames: run exactly one
  confirming rep, write the diagnosis, and move to the next mode — don't burn the third rep
  on a reproduced failure.
- Between takes: wait for temp < 70 °C and `Dirty` in `/proc/meminfo` back under ~50 MB.
- If a session dies mid-take, classify `ABORTED-OTHER`, capture logs, `cinemate_dev.py stop`,
  and restart the sequence at the same rep once.

### STOP GATE 1 — Fable review

When all Stage 1 takes are done: fill in the **Stage 1 summary block** in `RESULTS.md`
(the template is there — per-mode table, the three worst sampler curves described in words,
every prediction verdict, and your ranked hypothesis list for any loss or sync deviation
observed). Commit. Then tell the operator, verbatim enough to paste:

> Stage 1 complete. `dev-track/C1-longtake-stability/RESULTS.md` on `feature/dev-track` has
> the summary block. Take it to the Fable thread for review; Stage 2 (10-minute takes) will
> not start until you tell me the review is done and what, if anything, changed.

Then **end your turn**. Do not begin Stage 2 in the same turn under any circumstances.

---

## Stage 2 — two 10-minute takes per mode (gated on the Fable review)

Preconditions: operator has explicitly said "Stage 2 go", and has told you whether any fixes
were merged to `dev` from the Stage 1 review. If fixes were merged: update the Pi per the
standard sync contract (operator-run or agent-run per their instruction), rebuild
(`cinemate_dev.py build-raw` if cinepi-raw changed), and record the new commits in the ledger
— Stage 2 then doubles as the fix re-verification.

Protocol = Stage 1's per-take procedure with:

- `frames_10min = fps × 600`; recompute the space feasibility (take sizes double; a mode that
  fit in Stage 1 may not fit now — recompute, don't assume).
- Two reps per mode (`S2-A1`, `S2-A2`, …), same run order, same abort rule after rep 1.
- Any mode that was `INFEASIBLE-ON-THIS-RIG` or reproducibly failed in Stage 1 **without** a
  merged fix addressing it: skip, and say why in the ledger — re-running a known failure
  twice as long produces no new information.
- Prediction rows for Stage 2 must be written (or explicitly re-confirmed) **after** the
  Stage 1 review outcomes are known and before the first Stage 2 take.

### STOP GATE 2 — final Fable review

Fill the Stage 2 summary block + the campaign-level conclusion (per mode: is the
drop-frame goal met? is the audio-sync goal met? what is the single limiting factor?).
Draft — but do not push — the `cinemate-handbook/lessons/hardware-log.md` entries for every
operator-confirmable finding, using that file's Tested / Worked / Did not work / Why /
Confirmed by format; list them at the end of the ledger as proposals. Commit everything,
then hand back to the operator for the final Fable-thread review with the same
paste-ready message pattern as Gate 1.

---

## Ledger discipline (applies to every phase)

- `RESULTS.md` is append-per-phase: never rewrite a filled row; corrections get a dated
  strike-through note.
- Every number in the ledger carries its source (command or file), same as the PI-RESULTS
  files this review already uses.
- Commit messages: `c1: <phase/take-ids> — <one-line outcome>` on
  `feature/dev-track`, named files only, no push without asking.
