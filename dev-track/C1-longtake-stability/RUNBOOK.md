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
> **The upheld findings are applied in the text below.** The full record — every finding, its
> evidence, its adjudicated fix, and the 13 refuted claims nobody should re-raise — is in
> [`VERIFICATION-2026-08-26.md`](VERIFICATION-2026-08-26.md) beside this file. **Read it if
> something here reads ambiguous; it is a reference, not a task list, and you do not edit it
> during the campaign.** Several fixes exist because the original text would have silently
> produced invalid data — notably the fps-snapping trap, the per-frame log volume, and the
> fact that a recovered xrun logs nothing. Do not "simplify" those paragraphs back.

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
   documented invariant (e.g. a missing RT-scheduling grant — see 0.6), and each one must be
   logged in the ledger's config-interventions log before you apply it.
   **"Configuration-level" never extends to editing a file in either repo.** A wrong
   affinity, threshold or default that shows up in preflight is a *finding*: record the raw
   evidence verbatim, flag it as a confound for every verdict it touches, and raise it at the
   STOP gate — do not correct it yourself. The two session-state pins
   (`set dynamic resolution 0`, `set fps free 1`) are pre-authorized under this rule: apply
   them before the first test mode is selected, re-issue them after every `session-start`,
   and log them once. Fixes to code are decided at the STOP-gate reviews in the Fable thread,
   not by you mid-stage.
3. **All bookkeeping goes to `cinemate/dev-track/C1-longtake-stability/RESULTS.md`** on the
   local branch `feature/dev-track` (cinemate repo, root
   `/Users/patrikeriksson/Documents/cinemate/cinemate`). Commit after every phase and every
   take batch. `cd` does not persist between shell calls — use `git -C` and absolute paths:
   `git -C /Users/patrikeriksson/Documents/cinemate/cinemate add dev-track/C1-longtake-stability/RESULTS.md`,
   then `git -C /Users/patrikeriksson/Documents/cinemate/cinemate commit -m "c1: …"`.
   **Never `git add -A` in this repo** (LFS pointer trap) — stage the named files only: the
   ledger, plus any other file this runbook tells you to update or that you deliberately
   created. Do not push without asking the operator.
4. **The Pi's repos stay on `dev`.** You do not switch branches on the Pi. Record the exact
   Pi-side commits in the ledger during preflight. The local
   `feature/dev-track` branch is bookkeeping only.
5. **STOP gates are hard stops.** After Stage 1 (5-minute takes) you write the summary block,
   commit, tell the operator it is ready for review in the Fable thread, and end your turn.
   Stage 2 (10-minute takes) only starts when the operator explicitly says the Fable review
   is done and Stage 2 is a go. Same again after Stage 2.
   Stage 1 does not have to be one turn. Nine 5-minute takes plus per-take overhead is
   1.5–2.5 hours of wall clock; if context is running short mid-stage, finish the take you
   are in, complete its archive and ledger row, commit, tell the operator which take IDs are
   done and which remain, and end your turn. A resumed Stage 1 is fine; a Stage 1 summary
   written from a compacted transcript is not. On resume, rebuild state from `RESULTS.md`,
   `/home/pi/c1/results/` and the archive — never from recollection of earlier takes.
6. `PI_PASSWORD` lives only in the environment, never in any file you write.

## Known context you must carry in (do not re-derive, do verify)

- **Measure the board's RAM in 0.7 before reasoning about it — do not assume 2 GB.**
  `cinepi.local` is whichever CM5 is plugged in. It read 2 GB on 2026-08-04, but the
  2026-08-24 Pi session (PI-016) measured **4048 MB, operator-confirmed as the genuine
  current unit**, with available memory never below ~2970 MB at 4056x3040 12-bit. Whatever
  `free -b` says in 0.7 is the number you reason from.
- **Three independent watchdogs can force-stop a take. Never write "the 80 % RAM guard" as
  if it were one thing** — identify which one fired, from its own log line:
  | guard | threshold | log line | owner |
  |---|---|---|---|
  | write-backlog | `buffer / buffer_size` ≥ **90 %** (`BUFFER_LIMIT_PERCENT`) — checked first, and the direct "about to drop frames" signal | `RAM frame buffer NN% ≥ 90%! Stopping recording.` | cinemate `cinepi_controller.py` |
  | system RAM | `psutil.virtual_memory().percent` ≥ **80 %** (`RAM_LIMIT_PERCENT`) — whole-board memory, not a backlog measurement | `RAM NN.N% ≥ 80%! Stopping recording.` | cinemate `cinepi_controller.py` |
  | encoder RAM pool | `ram_buffers_ + 2 >= max_ram_buffers_` (`buffer_full()`, `dng_encoder.hpp`) | `RAM pool exhausted — recording stopped` | cinepi-raw `cinepi_raw.cpp` |
  The two cinemate guards both write their tripping percentage to `memory_alert` and then log
  `Stopped recording`, so `memory_alert` does not tell you which of the two fired — the
  warning line above it is the only discriminator. cinepi-raw's guard writes **no**
  `memory_alert` and only flips its own in-process flag (`setRecording(false)`); it does not
  clear cinemate's `is_recording`, so it presents as a *hang* — `framecount` frozen,
  `is_recording` still 1, the frame-limit stop never reached. Its log line is its only
  signature.
  An auto-stop is a *distinct outcome class* (the drive cannot sustain the data rate), never
  a drop-frame bug. Record the guard name and its log line, not just "it stopped".
- **`set fps` SNAPS to the configured steps — it does not take your number.** With
  `arrays.fps.steps = [25, 33, 50]` and `arrays.fps.free = false` (the shipped default in
  `settings.jsonc`), `set_fps` picks the *nearest* step from a table that has first been
  capped at `fps_max` — and `fps_max` is **truncated** to an int, not rounded. For any mode
  whose cap is under 25 that table collapses to the single value `[int(fps_max)]`, so **every**
  `set fps` lands on it whatever you asked for: imx477's 4056x2160 (cap 16.39) always returns
  **16**, which is 6.7 % above the 0.95 margin the 0.5 formula exists to create. 4056x3040
  (cap 11.72) returns 11 — matching the formula only by coincidence, not by mechanism. Before
  setting any test fps you must issue **`set fps free 1`** (free mode skips the snap entirely
  and clamps to `[1, fps_max]`), then set the number, then **read `fps` back from Redis and
  confirm it equals your target**. Free mode is a runtime flag, re-read from `settings.jsonc`
  at every controller start and never persisted, so **`session-start` resets it to off —
  re-issue it every take**. A take recorded at a silently snapped fps is invalid data — this
  is the single most likely way to waste a whole stage.
- **Dynamic resolution is ON by default and silently rewrites the mode you asked for.**
  `set_resolution` substitutes the largest mode that can sustain the *current* `fps_user`
  before applying anything, and `set_fps` runs the same substitution *before* the fps is
  applied — so the mode can move under **both** commands. The C → B → A run order guarantees
  this fires: `set resolution <B>` issued while `fps_user` is still 25 from the mode-C takes
  lands back on the 25 fps control mode. Pin it off before selecting any test mode —
  `set dynamic resolution 0` (that exact CLI form), then confirm
  `redis-cli GET dynamic_resolution_enabled` reads `0` — and re-confirm after every
  `session-start`, which re-reads it. Because `set fps` can move the mode, take the
  `resolution_target_*` readbacks **after** the fps is set, never before.
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
  disk-worker/audio-core collision is fixed (no profile's `encode_affinity`/`disk_affinity`
  includes the audio core, and cinepi-raw strips it from any requested set as a backstop).
  `cinepi-audio-capture` raises itself to SCHED_FIFO 80 and pins itself to the last CPU core
  (core 3 on this 4-core unit) — but **only while it is actually writing a WAV**. The
  always-running idle VU monitor is launched with `--discard-output` and is deliberately never
  elevated or pinned, so an idle `ps` shows `rtprio -` on a perfectly healthy rig. Check this
  during a take, never at idle.
- **The SCHED_FIFO grant is not a `setcap`.** `setcap` appears nowhere in `cinemate`,
  `cinepi-raw`, the installer or the handbook. The grant is the installer's
  `/etc/security/limits.d/cinemate-audio.conf` (`@audio - rtprio 80`,
  `@audio - memlock unlimited`) plus `pi` in the `audio` group
  (`cinemate-install.sh :: configure_audio_rtprio`); the binary's own failure message offers
  "Grant CAP_SYS_NICE **or** raise the rtprio ulimit", and this stack chose the ulimit. Older
  notes calling this a pending `setcap` item are stale. `session-start` runs cinemate
  **outside** systemd, so `cinemate-autostart.service`'s `LimitRTPRIO=80` does not reach this
  campaign — the limits.d drop-in is the only grant in play. Phase 0 verifies it.
- **A recovered xrun logs NOTHING. Do not grep for "xrun".** In
  `cinepi_audio_capture.cpp`, an ALSA error return (`-EPIPE`) calls `recoverCaptureError()`
  and, when recovery succeeds, simply `continue`s — silently. Only a *failed* recovery prints
  `Capture read failed:`. The observable evidence of lost audio is the **silence-padding
  line**, emitted when the reconciler inserts silence to cover a shortfall and relayed into
  the session log with an `Audio capture helper: ` prefix:
  `Audio capture helper: Inserted <N> silent frame(s) to cover a capture shortfall of <X>s;
  WAV stays aligned to wall clock`. **That line — not "xrun" — is the audio-loss signal for
  every verdict and grep in this runbook.** Its presence also means the WAV was padded back to
  real time, so duration alone can look perfect while samples were lost: always check both.
  The word "xrun" *is* emitted by exactly two lines, and both mean the opposite of an xrun:
  `…raise the rtprio ulimit for xrun-resistant capture` is the SCHED_FIFO-grant failure, and
  `cinepi-audio-capture helper not found; falling back to plain arecord without … xrun
  silence-fill` means the take ran with no silence-fill protection at all and its audio
  verdict is void. Treat a hit on either as a rig fault, never as evidence of a capture stall.
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

- Deterministic helper: `python3 ~/.claude/skills/cinemate-dev/scripts/cinemate_dev.py`
  (`stop`, `session-start`, `session-send "<cmd>"`, `session-tail <n>`, `session-stop`,
  `status --write-report`, `sync-status --repo <repo>`). The file carries a `python3` shebang
  but is **not** mode `+x` and is not on `PATH` — always invoke it through `python3` with the
  full path. A `permission denied` on it is that missing exec bit, **not** a
  `sudo`/`PI_PASSWORD` failure; do not `chmod` it, it is a governed skill file and outside
  this campaign's sanctioned interventions. Everywhere below, `cinemate_dev.py <sub>` is
  shorthand for that full command. Use the **explicit session commands**, not
  `roundtrip-take` — these takes are far too long and too large for the convenience wrapper's
  copy step.
- **Ad-hoc Pi shell and file transfer.** The helper has **no** generic remote-exec and no
  selective file-pull — its only copy command is `copy-latest-take`, which pulls the whole
  take directory (the 30–70 GB you must never copy). Everything in this runbook that is not
  a `cinemate_dev.py` subcommand (`findmnt`, `df`, `dd`, `free`, `ps`, `arecord -l`,
  `getcap`, `vcgencmd`, `dmesg`, `rm -rf`, running the sampler and the analyzer) goes through
  **`~/.claude/skills/cinemate-dev/scripts/pi_ssh.sh '<command>'`**, which uses `PI_PASSWORD`
  from the environment when SSH keys are unavailable. For pulling individual files use
  `~/.claude/skills/cinemate-dev/scripts/pi_expect.exp "$PI_PASSWORD" scp -o StrictHostKeyChecking=accept-new pi@cinepi.local:<src> <dst>`.
  **Give both scripts their full path — neither is on `PATH`.** With `PI_PASSWORD` set they
  run `ssh`/`scp` under `expect` on a local PTY, so stdout carries an injected `spawn ssh …`
  line, a `pi@cinepi.local's password:` line, and CRLF on every line (the password itself is
  never echoed). Whenever you redirect helper or `pi_ssh.sh` output into an evidence file,
  clean it: `| tr -d '\r' | sed -e '/^spawn ssh /d' -e "s/^pi@[^ ]*'s password: *//"`. Never
  filter on the bare word `password:` — that silently deletes real log lines.
- Media analyzer: `~/.claude/skills/cinemate-dev/scripts/analyze_cinepi_media.py`. Its
  **imports** are stdlib-only, so it runs on the Pi's `python3` with no pip install — but it
  shells out to **`exiftool`** and **`ffprobe`**. Confirm `command -v exiftool ffprobe` on the
  Pi in 0.9 and record the answer; the JSON's own `tools` block repeats it. Without
  `exiftool` the DNG-metadata half (`sample_metadata`) is `{}`; without `ffprobe` the
  `wav.ffprobe` block is `{}`. Neither gates a verdict here — record an empty block as tooling
  state, never as a media defect. `scp` it to `/home/pi/c1/` and run it there against the
  take directory; full takes are far too large to copy to the Mac.
  **It does not produce per-frame timestamps** — it runs `exiftool` on the *first* DNG only
  and stores that single result as `sample_metadata`. Any instruction to derive a mean frame
  interval "from the analyzer JSON" is impossible; see the audio-verdict section for what to
  do instead.
  Trust these fields and no others: `dng.count`, `dng.first_index`, `dng.last_index`,
  `dng.missing_indices`, `wav.exists`. Width, height and bit depth come from the
  `resolution_target_*` Redis readbacks, not from here. **Never read `parsed_name.ff` as a
  frame rate**: the take folder's `F##` field is a sub-second timecode frame index
  (`cinepi-raw cinepi/utils.cpp:74-86`, `frameNumber % frameRate`), so it ranges `0 … fps−1`
  and takes shot seconds apart at one fps show unrelated values (`F03`, `F31`, `F45`).
- Archive root on the Mac (**created in 0.9 — the `c1/` level does not exist yet**):
  `/Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/c1/<take-id>/` —
  per-take analysis JSON, sampler CSV, the full session log (a few MB of text), the WAV, and
  first/last 3 DNGs. Nothing larger. (The `pi-test-takes/` tree is currently empty apart from
  `.DS_Store`; that is expected — C1 has not run yet. It is the destination, not a source of
  prior data.)
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
  ts=$(date +%s.%N); fc=$(g framecount)
  echo "$ts,$(g buffer),$(g buffer_size),$fc,$(g fps_actual),$(g is_writing_buf),$(g write_speed_to_drive),$(g space_left),$(g memory_alert),$d,$t,$th" >> "$OUT"
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
- `ts` is `date +%s.%N` — **sub-second, and read immediately before `framecount` in the same
  iteration** so the two are adjacent. That pairing is what makes a `framecount`-slope fps
  admissible: fitted over a 5-minute window it is good to a few milliseconds of expected
  duration, against a PASS threshold of half a frame period. Do not revert it to `date +%s`;
  whole-second stamps put the fit's uncertainty at ~±1 s ≈ 25 frame periods at 25 fps, which
  is not admissible for any audio verdict. The **cadence** is still 2 s (~150 rows per
  5-minute take) — enough to fit a rate and to show the shape of buffer pressure, not enough
  to resolve a stall shorter than 2 s.
- **The `buffer_size` column is stale in every row before the take's first recorded frame.**
  cinepi-raw publishes that key once per encoder setup, from the per-frame path
  (`cinepi/cinepi_controller.cpp:393-398`, guarded on
  `!buffer_size_sent_ && GetEncoder()->initialized()`), so early rows carry the previous
  take's — possibly another mode's — pool size. Read the column from the first row **after**
  `framecount` starts advancing, and note it in the ledger if it differs from that mode's 0.7
  figure. It legitimately can: the pool is sized from `MemAvailable` sampled at that take's
  first frame, which differs between a cold session and one following a 5-minute take.

Start it right before each `rec`, stop it after the post-take flush. One CSV per take:
`/home/pi/c1/samples/<take-id>.csv`.

WAV duration check (on the Pi, stdlib). The WAV always sits inside the take directory and its
basename equals that directory's name (`cinepi-raw cinepi/cinepi_sound.cpp:835`), so derive
the path from the `$TAKE_DIR` you already resolved — the snippet has no default and dies with
`FileNotFoundError` on an empty argument:

```bash
WAV="$TAKE_DIR/$(basename "$TAKE_DIR").wav"
python3 - "$WAV" <<'EOF'
import sys, wave, os
p = sys.argv[1]
size = os.path.getsize(p)
w = wave.open(p, 'rb')
n, rate, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
print(f"frames={n} rate={rate} ch={ch} sampwidth={sw} "
      f"duration_s={n/rate:.6f} filesize={size}")
# The data-chunk size is written as 0 when the WAV is opened and only rewritten
# with the true size on the graceful shutdown path (cinepi_audio_capture.cpp
# :457 and :715-721). frames=0 on a large file means the capture helper was
# hard-killed — it does NOT mean audio was lost.
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
one, note both numbers, and score the take's audio `UNFINALISED-WAV — not a sync deviation`.
This cannot happen on a `COMPLETE-*` or `AUTO-STOP-GUARD` take: every one of those stops runs
`sound.record_stop()` → `SIGTERM` to the helper's process group → graceful finalise. It is
evidence of a hard abort, so cross-check the session log's `WAV ready for metadata update:
<n> bytes`. Do **not** add a blanket `(filesize − 44) / (channels × sampwidth)` cross-check
against `frames`: the parent appends an iXML chunk after the data chunk and repairs only the
RIFF size, so that arithmetic disagrees with `frames` on every healthy take and would
false-positive on all of them. `frames == 0` is the unambiguous signal.

On an `AUTO-STOP-GUARD` or `ABORTED-OTHER` take the requested frame count never happened —
build the expected duration from the DNGs actually on disk, never from `frames_requested`.

## Outcome classes and pass thresholds (fixed for the whole campaign)

Every take gets exactly one outcome class:

| Class | Definition |
|---|---|
| `COMPLETE-CLEAN` | Stopped at the requested frame count; from the analyzer JSON **all** of `dng.count` == requested, `dng.first_index` == 0, `dng.last_index` == `dng.count − 1`, `dng.missing_indices` == 0; Redis `missing_frame_count` == 0 **and** `drop_frame_during_last_take` == 0; no write-failure, drop/sync, index-gap or silence-padding hits in the **full** session log. `missing_indices` alone is blind at the edges — it only counts holes inside `min..max`, so frames lost before the first or after the last surviving index are invisible. The `first_index`/`last_index` checks close that hole and match cinemate's own formula `last idx + 1 − count`. |
| `COMPLETE-OVERSHOOT` | Every `COMPLETE-CLEAN` condition holds except that DNG count is **greater** than requested. Benign, not a fault: the frame-limited stop deliberately fires `min(2, frames−1)` slots early to compensate for pipeline lead (the take's `Armed exact frame-limited stop: <N> additional frame slots (threshold slot <x>, pipeline lead compensation <n>).` line), so landing exactly on the request is a calibrated estimate that can land over. cinemate agrees nothing was lost — `missing_frame_count` is `max(0, expected − recorded)`, hence 0 — and logs `Frames within final tolerance: -1 frame difference …` at INFO for one frame over (inside the ±1 tolerance, so **no warning is emitted at all**), or `Sensor ran fast: recorded N extra frame(s)` for two or more. Count the take as **clean** in the Gate 1 `takes clean / total`, note the surplus in the per-take note, and put **0** — never a negative number — in `frames lost total`. |
| `COMPLETE-WITH-LOSS` | Reached the requested count / duration but a `COMPLETE-CLEAN` condition **other than a pure DNG-count overshoot** is violated — DNG count *below* requested, a filename-sequence or index gap, `missing_frame_count` > 0, or write-failure / drop-sync / silence-padding hits in the session log |
| `AUTO-STOP-GUARD` | A watchdog force-stopped the take. **Name which one** and quote its log line verbatim — the log line is the only discriminator: `RAM frame buffer NN% ≥ 90%! Stopping recording.` (write-backlog), `RAM NN.N% ≥ 80%! Stopping recording.` (system RAM), `RAM pool exhausted — recording stopped` (cinepi-raw's encoder pool). `memory_alert` does **not** identify the guard: both cinemate guards write their tripping percentage to it, and cinepi-raw's pool stop never writes it at all — so `memory_alert` == 0 does not rule out an auto-stop. |
| `ABORTED-OTHER` | Anything else (crash, storage yank, operator abort) — attach the evidence. A take that ended early with **no** guard line and no `Exact frame-limited stop reached: slot <x>/<N>` belongs here, not in `AUTO-STOP-GUARD`: both cinemate guards log their warning and then `Stopped recording`, so a log that simply goes silent is a crash. |

`frames lost total` in the Gate 1 summary is the sum of the per-take `missing_frame_count`,
**not** `frames requested − DNGs on disk`. The two diverge whenever the frame-limited stop
lands off the request in either direction; only `missing_frame_count` counts frames the
system considers absent.

**Every log string a class or verdict turns on.** Step 10's grep must cover all of these, and
each one has exactly one consequence — a term with no consequence is uncollectable evidence,
and a consequence with no term is an undecidable class. Record the verbatim line, with its
line number and timestamp, for every hit.

| Log line (as emitted) | Consequence |
|---|---|
| `✓ All frames accounted for.` (INFO) | exact landing — the only line that *positively* supports `COMPLETE-CLEAN` |
| `Frames within final tolerance: <±d> frame difference between expected and recorded counts.` (INFO) | sign is `expected − recorded`: `-1` = one frame over → `COMPLETE-OVERSHOOT`; `+1` = one frame short → `COMPLETE-WITH-LOSS` |
| `Sensor ran fast: recorded N extra frame(s) vs M expected` | `COMPLETE-OVERSHOOT` |
| `Frame count low: N fewer frame(s) than expected M` | `COMPLETE-WITH-LOSS` |
| `Missing frames: N frame(s) not written to disk …` | `COMPLETE-WITH-LOSS`; N is the loss. The plain variant carries **no** `fail` and no `drop` token — grep for `Missing frames` explicitly or you will not see it |
| `DNG index gaps: N missing file slot(s) in sequence` | `COMPLETE-WITH-LOSS` |
| `<cam> appears to be missing N DNG index slot(s) (count=…, last idx=…)` | same defect, per folder. The summary line above sits in an `elif` chain **behind** `Missing frames:`, so on a take with both, this is the only index-gap line emitted — grep `DNG index slot` as well as `index gap` |
| `TC timing: N late-arrival event(s) … All M files present with contiguous indices — no data lost.` (INFO) | timing irregularity only, **not** loss — do not downgrade the class on it |
| `Drop frame detected (…)` · `Live frame sync warning:` · `Disk write failure:` · `DNG write FAILED …` | `COMPLETE-WITH-LOSS` |
| `RAM frame buffer …! Stopping recording.` · `RAM …! Stopping recording.` · `RAM pool exhausted — recording stopped` | `AUTO-STOP-GUARD`, named per the class table above. `%! Stopping recording` is the safe anchor for the first two; do **not** loosen it to `RAM [0-9]`, which under `-i` matches inside unrelated lines |
| `Audio capture helper: Inserted N silent frame(s) to cover a capture shortfall of X s` | audio WARN or FAIL, by summed X (below) |
| `Capture read failed:` | audio FAIL |
| `Audio capture helper exited before capture actually started` · `Failed to launch audio capture helper` | no WAV → audio `FAIL (no WAV)` |
| `cinepi-audio-capture helper not found; falling back to plain arecord …` | the take ran with **no** silence-fill protection; its audio verdict is void — say so rather than scoring it |

Any other hit is still recorded in the ledger, but it does not move a class on its own.
`xrun` and `overrun` appear in no row on purpose: no xrun *event* emits either word (see
"Known context"). Exactly two emitted lines contain `xrun`, and both are rig faults rather
than capture stalls — the SCHED_FIFO-grant failure (`…raise the rtprio ulimit for
xrun-resistant capture`) and the helper-missing fallback in the last row.

Audio verdict per take (independent of the outcome class above; a missing WAV never changes
that class). **Both legs must be checked — a padded WAV has correct duration and lost
samples:**

- **PASS** — WAV present; `|wav_duration − expected_duration| ≤ 0.5 frame period`; **and zero
  silence-padding lines** (`silent frame(s) to cover a capture shortfall`) and zero
  `Capture read failed:` lines in the full session log for the take.
- **WARN** — deviation ≤ 1 frame period, or padding lines present whose **summed** inserted
  silence is under one frame period. The line *count* is not the criterion; the sum is.
- **FAIL** — deviation > 1 frame period, any `Capture read failed:`, summed padding ≥ one
  frame period, or a missing WAV. On FAIL, do the deep dive below before writing the verdict
  — **except when the WAV is missing entirely**, where there is nothing to analyse.

Sum the padding for **every** take, PASS included — count and seconds both:

```bash
grep -Eo 'Inserted [0-9]+ silent frame\(s\) to cover a capture shortfall of [0-9.]+s' \
  <archive>/session-log.txt \
  | awk '{n++; s+=$(NF)} END {printf "silence_fills=%d total_inserted_s=%.4f\n", n+0, s+0}'
```

The helper only fills shortfalls larger than a quarter ALSA period (~5.3 ms at 48 kHz), a
threshold chosen so SCHED_FIFO scheduling jitter cannot trigger a spurious fill — so on a
healthy rig the expected count is **zero**, and any nonzero count is a real capture stall. A
single fill is capped at 5 s (`maxGapFrames = rate × 5`), so a stall longer than that also
shortens the WAV and shows up in the duration term as well. **A nonzero fill count with a
clean duration is the campaign's key audio datum** — it is the signature of the
storage-contention sample loss this campaign exists to measure.

**Missing WAV.** Record `FAIL (no WAV)`, and grep the take's log for `helper not found`,
`Failed to launch audio capture helper`, `Audio capture helper exited before capture actually
started`, and `Audio capture helper:`. cinepi-raw emits each of these and deliberately
continues the take without audio. Quote the matching line in the ledger and carry it to the
STOP gate. Do not re-run the take on that basis alone, and do not change the video outcome
class — the audio verdict is independent of it.

**`frames=0` is not a sync deviation.** The helper writes the WAV's `data` chunk size as 0 at
open and only rewrites it with the true size on the graceful shutdown path. If the duration
check prints `frames=0` on a file that is not tiny (`ls -l` it), the header was never
finalised — a hard kill, not lost audio. Record it as `UNFINALISED-WAV`, derive the duration
from the payload bytes, cross-check against the parent's `WAV ready for metadata update: <n>
bytes` line, and do not score it as a duration deviation.

`expected_duration` = `dng_count / fps_target`. **If the sensor's real cadence differs from
`fps_target`**, recompute against the real cadence and record both numbers. Derive that
cadence from the sampler CSV — not from the analyzer JSON, which has no per-frame timestamps,
and not from `exiftool`, which 0.9 will almost certainly record as absent on this Pi and which
you may not install (ground rule 2). Restrict to the rows where `framecount` is strictly
increasing (it is per-take and sits flat outside a take) and least-squares fit `framecount`
against `ts`; the slope is the measured fps and `mean_frame_interval = 1 / slope`. Record four
numbers: the target-fps expectation, the fitted-fps expectation, the fitted fps itself, and
the residual against `wav_duration`.

State the fit's resolution alongside them. `ts` is `date +%s.%N` — **sub-second**, and read in
the same sampler iteration immediately before `framecount` — so over a 5-minute take (~150
paired samples) the timestamp contributes only milliseconds of uncertainty; the fit's floor is
set by `framecount`'s ±0.5-frame quantisation, not by the clock. That is well inside half a
frame period at every fps this campaign uses, so **the fitted expected duration is admissible
for the audio verdict itself**, not merely for attributing a deviation. Quote the fitted slope
with its standard error and the residual against `wav_duration`; only when the residual is
smaller than that standard error do you write "consistent with fps offset, at the fit's
resolution floor" instead of a precise value.

What the fit cannot do is resolve a stall shorter than the 2 s sampler cadence — use the
padding lines for that. And if you ever meet a CSV whose `ts` is whole seconds, it was not
written by this runbook's sampler: that fit is ±1 s ≈ 25 frame periods at 25 fps, voids every
audio verdict derived from it, and the take must be re-run with the corrected sampler.

**Audio deep dive (self-contained — there is no external method file).** On FAIL with a WAV
present:

1. Sum the inserted silence (one-liner above) and compare it to the duration deviation — if
   they match, the loss is capture-side, not clock drift.
2. Classify the shape: fills clustered at one moment = a single storage stall; fills spread
   across the take = sustained contention. Correlate each fill against the sampler CSV's
   `buffer`, `dirty_kb` and `write_speed_to_drive` columns at the same second — log stamps are
   local wall clock `YYYY-MM-DD HH:MM:SS.mmm` and the CSV is epoch seconds, so convert with
   `date -d '<stamp>' +%s` on the Pi. Padding that coincides with buffer pressure is the
   storage-contention mechanism this campaign exists to measure.
3. Only if the deviation is large **and** there are no fill lines: recompute against the
   fitted cadence above. That pattern points at fps offset or start-of-take latency, not
   sample loss.
4. Check whether the affected take's disk workers and `cinepi-audio-capture` shared a core
   (the 0.6 check), since that collision has caused this before.
5. Confirm the WAV is continuous with the `wave` snippet above.
6. Name the mechanism in the verdict: `sample-loss (N fills, X.XXX s)`, `fps-offset`,
   `start-latency`, `core-collision`, or `undetermined`. **Never write FAIL without one of
   these.**

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

0.2 **Sensor + mode table.** `session-start` — the helper blocks internally until
`Storage pre-roll complete` appears in `/tmp/cinemate_cli.log` and applies its own settle; do
not add a poll loop. **Check the exit code.** From the session log / Redis, record the detected
sensor and the full 12-bit mode list with fps caps. Select the test modes per the rule above
and give each a letter: **A** = largest 12-bit, **B** = second-largest 12-bit, **C** = 25 fps
control (if available).

**If `session-start` exits non-zero with `Timed out waiting for storage pre-roll
completion.`, do not retry blindly.** The session is still running — the helper prints
`started:<pid>` before it waits — so a retry kills a healthy session and burns another 120 s
(`--ready-timeout-seconds` default). On three configurations the marker is unreachable **by
design** and no wait will ever satisfy it. Diagnose in this order:

- `findmnt -no SOURCE,FSTYPE /media/RAW` — no output means the media never mounted, so
  `_arm_startup_preroll` returned early and the pre-roll never ran. **That path is silent**;
  only the deferred variant logs anything (`Storage pre-roll remained deferred through
  startup, but no media is mounted`), so the absence of a skip line proves nothing. STOP and
  report — every blind retry costs a further 120 s.
- `session-tail 200 | grep -i "storage pre-roll"` —
  `Automatic storage pre-roll disabled by settings.jsonc` means `auto_preroll` is `false` on
  this Pi; `Skipping storage pre-roll (…): recording already active` means a stale
  `is_recording` = 1 is left in Redis from a killed session. Both are STOP-and-report.
  **Do not change `auto_preroll` and do not clear `is_recording` yourself** — the first
  confounds the whole comparison (see "Known context"), the second is not a sanctioned
  intervention.
- Nothing in the log and `/media/RAW` mounted → a real startup fault. `session-stop`, then
  `cinemate_dev.py stop`, then retry **once**. Keep the helper's 80-line stderr tail as
  evidence. A second failure is a STOP.

Only with explicit operator approval may you proceed without the warm-up: use
`--- Initialization Complete ---` (`src/main.py`) as the readiness marker instead, record the
deviation in the interventions log, and flag every take started that way as `no-preroll`.
Stage 1 step 1 inherits this rule unchanged.

0.2b **Pin the two silent rewriters — dynamic resolution and fps snapping.** Both are shipping
defaults, both are session state rather than file edits, and both will silently replace the
mode or the fps you asked for. Pre-authorized under ground rule 2; log both in the
interventions table with before/after values.

- **Dynamic resolution is ON by default** (`docs/redis-keys.md`: persisted and read back at
  startup, defaulting to on when unset). While it is on, `set_resolution` substitutes the
  largest mode that sustains the *current* `fps_user` before applying anything
  (`cinepi_controller.py :: set_resolution` → `_dynamic_resolution_choice_for_fps`), and
  `set_fps` runs the same hook — so it can move the mode **after** you verified it. With this
  campaign's run order (C → B → A) that is not hypothetical: `set resolution <B>` issued while
  `fps_user` is still 25 from the mode-C takes lands back on the 25 fps control mode, and
  `resolution_target_*` reports the substitute as if you had asked for it.
  Turn it off: `set dynamic resolution 0` (exact command — `set dynamic_resolution_enabled`
  is not a command), then confirm `redis-cli GET dynamic_resolution_enabled` reads `0`.
- **`set fps` snaps** unless free mode is on — see "Known context". `set fps free 1`, then
  confirm by grepping the log for the prefix **`FPS Free`** only — never the whole line — and
  from the `fps` readback. The handler logs the raw argument, so it reads `set to 1`, not
  `set to True`; and the wording differs by branch (`FPS Free Mode` on `dev`, `FPS Free
  Stepping` once the free-stepping rename merges). There is
  **no Redis key for free mode**: `fps_free` is re-read from `settings.jsonc` at every
  controller start and never published, so a Redis check is impossible and a missed re-issue
  is silent.

Re-issue **both** after every `session-start`, before setting any mode — the fps pin is not
persisted at all, and the dynamic-resolution pin is re-read at process start. If either
verification fails, STOP and report; do not proceed with a substituted mode or a snapped fps.

> **Execution order — the numbering is not the running order.** 0.5's fps rule needs
> bytes/frame (0.3) *and* sustained write speed (0.4), while 0.3 needs an fps to record at.
> Break the circle by running: **0.1 → 0.2 → 0.2b → 0.4 → 0.3 → 0.5 → 0.6 → 0.7 → 0.8 →
> 0.9 → 0.10**, and record 0.3's validation takes at a **provisional** fps of
> `min(floor(0.95 × sensor fps_max), 25)` — bytes/frame does not depend on fps, so the
> provisional value is only used to make the mode record at all. 0.5 then computes the real
> test fps from the measured numbers. If 0.5's answer differs from the provisional value, that
> is expected and needs no re-run of 0.3.

0.3 **Mode validation + measured bytes/frame.** Run after 0.4. All validation takes share the
one session started in 0.2, so they do **not** get Stage 1's fresh-session guarantees — apply
the same guards by hand. For each selected mode:

1. `set resolution <n>` → read back `resolution_target_width/height/bit_depth`.
2. Set the **provisional** fps: `set fps free 1`, then the number, then read `fps` back and
   confirm it equals your target exactly. Then **re-read the three `resolution_target_*`
   values** — `set fps` runs the same dynamic-resolution hook as `set resolution`, so it can
   move the mode after step 1 verified it (0.2b). Record the readbacks only after this second
   confirmation.
3. **Before sending `rec`**, poll until `is_writing_buf` = 0 **and** `is_buffering` = 0.
   `start_recording()` silently refuses a new take while either key is 1 — those are the exact
   two keys `_buffered_frames_flushing()` reads, *not* `is_writing`. The only trace is
   `rec ignored` in the log, followed by `Unable to start recording; frame-limited stop not
   scheduled.` Grep for both after every `rec`; if either appears, redo the wait and resend.
4. Record the log offset: `LINES=$(wc -l < /tmp/cinemate_cli.log)`.
5. Start the 0.6 thread snapshot **before** `rec`, as a **backgrounded** command over a second
   `pi_ssh.sh` connection writing to a file on the Pi — a foreground call would block and
   finish before step 6 ever runs, and a 25-frame take is only 1.0–2.3 s of capture with
   nothing elevated or pinned when idle:
   ```
   pi_ssh.sh 'nohup bash -c "for i in \$(seq 1 120); do date +%s.%N; ps -eLo pid,tid,comm,rtprio,psr | grep -Ei \"[c]inepi-audio|dng-\"; echo ---; sleep 0.5; done" > /home/pi/c1/threads_<mode>.txt 2>&1 & echo \$!'
   ```
   Note the printed PID, send `rec f 25` (step 6) within a few seconds, and after step 8's
   flush stop it with `pi_ssh.sh 'kill <pid> 2>/dev/null; true'` — the loop is bounded at 60 s
   and self-terminates, so the kill is a tidy-up, not a requirement. `scp` the file into the
   archive and read 0.6's two checks off it. **Confirm at least two `---` blocks fall between
   `is_recording` going 1 and 0**; if none do, re-run this step rather than scoring 0.6 from an
   idle sample.
6. `session-send "rec f 25"`. Confirm it was **accepted**: the lines added after the offset
   must show the `Received: rec f 25` echo and `Armed exact frame-limited stop:`, and
   `is_recording` must go to 1. No `Armed` line means the frame limit was never set — stop the
   take rather than letting it run unbounded.
7. Wait for the stop **only in the lines added after the offset**:
   `tail -n +$((LINES+1)) /tmp/cinemate_cli.log | grep -q "Stopped recording"`.
   **Never grep the whole file and never use a fixed-depth tail here.** `session-start`
   truncated the log once, back in 0.2, and the startup pre-roll already logged its own
   `Stopped recording` (`storage_preroll.py` calls `stop_recording()`), so a whole-file match
   returns true instantly and you would measure a take that is still being written. This is
   also why `roundtrip-take` is banned — its internal wait is exactly that whole-file grep.
8. Poll until `is_writing_buf` = 0 and `is_buffering` = 0, then record: actual DNG file size
   (`stat -c%s` on one mid-take DNG), WAV presence, and that the 25 DNGs are
   sequence-continuous. Read `buffer_size` for 0.7 **now** — it is valid for this mode only
   after this take — and record `MemAvailable` (`grep MemAvailable /proc/meminfo`) captured
   immediately **before** this take's `rec`: 0.7's runway needs the memory state the pool was
   sized from, and that moment is gone once the session moves on.

   **Resolve the take directory before touching it**, exactly as Stage 1 step 9 does:
   `TAKE_DIR=$(dirname "$(redis-cli GET last_dng_cam0)")`, then assert it is non-empty, is not
   the literal string `None` (`dirname None` returns `.`), starts with `/media/RAW/CINEPI_`,
   ends in `_cam0`, and `[ -d "$TAKE_DIR" ]`. Use `$TAKE_DIR` for the `stat -c%s`, the sequence
   check, the WAV snippet and the delete. **If any assertion fails, delete nothing and report.**
9. **Do not delete the take until this mode's 0.3, 0.6 and 0.7 rows are all in the ledger.**
   Then delete it — the named directory only, never a wildcard.

**Measured bytes/frame × applied test fps = the mode's data rate.** Bytes/frame is a function
of width × height × bit depth only, so if 0.5's final fps differs from the provisional one,
nothing measured here needs redoing; re-run a single `rec f 25` at the final fps only if you
want to reconfirm sequence continuity.

0.4 **Storage identity + sustained write speed.** `findmnt -no SOURCE,FSTYPE /media/RAW`
(expect the NVMe, ext4), `df -B1 /media/RAW`, and identify the drive itself
(`cat /sys/block/<dev>/device/model`, plus capacity and % used) so the result is attributable
to a specific piece of hardware. The burst-versus-sustained gap is a property of the NAND, so
the number below is uninterpretable without knowing which drive produced it.

Sustained speed. Confirm at least 40 GB free, then capture the progress stream to a file on
the Pi (dd writes it to stderr, CR-separated):

```
dd if=/dev/zero of=/media/RAW/c1_speedtest bs=4M count=8192 oflag=direct conv=fsync status=progress 2> /home/pi/c1/dd_progress.txt
```

That is 32 GiB — about one Stage 1 take, and long enough to run out of the drive's pSLC write
cache. Expect roughly 76 s at 450 MB/s, 172 s at 200 MB/s, 344 s at 100 MB/s. **This one
command can run for ~6 minutes: give the Bash call an explicit timeout of 600000 ms.** At the
default 120 s it is killed mid-write and the delete below never runs — if that happens, before
anything else run `pi_ssh.sh 'rm -f /media/RAW/c1_speedtest; df -B1 /media/RAW'` and confirm
free space is back. A leftover 32 GiB file is enough to fail 0.5's free-space check for mode A.

**dd's `status=progress` prints a *cumulative average*, not an instantaneous rate** — a
running mean never "steps down", so you cannot read the trailing rate off it directly.
Difference adjacent samples instead:

```
tr '\r' '\n' < /home/pi/c1/dd_progress.txt | awk '/copied/{b=$1+0; t=$(NF-1)+0; if(pt && t>pt) printf "%.1f GiB  inst %.0f MB/s\n", b/1073741824, (b-pb)/(t-pt)/1e6; pb=b; pt=t}'
```

Record the **last three instantaneous rates** as the trailing sustained MB/s (the number every
downstream `0.85 ×` threshold uses) and the **first three** as `burst MB/s @ NN GB`. If the
instantaneous rate never drops more than 15 % below the burst figure, write "no cache step
observed" and still use the trailing instantaneous rate — **never dd's final average**.

Run it **once**. Do not run it twice and keep the lower number: two short runs both sit inside
the cache, and averaging them hides exactly the step this measurement exists to find. A single
confirmation run after 5 minutes idle is optional; it should agree with the trailing figure,
not with the average.

Two caveats to record alongside it, because the campaign's feasibility maths leans on it: a
short run of zeros lands entirely inside an SSD's SLC cache and overstates sustained speed
(the failure mode the exFAT/USB-SSD notes in `storage_profiles.py` describe, which shows up
~90 s into a real take) — `oflag=direct` bypasses the Pi's page cache but **not** the drive's
own — and the real DNG writer does not use `O_DIRECT` at all. Treat even the trailing figure
as an optimistic ceiling, not a promise.

Do **not** run it twice and keep the lower number. After a 32 GiB run the drive is
cache-depleted and still folding, so a back-to-back second run under-reports steady state. If
you want a confirmation run, idle 5 minutes first; it should agree with the trailing rate, not
with the average. Leave the drive idle 5 minutes after the test before any 0.3 or Stage 1
take, so no take starts mid-fold in a state normal use never produces. Do not repeat this test
for Stage 2 — steady-state write speed is a property of the drive, not of take length.

0.5 **Per-mode fps + feasibility.** Planned test fps for each mode =
`min( highest integer ≤ 0.95 × sensor fps_max , highest integer with data-rate ≤ 0.85 × the 0.4 trailing sustained MB/s , 25 )`.
That value is reachable only in free fps mode. Per mode, in this order: `set fps free 1`, then
`set fps <planned>`, then read `fps` back — and record the **planned** and the **applied**
numbers as two separate columns. If the readback does not equal the planned integer, STOP and
report — do not
carry that mode into Stage 1. Every downstream number — data rate, take size, free-space
requirement, `runway_s`, `frames_5min`/`frames_10min`, and the audio `fps_target` — uses the
**applied** fps, never the planned one.

Then per mode: `frames_5min = applied fps × 300`, take size = frames × bytes/frame, and
required free space = take size × 1.2. If a mode cannot fit or cannot stay under the storage
cap at any usable fps, record it as `INFEASIBLE-ON-THIS-RIG` with the arithmetic — that is a
finding, not a failure.

The rate term has no floor — inspect it before using the result:

- **Rate term = 0** (no integer fps keeps the mode under the storage cap) is exactly the
  `INFEASIBLE-ON-THIS-RIG` trigger: record the arithmetic and skip the mode. **Never send
  `rec f 0`** — cinemate logs `Timed recording frame count must be greater than zero.` and
  does nothing, so you would wait forever on a `Stopped recording` that never comes.
- **Applied fps < 60 % of that mode's raw sensor `fps_max`** means the drive set the rate, not
  the sensor. Run the mode anyway, but write `STORAGE-LIMITED (<fps> of <fps_max>, <n> %)` in
  the `feasible?` column, carry the label into Stage 1's limiting-factor column, and never
  answer the Stage 2 "drop-frame goal met?" cell a bare "yes" — a clean take at that fps does
  not clear the mode at its native rate. Compare against the raw `fps_max`, not against
  `floor(0.95 × fps_max)`; the derated value is the number being tested.

0.6 **Audio preflight.** `arecord -l` — the mic must be present; if absent, **STOP and report
to the operator**, and do not start any take without it.

**The authoritative SCHED_FIFO signal is the running thread's `rtprio`, not `getcap`.** An
empty `getcap` is the **normal, correct state** on a properly installed Pi: this stack grants
RT scheduling through the installer's `configure_audio_rtprio()`: a limits.d drop-in at
`/etc/security/limits.d/cinemate-audio.conf` carrying `@audio - rtprio 80`, plus `pi` in the
`audio` group — not through file capabilities. Run `getcap` for the record, decide on the
live check.
`cinepi-audio-capture` is resolved by cinepi-raw as a sibling of its own binary, so find the
real path with `readlink -f /proc/$(pgrep -f cinepi-audio-capture | head -1)/exe` rather than
guessing.

**Both checks read the 0.3 step-5 thread snapshot — they cannot be run at idle.** The helper
elevates and pins itself only when writing a WAV (`tryElevateRealtimePriority()` is gated behind
`if (!options.discardOutput)`), and the always-running idle VU monitor is launched with
`--discard-output`. An idle `ps` therefore reads as a failure on a perfectly healthy rig.

1. **`cinepi-audio-capture` at `rtprio` 80 on the last core** (core 3 on this 4-core unit).
   `comm` is truncated to 15 characters (`cinepi-audio-ca`), so match on the prefix and record
   the exact thread names you see rather than assuming `dng-enc`/`dng-dsk`.
   **The process has two threads and one of them is *supposed* to read `rtprio -`** — the WAV
   writer thread is deliberately never elevated and never pinned, and the `--discard-output`
   VU monitor is never elevated either. The check FAILS only if **no** `cinepi-audio-ca` row
   shows `rtprio` 80. Never act on an `rtprio -` row alone.
   Cross-check the session log for the same take: `Capture thread elevated to SCHED_FIFO
   priority 80` and `Capture thread pinned to CPU 3 (of 4 available)` = granted;
   `Could not set SCHED_FIFO capture priority` = not granted.
   If not granted, this is the one sanctioned config intervention — and it is **not `setcap`**
   (that string appears nowhere in `cinemate`, `cinepi-raw` or the installer; the
   `CAP_SYS_NICE` wording in the helper's own error message is one of two alternatives and
   this stack chose the ulimit). Re-apply the installer's own grant for whichever leg failed:
   - `cat /etc/security/limits.d/cinemate-audio.conf` must contain `@audio - rtprio 80`; if
     not: `printf '@audio - rtprio 80\n@audio - memlock unlimited\n' | sudo tee /etc/security/limits.d/cinemate-audio.conf`
   - `id pi` must list the `audio` group; if not: `sudo usermod -aG audio pi`
   - `ulimit -r` over the helper SSH transport must return `80`.
   Then `session-stop` and `session-start` — every helper command opens a fresh SSH login, so
   PAM re-reads groups and limits and no reboot is normally needed. Re-verify against the
   **log line**, not the `ps` table (the `rtprio -` writer row survives a successful fix and
   would otherwise make re-verification loop forever), and record before/after. The restart
   renumbers resolution indices and voids every `buffer_size` reading, so re-run 0.3 for all
   modes after it. If `ulimit -r` is still not 80 after a fresh login, STOP and report — do
   not attempt further remedies.
2. **No encode/disk worker sharing the audio core.** Those threads are properly named
   (`dng-enc-<n>`, `dng-dsk-<n>`), so this half of the grep is reliable. A hit is a **finding,
   not something you fix**: no recorder profile requests core 3, and cinepi-raw strips the
   audio core from any requested affinity as a backstop (`dng_encoder.cpp`), so a thread
   sitting there means the Pi's build or profile is not what `dev` says it is — which also
   puts 0.1's recorded commits in doubt. Record the raw `ps` output verbatim in the ledger,
   **STOP, report to the operator, and end your turn.** Do not edit `storage_profiles.py`, or
   any other file, to correct the affinity yourself — every code-level affinity change is a
   Fable-thread decision. If the operator clears you to proceed regardless, flag the audio
   verdict of every take that follows as confounded.

0.7 **Board RAM + encoder runway.** `free -b` — **record `MemTotal`; this is the number the
whole campaign's RAM reasoning rests on, and it is not assumed** (see "Known context").

`buffer_size` is **not a live key**: cinepi-raw publishes it once per encoder setup, at the
**first recorded frame** after that setup. Reading it before any take of a given mode returns
a stale value from the previous mode, or nothing. So read it during that mode's 0.3 validation
take (0.3 step 8) and record which take it came from. Record `MemAvailable` from the same
moment: the pool is sized as `0.90 × MemAvailable ÷ per-frame bytes`, so the runway is a
function of the memory state as well as of the mode, and it legitimately differs between a
cold session and one following a long take.

Confirm the value rather than trusting the key. That take's log carries two setup lines —
`RAM pool: up to <N> frames` with its MB figure, and `Encoder configured` with the mode's
width, height, bit depth and per-frame buffer MB. Check the dimensions and bit depth are the
mode you set, then confirm `buffer_size` equals `<N>`. **Never record a `buffer_size` that
disagrees with `<N>`** — a disagreement means you are reading a stale key; re-read, since the
publish lands on the frame after the first encoded frame.

Then compute `runway_s = 0.90 × buffer_size / fps` — the seconds of total write stall the
frame pool can absorb before the **write-backlog guard** (90 % of `buffer_size`, the first of
the three watchdogs) ends the take. Treat it as an **upper bound**: the system-RAM backstop
and cinepi-raw's own pool guard can preempt it, which is why the ledger also carries
`MemAvailable` — it shows how much headroom the 80 % backstop had. Expect single-digit
seconds; if it is under ~2 s for a mode, say so in 0.10, because that mode's result will be
dominated by transient stalls rather than by sustained throughput.

0.8 **Thermals.** `vcgencmd measure_temp` and `vcgencmd get_throttled` at idle. If
`get_throttled` ≠ `0x0` at rest, record it and flag — under-voltage invalidates everything
downstream. If idle temp is already ≥ 70 °C, the between-takes cooldown gate in Stage 1 is
unsatisfiable on this rig as configured: raise it at the Phase 0 STOP-check and wait for the
operator, rather than discovering it between takes with nine takes queued.

0.9 **Install instrumentation.** On the Pi, via `pi_ssh.sh`:
`mkdir -p /home/pi/c1/samples /home/pi/c1/results`. Write `c1_sampler.sh` locally first — it
does not exist yet, author it verbatim from the Instrumentation section above — then push it and
`~/.claude/skills/cinemate-dev/scripts/analyze_cinepi_media.py` to `/home/pi/c1/` with the
`pi_expect.exp … scp` form from "Tools you drive". Then
`pi_ssh.sh 'chmod +x /home/pi/c1/c1_sampler.sh'` and confirm both landed with
`pi_ssh.sh 'ls -l /home/pi/c1/'`.

On the Mac, create the archive root now — it does not exist yet, and `scp` will not create it:
`mkdir -p /Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/c1`.

Record `command -v exiftool ffprobe` (the analyzer shells out to both) and `df -h /tmp` — if
`/tmp` is a tmpfs, the multi-MB session log competes for the same RAM the encoder buffers
into, which is itself a confound worth knowing about before you interpret buffer pressure.
Then run `python3 /home/pi/c1/analyze_cinepi_media.py /media/RAW --json | head -8` and record
its `"tools"` block (`{"ffprobe": …, "exiftool": …}`) verbatim in the ledger — the block is
emitted whether or not any take is present, so this does not depend on a 0.3 take still being
on disk. It is the live proof of which analyzer fields will be populated for the rest of the
campaign. Neither binary gates a
pass/fail rule here — DNG count, index range and sequence gaps come from the analyzer's
stdlib path, and WAV duration from the `wave` snippet above — so if one is absent, record it
as tooling state, not as a media defect. **Do not install either**; installing packages is not
a sanctioned intervention.

0.10 **Predictions — written before Stage 1 starts.** One row per selected mode, **Stage 1
only**: the `A × S1` / `B × S1` / `C × S1` rows already in the ledger's 0.10 table (if 0.2
selected no 25 fps control mode, mark row C `n/a`). Stage 2's predictions are a separate table
filled after the Stage 1 review — do not pre-fill it here. Per row: predicted outcome class +
audio verdict, with one sentence of reasoning anchored in the 0.3–0.7 numbers. For any mode
whose data rate is within 15 % of the 0.4 **trailing** sustained speed, the reasoning must name
**which** watchdog you expect to fire first (write-backlog 90 %, system RAM 80 %, or the
encoder pool) and cite the measured `buffer_size`, `runway_s` and RAM figures from 0.7 that
support it.

`session-stop`. Commit the ledger (`plan/results only, named files`).

**Phase 0 STOP-check (conditional — it fires only when triggered, unlike the scheduled Gates 1
and 2, but when it fires it is just as hard a stop):** if any of 0.1–0.9 contradicts the "known
context" section in a way that changes the test design (different sensor, exFAT instead of
ext4, missing mic, throttling at idle, idle temp already ≥ 70 °C, or a `free -b` total
materially different from the 4048 MB last measured — a 2 GB unit changes every runway and
every prediction), report the contradiction to the operator with its ledger row and source
command, then **end your turn**. Do not begin Stage 1 in the same turn — Stage 1 resumes only
on the operator's explicit go.

---
## Stage 1 — three 5-minute takes per mode

Take IDs: `S1-<mode-letter><rep>` (e.g. `S1-A1`, `S1-A2`, `S1-A3`, `S1-B1`, …). A rep that
aborts and is re-run gets a **new** id with an `r<n>` suffix (`S1-A1` → `S1-A1r1`) and its own
ledger row directly beneath the aborted one. The analyzer JSON (a truncating `>` redirect) and
the Mac archive directory are both keyed on the take-id, so reusing an aborted take's id
overwrites its evidence.

Per-take procedure (identical every time):

1. `session-start`. The helper blocks internally until `Storage pre-roll complete`, then
   settles; do not add your own poll loop. **Check the exit code, and never retry blindly.**
   A non-zero exit with `Timed out waiting for storage pre-roll completion.` does **not** mean
   a hung session: the marker is emitted only after a pre-roll actually records, and pre-roll
   returns early without it when `/media/RAW` is not mounted. The session is also left
   **running** — the helper writes the pid file before it waits — so `session-send "rec f …"`
   is still accepted, logs `No disk.`, and never records. Diagnose before doing anything else:
   `pi_ssh.sh 'findmnt -no SOURCE,FSTYPE /media/RAW'`.
   - No output → `/media/RAW` is not mounted. `session-stop`, report to the operator, and end
     your turn. Each blind retry burns the full 120 s `--ready-timeout-seconds`.
   - The NVMe + ext4 recorded in 0.4 → a real startup fault. `cinemate_dev.py stop`, retry
     once, keeping the helper's stderr tail as evidence. A second failure is a STOP: report
     and wait.
2. Re-apply the two session-scoped pins. Both are re-read at process start, so `session-start`
   can undo them, and a missed re-issue silently rewrites the mode or the fps under you:
   - `set dynamic resolution 0`, then confirm `redis-cli GET dynamic_resolution_enabled`
     reads `0`. Dynamic resolution is on by default (the key defaults to on when unset), and
     while it is on `set resolution <n>` is silently replaced by the largest mode that
     sustains the *current* `fps_user` — and `set fps` runs the same substitution, so it can
     move the mode after you set it.
   - `set fps free 1`. This one is a controller flag, **not** a Redis key — confirm it from
     the session log — grep the prefix **`FPS Free`** only (it logs `set to 1`, and the wording
     differs by branch) — and from the step 4 readback.
3. Set the mode: `set resolution <n>` → verify the three `resolution_target_*` readbacks
   match the plan (renumbering gotcha — re-check every session).
4. Set fps: `set fps <test fps>`, then **read `fps` back and confirm it equals the target
   exactly**, then **re-read the three `resolution_target_*` values** — setting fps can move
   the resolution. Without free mode the value snaps to `[25, 33, 50]` capped at `fps_max`
   and the take is invalid (see "Known context"). Record both readbacks in the ledger. If
   either disagrees with the plan, do **not** re-issue the same command — the substitution is
   deterministic and will repeat. Re-check the step 2 pins; if both are correct and the
   readback still disagrees, STOP and report before recording anything. Cross-check the real
   cadence later from the sampler's `framecount` deltas, never from `fps_actual`.
5. Pre-take snapshot: `df -B1 /media/RAW` free bytes; `vcgencmd measure_temp`; confirm free
   space ≥ required (0.5). If temp > 70 °C, wait — poll every 60 s, and if it has not cleared
   after 10 minutes, stop and report rather than recording hot. Never start a take hot.
6. Start the sampler with a per-take pidfile, after confirming none is running
   (`pgrep -f c1_sampler.sh` empty):
   `nohup /home/pi/c1/c1_sampler.sh /home/pi/c1/samples/<take-id>.csv /tmp/c1_<take-id>.pid >/dev/null 2>&1 &`
7. Capture the log anchor, then start the take:
   `A=$(wc -l < /tmp/cinemate_cli.log)`, then `session-send "rec f <frames_5min>"`.

   **Confirm the take was armed before you start counting.** The region after the anchor must
   show the echo `Received: rec f <N>` and then
   `Armed exact frame-limited stop: <N> additional frame slots …`. If the `Armed` line never
   appears the frame limit was not set — abort rather than let a take run unbounded. `No disk.`
   there is step 1's unmounted case; `rec ignored` means the previous flush had not finished.

   **The anchor is mandatory even in a fresh session.** `session-start` truncates the log, but
   storage pre-roll then calls `stop_recording()` itself, so a pre-roll `Stopped recording` is
   already in the log before your first `rec`. A whole-log grep — including the helper's own
   `roundtrip-take` wait — reports a stop that has not happened.

   Poll every 60 s with exactly these two cheap reads, and send nothing else to the session
   while recording (one exception: the stall watchdog below):
   - `tail -n 1 /home/pi/c1/samples/<take-id>.csv` — one line carrying `framecount`, `buffer`,
     `temp` and `memory_alert`. A rising `framecount` is the liveness signal.
   - `tail -n +$((A+1)) /tmp/cinemate_cli.log | grep -nE 'Exact frame-limited stop reached|Stopping recording|Stopped recording|No disk|rec ignored'`

   **Do not `session-tail` a window during a take.** cinepi-raw logs `DNG written:` per frame
   and cinemate logs `Frame <n> ┃rec=…s` and `Changed value: last_dng_cam0 = … ┃RAM: NN%` per
   frame, so a 5-minute take is roughly 3 lines per recorded frame — 10,000–22,500 lines. Five
   polls of `session-tail 100` across nine takes would exhaust the context before Stage 1 ends,
   and the Gate 1 summary would then be written from a compacted transcript. Warnings between
   polls are caught by step 10's whole-file grep, not here.

   **Liveness is those two reads only.** Never judge it from `session-send`'s exit code or
   from `status`'s `Helper session: running` / `Ready: True`. Both test the PID of the wrapper
   pipeline (`tail -n0 -f /tmp/cinemate_cli.in | bash -lic cinemate`), which outlives a dead
   cinemate — `tail -f` stays blocked on a file nobody writes, so it never takes SIGPIPE, and
   `Ready` is a grep over the log file, so it never goes false. If two consecutive polls show
   a flat `framecount` **and** no new anchored log lines, settle it on the Pi:
   `pgrep -af '/home/pi/cinemate/src/main.py|cinepi-raw'`. Processes present = a stall — keep
   polling and record it as buffer pressure. Processes absent = the session died — go to the
   abort rule in the sequencing rules below.

   **Stall watchdog (mandatory).** `rec f` has no wall-clock timeout. The stop is driven only
   by incoming `cp_stats` messages, so if cinepi-raw stalls, `framecount` freezes and the take
   rolls indefinitely — and the RAM/buffer guard cannot save you, because it reads the same
   frozen Redis keys. Before starting, write down
   `deadline = frames_5min / <test fps> × 1.2 + 60 s`. If it passes with no stop:
   a. Record the last `framecount`, `buffer`, `is_writing_buf` and `is_recording`, plus whether
      `framecount` was rising.
   b. **Read `is_recording` first.** Send a bare `rec` **only if it is 1** — `rec` is a toggle,
      and sending it at 0 starts a new unbounded take that fills the drive. If it is already 0,
      go straight to step 8's flush wait.
   c. Classify `ABORTED-OTHER` and name the stall: `framecount` frozen = cinepi-raw pipeline
      stall; `framecount` still rising = frame-limit accounting or target mismatch, which is a
      separate reportable finding for the gate.
   d. Continue through steps 8–13 anyway, so the partial take is still flushed, analysed and
      archived, then treat it as this mode's rep-1 failure under the sequencing rules.
8. Wait in three stages, and **do not gate on `is_writing`** — `mediator.py` forces it to 0 the
   moment recording intent goes off and only ever re-raises it *while* recording, so it is
   always 0 here and proves nothing.

   **8a — the take really stopped.** The anchored region must show
   `Exact frame-limited stop reached: slot <x>/<N>; stopping recording.` **followed by**
   `Stopped recording`, **and** `redis-cli GET is_recording` must read `0`. A `Stopped
   recording` with **no** preceding `Exact frame-limited stop reached` means the take did not
   end on its frame limit — look for a guard warning immediately above it:
   `RAM frame buffer NN% ≥ 90%! Stopping recording.` (write-backlog) or
   `RAM NN.N% ≥ 80%! Stopping recording.` (system RAM). **Only with one of those lines present
   is the take `AUTO-STOP-GUARD`; a `Stopped recording` with no guard line at all is
   `ABORTED-OTHER`**, per the outcome-class table — do not infer a guard that left no trace.
   cinepi-raw's pool stop logs `RAM pool exhausted — recording stopped` instead, leaves
   `memory_alert` untouched, and never reaches `Stopped recording` — it presents as a hang.

   **8b — flush idle.** Poll until `is_writing_buf`, `is_buffering` **and** `buffer` all read
   0, twice in a row 2 s apart. All three: cinemate's own flush gate
   (`redis_listener.py :: _storage_is_still_flushing`) checks `is_writing_buf`, `is_buffering`
   and `is_writing` plus a `framesInFlight` fallback, and `is_writing_buf` is raised on the
   stop edge only if the *last* stats message already showed frames in flight — a stale zero
   snapshot leaves it at 0 while frames are still draining.

   **8c — post-take analysis finished. This is the real gate.** `missing_frame_count` and
   `drop_frame_during_last_take` (step 10) are written by `analyze_frames()`, which runs
   *after* the flush gate, and `missing_frame_count` is never cleared at record start — so any
   flush-only gate releases you early and you silently record the **previous** take's number.
   Poll the anchored region every 5 s until both of
   `Calculated expected number of frames:` and `Actual number of recorded frames:` have
   appeared, followed by exactly one verdict line:
   `✓ All frames accounted for.` · `Frames within final tolerance:` · `Sensor ran fast:` ·
   `Frame count low:` · `Skipping frame-sync warning because FPS or resolution changed during
   this take.`
   `Waiting for buffered frames to finish writing before frame-sync analysis.` appearing first
   is normal — the analysis is queued behind the flush. If
   `Buffered frame flush did not go idle within 30.0s; analyzing with stable on-disk count.`
   appears, **record it in the ledger as a finding**: the on-disk count was taken while writes
   were still draining.
   Cap the wait at 90 s (cinemate's own flush timeout is 30 s, plus the stable-count settle on
   a 3,000–7,500-file directory). If nothing terminal has appeared by then, do **not** read the
   Redis verdict keys: record them as `UNVERIFIED — analysis line absent`, classify the take
   from the analyzer JSON alone (`dng.count` vs frames requested, `missing_indices`), and log
   the anomaly — a missing analysis is itself a finding.

   **Only then** stop the sampler: `kill $(cat /tmp/c1_<take-id>.pid)`, and confirm it is gone
   (`pgrep -f c1_sampler.sh` empty). Stopping it at the flush edge truncates the buffer-decay
   tail that step 13 asks you to describe.
9. **Resolve the take directory once, then use it everywhere.** `last_dng_cam0` holds the
   path of the last written DNG, so its parent is the take dir:
   `TAKE_DIR=$(dirname "$(redis-cli GET last_dng_cam0)")`. Assert all three before touching
   anything:
   - The key is non-empty and is **not** the literal string `None` — pre-roll writes `None`
     back when there is no prior take, and `dirname None` is `.`, so step 12 would `rm -rf`
     the ssh working directory.
   - `$TAKE_DIR` starts with `/media/RAW/CINEPI_`, ends in `_cam0`, and `[ -d "$TAKE_DIR" ]`.
   - It is *this* take: its mtime falls inside this take's window and its basename is not one
     already recorded as deleted in the ledger. On a take that wrote zero DNGs the key still
     points at the previous take.
   If any assertion fails: classify `ABORTED-OTHER`, archive whatever exists, **delete
   nothing**, and report to the operator before starting the next take. Steps 10–12 all use
   `$TAKE_DIR`; never re-derive it, never use a wildcard, never `ls -t`.
10. Evidence capture, before anything is deleted. Create the take's archive directory first —
    `scp` will not create it and fails outright into a missing path:
    `mkdir -p /Users/patrikeriksson/Documents/cinemate/development/pi-test-takes/c1/<take-id>`
    - **Copy the whole session log — a tail is not enough.** cinepi-raw emits one
      `DNG written:` INFO line **per frame**, so a 5-minute take at 25 fps produces ~7,500 of
      them and ~22,500 lines in total; `session-tail 400` would cover only the last few
      seconds and would silently hide exactly the mid-take failures this campaign exists to
      find. Copy it with
      `pi_expect.exp "$PI_PASSWORD" scp … pi@cinepi.local:/tmp/cinemate_cli.log <archive>/session-log.txt`.
      **Copy it before the next `session-start`, and before any `cinemate_dev.py stop` or
      `session-stop`** — all three run `rm -f /tmp/cinemate_cli.log`, and the take's only
      full record goes with it.
      Then grep the copied file and record every hit **with its line number**:
      ```
      grep -Ein 'write.*fail|FAILED|Error writing to file|Capture read failed|WAV writer|silent frame|shortfall|drop|SYNC|memory|index gap|DNG index slot|Missing frames|Frame count low|Sensor ran fast|Stopping recording|RAM pool exhausted|did not go idle|helper not found|falling back to plain arecord|exited before capture actually started' <archive>/session-log.txt
      ```
      Match ASCII substrings only — the real warnings contain `≥` and `—`, which are fragile
      to type into a shell pattern. To place a hit inside the take, quote the nearest
      **preceding** `Frame <n> ┃rec=<secs>s` line: that gives the exact frame and elapsed
      record time. Do not infer position from line-number arithmetic — threads interleave, so
      3 lines/frame is an average, not a stride.
      Record the copied file's `wc -l` beside the hit count, so a genuine "0 hits" is
      distinguishable from a truncated copy: expect roughly 1–3 lines per recorded frame. Far
      below that means the copy is incomplete — re-copy before classifying the take. If there
      are no hits, write "none" explicitly; that is the evidence behind `COMPLETE-CLEAN` and
      an audio `PASS`.
    - Sampler maxima, from the stopped CSV (`temp` is field 12, `buffer` is field 2):
      `awk -F, 'NR>1{if($12+0>t)t=$12; if($2+0>b)b=$2} END{print "temp_max="t, "buffer_max="b}' /home/pi/c1/samples/<take-id>.csv`
      → the ledger's **temp max** and the max half of **buffer max / shape**. Step 5's
      pre-take temp is a go/no-go check only; never write it into `temp max`.
    - Redis — **only after 8c**: `framecount`, `missing_frame_count`,
      `drop_frame_during_last_take`, `memory_alert`, `last_dng_cam0`, `buffer`, `buffer_size`.
      The first two verdict keys fail in opposite directions when read early:
      `missing_frame_count` is written only by the post-take analysis and is never cleared at
      record start, so an early read returns the **previous** take's number (false alarm,
      likeliest right after an `AUTO-STOP-GUARD` take); `drop_frame_during_last_take` **is**
      cleared to 0 at record start and only re-raised by the same analysis, so an early read
      returns a clean-looking 0 (false negative, which no other ledger column catches).
      Cross-check before writing the row: `expected − actual` from the two 8c lines must equal
      `missing_frame_count`. If it does not, the read was early — re-read, and if they still
      disagree prefer the log numbers and note the discrepancy.
    - `dmesg | tail -150` → append any storage/USB/ALSA lines to the archive.
    - On-Pi analysis:
      `python3 /home/pi/c1/analyze_cinepi_media.py "$TAKE_DIR" --json > /home/pi/c1/results/<take-id>.json`
    - WAV duration check (snippet above) on the take's WAV.

    **Never redirect helper or `pi_ssh.sh` stdout raw into an evidence file.** With
    `PI_PASSWORD` set they run `ssh` under `pi_expect.exp` on a PTY, so the stream carries an
    injected `spawn ssh …` line, the `pi@cinepi.local's password:` prompt line, and CRLF on
    every line. `scp` the file instead, as above.
11. Archive to the Mac, into the directory created in step 10
    (`development/pi-test-takes/c1/<take-id>/`): the analyzer JSON, the sampler CSV,
    `session-log.txt`, the WAV, and the first 3 + last 3 DNGs. Always put a trailing `/` on
    the destination, so a stray copy can never land as a file named after the directory.
    Verify the copies are non-empty and the JSON parses (`python3 -m json.tool`) **before**
    proceeding.
12. **Only then** delete the take: `rm -rf "$TAKE_DIR"` — the directory resolved in step 9,
    never a wildcard, never a freshly re-derived path, and only after step 11 verified the
    archive.
13. Ledger: one row in the stage's take table + a short per-take note in that stage's
    "Per-take notes" list (outcome class, audio verdict, buffer-pressure shape, the step 10
    grep hits — verbatim lines, or "none" — verdict vs prediction, and the take's archive
    path; the full log stays in the archive's `session-log.txt`). Commit after each mode's
    three reps. **Commits run in the repo, not the working directory** — the session's cwd
    `Documents/cinemate` is not a git repo; use
    `git -C /Users/patrikeriksson/Documents/cinemate/cinemate`.

Sequencing rules:

- Run order: C (control, if present) → B → A, three reps each, so the easiest mode
  establishes the healthy baseline shape of the sampler curves first. This order is exactly
  why step 2's dynamic-resolution pin matters: after the mode-C takes leave `fps_user` at 25,
  `set resolution <B>` with dynamic resolution on lands back on the mode that sustains 25 fps
  — mode C itself.
- If rep 1 of a mode is `AUTO-STOP-GUARD` or loses > 1 % of frames: run exactly one
  confirming rep, write the diagnosis, and move to the next mode — don't burn the third rep
  on a reproduced failure.
- Between takes, return the rig to a known state before the next `rec`. Poll every 30 s with
  `vcgencmd measure_temp` and `awk '/^Dirty:/{print $2" kB"}' /proc/meminfo`. **`/proc/meminfo`
  is in kB — the ~50 MB gate is ~51200 kB**, the same unit as the sampler's `dirty_kb` column.
  - **`Dirty` under ~51200 kB.** This should clear within about a minute: recording has
    stopped and step 8 already confirmed the flush idle, so nothing is adding to the backlog
    and kernel writeback only has to drain it. If it is still above ~51200 kB after
    **5 minutes**, that is an I/O fault, not thermal soak. Capture `dmesg | tail -150` and
    `grep -E '^(Dirty|Writeback):' /proc/meminfo` to the archive, log it in the ledger as a
    durability-relevant finding, and do not start another take on a drive that is not retiring
    its writes — report to the operator and end your turn.
  - **Temp < 70 °C.** Idling the Pi is the only cooling action available to you. If temp is
    still > 70 °C after **10 minutes** of idle, it will not get there on its own. Record the
    last three readings plus the completed/remaining take list, tell the operator — paste-ready,
    same pattern as the STOP gates — that the rig needs physical cooling, and end your turn.
    Resume at the next un-run take when they say so.
- If a session dies mid-take: classify `ABORTED-OTHER`; **capture the session log first**
  (step 10's scp — `cinemate_dev.py stop` deletes `/tmp/cinemate_cli.log`); **kill the sampler
  next** (`pkill -f c1_sampler.sh`) — the abort path never reaches step 8 and
  `cinemate_dev.py stop` does not touch samplers, so it would otherwise keep appending to that
  take's CSV for the rest of the campaign; archive the partial CSV under the aborted take-id;
  `cinemate_dev.py stop`; then restart that rep **once** under a new `r<n>` take-id. Death is
  established by the `pgrep` check in step 7, never by the helper's reported session state. A
  crash is `ABORTED-OTHER` even if `memory_alert` is set: a guard stops the *take* and leaves
  cinemate alive and logging (`Stopping recording.` then `Stopped recording`), so a log that
  simply went silent is a crash, not `AUTO-STOP-GUARD`.
- Stage 1 does not have to be one turn. If context runs short mid-stage, finish the take you
  are in, complete its archive and ledger row, commit, tell the operator which take IDs are
  done and which remain, and end your turn. On resume, rebuild state from `RESULTS.md`,
  `/home/pi/c1/results/` and the archive — never from recollection of earlier takes. A resumed
  Stage 1 is fine; a Stage 1 summary written from a compacted transcript is not.

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
(`python3 ~/.claude/skills/cinemate-dev/scripts/cinemate_dev.py build-raw` if cinepi-raw
changed), and record the new commits and the rebuild on the Stage 2 preconditions line in
`RESULTS.md` — Stage 2 then doubles as the fix re-verification.

`build-raw` runs `sudo meson install` and replaces `/usr/local/bin/cinepi-audio-capture`, but
**the RT grant is not on the binary** — it is the limits.d drop-in plus `audio` group
membership (see 0.6), so a rebuild cannot revoke it. Do **not** attempt 0.6's `ps` check at
idle before Stage 2: nothing is elevated when idle, so it reads as a failure on a healthy rig.
Verify the grant on the **first Stage 2 take** from the session log alone — the anchored region
must show `Capture thread elevated to SCHED_FIFO priority 80` and `Capture thread pinned to
CPU 3 (of 4 available)`. Record that line on the Stage 2 preconditions line. If instead
`Could not set SCHED_FIFO capture priority` appears, stop after that take, apply 0.6's limits.d
remedy, and re-run the take under an `r1` id.

Protocol = Stage 1's per-take procedure with:

- `frames_10min = test fps × 600` — the Phase 0.5 test fps, still readback-verified on every
  take. Recompute the space feasibility: take sizes double, so a mode that fit in Stage 1 may
  not fit now. Record the recompute in the Stage 2 **"Feasibility recompute for 10-minute
  takes"** table in `RESULTS.md` (frames, take size, free needed = size × 1.2, free at check,
  feasible?) — do not carry the Phase 0 five-minute numbers over.
- Two reps per mode (`S2-A1`, `S2-A2`, …), same run order, same abort rule after rep 1.
- Stage 2 rows and per-take notes go in the **Stage 2** take table and the Stage 2 "Per-take
  notes" list in `RESULTS.md` — never appended to Stage 1's.
- Any mode that was `INFEASIBLE-ON-THIS-RIG` or reproducibly failed in Stage 1 **without** a
  merged fix addressing it: skip, and say why in the ledger — re-running a known failure
  twice as long produces no new information.
- Prediction rows for Stage 2 must be written (or explicitly re-confirmed) **after** the
  Stage 1 review outcomes are known and before the first Stage 2 take.

### STOP GATE 2 — final Fable review

Fill the Stage 2 summary block + the campaign-level conclusion (per mode: is the
drop-frame goal met? is the audio-sync goal met? what is the single limiting factor?).
Draft the `cinemate-handbook/lessons/hardware-log.md` entries for every operator-confirmable
finding **into the ledger** — the "Proposed … entries" block at the end of the Stage 2
section — using that file's entry format: a dated `## YYYY-MM-DD — <one-line subject>`
heading plus **Tested / Worked / Did not work / Why / Confirmed by**. Do not edit or commit
anything under `cinemate-handbook/`: it is a separate repo, and an entry lands there only
after the operator confirms the finding — which is what the Fable review is for. Commit
everything, then hand back to the operator for the final Fable-thread review with the same
paste-ready message pattern as Gate 1.

---

## Ledger discipline (applies to every phase)

- `RESULTS.md` is append-per-phase: never rewrite a filled row; corrections get a dated
  strike-through note.
- Every number in the ledger carries its source (command or file). Same convention as
  `cinemate/system-review/PI-RESULTS-2026-08-25.md` on this branch — skim it if you want a
  worked example of the format. That file belongs to the system review, which C1 is **not**
  part of: read from `cinemate/system-review/` if useful, never write to it.
- The `fps target` / `fps readback` columns in the Stage 1/2 take tables come from the mode's
  **Phase 0.5 test fps** and that take's Redis readback, cross-checked against the
  **`framecount` slope** in the sampler CSV — never from `fps_actual` (dead-emit history) and
  never from the take folder's `F##` field, which the analyzer JSON exposes as
  `parsed_name.ff`. That field is a sub-second timecode frame index (cinepi-raw
  `cinepi/utils.cpp:74-86`, `llround(µs × fps / 1e6) % fps`), not a frame rate: it ranges
  `0 … fps−1`, so at this campaign's ≤ 25 fps it produces plausible-looking values that are
  silently wrong. Real takes from one rig at one fps read `F03`, `F31`, `F45`, `F47`.
- Commit messages: `c1: <phase/take-ids> — <one-line outcome>` on
  `feature/dev-track`, named files only, no push without asking.
- The plan table mirrors this ledger: whenever you change the **Status** line at the top of
  `RESULTS.md` (Phase 0 complete, STOP GATE 1, STOP GATE 2), edit the **State** cell of the
  **C1 row only** in `dev-track/README.md` to match, in the same commit — same
  `git -C /Users/patrikeriksson/Documents/cinemate/cinemate` form as step 13:
  `add dev-track/README.md dev-track/C1-longtake-stability/RESULTS.md`. That cell is
  overwritten in place — the append-only / strike-through rule above governs `RESULTS.md`,
  not the plan table. Leave every other row alone.
