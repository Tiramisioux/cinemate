# Standards proposal — CineMate

**Session:** S06 · **Status:** proposal, nothing applied · **Drafts:** `deliverables/draft-config/`

Scope: cinemate's Python, shell and config. cinepi-raw already has `.clang-format` and a
working `meson test` target and is not the problem (F-005, F-030).

---

> ## ⚠ CORRECTION — reconciled against `PI-RESULTS-2026-08-24.md`
>
> **Added 2026-08-25.** This proposal was written before the Pi session. Four things it
> states as open or as a specific shape are now settled:
>
> - **§6.2's premise is gone.** PI-002 ran the full suite on real hardware: 381 passed + 241
>   subtests, zero skips, zero collection errors, matching the off-hardware baseline exactly.
>   "The portable/hardware split... appears not to exist" (PI-RESULTS). §6.2's discovery-mode
>   job (`continue-on-error: true`) was the right call *before* this result — it no longer
>   needs to be provisional. Item 9 in §9's table can gate at zero from adoption, not just
>   after a discovery run.
> - **§11's Flask claim is confirmed, not probable.** PI-004: a clean install's `pip show
>   flask` reads `Required-by: Flask-SocketIO`. Verifying it did not need a network resolve
>   this review lacked — it needed the clean install this review now has.
> - **§9 item 8's risk note cited the wrong PI item** (said "needs PI-012's clean install to
>   verify" — PI-012 is the GPIO-backend item, F-182). The clean install is **PI-004**, and
>   it's done: flask and pyserial both confirmed transitive-only, F-003's split decision
>   stands on measured ground now, not an assumption.
> - **§3.1's F-027 row undersells what the ratchet would catch.** PI-008 found the 12
>   "unreferenced" keys are not dead — 8 are an undocumented cinepi-raw launch-config
>   contract, 2 are live per-frame telemetry. The ratchet is more valuable than the proposal
>   argued: it would surface a real live contract with no other guard, not just prune dead
>   entries. See `FINDINGS.md` F-027.

---

## 1. The thesis

**CineMate does not have a style problem. It has a drift problem.**

That is the single most important thing five sessions of reading produced, and it should
decide what the standard is. Go down the list of everything serious this review has found:

| Finding | What it actually is |
|---|---|
| F-118 | A settings-editor button that silently no-ops, because a Python↔JS catalogue says `set_log` and the method is `set_log_encode` |
| F-251 | Config defaults declared in 4 registries; **11 keys disagree** |
| F-027 | 12 Redis key strings cinepi-raw handles with zero references in cinemate — PI-008 found them live, not dead: an undocumented launch-config contract + per-frame telemetry nobody reads |
| F-002 / F-003 | Two Python dependency registries sharing only 12 of 30 packages |
| F-260 | One absolute path retyped in 7 files; the comment indexing them lists 4, one with a wrong line number |
| F-164 | Six apparent copy-pastes that turned out to be one severed link |

Not one of those is a formatting defect, and not one of them would have been caught by
`black`, `isort`, or a naming convention. Every one of them is **two copies of one truth
that stopped agreeing**, and in three cases the sync mechanism the codebase reached for was
*a hand-maintained comment* — two of which are themselves now wrong (F-260, F-183, F-191).

So the proposal inverts the usual order. **Drift checks first, lint second, formatting
last.** A formatter adopted before the drift checks would produce a large, satisfying diff
and prevent nothing.

### What this means for the rules

Every rule below has to answer one question: *which finding in `FINDINGS.md` would this
have caught?* A rule that cannot name one does not go in. This is why the ruff set is
small — most of ruff's catalogue is answering a problem CineMate does not have.

---

## 2. What this proposal deliberately rejects

Stated up front, because the default advice for a Python repo with no tooling is a
five-tool pipeline, and that would be the wrong call here.

**Rejected: `black` + `isort` + `flake8` + `mypy` + `pylint`.** Five tools, five configs,
five failure modes, overlapping and mutually contradictory (`black` vs `flake8` line length
is the classic). Ruff replaces the first four for this codebase's purposes in one binary
with one config file. One maintainer plus agents cannot carry five tools; the ledger's own
evidence is that this project abandons unmaintained mechanisms (F-164, F-161, and the three
stale sync comments).

**Rejected: a repo-wide reformat as the first move.** ~19,800 lines across 48 modules.
A formatting commit touching all of them destroys `git blame` on the single best asset this
codebase has — the 47 load-bearing comments catalogued in F-133, several of which are only
interpretable next to the code they annotate. If formatting is adopted at all it comes
after the checks, and it comes file-by-file (§7).

**Rejected: a docstring mandate.** S05 measured docstring coverage and the honest reading
was that the *comments* in this codebase carry the value, not the docstrings. A coverage
mandate produces `"""Initialise the controller."""` above `__init__` — noise that dilutes
the prose that is actually load-bearing.

**Rejected: `--strict` on the Redis key diff, for now.** `harness/redis_key_diff.py` works
today and reports 12 known drifts. Wired strictly it fails on day one, gets marked
`continue-on-error`, and becomes decoration. See §3.1 for the form that survives.

---

## 3. Tier 0 — the drift checks

These are the proposal. Everything after this section is hygiene.

Each one is a script that fails CI when two copies of a truth disagree. Three of the four
already exist in some form; none of them requires a Raspberry Pi.

### 3.1 Cross-repo Redis key contract — **ready today**

`harness/redis_key_diff.py` was written in S03 and needs no dependencies. It parses
`ParameterKey` (84 members), the `CONTROL_KEY_*` macros (24), and direct `redis_->` calls,
and reports 84 / 32 / 19 shared / 12 unreferenced.

**Wire it as a ratchet, not a gate.** Commit the current count as a baseline; fail only when
the number of unreferenced keys *increases*. This is the difference between a check that
gets adopted and one that gets disabled in week two. The 12 known drifts then get retired
deliberately, and the ratchet stops them coming back.

Catches: the F-027 family. Would have caught F-107 (five `MIC_*` keys published twice,
read never).

### 3.2 Settings-defaults agreement — **the highest-value new check**

F-251 is the worst finding in the ledger by consequence: four registries of config defaults,
eleven keys where they disagree, and no way to know which one wins without reading all four.
F-252 adds two more subsystems that live outside the central loader entirely.

A check that loads the JSON Schema `default`s, the `setdefault` calls in `config_loader.py`,
and the shipped `resources/settings/settings_default.jsonc`, and asserts they agree, is
maybe 80 lines. It is also the check most likely to catch a *future* bug, because config
defaults are exactly what a contributor edits in one place.

Ratchet the same way: baseline the 11 known disagreements, fail on the 12th.

### 3.3 Reflective-dispatch name check — **catches a shipped bug class**

F-118 is a button that does nothing, shipped, in the settings editor. The mechanism:
`settings.jsonc` and a JS catalogue name controller methods as strings, and
`getattr(cinepi_controller, name)` resolves them at runtime. A typo is not an error — it is
silence.

The check: collect every method name that appears as a string in `settings.jsonc`, in
`settings.schema.json`, and in the settings-editor catalogue; assert each one exists on
`CinePiController`. Pure `ast` + `json`, no imports of the app, no hardware.

This one should **not** be a ratchet. There is one known instance and it is a bug; fix it
and gate at zero.

Also catches the F-167 hole from the other side: the schema declares
`quad_rotary_controller.encoders` as a bare `{"type": "object"}`, so today *nothing*
validates the most complex and most reflectively-dispatched block in the config.

### 3.4 Dependency-registry agreement — **or just delete one registry**

F-002 and F-003 (S01): `requirements.txt` and the installer's pip list share 12 of 30
packages, and `requirements.txt` is referenced by nothing at all. It contains a stdlib
module (`wave`), three duplicate lines, three docs-only packages, and a GPIO stack the
installer does not build. S06 adds two dead entries on top: `sounddevice` is installed on
every camera and referenced nowhere (F-187), and `pyaudio` is required and imported nowhere
(F-188).

**The check is the fallback here; the fix is better.** Make `cinemate-install.sh` read
`requirements.txt` — one registry, no check needed. That is the pattern to prefer wherever
it is available: *delete the duplicate rather than check it*. Where the duplicate cannot be
deleted, `cinemate-install.sh:1633-1636` shows the acceptable form — it names the reason it
must exist ("this heredoc runs under the system python3, outside the venv"). It still lacks
a check, and that is the gap the rule closes.

> **The rule this generalises to, and the one rule worth writing down:**
> *Duplicated truth must either be deleted, or carry a named reason **and** an automated
> check. A comment is not a check.* The codebase has already run this experiment three
> times and the comments drifted every time.

---

## 4. Tier 1 — ruff, and only the rules the ledger earned

Draft at `draft-config/ruff.toml`. Every selected rule below names its finding.

| Rule | Catches | Evidence |
|---|---|---|
| `E722` bare-except | 2 bare `except:` that also swallow `KeyboardInterrupt` | F-131 · `cli_commands.py:159,167` |
| `S110`/`S112` try-except-pass/continue | 15 handlers that swallow silently | F-130 |
| `F401` unused import, `F841` unused local | dead-code residue; the shell equivalent already found 4 (F-178, F-179) | F-122 |
| `T201` print-found | 26 surviving `print()` calls that bypass the file handler, the colour formatter and the UI queue | F-169 |
| `ARG001`/`ARG002` unused argument | `configure_logging(MODULES_OUTPUT_TO_SERIAL, …)` never reads its first parameter | F-171 |
| `B006` mutable default, `B008` call-in-default | not yet observed — cheap, and the config layer passes dicts around freely | — |
| `E9`/`F82` syntax + undefined name | the floor. `CMakeLists.txt:4` referencing a deleted directory (F-165) is the same class of error in another language | F-165 |

### The framing that matters

`E722`, `S110` and `S112` are not style rules here. `storage_profiles.py:41-49` states the
project's own principle — **fail visible, never silent** — and F-130 shows 15 places that
violate it. These three ruff codes are that principle, mechanised. Presenting them that way
is the difference between "the linter wants this" and "we already decided this."

`T201` is the same argument in a different key: `battery_monitor.py` contains 18 `print()`
calls and zero logging calls (F-169), which means its entire output is invisible to the log
file, the colour formatter, and the in-app log view. That is a *fail-silent* defect wearing
formatting clothes.

### Two mandatory exemptions

**1. Never enable `ERA001` (commented-out code).** F-133 catalogued 47 comments that encode
*why* — including two falsified experiments (`ssd_monitor.py:1122-1125`: 1 MB exFAT clusters
break the macOS driver) and a cross-repo invariant (`storage_profiles.py:41-49`). Several
are commented-out code kept deliberately as the record of what was tried. `ERA001` would
delete the most valuable prose in the repository and it would look like cleanup. This must
be written into the config as a comment, not just omitted, so nobody adds it later.

**2. `T201` needs per-file ignores.** `cinepi_controller.py`'s three `print()` calls
(`:print(f"{'Parameter':<25}Value")` and neighbours) are a CLI table renderer — `print` is
correct there. `grove_base_hat_adc.py`'s three are a vendored `__main__` self-test. Both are
in the draft's `per-file-ignores`.

### Line length

Set it, do not enforce it retroactively. `line-length = 100` matches what the code mostly
already does, and `E501` stays **off** — turning it on flags hundreds of lines including
several of the F-133 comments, and the noise would bury the seven rules above.

---

## 5. Type hints — arguing both sides

**For.** The audience for this codebase is an intermediate Python developer (KICKOFF §1.3),
and the hardest thing about reading it is not syntax — it is not knowing what a thing *is*.
`redis_controller.get_value()` returns a string that is sometimes an int, sometimes a float,
sometimes `"None"` as a literal string. The Redis boundary is where the types are genuinely
unclear and where the bugs are (F-015, F-259, F-253).

**Against.** A repo-wide annotation pass on ~19,800 lines is weeks of work, most of it on
code that S05 flagged for deletion — `cinepi_controller.py` alone is 2626 lines. It would
also produce a large diff over the F-133 comments. And `mypy` on a codebase with 337 except
handlers and heavy `getattr` dispatch will produce a wall of unfixable errors, which
guarantees the tool gets turned off.

**Verdict: yes, at exactly two boundaries, and nowhere else.**

1. **`RedisController.get_value` / `set_value` and their typed accessors.** This is the
   system's central contract and the place a reader is most lost. Annotate the signatures
   and document what `"None"`-as-a-string means.
2. **`config_loader.py`'s public functions.** The four-registry defaults problem (F-251) is
   partly a legibility problem, and annotations there pay for themselves.

**Do not run `mypy` in CI.** Annotate for the reader, not for the checker. The moment
annotations exist to satisfy a tool, they start being written to satisfy the tool.

---

## 6. CI — what can ship now, what cannot

### 6.1 The docs workflow: highest value per unit of effort in the whole ledger

F-006: the only workflow triggers on `push` to `main`. Development happens on `dev`. **PR
#129 has zero checks.** Twenty-seven pytest files have never been run by anything.

Adding `pull_request` and `dev` triggers is a three-line change — **but not as the file
stands.** `docs.yml` has a trap:

- `Deploy to GitHub Pages` (`peaceiris/actions-gh-pages@v4`) runs unconditionally and would
  publish gh-pages **from a pull request**.
- `Copy PDF to docs/renders and push` runs `git commit` and `git push` — a PR build would
  push a commit to the branch, and from a fork it would fail outright.

**Split build from deploy.** `draft-config/docs-split.md` gives the exact edit: everything
up to `Build site` runs on every PR and every `dev` push; the two publishing steps get
`if: github.event_name == 'push' && github.ref == 'refs/heads/main'`. Build breakage then
gets caught on the PR, and nothing publishes from one.

### 6.2 The test job — blocked on PI-002, but not entirely

The portable/hardware split across the 27 test files is unknown until they are actually run,
and this review has no Pi. **The draft workflow therefore states its assumption in a comment
and does not pretend otherwise** — it runs `pytest _test/` with `continue-on-error: true`
on first adoption, purely to *discover* the split, and the very first task after adoption is
to read the output, mark the hardware tests, and remove `continue-on-error`.

That is not a hedge; it is the only honest way to write this job without hardware. A
workflow that asserts a green suite it has never seen is worse than none.

Note the precedent: **cinepi-raw already has what cinemate lacks** — `phase_lock_core_test`
wired into `meson test` (F-030). The argument to make is not "add tests", it is "do what the
sister repo already does."

### 6.3 A lint job

Ruff over `src/`. Fast, no dependencies beyond `pip install ruff`, no hardware. Safe to gate
from day one *if* the rule set is the small one in §4 — run it once locally first and fix or
ignore what it finds, so the first CI run is green.

### 6.4 Static checks

The Tier 0 checks (§3) are plain Python with no dependencies and belong in the same job.

### 6.5 shellcheck — a formality worth having

F-174 is a **strength**: shellcheck over all 11 shell scripts produces 15 findings total, of
which the 1916-line `cinemate-install.sh` contributes exactly **one**. Five scripts are
clean. The shell in this repository is materially better maintained than the Python.

That makes shellcheck nearly free to gate: fix the 15, then hold the line at zero. Two of
the 15 are real (F-176's masked `git rev-parse` status, F-175's literal `\n`), the rest are
one-line changes.

---

## 7. Tier 2 — formatting, last and optional

`draft-config/.editorconfig` is uncontroversial and costs nothing: UTF-8, LF, final newline,
4-space Python, 2-space JSON/YAML, and `trim_trailing_whitespace` off for Markdown. Adopt it
whenever.

`ruff format` is a real decision and the recommendation is **not yet**. It reformats the
whole tree in one commit, which is precisely the commit that makes `git blame` useless on
the F-133 comments. If it is adopted:

1. Land every Tier 0 and Tier 1 change first.
2. Format in one commit that touches *only* formatting, with a clear message.
3. Add that commit's SHA to `.git-blame-ignore-revs`. This is the step people skip and it
   is the one that protects the comment history.

---

## 8. Pre-commit — recommendation: no

Pre-commit is right for a multi-contributor repo where CI feedback is slow and social. Here
there is one maintainer and agents. It adds an install step that agents in fresh containers
will not have, it fires on every commit including the ledger commits, and when it is slow
people learn `--no-verify` — at which point it is worse than nothing because it creates a
false sense of coverage.

**The CI lint job gives the same guarantee with no local install and no bypass.** If a local
hook is ever wanted, the right one is a single fast `ruff check --fix` and nothing else.

---

## 9. Adoption order

Ordered by value per unit of risk, not by convenience. Nothing here needs a Pi.

| # | Change | Effort | Risk | Catches |
|---|---|---|---|---|
| 1 | `.editorconfig` | minutes | none | — |
| 2 | Split `docs.yml` build from deploy; add `pull_request` + `dev` triggers | 30 min | low — the split *removes* a hazard | F-006 |
| 3 | Fix the 15 shellcheck findings; gate shellcheck at zero | 1 h | low | F-174..F-179 |
| 4 | `ruff.toml` + lint job, §4 rule set | 2–3 h incl. fixing hits | low | F-130, F-131, F-169, F-171 |
| 5 | Wire `redis_key_diff.py` as a ratchet | 1 h | none | F-027 family |
| 6 | Write the reflective-dispatch name check; gate at zero | 2 h | none | F-118 |
| 7 | Write the settings-defaults check; ratchet at 11 | 3 h | none | F-251, F-252 |
| 8 | Make the installer read `requirements.txt`; delete the duplicate list | 1 h | low — **PI-004 verified a clean install end to end on this dependency shape** | F-002, F-003, F-187, F-188, F-190 |
| 9 | Test job — **PI-002 closed the discovery question (381/241 pass, zero skips); can gate at zero from adoption** | 1 h | none | F-006 |
| 10 | Annotate the two boundaries in §5 | 1 day | low | legibility |
| 11 | `ruff format` + `.git-blame-ignore-revs` | 1 h | **medium — blame churn** | — |

Items 1–7 are roughly one focused day and cover every mechanical finding in the ledger.
Item 8 is the only one that touches the install path and is the only one that should wait
for hardware.

---

## 10. What this proposal does not cover

- **Testing strategy.** What the 27 files test, and what a camera *should* test, is a
  question this review cannot answer without running them (PI-002). §6.2 is a discovery
  mechanism, not a strategy.
- **The GUI question.** S07/S08. Note S04's standing verdict: *verification before
  unification* — a unification shipped without a drift check will re-grow the duplicates
  within a release, because the codebase already tried comments as the sync mechanism.
- **cinepi-raw's C++ conventions.** It has `.clang-format` and a test target. The
  cross-repo contract (§3.1) is the seam that matters, not its internal style.
- **The 2626-line `cinepi_controller.py`.** A decomposition proposal needs blast radius and
  a rollback plan (KICKOFF §10); that is S12's work, not a lint rule's.

---

## 11. Confidence

Everything in §§1–4 and §§6–9 is derived from files read in this repository and cited in
`FINDINGS.md`. The drafts in `draft-config/` are **unexecuted** — no ruff, pytest, or GitHub
Actions run happened here. Specifically:

- `ruff.toml` has not been run against `src/`. The rule set is chosen from grep-confirmed
  counts, so the *findings* are confirmed, but the exact hit count ruff reports is
  `unverified` and will be higher than the numbers in §4 (grep undercounts — this review has
  been caught by that three times).
- The workflow YAML has never executed. Treat it as a reviewed starting point.
- The claim that Flask arrives only transitively (F-003, refined in S06) is **confirmed by
  PI-004**: a clean install's `pip show flask` reads `Required-by: Flask-SocketIO`.
