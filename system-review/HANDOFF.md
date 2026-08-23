Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full.
2. **Read `system-review/STATE.md` — all of it, before your first grep.** S06 skipped this
   step and re-derived five findings that S01 had already recorded. The "Do not redo" list
   only works if it is read.
3. Read `system-review/sessions/S06-standards.md`.
4. Then execute **S07 — GUI surface inventory & state-model extraction** per `PLAN.md`.

---

## S07 is the biggest single session left. Budget accordingly.

Three-plus GUI surfaces, and KICKOFF §6.3 wants **every surface, every widget, every
control, every field**, plus the surface × field matrix with a source of truth per field.
This is the input to ADR-001 and the review's most consequential open decision rests on it.

**This is the right session for a subagent fan-out** — one agent per surface, reserved
finding-ID blocks, each writing its own file. See the method warnings below; they are not
optional.

### What is already established — do not re-derive

| S07 needs | Already in the ledger |
|---|---|
| the HDMI GUI's layout model | **F-008** — 1920-reference absolute constants, proportionally scaled via `simple_gui.py:1657-1658`. It *scales*, it does not reflow. This is the crux, not a detail. |
| colour constants | **F-007** — Python tuples in `simple_gui.py:21-45` vs CSS custom properties in `app/templates/template.html:23-40`, synced only by a comment |
| the settings-editor catalogue | **F-118** — and it has already shipped a silent no-op button (`set_log` vs `set_log_encode`) |
| Redis as the shared state bus | `CODE-MAP-cinemate.md` §4, `CODE-MAP-cinepi-raw.md`, F-027 |
| an off-hardware render precedent | `_test/test_simple_gui_preview_guide.py` — **read this first.** It already exercises `simple_gui` without a Pi. Do not reinvent the stubbing approach. |
| dead templates | **F-001** — four unreferenced HTML templates, 928 LOC |

### Two things S06 hands S07 directly

- **F-166/F-167.** `settings.schema.json` cannot reject an unknown key
  (`"additionalProperties": true` 25×, `false` 0×), and the `quad_rotary_controller.encoders`
  block — the most reflectively-dispatched config in the system — is declared as a bare
  `{"type": "object"}`. Any GUI that edits settings is editing an unvalidated document.
- **The framing.** S06's thesis is that this codebase has a *drift* problem, not a style
  problem. The GUI inventory is the place that claim gets its strongest test: if the surface
  × field matrix shows the same field with a different source of truth per surface, that is
  the same finding again, and ADR-001 has to answer it.

---

## Method warnings — every one earned in this review

**Incremental agent writes are mandatory, not advice.** Four agents that batched their
writes lost everything to a usage limit; the one instructed to append as it went preserved
16 findings through the same failure. Put **"WRITE YOUR REPORT FILE INCREMENTALLY"** in every
agent prompt, in bold. Save the prompts verbatim before dispatching.

**Verify agent claims before merging.** S04 corrected two of 40 — one overstated, one
understated. Both took one grep.

**Pattern matching has under-reported three times** (`cinepi_ready_<port>`, `tc_key`,
`from module import X` — the last put five *live* modules on a dead list) **and
over-reported once** (S06's 88 "unvalidated" schema keys, most of which were covered by
`additionalProperties` subschemas). Probe the structure before counting it, and say
"at least N".

**Citation discipline.** Line numbers from `grep -n` only, never arithmetic on a `sed`
window. S02 and S03 both shipped off-by-one citations that way.

---

## Context that isn't obvious

**Branch:** `claude/cinemate-system-review-kickoff-cilicc`. PR #129 (draft). Ledger-only —
`git add system-review/`, never `-A`.

**cinepi-raw** may need re-cloning (read-only, `main`, shallow, no history):
```
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/Tiramisioux/cinepi-raw /workspace/tiramisioux/cinepi-raw
```

**Free ID blocks:** F-135..F-149, F-196..F-199, F-203..F-249, F-262..F-299.
Allocate per-agent blocks from these and record the allocation in `CONVENTIONS.md`.

## Still open from earlier sessions

- **The `wifi_hotspot` triangle** — two thirds unreached. Only the `_test/` copy (F-150).
- **Settings keys defined-but-never-read.** The schema side is done (F-166, F-167); the
  liveness side needs an AST pass over the `get`/`setdefault` chains, not a grep.
- **`cinepi_controller.py` (2626 LOC) internals are still untraced** since S02. It is the
  largest remaining unknown on the Python side and it gates F-025's severity — **and S07
  will need it**, because it is the dispatch target for every GUI control.

## Watch for S08

**PI-009 blocks S08.** DRM master exclusivity is confirmed from cinepi-raw's own comment
(`dualHdmiPreviewStage.cpp:5-18`), but how the DRM preview and the fbdev GUI *compose* is
not determinable statically. S08 must not answer KICKOFF §7 constraint 2 from reasoning.

S04's standing verdict for S08 is **verification before unification** — a GUI unification
shipped without a drift check will re-grow the duplicates within a release. The codebase
already tried comments as the sync mechanism and the comments drifted. S06 turned that into
a concrete rule; §3 of `STANDARDS-PROPOSAL.md` is the mechanism ADR-001 should assume exists.

## Finish with

Update `STATE.md`, write `sessions/S07-*.md`, overwrite this file for S08, then
`git add system-review/`, commit as `review(S07): ...`, and push.
