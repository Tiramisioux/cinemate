Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full.
2. Read `system-review/STATE.md` — **especially Deviations D1–D5**, which correct several
   assumptions KICKOFF makes about this environment.
3. Read `system-review/sessions/S02-code-map-cinemate.md`.
4. Then execute **S03 — Architecture map, cinepi-raw (C++)** as specified in
   `system-review/PLAN.md`.

---

## Context you need that isn't obvious from those files

**Your branch is `claude/cinemate-system-review-kickoff-cilicc`**, not
`review/system-analysis`. PR #129 (draft) tracks it. Ledger-only commits; never stage
outside `system-review/`.

**cinepi-raw is not checked out.** Clone it read-only first — this is S03's entire subject:
```
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/Tiramisioux/cinepi-raw /workspace/tiramisioux/cinepi-raw
```
It lands on **`main` @ 774402c, not `dev`**, shallow, no history, and you cannot push to
it. Say so in the deliverable — the LOC figures in KICKOFF §6.2 describe `dev` and do not
match. `CENSUS.md` §2 has the `main` figures.

**S03's highest-value output is the cross-repo Redis key diff.** S02 established that
cinemate's registry is `ParameterKey` (`redis_controller.py:18`, 84 members) and found
that `audio_vu` is declared *independently on both sides* with the same constant name
(F-016: `cinepi_sound.cpp:22` ↔ `simple_gui.py:21`). Nobody knows how many more keys do
this. Enumerate every Redis key cinepi-raw touches and diff it against those 84. That
diff is the input ADR-001 needs and it does not exist yet.

**F-016 reframes ADR-001 and S03 should reinforce or refute that.** The GUI question is
usually posed as PIL-raster vs. browser-CSS — two surfaces. F-016 shows the state contract
spans three languages, with C++ as a first-class writer. If the key diff turns up more
cross-repo duplication, options B and C in KICKOFF §7 get materially harder and S08 needs
to know before it starts.

**Build-graph loose end from S01, still open:** `cinepi_audio_capture.cpp` (744 LOC) and
`lj92.c` (1218 LOC) are **not** in `cinepi/meson.build`'s 10-file source list
(`meson.build:24-34`). Find out how they enter the build, or whether they don't.

**Budget.** `cinepi_sound.cpp` is 1804 LOC and `dng_encoder.cpp` 1521. Do not read them
whole. Use `grep -n` for structure (`^[A-Za-z_].*::`, `^class`, `^struct`, `#include`),
then `sed -n 'A,Bp'` on regions that matter.

**Citation discipline — a trap S02 hit twice.** Cite line numbers from `grep -n` output,
never from arithmetic on a `sed -n 'A,Bp'` window; S02 put several citations off by one
that way and had to correct them. Also avoid `\x27` in single-quoted grep patterns — it is
a literal backslash there, and it silently dropped five enum members before the error was
caught. Prefer a short Python parse over a clever regex when extracting structured lists.

---

## Do not re-do

- The Redis key census for **cinemate** — done, `ParameterKey` at `redis_controller.py:18`.
  `CENSUS.md` §7 is superseded by S02. (cinepi-raw's side is still needed — that's S03.)
- `main.py` boot order, the thread table, or the shutdown path — `CODE-MAP-cinemate.md`
  §3–4, citations verified against source.
- The control-surface → dispatcher → controller mapping — `CODE-MAP-cinemate.md` §5.
- Verifying F-001..F-026 — all checked; detail files exist for F-003, F-006, F-011, F-013, F-016.
- Counting docs or auditing the mkdocs nav — `CENSUS.md` §9.

## Two desk tasks that are cheap and unblock later sessions

Neither is S03's job, but if S03 finishes early, either is worth more than starting S04:

- **PI-007 step 1:** read `cinepi_controller.py` (2626 LOC) for internal locking. It
  decides whether F-025 (unserialised hardware control path) is a real race or a style
  issue, and it needs no hardware.
- `redis_listener.py` (2084 LOC) internals — the entire Redis read side, still untraced.

## Start with

Clone cinepi-raw (above), then
`grep -n "^[A-Za-z_].*::\|^class \|^struct \|^int main" cinepi/cinepi_raw.cpp cinepi/cinepi_manager.cpp cinepi/cinepi_state.cpp`
to get the skeleton before reading any of it in prose.

## Finish with

Update `STATE.md`, write `sessions/S03-*.md`, overwrite this file for S04, then
`git add system-review/` (narrow), commit as `review(S03): ...`, and push.
