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
| **B9** | One fact, one home | B9.1/B9.4 | medium | 28 | 7 |
| **B10** | Close the ledger | B10.2 only | low | 35 + all 201 dispositioned | 7 |
| **B11** | Field-reported defects | B11.1/2/8 | mixed | 11 | 8 |
| **B13** | Docs vs. the code that shipped | B13.1/2 verify | none | 8 | 7 |

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

**Verification, Pi (rolled into B5, done 2026-08-24):** PI-014 for F-204 — **CONFIRMED**, the
worst-case failure mode: both the cache-backed HTTP API and the SSE stream froze permanently
and silently on the first PUBLISH after a forced subscriber exception. PI-013 for F-172 —
**CONFIRMED**, log-queue RSS growth is ~70x faster while recording than idle. B3.1 and B3.6
are safe to merge and now hardware-verified, not just structurally argued.

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
| B2.2 | Unreferenced templates — **5 files, not 4** (`template_old.html` missed), ~928+ LOC. **PI-001 confirmed all five are deployed to every camera** — the deletion has real effect, not just repo hygiene | F-001 |
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
| B4.6 | pytest job — **PI-002 has since closed the discovery question**: 381 passed + 241 subtests, zero skips, on- and off-hardware alike. `continue-on-error: true` is no longer needed as a hedge; the job can gate at zero from adoption | **F-222**, F-006 |

**The four checks, all stdlib-only and hardware-free:**

| script | gates |
|---|---|
| `redis_key_diff.py` | the cross-repo key contract — ratchet at 12 unreferenced |
| `gui_field_extract.py` | reflective-dispatch names — **gate at 0** after B3.5 |
| `design_token_diff.py` | colour tokens — **gate at 0**, nothing has drifted yet |
| `docs_drift_check.py` | six docs checks — 4 gate at 0, `keys`/`nav` ratchet |

> **381 tests across 27 files have never run in CI** (F-222). B4.6 is how that changes.
> **PI-002 has since run them once, manually, on real hardware — 381 passed, zero skips,
> matching the off-hardware baseline exactly** — so the first CI run can gate at zero rather
> than discover the split.

---

### B5 · The Pi session — 16 queued items

> **DONE, 2026-08-24.** All 16 items closed across two sessions (2026-08-23, 2026-08-24).
> Digest: `PI-RESULTS-2026-08-24.md`. Five predictions CONTRADICTED (PI-005, PI-008 partly,
> PI-010, PI-012, PI-016); the rest CONFIRMED or CONFIRMED/CONTRADICTED split. See
> `FINDINGS.md` for the findings this reconciled and `STATE.md` for the ground-truth summary.
> Two narrower sub-cases were not reached (PI-009's `--same-hdmi` toggle, PI-015 step 3) —
> see `PI-RESULTS-2026-08-24.md` "Not run".

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
| B6.1 | Three-file split — `requirements.txt` (portable, **pinned**), `requirements-hardware.txt`, `docs/requirements-docs.txt`. **The split line comes from PI-002's output, not from a guess** — PI-002 is done: 381 passed + 241 subtests, zero skips, both on- and off-hardware, so the portable/hardware split among test files "appears not to exist" (see `PI-RESULTS-2026-08-24.md`). `lgpio` moves to the hardware file *unconditionally* — no longer F-182's fix for a real crash (PI-012 contradicted the crash prediction), but still correct hygiene | F-002, F-003, F-184..F-190 |
| B6.2 | Installer reads them: `pip install -r requirements.txt -r requirements-hardware.txt` — **draft PR #133 implements this into a `$VENV_DIR`, which the operator has since removed in favour of `pip install --user --break-system-packages`; #133 is `NEEDS-CHANGE` on the install mechanism, not on this requirements-file content, which PI-004 vindicated directly (flask/pyserial both confirmed transitive-only on a clean install)** | F-003 |
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
  9 lock sites across 151 methods. This needs a design decision, not a patch. **PI-007/F-285
  (done, 2026-08-24) confirmed the race is not just observable but a 100% starve**: a live
  analog pot out-polled 20/20 explicit CLI `set iso` calls over 14s. Still deferred to B8 —
  the fix (route `AnalogControls` through the lock, or back off after an external command
  lands) is a design decision, not a patch, but it is no longer a hypothetical one.
- **F-251** — four registries of config defaults, 11 keys disagreeing. B4.4's ratchet stops
  it growing; unification is its own project.
- **F-160** — two processes mounting/fsck'ing `/media/RAW` with no ownership protocol.
  `probable`, and the root cause (F-164) is a severed link, not six copy-pastes.

---

### B9 · One fact, one home — the duplication backlog

**39 redundancy and duplication findings sit outside every earlier batch.** They are the
review's central thesis in its rawest form: one fact, written down in several places, kept in
step by hand — and in nine cases the copies have already stopped agreeing. Every commit below
collapses one *fact*, not one file. Group by what is duplicated, never by where it lives.

The ordering inside B9 is by how much a disagreement costs at the moment it happens.

| commit | change | closes |
|---|---|---|
| B9.1 | **Storage facts into one module both processes import.** The filesystem→mount-options table (**copies disagree**), the ext4 option string stated 5×, `YANK_ERRNOS` byte-identical twice, two device-classification taxonomies that are **incompatible**, and the partition→root-block-device derivation | **F-156**, **F-158**, F-157, **F-155**, F-159, F-258 |
| B9.2 | **One boolean decoder.** Four divergent `_as_bool` implementations — `_as_bool(2)` is `True` in `gpio_input` and `False` in the other three — the truth-set `("1","true","yes","on")` re-typed across 7 files and 8 helpers, and one Redis boolean re-decoded in 6 places under 3 incompatible rules | **F-126**, F-254, F-255 |
| B9.3 | **One Redis client, and `ParameterKey` enforced rather than merely offered.** Four independent `StrictRedis` clients with hardcoded `localhost:6379`; `CAPTURE_GAIN_REDIS_KEY` re-declaring an existing member; the five `MIC_*` keys published by both repos; `set_value` accepting any string | F-105, F-106, F-107, **F-015**, F-028 |
| B9.4 | **The cross-repo formulas.** "SMPTE base = round(fps)" at 4 sites under **3 rounding rules** (PI-010 measured base 24 as the live winner — encode that, do not re-derive it); `tc_cam0`/`tc_cam1` written by both repos by different algorithms, last write wins mid-take; the `--mode W:H:B:P` string; `FALLBACK_PACKING_INFO` against `sensors.json` | **F-253**, **F-202**, F-250, F-261 |
| B9.5 | **Config defaults, and the comments that were standing in for a check.** `arrays.*.steps` stated 7× across 4 languages with the shutter table already missing entries; `system.web_api.*`/`system.recovery.*` 3× each; the settings path re-typed in 7 files; `pwm_pin`; the installer's heredoc reimplementation of `strip_jsonc()`; and the two hand-sync comments that were themselves incomplete | **F-256**, F-252, F-260, F-180, F-191, F-220, F-217 |
| B9.6 | **Four `class Event` definitions** with divergent error handling and signatures. B3.1 fixed the one that mattered; the other three still exist and can be raised through | F-127 |
| B9.7 | **The GUI's derived labels.** `populate_values()` publishes `iso_label`/`fps_label` for the web GUI while the template derives its own; the web GUI shows the drop/sync warning *state* but not the *counts* | F-257, F-211 |

**Precondition:** B9.4 must follow B5 — PI-010 and PI-011 measured which of the competing
implementations actually wins at runtime, and unifying on the wrong one is worse than leaving
four. **Both are done.**

**Do not start B9.3 before B9.2.** The boolean decoder is the thing several Redis readers use
to interpret what they read; fixing the client first just moves the disagreement.

**Verification, desk:** `python3 tools/redis_key_diff.py` — the unreferenced count must not
rise, and B9.3 should *lower* it. `python3 tools/design_token_diff.py --strict` after B9.7.
The full suite after each commit. **B9.1 and B9.4 want hardware:** a mount/unmount round trip
on the real NVMe, and a timecode round trip at a non-integer fps (24.5 or 29.97) checked in
the DNG, not in the GUI.

**Blast radius:** B9.1 touches the recording target's mount path and B9.4 touches values the
operator reads mid-take. Both are one-commit reverts, and neither should be merged the same
day as the other.

---

### B10 · Close the ledger — every remaining finding gets a disposition

The other batches fix what is dangerous. B10 exists so the review can be *finished* rather
than merely abandoned: **every finding ends with a recorded disposition, and a check enforces
it.** Most of these dispositions are "accepted, no action" — that is a legitimate outcome, and
writing it down is what separates an accepted risk from a forgotten one.

Five dispositions, and nothing else is allowed: `fixed` · `guarded` (not fixed, but a check
stops it growing — F-117 is the model) · `accepted` · `superseded` · `strength`.

| commit | change | closes |
|---|---|---|
| B10.1 | **The triage pass.** Add a `disposition` column to `FINDINGS.md` and fill it for all 201 rows. Verify each against the tree rather than trusting this plan — several findings here were closed by merged PRs after it was written. Anything that turns out still-open and *dangerous* gets pulled out into its own commit rather than dispositioned away | all 201 |
| B10.2 | **Second deletion pass.** Two write-only Redis keys; `Mediator`'s two no-op handlers and its two unused attributes; five `SSDMonitor` properties with no reader; six wrapper accessors; three zero-caller compatibility aliases; the dead hotspot check; the superseded `arecord -vvv` VU path; four stale `_test/` forks; the committed `.pyc` files; and the **nine pip packages installed on every camera and imported nowhere** | F-019, **F-274**, F-103, F-120, F-116, F-123, F-124, F-114, F-150, F-151, F-152, F-153, F-154, F-101, **F-277**, F-187, F-188, **F-032**, F-163 |
| B10.3 | **Shell-script correctness.** `local x=$(git …)` masking git's exit status at 4 sites (SC2155); `echo "\n…"` without `-e`; `[[ ]]` with no shebang in a `profile.d` script; the `pkill -f` pattern that can match more than its child; and put the two scripts the repo-wide `shellcheck` sweep misses **into** the sweep | F-176, F-175, F-177, F-033, **F-195** |
| B10.4 | **Logging and standards hygiene.** One logging idiom, not two (615 module-level calls beside a configured logger); lazy `%` formatting or f-strings, chosen once, ruff-enforced; the hardcoded `/home/pi/cinemate/src/logs`; the raw `'resolution_switching'` string where a `ParameterKey` exists; and the bare `set` no-op in the boot path | F-168, F-170, F-173, F-212, F-021, F-167, F-111 |
| B10.5 | **Docs, round two.** The 18 `ParameterKey` members absent from `redis-keys.md`; `web-gui.md`'s "same field layout, same styling" claim; the installer's missing step-level correspondence; the recovery console's total absence from a 1061-line install document; and the `--same-hdmi` description both repos state differently | F-014, F-248, **F-265**, **F-266**, F-229 |
| B10.6 | **Give cinepi-raw a CI.** It has **seven** `meson test` targets and **no `.github/workflows` at all** — they passed for the first time on 2026-08-24, run by hand. cinemate now has five checks on every PR and cinepi-raw has none; that asymmetry is the finding. A build job and `meson test` is the whole commit | **F-287**, F-228, F-030 |
| B10.7 | **The gate.** `tools/findings_disposition_check.py`, wired into the drift job: fail if any row in `FINDINGS.md` lacks a disposition, or carries one outside the five. This is what makes "all findings handled" a fact instead of a claim | — |
| B10.8 | **Record what the merged work already earned.** This plan predates the batch merges, the Pi session and the fix round, so a block of findings are closed in the tree and open in the ledger. Verify each against `dev` before marking — `fixed` where a merged PR closed it, `guarded` where only a check stands between it and a regression | F-166, F-276, F-279, F-280, F-281, F-282, F-283, F-284, F-286, F-275, F-016, F-207, F-259, F-272, F-278, F-237, F-235, F-236, F-239, F-026 |

**What B10.1 will mostly record, and should not try to fix:**

- **11 strengths** (F-181, F-192, F-194, F-206, F-210, F-221, F-223, F-234, F-240, F-262,
  F-267, F-134) → `strength`. §4 names which batches endanger which. F-134 — zero
  `TODO`/`FIXME`/`HACK` markers in the entire Python codebase — is the one worth stating out
  loud, because B10.4 is the commit most likely to leave one behind.
- **Bookkeeping** — merged duplicates, corrections, and one finding that was not reproducible
  (F-011, F-110, F-113, F-183, F-185, F-186, F-189, F-112, F-273, F-225, F-230, F-231, F-263,
  F-226, F-227) → `superseded`.
- **The structural and readability measurements** (F-010, F-128, F-129, F-132, F-009, F-020,
  F-024, F-209, F-213, F-224) → `accepted`, with a pointer to B8. Depth-11 nesting and 27%
  docstring coverage are facts about a codebase, not defects with a fix; F-270 already showed
  that treating the controller's size as a defect leads to the wrong remedy.
- **Findings B8 owns** (F-025, F-268, F-269, F-251, F-160, F-164) → `accepted`, pointing at
  B8. F-285 gave the concurrency question hardware proof; it is still a design decision.

**Verification:** B10.7's own check, run against `FINDINGS.md`, is the batch's verification —
it must pass with zero unset dispositions. B10.6 verifies itself on the first cinepi-raw PR.
B10.2 needs `git grep` per symbol before each deletion and the full suite after, exactly as
B2 did — and B2's own precondition applies again: **F-133's 47 load-bearing why-comments are
the risk**, promote any that document a deletion's reasoning before removing it.

**Blast radius:** B10.2 is the only one that can break a camera, and only through the pip
removals — nine packages that nothing imports is a static claim, and PI-012 already showed
once that an apt-installed dependency can be reached without a Python import. **Test the
package removals on a clean install, not on a running camera.**

---

### B11 · Field-reported defects — the first batch that did not come from the audit

**Every other batch in this plan came from reading. B11 came from using the camera.** Eleven
findings (F-288..F-298) reported by the operator from a running system, investigated against
`dev` at `13ab022`. That provenance matters: the audit read 20k lines of Python and never
found F-288, because a permission error on a root-owned directory is invisible to static
analysis — the same lesson `lessons/what-the-pi-taught-us.md` records for the Pi session.

Two of these are broken-in-the-field, not cosmetic. Do those first.

| commit | change | closes |
|---|---|---|
| B11.1 | **`config.txt` cannot be saved at all.** `mkstemp(dir="/boot/firmware")` as `User=pi` fails before writing a byte. Stage the temp file somewhere pi-writable and move it into place with a narrow privileged step — the installer's `configure_sudoers()` is the existing mechanism, and #138's `sudo -n` is the existing idiom. **Do not widen sudo to a general file write**; scope it to this one path | **F-288** |
| B11.2 | **`cinepi.local` does not resolve.** Nothing in either repo installs or enables `avahi-daemon`; a repo-wide grep for `avahi`/`mdns`/`nss-mdns` returns zero. Install and enable it, and fix `/etc/hosts` alongside `hostnamectl`, which currently leaves the old `127.0.1.1` entry | **F-289** |
| B11.3 | **The preview reconnects too early after a resolution change.** Move the `reload_stream` emit off `_notify_resolution_change` (fired at initiation, `cinepi_controller.py:1749`) and onto the completion path — `_schedule_resolution_switch_complete` is the very next line. The client machinery at `template.html:914-925` is already correct and needs no change | **F-290** |
| B11.4 | **"Restart Cinemate" does nothing.** Root-cause first, fix second — `journalctl -u cinemate-autostart -f` while pressing it. Candidates in the finding. If `os.execl` from a Timer thread is the cause, restarting via systemd rather than in-process is the more honest fix | F-291 |
| B11.5 | **The GPIO panes, rebuilt to the operator's column model.** Inputs: GPIO · action (**including `press`, currently missing from the dropdown**) · method, renamed to something a user recognises, with several actions per pin adding aligned method rows. Outputs: the same shape, section renamed **"GPIO out"**, which makes multiple tally pins expressible for the first time. This subsumes the 3-button/2-switch ceiling — rebuild the pane so the banner at `settings_editor.html:1730` can be deleted rather than reworded | **F-293**, **F-294**, F-292 |
| B11.6 | **Raw pane:** move "download selected" and "delete selected" below the list they act on | F-295 |
| B11.7 | **The web GUIs scale rather than reflow.** The top row stays the top row; the left and right grey-box columns stay columns at any width. Characterise the phone hamburger failure before touching it — it is currently only "does not really work" | **F-297**, F-296 |
| B11.8 | **Make the per-resolution fps ceiling correctable and editable, sensor value as default.** `image_capture.custom_modes` already carries `fps_max` per mode and is already read — it just `append`s instead of merging, so it can add a mode but never correct a detected one. Make a matching entry **override** that mode's `fps_max`, give the block a real schema, and **surface it in the settings editor** so the ceiling can be found by trial without editing code. Prefer sparse overrides with detected values shown as placeholders — materialising the whole table goes stale on every sensor swap, and this project swaps sensors. `choose_resolution()` needs no new logic: it keeps selecting on `fps_max`, now the effective value | **F-298** |

**Why B11.8 is shaped this way, stated once so it is not re-litigated:** `fps_max` comes from
`cinepi-raw --list-cameras`. It is an electrical property of the *sensor* and says nothing about
what this storage and this CPU sustain — only trial can find that. But the fix is **not** a new
global threshold: the switching mechanic is already right, it is simply reading a number nobody
can correct. Per-resolution overrides with the sensor value as default keep the existing
selection logic untouched, keep behaviour identical until someone overrides something, and let
4K be tuned down without touching 2K. `custom_modes` already proves the shape.

**Ordering:** B11.1 and B11.2 are broken-in-the-field — do them first and land them alone.
B11.3 and B11.4 are small and independent. B11.5 and B11.7 are the real work and want a
design pass before code. B11.8 should follow B9.5, which touches the same settings plumbing.

**Verification:** B11.1 and B11.2 need a real install — **a clean one, not a running camera**,
for the same reason B10.2 does. B11.3 needs a resolution change with the web GUI open. B11.5,
B11.6 and B11.7 need a browser at several widths, and a phone for the hamburger. B11.8 needs a
recording at either side of the threshold. Everything else is desk work.

---

### B13 · The documentation against the code that shipped

*(B12 is deliberately unused — the operator numbered this batch B13.)*

**B1 fixed the drift the checker could see. This batch fixes the drift it cannot.**
`docs_drift_check.py` verifies links, citations, method names, redis keys and settings
headings — all things with a machine-checkable counterpart. It has nothing to say about a
paragraph that describes a virtualenv the installer stopped creating, and it reported clean
on `13ab022` while every finding below was already true.

Eight findings, F-299..F-306, from reading both doc sets against `dev` (`13ab022`) and
cinepi-raw `dev` (`bc63598`) after eleven merged PRs.

**The two that actively mislead come first.**

| commit | change | closes |
|---|---|---|
| B13.1 | **Remove the virtualenv from the documentation.** `installation-steps.md:611-613,619-620,728` builds `~/.cinemate-env`, appends its activation to `.bashrc`, and writes the sudoers rule that #138's `configure_sudoers()` now **actively deletes**. Four more files reason about it: `:116,154` (meson picking the venv Python), `overclocking.md:116-119` (`deactivate` first), and the "broken virtualenv" failure mode in `recovery-console.md:35-36` and `hotspot-logic.md:8` | **F-299** |
| B13.2 | **Reconcile the manual pip list with `requirements*.txt`.** The hand list at `installation-steps.md:640-646` omits **`pyserial`** (F-276's exact defect, fixed by #133) and **`lgpio`** (annotated "NOT optional" in `requirements-hardware.txt`), and installs nine packages nothing imports. Replace the list with `pip install -r requirements.txt -r requirements-hardware.txt` — one source, not two | **F-300** |
| B13.3 | **Document the dependency layout.** `requirements.txt` / `-hardware` / `-dev`, `docs/requirements-docs.txt`, and the `versions.env` pairing manifest are live and unmentioned anywhere. Say what each is for and which the installer reads | **F-302** |
| B13.4 | **Document the CI, in both repositories.** Five checks on every cinemate PR since #131, and cinepi-raw's first workflow from B10.6. What each protects, and that a ratchet is tightened when reality improves and never raised to make a job pass. Depends on B10.6 landing (#60) | **F-303** |
| B13.5 | **cinepi-raw README: `python-pip` at `:17` cannot install** on any image this project targets — `:51` already gets it right with `python3-pip`. While there: add the test-suite and CI section B10.6 earns | **F-304** |
| B13.6 | **Give the install document step-level correspondence.** `main()` runs **45 named steps**; the prose mirrors none of them and never mentions `align_pi5_kernel_baseline`, the two sensor-support steps, `configure_rp1_overclock`, `refresh_pi5_boot_handoff`, `configure_audio_rtprio` or `seed_redis_defaults` by name. Structure the document so each section names the installer function it corresponds to — that is what makes the two checkable against each other in future, and it closes F-266's missing recovery-console section at the same time | **F-301**, F-266 |
| B13.7 | **Re-check the two claims that rest on retracted premises.** The recovery console's degradation ladder, described in terms of a virtualenv that no longer exists — **read `cinemate-recovery.py` before rewriting**, the mechanism probably survives even though the framing does not, and F-221 records this component as a strength to preserve. And `simple-gui.md:15`'s "2 GB boards" attribution, which PI-016 contradicted for the tested board | F-305, F-306 |

**Why this batch exists at all, stated once:** the audit's own `docs_drift_check.py` passes
clean on a tree where the installation guide builds an environment the installer deletes. A
check that compares names cannot compare meaning. That is a limit of the tooling, not a
failure of it — but it means prose against behaviour stays a **reading** task, and needs
redoing whenever behaviour changes. #138 changed behaviour; this is the redo.

**Ordering:** B13.1 and B13.2 first and together — they are the two that send a reader down a
path that does not work. B13.5 is independent and one line plus a section. B13.6 is the real
work and wants the installer open beside the document.

**Verification:** `docs_drift_check.py` must stay clean and `mkdocs build --strict` must exit
0 — necessary, not sufficient, since both already pass today. **The real verification for
B13.1 and B13.2 is a clean install performed by following the document**, not the script.
That is the only test that distinguishes a doc that is accurate from one that merely parses.

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
| B9 | `redis_key_diff.py` (count must not rise), `design_token_diff.py --strict`, full suite per commit | **B9.1 mount round trip, B9.4 timecode at 24.5/29.97 — mandatory** |
| B10 | `findings_disposition_check.py` at zero unset; `git grep` per deleted symbol | **B10.2 pip removals on a clean install, never on a running camera** |

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
