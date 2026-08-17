# CineMate / CinePi-raw System Review — Kickoff

**This file is the complete specification for a long-horizon, multi-session, critical
review of the CineMate + CinePi-raw ecosystem. It is self-contained. Do not assume any
skill, external reference file, or prior conversation is available.**

Read this file top to bottom before doing anything. Then read `system-review/STATE.md`
(if it exists) and do only what it says is next.

---

## 1. What this is

A static, hardware-free, multi-session audit of the camera stack, run mostly by
subagents, producing a durable on-disk ledger. It ends with decisions and a sequenced
remediation plan — not with code changes.

**Goals, in priority order:**

| # | Goal |
|---|------|
| 1 | Understand the system well enough to write down how it actually works |
| 2 | Find redundancy, dead code, and duplicated logic across both repos |
| 3 | Make the code readable to a competent *intermediate* Python/C developer |
| 4 | Establish coding standards and consistency where none exist today |
| 5 | Decide whether the three+ GUI surfaces should be unified, and how |
| 6 | Verify docs match code, and that install docs match the install script |
| 7 | Distill a reusable "CineMate style + philosophy + code map" for future work |
| 8 | Produce a risk-ordered remediation plan and a Pi-verification queue |

**Explicit non-goals for this stage:** no refactoring, no source edits, no Pi.

---

## 2. Hard constraints — read these twice

### 2.1 No Raspberry Pi

There is **no hardware access during this entire review**. Pi verification is Stage 2,
after decisions are made.

Consequences:

- Never state runtime behavior as confirmed. You can only confirm what the *source* says.
- Anything that needs hardware to settle goes into `system-review/PI-VERIFICATION-QUEUE.md`
  with an exact test procedure. That queue is a first-class deliverable.
- Timing, thermals, DRM/framebuffer ownership, sensor behavior, storage throughput,
  and audio sync are all **unverifiable here**. Reason about them from code, label the
  conclusion `probable` or `unverified`, and queue the test.

### 2.2 Analysis only — zero source edits

During every session in the plan below, the **only** files you may create or modify are
under `system-review/**` in the cinemate repo.

Do not touch `src/`, `docs/`, `cinemate-install.sh`, or anything in cinepi-raw. Proposed
changes are *written down as proposals*, including full draft file contents where useful,
but not applied. This keeps the review branch trivially reviewable and prevents
half-finished refactors from accumulating across sessions.

### 2.3 The disk is your memory

Context *will* run out, repeatedly, mid-task. Treat every session as if it may be
killed without warning.

- Write findings to the ledger **as you discover them**, never in a batch at the end.
- A finding that exists only in your context does not exist.
- Commit and push after every meaningful unit of work, not just at session end.

### 2.4 Every claim needs evidence

Every finding must cite `path:line` (or `path:start-end`) that you actually read in this
session or that is recorded in the ledger. No claims from inference alone, from
plausible-sounding memory, or from "this is how such systems usually work."

Confidence is mandatory and has exactly three values:

| Value | Meaning |
|---|---|
| `confirmed` | Directly observed in source you read. Cite the lines. |
| `probable` | Consistent with observed evidence, one inferential step away. Say what the step is. |
| `unverified` | Needs something you don't have (usually the Pi). Must have a queue entry. |

Downgrade aggressively. A wrong `confirmed` poisons every later session that trusts the
ledger.

### 2.5 Session budget — Claude Pro, 5-hour windows

The operator is on a Claude Pro plan with a rolling 5-hour usage window. Sessions must
fit inside one window and must fail safe.

Rules:

- **One plan entry per session.** Do not start the next one "because there's time left."
- **Max 4 concurrent subagents.** Each writes its own report file and returns a
  summary of **20 lines or fewer**. Never let a subagent return a full report into your
  context — that is the fastest way to burn the window.
- **At ~60% context used: stop starting new work.** Finish the current item, write the
  handoff, commit, push. Do not gamble on one more agent.
- Prefer `rg` / `grep -n` / `wc -l` / `sed -n 'A,Bp'` over reading whole large files.
  Several files here are >2000 lines.
- If a fact is already in the ledger, read the ledger — do not re-read the source.

---

## 3. Repos, branches, and where the ledger lives

Two sibling repos are checked out:

```
<workspace>/
  cinemate/      Python: UI, controller, services, docs, installer
  cinepi-raw/    C++: capture, DNG/WAV writer, preview, Redis bridge
```

There may also be `libcamera/` and `imx585-v4l2-driver/`. They are **out of scope** for
this review except where cinepi-raw's behavior depends on them — note the dependency,
do not audit them.

**Branches.** Both repos develop on `dev`. Create, from `dev`, in each repo:

```
review/system-analysis
```

The cinemate branch carries the ledger. The cinepi-raw branch stays empty during
Phases 0–4; it exists so Stage-2 work has somewhere to land.

**The ledger lives at `cinemate/system-review/`** and is committed and pushed to
`origin review/system-analysis` every session. This is not optional: fresh sessions
start cold and clone from the remote, so an unpushed ledger is a lost ledger.

Never commit to `dev`. Never push to `dev`.

> **Note on convention:** the operator's normal convention puts scratch/dev workspaces
> *outside* the repo tree. That is deliberately overridden here — sessions run on a
> mobile client that only sees the repos, so git is the only viable cross-session
> persistence layer. Record this as an intentional exception in `STATE.md`.

---

## 4. Ledger layout

Create this on first run:

```
cinemate/system-review/
  KICKOFF.md                  This file. Immutable — never edit it.
  STATE.md                    Read first, every session. Current phase, what's done, what's next.
  PLAN.md                     The session plan (copy §8 into it, then keep it updated).
  CONVENTIONS.md              Schemas and rules (copy §5 into it).
  FINDINGS.md                 Append-only one-line index of every finding.
  findings/F-###.md           Detail file, for findings that need more than three lines.
  decisions/ADR-###-slug.md   Decisions. One per real fork in the road.
  sessions/S##-slug.md        One log per session. Append as you go.
  agent-reports/<slug>.md     Raw subagent output. Never edited, only appended to.
  deliverables/               The actual outputs. See §8.
  harness/                    Runnable simulation/verification scripts (Mac-only, no Pi).
  PI-VERIFICATION-QUEUE.md    Everything that needs hardware, with exact test steps.
  HANDOFF.md                  Overwritten each session. Paste-ready prompt for the next one.
```

### STATE.md — the single most important file

It is the entry point for every future session. Keep it short and current. Template:

```markdown
# STATE

- Last session: S03 (2026-08-19)
- Current phase: A — Understanding
- Next session: S04 — Redundancy & dead code sweep
- Ledger branch: review/system-analysis @ <sha>, pushed: yes
- Findings: 41 total (3 critical, 9 high, 18 medium, 11 low)
- Open decisions: ADR-001 (GUI harmonization) — drafting, blocked on S07 inventory
- Blockers: none

## Ground truth established so far
- <one line per durable fact, with a pointer to the deliverable that holds the detail>

## Do not redo
- <things a future session might wastefully repeat>
```

---

## 5. Conventions

### 5.1 Finding schema

Append one line per finding to `FINDINGS.md`:

```
| F-042 | high | confirmed | cinemate | redundancy | Four unreferenced HTML templates, ~928 LOC | src/module/templates/ |
```

Columns: `id | severity | confidence | repo | category | one-line summary | primary evidence path`

If the finding needs more than three lines of explanation, create `findings/F-042.md`:

```markdown
# F-042 — <title>

- **repo:** cinemate | cinepi-raw | both | docs | install
- **severity:** critical | high | medium | low | nit
- **confidence:** confirmed | probable | unverified
- **category:** redundancy | dead-code | correctness | readability | structure | standards | docs-drift | install-drift | gui | perf | test-gap
- **evidence:** src/module/foo.py:123-140
- **needs-pi:** yes | no
- **effort:** S | M | L

## What
## Why it matters
## Proposed action
## Risk if changed
## How to verify the fix (Mac / Pi)
```

Severity is about **consequence**, not effort:

| Severity | Means |
|---|---|
| critical | Can lose footage, corrupt data, or brick a shoot |
| high | Wrong behavior, or a maintenance trap that will cause a bug soon |
| medium | Real cost to comprehension or maintenance |
| low | Worth fixing when nearby |
| nit | Cosmetic |

IDs are global, sequential, never reused. Reserve a block before fanning out agents
(e.g. "agent 1 uses F-100..F-149") so parallel agents never collide.

### 5.2 Subagent rules

Every subagent prompt must include, verbatim:

1. Its assigned finding-ID block.
2. The exact output file path it must write (`system-review/agent-reports/<slug>.md`).
3. "Cite `path:line` for every claim. No claim without evidence."
4. "You have no Raspberry Pi. Anything needing hardware is `unverified` — say what test would settle it."
5. "Do not modify any file outside `system-review/`."
6. "Return at most 20 lines: counts by severity, your finding IDs, and anything that
   blocks other agents. Your full report goes in your file, not your reply."

After agents return, the coordinator reads the report files, merges them into
`FINDINGS.md`, resolves duplicates, and commits.

### 5.3 Handoff protocol

`HANDOFF.md` is overwritten at the end of every session. It must be pasteable as a
standalone prompt with no other context. Template:

```markdown
Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full.
2. Read `system-review/STATE.md`.
3. Read `system-review/sessions/S##-<slug>.md` (the last session).
4. Then execute session S##+1 exactly as specified in `system-review/PLAN.md`.

Context you need that isn't obvious from those files:
- <carry-over facts, half-finished threads, traps discovered>

Do not re-do: <list>
Start with: <first concrete action>
```

### 5.4 Commit convention

```
review(S04): redundancy sweep — 17 findings, 4 agent reports
```

Scope is always `review`, plus the session number. Ledger-only changes.

---

## 6. Baseline: what is already established

These facts were verified against the working tree before this review began. Treat them
as **starting points to confirm**, not as gospel — re-check anything you depend on
heavily, and correct this section's claims in the ledger if they are wrong.

### 6.1 Repo state at kickoff

| Item | State |
|---|---|
| cinemate branch | `dev` @ `02b5a39` |
| cinemate working tree | **8 modified files, uncommitted** (settings-editor + recovery-console work) |
| cinepi-raw branch | `dev` @ `ea96f2d` |
| cinepi-raw vs origin | local `dev` is **1 commit ahead** of `origin/dev` |
| libcamera branch | `cinemate` @ `bcdd7e17b` (out of scope) |

**Session 01 must resolve the dirty cinemate tree with the operator before cutting
branches.** Do not stash, commit, or discard someone else's in-flight work unilaterally.

> ### ⚠ Git trap: LFS pointers in `docs/images/`
>
> Four files under `docs/images/` show as **modified** in the review worktree because
> they are Git-LFS pointers that were not smudged (130 bytes each, versus ~70 KB for the
> real image). They are *not* real edits.
>
> **Never run `git add -A` or `git commit -a` on this branch.** That would commit
> 130-byte pointer files over real images and silently corrupt the docs.
>
> Always stage explicitly and narrowly:
>
> ```
> git add system-review/
> ```
>
> Before every commit, run `git status --short` and confirm nothing outside
> `system-review/` is staged.

### 6.2 Size census (starting figures)

cinemate Python, largest modules:

| File | LOC |
|---|---|
| `src/module/cinepi_controller.py` | 2626 |
| `src/module/simple_gui.py` | 2129 |
| `src/module/redis_listener.py` | 2084 |
| `src/module/ssd_monitor.py` | 1323 |
| `src/main.py` | 1089 |
| `src/module/cinepi_multi.py` | 878 |
| `src/module/usb_monitor.py` | 877 |
| `src/module/sensor_detect.py` | 853 |
| `src/module/wifi_hotspot.py` | 753 |

cinepi-raw C++, largest sources:

| File | LOC |
|---|---|
| `cinepi/cinepi_sound.cpp` | 1804 |
| `cinepi/dng_encoder.cpp` | 1670 |
| `core/rpicam_app.cpp` | 1375 |
| `cinepi/cinepi_controller.cpp` | 894 |
| `encoder/libav_encoder.cpp` | 768 |
| `cinepi/cinepi_audio_capture.cpp` | 744 |
| `cinepi/cinepi_options.cpp` | 665 |
| `preview/drm_preview.cpp` | 656 |
| `cinepi/dualHdmiPreviewStage.cpp` | 638 |

Other: `cinemate-install.sh` 1916 LOC · `docs/installation-steps.md` 1061 LOC ·
`src/module/app/templates/settings_editor.html` 3706 LOC ·
`src/module/app/templates/template.html` 965 LOC · ~30 test files in `_test/`.

### 6.3 GUI surface inventory (verified, but incomplete — S07 must finish it)

| # | Surface | Port / path | Renderer | Source | LOC |
|---|---|---|---|---|---|
| 1 | HDMI on-camera monitor | `/dev/fb0` | **PIL raster → framebuffer** | `src/module/simple_gui.py` + `framebuffer.py` | 2129 + 194 |
| 2 | Web GUI | `:5000/` | HTML + adaptive CSS + Socket.IO | `app/main/routes.py` → `app/templates/template.html` | 965 |
| 3 | Settings editor | `:5000/settings-editor` | HTML, different visual language | `app/settings_editor.py` → `app/templates/settings_editor.html` | 3706 |
| 4 | Recovery console | `:8080` | stdlib-only HTTP + inline HTML | `services/cinemate-recovery/cinemate-recovery.py` | — |
| 5 | MJPEG preview (cam0/cam1) | `:8000` / `:8001` | raw video, consumed by #2 | cinepi-raw preview stage | — |
| 6 | Web API | `:5000/api/v1`, broadcast `:8888` | JSON, no rendering | `app/api.py`, `module/web_api_settings.py` | 225 |

Single Flask app: `Flask(__name__)` in `src/module/app/__init__.py`, served by
`socketio.run(..., port=5000)` at `src/main.py:935`.

### 6.4 Seed findings — carry these into `FINDINGS.md` as F-001..F-011 in Session 01

These were confirmed before kickoff. Verify each cheaply, then record it. If one is
wrong, say so in the ledger — that is a useful result too.

| ID | Sev | Conf | Finding | Evidence |
|---|---|---|---|---|
| F-001 | medium | probable | Four unreferenced HTML templates, ~928 LOC: `src/module/templates/index.html` (0 bytes), `template.html` (357), `template_old.html` (336), `src/module/app/template.html` (235). Grep finds no reference; the only Flask app resolves templates to `app/templates/`. Confirm the installer doesn't copy them. | `src/module/templates/`, `src/module/app/template.html` |
| F-002 | high | confirmed | `requirements.txt` lists `wave`, which is a **Python stdlib module, not a PyPI package**. Also duplicates `sugarpie` and `flask_socketio`, and lists both `Pillow` and `pillow`. Also mixes docs-build deps (`mkdocs-with-pdf`, `schemdraw`) into runtime deps. | `requirements.txt` |
| F-003 | high | confirmed | **`requirements.txt` is never referenced by the installer** — grep for "requirements" in `cinemate-install.sh` returns nothing. The installer pip-installs its own inline list. The two lists have diverged badly: **11 packages the installer installs are absent from `requirements.txt`** (`luma.oled`, `grove.py`, `pigpio-encoder`, `smbus2`, `rpi_hardware_pwm`, `watchdog`, `keyboard`, `sounddevice`, `evdev`, `inotify_simple`, `sysv_ipc`), and `flask`, `pyaudio`, `rpi-lgpio` appear only in `requirements.txt`. Notably **`flask` itself is never installed directly** — it arrives only as a transitive dep of `flask_socketio`. Also check whether `pyaudio` is still used at all, or was superseded by `sounddevice`. | `cinemate-install.sh:917-931`, `requirements.txt` |
| F-004 | low | confirmed | `docs/contributing.md` is **0 bytes**, and its mkdocs nav entry is commented out. Dead file plus a disabled nav line — decide whether to write it or delete both. | `docs/contributing.md`, `mkdocs.yml:62` |
| F-005 | high | confirmed | No Python lint/format/type config anywhere: no `pyproject.toml`, `ruff.toml`, `.flake8`, `setup.cfg`, `.editorconfig`, `.pre-commit-config.yaml`. cinepi-raw *does* have `.clang-format`. Standards are asymmetric between the repos. | repo root |
| F-006 | high | confirmed | CI contains only `docs.yml`. ~30 test files in `_test/` never run automatically. | `.github/workflows/` |
| F-007 | high | confirmed | Colour and typography constants are **duplicated by hand** between `simple_gui.py` (Python tuples) and `app/templates/template.html` (CSS custom properties), kept in sync only by a comment. This is the canonical example of the redundancy the GUI work should fix. | `simple_gui.py:21-45`, `app/templates/template.html:26-45` |
| F-008 | high | confirmed | `simple_gui.py` lays out with **absolute 1920-reference pixel constants** (`TOP_ROW_LEFT_X = 90`, `RES_RIGHT_ANCHOR = 1823`, `PREVIEW_PADDING_X = 94`, …). This is the core technical obstacle to "adaptive CSS everywhere". | `simple_gui.py:26-45` |
| F-009 | low | confirmed | `_test/` mixes pytest tests with non-test utilities (`analyze_logs.py`, `automount.py`, `i2c_scan_all.py`) and underscore-prefixed probable-dead files (`_gpio_output.py`, `__gpio_output.py`, `_mediator.py`, `_wifi_hotspot_service.py`). | `_test/` |
| F-010 | medium | confirmed | Nine Python modules and two C++ files exceed 850 LOC; five exceed 1300. See §6.2. Single-responsibility is likely violated in the largest. | §6.2 |
| F-011 | medium | confirmed | Branch hygiene: cinemate `dev` has 8 uncommitted modified files; cinepi-raw `dev` is 1 commit ahead of `origin/dev`. Must be resolved before cutting review branches. | git status |

---

## 7. The GUI harmonization question — framing

This is the single largest open decision in the review. It gets its own ADR
(`decisions/ADR-001-gui-harmonization.md`) and two dedicated sessions.

**The operator's hypothesis:** the three GUI renderings are all derived from
`simple_gui`'s static layout. Would it be better to generate all of them "the same way",
using an adaptive-CSS approach — including the HDMI GUI — so future changes are made
once, with per-surface differences limited to which controls are exposed (eject buttons,
file browser, etc.)?

**Do not treat this as settled in either direction.** The job is to establish the real
constraints and then recommend.

### The central tension

| Surface | Paradigm |
|---|---|
| HDMI GUI | **Immediate-mode raster.** PIL draws pixels at absolute coordinates into `/dev/fb0`, redrawn per refresh. |
| Web GUIs | **Retained-mode declarative layout.** The browser computes layout from CSS. |

These are not the same kind of thing. "Use adaptive CSS for the HDMI GUI too" implicitly
requires *something* to perform CSS layout on the Pi. That is the crux.

### Options to evaluate — all of them, with evidence

| Option | Sketch |
|---|---|
| **A. Status quo** | Keep three renderers, hand-sync. Baseline to measure against. |
| **B. Shared design tokens only** | One source of truth for colours, fonts, thresholds, labels; generate the Python constants and the CSS custom properties from it. Cheap. Kills F-007. Does not unify layout. |
| **C. Shared declarative spec, two backends** | One schema describes widgets, grouping, order, and per-surface visibility. A PIL backend renders it to the framebuffer; a CSS/HTML backend renders it in the browser. "Same way" = one spec, N renderers. |
| **D. Browser on the Pi drives HDMI** | Run a kiosk browser on the framebuffer/DRM. One renderer everywhere, literally. |
| **E. Server-side HTML→raster** | Render HTML to a bitmap on the Pi and blit it to the framebuffer. |

### Constraints each option must be tested against

Write the answer for every option; "unknown" is an acceptable answer if queued.

1. **DRM master is exclusive.** cinepi-raw composites the preview and owns the display
   (`preview/drm_preview.cpp`, `cinepi/dualHdmiPreviewStage.cpp`). Any option that
   introduces a second display client must explain how it coexists. This is likely fatal
   to D and E — but prove it from the source, don't assume it.
2. **The GUI overlays live video.** Establish exactly how the framebuffer overlay and
   the camera preview compose today. This determines whether an HTML layer is even
   expressible.
3. **RAM and CPU.** The dev unit is a 2 GB CM5 Lite that already trips a RAM auto-stop
   at UHD. A resident browser is a large fixed cost. Quantify from source/config where
   possible; queue the measurement.
4. **Refresh rate and latency.** The HDMI GUI is a camera instrument. Establish the
   current redraw cadence (see `docs/simple-gui-refresh-tuning.md` and the refresh logic
   in `simple_gui.py`) and what each option would do to it.
5. **Failure mode.** If the renderer dies mid-take, what does the operator see? The HDMI
   GUI is the last thing you want fragile. Rank the options on this explicitly.
6. **Boot time.** Camera-ready-to-shoot time is a real product requirement.
7. **Migration cost and reversibility.** How much of the 2129-line `simple_gui.py` must
   change, and can it be done incrementally behind a flag?

### Simulation you *can* run without a Pi

This is where "simulation and testing" is genuinely possible on a laptop. Build these in
`system-review/harness/`:

- **Offscreen HDMI GUI render.** `simple_gui.py` draws with PIL, which is pure Python.
  Stub the framebuffer and the Redis/controller inputs, drive it with a fixed synthetic
  state, and save the result as a PNG. This turns the HDMI GUI into something you can
  inspect, diff, and golden-test on a Mac. High value, and it outlives the review.
- **Web GUI render at matched viewport.** Serve `template.html` against the same
  synthetic state and capture it at 1920×1080.
- **Divergence diff.** Compare the two. Answer empirically: *how far apart are they
  today?* That number is the real argument for or against harmonization, and nobody has
  it yet.
- **State-field union.** Extract every field each surface displays and build the matrix
  of surface × field × source-of-truth. This is the input to option C's schema and is
  useful regardless of which option wins.

Note honestly in the ADR which harness pieces you actually got working and which you
only specified.

### Required ADR output

`decisions/ADR-001-gui-harmonization.md` must contain: context, the five options with
evidence against all seven constraints, a **recommendation with a stated confidence
level**, what would change the recommendation, a migration sketch with effort estimate,
and the Pi tests needed to confirm.

---

## 8. Session plan

One session per row. Do not merge rows. Update `PLAN.md` as reality diverges — and it
will; that is expected, not a failure.

### Phase 0 — Bootstrap

**S01 · Bootstrap & census**
- Resolve the dirty cinemate tree **with the operator** (§6.1). Do not decide alone.
- Cut `review/system-analysis` in both repos from `dev`. Push cinemate's.
- Create the full ledger layout (§4). Copy §5 into `CONVENTIONS.md`, §8 into `PLAN.md`.
- Record F-001..F-011 (§6.4) into `FINDINGS.md`, verifying each cheaply first.
- Deterministic census, no opinions: file inventory with LOC, module list, Python import
  graph, C++ include graph, test inventory, docs inventory, entry points, every
  network port bound, every Redis key referenced, every settings key referenced.
- → `deliverables/CENSUS.md`
- Mostly mechanical. Use subagents for the graphs. Keep this session cheap.

### Phase A — Understanding

**S02 · Architecture map — cinemate (Python)**
- Trace `src/main.py` boot: construction order, thread inventory and lifecycle, shutdown
  path, who owns which state, where Redis is written vs. read.
- Map the control surfaces (GPIO, rotary, serial, CLI, web API, keyboard) onto the
  dispatcher, and the dispatcher onto the controller.
- Name the seams — the places a change is *supposed* to be made.
- → `deliverables/CODE-MAP-cinemate.md`. Written for someone who has never seen the repo.

**S03 · Architecture map — cinepi-raw (C++)**
- Trace `cinepi/cinepi_raw.cpp` → manager/controller/state → capture loop →
  `dng_encoder` / `cinepi_sound` → preview stages → Redis bridge.
- Document the frame lifecycle end to end, and the metadata path (timing → DNG tags).
- Note where behavior depends on the forked libcamera without auditing libcamera.
- → `deliverables/CODE-MAP-cinepi-raw.md`

### Phase B — Critical analysis

**S04 · Redundancy & dead code sweep** *(agent fan-out, both repos)*
- Unreferenced files, unreachable code, dead branches, commented-out blocks.
- Duplicated logic: same computation in two places; constants duplicated across the
  Python/C++/CSS boundary; parallel implementations that drifted.
- Dead config keys, dead Redis keys, dead CLI commands, dead settings.
- Stale patch files, unused build targets, vestigial `codex/`-era leftovers.
- → `deliverables/REDUNDANCY-REPORT.md`

**S05 · Readability, comments & structure**
- Target reader: **competent but intermediate** Python/C developer, new to this code.
- Flag: functions >60 lines, nesting >3 deep, magic numbers, boolean-parameter APIs,
  unclear names, over-clever code, inconsistent abstraction level within a function.
- Comments specifically: stale or contradicted-by-code comments, comments that restate
  *what* instead of *why*, missing docstrings on public seams.
- **Equally important — comments that are load-bearing and must be preserved.** Several
  blocks in this codebase encode hard-won knowledge (why a constant is what it is, which
  hypotheses were falsified). Identify these; recommend promoting them into docs.
- → `deliverables/READABILITY-REPORT.md`

**S06 · Standards, consistency & tooling**
- Given F-005/F-006: propose a **minimal, low-friction** standard. One developer plus
  agents. Do not propose a twelve-tool pipeline that will be abandoned.
- Consistency audit: logging (levels, formatting, who logs what), error handling and
  bare `except`, thread start/stop patterns, Redis access patterns, settings access,
  hardcoded absolute paths, import style.
- Draft — do not apply — the config files: `pyproject.toml`/`ruff.toml`, `.editorconfig`,
  a test CI workflow, and a pre-commit config if warranted.
- Decide whether type hints are worth it here, and if so where. Argue both sides.
- → `deliverables/STANDARDS-PROPOSAL.md` + `deliverables/draft-config/`

### Phase C — GUI

**S07 · GUI surface inventory & state-model extraction**
- Complete the §6.3 table: every surface, every widget, every control, every field.
- Build the surface × field matrix with source-of-truth per field.
- Separate genuinely surface-specific affordances (eject, file browser, settings editing)
  from things that are duplicated by accident.
- Build the `harness/` render tooling described in §7.
- → `deliverables/GUI-INVENTORY.md`, `deliverables/GUI-STATE-MODEL.md`

**S08 · GUI harmonization evaluation → ADR-001**
- Execute §7 in full: five options against seven constraints, run the divergence diff.
- Split into S08a/S08b if the window runs out. Do not rush the recommendation.
- → `decisions/ADR-001-gui-harmonization.md`

### Phase D — Truth passes

**S09 · Docs vs. code**
- Every file in `docs/` against actual behavior. Prioritize the thinnest coverage of the
  biggest surfaces: `web-gui.md` is 32 lines for a 965-line GUI; `simple-gui.md` is 31
  lines for a 2129-line module.
- Check `settings-json.md` against `settings.schema.json` and against what the code
  actually reads; `redis-keys.md` against keys actually used; `cli-commands.md` against
  the real dispatcher; `changelog.md` against git history since the `cinemate-v3.1.1` tag.
- Check the mkdocs nav for links to missing or empty pages (see F-004).
- → `deliverables/DOCS-DRIFT-REPORT.md`

**S10 · Install script vs. install docs**
- `cinemate-install.sh` (1916 lines) against `docs/installation-steps.md` (1061 lines),
  step by step. Build the correspondence table; every divergence is a finding.
- Settle F-002/F-003: what actually installs the Python deps, and is `requirements.txt`
  live or decorative?
- Audit `services/` unit files and the Makefiles against what the docs claim is installed.
- Check the installer against the most recent feature work — anything landed on `dev` that
  the installer or the docs don't yet know about.
- Run `shellcheck` on the installer if available; record every warning class.
- Check idempotency and failure handling by reading: what happens on re-run, and on
  failure at each stage.
- → `deliverables/INSTALL-DRIFT-REPORT.md`

### Phase E — Synthesis

**S11 · CineMate style, philosophy & skill payload**
- `deliverables/CINEMATE-STYLE.md` — how code is written here. Naming, module shape,
  error handling, logging, threading, config, comments. Derived from the code, with
  citations, not from generic best practice.
- `deliverables/CINEMATE-PHILOSOPHY.md` — how problems get solved here. §9 has candidate
  principles; confirm, refute, or refine each **against code**, and add what you found.
- `deliverables/ENTRY-POINTS.md` — the "where do I go to change X" table. This is the
  highest-value artifact for future sessions. Every row: task → file → function → what
  else to update.
- `deliverables/SKILL-PAYLOAD.md` — the above, packaged to drop into the `cinemate-dev`
  skill's `references/` directory. Self-contained; assumes no repo access.

**S12 · Remediation plan**
- Triage every finding into PR-sized batches. Order by (risk reduction × comprehension
  gain) ÷ blast radius.
- Each batch: what changes, why, which findings it closes, how to verify on a Mac, what
  needs the Pi, and how to roll it back.
- Separate "safe now" (dead file deletion, tooling config, docs) from "needs Pi
  confirmation" from "blocked on ADR-001".
- Finalize `PI-VERIFICATION-QUEUE.md` as the Stage-2 work order.
- → `deliverables/REMEDIATION-PLAN.md`

---

## 9. Candidate system principles — confirm or refute against code

These are **hypotheses** drawn from the codebase's own comments and structure. S11 must
test each one against actual code and cite evidence. Some will be wrong. Delete those.

1. **Redis is the single source of live state.** Every surface is a view onto it; state
   is not held privately by UI layers.
2. **The Pi is the runtime truth.** Static reasoning proposes; hardware disposes. No
   behavioral claim is final until measured on the device.
3. **Fail visible, never silent.** A failure the operator can't see during a take is
   worse than a crash. Errors surface on the GUI, not only in a log.
4. **Hardware facts live in data, not code.** Sensor modes, packing, and capabilities
   belong in data files that both repos read.
5. **One process owns the display.** Display ownership is exclusive and deliberate.
6. **Comments record the *why*, including dead ends.** Falsified hypotheses are
   documented so they aren't re-investigated. Preserve this.
7. **The camera must survive its own software.** Degraded operation beats no operation —
   hence the recovery console and the standby-storage promotion.
8. **Config is declarative and user-editable.** `settings.jsonc` and `config.txt` are
   the contract with the operator, and comments in them are part of the product.

Add principles you discover. For each, note where the codebase **violates** it — those
violations are findings.

---

## 10. Anti-patterns for this review

Things that will waste the operator's plan window:

- Reading a 2000-line file into context when `grep -n` would answer the question.
- Letting a subagent return its full report instead of writing it to a file.
- Deferring ledger writes to the end of a session.
- Producing a finding without `path:line`.
- Recommending a refactor without stating its blast radius and rollback.
- Asserting runtime behavior as fact with no Pi.
- Starting a second plan entry because the first finished early.
- Rewriting `KICKOFF.md`. It is immutable; corrections go in `STATE.md`.
- Generic advice that would apply to any Python project. Everything must be specific to
  this codebase, with citations.

---

## 11. Session 01 — start here

1. Read this file in full. (Done, if you're here.)
2. Confirm both repos are present and report their branch + status.
3. **Ask the operator how to handle the 8 uncommitted cinemate files** before touching git.
4. Cut `review/system-analysis` in both repos from `dev`.
5. Create the ledger layout from §4; write `CONVENTIONS.md` (§5) and `PLAN.md` (§8).
6. Verify and record F-001..F-011 in `FINDINGS.md`.
7. Run the census (S01 scope above) → `deliverables/CENSUS.md`.
8. Write `sessions/S01-bootstrap.md` and `STATE.md`.
9. Write `HANDOFF.md` for S02.
10. Commit and push to `origin review/system-analysis`.
