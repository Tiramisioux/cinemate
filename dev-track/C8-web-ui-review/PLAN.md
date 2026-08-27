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
| `4b3d5093` | web GUI · select tap targets 44×18 → 56×34, px font floors on clip name + WAV badge, `docs/web-gui.md` qualifier |

That fixed the operator-reported bug: the settings editor had **no doctype and no viewport
meta at all**, so phones laid it out at the 980px fallback viewport and its `≤860px`
hamburger — which already existed — never fired in portrait. **This step is the rest.**

## The remaining findings

Nothing below is started. W1 is a decision, not a patch; W2–W7 are self-contained.

| # | Finding | Evidence | Shape of the fix |
|---|---|---|---|
| W1 | **Portrait phone wastes most of the screen.** The preview renders 501×281 inside a 375×812 viewport, vertically centred, with large empty bands above and below it and the rails hugging the left edge | 375×812 harness screenshot | **Decide, don't patch** — see "W1 is an ADR question" below |
| W2 | **Left rail clips silently.** At 812×375 the rail's `scrollHeight` is 444 against a 282 `clientHeight`; the SYS section (storage type *and filesystem*) scrolls out of view with no visible scrollbar. The rule's own comment says "scroll rather than clip, so a real status … never silently disappears" — visually it does disappear | measured; visible in the `?state=warn` screenshot, SSD/ext4 cut mid-box | Bottom fade-mask (or a scroll affordance) when the rail overflows, and/or shrink `--box-size`/gaps at short heights instead of overflowing |
| W3 | **DROP badge fails contrast, and crowds its own count.** Black on `rgb(120,40,180)` ≈ **2.8:1** (WCAG AA wants 4.5:1); white on that purple ≈ 7.6:1. Separately, "DROP 17" wraps tightly inside the fixed `--box-size`×`--box-height` box | computed from the token value | Change the text colour **in `src/module/design_tokens.py`** so both surfaces move together (that is what the token pipeline is for — `tools/design_token_diff.py --strict` gates it), and let a warning box carrying a count auto-width |
| W4 | **Locked reads as selected.** A locked FPS/SHUTTER/EI draws as an inverted white pill — which reads "highlighted", not "locked" — and the transparent `<select>` over it still opens the picker on tap, so a locked parameter looks changeable | `?state=warn`, `.group.locked .value` | Faithful to `draw_rounded_box()`, so a change is a deliberate divergence: either a lock glyph, or `pointer-events:none` on the select while locked (the reject toast already explains the refusal, so this is polish, not correctness) |
| W5 | **FULLSCREEN is dead on iPhone.** `(el.requestFullscreen \|\| el.webkitRequestFullscreen).call(el)` throws when both are undefined — iOS Safari has no element-fullscreen API | code read, **not** observed on a device | Feature-detect and hide the button when neither API exists |
| W6 | **~150 lines of dead theme CSS in the settings editor.** The light "paper" palette, the `@media (prefers-color-scheme: dark)` block and the `:root[data-theme="light"/"dark"]` hooks are all permanently overridden by `#app.skin-hud`, which the markup carries unconditionally — its own comment says "there's no Manual/HUD switch anymore" | `settings_editor.html` `:root` blocks vs `#app.skin-hud`; it misled the review itself mid-session (a light-scheme test rendered dark) | Delete the dead palettes, **or** reconnect a real toggle. Deleting is the smaller change and the honest one unless a theme switch is actually wanted |
| W7 | **Save can scroll out of reach.** The topbar is a nowrap flex row that scrolls inside itself by design at narrow widths — but "Save changes", the one action that matters, is last in that row and can sit off-screen with no affordance | `.topbar{overflow-x:auto}` + narrow-width render | Pin Save (and probably the unsaved-count chip) outside the scrolling region |
| W8 | **Wrapped-portrait select overlap** — accepted trade-off from PR #160, recorded so it is not rediscovered as a bug. Where the top row wraps, rows sit ~4px apart, so a lower row's enlarged select reaches ~4px into the row above; a tap on those descender pixels opens the lower group's picker | adversarial review of #160; documented in the rule's comment | Optional hardening: cap the vertical extension against the row gap, or raise `#top-row`'s row-gap to match |

Explicitly **not** doing: the `inset` shorthand's lack of a fallback for iOS 14.0–14.4 (that
window is the only engine that renders this page but drops `inset`; the degradation is a
worse tap target, not a broken page).

## W1 is an ADR question, not a CSS task

The portrait layout is the way it is **on purpose**. B11.7 / F-297 deliberately removed the
old `@media (max-width:900px), (orientation:portrait)` restack — which turned the rails into
horizontal strips above and below the preview — on the grounds that `simple_gui.py` scales
its whole 1920×1080 layout by a single ratio and never restacks, so the browser should not
either. That reasoning is sound for the surface it was written about.

The counter-argument this review raises is narrow and worth stating plainly: **the HDMI GUI
never meets a portrait viewport, and a phone does.** A single-ratio scale of a 16:9-authored
instrument panel into a 9:19.5 window necessarily leaves most of that window empty. So this
is not "B11.7 was wrong"; it is "B11.7's premise does not reach the portrait case."

Before changing anything here, read `system-review/decisions/ADR-001-gui-harmonization.md`
(it already worked this through against measured DRM/RAM/refresh constraints) and the
handbook's `architecture/gui-state-model.md`. Options worth weighing, cheapest first:

1. Do nothing; add a "rotate for the full HUD" hint in portrait.
2. Keep the three-column grid but let the stage centre as a unit and give the preview
   priority width, reclaiming the dead bands without restacking.
3. Reinstate a portrait-only restack (what B11.7 removed) — the largest usable preview, and
   the option that most directly contradicts the existing decision. Needs the operator.

**Do not just re-add the media query.** If option 3 wins, it should land as an amendment to
the decision, with the reasoning recorded, not as a silent revert of a deliberate change.

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
