# C0 Pi re-check — kickoff prompt for the executing session

C0 is already implemented, merged and hardware-verified once (`e54e691b`, PR #152,
2026-08-26). This is **not** an implementation session and **not** a re-run of the original
destructive checklist. It is a regression re-check plus the capture of two facts the first
run never established.

Paste everything below the line into a fresh Sonnet thread with the working directory
`/Users/patrikeriksson/Documents/cinemate`.

---

Run the C0 Pi re-check for CineMate. Invoke the `/cinemate-dev` skill first, then open
`cinemate/dev-track/C0-format-drive/PI-RECHECK-PROMPT.md` on branch `feature/dev-track` and
follow it. Read `cinemate/dev-track/C0-format-drive/PLAN.md` for what C0 is and what its
first hardware run did and did not prove.

## Why this session exists

C0 added a format-drive control to the settings editor's RAW pane. It passed a full
destructive checklist on 2026-08-26 at commit `e54e691b`, off `dev` `953477e8`. Since then
`settings_editor.py` and `settings_editor.html` have both changed several times —
control-row layout, phone/tap-target stacking, the dotted action/command rule, the
`free mode` → `free stepping` rename, and a hardening of the *generic* action catalogue's
`format_drive` entry to `"no_arg": "required"` (a blank argument used to silently format as
exFAT). **The format endpoint itself is untouched; the pane around its control is not what
was tested.**

Two things the first run explicitly did not establish, both recorded as unknown:

1. **Which fstype string NTFS actually reports.** The endpoint accepts `ntfs`, `ntfs3` and
   `fuseblk` precisely because it is driver-dependent. Nobody wrote down which one appeared.
2. **How long a format holds the dispatch lock.** The whole format runs under
   `_dispatch_lock`, so every other CLI/serial/web command reports `busy` meanwhile. The
   duration was never measured.

Capture both. They are the main new value in this sitting.

## Ground rules

1. **Measurement and verification only. Change no source code**, in either repo. If you find
   a defect, record it in the results file and raise it — do not fix it. The one thing you
   may change is the state of the scratch drive, which is the point.
2. **DESTRUCTIVE.** Every format erases a drive completely. Before the first format, confirm
   with the operator **in writing in this thread** that the drive mounted at `/media/RAW` is
   a scratch drive whose contents are expendable. If `/media/RAW` holds takes anyone wants,
   STOP and ask. Do not proceed on assumption.
3. **The Pi stays on `dev`.** Do not switch branches or rebuild anything on the Pi. Record
   the exact Pi-side commit during preflight and confirm it contains `e54e691b`
   (`git -C /home/pi/cinemate merge-base --is-ancestor e54e691b HEAD && echo yes`).
4. **Report to the repo after every phase.** See "Reporting" — this is how the work is
   monitored; a phase that is not committed and pushed did not happen.
5. `PI_PASSWORD` lives only in the environment. Never write it to any file.
6. Stop and ask the operator if a prediction fails in a way that suggests a real regression,
   rather than working around it.

## Tools

- Pi shell / file transfer: `~/.claude/skills/cinemate-dev/scripts/pi_ssh.sh '<command>'`
  (uses `PI_PASSWORD` when SSH keys are unavailable). The helper `cinemate_dev.py` has no
  generic remote-exec.
- Managed session for the recording interlock: `cinemate_dev.py`
  (`stop`, `session-start`, `session-send`, `session-tail`, `session-stop`). Do **not** use
  `roundtrip-take`.
- Pi: `pi@cinepi.local`, repo `/home/pi/cinemate`, RAW root `/media/RAW`.
- Settings editor: `http://cinepi.local:5000/settings-editor/` → **RAW files** tab. Port 5000
  is the web GUI; **8000 is cinepi-raw's MJPEG preview**, a different service.

## What shipped, so you know what "working" looks like

| Piece | Detail |
|---|---|
| Endpoint | `POST /settings-editor/api/raw/format`, JSON body `{"filesystem": "ext4"\|"exfat"\|"ntfs"}` |
| Responses | 200 ok · 400 invalid filesystem · 409 refused while recording · 503 no dispatcher, or `busy` · 500 dispatched but the drive did not come back as the requested fs |
| Server log | `Dispatching 'format <fs>' from the settings editor` |
| Control | On the **active** storage card only (`active: true`, i.e. `/media/RAW`). A `select` (`[data-format-fs]`, exFAT preselected) + a `Format…` button (`[data-format-go]`), wired by `wireStorageFormat(card, s)` |
| Confirm modal | `Format <label> (<device>, <size>) as <fs>? Every take on it is permanently erased.` |
| Toast on start | `Formatting — this can take a couple of minutes. Other commands will report busy until it finishes.` |
| Success check | The endpoint ignores the dispatch result (the dispatcher discards handler return values) and instead reads which filesystem is mounted at the active root after `format_drive()` remounts |

## Phases

Fill `PI-RECHECK-RESULTS.md` as you go. **State each prediction before you run the step**,
then the verdict (CONFIRMED / CONTRADICTED) after — the hardware-session method from the
handbook. A verdict with no prior prediction is worth much less.

### P0 — Preflight

- Pi reachable; `uname -r`; `free -b` (record `MemTotal` — the board is swappable).
- `git -C /home/pi/cinemate log --oneline -1` and the `merge-base --is-ancestor` check above.
- Is cinemate running? Which unit/session owns it?
- `findmnt -no SOURCE,FSTYPE,SIZE /media/RAW` — device, **current filesystem**, size.
- `ls /media/RAW` and a take count. **Get the operator's written go-ahead** (rule 2).
- Fetch the RAW pane and confirm the endpoint exists:
  `curl -s -o /dev/null -w '%{http_code}' -X POST http://cinepi.local:5000/settings-editor/api/raw/format -H 'Content-Type: application/json' -d '{"filesystem":"vfat"}'`
  → expect **400** (invalid fs, nothing destroyed). This is the safe liveness probe; use it
  before anything destructive.

### P1 — Regression spot-check (the reason this session exists)

Does the control still render correctly after the settings-editor churn? Check the served
HTML/JS, and have the operator eyeball the pane on both a desktop browser and a phone.

- Is the format row present on the active card, and only on the active card?
- Is the select populated exFAT / ext4 / NTFS with **exFAT preselected**?
- Is it styled — not an unstyled fallback? (`card-help` guidance line present, button reads
  as a danger control, tap targets sane on the phone after PR #160's work.)
- Does the confirm modal appear and name label, device, size and chosen filesystem?
- **Cancel the modal once and confirm nothing is sent** (no `Dispatching 'format` line in the
  log). This is the cheapest proof the are-you-sure step is real.

### P2 — Format cycle, ordered deliberately

Run **NTFS → exFAT → ext4**, in that order, from the browser.

- **NTFS first** — this is where you capture unknown #1: after it remounts, record the exact
  string from `findmnt -no FSTYPE /media/RAW` **and** the `filesystem` value the pane shows
  (they come from different places — psutil vs findmnt — so record both, verbatim).
- **exFAT second** — the default selection; confirms the common path.
- **ext4 last** — deliberate: ext4 is C1's preferred filesystem for sustained recording, so
  this leaves the drive in the exact state the C1 campaign wants to start from.

For each: time it (unknown #2 — see P3), confirm the card reappears with label `RAW`, the
requested filesystem, full capacity and 0 takes, and confirm the toast text.

### P3 — The two unknowns

- **Dispatch-lock duration.** Time each format wall-clock from the moment the confirm is
  accepted to the toast. During **one** of them, from a second shell, send a harmless command
  through the CLI/serial path (e.g. `set iso 800`) and record (a) that it reports `busy`,
  (b) roughly when it starts succeeding again. Record the lock duration per filesystem —
  mkfs cost differs a lot between exFAT and ext4.
- **NTFS fstype string** — captured in P2. Say plainly which of `ntfs` / `ntfs3` / `fuseblk`
  appeared, and from which command.

### P4 — Interlocks

- **409 while recording.** Start a recording via a helper-owned session, attempt a format
  from the browser, expect the 409 toast, and confirm **the recording is undisturbed** (it
  keeps writing frames and stops cleanly). This is the interlock that stops `fuser -km` from
  killing a live writer — the most safety-relevant check here.
- **Recovery.** After the busy period in P3, confirm normal dispatch resumes (a plain
  `set iso 400` lands and reads back).
- **`storage-automount.service`.** After the last format, watch for a mount fight — the
  service also owns `/media/RAW` while `SSDMonitor` remounts. `journalctl -u
  storage-automount --since '-5 min'` plus a stable `findmnt` a minute later.

### P5 — Handoff state for C1

Leave the drive **ext4, empty, mounted at `/media/RAW`, label `RAW`, full capacity**, and
record the free bytes. Say explicitly in the results file whether the rig is ready for C1's
Phase 0, or what is in the way.

## Reporting — how this is monitored

The operator is watching through the repo, not this thread.

- Write into `cinemate/dev-track/C0-format-drive/PI-RECHECK-RESULTS.md` on branch
  `feature/dev-track`.
- **Commit and push after every phase**, not at the end. Someone else may push to this branch
  while you work, so before each push:
  `git -C /Users/patrikeriksson/Documents/cinemate/cinemate pull --rebase` then push.
- Commit message prefix **`c0-pi:`** — e.g. `c0-pi: P2 — NTFS reports <string>, formats clean`.
  The prefix is how the monitoring session finds your commits.
- Stage that **one file only**. Never `git add -A` in this repo (LFS pointer trap: unsmudged
  `docs/images/*.png` pointers would be committed over real images).
- The working directory `Documents/cinemate` is **not** a git repo — the repo is
  `Documents/cinemate/cinemate`. Use `git -C`.
- Push over HTTPS: `git push https://github.com/Tiramisioux/cinemate.git feature/dev-track`.
- If a phase fails or you stop early, commit that too, with the failure recorded. A silent
  gap is indistinguishable from a crash.

## Done means

1. All five phases recorded in `PI-RECHECK-RESULTS.md`, each with its prediction and verdict.
2. Both unknowns answered in plain words, or explicitly marked still-unknown with the reason.
3. Every phase committed and pushed with the `c0-pi:` prefix.
4. The drive left in C1's expected starting state (P5), and that state stated.
5. A short close-out message to the operator: what held, what did not, and whether C0 is
   still good after the settings-editor churn.
6. **Draft** a dated entry for `cinemate-handbook/lessons/hardware-log.md` in the results
   file's final block — Tested / Worked / Did not work / Why / Confirmed by. Do **not** edit
   or push the handbook repo; the operator decides when that lands.
