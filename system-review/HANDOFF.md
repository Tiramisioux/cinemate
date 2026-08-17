Continue the CineMate system review.

1. Read `system-review/KICKOFF.md` in full.
2. Read `system-review/STATE.md` — **especially the Deviations section (D1–D5)**, which
   corrects several assumptions KICKOFF makes about this environment.
3. Read `system-review/sessions/S01-bootstrap.md`.
4. Then execute **S02 — Architecture map, cinemate (Python)** exactly as specified in
   `system-review/PLAN.md`.

---

## Context you need that isn't obvious from those files

**Your branch is `claude/cinemate-system-review-kickoff-cilicc`, not
`review/system-analysis`.** The harness mandates it. Don't create the other one.

**cinepi-raw is not checked out beside you.** If S02 needs it (it mostly shouldn't —
S02 is the Python side), clone it read-only:
```
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/Tiramisioux/cinepi-raw /workspace/tiramisioux/cinepi-raw
```
It lands on `main`, not `dev`, shallow, no history, and you cannot push to it.

**S02 inherits one unfinished job from S01: the Redis key census.** S01's approach —
grepping call sites for string literals — found 13 keys where the docs list 69. Keys are
passed as variables, built dynamically (`tc_cam0`, `log_encode_cam0`, `last_dng_cam0` are
plainly `f"{base}_cam{n}"`), or reached through `RedisController` wrapper methods. The
method that will work is written up in `deliverables/CENSUS.md` §7: read
`src/module/redis_controller.py` (411 LOC) in full to learn the access API first, then
trace its callers, with `redis_listener.py` (2084 LOC) as the read side. **Do this first
in S02** — S09's docs-drift pass is blocked on it.

**Budget warning for S02.** The three files at the centre of this session are large:
`cinepi_controller.py` (2626), `redis_listener.py` (2084), `main.py` (1089). Do not read
them whole. Use `grep -n` for structure (`^class `, `^\s*def `, `threading.Thread`,
`\.start()`, `redis`), then `sed -n 'A,Bp'` on the regions that matter. KICKOFF §2.5 and
§10 are explicit about this and S01 stayed well inside budget by following it.

**Agent fan-out:** S01 used none, deliberately (the work was one shell loop). S04 is the
session designed for fan-out. For S02, judge it on the merits — tracing a boot sequence is
inherently serial, so agents may not help. If you do fan out, reserve IDs from the free
blocks in `CONVENTIONS.md` §5.1 and follow the six mandatory prompt clauses in §5.2.

**Two structural facts from S01 that shape S02's map:**
- `main.py` imports 27 modules directly with no composition layer — the boot sequence
  *is* `main.py`, there is no builder to read instead.
- `redis_controller` has the widest fan-in in the repo (10 importers). Whoever owns state
  ownership questions, that module is the centre of the answer.

---

## Do not re-do

- Verifying F-001..F-013 — all checked against source in S01, with detail files for
  F-003, F-011, F-013.
- The requirements.txt / installer dependency divergence — fully computed in
  `findings/F-003.md`.
- Counting docs or auditing the mkdocs nav — `CENSUS.md` §9 is complete and correct.
- The file/LOC census, import graph, port list, or entry-point list — `CENSUS.md` §1–6.
- Looking for uncommitted working-tree changes or LFS pointer corruption — neither exists
  here (STATE.md D3, D4).

## Start with

`grep -n "^class \|^\s*def \|threading.Thread\|\.start()\|\.join()" src/main.py` — get the
skeleton of the boot sequence and the thread inventory before reading any of it in prose.

## Finish with

Update `STATE.md`, append `sessions/S02-*.md`, overwrite this file for S03, then
`git add system-review/` (narrow — never `-A`), commit as
`review(S02): cinemate architecture map — <n> findings`, and push.
