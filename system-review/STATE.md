# STATE

**Read this first, every session.** Then read the last `sessions/S##-*.md`, then do what
`PLAN.md` says is next.

- **Last session:** S07 (2026-08-23) — GUI inventory **delivered**:
  `deliverables/GUI-INVENTORY.md`, `deliverables/GUI-STATE-MODEL.md`,
  `harness/gui_field_extract.py`, 22 findings, 2 PI items. See
  `sessions/S07-gui-inventory.md`.
- **Current phase:** C — GUI.
- **Next session:** **S08 — GUI harmonization evaluation → ADR-001.** Still gated by
  PI-009, but S07 narrowed it substantially — read `GUI-STATE-MODEL.md` §6 first.
- **Ledger branch:** `claude/cinemate-system-review-kickoff-cilicc` — pushed: yes · PR #129 (draft)
- **Findings:** 151 rows, **146 net** (F-183..F-186, F-189 merged into F-002/F-003). Free ID
  blocks: F-135..F-149, F-196..F-199, F-225..F-249, F-262..F-299.
- **Open decisions:** ADR-001 (GUI harmonization) — not started.
  **S03 supplied its hardest evidence and its hardest blocker.** DRM master exclusivity is
  now confirmed *from cinepi-raw's own comment* (`dualHdmiPreviewStage.cpp:5-18`), which
  likely kills options D and E. But **PI-009 blocks S08**: how the DRM preview and the
  fbdev GUI actually compose cannot be determined from source.
- **Blockers:** **PI-009 blocks S08** — do not let S08 answer KICKOFF §7
  constraint 2 from reasoning.

---

## Deviations from KICKOFF — read before touching git

KICKOFF is immutable (§10). These corrections live here instead.

### D1 · Branch name differs

KICKOFF §3 says `review/system-analysis`. **The actual ledger branch is
`claude/cinemate-system-review-kickoff-cilicc`**, mandated by the session harness, which
forbids pushing elsewhere without permission. Cut from `origin/dev` @ `02b5a39`.

Use this branch. Do not create `review/system-analysis` without asking the operator.

### D2 · cinepi-raw is read-only, shallow, and on `main` — not `dev`

Not a sibling checkout. Fetched per-session as an anonymous clone at
`/workspace/tiramisioux/cinepi-raw`, branch **`main` @ `774402c`**.

- **Cannot push.** No review branch exists there. Stage-2 work needs `add_repo` with
  `access: "push"`, which lands the clone at a *different* path (`/workspace/cinepi-raw`).
- **No history.** Shallow clone — no `git log`, blame, or `-S`. PI-003 is blocked on this.
- **C++ LOC differ from KICKOFF §6.2**, which described `dev` @ `ea96f2d`. Use
  `CENSUS.md` §2 for `main` figures. Do not mix the two tables.
- `libcamera/` and `imx585-v4l2-driver/` are absent entirely.

**If a fresh session finds no cinepi-raw:** re-clone with
`GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/Tiramisioux/cinepi-raw /workspace/tiramisioux/cinepi-raw`

### D3 · The dirty tree in KICKOFF §6.1 does not exist

Working tree is clean; `origin/dev == 02b5a39 ==` branch base. KICKOFF §11 step 3 ("ask
the operator about the 8 uncommitted files") is **satisfied with nothing to ask.** See
`findings/F-011.md`. Do not go looking for those edits.

### D4 · The LFS pointer trap did not reproduce

`docs/images/*.png` are real files (53–75 KB), tree clean. `.gitattributes` does route
`*.png`/`*.jpg`/`*.ipynb` through LFS, so the trap is real in principle.
**Keep staging narrowly regardless:** `git add system-review/`, never `git add -A`.
Run `git status --short` before every commit.

### D5 · Ledger lives inside the repo, intentionally

KICKOFF §3 notes this overrides the operator's normal convention (scratch workspaces
outside the repo tree). Sessions run on clients that only see the repo, so git is the only
cross-session persistence layer. **This is deliberate. Do not "fix" it.**

---

## Ground truth established so far

### From S05 (readability) — detail in `deliverables/READABILITY-REPORT.md`
- **The best comment in the codebase guards an invariant that no running test protects.**
  `storage_profiles.py:41-49` (AUDIO-CORE INVARIANT) names its own guarding test, and that
  test is one of the 27 that never run. Sharpest argument in the review for CI first.
- **47 load-bearing why-comments exist and are a deletion hazard** (F-133), including two
  falsified experiments. Promote to `docs/` before refactoring those files.
- **Zero TODO/FIXME/XXX/HACK** in ~19,800 LOC (F-134) — a genuine positive.
- **337 except handlers, 15 silently swallowing** (F-130) — violates the project's own
  "fail visible" principle.
- **The codebase explains decisions well and interfaces poorly** — 27% docstring coverage,
  40 public classes with none including `CinePiController`.
- **A second duplication cluster exists around storage** (F-155..F-165), and **F-164 is its
  root cause**: the service↔app coupling is a dead journalctl tail, so the app polls
  instead. Fixing that one link collapses five findings.

### From S04 (redundancy sweep) — detail in `deliverables/REDUNDANCY-REPORT.md`
- **Duplicated truth is systemic: 16 instances, 9 already drifted.** This is the review's
  central structural finding and it constrains ADR-001 — see the deliverable §6.
- **F-118 is the proof it costs something:** a Python↔JS duplicated action catalogue offers
  `set_log` where the method is `set_log_encode`, so a settings-editor button silently
  no-ops **today**.
- **≈3,250 LOC of confirmed-dead source** is deletable with no hardware (deliverable §2).
- **Module reachability in `src/` is exhausted** — exactly 4 of 48 unreachable (F-122).
- **No triple sensor table.** `resources/sensors.json` is a genuine single source; cinepi-raw
  holds no sensor data. Hypothesis disproved — do not re-hunt.
- **`settings.schema.json` agrees with `config_loader.py` on all 41 comparable defaults** —
  the viable origin for defaults unification (F-251).

### From S06 (standards) — detail in `deliverables/STANDARDS-PROPOSAL.md`
- **The review's organising claim, now stated outright: CineMate has a drift problem, not a
  style problem.** Every serious finding is two copies of one truth that stopped agreeing.
  The standard is built around drift *checks*, with lint second and formatting last. Carry
  this framing into S11 and S12 — it is the spine of the remediation plan.
- **The rule worth writing down:** *duplicated truth must either be deleted, or carry a
  named reason **and** an automated check. A comment is not a check.* Three hand-sync
  comments exist; two are already wrong.
- **The shell is the best-maintained code in the repo** (F-174, F-192, F-194). 15 shellcheck
  findings across 11 scripts, one of them in the 1916-line installer, whose idempotency is
  *designed and documented*. The standards proposal generalises from it rather than
  importing conventions from outside. Do not propose shell cleanup as a priority.
- **`settings.schema.json` cannot reject an unknown key** — `"additionalProperties": true`
  25×, `false` 0× (F-166). A typo'd setting validates clean and is silently ignored.
- **The in-app log queue is never drained** (F-172) — unbounded growth for the process
  lifetime. Structurally confirmed; rate is PI-013.
- **`INSTALL_ALT_GPIO_BACKEND` is advertised as optional but is load-bearing for boot**
  (F-182) → PI-012. The only S06 finding that touches the install path.

### From S07 (GUI) — detail in `deliverables/GUI-INVENTORY.md` + `GUI-STATE-MODEL.md`
- **THE headline for ADR-001: the web GUI has no state model of its own — it consumes
  `simple_gui.populate_values()` verbatim** (F-203). The operator's hypothesis is half
  right and the true half is the expensive half. A shared state model does not need
  building; it exists, 68 fields wide, one owner.
- **Option C's widget spec also already exists** (F-215): `left_section_layout` /
  `right_section_layout` in `setup_resources` — label, ordered items, per-item formatters,
  optional visibility `condition`. Encoded as Python lambdas, so not serialisable, but the
  shape is right. **The residual hard problem is layout and only layout** (F-008).
- **Surface 4 (recovery console) must be excluded from any unification** (F-221). Its value
  is its isolation, and it is the best-engineered component in the review.
- **F-204 is the most severe finding in the ledger.** One raising redis subscriber kills the
  live-state bus permanently and silently; `get_value()` then serves a stale cache, so every
  surface shows plausible frozen values instead of an error. That is the baseline for
  KICKOFF §7 constraint 5. → PI-014. **F-208: the guarded version of the same loop already
  exists 900 lines away** (`cinepi_controller.py:1082-1087`).
- **HDMI hot-plug restarts `cinepi-raw`** (F-223) — so the preview binds to the display at
  process start and cannot rebind. Strongest static evidence for PI-009; narrows ADR-001
  constraint 2 without settling it.
- **The settings-editor action catalogue is the thesis in miniature**: 3 copies, the two
  hand-maintained ones agreeing perfectly *including on the same bug*, a hand-correction
  that was itself incomplete, and the mechanical check written and unwired (F-218..F-220).
- **381 tests across 27 files have never run** (F-222). F-006 undercounted the loss.
- **The extractor over-counted once and under-counted once, in one session.** Both were
  caught by re-checking output against source. Numbers not produced by a committed script
  should be treated as provisional.
- **Incremental agent writes are mandatory, not advice.** Two agent runs died mid-flight
  to usage limits; the one told to write incrementally preserved 16 findings, the four that
  weren't preserved nothing.
- **Pattern matching has under-reported three times now** (`cinepi_ready_<port>`, `tc_key`,
  `from module import X`). Treat "no grep hit" as a hypothesis, never a result.
- **And it has OVER-reported once** (S06): a naive schema walk claimed 88 settings keys were
  unvalidated; most were covered by `additionalProperties` subschemas and `$ref`s. The real
  finding was different and stronger (F-166). Probe the structure before counting it.
- **Read `STATE.md` before the first grep — including in a resumed session.** S06 skipped it
  and re-derived F-002/F-003 as five new findings before catching itself. The "Do not redo"
  list below only works if it is actually read.

### Tooling now in the ledger
- **`harness/redis_key_diff.py` works** and reproduces F-027: 84 / 32 / 19 shared / 12
  unreferenced. Run it before trusting any hand-counted key figure — it already caught one
  arithmetic error in F-027 (11 → 12 key strings).

### From S03 (cinepi-raw architecture) — detail in `deliverables/CODE-MAP-cinepi-raw.md`
- **cinepi-raw is a fork of `rpicam-apps`.** `cinepi/` is the product; `core/`, `preview/`,
  `encoder/`, `apps/` are upstream.
- **Three executables**, not one: `cinepi-raw`, `cinepi-audio-capture` (separate process,
  supervised via fork/popen), and `phase_lock_core_test` (wired into `meson test`).
- **The cross-repo contract is the `cp_controls` channel.** cinepi-raw's registry is 24
  `CONTROL_KEY_*` macros (`cinepi_state.hpp:23-52`) against cinemate's 84-member enum.
  ≥19 shared, ≥11 orphaned (F-027). Counts are lower bounds — dynamic keys exist.
- **`cinepi_ready_<port>` is a live handshake in neither registry** and is a fifth Redis
  access pattern (glob scan through the raw client).
- **DRM master is exclusive and cinepi-raw holds it.** The project already worked around
  this once for dual-sensor, using SysV shared memory rather than sharing the display.
- **The GUI and the preview use two different kernel interfaces** — DRM/KMS vs legacy
  fbdev. How they compose is unknown (PI-009).
- **The RAM auto-stop is `cinepi_raw.cpp:200-212`** — a hard stop on the record path.

### From S02 (cinemate architecture) — detail in `deliverables/CODE-MAP-cinemate.md`
- **`ParameterKey` (`redis_controller.py:18`) is the canonical Redis registry** — 84
  members. It is convention, not enforcement: `set_value` accepts any string (F-015).
- **Redis docs are a strict subset of code** — 18 undocumented keys, 0 orphan docs (F-014).
  The gap clusters around dual-sensor and dynamic-resolution work.
- **`RedisController` caches locally.** `get_value()` reads the cache, not Redis; a pub/sub
  listener thread keeps it fresh. Four distinct access patterns exist across the codebase.
- **Two paths into `CinePiController`, one serialised.** CLI/serial/HTTP share
  `_dispatch_lock`; GPIO, pots, quad rotary and keyboard bypass it entirely (F-025).
- **`settings.jsonc` contains controller method names**, resolved by `getattr`. Those 94
  method names are a user-facing API — renaming one is a breaking change (F-026).
- **Boot is one 400-line straight-line function**; `cleanup()` sits 300 lines away in the
  same function and misses four components (F-022, F-023, F-024).
- **`timekeeper.py` (243 LOC) is entirely dead** — `Timekeeper(` appears nowhere (F-017).

- **Scale.** cinemate: 47 Python files / 19,794 LOC in `src/`, plus a 1,916-LOC installer,
  50 docs, 34 files in `_test/`, 5 systemd service subsystems (one of which,
  `storage-automount.py`, is ~1,123 LOC and was invisible to KICKOFF's `src/`-only table).
  cinepi-raw: 24,051 LOC C/C++. → `deliverables/CENSUS.md` §1–2
- **`redis_controller` is the hub** — imported by 10 modules, the widest fan-in in the
  repo. Early support for KICKOFF §9 principle 1, not yet proof. → CENSUS.md §4
- **`main.py` imports 27 modules directly.** No intermediate composition layer. → CENSUS.md §4
- **Ports:** 5000 (Flask GUI/API/settings-editor), 8888 (status broadcast), 8080 (recovery
  console), 8000/8001 (MJPEG preview, consumed not bound), 6379 + 8423 outbound.
  → CENSUS.md §6
- **The GUI colour duplication (F-007) is self-documenting** — `template.html`'s CSS
  custom properties carry comments naming the Python constants they mirror. Strongest
  available argument for ADR-001 option B.
- **The HDMI GUI scales, it does not reflow.** `simple_gui.py:1657-1658` applies
  `shrink_x` to the 1920-reference constants. F-008's real obstacle is the absence of
  content-driven layout, not the absence of scaling. Matters for S08.
- **A working off-hardware `simple_gui` test already exists** —
  `_test/test_simple_gui_preview_guide.py`. This is the precedent for the S07 render harness.
- **Dependency management is broken in a specific, documented way** — `requirements.txt`
  is read by nothing; `flask` is never installed directly. → `findings/F-003.md`

## Do not redo

- **Do not re-verify F-001..F-013.** Each was checked against source in S01. Read
  `FINDINGS.md` and the `findings/*.md` detail files.
- **Do not re-derive the requirements.txt / installer divergence.** Fully computed in
  `findings/F-003.md`, including the exact package lists both ways. S10 chooses between
  the two remediation options; it does not recount.
- **Do not recount the docs.** `CENSUS.md` §9 has the complete 50-file inventory, the
  empty files, and the mkdocs nav gaps. S09 starts from there.
- **Do not re-audit logging, `print()`, shellcheck, or the settings schema.** S06 did all
  four; figures are in `sessions/S06-standards.md` and F-166..F-181.
- **Do not re-derive installer idempotency.** F-192 settles it: idempotent by construction.
- **Do not re-inventory the GUI surfaces or re-count their fields.** S07 did it and the
  counts are reproducible: `python3 system-review/harness/gui_field_extract.py --repo .`
- **The Redis key census is DONE** (S02). `ParameterKey` at `redis_controller.py:18` is the
  registry; the docs diff is F-014. Do not re-derive it. `CENSUS.md` §7 is superseded.
- **Do not re-trace `main.py` boot or shutdown** — `deliverables/CODE-MAP-cinemate.md` §3–4
  has the 28-step construction order and the full thread table with verified citations.
- **Do not re-map the control surfaces** — CODE-MAP §5 has both dispatch paths. Note the
  keyboard surface is **dead** (F-031); an early revision of that map said otherwise.
- **Do not redo the cross-repo Redis key diff** — S03 did it, `findings/F-027.md`.
- **Do not re-run module reachability in `src/`** — F-122 is the corrected, exhaustive result.
- **Do not re-hunt a duplicated sensor table** — disproved in S04.
- **Do not re-verify F-100..F-127, F-200..F-202, F-250..F-261** — all merged with citations.
- **Do not re-derive the cinepi-raw build graph** — CODE-MAP-cinepi-raw §2. `lj92.c` is
  dead (F-029); `cinepi_audio_capture.cpp` is a separate executable, not a missing source.
- **Do not look for the 8 uncommitted files** (D3) or the LFS pointer corruption (D4).
- **Do not re-read `KICKOFF.md` §6.2's C++ table as current.** It describes a different
  branch than the one available. (D2)

## Watch items

- **PI-007 step 1 is a desk task, not a Pi task.** Reading `cinepi_controller.py` for
  internal locking may settle F-025 for free. Do it before booking hardware time.
- **The DNG metadata path (timing → DNG tags) was in S03's brief and was not done.**
  `dng_save()` and `dng_encoder.cpp` (1521 LOC) remain untraced. Blocks nothing yet.
- ~~The F-027 key-diff harness script is unwritten.~~ **Done** — `harness/redis_key_diff.py`.
  S07 added a second: `harness/gui_field_extract.py`, which independently reproduces F-118.
  Both are wired into `STANDARDS-PROPOSAL.md` §3 as CI checks and neither needs hardware.
- **`cinepi_controller.py` (2626 LOC) internals are still untraced** — deliberately
  deferred at S02's budget line. It is the largest remaining unknown in the Python side and
  it gates F-025's severity.

- `CENSUS.md` §12 lists everything S01 deliberately left unestablished. Check it before
  assuming coverage.
- `PI-VERIFICATION-QUEUE.md` has **15** open entries. **PI-002 (run the test suite) gates
  S06's CI proposal** — it should be among the first things done once hardware is
  available, and F-222 raises its value: **381 tests**, not 27 files.
- PI-003 is mislabelled as Pi-bound; it only needs a full cinepi-raw clone. Reclassify
  when one is attached.
