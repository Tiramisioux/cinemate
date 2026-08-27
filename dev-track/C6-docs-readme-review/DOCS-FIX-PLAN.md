# C6 — full fix spec

Written against cinemate GitHub `dev` @ `8427ca0b` and cinepi-raw `dev` @ `bc63598`
(2026-08-26). Every item was verified against code once during the review; **re-verify
each against the current tree before editing** — dev moves fast.

Raw notes with per-line references: `Documents/cinemate/development/readme-docs-review/`
(external workspace, not in git).

## P0 — docs instruct things that don't work

| File(s) | Fix |
|---|---|
| `docs/storage-preroll.md` L5, `docs/troubleshooting.md` L11, `docs/cli-commands.md` L97 | `settings.auto_storage_preroll` → `system.storage.auto_preroll` (only key `config_loader.auto_storage_preroll_enabled()` reads; no legacy fallback) |
| `docs/audio-recording.md` L18, `docs/audio-sync.md` L8 | Sample section `"audio"` → `"audio_capture"` (no `"audio"` fallback in src/module) |
| `docs/dual-sensors.md` L39-43 | `record_policy` values `false`/`true` → `"follow_preview"` / `"always_both"`; reword the two bullets accordingly (settings-json.md L139 is the correct model) |
| `docs/dual-sensors.md` L20/L24, `docs/digital-zoom.md` L20 | Settings paths `preview.*` → `hdmi_display.preview.*` (no top-level `preview` key) |
| `README.md` L6 | Dead link `…/cinepi-raw/tree/rpicam-apps_1.7_custom_encoder` → `https://github.com/Tiramisioux/cinepi-raw` |
| `docs/installation-steps.md` manual path | References `/home/pi/run_cinemate.sh` (sudoers L669, alias L729, run step L971) but never creates it — only `cinemate-install.sh` L1554 writes it. Add a creation step or ship it as a repo file. **Coordinate with the uncommitted local rework of this page first.** |

## P1 — stale claims about current behaviour

| File | Fix |
|---|---|
| `docs/sensors.md` L67 + footnote L78 | CCMP12 log-encode is no longer refused: cinepi-raw composes CCMP-decompand → 16-bit linear → 16to10 (`dng_encoder.cpp`; `sensor_detect.py` ~L783 narrates the change). Update the frame-size row (on → 10, smaller file) and the footnote. The page's own support table (L89) and `cinemate-log.md` L27 are already correct — align to them. |
| `docs/sensors.md` | Reconcile the three IMX283 mode sets: "Compatible sensors" table (2736×1824/2736×1538/3840×2160 @ 36/41/44 fps = the Pi-validated fork modes) vs frame-size table (= `resources/sensors.json`'s 5568/2784 rows) vs sensor-size table (5472 optical dims). Decide the source of truth (live `--list-cameras` on the 6.12.y fork) and update `sensors.json` + tables together; L80's "older/alternate" caveat currently points at the wrong table. Give the page an H1 matching the nav label. |
| `docs/hardware-controls.md` L144-149 | Quad-rotary "stock mapping" is dial-reversed. Stock: 0=ISO (press zoom, hold shutdown), 1=shutter (sync), 2=fps (double), 3=WB (click cluster). |
| `docs/hardware-controls.md` L142 + `docs/settings-json.md` L525 | Quad rotary ships **enabled** (`"enabled": true`, hot-plug retry makes it safe) — both pages say disabled. Align settings-json's sample mapping with stock while there. |
| `docs/hardware-controls.md` L159 | "the web GUI has a format button" → format lives in the settings editor RAW-files pane and the CLI `format` command; the web GUI has unmount only. |
| `docs/config-txt.md` | Canonical managed block is missing `#dtoverlay=rp1-overclock` (installer L1137) and `hdmi_ignore_cec_init=1` (installer L1166). Re-derive the example from `cinemate-install.sh`'s current block verbatim. |
| `docs/overclocking.md` §2 | Note that Tiramisioux/libcamera `cinemate` tip (614ce18c6) already ships `1.0us / 580` — the hand-edit applies only to stock libcamera. |
| `docs/installation-steps.md` L399 + `docs/settings-json.md` L321 | Stock `k_steps` is `[1.5, 2, 3, 4]` (global). Keep the "[3,4] are the IMX283-relevant entries" explanation, stop quoting [3,4] as the stock value. |
| `docs/controller-methods.md` | Add `pip_cam0`/`pip_cam1` (+ `pip`/`pip0`/`pip1` aliases) to `set_preview_source`; consider folding this page into cli-commands.md or regenerating from `ACTION_METHODS` (it exists in two code copies already). |
| `docs/redis-keys.md` L39 | Command name `set dynamic_resolution_enabled` → `set dynamic resolution` (cli_commands.py L105). |
| `docs/cli-user-guide.md` L74-78 | 3-flag table vs 13+ real flags — either sync from the cinepi-raw README table or replace with a link to it. |
| `docs/changelog.md` | L24: "imx585 driver — uses its own fork of **imx283** driver" copy-paste; L49 stray `**` in heading; add the missing 3.3.2 entries: **ClearHDR (16-bit + 12-bit CCMP12 + live knobs + `set hdr`)**, settings editor (`/settings-editor`), format-drive/RAW-files pane (PR #152). |
| `docs/audio-recording.md` L31 | "16bit = plain-arecord fallback" → the capture helper serves both 16- and 24-bit mic paths now (`cinepi_sound.cpp` L1332 area; settings-json.md L346 has the current wording). |
| `docs/web-api.md` L14 | Drop the "(not yet confirmed against a running hotspot)" parenthetical — either verify 10.42.0.1 on the Pi once, or state it plainly (recovery-console.md already does). |
| `docs/web-gui.md` L4 | "mirrors the on-camera HDMI GUI ([hardware-controls.md])" → link `simple-gui.md`. |
| `docs/speed-ramping.md` | Page ends mid-sentence ("…from the stored exposure time:"); finish or cut. Button example uses GPIO 18 = stock `rec_tone.pin`; pick a free pin. |
| `docs/settings-json.md` L107-127 | Sensors sample shows `override_camera_name: false` + Blackmagic name; stock ships `true` + `"cinepi"`. Show stock, keep the Blackmagic spoof as the documented alternative. |
| `docs/recovery-console.md` L15-17 | Two consecutive paragraphs open with the same "That is the fixed address…" sentence — merge. |

## P2 — kill drift-prone duplication

1. `README.md` 3.3.2 block → 3-5 headline bullets + changelog link (today README ⊂ changelog and both miss the biggest features).
2. One-click installer block ×3 (README, docs/readme.md, installation-steps) → one canonical copy + links. Overview's copy is missing `imx585_mono`.
3. compile-raw.sh exists twice (installer heredoc L832 + inlined in installation-steps L208-283, already drifted in comments). Commit `scripts/compile-raw.sh`; installer installs it, docs reference it.
4. asound.conf ×2 — installation-steps' version (separate 16-bit `Device` card) is the better one; canonicalise, fix `~/etc/` typo and stray "Exit nano" lines in both repos.
5. `docs/acknowledgments.md` lacks PiShrink vs README's list — align.
6. cg_rb seed: 3.5,1.5 (docs) vs 2.5,2.2 (cinepi-raw README) — pick one.

## P3 — mkdocs + orphans

- Delete: `docs/overview.md` (TBA stub, invents `cinemate-cli --init --profile=4k60`), `docs/sensor.sizes.md` (superseded by image-circle.md), `docs/hardware-introduction.md` (empty), `docs/preinstalled-hardware.md` (fold its one useful sentence into README/Overview). Refresh or drop `docs/todo.md` (first item — imx585 16-bit — shipped). Rescue `docs/cinepi-multi.md` into the Reference nav group or move to the handbook.
- `mkdocs.yml`: `extra_css: templates/styles.scss` → `stylesheets/styles.scss` (file doesn't exist at the listed path); strip Material-only `features:`/`palette:` from the RTD theme block; delete unused `docs/js/init-mermaid.js` + `set-code-colours.js`; rename the one-page "Contributing" group.

## P4 — README shape (after the correctness passes)

**cinemate README:** title `# Cinemate` + docs-Overview's opening (Pi 4 or 5; drop the
"12 bit"-only claim); add a 5-line First-run section (hotspot `CinePi`/`11111111` →
`cinepi.local:5000`, HDMI GUI, GPIO7 record button, exFAT drive labelled `RAW`); feature
bullets linking web GUI / web API / settings editor / recovery console / ClearHDR /
CineMate Log / dual sensors; rename "Preinstalled hardware"; fix the L2 fragment and the
4-stop `set preview` cycle (real cycle: both → cam0 → cam1 → pip_cam0 → pip_cam1).

**cinepi-raw README** (after merging `docs/b13-5-readme-fix`):
- Move the dependency install (L51) ahead of the libcamera build block it feeds; replace `cd build && sudo meson setup && sudo ninja` with compile-raw.sh's `meson setup <builddir> <srcdir>` form, unsudoed.
- L171: no clock-correction *flag* exists (it's the built-in per-mic database) and the key is `audio_capture.24bit.timecode_offset_frames` in `settings.jsonc`.
- ClearHDR section: add the 12-bit CCMP12 mode (AE/AWB works there; `--hdr` accepts off/auto/sensor/single-exp; log-encode composes to target 10; 16-bit stays the quality/manual mode).
- Flags table: add `--sync`, `--zoom`, `--scaler-crops` rows; note `--hdr` values beyond `sensor`.
- Small: "capabillities" typo; `~/etc/asound.conf` → `/etc/`; drop "Exit nano" line; `media/RAW` → `/media/RAW`; "rpicam-apps 1.0.7" → 1.7; cpp-mjpeg-streamer source (tiramisioux fork w/ `cinemate` branch vs installer's upstream nadjieb) — pick the one the installer uses; one H1, License to the bottom.

## Do NOT churn (verified accurate against code)

`cli-commands.md` (table = `cli_commands.py` 1:1; fix only the two cosmetic slips: L3
missing space, L63 stray backtick), `redis-keys.md` (one fix above), `web-api.md` (one),
`recovery-console.md` (one), `hotspot-logic.md`, `system-services.md`, `simple-gui.md`,
`simple-gui-refresh-tuning.md`, `clear-hdr.md`, `cinemate-log.md`, `image-circle.md`,
`building-control-units.md`, `getting-started.md`, `ssh.md`, `overclocking.md` (one note).
These carry the house style the weaker pages should converge on.
