# Docs vs. code — drift report

**Session:** S09 · **Method:** `harness/docs_drift_check.py` + targeted reading · **Pi used:** no
**Scope:** all 50 files in `docs/`, plus `mkdocs.yml` · **Branch:** `dev`, both repos

---

## 1. The verdict, which is not the one this review expected

> **The documentation is the best-maintained boundary in the system.**

Six sessions established that CineMate's problem is duplicated truth that has stopped
agreeing: 16 instances, 10 already drifted, a settings-editor button that silently no-ops
today, four registries of config defaults disagreeing on 11 keys. Going into S09 the
reasonable prior was that `docs/` would be the worst of it — prose is the cheapest thing to
leave behind.

It is the opposite. Mechanically, across 50 files:

| check | result |
|---|---|
| internal links | **103 checked, 0 broken** |
| code citations into the repo | **64 resolved, 0 unresolvable, 0 line numbers out of range** |
| `settings.jsonc` top-level sections documented | **11 of 11**, and no heading names a section that does not exist |
| `redis-keys.md` rows that name a real key | **71 of 71 — zero orphan documentation** |
| `controller-methods.md` method names that exist | **43 of 43** |

Reproduce with `python3 system-review/harness/docs_drift_check.py --repo .`

**The sharpest single data point:** the controller-method catalogue exists four times — in
`docs/controller-methods.md`, in `settings_editor.py`'s `ACTION_METHODS`, in the settings
editor's JavaScript, and as the 94 real methods on `CinePiController`. **The prose copy is
the correct one.** Both machine-readable copies carry `set_log`, a method that does not
exist, and one of them ships a button that silently does nothing (F-118, F-218, F-242).

---

## 2. What is actually wrong — nine defects, ranked

### Substantive

**F-245 — `web-gui.md` asserts a safety property that does not hold.**
> *"Every control action posts a CLI command line to `/api/v1/cmd` — the same dispatcher the
> CLI, serial and GPIO paths use, so the browser cannot drift from them."*

True for CLI and serial. **False for GPIO**, which dispatches by
`getattr(self.cinepi_controller, method_name)` at seven sites in `gpio_input.py` and never
touches the HTTP path — bypassing `_dispatch_lock` entirely (F-025). The sentence is right
about the real architectural win (F-206) and wrong about its scope, which is the most
misleading way to be wrong. **Fix: strike "and GPIO".**

**F-246 — a setting that does not exist, named in three places, two of them in the code.**
`lock_dual_recording` appears in `changelog.md:11`, in a **docstring** at
`cinepi_controller.py:1347`, and in a **comment** at `cli_commands.py:267`. It is in no
settings file, no schema, no loader. The real control is
`sensors.record_policy == "always_both"` (`cinepi_controller.py:1369`).

One rename, three stale references. This is F-118's failure mode in prose — and note that
**two thirds of it is inside the source tree**, not in `docs/`. Which sharpens where the
drift actually lives.

**F-241 — 13 of 84 Redis keys are undocumented, and 7 are one feature.**
`resolution_switching`, `resolution_target_mode/width/height/bit_depth`,
`dynamic_resolution_enabled/active/desired_mode`. Plus `audio_capture_gain_db`,
`fps_phase_lock`, `trigger_mode`, `mode`, `packing`. **Zero orphan documentation** in the
other direction. This is one under-documented feature, not scattered rot — and S02 recorded
18 by a different method, so the character has been stable.

### Cosmetic

- **F-248** — `web-gui.md` claims "same field layout" as the HDMI GUI. 48 of 68 fields reach
  the template; the recording-integrity counts are HDMI-only (F-211).
- **F-247** — `changelog.md:11,66` say `settings.json`; the file is `settings.jsonc`. The
  other 49 docs get it right.
- **F-243** — `cli-user-guide.md` cites `boot/firmware/config.txt`, missing the leading
  slash. The only unresolvable citation among 100.
- **F-249** — `simple-gui.md:5` is an orphan sentence about the browser UI inside a
  document about the HDMI GUI. Draft residue.

### Structural — and the biggest one

**F-244 — 15 of 50 documents are unreachable from the mkdocs nav.** Five are 0-byte files
and five nav lines are commented out, but two are not stubs:

| file | LOC | why it matters |
|---|---|---|
| `image-circle.md` | 159 | real content, entirely unpublished |
| `controller-methods.md` | 73 | **the most accurate catalogue of controller methods in the repository** (F-242), and the site does not link to it |

**The published site is missing its best method reference.** That is the single
highest-value docs fix available and it is one line of YAML.

---

## 3. Why the docs are accurate — the pattern worth copying

This is the more useful half of the report. Three properties distinguish the accurate docs
from the drifted code:

**1. Tabular, one row per fact.** `redis-keys.md` is a table with one row per key and four
columns including *"Safe to change manually?"*. A table row is cheap to add when you add a
key and conspicuous when it is missing. Prose paragraphs hide omissions; a table shows them.
It is at 71 of 84 — the gap is visible as gaps.

**2. Structured to mirror the thing described.** `settings-json.md` uses `##`/`###` headings
that match `settings.jsonc`'s own key names, so the diff is mechanically checkable —
which is how this report checked it, and how CI could. 11 of 11, no phantoms.

**3. Scoped honestly.** `controller-methods.md` says it covers *"the most useful ones"*, so
its 43-of-94 coverage is a stated scope, not a gap. `compiling-cinepi-raw.md` is 15 lines
because its job is "how to rebuild", not "how it is built" — and both facts it states are
exactly right (F-262).

> **Thin is not the same as drifted, and this review's own plan conflated the two.**
> `PLAN.md` S09 ranked docs by LOC-per-surface and flagged `compiling-cinepi-raw.md`,
> `simple-gui.md` and `web-gui.md` as thinnest-coverage. Reading them: the 15-line one is
> completely correct, the 31-line one is dense and accurate, and the error is in the
> 32-line one — but it is a scope error in one sentence, not a coverage gap. Line count
> did not predict correctness in any of the three cases.

**And one doc is verified accurate end to end:** `simple-gui-refresh-tuning.md` (F-234)
matches every constant in `simple_gui.py`, including which values are derived and should not
be edited directly, and states the operational ceiling. It was written by someone reading
the code.

---

## 4. Where the drift actually lives

Restating the S09 result against the review's thesis, because it moves the target:

| boundary | state |
|---|---|
| docs ↔ code | **best in the system.** 9 defects across 50 files, 4 cosmetic |
| code ↔ code | 16 duplicated-truth instances, 10 drifted (`REDUNDANCY-REPORT.md`) |
| code prose ↔ code | **worse than docs.** 3 hand-sync comments drifted (F-260, F-183, F-220), a fourth in CSS (F-217), and F-246's two stale in-code references |

**Docstrings and comments have drifted where `docs/` has not.** F-246 is the clean
demonstration: the same dead setting name survives in a docstring and a comment as well as
in the changelog, and only one of those three lives in `docs/`.

The plausible reason is that `docs/` is a published site someone reads, and comments are
not. That is worth stating in S11's philosophy distillation, and it argues for **F-133's
promotion recommendation**: S05 catalogued 47 load-bearing why-comments as a deletion
hazard. S09 adds a second reason to promote them into `docs/` — comments are where this
project's prose actually rots.

---

## 5. What could not be checked

- **`changelog.md` against git history** (F-263). `PLAN.md` asks for a diff against the
  `cinemate-v3.1.1` tag; this clone has **no tags**. Content was spot-checked — that
  produced F-246 and F-247 — but completeness against the commit log is `unverified`.
- **`cli-commands.md` against the dispatcher — inconclusive, and deliberately not reported
  as a finding.** A naive token diff produced 14 "doc-only commands" that were argument
  values (`exfat`, `false`, `sec`) and multi-word forms (`rec cam1`) the dispatcher parses
  as `rec` plus an argument. The method could not distinguish a command from its arguments,
  so no verdict is offered. A real check needs the dispatcher's grammar, not its string
  literals.
- **Semantic accuracy generally.** Every mechanical check above proves a name exists. That a
  described *behaviour* is correct is a reading job, and only the three thin docs, the
  refresh-tuning doc and the redis-key table were read closely.
- **Anything requiring a Pi.** No documented behaviour was observed.

---

## 6. Recommendations

Ordered by value per unit of effort.

| # | Action | Effort | Finding |
|---|---|---|---|
| 1 | **Add `controller-methods.md` and `image-circle.md` to the mkdocs nav.** One line each; publishes 232 lines of correct content, including the best method reference in the repo | minutes | F-244 |
| 2 | Strike "and GPIO" from `web-gui.md`. It claims a safety property GPIO does not have | minutes | F-245 |
| 3 | Fix `lock_dual_recording` in all three places — the changelog, the docstring and the comment — to `sensors.record_policy` | 15 min | F-246 |
| 4 | Document the 13 missing Redis keys. Seven are one feature, so it is one table block | 1 h | F-241 |
| 5 | Decide the five 0-byte files: write them or delete them and their commented-out nav lines | 30 min | F-004, F-244 |
| 6 | The three cosmetic fixes (`settings.json`→`.jsonc`, the missing slash, the orphan sentence) | 15 min | F-247, F-243, F-249 |
| 7 | **Wire `docs_drift_check.py` into CI.** All six checks pass at zero today except `keys` (13) and `nav` (15) — gate those two as ratchets, the other four at zero | 1 h | — |

Item 7 is the one that matters after the fixes. `STANDARDS-PROPOSAL.md` §3's rule applies
here too: the docs are accurate *now*; a check is how they stay that way. This is the
**fourth** stdlib-only checker in the ledger, after `redis_key_diff.py`,
`gui_field_extract.py` and `design_token_diff.py`, and none of the four needs hardware.

---

## 7. Confidence

Every mechanical count is reproducible by `harness/docs_drift_check.py`. Every qualitative
claim cites a line read in this repository.

Three of this session's checks were **wrong on the first attempt** and were corrected before
anything was written up:

- The Redis-key check matched only backticked names and reported 8 of 84 documented,
  apparently contradicting F-014. `redis-keys.md` is a table and does not backtick its keys.
  The real figure is 71.
- The same check reported `pip_cam0`/`pip_cam1` as documented-but-nonexistent keys. They are
  *values* of `hdmi_preview_source`.
- The settings check matched backticked dotted paths and found 9 in a 611-line document, two
  of which were filenames. The document is structured by heading.

All three are now documented in the script's own source as warnings. Any count in this
report that a committed script does not produce should be read as provisional — and the
`cli-commands.md` check was withheld for exactly that reason.
