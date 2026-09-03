# C8 — Web UI review: full spec (W1–W10)

The implementing session is kicked off by `SONNET-PROMPT.md` beside this file, which points here.
Read this document in full before writing code.

Repo: `/Users/patrikeriksson/Documents/cinemate/cinemate`. Branch off `dev`. Ten findings, W1–W10.
Every item was re-measured against the pinned dev tree and then adversarially re-verified. Where the
verification contradicted the original review, the verification is what is written here.

| Surface | File |
|---|---|
| Live web GUI | `src/module/app/templates/template.html` |
| Settings editor | `src/module/app/templates/settings_editor.html` |
| Shared colour table | `src/module/design_tokens.py` |
| HDMI GUI (parity source) | `src/module/simple_gui.py` |
| RAW pane server | `src/module/app/raw_files.py`, `src/module/app/settings_editor.py` |

This document supersedes `dev-track/C8-web-ui-review/PLAN.md` wherever the two differ.

| Item | What PLAN.md gets wrong |
|---|---|
| W1 | The framing. Settled by operator ruling, not an open ADR question |
| W3 | The prescribed file |
| W6 | The line range. Deleting it as written breaks five focus rings |
| W8 | Nothing. A later "3× worse" restatement was wrong |
| W9, W10 | Absent from PLAN.md |

## Before you touch anything

**Start point.** Branch off `dev`. Verified today: `origin/dev` is `c0eb9ff7`, three commits past the
`981b6bf1` the findings were pinned at. Those three commits touch `innomaker585/ccmp12-lut/**` only —
`git diff --name-only 981b6bf1..origin/dev | grep -v '^innomaker585/'` is empty — so no `src/`,
`docs/`, `tools/` or `_test/` file moved and every line anchor in this document is still exact at
`origin/dev`.

**The clone is shared.** At the time of writing it was on `claude/cinemate-docs-review-h4pxp6`
(`6663e84e`), working tree clean — another session's branch, not yours. It has moved between branches
several times in the last day. Check before you do anything, and never `git checkout` / `git switch` /
`git stash` over someone else's in-flight work.

**`fix/web-ui-portrait` already exists, and a worktree already holds it.** Verified today:
`git branch -a --list '*web-ui*'` returns `fix/web-ui-mobile` (merged) **and** `fix/web-ui-portrait`,
and `git worktree list` shows the latter checked out at
`/Users/patrikeriksson/Documents/cinemate/development/worktrees/c8-web-ui-review` at `c0eb9ff7` —
origin/dev tip, zero commits on it. A `worktree add -b fix/web-ui-portrait` therefore aborts with
`fatal: a branch named 'fix/web-ui-portrait' already exists`. Do **not** recover with `-B` (that
force-resets another session's branch) and do **not** `git checkout` in the shared clone.

```bash
REPO=/Users/patrikeriksson/Documents/cinemate/cinemate
git -C "$REPO" fetch origin dev
git -C "$REPO" rev-parse --abbrev-ref HEAD   # note what you found; do not change it
git -C "$REPO" worktree list | grep fix/web-ui-portrait

# 1. A worktree already holds it (expected). Confirm it is unstarted, then reuse it:
TREE=/Users/patrikeriksson/Documents/cinemate/development/worktrees/c8-web-ui-review
git -C "$TREE" log --oneline origin/dev..HEAD    # must be empty
git -C "$TREE" merge --ff-only origin/dev        # bring it to tip if it is behind

# 2. Branch exists, no worktree — attach one, no -b:
# git -C "$REPO" worktree add <path> fix/web-ui-portrait

# 3. Neither exists — only then:
# git -C "$REPO" worktree add <path> -b fix/web-ui-portrait origin/dev
```

Whichever path you take, that directory is `$TREE` for the rest of this document — the harness recipe
and the `settings-editor-harness` re-point both need it. Note the existing worktree is named
`c8-web-ui-review`, **not** `web-ui-portrait`. `development/worktrees/` is outside every tracked tree,
which is the convention; `/private/tmp` is the convention only for a dirty-tree rescue, not for feature
work.

**`git status --porcelain` is not empty in a worktree, and that is correct.** The shared clone is clean
today. Your worktree reports exactly four modified paths the moment it is created:

```
 M docs/images/camera-stack.png
 M docs/images/camera-stack2.png
 M docs/images/camera-stack3.png
 M docs/images/check-name-image-file.png
```

That is the LFS smudge/clean asymmetry below, not your edit. **Leave them alone: never stage them,
never `git restore` them, never `git checkout -- docs/images/`.** Treat the tree as clean if and only
if `git status --porcelain` shows those four and nothing else.

**Never `git add -A`.** This repo has a live git-LFS trap and it is armed before you add anything:

| fact | evidence |
|---|---|
| `*.png`, `*.jpg`, `*.ipynb` route through the LFS clean filter | `.gitattributes:1-3`; `git check-attr filter -- shot.png` → `filter: lfs` |
| Four already-committed real PNGs show as modified in a clean tree | `git status --porcelain` in a fresh checkout → ` M docs/images/camera-stack.png` ×4 |
| A bare add rewrites them to 130-byte pointers | `git diff --stat -- docs/images/` → `Bin 53639 -> 130 bytes` (×4) |

So `git add -A`, `git add .` and `git add docs/images/` all corrupt four committed images even if you
never create a screenshot. **Add named files only, and run `git diff --cached --name-only` before every
commit.** Harness screenshots and measurement JSON stay in the external workspace
(`/Users/patrikeriksson/Documents/cinemate/development/web-ui-review/`) or your scratchpad — never in
the tracked tree.

**Commits.** One commit per W item. Subject line `<step>: <files> — <what>`, lowercase, em-dash
separator:

```
w3: template.html + design_tokens.py — DROP badge to 7.61:1, warning box auto-widths
```

Body carries the detail, matching recent history (see `4b3d5093` for the house shape): what was
measured before and after with numbers, which gate was re-run, and any deliberate HDMI/web divergence
stated in one sentence. Recent commits carry a `Co-Authored-By:` trailer — keep it.

**"In the PR body" means the commit body.** You cut **one** branch and make **one commit per W item**.
The PR A–E groupings in *Order of work* are a landing order for a human later, not five branches. Every
instruction below that says to state something "in the PR" goes into that item's commit body. Do not
write a summary `.md` file for it.

**Do not push.** Neither this repo nor `cinemate-handbook` (a separate repo, its own push-approval
rule). Docs deploy from `main` only, so nothing goes live from `dev` regardless.

**Ledger edits — the complete list, nowhere else.** Every in-repo text correction this batch owes is
here. Do not hunt for them in the W sections.

| File · line | Becomes | Ships with |
|---|---|---|
| `dev-track/C8-web-ui-review/PLAN.md:25` | "Nothing below is started. W1 is a decision, not a patch" → record that W1 is settled by the 2026-09-01 operator ruling and is an implementation task, and that W9/W10 exist and are not in the findings table | W1's commit |
| `PLAN.md:29` | Replace 501×281 with 285×160 / 15.0%; fix column "Decide, don't patch" → the shrink-to-fit task | W1's commit |
| `PLAN.md:42-66` | Delete the whole "W1 is an ADR question, not a CSS task" section; replace with the operator ruling. Do **not** carry forward any claim that ADR-001 contradicts B11.7 — read in context, ADR-001:250 and :378-380 constrain a *future shared layout engine*, not this file, and the two positions are compatible | W1's commit |
| `PLAN.md:17` | "select tap targets 44×18 → 56×34" is wrong; no select is 56 wide. Use W8's measured width table | W8's commit |
| `PLAN.md:34` | "~150 lines" → the real accounting (42 dead lines), and record that the paper palette was live outside `#app` | W6's commit |
| `PLAN.md:38-40` | The stated reason for excluding iOS 14.0–14.4 is measurably wrong on both halves. Correct the reasoning; the exclusion itself stands | W8's commit |
| `dev-track/README.md:29` | The C8 State cell reads "remaining 8 findings not started, W1 needs an operator decision" — both halves are now false. Restate against what actually landed | last commit of the run |

Two things this table does **not** decide, and you should not decide silently:

- **W9/W10 rows in PLAN.md.** They are findings the plan never had. Adding rows is reasonable; do it
  only if you also give them evidence and disposition columns matching the existing shape. Otherwise
  report them as candidate rows and leave PLAN.md's table at W1–W8.
- **Which branch the ledger edits ride.** `dev-track/README.md:39-44` says implementation happens on
  the step branch but process ledgers "are updated and committed **on this branch**"
  (`feature/dev-track`), with `c<n>: <scope> — <outcome>` subjects. Folding them into `w1:`/`w6:`/`w8:`
  commits on `fix/web-ui-portrait` is a deliberate deviation. Take it — a split across two branches you
  cannot push is worse — and say so in one sentence in the report.

`/Users/patrikeriksson/Documents/cinemate/development/web-ui-review/README.md:69` carries the same
wrong 501×281. Fix it in place, but **it cannot be in any commit**: `git ls-files development/` is
empty, that whole workspace is untracked. Say in the report that you fixed it.

**Read first, in this order:**

1. `dev-track/C8-web-ui-review/PLAN.md` — the original review. Read it knowing this document overrides it.
2. `dev-track/README.md:29` (the C8 row) and `:35-47` (step convention, commit style, the `add -A` ban).
3. `src/module/app/templates/template.html` — the whole file. It is 1783 lines and most of it is comment-documented design decisions you must not silently revert.
4. `src/module/design_tokens.py` — all 34 lines, especially the docstring at `:12-16`.
5. `system-review/decisions/ADR-001-gui-harmonization.md:240-260, 370-385` — the parity argument W1/W3/W4 all sit on.
6. `docs/web-gui.md:26-43` — user-facing prose that becomes false if the rail geometry changes.
7. `src/module/app/templates/settings_editor.html:19-186, 880-1010` — only if you are doing W6/W7.
8. `src/module/app/raw_files.py` and `src/module/app/settings_editor.py` — only if you are doing W9/W10.

## Ground truth

Every line number below was read from the pinned tree today. Use them; do not rediscover the codebase.

| File · lines | What is there |
|---|---|
| `template.html:34` | `--box-text: #000;` — CSS-only, **not** a shared token |
| `template.html:36` | `--drop: rgb(120, 40, 180);` — generated from `design_tokens.py` |
| `template.html:47` | `--gap: clamp(8px, 1.4vw, 22px);` (row-gap is half this) |
| `template.html:95` | `#top-row` `gap: calc(var(--gap) * 0.5) var(--gap);` — the 4px row gap behind W8 |
| `template.html:119-125` | `/* draw_rounded_box(): a locked parameter is drawn inverted. */` + `.group.locked .value` — W4 |
| `template.html:127-137` | The PR #160 tap-target trade-off comment — W8's subject |
| `template.html:138-146` | `.group select { position: absolute; inset: -8px -6px; opacity: 0; … }` |
| `template.html:155,160` | `.badge { color: #000 }`, `.badge.sdr` — a **separate** literal from `--box-text` |
| `template.html:183-200` | The `.rail` rule and its "scroll rather than clip" comment — W2 |
| `template.html:203` | `.section { display:flex; flex-direction:column; align-items:center; }` |
| `template.html:217-228` | `.box` (`color: var(--box-text)` at `:221`) |
| `template.html:231` | `.box.small { font-size: calc(var(--box-height) * 0.48); }` |
| `template.html:234` | `.box.drop { background: var(--drop); }` — W3's insertion point |
| `template.html:336-337` | `#bottom-row` re-scopes `--value-size` / `--label-size` — the idiom W1 reuses |
| `template.html:350` | `font-size: max(10px, calc(var(--value-size) * 0.44))` — PR #160's clip-name floor |
| `template.html:404-419` | EXPERIMENT drawer comment ("opening it does NOT reflow anything") |
| `template.html:434-435` | `#experiment` re-scopes the same properties — second instance of the idiom |
| `template.html:563-585` | The F-297 removal comment + **the file's only `@media`** (`:579`, width-or-orientation) |
| `template.html:623` | `<img id="stream" src="{{ stream_url }}">` |
| `template.html:663` | `<button id="btn-fullscreen">FULLSCREEN</button>` — the only button in the row with no `title=` |
| `template.html:683,700` | `const API = '/api/v1/cmd';` and the `fetch` that writes controls |
| `template.html:765` | `const extra = (part === 'MONO' \|\| part.length > 3) ? ' small' : '';` |
| `template.html:786-794` | The F-211 comment: the HDMI box never shows a count, the browser does |
| `template.html:798-799` | ``const label = count > 0 ? `DROP ${count}` : 'DROP';`` |
| `template.html:1618-1680` | Ten `socket.on(...)` handlers; the harness fakes exactly one |
| `template.html:1623-1626` | `data.control_ranges` — absent from the harness mock |
| `template.html:1760-1762` | `ResizeObserver` driving `sizePreview()` |
| `template.html:1769` | `(el.requestFullscreen \|\| el.webkitRequestFullscreen).call(el);` — W5 |
| `design_tokens.py:12-16` | Docstring: `--box-text` and `--sync-tint` deliberately excluded, "would invent a link that isn't real" |
| `design_tokens.py:19-34` | `DESIGN_TOKENS` — exactly 14 entries; `"drop": (120, 40, 180)` at `:25` |
| `simple_gui.py:15` | `from module.design_tokens import DESIGN_TOKENS` |
| `simple_gui.py:481` | `self.colors = {` — still a hand-written table of literal tuples; only 2 of its fields read tokens |
| `simple_gui.py:1286,1298` | `_draw_status_box(...)`; `text_color` also draws the strike-through line |
| `simple_gui.py:1307,1470` | `TEXT_COLOR = (0, 0, 0)` — hard-coded **twice** (left rail, right rail) |
| `simple_gui.py:1928` | `"exposure_time": "shutter_a_nom_lock"` — the HDMI lock mapping the web GUI lacks |
| `simple_gui.py:2041` | `draw_rounded_box(...)` — the value pill; **not** what draws the DROP box |
| `settings_editor.html:19-105` | `:root` + `prefers-color-scheme` + two `[data-theme]` blocks — W6; only **66-105** is dead |
| `settings_editor.html:40,63` | The only two `--focus` declarations — deleting them kills five focus rings |
| `settings_editor.html:109-112` | `body{ background: var(--bg) }` — **outside** `#app`, so `:root` is live there |
| `settings_editor.html:174-186` | `.topbar{ overflow-x:auto; scrollbar-width:none }` + hidden webkit bar — W7 |
| `settings_editor.html:890-911` | `#app.skin-hud{` — the palette that actually renders |
| `settings_editor.html:980` | `<div class="app skin-hud" id="app">` — unconditional |
| `settings_editor.html:1005` | `#saveBtn`, last child of the scrolling topbar |
| `settings_editor.html:2204` | "Save &amp; reboot Pi" — currently only animates |
| `raw_files.py:182` | `zf.write(f, arcname=f"{path.name}/{f.relative_to(path)}")` — zip entries already prefix the take |
| `tools/design_token_diff.py:29-31` | Only literal `rgb(r,g,b)` / `(r,g,b)` are compared; `#000` and named colours are not |
| `tools/design_token_diff.py:236` | `print("The 14 shared tokens above …")` — a hardcoded 14 next to a dynamic list |
| `tools/redis_key_diff.py:150` | `--cinepi-raw` argument — the escape hatch when the sibling clone is not at `../` |
| `.github/workflows/checks.yml:29,59,71,79` | ruff (src/ only), pytest (`-p no:randomly`), shellcheck ×2 |
| `.github/workflows/checks.yml:92` | `# These four exist because …` — stale, six run |
| `.github/workflows/checks.yml:97,104,107,112,115,127` | The **six** drift scripts |
| `.github/workflows/docs.yml:48,77` | `mkdocs build --clean` (no `--strict`); deploy gated to `main` |
| `docs/web-gui.md:29` | "fullscreen toggle" — W5's docs obligation |
| `docs/web-gui.md:36-43` | The "scales rather than reflows" paragraph — must stay true |
| `dev-track/README.md:29` | The C8 row. Its State cell is stale on both halves — see *Ledger edits* |
| `ADR-001-gui-harmonization.md:250,378-380` | "a 1920 instrument panel and a phone browser should **not** share a grid" |

### The design-token pipeline

`src/module/design_tokens.py` is the source of record for every colour both GUIs share. `simple_gui.py`
imports `DESIGN_TOKENS` at `:15`. The `:root` block in `template.html` is **hand-maintained on the other
side** — there is no generator (`tools/` holds seven scripts, all checkers). Every token change is two
edits. `tools/design_token_diff.py --repo . --strict` is the CI gate that compares them; it exits 0 at
dev tip with 14 shared tokens, 0 drifted.

Four gate properties:

1. **Never hardcode, in the template, a colour the token owns.** If a colour has an entry in
   `DESIGN_TOKENS`, edit both sides in the same commit and re-run the gate.
2. **The gate is one-directional.** `check_shared_tokens` iterates `design_tokens.py` and looks each key
   up in the CSS; it never walks the CSS looking for orphans. A CSS-only colour can never fail `--strict`.
3. **It only compares literal `rgb(r, g, b)` / `(r, g, b)`** (`design_token_diff.py:29-31`). `#000` and
   `lightgreen` are printed under "NOT COMPARABLE" and are ungated. `--box-text` is one of the two.
4. **Adding a key without a matching CSS literal fails loudly, not silently.** Adding
   `"box_text": (255,255,255)` while `--box-text` stays `#000` makes `RGB_RE.search("#000")` return
   `None`, prints `<-- DRIFTED`, and `--strict` exits 1. Do not "fix" that by rewriting the CSS to
   `rgb(0, 0, 0)` unless the item tells you to.

After any colour edit, `python3 tools/design_token_diff.py --repo . --strict` must exit 0 **and**
`--box-text  #000` must still appear under NOT COMPARABLE unless the item explicitly changes that.

### The HDMI-GUI parity constraint

**The rule: a web-only change to anything the HDMI GUI also draws is a divergence, and a divergence must
be deliberate, stated in a comment at the site, and repeated in the commit body.**

| Fact | Evidence |
|---|---|
| `simple_gui.py` draws the camera's own 1920×1080 framebuffer panel; the web GUI mirrors its regions, colours and box shapes | `template.html:119` names `draw_rounded_box()` |
| Same "scale, never restack" model, per B11.7 / F-297 | `docs/web-gui.md:36-43` states it in user-facing prose |
| Parity means "never restacks", not "uses the same mechanism" | `simple_gui.py:1893-1896` scales a fixed canvas by `disp_width / 1920`; the browser has no analogue and is not expected to grow one |
| It does not reach the settings editor — W6, W7, W9, W10 are not parity-constrained | `working/changing-the-gui.md:55-60` scopes the settings editor and recovery console out of the GUI state model; they edit files on disk, not live state |

## Table of contents

Nothing in this list is already fixed at dev tip. Four items carry numbers that PLAN.md gets wrong;
those corrections are at the top of each item's section.

| # | Item | One line | Status vs PLAN.md |
|---|---|---|---|
| W1 | Portrait/narrow viewport: shrink to fit, rails pinned left and right | Preview is 285×160 = 15.0% of a 375×812 screen with 253px dead bands; shrink the rail chrome via the width term of W2's `--fit` scalar | **Task changed.** Operator ruled 2026-09-01: rails always left/right, shrink, never restack. PLAN's "decide, don't patch" framing and its 501×281 figure are both dead |
| W2 | Left rail clips silently at short heights | 282px of rail hidden at 812×375 warn, 129px at 1440×800 (the whole SYS section), 66% hidden with the drawer open | Still true and **worse** than PLAN's 444/282: it is no longer phone-only. **W1 and W2 are one implementation** — see W2 for the mechanism |
| W3 | DROP badge fails contrast and crowds its count | Black on `rgb(120,40,180)` = 2.761:1 (AA wants 4.5); white = 7.605:1. "DROP 17" wraps to two line boxes at every viewport | Still true. **PLAN's prescribed file is wrong** — `--box-text` is not in `DESIGN_TOKENS` and is not gated |
| W4 | Locked reads as selected | A locked FPS / SHUTTER / ISO draws as an inverted white pill and its transparent `<select>` still opens the picker (`pointer-events: auto`) | Partially drifted; the page now ships two contradictory lock treatments. **PLAN's "FPS/SHUTTER/EI" is wrong — there is no EI group** |
| W5 | FULLSCREEN is dead on iPhone | `(el.requestFullscreen \|\| el.webkitRequestFullscreen).call(el)` throws when both are undefined | Still true, unchanged at dev tip. Two adjacent defects found in the same 14 lines |
| W6 | Dead theme CSS in the settings editor | **42** lines are dead, not ~150 | Partially drifted. **Deleting PLAN's range breaks five focus rings** — `--focus` is declared only at `:40` and `:63` |
| W7 | Save can scroll out of reach | `.topbar` scrollWidth 803 vs clientWidth 375 at phone width; `#saveBtn`'s right edge sits 410px past the viewport behind a suppressed scrollbar | Still true |
| W8 | Wrapped-portrait select overlap | Two distinct quantities: 4.000px of group intrusion and 12.00px of select-to-select overlap at 375×812. The comment's 4px is right; its "descender pixels" is wrong | Still true, and **PLAN is not wrong** — a later "3× worse" reading of it was |
| W9 | Clip download, server half | `build_take_zip` writes a whole take to a temp file before the first byte reaches the browser | **NEW** — not in PLAN.md |
| W10 | Clip download + destination folder, client half | `window.location` bulk download races itself; `showDirectoryPicker` is Chromium-desktop-only and needs a secure context | **NEW** — not in PLAN.md |

### How each item is structured

Every W section carries the same six headings, in this order.

| Heading | What it holds |
|---|---|
| **What is wrong** | Verified evidence only: real `file:line`, real source text, real measured numbers |
| **Current state at dev tip 981b6bf1** | Drift from PLAN.md, or an already-fixed flag |
| **What to change** | The exact selectors, functions and code. If a change is not written as code or as a named line edit, it is not in this item — it belongs under *Decision required* |
| **How to prove it** | The exact command or measurement, and the number that counts as proof |
| **Constraints and risks** | CI gates, HDMI-GUI parity, interactions with other W items |
| **Decision required from the operator** | Or "None — mechanical." |

Anything marked "unverified — check first" was not measured. Do not promote it to fact, and do not
report it as done. Enumerate them before you finish: `grep -n "unverified — check first"` over this
document, and answer every hit in the report.

## W1 — Portrait/narrow viewport: shrink to fit, rails pinned left and right

**W1's task changed.** `dev-track/C8-web-ui-review/PLAN.md:29` says "Decide, don't patch" and lines
42–66 frame W1 as an open ADR question with three options. That framing is dead. Operator ruling,
2026-09-01: *"the left and right columns with grey boxes should always be in the left and right. not
reflowed but rather shrunk in order to fit."* Settled consequences:

| | |
|---|---|
| Rails | Stay left and right at **every** viewport, portrait phone included |
| Reflow / restack | **Never.** The layout shrinks. B11.7 / `d8bfbbd1` stands |
| PLAN option 3 (reinstate the removed portrait restack) | **REJECTED** |
| PLAN option 1 (do nothing + "rotate your phone" hint) | **REJECTED** |
| W1 status | Implementation task, not a decision gate |
| W2 (left rail clipping) | **The same implementation.** One mechanism, one floor table, one fade — all of it is written in W2 |
| Scope of the ruling | `#stage`'s three columns and `.rail`'s `flex-direction`. `#top-row`'s `flex-wrap` (W8) is a pre-existing behaviour outside it and is not in scope for the ruling |

**W1's fix lives in W2's "What to change".** Do not build a second mechanism here. W1 contributes one
thing to it: a **width** ratio, folded into the same `--fit` scalar via `Math.min`, plus two collateral
declarations on `#stage` and `#app` that are not `.rail` properties and therefore cannot collide with
`--fit`. Everything else below is W1's evidence, its proof gates and its own edits.

Also correct before you quote it: **the plan's portrait measurement is wrong.** `PLAN.md:29` and
`/Users/patrikeriksson/Documents/cinemate/development/web-ui-review/README.md:69` both record
"501×281" for portrait. 501×281 is the **812×375 landscape** figure, mis-filed into the portrait row.
Portrait is 285×160. Correcting both lines is part of this task — see *Ledger edits*.

### What is wrong

Measured on a harness built from template.html at `981b6bf1`, headless Chrome, `?state=idle`.
All figures ±2px — they are font-metric dependent and differ slightly between machines.

| Viewport | `#stage` `grid-template-columns` | `#preview-frame` | Frame ÷ screen |
|---|---|---|---|
| 375×812 portrait | `38px 285px 20px` | **285×160** | **15.0%** |
| 375×812 portrait, `?state=dual` | `38px 267px 38px` | **267×75** | **6.6%** |
| 812×375 landscape | `38px 708.5px 20.05px` | 502×282 | 46.5% |

- `#preview-wrap` is 671.3px tall in portrait against a 160px frame — **511px of dead band**, split
  evenly above and below by `align-items: center` (`src/module/app/templates/template.html:297-303`).
- The preview is **width-limited, not height-limited**. `sizePreview()` at `template.html:932-948`
  takes the `let w = avail.width` branch at :940 and never enters the `if (h > avail.height)` clamp at
  :942. Anything that only adds vertical room is a no-op.
- The rails cost 58px + two 8px gaps + two 8px `#app` paddings = **90px of 375 (24%)** of viewport
  width, and the boxes are already sitting on their `:root` clamp **minimums**: at 375px wide,
  `--box-size` = `clamp(38px, 3.6vw, 60px)` → **38px** (3.6vw = 13.5px), `--gap` → **8px**,
  `--box-height` → **28px**, `--label-size` → **11.52px** (`template.html:47-51`). Those minimums were
  authored for a laptop and were never re-derived for a phone.
- W2, same root cause on the other axis: at 812×375 `?state=warn` the left rail reports `scrollHeight`
  **542** vs `clientHeight` **260** (idle is 446 vs 282 — do not mix the two states). `.rail` has
  `overflow-y: auto` (`template.html:192`) so it scrolls rather than clips, but there is no visible
  affordance, so the SYS section reads as absent.
- Ceiling arithmetic: a 16:9 picture in a 375px-wide window is at most
  375×210.9 = **26.0%** of a 375×812 screen. With **both rails deleted outright** the frame measures
  359×201 = **23.7%**. The old restack measures 359×201 too — identical. The vertical band is
  geometric, not a layout defect.

### Current state at dev tip 981b6bf1

- The layout system is **byte-identical** to `4affc53e`, the tip PLAN.md was written against: sha256 of each
  extracted block matches for `#app`, `#stage`, `.rail`, `#preview-wrap`, `#preview-frame`,
  `sizePreview`. No drift. Every line number above is confirmed at the tip.
- **Drift that changes scope:** the EXPERIMENT drawer landed *after* PLAN.md was written. Opening it at 375×812
  fills **324.8px** of the dead band (`#experiment` = 359×324.8) at **zero cost to the preview** — the
  frame stays 285×160, because it is width-limited. The vertical band is therefore already reclaimable
  on demand. Do not add height-driven scaling; it would only shrink the picture.
- **But the drawer induces W2 in portrait.** Drawer closed at 375×812: rail `scrollHeight` 671 =
  `clientHeight` 671, no overflow. Drawer open: stage drops to 342.9 and the rail goes
  `scrollHeight` **427** vs `clientHeight` **343**. Your fix must cover this state.
- The surviving media query at `template.html:579` is `@media (max-width: 900px), (orientation: portrait)`.
  The comma is an **OR**. Verified at 812×375: `(max-width:900px)` matches, `(orientation:portrait)`
  does not — so this block **fires on landscape phones**. Do not add anything orientation-specific to it.
- `docs/web-gui.md:36-42` already documents the intended behaviour ("The layout scales rather than
  reflows … shrinking smoothly on a narrow or portrait screen instead of restacking"). **No docs change
  is needed** — this task makes the code match the docs.
- The design-token CI gate is not a risk. `css_tokens()` (`tools/design_token_diff.py:137-145`) parses
  only the first `:root` block, and `main()` at :167-168 explicitly excludes `gap`, `value-size`,
  `label-size`, `box-size`, `box-height` from the colour comparison.
- Harness: rebuild it first. See **Verification and gates → Rebuild the harness**. Do not measure the
  checked-in `index.html`. Related provenance note: `development/web-ui-review/README.md:59` heads its
  measurement table "Measurements taken (dev `4affc53e`, before PR #160)", but the checked-in
  `index.html` (38359 B, 965 lines) is a build of `c02f8e67`. That says nothing about when the numbers
  were taken — it says the checked-in artifact no longer matches the tree they were taken against.
  Treat that `index.html` as unprovenanced; do not "correct" the README heading.

### What to change

Pick **(b): shrink the geometry tokens.** Reject **(a): one `transform: scale()` on the stage.** Why:

1. **(a) moves W1 backwards.** The preview is width-limited (proof above). `transform: scale(k<1)` on
   `#stage` shrinks the *preview* along with the rails. To get a net win you need a second,
   compensating `width: calc(100% / k)` — which destroys (a)'s single-number advantage.
2. **(a) breaks `sizePreview()`.** It reads `wrap.getBoundingClientRect()` (`template.html:935`), which
   returns **post-transform** geometry. Under a stage transform the px it writes back to
   `#preview-frame` get scaled again, landing the frame at k². (b) leaves `sizePreview()` and
   `#preview-frame` untouched — it changes only the rail's own tokens, so the preview is never measured
   through a transform.
3. **(b) is already this file's idiom, twice.** `#bottom-row` re-scopes `--value-size`/`--label-size`
   (`template.html:336-337`); `#experiment` does the same (`template.html:434-435`).
4. **(b) matches the shipped parity claim.** `d8bfbbd1`'s own message says the web GUI keeps its tokens
   "all `clamp()`-based, shrinking smoothly with viewport width". Parity with `simple_gui.py` is *never
   restacks*, not *uses a transform*. `simple_gui.py:1893-1896` is `shrink_x = disp_width / 1920` —
   a fixed-canvas mechanism with no browser analogue that keeps text crisp.
5. **The "multiplies tuned values" objection to (b) is answered by scoping.** Re-derive the four
   geometry tokens on `.rail` and every dependent `calc()` follows automatically: `.rail` `gap` (:191),
   `padding-top` (:199), `.section + .section` margin (:204), `.section .boxes` gap (:214), `.box`
   width/height/glyph (:217-228, glyph `font-size` at :223), `#vu-meter` `padding-top` (:257). **Four
   numbers, not twenty.**

**W1 adds exactly two things to W2's mechanism. Nothing else in this section is new CSS.**

**Addition 1 — the width ratio, folded into the same `--fit`.** W2's `fitRails()` computes a height
ratio; W1 computes a width ratio in the same measurement pass and takes `Math.min`. One variable, one
write, one floor table. **The code is W2's Edit 2 listing** — the `RAIL_WIDTH_SHARE` constant and the
`fitW` line are already in it, marked W1. Do not write a second mechanism here.

Why 0.085: each rail gets 8.5% of viewport width. At 375 that is 31.9px against a 38px natural box, so
`fitW` = 0.839 and `--box-size` lands just above its 31px floor. The term is **inert above 447px of
viewport width** (447 × 0.085 = 38), so nothing in landscape or on desktop changes — every viewport in
W2's fit/floor table is ≥ 812 wide, where 812 × 0.085 = 69 exceeds even the 60px `--box-size` cap.

**Addition 2 — two collateral declarations that are not `.rail` properties.** `#stage`'s gap and
`#app`'s padding are fixed chrome around the rails; `--fit` cannot reach them and they cannot collide
with it. One narrow-width block, placed after `:579`, containing **nothing else**. Never put a `.rail`
declaration in it — that is exactly how two conflicting geometry mechanisms get shipped.

```css
/* Narrow width only: claw back the fixed chrome around the rails. The rails
   themselves shrink through --fit (see fitRails), never through this block.
   Width-keyed, so 812x375 landscape does NOT match — unlike :579, whose comma
   is an OR and fires on landscape phones. */
@media (max-width: 540px) {
    #stage { gap: 6px; }
    #app   { padding-left: 4px; padding-right: 4px; }
}
```

Do **not** change the five existing `:root` values at `template.html:47-51` — those minimums are correct
for a laptop. W2's Edit 1 *adds* four `*-base` siblings to that block; that is the only `:root` change
in this PR.

**The legibility floor is W2's table, not a second one.** `--box-size` 31px, `--box-height` 23px,
`--label-size` 11px, `--gap` 6px, written into the CSS as `max()`. There is no separate W1 floor.

**The overflow affordance is W2's** — `.clipped` + `.more-above` / `.more-below` with `mask-image`,
toggled from `fitRails()` and a passive `scroll` listener. There is no `.rail.overflowing`. It is a
**fallback only, permitted solely once the floor binds**, i.e. only if the rail still overflows after
shrinking as far as the floor allows.

**The gain, as arithmetic, at 375×812 idle.** Baseline columns are `38px 285px 20px`; the two `#stage`
gaps are 8px each and the two `#app` paddings 8px each, and 38 + 285 + 20 + 16 + 16 = 375, which
checks out.

| Term | Before | After | Reclaimed |
|---|---|---|---|
| left rail (`--box-size` × 0.839) | 38.00 | 31.90 | 6.10 |
| right rail (20.05 natural, budget 31.9 → `fitW` = 1) | 20.05 | 20.05 | 0 |
| two `#stage` gaps | 16.00 | 12.00 | 4.00 |
| two `#app` paddings | 16.00 | 8.00 | 8.00 |
| **`#preview-frame` width** | **285** | **≈ 303** | **≈ 18** |

≈ 303 × 170.4 ÷ (375 × 812) = **≈ 17.0%** of screen, up from 15.0%. Gate on **≥ 300px**, not 305 —
303 ± 2px of font-metric variance. If the measurement misses, report the number; do not go below the
floor to reach it.

### How to prove it

Harness: rebuild it first. See **Verification and gates → Rebuild the harness**. **Assert the viewport
before every measurement**: `window.innerWidth`/`innerHeight` must read back exactly 375/812 or 812/375.
Chrome's `--window-size` is ignored under `--headless=new` with `--dump-dom` on this machine (it
silently gives a 500×725 viewport); use `preview_resize` or a fixed-size same-origin iframe. Mis-sized
viewports are precisely how 501×281 got filed as portrait.

`$` is **not** reachable from the console — it is declared at `template.html:726` inside the page-wide
IIFE that opens at `:677`, and the file makes zero `window.X =` assignments. Every expression below uses
`document.getElementById` / `document.querySelector`.

| Check | Where | Passes when |
|---|---|---|
| Baseline reproduces | 375×812, `?state=idle` | frame **285×160**, cols `38px 285px 20px` (±2px) |
| Portrait widened | 375×812, `?state=idle`, after fix | frame width **≥ 300px** (arithmetic gives 303: 375 − 31.9 − 20.05 − 12 − 8); left rail track **≤ 32px** |
| Rails still left and right | 375×812 | `getComputedStyle(document.getElementById('stage')).gridTemplateColumns` resolves to three tracks; `#rail-left`.x < `#preview-wrap`.x < `#rail-right`.x |
| No restack | 375×812 and 812×375 | `getComputedStyle(document.getElementById('rail-left')).flexDirection === 'column'` in both |
| Dual improves | 375×812, `?state=dual` | frame width **≥ 285px** (was 267) |
| W2 closed where it can be | 812×375, `?state=warn` — baseline **542 vs 260** | computed `--box-height` is **exactly 23px** (the floor binds) **and** `railL.classList.contains('clipped') && railL.classList.contains('more-below')`. Zero overflow is **not** achievable here: 13 boxes × 23px = 299px of irreducible box against a 260px viewport |
| W2 closed where it must be | 1440×800, `?state=warn` — baseline `[638, 767, 129]` | `railL.scrollHeight - railL.clientHeight === 0` |
| W2 with drawer | 375×812, click `#btn-experiment` — baseline **427 vs 343** | Marginal by arithmetic (`fitH` = 343/427 = 0.803 against a 0.821 box-height floor), so **either** outcome passes: `railL.scrollHeight <= railL.clientHeight + 1`, **or** `--box-height` computes to exactly 23px with `clipped` + `more-below` set. Report which one you measured |
| Floor honoured | 375×812 and 812×375 | every row of W2's floor table holds under `getComputedStyle` |
| Landscape not regressed | 812×375 | frame still ≥ 500×280; no rule added to the `:579` block |
| Desktop untouched | 1440×800 | `#stage` columns and `#preview-frame` byte-identical to pre-change; `--fit` and the narrow-width block are both inert |
| CI gate | repo root | `python3 tools/design_token_diff.py --strict` exits **0** |

Expected gain: **15.0% → ≈17.0%** of screen in portrait idle. Hard ceiling with zero rails is 23.7%;
geometric 16:9 ceiling is 26.0%. Deliverable: no clipping, rails pinned, dead horizontal band reclaimed.

### Constraints and risks

- **Never add rules to `template.html:579`.** `(max-width: 900px), (orientation: portrait)` is an OR and
  fires at 812×375. Use the width-keyed block above.
- **The narrow-width block must contain no `.rail` declaration.** A `.rail` rule inside a media query is
  a later, equal-specificity `.rail` rule; it would silently overwrite W2's `max()` floors wholesale and
  make `--fit` inert at exactly the viewports it exists for.
- **Never re-add the restack.** `git show d8bfbbd1` removed it deliberately; `docs/web-gui.md:36-38`
  documents its absence as intended behaviour. Do not touch `#stage`'s `grid-template-columns`.
- **Scope every token override to `.rail`.** `.section`, `.section .boxes` and `.box` are shared with
  desktop rendering; an unscoped `--box-size` change regresses 1440×800.
- Interacts with **W3** (DROP badge contrast + auto-width warning boxes). W3's `.box.wide` makes a
  count-carrying warning box auto-width, which is what lets "DROP 17" (41.79px at the 23px floor) live
  in a 31px box. W3 lands first — *Order of work*, row 2. Re-measure the DROP box after W1's shrink,
  because W1 moves the `--box-size` floor W3's auto-width sits on.
- **W2 is the same PR and the same code.** Re-measure both in `?state=warn`, `?state=dual` and
  drawer-open, not just `?state=idle`.
- `tools/design_token_diff.py --strict` is safe (colour-only), but a non-zero exit means your edit
  strayed into the `:root` block at :29-51. CI also builds mkdocs — if you touch `docs/`, keep it valid.
- **Desk verification cannot close this.** Everything above is headless Chrome. Real iOS Safari, the
  dynamic viewport units with the URL bar showing/hidden, safe-area insets, the home indicator and
  actual finger accuracy are phone-on-the-rig checks. The 812×375 figures in particular are a synthetic
  viewport and are an upper bound.

### Decision required from the operator

None — mechanical. The (a)/(b) sub-choice is settled as (b), the mechanism is W2's, and the legibility
floor is W2's px table.

The floor is already known to bind in four cases — W2's own fit/floor table: **812×375, 844×390,
932×430, and 1440×800 with the drawer open.** Ship the fade fallback in those four, say so in the commit
body, and do not go below the floor to avoid it. That is a stated outcome, not an escalation.

## W2 — Left rail clips silently at short heights

Single file: `src/module/app/templates/template.html`. All line numbers verified at dev tip `981b6bf1`.

**Operator decision (binding, overrides anything else you read):** the left and right rails stay on the left and right at every viewport, including portrait phone. The layout never reflows or restacks — it **shrinks to fit**. Portrait restack (removed by B11.7 / F-297) is not coming back. "Rotate your phone" is not the answer. A scroll fade is a **fallback only**, permitted solely once the legibility floor below binds. The ruling scopes to `#stage`'s three columns and `.rail`'s `flex-direction`.

**This section holds the whole W1 + W2 mechanism.** One `--fit` scalar, one floor table, one fade. W1 contributes the width term named in Edit 2 and the two non-`.rail` declarations in its own section.

### What is wrong

| Fact | Evidence |
|---|---|
| `.rail` is a column flex scroller | `template.html:188-200`: `display:flex; flex-direction:column; gap:calc(var(--gap)*0.5)` (:191); `overflow-y:auto` (:192); `overflow-x:hidden` (:193); `scrollbar-width:thin` (:194); `padding-top: calc(var(--box-height)*1.3)` (:199) |
| It is an `auto` track of `#stage`'s `auto minmax(0,1fr) auto` grid | `:175-181` |
| `#stage` is the single `1fr` row of `#app`'s `grid-template-rows: auto 1fr auto` | `:78-84` |
| `html/body` are `overflow:hidden`, so rail content has nowhere to go but its own scroller | `:70` |

The five geometry tokens are declared **exactly once**, in `:root` (:47-51), with no `@media` override and no JS `setProperty` anywhere in the file:

| token | value at :47-51 |
|---|---|
| `--gap` | `clamp(8px, 1.4vw, 22px)` |
| `--value-size` | `clamp(1.05rem, 2.05vw, 1.9rem)` |
| `--label-size` | `clamp(0.72rem, 1.45vw, 1.35rem)` |
| `--box-size` | `clamp(38px, 3.6vw, 60px)` |
| `--box-height` | `clamp(28px, 2.5vw, 40px)` |

Every clamp keys off **width only**. Nothing in the file keys off viewport height — the sole `@media` block (:579-586) is `(max-width: 900px), (orientation: portrait)` and touches only `#button-row`, `.vu-track`, `#experiment`, `.xp-slider .label`. So a wide-but-short window gets the same 40px boxes and 52px rail padding as a 1080p one, and the rail overflows.

Measured (headless Chrome against a harness rebuilt from the 981b6bf1 template + unmodified `mock-io.js`; reproduced independently by a second measurement pass, pixel-for-pixel). `?state=warn` = 13 boxes:

| viewport | `--box-height` | rail clientH | scrollH | hidden |
|---|---|---|---|---|
| 812x375 idle | 28 | 282 | 446 | 164 |
| 812x375 warn | 28 | 260 | 542 | **282** |
| 844x390 warn | 28 | 273 | 549 | 276 |
| 932x430 warn | 28 | 303 | 566 | 263 |
| 1024x600 warn | 28 | 484 | 579 | 95 |
| 1180x700 warn | 29.5 | 566 | 628 | 62 |
| 1280x720 warn | 32 | 575 | 678 | 103 |
| 1366x768 warn | 34.14 | 614 | 721 | 107 |
| 1440x800 warn | 36 | 638 | 767 | **129** |
| 1512x850 warn | 37.8 | 682 | 804 | 122 |
| 1600x900 warn | 40 | 730 | 841 | 111 |
| 1920x1080 warn | 40 | 910 | 910 | 0 |
| 1920x1080, 15-box max load | 40 | 910 | 936 | 26 |
| 1440x800 warn, drawer open | 36 | 261 | 767 | **506** |
| 812x375 warn, drawer open | 28 | 105 | 542 | 437 |

Facts:

- **It is a HEIGHT bug, not a phone bug.** Clean at 1366x1024, 1680x1050, 1728x1117, 1792x1120, 1920x1200, 2560x1440. Rail clientHeight ≈ viewportHeight − 170, and the warn content saturates at 841px once width ≥ 1600 (both clamps cap: `--gap` at w≥1571.4, `--box-height` at w≥1600). Rule of thumb: **clean above ~1050px of viewport height at any width.**
- **Portrait 375x812 is currently clean with real slack** — 244.5px idle, 149.1px warn. (`scrollHeight == clientHeight` proves *no overflow*, never *no slack*; `scrollHeight` is `max(content, clientHeight)`. Measure true content as `[...rail.children].pop().getBoundingClientRect().bottom - rail.getBoundingClientRect().top + rail.scrollTop`.)
- **SYS is built last** (:829-843: SER, MIC, KEY, storage, filesystem badge), so it is always the first casualty. At 812x375/warn the fully-hidden boxes are `['1.0X','48','24','MIC','KEY','SSD','ext4']`; at 1440x800/warn `['KEY','SSD','ext4']`.
- **With the drawer open the warnings themselves vanish.** `#experiment` is a child of `#bottom` (:669), i.e. inside the third `auto` row, so it eats the same `1fr` row. Cap is `min(46vh,460px)` (:421), `40vh` on phones (:584) — 368px at 1440x800, 150px at 812x375. At 812x375/warn+drawer the fully hidden list is `['LOG12','DROP 17','SYNC','2.0','1.0X','48','24','MIC','KEY','SSD','ext4']`. Both warning boxes gone.
- **No scrollbar is visible.** There is no `::-webkit-scrollbar` and no `scrollbar-color` anywhere in the file; only `scrollbar-width: thin` at :194 and :424. On macOS/iOS/Android overlay scrollbars reserve no width and are transparent at rest. (Unverified — check first: the headless-Chrome `offsetWidth - clientWidth == 0` measurement has no discriminating power; a control div with `overflow-y:scroll; scrollbar-width:auto` also reports 0. Do not use it as a guard. macOS "Show scroll bars: Always" is a real counter-case.)

### Current state at dev tip 981b6bf1

**Not fixed. No drift.** The `:root` block and the `.rail` block are byte-identical to 4affc53e. The one `@media` block grew from 4 to 8 lines, gaining only `#experiment { max-height: 40vh; }` and `.xp-slider .label { flex: 0 0 6em; }`. New since the original write-up: the EXPERIMENT drawer (`#experiment`, :420-424 / :669) now removes up to 506px of rail viewport at 1440x800/warn — that case is in scope for W2 because it changes rail height without a window resize, which is exactly what a media-query fix cannot see.

### What to change

**Chosen mechanism: (b) — shrink the geometry tokens, driven by one measured ratio.** Rejected: whole-stage `transform: scale()`. Reasons:

1. A naive `transform: scale()` on `#stage` **does not fix this at all**. Transforms do not change layout size, so the rail's `clientHeight` in CSS px is unchanged and `scrollHeight/clientHeight` is unchanged. To make (a) work you must give `#stage` a fixed logical canvas sized `viewport / s` and re-fit on every resize *and* every drawer toggle — a re-architecture of the one element `sizePreview()` measures via the ResizeObserver at :1760-1762, with a live double-scaling hazard for the preview.
2. **The HDMI-parity argument for (a) is materially false.** `shrink_x = disp_width/1920` / `shrink_y = disp_height/1080` are computed at `src/module/simple_gui.py:1895-1896` but reach only the top row, the layout-dict positions, the HDR badge and the clip name (:1694-1780, :1935-2007). `draw_left_sections` (:1300) and `draw_right_sections` (:1465) use hard-coded `BOX_H, BOX_W = 40, 60`, `y = 97` and absolute gaps with **no shrink factor**. There is no scaled-rail behaviour to be faithful to. (template.html:566-568's claim that simple_gui "scales its whole 1920x1080 layout by a single ratio" is only half true; fix that comment while you are in there.)
3. **Shrinking rail geometry is the HDMI GUI's own move.** `simple_gui.py:1315-1316` tightens `BOX_GAP` 14→10 and `SECTION_GAP` 66→26 when the buffer VU shares the column, and `draw_left_sections` `return y` (:1458, comment "caller uses this to avoid VU-meter collision") feeds :2018-2025, which shrinks the VU bar between 40 and 200px to give the grown column room. The HDMI answer to "the left column grew" is already "shrink something else", not "clip it".
4. A whole-stage scale drags `#top-row` and `#bottom` down with it for no benefit — they are not the overflowing element — and at 812x375/warn would need s = 260/541.84 = **0.48**, taking the box glyph from 17.4px to 8.3px and the section label from 11.8px to 5.7px.

**Legibility floor — binding, and the only floor table in this document. Write it into the CSS as `max()`, not into a comment. It governs both the height term and W1's width term.**

| property | floor | basis, measured against the shipped `DIN2014-Bold.ttf` |
|---|---|---|
| `--box-height` | **23px** | `.box.small` = `calc(var(--box-height) * 0.48)` (:231) → **11.04px**, the smallest rendered glyph in the rail |
| `--label-size` | **11px** | `.section-label` font (:207) → 11px |
| `--box-size` | **31px** | at the 11.04px small glyph: `1.85` 20.93px, `ext4` 20.39px, `NTFS` 25.26px, `exFAT` **29.15px** — fits with ~1.85px margin. `DROP 17` is 41.79px and does **not** fit; it depends on W3's `.box.wide` auto-width having landed first |
| `--gap` | **6px** | boxes must stay visually separate |

Below 11px of rendered glyph, stop shrinking and fall back to scroll + fade.

**Edit 1 — factor the tokens into base + fit.** In `:root` (:47-51) keep the five names exactly as they are (`tools/design_token_diff.py` reads only the first `:root` block) and add four `*-base` siblings:

```css
--gap-base:        clamp(8px, 1.4vw, 22px);
--label-size-base: clamp(0.72rem, 1.45vw, 1.35rem);
--box-size-base:   clamp(38px, 3.6vw, 60px);
--box-height-base: clamp(28px, 2.5vw, 40px);
```

Then re-derive them **on `.rail` only** (custom properties resolve at the element where they are declared, so a `--fit` set on `.rail` cannot retroactively change a `:root`-declared `--gap` — the re-declaration is required).

**These are additions to the existing `.rail` rule at `template.html:188-200`, not a replacement.** Only the `padding-top` line at `:199` is rewritten. Keep `display`, `flex-direction`, `gap`, `overflow-y`, `overflow-x`, `scrollbar-width` and both comments verbatim — dropping `flex-direction: column` turns each rail into a horizontal row, a direct violation of the binding ruling, and dropping `overflow-y: auto` is the regression named in *Constraints* below. The full resulting rule:

```css
.rail {
    display: flex;
    flex-direction: column;
    gap: calc(var(--gap) * 0.5);
    overflow-y: auto;
    overflow-x: hidden;
    scrollbar-width: thin;
    /* NEW: W1+W2 fit. --fit is written by fitRails() and is the smaller of the
       height ratio (rail content vs stage row) and the width ratio (rail budget
       vs viewport). The max() floors are the legibility floor; when one binds,
       fitRails sets .clipped and the fade fallback shows. */
    --gap:         max(6px,  calc(var(--gap-base)        * var(--fit, 1)));
    --label-size:  max(11px, calc(var(--label-size-base) * var(--fit, 1)));
    --box-size:    max(31px, calc(var(--box-size-base)   * var(--fit, 1)));
    --box-height:  max(23px, calc(var(--box-height-base) * var(--fit, 1)));
    /* was: padding-top: calc(var(--box-height) * 1.3) at :199 — keep the
       existing draw_left_sections() comment above it */
    padding-top:   calc(var(--box-height) * var(--rail-pad, 1.3));
    overscroll-behavior: contain;   /* matches #experiment:423; the rails were missed */
}
.rail.fitted { --rail-pad: 0.4; }   /* reclaim the dead band once we are shrinking */
```

Scope is contained: `#stage { gap: var(--gap) }` (:180) and `#app`'s padding stay on the `:root` value here — W1's narrow-width block is what moves them, and only below 540px. Everything the rail's height is built from is inside this scope — `padding-top` (:199), `.section + .section { margin-top: calc(var(--gap)*0.7) }` (:204), `.section .boxes { gap: calc(var(--gap)*0.35) }` (:214), `.box { width/height/font-size }` (:217-228, glyph at :223), and `.section-label { font-size: var(--label-size) }` (:205-210). That last one is 11.9% of the warn content at 812px wide (4 sections × 16.18px) and is **not** derived from `--gap`/`--box-height` — a gaps-only shrink cannot touch it, which is why `--label-size` must be in the fit set.

**Edit 2 — measure and write `--fit`.** `$` is `document.getElementById` (:726). `render()` (:1567) is the single call site for `renderLeftRail`/`renderRightRail` (:1574-1575) and is also called by the drawer toggle (:1752). Do the fit in a `requestAnimationFrame`, **not** inline in `render()` — `render()` runs at up to 12 Hz during a take (`simple_gui.py:192-193`, `target_fps = 12`), and reading `scrollHeight` straight after `rail.replaceChildren(...)` (:843) is a forced synchronous layout on a dirty tree.

This is the canonical listing. W1's width term is in it, marked. Do not write a second one.

```js
// Each rail may take at most 8.5% of the viewport width (W1). At 375 that is
// 31.9px against a 38px natural box -> 0.839, landing --box-size just above its
// 31px floor. Inert above 447px of viewport width (447 * 0.085 == 38), so no
// row of the fit/floor table below changes: its narrowest case is 812 wide.
const RAIL_WIDTH_SHARE = 0.085;

let fitPending = false;
function fitRails() {
    fitPending = false;
    ['rail-left', 'rail-right'].forEach((id) => {
        const el = $(id);
        if (!el || !el.isConnected || !el.clientHeight) { return; }
        el.classList.remove('fitted');
        el.style.setProperty('--fit', '1');          // measure at natural size
        const natural  = el.scrollHeight, avail = el.clientHeight;
        const naturalW = el.getBoundingClientRect().width;
        const fitH = Math.min(1, avail / natural);                                   // W2, height
        const fitW = Math.min(1, (window.innerWidth * RAIL_WIDTH_SHARE) / naturalW); // W1, width
        const fit  = Math.min(fitH, fitW);
        if (fit < 1) { el.classList.add('fitted'); }
        el.style.setProperty('--fit', fit.toFixed(4));
        // the max() floors can stop the shrink short of avail — say so out loud
        el.classList.toggle('clipped', el.scrollHeight - el.clientHeight > 1);
    });
}
const scheduleFit = () => { if (!fitPending) { fitPending = true; requestAnimationFrame(fitRails); } };
```

Both ratios are read in the one `--fit: 1` pass, so the width term costs no extra reflow.

Call `scheduleFit()` at the end of `render()` and observe **`#stage`**, not the rails, for geometry:

```js
if (window.ResizeObserver) { new ResizeObserver(scheduleFit).observe($('stage')); }
```

Observe `#stage` because writing `--fit` changes a rail's width, which would re-trigger a ResizeObserver on the rail itself; `#stage`'s border box is fixed by the grid and only its columns redistribute, so this cannot loop. `#stage`'s height *does* change when the drawer opens — which is the case a media query cannot catch.

**Edit 3 — fallback fade, only when `.clipped`.** Use `mask-image` on `.rail` itself, not a `::after`: a pseudo-element inside a scroll container scrolls away with the content; a mask paints in the container's own box (verified in Chrome — `mask-origin` computes to `border-box` and the computed `maskImage` is byte-identical after `rail.scrollTop = rail.scrollHeight`). Ship `-webkit-mask-image` for Safari < 15.4. Do **not** use `animation-timeline: scroll()` — Chrome-only in the iOS-relevant window. Place after the `.rail` block (:200) and before `.rail:empty` (:201); keep the new rules property-disjoint from `display` so `.rail:empty`'s higher specificity never bites.

```css
.rail.clipped.more-below { -webkit-mask-image: linear-gradient(to bottom, #000 calc(100% - 26px), transparent);
                                   mask-image: linear-gradient(to bottom, #000 calc(100% - 26px), transparent); }
.rail.clipped.more-above { -webkit-mask-image: linear-gradient(to bottom, transparent, #000 14px);
                                   mask-image: linear-gradient(to bottom, transparent, #000 14px); }
.rail.clipped.more-above.more-below { -webkit-mask-image: linear-gradient(to bottom, transparent, #000 14px, #000 calc(100% - 26px), transparent);
                                              mask-image: linear-gradient(to bottom, transparent, #000 14px, #000 calc(100% - 26px), transparent); }
```

Toggle `more-above`/`more-below` from a `scroll` listener (`{ passive: true }`) and from `fitRails`. Keep the mask off unless `.clipped` — a permanent mask forces compositing on a subtree repainted at 12 Hz.

**What this closes.** `fit_needed = clientH / scrollH` (measured); `fit_floor = 23 / --box-height` (arithmetic — re-measure, do not trust):

| viewport (warn) | fit needed | fit floor | outcome |
|---|---|---|---|
| 812x375 | 0.480 | 0.821 | floor binds → **fade fallback** |
| 844x390 | 0.497 | 0.821 | floor binds → fade fallback |
| 932x430 | 0.535 | 0.821 | floor binds → fade fallback |
| 1024x600 | 0.836 | 0.821 | closed (marginal; `--rail-pad` reclaim gives headroom) |
| 1180x700 | 0.901 | 0.780 | closed |
| 1280x720 | 0.848 | 0.719 | closed |
| 1366x768 | 0.851 | 0.674 | closed |
| 1440x800 | 0.832 | 0.639 | closed |
| 1512x850 | 0.848 | 0.608 | closed |
| 1600x900 | 0.868 | 0.575 | closed |
| 1920x1080, 15-box max | 0.972 | 0.575 | closed |
| 1440x800 + drawer | 0.340 | 0.639 | floor binds → fade fallback |

Every viewport in this table is ≥ 812 wide, so W1's width term is 1 in all of them and the column is unchanged by the merge. Every laptop and desktop case closes by shrinking. Phone-landscape warn and drawer-open do not: 13 boxes × 23px = 299px of irreducible box against a 260px viewport. That is arithmetic. Ship the fade fallback there.

### How to prove it

Harness: rebuild it first. See **Verification and gates → Rebuild the harness**. Do not measure the checked-in `index.html`.

Probe: `const r = document.getElementById('rail-left'); [r.clientHeight, r.scrollHeight, r.scrollHeight - r.clientHeight, getComputedStyle(r).getPropertyValue('--fit')]`

| case | baseline triple | passes when |
|---|---|---|
| 1440x800 `?state=warn` | `[638, 767, 129]` | third number **0**, `--fit` ≈ 0.83, computed `--box-height` ≥ 23px |
| 1280x720 warn | `[575, 678, 103]` | third number 0 |
| 1024x600 warn | `[484, 579, 95]` | third number 0 |
| 1920x1080, 15-box max load | `[910, 936, 26]` | third number 0 |
| 812x375 warn | `[260, 542, 282]` | `--box-height` == 23px exactly (floor binds) **and** `r.classList.contains('clipped') && r.classList.contains('more-below')` |
| 812x375 warn + click `#btn-experiment`, wait 400ms | `[105, 542, 437]` | `clipped` + `more-below` still true (proves the fit re-ran on the drawer, not on a resize) |
| 375x812 idle | content **426.52** vs clientH 671 | overflow stays 0. `--fit` ≈ **0.839** (W1's width term, not the height term) and `--box-height` ≈ 23.5px, still above the 23px floor |
| 375x812 warn | content **518.91** vs clientH 668 | overflow stays 0 at `--fit` ≈ 0.839 — the content shrinks with the boxes, so shrinking cannot create overflow here |
| **Operator ruling, every viewport above** | — | `getComputedStyle(document.getElementById('stage')).gridTemplateColumns` resolves to **three** tracks; `#rail-left`.x < `#preview-wrap`.x < `#rail-right`.x; `getComputedStyle(document.getElementById('rail-left')).flexDirection === 'column'`. Re-assert with `#btn-experiment` open. **A fail here voids the item regardless of the overflow numbers.** |

Reachability, not just totals: `const rr = r.getBoundingClientRect(); [...r.querySelectorAll('.box')].filter(b => b.getBoundingClientRect().top - rr.top + r.scrollTop >= r.clientHeight).map(b => b.textContent)` — must return `[]` at 1440x800/warn (baseline `['KEY','SSD','ext4']`).

Mask-not-a-pseudo-element test: set `r.scrollTop = r.scrollHeight`, then assert `getComputedStyle(r).maskImage` still resolves, `more-above === true`, `more-below === false`. A `::after` implementation fails this.

Gate: `python3 tools/design_token_diff.py --strict` must exit 0 (it does today at 981b6bf1 — verified).

Not provable from the desk: whether a finger can drag a ~31px strip that sits next to the tap-to-record `#preview-frame` (:622), and whether `mask-image` renders correctly on iOS Safari. Both need an iPhone against the rig.

### Constraints and risks

| item | detail |
|---|---|
| CI gate is inert here | `tools/design_token_diff.py:167-168` explicitly filters `("gap","value-size","label-size","box-size","box-height")` out of the colour check, and `--strict` exits 1 only on `not shared_ok` (:239-240), which compares the 14 rgb tuples in `src/module/design_tokens.py`. It is also one-directional — it never walks the CSS for strays, so **adding** `--gap-base` etc. cannot trip it. **There is no CI check that will catch a geometry regression.** Every claim above must be asserted by hand. |
| `--*-base` names must stay prefix-compatible | The filter is `startswith(...)`, so `gap-base` / `box-size-base` / `box-height-base` / `label-size-base` all pass. `css_tokens` (:137-145) reads only the **first** `:root` block — put the new tokens there. |
| Do not remove `overflow-y: auto` | `html/body` are `overflow: hidden` (:70). Without the rail's own scroller the `auto` grid column overruns `#stage`'s `1fr` row and the content is hard-clipped by the body with no scroll at all — strictly worse. The scroll must stay under the fit. |
| HDMI parity | Shrinking rail geometry is not a divergence (see `simple_gui.py:1315-1316` and :1458 / :2018-2025). Cite `system-review/decisions/ADR-001-gui-harmonization.md:378-380` — "**Keep the region anchors per-surface.** The HDMI panel is a fixed-resolution instrument; the browser is not." — in the commit message so this does not read as a revert of B11.7 / F-297, whose rationale is at template.html:563-578. |
| `overscroll-behavior: contain` | Behavioural change on iOS on the same element as the visual fix. Right call (matches :423) but land it as its own hunk so it can be reverted separately. |
| W8 interaction — no risk | The claim that raising `#top-row`'s row-gap (`calc(var(--gap) * 0.5)`, :95) tips portrait into overflow is false. Injecting a change to `calc(var(--gap) * 1.2)` — more than double, 4px → 9.6px at 375 wide — costs portrait exactly 5px: idle headroom 244.48 → 239.48, warn 149.09 → 144.09. Tipping portrait/warn needs ~149px. |
| W1 interaction — resolved, one mechanism | A height-only fit leaves `--fit` at 1 in portrait (244.5px of vertical slack), so the rails would never narrow there — which is the whole of W1. Both terms therefore write the **same** `--fit`: `Math.min(fitH, fitW)` in the Edit 2 listing above. There is no second variable, no second floor table, and no `.rail` declaration inside W1's media query. |
| Repaint cost | `render()` runs at up to 12 Hz (`simple_gui.py:192-193`, `target_fps = 12`; deltas emitted at :1862, consumed at template.html:1630-1634). The rAF gate plus keeping the mask class-toggled are both load-bearing, not polish. |
| Grep hazard | `src/module/app/templates/settings_editor.html` has an unrelated `.rail` nav-sidebar class (17 hits). Separate template, separate `<style>`, no cascade collision. Only `template.html` is in scope. |

### Decision required from the operator

None — mechanical. The mechanism, the sub-choice (b), and the 11px / 23px legibility floor are all settled above, and they are the same ones W1 uses.

Two findings to file **separately**, not to fix here:

1. **The HDMI GUI has the same bug and cannot scroll.** Walking `draw_left_sections` by hand for the warn load (y starts 97, label step `BOX_H + LABEL_SPACING` = 36, box step `BOX_H + BOX_GAP`): with `buffer_vu_meter` true (`settings.jsonc:251` default) y ends at 969 and fits; with it false y ends at 1141 and the ext4 box is drawn at 1087-1127, entirely off a 1080 canvas, with no scroll and no affordance. Worse, `draw_left_sections` is unscaled, so on a 1280x720 HDMI monitor the column still starts at y=97 with 40px boxes and runs off the bottom before SYS even with the VU meter on.
2. **SYS-last ordering** (:829-843) is arguably the root cause on both surfaces — the storage filesystem badge, the thing `.rail`'s own comment (:183-187) says must never silently disappear, is the last thing drawn. Moving `warningBoxes()` (:794-803) out of CAM (:812) would protect DROP/SYNC, but the HDMI GUI draws them inside CAM too (`simple_gui.py:1374-1395`), so that is a divergence needing its own ADR-001 argument.

## W3 — DROP badge fails contrast and crowds its count

### What is wrong

Two independent defects in the web GUI's DROP warning box. Both confirmed present at dev tip 981b6bf1.

1. **Contrast.** `.box.drop` paints `rgb(120, 40, 180)` behind black text. WCAG 2.x ratio = **2.7612:1**. AA needs 4.5:1 for normal text and 3:1 for large bold text — this fails both, at every viewport.
2. **Crowding.** `"DROP 17"` wraps to two lines inside the fixed box. Bare `"DROP"` (count 0) *overflows* the box and is clipped by `.rail { overflow-x: hidden; }`.

Colour source, one place per surface:

| What | File:line | Source text |
|---|---|---|
| Shared background token | `src/module/design_tokens.py:25` | `    "drop": (120, 40, 180),` |
| Web copy of it | `src/module/app/templates/template.html:36` | `            --drop: rgb(120, 40, 180);` |
| Only rule consuming it (background only, no `color`) | `template.html:234` | `.box.drop { background: var(--drop); }` |
| Web text colour (NOT a token) | `template.html:34` | `            --box-text: #000;` |
| Its sole consumer, specificity (0,1,0) | `template.html:221` | `            color: var(--box-text);` |
| HDMI text colour, left rail | `src/module/simple_gui.py:1307` | `        TEXT_COLOR    = (0,   0,   0)` |
| HDMI text colour, right rail | `src/module/simple_gui.py:1470` | `        TEXT_COLOR    = (0,   0,   0)` |

`--drop` is the only failing box background. The five real `.box` backgrounds against black: `--box` 5.92, `--sync` 6.70, `--log-badge` 13.21, `--zoom-hi` 15.59, `--drop` **2.76**. (`--lock`, `--voltage`, `--res-switching` are foreground text colours on the black page, not box fills — `template.html:117`, `:357`, `:358`. `--sdr-badge`/`--hdr-badge`/`--wav-rec` are `.badge` fills whose text colour is an independent hardcoded `color: #000;` at `template.html:155`, unreachable from `--box-text`.)

Crowding. Box pitch is `--box-size: clamp(38px, 3.6vw, 60px)` and `--box-height: clamp(28px, 2.5vw, 40px)` (`template.html:50-51`). `.box` font = `0.62 × --box-height`; `.box.small` = `0.48 ×` (`:231`). The label is built at `template.html:796-800`, and `.small` is gated on `label.length > 4` — `"DROP"` is exactly 4 characters, so bare DROP renders at the 0.62 factor.

Measured against DIN2014-Bold advance widths (`DROP` 2.4550 em, `SYNC` 2.4080, `DROP 17` 3.7850, `DROP 173` 4.3250, `+0.5400` per extra digit):

| Label | Class today | vw ≤1055 (38×28 box) | vw 1280 | vw 1920 |
|---|---|---|---|---|
| `DROP 17` | `drop small` | needs 50.87px → wraps, 26.88px tall in 28px | +12.06px | +12.67px |
| `DROP` | `drop` (no small) | needs 42.62px → **overflows +4.62px, clipped** | +2.63px | +0.88px |
| `SYNC` | `sync` (no small) | needs 41.80px → **overflows +3.80px, clipped** | +1.69px | fits from vw ≈1659 |

The HDMI GUI does not have this defect: `_draw_status_box` auto-shrinks when the text exceeds the inner width (`simple_gui.py:1290-1293`). Measured with the repo's own font via Pillow, `DROP` is **64px** at bold 26 (left rail) and **60px** at bold 24 (right rail), both over the 56px threshold, so the redraw at bold 20 always fires. The web GUI is the surface that drifted.

Sibling inconsistency: `boxes()` uses `part.length > 3` (`template.html:765`); `warningBoxes()` uses `label.length > 4` (`:799`). They disagree on any 4-character string.

### Current state at dev tip 981b6bf1

Nothing is fixed. `git diff --stat 4affc53e 981b6bf1 -- src/module/design_tokens.py` is empty; the token has not moved since e9299226. The template diff over the same range contains no line touching `--drop`, `--box-text`, `--box-size`, `--box-height`, `.box`, `warningBoxes` or `DROP`. `python3 tools/design_token_diff.py --repo . --strict` exits 0 today and prints `design_tokens.py entries: 14`.

Corrections to numbers and scope claims commonly attached to this item, verified against the tree:

- The right-rail call site is `template.html:853`, not 852. (`:852` is the `log_badge_cam1` line.) Left rail is `:812`.
- `settings_editor.html` has a wholly separate palette and no `--drop`. "Both surfaces" = HDMI + live web GUI only.
- `docs/simple-gui.md:27` does **not** describe the DROP colour — its "magenta" attaches to SYNC. Only `docs/troubleshooting.md:10`, `docs/sensors.md:5` and `docs/sensors.md:170` call DROP purple/magenta.

### What to change

Two routes for the contrast half. **Route B is recommended** and is written out below; Route A is the operator's alternative (see the last subsection).

*Route B — white text on the existing purple (7.6054:1, clears AA and AAA).* There is no existing text-colour token to flip, so add a new key. Do not touch `--box-text` or `TEXT_COLOR`.

1. `src/module/design_tokens.py`, inside `DESIGN_TOKENS` after line 25: `"drop_text": (255, 255, 255),`
2. `src/module/app/templates/template.html`, **inside the first `:root` block, on any line 30–51** (line 52 is the closing `}` and the gate truncates there). Put it next to `--drop` at line 37. Literal comma-form `rgb()` only — `#fff`, `white` and `rgb(255 255 255)` all fail the gate:
   `            --drop-text: rgb(255, 255, 255);`
3. `template.html:234` — extend the existing rule. Specificity (0,2,0) beats `.box`'s (0,1,0) and it is already later in source order:
   `.box.drop { background: var(--drop); color: var(--drop-text); }`
4. `src/module/simple_gui.py` near line 21, beside `DROP_WARNING_COLOR = DESIGN_TOKENS["drop"]`: `DROP_TEXT_COLOR = DESIGN_TOKENS["drop_text"]`. Pass it instead of `TEXT_COLOR` in the two DROP draw calls only — the `TEXT_COLOR,` argument at `simple_gui.py:1381` (left rail) and `simple_gui.py:1526` (right rail). Leave `:1307` and `:1470` untouched.

*Crowding half.* Add after `.box.small` (`template.html:231`):

```css
/* A warning box may carry a count ("DROP 17"). simple_gui's box is a fixed
   60x40 and shrinks the font instead (simple_gui.py:1290-1293); the browser
   has room. Grow on the inline axis only, from the same --box-size floor,
   so every box that already fits keeps the rail's pitch. */
.box.wide {
    width: auto;
    min-width: var(--box-size);
    padding-inline: calc(var(--box-height) * 0.18);
    white-space: nowrap;
}
```

Replace `template.html:799`. Every label here is ≥4 characters, so `.small` becomes unconditional — which also fixes the bare-DROP clipping and matches the HDMI's own shrink:

```js
out.push(box(label, 'drop' + ' small' + (count > 0 ? ' wide' : '')));
```

The concatenated `' small'` is load-bearing. `_test/test_b97_web_gui_drop_count.py:43` is `self.assertIn("' small'", self.warning_boxes_body)` — an 8-character search ending in a quote. Writing `' small wide'` as one literal **fails that test** (verified by applying the edit and re-running the assertion). Either keep the `+ ' wide'` form above, or amend the test in the same commit.

### How to prove it

| Check | Command / measurement | Passing number |
|---|---|---|
| Token gate | `python3 tools/design_token_diff.py --repo . --strict; echo $?` | exit `0`; header reads `design_tokens.py entries: 15`; report gains the line `  --drop-text       (255, 255, 255)    == design_tokens.py` |
| Token is inside the parsed block | `awk 'NR>=30 && NR<=51' src/module/app/templates/template.html \| grep -- --drop-text` | one hit |
| Unit gates | `python3 -m pytest _test/ -q -p no:randomly` | 0 failures, specifically `test_b97_web_gui_drop_count.py` and `test_b95_sync_box_crossed_consistency.py` |
| Contrast, measured | Paste the `ratio()` helper from **Verification and gates → WCAG contrast, in JS** (it parses the `rgb(...)` string; feeding `c.color` straight into an array destructure yields `NaN`), then: `const c = getComputedStyle(document.querySelector('.box.drop')); ratio(c.color, c.backgroundColor)` | **≥ 4.5**. Today returns 2.761. |
| Crowding, at 1440×800, 812×375, 375×812 | `const b=document.querySelector('.box.drop'),r=b.getBoundingClientRect(); [r.width,r.height,b.scrollWidth,b.scrollHeight]` | `scrollWidth <= Math.ceil(r.width)` AND `scrollHeight <= Math.ceil(r.height)` |
| Bare-DROP regression | same measurement with the mock count set to 0 | overflow goes from ~42.6px in a 38px box to 0 |
| Rail jump | `document.getElementById('rail-left').getBoundingClientRect().width` and `#preview-wrap` likewise, with `drop_frame_latched` false then true | record the delta in the PR; predicted +23.0px per rail at 375px wide |

Harness: rebuild it first. See **Verification and gates → Rebuild the harness**. The checked-in copy is **stale** in a way specific to this item — `index.html:605` still reads `box('DROP', 'drop')` (pre-`020910a3`, no count) and `:29` carries a `/* DROP_WARNING_COLOR */` comment the live template no longer has. Load `?state=warn`; `mock-io.js:68` already sets `drop_frame_latched: true, drop_frame_count: 17`.

### Constraints and risks

- **Never flip `--box-text` or `TEXT_COLOR`.** They are global. `--box-text` reaches five box background variants: default grey (white-on-`rgb(136,136,136)` = 3.54:1), `.box.log` (1.59:1), `.box.zoom-active` (1.35:1), `.box.sync` (3.14:1), `.box.drop`. Scope every change to `.box.drop` and the two DROP draw calls.
- **The token gate proves nothing about this finding.** `tools/design_token_diff.py --strict` compares colour equality only (`:63-79`). It cannot see the applied text colour, the `.small` gating, or any contrast ratio; `--box-size`/`--box-height` are explicitly filtered out at `:167-168`. Green CI ≠ W3 fixed. CI job is `drift` in `.github/workflows/checks.yml:106-107`.
- **HDMI-GUI parity.** The framebuffer box is a hard 60×40 (`simple_gui.py:1304`, `:1468`) and can never auto-width. `.box.wide` is a deliberate per-surface divergence. ADR-001 sanctions it — cite `system-review/decisions/ADR-001-gui-harmonization.md:378-380` ("Keep the region anchors per-surface…") in the PR or it reads as unreviewed drift.
- **Widening the box resizes the live preview mid-record.** The rail is a content-sized `auto` grid track (`template.html:178`) whose max-content is currently `--box-size`. Measured: `.box.wide` makes it 60.95px, a **+23.0px** jump per rail; `warningBoxes()` feeds both rails (`:812` and `:853`), so a dual-sensor rig loses 45.9px = 12.2% of a 375px viewport. That reflow of the MJPEG `<img>` fires the instant DROP latches.
- **Width is unbounded in the count** (+0.54 em per digit). Cap the rendered number — `"DROP 99+"` measures 4.3250 em, identical to three digits.
- **Do not add any class to the SYNC box.** `_test/test_b95_sync_box_crossed_consistency.py:56-57` pins `if (V.frames_off_sync) { out.push(box('SYNC', 'sync')); }` byte-for-byte, and `.box.sync::after`'s diagonal strike (`template.html:237-244`) has a fixed 3px band tuned to a square-ish box.
- **Cosmetic, expect it:** `DROP_TEXT_COLOR = DESIGN_TOKENS["drop_text"]` is a Subscript, so the tool's informational Python-constant scan skips it exactly as it already skips `DROP_WARNING_COLOR`. Also stale after this change but ungated: the `"The 14 shared tokens above…"` string at `tools/design_token_diff.py:236`, the VERDICT counts (16→17, 14→15), and `system-review/STATE.md:103` ("the 14 shared HDMI/web colours").
- **Stale claim worth correcting while here:** `src/module/design_tokens.py:12-16` says `--box-text` has no equivalent on the Python side. `simple_gui.py:1307` and `:1470` both define `TEXT_COLOR = (0,0,0)`.

### Decision required from the operator

1. **Route A or Route B.** Route B (above) keeps the purple and turns the text white: 7.6054:1, docs stay true. Route A is the one-line token edit — lighten `--drop` to `rgb(165, 58, 245)` (4.5236:1 against black, near-fluorescent, blue channel nearly clipped) or desaturate to `rgb(150, 100, 205)` (5.0012:1). Route A changes a recognised on-camera alarm colour and contradicts `docs/troubleshooting.md:10`, `docs/sensors.md:5`, `docs/sensors.md:170`; `tools/docs_drift_check.py` does not check colour words, so nothing will catch it.
2. **Accept the ~23px-per-rail preview shrink at latch time, or reserve the width permanently** via a `min-width` on `.rail` (never jumps, permanently narrower picture at every viewport).
3. **Cap the drop count?** Realistic magnitude on a bad take is unknown — needs a Pi or real take logs (unverified — check first). Without a cap the rail width is unbounded.
4. **SYNC overflows too** (+3.80px at the clamp floor, clipped at every viewport below ≈1659px — that is where `--box-size: 3.6vw` reaches SYNC's 59.72px, not the 1666.67px where `--box-size` hits its 60px cap). The real defect is "any 4-letter warning label rendered without `.small`". Fixing SYNC requires editing `_test/test_b95_sync_box_crossed_consistency.py` in the same commit. Fix it here, or file it separately?
5. **Does white DROP text read on the physical HDMI panel** at real viewing distance and brightness? sRGB maths is a proxy; the panel has its own gamma. Needs eyes on cinepi.local. The geometry half of parity needs no device — it is derivable from the repo's own font file.

## W4 — Locked reads as selected

Nothing here is fixed at dev tip. All file paths are relative to the repo root; all line numbers are verified at `981b6bf1`.

### What is wrong

A locked FPS / SHUTTER / ISO draws as an inverted white pill in the web GUI top row, and a fully live, invisible `<select>` sits on top of it. The pill says "this parameter is frozen"; the control under it opens a picker, accepts a value, and posts a command.

| Fact | Location | Source text |
|---|---|---|
| The only locked styling | `src/module/app/templates/template.html:119-125` | `/* draw_rounded_box(): a locked parameter is drawn inverted. */`<br>`.group.locked .value { background:#fff; color:#000; border-radius:5px; padding:0 0.22em; }` |
| The overlay is live | `template.html:138-146` | `.group select { position:absolute; inset:-8px -6px; opacity:0; border:0; cursor:pointer; ... }` |
| No lock guard on any top-row handler | `template.html:1734-1736` | `$('s-shutter').addEventListener('change', (e) => cmd('set shutter a ' + e.target.value));` |
| Only 3 groups get `.locked` | `template.html:993-995` | `toggle('locked', Boolean(V.fps_lock / V.shutter_a_nom_lock / V.iso_lock))` |
| HDMI GUI source of the pill | `src/module/simple_gui.py:1959-1961` | `self.draw_rounded_box(draw, value, position, font_size, 5, "black", "white", image)` — `radius = 5` at `simple_gui.py:2049` |

Three verified consequences.

1. **The toast never says "locked".** FPS and ISO setters return before any Redis write (`cinepi_controller.py:1024` `if self.fps_lock and not self.lock_override:`; `cinepi_controller.py:2006` `if not self.iso_lock:` wrapping the body). `cli_commands.py:225` then answers `True, f"requested {requested_value}, live value is {actual}"`, `api.py:78` renders `ok <message>`, and `template.html:707` toasts `set fps 30 → requested 30.0, live value is <n>`. `grep -rn "is locked" src/module/` returns only `template.html:1096, 1102, 1108` — EXPERIMENT-drawer `lockLabel` strings. The exact digits of `<n>` are a runtime fact (raw Redis string) — unverified, needs a device.
2. **SHUTTER is not refused at all — the pill lies.** `template.html:1735` sends `set shutter a`, routed by `cli_commands.py:59` to `set_shutter_a`. That function (`cinepi_controller.py:2012-2076`) contains no read of `shutter_a_nom_lock` anywhere — only the threading lock `parameters_lock_obj` and sync-mode clamping. The guard lives in `set_shutter_a_nom` (`cinepi_controller.py:2082 if not self.shutter_a_nom_lock:`), which only the drawer calls (`set shutter a nom`, `cli_commands.py:64`). It writes `shutter_a` / `shutter_a_actual` unconditionally, and `SHUTTER_A_NOM` at `cinepi_controller.py:2049` when gated by `2046 if self.shutter_a_sync_mode == 0:`.
3. **The browser is the outlier.** The analog pot routes through the guarded setter — `analog_controls.py:266 self._dispatch('shutter_a_nom', new_shutter_a)`. The web top row is the only operator surface that writes through a shutter lock.

Two more verified gaps.

- `#g-exp` never gets `.locked`. `simple_gui.py:1924-1930` `lock_mapping` includes `"exposure_time": "shutter_a_nom_lock"`, so the HDMI GUI inverts EXP under a shutter lock and the browser does not. `#g-exp` (`template.html:601`) is also the only top-row group without `.selectable` and without a `<select>`.
- The same file already ships the opposite lock treatment for the drawer: `template.html:1494-1497` sets `entry.input.disabled = unusable`, `.disabled` class, and a named `title`; `template.html:476` `.xp-slider.disabled { opacity:0.4; pointer-events:none; }`. Two contradictory lock idioms on one page.

### Current state at dev tip 981b6bf1

- CSS did not drift. `.group.locked .value` at `119-125` is byte-identical to `4affc53e`.
- The overlay GREW since the plan. `4affc53e` had `inset:0; width:100%; height:100%`; `981b6bf1` has `inset:-8px -6px` (commit `4b3d5093`, PR #160). `.group` has no border or padding, so the hit area is the group box + 16px height + 12px width, and it spans the LABEL as well as the value. Tapping the word "FPS" on a locked group opens the picker.
- **Correction to the plan text:** the plan writes "FPS/SHUTTER/EI". There is no EI group. The third locked group is `#g-iso` (`template.html:604`, key `iso_lock`).
- **Correction:** the plan's claim that "the reject toast already explains the refusal" is wrong. See point 1 above.
- Cascade census: there are FOUR `.group.X .value` rules, not three — `.tinted` (116), `.switching` (117), `.locked` (120-125), `.clip` (349-354). `.clip` is later in source but sets **no colour property** (`font-size`, `overflow`, `text-overflow`, `max-width`), and `.group.clip` is used once, at `template.html:641` (bottom row), which never gets `.locked`. So `.group.locked .value` currently wins every colour tie. A new colour-setting `0-3-0 .group.X .value` rule is only dangerous if inserted **after line 125**; inserting before 120 is safe.

### What to change

Recommended: guard the change handlers, keep every pixel identical, name the reason. Zero visual change means zero parity risk against `simple_gui.py`. Replace `template.html:1734-1738`:

```js
// A locked parameter's setter drops the write and still answers 200
// (cinepi_controller.set_fps / set_iso), so the only feedback today is
// _confirm_or_ok's generic "requested X, live value is Y" — which never
// says "locked". SHUTTER is worse: the top row sends `set shutter a`,
// which never reads shutter_a_nom_lock, so the pill lies.
const TOP_LOCKS = {
    's-iso':     { key: 'iso_lock',           label: 'ISO is locked' },
    's-shutter': { key: 'shutter_a_nom_lock', label: 'Shutter angle is locked' },
    's-fps':     { key: 'fps_lock',           label: 'Frame rate is locked' },
};
function bindTopSelect(id, prefix) {
    $(id).addEventListener('change', (e) => {
        const guard = TOP_LOCKS[id];
        if (guard && truthy(V[guard.key])) {
            toast(guard.label);
            renderSelectors();
            return;
        }
        cmd(prefix + e.target.value);
    });
}
bindTopSelect('s-iso',     'set iso ');
bindTopSelect('s-shutter', 'set shutter a ');
bindTopSelect('s-fps',     'set fps ');
bindTopSelect('s-wb',      'set wb ');
bindTopSelect('s-res',     'set resolution ');
```

- `truthy` (`:733`), `toast` (`:689`), `renderSelectors` (`:1040`) and `V` (`:717`) are all already in scope.
- The three label strings live today only inside `XP_SLIDER_GROUPS` (`:1096`, `:1102`, `:1108`). Hoist them to one shared const that both the drawer and `TOP_LOCKS` read. Do not create a fourth copy — this repo has CI gates specifically because duplicated facts drift.
- **`renderSelectors()` does not reliably restore SHUTTER.** `template.html:1042-1043` passes `steps.shutter_a.find((v) => String(v) === String(parseFloat(V.shutter_speed)))` as `current`; `find` returns `undefined` on no match, and `fillSelect` at `:748` is guarded by `if (current !== undefined && current !== null)`. `V.shutter_speed` is a formatted string (`f"{actual_angle_f:.1f}°"`, `simple_gui.py:750`). If the live angle is absent from the step table the rejected pick stays visible. Either set `e.target.value = String(<live value>)` explicitly in the guard branch, or fix the `find` fallback. iso/fps are unaffected.

Optional companion, still zero visual change — add beside `template.html:993-995`:

```js
$('s-fps').title = V.fps_lock ? 'Frame rate is locked' : '';
$('s-fps').setAttribute('aria-disabled', V.fps_lock ? 'true' : 'false');
```

Rejected alternatives, with the reasons:

| Option | Why not |
|---|---|
| `.group.locked select { pointer-events:none; }` | Touch/mouse only. The `<select>` stays in the tab order and keyboard-operable, so Tab + ArrowDown still fires `change` and still POSTs. And it removes the only feedback the operator gets today — nothing else in `.group` has a click handler (the only nearby listener is `template.html:1740` on `#preview-frame`), so the tap becomes wholly inert. |
| Lock glyph in the pill | Not renderable in both GUIs. `DIN2014-Bold.ttf` cmap: U+1F512 PADLOCK absent, U+25A0 / U+25CF / U+2219 absent; only U+00B7 and U+2022 survive. `simple_gui._get_font` (`:688-696`) loads the same TTF through PIL, so a padlock is `.notdef` there and falls back to colour emoji in the browser. |
| Red ring via `box-shadow: 0 0 0 2px var(--lock)` | Viable but visual, so it needs a mirrored change in `draw_rounded_box` (`simple_gui.py:2041`). Operator call — see below. Use `box-shadow`, never `border`, so the top row does not reflow. |

### How to prove it

| Check | Command / expression | Proof value |
|---|---|---|
| Toast never says "locked" | `grep -rn "is locked" src/module/` | Exactly 3 hits, all `template.html:1096/1102/1108` |
| Locked pill computed style | `getComputedStyle(document.querySelector('#g-fps .value'))` | `backgroundColor rgb(255,255,255)`, `color rgb(0,0,0)`, `borderRadius 5px` |
| Hit-area overshoot | `const g=document.getElementById('g-fps').getBoundingClientRect(), s=document.querySelector('#g-fps select').getBoundingClientRect(); [s.height-g.height, s.width-g.width]` | `[16, 12]` today |
| Pill padding sanity | `getComputedStyle(document.querySelector('#g-iso .value')).paddingLeft` at 1280px viewport | `5.7728px` (0.22 × 26.24px); `3.696px` at 375px (0.22 × 16.8px floor) |
| FPS refusal path | `set fps lock 1`, then `curl -s -X POST -H 'Content-Type: text/plain' --data 'set fps 30' http://cinepi.local/api/v1/cmd` | HTTP 200, body `ok requested 30.0, live value is <old fps>` |
| **SHUTTER write-through (needs a Pi)** | `set shutter a nom lock 1`; note `redis-cli get shutter_a`; `curl -s -X POST --data 'set shutter a 45' .../api/v1/cmd` | Bare `ok` AND `redis-cli get shutter_a` returns `45` ⇒ the lock is cosmetic. Unchanged ⇒ refuted. |
| After the fix | pick a value on a locked group | Toast reads exactly `ISO is locked` / `Shutter angle is locked` / `Frame rate is locked`; no POST in DevTools Network; select shows the live value |
| CI | `python3 tools/design_token_diff.py --repo . --strict` and `python3 tools/gui_field_extract.py --repo . --max-unresolved 0` | Both exit 0 |

Harness caveat — **the measurement harness cannot show this case as it stands.** `development/web-ui-review/harness/mock-io.js:70-74` sets `iso_lock: true, fps_lock: true, shutter_a_sync: true` and **no** `shutter_a_nom_lock`, so `?state=warn` never showed a locked SHUTTER. Hand-add `shutter_a_nom_lock: true` to a mock state before measuring. Build and serve per **Verification and gates → Rebuild the harness** (`build.sh:16` defaults `REPO` to the shared clone, which is on another session's branch — always pass `$TREE`).

### Constraints and risks

- **Parity is a stated contract.** `template.html:8-11` says the browser and the on-camera monitor "read as one instrument", and the locked rule's own comment names `draw_rounded_box()`. There is no CI gate on it — only that comment. Any pixel change to `.group.locked .value` must be mirrored at `simple_gui.py:1961`. The recommended fix changes no pixels.
- Inverse mode is already faithful: `body.inverse` (`template.html:58-62`) rebinds only `--label`, `--value`, `--sync-tint`, so the hardcoded `#fff`/`#000` survive, mirroring `simple_gui`'s hardcoded `"black"`/`"white"`.
- Cascade: insert any new `.group.X .value` colour rule **before** line 120, never after 125.
- **`design_token_diff.py` only checks Python → CSS.** `check_shared_tokens()` (`tools/design_token_diff.py:56-79`) iterates `DESIGN_TOKENS` and reports MISSING/DRIFTED; there is no reverse pass, and `:root` already declares 21 `--` names against 14 Python entries with CI green. A new CSS-only token would NOT fail the build. Reuse `var(--lock)` for style reasons, not CI reasons.
- `--lock` / `DESIGN_TOKENS["lock"]` renders nowhere today. `parameters_lock` is assigned exactly once in the tree — `cinepi_controller.py:179 self.parameters_lock = False` — and is only read at `simple_gui.py:1134`. `all_lock` is a different, live attribute. So reusing `--lock` has zero collision, but no operator has ever seen it.
- "Light pill with black text = ON" collision: `template.html:395 button.on { background: var(--log-badge); color:#000; }` with `--log-badge: rgb(205,205,205)`, used by the drawer's `ISO LOCK` / `SHUTTER LOCK` / `FPS LOCK` buttons (`:1551`). A lit lock button and a locked value pill are two light pills meaning different things. Any brighter locked treatment pushes further into that vocabulary.
- **Do not close the backend hole in this PR.** Adding a `shutter_a_nom_lock` early return to `cinepi_controller.set_shutter_a` (`:2012`) also hits `set_fps`'s motion-blur snap (`cinepi_controller.py:987 self.set_shutter_a(closest_shutter_angle)`) and, critically, the ClearHDR self-heal, which calls it deliberately at `cinepi_multi.py:1045` and `:1049` with a docstring (`:1028-1033`) saying it must go through the real setter rather than a direct Redis write. A guard there would silently disable ClearHDR self-heal whenever SHUTTER LOCK is on. Controller-level change, Pi-gated, separate PR.
- Interaction with W8: making a locked select inert (option b) would hand the ~4px of wrapped-row overlap to the row above, turning a static ambiguity into a state-dependent hit target. The recommended fix avoids this — the select stays live, only the write is guarded.
- Docs: `docs/web-gui.md:86-89` documents the drawer's lock behaviour and says nothing about the top row. `grep -n "template" tools/docs_drift_check.py` returns nothing, so the docs gate will NOT catch this. Add the line by hand.
- One media query exists in the whole stylesheet (`template.html:579-586`) and contains no `.group`, `.value`, `select` or lock rule. Nothing changes by viewport.

### Decision required from the operator

1. **Inert or explicit?** On a locked parameter, should the web GUI be silently inert (closest to the HDMI GUI, where a locked rotary simply does nothing) or explicitly refuse with a named reason (closest to what a touch instrument owes its operator)? The recommended fix assumes explicit. Both keep the pixels identical.
2. **Should `#g-exp` get `.locked` under `shutter_a_nom_lock`,** matching `simple_gui.py:1928`? Cheap to close, but it puts a lock pill on a read-only field.
3. **Is a visible per-parameter lock affordance wanted at all,** given the HDMI GUI has none? If yes, `simple_gui` must grow one too, and DIN2014 cannot draw a padlock — the cost is a font file or new `ImageDraw` primitives.
4. **Should the SHUTTER backend hole be filed as its own finding?** It reclassifies W4: "polish, not correctness" holds for FPS and ISO only.

## W5 — FULLSCREEN is dead on iPhone

### What is wrong

`src/module/app/templates/template.html:1764-1777` is the whole fullscreen implementation:

```js
    const fsBtn = $('btn-fullscreen');
    function toggleFullScreen() {
        const el = document.documentElement;
        const active = document.fullscreenElement || document.webkitFullscreenElement;
        if (!active) {
            (el.requestFullscreen || el.webkitRequestFullscreen).call(el);
        } else {
            (document.exitFullscreen || document.webkitExitFullscreen).call(document);
        }
    }
    fsBtn.addEventListener('click', toggleFullScreen);
    document.addEventListener('fullscreenchange', () => {
        fsBtn.textContent = document.fullscreenElement ? 'EXIT FULLSCREEN' : 'FULLSCREEN';
    });
```

Three defects, all verified in source:

| # | Defect | Evidence |
|---|---|---|
| D1 | `:1769` and `:1771` have no feature detect. When neither method exists, `(a \|\| b)` is `undefined` and `.call` throws a TypeError inside the click listener. | Apple's `jsc` prints `TypeError: undefined is not an object (evaluating '(el.requestFullscreen\|\|el.webkitRequestFullscreen).call')`; node/V8 prints `Cannot read properties of undefined (reading 'call')` |
| D2 | Label never flips on prefixed-only WebKit. `:1775` subscribes to `'fullscreenchange'` only; `:1776` reads `document.fullscreenElement` only — while `:1767` *does* read `webkitFullscreenElement`. The file contradicts itself. | Safari desktop 5.1–16.3 fires only `webkitfullscreenchange` |
| D3 | Both calls return a Promise; the return value is discarded at `:1769` and `:1771`. A rejection (untrusted gesture, permissions policy) is an unhandled rejection. | spec-mandated Promise return |

Nothing catches D1. The only try/catch in the page is `:699-712` inside `cmd()`. The only `'error'` listener is `:1711`, on the MJPEG `<img>` elements. No `window.onerror`, no `unhandledrejection` handler. Strict mode is in force from `:678`, so the member access is a hard TypeError, not a no-op. `toast()` (`:689`) is never reached.

`button:active { background: var(--label); color: #000; }` at `:394` inverts the button under the finger, so the dead control still gives press feedback and then does nothing.

No fallback exists on this page. `grep -c -iE "<video|<canvas|<audio"` over the template returns **0**. The preview is two MJPEG `<img>` tags (`:621-629`). `HTMLVideoElement.webkitEnterFullscreen()` — the only fullscreen affordance iPhone Safari has ever exposed — has no element to be called on.

Platform facts (MDN browser-compat-data, re-fetched and confirmed 2026-09-01):

| Browser | `Element.requestFullscreen` | Note |
|---|---|---|
| Safari iOS — iPad | webkit-prefixed from 12, unprefixed from 16.4 | works; forced overlay button, swipe-down exits |
| Safari iOS — iPhone | none, any version | BCD note verbatim: "Only available on iPad, not on iPhone." |
| Safari desktop | webkit `requestFullscreen` 5.1, `fullscreenElement` 6, unprefixed 16.4 | this is why D2 is real |

It is **iPhone**, not iOS. A UA or OS test would wrongly hide the button on iPad. caniuse still lists iOS Safari 12.0–26.6 as partial. Claims that Apple shipped iPhone element-fullscreen behind a flag in Safari 17.2 are **unverified — check first**; do not encode any version assumption either way.

### Current state at dev tip 981b6bf1

Not fixed. `git diff 4affc53e 981b6bf1 -- src/module/app/templates/template.html` renders `const fsBtn` / `function toggleFullScreen` / `const el = document.documentElement` as context lines. The block is byte-identical to the baseline the plan was written against. The only insertion in that region is the eight-line ResizeObserver block at `:1760-1762`.

| Fact | State at 981b6bf1 |
|---|---|
| Markup `<button id="btn-fullscreen">FULLSCREEN</button>` | `:663`, last child of `#button-row` (`:659`), the only one of the four buttons with no `title=` |
| `.hidden { display: none !important; }` | `:541`, specificity (0,1,0) |
| `const show = (el, on) => el.classList.toggle('hidden', !on);` | `:732` |
| `const truthy = (v) => ...` | `:733` |
| `toast(msg)` | `:689` |
| Repo-wide `btn-fullscreen` references | exactly **2**: `template.html:663` and `:1764`. (`:1776` is `fsBtn.textContent`, the variable, not the id; `PLAN.md:33` quotes `requestFullscreen`, not the id) |
| `grep -c -i fullscreen src/module/simple_gui.py` | 0 |
| `grep -i fullscreen` in `settings_editor.html` (4737 lines) | 0 — W5 is single-surface |
| `docs/web-gui.md:29` | `- fullscreen toggle`, in the unconditional list opened at `:21` |

### What to change

Replace `src/module/app/templates/template.html:1764-1777` wholesale. Probe the methods once at wire-up, hide via the file's own `show()` helper, bind only if usable.

```js
    // iPhone Safari exposes no element-fullscreen API at all; iPad does
    // (webkit-prefixed since iOS 12, unprefixed since 16.4). Probe the methods,
    // never the UA, so iPad keeps the button and a future iPhone gains it. The
    // preview is an MJPEG <img>, not a <video>, so there is no
    // HTMLVideoElement.webkitEnterFullscreen() fallback here. Calling a missing
    // method threw a TypeError inside the click listener that nothing caught --
    // and button:active still flashed, so the control looked like it worked.
    const fsBtn = $('btn-fullscreen');
    const fsRoot = document.documentElement;
    const fsRequest = fsRoot.requestFullscreen || fsRoot.webkitRequestFullscreen;
    const fsExit = document.exitFullscreen || document.webkitExitFullscreen;
    const fsActive = () => document.fullscreenElement || document.webkitFullscreenElement;

    show(fsBtn, Boolean(fsRequest && fsExit));

    if (fsRequest && fsExit) {
        fsBtn.addEventListener('click', () => {
            // Both return a promise that rejects on an untrusted gesture or a
            // blocking permissions policy. webkitRequestFullscreen returns
            // undefined, hence the guard.
            const p = fsActive() ? fsExit.call(document) : fsRequest.call(fsRoot);
            if (p && p.catch) { p.catch((err) => toast('fullscreen → ' + err.message)); }
        });
        // Safari and iPadOS below 16.4 fire only the prefixed event and set only
        // document.webkitFullscreenElement, so one name and one property left
        // the label permanently stuck on 'FULLSCREEN' there.
        ['fullscreenchange', 'webkitfullscreenchange'].forEach((ev) => {
            document.addEventListener(ev, () => {
                fsBtn.textContent = fsActive() ? 'EXIT FULLSCREEN' : 'FULLSCREEN';
            });
        });
    }
```

Rules for this edit:

- Do **not** move the `show(fsBtn, ...)` into `render()`. One-shot at wire-up is correct and safe: `render()` runs at `:1779` and on every `gui_data_change`, calls `show()` on eleven other elements, and touches `btn-fullscreen` nowhere — the id appears only at `:663` and `:1764`.
- Use `show()`, not `style.display`. `show()` is not always wrapped in `Boolean()` — `:895` passes `false`, `:919` passes `true`, `:925` and `:955` pass bare expressions, `:1453`/`:1550` pass `truthy(...)`. The idiom is `show(el, <anything truthy/falsy>)`. `Boolean(...)` here is fine, not mandatory.
- Do **not** detect with `document.fullscreenEnabled`. It also goes false under a Permissions-Policy or in an iframe, which is a behaviour change. (It would not behave differently on iPhone — BCD gives it the identical iPad-only note.)
- Do **not** UA-sniff or version-test. `if (window.ResizeObserver)` at `:1760` is the in-file precedent for a truthiness capability detect.
- If the button is hidden rather than disabled, add a `title=` to `:663` for parity with its three siblings.
- If `docs/web-gui.md:29` is qualified in the same PR, keep the wording free of backticked file paths — see gates below.

### How to prove it

| Step | Command / assertion | Proof |
|---|---|---|
| 1. Defect is real | `/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc -e "var el={}; try{(el.requestFullscreen\|\|el.webkitRequestFullscreen).call(el);}catch(e){print(e.name+': '+e.message);}"` | prints `TypeError: undefined is not an object (evaluating '(el.requestFullscreen||el.webkitRequestFullscreen).call')` — the exact string an iPhone console shows |
| 2. Harness | Build and serve per **Verification and gates → Rebuild the harness**, then open `?state=idle` | page renders; a JS syntax error kills `render()` at `:1779` and yields a blank page |
| 3. Probe is not over-eager | console: `JSON.stringify([!!document.documentElement.requestFullscreen, !!document.exitFullscreen])` | `[true,true]` on desktop — button stays visible where fullscreen works |
| 4. Hide path | copy `harness/index.html`, edit `const fsRequest = ...` to `const fsRequest = null;`, load it, assert `document.getElementById('btn-fullscreen').classList.contains('hidden') === true` **and** `getComputedStyle(...).display === 'none'` | both true — proves `.hidden`'s `!important` (`:541`) wins |
| 5. No throw, no listener | in that same copy install `window.addEventListener('error', e => console.log('UNCAUGHT', e.message))` and an `unhandledrejection` listener, then call `document.getElementById('btn-fullscreen').click()` programmatically (the button is `display:none`, hit-testing skips it — a real tap is impossible) | zero UNCAUGHT lines; post-fix the click dispatches to zero listeners |
| 6. Contrast (regression baseline) | in the **unmodified pre-fix** harness, console: `delete Element.prototype.requestFullscreen; delete Element.prototype.webkitRequestFullscreen;` then `document.getElementById('btn-fullscreen').click()` | exactly one UNCAUGHT TypeError. There are no `fsRequest`/`fsExit` variables pre-fix — the lookup is inline at `:1769` — so property deletion is the only way to reproduce |
| 7. Label | desktop browser: click FULLSCREEN, assert `textContent === 'EXIT FULLSCREEN'`; Esc, assert back to `'FULLSCREEN'`. Confirm by reading the source that both `'fullscreenchange'` and `'webkitfullscreenchange'` are registered | the prefixed path itself cannot be exercised on a current desktop browser |
| 8. Gates | from repo root: `python3 tools/design_token_diff.py --repo . --strict`, `python3 tools/gui_field_extract.py --repo . --max-unresolved 0`, `python3 tools/docs_drift_check.py --repo . --strict` | all exit 0 (all three are 0 at 981b6bf1 today) |
| 9. Device gate — desk CANNOT close this | load `http://cinepi.local:5000/` on a real **iPhone** over the hotspot: FULLSCREEN absent. On a real **iPad**: present, works, label flips | catches a UA-sniff regression and catches a future iOS that ships element fullscreen on iPhone |

Layout is **not** a risk and needs no measurement pass. Row width was computed statically against the shipped `src/module/app/static/DIN2014-Bold.ttf` (97272 bytes, real TTF, magic `00010000`, not an LFS pointer), with `--gap: clamp(8px,1.4vw,22px)` (`:47`), `--value-size: clamp(1.05rem,2.05vw,1.9rem)` (`:48`), `button { font-size: calc(var(--value-size)*0.62); padding: 0.3em 0.7em; border: 2px }` (`:385`,`:388`,`:390`), `#button-row { gap: calc(var(--gap)*0.5) }` (`:377`), `#app` padding (`:82`):

| viewport | gap px | font px | need, 4 btns | need, 3 btns | available | slack, 4 btns |
|---|---|---|---|---|---|---|
| 320 | 8.00 | 10.42 | 270.41 | 188.55 | 304.00 | +33.59 |
| 375 | 8.00 | 10.42 | 270.41 | 188.55 | 359.00 | +88.59 |
| 812 | 11.37 | 10.42 | 275.46 | 191.92 | 789.26 | +513.80 |
| 1440 | 20.16 | 18.30 | 472.19 | 328.33 | 1399.68 | +927.49 |

The row fits all four buttons on one line at every width down to 320 CSS px (narrowest shipping iPhone); wrap would only occur below ~286 px. Hiding one button cannot change `#button-row` height. CSS `gap` renders nothing around a `display:none` item. FULLSCREEN is *not* meaningfully the widest label — 5.6907 em vs EXPERIMENT's 5.6537 em, a 0.65% difference. If you recompute these numbers, note `--value-size` is **redefined** at `:434` inside the `#experiment` rule (`:420-436`); `#button-row` (`:659`) is a sibling of `#experiment` (`:669`) and uses the `:root` value.

### Constraints and risks

| Item | State |
|---|---|
| Cascade | The complete list of button selectors is `button` (`:382-393`), `button:active` (`:394`), `button.on` (`:395`), `button[disabled]` (`:396`), `.xp-row button` (`:519-523`). None sets `display`. `#button-row { display:flex }` (`:374`) applies to the container. `.hidden` is `!important` — the hide cannot lose. |
| Media query | `@media (max-width:900px), (orientation:portrait)` (`:579`) sets `#button-row { justify-content: center }` (`:580`), specificity (1,0,0), same as `:373` but later in source so it wins. With three buttons the row still centres. No rule targets `#btn-fullscreen` at any breakpoint. |
| HDMI-GUI parity | No divergence. `simple_gui.py` has zero `fullscreen` occurrences — it owns the DRM plane and is inherently full-screen. FULLSCREEN is web-only chrome, like EXPERIMENT. |
| CI — token gate | `tools/design_token_diff.py:46` sets `TEMPLATE = "src/module/app/templates/template.html"`; `css_tokens()` does `src.find(":root")` and parses only the first `:root` block (`:29-52`). A JS edit ~1700 lines below cannot move it. |
| CI — field gate | Not the only gate that reads the template. `.github/workflows/checks.yml:112` runs `tools/gui_field_extract.py --max-unresolved 0`, which opens the template at `:117`/`:133`/`:139` — `web_consumed()` does a whole-word search for every HDMI field name, `socket_events()` regexes `socket\.on\(['"]([a-z_]+)['"]`. The fullscreen block contains neither, so this edit is safe — but `web_consumed()` is *removal*-sensitive, so verify rather than assume on any future template deletion. |
| CI — docs gate | Editing `docs/web-gui.md` is gated by `tools/docs_drift_check.py --strict` (`checks.yml:97`), which validates every backticked file citation (`CITE_RE` at `tools/docs_drift_check.py:126`) and every internal link. A qualifier containing a backticked path must name a file that exists. |
| CI — nothing lints JS | `checks.yml` runs ruff (`src/` only), pytest, shellcheck, and the six contract-drift tools. `docs.yml` builds MkDocs. There is no HTML or JS linter and no browser test. A syntax error inside the IIFE (`:677-1780`) ships with green CI as a fully dead page. **Loading the harness after editing is mandatory, not optional.** |
| Fullscreen is treated as protected state elsewhere | `src/module/app/__init__.py:51` suppresses the mid-take browser reload with the comment `# reload would kick the operator out of fullscreen mid-take.` Do not describe FULLSCREEN as inconsequential chrome. |
| Adjacent bug, out of W5's brief | `template.html:1673` is `socket.on('reload_browser', () => window.location.reload());` and `app/__init__.py:58-65` fires that on a 2 s timer after every completed resolution switch while **not** recording. A full reload drops fullscreen. So on iPad and desktop — exactly where the button works — an idle resolution change kicks the operator out of fullscreen 2 s later. The guard at `:48-52` covers only the recording case. File as its own row; do not fix inside W5. |
| Interaction with other W items | None. Single-surface (`settings_editor.html` has zero `fullscreen` hits). Note the style split: `template.html` is `const`/arrow, `settings_editor.html` is `var`/ES5 — match the file you edit. |

### Decision required from the operator

1. **Hide or disable.** The plan says hide. `button[disabled] { opacity: 0.45; cursor: default; }` already exists at `:396`, so `fsBtn.disabled = true; fsBtn.title = 'not supported by this browser';` is a one-line alternative that keeps the row balanced and explains itself. Layout is safe either way (table above).
2. **Scope.** D1 (probe + hide) is W5's stated brief. D2 (label desync) and D3 (unhandled rejection) are real, verified, and in the same 14 lines. Fold them in, or land D1 only and file D2/D3 as new PLAN.md rows.
3. **Docs.** Whether `docs/web-gui.md:29` gets a qualifier in the same PR, and with what wording — e.g. "fullscreen toggle (hidden on browsers with no element-fullscreen API, such as iPhone Safari)".
4. **Is iPad a supported operator device?** If yes the button must survive there, and BCD flags a forced overlay button that cannot be disabled plus swipe-down-exits. Whether that is acceptable during a take is an operator call.
5. **Which iPhone/iOS.** If the operator's phone runs an iOS that has shipped element fullscreen, the probe correctly keeps the button and the "dead on iPhone" headline is stale for that device — the unguarded `.call` at `:1769` is still a genuine defect on any engine lacking the API. Only the phone settles this.

## W6 — Dead theme CSS in the settings editor

**Do not execute `PLAN.md:34` literally.** It says "~150 lines of dead theme CSS … Delete the dead palettes". The real dead count is **42 lines**: 40 lines of dead `[data-theme]` palettes (66-105), plus the empty `.console` rule at 672, plus the shadowed `--line` at 47. The `:root` palette the row calls dead is live and load-bearing: it paints the raw-file drawer, every toast and the confirm modal, and it supplies the only declaration of `--focus`. Deleting it as written removes every keyboard focus indicator on the page and turns three surfaces transparent.

All file references below are `src/module/app/templates/settings_editor.html` unless stated, at dev tip 981b6bf1, and every line number was re-read in the tree.

### What is wrong

Four palette blocks exist. Only two are dead.

| Block | Lines | Status | Why |
|---|---|---|---|
| `:root{}` — light "paper" | 19-41 | **LIVE** | Inherited by everything outside `#app`; sole declaration of `--focus` (line 40) |
| `@media (prefers-color-scheme: dark){ :root{} }` | 42-65 | **LIVE** | Same, when the operator's OS is dark; re-declares `--focus` at 63 |
| `:root[data-theme="dark"]{}` | 66-85 | DEAD | Never matches |
| `:root[data-theme="light"]{}` | 86-105 | DEAD | Never matches |

Two independent facts make the "paper" palette live.

1. **`--focus` is not shadowed.** `:root` declares 21 custom properties. `#app.skin-hud` (890-911) declares 20. The set difference is exactly `{--focus}`. Five rules pair `outline:none` with `box-shadow: var(--focus)`:

```
238:  .btn:focus-visible{ outline:none; box-shadow: var(--focus); }
320:  .page-tabs button:focus-visible{ outline:none; box-shadow: var(--focus); }
390:  .field-input:focus-visible, select.field-input:focus-visible{ outline:none; box-shadow: var(--focus); }
409:  .toggle:focus-visible{ outline:none; box-shadow: var(--focus); }
709:  .json-tabs button:focus-visible{ outline:none; box-shadow: var(--focus); }
```

Per CSS Custom Properties L1, `var()` inside a custom property is substituted where the property is **declared**. `--focus: 0 0 0 2px var(--bg), 0 0 0 4px var(--accent)` therefore resolves against `:root`'s colours and inherits already-resolved into `#app`. Every focus ring on the page is currently paper-orange or amber, not HUD green.

2. **Four nodes live outside `#app`.** A `<div>` balance over 980-2232 gives 305 opens / 305 closes with depth first reaching zero at **line 2232** — `#app` closes there. These are siblings, not descendants:

| Element | Line | var()-dependent? |
|---|---|---|
| `.json-scrim#jsonScrim` | 2234 | No — literal `rgba(0,0,0,.3)` at 718 |
| `.json-drawer#jsonDrawer` (+ head/tabs/body/foot/icon-btn, 689-725) | 2235-2249 | **Yes** |
| `.toast#toast` (728-737) | 2251 | **Yes** |
| `.modal-scrim#modalScrim` | 2253 | No — literal `rgba(0,0,0,.4)` at 740 |
| `.modal#confirmModal` (+ `h3`/`p`/`.btn`s, 742-750) | 2254-2261 | **Yes** |

There is no `#app.skin-hud .json-*`, `.toast` or `.modal` rule anywhere (all 42 `skin-hud` hits sit in 890-977 plus the markup at 980). So those three surfaces resolve against `:root` and flip with the operator's OS colour scheme on a page that is otherwise permanently black.

Measured consequences today (recomputed WCAG 2.x, surface named):

| Surface | Light OS | Dark OS | Inside `#app` |
|---|---|---|---|
| `#confirmModal` background | `#ffffff` | `#1a1713` | would be `#0c0b09` |
| `#toast` bg / text | `#211d17` / `#f7f3ec` | `#f2ede4` / `#100e0c` (cream toast on black HUD) | — |
| `.modal` / `.toast` border-radius | 5px | 5px | 0px |
| `.json-tabs button` radius | 3px | 3px | 0px |
| Focus ring outer, on `--panel` `#0c0b09` | `#a6631c` = 4.14:1 | `#dd9a45` = 8.23:1 | HUD `#90ee90` would be 13.88:1 |
| Focus ring inner, on `--panel` | `#f7f3ec` = 17.79:1 | `#100e0c` = 1.02:1 (invisible) | — |

Neither the media block nor the `data-theme` blocks redeclare `--radius`/`--radius-lg`, which is why the radii stay 3px/5px in both OS schemes.

Genuinely dead, verified:

| Item | Lines | Note |
|---|---|---|
| `:root[data-theme="dark"]` + `:root[data-theme="light"]` | 66-105 (40 lines) | `data-theme` appears only at 66, 86, 672 — zero hits in the 2475-line script region; `documentElement` count = 0 file-wide |
| `:root[data-theme="light"] .console, .console{ }` | 672 | Empty body, emits nothing |
| `--line: #33301f2b;` | 47 | Immediately overwritten by `--line: #363026;` at 48 |
| `background: #0c0a08;` inside `.console` | 667 | Beaten everywhere by `#app.skin-hud .console{ background:#000; … }` (974); both `.console` nodes (1993, 2208) are inside `#app` |
| Paper literals surviving inside the HUD | 667, 677-679 | `.console` `color:#d8cdb8`, `.tag-ok #8fce87`, `.tag-warn #e0ac5c`, `.prompt #7a7263`. Line 974 overrides only `background`, so these render. Not reachable by deleting `:root`, and no HUD substitute is defined anywhere. **Out of scope for W6** — file as a new PLAN.md row |

### Current state at dev tip 981b6bf1

- **No drift.** `git diff 4affc53e 981b6bf1 -- src/module/app/templates/settings_editor.html` = 61/37 across 30 hunks; grepping that diff for `--focus|:root|skin-hud|json-drawer|class="modal"|class="toast"` returns zero hits. The theme region is byte-identical to when the plan was written. Nothing here is already fixed.
- **Every line number shifted +2** since 4affc53e: the first hunk is `@@ -1,4 +1,6 @@`, adding `<!DOCTYPE html>` and the viewport meta. Numbers in this section are correct at 981b6bf1. Older notes citing this file are off by two — do not "correct" a number in this section against them.
- `grep -c 'prefers-color-scheme'` is **1** today, and that hit is line 42, the colour block itself. Line 878 is `prefers-reduced-motion` and does not match.
- No `color-scheme:` declaration exists in the file. `services/cinemate-recovery/cinemate-recovery.py:702` has `:root { color-scheme: light dark; }` as precedent.

### What to change

**Option A — promote the HUD palette to `:root` (recommended).** Net effect: zero computed-style change for anything inside `#app`, and the drawer/toast/modal/focus-ring stop flipping with the OS.

1. In the surviving `:root{}` (19-41), replace the 20 palette values on lines **20-39** with the `#app.skin-hud` values verbatim from **891-910**. Keep `--focus` on line 40 unchanged — it re-resolves automatically to `0 0 0 2px #050403, 0 0 0 4px #90ee90`. Add `color-scheme: dark;` to the same block.
2. Delete lines **42-65** — the whole `@media (prefers-color-scheme: dark)` block. Now redundant.
3. Delete lines **66-105** — both `:root[data-theme=…]` blocks. Line 106 is blank, 107 is `*{ box-sizing: border-box; }`; the cut is clean.
4. Delete line **672**.
5. Delete the `#app.skin-hud{ … }` variable block, lines **890-911**, only. **Keep 912-977 unchanged** — the bare `#app.skin-hud,` selector at 912 starts the DIN font override and every rule below is component behaviour, several hardcoding literals that are not tokens.
6. Drop the now-dead `background: #0c0a08` on line **667**. Leave the three paper *text* literals on 667 and 677-679 alone — no HUD substitute exists for them and inventing one is not cleanup. They are already recorded above as a separate finding.
7. Update `PLAN.md:34` per *Ledger edits*.

**Option B — move the nodes instead** (smaller diff, no palette edit): move lines 2234-2261 to just before the `</div>` at 2232 so they become children of `#app`. Verified safe today: all four are `position:fixed`, and `.app` (134-144, plus 146 which sets only `grid-template-*`) has no `transform`, `filter`, `perspective`, `contain` or `will-change` — `grep -n 'will-change\|contain:\|perspective\|backdrop-filter'` over the file returns nothing, so the viewport stays their containing block. Fragile: adding any of those to `.app` later silently reparents four fixed elements with no test covering it. Option A has no such tripwire.

**Option C — reconnect a real toggle** (the plan's fallback): only if a daylight/outdoor light mode is actually wanted. Requires a control, persistence, setting `data-theme` on `documentElement`, **and** moving the HUD palette off `#app.skin-hud` onto `:root[data-theme="hud"]` so the toggle reaches the out-of-`#app` surfaces. A toggle that only flips `#app` reproduces today's bug.

**Never:** delete lines 19-41 or 42-65 without re-homing `--focus` first.

### How to prove it

Static. No hardware needed.

| Check | Command | Proof |
|---|---|---|
| `data-theme` gone | `grep -n 'data-theme' src/module/app/templates/settings_editor.html` | no output |
| media block gone (option A) | `grep -c 'prefers-color-scheme' src/module/app/templates/settings_editor.html` | `0` (was `1`) |
| `--focus` survives | `grep -c -- '--focus' src/module/app/templates/settings_editor.html` | `6` (1 declaration + 5 consumers; was 7) |
| Token parity inside `#app` | extract every `--name:` from the new `:root` and diff against the old `#app.skin-hud` block from `git show 981b6bf1` | identical 20 names/values, plus `--focus` and `color-scheme` |

CI gates that must stay green — run all four, not just the first:

```
python3 tools/design_token_diff.py --repo . --strict          # checks.yml:107
python3 tools/gui_field_extract.py --repo . --max-unresolved 0 # checks.yml:112
python3 tools/link_frequency_drift_check.py --repo . --strict  # checks.yml:115
python3 -m pytest _test/ -q
```

`design_token_diff.py` never reads this file (`TEMPLATE = "src/module/app/templates/template.html"`, line 46; it takes only `src.find(":root")`, 139-142) — a failure there means something unrelated broke. `gui_field_extract.py:160` and `link_frequency_drift_check.py:30` **do** parse `settings_editor.html`, but as regex/JS parsers, so a CSS-only edit is safe; run them anyway. Three tests read the file (`_test/test_action_catalogues_agree.py:29`, `_test/test_log_encode_normalization.py:47`, `_test/test_b95_config_defaults_consistency.py:62`); none assert on CSS, so **no test can catch a CSS regression here** — the greps above are the only guard.

Browser confirmation at `http://cinepi.local:5000/settings-editor`, optional but cheap. Before the edit, with the OS in light mode: `getComputedStyle(document.getElementById('confirmModal')).backgroundColor` returns `rgb(255, 255, 255)`; in dark mode `rgb(26, 23, 19)`. After: `rgb(12, 11, 9)` in both. Regression guards, after: tab to a `.btn` and assert `getComputedStyle(btn).boxShadow !== 'none'`; open the drawer and assert `getComputedStyle(document.getElementById('jsonDrawer')).backgroundColor !== 'rgba(0, 0, 0, 0)'`; same for `#confirmModal` and `#toast`.

### Constraints and risks

| Risk | Detail |
|---|---|
| **Dropping `--focus`** | Highest. `box-shadow` becomes invalid-at-computed-value-time → initial `none`; the same rules set `outline:none`, so the page loses every keyboard focus indicator. WCAG 2.4.7 regression, silent, invisible to the suite. |
| **Deleting `:root` 19-41 or 42-65 wholesale** | `.json-drawer`, `.toast`, `.modal` lose background/border/color/radius — transparent slabs. The toast has 30+ `showToast()` call sites and is the primary feedback channel. |
| **Off-by-one at 47/48** | Adjacent, near-identical `--line` lines. Deleting 48 instead of 47 leaves an 8-digit hex (`#33301f2b`, alpha 0x2b) → 83%-transparent borders outside `#app` in dark OS. |
| **Off-by-one at 672** | Line 672 also carries a bare `.console` selector. It is an empty rule, so deleting the whole line is a no-op — but deleting the real `.console{…}` at 666-671 instead breaks both consoles (1993, 2208). |
| **Option A is a visual change** | Drawer, toast and confirm modal go from paper/warm-dark to HUD black, square corners, DIN instead of serif (the font override at 912-921 is scoped to `#app.skin-hud` descendants). Do not ship this under a "remove dead CSS" commit message. |
| **HDMI-GUI parity** | This file's HUD palette is a hand-written second copy of `simple_gui.py`'s colours (`#90ee90` lightgreen, `#ffdd00` zoom_hi, `#ff33ff` sync, `#ff4136` lock) that `design_tokens.py` does **not** cover — only `template.html` is under the pipeline. Editing 890-911 touches that untracked duplication. Bringing it under the pipeline would require extending `design_token_diff.py`'s parser (first `:root` of `template.html` only) — out of scope for W6. |
| **iframe** | `<iframe id="liveEmbedFrame" src="/">` at 2226 embeds `template.html`. Its palette is independent and unaffected. Any "the whole page is now one palette" claim in a commit message is false for that region. |
| **W-item interaction** | Two, both in this document. W7 edits `.topbar` (174-186) and restructures 987-1006. W10 inserts `.clip-progress` CSS after `:793` and reads `#app.skin-hud` (890-911) as its contrast basis. Sequence W6 first — *Order of work*, row 6. |

### Decision required from the operator

**Yes — one call, before any code is written: A, B or C.**

- The 42-line deletion (66-105 = 40, plus 672, plus 47) is mechanical and belongs in whichever option ships.
- Whether the raw-file drawer, the toast and the confirm modal should turn HUD-black is a design decision, not a cleanup. Nothing in the repo settles it: `system-review/decisions/ADR-001-gui-harmonization.md` never mentions light/dark/theme/skin/paper (grep count 0), and there is no `docs/settings-editor.md`.
- If a daylight/outdoor light mode is wanted, nothing should be deleted from the palettes and option C is the answer — the opposite of what the plan proposes.
- Context for the decision: PLAN.md:34's own evidence cell says the light-scheme test "rendered dark" mid-session. That is consistent with this finding — `#app` is the one region genuinely immune. The plan recorded the symptom and drew the opposite conclusion.

## W7 — Save can scroll out of reach

All work is in one file: `src/module/app/templates/settings_editor.html` (the settings-editor page served at `/settings-editor`). Line numbers below are dev tip `981b6bf1` and were re-read against the tree.

### What is wrong

`.topbar` is a nowrap flex row that hides its own scrollbar. `#saveBtn` is its last child, so on a narrow viewport Save sits past the right edge with no scrollbar, no fade, no chevron.

| Fact | Location | Source text |
|---|---|---|
| Topbar scrolls inside itself, scrollbar suppressed | 174-186 | `min-width: 0; overflow-x: auto; scrollbar-width: none;` and `.topbar::-webkit-scrollbar{ display:none; }` |
| Save is the last of 10 children | 1005 | `<button class="btn btn-primary" id="saveBtn" disabled>Save changes</button>` |
| Unsaved chip carries `hidden` | 996 | `<span class="pill" id="dirtyPill" hidden>…` |
| `.pill` sets `display:flex` — author rule beats UA `[hidden]{display:none}` | 220 | `display:flex; align-items:center; gap:6px;` |
| `.btn` sets `display:inline-flex; flex:0 0 auto` — same defeat, and buttons never shrink | 232-233 | `display:inline-flex; align-items:center; gap:7px;` / `flex: 0 0 auto; white-space: nowrap;` |
| Hamburger breakpoint shows the menu button only; it does not move Save | 197 | `@media (max-width: 860px){ .hamburger{ display:flex; } }` |
| `#saveBtn` click is the ONLY code path that PUTs either file | 3770 | `document.getElementById('saveBtn').addEventListener('click', …` |
| "Save & reboot Pi" does not save | 2204 label; handler 4716-4724 | handler calls only `runBootSequence` (4629), which is `setTimeout` line-painting + `showToast`, zero `fetch` |

Measured in headless Chrome 149 against this exact template (fonts are base64 data URIs at lines 6-7, so headless metrics equal real metrics):

| Viewport | Save right edge | On screen? |
|---|---|---|
| 320 / 360 / 375 / 393 / 430 | 784.91 | no — 409.91 px past the edge at 375 |
| 784 | 784.91 | no |
| 785 | 784.91 | yes (crossover) |
| 860 | 842 | yes |
| 861 / 900 / 960 / 973 | 973.91 | no — desktop dead band |
| 974+ | 973.91 | yes (crossover) |

Two clip bands, not one. Crossing 861 → 860 *rescues* Save, because the 860px query drops the 232px `.brand` column (136 → 146) while the hamburger costs only 29+14=43px: net +189px. Child widths at 375px: hamburger 29.00, `.search` 60.00, `.topbar-spacer` 0.00, `#dirtyPill` 97.63, `#openJson` 132.77, `#revertBtn` 68.69, `#downloadBtn` 86.83, `#uploadBtn` 70.88, `#saveBtn` 109.13, gaps 14, padding 18 each side → `scrollWidth` 803.

Save is reachable but undiscoverable: `topbar.scrollLeft = 99999` lands at 428 and Save's right edge becomes 356.91. `offsetHeight 56 − clientHeight 55` is the 1px border-bottom (178), not a scrollbar. The bar is `position: sticky`, so it never moves out of the way.

Second, independent bug found in the same pass — the `hidden` attribute is inert wherever an author rule sets `display`. Verified by measurement, not inference:

| Element | Line | `hasAttribute('hidden')` | computed `display` | measured size |
|---|---|---|---|---|
| `#dirtyPill` | 996 | true | `flex` | 97.63 px wide, renders "0 UNSAVED" permanently |
| `#saveBtn` `#openJson` `#revertBtn` `#downloadBtn` `#uploadBtn` on the RAW/Live tabs | 997-1005 (`#openJson`'s `<button>` opens at 997; `:999` is its inner `<span id="openJsonLabel">`) | true | `flex` | 109.13 / 132.77 / 68.69 / 86.83 / 70.88 — `syncTopbarForPage()` (4570-4582) is dead for all five |
| `#welcomeImgClear` (`.icon-action`, 797-800) | 1107 | true | `flex` | 30.00 × 30.00 — "Remove image" always visible; the toggles at 3295/3305 do nothing |
| `#cfg-cam0-link-card` / `#cfg-cam1-link-card` (`.card`, 338-345) | 2127 / 2137 | true | `grid` | 834.00 × 88.88 each on the config tab — `card.hidden = !cfgSupportsLinkFreq(sensor)` at 3169 is dead |

`[hidden]` DOES work on `#uploadInput`, the four `[data-page-lede]` `.lede` paragraphs, and both `.cfg-link-warn` spans — those have no author `display`.

No keyboard escape hatch: `grep -c 'metaKey\|ctrlKey'` = **0**. No unsaved-changes guard: `grep -c 'beforeunload'` = **0**. The drawer footer (2246-2248) offers only Copy.

### Current state at dev tip 981b6bf1

- W7 is **still true and unfixed**. `.topbar` (174-186), the child order (987-1006), `#dirtyPill` (996) and `#saveBtn` (1005) are byte-identical to what the C8 plan reviewed.
- The one relevant drift since the plan: PR #160 added `<!DOCTYPE html>` (line 1) and `<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">` (line 3). Before that, a 375px phone rendered at a 980px layout viewport where Save's right edge (973.91) cleared by 6.09px — visible, drawn ~41.7 physical px wide. #160 was correct, but it turned W7 from "tiny but present" to "409.91px off screen".
- `dev-track/C8-web-ui-review/PLAN.md:25` still reads "Nothing below is started. W1 is a decision, not a patch" — stale on both halves. Correcting it is assigned in *Ledger edits*, not here.
- Contrast is fine — this is purely reachability. `#app.skin-hud` (890-899) is the palette in force: Save enabled `#04210c` on `#90ee90` = 12.07:1; disabled 3.82:1; chip idle 5.70:1; chip dirty 5.94:1.

### What to change

Do **A** and **B** together. B alone leaves four dead-`hidden` defects; A alone is insufficient — with A only, `scrollWidth` drops 803 → 691 and Save needs a 674px viewport, still off screen on every phone.

**A. Make `hidden` work.** Add one rule near the `.pill`/`.btn` block. Use the four-selector form — the narrower `#dirtyPill[hidden], .btn[hidden]` covers only 6 of the 8 broken sites and ships a half-fix:

```css
#dirtyPill[hidden], .btn[hidden], .icon-action[hidden], .card[hidden]{ display:none !important; }
```

The global `[hidden]{display:none !important}` is more correct but has a 25-site blast radius (10 markup `hidden` attributes, 15 `.hidden =` assignments). If you take the global form, enumerate first with `grep -o '<[^>]* hidden[ >]'` and `grep -n '\.hidden = '` and check every page tab by hand.

**B. Pin Save and the chip outside the scroller.** Restructure 987-1006 — wrap the middle band, leave hamburger, chip and Save as direct `.topbar` children:

```html
<header class="topbar">
  <button class="hamburger" id="hamburger" …>…</button>
  <div class="topbar-scroll">
    <label class="search">…</label>
    <div class="topbar-spacer"></div>
    <button class="btn btn-ghost" id="openJson" …>…</button>
    <button class="btn btn-ghost" id="revertBtn" …>Revert</button>
    <button class="btn btn-ghost" id="downloadBtn" …>Download</button>
    <button class="btn btn-ghost" id="uploadBtn" …>Upload</button>
  </div>
  <input type="file" id="uploadInput" accept=".json,.jsonc,.txt" hidden>
  <span class="pill" id="dirtyPill" hidden>…</span>
  <button class="btn btn-primary" id="saveBtn" disabled>Save changes</button>
</header>
```

Keep `.topbar-spacer` INSIDE the scroller — it is what right-aligns the ghost buttons at wide widths. `#uploadInput` genuinely computes `display:none`, so its position is free.

CSS, replacing 174-186 (move `overflow-x` off `.topbar` onto the new child; delete the retargeted `.topbar::-webkit-scrollbar` rule at 186):

```css
.topbar{
  grid-area: topbar;
  display:flex; align-items:center; gap:14px;
  padding: 0 18px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
  position: sticky; top:0; z-index: 20;
  /* Only the middle band scrolls. #dirtyPill and #saveBtn are pinned outside
     .topbar-scroll so the one action that matters cannot scroll out of reach;
     min-width:0 still stops the PAGE scrolling sideways. */
  min-width: 0;
}
.topbar-scroll{
  flex: 1 1 auto; min-width: 0;
  display:flex; align-items:center; gap:14px;
  overflow-x: auto; scrollbar-width: none;
}
.topbar-scroll::-webkit-scrollbar{ display:none; }
#dirtyPill, #saveBtn{ flex: 0 0 auto; }
```

No JS changes are required — there is still exactly one `#saveBtn`, so `updateDirtyPill()` (3223-3232) and `syncTopbarForPage()` (4570-4582) keep working untouched.

Optional, independent, cheap: a document-level Cmd/Ctrl+S that calls `saveBtn.click()` only when `!saveBtn.disabled`, and `preventDefault()` only when it actually handles the event. Also consider a `beforeunload` guard gated on `dirtyEls.size || configDirty` — 3 lines, and today there is nothing stopping a user losing every edit.

A sticky bottom save bar was considered and rejected: it needs a new element, `env(safe-area-inset-bottom)` padding, a `.main` bottom-padding change, per-page show/hide, and either moves `#saveBtn` (breaking desktop balance) or duplicates it (two elements whose `disabled`/`hidden` must stay in sync). Fix B is one wrapper div and ~6 CSS lines.

### How to prove it

The template has exactly ONE Jinja expression — `var API_TOKEN = {{ api_token | tojson }};` at line 2270. Substitute that one string and the file needs no Flask server.

**Do not use `chrome-headless-shell`.** It is not on PATH on this machine, and `--window-size` is silently ignored under headless with `--dump-dom` here (you get a 500×725 viewport), which would invalidate every px number below. Use the `preview_*` tools against the `settings-editor-harness` config (port 8792) — note it is hard-wired to `development/worktrees/settings-editor-fixes` and must be re-pointed at `$TREE` — and set each viewport with `preview_resize`, asserting `window.innerWidth` before measuring. See **Verification and gates → Driving it with the preview_\* tools**.

| Check | Baseline (must reproduce first) | Pass condition after A+B |
|---|---|---|
| Topbar width @375 | `.topbar` `scrollWidth` = 803, `#saveBtn` right = 784.91 | — |
| Primary gate: Save on screen | fails at 320/360/375/393/430 | `saveBtn.getBoundingClientRect().right <= innerWidth && .left >= 0` at all five; prototype measured **302 / 342 / 357 / 375 / 412** |
| Desktop dead band | right = 973.91 at 861/900/960/973 | right = **882** at 900px; re-check 861, 870, 973 |
| `hidden` works | `#dirtyPill` `hasAttribute('hidden')===true` with `display:'flex'`, width 97.63 | `display:'none'`, width 0 |
| RAW-tab leak | click `[data-page-tab="raw"]`; all five controls `display:flex`, `scrollWidth` still 803 | all five `display:'none'`; `scrollWidth` ≈ 330 |
| Config-tab leak | click `[data-page-tab="config"]`; both link cards 834.00 × 88.88 while `hidden` | both `display:'none'`, width 0 |
| No sideways page scroll | — | `documentElement.scrollWidth == innerWidth` at 360/375/393/430/861/900/973/1024/1440 |
| 320px caveat | `documentElement.scrollWidth` = **352** vs innerWidth 320 **already, before any change** | must stay 352 — "not worse", not "fixed" |
| Inner scroller still scrolls | — | `.topbar-scroll.scrollLeft = 99999` lands positive (prototype: scrollWidth 489 vs clientWidth 173 @375) and `#saveBtn`'s rect does not move |
| Wide-width layout | `.search` = **314.05px** @1440 | `.search` ≈ **370px** @1440 — this GROWS by design. Fix A frees 97.63+14 = 111.63px inside the scroller, and `.search{flex:1 1 120px}` (200) + `.topbar-spacer{flex:1 1 auto}` (212) split it. Do **not** gate on 314 — that rejects a correct implementation. |
| Token gate | `python3 tools/design_token_diff.py --strict` exits 0 today | still 0. It reads only `src/module/simple_gui.py` (45) and `template.html` (46) — a failure means you edited the wrong file. |

Device check no harness substitutes for: load `http://cinepi.local/settings-editor` on a real phone in portrait, change one field, confirm the chip appears (it must NOT read "0 unsaved" when clean) and Save is visible with no horizontal scrolling.

### Constraints and risks

| Risk | Detail |
|---|---|
| The original bug the `overflow-x` rule fixed | The comment at 181-183 records that `overflow-x:auto` exists to stop the PAGE scrolling sideways. `min-width:0` must stay on `.topbar` AND be set on `.topbar-scroll`. This is the single most likely way to get the fix wrong. |
| `overflow-y` side effect | `.topbar` today computes `overflow-y: auto` (spec-derived from `overflow-x: auto` + `visible`). Removing `overflow-x` restores true `visible`. Desirable for a sticky header, but any descendant relying on the 56px row clipping vertically will now escape it. |
| Tight middle band | Pinned Save (109.13) + hamburger (34) leaves ~118px of scroller at 320px and ~173px at 375px, against `.search{min-width:60px}` (200). Raising the search min-width later can push Save off again. |
| Visible behaviour changes beyond "Save is reachable" — put all four in the PR body | (1) the permanent "0 UNSAVED" chip starts disappearing; (2) file controls vanish on RAW/Live; (3) the "Remove image" button and the two CSI-2 link cards stop rendering when they should be hidden; (4) an accidental escape hatch closes — today `updateDirtyPill` (3231) leaves Save *enabled* on RAW/Live when settings are dirty, and because `hidden` is ignored it is still clickable and its handler falls through to the settings PUT. After Fix A it correctly disappears. |
| a11y win worth noting | Because `hidden` only ever acted through the UA rule, those five "hidden" controls stay focusable and exposed to AT on RAW/Live today. Fixing the cascade fixes tab order for free. |
| Chip reorders | Fix B moves `#dirtyPill` from 4th child (left of the ghost cluster) to the right of all four ghost buttons, adjacent to Save. Arguably an improvement, but it is a visible desktop change — state it, don't ship it silently. |
| HDMI-GUI parity | Does **not** bind. ADR-001 (`system-review/decisions/ADR-001-gui-harmonization.md`) governs `simple_gui.py` ↔ `template.html`; `settings_editor.html` has no HDMI counterpart. Say so in the PR so a reviewer does not reject on parity grounds. |
| No CI guard | `tools/design_token_diff.py` cannot see this file. There is no automated guard on `settings_editor.html` layout — verification is by measurement, not CI. Still run `.github/workflows/checks.yml`. |
| Cmd/Ctrl+S | Shadows the browser's Save-Page shortcut on every tab. Gate on `!saveBtn.disabled`; `preventDefault()` only when handled. Helps desktop only, not phones. |
| Ordering vs other W items | If W6 (dead `:root` palettes overridden by `#app.skin-hud`) lands in the same pass, sequence W6 first — anyone measuring colours here hits the `#app.skin-hud` trap at 890. |

### Decision required from the operator

1. **Pin the chip too, or only Save?** Recommended: pin both. The chip is the only signal that unsaved work exists, and it costs 97.63px of scroller. Pinning it also relocates it (see risks).
2. **Short label under ~400px?** At 320-375px the scroller has only 118-173px left. Swapping "Save changes" → "Save" below a breakpoint buys back ~50px. Unverified px saving — measure if adopted.
3. **Scroll affordance on `.topbar-scroll`?** Edge fade or chevron, versus accepting silent truncation now that the critical action is outside it.
4. **`#cfgRebootBtn` (2204, "Save &amp; reboot Pi")** — should it save? It currently only animates. It is the button a user hits precisely when they cannot find the real Save. Either wire it to the config PUT or relabel it "Reboot Pi". Out of scope for W7 as a code change, but the decision belongs with this finding.
5. **Add Cmd/Ctrl+S and a `beforeunload` guard in this pass?** Both are independent of the layout fix and cheap.
6. **Scope floor:** if sub-360px viewports are out of scope, the scroller gets noticeably more room and item 2 becomes unnecessary. If the editor is laptop-first rather than phone-first, the 861-973px dead band is the more common failure.

## W8 — Wrapped-portrait select overlap (accepted trade-off)

Not fixed at dev tip. Reproduces exactly. Scope is one CSS line plus a comment rewrite.

All geometry below is headless Chrome, devicePixelRatio 1, real DIN2014 faces, viewport forced by a same-origin iframe. Nothing here is device-verified on iOS/WebKit — see "Decision required".

### What is wrong

The live web GUI top row wraps to two lines on every phone-portrait width. Rows sit 4px apart. Each `<select>` hit area bleeds 8px past its group box vertically. The lower row's select therefore wins a 4.000px strip of the upper row's groups: a tap on the bottom of FPS opens the RESOLUTION picker.

| Fact | file:line | Source text / measured value |
|---|---|---|
| Enlarged hit area, no width/height | `src/module/app/templates/template.html:138-146` | `.group select { position: absolute; inset: -8px -6px; opacity: 0; border: 0; cursor: pointer; -webkit-appearance: none; appearance: none; }` |
| Trade-off comment (one word wrong, both numbers right) | `template.html:127-137` | `…the only cost is ambiguity where the top row wraps on a portrait phone: rows sit 4px apart there, so a lower row's select reaches ~4px into the row above…` |
| Row gap, the only rule setting it | `template.html:90-96` | `#top-row { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: calc(var(--gap) * 0.5) var(--gap); }` |
| `--gap` floors at 8px | `template.html:47` | `--gap: clamp(8px, 1.4vw, 22px);` — 1.4vw reaches 8px only at 571.43px, above every wrap threshold, so the wrapped row gap is **always** 4px |
| Only `@media` in the file; touches neither rule | `template.html:579-586` | `#button-row`, `.vu-track`, `#experiment`, `.xp-slider .label` |
| `#app` top padding clips row-0 selects | `template.html:82` | `padding: calc(var(--gap) * 0.6) var(--gap);` → 4.797px, so 3.203px of every row-0 select sits above the layout viewport |

Measured at 375×812, `?state=idle`:

| Quantity | Value |
|---|---|
| `getComputedStyle('#top-row').rowGap` | `4px` |
| `.group` boxes, row 0 (g-fps/g-shutter/g-exp/g-iso/g-wb) | y[4.797, 22.797], h 18.000 |
| `.group` box, row 1 (g-res) | y[26.797, 44.797], h 18.000 |
| `s-res` top | 18.797 → intrusion = 22.797 − 18.797 = **4.000px** |
| `elementFromPoint(95.2, 18.8)` / `(95.2, 16.8)` | `select#s-res` / `select#s-shutter` |
| `?state=warn`, `elementFromPoint(44.8, 18.8)` / `(44.8, 16.8)` | `select#s-wb` / `select#s-fps` |

Why the lower row wins: all five selects are `position:absolute; z-index:auto` and `.group` is `position:relative; z-index:auto` (no stacking context), so hit order is DOM order and the later element wins. Confirmed empirically, not only by spec.

Cost: in the collision columns the upper group's reachable tap band drops from 34px to 18.797px — roughly the pre-#160 18px, i.e. PR #160's own gain is cancelled for those groups. (The purely geometric uncontested band is 22.000px; 18.797px is what a finger can reach, because `#app`'s 4.797px top padding puts the rest off-viewport.)

Wrap thresholds, bisected: two rows at ≤548px (idle/rec/dual) and ≤563px (warn, whose locked pills are wider). One row at ≥549 / ≥564. The row never splits into three lines down to 320px. So every phone portrait width wraps, no phone landscape width does, and the fix below can only ever add one gap.

Collision count (groups geometrically overlapped by a row-1 select): 5 at 320 and 360, 3 at 375 and 393, 2 at 412/430/480/540. At 375 idle those three are g-fps, g-shutter, g-exp; only the first two own a `<select>`, so only two lose a tap band.

**Two distinct quantities, do not merge them.** The *group intrusion* is **4.000px** — how far a row-1 select reaches into a row-0 group *box* (22.797 − 18.797). The *select-to-select overlap* is **12.00px** — how far the two 34px hit areas overlap *each other*: 8px of bleed below row 0 plus 8px above row 1, less the 4px row gap. Row-0 select bottom 30.797, row-1 select top 18.797. The battery reports it as `oy` on four pairs. A 16px row gap closes both (8 + 8 = 16). The template comment's "4px" is the first quantity and is correct.

Four claims measurement disproves. Do not repeat them:

| Claim | Truth |
|---|---|
| "the overlap is MUTUAL — row 0 also reaches 4px into row 1" | Geometrically true, operationally void. Every column where a row-0 select bleeds down is also covered by a row-1 select, which wins by DOM order. Probes at 375×812 idle: `elementFromPoint(30, 28)`, `(30, 30.5)`, `(30, 20)` all return `s-res`, never `s-fps`. The defect is one-directional. Say "the lower row's select wins a 4px strip of the row above". |
| "a tap on those descender pixels" is literally accurate | No. Baseline y = 18.117 (4.797 + 0.320 half-leading + 13.000 ascent). Deepest ink of any selectable value = 18.268. The band starts at 18.797, i.e. 0.529px below the deepest descender. The band is line-box leading and contains zero glyph ink. |
| Selects are "56×34" | Height is uniformly 34; widths are not uniform and none is 56. At 375×812 idle: 55.219, 110.469, 54.219, 85.469, 186.438 — over groups of 43.219 / 98.469 / 42.219 / 73.469 / 174.438, all 18.000 tall. "44×18 → 56×34" is rounded prose copied from `dev-track/C8-web-ui-review/PLAN.md:17`, not a measurement. |
| g-exp's `1/52` has ink in the stolen band | False at 375 (the width everything else is measured at). `v-exp` spans x[195.313, 230.656]; `s-res` ends at x=188.438. The stolen columns of g-exp are x[170.344, 188.438] — the `EXP` label. True only at 320 and 360. |

### Current state at dev tip 981b6bf1

- **Not fixed, not drifted.** `template.html:138-146` and `:127-137` are byte-identical to what PR #160 landed in `4b3d5093`. `git log 4affc53e..981b6bf1 -- src/module/app/templates/template.html` returns exactly `d6c1a0c3`, `4b3d5093`, `1675ca66`, `a5a86358`, `94f80e54`; none touches the select rule or `#top-row`'s gap (`a5a86358` mentions `#top-row` only in prose at `template.html:410`).
- Pre-#160 rule, from source at `4affc53e:src/module/app/templates/template.html:129-133`: `position: absolute; inset: 0; width: 100%; height: 100%;`. #160 deleted the two longhands.
- `.group select` matches exactly five elements (`s-fps`, `s-shutter`, `s-iso`, `s-wb`, `s-res`, markup at `template.html:595/599/606/610/615`). The EXPERIMENT drawer's runtime selects are under `.xp-select` / `.xp-group`, never `.group`. Bottom-row groups (`template.html:635-637`) have no selects.
- **A claimed W2 regression is false — do not carry it.** It is sometimes said that the left rail worsened from 444/282 to 542/260 at 812×375 because of the EXPERIMENT drawer commits. That is an idle-vs-warn state mismatch. Measured at both `4affc53e` and `981b6bf1`: idle = 446/282, warn = 542/260, byte-identical across commits. `#experiment` carries `class="hidden"` (`template.html:669`) with `.hidden { display: none !important; }` (`template.html:541`) and sits outside `#stage`. No regression.
- The shared clone `/Users/patrikeriksson/Documents/cinemate/cinemate` is **not** on dev — it was on `claude/cinemate-docs-review-h4pxp6` at `6663e84e` when this was written. Work in `$TREE`, per *Before you touch anything*.

### What to change

**One line.** Raise `#top-row`'s row gap to twice the select's vertical bleed. At 16px the two hit areas meet edge-to-edge with zero overlap.

Edit `src/module/app/templates/template.html:90-96`:

```css
#top-row {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: baseline;
    /* Row gap must be at least twice .group select's 8px vertical bleed,
       or the two wrapped rows' invisible hit areas meet in the middle and
       the lower row's picker wins the upper row's bottom 4px. Inert
       whenever the row does not wrap, so it costs nothing at any width the
       HDMI GUI has a counterpart for. */
    gap: max(16px, calc(var(--gap) * 0.5)) var(--gap);
}
```

`max()` is always 16px today (`--gap` caps at 22px, so `calc(--gap * 0.5)` caps at 11px); it documents the coupling and survives a future `--gap` raise.

**Also rewrite the comment at `template.html:127-137`.** Keep the px-not-em rationale. The two numbers in it are right; the phrase "a tap on those descender pixels" is wrong — the band is line-box leading and contains zero glyph ink (proved below). Correct statement: where the top row wraps, the lower row's select wins a 4px strip of the row above, cancelling this rule's own tap-target gain for the two affected groups; `#top-row`'s row gap is what prevents it, so the two rules are coupled.

**Do NOT ship the "cap the vertical extension" option.** Both formulations measured, both bad:

| Formulation | Measured result |
|---|---|
| `inset: calc(-1 * min(8px, var(--gap) * 0.25)) -6px` | `--gap` is small at every real width, so the bleed resolves to 2px/side. Select height collapses to **22.000px at 375×812 and 23.656px at 812×375** — it defeats #160 in landscape too, where nothing wraps. This expression appears nowhere in PLAN.md; `PLAN.md:36` states no formula. Treat it as the trap, not the instruction. |
| `inset: -4px -6px` | Intrusion exactly 0, `#top-row` stays 40px — but the select drops 34 → 26px at **every** width, paying back part of #160 everywhere. |
| Either, gated on a breakpoint | Rejected because it makes a hit-target detail state-dependent for a 4px gain, and the breakpoint would have to be ≥564 to cover warn's 549–563 wrap band. **Not** because width media queries are banned in this file — `:579` already is one, and W1 adds a second. B11.7/F-297 removed the portrait *restack* (see the comment at `:563-578`), not width queries. |

**iOS 14.0–14.4: out of scope, but `PLAN.md:38-40`'s stated reason is measurably wrong on both halves.** Correcting that prose is part of W8's comment work. **Write no CSS for it.**

> Explicitly **not** doing: the `inset` shorthand's lack of a fallback for iOS 14.0–14.4 (that window is the only engine that renders this page but drops `inset`; the degradation is a worse tap target, not a broken page).

MDN browser-compat-data: `css.properties.inset` → safari `14.1`, safari_ios `mirror`; `css.properties.row-gap` flex_context → safari `14.1`, safari_ios `mirror`. Both land in the same release, so that engine drops `inset` **and** flexbox gap together — simulated, `#top-row` goes 40 → 36px, the wrapped rows touch at 0px, `g-fps` 43.219 → 37.625px. W8's 4px premise does not exist there. And the degradation is worse than "a worse tap target": with `inset` dropped, the selects fall to their static position at intrinsic size — 15×15, 34×15, 30×15, 39×15, 68×15, `coversGroup=false` for all five. The picker no longer covers the text it controls.

### How to prove it

Harness: rebuild it first. See **Verification and gates → Rebuild the harness**. Do not measure the checked-in `index.html`.

Measure inside a fixed-width same-origin iframe or via `preview_resize`, and assert `window.innerWidth`. Chrome clamps `--window-size` to a 500px minimum on macOS, and because `--gap`/`--value-size`/`--label-size` all sit on their clamp floors below ~571px, every y-coordinate is identical at 375 and 500 — a bad run looks right and only the collision count differs.

| Step | Assertion that counts as proof |
|---|---|
| Reproduce | `?state=idle` @375×812: `rowGap === '4px'`; `g-fps` {y 4.797, h 18.000}; `g-res` {y 26.797, h 18.000}; `s-res.top === 18.797`. Intrusion 4.000. |
| Prove the lower row wins | `elementFromPoint(95.2, 18.8).id === 's-res'` and `(95.2, 16.8).id === 's-shutter'`. `?state=warn` @x=44.8: 18.8 → `s-wb`, 16.8 → `s-fps`. That 2px flip is the whole finding. |
| Confirm the fix | With the change: `rowGap === '16px'`; `#top-row` height 40 → 52; every select still exactly 34.000 tall; `s-fps.bottom === 30.797 === s-res.top` (zero overlap); `elementFromPoint(95.2, 21.8) === 's-shutter'` (idle) and `(44.8, 21.8) === 's-fps'` (warn). |
| Confirm it is free in landscape | @812×375 `?state=warn`, before/after must be identical: `#top-row` height 18/18, `#rail-left` scrollHeight/clientHeight 542/260 in both, `#stage` height 259.922 in both. |
| Confirm it is free in portrait | @375×812 `?state=warn`: `#rail-left` 668/668 → 656/656 (scrollHeight === clientHeight both ways, so nothing new is hidden). idle 671/671 → 659/659. The 12px comes out of `#stage`, which has slack. |
| Re-bisect the wrap threshold if fonts, `--value-size` or the value strings change | Binary-search iframe width, cluster `.group` rects by `rect.top`. Expect 1 row from 549 (idle/rec/dual) and 564 (warn). |
| Contract gates | From the repo root, all three must exit 0: `python3 tools/design_token_diff.py --repo . --strict`; `python3 tools/gui_field_extract.py --repo . --max-unresolved 0`; `python3 tools/docs_drift_check.py --repo . --strict`. |
| Device gate (harness cannot do this) | On a real iPhone/Android in portrait, top row wrapped: tap the bottom edge of FPS and SHUTTER and record which picker opens, before and after. |

### Constraints and risks

- **Contract gates cannot see this change, unconditionally.** `tools/design_token_diff.py` `css_tokens()` reads only the first `:root` block — `start = src.find(":root")` / `block = src[start:src.find("}", start)]` at `tools/design_token_diff.py:140-143`. No declaration on `#top-row` or `.group select` is parsed by that tool at any value. (The name filter at `:167-168` excluding `gap`/`value-size`/`label-size`/`box-size`/`box-height` is a second, weaker line of defence; the value-shape filter at `:164-165` is a third. Cite the `:root`-only scan, not the name filter.)
- **HDMI-GUI parity is not at risk from the row-gap change.** `src/module/simple_gui.py:1734-1736` — `_top_row_layout` justifies six groups between `TOP_ROW_LEFT_X` and `RES_RIGHT_ANCHOR` on a fixed canvas with no wrapped state. `row-gap` is inert when a flex container does not wrap. But any change that alters `#top-row`'s height in the non-wrapping case **would** break parity, so the 812×375 and desktop-width height assertions above are mandatory.
- **Residual cost, confined.** +12px of `#top-row` at viewports that wrap **and** are short — resized desktop windows and Android split-screen landscape; no phone is both. Extra hidden left-rail content, `?state=warn`: 548×400 244→256, 540×360 284→296, 500×320 343→355, 480×300 363→375 (~+4%). Zero at 812×375 and zero at 375×812.
- **Interaction with W1.** W1 is settled, not open: the rails stay left and right at every viewport and the layout shrinks to fit, so W8 does not disappear with it. Sequence W8 *after* W1 all the same — W1 changes the portrait geometry this row gap sits in, so measure the wrap once W1's shrink has landed.
- **`#top-row`'s wrap is outside the operator ruling.** The ruling scopes to `#stage`'s three columns and `.rail`'s direction. `#top-row` carries `flex-wrap: wrap` and wraps at every phone-portrait width; that is pre-existing, accepted behaviour, and W8's fix (+12px of row gap) entrenches it rather than removing it. Say so in the commit body so it does not read as a reflow shipped against the ruling.
- **Interaction with W2.** W8 costs zero glyph legibility; W2 hides the storage filesystem badge outright at 812×375. If only one lands this cycle, land W2. Do not let W8's +12px in the wrapped-and-short case be confused with W2's existing overflow.
- **WebKit unverified — check first.** All numbers are Chrome headless. WebKit's flex baseline alignment could yield a group height other than 18.000, which would move the 4.000px figure. The DOM-order tiebreak for two `z-index:auto` positioned siblings is per spec and should hold, but is unverified there.
- `PLAN.md:17` and `PLAN.md:38-40` both need correcting — see *Ledger edits*.

### Decision required from the operator

1. **Comment-only fallback.** If the row-gap change is not wanted, does the operator still want `template.html:127-137` corrected? As written it misnames the band ("descender pixels" — the band has zero glyph ink), which is exactly how a recorded trade-off gets rediscovered as a bug. Default: yes, correct it either way.

## W9 — Clip download, server half (NEW, not in the plan)

Not a W1–W8 item. `dev-track/C8-web-ui-review/PLAN.md` contains no finding about the RAW pane, downloads, takes or clips. The operator's report is the claim. Nothing here is already fixed at dev tip.

### What is wrong

One download route exists in the whole tree. It builds a complete zip on disk before any byte reaches the client.

| Fact | Location | Verified source |
|---|---|---|
| Download route builds the zip, then sends it | `src/module/app/settings_editor.py:486-502` | `zip_path = raw_files.build_take_zip(path)` at :492, `@after_this_request` at :494, `send_file(...)` at :502 |
| Temp file has no `dir=` → lands in `tempfile.gettempdir()` = `/tmp` on the Pi rootfs | `src/module/app/raw_files.py:175` | `fd, tmp_path = tempfile.mkstemp(prefix="settings-editor-", suffix=".zip")` |
| Whole take is walked and copied uncompressed before the response starts | `raw_files.py:179-183` | `zipfile.ZipFile(tmp, mode="w", compression=zipfile.ZIP_STORED)` over `sorted(path.rglob("*"))` |
| `%00` in `<name>` → HTTP 500, not 404 | `raw_files.py:145` | `except OSError:` — `Path.resolve()` raises `ValueError: lstat: embedded null character in path` and escapes it |
| No recording interlock on DELETE | `settings_editor.py:480-483` | `ok, message = raw_files.delete_take(name)` — nothing else |
| No recording interlock on bulk delete either | `settings_editor.py:505-518` | loops `raw_files.delete_take(name)` over an arbitrary `names` list |
| Format route DOES have the interlock — copy this | `settings_editor.py:545-549` | `if rec == "1": return jsonify({...}), 409` |
| Single download is a top-level navigation, so an error page replaces the settings editor | `templates/settings_editor.html:4043-4048` | `window.location = '/settings-editor/api/raw/takes/' + encodeURIComponent(name) + '/download';` |
| Bulk download fires `window.location` every 800 ms | `settings_editor.html:4084-4096` | `setTimeout(function(){ window.location = ... }, i * 800)` |
| Server is threaded Werkzeug dev server | `src/main.py:953` | `kwargs={'host': '0.0.0.0', 'port': 5000, 'allow_unsafe_werkzeug': True}` — no eventlet/gevent in requirements, so engineio resolves `async_mode='threading'` and flask_socketio calls `app.run(..., threaded=True)` |

Reproduced measurements:

- ENOSPC leaks the partial zip permanently. Monkeypatching `zipfile.ZipFile.write` to raise `OSError(28)` on the 3rd call left an orphaned `settings-editor-*.zip` in `gettempdir()`. The cleanup hook is registered at :494, after the build at :492, so a build failure never registers it.
- The cleanup order is the opposite of what it looks like. Instrumented run: `send_file called → temp exists True`, `body iteration STARTS → temp exists False`. Flask runs `after_request` in `finalize_request` **before** the WSGI server consumes the iterable; the transfer works only because werkzeug holds an open fd. Consequence: a client that aborts mid-transfer does **not** leak. The leak is exactly the exception path.
- Traversal is genuinely closed. `..`, `../secret`, `TAKE/../../secret`, `.`, `""`, `%2e%2e`, `..%2Fsecret.txt`, `%252e%252e`, and a symlinked take dir all return `None`.
- Size arithmetic: `docs/clear-hdr.md:20` — "Each 3840×2200 16-bit DNG is ≈ 16.9 MB". 240 frames (10 s @ 24 fps) ≈ 4.06 GB; 1440 frames (60 s) ≈ 24.3 GB of temp file on the rootfs.
- ZIP_STORED overhead is `30 + n` (local header) + `46 + n` (central dir) per file + 22 (EOCD), n = len(arcname). With a real CineMate arcname (n=38) that is **152 B/file**, measured exactly. Negligible against 16.9 MB, but do not quote a smaller figure.
- `resolve_take` returns the first matching root only. With the same take name on `/media/RAW` and `/media/RAW1`, `list_takes()` returns two rows (each tagged `storage`) but both rows' buttons hit the RAW copy — the template keys on `data-name` alone.
- `_is_take_dir` (`raw_files.py:51-55`) matches any dir with one `.dng`, so the take being recorded right now is listed, zippable and deletable.

Unverified — check first: the claim that the bulk `window.location` race means only the LAST take arrives. The code and the server-side "no headers until the zip is built" premise are both confirmed; the browser-navigation consequence was never driven in a browser. Treat as leading hypothesis.

### Current state at dev tip 981b6bf1

- `src/module/app/raw_files.py` is byte-identical to the plan's base commit 4affc53e (`git diff --stat 4affc53e..HEAD` empty).
- `settings_editor.py` changed 4/4 lines between those commits, all label strings inside `ACTION_METHODS`. Every RAW route line number above holds.
- The template changed 61/37 lines, but no diff hunk touches `raw/takes`, `bulkDownload`, `data-download` or `build_take_zip`.
- Nothing in this item is fixed.
- The `/api/v1` token gate at `api.py:83-92` is a **no-op on a stock install**: `web_api_settings.py:13` and `settings.jsonc:23` both ship `"token": ""`, and `api.py:87-88` is `if not token: return None`. Do not frame the settings_editor blueprint as "less protected" — by default neither is authenticated. (Note `api.py:85` is `current_app.config['SETTINGS']`, a bare subscript.)

### What to change

1. `raw_files.resolve_take` — widen the except and add a storage filter. Signature: `def resolve_take(name: str, *, storage: str | None = None) -> Path | None:` (the bare `*` is required if keyword-only is intended; `from __future__ import annotations` is already at `raw_files.py:16` so `str | None` is fine on the Pi's 3.11). Change `except OSError:` at :145 to `except (OSError, ValueError):`. Add `if storage and root.name != storage: continue` inside the root loop. Both existing callers (`settings_editor.py:488`, `raw_files.py:153`) pass one positional arg and are unaffected.

   Thread `?storage=` through the two **single-take** routes that already have it available client-side (rows carry `t.storage`, `settings_editor.html:3979`): `GET .../download` (`settings_editor.py:486-502`) and `DELETE /api/raw/takes/<name>` (`:480-483`). `POST /api/raw/bulk` (`:505-518`) takes a bare `names` list and stays name-only — **the duplicate-name ambiguity therefore remains open on bulk delete, which is a data-loss path.** Do not close it by inventing a wire format. File it as a candidate PLAN.md row, and say in the report that "Delete selected" is first-match-wins across `/media/RAW` and `/media/RAW1` until it is closed.

**Items 2 and 3 are conditional.** They exist solely to feed `showDirectoryPicker`. **Write them only if the operator answers W10 decision 1 "yes".** W10's own evidence says the picker cannot work on the real origin, so the likely answer is no — in which case skip straight to item 4, which is the whole of W9.

2. *(gated)* NEW `GET /settings-editor/api/raw/takes/<name>/files?storage=RAW1` — the manifest the folder picker needs. Body: `{"ok": true, "take": ..., "storage": ..., "file_count": N, "total_bytes": B, "recording": bool, "files": [{"name": "f000001.dng", "size_bytes": ..., "mtime": ...}]}`. `sorted()`, `is_file()` only, names relative to the take dir. 404 → `{"ok": false, "message": "Take 'X' not found"}`.

3. *(gated)* NEW `GET /settings-editor/api/raw/takes/<name>/files/<path:filename>` — `return send_from_directory(path, filename, conditional=True, max_age=0)`. Use `send_from_directory`, not `send_file`: werkzeug's `safe_join` is the traversal guard. Measured on a real server: good name → 200 with `Content-Length`, `Accept-Ranges: bytes`, stable `ETag`; `Range: bytes=0-99` → **206** with `Content-Range`; `../../etc/passwd` and `..%2F..%2Fetc%2Fpasswd` → 404 both. It returns `Content-Disposition: inline`, not `attachment` — fine for the fetch path, pin it explicitly if the endpoint ever becomes user-clickable. **Its 404 is werkzeug's HTML page, not JSON, unlike every other route in this blueprint.** That is accepted: nothing but `fetch` reads it, and adding a blueprint `errorhandler(404)` would change the body of the existing JSON routes too. State it in the commit body.

4. CHANGED `GET .../download` — stream the zip, no temp file. The existing docstring rejects streaming ("a hand-rolled streaming encoder risks silently corrupt downloads"); that objection does not apply, because stdlib `zipfile` handles a non-seekable sink itself. Verified end to end: `zf._seekable == False`, `testzip()` returns `None`, `namelist()` correct, bodies byte-exact, macOS `unzip -t` "No errors detected".

```python
class _StreamSink(io.RawIOBase):
    def __init__(self): self._buf = bytearray()
    def writable(self): return True
    def write(self, b): self._buf += b; return len(b)
    def drain(self):
        chunk = bytes(self._buf); self._buf.clear(); return chunk

def stream_take_zip(path: Path):
    sink = _StreamSink()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for f in sorted(path.rglob("*")):
            if not f.is_file():
                continue
            zi = zipfile.ZipInfo.from_file(f, arcname=f"{path.name}/{f.relative_to(path)}")
            zi.compress_type = zipfile.ZIP_STORED
            with zf.open(zi, "w") as dest, open(f, "rb") as src:
                while (chunk := src.read(1 << 20)):
                    dest.write(chunk)
                    if (out := sink.drain()):
                        yield out
            if (out := sink.drain()):
                yield out
    if (out := sink.drain()):
        yield out
```
Route side: `Response(stream_with_context(raw_files.stream_take_zip(path)), mimetype="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})`. Chunked transfer is confirmed working on this exact server (real `curl` against a threaded werkzeug: `Transfer-Encoding: chunked`, no `Content-Length`, `unzip -t` clean). No reverse proxy exists anywhere in the repo to buffer it.

5. Imports in `raw_files.py:18-22` — **add `import io`** (needed by `_StreamSink(io.RawIOBase)`; the current imports are `logging, shutil, tempfile, zipfile, pathlib, psutil`, with no `io`) and **delete `import tempfile` at `:20`**. `tempfile` is used only inside `build_take_zip`, `ruff.toml` selects `F401`, and CI runs `ruff check src/`. Reproduced: leaving it gives `F401 tempfile imported but unused --> raw_files.py:20:8`. `zipfile` at `:21` stays (used by `stream_take_zip`).

6. Delete `build_take_zip()`. Its only caller is `settings_editor.py:492`, plus the comment at `settings_editor.html:4085-4088` that cites its docstring — update that comment in the same change or it becomes a lie.

   Imports in `settings_editor.py:19-27` — currently `Blueprint, after_this_request, current_app, jsonify, render_template, request, send_file`. Add `Response` and `stream_with_context` (and `send_from_directory` only if items 2/3 are in). Remove `after_this_request` and `send_file` once `/download` no longer uses them, or `F401` fails CI.

7. Recording interlock. Add `raw_files.active_take_names(redis_controller) -> set[str]` reading `last_dng_cam0` / `last_dng_cam1` and taking `Path(v).parent.name`, skipping `""` and the literal `"None"`. Those keys hold a full DNG path (`docs/redis-keys.md:80`; written at `cinepi_multi.py:323`, key name built at :293) and are reset to `"None"` on start_all/stop_all, not on record stop — so AND the result with `is_recording == "1"`. `app.config['REDIS_CONTROLLER']` already exists (`app/__init__.py:69`).

   Three response shapes, written out so they are not invented:

   - `DELETE /api/raw/takes/<name>` on an active take — copy the format route's precedent verbatim (`settings_editor.py:549`):
     `return jsonify({"ok": False, "message": "Refusing to delete while recording"}), 409`
   - `POST /api/raw/bulk` — **whole-request 409**, not a per-name refusal. The route today returns `{"ok": all_ok, "results": {name: {...}}}`; a partial delete that silently skipped the recording take is worse than a refusal the operator can see. Check the whole `names` list first:
     `return jsonify({"ok": False, "message": "Refusing to delete while recording", "recording": sorted(active & set(names))}), 409`
   - `/download` and the manifest stay **allowed**. `/download` returns a zip stream with no JSON envelope, so it cannot carry `recording: true` — only the manifest reports it, as a body field. Do not add a header for it.

8. Concurrency cap. Module-level `threading.BoundedSemaphore(2)`, acquired **non-blocking in the route**. The release point is the part that is easy to get wrong:

   - `@after_this_request` and request teardown both run at `finalize_request`, **before** the WSGI server consumes the response iterable (proved in *What is wrong*). Releasing there is a no-op for the case the cap exists to protect.
   - Release inside the generator, wrapped in `try/finally`, so a client abort — which raises `GeneratorExit` into the generator — still frees the permit. Without the `finally`, two aborts leak both permits and every subsequent download 429s forever.

   ```python
   def _guarded(gen, sem):
       try:
           yield from gen
       finally:
           sem.release()
   ```

   Acquire in the route with `sem.acquire(blocking=False)`; on failure return 429 `{"ok": false, "message": "A download is already in progress"}` with `Retry-After: 5`. **Client concurrency must be ≤ 2 to match**, or 4 parallel per-file fetches produce 429s on correct traffic — pick the two numbers together with W10 and say which you picked. Load-bearing, not polish: `threaded=True` puts no ceiling on concurrent full-bandwidth reads off the media volume, which is the storage contention already known to cause frame drops and ALSA xruns.

### How to prove it

| Check | Command | Passing number |
|---|---|---|
| `%00` no longer 500s | `client.get('/settings-editor/api/raw/takes/%00abc/download')` | **404** JSON (today: 500 HTML, measured) |
| No temp file during download | snapshot `glob(gettempdir()+'/settings-editor-*.zip')` before/after a full GET | set difference **empty** |
| ENOSPC no longer leaks | monkeypatch `ZipFile.write` → `OSError(28)` on 3rd call, run the route | **0** leaked files (today: 1, measured) |
| Streamed zip is valid | `data=b''.join(stream_take_zip(t))` | `ZipFile(BytesIO(data)).testzip() is None`, `namelist()` exact, bodies byte-equal |
| Wire format on the real server | `curl -sD- -o /dev/null http://cinepi.local:5000/settings-editor/api/raw/takes/<TAKE>/download` | `Transfer-Encoding: chunked`, `Content-Type: application/zip`, **no** `Content-Length`, TTFB **< 1 s** (today: minutes) |
| Range on per-file route *(gated on items 2/3)* | `curl -sD- -r 0-99 -o /dev/null .../files/f000001.dng` | **206** + `Content-Range: bytes 0-99/<size>` |
| Traversal still closed *(gated on items 2/3)* | `curl -s -o /dev/null -w '%{http_code}' .../files/../../etc/passwd` and `..%2F..%2Fetc%2Fpasswd` | **404** both |
| Recording interlock | start a take, `curl -X DELETE .../api/raw/takes/<ACTIVE>`; then the same via `POST /api/raw/bulk` | **409** both; a different take still 200; the bulk 409 is whole-request and deletes nothing |
| Concurrency cap | 3 concurrent curls | 3rd → **429** + `Retry-After: 5` |
| Cap releases on abort | start 2 downloads, `Ctrl-C` both mid-transfer, then start a 3rd | 3rd returns **200**. A 429 here means the `finally` is missing and the permits leaked |
| Desktop round-trip | unzip a real multi-GB take with `unzip -t`, macOS Archive Utility, Windows Explorer | DNG count == the take dir's own file count; a sample DNG opens in a raw converter |
| Folder-picker path *(gated on items 2/3)* | Chromium `showDirectoryPicker()` → per-file `getFileHandle(create:true)` + `createWritable()` + the pump in W10 change 6 | `du -sb` of the saved folder **==** manifest `total_bytes` |
| CI | `python3 -m pytest _test/ -q -p no:randomly` and `ruff check src/` | both green off-hardware |

**New tests are required, not optional.** This item adds a streaming generator, a recording interlock and a semaphore, and nothing in the existing suite covers any of it. The fixture to copy is `_test/test_settings_editor_format.py:45` — `make_app(redis_values=None, with_executor=True)` builds a bare Flask app with `settings_editor_bp` registered and a fake redis in `app.config['REDIS_CONTROLLER']`. Two sibling files (`test_settings_editor_backup.py`, `test_web_api_blueprint.py`) establish the convention for this blueprint. Add, in one new `_test/test_raw_files_download.py`:

| Test | Asserts |
|---|---|
| `%00` in the name | 404 with a JSON body, not 500 |
| `stream_take_zip` round-trip | `ZipFile(BytesIO(b''.join(...))).testzip() is None`, `namelist()` exact, bodies byte-equal |
| Recording interlock, DELETE | 409, take still on disk |
| Recording interlock, bulk | whole-request 409, **nothing** deleted |
| Semaphore | 3rd concurrent acquire → 429 + `Retry-After`; and a permit released after a generator is closed early (`gen.close()`) |
| Traversal on the per-file route *(only if items 2/3 shipped)* | 404 for `../../etc/passwd` and `..%2F..%2Fetc%2Fpasswd` |
| Manifest shape *(only if items 2/3 shipped)* | keys present, `file_count` matches the fixture, 404 body is JSON |

Pi baseline to capture BEFORE changing anything: `findmnt /tmp`, `df -h / /tmp`, `ls -la /tmp/settings-editor-*.zip`. Anything in that last listing is already-leaked evidence (an in-flight transfer's temp file is already unlinked and therefore invisible, so a hit there is a past failure, not a live download).

### Constraints and risks

- CI jobs that exist at 981b6bf1: `lint` (`ruff check src/`), `test` (`pytest _test/ -q -p no:randomly`), `shell`, `drift` (six named tools: docs_drift_check, findings_disposition_check, design_token_diff, gui_field_extract, link_frequency_drift_check, redis_key_diff). **There is no requirements-drift job** — the stale comment in `requirements.txt` claiming one is wrong; `checks.yml` explicitly does not `pip install -r requirements.txt`. Keeping imports stdlib-only (`io`) is still correct, just not for that reason.
- `tools/docs_drift_check.py --strict` will not fire: no file under `docs/` cites `raw_files.py` or `settings_editor.py` with a line number. Renumbering these modules is safe.
- **No docs change is required for W9.** `docs/changelog.md:49` already advertises "browse, download or format the RAW drive from the RAW files pane", which stays true; the two new endpoints (if items 2/3 ship) are internal to the pane and there is no `docs/settings-editor.md` to add them to — creating one is out of scope. If bulk download's *behaviour* changes, that is W10's docs obligation, not W9's.
- HDMI-GUI parity does not apply — the RAW pane has no `simple_gui` counterpart, and no design tokens change.
- Archive format changes: streamed entries always carry data descriptors (`flag_bits=0x8`, measured). ZIP64 is **conditional**, not automatic — a small test fixture stays `extract_version=20`; ZIP64 records appear only once sizes/offsets exceed 32-bit limits. Do not go looking for ZIP64 in a 400 KB fixture. The desktop round-trip gate still stands for real multi-GB takes.
- Losing `Content-Length` on /download is a real browser-UX regression: no size, no ETA, no resume. Today's response does carry it (measured). The per-file path gets progress from the manifest instead.
- Werkzeug sends `Connection: close` on every response (hardcoded), so a 1400-DNG per-file save costs 1400 TCP handshakes. Client concurrency must be **≤ 2** to match the server semaphore, or specify 429 + `Retry-After` backoff in W10. Pick both numbers in one decision.
- `_test/test_settings_editor_format.py` imports `raw_files` and patches `raw_files.storage_summary`. Keeping `storage` keyword-with-default preserves it.
- Listing cost is 3 directory walks per Refresh, not 1: `_is_take_dir` globs (`raw_files.py:53`), `_take_info` iterdirs + stats each entry (`:63-65`), and `storage_summary` walks every take dir again (`:127`) — and `refreshRawPane()` hits both endpoints. Six call sites: `settings_editor.html:3954, 3957, 4056, 4069, 4080, 4101`. No polling timer exists. Out of scope for W9 but do not make it worse.

### Decision required from the operator

1. What is actually observed — a browser error page replacing the settings editor, a hang with no download entry, a 0-byte file, or (with "Download selected") only one take arriving? Each maps to a different mechanism above, and none of them was observed on the operator's device. Nothing in this item has been exercised against real storage, a real take, or a real browser.
2. `findmnt /tmp` + `df -h /` on the Pi: rootfs ENOSPC (likely) vs tmpfs RAM exhaustion tripping the 80% auto-stop.
3. Browser/OS: `showDirectoryPicker()` is Chromium-desktop only. Is "use Chrome on a laptop" acceptable, or is a fallback needed?
4. Hotspot AP or LAN? That is the throughput ceiling and sets per-file concurrency.
5. Hide the actively-recording take from `list_takes()`, badge it, or leave it? Server reports `recording: true` either way.
6. Add an `X-Cinemate-Token` gate to the settings_editor blueprint? Note it would be inert by default, same as `/api/v1`.
7. Multi-take streaming zip now? The original objection ("briefly doubles disk usage") disappears with streaming.

## W10 — Clip download + destination folder, client half (NEW, not in the plan)

Nothing here is already fixed at dev tip. This item is **not** in `dev-track/C8-web-ui-review/PLAN.md` — that findings table is W1–W8 (`PLAN.md:29-36`) and `grep -niE "download|raw pane|raw files" PLAN.md` returns nothing. All work lands in `/Users/patrikeriksson/Documents/cinemate/cinemate` (the read-only pinned tree used for these line numbers is a different checkout). Confirm your branch is based on dev tip `981b6bf1` before trusting any line number below — the local clone was on `claude/cinemate-docs-review-h4pxp6` @ `6663e84e` when this was written.

**Read this first: the folder picker cannot work on the real origin.** `window.showDirectoryPicker` is `[SecureContext]`-gated.

| Fact | Evidence |
|---|---|
| The server has no TLS | `src/main.py:953` runs `socketio.run` with `{'host': '0.0.0.0', 'port': 5000, 'allow_unsafe_werkzeug': True}` — no `ssl_context` |
| Nothing terminates TLS in front of it | no nginx/Caddy/certbot in `cinemate-install.sh` or `services/` |
| Operators reach it over plain HTTP | `http://10.42.0.1:5000` (`docs/web-api.md:17`), `http://cinepi.local:5000` (`docs/web-gui.md:10`) — neither is a potentially-trustworthy origin |
| "Just enable TLS" is not available | `docs/building-control-units.md:45` and `:112` both hardcode `const char* CAM = "http://10.42.0.1:5000";` |
| **Unverified — check first** | That `window.showDirectoryPicker === undefined` and `isSecureContext === false` there. This is spec reasoning, not a browser observation. Prove it before writing a single line of picker code |

### What is wrong

| # | File:line | Verified source | Defect |
|---|---|---|---|
| 1 | `settings_editor.html:4046` | `window.location = '/settings-editor/api/raw/takes/' + encodeURIComponent(name) + '/download';` | Per-row download is a top-level navigation, not a download-attributed anchor. |
| 2 | `settings_editor.html:4090-4093` | `names.forEach(function(name, i){ setTimeout(function(){ window.location = ... }, i * 800); });` | Bulk fires N navigations 800 ms apart. Not a naked loop — the stagger exists and is still far too short. |
| 3 | `settings_editor.py:492` then `:502` | `zip_path = raw_files.build_take_zip(path)` … `return send_file(zip_path, as_attachment=True, download_name=f"{name}.zip")` | The entire zip is built before any header is emitted. TTFB = full zip build time, so the 800 ms stagger cannot serialise anything. |
| 4 | `raw_files.py:175-183` | `tempfile.mkstemp(prefix="settings-editor-", suffix=".zip")` … `zipfile.ZIP_STORED` … `zf.write(f, arcname=f"{path.name}/{f.relative_to(path)}")` | Every byte of the take is copied to the system `/tmp` first. Arcnames already prefix `<take>/`. |
| 5 | `settings_editor.py:489-490` | `return jsonify({"ok": False, "message": f"Take '{name}' not found"}), 404` | Not an attachment, so `window.location` **commits** the navigation and replaces the editor with raw JSON. |
| 6 | `settings_editor.html:2280`, `:3227`, `grep -c beforeunload` = 0 | `var dirtyEls = new Set();` / `var n = dirtyEls.size;` | A committed navigation silently discards every unsaved `settings.jsonc`/`config.txt` edit. No unload guard exists. |
| 7 | `settings_editor.html:2226` | `<iframe id="liveEmbedFrame" class="live-embed-frame" src="/" …>` | The same navigation tears down the live GUI iframe — socket.io connection and MJPEG preview both drop. |
| 8 | `settings_editor.py:505-511` | `if action != "delete" or not isinstance(names, list): return jsonify(...), 400` | There is no bulk-download endpoint. A one-request combined zip does not exist server-side. |
| 9 | — | — | No progress UI, no cancel, no error surface on either path. A minutes-long silent TTFB reads as a dead button. |

Not wrong, despite what the symptom suggests: the filename **is** set (`download_name=f"{name}.zip"`, `:502`) and `Content-Length` is present, so a percentage progress bar is feasible. A 500 renders Flask's generic "Internal Server Error" page, **not** a traceback — debug is never enabled (`SocketIO(app)` at `src/module/app/__init__.py:15`, no `debug` kwarg at `src/main.py:953`).

Corroborating prior art already in-repo: `system-review/deliverables/FORMAT-DRIVE-PLAN.md:66-68` — "The server is threaded werkzeug … and take-zip downloads already block requests this long. No background thread, no job queue." (that doc says `main.py` line 937; the call is now at 953). `system-review/FINDINGS.md:219` (F-295) already moved the bulk buttons below the list; the fix comment survives at `settings_editor.html:2059-2060`.

### Current state at dev tip 981b6bf1

- Blueprint prefix is `/settings-editor` (`settings_editor.py:43-46`, registered unconditionally at `src/module/app/__init__.py:82`), so every URL above is correct as written.
- `requirements.txt` lists only `flask` (:16) and `flask_socketio` (:17) — no eventlet/gevent, `SocketIO(app)` passes no `async_mode`. Werkzeug runs threaded. N selections really do mean N concurrent full-take copies into `/tmp`.
- `services/cinemate-autostart/cinemate-autostart.service` sets no `PrivateTmp=` and no `TMPDIR=`, so `mkstemp` uses the real system `/tmp`. **Unverified — check first:** whether `/tmp` is tmpfs on this image (`findmnt /tmp`). If it is, `build_take_zip` writes a whole take into RAM and that is a more urgent bug than anything in this section.
- `refreshRawPane()` (`:4021-4024`) is **not** polled — `grep -c setInterval` = 0. Its only callers are `:3954`, `:3957`, `:4056`, `:4069`, `:4080`, `:4101`.
- JS idiom: `grep -cE 'async function|await |=> *\{'` = 0, `grep -c "new Promise\|Promise\."` = 0, zero `const`, and every `let` hit is the English word inside a CSS comment. **ES5 syntax; ES6+ runtime APIs (`fetch`, `Set`) are already in use.** New code must be `var` + `function` + `.then`, but may use `Promise`/`AbortController`/`getReader()`.
- `python3 tools/design_token_diff.py --strict` exits 0. It reads only `SIMPLE_GUI = "src/module/simple_gui.py"` (`:45`) and `TEMPLATE = "src/module/app/templates/template.html"` (`:46`) — settings_editor.html is never read, so this gate cannot trip on your edits.
- `docs/changelog.md:49` advertises "browse, download or format the RAW drive from the RAW files pane". `docs/web-gui.md` mentions downloads **nowhere** — editing it is optional new documentation, not correcting an existing lie.

### What to change

**1. Replace `window.location` with an `<a download>` click.** The file already has the idiom at `:3824-3831` (`downloadText`: `a.href = url; a.download = filename;`). An anchor download is handed to the download manager, not the navigable, so a 404/500 can no longer replace the document. This alone removes defects 1, 5, 6, 7 and the mutual cancellation in 2.

```js
  var CAN_PICK_FOLDER = !!(window.isSecureContext && window.showDirectoryPicker);
  function takeDownloadUrl(name){
    return '/settings-editor/api/raw/takes/' + encodeURIComponent(name) + '/download';
  }
  // only used by the picker path (change 6); needs W9 item 3
  function takeFileUrl(name, file){
    return takeDownloadUrl(name).replace(/\/download$/, '/files/') + encodeURIComponent(file);
  }
  function downloadViaAnchor(url, filename){
    var a = document.createElement('a');
    a.href = url; a.download = filename; a.rel = 'noopener';
    document.body.appendChild(a); a.click(); a.remove();
  }
```

**2. Pre-flight against `/api/raw/takes`** (`settings_editor.py:475-477`, returns `raw_files.list_takes()`) before firing. It is cheap and catches the one predictable failure — take deleted or drive unmounted — without paying for a zip build. **Do not call `refreshRawPane()` from inside a download queue**: it rebuilds every row via `list.innerHTML = ''` (`:3974`) and rewires listeners (`:4004`), destroying the row holding the progress bar. Set a `refreshSuppressed` flag while a download is active, or refresh only after the queue drains.

**3. Per-row progress UI, reusing `.capacity-track` / `.capacity-fill`** (`:761-762`, live on the storage meter at `:3911`). Row markup ends at `:3996` with `        '</div>';` — **that line must first become `'</div>' +`** or appending is a syntax error. Then append:

```js
        '<div class="clip-progress">' +
          '<div class="capacity-track"><div class="capacity-fill" data-progress-fill style="width:0%"></div></div>' +
          '<span class="clip-progress-text" data-progress-text>Starting…</span>' +
          '<button class="icon-action" data-cancel-download title="Cancel" aria-label="Cancel download">' + CANCEL_ICON + '</button>' +
        '</div>';
```

Declare `CANCEL_ICON` beside the two that already exist — `DOWNLOAD_ICON` (`:3872`) and `DELETE_ICON` (`:3873`) — in the same idiom (`<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">` plus two crossing `<path>`s). Do not author a new icon language; the pane has exactly one.

Use `.icon-action` (`:797-800`, 30×30, `flex: none`) rather than `.btn.btn-ghost` (`:225-231`, ~33px tall) — it matches the row's existing control language beside an 8px track. CSS, inserted after `.clip-actions` at `:793`:

```css
  .clip-progress{ grid-column: 1 / -1; display:none; align-items:center; gap:10px; margin-top:9px; }
  .cliprow.is-downloading .clip-progress{ display:flex; }
  .clip-progress .capacity-track{ flex:1; }
  .clip-progress-text{ font-size:12px; color: var(--muted); font-variant-numeric: tabular-nums; white-space:nowrap; }
```

`grid-column: 1 / -1` spans both `grid-template-columns: 22px 1fr auto auto` (`:783`) and the ≤640px `20px 1fr` (`:811`), so the media query at `:810-813` needs no change and defines no conflicting rule. Specificity `.cliprow.is-downloading .clip-progress` (0,3,0) beats `.clip-progress` (0,1,0).

**4. Row lookup: do not hand-roll CSS escaping.** Take names come from directory names on removable media. Iterate `.cliprow` and compare `getAttribute('data-name')`, or use `CSS.escape`.

**5. Bulk path.** Operator decision 2; **default (b)** if unanswered.
- (a) Serialise anchor downloads behind one `showConfirm` that warns the browser may prompt to allow multiple downloads.
- (b) Disable "Download selected" for >1 with an explanatory tooltip until a server-side combined-zip endpoint exists. Simpler and honest.

**6. Picker path — write it only if the operator answers decision 1 "yes".** It depends on W9 items 2 and 3, which are themselves gated on the same answer. Capability-gated at every call site.

Constraints it must satisfy, all of which the prose version left to invention:

- ES5 syntax (`var` + `function` + `.then`; no `async`/`await`/arrow — `grep -cE 'async function|await |=> *\{'` must stay `0`).
- `createWritable()` **truncates on open**. Cancelling without an explicit cleanup leaves a truncated file, not a removed one. The cleanup contract is `writable.abort()` **then** `dirHandle.removeEntry(name)`.
- Strictly one take in flight. `showConfirm` (`:4206`) is callback-based — `function showConfirm(message, onYes, onCancel, opts)` with a single global pending slot (`pendingConfirmYes`/`pendingConfirmCancel`, `:4205`) that `:4213-4214` overwrites **without invoking either previous callback**. A second confirm therefore drops the first pair silently. Refuse to open an overwrite prompt while `confirmModal` has class `open`.
- Client concurrency ≤ 2, to match W9's server semaphore.

```js
  var pickerAbort = null;                 // AbortController for the take in flight
  function savePickedTake(dirRoot, take, files, onProgress){
    var total = files.reduce(function(a, f){ return a + f.size_bytes; }, 0), done = 0;
    pickerAbort = new AbortController();
    return dirRoot.getDirectoryHandle(take, { create: true }).then(function(dir){
      return files.reduce(function(chain, f){
        return chain.then(function(){
          var writable;
          return dir.getFileHandle(f.name, { create: true })
            .then(function(fh){ return fh.createWritable(); })
            .then(function(w){
              writable = w;
              return fetch(takeFileUrl(take, f.name), { signal: pickerAbort.signal });
            })
            .then(function(res){
              if (!res.ok) { throw new Error('HTTP ' + res.status + ' on ' + f.name); }
              var reader = res.body.getReader();
              function pump(){
                return reader.read().then(function(r){
                  if (r.done) { return writable.close(); }
                  done += r.value.length;
                  onProgress(done / total);
                  return writable.write(r.value).then(pump);
                });
              }
              return pump();
            })
            .catch(function(err){
              // truncate-on-open means a half-written file must be removed,
              // not just closed.
              var cleanup = writable ? writable.abort() : Promise.resolve();
              return cleanup
                .then(function(){ return dir.removeEntry(f.name); })
                .catch(function(){ /* best effort */ })
                .then(function(){ throw err; });
            });
        });
      }, Promise.resolve());
    });
  }
```

Error taxonomy — map each to a toast, do not let any reach the console unhandled:

| `err.name` | Cause | Toast |
|---|---|---|
| `AbortError` | operator hit Cancel, **or** dismissed the picker dialog | "Download cancelled" — not an error |
| `NotAllowedError` | permission denied on the directory handle | "Permission denied for that folder" |
| `SecurityError` | call reached a non-secure context (a `CAN_PICK_FOLDER` gate is missing) | "Folder picker unavailable here" + fall back to the anchor path |
| `QuotaExceededError` | destination disk full | "Not enough space in that folder" |
| anything else | — | the message verbatim, prefixed "download failed — " |

**7. Honest destination hint** under `#clipListFooter` (`:2057`): when `CAN_PICK_FOLDER` is false, tell the operator the page is served over plain HTTP so it cannot open a folder picker, and to enable "Ask where to save each file" in the browser.

**Do not** adopt a blob-buffered fetch (fetch → Blob → object URL) as the default. It buffers the whole take in memory and will OOM the tab on a multi-GB take on iOS Safari or low-memory Android.

### How to prove it

| Check | Command / expression | Proof value |
|---|---|---|
| Secure-context verdict (decides the feature) | On the hotspot, `http://10.42.0.1:5000/settings-editor` console: `JSON.stringify({secure: window.isSecureContext, picker: typeof window.showDirectoryPicker, origin: location.origin})` | `{"secure":false,"picker":"undefined","origin":"http://10.42.0.1:5000"}` → picker-as-primary is dead. Repeat on `cinepi.local:5000`. |
| Picker reachable at all | `ssh -L 5000:localhost:5000 pi@cinepi.local`, then same snippet on `http://localhost:5000` | `{"secure":true,"picker":"function"}`. If not true here, delete the picker branch entirely. |
| Stagger is hopeless | `time curl -s -o /dev/null -D - "http://localhost:5000/settings-editor/api/raw/takes/<TAKE>/download" -w '%{time_starttransfer}s TTFB / %{size_download} bytes\n'` | Any `time_starttransfer` > 1.0 s proves `i * 800` at `:4093` cannot serialise. Record the real number — no estimate exists. |
| Mutual cancellation (dev tip) | Select 3 takes → "Download selected" → DevTools Network | 3 `/download` requests, first two "(canceled)", 1 file on disk not 3. |
| SPA destruction (dev tip) | Dirty the form, then console: `window.location = '/settings-editor/api/raw/takes/definitely-not-a-take/download'` | Page replaced by the 404 JSON; dirty pill gone; iframe torn down. |
| Anchor fix | Same URL via an `<a download>` element | Page does **not** navigate, dirty pill survives. **Unverified — record what happens to the response**: Chrome may save a tiny file *or* show a failed-download entry. Note which; if it fails silently, the pre-flight in change 2 is mandatory, not optional. |
| Headers present | `curl -sI ".../download" \| grep -iE 'content-disposition\|content-length'` | `attachment; filename=<TAKE>.zip` + numeric length. **This HEAD builds the whole zip** — small take only, watch `df -h /`. |
| Disk doubling | `watch -n1 'df -h / /media/RAW'` during one large download | Free space on `/` drops by the take's full size and recovers. Repeat with 3 selected to size the concurrent risk. |
| Progress geometry *(change 3, gated on decision 1)* | `getComputedStyle(document.querySelector('.cliprow.is-downloading .clip-progress')).display` | `'flex'`; `'none'` on a non-downloading row. |
| Track height *(gated)* | `document.querySelector('.clip-progress .capacity-track').getBoundingClientRect().height` | `8`. **Do not use `getComputedStyle().height`** — `*{box-sizing:border-box}` at `:107` plus the 1px border makes it report `6px`, and the assertion would fail on a correct implementation. |
| Full-row span *(gated)* | Compare `.clip-progress` rect width to `.cliprow` rect width − 32 (padding `13px 16px`, `:784`) at 1280px and 375px | Match within 1px at both breakpoints. |
| Cancel *(picker path only)* | Abort mid-transfer on the tunnel | Network shows "(canceled)", **and the destination folder no longer contains the file at all** — `dir.removeEntry(name)` ran. A truncated or zero-length file left behind means the cleanup path is missing; `createWritable()` truncates on open, so "zero-length" is the failure, not the pass. |
| Contrast (HUD skin is unconditional — `#app.skin-hud` at `:890-911`, applied at `:980`) | `.clip-progress-text` = `#8a8a8a` on `.cliplist` `--panel #0c0b09` (`:781`); fill `#90ee90` on track `--panel-2 #131210` | 5.70:1 (passes AA 4.5:1) and 13.2:1 (passes SC 1.4.11 3:1). Both recomputed and confirmed. |
| Gate | `python3 tools/design_token_diff.py --strict` | Exit 0 (baseline verified at dev tip). |
| Idiom | `grep -cE 'async function\|await \|=> *\{' src/module/app/templates/settings_editor.html` | Still `0`. |

### Constraints and risks

- **Unguarded picker call = a newly dead button.** On the real origin the property does not exist, so `window.showDirectoryPicker(...)` throws `TypeError`. Every call site must sit behind `CAN_PICK_FOLDER`.
- **Chrome gates downloads 2..N** behind an "Automatic downloads" permission chip. On a phone or kiosk the chip may be invisible, so serialised anchors can silently produce exactly one file — today's symptom with a different cause.
- **N concurrent anchor downloads = N concurrent `build_take_zip()` calls**, each copying a full take to `/tmp` on the rootfs SD card. This can fill `/` and take the Pi down. Serialise or replace with a server-side stream.
- **Do not refactor `send_file` to X-Sendfile.** The `@after_this_request` unlink (`settings_editor.py:494-500`) runs at `finalize_request`, before the body streams; it only works because `send_file` already holds an open fd and POSIX keeps the inode alive.
- **Grid hazard:** a child of `.cliprow` without an explicit `grid-column` is auto-placed into the next cell and shifts the layout — the exact bug the CSS comment at `:523` warns about. `.clip-progress` must carry `grid-column: 1 / -1`.
- **HDMI-GUI parity: none required.** This pane has no simple_gui counterpart, and the design-token gate does not read this template.
- **Interactions:** W6 (HUD skin is the only live palette) sets the contrast basis used above. Any W item that touches `renderClipList` or `.cliprow` grid columns collides with change 3 — land them in one pass.
- **Docs:** if bulk download is disabled or changed, update `docs/changelog.md:49`. `docs/web-gui.md` needs an addition only if you want the RAW pane documented at all.
- Security note, not a regression: this is an unauthenticated pane on an open hotspot. `raw_files.resolve_take` (`:134-149`) blocks traversal, but any joined client can already enumerate and pull every take.

### Decision required from the operator

1. **Is the picker branch worth writing?** This gates the largest block of new code in the batch: change 6 here, change 3's progress UI, **and W9 items 2 and 3**. If the answer to "how do you reach the editor" is "hotspot only, from an iPad", the whole branch is dead code — ship only the anchor path (a ~5-line change), skip both new endpoints, and accept that **there is then no progress UI and no destination folder at all**: an `<a download>` hands off to the browser's download manager, which owns the progress bar, and the browser's "Ask where to save each file" setting is the entire destination story. The blob-buffered alternative that could report progress is forbidden below. Default if unanswered: **skip the picker.**
2. **Bulk download: keep (serialised, with warning) or disable for >1** until a server-side combined-zip endpoint exists?
3. *(only if decision 1 is "yes")* **Layout on the picker path:** `<chosen>/<take>/<take>.zip` (nested) or flat `<chosen>/<take>.zip`? The zip's arcnames already prefix `<take>/` (`raw_files.py:182`), so nesting double-wraps on extract.
4. **A combined-zip endpoint now?** The streaming server half is already in scope as W9. A *multi-take* combined zip is not, and it is what would make bulk download one request instead of N. W9 decision 7 is the same question from the server side — answer them together.
5. **Has a single-take download ever succeeded on real hardware?** A stopwatch on one click distinguishes "broken" from "multi-minute silent TTFB read as a dead button" and changes which fix is urgent.

## Order of work

**Ask these in one message before writing code.** Every decision below gates code, not commentary. If a
decision is unanswered when you reach it, take the Default, proceed, and record the assumption in the
report as `applied (on default, operator confirmation open)`.

| W | Decision | Default if unanswered |
|---|---|---|
| W3 | Route A (lighten `--drop`) or Route B (white text) | **B** |
| W4 | Silently inert, or explicit refusal with a named reason | **Explicit** |
| W5 | Hide or disable the button; D1 only, or D1+D2+D3 | **Hide; all three** |
| W6 | A (promote HUD palette), B (move the nodes) or C (real toggle) | **None — hard block.** A, B and C ship visibly different products. Do not guess |
| W7 | Pin the chip too, or only Save; ship Cmd/Ctrl+S and `beforeunload`? | **Pin both; skip both extras** |
| W9 | Concurrency cap value; hide the actively-recording take? | **2; leave it listed, report `recording: true`** |
| W10 | Write the picker branch at all (also gates W9 items 2/3); bulk = serialise or disable >1 | **Skip the picker; disable >1** |

**W6 is the only hard block.** Everything else has a default — start on it and flag the assumption.

W1, W2 and W8 need no answer at all: their mechanisms are settled in their own sections, and W8's
residual question is answered by the Out of scope list below.

| Order | Item(s) | Branch / PR | Why here |
|---|---|---|---|
| 1 | **W5** | PR A | `template.html` JS only, 14 lines, touches nothing any other item touches. Land it first to prove the harness loop works |
| 2 | **W3** | PR B | Changes the DROP box's **width**, which moves the rail width, which is W1's and W2's input. Must land before the geometry work or you measure a moving target |
| 3 | **W4** | PR B (2nd commit) | Same file, same parity question as W3, no geometry. Ride the same PR only if the operator answers W3 and W4 the same way; otherwise its own PR |
| 4 | **W1 + W2** | PR C, **one PR** | They are one implementation, not two. W2's `--fit` scalar *is* W1's shrink; W1 contributes only the width term to the `Math.min` and two non-`.rail` declarations. A media query alone cannot close W2's drawer-open case (`#stage`'s height changes with no window resize) and a height-only fit cannot close W1's portrait case (portrait has 244.5px of vertical slack, so the height ratio is 1). Splitting them produces two conflicting `.rail` overrides — equal specificity, source order decides |
| 5 | **W8** | PR C (3rd commit) | One line (`#top-row { row-gap: … }`) in the same file and the same portrait layout W1 just changed. Measure it *after* W1's shrink lands. Note W1 re-derives `--gap` on `.rail` only, so `#top-row`'s `calc(var(--gap) * 0.5)` still reads the `:root` value — but re-measure rather than assume |
| 6 | **W6 → W7** | PR D, **one PR, in this order** | Same file (`settings_editor.html`), overlapping regions. W6 first: until you know `#app.skin-hud:890` is what renders, every colour you measure in that file is wrong — that trap is what misled the original review |
| 7 | **W9 + W10** | PR E, **one PR** | Two halves of one feature. A streaming-zip client against a temp-file server (or vice versa) is untestable and half-shipped |

Independent of everything: **W5**. Shares a file but not a region: W3/W4/W8 with W1/W2 (all
`template.html`). Shares a file *and* a region: **W1/W2** (rail geometry), **W6/W7** (settings-editor
topbar and palette). Inseparable: **W9/W10**.

After PR C lands, re-run W3's proof (`getClientRects().length` on `.box.drop`, box width vs rail
content width). W1 shrinks `--box-size`/`--box-height` at narrow widths, so W3's auto-width has to be
re-confirmed under the new floors.

**Merge hazard.** `origin/feature/no-camera-start` is unmerged and adds `"no_cam"` to `DESIGN_TOKENS`,
`--no-cam` to `:root`, and `.box.no-cam { background: var(--no-cam); }` on the line **immediately above**
`.box.drop`. If it lands on `dev` before PR B, W3 collides in the same diff hunk — and the NO CAM badge
repeats W3's defect (black on `rgb(220,30,30)` = 4.248:1, also below AA). Do **not** probe with
`git log origin/dev | grep -i no-camera` — a squashed or retitled merge need not carry that string and
the check silently returns nothing. Probe the code instead, on the fetched tip:

```bash
git -C "$TREE" grep -n no_cam origin/dev -- src/module/design_tokens.py
git -C "$TREE" grep -n 'box\.no-cam' origin/dev -- src/module/app/templates/template.html
```

If either hits, scope W3's fix to the warning-badge family rather than one selector.

## Verification and gates

### Rebuild the harness — every time, before every measurement

`development/web-ui-review/harness/index.html` in the shared workspace is **stale** and does not
announce it: it is a build of `c02f8e67` (2026-08-17), 965 lines against dev's 1783, predating both
PR #160 and the entire EXPERIMENT drawer. Its mtime is not a reliable signal — something rewrote it on
2026-09-01 without a clean `build.sh` run. Never measure the checked-in copy.

`build.sh` **does** honour `$1` as the source tree, but it **always** writes its output to
`$HERE/index.html` — `HERE` is derived from `BASH_SOURCE`, and the write is `> "$HERE/index.html"` at
`build.sh:28`. Running it in place therefore overwrites the checked-in artifact. Its `REPO` default
(`build.sh:16`) is the shared clone, which is on another session's branch. So copy it out **and** pass
an explicit path:

```bash
SCRATCH=<your scratchpad>/harness-dev
TREE=<the worktree from "Before you touch anything">
HARNESS=/Users/patrikeriksson/Documents/cinemate/development/web-ui-review/harness

mkdir -p "$SCRATCH"
cp "$HARNESS"/{build.sh,mock-io.js,preview.svg} "$SCRATCH/"
bash "$SCRATCH/build.sh" "$TREE"          # also copies the two DIN2014 faces

# Proof the build is current: sed is line-for-line, so the counts MUST match.
wc -l < "$SCRATCH/index.html"
git -C "$TREE" show HEAD:src/module/app/templates/template.html | wc -l
# 1783 == 1783 before any edit. The two must always match each other; the
# absolute number grows as you add CSS. If you see 965 you are looking at the
# stale copy.
```

Serve it **in the background** — a foreground `http.server` blocks the Bash tool until timeout and
`sleep` is blocked, so you could never curl it. There is no `launch.json` entry for 8811, so this is
the one server that does not go through `preview_start`:

```bash
# run_in_background: true
/Users/patrikeriksson/.pyenv/versions/3.12.8/bin/python -m http.server 8811 \
    --bind 127.0.0.1 --directory "$SCRATCH"
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8811/index.html?state=warn'   # 200
```

`build.sh` exits 1 if any `{{` survives, so a silent half-substitution is not possible.

**This is the only harness recipe in this document.** W2, W3, W4, W5 and W8 all point here. Do not run
`build.sh` from its own directory and do not serve port 8794 from the shared workspace.

The mock exposes exactly one query parameter, `state`, with four values (`mock-io.js:86`); an unknown
value falls back to `idle` silently. **Measure W2/W3/W4/W8 in `?state=warn`** — it is the only state
that renders the DROP/SYNC/LOG boxes and a `.group.locked`.

### Driving the RAW pane locally (W9 / W10)

`raw_files.MEDIA_ROOT` is a module-level `Path("/media")` (`raw_files.py:28`), so nothing in the RAW
pane renders on a Mac until you re-point it. Build a fixture tree in the scratchpad — a few take
directories each holding one or more `.dng` files, since `_is_take_dir` (`raw_files.py:51-55`) matches
any dir with one `.dng` — then monkeypatch `raw_files.MEDIA_ROOT` at it and register the blueprint on a
bare Flask app, copying `make_app()` from `_test/test_settings_editor_format.py:45`.

| Desk-closable with the fixture | Still needs `cinepi.local` |
|---|---|
| `%00` → 404 JSON; traversal 404s; manifest shape | `findmnt /tmp`, `df -h /`, real ENOSPC |
| `stream_take_zip` round-trip, `testzip()`, byte-equality | TTFB on a real multi-GB take |
| Recording interlock 409 on DELETE and bulk (fake redis) | Hotspot throughput, real take size |
| Semaphore 429 and release-after-abort | Whether a single-take download has ever succeeded |
| Every W10 client proof: `.clip-progress` display, track height 8, full-row span at 1280 and 375, contrast | The secure-context verdict on the operator's own device |

### Driving it with the preview_* tools

**A `.claude/launch.json` exists** — at `/Users/patrikeriksson/Documents/cinemate/.claude/launch.json`,
one level *above* the repo (the repo's own `cinemate/.claude/` is an empty directory). `preview_start`
resolves it from a cwd inside the repo. It holds 19 configurations; none sets `"autoPort": true`, so
`preview_start` refuses rather than reassigning when a port is already held by another session.

Two traps: `webgui-review-harness` (port 8794) points at the **stale** shared workspace directory, and
in the verification session it reported success and then vanished between calls. Do not rely on it.

The recipe that worked:

1. `preview_start` any stable config purely to obtain a `serverId` — `settings-editor-preview` (8791)
   worked. If its port is already held by another session, any of the other 18 configs does just as
   well; the page is navigated away from in the next step, so which one it is does not matter.
2. `preview_eval` → `location.replace('http://127.0.0.1:8811/index.html?state=warn')`.
3. Assert you are actually there before measuring — a `chrome-error://` page silently reports
   `innerWidth` 980:
   ```js
   ({ href: location.href, mode: document.compatMode })   // want 'CSS1Compat'
   ```
4. `preview_resize` with explicit `width`/`height`, then **`location.reload()`**, then wait for render.
   `sizePreview()` runs off a `ResizeObserver` (`template.html:1760-1762`) and the mock fires
   `initial_values` at t+30ms; measuring too early returns a stale preview rect (observed: 708×638 where
   the truth was 460×258). Gate on `document.querySelector('.box.drop') !== null`.
5. `preview_inspect` is the cheapest way to prove one colour (computed styles + bounding box in one
   call). `preview_screenshot` is illustration only — **never** evidence for a ratio or a font size.
6. `preview_resize` also takes `colorScheme: "light" | "dark"`. It is a no-op for `template.html`
   (every `@media` in it is width- or orientation-keyed, both before and after W1) and is exactly what
   W6 needs on `settings_editor.html`.

### WCAG contrast, in JS

```js
// WCAG 2.x contrast ratio from two getComputedStyle colour strings.
// Caveat: getComputedStyle returns rgba() when alpha < 1; this takes the first
// three numbers, which is only correct for opaque colours. Composite first otherwise.
function ratio(fg, bg) {
  const lin = c => (c /= 255, c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  const L = s => { const [r, g, b] = s.match(/[\d.]+/g).map(Number);
                   return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); };
  const a = L(fg), b = L(bg);
  return +(((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)).toFixed(3));
}
// Self-check: ratio('rgb(0,0,0)', 'rgb(120,40,180)') === 2.761
//             ratio('rgb(255,255,255)', 'rgb(120,40,180)') === 7.605
```

### The per-viewport battery

Run this at **1440×800**, **812×375** and **375×812**, in `?state=warn`, reloading after each resize.
Paste it whole into `preview_eval`.

It is self-contained — `ratio()` is inlined, and nothing depends on `$` (which is IIFE-scoped at
`template.html:726` and unreachable from the console).

```js
(() => {
  const ratio = (fg, bg) => {
    const lin = c => (c /= 255, c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
    const L = s => { const [r, g, b] = s.match(/[\d.]+/g).map(Number);
                     return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); };
    const a = L(fg), b = L(bg);
    return +(((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)).toFixed(3));
  };
  const R = e => { const q = e.getBoundingClientRect();
    return [+q.width.toFixed(2), +q.height.toFixed(2), +q.left.toFixed(2), +q.top.toFixed(2)]; };
  const rail  = document.querySelectorAll('.rail')[0];
  const drop  = document.querySelector('.box.drop');
  const dcs   = getComputedStyle(drop);
  const rng   = document.createRange(); rng.selectNodeContents(drop);
  const frame = document.getElementById('preview-frame');
  const stage = document.getElementById('stage');
  const fr = frame.getBoundingClientRect(), sr = stage.getBoundingClientRect();
  const ids   = [...document.querySelectorAll('.group select')].map(s => s.id);
  const rects = ids.map(id => ({ id, r: document.getElementById(id).getBoundingClientRect() }));
  const overlaps = [];
  for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) {
    const a = rects[i].r, b = rects[j].r;
    const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (ox > 0 && oy > 0) overlaps.push([rects[i].id, rects[j].id, +ox.toFixed(2), +oy.toFixed(2)]);
  }
  return {
    vp: [innerWidth, innerHeight],
    // Operator ruling (binding): rails stay left and right; the layout shrinks, never restacks.
    stageCols:   getComputedStyle(stage).gridTemplateColumns,
    railOrder:   ['rail-left', 'preview-wrap', 'rail-right']
                   .map(id => +document.getElementById(id).getBoundingClientRect().x.toFixed(2)),
    railFlexDir: getComputedStyle(document.getElementById('rail-left')).flexDirection,
    // W3
    dropRatio:     ratio(dcs.color, dcs.backgroundColor),
    dropIfWhite:   ratio('rgb(255,255,255)', dcs.backgroundColor),
    dropBox:       R(drop), dropFont: dcs.fontSize,
    dropLineBoxes: rng.getClientRects().length,          // > 1 means the count wrapped
    // W2
    railClippedPx: rail.scrollHeight - rail.clientHeight,
    railGutterPx:  rail.offsetWidth  - rail.clientWidth, // 0 here; non-zero only with classic scrollbars
    boxOverhangPx: +(drop.getBoundingClientRect().width - rail.clientWidth).toFixed(2),
    // W1
    frame: R(frame), stage: R(stage),
    deadAbove:    +(fr.top - sr.top).toFixed(2),
    deadBelow:    +(sr.bottom - fr.bottom).toFixed(2),
    frameAreaPct: +((fr.width * fr.height) / (innerWidth * innerHeight) * 100).toFixed(2),
    // W8 + the PR #160 floors
    selRects:    rects.map(x => [x.id, +x.r.width.toFixed(2), +x.r.height.toFixed(2)]),
    selOverlaps: overlaps,
    clipFont: getComputedStyle(document.getElementById('v-clip')).fontSize,   // must stay 10px
    wavFont:  getComputedStyle(document.getElementById('v-wav')).fontSize,    // must stay 8px
    // W4
    lockedSelPointerEvents: getComputedStyle(document.querySelector('.group.locked select')).pointerEvents
  };
})()
```

Baseline at dev tip, `?state=warn`:

| | 1440×800 | 812×375 | 375×812 |
|---|---|---|---|
| `stageCols` | three tracks | three tracks | three tracks |
| `railOrder` | strictly ascending | strictly ascending | strictly ascending |
| `railFlexDir` | `column` | `column` | `column` |
| `dropRatio` | 2.761 | 2.761 | 2.761 |
| `dropIfWhite` | 7.605 | 7.605 | 7.605 |
| `dropLineBoxes` | 2 | 2 | 2 |
| `railClippedPx` | 129 | 281 (104 clientHeight with the drawer open → 436) | 0 |
| `frameAreaPct` | 62.86 | 39.0 | **14.98** |
| `deadAbove` / `deadBelow` | 0.02 / 0.02 | 0.43 / 0.44 | 253.66 / 253.66 |
| `selOverlaps` | none | none | 4 pairs, `oy` = 12.00 each |
| `clipFont` / `wavFont` | 10px / 8px | 10px / 8px | 10px / 8px |
| `lockedSelPointerEvents` | `auto` | `auto` | `auto` |

For the settings editor (W6/W7) use the same loop against `settings-editor-harness` (port 8792) — but
note it is hard-wired to `development/worktrees/settings-editor-fixes`, which currently has the `dev`
*branch* checked out. Re-point it at `$TREE` or you are measuring someone else's tree.

### CI gates — every one, with its exact local command

Run all **eleven** from the worktree root before each commit. Nothing in the suite asserts a px value or
a contrast ratio (`grep -lnE 'px\b' _test/*.py` returns nothing), so the harness measurement is the only
check on any CSS change here.

| Gate | Command | Pass looks like |
|---|---|---|
| ruff | `ruff check src/` | `All checks passed!` (scope is `src/` only; `_test/` and `tools/` are unlinted) |
| pytest | `python3 -m pytest _test/ -q -p no:randomly` | `688 passed, 368 subtests passed` at dev tip — the count **rises** once W9's `_test/test_raw_files_download.py` lands; zero failures is the gate, not the number. `-p no:randomly` is **mandatory** — two tests stub `flask_socketio` into `sys.modules` and never clean up |
| shellcheck | `find . -name '*.sh' -not -path './.git/*' -print0 \| xargs -0 shellcheck -f gcc` | no output. Verified installed today at `/opt/homebrew/bin/shellcheck` |
| shellcheck (generated) | `python3 tools/check_generated_scripts.py` | exit 0 |
| drift 1/6 | `python3 tools/docs_drift_check.py --repo . --strict` | exit 0 |
| drift 2/6 | `python3 tools/findings_disposition_check.py --repo .` | `228 findings, all dispositioned` |
| drift 3/6 | `python3 tools/design_token_diff.py --repo . --strict` | `0 drifted`, and `--box-text  #000` still under NOT COMPARABLE |
| drift 4/6 | `python3 tools/gui_field_extract.py --repo . --max-unresolved 0` | `offered but ABSENT on the controller: 0` |
| drift 5/6 | `python3 tools/link_frequency_drift_check.py --repo . --strict` | `12 frequencies … none restated in the template. OK` |
| drift 6/6 | `python3 tools/redis_key_diff.py --max-unreferenced 12 --cinepi-raw /Users/patrikeriksson/Documents/cinemate/cinepi-raw` | exit 0. **Without `--cinepi-raw` it exits 2 from a worktree** — it looks for `../cinepi-raw`, which only exists next to the main clone |
| mkdocs | `/Users/patrikeriksson/.pyenv/versions/3.12.8/bin/python -m mkdocs build --strict --site-dir <scratch>/mkdocs-out` | exit 0. Use the pyenv interpreter; the material plugin stack is not installed under the system python. CI itself runs `--clean` without `--strict`; `--strict` is the stricter local convention |

**There is no `make test`, `make lint` or `make check`.** The Makefile is a systemd-service installer
(`Makefile:22`); `make` prints help and `make install` runs `sudo systemctl` on the developer's Mac. Do
not invoke it.

Tests that read the templates as **text**, and will fire if you move a substring they match: four on
`template.html` (`test_b95_sync_box_crossed_consistency`, `test_b97_web_gui_drop_count:25`,
`test_b97_web_gui_labels_from_populate_values:22`, `test_web_gui_resolution_auto_refresh:41`), three on
`settings_editor.html` (`test_action_catalogues_agree:29`, `test_b95_config_defaults_consistency:62`,
`test_log_encode_normalization:47`). If W6/W7 touch the settings editor's JavaScript action catalogue,
`test_action_catalogues_agree` is the one that fires — that list exists in three copies and the test
enforces agreement.

## What the desk cannot close

Nothing in this list can be closed from a laptop. **Report each as "code change written, hardware gate
open" — never as done.**

| Needs | Which items | What specifically |
|---|---|---|
| **A physical iPhone on the hotspot** | W5 | Whether `requestFullscreen` is actually absent on the operator's iOS version; whether the probe hides the button correctly; the label-desync path on prefixed-only WebKit |
| | W8 | Whether a real finger triggers the 4px group intrusion at all. All overlap geometry is `elementFromPoint` in headless Chrome; iOS applies touch-centroid adjustment and fuzzy tap targeting |
| | W1, W2 | Whether a vertical drag starting on the rail — ~32px wide after the shrink, down from 38 — scrolls the rail, or is eaten by the page / the adjacent tap-to-record handler. Also whether `mask-image` renders the fade correctly on iOS Safari |
| | W7 | Whether the pinned Save is reachable one-handed at 320–375px |
| **A real Pi (`cinepi.local`)** | W3 | Whether white DROP text reads on the physical HDMI panel at real viewing distance and brightness — sRGB maths is a proxy, the panel has its own gamma. Also the realistic magnitude of `drop_frame_count` on a bad take, which sets whether the rail width needs a cap |
| | W4 | Whether the SHUTTER write-through actually moves the redis value while locked |
| | W9 | `findmnt /tmp` and `df -h /` — rootfs ENOSPC versus a tmpfs `/tmp` exhausting RAM and tripping the 80% auto-stop. Also `ls /tmp/settings-editor-*.zip` for leaked temp files |
| | W10 | Real take size, hotspot AP throughput, and whether a single-take download has *ever* succeeded (a stopwatch on one click distinguishes "broken" from "multi-minute silent TTFB") |
| **The HDMI panel itself** | W3, W4 | Any parity change to `simple_gui.py` changes what the camera's own screen looks like. `TEXT_COLOR` also draws the crossed-SYNC strike line (`simple_gui.py:1298`), so an HDMI-side text-colour change recolours more than the badge |

Both browser harnesses are headless Chrome at `devicePixelRatio` 1. No test, no gate and no tool in the
repo exercises a browser.

## Out of scope

- **The `inset` shorthand fallback for iOS 14.0–14.4.** PLAN.md's exclusion stands. Its *reasoning* is
  measurably wrong on both halves — that engine drops `inset` and flexbox `gap` together, so W8's 4px
  premise does not exist there, and the degradation is a select that no longer covers its group, not
  merely a worse tap target. Correcting `PLAN.md:38-40`'s prose is W8's work. **Write no CSS for it**,
  and do not add `min-width`/`min-height` to `.group select`.
- **Any change to `cinepi-raw`.** Every item here is template, CSS, JS, plus at most one Python token
  dict and the two settings-editor modules. If a fix appears to need the C++ side, stop and report.
- **Any rebuild.** Nothing in this work requires recompiling `cinepi-raw`, reflashing, or touching the
  driver, libcamera or the installer.
- **Reinstating the portrait restack.** The operator ruled on 2026-09-01 that the rails stay left and
  right at every viewport and the layout shrinks rather than reflows. B11.7 / `d8bfbbd1` stands and
  PLAN.md's option 3 is rejected. See W1. Do not add an orientation-keyed media query; W1's one new
  block is width-keyed on purpose, and it contains no `.rail` declaration.
- **Handbook edits.** `cinemate-handbook` has two known-stale pages
  (`conventions/checks-and-ci.md` says four drift scripts where six run;
  `working/changing-the-gui.md` says colours are "defined twice"). Both are real, both are a separate
  repo with its own push-approval rule, and neither belongs in this PR.
- **A docs page for the settings editor.** It has no entry in `mkdocs.yml`'s nav today. Adding one is
  scope creep.

## Reporting

Hand back one report. No summary `.md` files in the repo — the report is your final message.

One exception, and it is a decision, not a default: C0, C2, C3 and C4 each keep their kickoff prompt
in-repo as `SONNET-PROMPT.md`, and `dev-track/C8-web-ui-review/` holds only `PLAN.md`. **Do not file
this document as `dev-track/C8-web-ui-review/SONNET-PROMPT.md` unless the operator asks for it.** Note
the inconsistency in the report and let them call it.

**Per item, one row.** Status is exactly one of: `applied` · `already-fixed-at-tip` ·
`blocked-on-decision` · `blocked-on-hardware` · `skipped`. Never silently drop an item.

| W | Status | Files touched | Before → after | Gate |
|---|---|---|---|---|
| W3 | applied | `template.html`, `design_tokens.py` | DROP contrast 2.761 → 7.605; `dropLineBoxes` 2 → 1 at all three viewports | token diff exit 0, `--box-text` still NOT COMPARABLE |

Then, in prose:

1. **The operator ruling, asserted.** For every item that touched `template.html` CSS, paste
   `stageCols`, `railOrder` and `railFlexDir` at all three viewports, and again with the EXPERIMENT
   drawer open. `railOrder` must be strictly ascending and `railFlexDir` must be `column` in every one.
   A run that does not show this is not a pass, whatever the other numbers say.
2. **Measured numbers, before and after, at all three viewports** for every item that changed geometry
   or colour. Raw `preview_eval` output is acceptable and preferred over description. State the harness
   build's line count so the reader knows it was current.
3. **Every gate you ran, with its result** — the eleven commands in the table above. Say explicitly if
   you skipped one and why.
4. **Every deliberate HDMI/web divergence**, one sentence each, matching what you wrote in the code
   comment and the commit body.
5. **Every decision you took on its Default** rather than an operator answer, and the ledger-branch
   deviation, one line each.
6. **Everything left open**: which operator decisions are unanswered, which hardware gates are open, and
   for each, exactly what question or measurement would close it. Include the two findings W9 leaves
   open by design: bulk delete's duplicate-name ambiguity, and the paper text literals at
   `settings_editor.html:667, 677-679`.
7. **Anything you found that is not in this document.** New defects go in the report as candidate
   PLAN.md rows, not into the diff.
8. **Anything marked "unverified — check first" that you checked** — run
   `grep -n "unverified — check first"` over this document and answer every hit. Say what you found, and
   say so plainly if it did not reproduce.
