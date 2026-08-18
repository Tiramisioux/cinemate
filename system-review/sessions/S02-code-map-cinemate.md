# S02 — Architecture map, cinemate (Python)

**Date:** 2026-08-18
**Phase:** A — Understanding
**Outcome:** complete. Redis census closed, boot/shutdown traced, control surfaces mapped,
13 findings (F-014..F-026), 2 queue entries.
**Deliverable:** `deliverables/CODE-MAP-cinemate.md`

---

## 1. The Redis key census, closed

S01 handed this over as a failure with a prescribed method. The method worked.

`ParameterKey` (`redis_controller.py:18`) is the canonical registry S01's call-site grep
missed — an 84-member `Enum`, not the 13 literals the grep found. Extracted it with a
Python parse rather than a regex, after a first attempt using `\x27` inside a
single-quoted grep pattern silently dropped the five single-quoted members.

**Result of the diff against `docs/redis-keys.md` (66 documented):**

- **18 keys in code are undocumented** → F-014
- **0 documented keys are missing from code** — the docs are a strict subset, which is the
  better of the two failure modes

The undocumented 18 cluster meaningfully: six `resolution_target_*` /
`dynamic_resolution_*` keys, both `cam1` variants (`tc_cam1`, `log_encode_cam1`,
`last_dng_cam1`), and `packing` / `trigger_mode` / `fps_phase_lock`. That is not random
drift — it is **dual-sensor and dynamic-resolution work that outran its documentation.**
Worth saying explicitly in S09.

### The enum is not enforcement

`set_value` (`redis_controller.py:235`) does
`key.value if isinstance(key, ParameterKey) else str(key)` — any string is accepted. Three
live keys bypass the enum, and one of them, `FSCK_STATUS`, is SCREAMING_CASE against a
uniformly lowercase convention (F-015).

Chasing those three produced most of the session's dead-code findings.

---

## 2. What chasing the orphan keys turned up

| Key | Verdict |
|---|---|
| `audio_vu` | **live**, and a cross-repo contract — F-016 |
| `FSCK_STATUS` | **write-only** — 3 writes, sole reader commented out — F-019 |
| `user_changing_fps` | **write-only** — sole reader is dead code — F-019 |
| `vu_meter` | **phantom** — only a commented-out write — F-018 |

### F-016 is the one that matters

`audio_vu` is declared independently on both sides of the repo boundary, with the *same
constant name*:

```
cinepi-raw/cinepi/cinepi_sound.cpp:22   constexpr char RECORDER_VU_REDIS_KEY[] = "audio_vu";
cinemate/src/module/simple_gui.py:21    RECORDER_VU_REDIS_KEY    = "audio_vu"
```

Same defect class as F-007, but split across two repositories that version independently,
with no comment on either side acknowledging the other. And the read path swallows
failure, so breaking it removes the operator's audio meter mid-take with nothing logged.

**This changes the shape of ADR-001.** The GUI harmonization question is usually framed as
Python-raster vs. browser-CSS. F-016 shows the state contract actually spans **three**
languages — C++ writes, Python reads, HTML/CSS displays. Options B and C in KICKOFF §7
have to answer for the C++ side, not just the two Python/HTML surfaces. S08 should not
treat this as a two-body problem.

### Two dead modules confirmed

- **`timekeeper.py`, 243 LOC, entirely dead** (F-017). `Timekeeper(` appears **nowhere** in
  the repo — not in `src/`, not in `_test/`. `main.py:658` pins `timekeeper = None` and
  `:1026-1027` guards the only use behind `if timekeeper`, which can never be true. This
  confirms a candidate S01 flagged from the import graph.
- **`handle_vu_output()`** (`main.py:633-644`), sole call site commented out at `:743`
  (F-018).

---

## 3. Boot and shutdown

`run_application()` (`main.py:646`) is ~400 lines of straight-line construction — 28
ordered steps, fully tabulated in the deliverable. No composition layer, no builder; the
boot sequence *is* this function.

The shutdown path is where the findings are. `cleanup()` (`:954`) stops eight components
carefully, with a `system_shutdown_in_progress()` branch that widens join timeouts from
0.25 s to 2.0 s on a real power-down — that is thoughtful code. But four live threads are
never told to stop:

| Component | Has `stop()`? | Called? |
|---|---|---|
| `RedisController` pub/sub listener | `stop_listener()` at `:410` | **never, anywhere** (F-022) |
| `USBMonitor` | `:528` | no (F-023) |
| `SSDMonitor` | `:152` | no (F-023) |
| `RedisListener` (2084 LOC) | **none exists** | — (F-023) |
| `storage_preroll` | **none exists** | — (F-023) |

Plus the socketio thread, which is the only ad-hoc thread in `main.py` without
`daemon=True` and is neither stopped nor joined (F-024).

**Stated carefully:** `handle_exit` ends with `os.kill(os.getpid(), sig)`, which kills the
process outright, so the non-daemon thread cannot actually hang exit today. The code shape
is confirmed; the "would hang" consequence is masked and remains unverified. I did not
claim more than that.

The structural cause is worth recording for S05: `run_application()` and `cleanup()` are
**300 lines apart in the same function**, with nothing linking a construction site to its
teardown. Forgetting one is the default outcome, and four components already have.

---

## 4. Control surfaces — the finding I did not expect

There are **two independent paths into `CinePiController`, and only one is serialised.**

- **Path A (locked):** CLI, serial and HTTP all funnel through
  `CommandExecutor.handle_received_data()`, which holds `_dispatch_lock` for the whole
  dispatch (`cli_commands.py:218-257`) and *drops* commands on a 2 s timeout. The comment
  at `:17-20` shows this was deliberate — HTTP was given the ordering guarantee CLI and
  serial had by construction.
- **Path B (unlocked):** GPIO buttons, analog pots, the quad rotary and the keyboard each
  hold a `cinepi_controller` reference and call methods directly. `_dispatch_lock` appears
  **only** in `cli_commands.py` — grep confirms three occurrences, all in that file.

So the four *hardware* surfaces — the ones an operator actually touches during a take —
bypass the lock that the software surfaces share. Recorded as F-025 with the consequence
marked **probable**, not confirmed: whether it is harmful depends on locking inside
`CinePiController`, which I did not trace (2626 LOC, and I was watching the budget).

PI-007 records this, and **its step 1 is a desk task, not a Pi task** — read the controller
for internal locking first. That may settle F-025 for free and should happen before anyone
books hardware time.

### settings.jsonc contains controller method names

Both GPIO and the quad rotary resolve methods reflectively:

```
quad_rotary_controller.py:114   method = getattr(self.cinepi_controller, method_name, None)
settings.jsonc:270              "double_click_action": { "method": "restart_cinemate" }
```

`CinePiController`'s 94 method names are therefore a **user-facing API contract**.
Renaming one silently breaks every camera whose config references it, and the failure is
`logger.error("method %s not found")` — a log line, not a visible error. A typo yields a
button that does nothing (F-026).

Two things follow. First, this is a large part of why `cinepi_controller.py` is 2626 LOC
and why S05/S12 must treat renames there as breaking changes, not refactors. Second, it
explains why `_test/test_quad_rotary_controller_setting_names.py` exists — it guards
exactly this contract, and it is one of the 27 tests that never run (F-006).

---

## 5. Corrections I made mid-session

Recorded because the ledger's value depends on the citations being right.

- **My first `ParameterKey` extraction was wrong.** Used `\x27` inside a single-quoted
  grep pattern, where it is a literal backslash rather than an apostrophe, silently
  dropping the five single-quoted enum members and producing a bogus "5 documented keys
  missing from code" result. Caught it because that result was implausible — docs
  describing keys that do not exist is a rarer failure than the reverse. Redid it with a
  Python parse and an assertion that the values are unique.
- **`audio_vu` was briefly mis-called dead.** A literal grep found only its definition; the
  read at `simple_gui.py:1172` goes through the constant. Corrected before recording.
- **Off-by-one line citations in the deliverable's thread table.** Derived from `sed`
  offsets rather than `grep -n`, then cross-checked against source and fixed. A chained
  `sed` fix then double-substituted one value, which I caught and repaired with an exact
  string replace. Lesson for later sessions: **cite from `grep -n`, never from arithmetic
  on a `sed` window.**

---

## 6. Budget and judgement

Stopped at roughly 57% context per KICKOFF §2.5 rather than starting the
`cinepi_controller.py` internals trace. That trace is genuinely the next thing worth
doing, but it is a 2626-LOC file and starting it here would have risked finishing neither
it nor the handoff.

No subagents. The work was sequential — each finding came from chasing the previous one's
loose end — so fan-out had nothing to parallelise. S04 remains the fan-out session.
