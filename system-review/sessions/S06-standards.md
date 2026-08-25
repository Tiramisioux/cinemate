# S06 — Standards, consistency & tooling

**Plan entry:** S06 · **Findings this session:** F-166..F-195 (30 recorded, **25 net** — 5 merged into F-002/F-003) · **Ledger total:** 129
**PI items added:** PI-012, PI-013 · **Pi used:** no · **Subagents used:** none

---

## What was produced

- `deliverables/STANDARDS-PROPOSAL.md` (358 lines) — the argument.
- `deliverables/draft-config/` — `ruff.toml`, `editorconfig`, `checks.yml`, `docs-split.md`,
  `README.md`. **None applied, none executed.**

## The session's thesis

The handoff predicted the consistency audit was mostly already done and that drafting would
be the work. That held, but the drafting produced a claim the earlier sessions had not
stated outright, and it reframes the whole deliverable:

> **CineMate does not have a style problem. It has a drift problem.**

Every serious finding in five sessions — F-118, F-251, F-027, F-183, F-260, F-164 — is two
copies of one truth that stopped agreeing. Not one would have been caught by a formatter or
a naming convention. So the proposal inverts the usual order: **drift checks first, lint
second, formatting last**, and every ruff rule selected has to name the finding it catches.

Three of the duplicate copies are hand-maintained comments; two of those comments are now
wrong. Hence the one rule worth writing down: *duplicated truth must either be deleted, or
carry a named reason **and** an automated check. A comment is not a check.*

## New audit work (the parts not already in the ledger)

**Logging** was the one item the handoff flagged as genuinely undone. Result: two competing
idioms — 615 module-level `logging.X(` across 26 files vs 112 named-logger calls across 7
(F-168) — plus 26 surviving `print()` calls (F-169), mixed f-string/`%` interpolation
(F-170), a `configure_logging` parameter that is never read (F-171), and an **unbounded
log queue that is never drained** (F-172, the session's most serious single finding).

**Dependencies.** S06 re-derived the `requirements.txt` / installer divergence that S01 had
already computed — a process failure, see Corrections. What survived the merge is genuinely
new: **F-182** — `INSTALL_ALT_GPIO_BACKEND` is listed under "Optional features" but `lgpio`
is imported unguarded at the top of the boot chain, so the supported `=0` configuration
plausibly cannot start (→ PI-012); plus two dead entries (`sounddevice` installed and
referenced nowhere, F-187; `pyaudio` required and imported nowhere, F-188), the absence of
any version pinning (F-190), and the fourth hand-sync comment (F-191).

**Shell** was audited with `shellcheck` (available in this environment) and came out as a
**strength**: 15 findings across 11 scripts, one of them in the 1916-line installer (F-174).
The installer's idempotency is *designed and documented* — managed-block markers,
delete-then-rewrite, guarded patches with the reasoning in comments (F-192, F-194).

That contrast is what makes the proposal credible rather than generic: **the installer
already does what the Python doesn't.** The standard is not being imported from outside;
it is being generalised from the best part of the repo.

## Corrections made during the session

- Initially counted **28** `print(` calls; the statement-level figure is **26** (28 counts
  two occurrences inside other expressions). The ledger records 26.
- `wifi_hotspot.py:750`'s `logging.basicConfig` was a candidate finding until read in
  context — it is inside `if __name__ == "__main__"`, which is *correct*. Recorded as a
  **strength** (F-181) instead, since it is the only module that gets this right.
- The naive schema-vs-settings key diff reported 88 keys "missing from the schema". Probing
  the schema showed most are covered by `additionalProperties` subschemas and `$ref`s. The
  honest finding is not a key count but that `"additionalProperties": true` appears **25
  times and `false` zero times** (F-166) — the schema structurally cannot reject a typo.
  This is the fourth time in this review that a first-pass pattern match was wrong in the
  direction of over-claiming.
- The three keys present in the schema but absent from `settings.jsonc` were checked against
  the code before being written up. All three are legitimate (code defaults, optional
  list-element keys). **Not recorded as findings.**
- A mojibake ellipsis got into F-193's evidence field via a heredoc and was repaired.
- **Process failure — five findings duplicated S01.** F-183..F-186 and F-189 re-derived the
  `requirements.txt` / installer divergence that F-002 and F-003 already record, and that
  `STATE.md`'s "Do not redo" list explicitly warns against. Cause: this session resumed
  mid-task from a summary and never re-read `STATE.md`, which the handoff lists as step 2.
  All five rows are now marked **MERGED** into F-002/F-003 and the deliverable's citations
  repointed. One useful thing came out of the recount: S06's set-based figure (7
  requirements-only) and F-003's ("4") **agree** — the difference is the three docs-build
  packages, which F-002 counts separately. No contradiction, different counting bases.
  **Standing rule reinforced: read `STATE.md` before the first grep, every session,
  including resumed ones.**

## Decisions taken, with the reasoning in the deliverable

- **Pre-commit: no.** One maintainer plus agents in fresh containers; `--no-verify` makes it
  worse than nothing. The CI lint job gives the same guarantee.
- **`mypy`: no.** Annotate two boundaries for the *reader* (`RedisController` accessors,
  `config_loader` public functions) and nowhere else.
- **`ruff format`: not yet**, and never before the checks — and when it happens, with a
  `.git-blame-ignore-revs` entry, because F-133's comments are the repo's best asset.
- **`ERA001`: prohibited**, in a block comment in `ruff.toml` so nobody adds it later.
- **Ratchets, not gates**, for the two checks with known existing violations. A check that
  is red on arrival gets disabled in week two.

## Left undone

- **The `wifi_hotspot` triangle** — still two thirds unreached from agent 2's S04 scope.
  Only the `_test/` copy (F-150) has been read.
- **Settings keys defined-but-never-read.** The schema side is done (F-166, F-167); the
  liveness side — which keys the code actually reads — is not, and it needs an AST pass over
  the `get`/`setdefault` chains rather than a grep.
- The ruff config has never been run. Its hit count will exceed the grep-derived numbers.
