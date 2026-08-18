# PLAN

From `KICKOFF.md` §8, with live status. **One plan entry per session — do not merge rows,
do not start the next one because there's time left** (KICKOFF §2.5).

Update this file as reality diverges. Divergence is expected, not failure.

| Session | Title | Status |
|---|---|---|
| S01 | Bootstrap & census | ✅ done 2026-08-17 |
| S02 | Architecture map — cinemate (Python) | ✅ done 2026-08-18 |
| S03 | Architecture map — cinepi-raw (C++) | ✅ done 2026-08-18 |
| S04 | Redundancy & dead code sweep | ⚠ attempted 2026-08-18, **blocked on usage limit — retry** |
| S05 | Readability, comments & structure | pending |
| S06 | Standards, consistency & tooling | pending |
| S07 | GUI surface inventory & state-model extraction | pending |
| S08 | GUI harmonization evaluation → ADR-001 | pending |
| S09 | Docs vs. code | pending |
| S10 | Install script vs. install docs | pending |
| S11 | CineMate style, philosophy & skill payload | pending |
| S12 | Remediation plan | pending |

---

## Phase 0 — Bootstrap

### S01 · Bootstrap & census — ✅ DONE

- ~~Resolve the dirty cinemate tree with the operator~~ → **moot, tree was clean.** F-011 refuted.
- ~~Cut `review/system-analysis` in both repos from `dev`~~ → **deviated**, see STATE.md D1/D2.
- Create the full ledger layout (§4). Copy §5 → `CONVENTIONS.md`, §8 → `PLAN.md`. ✅
- Record F-001..F-011, verifying each cheaply first. ✅ (+F-012, F-013 incidental)
- Deterministic census → `deliverables/CENSUS.md` ✅ (Redis keys incomplete — see below)

**Carried forward from S01 to S02:** the Redis key census failed its method and is
S02's first task. See `CENSUS.md` §7.

---

## Phase A — Understanding

### S02 · Architecture map — cinemate (Python) — ✅ DONE

- ~~Complete the Redis key census~~ ✅ `ParameterKey` is the registry; F-014/F-015.
- ~~Trace `src/main.py` boot~~ ✅ 28-step order, full thread table, shutdown gaps F-022..F-024.
- ~~Map the control surfaces onto the dispatcher~~ ✅ two paths, one lock; F-025/F-026.
- ~~Name the seams~~ ✅ CODE-MAP §7.
- → `deliverables/CODE-MAP-cinemate.md` ✅

**Deferred out of S02 at the budget line:** `cinepi_controller.py` (2626 LOC) internals,
`redis_listener.py` (2084 LOC) internals. Neither is S03's subject. Fold the controller
read into PI-007 step 1 (a desk task) or into S05.

### S03 · Architecture map — cinepi-raw (C++) — ✅ DONE

- Trace `cinepi/cinepi_raw.cpp` → manager/controller/state → capture loop →
  `dng_encoder` / `cinepi_sound` → preview stages → Redis bridge.
- Document the frame lifecycle end to end, and the metadata path (timing → DNG tags).
- Note where behavior depends on the forked libcamera without auditing libcamera.
- **Also resolve:** how `cinepi_audio_capture.cpp` and `lj92.c` enter the build — neither
  is in `cinepi/meson.build`'s source list (CENSUS.md §3).
- **Carry F-016 forward:** `cinepi_sound.cpp:22` declares `RECORDER_VU_REDIS_KEY = "audio_vu"`,
  hand-mirrored in `simple_gui.py:21`. While tracing the Redis bridge, **enumerate every
  Redis key cinepi-raw writes or reads** and diff against cinemate's 84-member
  `ParameterKey`. That cross-repo key diff is the single most valuable thing S03 can
  produce for ADR-001, and nobody has it.
- Remember the constraint: shallow read-only clone on `main`, no history (STATE.md D2).
- → `deliverables/CODE-MAP-cinepi-raw.md`

---

## Phase B — Critical analysis

### S04 · Redundancy & dead code sweep *(agent fan-out, both repos)* — ⚠ RETRY NEEDED

> **Attempt 1 (2026-08-18) produced nothing.** All four agents died on an account session
> limit in their first step. Prompts are saved verbatim in
> `agent-reports/S04-AGENT-PROMPTS.md` — the retry is copy-paste. F-100..F-299 unconsumed.
> If capacity is uncertain, run **two agents at a time**; agents 1 and 4 are highest value.
> The one thing attempt 1 delivered was `harness/redis_key_diff.py`.

- Unreferenced files, unreachable code, dead branches, commented-out blocks.
- Duplicated logic: same computation in two places; constants duplicated across the
  Python/C++/CSS boundary; parallel implementations that drifted.
- Dead config keys, dead Redis keys, dead CLI commands, dead settings.
- Stale patch files, unused build targets, vestigial `codex/`-era leftovers.
- **S01 handed over these specific candidates — confirm or clear each:**
  - `parameters.py`, `rotary_encoder.py`, `timekeeper.py` — no inbound import edge
  - `app/raw_files.py`, `app/boot_config.py` — no inbound edge; may be dynamically loaded
  - `src/module/__pycache__/adc.cpython-39.pyc` — bytecode for a module that no longer exists
  - four `_test/` underscore files, three `_test/` non-test utilities
  - the two cinepi-raw root patch files (see PI-003)
  - three-way `wifi_hotspot` duplication (`src/module/`, `services/`, `_test/`)
  - `usb_monitor.py` opening its own Redis client at 4 sites instead of reusing the injected one
- **Already confirmed dead by S02/S03 — do NOT re-investigate, just fold into the report:**
  `timekeeper.py` (243 LOC, F-017) · `keyboard.py` (F-031) · `src/stream.py` (F-013) ·
  `handle_vu_output()` (F-018) · `lj92.c`+`lj92.h` (1218 LOC, F-029) ·
  `_mjpegPreviewStage.cpp` (F-012) · 4 unreferenced HTML templates (F-001)
- **Still open from S02/S03 — these are the real S04 work:**
  `parameters.py`, `rotary_encoder.py`, `app/raw_files.py`, `app/boot_config.py`;
  the 11 orphaned Redis keys (F-027, see PI-008); the 7 unused installer packages (F-032);
  the two cinepi-raw patch files (PI-003); `cinepi_state.cpp`/`cinepi_manager.*` unread
- ID blocks: agent1 F-100.., agent2 F-150.., agent3 F-200.., agent4 F-250..
- → `deliverables/REDUNDANCY-REPORT.md`

### S05 · Readability, comments & structure

- Target reader: **competent but intermediate** Python/C developer, new to this code.
- Flag: functions >60 lines, nesting >3 deep, magic numbers, boolean-parameter APIs,
  unclear names, over-clever code, inconsistent abstraction level within a function.
- Comments: stale or contradicted-by-code, comments that restate *what* instead of *why*,
  missing docstrings on public seams.
- **Equally important — comments that are load-bearing and must be preserved.** Several
  blocks encode hard-won knowledge (why a constant is what it is, which hypotheses were
  falsified). `simple_gui.py:31-45` is a confirmed example — the top-row geometry comment
  explains *why* `RES_RIGHT_ANCHOR = 1823`. Identify these; recommend promoting to docs.
- → `deliverables/READABILITY-REPORT.md`

### S06 · Standards, consistency & tooling

- Given F-005/F-006: propose a **minimal, low-friction** standard. One developer plus
  agents. Do not propose a twelve-tool pipeline that will be abandoned.
- Consistency audit: logging, error handling and bare `except`, thread start/stop
  patterns, Redis access patterns, settings access, hardcoded absolute paths, import style.
- Draft — do not apply — `pyproject.toml`/`ruff.toml`, `.editorconfig`, a test CI
  workflow, and a pre-commit config if warranted.
- **Blocked on PI-002** for the CI proposal: the portable/hardware test split is unknown
  until the suite is actually run. Draft the workflow with an explicit assumption stated.
- Decide whether type hints are worth it here, and if so where. Argue both sides.
- → `deliverables/STANDARDS-PROPOSAL.md` + `deliverables/draft-config/`

---

## Phase C — GUI

### S07 · GUI surface inventory & state-model extraction

- Complete the KICKOFF §6.3 table: every surface, every widget, every control, every field.
- Build the surface × field matrix with source-of-truth per field.
- Separate genuinely surface-specific affordances (eject, file browser, settings editing)
  from things duplicated by accident.
- Build the `harness/` render tooling described in KICKOFF §7.
- **Start by reading `_test/test_simple_gui_preview_guide.py`** — S01 found it already
  exercises `simple_gui` off-hardware. It is the working precedent for the offscreen
  render harness; do not reinvent the stubbing approach.
- → `deliverables/GUI-INVENTORY.md`, `deliverables/GUI-STATE-MODEL.md`

### S08 · GUI harmonization evaluation → ADR-001

- Execute KICKOFF §7 in full: five options against seven constraints, run the divergence diff.
- **Must queue the DRM-ownership Pi test** — options D and E stand or fall on it
  (PI-VERIFICATION-QUEUE.md, Notes on scope).
- Split into S08a/S08b if the window runs out. Do not rush the recommendation.
- → `decisions/ADR-001-gui-harmonization.md`

---

## Phase D — Truth passes

### S09 · Docs vs. code

- Every file in `docs/` against actual behavior. Prioritize thinnest coverage of biggest
  surfaces: `web-gui.md` 32 LOC / 965-LOC template; `simple-gui.md` 31 LOC / 2129-LOC module;
  `compiling-cinepi-raw.md` 15 LOC / 24k-LOC repo.
- Check `settings-json.md` against `settings.schema.json` and against what code actually
  reads; `redis-keys.md` against keys actually used (**needs S02's key census first**);
  `cli-commands.md` against the real dispatcher; `changelog.md` against git history since
  the `cinemate-v3.1.1` tag.
- Check the mkdocs nav for links to missing or empty pages — **S01 already established
  the shape (F-004): 50 docs, 35 nav entries, 15 unreachable, 5 empty. Start from
  CENSUS.md §9 rather than recounting.**
- → `deliverables/DOCS-DRIFT-REPORT.md`

### S10 · Install script vs. install docs

- `cinemate-install.sh` (1916 LOC) against `docs/installation-steps.md` (1061 LOC), step
  by step. Correspondence table; every divergence is a finding.
- **F-002/F-003 are already settled** (see `findings/F-003.md`) — do not re-derive the
  dependency divergence. S10's job is the *rest* of the installer, plus choosing between
  F-003's two remediation options.
- Audit `services/` unit files and Makefiles against what the docs claim is installed.
  Note `services/storage-automount/storage-automount.py` is ~1123 LOC and was invisible
  to KICKOFF §6.2's `src/`-only table.
- Check the installer against the most recent feature work on `dev`.
- Run `shellcheck` on the installer if available; record every warning class.
- Check idempotency and failure handling by reading: what happens on re-run, on failure
  at each stage.
- → `deliverables/INSTALL-DRIFT-REPORT.md`

---

## Phase E — Synthesis

### S11 · CineMate style, philosophy & skill payload

- `deliverables/CINEMATE-STYLE.md` — how code is written here. Naming, module shape,
  error handling, logging, threading, config, comments. Derived from the code, with
  citations, not from generic best practice.
- `deliverables/CINEMATE-PHILOSOPHY.md` — KICKOFF §9 has 8 candidate principles; confirm,
  refute, or refine each **against code**, and add what you found. Note where the codebase
  violates its own principles — those violations are findings.
  - S01 early signal for principle 1 ("Redis is the single source of live state"):
    `redis_controller` is imported by 10 modules, the widest fan-in in the repo
    (CENSUS.md §4). Suggestive, not proof.
- `deliverables/ENTRY-POINTS.md` — the "where do I go to change X" table. Highest-value
  artifact for future sessions. Every row: task → file → function → what else to update.
- `deliverables/SKILL-PAYLOAD.md` — the above, packaged for the `cinemate-dev` skill's
  `references/` directory. Self-contained; assumes no repo access.

### S12 · Remediation plan

- Triage every finding into PR-sized batches. Order by
  (risk reduction × comprehension gain) ÷ blast radius.
- Each batch: what changes, why, which findings it closes, how to verify on a Mac, what
  needs the Pi, how to roll it back.
- Separate "safe now" (dead file deletion, tooling config, docs) from "needs Pi
  confirmation" from "blocked on ADR-001".
- Finalize `PI-VERIFICATION-QUEUE.md` as the Stage-2 work order.
- → `deliverables/REMEDIATION-PLAN.md`
