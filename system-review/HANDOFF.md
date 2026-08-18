Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full.
2. Read `system-review/STATE.md` — **especially Deviations D1–D5**.
3. Read `system-review/sessions/S04-redundancy-sweep.md`.
4. **First**, run agent 2's unrun S04 scope (below). **Then** execute
   **S05 — Readability, comments & structure** per `system-review/PLAN.md`.

---

## First: S04 owes one scope

S04 ran two agents plus one inline scope and delivered
`deliverables/REDUNDANCY-REPORT.md`. **Agent 2's scope was never run** — services, `_test/`,
`cinemate-install.sh`, `cinemate-update.sh`, config keys, Makefiles, `scripts/`,
`resources/`.

Its prompt is ready verbatim in `agent-reports/S04-AGENT-PROMPTS.md` (§"Agent 2"). Use ID
block **F-150..F-199** — untouched. It is one agent's worth of work; do it first, merge into
`FINDINGS.md`, then start S05. Do not open a third S04 session for it.

Specific open items it should settle, listed in `REDUNDANCY-REPORT.md` §7:
- Three-way `wifi_hotspot` duplication (753 / 52 LOC + a `_test/` copy)
- Whether `services/storage-automount/storage-automount.py` (~1123 LOC) duplicates
  `usb_monitor.py` / `ssd_monitor.py`
- Settings keys defined but never read; keys read but absent from the schema
- Installer idempotency by reading, and `shellcheck` warning classes
- **New:** `python3-systemd` (`cinemate-install.sh:523`) becomes an unused install
  dependency once F-109 lands — add to the F-032 list

---

## What S04 established that changes later sessions

**Duplicated truth is systemic — 16 instances, 9 already drifted.** This is now the
review's central structural finding. `REDUNDANCY-REPORT.md` §1 has the table, §6 has what
it means for ADR-001. The short version for S08:

> "One source of truth, N renderers" is viable for cinemate-internal data but should be
> scoped **out** for the cinepi-raw boundary. The binding constraint is not language count
> — it is that **nothing verifies anything**. A test runner plus ~5 cross-registry
> assertions would catch 5 of the 6 drifts with no architectural change. A GUI unification
> shipped without one will re-grow these duplicates within a release.
> **Sequencing: verification before unification.**

**≈3,250 LOC of confirmed-dead source** is deletable without hardware — S12's easiest batch.

**Three closed avenues — do not re-open:**
- Module reachability in `src/` is exhausted (F-122: exactly 4 of 48 unreachable).
- There is no duplicated sensor table. `resources/sensors.json` is a genuine single source.
- `settings.schema.json` agrees with `config_loader.py` on all 41 comparable defaults.

---

## Method warnings — earned, not theoretical

**Pattern matching has under-reported three times in this review.** `cinepi_ready_<port>`
(S03), `tc_key` (S04), and `from module import X` (S04, which put five live modules on a
dead list in `CENSUS.md` §4). **Treat "no grep hit" as a hypothesis, never a result**, and
say "at least N" for any count derived that way.

**Citation discipline.** Line numbers from `grep -n` only, never from arithmetic on a
`sed -n 'A,Bp'` window. S02 and S03 both shipped off-by-one citations that way.

**Tell agents to write their report file incrementally.** Attempt 1 of S04 lost four agents'
work entirely to a usage limit; attempt 2 added that instruction and one agent's file
survived a mid-run interruption as a strict superset.

**Verify agent claims before merging.** S04 corrected two of 40 agent findings — one
overstated (F-112 claimed a call to a non-existent method; that branch is commented out),
one understated (F-107 was a cross-repo duplication, not a dead key). Both were caught by
one grep each.

---

## Context that isn't obvious

**Branch:** `claude/cinemate-system-review-kickoff-cilicc`. PR #129 (draft). Ledger-only —
`git add system-review/`, never `-A`.

**cinepi-raw** may need re-cloning (read-only, `main`, shallow, no history):
```
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/Tiramisioux/cinepi-raw /workspace/tiramisioux/cinepi-raw
```

**Free ID blocks:** F-128..F-149, F-150..F-199 (agent 2), F-203..F-249, F-262..F-299.

**`harness/redis_key_diff.py` works** — run it before trusting any hand-counted key figure.
It should grow a check that flags dynamic `redis_->set(<identifier>, …)` call sites as
"needs manual review" rather than skipping them (F-202 showed why).

## Watch for S08

**PI-009 blocks S08.** DRM master exclusivity is confirmed from cinepi-raw's own comment,
but how the DRM preview and the fbdev GUI *compose* is not determinable statically. S08
must not answer KICKOFF §7 constraint 2 from reasoning.

## Finish with

Update `STATE.md`, write `sessions/S05-*.md`, overwrite this file for S06, then
`git add system-review/`, commit as `review(S05): ...`, and push.
