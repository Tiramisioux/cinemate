# S04 (attempt 2) — Redundancy & dead code sweep

**Date:** 2026-08-18 · **Phase:** B
**Outcome:** delivered, with one scope outstanding.
**Deliverable:** `deliverables/REDUNDANCY-REPORT.md`
**Yield:** 41 net new findings (43 raised, 2 merged). Ledger total 76.

---

## How it ran

Attempt 1 died entirely on an account usage limit (`sessions/S04-attempt-blocked.md`).
Attempt 2 launched **two** agents rather than four, per that session's own advice, and the
coordinator ran a third scope inline so nothing sat idle.

| Scope | Who | Result |
|---|---|---|
| cinemate `src/` | agent 1 | ✅ 28 findings, F-100..F-127 |
| cross-boundary duplicated truth | agent 4 | ✅ 12 findings, F-250..F-261 |
| cinepi-raw | coordinator, inline | ✅ 3 findings, F-200..F-202 |
| services / `_test/` / installer | **not run** | ❌ owed — prompt is ready |

Both agents were told to **write their report file incrementally**. That instruction was
added after attempt 1 lost everything, and it paid off: agent 1 noted a mid-run commit
captured its file at F-125 and the final version was a strict superset.

## The result that matters

The review had three instances of duplicated truth and an open question: pattern or
coincidence? **Pattern — 16 instances, and nine have already drifted.** Full table in the
deliverable §1.

The single most damning one is **F-118**: the 46-entry action catalogue is duplicated
verbatim between Python and JS, it offers `set_log` where the real method is
`set_log_encode`, and so a settings-editor button **silently does nothing today**. The only
thing that could have caught it, `GET /api/actions`, has no consumer.

Behind that, a self-referential detail worth keeping: three of the duplicate copies are
hand-maintained *comments indexing the duplication*, and two of those comments are
themselves already wrong. The codebase tried manual synchronisation; the manual
synchronisation drifted.

## Coordinator corrections to agent output

Per CONVENTIONS §5.2 the coordinator merges and resolves — which here meant verifying, not
just copying.

- **F-112 downgraded high → medium.** The commented-out `if is_mounted:` guard making
  `unmount_drive()` run unconditionally is real. The agent's added claim that the CFE-HAT
  branch calls a non-existent `mount_cfe` is wrong — that whole `else` branch is commented
  out too, so it calls nothing. Checked at `cinepi_controller.py:2032-2040`.
- **F-107 upgraded low/probable → medium/confirmed, re-scoped to both repos.** Reported as
  "MIC_* keys with no reader"; checking cinepi-raw showed it publishes *the same five keys*
  at `cinepi_sound.cpp:1783-1789`, duplicating even the debug string. Two writers, zero
  readers — the fifth cross-repo duplication, not a dead-key finding.
- **F-110 → F-017** and **F-113 → F-019** merged as duplicates, keeping agent 1's preferred
  remediation for the latter (add `FSCK_STATUS` to `ParameterKey`, don't delete).

Also normalised agent 4's confidence column: it used `high`, the ledger vocabulary is
`confirmed`/`probable`/`unverified`. Code-level claims → `confirmed`; the two field-impact
caveats became PI-010 and PI-011 rather than being flattened away.

## A correction to the review's own earlier work

Agent 1 **disproved four of the targets S01 handed it**. `parameters.py`,
`app/raw_files.py`, `app/boot_config.py`, `mediator.py` and `utils.py` are all live.

The cause was a real bug in the S01 import graph, not just its stated caveat: the regex
read `from module import parameters` as an edge to `module`, hiding three live importers.
`CENSUS.md` §4 now carries the correction at the top and defers to F-122 (exactly 4 of 48
modules unreachable).

**This is the third time pattern-matching has under-reported in this review** — after
`cinepi_ready_<port>` and `tc_key`, both dynamically built Redis keys. The deliverable
states the generalisation: treat absence of a grep hit as a hypothesis, not a result.

## Negative results

- **No triple sensor table.** `resources/sensors.json` is a genuine single source; cinepi-raw
  encodes no sensor data at all. The review's biggest duplication hypothesis is disproved.
- `settings.schema.json` agrees with `config_loader.py` on all 41 comparable defaults — so
  it is the viable origin for unification work.
- Module reachability in `src/` is exhausted.

## What S04 owes

Agent 2's scope (services, `_test/`, installer, config keys) was never run — the session
deliberately ran two agents instead of four after attempt 1's failure. The prompt is ready
in `agent-reports/S04-AGENT-PROMPTS.md`. Listed in the deliverable §7 with the specific
open items, plus a new one from agent 1: `python3-systemd` becomes an unused install
dependency once F-109 lands.

**Recommendation:** run agent 2 at the start of S05 rather than opening a third S04, then
proceed. It is one agent's worth of work and S05's readability pass does not depend on it.
