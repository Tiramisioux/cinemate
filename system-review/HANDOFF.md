Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full — **§9's eight candidate principles are S11's
   spine**, and §1.7 says what the skill payload is for.
2. **Read `system-review/STATE.md` — all of it, before your first grep.** Two sessions have
   been caught skipping it.
3. Read `system-review/sessions/S10-install-drift.md`.
4. Then execute **S11 — CineMate style, philosophy & skill payload** per `PLAN.md`.
   → `CINEMATE-STYLE.md`, `CINEMATE-PHILOSOPHY.md`, `ENTRY-POINTS.md`, `SKILL-PAYLOAD.md`

Phase D is closed. S11 opens Phase E — distillation. **This is the session the whole review
has been feeding**, and four deliverables is a lot: split into S11a/S11b rather than
thinning any of them.

---

## S11 is assembly, not investigation — and the ledger is unusually ready

Ten sessions have produced 182 findings and 8 deliverables. S11's job is to turn them into
four documents a future developer or agent can use **without repo access**. Almost nothing
new needs discovering.

### `CINEMATE-PHILOSOPHY.md` — the one with real intellectual work

KICKOFF §9's eight principles must each be **confirmed, refuted or refined against code**,
and *"where the codebase violates its own principles, those violations are findings."*
Several are already settled:

| principle | evidence |
|---|---|
| "Redis is the single source of live state" | **Refine.** `redis_controller` has the widest fan-in (10 modules, CENSUS §4) — but `get_value()` reads a **cache**, not Redis (S02), four independent `StrictRedis` clients bypass it (F-105), and the enum is convention not enforcement (F-015, F-212). The principle is *aspired to*, not enforced |
| "fail visible, never silent" | **Confirmed as intent, violated in practice.** The project states it at `storage_profiles.py:41-49`. F-130: 15 silently-swallowing handlers. F-204: the state bus dies silently. F-118/F-219: a button that no-ops. F-193: a patch that silently skips |
| duplication policy | **The review's central thesis.** 16 instances, 10 drifted. S06's rule: *duplicated truth must be deleted, or carry a named reason **and** a check. A comment is not a check.* |

**Add what the review found that KICKOFF did not list.** Strong candidates, all evidenced:
*degrade in ladders whose last rung still answers* (F-221, the recovery console, and the
wifi-hotspot ladder); *state the reason in place* (F-192's idempotency comments, F-206's
`/api/v1/cmd` note, F-191's honest "keep in sync by hand"); *the operator must never see a
plausible wrong number* — which F-204 violates and which is the sharpest thing the review
found.

### `CINEMATE-STYLE.md` — derived, not generic

`STANDARDS-PROPOSAL.md` §4 already argues the rules from findings. S05's
`READABILITY-REPORT.md` has the metrics and the PRESERVE list. S09 found **why the accurate
docs are accurate** — tabular, structurally mirroring what they describe, honestly scoped
(`DOCS-DRIFT-REPORT.md` §3) — and that generalises past docs.

**The best material is the strengths.** F-174/F-192/F-194 (the shell), F-221 (the recovery
console), F-206, F-210, F-223, F-234, F-242, F-181. This codebase's own best work is the
style guide; do not import conventions from outside. S06 made that argument and it held.

### `ENTRY-POINTS.md` — "where do I go to change X"

`PLAN.md` calls this the highest-value artifact for future sessions. Every row: task → file
→ function → **what else to update**. That last column is the review's whole thesis made
operational — it is the drift map. Sources: `CODE-MAP-cinemate.md` §3–5,
`CODE-MAP-cinepi-raw.md`, `GUI-STATE-MODEL.md`, `REDUNDANCY-REPORT.md`.

**Blocked-ish:** `cinepi_controller.py` (2626 LOC) is the dispatch target for nearly every
row and **is still untraced** — see below.

### `SKILL-PAYLOAD.md` — self-contained, assumes no repo access

Which means every citation needs enough context to be useful without opening the file.

---

## Do this first, before the four deliverables

**Trace `cinepi_controller.py`.** It has been deferred **six times** — S02 through S10 — and
it is now blocking:

- `ENTRY-POINTS.md`, whose rows mostly land in it;
- **F-025's severity**, which `PI-007 step 1` says may be settleable **at a desk, with no
  hardware** — reading it for internal locking;
- the F-026 claim that its 94 public method names are a user-facing API.

It is 2626 lines, so budget for it — but an AST pass plus targeted reads has worked in every
session that tried it. **If the window is tight, do this and S11a's philosophy document, and
leave style/entry-points/payload for S11b.** Do not write `ENTRY-POINTS.md` without it.

---

## Method warnings — every one earned here

**Read `STATE.md` before the first grep.** S06 skipped it and re-derived five findings.

**Write the checker before the prose that cites it.** Four sessions running. In S10 a
keyword matcher produced **11 false "missing steps"**; grepping each subject dissolved all
eleven. In S09 three of six checks were wrong on the first attempt.

**Most candidate findings dissolve.** S10 recorded 4 and dissolved 4, and the dissolved ones
took longer. Check before writing, every time.

**Withhold a check you cannot trust.** S09 attempted a `cli-commands.md`-vs-dispatcher diff,
could not separate commands from arguments, and reported *that* instead of numbers.

**Say "at least N".** Pattern matching has under-reported six times and over-reported twice.

**Citation discipline.** Line numbers from `grep -n` only, never arithmetic on a `sed`
window.

**Contradict a finding rather than quietly amending it.** F-238 corrects F-008 as its own
row. Corrections are additive and traceable.

## Context that isn't obvious

**Branch:** `claude/cinemate-system-review-kickoff-cilicc`. PR #129 (draft). Ledger-only —
`git add system-review/`, never `-A`. Never commit or push to `dev`.

**Both repos are on `dev`** (STATE.md D2). **Verify before trusting any cinepi-raw figure:**
`git -C /workspace/tiramisioux/cinepi-raw branch --show-current` must print `dev`.

**This clone has no git tags** (F-263).

**Free ID blocks:** F-135..F-149, F-196..F-199, F-268..F-299.

**Four stdlib-only harness checks exist** — `redis_key_diff.py`, `gui_field_extract.py`,
`design_token_diff.py`, `docs_drift_check.py`. Run them rather than re-deriving numbers.

## Still open

- **`cinepi_controller.py` (2626 LOC)** — see above. Deferred six times; do it now.
- **`dng_encoder.cpp` on `dev` changed by 687 lines** — `CODE-MAP-cinepi-raw.md` §4 is a
  `main` account of a rewritten component. Banner is on the file.
- **The `wifi_hotspot` triangle** — two thirds unreached since S04. Its ladder is good
  material for the philosophy doc, so S11 may want it anyway.
- **The 1471 lines of JavaScript in `settings_editor.html`** were scanned, not read.

## For S12, the last session

**The spine is settled and does not need rediscovering:** CineMate has a drift problem, not
a style problem, and four stdlib-only checks are the mechanism. The orderings already exist
— `ADR-001` §6 for the GUI, `STANDARDS-PROPOSAL.md` §9 for tooling, `DOCS-DRIFT-REPORT.md`
§6 for docs, `INSTALL-DRIFT-REPORT.md` §5 for dependencies. **F-204 outranks all of them:**
one raising redis subscriber silently freezes every surface, `get_value()` then serves a
stale cache, and the guarded version of that loop already exists 900 lines away (F-208).
~10 lines, and it should be the first thing anyone does.

## Finish with

Update `STATE.md`, write `sessions/S11-*.md`, overwrite this file for S12, then
`git add system-review/`, commit as `review(S11): ...`, and push.
