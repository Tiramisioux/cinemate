# S12 — Remediation plan

**Plan entry:** S12, **run out of order** on operator request (ahead of S11b)
**Findings:** 0 — this session spends the ledger rather than adding to it
**Pi used:** no · **Deliverable:** `deliverables/REMEDIATION-PLAN.md` (450 lines)

---

## What was asked

The operator asked what the next steps are, and proposed: separate threads for cinepi-raw,
cinemate and docs; fixes applied one at a time under supervision with the Pi connected; and
findings grouped into logical commits.

Two thirds of that is right and is what S12 was already scoped to produce. **The one-thread-
per-repo split is not**, and the finding distribution says so plainly.

## Why the per-repo split was rejected

| repo | findings |
|---|---|
| cinemate | 128 |
| install | 19 |
| **both (cross-repo)** | **17** |
| docs | 14 |
| **cinepi-raw** | **8** |

A cinepi-raw thread would have eight items, six of which are cross-repo anyway. And the 17
"both" findings — the Redis key contract, the timecode divergence, the unpinned pairing —
have no single home: a per-repo split puts them in no thread or in two, **reproducing exactly
the coordination failure the review spent eleven sessions documenting.**

The batches split by **risk and verifiability** instead, which is also how they can be
supervised: a batch is a thread, and a thread is a sitting.

## The eight batches

| # | batch | Pi | risk | closes | commits |
|---|---|---|---|---|---|
| **B3** | Small correctness fixes | verify only | low | 10 | 7 |
| B1 | Docs | no | none | 8 | 5 |
| B2 | Delete dead code (~3,250 LOC) | no | low | 30 | 5 |
| B4 | The checks (CI + 4 harness scripts) | no | low | 6 | 6 |
| B5 | Pi verification session | **yes** | none | settles ~10 | 0 |
| B6 | Dependencies & pinning | on merge | medium | 9 | 3 |
| B7 | ADR-001 steps 1–3 | verify | medium | 6 | 4 |
| B8 | Structural — deferred with reasons | mixed | high | — | — |

**B3 goes first**, even though it is the only desk batch wanting hardware to confirm. F-204
and F-271 are the two worst defects found, they are about ten lines each, and in both cases
**the correct implementation already exists a few hundred lines away in the same
repository.** Nothing is learned by deferring them.

B1, B2 and B4 can run in any order and in parallel; none can break a camera.

## §6 — the handoff prompts

Six self-contained prompts, ready to paste, one per supervised thread. Each carries the
finding list, the specific trap for that batch, the verification command, and the git-safety
rules — so a session starts cold without the operator re-explaining eleven sessions of
context.

The traps are the part worth having written down. B4's prompt leads with the `docs.yml`
publishing hazard (two steps push gh-pages unconditionally; widening the trigger without
guarding them makes every PR publish). B2's leads with the two rules that keep a deletion
batch from doing damage: use F-122's corrected reachability result rather than S01's buggy
import graph, and never let a "remove commented code" tool near F-133's 47 load-bearing
why-comments.

## §4 — what must survive

24 of the 186 findings are strengths, and several could plausibly be damaged by a batch that
is otherwise correct. They are listed with the batch that threatens each: F-133's comments
(B2), the recovery console's isolation (B6), the installer's designed idempotency (B6.2), the
accurate docs (B1), and the two boundaries that have *not* drifted (F-206, F-210 — both
examples to copy rather than things to change).

## Deviation recorded

S12 ran **before S11b**, which is out of plan order. `PLAN.md` and `STATE.md` both say so.
The reason: S11b's three documents (style guide, entry-points map, skill payload) are
reference material for future work, while S12 is what unblocks the operator now. The cost is
that B2 and B7's blast-radius notes are compact rather than derived from a finished
`ENTRY-POINTS.md`; each batch carries its own instead.

**The analysis phase is closed.** S11b adds reference material, not findings.

## Left undone

- **S11b** — `CINEMATE-STYLE.md`, `ENTRY-POINTS.md`, `SKILL-PAYLOAD.md`.
- **`dng_encoder.cpp` on `dev` (687 lines changed)** — the largest cinepi-raw hole, from
  S07b. It does not block any batch: B2.3's cinepi-raw deletions are in files the rewrite
  did not touch.
- **The `wifi_hotspot` triangle** — two thirds unreached since S04.
- **The 1471 lines of JavaScript in `settings_editor.html`** were scanned, not read. B3.5
  touches that file, so that thread should read the region it edits.
