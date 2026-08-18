Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full.
2. Read `system-review/STATE.md` — **especially Deviations D1–D5**.
3. Read `system-review/sessions/S05-readability.md`.
4. Then execute **S06 — Standards, consistency & tooling** per `system-review/PLAN.md`,
   **absorbing the small remainder of agent 2's S04 scope** (see below).

---

## S06 has unusually good inputs — most of the audit is already done

S06's brief is "propose a minimal standard + audit consistency". **The consistency audit
has largely been performed already** across S02–S05. Do not redo it; assemble it.

| S06 asks for | Already established |
|---|---|
| error handling / bare `except` | **F-130** (337 handlers, 15 silent), **F-131** (2 bare) |
| thread start/stop patterns | **F-022, F-023, F-024** + the full thread table in `CODE-MAP-cinemate.md` §4 |
| Redis access patterns | **F-015, F-020, F-105** — five distinct patterns catalogued |
| settings access | **F-251** (4 registries, 11 keys disagree), **F-252** |
| hardcoded absolute paths | **F-260** (`settings.jsonc` path in 7 files) |
| logging | not yet done — this is genuinely S06's own work |
| import style | partly — see the `from module import X` note in `CENSUS.md` §4 |

**So the drafting is the work, not the auditing.** Spend the session on
`deliverables/STANDARDS-PROPOSAL.md` + `deliverables/draft-config/`.

### Concrete inputs for the config drafts

- **ruff `E722`** catches F-131's bare `except:` mechanically. **`S110`/`S112`**
  (`try-except-pass`/`continue`) catches F-130's 15 silent handlers. Both are exactly the
  project's own "fail visible, never silent" principle expressed as a lint rule — say so
  in the proposal; it lands better than a generic style argument.
- **Any "remove commented-out code" rule must exempt F-133's load-bearing comments.**
  47 of them encode *why*, including two falsified experiments. A blanket rule would
  destroy the most valuable prose in the repo. Name the exemption explicitly.
- **`.editorconfig`** is trivially safe and uncontroversial — include it.
- **CI is still blocked on PI-002** for the *test* job (the portable/hardware split is
  unknown). But the **docs-build job is not blocked** (F-006): adding `pull_request` and
  `dev` triggers to the existing working workflow is the single highest value-per-effort
  change in the ledger. `findings/F-006.md` has the trap — you must split build from
  deploy, or a PR build will publish gh-pages and push a commit.
- **`harness/redis_key_diff.py` is a ready-made CI check.** Do not wire `--strict` yet
  (12 known drifts would fail day one); the useful form fails only on an *increase*.
- **cinepi-raw already has the pattern** cinemate lacks — `meson test` with
  `phase_lock_core_test` (F-030). Point at it rather than proposing from scratch.

### Also fold in: the rest of agent 2's scope

Small, and overlapping S06's brief. Use IDs **F-166..F-199**. Still open:
settings keys defined-but-never-read and read-but-absent-from-schema · installer
idempotency by reading · `shellcheck` warning classes · two thirds of the `wifi_hotspot`
triangle (only the `_test/` copy was reached, F-150).

---

## Method warnings — all earned in this review

**Incremental agent writes are mandatory, not advice.** Four agents that batched their
writes lost everything to a usage limit; the one instructed to append as it went preserved
16 findings through the same failure. Put it in every agent prompt, in bold.

**Pattern matching has under-reported three times.** `cinepi_ready_<port>`, a `tc_key`
variable, and `from module import X` — the last put five *live* modules on a dead list.
Treat "no grep hit" as a hypothesis; say "at least N".

**Citation discipline.** Line numbers from `grep -n` only, never arithmetic on a `sed`
window. S02 and S03 both shipped off-by-one citations that way.

**Verify agent claims before merging.** S04 corrected two of 40 — one overstated, one
understated. Both took one grep.

---

## Context that isn't obvious

**Branch:** `claude/cinemate-system-review-kickoff-cilicc`. PR #129 (draft). Ledger-only —
`git add system-review/`, never `-A`.

**cinepi-raw** may need re-cloning (read-only, `main`, shallow, no history):
```
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/Tiramisioux/cinepi-raw /workspace/tiramisioux/cinepi-raw
```

**Free ID blocks:** F-135..F-149, F-166..F-199, F-203..F-249, F-262..F-299.

## Watch for S08

**PI-009 blocks S08.** DRM master exclusivity is confirmed from cinepi-raw's own comment,
but how the DRM preview and the fbdev GUI *compose* is not determinable statically. S08
must not answer KICKOFF §7 constraint 2 from reasoning.

Also for S08: S04's verdict is **verification before unification** — a GUI unification
shipped without a verification layer will re-grow the duplicates within a release. The
codebase already tried comments as the sync mechanism and the comments drifted.

## Finish with

Update `STATE.md`, write `sessions/S06-*.md`, overwrite this file for S07, then
`git add system-review/`, commit as `review(S06): ...`, and push.
