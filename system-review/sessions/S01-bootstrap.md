# S01 — Bootstrap & census

**Date:** 2026-08-17
**Phase:** 0 — Bootstrap
**Outcome:** complete. Ledger established, 13 findings recorded, census delivered.

---

## What happened, in order

1. Read `KICKOFF.md` in full.
2. Checked repo state — **found three material deviations from KICKOFF's assumptions**
   (see below). None blocked the session.
3. Attached and cloned `cinepi-raw` (read-only).
4. Verified F-001..F-011 individually against source before recording any of them.
5. Built the ledger layout, `CONVENTIONS.md`, `PLAN.md`.
6. Ran the census → `deliverables/CENSUS.md`.
7. Opened `PI-VERIFICATION-QUEUE.md` with 5 entries.
8. Wrote `STATE.md`, this log, `HANDOFF.md`. Committed and pushed.

---

## Deviations from KICKOFF — the important part of this session

### D1. Branch name

KICKOFF §3 mandates `review/system-analysis` in both repos. **The session harness
mandates `claude/cinemate-system-review-kickoff-cilicc`** and explicitly forbids pushing
elsewhere without permission.

**Resolution:** used the harness-designated branch. It is cut from `origin/dev` @
`02b5a39`, which is what KICKOFF actually cares about. The ledger is identical either way;
only the ref name differs.

**Operator action, if desired:** rename or re-cut to `review/system-analysis` at any point.
The ledger is a directory of files — it moves branches without friction.

### D2. cinepi-raw is not a sibling checkout

KICKOFF §3 assumes `cinemate/` and `cinepi-raw/` side by side, both on `dev`, and asks
S01 to cut `review/system-analysis` in both.

**Reality:** this container held only `cinemate`. `cinepi-raw` was fetched during this
session as a **shallow, read-only, anonymous clone** at
`/workspace/tiramisioux/cinepi-raw`, on branch **`main` @ `774402c`** (a merge of `dev`
via PR #58).

Consequences that later sessions must respect:

- **No branch was cut in cinepi-raw.** This session cannot push there. Stage-2 work needs
  an attached checkout (`add_repo` with `access: "push"`).
- **The C++ figures in `CENSUS.md` §2 are for `main`, not `dev`.** Several differ
  materially from KICKOFF §6.2 — `dng_encoder.cpp` is 1521 here vs 1670 there,
  `cinepi_controller.cpp` 743 vs 894, `drm_preview.cpp` 542 vs 656. Do not treat KICKOFF
  §6.2 and CENSUS §2 as describing the same tree.
- **Shallow clone = no history.** `git log`, blame, and `-S` searches are unavailable.
  PI-003 (the patch files) is blocked on a full checkout.
- `libcamera/` and `imx585-v4l2-driver/` are **not present at all**. Already out of scope.

### D3. The dirty working tree does not exist — F-011 refuted

KICKOFF §6.1/§6.4 describes 8 uncommitted cinemate files, and §11 step 3 instructs S01 to
**ask the operator** before touching git.

**There was nothing to ask.** `git status --short` is empty; `origin/dev == 02b5a39 ==`
the branch base. The settings-editor work KICKOFF called "in-flight" is present as
commits (`8932ae2`, `48d2f84`, `02b5a39`). The container clones fresh from the remote, so
local uncommitted state cannot appear here by construction.

Recorded as `findings/F-011.md` with confidence `refuted` rather than deleted, so no
future session goes looking for phantom edits.

### D4. The LFS trap did not reproduce

KICKOFF §6.1 warns that four `docs/images/` files appear modified as unsmudged 130-byte
LFS pointers, and that `git add -A` would corrupt the docs.

**Not observed.** `docs/images/*.png` are real files (53–75 KB) and the tree is clean.
`.gitattributes` does route `*.png`/`*.jpg`/`*.ipynb` through LFS, so the trap is real in
principle. **Narrow staging was used anyway** (`git add system-review/`) — zero cost,
and the downside of being wrong is corrupted docs images.

---

## Findings recorded

F-001..F-011 from KICKOFF §6.4, each verified before recording, plus two found
incidentally while verifying the others.

| ID | Verdict on the KICKOFF claim |
|---|---|
| F-001 | **Confirmed and upgraded** to `confirmed` (was `probable`). 928 LOC across 4 files, zero code references, installer does not copy them. `index.html` is 0 lines / 15 bytes. |
| F-002 | Confirmed exactly as written. |
| F-003 | Confirmed exactly, including the "11 packages" count. Detail file written. |
| F-004 | **Confirmed and substantially widened** — see below. |
| F-005 | Confirmed. |
| F-006 | Confirmed; count refined to 27 pytest files (of 34 total in `_test/`). |
| F-007 | Confirmed, with stronger evidence than KICKOFF claimed. |
| F-008 | Confirmed, **with a nuance** — see below. |
| F-009 | Confirmed exactly. |
| F-010 | Confirmed; extended to 4 C++ files ≥850 LOC once `lj92.c` is counted. |
| F-011 | **Refuted.** See D3. |
| F-012 | New. `cinepi/_mjpegPreviewStage.cpp` (240 LOC) is dead. |
| F-013 | New. `src/stream.py` is a dead, unimportable second Flask entry point. |

### F-004 turned out to be much bigger than "one empty file"

KICKOFF described a single 0-byte `contributing.md` with a commented-out nav line. The
real shape: **50 docs, only 35 in the mkdocs nav, 15 unreachable, five 0-byte files, two
1-line stubs, six commented-out nav lines.** The notable casualty is
`docs/image-circle.md` — 159 lines of real documentation, hidden at `mkdocs.yml:23`
"until manually reviewed". Severity raised low → medium.

### F-008 nuance worth carrying to S08

`simple_gui.py` does use 1920-reference absolute constants, but it is **not** pure fixed
layout — `simple_gui.py:1657-1658` applies a `shrink_x` factor:

```
left  = TOP_ROW_LEFT_X   * shrink_x
right = RES_RIGHT_ANCHOR * shrink_x
```

So the design is *proportionally scaled from a 1920 reference*, not pixel-frozen. This
softens the "core technical obstacle" framing in KICKOFF §6.4 slightly: the obstacle is
the absence of *reflow* (content-driven layout), not the absence of scaling. S08 should
argue against the accurate version.

### F-007's evidence is stronger than KICKOFF suggested

The duplication is not merely parallel — `template.html`'s CSS custom properties carry
comments that **name the Python constants they mirror**:

```
--drop: rgb(120, 40, 180);   /* DROP_WARNING_COLOR   */
--sync: rgb(255, 0, 255);    /* SYNC_WARNING_COLOR   */
--label: rgb(136, 136, 136); /* simple_gui label grey */
```

This is the cleanest possible argument for ADR-001 option B (shared design tokens): the
codebase has already written down the mapping by hand, it just isn't machine-checked.

---

## Census — what got done and what didn't

Delivered in `deliverables/CENSUS.md`: file inventory, LOC census for both repos, module
lists, **Python internal import graph**, entry points, network ports, settings sections,
docs inventory, test inventory, cinepi-raw build/patch notes.

**One census item failed its method: the Redis key census.** Grepping call sites for
string literals found only 13 keys; `docs/redis-keys.md` documents 69. Keys are evidently
passed as variables, built dynamically (`tc_cam0`, `log_encode_cam0` are clearly
`f"{base}_cam{n}"`), or accessed via `RedisController` wrapper methods. **The correct
method is recorded in CENSUS.md §7 and the task is handed to S02.** The failed approach is
written down so it is not repeated.

`CENSUS.md` §12 lists everything else S01 deliberately did not establish.

---

## Judgement calls made

- **No subagents.** KICKOFF §8 S01 says "use subagents for the graphs", but also "keep
  this session cheap" (§2.5). The import graph was one shell loop; spawning agents for it
  would have cost more context than it saved. Agent fan-out is deferred to S04, where the
  work genuinely parallelises. Noted here so S04 doesn't assume a precedent either way.
- **Recorded F-012 and F-013 rather than deferring to S04.** Both were confirmed with
  full evidence while verifying other findings. Holding a confirmed finding out of the
  ledger to preserve session-scope purity would violate §2.3 ("a finding that exists only
  in your context does not exist").
- **Corrected my own census mid-session.** A truncated `head -30` produced a wrong docs
  count (30) and a wrong claim that `simple-gui.md` was absent. Both were caught and
  fixed before commit; the correction is noted inline in CENSUS.md §9 so the error is not
  silently rewritten out of history.

---

## Context budget

Comfortable. Finished well inside the window with no work abandoned mid-flight.
