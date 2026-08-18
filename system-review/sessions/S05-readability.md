# S05 — Readability, comments & structure (+ agent 2's owed S04 scope)

**Date:** 2026-08-18 · **Phase:** B
**Outcome:** delivered. S04's owed scope partially recovered.
**Deliverable:** `deliverables/READABILITY-REPORT.md`
**Yield:** 7 findings (F-128..F-134) + 16 recovered from agent 2 (F-150..F-165). Ledger: 99.

---

## 1. S04's owed scope — agent 2 failed again, but not for nothing

Launched agent 2 first per the handoff. It died on an account usage limit for the
**second** time (reset 14:10 UTC). But attempt 2 of S04 had added an instruction —
*write your report file incrementally, do not batch to the end* — and it worked: **16
findings survived** (F-150..F-165), checkpointed by an auto-commit.

That instruction has now paid for itself twice. It should be treated as mandatory in
`CONVENTIONS.md` §5.2, not advice.

### What survived is a second duplication cluster — around storage, and worse than the GUI one

| Finding | What |
|---|---|
| **F-160** (high) | **Two processes independently mount, fsck and unmount `/media/RAW`** — the recording target — with no lock or ownership protocol |
| **F-156** (high) | The filesystem→mount-options table is duplicated across those two processes and **the copies disagree** |
| **F-155** (high) | `YANK_ERRNOS` defined byte-identically in both, no shared module |
| **F-161** (high) | `services/cinemate-services.Makefile` recurses into three **deleted** directories |
| **F-165** | Root `CMakeLists.txt` references a directory that does not exist — `cmake .` fails immediately |

**F-164 is the finding that makes the cluster tractable.** The intended coupling between
`storage-automount` and the app is a dead `journalctl -fu storage-automount` tail
(`ssd_monitor.py:139-144`), so the app re-implements mount detection by polling instead.

So F-155..F-160 are **not six independent copy-pastes — they are the symptom of one
severed link.** Fixing the coupling collapses five findings at once. That is a materially
different remediation from "de-duplicate six things", and it is exactly the kind of insight
a scoped agent produces that a broad sweep does not.

Drifted-duplication count rises 9 → 10 (F-156 joins).

**Still uncovered:** settings-key liveness, installer idempotency, `shellcheck`, and two
thirds of the `wifi_hotspot` triangle. F-166..F-199 remain free.

---

## 2. S05 proper — measured, not estimated

All figures from AST analysis over `src/` (43 files, ~19,800 LOC), not eyeballing.

| Metric | Result |
|---|---|
| Functions > 60 lines | **43** (8 over 250) |
| Longest | `run_application` 405, `analyze_frames` 401, `populate_values` 369 |
| Nesting depth ≥ 5 | 86 sites / 20 functions; **max depth 11** |
| `except` handlers | **337** — one per 59 lines |
| …silently swallowing | **15** (bare `pass`/`continue`/`break`) |
| Bare `except:` | 2 |
| Docstrings on public defs | **27%** (152/543); **40 public classes have none** |
| TODO/FIXME/XXX/HACK | **0** |

### The finding that matters most is not a defect

KICKOFF §8 S05 asks specifically for load-bearing comments, and they turned out to be the
most valuable prose in the repo (F-133). **The best comment in the codebase** is the
AUDIO-CORE INVARIANT at `storage_profiles.py:41-49` — it states a cross-repo constraint,
names the consequence (*the WAV loses sync*), names the backstop **and** warns against
relying on it, and names its own guarding test.

**That test is one of the 27 that never run.** The invariant preventing lost audio sync is
guarded by a test nobody executes. That is now the sharpest single argument in the review
for fixing CI before anything else, and it reordered the report's recommendations.

Two more must survive any cleanup: `ssd_monitor.py:1122-1125` records a **falsified
experiment** (1 MB exFAT clusters break the macOS driver — deleting the comment invites
redoing it), and `sensor_detect.py:745-752` records a superseded hypothesis with its
reasoning.

### A positive finding, recorded as such

**Zero TODO/FIXME/XXX/HACK markers** in ~19,800 LOC (F-134). Unusual discipline, and worth
stating in a review that is otherwise a list of problems.

### The inversion worth naming

This codebase explains **decisions** well (47 why-comments) and **interfaces** poorly (27%
docstrings, `CinePiController` undocumented). For the intermediate reader the kickoff names
as the target, that is the wrong way round — they need the interface first.

---

## 3. Recommendation ordering — deliberate

The report sequences remediation CI → silent handlers → promote comments → class
docstrings → *then* split large functions. Items 1–4 are additive or observational and
cannot break a take. Item 5 touches the boot path and the Redis read path, and should not
happen before something exists that can tell you you broke it.

---

## 4. Judgement calls

- **Ran agent 2 first, as the handoff instructed**, rather than starting S05 clean. It
  half-failed, but half of a scoped agent beat none.
- **Did the S05 measurement inline** rather than delegating — it is deterministic AST work
  where an agent adds latency and a re-verification burden without adding accuracy.
- **Recorded F-133 and F-134 with no severity.** Neither is a defect; the schema's severity
  column is about consequence of a problem, and forcing one would misrepresent them. They
  carry `—` and are flagged PRESERVE / positive respectively.

## 5. Not covered

`cinepi_controller.py` internals (2626 LOC, still untraced since S02 — PI-007 step 1 also
wants it) · C++ readability (`cinepi_sound.cpp` 1804, `dng_encoder.cpp` 1521) ·
HTML/JS readability (`settings_editor.html` 3706, assessed only for duplication).
