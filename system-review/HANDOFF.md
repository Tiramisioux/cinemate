Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full — **§1.7 says what the skill payload is for**.
2. **Read `system-review/STATE.md` — all of it, before your first grep.**
3. Read `system-review/sessions/S11a-controller-and-philosophy.md`, then
   **`deliverables/CINEMATE-PHILOSOPHY.md`** — S11b's three documents are its consequences.
4. Then execute **S11b** — the other three S11 deliverables:
   → `CINEMATE-STYLE.md`, `ENTRY-POINTS.md`, `SKILL-PAYLOAD.md`

S11 was split. **S11a is done**: `cinepi_controller.py` is traced (the six-times-deferred
item), the philosophy is written, and PI-007 step 1 is discharged. The blocker on
`ENTRY-POINTS.md` is gone.

---

## S11b is assembly. Almost nothing new needs discovering.

Eleven sessions, 186 findings, 10 deliverables. The material is on disk.

### `ENTRY-POINTS.md` — do this one first; it is the highest-value artifact

`PLAN.md` calls it that, and it is now unblocked. Every row: **task → file → function →
what else to update.** That last column is the review's thesis made operational — it is the
drift map, and it is the thing a future developer or agent will actually open.

Sources, in order of usefulness:
`CODE-MAP-cinemate.md` §3–5 (28-step boot order, thread table, both dispatch paths) ·
`REDUNDANCY-REPORT.md` (the 16 duplicated-truth instances *are* the "what else to update"
column) · `GUI-STATE-MODEL.md` (68 fields, provider per field) · `CODE-MAP-cinepi-raw.md`
(mind its correction banner) · F-270's shape of the controller.

**Rows that matter most, because each has a non-obvious second edit:**
add a Redis key · add a controller method (**four registries** — F-218, F-242) · add a
settings key (**schema cannot reject a typo**, F-166) · add a GUI field (**one dict, two
renderers**, F-203) · add a colour (**16 tokens, 3 annotated**, F-232) · add a dependency
(**two registries**, F-003, and S10 chose option 2) · add a service · add a CLI command.

### `CINEMATE-STYLE.md` — derived, not generic

`STANDARDS-PROPOSAL.md` §4 already argues each rule from a finding. `READABILITY-REPORT.md`
has the metrics and the PRESERVE list. `DOCS-DRIFT-REPORT.md` §3 explains why the accurate
docs are accurate (tabular / structurally mirroring / honestly scoped) and that generalises.

**Build it from the strengths, not the defects.** F-174/F-192/F-194 (the shell is the
best-maintained code here) · F-221 (the recovery console) · F-206 · F-210 · F-223 · F-234 ·
F-242 · F-181. S06 argued that this codebase's own best work is the style guide rather than
imported convention, and it held for five sessions since.

**P10 from the philosophy is the style rule that matters most:** *state the reason in place,
especially for a compromise.* Where the codebase does this the code is trustworthy; where it
skips it, the same construct is a defect. That is a style rule with evidence on both sides.

### `SKILL-PAYLOAD.md` — self-contained, assumes no repo access

Which means every citation carries enough context to be useful without opening the file.
Budget for it properly; it is not a copy-paste of the other three.

---

## Method warnings — every one earned here

**Read `STATE.md` before the first grep.** S06 skipped it and re-derived five findings.

**Cross-check a grep against a second, differently-shaped grep.** S11a read the controller as
having no internal locking because the pattern required a leading underscore and missed
`parameters_lock_obj`'s four sites. Comparing the *declaration* list against the *usage* list
caught it. Sixth under-report of the review.

**Most candidate findings dissolve.** S10 recorded 4 and dissolved 4, and the dissolved ones
took longer.

**Write the checker before the prose that cites it.** Four sessions running.

**Withhold a check you cannot trust** — S09's `cli-commands.md` diff.

**Say "at least N".** Under-reported six times, over-reported twice.

**Citation discipline.** Line numbers from `grep -n` only, never `sed`-window arithmetic.

**Contradict a finding rather than quietly amending it.** F-238 corrects F-008; F-268
broadens F-025. Both are their own rows with their own citations.

## Context that isn't obvious

**Branch:** `claude/cinemate-system-review-kickoff-cilicc`. PR #129 (draft). Ledger-only —
`git add system-review/`, never `-A`. Never commit or push to `dev`.

**Both repos are on `dev`** (STATE.md D2). Verify:
`git -C /workspace/tiramisioux/cinepi-raw branch --show-current` must print `dev`.

**This clone has no git tags** (F-263).

**Free ID blocks:** F-135..F-149, F-196..F-199, F-272..F-299.

**Four stdlib-only harness checks exist** — `redis_key_diff.py`, `gui_field_extract.py`,
`design_token_diff.py`, `docs_drift_check.py`. Run them rather than re-deriving numbers;
they belong in `ENTRY-POINTS.md`'s rows as the "what else to update" enforcement.

## Still open

- **`dng_encoder.cpp` on `dev` changed by 687 lines** — `CODE-MAP-cinepi-raw.md` §4 is a
  `main` account of a rewritten component. Banner is on the file. Largest cinepi-raw hole.
- **The `wifi_hotspot` triangle** — two thirds unreached since S04. Its credential ladder is
  now cited in philosophy P7/P9, so S11b may want to read it properly.
- **The 1471 lines of JavaScript in `settings_editor.html`** were scanned, not read.

## For S12, the last session

**The spine is settled and does not need rediscovering.** From S11a, stated as the review's
thesis in its final form:

> *This project knows what it believes, states it in prose, and enforces it nowhere — and
> where a principle is violated, the correct implementation usually exists a few hundred
> lines away.*

Three instances to lead with: **F-204/F-208** (the state bus dies silently; the guarded loop
is 900 lines away) · **F-271/`write_config_file`** (the settings editor destroys 74 comment
lines; the backing-up version is 1000 lines away) · **F-118/F-219** (a drifted catalogue; the
check is written and unwired).

The orderings already exist — `ADR-001` §6 for the GUI, `STANDARDS-PROPOSAL.md` §9 for
tooling, `DOCS-DRIFT-REPORT.md` §6 for docs, `INSTALL-DRIFT-REPORT.md` §5 for dependencies.
**F-204 outranks all of them: ~10 lines, and it should be first.** F-271 is second and about
as small.

## Finish with

Update `STATE.md`, write `sessions/S11b-*.md`, overwrite this file for S12, then
`git add system-review/`, commit as `review(S11b): ...`, and push.
