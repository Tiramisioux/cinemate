# Kickoff prompt for the implementing session

Paste everything below the line into a fresh Sonnet thread.

Note: unlike C0, this step spans **two repos** and its hardware gates are unrun. The prompt
tells the implementer to write the desk-verifiable work and stop before the Pi.

---

Implement DSI/DPI panel support in CineMate — an official Raspberry Pi Touch Display or a
HyperPixel usable as the camera monitor, alongside HDMI rather than instead of it.

The full spec is at:
`/Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C2-dsi-display/DSI-DISPLAY-PLAN.md`
on branch `feature/dev-track` — ledger entry C2 in `PLAN.md` beside it.

Read the spec in full before touching anything, and read
`/Users/patrikeriksson/Documents/cinemate/cinemate-handbook/README.md` plus
`orientation/the-traps.md` and `orientation/entry-points.md` first — this change touches
trap #4 (one process owns the display) and three of the entry-points table's "also update"
rows. Every design decision in the spec is operator-approved: implement them, don't
relitigate.

Ground rules:

- Two repos, two branches. `cinepi-raw`
  (`/Users/patrikeriksson/Documents/cinemate/cinepi-raw`): branch
  `feature/display-connector` off up-to-date `dev`, commit C2.1. `cinemate`
  (`/Users/patrikeriksson/Documents/cinemate/cinemate`): branch `feature/dsi-display` off
  up-to-date `dev`, commits C2.2–C2.8. `cd` does not persist between shell calls — use
  `git -C` and absolute paths.
- **Never `git add -A`** in either repo (LFS pointer trap) — stage named files only.
- Do not merge to `dev`, do not open PRs, and **do not touch the Pi**. No hardware gate has
  been run yet; you are producing the desk-verifiable half.
- The settings-editor template's JS is ES5 (`var`, `function(){}`) — match it. The file
  embeds base64 font data: filter greps with `awk 'length($0) < 250'`.

Order matters — do C2.1 first, then the cinemate commits in order. Three places will bite
you, all called out in the spec; re-read those sections before writing them:

1. `cinepi_options.cpp` parses options in **two** places (the Boost table and a manual
   `--flag=value` scan). Both must learn `--display-connector`, or it silently no-ops.
2. `settings.schema.json` is `additionalProperties: false` at top level *and* on
   `hdmi_display`. The new `outputs` block needs a schema edit or it is rejected outright —
   `_test/test_settings_schema_rejects_unknown_keys.py` will catch you.
3. `boot_config.py`'s docstring states a replace-only rule as absolute. C2.6 deliberately
   breaks it by **inserting** the display section when absent, so existing installs get the
   feature without reinstalling. Update the docstring to record the exception — a future
   reader must not "fix" it back.

Before writing C2.5, verify one spec assumption against current source and tell me the
answer: that `cinepi_multi.py`'s `_build_args()` is the *only* place `--hdmi-port`,
`--same-hdmi` and `--nopreview` are assembled. If a second call site exists, stop and say
so rather than leaving two policies.

Done means:

1. The eight commits match the spec (deviate only where the spec contradicts current
   source, and say exactly where and why).
2. New tests, all Pi-free, following the existing patterns in `_test/`:
   - `resolve_display_args()` against the spec's full seven-row policy table.
   - `drm_display_connected()` against a fake `/sys/class/drm` tree.
   - The `boot_config.py` display section: parse, render, round-trip, insert-when-absent,
     and byte-identical preservation of everything outside the section — model it on
     `_test/test_settings_editor_preserves_comments.py`.
   - Schema: `hdmi_display.outputs` accepted, an unknown key under it still rejected.
3. `python -m pytest _test/ -q -p no:randomly` fully green in `cinemate`, and `cinepi-raw`
   compiles with `meson test` green. Do **not** invent a unit test for the DRM connector
   selector — it needs real hardware; say so instead.
4. Both branches committed with files staged explicitly and pushed to GitHub over HTTPS.
5. You hand me: the manual Pi update commands for both repos (`git fetch`, `git switch`,
   `git pull --ff-only`, **plus the cinepi-raw rebuild** — C2.1 is C++, so a restart alone
   is not enough), and the **G0–G5 hardware gate checklist** from the spec's Verification
   section, each gate with its prediction written out so I can record pass/fail against it.

Two things I want flagged in your final message, not buried:

- Whether G1 (mirror to a panel on an *unmodified* build) still looks likely after you have
  read `findCloneOutput()` yourself — the whole "half of this may already work" claim rests
  on it.
- Anything you found that makes G2 (does the clone carry the GUI overlay; what does fb0 do
  with two differently-sized displays) answerable from source rather than needing the Pi.
  The spec treats it as the one genuine unknown; if you can settle it by reading the
  kernel's fbdev-emulation behavior or existing project evidence, that is worth more than
  any of the code.

Stop and ask if a spec assumption fails.
