# C8 · Web UI design review — remaining findings

A design/UX review (2026-08-26/27, Fable session) of both browser surfaces on dev tip
`4affc53e`: the live web GUI (`src/module/app/templates/template.html`) and the settings
editor (`settings_editor.html`). Everything was measured in a desk harness, not guessed —
the harness and the raw measurements are in the external workspace
`Documents/cinemate/development/web-ui-review/` (`harness/build.sh` regenerates its page
from the live template, so it cannot drift).

**Two findings already shipped.** [PR #160](https://github.com/Tiramisioux/cinemate/pull/160)
merged to `dev` as `1675ca66` on 2026-08-26, CI green (contract-drift, mkdocs, pytest, ruff,
shellcheck):

| commit | change |
|---|---|
| `ab17fdb4` | settings editor · `<!DOCTYPE html>` + viewport meta + `.mode-table{line-height:1.3}` |
| `4b3d5093` | web GUI · select tap targets ~44×18 → 34px tall (widths vary by label, none is a uniform 56px — see W8's measured width table), px font floors on clip name + WAV badge, `docs/web-gui.md` qualifier |

That fixed the operator-reported bug: the settings editor had **no doctype and no viewport
meta at all**, so phones laid it out at the 980px fallback viewport and its `≤860px`
hamburger — which already existed — never fired in portrait. **This step is the rest.**

## The remaining findings

W1 was a decision at the time this table was written; it no longer is. The operator ruled on
2026-09-01 (see `WEB-UI-REVIEW-PLAN.md`'s W1 section): rails stay left and right at every
viewport and the layout shrinks rather than reflows. W1 is now an implementation task, folded
into W2's mechanism. Two findings surfaced after this table was written are not in it: **W9**
(clip download, server half) and **W10** (clip download + destination folder, client half) —
see `WEB-UI-REVIEW-PLAN.md` for both; they are candidate rows here, not added to preserve this
table's evidence/disposition shape without doing the same work for them.

| # | Finding | Evidence | Shape of the fix |
|---|---|---|---|
| W1 | **Portrait phone wastes most of the screen.** The preview renders 285×160 (15.0% of screen) inside a 375×812 viewport, vertically centred, with large empty bands above and below it and the rails hugging the left edge | 375×812 harness measurement | Shrink the rail chrome via the width term of W2's `--fit` scalar (operator ruling: shrink, never restack) |
| W2 | **Left rail clips silently.** At 812×375 the rail's `scrollHeight` is 444 against a 282 `clientHeight`; the SYS section (storage type *and filesystem*) scrolls out of view with no visible scrollbar. The rule's own comment says "scroll rather than clip, so a real status … never silently disappears" — visually it does disappear | measured; visible in the `?state=warn` screenshot, SSD/ext4 cut mid-box | Bottom fade-mask (or a scroll affordance) when the rail overflows, and/or shrink `--box-size`/gaps at short heights instead of overflowing |
| W3 | **DROP badge fails contrast, and crowds its own count.** Black on `rgb(120,40,180)` ≈ **2.8:1** (WCAG AA wants 4.5:1); white on that purple ≈ 7.6:1. Separately, "DROP 17" wraps tightly inside the fixed `--box-size`×`--box-height` box | computed from the token value | Change the text colour **in `src/module/design_tokens.py`** so both surfaces move together (that is what the token pipeline is for — `tools/design_token_diff.py --strict` gates it), and let a warning box carrying a count auto-width |
| W4 | **Locked reads as selected.** A locked FPS/SHUTTER/EI draws as an inverted white pill — which reads "highlighted", not "locked" — and the transparent `<select>` over it still opens the picker on tap, so a locked parameter looks changeable | `?state=warn`, `.group.locked .value` | Faithful to `draw_rounded_box()`, so a change is a deliberate divergence: either a lock glyph, or `pointer-events:none` on the select while locked (the reject toast already explains the refusal, so this is polish, not correctness) |
| W5 | **FULLSCREEN is dead on iPhone.** `(el.requestFullscreen \|\| el.webkitRequestFullscreen).call(el)` throws when both are undefined — iOS Safari has no element-fullscreen API | code read, **not** observed on a device | Feature-detect and hide the button when neither API exists |
| W6 | **42 lines of dead theme CSS in the settings editor** (not ~150): the `@media (prefers-color-scheme: dark)` block and the `:root[data-theme="light"/"dark"]` hooks, plus one empty rule and one shadowed declaration. The `:root` "paper" palette itself is **not** dead — it is live outside `#app` (the raw-file drawer, toast and confirm modal), which `#app.skin-hud` never reaches, and it is the sole declaration of `--focus` (every keyboard focus ring on the page) | `settings_editor.html` `:root` blocks vs `#app.skin-hud`; it misled the review itself mid-session (a light-scheme test rendered dark, which is consistent with `#app` being the one region genuinely immune) | Promote the HUD palette to `:root` (re-homing `--focus` safely) and delete the 42 dead lines, **or** move the 4 fixed-position nodes inside `#app`, **or** reconnect a real toggle. See `WEB-UI-REVIEW-PLAN.md` W6 for the three options — this one is a hard operator decision, not mechanical |
| W7 | **Save can scroll out of reach.** The topbar is a nowrap flex row that scrolls inside itself by design at narrow widths — but "Save changes", the one action that matters, is last in that row and can sit off-screen with no affordance | `.topbar{overflow-x:auto}` + narrow-width render | Pin Save (and probably the unsaved-count chip) outside the scrolling region |
| W8 | **Wrapped-portrait select overlap** — accepted trade-off from PR #160, recorded so it is not rediscovered as a bug. Where the top row wraps, rows sit ~4px apart, so a lower row's enlarged select reaches ~4px into the row above; a tap on those descender pixels opens the lower group's picker | adversarial review of #160; documented in the rule's comment | Optional hardening: cap the vertical extension against the row gap, or raise `#top-row`'s row-gap to match |

Explicitly **not** doing: a fallback for the `inset` shorthand on iOS 14.0–14.4. The exclusion
stands, but the original reasoning here was wrong on both halves: that engine drops `inset`
**and** flexbox `row-gap` together (both land in Safari/iOS 14.1), so W8's "4px of overlap"
premise does not exist there at all, and the actual degradation is not merely "a worse tap
target" — with `inset` dropped, every top-row `<select>` falls back to its intrinsic size
(15×15 to 68×15px) and the picker no longer covers the text it controls. See
`WEB-UI-REVIEW-PLAN.md`'s W8 section for the measurements.

## W1 — settled by operator ruling, 2026-09-01

This used to be an open ADR question with three options (below, for the record). It no longer
is. The operator ruled: *"the left and right columns with grey boxes should always be in the
left and right. not reflowed but rather shrunk in order to fit."* Consequences: the rails stay
left and right at every viewport including portrait phone; the layout shrinks, never restacks;
option 3 below (reinstating the restack) is rejected; option 1 (do nothing + a rotate hint) is
rejected. W1 is now an implementation task — see `WEB-UI-REVIEW-PLAN.md`'s W1/W2 sections,
which is where its mechanism actually lives (one `--fit` scalar shared with W2, no second
mechanism). The original three options, for the record:

1. Do nothing; add a "rotate for the full HUD" hint in portrait. — **Rejected.**
2. Keep the three-column grid but shrink its geometry tokens so the rails and preview all
   scale down together without restacking. — **This is the ruling**, implemented as W1+W2.
3. Reinstate a portrait-only restack (what B11.7 removed). — **Rejected.**

`system-review/decisions/ADR-001-gui-harmonization.md` was read before this ruling was acted
on; its "a 1920 instrument panel and a phone browser should not share a grid" argument
constrains a future shared layout engine, not this file, and is compatible with shrink-not-
restack.

## Verification

Desk-verifiable, except where noted. Per fix: rebuild the harness page
(`development/web-ui-review/harness/build.sh`), then measure the specific property with
`getComputedStyle`/`getBoundingClientRect` at 1440×800, 812×375 and 375×812 — a screenshot
alone is not evidence for a contrast ratio or a font size. `tools/design_token_diff.py
--strict` must stay at exit 0 (W3 changes its **source**, `design_tokens.py`, so both
surfaces move together — that check is the whole point).

Two items the desk cannot close, and should not be claimed as done without a Pi:

- **W5** is a code read. iOS Safari behaviour needs an actual iPhone against a real camera.
- Any tap-target change is geometry on desk; whether a finger lands where predicted is a
  phone-on-the-rig check. The same is true of the W1 options.

**Branch:** `fix/web-ui-portrait` (or per-finding branches) off `dev`, cinemate only — every
item here is template/CSS/JS plus, for W3, one Python token dict. No cinepi-raw side, no
rebuild.
