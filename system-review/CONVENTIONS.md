# CONVENTIONS

Copied from `KICKOFF.md` §5. This is the operative rule set for every session.

---

## 5.1 Finding schema

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

### Severity — about consequence, not effort

| Severity | Means |
|---|---|
| critical | Can lose footage, corrupt data, or brick a shoot |
| high | Wrong behavior, or a maintenance trap that will cause a bug soon |
| medium | Real cost to comprehension or maintenance |
| low | Worth fixing when nearby |
| nit | Cosmetic |

### Confidence — mandatory, exactly three values

| Value | Meaning |
|---|---|
| `confirmed` | Directly observed in source you read. Cite the lines. |
| `probable` | Consistent with observed evidence, one inferential step away. Say what the step is. |
| `unverified` | Needs something you don't have (usually the Pi). Must have a queue entry. |

Downgrade aggressively. A wrong `confirmed` poisons every later session that trusts the
ledger.

IDs are global, sequential, never reused. Reserve a block before fanning out agents
(e.g. "agent 1 uses F-100..F-149") so parallel agents never collide.

**ID blocks allocated so far:**

| Block | Owner | Status |
|---|---|---|
| F-001..F-011 | S01 — seed findings from KICKOFF §6.4 | used |
| F-012..F-013 | S01 — incidental confirmed findings | used |
| F-014..F-099 | reserved for S02/S03 architecture sessions | free |
| F-100..F-149 | S04 agent 1 | free |
| F-150..F-199 | S04 agent 2 | free |
| F-200..F-249 | S04 agent 3 | free |
| F-250..F-299 | S04 agent 4 | free |

---

## 5.2 Subagent rules

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

Max 4 concurrent subagents.

---

## 5.3 Handoff protocol

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

---

## 5.4 Commit convention

```
review(S04): redundancy sweep — 17 findings, 4 agent reports
```

Scope is always `review`, plus the session number. Ledger-only changes.

---

## 5.5 Git safety (environment-specific — see STATE.md §Deviations)

- **Stage narrowly, always:** `git add system-review/` — never `git add -A`, never `git commit -a`.
- Before every commit run `git status --short` and confirm nothing outside
  `system-review/` is staged.
- The ledger branch in this environment is **`claude/cinemate-system-review-kickoff-cilicc`**,
  not `review/system-analysis`. See STATE.md → Deviations D1.
- Never commit or push to `dev`.
- Push every session: `git push -u origin claude/cinemate-system-review-kickoff-cilicc`.

### On the KICKOFF §6.1 LFS trap

KICKOFF warns that four `docs/images/` files appear modified as unsmudged 130-byte LFS
pointers. **This did not reproduce in the S01 environment** — `docs/images/*.png` are
real files (53–75 KB) and the working tree is clean. `.gitattributes` does route
`*.png`, `*.jpg`, `*.ipynb` through LFS, so the trap remains plausible in other
checkouts. Keep staging narrowly regardless; the cost is zero and the downside of
getting it wrong is corrupted docs images.
