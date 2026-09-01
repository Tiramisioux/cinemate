# Kickoff prompt for the implementing session

Note: single repo (cinemate), five commits, no cinepi-raw changes. **The branch already exists**
— `feature/clip-playback`, two commits, local and unpushed, cut off `dev` @ `714ef7b4` on
2026-08-27 and now 1381 commits behind. This session does not build the pane; it lands the one
piece of C9 that is already correct, brings the branch to current `dev`, fixes six defects that
only appeared when the plan was re-grounded, and writes the harness the hardware session needs.
All ten gates are unrun and belong to the operator's Pi session, not this thread.

Paste everything below the line into a fresh Sonnet thread.

---

Bring C9 (clip playback) to the state its hardware gates can actually run from: the
`conform_frame_rate` docs correction landed on a branch that is not one laptop, `feature/clip-playback`
rebased onto current `dev` and green, six recorded defects fixed, the drift check the step owes
ADR-001, and `tools/playback_bench.py` — the harness G1, G2 and G9 are written against.

The plan and its gates are at:
`/Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C9-clip-playback/PLAN.md` and
`GATES.md` beside it, on branch `feature/dev-track`.

Read both in full before touching anything, and read
`/Users/patrikeriksson/Documents/cinemate/cinemate-handbook/README.md` plus
`orientation/the-traps.md` and `architecture/gui-state-model.md` first — the playback pane is
**file-backed**, which puts it on surface 3 with the settings editor and deliberately not in
`populate_values()`/Socket.IO. The plan was re-grounded against the repo on 2026-09-01 and every
correction in it carries a file:line citation: implement them, don't relitigate. Where a citation
and the current source disagree, the source wins — say so, and say where.

**Before you write anything, answer one question and report it.** Read the decode path in
`src/module/app/dng_preview.py` and establish whether it applies the DNG `LinearizationTable` and
subtracts `BlackLevel` in the **table's output domain**. `docs/cinemate-log.md:63` records what
happens if it does not: a log clip renders **solid black**, because a linear-domain BlackLevel is
subtracted from data that never reaches it. If the table is not applied, that is a seventh defect
and it is the most important one — fix it in C9.3 and tell me, rather than letting G9 confirm a
known bug on hardware.

Ground rules:

- One repo, one branch: `cinemate` (`/Users/patrikeriksson/Documents/cinemate/cinemate`), branch
  `feature/clip-playback`, which **already exists locally** with two commits. Do not re-cut it.
  Commits C9.1–C9.5 in order. `cd` does not persist between shell calls — use `git -C` and
  absolute paths.
- **Never `git add -A`** (LFS pointer trap) — stage named files only.
- Do not merge to `dev`, do not push without asking, and **do not touch the Pi**. You are
  producing the desk-verifiable half; gates G0–G9 run later on hardware.
- The settings-editor template's JS is ES5 (`var`, `function(){}`) — match it. The file embeds
  base64 font data: filter greps with `awk 'length($0) < 250'`.
- Commit messages: `c9.<n>: <scope> — <one-line outcome>`.
- The lint gate is **`ruff check src/`**, never `ruff check .` — the latter reports 146
  pre-existing errors across `tools/`, `system-review/` and `_test/` on a pristine tree and will
  convince you that you broke something.

Order matters — C9.1 (docs) first and **on its own**, then C9.2 (rebase), C9.3 (defects), C9.4
(the check), C9.5 (the harness). C9.1 is separate because it is the only part of C9 that is
correct today and it currently exists in exactly one place; it does not depend on the rebase and
must not be held hostage to it.

Five places will bite you, all detailed in the plan; re-read those sections before writing them:

1. **The rebase is not clean, and this checkout is not the target.** `dev` has moved 1381 commits
   through the files C9 edits — `settings_editor.html` alone moved 98 lines, including PR #160's
   `<!DOCTYPE html>` + viewport meta, which the C9 branch's copy **predates**. Rebase onto `dev`,
   resolve toward `dev`'s copy, and check afterwards that the doctype and viewport are still
   there. A conflict resolved the other way silently re-drops a shipped fix.
2. **`"value"` is a reserved key inside `settings_editor.py`.** `tools/gui_field_extract.py:190`
   and `_test/test_action_catalogues_agree.py:42` both regex `"value":\s*"([a-z0-9_]+)"` over the
   whole file and treat every hit as an offered controller action. A scale-option list written as
   `{"value": "quarter"}` fails CI **twice**, and the pytest message points at the JS catalogue,
   not at you. Use `id`, `divisor` or `scale` — or keep option lists in `playback.py`. Do not add
   entries to the `ACTION_METHODS` array either.
3. **The topbar will lie on the new tab.** `syncTopbarForPage()` reads
   `var noFilePage = activePage === 'live' || activePage === 'raw';` — `settings_editor.html:4574`
   on `dev` @ `c0eb9ff7`, but grep the symbol rather than the line, because the rebase moves it — a `playback` page falls
   through as a *file* page and offers Save changes / Revert / Download / Upload as if it edited
   settings.jsonc. Add it, or invert the predicate to a whitelist of file-backed pages.
4. **Do not build a second take enumerator.** `raw_files.py` already has `_media_roots()`,
   `_is_take_dir()`, `_take_info()`, `list_takes()` (mtime-sorted, `has_wav` per take) and a
   traversal-hardened `resolve_take()`. `playback.py` must call them and extend that module where
   it needs more, not re-scan. This repo has already shipped the duplicate-catalogue failure —
   three copies of the settings-editor action list that agree perfectly, including on the same
   wrong entry (F-218/219/220). And take mtime alone is not a sufficient cache key:
   `storage-automount` promotes a standby with `mount --move`, so a take's path changes from
   `/media/RAW1/<take>` to `/media/RAW/<take>` without its mtime moving. Key on resolved path
   **and** mtime, and re-resolve per request.
5. **The 409 is edge-driven and the pane cannot see an HTTP status.** `loadRawTakes()` and its
   siblings read `res.ok` out of the **JSON body** and never look at the status code — a bare 409
   with a non-JSON body makes `r.json()` reject into a silent `.catch`. Return
   `{"ok": false, "message": …}` with the code. And gate the refusal on `IS_RECORDING` **or**
   `IS_WRITING_BUF` **or** `IS_BUFFERING` **or** `STORAGE_PREROLL_ACTIVE` — the post-take flush and
   pre-roll are exactly the storage-contention windows the lockout exists for, and pre-roll writes
   at full rate with `IS_RECORDING` at 0. Check `listener_alive()` before trusting a "not
   recording" answer: a frozen cache otherwise fails **open**, into playback mid-take.

Also fix the sixth defect while you are in the template: the Live tab embeds
`<iframe id="liveEmbedFrame" … src="/">` (`settings_editor.html:2226` on `dev`) and nothing ever
clears its `src` — `setActivePage()` only hides it, so once the operator has visited Live view the shooting
screen's MJPEG stream and its Socket.IO connection stay live behind every other tab, on the same
Wi-Fi link that playback needs. Clear it on leave, restore it on entry.

`tools/playback_bench.py` (C9.5) is what makes the gate session possible, so build it to be run by
someone who is not you, on a Pi, over SSH:

- It imports `dng_preview` from the repo checkout and needs **nothing** that is not already on
  every camera — numpy and Pillow are unconditional runtime dependencies (`requirements.txt`,
  imported on `main.py`'s own boot path). `cinemate-update.sh` never re-runs pip, so a new
  dependency would break every deployed camera on update with a bare ImportError. This constraint
  is load-bearing, not stylistic.
- `--decode`: 15-iteration median per (scale × workers) over a named take, printing
  `numpy.__version__` and the achieved ms/frame. That is G1.
- `--io`: samples `/proc/diskstats` around N decoded frames and reports **bytes read from the
  device** per frame beside wall clock — not `dd`. That is the half of G2 that can invalidate the
  plan's central storage claim, because nothing in this stack tunes `read_ahead_kb` and readahead
  may transfer rows the decoder discards.
- `--render`: decodes one frame per take and prints mean luma, the 5th/95th percentiles and the
  zero-pixel fraction, writing a PNG beside the numbers. That is G9.
- Output as one line of JSON per measurement, so results paste into `GATES.md` without
  reformatting. Do not print anything else to stdout.

Done means:

1. The five commits match the plan (deviate only where the plan contradicts current source, and
   say exactly where and why), and you have reported the `LinearizationTable` answer.
2. Tests: `_test/test_dng_preview.py`'s nine already exist and must still pass post-rebase; add
   the check C9 owes ADR-001 — every `data-page-tab` value has matching `.group[data-page]`,
   `[data-page-lede]` and `.rail-group[data-page]` markup and is covered by the topbar's page
   predicate — following `_test/test_action_catalogues_agree.py`'s reading pattern. If you add a
   test that touches the playback endpoints, use `_test/test_web_api_blueprint.py:16-24`'s
   fake-`module.app`-package trick rather than stubbing `flask_socketio` into `sys.modules`; two
   files already do the latter and never clean up, which is why `-p no:randomly` is mandatory.
3. All six checks green, run in this order and reported with their actual output:
   `ruff check src/` · `python -m pytest _test/ -q -p no:randomly` ·
   `python3 tools/docs_drift_check.py --repo . --strict` ·
   `python3 tools/design_token_diff.py --repo . --strict` ·
   `python3 tools/gui_field_extract.py --repo . --max-unresolved 0` ·
   `python3 tools/redis_key_diff.py --max-unreferenced 12` (needs `../cinepi-raw`; say so if you
   skip it). **Report the post-rebase test count as a new number.** The plan's "556" is the figure
   at `714ef7b4`; `dev` alone now collects 688, so the target is ~697 and 556 is not an acceptance
   criterion.
4. `tools/playback_bench.py` dry-run on the Mac against a real take at each of its three modes,
   with the output pasted — the harness has to be known-working before it goes near a session
   where the Pi is the variable.
5. A closing summary listing: files touched per commit; the `LinearizationTable` verdict; what the
   rebase conflicted on and how you resolved it; and the exact manual Pi commands for the
   operator's Session A (`git fetch`, `git switch feature/clip-playback`, `git pull --ff-only`,
   restart cinemate — Python-only, no rebuild), with G0's baseline readback and each of G0/G1/G3/G5/G6's
   predictions written out so I can record pass/fail against them.

Stop after that summary. Do not start a Pi session, do not run hardware gates, do not merge. Stop
and ask if a plan assumption fails — in particular, the plan's headline claim that the Pi can be
~6× slower than the Mac and still hold the conform rate is unverified, and nothing in this session
tests it.
