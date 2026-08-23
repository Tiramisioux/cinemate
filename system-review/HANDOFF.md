Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full — **§7 especially**, it is S08's entire brief.
2. **Read `system-review/STATE.md` — all of it, before your first grep.**
3. Read `system-review/sessions/S07-gui-inventory.md`, then
   **`deliverables/GUI-STATE-MODEL.md` §6** — it is written as S08's input list.
4. Then execute **S08 — GUI harmonization evaluation → ADR-001** per `PLAN.md`.
   → `decisions/ADR-001-gui-harmonization.md`

---

## Read this before you start: S07 changed the question

KICKOFF §7 frames the decision as *"should we build one shared way of generating all three
GUIs?"* S07 established that **two of the three things such a system would need already
exist**, which changes the option costings materially. Do not evaluate the options against
KICKOFF's framing alone — evaluate them against what is actually in the code.

| Option C would need | Status |
|---|---|
| a shared state model | **exists** — the web GUI already consumes `simple_gui.populate_values()` verbatim, 68 fields, one owner (F-203) |
| a widget/grouping/visibility spec | **exists** — `left_section_layout` / `right_section_layout`, with labels, ordered items, per-item formatters and a `condition` predicate (F-215). Lambdas, so not serialisable — the shape is right, the encoding is not |
| adaptive layout | **does not exist and is the whole problem** — `self.layout` is absolute 1920-reference pixels scaled by `shrink_x`/`shrink_y`. It scales; it does not reflow (F-008) |

**Two consequences to state in the ADR:**

- **Option B (shared tokens only) is now under-ambitious.** It would kill F-007 and F-214,
  but the codebase has already gone further than B on its own. Shipping B means stopping
  short of where the code already is.
- **Option C is cheaper than KICKOFF assumes, and its cost is concentrated in one place.**
  The honest question is not "should we build a spec" but "should we lift the spec that
  exists out of `simple_gui.py` and give the HDMI backend a reflow engine".

## What S07 already answered, with evidence — do not re-derive

| KICKOFF §7 constraint | Answer available now |
|---|---|
| **1. DRM master exclusive** | Confirmed in S03 from cinepi-raw's own comment (`dualHdmiPreviewStage.cpp:5-18`) |
| **2. How the GUI and preview compose** | **Still PI-009 — but narrowed.** F-223: HDMI hot-plug makes the GUI thread restart `cinepi-raw` *"so preview binds to the active display"*. So the preview binds at process start and cannot rebind. Options D and E must own that behaviour. This narrows constraint 2; it does not settle it |
| **5. Failure mode** | **Answered, and the baseline is worse than it looks.** F-204: one raising redis subscriber kills the live-state bus permanently and silently; `get_value()` then serves a stale cache, so *every* surface renders plausible frozen values and none shows an error. Score every option against that, including option A |
| **7. Migration cost** | Partly. Note F-224: `simple_gui` also owns the restart-on-HDMI-attach logic, so a replacement renderer inherits it. The cost is not only pixels |
| **Scope** | **Surface 4 is out.** The recovery console's value is its isolation (F-221); unifying it deletes the property it exists for. Say so explicitly in the ADR and scope the recommendation to surfaces 1, 2, 3 |

Constraints **3 (RAM/CPU)**, **4 (refresh/latency)** and **6 (boot time)** have no numbers
yet. Constraint 4's measurement is **PI-015 step 4**. Do not estimate them from reading —
KICKOFF §2.1 forbids it and §7 says "unknown" is an acceptable answer if queued.

## The two precedents the ADR should lean on

- **F-206 — this project has already done a unification of this kind, and it held.**
  Control flow was routed through `POST /api/v1/cmd` so web, CLI and serial share one path,
  with the reason recorded in the code: *"behaviour cannot drift between them."* That is
  the model. State and presentation are the two that did not get the same treatment.
- **F-218..F-220 — and it has already tried the other way, and that failed.** The
  settings-editor action catalogue exists three times; the two hand-maintained copies agree
  perfectly *including on the same wrong entry*; a comment claims to have corrected the
  catalogue and missed one; and the endpoint that computes the check has zero consumers.

S04's standing verdict follows from both: **verification before unification.** A unification
shipped without a drift check will re-grow the duplicates within a release. S06 turned that
into a concrete mechanism — `STANDARDS-PROPOSAL.md` §3 — and `harness/gui_field_extract.py`
is already half of it.

## Do not

- **Do not answer constraint 2 from reasoning.** PI-009 is still open. F-223 is evidence
  about binding, not about composition.
- **Do not re-inventory the surfaces or re-count fields.** Reproduce instead:
  `python3 system-review/harness/gui_field_extract.py --repo .`
- **Do not rush the recommendation.** `PLAN.md` explicitly permits splitting into S08a/S08b.
  A five-option evaluation against seven constraints is the largest single deliverable in
  the review.

## Method warnings — every one earned here

**Read `STATE.md` before the first grep.** S06 skipped it and re-derived five findings.

**Scripts over reading, then check the script against the source.** S07's extractor
over-counted once (93 vs 68 — it swept in a nested colour dict) and under-counted once (two
Socket.IO events, because it scanned two of three emit sites). Both were caught by
re-checking. Four of S07's five corrections came from that habit.

**Say "at least N".** Pattern matching has under-reported four times in this review and
over-reported twice.

**Citation discipline.** Line numbers from `grep -n` only, never arithmetic on a `sed`
window.

**If you use subagents:** put **"WRITE YOUR REPORT FILE INCREMENTALLY"** in every prompt, in
bold, and save the prompts verbatim before dispatching. Four agents that batched their
writes lost everything to a usage limit; the one told to append as it went preserved 16
findings through the same failure.

## Context that isn't obvious

**Branch:** `claude/cinemate-system-review-kickoff-cilicc`. PR #129 (draft). Ledger-only —
`git add system-review/`, never `-A`.

**cinepi-raw** may need re-cloning (read-only, `main`, shallow, no history):
```
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/Tiramisioux/cinepi-raw /workspace/tiramisioux/cinepi-raw
```

**Free ID blocks:** F-135..F-149, F-196..F-199, F-225..F-249, F-262..F-299.

**`decisions/` does not exist yet.** S08 creates it.

## Still open from earlier sessions

- **`cinepi_controller.py` (2626 LOC) is still untraced** since S02 — now blocking more than
  before: it is the dispatch target for every GUI control and it gates F-025. **PI-007 step
  1 is a desk task** — reading it for internal locking may settle F-025 with no hardware.
- **The `wifi_hotspot` triangle** — two thirds unreached since S04.
- **The 1471 lines of JavaScript in `settings_editor.html`** were scanned, not read.

## Finish with

Update `STATE.md`, write `sessions/S08-*.md`, overwrite this file for S09, then
`git add system-review/`, commit as `review(S08): ...`, and push.
