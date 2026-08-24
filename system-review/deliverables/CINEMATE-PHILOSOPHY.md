# CineMate philosophy — the eight principles, tested

**Session:** S11a · **Method:** KICKOFF §9's hypotheses against code, with citations
**Pi used:** no · **Branch:** `dev`, both repos

KICKOFF §9 offered eight candidate principles drawn from the codebase's own comments and
structure, and asked for each to be confirmed, refuted or refined **against code** — noting
that *"where the codebase violates its own principles, those violations are findings."*

All eight survive in some form. **None survives unamended.** Three are violated by the
product itself, and in two of those three the correct implementation already exists
elsewhere in the same repository.

---

## The pattern that runs through all eight

Before the individual verdicts, the thing eleven sessions make unmissable:

> **This project knows what it believes, states it in prose, and enforces it nowhere.**

Every principle below is written down somewhere — in a comment, a docstring, a doc page.
Not one is checked by anything. And where a principle is violated, the violation is almost
never ignorance: **the correct implementation usually exists a few hundred lines away.**

| principle violated | the correct version, already in the repo |
|---|---|
| P3 fail visible (F-204: the state bus dies silently) | `cinepi_controller.py:1082-1087` — the same dispatch loop, guarded, ~900 lines away (F-208) |
| P8 config comments are part of the product (F-271: the settings editor deletes all 74) | `cinemate-recovery.py` `write_config_file` — writes raw text, backs up first, *"The order is not negotiable"* |
| P1 Redis is the single source (F-118: a catalogue that drifted) | `GET /api/actions` already computes the check — and has zero consumers (F-219) |

That is the review's central finding stated as philosophy rather than as a defect list:
**the gap is not between what this project believes and what it does; it is between what it
does once and what it does consistently.**

---

## P1 — "Redis is the single source of live state" · **REFINE**

**True as an aspiration and as topology, false as an invariant.**

Confirmed: `redis_controller` has the widest fan-in in the repo — 10 importing modules
(CENSUS §4) — and the cross-repo contract is genuinely the `cp_controls` channel, 23 shared
keys on `dev` (F-226). The web GUI holds no state of its own; it consumes
`simple_gui.populate_values()` verbatim (F-203).

Refuted as an invariant, four ways:

- **`get_value()` does not read Redis.** It reads a local cache kept fresh by a listener
  thread (S02). Every "read from Redis" in this system is a read from a cache — and per
  F-204 that cache can silently freeze.
- **Four independent `StrictRedis` clients bypass `RedisController` entirely**, with
  hardcoded `localhost:6379` (F-105).
- **The registry is convention, not enforcement.** `set_value` accepts any string; live keys
  bypass the enum (F-015, F-212).
- **15 of the HDMI GUI's 68 fields are not recoverable from Redis at all** — they are
  `SimpleGUI` instance state (`GUI-STATE-MODEL.md` §3).

**Restated as it actually holds:** *Redis is the single source of live state **between
processes**. Within a process, state is cached, and some of it never reaches Redis.*

---

## P2 — "The Pi is the runtime truth" · **CONFIRMED, and the codebase practises it**

This one the project genuinely lives. `ssd_monitor.py:1122-1125` records a falsified
experiment (1 MB exFAT clusters break the macOS driver). `dualHdmiPreviewStage.cpp:19-20`
labels itself *"a first, hardware-untested cut"* rather than claiming it works. The
docstring at `_test/test_simple_gui_preview_guide.py` explains that a golden value was
*"verified against real IMX585/IMX477 hardware"* and that an earlier test hardcoded the
pre-fix value and was never updated.

**The review itself is the strongest evidence:** 16 PI-queue items exist because static
reading kept hitting the same wall the codebase's own comments describe.

**One refinement.** The principle says hardware disposes — but F-234 shows
`simple-gui-refresh-tuning.md` documents every timing constant accurately, and F-267 shows
the installer and its docs agree on everything checkable. **Static truth is maintained well
here.** The principle should not be read as licence to leave statically-checkable things
unchecked; four stdlib-only checkers now exist that need no Pi at all.

---

## P3 — "Fail visible, never silent" · **STATED, AND THE MOST-VIOLATED PRINCIPLE IN THE SYSTEM**

The project states it itself, at `storage_profiles.py:41-49`. It is the principle the
codebase is proudest of and the one it breaks most.

| violation | |
|---|---|
| **F-204** | One raising subscriber kills the live-state bus permanently. `get_value()` then serves a stale cache, so **every surface renders plausible frozen values and none shows an error** |
| F-130 | 15 exception handlers swallow with a bare `pass`/`continue`; 337 handlers total |
| F-118 | A settings-editor button that silently does nothing |
| F-193 | The libcamera overclock patch has no `else` — an upstream change makes it a silent no-op |
| F-271 | Saving settings destroys 74 comment lines with no warning |
| F-171 | `configure_logging` ignores its first argument, so `MODULES_OUTPUT_TO_SERIAL` configures nothing while reading as live |

**F-204 is the one that matters most**, because it is the exact failure the principle names:
a failure the operator cannot see during a take. The camera keeps showing numbers. They are
just no longer true.

**Sharpened form, worth adopting verbatim:** *the operator must never be shown a plausible
wrong number.* That is stronger than "fail visible" and it is what P3 is reaching for.

---

## P4 — "Hardware facts live in data, not code" · **REFINE — single source, single consumer**

Confirmed: `resources/sensors.json` is a genuine single source. S04 tested the hypothesis
that a sensor table was duplicated and **disproved it** — cinepi-raw holds no sensor data.

Refuted in its second clause. The principle says *"data files that **both repos** read."*
cinepi-raw does not read `sensors.json` — zero references in its C++ sources. Hardware facts
reach cinepi-raw as **Redis keys and command-line arguments**, translated by cinemate.

**Restated:** *Hardware facts live in one data file, which one repo reads and translates for
the other.* That is a defensible design — cinepi-raw stays a capture engine — but it means
`sensors.json` is not a shared contract, and the actual shared contract is the 23 keys of
`cp_controls`.

---

## P5 — "One process owns the display" · **CONFIRMED, and enforced by the hardware**

The strongest-evidenced principle. cinepi-raw states the mechanism itself:
*"DRM master is exclusive per GPU"* (`dualHdmiPreviewStage.cpp:1-22`, byte-identical on
`dev`). The project paid for this once already — the dual-sensor workaround routes the
secondary sensor's frames through SysV shared memory rather than contending for the display.

Two refinements from S07/S08:

- **Ownership is bound at process start and cannot be rebound.** Hot-plugging HDMI makes the
  GUI thread restart `cinepi-raw` outright, *"so preview binds to the active display"*
  (F-223).
- **"One process" is not "one plane."** `dev`'s `drm_preview.cpp` enumerates DRM planes and
  programs a spare overlay plane for `--same-hdmi`, degrading with a log when none is free
  (F-227). The exclusivity is over DRM *master*, not over compositing.

This principle is why ADR-001 rejects option D.

---

## P6 — "Comments record the *why*, including dead ends" · **CONFIRMED — the best thing about this codebase**

F-133 catalogued **47 load-bearing why-comments**, including two falsified experiments and a
cross-repo invariant. F-134: **zero** TODO/FIXME/XXX/HACK markers in ~19,800 lines. The
comments that exist are load-bearing prose, not decoration.

The best of them names its own guarding test — `storage_profiles.py:41-49`, the AUDIO-CORE
INVARIANT — and that test is one of the 381 that never run (F-222).

**But S09 found the boundary of this principle, and it is uncomfortable:** *prose inside the
code rots where `docs/` does not.* Three hand-sync comments have drifted (F-260, F-183,
F-220), a fourth lives in CSS (F-217), and `lock_dual_recording` survives in a **docstring**
and a **comment** while existing nowhere in the system (F-246). Meanwhile `docs/` scored
zero broken links, zero bad citations and zero orphan entries (F-240).

**Restated:** *Comments record the why — and comments that record a **fact about other code**
are a different thing, and they rot.* S06's rule follows directly: **a comment is not a
check.** Preserve the why-comments (P6 holds); stop using comments as a sync mechanism.

---

## P7 — "The camera must survive its own software" · **CONFIRMED, and it is the design's best work**

Three independent mechanisms, all real:

- **The recovery console** (F-221) — stdlib-only by a stated rule with the reason given
  (*"every import it makes is another way for it to die exactly when it is needed"*),
  honoured via a subprocess rather than an import, numbered degradation ladders, 86 tests,
  and a deliberately absent systemd dependency explained in place.
- **Standby-storage promotion** — `/media/RAW` active with `/media/RAW1..N` standby,
  promoted with `mount --move` (`ssd_monitor.py:312`, `app/raw_files.py:8`).
- **The wifi-hotspot credential ladder** — 53 tests, a service that reconciles every 60 s
  and survives a CineMate crash, with in-app creation as the fallback (`main.py:584-600`).

**Generalise the mechanism, because it is the project's signature move:** *degrade in
ladders whose last rung still produces a usable answer.* The recovery console's
`load_config()` and `validate_settings_text()` are numbered rungs; the hotspot has a
credential ladder; storage has standby promotion.

**The violation is F-266:** the recovery console appears **zero times** in the 1061-line
install document. A survival mechanism the operator never learns about does not survive
anything.

---

## P8 — "Config is declarative and user-editable, and comments in it are part of the product" · **STATED, AND DIRECTLY VIOLATED BY THE PRODUCT**

Confirmed as intent and as design. `settings.jsonc` is 386 lines of which **74 are
comments** — section banners and inline explanations of what each key does. The codebase
carries its own `strip_jsonc()` tolerant parser to support them (`config_loader.py:518-525`),
and reimplements it in the installer with the reason named (F-191). `config.txt` gets the
same treatment.

**And then the web settings editor deletes all 74 of them.** `put_settings` writes
`json.dumps(settings, indent=2)` over the file — plain JSON. No warning. No backup: the word
does not appear in `settings_editor.py`. **One save from the GUI and 19% of the operator's
configuration file is gone** (F-271).

The contrast is the whole review in one pair of functions. Two surfaces write this file:

| | recovery console | settings editor |
|---|---|---|
| writes | the user's raw text | `json.dumps(parsed)` |
| comments | preserved | **all 74 destroyed** |
| backup | `backup_file()` with rotation | **none** |
| the code says | *"Back up, then atomically replace. The order is not negotiable."* | — |

**The correct implementation is in the same repository, ~1000 lines away, with a docstring
explaining why the order matters.** Same shape as F-208. This is not a knowledge problem.

---

## Principles the review found that KICKOFF did not list

Each is evidenced by code the project already wrote.

**P9 — Degrade in ladders whose last rung still answers.** Generalised from P7 (§above).
Rungs are numbered and each is tested; the last one always produces something usable rather
than an error. `cinemate-recovery.py`'s `load_config()` is the reference implementation.

**P10 — State the reason in place, especially for a compromise.** The codebase's best
comments do not describe *what*; they justify a decision that would otherwise look wrong.
`cinemate-install.sh:1633-1636` duplicates `strip_jsonc` and says why (*"this heredoc runs
under the system python3, outside the venv"*). `app/main/events.py:6-12` explains why control
moved to `/api/v1/cmd` (*"behaviour cannot drift between them"*). `simple_gui.py:750-757`
explains why the overclock patch is grep-guarded. **Where this is done, the code is
trustworthy; where it is skipped, the same construct is a defect.**

**P11 — Duplicated truth must be deleted, or carry a named reason *and* a check. A comment is
not a check.** S06's rule, and the review's central finding. 16 instances, 10 drifted. Three
of the duplicates are hand-maintained comments indexing the duplication, and two of those
comments are themselves wrong. **This is the principle the project most needs and does not
have.**

**P12 — Route, don't replicate.** The project's one successful de-duplication: control flow
moved to `POST /api/v1/cmd` so web, CLI and serial share a path (F-206). It held. Compare
the settings-editor catalogue, which was corrected by hand and drifted again (F-220). **When
this project routes, it wins; when it copies and comments, it loses.**

Note P12 has a boundary — F-268: six input surfaces still bypass the routed path and call
the controller directly through `getattr`.

---

## Summary

| # | principle | verdict |
|---|---|---|
| 1 | Redis is the single source of live state | **refine** — true between processes, cached within one |
| 2 | The Pi is the runtime truth | **confirmed** — and practised, including recorded dead ends |
| 3 | Fail visible, never silent | **stated; most-violated** — F-204 is the exact named failure |
| 4 | Hardware facts live in data | **refine** — single source, single consumer |
| 5 | One process owns the display | **confirmed** — enforced by DRM master; ownership binds at process start |
| 6 | Comments record the why, including dead ends | **confirmed** — and bounded: comments about *other code* rot |
| 7 | The camera must survive its own software | **confirmed** — the design's best work; undocumented in the installer |
| 8 | Config comments are part of the product | **stated; violated by the product's own editor** |
| 9 | Degrade in ladders whose last rung still answers | **new** |
| 10 | State the reason in place, especially for a compromise | **new** |
| 11 | Duplicated truth: delete it, or name a reason *and* add a check | **new — the one the project lacks** |
| 12 | Route, don't replicate | **new** — proven once, not generalised |

---

## Confidence

Every verdict cites a line read in this repository on the `dev` branch of both repos. This
document itself predates the 2026-08-24 Pi session; the two open dependencies below are
now settled — see `PI-RESULTS-2026-08-24.md`.

~~Two verdicts rest on `probable` consequences rather than confirmed ones: **P3**'s severity
depends on F-204's observed behaviour (PI-014), and **P5**'s bearing on ADR-001 options D
and E rests on resource arguments that were not measured (PI-016).~~ **Both are now
confirmed on hardware, and neither changes the verdict — but P5's specifically changes the
argument it feeds.** PI-014 confirmed F-204's worst-case failure mode decisively (both the
HTTP API and SSE stream froze permanently and silently). PI-016 measured the RAM headroom
this ADR-001 rejects options D/E on: at the sensor's true peak mode, available memory never
dropped below ~2970MB of 4048MB — **CONTRADICTING** the ~300MB-free-at-peak argument on this
board. See `decisions/ADR-001-gui-harmonization.md`'s own correction for what that changes.
