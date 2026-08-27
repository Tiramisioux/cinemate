# S09 — Docs vs. code

**Plan entry:** S09 · **Findings:** F-240..F-249, F-262, F-263 (12) · **Ledger total:** 178
**Pi used:** no · **Subagents used:** none
**Deliverable:** `deliverables/DOCS-DRIFT-REPORT.md` · **New harness:** `harness/docs_drift_check.py`

---

## The result inverts the prior

> **The documentation is the best-maintained boundary in the system.**

Going in, the reasonable expectation for a review whose central finding is systemic drift
was that `docs/` would be the worst of it. Across 50 files: **103 internal links, 0 broken;
64 repo code citations, 0 unresolvable and 0 out-of-range; 11 of 11 top-level settings
sections documented with no phantoms; 71 of 71 `redis-keys.md` rows naming a real key —
zero orphan documentation; 43 of 43 method names in `controller-methods.md` existing.**

**The sharpest data point (F-242):** the controller-method catalogue exists four times, and
**the prose copy is the correct one.** Both machine-readable copies carry `set_log`, which
does not exist, and one of them ships a button that silently no-ops (F-118, F-218).

## Where the drift actually is

| boundary | state |
|---|---|
| docs ↔ code | **best in the system** — 9 defects across 50 files, 4 cosmetic |
| code ↔ code | 16 duplicated-truth instances, 10 drifted |
| **code prose ↔ code** | **worse than `docs/`** — 3 hand-sync comments drifted, a fourth in CSS, plus F-246 |

**F-246 is the clean demonstration.** `lock_dual_recording` is named in `changelog.md:11`,
in a **docstring** at `cinepi_controller.py:1347`, and in a **comment** at
`cli_commands.py:267`. It exists in no settings file, no schema and no loader — the real
control is `sensors.record_policy == "always_both"`. One rename, three stale references,
**two of them inside the source tree**.

Docstrings and comments have rotted where `docs/` has not. The plausible reason is that
`docs/` is a published site someone reads. That belongs in S11's philosophy distillation,
and it adds a second argument for S05's F-133 recommendation: promote the 47 load-bearing
why-comments into `docs/`, because comments are where this project's prose actually rots.

## The two substantive errors

**F-245.** `web-gui.md` says every control action posts to `/api/v1/cmd` — *"the same
dispatcher the CLI, serial and GPIO paths use, so the browser cannot drift from them."*
True for CLI and serial; **false for GPIO**, which dispatches by `getattr` at seven sites
and bypasses `_dispatch_lock` entirely (F-025). It is right about the real architectural win
(F-206) and wrong about its scope — the most misleading way to be wrong. Fix: strike "and
GPIO".

**F-244.** 15 of 50 docs are unreachable from the nav, and two are not stubs:
`image-circle.md` (159 LOC of real content) and `controller-methods.md` (73 LOC, and per
F-242 the most accurate method catalogue in the repository). **The published site is missing
its best method reference**, and the fix is one line of YAML.

## Why the accurate docs are accurate

The more useful half of the report. Three properties separate them from the drifted code:
**tabular, one row per fact** (a missing row is visible; a missing paragraph is not);
**structured to mirror the thing described** (`settings-json.md`'s headings match
`settings.jsonc`'s keys, which is *why* a script could check it); and **scoped honestly**
(`controller-methods.md` says it covers "the most useful ones", so 43 of 94 is scope, not
a gap).

> **Thin is not the same as drifted, and this review's own plan conflated them.** `PLAN.md`
> ranked S09's targets by LOC-per-surface. The 15-line `compiling-cinepi-raw.md` is
> completely correct (F-262); the 31-line `simple-gui.md` is dense and accurate; the error
> is in the 32-line `web-gui.md` and it is one sentence, not a coverage gap. Line count
> predicted nothing.

## Corrections made during the session

**Three of the six checks were wrong on the first attempt.** Each is now a warning in the
function that made it:

- The Redis-key check matched only backticked names and reported **8 of 84** documented —
  apparently contradicting F-014's "18 undocumented, 0 orphan docs". `redis-keys.md` is a
  markdown **table** and does not backtick its keys. The real figure is **71 of 84**. Had I
  trusted it, S09 would have opened by contradicting a settled finding on a regex bug.
- The same check reported `pip_cam0`/`pip_cam1` as documented-but-nonexistent keys. They are
  **values** of `hdmi_preview_source`, correctly absent from `ParameterKey`.
- The settings check matched backticked dotted paths and found 9 in a 611-line document, two
  of which were filenames. The document is structured by `##`/`###` headings.
- The citation check reported 37 "unresolvable" paths; **all 37 were absolute runtime paths**
  (`/boot/firmware/config.txt`, `/home/pi/...`) correctly absent from the repo. It now
  classifies them. Exactly one real miss survived: F-243's missing leading slash.

**And one check was withheld rather than reported.** A `cli-commands.md`-vs-dispatcher token
diff produced 14 "doc-only commands" that were argument values (`exfat`, `false`, `sec`) and
multi-word forms (`rec cam1`) the dispatcher parses as a verb plus an argument. The method
could not distinguish a command from its arguments, so no verdict is offered. A real version
needs the dispatcher's grammar.

**One item was not checkable at all** (F-263): `changelog.md` against git history needs the
`cinemate-v3.1.1` tag, and this clone has no tags. Content was spot-checked — that produced
F-246 and F-247 — but completeness is `unverified`.

## Method note

Writing the checker before the prose paid for itself for the third session running: four of
the five corrections above came from reading a script's output back against the source
before believing it. The pattern is now consistent enough to state as a rule — it is in the
handoff.

## Left undone

- **`cinepi_controller.py` (2626 LOC) is untraced** since S02 — deferred five times now.
  **PI-007 step 1 is a desk task**, not a Pi task.
- **`dng_encoder.cpp` on `dev` (687 lines changed)** — largest cinepi-raw hole, from S07b.
- **The `wifi_hotspot` triangle** — two thirds unreached since S04.
- Semantic accuracy of the 44 docs that were not read closely.
