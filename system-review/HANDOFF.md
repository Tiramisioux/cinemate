Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full.
2. **Read `system-review/STATE.md` — all of it, before your first grep.** Two sessions have
   been caught skipping it.
3. Read `system-review/sessions/S08-adr-001.md`.
4. Then execute **S09 — Docs vs. code** per `PLAN.md`.
   → `deliverables/DOCS-DRIFT-REPORT.md`

Phase C is closed. **ADR-001 is written and `proposed`.** S09 opens Phase D.

---

## S09 has a strong head start — do not recount

| S09 asks for | Already established |
|---|---|
| the docs inventory | **F-004 / `CENSUS.md` §9** — 50 docs, 35 nav entries, **15 unreachable**, 5 empty, 6 commented-out nav lines. Complete. Start there |
| `redis-keys.md` vs the code | **F-014** — docs are a strict subset: 18 undocumented keys, 0 orphan docs. The gap clusters around dual-sensor and dynamic-resolution work |
| `settings-json.md` vs schema | Partly — **F-166/F-167**: the schema cannot reject an unknown key (`additionalProperties: true` 25×, `false` 0×), and `encoders`/`rotary_encoders` are declared with no properties at all |
| the cross-repo key contract | **F-027**, re-measured on `dev`: 84 / 36 / 23 shared / 12 unreferenced (F-226). Reproduce with `harness/redis_key_diff.py`, do not hand-count |
| `simple-gui-refresh-tuning.md` | **Done — F-234. It is accurate**, every value matches the code. One doc you can mark verified without re-reading |
| `cli-user-guide.md` on `--same-hdmi` | Spot-checked accurate (F-229) |

**The interesting question for S09 is not "how much is wrong" — it is which docs are
*accurate*, and why those.** F-234 and F-229 are two accurate ones. This review has recorded
a lot of drift; a docs pass that only counts errors will miss the more useful pattern.

### Two things S09 should carry from earlier sessions

- **F-133's 47 load-bearing comments should be promoted into `docs/`** before anyone
  refactors those files. S05 flagged them as a deletion hazard. S09 is the natural session
  to decide which become documentation.
- **Three hand-sync comments have drifted** (F-260, F-183, F-220) and a fourth kind exists
  in CSS (F-217). Comments that *claim* to index something else are a docs-drift category
  of their own, and grepping for that shape is cheap.

---

## Method warnings — every one earned here

**Read `STATE.md` before the first grep.** S06 skipped it and re-derived five findings.

**Write the checker before the prose that depends on it.** S08's design-token script caught
two of that session's four corrections, including one that would have shipped a false
finding.

**Say "at least N".** Pattern matching has under-reported four times in this review and
over-reported twice.

**Citation discipline.** Line numbers from `grep -n` only, never arithmetic on a `sed`
window.

**Contradict a finding rather than quietly amending it.** F-238 corrects F-008, a KICKOFF
seed finding, and is recorded as its own row with its own citations. Corrections are
additive and traceable.

**If you use subagents:** put **"WRITE YOUR REPORT FILE INCREMENTALLY"** in every prompt, in
bold, and save the prompts verbatim before dispatching.

## Context that isn't obvious

**Branch:** `claude/cinemate-system-review-kickoff-cilicc`. PR #129 (draft). Ledger-only —
`git add system-review/`, never `-A`. Never commit or push to `dev`.

**Both repos are on `dev`** (STATE.md D2). **Verify before trusting any cinepi-raw figure:**
`git -C /workspace/tiramisioux/cinepi-raw branch --show-current` must print `dev`. If the
clone is missing:
```
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --branch dev \
  https://github.com/Tiramisioux/cinepi-raw /workspace/tiramisioux/cinepi-raw
```

**Free ID blocks:** F-135..F-149, F-196..F-199, F-240..F-249, F-262..F-299.

**Three stdlib-only harness checks exist** — `redis_key_diff.py`, `gui_field_extract.py`,
`design_token_diff.py`. None needs hardware. Run them rather than re-deriving their numbers.

## Still open — and S12 will need these

- **`cinepi_controller.py` (2626 LOC) is untraced** since S02. It is the dispatch target for
  every GUI control and it gates F-025's severity. **PI-007 step 1 is a desk task**, not a
  Pi task — reading it for internal locking may settle F-025 for free. This is now the
  largest unknown on the Python side and it has been deferred four times.
- **`dng_encoder.cpp` on `dev` changed by 687 lines** — `CODE-MAP-cinepi-raw.md` §4's frame
  lifecycle is a `main` account of a rewritten component, and the new CCMP preview stage and
  LOG-LUT subsystem are not in the map at all. Banner is on the file. Largest cinepi-raw
  hole.
- **The `wifi_hotspot` triangle** — two thirds unreached since S04.
- **The 1471 lines of JavaScript in `settings_editor.html`** were scanned, not read.

## For S12, when it arrives

The remediation plan has one spine already: **CineMate has a drift problem, not a style
problem** — and the three checks above are the mechanism. ADR-001 §6 orders the GUI work;
`STANDARDS-PROPOSAL.md` §9 orders the tooling. **F-204 outranks both** — one raising redis
subscriber silently freezes every surface, and the guarded version of that loop already
exists 900 lines away (F-208). It is ~10 lines and it should be first.

## Finish with

Update `STATE.md`, write `sessions/S09-*.md`, overwrite this file for S10, then
`git add system-review/`, commit as `review(S09): ...`, and push.
