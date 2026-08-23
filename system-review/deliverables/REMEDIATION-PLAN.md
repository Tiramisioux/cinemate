# Remediation plan

**Session:** S12 · **Closes:** the review's analysis phase · **Pi used:** no
**Inputs:** 186 findings (40 high, 69 medium, 53 low, 24 strengths) across 11 sessions

This document turns the ledger into work. §6 has **ready-to-paste handoff prompts** — one
per thread, self-contained, so each supervised session starts cold.

---

## 1. Why the batches are not split by repository

The obvious split — one thread per repo — does not survive the finding distribution:

| repo | findings |
|---|---|
| cinemate | 128 |
| install | 19 |
| **both (cross-repo)** | **17** |
| docs | 14 |
| **cinepi-raw** | **8** |

A cinepi-raw thread would have eight items, six of which are cross-repo anyway. And the 17
"both" findings — the Redis key contract (F-027, F-226), the timecode divergence (F-202,
F-253), the unpinned pairing (F-264) — are cross-repo *by nature*. Splitting by repo puts
them in no thread or in two, which reproduces exactly the coordination failure the review
documented.

**The batches below split by risk and verifiability**, which is also how they can be
supervised: a batch is a thread, and a thread is a sitting.

---

## 2. Ordering principle

`PLAN.md` asks for (risk reduction × comprehension gain) ÷ blast radius. Applied, that gives
one clear first move and one clear shape.

> **B3 goes first even though it is the only desk batch that wants hardware to confirm.**
> F-204 and F-271 are the two worst defects found, they are about ten lines each, and in
> both cases **the correct implementation already exists a few hundred lines away in the same
> repository.** Nothing is learned by deferring them.

Everything else follows the safe-to-risky gradient. B1, B2 and B4 can run in any order and
in parallel with each other; none can break a camera.

| # | batch | Pi | risk | findings closed | commits |
|---|---|---|---|---|---|
| **B3** | Small correctness fixes | verify only | low per change | 10 | 7 |
| **B1** | Docs | no | none | 8 | 5 |
| **B2** | Delete dead code | no | low | 30 | 5 |
| **B4** | The checks (CI + harness) | no | low | 6 | 6 |
| **B5** | Pi verification session | **yes** | none (read-only) | settles ~10 | 0 |
| **B6** | Dependencies & pinning | on merge | medium | 9 | 3 |
| **B7** | ADR-001 steps 1–3 | verify | medium | 6 | 4 |
| **B8** | Structural (deferred) | mixed | high | — | — |

---

## 3. The batches

### B3 · Small correctness fixes — **do this first**

Seven commits. Every one is small, and every one has a reference implementation in-repo.

| commit | change | closes | reference already in-repo |
|---|---|---|---|
| B3.1 | Wrap `Event.emit`'s dispatch in `try/except Exception` + `logging.exception`; add a liveness check on the `_listen` thread | **F-204**, F-208 | `cinepi_controller.py:1082-1087` — the same loop, guarded |
| B3.2 | Settings editor: write the user's text, back up first | **F-271** | `cinemate-recovery.py` `write_config_file` — *"Back up, then atomically replace. The order is not negotiable."* |
| B3.3 | Remove the 2 s `time.sleep` from the redis subscriber; emit `reload_browser` off-thread | **F-205** | — |
| B3.4 | `cleanup()`: call `usb_monitor.stop()`, `ssd_monitor.stop()`; fix `SSDMonitor.stop()`'s `AttributeError`; call `stop_listener()` | F-023, F-108, F-022 | — |
| B3.5 | Fix `set_log` → `set_log_encode` in both catalogues, **and** wire the `available` flag the template ignores | **F-118**, F-219, F-218 | `GET /api/actions` — already computes it |
| B3.6 | Bound the in-app log queue (`deque(maxlen=…)` or drop the handler) | F-172 | — |
| B3.7 | Add the missing `else` + `warn` to the libcamera overclock patch | F-193 | the surrounding code's own guard comments |

**Verification, Mac/desk:** B3.1 and B3.4 are covered by existing tests once B4 runs them.
B3.2 — save from the settings editor, `diff` the file, confirm 74 comment lines survive and
a backup exists. B3.5 — `python3 tools/gui_field_extract.py` must report **0** offered-but-
absent names.

**Verification, Pi (rolls into B5):** PI-014 for F-204, PI-013 for F-172.

**Blast radius:** B3.1 touches the object every live value flows through — but it only adds a
guard, so the failure mode it changes is "thread dies" → "one subscriber's exception is
logged". B3.4 touches shutdown, which nothing else depends on. B3.5's second half is the
only one that changes UI behaviour (a greyed-out button appears).

**Rollback:** each commit is independently revertible; none changes a data format.

---

### B1 · Docs — zero risk, high legibility gain

| commit | change | closes |
|---|---|---|
| B1.1 | Add `controller-methods.md` and `image-circle.md` to the mkdocs nav — **232 lines of correct content currently unpublished**, including the most accurate method catalogue in the repo | **F-244**, F-242 |
| B1.2 | Strike "and GPIO" from `web-gui.md` — it asserts a drift-safety property GPIO does not have | **F-245** |
| B1.3 | `lock_dual_recording` → `sensors.record_policy` in all three places: `changelog.md:11`, the docstring at `cinepi_controller.py:1347`, the comment at `cli_commands.py:267` | **F-246** |
| B1.4 | Document the 13 missing Redis keys — 7 are one feature (dynamic resolution), so it is one table block | F-241 |
| B1.5 | Cosmetic: `settings.json`→`.jsonc` ×2, the missing leading slash, the orphan sentence, and decide the 5 empty files (write or delete, with their commented-out nav lines) | F-247, F-243, F-249, F-004 |

**Verification:** `python3 tools/docs_drift_check.py --repo .` — `links`, `cites`, `methods`
and `settings` must stay at zero; `keys` drops from 13 to 0; `nav` drops from 15 to ≤13.

**Note B1.3 is not a docs-only change** — two of the three stale references are inside
`src/`. S09's finding was that prose *inside the code* rots where `docs/` does not.

---

### B2 · Delete dead code — ~3,250 LOC, low risk

Five commits, grouped so each is independently reviewable.

| commit | contents | closes |
|---|---|---|
| B2.1 | Unreferenced Python modules: `timekeeper.py` (243), `keyboard.py`, `stream.py`, `rotary_encoder.py`, `USBDriveMonitor` | F-017, F-031, F-013, F-100, F-115 |
| B2.2 | Unreferenced templates — 4 files, 928 LOC | F-001 |
| B2.3 | cinepi-raw dead sources: `lj92.c`/`lj92.h` (1218), `_mjpegPreviewStage.cpp` (240), the 0-byte `cinepi_manager.cpp`, one of the two byte-identical patches | F-029, F-012, F-200, F-201 |
| B2.4 | Build-file rot: the Makefile recursing into three deleted directories, the `uninstall` targets with no recipe, and the root `CMakeLists.txt` that makes `cmake .` fail immediately | F-161, F-162, F-165 |
| B2.5 | Dead members and functions — 12 findings, all with no caller anywhere | F-018, F-102..F-104, F-109, F-119..F-121, F-125, F-171, F-178, F-179 |

> **Two hard preconditions on this batch.**
>
> 1. **Use F-122's corrected reachability result, not S01's import graph.** S01's regex read
>    `from module import parameters` as an edge to `module` and put **five live modules** on
>    a dead list. F-122 is the exhaustive corrected answer: exactly 4 of 48 unreachable.
> 2. **Do not let any "remove commented-out code" tool near this.** F-133 catalogued **47
>    load-bearing why-comments**, including two falsified experiments. `ruff.toml` in
>    `draft-config/` carries an explicit `ERA001` prohibition and the reason. Read it before
>    deleting a comment.

**Verification:** `git grep` each symbol one final time before deleting it; then B4's test job.

---

### B4 · The checks — what makes this review durable

Without this batch, everything above is a snapshot that starts drifting the next day.

| commit | change | closes |
|---|---|---|
| B4.1 | `.editorconfig` | — |
| B4.2 | **Split `docs.yml` build from deploy**, then add `pull_request` and `dev` triggers. `deliverables/draft-config/docs-split.md` has the exact edit **and the trap**: two steps publish gh-pages and `git push` unconditionally, so widening the trigger without guarding them makes every PR publish | **F-006** |
| B4.3 | `ruff.toml` + a lint job. Run it locally and fix the hits first so the first CI run is green | F-005, F-130, F-131, F-169 |
| B4.4 | Move the four harness scripts to `tools/` and add the `drift` job. Ratchet, do not gate, where a known count exists | F-027, F-118, F-007 |
| B4.5 | shellcheck gate at zero after fixing the 15 | F-174..F-179 |
| B4.6 | pytest job in **discovery mode** (`continue-on-error: true`) — its only purpose is to learn the portable/hardware split, then mark the hardware tests and remove the flag | **F-222**, F-006 |

**The four checks, all stdlib-only and hardware-free:**

| script | gates |
|---|---|
| `redis_key_diff.py` | the cross-repo key contract — ratchet at 12 unreferenced |
| `gui_field_extract.py` | reflective-dispatch names — **gate at 0** after B3.5 |
| `design_token_diff.py` | colour tokens — **gate at 0**, nothing has drifted yet |
| `docs_drift_check.py` | six docs checks — 4 gate at 0, `keys`/`nav` ratchet |

> **381 tests across 27 files have never run** (F-222). B4.6 is how that changes, and its
> first run is a discovery exercise, not a gate.

---

### B5 · The Pi session — 16 queued items

Read-only. Nothing is changed on hardware; the session produces answers.

**Run in this order** — the first three unblock the most:

1. **PI-002** — run the test suite. Gates B4.6's real form and B6's split line.
2. **PI-014** — kill the redis listener and watch every surface. Confirms F-204's severity
   and scores ADR-001 constraint 5.
3. **PI-009** — `modetest -p` with cinepi-raw running, `--same-hdmi` on and off. **Count the
   free overlay planes on the primary CRTC.** This is the last open ADR-001 constraint.
4. PI-012 (`INSTALL_ALT_GPIO_BACKEND=0` clean install), PI-016 (RAM/CPU/boot baseline),
   PI-013 (log-queue growth), PI-015 (browser cadence + headless path), then PI-001,
   PI-003..PI-008, PI-010, PI-011.

Budget ~5 hours including two clean installs. `PI-VERIFICATION-QUEUE.md` has an exact
procedure and a falsifiable prediction for each.

---

### B6 · Dependencies and pinning

| commit | change | closes |
|---|---|---|
| B6.1 | Three-file split — `requirements.txt` (portable, **pinned**), `requirements-hardware.txt`, `docs/requirements-docs.txt`. **The split line comes from PI-002's output, not from a guess.** `lgpio` moves to the hardware file *unconditionally*, which is F-182's fix | F-002, F-003, F-184..F-190 |
| B6.2 | Installer reads them: `pip install -r requirements.txt -r requirements-hardware.txt` | F-003 |
| B6.3 | **`versions.env`** — a pairing manifest the installer sources and the docs quote, pinning `CINEMATE_REPO_REF` and `CINEPI_RAW_REPO_REF` | **F-264** |

**B6.3 is the one to argue for.** cinepi-raw's `main` and `dev` differ by 45 files and +7164
lines, *including four `CONTROL_KEY_` macros of the cross-repo contract*. Nothing anywhere
records which cinemate goes with which cinepi-raw. This is the review's thesis in its
reproducibility form.

**Requires PI-004 and PI-012** — a clean install validates it or nothing does.

---

### B7 · ADR-001 steps 1–3

Per `decisions/ADR-001-gui-harmonization.md` §6, and **only after B3.1**, which fixes the bus
every surface rides on.

| commit | change | closes |
|---|---|---|
| B7.1 | One token source generating the Python constants and the CSS custom properties; `design_token_diff.py --strict` in CI on the same commit | F-007, F-214, F-232, F-233 |
| B7.2 | Lift `left_section_layout`/`right_section_layout` into data — named formatter references instead of lambdas. **Nothing about rendering changes.** | F-215, F-216 |
| B7.3 | Web backend reads the same spec | F-203 |
| B7.4 | Generalise `_top_row_layout`'s justified row and `draw_left_sections`' conditional stack into one region primitive, **behind a flag, region by region** | F-238, F-008 |

Options D and E are rejected. Surface 4 (recovery console) is excluded permanently — its
value is its isolation.

---

### B8 · Deferred, and deliberately so

- **`cinepi_controller.py` decomposition.** F-270: it is **wide, not deep** — 151 methods
  averaging ~16 lines. Split by concern into modules; do **not** hunt for long methods to
  extract, there are almost none. Only `__init__` (239 lines) is oversized.
- **F-268/F-269 — the concurrency model.** Three serialised input paths, six that bypass, and
  9 lock sites across 151 methods. This needs a design decision, not a patch. PI-007's
  remaining step says whether the race is observable.
- **F-251** — four registries of config defaults, 11 keys disagreeing. B4.4's ratchet stops
  it growing; unification is its own project.
- **F-160** — two processes mounting/fsck'ing `/media/RAW` with no ownership protocol.
  `probable`, and the root cause (F-164) is a severed link, not six copy-pastes.

---

## 4. What is NOT in any batch

**24 findings are strengths and must survive the work**, several because a batch could
plausibly damage them:

- **F-133** — 47 load-bearing why-comments. B2 is the risk. Promote them into `docs/` first
  if anything.
- **F-221** — the recovery console's isolation. B6 must not make it import anything.
- **F-192/F-194** — the installer's designed idempotency. B6.2 must preserve the
  managed-block pattern.
- **F-234, F-240, F-242** — the accurate docs. B1 should not rewrite what is already right.
- **F-206, F-210** — the two boundaries that have *not* drifted. Both are examples to copy.

---

## 5. Verification matrix

| batch | desk verification | hardware |
|---|---|---|
| B1 | `docs_drift_check.py`, `mkdocs build` | none |
| B2 | `git grep` per symbol, then B4's tests | PI-002 for the suite |
| B3 | `gui_field_extract.py`, a settings-editor round-trip diff | PI-013, PI-014 |
| B4 | the workflows themselves, on one PR | PI-002 |
| B5 | — | the whole session |
| B6 | `pip install -r` in a clean venv | **PI-004, PI-012 — mandatory** |
| B7 | `design_token_diff.py --strict`; per-region visual diff | PI-009, PI-015 |

---

## 6. Handoff prompts

Self-contained. Paste one at the start of a session.

### Thread B3 — small correctness fixes

```
Work on the CineMate repo, branch: cut a fresh branch from `dev`. Never commit or push
to `dev` itself.

Read `system-review/deliverables/REMEDIATION-PLAN.md` §3 batch B3, then
`system-review/FINDINGS.md` rows F-204, F-208, F-271, F-205, F-023, F-108, F-022, F-118,
F-219, F-172, F-193.

Land the seven B3 commits in order, one commit each, stopping after each for review.

Start with B3.1 — it is the worst defect in the system and it is about ten lines:
`RedisController.Event.emit` (redis_controller.py:155-157) dispatches nine subscribers in a
bare loop with no exception guard, `_listen` has none either, and the thread is daemon with
no watchdog. One raising subscriber kills all live state permanently, and because
get_value() serves a cache, every surface then shows plausible frozen values instead of an
error. Copy the guarded version that already exists at
cinepi_controller.py:1082-1087 (`try/except Exception` + `logging.exception`).

B3.2 is nearly as bad and equally small: app/settings_editor.py:186 writes
json.dumps(settings) over settings.jsonc, destroying all 74 of its 386 lines of comments,
with no backup. The correct implementation is
services/cinemate-recovery/cinemate-recovery.py's write_config_file — writes raw text,
backs up first.

Constraints: no refactoring beyond each fix. Do not touch system-review/. Run the repo's
tests if a runner exists yet; otherwise verify by reading and say so.
```

### Thread B1 — docs

```
Work on the CineMate repo, branch: cut a fresh branch from `dev`. Never commit or push
to `dev` itself.

Read `system-review/deliverables/DOCS-DRIFT-REPORT.md` in full, then
`system-review/deliverables/REMEDIATION-PLAN.md` §3 batch B1.

Land the five B1 commits. After each, run:
    python3 system-review/harness/docs_drift_check.py --repo .
links / cites / methods / settings must stay at 0. keys should fall 13 -> 0.
nav should fall 15 -> 13 or lower.

Context that changes how you should work: S09 found the docs are the BEST-maintained
boundary in this system - 103 links with 0 broken, 64 code citations with 0 bad, 43 of 43
method names real. Do not rewrite what is already correct. Fix the eight specific defects
and nothing else.

Note B1.3 edits src/ as well as docs/: `lock_dual_recording` does not exist anywhere, and
it is named in changelog.md:11, in a docstring at cinepi_controller.py:1347, and in a
comment at cli_commands.py:267. The real setting is sensors.record_policy == "always_both".

Do not touch system-review/.
```

### Thread B2 — delete dead code

```
Work on the CineMate repo, branch: cut a fresh branch from `dev`. Never commit or push
to `dev` itself.

Read `system-review/deliverables/REMEDIATION-PLAN.md` §3 batch B2 and
`system-review/deliverables/REDUNDANCY-REPORT.md` §2.

Land the five B2 commits, ~3,250 LOC of deletions. Before deleting ANY symbol, run one
final `git grep` for it and paste the result in the commit message.

Two hard rules:

1. Use F-122's corrected reachability result, not S01's import graph. S01's regex read
   `from module import parameters` as an edge to `module` and wrongly listed five LIVE
   modules as dead. F-122 is the exhaustive corrected answer: exactly 4 of 48 modules
   unreachable from main.py.

2. NEVER delete a comment as part of this. F-133 catalogued 47 load-bearing why-comments,
   including two falsified experiments (ssd_monitor.py:1122-1125 records that 1 MB exFAT
   clusters break the macOS driver) and a cross-repo invariant at
   storage_profiles.py:41-49. Do not enable ruff's ERA001. If a deletion would remove a
   comment explaining WHY, stop and ask.

B2.3 touches cinepi-raw, which is a separate repo on branch `dev`. Confirm the branch
first: git -C <clone> branch --show-current must print dev.

Do not touch system-review/.
```

### Thread B4 — the checks

```
Work on the CineMate repo, branch: cut a fresh branch from `dev`. Never commit or push
to `dev` itself.

Read `system-review/deliverables/STANDARDS-PROPOSAL.md` in full - it argues every rule from
a specific finding - then `system-review/deliverables/draft-config/README.md`.
`draft-config/` holds unexecuted drafts of ruff.toml, .editorconfig, checks.yml and the
docs.yml edit. Treat them as reviewed starting points, not as working files.

Land the six B4 commits.

B4.2 first and read `draft-config/docs-split.md` before touching docs.yml: the workflow has
two steps that publish gh-pages and `git push` unconditionally. Adding a pull_request
trigger without guarding them makes every PR publish the docs site and push a commit.

B4.4 moves four stdlib-only checkers from system-review/harness/ to tools/ - this is the
ONE case where you may move a file out of system-review/. Wire each as the plan specifies:
ratchet where a known count exists, gate at zero where it does not.

Before enabling the ruff job, run it locally and fix or ignore every hit, so the first CI
run on dev is green. A check that arrives red gets disabled within a week.

B4.6's pytest job must keep continue-on-error: true on its first runs. 381 tests across 27
files have never executed and nobody knows which need a Pi. The job's first purpose is to
find out.
```

### Thread B5 — the Pi session

Run this where the camera is reachable, **not** in a cloud session. Sonnet is a good fit:
the work is executing written procedures and recording what happened, and `PI-RUNBOOK.md`
is self-contained so the session does not need the review's context.

```
Hardware session on a CineMate camera. You are RECORDING OBSERVATIONS, not fixing
anything. No edits to src/, no commits to the camera's code, and never to `dev`.

Get the runbook first -- it is self-contained and you do not need anything else:

    cd ~/cinemate
    git fetch origin claude/cinemate-system-review-kickoff-cilicc
    git checkout claude/cinemate-system-review-kickoff-cilicc
    cat system-review/PI-RUNBOOK.md

(The runbook lives on that review branch, NOT on dev. If you are on dev you will not
find it.)

FIRST, AND THIS DECIDES HOW TO READ EVERY PREDICTION -- establish which build the
camera is running:

    git -C ~/cinemate   rev-parse HEAD && git -C ~/cinemate   log --oneline -3
    git -C ~/cinepi-raw rev-parse HEAD
    uname -a && cat /proc/device-tree/model && free -m

The predictions in the runbook describe the code BEFORE a set of fixes that are
currently in open pull requests (cinemate #130, #131, #132, #133; cinepi-raw #59).
If the camera is running a build that INCLUDES those fixes, several predictions
invert -- most importantly PI-014, where the whole point of the fix is that the
failure no longer happens. Say plainly which build you tested. A result recorded
against the wrong build is worse than no result.

Then work the runbook in its own order. Tier 1 is three items and is the session
even if you do nothing else:

  PI-014       kill the redis listener, watch all four surfaces in order
  PI-004/012   two clean installs on blank SD cards
  PI-009       count the free DRM overlay planes -- the only item with NO prediction,
               deliberately, because reading the source could not produce one

Tier 2 is nine items as a table. Tier 3 is three cheap greps.

RECORDING. Four lines per item, format in the runbook, ending in
CONFIRMED | CONTRADICTED | INCONCLUSIVE.

A CONTRADICTED prediction is the most valuable outcome here. These were written from
source with no hardware; several are probably wrong. Do not reconcile an observation
to match what the document expected, do not soften it, and do not drop an
INCONCLUSIVE because it looks untidy. If a procedure cannot be run, say why -- that
is a real result.

WHEN DONE, COMMIT THE RESULTS. Append them under each item in
system-review/PI-VERIFICATION-QUEUE.md, keeping the original prediction visible next
to what happened, then:

    git add system-review/ && git commit -m "pi: results from the hardware session"
    git push origin claude/cinemate-system-review-kickoff-cilicc

Only system-review/ should be touched. Results that exist only in a chat window are
one context window from gone.

Then post the same block in chat, raw, without summarising or interpreting.

Note on PI-002: the suite has since been run off-hardware -- 386 tests, ~2 s, nine pip
packages, all passing. So its question is no longer "which tests need a Pi" (none do).
It is now a spot-check: does any test pass on the camera for the WRONG reason, by
silently skipping the thing it claims to check? Run it with -v and look.

Budget ~5 hours, most of it waiting on the two installs.
```

### Thread B6 — dependencies and pinning

```
Work on the CineMate repo, branch: cut a fresh branch from `dev`. Never commit or push
to `dev` itself. DO NOT START until PI-002 has run - the split line depends on its output.

Read `system-review/deliverables/INSTALL-DRIFT-REPORT.md` §5 and
`system-review/findings/F-003.md`. S10 decided this: option 2, requirements.txt canonical,
three-file split. The reasoning is in §5 and includes why S01's opposite lean was superseded.

Land the three B6 commits. B6.2 changes the installer's pip invocation, which is a boot-path
change: it is not verified until a clean install on a blank SD card reaches camera-ready
(PI-004), and PI-012 covers the lgpio move.

B6.3 is the one that matters most and is not in F-003: add a versions.env pinning
CINEMATE_REPO_REF and CINEPI_RAW_REPO_REF. Today both default to empty while the sensor
drivers are pinned to 6.12.y and libcamera to `cinemate`. cinepi-raw's main and dev differ
by 45 files and +7164 lines including four CONTROL_KEY_ macros of the cross-repo Redis
contract, and nothing records which cinemate goes with which cinepi-raw.

Preserve the installer's managed-block idempotency pattern (F-192) - it is designed and
documented, and it is the best-engineered part of the repo.
```

---

## 7. Confidence

Every finding referenced here cites a line read in this repository on the `dev` branch of
both repos. **No Raspberry Pi was used at any point in this review**, and no runtime
behaviour is asserted as observed.

Specifically for this plan:

- **The effort and commit counts are estimates**, not measurements.
- **B6's split line is `unverified`** and must come from PI-002.
- **B7's cost rests on F-237's measurement** (925 of 1913 lines are draw/layout) and on
  F-238's finding that the two layout primitives already exist — both confirmed statically,
  neither exercised.
- **Two batch orderings are judgement calls**: B3 before B5 (the fixes are correct
  regardless of what the Pi shows), and B4 before B7 (a unification without its check
  re-grows the duplicates — S04's standing verdict, and the codebase has already run that
  experiment three times with comments as the sync mechanism).
