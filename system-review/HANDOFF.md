Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full.
2. **Read `system-review/STATE.md` — all of it, before your first grep.** Two sessions have
   been caught skipping it.
3. Read `system-review/sessions/S09-docs-drift.md`.
4. Then execute **S10 — Install script vs. install docs** per `PLAN.md`.
   → `deliverables/INSTALL-DRIFT-REPORT.md`

---

## S10's brief overlaps work already done — read this before starting

`PLAN.md` S10 lists five tasks. **Two are finished** and one is settled:

| S10 asks for | Status |
|---|---|
| run `shellcheck` on the installer, record warning classes | **Done — S06.** 15 findings across all 11 scripts, **1** in the 1916-line installer. F-174..F-179 have the classes. It is a **strength**, not a problem area |
| check idempotency and failure handling by reading | **Done — S06, F-192.** Idempotent *by construction*: `MANAGED_BEGIN`/`END` delete-then-rewrite, `ensure_repo` guards, a `grep -q`-guarded source patch whose comment states the reasoning. One gap: F-193, the libcamera patch has no `else` branch, so an upstream change makes it a silent no-op |
| the dependency divergence | **Settled — F-002/F-003.** `findings/F-003.md` has both package lists. S10 *chooses between the two remediation options*; it does not recount |

**So S10's real job is the correspondence table:** `cinemate-install.sh` (1916 LOC) against
`docs/installation-steps.md` (1061 LOC), step by step, plus `services/` against what the
docs claim gets installed.

### What S09 hands S10 directly

**`installation-steps.md` is the largest doc in the repo (1061 LOC) and S09 did not read
it.** S09's mechanical checks covered it — its links resolve and its citations are all
runtime paths, correctly absent — but nobody has read it against the installer. That is
S10's whole deliverable and it is genuinely unexamined.

S09's transferable result: **the docs turned out to be the best-maintained boundary in the
system** (F-240), and the accurate ones are accurate because they are tabular, structured to
mirror what they describe, and honestly scoped. A step-by-step installer doc is exactly that
shape. **Expect it to be better than the review's priors suggest, and be ready to say so.**

But note the counter-evidence in the same session: F-245, the one substantive docs error,
was a *scope* claim — "the CLI, serial and GPIO paths" where GPIO does not qualify. Installer
docs are full of scope claims ("this step installs X"). Check the scope of each claim, not
just whether the named thing exists.

### Known installer-side findings to carry in

F-163 (`python3-systemd` reachable only through dead code; F-032's unused list becomes 8 of
11) · F-161 (`services/cinemate-services.Makefile` recurses into three deleted directories)
· F-162 (`services/Makefile` `uninstall` targets generate no recipe) · F-165 (root
`CMakeLists.txt` references a directory that does not exist, so `cmake .` fails immediately)
· F-182 (`INSTALL_ALT_GPIO_BACKEND` advertised as optional but load-bearing for boot →
PI-012) · F-236 (`camera-ready.sh` can hold `ExecStartPre` ~30 s) · F-195 (the two scripts
the installer *generates* are never linted by anything).

---

## Method warnings — every one earned here

**Read `STATE.md` before the first grep.** S06 skipped it and re-derived five findings.

**Write the checker before the prose that cites it.** Three sessions running, this has
caught errors that would otherwise have shipped. In S09, three of six checks were wrong on
the first attempt and one would have appeared to contradict a settled finding (F-014).

**Withhold a check you cannot trust.** S09 attempted a `cli-commands.md`-vs-dispatcher diff,
got 14 false positives it could not separate from real ones, and reported *that* instead of
the numbers. An inconclusive result stated plainly is worth more than a confident wrong one.

**Say "at least N".** Pattern matching has under-reported six times in this review and
over-reported twice.

**Citation discipline.** Line numbers from `grep -n` only, never arithmetic on a `sed`
window.

**Contradict a finding rather than quietly amending it.** F-238 corrects F-008 as its own
row with its own citations. Corrections are additive and traceable.

## Context that isn't obvious

**Branch:** `claude/cinemate-system-review-kickoff-cilicc`. PR #129 (draft). Ledger-only —
`git add system-review/`, never `-A`. Never commit or push to `dev`.

**Both repos are on `dev`** (STATE.md D2). **Verify before trusting any cinepi-raw figure:**
`git -C /workspace/tiramisioux/cinepi-raw branch --show-current` must print `dev`.

**This clone has no git tags** (F-263) — anything asking for a diff against a release tag
cannot be done here. Say so rather than approximating.

**Free ID blocks:** F-135..F-149, F-196..F-199, F-264..F-299.

**Four stdlib-only harness checks exist** — `redis_key_diff.py`, `gui_field_extract.py`,
`design_token_diff.py`, `docs_drift_check.py`. Run them rather than re-deriving their
numbers. All four are candidates for the CI job in `STANDARDS-PROPOSAL.md` §3.

## Still open — S11 and S12 will need these

- **`cinepi_controller.py` (2626 LOC) is untraced** since S02 — **deferred five times.** It
  is the dispatch target for every GUI control and it gates F-025's severity. **PI-007 step
  1 is a desk task, not a Pi task.** If S10 finishes early, do this instead of extending
  S10's scope.
- **`dng_encoder.cpp` on `dev` changed by 687 lines** — `CODE-MAP-cinepi-raw.md` §4 is a
  `main` account of a rewritten component. Banner is on the file. Largest cinepi-raw hole.
- **The `wifi_hotspot` triangle** — two thirds unreached since S04.
- **The 1471 lines of JavaScript in `settings_editor.html`** were scanned, not read.

## For S11 and S12

**S11 (style/philosophy) has two strong new inputs from S09:** the accurate docs are
accurate for three identifiable reasons (tabular / structurally mirroring / honestly
scoped — `DOCS-DRIFT-REPORT.md` §3), and **prose inside the code rots where `docs/` does
not** (§4). The second is the sharpest argument yet for S05's F-133 recommendation to
promote the 47 load-bearing why-comments into `docs/`.

**S12's spine is settled:** CineMate has a drift problem, not a style problem, and four
stdlib-only checks are the mechanism. `ADR-001` §6 orders the GUI work;
`STANDARDS-PROPOSAL.md` §9 orders the tooling; `DOCS-DRIFT-REPORT.md` §6 orders the docs.
**F-204 outranks all three** — one raising redis subscriber silently freezes every surface,
and the guarded version of that loop already exists 900 lines away (F-208). ~10 lines, first.

## Finish with

Update `STATE.md`, write `sessions/S10-*.md`, overwrite this file for S11, then
`git add system-review/`, commit as `review(S10): ...`, and push.
