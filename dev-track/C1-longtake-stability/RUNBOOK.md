# C1 — Long-take stability runbook (the Sonnet session prompt)

This file IS the prompt for the Sonnet session that runs batch C1. The operator launches a
Claude Code session with **model = Sonnet**, working directory
`/Users/patrikeriksson/Documents/cinemate`, and gives it this instruction:

> Invoke the `/cinemate-dev` skill, then open
> `cinemate/dev-track/C1-longtake-stability/RUNBOOK.md` on branch `feature/dev-track`
> and execute it exactly. Start at Phase 0. Stop at every STOP gate.

Everything below is addressed to that Sonnet session.

> **This runbook was adversarially verified on 2026-08-26 before any Pi time**, by seven
> parallel checks against the real sources, each finding then re-verified by a second agent
> instructed to refute it: 49 claims confirmed correct, 59 defects upheld, 13 refuted.
> **The blockers and the confirmed major defects are already fixed in the text below.** The
> full record — every finding, its evidence, its adjudicated fix, and the 13 refuted claims
> nobody should re-raise — is in [`VERIFICATION-2026-08-26.md`](VERIFICATION-2026-08-26.md)
> beside this file. **Remaining unapplied items are the minor tier and the long tail of the
> major tier; work from that file if something here reads ambiguous, and update it when you
> apply one.** Several fixes exist because the original text would have silently produced
> invalid data — notably the fps-snapping trap, the per-frame log volume, and the fact that a
> recovered xrun logs nothing. Do not "simplify" those paragraphs back.

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

- **Measure the board's RAM in 0.7 before reasoning about it — do not assume 2 GB.**
  `cinepi.local` is whichever CM5 is plugged in. It read 2 GB on 2026-08-04, but the
  2026-08-24 Pi session (PI-016) measured **4048 MB, operator-confirmed as the genuine
  current unit**, with available memory never below ~2970 MB at 4056x3040 12-bit. Whatever
  `free -b` says in 0.7 is the number you reason from.
- **Three independent watchdogs can force-stop a take. Never write "the 80 % RAM guard" as
  if it were one thing** — identify which one fired, from its own log line:
  | guard | threshold | owner |
  |---|---|---|
  | write-backlog | `buffer / buffer_size` ≥ **90 %** (`BUFFER_LIMIT_PERCENT`) — checked first, and the direct "about to drop frames" signal | cinemate `cinepi_controller.py` |
  | system RAM | ≥ **80 %** (`RAM_LIMIT_PERCENT`) | cinemate `cinepi_controller.py` |
  | encoder RAM pool | `ram_buffers_ + 2 >= max_ram_buffers_` (`buffer_full()`) | cinepi-raw `dng_encoder` |
  An auto-stop is a *distinct outcome class* (the drive cannot sustain the data rate), never
  a drop-frame bug. Record the guard name and its log line, not just "it stopped".
- **`set fps` SNAPS to the configured steps — it does not take your number.** With
  `arrays.fps.steps = [25, 33, 50]` and `arrays.fps.free = false` (the shipped default in
  `settings.jsonc`), `set_fps` picks the *nearest* step, so `set fps 11` on a mode capped at
  11.72 does **not** give you 11. Before setting any test fps you must issue
  **`set fps free 1`** (free mode rebuilds the table to every integer 1..fps_max), then set
  the number, then **read `fps` back from Redis and confirm it equals your target**. A take
  recorded at a silently snapped fps is invalid data — this is the single most likely way to
  waste a whole stage.
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
- **A recovered xrun logs NOTHING. Do not grep for "xrun".** In
  `cinepi_audio_capture.cpp`, a short read calls `recoverCaptureError()` and, when recovery
  succeeds, simply `continue`s — silently. Only a *failed* recovery prints `Capture read
  failed:`. The observable evidence of lost audio is the **silence-padding line**, emitted
  when the reconciler inserts silence to cover a shortfall:
  `… silent frame(s) to cover a capture shortfall of …`. **That line — not "xrun" — is the
  audio-loss signal for every verdict and grep in this runbook.** Its presence also means the
  WAV was padded back to real time, so duration alone can look perfect while samples were
  lost: always check both.
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
- **Ad-hoc Pi shell and file transfer.** The helper has **no** generic remote-exec and no
  selective file-pull — its only copy command is `copy-latest-take`, which pulls the whole
  take directory (the 30–70 GB you must never copy). Everything in this runbook that is not
  a `cinemate_dev.py` subcommand (`findmnt`, `df`, `dd`, `free`, `ps`, `arecord -l`,
  `getcap`, `vcgencmd`, `dmesg`, `rm -rf`, running the sampler and the analyzer) goes through
  **`~/.claude/skills/cinemate-dev/scripts/pi_ssh.sh '<command>'`**, which uses `PI_PASSWORD`
  from the environment when SSH keys are unavailable. For pulling individual files use
  `pi_expect.exp "$PI_PASSWORD" scp -o StrictHostKeyChecking=accept-new pi@cinepi.local:<src> <dst>`.
- Media analyzer: `~/.claude/skills/cinemate-dev/scripts/analyze_cinepi_media.py`. Its
  **imports** are stdlib-only, so it runs on the Pi's `python3` with no pip install — but it
  shells out to **`exiftool`**, so confirm `command -v exiftool` on the Pi in 0.9 and record
  the answer; without it the DNG-metadata half of the JSON is empty. `scp` it to
  `/home/pi/c1/` and run it there against `/media/RAW/<take>`; full takes are far too large
  to copy to the Mac.
  **It does not produce per-frame timestamps** — it runs `exiftool` on the *first* DNG only
  and stores that single result as `sample_metadata`. Any instruction to derive a mean frame
  interval "from the analyzer JSON" is impossible; see the audio-verdict section for what to
  do instead.
- Archive root on the Mac:
  `/Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/c1/<take-id>/` —
  per-take analysis JSON, sampler CSV, the full session log, the WAV, and first/last 3 DNGs.
  Nothing larger. (The `pi-test-takes/` tree is currently empty apart from `.DS_Store`; that
  is expected — C1 has not run yet. It is the destination, not a source of prior data.)
- **There is no prior sync-matrix file — do not go looking for one.** Earlier sessions'
  `sync-matrix.md` is not present anywhere in the workspace. The audio deep-dive method is
  self-contained and defined in this runbook's audio-verdict section; use it as written.

## Instrumentation (install once in Phase 0)

Create `/home/pi/c1/c1_sampler.sh` on the Pi, verbatim:

```bash
#!/bin/bash
# c1_sampler.sh OUTFILE PIDFILE — 2 s cadence recorder-state sampler.
# Stop with: kill $(cat PIDFILE)
OUT="$1"; PIDF="${2:-/tmp/c1_sampler.pid}"
echo $$ > "$PIDF"
g() { redis-cli GET "$1" 2>/dev/null | head -c 32; }
# Truncate, don't append: one clean CSV per take even if a take-id is retried.
echo "ts,buffer,buffer_size,framecount,fps_actual,is_writing_buf,write_speed_to_drive,space_left,memory_alert,dirty_kb,writeback_kb,temp,throttled" > "$OUT"
while true; do
  d=$(awk '/^Dirty:/{a=$2} /^Writeback:/{b=$2} END{print a","b}' /proc/meminfo)
  t=$(vcgencmd measure_temp | sed 's/[^0-9.]//g')
  th=$(vcgencmd get_throttled | cut -d= -f2)
  echo "$(date +%s),$(g buffer),$(g buffer_size),$(g framecount),$(g fps_actual),$(g is_writing_buf),$(g write_speed_to_drive),$(g space_left),$(g memory_alert),$d,$t,$th" >> "$OUT"
  sleep 2
done
```

Notes on the sampler, all load-bearing:

- It is started with an explicit **per-take pidfile** (`/tmp/c1_<take-id>.pid`) so a stale
  sampler from a previous take can never be the thing you kill — or the thing you leave
  running. Before each start, confirm no sampler is already alive
  (`pgrep -f c1_sampler.sh` must be empty); if one is, kill it and note it in the ledger.
- `sed 's/[^0-9.]//g'` (not `tr -d "temp='C"`): `tr -d` deletes *characters*, and the set
  `temp='C` contains `e`, `m`, `p`, `t` — harmless for the digits, but the `sed` form is
  unambiguous and survives a firmware wording change.
- `date +%s` is whole seconds at a 2 s cadence, so sampler timestamps are ±1 s. That is fine
  for correlating buffer pressure with log events, and **too coarse to derive a frame rate
  from** — use it for shape, not for precision.

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
| `COMPLETE-CLEAN` | Stopped at the requested frame count; DNG count **exactly** == requested; no filename-sequence gaps; `missing_frame_count` == 0; no write-failure, drop/sync, index-gap or silence-padding hits in the **full** session log |
| `COMPLETE-WITH-LOSS` | Reached the requested count / duration but any of the above is violated — **including a DNG count *above* the request** (an overshoot is a real anomaly, not a rounding artifact: say so explicitly rather than letting it read as "loss") |
| `AUTO-STOP-GUARD` | A watchdog force-stopped the take. **Name which one** (write-backlog 90 %, system RAM 80 %, or cinepi-raw's encoder pool) and quote its log line; `memory_alert` alone does not identify the guard |
| `ABORTED-OTHER` | Anything else (crash, storage yank, operator abort) — attach the evidence |

Audio verdict per take (independent of the class above). **Both legs must be checked — a
padded WAV has correct duration and lost samples:**

- **PASS** — WAV present; `|wav_duration − expected_duration| ≤ 0.5 frame period`; **and zero
  silence-padding lines** (`silent frame(s) to cover a capture shortfall`) and zero
  `Capture read failed:` lines in the full session log for the take.
- **WARN** — deviation ≤ 1 frame period, or 1–2 padding lines totalling well under one frame
  period of inserted silence.
- **FAIL** — deviation > 1 frame period, any `Capture read failed:`, padding totalling ≥ one
  frame period, or a missing WAV. On FAIL, do the deep dive below before writing the verdict.

`expected_duration` = `dng_count / fps_target`. **If the sensor's real cadence differs from
`fps_target`** (check the sampler's `framecount` deltas — 2 s cadence, so this is coarse),
recompute against the real cadence and record both numbers. Do **not** try to get a mean
frame interval out of the analyzer JSON; it has no per-frame timestamps. If you need true
per-frame timing, run `exiftool` yourself on the Pi over the first and last DNG of the take
and difference their timestamps — say so in the ledger when you do.

**Audio deep dive (self-contained — there is no external method file).** On FAIL: (1) sum the
inserted silence from every padding line and compare it to the duration deviation — if they
match, the loss is capture-side, not clock drift; (2) correlate each padding line's timestamp
against the sampler CSV's `buffer` column at the same moment — padding that coincides with
buffer pressure is the storage-contention mechanism this campaign exists to measure;
(3) check whether the affected take's disk workers and `cinepi-audio-capture` shared a core
(the 0.6 check), since that collision has caused this before.

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

> **Execution order — the numbering is not the running order.** 0.5's fps rule needs
> bytes/frame (0.3) *and* sustained write speed (0.4), while 0.3 needs an fps to record at.
> Break the circle by running: **0.1 → 0.2 → 0.4 → 0.3 → 0.5 → 0.6 → 0.7 → 0.8 → 0.9 → 0.10**,
> and record 0.3's validation takes at a **provisional** fps of
> `min(floor(0.95 × sensor fps_max), 25)` — bytes/frame does not depend on fps, so the
> provisional value is only used to make the mode record at all. 0.5 then computes the real
> test fps from the measured numbers. If 0.5's answer differs from the provisional value, that
> is expected and needs no re-run of 0.3.

0.3 **Mode validation + measured bytes/frame.** For each selected mode: `set resolution <n>`,
read back `resolution_target_width/height/bit_depth`, set the **provisional** fps (see the
order note above — remember `set fps free 1` first, then read `fps` back), then
`rec f 25`, wait for `Stopped recording`, and record: actual DNG file size (`stat -c%s` on one
mid-take DNG), WAV presence, and that the 25 DNGs are sequence-continuous. **Measured
bytes/frame × test fps = the mode's data rate.** Delete each 25-frame validation take after
recording its numbers.

These validation takes share one session, so they do not get Stage 1's fresh-session
guarantees. Apply the same two guards by hand each time: confirm the previous validation
take's flush finished (`is_writing_buf` = 0 and `buffer` = 0) before starting the next, and
confirm `rec` was actually accepted — a refused `rec` (no storage, still flushing, pre-roll
active) logs and returns silently, so check that `is_recording` went to 1 rather than
assuming it started.

0.4 **Storage identity + sustained write speed.** `findmnt -no SOURCE,FSTYPE /media/RAW`
(expect the NVMe, ext4), `df -B1 /media/RAW`, and identify the drive itself
(`cat /sys/block/<dev>/device/model` where applicable) so the result is attributable to a
specific piece of hardware. Sustained speed:
`dd if=/dev/zero of=/media/RAW/c1_speedtest bs=4M count=1024 oflag=direct conv=fsync status=progress`
then delete the file. Run it **twice and keep the lower number**; if the two runs differ by
more than 25 %, run a third and record all three — a drive whose own speed is unstable makes
every downstream 0.85 × threshold unstable too, and that is itself a finding.

Two caveats to record alongside the number, because the campaign's feasibility maths leans on
it: 4 GiB of zeros may fit inside an SSD's SLC cache and overstate sustained speed (the very
failure mode the exFAT/USB-SSD notes in `storage_profiles.py` describe, which shows up ~90 s
into a real take), and `oflag=direct` bypasses the page cache while the real DNG writer does
**not** use `O_DIRECT`. Treat the dd figure as an optimistic ceiling, not a promise.

0.5 **Per-mode fps + feasibility.** Test fps for each mode =
`min( highest integer ≤ 0.95 × sensor fps_max , highest integer with data-rate ≤ 0.85 × sustained MB/s , 25 )`.
Then per mode: `frames_5min = fps × 300`, take size = frames × bytes/frame, and required free
space = take size × 1.2. If a mode cannot fit or cannot stay under the storage cap at any
usable fps, record it as `INFEASIBLE-ON-THIS-RIG` with the arithmetic — that is a finding,
not a failure.

0.6 **Audio preflight.** `arecord -l` — the mic must be present; if absent, STOP and ask the
operator to attach it.

**The authoritative SCHED_FIFO signal is the running thread's `rtprio`, not `getcap`.**
`getcap` only tells you the grant exists; the process still has to take it. Run `getcap` for
the record, but decide on the live check. `cinepi-audio-capture` is resolved by cinepi-raw as
a sibling of its own binary, so find the real path with
`readlink -f /proc/$(pgrep -f cinepi-audio-capture | head -1)/exe` rather than guessing.

**Both checks run *during* a 0.3 validation take** (nothing is scheduled when idle):
`ps -eLo pid,comm,rtprio,psr | grep -Ei 'audio|dng-'`. Note `comm` is truncated to 15
characters, so match on the prefix, and record the exact thread names you see rather than
assuming `dng-enc`/`dng-dsk`.

1. **`cinepi-audio-capture` at `rtprio` 80.** If it shows `-`, SCHED_FIFO was never granted —
   this is the known pending item. Log it, apply
   `sudo setcap cap_sys_nice+ep <resolved path>`, restart the session, re-verify, and record
   before/after. **This is the one sanctioned config intervention.**
2. **No encode/disk worker sharing the audio core.** If one is co-resident with
   `cinepi-audio-capture`, do **not** fix it — that is a code-level affinity question, not a
   config one. Record it, flag it as a known confound for every audio verdict in the
   campaign, and raise it at STOP GATE 1.

0.7 **Board RAM + encoder runway.** `free -b` — **record `MemTotal`; this is the number the
whole campaign's RAM reasoning rests on, and it is not assumed** (see "Known context").

`buffer_size` is **not a live key**: cinepi-raw publishes it once per encoder setup, at the
**first recorded frame** after that setup. Reading it before any take of a given mode returns
a stale value from the previous mode, or nothing. So read it *during or right after* that
mode's 0.3 validation take, and record which take it came from. Then compute
`runway_s = buffer_size / fps` — the number of seconds of total write stall the frame pool
can absorb before the encoder-pool guard ends the take. Expect single-digit seconds; if it is
under ~2 s for a mode, say so in 0.10, because that mode's result will be dominated by
transient stalls rather than sustained throughput.

0.8 **Thermals.** `vcgencmd measure_temp` and `vcgencmd get_throttled` at idle. If
`get_throttled` ≠ `0x0` at rest, record it and flag — under-voltage invalidates everything
downstream.

0.9 **Install instrumentation.** `mkdir -p /home/pi/c1/samples /home/pi/c1/results`; scp
`c1_sampler.sh` (chmod +x) and `analyze_cinepi_media.py` to `/home/pi/c1/`. Record
`command -v exiftool` (the analyzer shells out to it) and `df -h /tmp` — if `/tmp` is a
tmpfs, the multi-MB session log competes for the same RAM the encoder buffers into, which is
itself a confound worth knowing about before you interpret buffer pressure.

0.10 **Predictions — written before Stage 1 starts.** One row per (mode × stage): predicted
outcome class + audio verdict, with one sentence of reasoning anchored in the 0.3–0.7
numbers. For any mode whose data rate is within 15 % of the measured sustained speed, the
reasoning must name **which** watchdog you expect to fire first (write-backlog 90 %, system
RAM 80 %, or the encoder pool) and the measured RAM figure from 0.7 that supports it.

`session-stop`. Commit the ledger (`plan/results only, named files`).

**Phase 0 STOP-check (not a gate):** if any of 0.1–0.9 contradicts the "known context"
section in a way that changes the test design (different sensor, exFAT instead of ext4,
missing mic, throttling at idle), report to the operator and wait before Stage 1.

---

## Stage 1 — three 5-minute takes per mode

Take IDs: `S1-<mode-letter><rep>` (e.g. `S1-A1`, `S1-A2`, `S1-A3`, `S1-B1`, …).

Per-take procedure (identical every time):

1. `session-start`. The helper blocks internally until `Storage pre-roll complete`, then
   settles; do not add your own poll loop. If it returns without that marker, treat the
   session as unusable — `cinemate_dev.py stop`, then retry once — do not record into it.
2. Set the mode: `set resolution <n>` → verify the three `resolution_target_*` readbacks
   match the plan (renumbering gotcha — re-check every session).
3. Set fps: **`set fps free 1` first**, then `set fps <test fps>`, then **read `fps` back and
   confirm it equals the target exactly**. Without free mode the value snaps to
   `[25, 33, 50]` and the take is invalid (see "Known context"). Record the readback in the
   ledger. Cross-check the real cadence later from the sampler's `framecount` deltas, never
   from `fps_actual`.
4. Pre-take snapshot: `df -B1 /media/RAW` free bytes; `vcgencmd measure_temp`; confirm free
   space ≥ required (0.5). If temp > 70 °C, wait — poll every 60 s, and if it has not cleared
   after 10 minutes, stop and report rather than recording hot.
5. Start the sampler with a per-take pidfile, after confirming none is running
   (`pgrep -f c1_sampler.sh` empty):
   `nohup /home/pi/c1/c1_sampler.sh /home/pi/c1/samples/<take-id>.csv /tmp/c1_<take-id>.pid >/dev/null 2>&1 &`
6. `session-send "rec f <frames_5min>"`. Poll `session-tail 100` every 60 s **for liveness
   only** — that output is not evidence and is not archived (see step 8). The take is
   *expected* to stop itself at the frame count; if the elapsed time exceeds
   `frames / fps × 1.5`, treat it as `ABORTED-OTHER`, capture what you can, and stop the
   session rather than waiting indefinitely. Send nothing else while recording.
7. Wait for the flush in two stages, and **do not gate on `is_writing`** — `mediator.py`
   forces it to 0 the moment recording intent goes off, so it proves nothing:
   (a) wait for the take's own `Stopped recording`; (b) then poll `is_writing_buf` until it
   reads 0 **and** `buffer` has returned to 0, twice in a row 2 s apart. Then stop the
   sampler: `kill $(cat /tmp/c1_<take-id>.pid)`.
8. **Resolve the take directory once, then use it everywhere.** `last_dng_cam0` holds the
   path of the last written DNG, so its parent is the take dir:
   `TAKE_DIR=$(dirname "$(redis-cli GET last_dng_cam0)")` — sanity-check it starts with
   `/media/RAW/` and exists before using it. Steps 9–11 all use `$TAKE_DIR`; never re-derive
   it, and never use a wildcard.
9. Evidence capture, before anything is deleted:
   - **Copy the whole session log — a tail is not enough.** cinepi-raw emits one
     `DNG written:` INFO line **per frame**, so a 5-minute take at 25 fps produces ~7,500
     lines; `session-tail 400` would cover only the last ~16 seconds and would silently hide
     exactly the mid-take failures this campaign exists to find. Copy it with
     `pi_expect.exp "$PI_PASSWORD" scp … pi@cinepi.local:/tmp/cinemate_cli.log <archive>/session-log.txt`.
     **This must happen before the next `session-start`, which deletes the log.**
     Then grep the copied file (`grep -Ei`) for
     `write.*fail|FAILED|Capture read failed|silent frame|shortfall|drop|SYNC|memory|index gap`
     and record every hit in the ledger.
   - Redis: `framecount`, `missing_frame_count`, `drop_frame_during_last_take`,
     `memory_alert`, `last_dng_cam0`, `buffer`, `buffer_size`.
   - `dmesg | tail -150` → append any storage/USB/ALSA lines to the archive.
   - On-Pi analysis:
     `python3 /home/pi/c1/analyze_cinepi_media.py "$TAKE_DIR" --json > /home/pi/c1/results/<take-id>.json`
   - WAV duration check (snippet above) on the take's WAV.
10. Archive to the Mac (`development/pi-test-takes/c1/<take-id>/`): the analyzer JSON, the
    sampler CSV, `session-log.txt`, the WAV, and the first 3 + last 3 DNGs. Verify the copies
    are non-empty and the JSON parses **before** proceeding.
11. **Only then** delete the take: `rm -rf "$TAKE_DIR"` — that directory only, never a
    wildcard, and only after step 10 verified the archive.
12. Ledger: one row in the Stage 1 table + a short per-take note (outcome class, audio
    verdict, buffer-pressure shape, verdict vs prediction). Commit after each mode's three
    reps. **Commits run in the repo, not the working directory** — the session's cwd
    `Documents/cinemate` is not a git repo; use
    `git -C /Users/patrikeriksson/Documents/cinemate/cinemate`.

Sequencing rules:

- Run order: C (control, if present) → B → A, three reps each, so the easiest mode
  establishes the healthy baseline shape of the sampler curves first.
- If rep 1 of a mode is `AUTO-STOP-GUARD` or loses > 1 % of frames: run exactly one
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
