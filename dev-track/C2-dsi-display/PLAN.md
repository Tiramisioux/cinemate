# C2 · DSI / DPI panel as a camera monitor, alongside HDMI

Run the preview + GUI on an official Raspberry Pi Touch Display (DSI) or a HyperPixel
(DPI), **without giving up HDMI**. Two flip switches in `settings.jsonc`
(`hdmi_display.outputs.hdmi` / `.dsi`); everything else — which display is primary,
whether the second one mirrors — is resolved at launch from what is actually attached.
Defaults reproduce today's behavior exactly.

**Full implementation spec: [`DSI-DISPLAY-PLAN.md`](DSI-DISPLAY-PLAN.md) in this
directory**, written against `dev` 2026-08-26 (cinemate `13ab0225` era; cinepi-raw `dev`).

The finding that shapes the step: **the display path is already connector-agnostic at the
DRM level.** cinepi-raw never modesets — it attaches a plane to a CRTC fbcon already lit —
and the clone path's connector filter (`findCloneOutput()`) accepts *any* connected
connector with an active CRTC and a spare plane. Nothing in it checks for HDMI. What
blocks DSI today is four filters that spell "HDMI" literally:

| Blocker | Where |
|---|---|
| Primary-display selection counts `HDMI-A`/`HDMI-B` connectors only | `preview/hdmi_utils.cpp` `drm_connector_id_for_port()` |
| `--hdmi-port` validated to −1/0/1, throws otherwise | `core/options.cpp` |
| GUI headless gate globs `card*-HDMI-A-*/status` → a DSI-only rig gets no GUI *by design* | `module/framebuffer.py` |
| No config.txt plumbing, settings keys, schema or editor UI for panels | `boot_config.py`, `settings.schema.json`, `settings_editor.html` |

Consequence worth stating up front: **half this feature may already work on the current
build.** Gate G1 — set the existing `mirror_to_both_ports: true` with a panel attached —
tests the mirror path with zero code written. Run it before or during implementation; if
it fails, the fix lands inside C2.1 and the design is unchanged either way.

Operator-settled decisions, recorded once here:

- Both outputs are **switches, not a mode selector**. The hdmi/dsi/both/auto question is
  answered by the pair of booleans crossed with what is attached — see the spec's policy
  table. Seamless means the operator does not choose a mode; they say which outputs are
  allowed.
- The section stays `hdmi_display` despite now covering non-HDMI outputs. Renaming it
  breaks user settings files, the schema, the docs and ~8 editor `data-path` attributes
  for a cosmetic gain.
- Cinemate owns the policy, cinepi-raw stays mechanism: cinemate reads `/sys/class/drm`
  and passes an explicit decision. Keeps "which display?" unit-testable in Python.
- No live switching in v1. The preview binds one connector at first frame and cannot
  rebind, so a live toggle needs the same restart the HDMI hotplug path already performs.
  Restart-on-save, exactly like `mirror_to_both_ports`.

| commit | change |
|---|---|
| C2.1 | **cinepi-raw** · `drm_connector_id_for_selector()` (`hdmi0\|hdmi1\|dsi\|dpi\|auto`), new `--display-connector`, `--hdmi-port` kept as alias, validation relaxed, clone log/comment text corrected. Both option-parse paths in `cinepi_options.cpp` must learn the flag — missing the manual `--flag=value` scan is a silent no-op |
| C2.2 | `drm_display_connected()`; GUI headless gate accepts DSI/DPI. Keep `drm_hdmi_connected()` — the hotplug path still needs HDMI specifically |
| C2.3 | HDMI-attach restart triggers off the HDMI-connected transition rather than the `had_display` edge, which a panel now keeps permanently True |
| C2.4 | `hdmi_display.outputs` defaults + **schema** (`additionalProperties: false` makes this mandatory) + `docs/settings-json.md` |
| C2.5 | `resolve_display_args()` drives the launch args; optional GUI-margin scaling for small panels |
| C2.6 | `boot_config.py` display section — parse / render / **insert when absent**, a deliberate, documented deviation from the module's replace-only rule so existing installs get the feature without reinstalling |
| C2.7 | Settings editor: Display dropdown + the two output toggles + Pi 5 `camN`/`dsiN` port-conflict validation + HyperPixel GPIO warning |
| C2.8 | Docs: new `displays.md`, plus `config-txt.md`, `simple-gui.md`, `cli-user-guide.md` |

**Branches:** cinepi-raw `feature/display-connector` off `dev` (C2.1); cinemate
`feature/dsi-display` off `dev` (C2.2–C2.8). Neither repo pins the other, so the cinemate
side must degrade cleanly against an unrebuilt binary — `--display-connector` is emitted
only in the panel-primary case.

**Verification.** Desk — full `_test/` suite green plus new Pi-free tests for the policy
table, the `/sys/class/drm` scan, and the config.txt display section; cinepi-raw compiles
and `meson test` passes. The connector selector needs real DRM and is *not* unit-testable
— compile plus hardware, stated rather than faked. Hardware — six gates **G0–G5** in the
spec, each with its prediction written in advance; **G2 (does the mirror carry the GUI
overlay, and what does fb0 do with two differently-sized displays) is the one genuine
unknown** and also settles whether a long-standing docs claim is true. Gate outcomes go to
`cinemate-handbook/lessons/hardware-log.md`.

**Hardware needed:** an official 7" Touch Display (v1) is the primary target; Touch
Display 2 and HyperPixel are supported but carry caveats (portrait-native and
GPIO-consuming respectively). Pi 5 / CM5 shares each MIPI socket between `camN` and
`dsiN`, so sensor and panel take opposite ports — and **dual sensor + DSI panel is
impossible on Pi 5**.
