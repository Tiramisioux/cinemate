# Kickoff prompt — C6 docs + README correctness pass

Paste this into a fresh session in `~/Documents/cinemate/cinemate` (or hand it to a
worktree session). It is self-contained.

---

You are applying a pre-verified docs/README fix plan for the CineMate camera stack.

**Read first, in this order:**

1. `dev-track/C6-docs-readme-review/PLAN.md` — what this step is and the commit layout (C6.1–C6.6).
2. `dev-track/C6-docs-readme-review/DOCS-FIX-PLAN.md` — the full fix list. This is your work order.

**Ground rules:**

- Work on `docs/c6-correctness-pass` cut from `dev` in the cinemate repo. For cinepi-raw
  (`../cinepi-raw`): first merge the already-pushed branch `docs/b13-5-readme-fix` into
  `dev` (ask the operator before pushing anything), then cut `docs/c6-readme-pass` off `dev`.
- The fix plan was verified against cinemate dev `8427ca0b` / cinepi-raw dev `bc63598` on
  2026-08-26. **Re-verify every item against the current code before editing** — grep the
  named key/flag/value in `src/module/` (cinemate) or `cinepi/` (cinepi-raw). If the code
  moved again, fix the docs to match the code, not the plan.
- `docs/installation-steps.md` may have an operator rework in progress (a large one-path
  restructure existed uncommitted on `feature/dev-track` on 2026-08-26). Before touching
  that page, ask the operator whether the rework landed; reconcile with it, never edit the
  old version blind.
- Respect the "Do NOT churn" list at the bottom of the fix plan — those pages are verified
  accurate and carry the target style (behaviour-first tables, one path per page, no
  scene-setting intros, no end-of-page recaps). Match that style in everything you touch;
  do not add new admonition boxes where a sentence does.
- One commit per fix-plan section, following the C6.1–C6.6 layout in PLAN.md. Lowercase
  commit messages, e.g. `c6.1: docs — fix dead settings keys (auto_preroll, audio_capture, record_policy)`.
- **Never `git add -A` in these repos** (LFS pointer trap) — add named files only.
- Do not push without operator approval. Docs deploy from `main` only, so nothing goes
  live until a dev→main merge.

**Verification before you finish:**

- Re-grep each fixed key/value against the code so every documented key provably exists.
- `mkdocs build --strict` green (docs deps: `docs/requirements-docs.txt`; the docs.yml
  workflow runs the same build on PR).
- A link pass over every page you changed (internal anchors included).
- Report per fix: applied / already-fixed-by-newer-code / skipped-with-reason. Do not
  silently drop items.
