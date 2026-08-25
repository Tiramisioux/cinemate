# GUI surface inventory — CineMate

**Session:** S07 · **Method:** static reading + `harness/gui_field_extract.py` · **Pi used:** no
**Companion:** `GUI-STATE-MODEL.md` (the field matrix) · **Feeds:** ADR-001 (S08)

Completes KICKOFF §6.3, which was explicitly marked incomplete.

---

## 1. Correction to KICKOFF §6.3's table

KICKOFF is immutable, so the correction lives here. Its LOC column conflates
**source** with **template** for surfaces 2 and 3:

| # | Surface | KICKOFF said | Actual |
|---|---|---|---|
| 2 | Web GUI | 965 | `app/main/routes.py` **39** + `templates/template.html` **965** |
| 3 | Settings editor | 3706 | `app/settings_editor.py` **355** + `templates/settings_editor.html` **3706** |

The distinction matters: surface 3's Python is small and mostly a REST API. Its bulk is a
single 3706-line HTML file carrying **1471 lines of JavaScript and 822 of CSS**. Any
unification proposal is a proposal about that file, not about `settings_editor.py`.

---

## 2. The six surfaces, completed

| # | Surface | Bind | Renderer | Paradigm | Source | Total LOC |
|---|---|---|---|---|---|---|
| 1 | HDMI on-camera monitor | `/dev/fb0` | PIL raster → framebuffer | immediate-mode | `simple_gui.py` + `framebuffer.py` | 2323 |
| 2 | Web GUI | `:5000/` | HTML + CSS + Socket.IO | retained-mode | `app/main/routes.py`, `events.py`, `templates/template.html` | 1128 |
| 3 | Settings editor | `:5000/settings-editor` | HTML + CSS + fetch | retained-mode | `app/settings_editor.py` + `templates/settings_editor.html` | 4061 |
| 4 | Recovery console | `:8080` | stdlib HTTP + inline HTML | retained-mode, **isolated** | `services/cinemate-recovery/cinemate-recovery.py` + `jsonc.py` | 1183+ |
| 5 | MJPEG preview | `:8000` / `:8001` | raw video from cinepi-raw | n/a — consumed by #2 | cinepi-raw preview stage | — |
| 6 | Web API + broadcast | `:5000/api/v1`, `:8888` | JSON | no rendering | `app/api.py`, `web_api_settings.py`, `status_broadcast.py` | 265+ |

Surfaces 2, 3 and 6 are **one Flask app** (`app/__init__.py`), served by
`socketio.run(..., port=5000)` at `main.py:935`. Surface 4 is a separate process on a
separate port with a separate systemd unit and, deliberately, no shared code.

### Four render, two do not

Surface 5 produces video, not UI, and is consumed by surface 2 as two `<img>` sources.
Surface 6 emits JSON. **The real GUI count is four, and one of them (4) should never be
unified** — see §6.

---

## 3. Surface 1 — HDMI on-camera monitor

`SimpleGUI` is a `threading.Thread`. Its `run()` loop wakes on a dirty flag, calls
`populate_values()` to build a **68-field** dict, and passes it to `draw_gui()`, which
rasterises into a PIL image and blits to the framebuffer.

### Widgets

| Region | Widget | Fields |
|---|---|---|
| Top row | EI · SHUTTER · EXP · FPS · WB · RES, each label + value | `iso`, `shutter_speed`, `exposure_time`, `fps`, `color_temp`, `res` (+ their `*_label`s) |
| Top row | HDR badge, LOG badges (per camera) | `hdr_badge`, `log_badge_cam0`, `log_badge_cam1` |
| Left column | Grouped sections **CAM / MON / AUD** | `sensor`, `aspect`, `zoom_factor`, `anamorphic_factor`, `mic_sample_rate`, `mic_bit_depth` |
| Right column | Grouped section **CAM1** (dual-sensor) | `sensor_cam1`, `aspect_cam1`, `exposure_time` |
| Right edge | VU meter (2 channels, peak-hold) | `vu_levels`, `vu_peaks` |
| Bottom row | MEDIA · clip · frames · CPU · TEMP · RAM · BATT | `disk_label`, `disk_space`, `write_speed`, `clip_name`, `frame_count`, `recording_time`, `cpu_load`, `cpu_temp`, `ram_load`, `battery_level` |
| Status boxes | DROP · SYNC · LOCK · low-voltage | `drop_frame_latched`, `frames_off_sync`, `lock`, `low_voltage` |
| Overlay | Preview guide rectangle | computed by `_calculate_preview_guide_rect` |

### The important structural fact: its layout is already data

`setup_resources` (`simple_gui.py:436-599`) builds **three declarative tables**:

```
self.layout              field -> {"pos": (x, y), "size": px, "font": "regular"|"bold"}
self.colors              field -> {"normal": rgb, "inverse": "black"}
self.left_section_layout [ {"label": …, "condition": λ, "items": [{"key": …, "text": λ}]} ]
self.right_section_layout  (same shape)
```

The third is a **widget/grouping/visibility spec** — a label, an ordered item list,
per-item formatters, and an optional visibility predicate. That is very close to what
KICKOFF §7 option C proposes building. **It already exists.** See F-215, and §5 below for
what that does to the option costings.

Two caveats, stated so S08 does not over-read this:

1. The formatters and conditions are **lambdas**, so these tables are Python, not
   serialisable data. The shape is right; the encoding is not.
2. `self.layout` is absolute 1920-reference pixel positions, scaled by `shrink_x` /
   `shrink_y` at draw time (F-008). It **scales, it does not reflow.** That part is a real
   obstacle and is not solved by the section spec.

Six display items are disabled by being commented out *inside* these tables (F-216) —
in a structure that already supports a `condition` predicate.

### It is not a display-only surface

`_maybe_restart_camera_for_display_attach` (`simple_gui.py:407-433`) **restarts
`cinepi-raw` when an HDMI display is hot-plugged**, *"so preview binds to the active
display"*. It is carefully guarded — a cooldown, a not-recording/not-writing precondition
with a deferral log, and an exception handler that re-arms the pending flag rather than
dropping the request (F-223).

Two things follow, both of which S08 needs:

1. **cinepi-raw binds its preview to the display at process start and cannot rebind.**
   That is why the mechanism is a restart and not a reconfigure. This is the strongest
   statically-derived evidence available for PI-009 and for ADR-001 constraint 2 — and it
   is a hard constraint on options D and E, which would have to own the same behaviour.
2. Any renderer that replaces `simple_gui` inherits this responsibility (F-224). The
   migration cost in KICKOFF §7 constraint 7 is not only pixels.

---

## 4. Surface 2 — Web GUI

**It has no state model of its own.** On socket connect:

```python
initial_values.update(simple_gui.populate_values())   # events.py:57
```

and every later update is a delta of the same dict, emitted from inside `draw_gui()`
(`simple_gui.py:1764-1775`). `routes.py:29-32` states this in a comment.

So the web GUI is a **second renderer over surface 1's state model**, already. What is
duplicated between them is presentation only: colours (F-007), label strings (F-214), and
one CSS rule that names a Python method (F-217).

Consequences worth carrying into ADR-001:
- Browser update cadence is the framebuffer redraw cadence (F-207) — **PI-015 measured this
  at ~7.5 Hz (132.6ms mean interval) on real hardware, not the ~12fps this finding assumed.
  That is the only number ADR-001 constraint 4 has ever had.**
- The emit sits *before* `draw_gui`'s `if not fb: return`, so the web GUI keeps working
  with no HDMI display attached. Preserve that deliberately. **PI-015 confirmed this on a
  real physical HDMI detach+reattach (411 events, zero gaps >620ms over 55s) — the headless
  path is real, not accidental.**
- If the `SimpleGUI` thread dies, the web GUI freezes with it. (Not directly tested — PI-015
  tested the physical-cable-pull case, not killing the thread specifically; see
  `PI-VERIFICATION-QUEUE.md` "Not run".)

**Control has already been unified** (F-206): the browser POSTs command lines to
`/api/v1/cmd`, the same path the CLI and serial use, with the reasoning in the code —
*"behaviour cannot drift between them."*

### Socket.IO channel — 9 events, no drift

`background_color_change`, `fps_update`, `gui_data_change`, `initial_values`,
`parameter_change`, `reload_browser`, `reload_stream`, `resolution_change`,
`shutter_a_update`. Every one is emitted by the server and handled by the browser; no
orphans in either direction (F-210). Emitted from **three** modules with no registry
(F-209).

---

## 5. Surface 3 — Settings editor

A REST API (`settings_editor.py`, 355 lines, 13 routes) plus a 3706-line single-file
front end. Different visual language from surface 2 and no shared CSS.

### What it edits

| Route group | Target |
|---|---|
| `/api/settings` GET/PUT, `/default`, `/parse` | `settings.jsonc` |
| `/api/config-txt` GET/PUT, `/default`, `/parse` | `/boot/firmware/config.txt` |
| `/api/actions` GET | the action catalogue — **zero consumers** (F-219) |
| `/api/raw/storage`, `/api/raw/takes`, `…/<name>` DELETE, `…/download` | recorded takes |

### The action catalogue is stored three times

| Copy | Count | Location |
|---|---|---|
| Python `ACTION_METHODS` | 46 | `settings_editor.py:63-114` |
| JavaScript, hardcoded | 46 (identical set) | `templates/settings_editor.html` |
| The truth — `CinePiController` public methods | 94 | `cinepi_controller.py` |

The two hand-maintained copies agree **perfectly, including on the same wrong entry**:
`set_log`, where the method is `set_log_encode` (F-118, F-218). The comment at
`settings_editor.py:56-62` announces itself as a *"Corrected copy … Fixes the 3 entries
that don't resolve"* — it fixed three and missed the fourth (F-220).

And `GET /api/actions` **already computes the check that catches this**, resolving every
entry against `_public_method_names(cinepi_controller)` and shipping an `available` flag.
The template never fetches it; the word `available` does not appear in its JavaScript
(F-219). The fix is written and unwired.

> This is the review's cleanest single illustration of its own thesis: the duplication was
> found once, corrected by hand, drifted again, and the mechanical check that would have
> held the line exists in the same file and is not called.

---

## 6. Surface 4 — Recovery console, and why it must stay separate

Stdlib-only by an explicit rule stated at the top of the file, with the reason given:

> *"'The venv is broken' and 'redis is down' are supported failure modes that this console
> exists to survive; every import it makes is another way for it to die exactly when it is
> needed."*

It honours the rule. Where it needs the app's settings loader it runs it as a
**subprocess** under the venv python (`_VENV_VALIDATOR`), not as an import. It documents a
deliberately *absent* systemd dependency — *"that coupling is the bug being fixed, not an
oversight"* — and builds numbered degradation ladders where the last rung still answers.
It is covered by **86 tests** (F-221).

**ADR-001 constraint answered outright:** surface 4's value *is* its isolation. Unifying it
with surfaces 1–3 would delete the property it exists for. Any harmonisation proposal must
scope itself to surfaces 1, 2 and 3.

---

## 7. Surfaces 5 and 6

**5 — MJPEG preview.** Produced by cinepi-raw, consumed by surface 2 as
`http://{host}:8000/stream` and `:8001`. `routes.py:11-20` derives the host from
`request.host` rather than hardcoding `cinepi.local`, with the hotspot case named in the
comment. Not a GUI; it is the video layer the HDMI GUI overlays.

**6 — Web API.** `app/api.py`: `/cmd`, `/get/<key>`, `/status`, `/commands`, `/hello`,
`/events` (SSE), behind a `before_request` token check. Plus the `:8888` status broadcast.
No rendering. `/cmd` is the unified control path (F-206) and `/commands` is
self-describing — the API is the healthiest boundary in the system.

---

## 8. Surface capability matrix

What each surface can *do*, as distinct from what it displays.

| Capability | 1 HDMI | 2 Web | 3 Settings | 4 Recovery |
|---|---|---|---|---|
| Show live camera state | ✓ | ✓ | — | — |
| Show live video | overlay on preview | ✓ (MJPEG) | — | — |
| Change ISO / shutter / fps / WB | — | ✓ | ✓ (as actions) | — |
| Start / stop recording | — | ✓ | ✓ | — |
| Recording-integrity **counts** | ✓ | — (badges only, F-211) | — | — |
| VU meters | ✓ | ✓ | — | — |
| Browse / delete / download takes | — | — | ✓ | — |
| Edit `settings.jsonc` | — | — | ✓ | ✓ |
| Edit `config.txt` | — | — | ✓ | ✓ |
| Read service state / journal | — | — | — | ✓ |
| Works when redis is down | — | — | — | ✓ |
| Works when the venv is broken | — | — | — | ✓ |
| **Restart `cinepi-raw`** | ✓ (on HDMI attach, F-223) | ✓ (as an action) | ✓ (as an action) | — |

The bottom two rows are the whole argument of §6.

---

## 9. Confidence

Every count in this document is reproducible by
`python3 system-review/harness/gui_field_extract.py --repo .` or by the cited `grep -n`.
No Raspberry Pi was used and no runtime behaviour is asserted as observed.

**Lower bounds, not totals.** Field names built dynamically are invisible to a static
scan, and this review has been caught under-counting three times and over-counting once.
Read every number as "at least".

Specifically `unverified` at the time, since settled by the 2026-08-24 Pi session:
- How the framebuffer overlay and the DRM preview actually compose (**PI-009**) — **done**:
  the GUI (fbcon) holds a genuine DRM plane; cinepi-raw's own preview held none under the
  tested conditions (no `--same-hdmi`, no confirmed-attached preview client). Narrower and
  more concrete than "two interfaces racing" — see ADR-001.
- The HDMI redraw cadence in practice — **measured (PI-015): ~7.5 Hz (132.6ms mean
  interval)**, not the ~12fps this document's earlier drafts assumed.
- Whether the web GUI's dependence on the `SimpleGUI` thread (F-207) is observable as a
  freeze in the field — **still not directly tested**: PI-015 confirmed the headless path
  (no HDMI attached) survives a real cable pull, but did not stop the `SimpleGUI` thread
  itself, which is a different, more invasive test.
