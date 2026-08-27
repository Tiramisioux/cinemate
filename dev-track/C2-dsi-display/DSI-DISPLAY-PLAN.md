# C2 — DSI / DPI panel support: implementation spec

Written 2026-08-26 from source on `dev` (cinemate `feature/dev-track` = dev + this dir;
cinepi-raw `ci/b10-6-cinepi-tests`, verified identical to `dev` under `preview/` and
`cinepi/`). Nothing implemented.

**Goal.** Run CineMate's preview + GUI on a MIPI-DSI panel (official Raspberry Pi Touch
Display) or a DPI panel (HyperPixel), alongside HDMI rather than instead of it. Two flip
switches in `settings.jsonc`; the rest resolved automatically from what is actually
connected.

## Verdict

Feasible, moderate effort. The display path is already connector-agnostic at the DRM
level — the blockers are *filters that spell "HDMI"*, not architecture. There is no new
compositing, no second DRM client, and no conflict with trap #4 (one process owns the
display): the panel is another connector on the same card, driven by the same process
that already holds DRM master.

## Confirmed source facts

Every row read directly on `dev`. These are the load-bearing ones; cited by function, not
line (handbook convention).

| # | Fact | Where |
|---|---|---|
| 1 | cinepi-raw holds DRM master and binds **one** connector at first frame; it never rebinds — that is why HDMI hotplug restarts capture | `preview/drm_preview.cpp` `findCrtc()` |
| 2 | Primary display is selected by `--hdmi-port 0\|1` → connector id by counting connectors of type `HDMI-A`/`HDMI-B` **only**. DSI/DPI connectors are invisible to it | `preview/hdmi_utils.cpp` `drm_connector_id_for_port()` |
| 3 | `--hdmi-port` is validated to −1/0/1 and throws otherwise | `core/options.cpp` (`hdmi-port must be -1, 0 or 1`) |
| 4 | The clone path (`--same-hdmi`) filter is **already type-agnostic**: any *other* connector that is `DRM_MODE_CONNECTED` with a valid, active CRTC and a spare plane in the preview's format qualifies. Only the flag name, log strings and docs say "HDMI" | `preview/drm_preview.cpp` `findCloneOutput()` |
| 5 | The preview **never modesets**. It reads `enc->crtc_id` and attaches a plane to a CRTC something else already lit — normally fbcon at boot, which lights every connected display, DSI included | `findCrtc()`, `findPlane()` |
| 6 | Preview construction failure degrades to null preview; capture continues | `preview/preview.cpp` `make_preview()` |
| 7 | The dual-sensor compositor obtains its DRM preview through the same `make_drm_preview(app_->GetOptions())`, so any primary-selector change covers dual-sensor automatically | `cinepi/dualHdmiPreviewStage.cpp` |
| 8 | The on-camera GUI rasterises to `/dev/fb0` and **scales its entire layout** by `disp_width/1920`, `disp_height/1080`; fonts use `min(shrink, 1)` so they shrink but never enlarge | `module/simple_gui.py` (`shrink_x`/`shrink_y`, `_measure_layout_text`) |
| 9 | The GUI's headless gate checks **HDMI connectors only** — `drm_hdmi_connected()` globs `card*-HDMI-A-*/status` and `acquire_framebuffer()` returns `None` when no HDMI is connected. A DSI-only rig therefore gets *no GUI by design* today, and `--hdmi-port 0` fails to resolve → bare console on the panel | `module/framebuffer.py` |
| 10 | `hdmi_display.mirror_to_both_ports` (bool) → `--same-hdmi` at launch, single-sensor only, applied on restart. **This is the exact pattern C2 extends** | `config_loader.py`, `cinepi_multi.py` `_build_args()` |
| 11 | Launch geometry prefers the **active framebuffer size** over the configured canvas, then insets the preview rect by a fixed 94/50 px to leave the GUI its columns | `cinepi_multi.py` `_build_args()`, `_active_framebuffer_size()` |
| 12 | `config.txt` has a cinemate-managed block with a camera sub-section and standalone toggle lines; `apply_config_txt_state()` **replaces only** what it finds and refuses to synthesize a missing managed block | `module/app/boot_config.py` |
| 13 | The settings schema is `additionalProperties: false` at top level **and** on `hdmi_display` — a new key without a schema edit is rejected outright, and `_test/test_settings_schema_rejects_unknown_keys.py` enforces it | `settings.schema.json` |
| 14 | HDMI attach after a headless start queues a cinepi-raw restart so the preview can bind, gated on not-recording and a cooldown | `simple_gui.py` `check_display()`, `_maybe_restart_camera_for_display_attach()` |

### One inherited claim that is *not* confirmed

`drm_preview.cpp`'s clone block is commented "commit the same framebuffer (preview + GUI)",
and `docs/settings-json.md` repeats it ("mirror the one sensor's preview (with GUI)").
Mechanically, `Show()` commits **only `buffer.fb_handle`** — the camera preview buffer — to
the second CRTC. The GUI lives on fbcon's own plane on fb0. Whether the GUI reaches the
second display is therefore a property of the kernel's fbdev emulation (does fbcon drive
both CRTCs, and at what size), **not of this code**. Treat "with GUI" as unverified until
gate **G2** answers it. If it turns out false, it is a pre-existing limitation of
`mirror_to_both_ports`, not something C2 introduces — but C2 must not repeat the claim
about panels without evidence.

## Hardware constraints (platform, not code)

| Platform | Ports | Consequence |
|---|---|---|
| Pi 5 / CM5 | Two MIPI connectors, each usable as CSI **or** DSI. `camN` and `dsiN` are the *same physical socket* | Sensor and panel must use **opposite** ports. **Dual sensor + DSI panel is impossible** — both sockets are cameras |
| Pi 4 family | Dedicated DSI connector, separate from the CSI connectors | No conflict; dual sensor + panel is fine |

| Panel | Interface | Native | Overlay (*probable — verify against `/boot/firmware/overlays/README`*) | Notes |
|---|---|---|---|---|
| Official Touch Display (7", v1) | DSI | 800×480 landscape | `vc4-kms-dsi-7inch` (+`,dsi0` on BCM2712) | **Primary v1 target** |
| Touch Display 2 | DSI | 720×1280 **portrait** | `vc4-kms-dsi-ili9881-7inch` | vc4/HVS planes cannot rotate 90°; landscape needs a CPU rotate of the preview buffer. v1 renders portrait — usable, not pretty. Rotation deferred |
| HyperPixel 4 / 4 Square / 2r | **DPI, not DSI** | 800×480 / 720×720 / 480×640 | `vc4-kms-dpi-hyperpixel4` etc. | DRM-side identical (a `DPI` connector). **Consumes GPIO 0–25**, which kills the default button map (pins 7/10/13/22/24), the rotary encoders and I²C add-ons. Support it, but warn loudly in the editor |

Touch input: both official panels are ordinary evdev touchscreens. Nothing in cinemate
consumes touch events, and the web GUI already provides the touch UX. **Out of v1 scope.**

RAM/CMA: cloning adds no buffer allocation — the same framebuffer is scanned out by a
second CRTC. No 2 GB CM5 concern (see the dev-unit memory note on the 80% RAM auto-stop).

## Design

### 1. settings.jsonc — the flip switches

Extend the existing `hdmi_display` section. **Do not rename it**: the name appears in user
settings files, the schema, `docs/settings-json.md`, and ~8 `data-path` attributes in the
settings-editor template. A rename is a separate, purely cosmetic change with real breakage
risk.

```jsonc
"hdmi_display": {
  // ...existing keys unchanged...

  // Which physical outputs carry the preview + GUI. Both on = the panel
  // mirrors HDMI when both are attached, and either one alone still works.
  // Applied at cinepi-raw start (like mirror_to_both_ports).
  "outputs": {
    "hdmi": true,
    "dsi":  true
  }
}
```

`"dsi": true` covers DPI panels too — one switch for "the attached panel". Naming it
`"panel"` would be more accurate but reads worse against the documented overlay names;
`dsi` is the operator-facing word for both in the Pi ecosystem. Documented explicitly.

### 2. Launch policy — seamless means *resolved from what is connected*

Cinemate owns the policy and passes an explicit decision; cinepi-raw stays mechanism. This
matches the repo split (`orientation/entry-points.md`) and keeps the "which display?"
question testable in Python.

| `hdmi` | `dsi` | HDMI attached | Panel attached | Result |
|---|---|---|---|---|
| on | on | yes | yes | HDMI primary + panel mirrors (clone) |
| on | on | yes | no | **Exactly today's behavior** |
| on | on | no | yes | Panel becomes primary automatically |
| on | off | — | — | **Exactly today's behavior** |
| off | on | — | yes | Panel primary, HDMI dark |
| off | on | — | no | `--nopreview` |
| off | off | — | — | `--nopreview` |

Resolution helper (new, in `cinepi_multi.py` or a small module beside it — pure function,
unit-testable with no Pi):

```python
def resolve_display_args(outputs: dict, attached: dict, hdmi_port: int,
                         mirror_to_both_ports: bool, multi: bool) -> list[str]:
    """outputs/attached: {'hdmi': bool, 'dsi': bool}. Returns launch args."""
```

- eligible = outputs AND attached, per key.
- none eligible → `['--nopreview']`.
- HDMI eligible → primary is HDMI: keep today's `--hdmi-port <N>` (per-cam
  `sensors.camN.output.hdmi_port` still honored).
- Otherwise panel is primary → `--display-connector dsi`.
- More than one eligible output → append `--same-hdmi`.
- `mirror_to_both_ports` keeps its current meaning (HDMI-0 + HDMI-1) and also yields
  `--same-hdmi`; the two reasons collapse to one flag.

**Known v1 limitation:** `--same-hdmi` clones to the *first* eligible other connector. On a
rig with two HDMIs *and* a panel, which one gets the clone is first-found, not chosen. Note
it in the docs; the fix (an optional `--clone-connector <selector>` mirroring the primary
selector) is a listed follow-up, not v1.

**No live switching in v1.** The preview binds once at first frame (fact 1); a live
`set display` would need the same restart the HDMI hotplug path already performs. Toggles
apply on restart, exactly like `mirror_to_both_ports`, and the settings editor already
restarts after saving `settings.jsonc`.

### 3. cinepi-raw changes (~100 lines)

**C2.1** — `preview/hdmi_utils.{hpp,cpp}`: add

```cpp
std::optional<uint32_t> drm_connector_id_for_selector(const std::string &sel);
```

accepting `hdmi0`, `hdmi1`, `dsi`, `dpi`, `auto`:
- `hdmi0`/`hdmi1` — count `HDMI-A`/`HDMI-B` as `drm_connector_id_for_port()` does today
  (keep that function; the new one may delegate).
- `dsi`/`dpi` — first connector of `DRM_MODE_CONNECTOR_DSI` / `_DPI` whose
  `connection == DRM_MODE_CONNECTED`. **Require connected** here; the HDMI path does not,
  and that asymmetry is deliberate — a panel that isn't there must fall through to the
  auto-detect path rather than binding a dead connector.
- `auto` / unknown → `std::nullopt`, i.e. today's "first active connector" fallback in
  `findCrtc()`.

Add `--display-connector <selector>`. `cinepi_options.cpp` parses options in **two** places
— the Boost program-options table *and* a manual `--flag=value` scan — and both must learn
the new flag; missing the second is a silent no-op. Keep `--hdmi-port` working as an alias
(`0`→`hdmi0`, `1`→`hdmi1`), and relax the `core/options.cpp` validation so the two flags
coexist. `make_drm_preview(const Options *)` resolves the selector, preferring
`--display-connector` when set.

Also in C2.1: correct the clone-path log strings ("second active HDMI connector" → "second
active display") and the `Show()` comment's unverified "(preview + GUI)" claim. No
functional change to `findCloneOutput()` is expected — see gate G1.

### 4. cinemate changes (~200–300 lines + template)

**C2.2** — `module/framebuffer.py`: add `drm_display_connected()` globbing
`card*-HDMI-A-*`, `card*-DSI-*` and `card*-DPI-*` status files; use it as
`acquire_framebuffer()`'s gate. **Keep `drm_hdmi_connected()`** — `simple_gui.check_display()`
needs to distinguish "some display" (draw the GUI) from "HDMI specifically" (queue the
preview-rebinding restart).

**C2.3** — `module/simple_gui.py`: with a panel attached, `had_display` is already True when
HDMI arrives, so the existing attach detection in `check_display()` would miss it. Drive
`_pending_display_camera_restart` off a **`drm_hdmi_connected()` transition** instead of the
`had_display` edge. The recording/writing gate and cooldown in
`_maybe_restart_camera_for_display_attach()` stay as they are.

**C2.4** — `module/config_loader.py` defaults + `settings.schema.json`. The schema edit is
**mandatory**, not optional (fact 13). Add to `docs/settings-json.md` in the same commit —
`tools/docs_drift_check.py` gates it.

**C2.5** — `cinepi_multi.py`: the `resolve_display_args()` helper above, replacing the
current `--hdmi-port`/`--same-hdmi`/`--nopreview` assembly. Optional polish, cheap and
worth doing: scale the fixed 94/50 px GUI margins by `fw/1920`, `fh/1080` — on an 800×480
panel a 94 px inset is 12% of the width, and the GUI columns that inset protects have
already shrunk by 0.42×.

### 5. config.txt / boot_config.py

**C2.6** — a `# ---- Display section ----` … `# ---- End display section ----` region inside
the managed block, modeled directly on the camera section:

```
DISPLAY_MODELS = none | official-7inch | touch-display-2 |
                 hyperpixel4 | hyperpixel4-square | hyperpixel2r
```

→ one `dtoverlay=` line, with the `,dsi0`/`,dsi1` port parameter appended on BCM2712 and
omitted for DPI panels.

**One deliberate deviation from the module's replace-only rule:** `apply_config_txt_state()`
must **insert** the display section when its markers are absent, so existing installs get
the feature without reinstalling. Insert *inside* the existing managed block, immediately
after the camera section; still refuse when the managed block itself is missing. Document
the deviation in the module docstring — it currently states the replace-only rule as
absolute, and a future reader must not "fix" this back.

### 6. Settings editor UI

**C2.7** — two additions, both mechanical:
- Boot Config pane: a Display dropdown beside the existing per-port sensor dropdowns.
- HDMI/preview panel: two `data-path` toggle rows for `hdmi_display.outputs.hdmi` and
  `.dsi`, alongside the existing `f-mirror` toggle.

Cross-validation, editor-side, **BCM2712 only**: sensor on `camN` and panel on `dsiN` with
the same N is a hardware conflict → block the save with an explanatory error, the same
shape as the existing config-txt validation errors. On Pi 4 there is no conflict; do not
warn there.

Also surface the HyperPixel GPIO cost at selection time — choosing a `hyperpixel*` model
disables GPIO 0–25, and every default button/encoder in `settings.jsonc` sits in that
range. A one-line warning under the dropdown, not a blocking error.

**Drift note:** the display-model list will exist in **two copies** — `boot_config.py` and
the template's JS — exactly like `SENSOR_MODELS` and `ACTION_METHODS` before it. Add the
cross-reference comment in both copies. `_test/test_action_catalogues_agree.py` is the
precedent if a check is wanted later; adding one is optional for C2, and cheap.

### 7. Docs

- `docs/settings-json.md` — the `outputs` block (drift-checked).
- `docs/config-txt.md` — the display section and the port-conflict rule.
- **new `docs/displays.md`** — which panel on which port per Pi model, the Pi 5
  `camN`/`dsiN` socket-sharing rule, the HyperPixel GPIO cost, and what the mirror does
  and does not put on the second screen (per G2's answer).
- `docs/simple-gui.md` — a note that the GUI scales uniformly and what that looks like at
  800×480.
- `docs/cli-user-guide.md` — the `--display-connector` row; correct the `--same-hdmi` row.

## Commits

| commit | change |
|---|---|
| C2.1 | cinepi-raw: `drm_connector_id_for_selector()`, `--display-connector`, `--hdmi-port` kept as alias, validation relaxed, clone log/comment text corrected |
| C2.2 | cinemate: `drm_display_connected()`; headless gate accepts DSI/DPI |
| C2.3 | cinemate: HDMI-attach restart triggers off the HDMI-connected transition, not the display edge |
| C2.4 | cinemate: `hdmi_display.outputs` defaults + schema + `docs/settings-json.md` |
| C2.5 | cinemate: `resolve_display_args()` drives launch args; optional margin scaling |
| C2.6 | cinemate: `boot_config.py` display section (parse / render / **insert-if-absent**) |
| C2.7 | cinemate: settings-editor Display dropdown + the two output toggles + port cross-validation |
| C2.8 | docs: `displays.md`, `config-txt.md`, `simple-gui.md`, `cli-user-guide.md` |

Split across two repos, so two branches:
- cinepi-raw: `feature/display-connector` off `dev` (C2.1).
- cinemate: `feature/dsi-display` off `dev` (C2.2–C2.8).

Neither repo pins the other's revision, so C2.2–C2.5 must **degrade cleanly against an old
cinepi-raw**: if `--display-connector` is unknown to the installed binary it will fail to
start. Gate the flag on the panel-primary case only (it is never emitted when HDMI is
primary), and say plainly in the docs that panel-primary needs the rebuilt binary.

## Verification

### Desk (Sonnet, no Pi)

- `python -m pytest _test/ -q -p no:randomly` fully green.
- New unit tests, all Pi-free:
  - `resolve_display_args()` — the full seven-row policy table above.
  - `drm_display_connected()` — against a fake `/sys/class/drm` tree (tmp_path + monkeypatched glob root).
  - `boot_config.py` display section — parse, render, round-trip, **insert-when-absent**, and byte-identical preservation of everything outside the section. Follow `test_settings_editor_preserves_comments.py`'s pattern.
  - Schema: `hdmi_display.outputs` accepted; an unknown key under it still rejected.
- cinepi-raw: compiles; `meson test` green. The connector selector needs real DRM, so it is
  **not** unit-testable — compile + hardware only. Say so rather than faking a test.

### Hardware gates (operator, needs a panel)

Method per `cinemate-handbook/working/hardware-session.md`: belief → why hardware is needed
→ procedure → **prediction stated in advance** → verdict. Official 7" v1 first.

| Gate | Test | Prediction |
|---|---|---|
| **G0** | Panel attached, overlay line in config.txt, boot. `ls /sys/class/drm/`, `modetest -c` | A `DSI-1` (or `DPI-1`) connector on the vc4 card, status `connected`, with a CRTC already lit by fbcon |
| **G1** | **Unmodified current `dev` build.** HDMI + panel, single sensor, `mirror_to_both_ports: true` | The panel shows the mirrored preview, letterboxed — because `findCloneOutput()` is type-agnostic (fact 4). **Validates half the feature with zero code.** If it fails, the fix lands in C2.1 and the design is unchanged |
| **G2** | With G1 running: what exactly is on each screen — video only, or video + GUI overlay? And `cat /sys/class/graphics/fb0/virtual_size` with two displays of different sizes | **Unknown, and the one real unknown in this plan.** Hypothesis: the clone CRTC shows video *without* the GUI, and fb0 takes one display's geometry rather than both. Determines the docs' accuracy and whether panel-primary needs mixed-resolution GUI handling |
| **G3** | Panel only (HDMI unplugged), `outputs: {hdmi: false, dsi: true}`, patched build | Preview *and* GUI on the panel; GUI legible at 0.42× shrink. Confirms C2.1–C2.5 end to end |
| **G4** | With the panel primary, hot-plug HDMI; then unplug it | Attach queues a restart (not during recording); preview rebinds with HDMI primary and the panel falls back to mirror. Detach returns to panel-primary on the next restart |
| **G5** | Pi 4 + official 7", no overlay line | Auto-detected, same code path. *(Probable, not confirmed)* |

Recording gates' outcomes into `cinemate-handbook/lessons/hardware-log.md` is required, not
optional — see the skill's "Recording hardware findings".

## Out of v1 — recorded so they are not re-litigated

- Touch input (evdev → GUI actions). The web GUI already covers touch.
- Touch Display 2 landscape rotation (CPU rotate of the lores buffer).
- Live, restart-free display switching (`set display …`).
- Explicit clone targeting on 3-display rigs (`--clone-connector`).
- Panel-specific GUI layouts beyond the existing uniform shrink.

## Confidence

- **Confirmed:** every numbered source fact, read on `dev` in both repos.
- **Probable:** G1 mirrors to a panel unmodified; the overlay names; the Pi 5 `camN`/`dsiN`
  socket-sharing rule and the opposite-port requirement; DSI panels reporting `connected`.
- **Unknown:** whether the clone carries the GUI overlay and what fb0 does with two
  differently-sized displays (both G2); Touch Display 2's orientation behavior on bare KMS;
  Pi 4 auto-detect (G5).
