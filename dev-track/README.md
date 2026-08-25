# dev-track — the CineMate feature plan

Branch: `feature/dev-track`, cut from `dev` 2026-08-25 on operator instruction.

This directory is the **feature plan** for CineMate development, plus the per-feature
planning material and process ledgers. It is deliberately separate from the system-review
project: `system-review/` owns remediation of review findings; this track owns **features**.
(The first feature was briefly filed in the review ledger as batch B14 — that placement was
reversed by the operator the same day; see "Numbering and provenance" below.)

## The plan

One step per feature. **Features are being added one at a time; the order below is
provisional — the plan and its ordering get reviewed (operator + Fable thread) before the
execution sequence is fixed.** Nothing here implies C0 runs before C1 until that review has
happened.

| Step | Feature | State | Materials | Implementation branch |
|---|---|---|---|---|
| C0 | Format drive from the settings editor's RAW pane | Planned, not implemented | `C0-format-drive/PLAN.md` (ledger entry) + `FORMAT-DRIVE-PLAN.md` (full spec) + `SONNET-PROMPT.md` (kickoff prompt) | `feature/raw-pane-format-drive` off `dev` (to be cut) |
| C1 | Long-take stability — eliminate dropped frames, keep audio in sync at the higher 12-bit modes | Runbook ready, campaign not started | `C1-longtake-stability/RUNBOOK.md` (Sonnet session prompt + protocol) + `RESULTS.md` (campaign ledger) | none — measurement campaign on the Pi's `dev` checkouts |

Next free step: **C2**.

## Adding a feature

- One directory per step: `dev-track/C<n>-<short-name>/`, plus one row in the table above.
- A step's directory holds its durable planning artifacts (plan/spec/runbook/ledger). Scratch
  work — mockups, throwaway analysis — still goes to the external workspace
  `Documents/cinemate/development/<name>/`, per the workspace convention.
- Feature *implementation* happens on the step's own branch off `dev` (named in the table),
  not on this branch — `feature/dev-track` is planning and bookkeeping.

## Conventions on this branch

- Process ledgers (like C1's `RESULTS.md`) are updated and committed **on this branch** as
  the work runs; commit messages `c<n>: <scope> — <one-line outcome>`.
- **Never `git add -A` in this repo** (LFS pointer trap) — add named files only.
- Do not push without operator approval.

## Numbering and provenance

The C-series is this track's own numbering and lives only here. The B-series belongs to the
system-review ledger (`system-review/deliverables/REMEDIATION-PLAN.md` on
`claude/cinemate-system-review-kickoff-cilicc`) and stays review-only.

- **C0** was first committed to the review ledger as batch **B14** (commit `84bcb98b`,
  2026-08-25): a `REMEDIATION-PLAN.md` §3 section plus `deliverables/FORMAT-DRIVE-PLAN.md`.
  The copies here are the live ones; the review-branch copies remain until a review-branch
  session prunes them — this directory supersedes them.
- **C1** was drafted as B15 the same day and moved here before it was ever committed to the
  review ledger; no stale copy exists.
