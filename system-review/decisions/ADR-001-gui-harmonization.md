# ADR-001 — GUI harmonization

**Status:** proposed · **Session:** S08 · **Date:** 2026-08-23
**Decides:** KICKOFF §7 · **Inputs:** `GUI-INVENTORY.md`, `GUI-STATE-MODEL.md`, `REDUNDANCY-REPORT.md`, `STANDARDS-PROPOSAL.md`
**Blocked on:** PI-009 for constraint 2 · PI-013/PI-015 for constraints 3 and 4
**Pi used:** no. No runtime behaviour in this document is asserted as observed.

---

## 1. The question

> Would it be better to generate all the GUI renderings "the same way", using an
> adaptive-CSS approach — including the HDMI GUI — so future changes are made once, with
> per-surface differences limited to which controls are exposed?
> — KICKOFF §7, the operator's hypothesis

---

## 2. Four things changed between KICKOFF and this ADR

KICKOFF framed the decision honestly from the outside. Seven sessions of reading changed
four of its premises, and all four move in the same direction.

**1. The shared state model already exists.** The web GUI has no field set of its own — it
consumes `simple_gui.populate_values()` verbatim, 68 fields, one owner, with the deltas
emitted from inside `draw_gui()` (F-203). *The operator's hypothesis is half true, and the
true half is the expensive half.*

**2. The widget spec already exists.** `setup_resources` builds
`left_section_layout`/`right_section_layout`: a label, ordered items, per-item formatters,
and an optional visibility `condition` per section (F-215). That is close to option C's
schema. The formatters are lambdas, so it is Python rather than serialisable data — the
shape is right, the encoding is not.

**3. The HDMI GUI already does flow layout** (F-238, and this is the one that decides the
ADR). `_top_row_layout` measures the six top-row groups' rendered widths and distributes
the free space between two anchors as an equal gap — a justified flex row, in PIL, with a
conditional badge participating in the flow. `draw_left_sections` walks the section spec,
honours each `condition`, centres labels on measured width, and advances a cursor — a
vertical stack with conditional visibility whose gaps adapt to whether the VU bar is shown.

> **F-008 is therefore partly outdated.** The HDMI GUI is not uniformly absolute-positioned.
> It is a **fixed grid of regions with content-driven flow inside the two busiest ones.**
> What is pinned is the region anchors and the bottom status row.

**4. So KICKOFF §7's "central tension" is narrower than stated** (F-239). "Immediate-mode
raster vs retained-mode declarative layout" is a real difference, but the HDMI renderer
already measures content and derives positions from it where that matters. The gap is not
paradigmatic. It is a missing generalisation.

---

## 3. The seven constraints, answered

### C1 — DRM master is exclusive · **confirmed**

cinepi-raw says so itself: *"DRM master is exclusive per GPU. Two independent cinepi-raw
processes therefore cannot both draw to the display."* The project already paid for this
once, routing the secondary sensor's frames through SysV shared memory rather than sharing
the display (`dualHdmiPreviewStage.cpp:1-22`). **Byte-identical on `dev`.**

### C2 — How the GUI and the preview compose · **PI-009. Narrowed three times, not settled**

- **F-223.** Hot-plugging HDMI makes the GUI thread restart `cinepi-raw` *"so preview binds
  to the active display"* — properly guarded by a cooldown and a not-recording
  precondition. So **the preview binds its display at process start and cannot rebind.**
- **F-227 (`dev`-only).** `drm_preview.cpp`'s `--same-hdmi` clone path already enumerates
  DRM planes, selects one that is not the primary's and supports the same fourcc, and
  programs it with `drmModeSetPlane` — degrading with *"no spare plane for the second
  output; clone disabled"*. **cinepi-raw already does plane-level composition and already
  handles plane exhaustion.**
- **F-229.** Both repos describe `--same-hdmi` as making *preview and GUI share the same
  HDMI output*. Two independent statements that they compose. Neither says how.

**The answerable form of C2 is now a number:** how many overlay planes are free on the
primary CRTC, with `--same-hdmi` on and off. PI-009 has been updated to ask for exactly
that. **This ADR does not answer C2 and must not be read as doing so.**

### C3 — RAM and CPU · **unquantified; two auto-stops already exist**

The dev unit is a 2 GB CM5 Lite. There are **two** independent RAM auto-stops (F-235):
cinemate trips at `RAM_LIMIT_PERCENT = 80`, cinepi-raw trips on encoder pool exhaustion
(*"RAM pool exhausted — recording stopped"*). A recording camera that already stops itself
for memory at UHD has **no headroom budget for a resident renderer**, and no measurement
exists. → PI-013 measures the baseline; a browser's resident cost is an unqueued unknown.

### C4 — Refresh rate and latency · **answered from source**

`target_fps = 12` → `min_frame_interval ≈ 0.083 s`; `slow_refresh_interval = 1.0 s`; idle
wait 0.1 s; event-driven with a cap (`simple_gui.py:201-203`). `docs/simple-gui-refresh-
tuning.md` documents all of it accurately (F-234) and states the operational ceiling:
*"above 15 fps: usually not recommended with the current full-screen PIL-to-framebuffer
path."*

**That ceiling is the number every option must beat or match.** Measured cadence is
PI-015 step 4.

### C5 — Failure mode · **answered, and the baseline is worse than it looks**

**F-204.** `RedisController.Event.emit` is a bare synchronous loop over nine subscribers
with no exception guard; `_listen` has none either; the thread is `daemon=True` with no
watchdog and no restart. One raising subscriber kills the live-state bus permanently — and
because `get_value()` serves a cache, **every surface then renders plausible frozen values
and none shows an error.**

For a camera instrument, *silently wrong* is the worst available failure category. **Option
A does not score zero here; it scores negative**, and every other option inherits the same
bus unless it is fixed. F-208: the guarded version of this exact loop already exists 900
lines away (`cinepi_controller.py:1082-1087`).

### C6 — Boot time · **unquantified; the budget is already spent**

`camera-ready.sh` runs as `ExecStartPre` with `MAX_ATTEMPTS=30` at `RETRY_INTERVAL=1`, so
up to ~30 s can elapse **before `main.py` starts**, ordered ahead of the console handoff
(F-236). Any option that adds a renderer startup adds to a budget that is already long. No
measurement exists.

### C7 — Migration cost and reversibility · **measured**

`SimpleGUI` is 48 methods / 1913 lines (F-237):

| part | lines | share | fate under a renderer swap |
|---|---|---|---|
| draw + layout | 925 | 48.4% | rewritten |
| **state** | **636** | **33.2%** | **preserved — surface 2 already reuses it** |
| display / framebuffer | 241 | 12.6% | preserved except under D/E |
| socket.io | 19 | 1.0% | preserved |
| other | 92 | 4.8% | mostly preserved |

**~925 lines change, not 2129.** And the change is contiguous and identifiable, which is
what makes it flag-gateable.

---

## 4. The options

### A — Status quo

| C1 | C2 | C3 | C4 | C5 | C6 | C7 |
|---|---|---|---|---|---|---|
| n/a | works today | baseline | 12 fps | **negative — silently wrong (F-204)** | baseline | zero |

Cheapest and already shipping. But it is **not a safe default**: C5 is actively bad, and the
hand-sync it relies on has a measured failure record — 16 duplicated-truth instances, 10
already drifted (`REDUNDANCY-REPORT.md`), and F-118 is a settings-editor button that
silently no-ops **today**.

### B — Shared design tokens only

Generate the Python colour constants and the CSS custom properties from one source.

| C1 | C2 | C3 | C4 | C5 | C6 | C7 |
|---|---|---|---|---|---|---|
| n/a | unchanged | nil | unchanged | unchanged | nil | ~1 day |

Kills F-007, F-214, F-232, F-233. The measured target: **16 colour tokens, of which only 3
name their Python counterpart; 11 are undocumented parallel definitions** (F-232) — the sync
mechanism is *weaker* than "a comment". Currently zero have drifted.

**But B is now a subset of where the code already is.** Given F-215 and F-238, shipping B as
the destination means stopping short of the structure that exists.

### C — Shared declarative spec, two backends

| C1 | C2 | C3 | C4 | C5 | C6 | C7 |
|---|---|---|---|---|---|---|
| n/a — no new display client | unchanged | ≈ nil (same renderers) | should match 12 fps; verify | inherits F-204 until fixed | ≈ nil | **~925 lines, incremental** |

The state model exists (F-203), the section spec exists (F-215), and **the HDMI backend
already implements the two layout primitives the spec needs** — a justified row and a
conditional vertical stack (F-238). C is not "port CSS to PIL". It is:

1. lift the section spec out of `simple_gui.py` into data (replace lambdas with named
   formatter references),
2. generalise `_top_row_layout`'s justified-row and `draw_left_sections`' stack into a small
   region-layout primitive the other regions also use,
3. give the web backend the same spec,
4. keep the region anchors per-surface — a 1920 instrument panel and a phone browser should
   *not* share a grid.

Per-surface difference then reduces to "which regions exist and which items are visible",
which is what the `condition` predicate already expresses.

### D — Browser on the Pi drives HDMI

| C1 | C2 | C3 | C4 | C5 | C6 | C7 |
|---|---|---|---|---|---|---|
| **fatal** | fatal | **fatal** | poor | poor | poor | total |

- **C1:** a kiosk browser wants DRM/KMS or a Wayland compositor; either takes DRM master,
  which cinepi-raw holds exclusively. The one workaround the project already built for this
  problem was shared memory, precisely to *avoid* a second display client.
- **C3:** a resident browser on a 2 GB board that already auto-stops recording for memory
  at UHD. Two independent RAM stops exist because memory is already the binding constraint.
- **C5:** the HDMI GUI is the last thing you want fragile; a browser is a large, complex,
  independently-crashing process in front of the operator's only monitor.

**Reject.**

### E — Server-side HTML → raster, blit to the framebuffer

| C1 | C2 | C3 | C4 | C5 | C6 | C7 |
|---|---|---|---|---|---|---|
| **not fatal** | unchanged | fatal | **fatal** | poor | poor | total |

> **Correction to KICKOFF §7.** It says C1 is *"likely fatal to D and E"*. **That is right
> for D and wrong for E.** E rasterises to a bitmap and writes `/dev/fb0` — exactly what
> `simple_gui` does today. It introduces **no second DRM client.** C1 does not kill E.

E dies on C3 and C4 instead. An HTML→bitmap rasteriser capable of 12 fps full-screen on a
CM5 does not exist in a form this project could adopt; the available ones are either a
headless browser (which is option D's memory cost without its benefits) or print-oriented
renderers measured in seconds per page. The project's own doc already warns that the
*current, far cheaper* PIL path should not exceed 15 fps.

**Reject** — on performance, not on DRM.

---

## 5. Decision matrix

| | A | B | C | D | E |
|---|---|---|---|---|---|
| C1 DRM master | n/a | n/a | n/a | **fatal** | ok |
| C2 composition | ? | ? | ? | fatal | ? |
| C3 RAM/CPU | base | nil | ≈nil | **fatal** | **fatal** |
| C4 refresh | 12 fps | 12 fps | verify | poor | **fatal** |
| C5 failure mode | **negative** | negative | negative→fixable | poor | poor |
| C6 boot | base | nil | ≈nil | poor | poor |
| C7 cost | 0 | ~1 day | ~925 lines | total | total |
| kills F-007/F-214 | no | **yes** | **yes** | yes | yes |
| kills the layout duplication | no | no | **yes** | yes | yes |

`?` = PI-009. It gates C2 for every surviving option equally, so it does not discriminate
between A, B and C — which is why this ADR can be proposed before it is answered.

---

## 6. Recommendation

**Reject D and E. Adopt C, reached through B, and fix F-204 before either.**

Ordered, each step shippable and revertible on its own:

**Step 0 — fix F-204 first. It is not part of the GUI work and it outranks it.**
Wrap `Event.emit`'s dispatch in `try/except Exception` with `logging.exception`, copying
`cinepi_controller._notify_resolution_change` verbatim (F-208), and add a liveness check on
the `_listen` thread. Every option inherits this bus. Harmonising the renderers over a bus
that can silently freeze all of them is building on the wrong thing. **~10 lines.**

**Step 1 — option B, as the first increment of C, not as the destination.** One token
source generating both the Python constants and the CSS custom properties. Wire
`harness/design_token_diff.py --strict` in CI on the same commit. Currently 0 of 16 tokens
have drifted; the check exists to keep it that way. **~1 day.**

**Step 2 — lift the section spec into data.** Replace the lambdas in
`left_section_layout`/`right_section_layout` with named formatter references so the
structure is serialisable, and have the web backend read the same spec. Nothing about
rendering changes. **This is the reversible half of C.**

**Step 3 — generalise the layout primitives.** Extract `_top_row_layout`'s justified row and
`draw_left_sections`' conditional stack into a region-layout helper, and move the bottom
status row onto it. **Behind a flag, region by region** — each region is independently
verifiable against the current output, and the PIL path stays the fallback.

**Keep the region anchors per-surface.** The HDMI panel is a fixed-resolution instrument;
the browser is not. Sharing the grid is the part of "adaptive CSS everywhere" that should
*not* be adopted.

### Verification before unification

S04's standing verdict, and it is not a caution here — it is a precondition with evidence
on both sides:

- **The project has done this kind of unification once and it held.** Control flow was
  routed through `POST /api/v1/cmd` so web, CLI and serial share one path, with the reason
  recorded in the code: *"behaviour cannot drift between them"* (F-206).
- **It has also tried the other way, and that failed.** The settings-editor action catalogue
  exists three times; the two hand-maintained copies agree perfectly *including on the same
  wrong entry*; a comment claims to have corrected the catalogue and missed one; and the
  endpoint that computes the check has zero consumers (F-218, F-219, F-220).

Two of the three checks already exist: `harness/gui_field_extract.py` and
`harness/design_token_diff.py`. Neither needs hardware. **No step above should land without
its check landing on the same commit.**

### Scope exclusion

**Surface 4, the recovery console, is out of scope permanently** (F-221). Its value is its
isolation — stdlib-only by a stated rule, venv-side validation by subprocess rather than
import, numbered degradation ladders, 86 tests. Unifying it deletes the property it exists
for. This ADR covers surfaces 1, 2 and 3 only.

---

## 7. What this ADR does not decide

- **C2.** PI-009 is open. It does not discriminate between A, B and C, so the recommendation
  stands without it — but **nothing here licenses a second display client**, and if PI-009
  reports zero free overlay planes on the primary CRTC, that is new information about what
  any future overlay could do.
- **C3 and C6 quantitatively.** No measurement was taken. D and E are rejected on argument
  and on the project's own auto-stops, not on a benchmark. If someone wants to revive
  either, the burden is a measurement on a 2 GB CM5.
- **Whether the web GUI *should* show the recording-integrity counts it currently omits**
  (F-211). That is a product question for the operator, not an architecture question.

---

## 8. Confidence

| claim | confidence |
|---|---|
| The web GUI consumes `populate_values()` | **confirmed** — `events.py:57`, and `routes.py:29-32` says so |
| A section spec with visibility conditions exists | **confirmed** — `simple_gui.py:541-599` |
| The HDMI GUI does content-driven flow in two regions | **confirmed** — `simple_gui.py:1643-1671,1238-1250` |
| ~925 of 1913 lines are draw/layout | **confirmed** — AST measurement, reproducible |
| DRM master is exclusive | **confirmed** — cinepi-raw's own comment |
| One raising subscriber kills the state bus | **confirmed** structurally; the *observed* consequence is `probable` → PI-014 |
| D is fatal on RAM | **probable** — argued from two existing auto-stops and a 2 GB board; not measured |
| E is fatal on refresh rate | **probable** — argued from the project's own 15 fps ceiling; not measured |
| C matches 12 fps | **unverified** — same renderers, but unmeasured |

Everything above was read on the **`dev`** branch of both repositories (STATE.md D2). No
Raspberry Pi was used.
