Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full.
2. Read `system-review/STATE.md` — **especially Deviations D1–D5**.
3. Read `system-review/sessions/S04-attempt-blocked.md`, then
   `sessions/S03-code-map-cinepi-raw.md`.
4. Then **re-run S04 — Redundancy & dead code sweep**.

> **S04 attempt 1 produced nothing.** All four agents died on an account session limit in
> their first step. No agent reports exist; F-100..F-299 are unconsumed. **The four prompts
> are saved verbatim in `agent-reports/S04-AGENT-PROMPTS.md` — start there, it is
> copy-paste.** If capacity is uncertain, launch **two at a time** rather than four;
> agents 1 and 4 are the highest value.

Phase A is complete. Both repos are mapped: `deliverables/CODE-MAP-cinemate.md` and
`deliverables/CODE-MAP-cinepi-raw.md`. Read those before searching for anything.

---

## S04 is the fan-out session — and it is already planned

S01–S03 used no subagents, deliberately: each finding came from chasing the previous one's
loose end, so there was nothing to parallelise. The redundancy sweep is different — it is
embarrassingly parallel.

**All the planning is done.** `agent-reports/S04-AGENT-PROMPTS.md` holds the four prompts
verbatim, including the shared preamble (CONVENTIONS §5.2's six mandatory clauses), the
method warnings, the "already confirmed — do not re-investigate" list, and per-agent
priority targets. Do not rewrite them; launch them.

| Agent | Scope | IDs | Value |
|---|---|---|---|
| 1 | cinemate `src/` | F-100.. | high — largest body of code |
| 2 | services, `_test/`, installer, config | F-150.. | medium |
| 3 | cinepi-raw | F-200.. | medium |
| 4 | cross-boundary duplicated truth | F-250.. | **highest — feeds ADR-001 directly** |

If you can only run two, run **1 and 4**.

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

1. ~~The F-027 key-diff harness script~~ ✅ **done** — `harness/redis_key_diff.py`. It
   reproduces F-027 (84 / 32 / 19 shared / 12 unreferenced) and already caught an
   arithmetic error in that finding. Run it before trusting any hand-counted key figure.
2. **PI-007 step 1** — read `cinepi_controller.py` for internal locking; settles F-025's
   severity without hardware. Still unclaimed.

## Watch this for S08

**PI-009 blocks S08.** DRM master exclusivity is confirmed from source
(`dualHdmiPreviewStage.cpp:5-18` says it outright, and shows the project already worked
around it with SysV shared memory). But how the DRM preview and the fbdev GUI *compose* is
not determinable statically. S08 must not answer KICKOFF §7 constraint 2 from reasoning.

## Start with

`cat system-review/agent-reports/S04-AGENT-PROMPTS.md` and launch from it. The prompts are
already written and reviewed; the previous attempt failed on capacity, not on planning.

## Finish with

Update `STATE.md`, write `sessions/S04-*.md`, overwrite this file for S05, then
`git add system-review/`, commit as `review(S04): ...`, and push.
