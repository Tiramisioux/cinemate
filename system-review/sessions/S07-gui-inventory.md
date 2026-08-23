# S07 — GUI surface inventory & state-model extraction

**Plan entry:** S07 · **Findings:** F-203..F-224 (22) · **Ledger total:** 151
**PI items added:** PI-014, PI-015 · **Pi used:** no · **Subagents used:** none

---

## What was produced

- `deliverables/GUI-INVENTORY.md` — the six surfaces completed, widget by widget, plus a
  capability matrix and a correction to KICKOFF §6.3's LOC column.
- `deliverables/GUI-STATE-MODEL.md` — the 68-field matrix with provider and per-surface
  reach, and §6: what all of it means for ADR-001.
- `harness/gui_field_extract.py` — stdlib-only, reproduces every count in both documents.

## The finding that reframes ADR-001

> **The web GUI has no state model of its own. It consumes the HDMI GUI's.**

`app/main/events.py:57` is `initial_values.update(simple_gui.populate_values())`, and every
later update is a delta of that same 68-field dict, emitted from inside `draw_gui()`.
`routes.py:29-32` says so in a comment.

The operator's hypothesis — *"the three GUI renderings are all derived from `simple_gui`"* —
is **half true, and the true half is the expensive half.** Deriving the surfaces "the same
way" does not require building a shared state model. One exists, 68 fields wide, with one
owner. What is duplicated is presentation only.

Then it got better. `setup_resources` (`simple_gui.py:436-599`) already builds a
**declarative widget spec** — `left_section_layout` / `right_section_layout`, each a label
plus ordered items plus per-item formatters plus an optional visibility `condition`. That
is close to what KICKOFF §7 option C proposes constructing (F-215). The project invented it
independently, for one surface, and did not share it.

**So option C's two hard parts both already exist in some form, and the residual problem is
layout and only layout** — `self.layout` is absolute 1920-reference pixels scaled by
`shrink_x`/`shrink_y`. It scales; it does not reflow (F-008). That is the entirety of the
immediate-mode/retained-mode tension, and no amount of shared state touches it.

## The finding that outranks it in severity

**F-204.** `RedisController.Event.emit` is a bare `for fn in self._handlers: fn(data)` with
no exception guard; `_listen` has none either; the thread is `daemon=True` with no
`is_alive()` check, no watchdog, no restart. Nine subscribers ride it. One raising
subscriber kills the live-state bus permanently — and because `get_value()` serves a cache,
**every surface then displays plausible frozen values rather than an error.**

That is the worst failure category for a camera instrument, and it is the baseline score
for KICKOFF §7 constraint 5. → PI-014.

**F-208 is why it is worth fixing rather than debating:** the guarded version of exactly
this loop already exists in the same codebase. `_notify_resolution_change`
(`cinepi_controller.py:1082-1087`) wraps each callback in `try/except` and logs with
`logging.exception`. Same pattern, ~900 lines away, correct.

## The settings editor is the review's thesis in miniature

Three copies of the action catalogue: Python `ACTION_METHODS` (46), a hardcoded JavaScript
copy (the same 46), and `CinePiController`'s 94 real methods. The two hand-maintained
copies agree **perfectly — including on the same wrong entry**, `set_log` (F-218).

The comment above the Python copy announces itself as a *"Corrected copy … Fixes the 3
entries that don't resolve via getattr()"*. It fixed three and missed a fourth (F-220).
And `GET /api/actions` already computes exactly the check that catches it, shipping an
`available` flag per action — which the template never fetches, and the word `available`
appears nowhere in its 1471 lines of JavaScript (F-219).

Found once, fixed by hand, drifted again, and the mechanical check that would have held the
line is written and unwired. S06's rule was argued from the ledger; this is it happening.

## Strengths recorded

- **F-221 — the recovery console is the best-engineered component in the review**, and it
  answers one seventh of ADR-001 by itself: **surface 4 must not be unified.** Stdlib-only
  by a stated rule with the reason given, honoured via a subprocess rather than an import,
  numbered degradation ladders, a deliberately absent systemd dependency explained in
  place, 86 tests.
- **F-223 — HDMI hot-plug restarts `cinepi-raw`**, properly guarded, and the implication is
  the strongest static evidence yet for PI-009: the preview binds to the display at
  process start and cannot rebind.
- **F-210 — the Socket.IO contract has not drifted.** Nine events, all emitted, all
  handled, clean both ways. Useful counter-evidence in a review about drift.
- **F-206 — control flow was already de-duplicated** across web, CLI and serial via
  `POST /api/v1/cmd`, with the reason in the code. The project has done this kind of
  unification once and it held.

## Corrections made during the session

- **The first field extractor over-counted, 93 vs 68.** It walked every `ast.Dict` inside
  `populate_values` and swept in a nested colour table, reporting `normal`, `lock` and
  `low_voltage` as GUI fields. The script now reads only the `values` binding. This is
  exactly the over-reporting failure S06 recorded — second occurrence, same shape.
- **The Socket.IO scan under-counted**, reporting `reload_stream` and `resolution_change`
  as handled-but-never-emitted. They are emitted from `app/__init__.py`, a third emit site
  the scan did not cover. Not a finding about the code; a finding about the scan — which
  became F-209, since nothing in the repo lists what the channel carries.
- **F-211 was nearly over-claimed.** "The web GUI does not show drop/sync diagnostics" is
  wrong: it renders DROP and SYNC badges from the latched booleans. It shows the *state*
  and not the *counts*. Caught by grepping the template before writing.
- **"Python catalogue has 10 entries the JS lacks" was an artifact of my own regex**
  (`set_|inc_|dec_` misses `rec`, `mount`, `reboot`…). Checked all ten individually; every
  one is present. The two copies are identical. The harness now derives its vocabulary from
  the Python catalogue instead of guessing at prefixes.
- **"The HDMI GUI is display-only" was wrong.** `simple_gui.py:428` restarts the camera
  (F-223, F-224). The capability matrix was corrected before publishing.
- Two stale `STATE.md` watch items fixed: the key-diff harness is written, and the PI queue
  has 15 entries, not 5.

## Method note

No subagents. The surfaces total ~9,000 lines, which is nominally fan-out territory, but
the work turned out to be extraction rather than reading — an AST pass over one function
produced the field inventory that reading 2129 lines would have produced worse. Four of the
five corrections above came from re-checking a script's output against the source, which is
cheap to do inline and was the main quality control available.

## Left undone

- **`cinepi_controller.py` (2626 LOC) is still untraced** — now blocking more than before.
  It is the dispatch target for every GUI control and it gates F-025.
- **The `wifi_hotspot` triangle** — still two thirds unreached, since S04.
- The 1471 lines of JavaScript in `settings_editor.html` were scanned for catalogue names
  and `available`, not read. Surface 3's client-side behaviour is `unverified` beyond that.
