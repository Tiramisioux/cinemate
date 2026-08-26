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
| C1 | Long-take stability — eliminate dropped frames, keep audio in sync at the higher 12-bit modes | Runbook **verified 2026-08-26** (blockers fixed), campaign not started | `C1-longtake-stability/RUNBOOK.md` (Sonnet session prompt + protocol) + `RESULTS.md` (campaign ledger) + `VERIFICATION-2026-08-26.md` (pre-flight findings) | none — measurement campaign on the Pi's `dev` checkouts |
| C3 | Start without a camera, and say so in the GUI | Planned, not implemented; hardware gates unrun | `C3-no-camera-start/PLAN.md` (ledger entry) + `NO-CAMERA-START-PLAN.md` (full spec) + `SONNET-PROMPT.md` (kickoff prompt) | `feature/no-camera-start` off `dev` (cinemate only, to be cut) |
| C4 | Sensor autodetect — probe-and-heal the camera overlay, with on/off toggle, explicit fallback and imx585 mono checkbox | Planned, not implemented; **depends on C3**; go/no-go gate G0 unrun | `C4-sensor-autodetect/PLAN.md` (ledger entry) + `SENSOR-AUTODETECT-PLAN.md` (full spec) + `SONNET-PROMPT.md` (kickoff prompt) | `feature/sensor-autodetect` off `dev` (cinemate only, to be cut after C3 lands) |
| C5 | Link frequency and RP1 regime — verify what shipped, then make the advertised mode ceilings reflect the live RP1 clock | Feature **shipped to `dev` unverified**; gates G0–G3 unrun; regime fix planned | `C5-link-frequency-regime/PLAN.md` (ledger entry) + `GATES.md` (four gates, predictions stated in advance) | `feature/link-frequency-regime` off `dev` (cinemate only, to be cut after G2) |
| C2 | DSI / DPI panel as a camera monitor, alongside HDMI | Planned, not implemented; hardware gates unrun; moved to last in execution order 2026-08-26 (operator instruction) | `C2-dsi-display/PLAN.md` (ledger entry) + `DSI-DISPLAY-PLAN.md` (full spec) + `SONNET-PROMPT.md` (kickoff prompt) | `feature/display-connector` off `dev` (cinepi-raw) + `feature/dsi-display` off `dev` (cinemate) — both to be cut |
| C6 | Docs + README correctness pass — apply the 2026-08-26 review of both repos' public doc surfaces | **Fixes applied 2026-08-26** (7 commits across both repos, mkdocs --strict green), branches local pending push/PR; deferred items listed in `APPLIED-2026-08-26.md` | `C6-docs-readme-review/PLAN.md` + `DOCS-FIX-PLAN.md` + `SONNET-PROMPT.md` + `APPLIED-2026-08-26.md` (outcome record); raw notes in external `development/readme-docs-review/` | `docs/c6-correctness-pass` off `dev` (cinemate, cut) + `docs/c6-readme-pass` off `dev` (cinepi-raw, cut; `docs/b13-5-readme-fix` was already merged upstream) |
| C7 | ClearHDR: INNO-MAKER knob defaults, SDR HCG toggle, ISO-ceiling warning; gradation curve / black level deliberately kept locked | **Implemented on branches, unverified** — gates G0–G3 unrun, cinepi-raw side not yet built on the Pi | `C7-clearhdr-defaults-controls/PLAN.md` (ledger entry, incl. gates + decision record); research plan in external `development/clearhdr-innomaker-defaults/PLAN.md` | `feature/clearhdr-controls` off `dev` (cinemate `8dfcd165` + cinepi-raw `399692f`, cut 2026-08-26) + driver fork `imx585-v4l2-driver` `6.12.y` @ `cb7c7a6` |

| C8 | Web UI design review — the findings PR #160 did not fix | **Two fixes shipped** (PR [#160](https://github.com/Tiramisioux/cinemate/pull/160), merged `1675ca66`); remaining 8 findings not started, W1 needs an operator decision | `C8-web-ui-review/PLAN.md` (ledger entry incl. the W1 ADR question); harness + measurements in external `development/web-ui-review/` | `fix/web-ui-mobile` off `dev` (merged); remainder on `fix/web-ui-portrait` off `dev` (cinemate only, to be cut) |

Next free step: **C9**.

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
- **C2** was briefly filed as C3 on 2026-08-26, with C2 held open; the operator closed the
  gap the same day and it was renumbered before the branch was ever pushed. No stale copy
  under the old number exists.
- **C3** (no-camera start) was planned directly here on 2026-08-26 from a Fable
  investigation thread; it is unrelated to C2's brief tenure of that number.
- **C4** (sensor autodetect) was planned directly here on 2026-08-26 from a second Fable
  investigation thread the same day, building on a hardware feasibility session from
  2026-06-16 (`~/Documents/codex/sensor_probe.sh`). It deliberately layers on C3's
  advisory gate and NO CAM fallback — implementation order C3 → C4 is a real dependency,
  not just numbering.
- **C5** (link frequency / RP1 regime) is the only step so far whose feature **shipped
  before** it was filed: the RP1 overclock automation, the settings-editor toggle and the
  database-driven link-frequency menus all merged to `dev` on 2026-08-26 (`d175b2fe`, then
  PR #154 at `9834b322`) from a Fable session that started as "are my old overclock
  instructions still valid". It is filed here because that work is entirely unverified on
  hardware and because it exposed a real defect — advertised mode ceilings ignore the live
  RP1 clock — which is a feature, not review remediation. Its `GATES.md` supersedes the
  scratch copy at `development/rp1-overclock/HARDWARE-GATES.md`; that external file was the
  drafting copy and should not be worked from.
- **C6** (docs + README correctness pass) was requested by the operator as "C4" on
  2026-08-26, before the same day's C4 (sensor autodetect) and C5 filings were known to
  that session; C4 was already taken, so it was filed at the next free number instead.
  Nothing was renumbered or overwritten.
- **C7** (ClearHDR defaults + controls) is the second step after C5 whose implementation
  shipped before filing: the operator approved the recommendations of a Fable research
  plan on 2026-08-26 and the code landed on `feature/clearhdr-controls` (both repos) plus
  the driver fork the same day. That session initially drafted this step as C6, then found
  the docs-pass C6 filed by a parallel session mid-flight and took the next free number —
  same collision shape as C6's own filing, resolved the same way.
- **C8** (web UI design review) is filed *after* part of it shipped, like C5 and C7, but
  for a different reason: the operator asked for a UI review, two of its findings were
  small and obviously right (a missing doctype/viewport meta, tap targets and font floors),
  so those were applied and merged the same day as PR #160 — and the operator then asked
  for "the rest" to be recorded here. So this entry is deliberately a **remainder ledger**,
  not a plan for work that was never begun; the applied half is recorded in it only as
  context for what the numbers in the findings table were measured against. One of its
  findings (W1, the portrait layout) is a question for the operator against ADR-001 rather
  than a task, and is marked as such — it argues *against* a deliberate earlier decision
  (B11.7 / F-297) and must not be silently reverted.
