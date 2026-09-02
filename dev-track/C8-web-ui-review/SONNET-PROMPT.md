# Kickoff prompt for the implementing session

Paste everything below the line into a fresh Sonnet thread.

Note: single repo (cinemate), ten findings W1–W10, no cinepi-raw changes, no rebuild. Two of
the ten (W9, W10 — clip download) are new work added by the operator on 2026-09-01 and are
not in `PLAN.md`. W1's ADR question was settled by operator ruling the same day: the rails
stay left and right and the layout shrinks, it never restacks. The findings were measured in
a desk harness and then adversarially re-verified against the pinned dev tree; the full spec
records where the original review was wrong. Hardware gates are unrun — the prompt tells the
implementer to produce the desk-verifiable work and stop before the Pi and the phone.

---

Implement C8 — the web UI review findings PR #160 did not fix: ten items across the live web
GUI and the settings editor, from a portrait layout that wastes most of a phone screen to a
clip download that does not work.

The full spec is at:
`/Users/patrikeriksson/Documents/cinemate/development/worktrees/c8-web-ui-review/dev-track/C8-web-ui-review/WEB-UI-REVIEW-PLAN.md`
on branch `fix/web-ui-portrait` — ledger entry C8 in `PLAN.md` beside it.

Read the spec in full before touching anything. It supersedes `PLAN.md` wherever the two
differ, and it says exactly where `PLAN.md` is wrong (W1's framing, W3's prescribed file,
W6's line range, W1's portrait measurement). Then read
`/Users/patrikeriksson/Documents/cinemate/cinemate-handbook/README.md` plus
`orientation/the-traps.md` and `architecture/gui-state-model.md`, and `docs/web-gui.md`'s
"scales rather than reflows" paragraph — this work rides the shared `populate_values()` state
dict and the design-token pipeline. Every number in the spec came from a measured harness run
and an adversarial re-check: implement them, don't relitigate.

Ground rules:

- One repo, one branch: `cinemate`. A worktree is already cut for you at
  `/Users/patrikeriksson/Documents/cinemate/development/worktrees/c8-web-ui-review` on branch
  `fix/web-ui-portrait` off `dev`. Work there — the main clone is on another feature branch.
  `cd` does not persist between shell calls: use `git -C` and absolute paths.
- **Never `git add -A`** (LFS pointer trap) — stage named files only. This is not theoretical:
  that worktree checked out four `docs/images/*.png` as 130-byte LFS pointers over real
  binaries. They show as modified. Leave them alone.
- Do not merge to `dev`, do not push without asking, and **do not touch the Pi**. You are
  producing the desk-verifiable half.
- The web template's JS is ES5 (`var`, `function(){}`) — match it. The template embeds base64
  font data: filter greps with `awk 'length($0) < 250'`.
- Commit messages: `c8.<n>: <scope> — <one-line outcome>`.
- Colours that exist on both GUIs live in `src/module/design_tokens.py`, not in the template.
  `tools/design_token_diff.py --strict` gates it. But `--box-text` is deliberately *excluded*
  from that table — W3's fix does not go where `PLAN.md` says it does.

**Ask the operator these before writing code**, in one message. Each gates code, not
commentary. Defaults are in the spec's "Order of work" — take the default, proceed, and record
the assumption, except for W6:

- W3 lighten the token or white text; W4 silent-inert or explicit refusal; W5 hide or disable;
  W7 pin the chip too; W9 concurrency cap; W10 whether to write the directory-picker branch.
- **W6 is a hard block.** Its three options ship visibly different products. Do not guess.

Order matters — the spec's "Order of work" table is the authority. Five PRs:

1. **W5** (PR A) — 14 lines of JS, touches nothing else. Land first to prove the harness loop.
2. **W3** (PR B) — changes the DROP box's width, which moves the rail width, which is W1/W2's
   input. Must land before the geometry work or you measure a moving target.
3. **W4** (PR B, 2nd commit) — same file, same parity question, no geometry.
4. **W1 + W2** (PR C, one PR) — they are one implementation. W2's `--fit` scalar *is* W1's
   shrink; W1 contributes the width term. Splitting them produces two conflicting `.rail`
   overrides at equal specificity where source order decides.
5. **W8** (PR C, 3rd commit) — one line, measured after W1's shrink lands.
6. **W6 → W7** (PR D, one PR, that order) — until you know `#app.skin-hud` is what renders,
   every colour you measure in that file is wrong. That trap misled the original review.
7. **W9 + W10** (PR E, one PR) — server and client halves of one feature.

Four things will bite you. All are written up in the spec; re-read those sections before
writing them:

1. **The checked-in harness is stale and does not say so.** `development/web-ui-review/harness/index.html`
   is a build of `c02f8e67` — 965 lines against dev's 1783, predating PR #160 and the whole
   EXPERIMENT drawer. Its mtime lies. Rebuild with the spec's recipe (copy `build.sh` out,
   pass an explicit tree, check the line counts match) and never measure the checked-in copy.
2. **W3's fix is not where `PLAN.md` sends you.** `--box-text` is CSS-only by deliberate design
   (`design_tokens.py:12-16` explains why), applied by the generic `.box` rule — so editing the
   token recolours every status box, not just DROP. The spec gives two scoped routes.
3. **W6's deletion as written breaks five focus rings.** The dead-palette line range in
   `PLAN.md` is wrong. Some variables in those blocks are not shadowed by `#app.skin-hud` and
   must survive. The spec lists which.
4. **`origin/feature/no-camera-start` is a live merge hazard.** It adds `.box.no-cam`
   immediately above `.box.drop`, so if it lands on `dev` before PR B, W3 collides in the same
   hunk. Its NO CAM badge also repeats W3's defect (black on `rgb(220,30,30)` = 4.25:1, below
   AA). Probe the code on the fetched tip, not the log — a squashed merge need not carry the
   branch name.

Gates, all local, all currently green: `ruff check src/`; `python3 -m pytest _test/ -q`;
`shellcheck` over committed `*.sh` plus `python3 tools/check_generated_scripts.py`; the six
contract-drift scripts (`redis_key_diff.py` needs `--cinepi-raw
/Users/patrikeriksson/Documents/cinemate/cinepi-raw` or it exits 2 from a worktree);
`python3 -m mkdocs build --strict`. Seven tests read the two templates as raw text and will
fire if you move a substring they match — the spec names them.

Done means:

1. Each item either implemented with its proof measured, or explicitly deferred with the
   reason. The spec gives every item a "How to prove it" with the number that counts.
2. Before/after numbers for every geometry and contrast change, measured at 1440×800, 812×375
   and 375×812 on a freshly rebuilt harness in `?state=warn`. A screenshot is not evidence for
   a contrast ratio or a font size.
3. All gates green, including the drift six.
4. Ledger edits applied: `PLAN.md`'s portrait figure is wrong (it records 501×281, which is the
   **landscape** measurement mis-filed; portrait is 285×160) and so is the same line in
   `development/web-ui-review/README.md`. W8's `inset` reasoning in `PLAN.md:38-40` is also
   wrong and needs correcting in prose.
5. A closing summary: files touched per commit, per-item status, the measured numbers, every
   decision taken on default, and everything left for hardware.

**Never report a hardware-gated item as done.** W5 needs a physical iPhone. W1, W2, W7 and W8
need a real finger on a real phone. W3, W4, W9 and W10 need the Pi. The spec's "What the desk
cannot close" table says exactly what each one needs and why. Write the code, state the gate,
stop there.

Stop after that summary. Do not start a Pi session, do not run hardware gates, do not merge.
