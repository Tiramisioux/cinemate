Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full.
2. Read `system-review/STATE.md` — **especially Deviations D1–D5**.
3. Read `system-review/sessions/S03-code-map-cinepi-raw.md`.
4. Then execute **S04 — Redundancy & dead code sweep** as specified in
   `system-review/PLAN.md`.

Phase A is complete. Both repos are mapped: `deliverables/CODE-MAP-cinemate.md` and
`deliverables/CODE-MAP-cinepi-raw.md`. Read those before searching for anything.

---

## S04 is the fan-out session — the first one that genuinely suits it

S01–S03 used no subagents, deliberately: each finding came from chasing the previous
one's loose end, so there was nothing to parallelise. **The redundancy sweep is different**
— it is embarrassingly parallel. Use up to 4 agents (KICKOFF §2.5) and follow the six
mandatory prompt clauses in `CONVENTIONS.md` §5.2 verbatim.

Suggested split, with reserved ID blocks already allocated in `CONVENTIONS.md` §5.1:

| Agent | Scope | IDs |
|---|---|---|
| 1 | cinemate `src/` — unreferenced modules, unreachable code, dead branches | F-100.. |
| 2 | cinemate `services/`, `_test/`, installer, config keys | F-150.. |
| 3 | cinepi-raw — dead sources, unused build targets, the two patch files | F-200.. |
| 4 | duplicated logic across the Python/C++/CSS boundary | F-250.. |

Agent 4 has the most interesting brief: F-007 (colours), F-016 (`audio_vu`) and F-027/F-028
(key registries) are all the same defect class. A fourth or fifth instance would make the
pattern conclusive for ADR-001.

**Do not let agents re-investigate what is already confirmed dead.** `PLAN.md` S04 now has
two explicit lists: things to fold into the report without re-checking, and the genuinely
open candidates. Put the "already confirmed" list in every agent prompt.

---

## Context you need that isn't obvious

**Branch:** `claude/cinemate-system-review-kickoff-cilicc`. PR #129 (draft). Ledger-only
commits — `git add system-review/`, never `-A`.

**cinepi-raw** may need re-cloning (read-only, lands on `main`, no history):
```
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/Tiramisioux/cinepi-raw /workspace/tiramisioux/cinepi-raw
```

**A caveat S04 must respect.** S03's key counts are **lower bounds**, not a census —
pattern matching cannot see dynamically constructed keys, and at least one important one
exists (`cinepi_ready_<port>`, built by string concatenation on both sides, in neither
registry). Any agent doing key or symbol analysis must say "at least N", not "N".

**"Unreferenced" is not "dead".** F-027's PLL keys are reachable by `redis-cli` and read
like a deliberate tuning surface. Agents should classify as *unreferenced* and note what
would settle it, not declare things dead. This distinction is the difference between a
useful report and one the operator cannot act on.

**Citation discipline — this has bitten two sessions running.** Cite line numbers from
`grep -n` output only. Never derive them from arithmetic on a `sed -n 'A,Bp'` window; S02
and S03 both shipped off-by-one citations that way and had to correct them. Re-grep every
derived citation before commit. Put this in the agent prompts.

---

## Do not re-do

- Either code map, or anything in them — boot order, thread tables, dispatch paths, the
  frame lifecycle, build targets, display ownership.
- The cross-repo Redis key diff — `findings/F-027.md`.
- The cinemate Redis key census — `ParameterKey` at `redis_controller.py:18`.
- Verifying F-001..F-033.
- Counting docs or auditing the mkdocs nav — `CENSUS.md` §9.

## Cheap, high-value, currently unclaimed

If S04 finishes early, these beat starting S05:

1. **The F-027 key-diff harness script.** Parse `ParameterKey` from `redis_controller.py`
   and `CONTROL_KEY_*` from `cinepi_state.hpp`; report shared / cinemate-only /
   cinepi-raw-only. Turns the review's best finding into a check that cannot regress. No
   hardware. Belongs in `harness/`. **This is the single highest value-per-effort item in
   the ledger.**
2. **PI-007 step 1** — read `cinepi_controller.py` for internal locking; settles F-025's
   severity without hardware.

## Watch this for S08

**PI-009 blocks S08.** DRM master exclusivity is confirmed from source
(`dualHdmiPreviewStage.cpp:5-18` says it outright, and shows the project already worked
around it with SysV shared memory). But how the DRM preview and the fbdev GUI *compose* is
not determinable statically. S08 must not answer KICKOFF §7 constraint 2 from reasoning.

## Start with

Read both code maps, then write the four agent prompts before launching anything — the
prompts are the work product that determines whether this session is worth its window.

## Finish with

Update `STATE.md`, write `sessions/S04-*.md`, overwrite this file for S05, then
`git add system-review/`, commit as `review(S04): ...`, and push.
