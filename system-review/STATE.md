# STATE

**Read this first, every session.** Then read the last `sessions/S##-*.md`, then do what
`PLAN.md` says is next.

- **Last session:** S03 (2026-08-18) — Architecture map, cinepi-raw (C++)
- **Current phase:** A complete → B. Both repos are now mapped.
- **Next session:** S04 — Redundancy & dead code sweep *(the fan-out session)*
- **Ledger branch:** `claude/cinemate-system-review-kickoff-cilicc` — pushed: yes · PR #129 (draft)
- **Findings:** 33 total — 0 critical, 11 high, 15 medium, 6 low, 1 refuted
- **Open decisions:** ADR-001 (GUI harmonization) — not started.
  **S03 supplied its hardest evidence and its hardest blocker.** DRM master exclusivity is
  now confirmed *from cinepi-raw's own comment* (`dualHdmiPreviewStage.cpp:5-18`), which
  likely kills options D and E. But **PI-009 blocks S08**: how the DRM preview and the
  fbdev GUI actually compose cannot be determined from source.
- **Blockers:** none for S04. **PI-009 blocks S08** — do not let S08 answer KICKOFF §7
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
- **The Redis key census is DONE** (S02). `ParameterKey` at `redis_controller.py:18` is the
  registry; the docs diff is F-014. Do not re-derive it. `CENSUS.md` §7 is superseded.
- **Do not re-trace `main.py` boot or shutdown** — `deliverables/CODE-MAP-cinemate.md` §3–4
  has the 28-step construction order and the full thread table with verified citations.
- **Do not re-map the control surfaces** — CODE-MAP §5 has both dispatch paths. Note the
  keyboard surface is **dead** (F-031); an early revision of that map said otherwise.
- **Do not redo the cross-repo Redis key diff** — S03 did it, `findings/F-027.md`.
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
- **The F-027 key-diff harness script is unwritten.** It would turn the cross-repo drift
  into a CI check. Needs no hardware; belongs in `harness/`. Highest value-per-effort item
  currently unclaimed.
- **`cinepi_controller.py` (2626 LOC) internals are still untraced** — deliberately
  deferred at S02's budget line. It is the largest remaining unknown in the Python side and
  it gates F-025's severity.

- `CENSUS.md` §12 lists everything S01 deliberately left unestablished. Check it before
  assuming coverage.
- `PI-VERIFICATION-QUEUE.md` has 5 open entries. **PI-002 (run the test suite) gates
  S06's CI proposal** — it should be among the first things done once hardware is available.
- PI-003 is mislabelled as Pi-bound; it only needs a full cinepi-raw clone. Reclassify
  when one is attached.
