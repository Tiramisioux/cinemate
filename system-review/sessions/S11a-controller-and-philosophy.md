# S11a — `cinepi_controller` traced, and the philosophy tested

**Plan entry:** S11 (split; **S11b carries style / entry-points / skill payload**)
**Findings:** F-268..F-271 (4) · **Ledger total:** 186 · **Pi used:** no · **Subagents:** none
**Deliverable:** `deliverables/CINEMATE-PHILOSOPHY.md` · **Discharged:** PI-007 step 1

---

## The deferral is over

`cinepi_controller.py` had been deferred **six times**, S02 through S10. It took one AST pass
and four greps, and it settled a finding that has been carrying an "unknown severity" flag
since S02.

**F-270 — it is wide, not deep.** 2626 lines is **151 methods on one class** (94 public, 57
private, zero `@property`), averaging ~16 lines. Only `__init__` (239 lines) is oversized;
the next largest is 108. That is a broad facade, not tangled logic — which is *why* six
sessions could defer it without the review stalling, and it changes what S12 should
recommend: split **by concern into modules**, not by extracting long methods. There are
almost none to extract.

**F-268 — F-025 settled, and broader than recorded.** `_dispatch_lock` lives in
`CommandExecutor` (`cli_commands.py:21`, 2 s timeout) and serialises **three** input paths:
CLI, serial, HTTP `/api/v1/cmd`. **Six** modules bypass it entirely via `getattr` —
including **`storage_preroll.py`** and **`simple_gui.py`**, which F-025 did not name.

**F-269 — and there is no internal fallback.** Three locks, **9 acquisition sites across 151
methods**, guarding three specific concerns (shutter/exposure state, storage-profile restart,
resolution-change pacing). So: *the only general serialisation in the system is a lock two
thirds of the input surfaces do not take, and the object it protects does not protect
itself.*

PI-007 step 1 is discharged with no hardware, exactly as `STATE.md` predicted. What remains
for the Pi is only whether the race is observable.

## The philosophy document

All eight of KICKOFF §9's principles survive; **none survives unamended.** Two refined (P1
Redis-as-single-source is true *between* processes and cached *within* one; P4 hardware facts
are single-source but **single-consumer** — cinepi-raw does not read `sensors.json`), three
confirmed outright (P2, P5, P7), one confirmed and bounded (P6), and **two are stated by the
project and violated by the product** (P3, P8).

Four principles added, each evidenced by code the project already wrote: **P9** degrade in
ladders whose last rung still answers · **P10** state the reason in place, especially for a
compromise · **P11** duplicated truth must be deleted, or carry a named reason *and* a check
· **P12** route, don't replicate.

### The pattern that emerged, which is the document's spine

> **This project knows what it believes, states it in prose, and enforces it nowhere.** And
> where a principle is violated, the correct implementation usually exists a few hundred
> lines away.

Three instances, and they are the same shape:

| violated | the correct version, already in-repo |
|---|---|
| P3 (F-204: the state bus dies silently) | the same dispatch loop, guarded, ~900 lines away (F-208) |
| P8 (F-271: the settings editor deletes all 74 comments) | `cinemate-recovery.py`'s `write_config_file` — raw text, backup first |
| P1 (F-118: a drifted catalogue) | `GET /api/actions` computes the check and has zero consumers (F-219) |

That reframes the review's thesis: *the gap is not between what this project believes and
what it does; it is between what it does once and what it does consistently.*

## F-271 — the sharpest new finding

Going after P8 produced the best single defect of the session. **Saving from the web settings
editor destroys every comment in `settings.jsonc`** — `put_settings` writes
`json.dumps(settings, indent=2)` over a file that is **74 comment lines out of 386 (19%)**.
No warning. No backup: the word does not appear in `settings_editor.py`.

And the correct implementation is ~1000 lines away in the same repository. The recovery
console's `write_config_file` writes the user's **raw text** and backs up first, with a
docstring reading *"Back up, then atomically replace. The order is not negotiable."*

KICKOFF P8 says the comments *"are part of the product."* One save from the GUI deletes 19%
of it.

## Corrections made during the session

- **I read the controller as having no internal locking at all.** My grep required a leading
  underscore (`with self\._[a-z_]*lock`) and missed `parameters_lock_obj`'s four acquisition
  sites. The corrected figure is 9 sites, not 5. Sixth pattern-matching under-report of the
  review — caught by cross-checking the declaration list against the usage list rather than
  trusting one grep.
- F-025's bypass list said four surfaces; the real count is six. Recorded as a broadening in
  F-268 with the two new names called out, not as a silent amendment.

## Why S11 was split

Four deliverables, and the controller trace was a prerequisite for one of them
(`ENTRY-POINTS.md`, whose rows mostly land in `cinepi_controller.py`). The trace plus the
philosophy document is a full session's work and both are finished; `CINEMATE-STYLE.md`,
`ENTRY-POINTS.md` and `SKILL-PAYLOAD.md` go to S11b with the controller now mapped.

## Left undone

- **S11b:** style, entry-points, skill payload.
- **`dng_encoder.cpp` on `dev` (687 lines changed)** — largest cinepi-raw hole, from S07b.
- **The `wifi_hotspot` triangle** — two thirds unreached since S04. Its credential ladder is
  now cited in P7/P9, so S11b may want to read it properly.
- **The 1471 lines of JavaScript in `settings_editor.html`** were scanned, not read.
