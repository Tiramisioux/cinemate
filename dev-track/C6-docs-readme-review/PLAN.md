# C6 · Docs + README correctness pass (both repos)

A read-only review (2026-08-26, Fable session) checked every public doc surface against the
code on the two dev tips: cinemate `README.md` + all 45 `docs/*.md` pages + `mkdocs.yml`
(GitHub `dev` @ `8427ca0b`) and cinepi-raw `README.md` (`dev` @ `bc63598`). This step turns
the findings into applied fixes.

**Full fix spec: [`DOCS-FIX-PLAN.md`](DOCS-FIX-PLAN.md) in this directory.** Raw
observation notes (every finding with file/line and a confidence label) are in the external
workspace `Documents/cinemate/development/readme-docs-review/` — the spec here is
self-contained; the workspace is backing evidence.

The finding that shapes the step: **the reference pages are in excellent shape — the drift
is concentrated in settings-key paths and in feature pages that predate later code
changes.** The CLI table matches `cli_commands.py` 1:1; redis-keys, web-api,
recovery-console, hotspot-logic, clear-hdr, cinemate-log, building-control-units and
simple-gui-refresh-tuning all verify against code. Against that baseline:

| Class | Count | Worst examples |
|---|---|---|
| Docs instruct keys/values the code never reads | 4 | `settings.auto_storage_preroll` (3 pages; real key `system.storage.auto_preroll`), `"audio"` section (2 pages; real `"audio_capture"`), `record_policy: false/true` (real `"follow_preview"/"always_both"`), `preview.*` paths (real `hdmi_display.preview.*`) |
| Stale vs current code | ~12 | sensors.md says CCMP12 log-encode "refused" while the code now composes to target 10 (its own support table already says so); quad-rotary stock mapping dial-reversed; "web GUI has a format button" (it's the settings-editor RAW pane); README links a deleted cinepi-raw branch (404) |
| Cross-copy drift | 6 pairs | README 3.3.2 list ⊂ changelog, and **both** miss ClearHDR + settings editor + format-drive; installer block ×3; compile-raw.sh inlined twice; asound.conf ×2; cg_rb seed 2.5,2.2 vs 3.5,1.5 |
| cinepi-raw README | 16 items | dead "clock-correction flag" + wrong settings key; deps installed after the build that needs them; ClearHDR section missing the 12-bit CCMP12 mode entirely; flags table missing `--sync`/`--zoom`/`--scaler-crops` |
| mkdocs hygiene | 7 | 8 orphan pages (one invents a `cinemate-cli` binary), `extra_css` → nonexistent file, Material-only config under the RTD theme |

| commit | change |
|---|---|
| C6.1 | cinemate docs · P0 dead-key fixes (auto_preroll, audio_capture, record_policy, preview paths) + dead branch link in README |
| C6.2 | cinemate docs · P1 stale-behaviour fixes (CCMP12 row, quad mapping, format-button claim, config-txt canonical block, overclock manual note, k_steps, controller-methods pips, changelog copy-paste + missing 3.3.2 entries) |
| C6.3 | dedup · README 3.3.2 → headline bullets + changelog link; compile-raw.sh to one source; asound.conf canonicalised; acknowledgements aligned |
| C6.4 | mkdocs · orphan prune/rescue, extra_css fix, theme-config cleanup |
| C6.5 | cinemate README · shape pass (title, first-run section, feature links, "Preinstalled hardware" rename) |
| C6.6 | cinepi-raw · merge `docs/b13-5-readme-fix`, then the C-series README fixes (dep order, CCMP12 section, flags table, asound path) |

**Branches:** `docs/c6-correctness-pass` off `dev` (cinemate); cinepi-raw: merge the
already-pushed `docs/b13-5-readme-fix` (e083186) into `dev` first, then
`docs/c6-readme-pass` off `dev`.

**Conflict guard:** `docs/installation-steps.md` has an uncommitted local rework in the
`feature/dev-track` working tree (−221 lines: one-path restructure of the libcamera
section). All installation-steps fixes (D30–D39 in the spec) must be reconciled with that
rework, not applied to the stale page — coordinate with the operator before touching it.

**Verification.** Desk only — this step has no runtime surface. Per fix: re-grep the
corrected key/value against `src/module/` so every documented key provably exists in code.
Page level: `mkdocs build --strict` green (docs.yml runs it on PR), plus a link pass over
changed pages. The review session already verified each finding against code once; the
implementing session re-verifies before each edit rather than trusting the list.
