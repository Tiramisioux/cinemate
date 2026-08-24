# ADR-001 — GUI harmonization

**Status:** proposed · **Session:** S08 · **Date:** 2026-08-23
**Decides:** KICKOFF §7 · **Inputs:** `GUI-INVENTORY.md`, `GUI-STATE-MODEL.md`, `REDUNDANCY-REPORT.md`, `STANDARDS-PROPOSAL.md`
**Blocked on:** ~~PI-009 for constraint 2 · PI-013/PI-015 for constraints 3 and 4~~ **all
closed 2026-08-24 — see correction below.**
**Pi used:** no at time of writing. Reconciled 2026-08-25 against a Pi session that ran
2026-08-23/24 — see `PI-RESULTS-2026-08-24.md`.

---

> ## ⚠ CORRECTION — premise error and three constraints settled, reconciled 2026-08-25
>
> **The board.** §3 C3 and §4/§7 state the dev unit is a **2 GB CM5 Lite**. It is not: the
> Pi session measured **4048 MB total RAM** on the actual hardware (`free -m`, confirmed
> repeatedly across PI-016's three passes). The operator has since confirmed directly: **the
> current dev unit genuinely is the 4 GB variant, and it is not a fluke** — but **2 GB
> remains a real target board the installer and compile step must keep working on.** So this
> ADR's headroom argument was wrong twice over: wrong about the board it was reasoning from,
> and — see below — wrong about the conclusion that board's numbers would have supported
> even if the RAM figure had been right.
>
> **C3 (RAM/CPU), measured, not argued.** PI-016 forced the sensor's true peak mode
> (4056×3040, 12-bit) and ran a real 60s take: `available` memory never dropped below
> **~2970 MB of 4048 MB (73%)** at any point. The **~300 MB-free-at-peak argument this ADR
> rejected D and E on does not hold on the tested board.** This directly **CONTRADICTS** the
> `D is fatal on RAM` row in §8's confidence table and the C3 cells in §4/§5 — see those
> sections for the correction, not just this banner.
>
> **What does *not* change: the decision.** Reject D, reject E, adopt C — unchanged. Not
> because the RAM argument survives (it doesn't), but because **both rejections were always
> two independent legs, and one leg each is untouched by this measurement:**
> - **D** was rejected on **C1 (DRM master exclusivity, fatal) and C3 (RAM, fatal)**
>   together. C1 is a structural fact from cinepi-raw's own comment, confirmed byte-identical
>   on `dev`, and nothing in the Pi session touches it. D stays rejected on C1 alone.
> - **E** was rejected on **C3 and C4 (refresh rate)** together. C4's argument — no
>   HTML→bitmap rasterizer hits 12 fps full-screen on this class of hardware, and the
>   project's own doc caps the *cheaper* PIL path at 15 fps — has nothing to do with RAM. E
>   stays rejected on C4 alone.
>
> **On 2 GB, this is genuinely unmeasured**, and given the operator's instruction that 2 GB
> stays a supported target, that gap is real — but it no longer matters to this ADR's
> conclusion, since neither rejection depends on the RAM figure anymore. A future session
> measuring a real 2 GB unit would be informative for the installer/compile-support question,
> not for D/E's status here.
>
> **C2 (GUI/preview composition) — PI-009 done.** The GUI (`fbcon`, i.e. `simple_gui.py`
> writing `/dev/fb0`) holds a genuine DRM plane (`plane-2` on `crtc-2`, driving `HDMI-A-1`).
> Under the tested conditions (no `--same-hdmi`, no confirmed-attached preview client),
> **cinepi-raw's own DRM preview held no plane at all** — narrower and more concrete than
> this ADR's "two interfaces racing" framing, which assumed active contention that was not
> observed. 55 of 56 planes on the card sat idle. The `--same-hdmi` on/off toggle comparison
> was not reached (deferred over a restart-hang risk) — see §3 C2 below for what remains
> open.
>
> **C4 (refresh rate) — PI-015 done.** Measured cadence is **~7.5 Hz (132.6 ms mean
> interval)**, not the ~12 fps this ADR assumed throughout — the only number this constraint
> has ever had. The headless path (browser updates with no HDMI attached) is confirmed real
> on a genuine physical detach/reattach, not accidental.

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

### C2 — How the GUI and the preview compose · **PI-009 done — answered, narrower than framed**

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

**PI-009 measured it.** `/sys/kernel/debug/dri/1/state` on the live device: 56 total planes
across 4 CRTCs. Exactly one is claimed — `plane-2` → `crtc-2`, format RG16, `1600x1024`,
`allocated by = [fbcon]` — the kernel console framebuffer `simple_gui.py` writes via
`/dev/fb0`, driving `HDMI-A-1`. **Under the tested conditions (no `--same-hdmi`, no
confirmed-attached preview client), cinepi-raw's own DRM preview held no plane at all.** The
other 55 planes sat idle. This confirms the GUI occupies a genuine DRM plane (not a
side-channel) and shows plenty of spare capacity exists in principle — but it does **not**
show the two interfaces actually contending for the same plane, because cinepi-raw's preview
wasn't exercised in this session. **Still open:** the `--same-hdmi` on/off toggle comparison
(deferred over a restart-hang risk, F-283) — the number that would show whether the clone
path's plane claim collides with the GUI's.

### C3 — RAM and CPU · **PI-016 done — measured, CONTRADICTS the ADR's own argument**

There are **two** independent RAM auto-stops (F-235): cinemate trips at
`RAM_LIMIT_PERCENT = 80`, cinepi-raw trips on encoder pool exhaustion (*"RAM pool
exhausted — recording stopped"*). This ADR reasoned from those two stops plus an assumed
2 GB board to conclude a resident renderer has no headroom. **PI-016 measured it on the
actual hardware (a genuine 4 GB unit, confirmed by the operator) at the sensor's true peak
mode (4056×3040, 12-bit) across a real 60s take: `available` memory never dropped below
~2970 MB of 4048 MB (73%).** The auto-stops exist and are real, but the headroom argument
against a resident renderer does not hold on this board as measured. **2 GB is unmeasured**
and remains a target the installer/compile step must support — see the correction banner
above for why that doesn't change this ADR's conclusion.

### C4 — Refresh rate and latency · **PI-015 done — the ~12 fps assumption was wrong**

`target_fps = 12` → `min_frame_interval ≈ 0.083 s`; `slow_refresh_interval = 1.0 s`; idle
wait 0.1 s; event-driven with a cap (`simple_gui.py:201-203`). `docs/simple-gui-refresh-
tuning.md` documents all of it accurately (F-234) and states the operational ceiling:
*"above 15 fps: usually not recommended with the current full-screen PIL-to-framebuffer
path."*

**That ceiling is the number every option must beat or match.** **PI-015 measured the actual
cadence at ~7.5 Hz (132.6 ms mean interval) on real hardware — not ~12 fps.** 411
`gui_data_change` events over 55s, zero gaps exceeding 620 ms, across a genuine physical HDMI
detach/reattach. The headless path (events keep arriving with no display attached) is
confirmed real, not accidental — and F-223's claim that reattaching a display restarts the
camera did **not** reproduce in the same test.

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

### C6 — Boot time · **still unquantified; deferred, not forgotten**

`camera-ready.sh` runs as `ExecStartPre` with `MAX_ATTEMPTS=30` at `RETRY_INTERVAL=1`, so
up to ~30 s can elapse **before `main.py` starts**, ordered ahead of the console handoff
(F-236). Any option that adds a renderer startup adds to a budget that is already long.
**PI-016 attempted `systemd-analyze`/`camera-ready.sh` timing in the same session and did
not reach it** — deferred behind the other live issues that session surfaced (sensor fault,
restart-hang). No measurement exists yet; this is the one open number C3/C4 no longer share.

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
| n/a — no new display client | unchanged | ≈ nil (same renderers) | should match ~7.5 Hz (PI-015); verify | inherits F-204 until fixed | ≈ nil | **~925 lines, incremental** |

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
| **fatal** | fatal | not fatal (measured) | poor | poor | poor | total |

- **C1:** a kiosk browser wants DRM/KMS or a Wayland compositor; either takes DRM master,
  which cinepi-raw holds exclusively. The one workaround the project already built for this
  problem was shared memory, precisely to *avoid* a second display client. **This alone is
  sufficient to reject D — unaffected by the C3 correction below.**
- **Operator constraint (2026-08-25), independent of C1–C7:** the HDMI output is used today
  for cinepi-raw's own libcamera-derived DRM preview specifically because of its image
  quality — a browser driving HDMI would mean giving that up (or fighting it for the
  display, which C1 already says can't work). This is a product reason to reject D even in
  a hypothetical where C1 were somehow not fatal; it is not just a technical constraint, it
  is a stated preference for what the display is *for*.
- **C3:** ~~a resident browser on a 2 GB board that already auto-stops recording for memory
  at UHD. Two independent RAM stops exist because memory is already the binding
  constraint.~~ **CONTRADICTED by PI-016**: on the actual (4 GB, not 2 GB) hardware,
  `available` memory never dropped below ~2970 MB of 4048 MB at the sensor's true peak load.
  The two auto-stops are real but did not fire, and memory was not the binding constraint in
  this test. Not independently fatal to D anymore — D is rejected on C1 alone. (2 GB target
  hardware remains unmeasured.)
- **C5:** the HDMI GUI is the last thing you want fragile; a browser is a large, complex,
  independently-crashing process in front of the operator's only monitor.

**Reject — on C1, decisively; C3 no longer supports this on its own.**

### E — Server-side HTML → raster, blit to the framebuffer

| C1 | C2 | C3 | C4 | C5 | C6 | C7 |
|---|---|---|---|---|---|---|
| **not fatal** | unchanged | not fatal (measured) | **fatal** | poor | poor | total |

> **Correction to KICKOFF §7.** It says C1 is *"likely fatal to D and E"*. **That is right
> for D and wrong for E.** E rasterises to a bitmap and writes `/dev/fb0` — exactly what
> `simple_gui` does today. It introduces **no second DRM client.** C1 does not kill E.

~~E dies on C3 and C4.~~ **E dies on C4 alone now — C3 is CONTRADICTED by PI-016** (same
measurement as D's: ~2970 MB available at peak on the 4 GB tested unit, not the ~300 MB this
ADR assumed). **C4 stands independently and is sufficient by itself:** an HTML→bitmap
rasteriser capable of matching real-hardware GUI cadence (~7.5 Hz measured by PI-015, let
alone the ~12 fps this ADR originally assumed) does not exist in a form this project could
adopt; the available ones are either a headless browser (which is option D's memory cost
without its benefits — and D is separately rejected on C1's DRM exclusivity, not on memory)
or print-oriented renderers measured in seconds per page. The project's own doc already
warns that the *current, far cheaper* PIL path should not exceed 15 fps.

**Reject** — on performance (C4) alone; not on DRM, and no longer on RAM.

---

## 5. Decision matrix

| | A | B | C | D | E |
|---|---|---|---|---|---|
| C1 DRM master | n/a | n/a | n/a | **fatal** | ok |
| C2 composition | answered¹ | answered¹ | answered¹ | fatal | answered¹ |
| C3 RAM/CPU | base | nil | ≈nil | not fatal² | not fatal² |
| C4 refresh | ~7.5 Hz³ | ~7.5 Hz³ | verify³ | poor | **fatal** |
| C5 failure mode | **negative** | negative | negative→fixable | poor | poor |
| C6 boot | base | nil | ≈nil | poor | poor |
| C7 cost | 0 | ~1 day | ~925 lines | total | total |
| kills F-007/F-214 | no | **yes** | **yes** | yes | yes |
| kills the layout duplication | no | no | **yes** | yes | yes |

¹ **PI-009, done.** The GUI holds a genuine DRM plane; cinepi-raw's own preview held none
under the tested conditions (no `--same-hdmi`, no confirmed-attached preview client) — 55 of
56 planes idle. Does not discriminate between A, B and C, same as before, but the `?` is now
an answer rather than an open question: no observed contention, `--same-hdmi` toggle still
untested.

² **PI-016, done — CONTRADICTS the `fatal` this row used to carry.** Measured on the actual
(4 GB, confirmed) hardware at the sensor's true peak load: available memory never dropped
below ~2970 MB of 4048 MB. D stays rejected on C1 alone; E stays rejected on C4 alone — see
§4. 2 GB target hardware remains unmeasured.

³ **PI-015, done.** Measured cadence ~7.5 Hz (132.6 ms mean interval), not the ~12 fps this
matrix originally carried for A/B. C's target is to match that number, still unmeasured for
C specifically.

---

## 6. Recommendation

**Reject D and E. Adopt C, reached through B, and fix F-204 before either.**

**Unchanged by the 2026-08-25 reconciliation** (see the correction banner above): D and E
were each rejected on two independent grounds; the Pi session removed the shared RAM leg
from both but left D's DRM-exclusivity (C1) and E's refresh-rate (C4) legs standing on
their own. The recommendation below is the same recommendation, now resting on narrower,
hardware-confirmed ground instead of an argument that turned out to be wrong about the
board it was reasoning from.

**Operator confirmation (2026-08-25):** the stated goal is *"one file to work with, when
adjusting the GUI, and that it propagates to the web instances"* — that is option C exactly,
not a rephrasing of it. Steps 2–3 below (lift the section spec into data; generalise the
layout primitives so both backends read it) are that one-file goal's implementation path.

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

- ~~**C2.** PI-009 is open.~~ **PI-009 is done (2026-08-24).** It found the GUI holds a
  genuine DRM plane and cinepi-raw's own preview held none under the tested conditions —
  narrower than "two interfaces racing", and it still does not discriminate between A, B and
  C, so the recommendation is unaffected. **Still open:** the `--same-hdmi` toggle comparison
  (deferred over a restart-hang risk, F-283) — the number that would show whether the clone
  path's plane claim collides with the GUI's. **Nothing here licenses a second display
  client** on the strength of 55 idle planes; the exclusivity argument (C1) is untouched.
- ~~**C3 and C6 quantitatively.** No measurement was taken.~~ **C3 is now measured (PI-016)
  and CONTRADICTS the argument this ADR made** — see the correction banner and §4. D and E
  no longer rest on C3 at all; each stands on an independent, unaffected leg (C1 for D, C4
  for E — C4 itself now measured too, by PI-015). **C6 (boot time) remains genuinely
  unquantified** — PI-016 attempted it in the same session and did not reach it. If anyone
  revives D or E on some other basis, C6 is the number still missing, and — separately —
  **a 2 GB unit's C3 number is still missing too**, since the operator has confirmed 2 GB
  stays a supported target even though the tested unit is 4 GB.
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
| DRM master is exclusive | **confirmed** — cinepi-raw's own comment, byte-identical on `dev` |
| The GUI holds a genuine DRM plane; cinepi-raw's preview held none this session | **confirmed** — PI-009, `/sys/kernel/debug/dri/1/state` |
| One raising subscriber kills the state bus | **confirmed** — structurally, and the *observed* consequence: PI-014, both the HTTP API and SSE stream froze permanently and silently |
| ~~D is fatal on RAM~~ — **D is fatal on C1 (DRM), independent of RAM** | **confirmed** on C1 (unchanged); the RAM leg is **CONTRADICTED** — PI-016 measured ~2970 MB available at peak on the actual (4 GB) hardware, not the ~300 MB this ADR assumed on an assumed 2 GB board |
| ~~E is fatal on refresh rate~~ — **E is fatal on C4 alone, independent of RAM** | **confirmed** — PI-015 measured ~7.5 Hz actual cadence, well under any plausible HTML→bitmap rasterizer's throughput at this class of hardware; the RAM leg (C3) is contradicted the same way as D's |
| C matches ~7.5 Hz (was: 12 fps) | **unverified for C specifically** — same renderers as today, target number now measured (PI-015), still unmeasured for C's own implementation |
| The dev unit is a 2 GB board | **REFUTED** — PI-016 measured 4048 MB total; the operator confirmed the 4 GB unit is genuine, not a fluke. **2 GB remains an unmeasured target for install/compile support**, per the operator |

Everything above was read on the **`dev`** branch of both repositories (STATE.md D2) and
reconciled 2026-08-25 against the 2026-08-23/24 Pi session (`PI-RESULTS-2026-08-24.md`).
