# READABILITY REPORT — S05

**Target reader (KICKOFF §8 S05):** a competent but *intermediate* Python/C developer, new
to this code. Everything below is judged against that reader, not against an expert who
already knows the system.

**Method:** AST analysis over `src/` (43 Python files, ~19,800 LOC) for function length,
nesting depth, exception handling and docstring coverage; targeted greps for comment
quality. Figures are counted, not estimated.

**Findings:** F-128..F-134.

---

## 1. Function length — 43 over 60 lines, 8 over 250

| LOC | Location | Function |
|---|---|---|
| 405 | `src/main.py:646` | `run_application` |
| 401 | `redis_listener.py:1634` | `analyze_frames` |
| 369 | `simple_gui.py:705` | `populate_values` |
| 337 | `cinepi_multi.py:351` | `_build_args` |
| 280 | `redis_listener.py:846` | `listen_stats` |
| 266 | `config_loader.py:149` | `_apply_settings_defaults` |
| 259 | `simple_gui.py:1695` | `draw_gui` |
| 239 | `cinepi_controller.py:41` | `__init__` |
| 174 | `ssd_monitor.py:979` | `format_drive` |
| 162 | `simple_gui.py:436` | `setup_resources` |

**The two that matter most for a newcomer** are `run_application` and
`cinepi_controller.__init__`. They are the front door: the first thing anyone reads is a
405-line straight-line function, and the first object they meet has a 239-line
constructor. Neither is *complex* — both are mostly sequential wiring — but length alone
makes them hard to hold, and `run_application` is where S02 found the shutdown-symmetry
bug (F-023): `cleanup()` sits 300 lines below the constructions it must mirror, with no
structural link between them.

**A 239-line `__init__` is also the mechanism behind F-026.** `CinePiController` takes 11
constructor arguments and exposes 94 methods whose *names* are a user-facing API bound
from `settings.jsonc`. Its size is not incidental — it is a god object that the config
format has frozen in place.

`_build_args` (337) is the cinepi-raw command-line builder — the seam where every
cinemate decision becomes a C++ process argument. Worth splitting for comprehension alone.

## 2. Nesting — reaching depth 11

86 sites across 20 functions sit at nesting depth ≥5. The worst:

| Depth | Location | Function |
|---|---|---|
| **11** | `dmesg_monitor.py:101` | `_start_monitoring` |
| **10** | `redis_listener.py:1064` | `listen_stats` |
| 8 | `simple_gui.py:974` | `populate_values` |
| 7 | `ssd_monitor.py:1211` | `get_latest_recording_infos` |
| 7 | `redis_listener.py:1476` | `listen_controls` |

Depth 11 means eleven enclosing `if`/`for`/`while`/`try` blocks. At that point the reader
cannot hold the conditions that got them there, and neither can the author — this is where
guard clauses and early returns pay for themselves.

`listen_stats` at depth 10 **and** 280 lines is the single least approachable function in
the repo, and it sits on the hot path: it is the Redis read side that drives the GUI.

## 3. Error handling — 337 handlers, 15 of them silent

**337 `except` handlers in ~19,800 lines — one per 59 lines.** That density is itself the
finding: it suggests defensive catching as a default habit rather than a considered choice
per call site.

Two specific problems:

**15 handlers swallow silently** — the body is a bare `pass`, `continue` or `break`, so the
error leaves no trace at all:

```
cli_commands.py:332 · redis_listener.py:552,1184,1557 · serial_handler.py:66,117 · +9
```

This is a **direct violation of the project's own stated principle** (KICKOFF §9 №3, "fail
visible, never silent"), and it is not theoretical: F-016 showed the `audio_vu` read path
swallowing failure, which would remove the operator's audio meter mid-take with nothing
logged. F-130.

**Two bare `except:`** (`cli_commands.py:159,167`) also catch `KeyboardInterrupt` and
`SystemExit` — in the CLI dispatcher, the one place a user expects Ctrl-C to work. F-131.

## 4. Comments — the good news, and what must not be deleted

### Zero TODO/FIXME/XXX/HACK in the entire codebase (F-134)

At ~19,800 LOC this is genuinely unusual and worth stating as a positive. Whatever else is
true of this code, it does not carry a backlog of abandoned intentions in its comments.

### 47 comments encode *why* — and they are a deletion hazard (F-133)

KICKOFF §8 S05 asks for these specifically, and they are the most valuable prose in the
repo. **The single best comment in the codebase** is `storage_profiles.py:41-49`:

> **AUDIO-CORE INVARIANT:** cinepi-audio-capture pins itself to the last CPU core (N-1) at
> SCHED_FIFO priority 80 so USB-audio interrupts are serviced on an uncontested core (see
> `cinepi_audio_capture.cpp`). No profile's `encode_affinity` or `disk_affinity` may
> include that core, or audio capture stalls at launch and **the WAV loses sync** (wrong /
> garbage start timecode, or no WAV at all). […] cinepi-raw strips the audio core from any
> requested set as a backstop, but profiles must not rely on that.
> **`test_storage_profiles.py` locks this invariant.**

That one comment does four things at once: states a cross-repo constraint, names the
consequence of breaking it, names the backstop *and* warns against relying on it, and names
its own guarding test.

**And that test is one of the 27 that never run (F-006).** The invariant preventing lost
audio sync is guarded by a test nobody executes. That is the sharpest argument in the
review for fixing CI first.

Other comments that must survive any cleanup:

| Location | What it preserves |
|---|---|
| `ssd_monitor.py:1122-1125` | **A falsified experiment.** 1 MB exFAT clusters were tried for write latency and break the macOS driver. Deleting this invites re-doing it. |
| `sensor_detect.py:745-752` | **A superseded hypothesis, with its reasoning.** Why 12-bit ClearHDR *used* to be refused, and why cinepi-raw's decompand-then-log composition changed the answer. |
| `redis_listener.py:1342` | `(do NOT update self.last_framecount – keep the higher baseline)` — a one-line invariant on drop-frame detection. |
| `storage_profiles.py:32-39` | Why `buffer_count` is what it is: ~25 MB CMA per buffer at 4K, with the command to verify headroom. |
| `cinepi_raw.cpp:175-184` | The cross-repo record interlock (S03) — nothing else documents it. |
| `dualHdmiPreviewStage.cpp:5-20` | DRM master exclusivity and the SysV workaround, plus its own "hardware-untested" warning (S03). |

**Recommendation:** promote the AUDIO-CORE INVARIANT and the two falsified-experiment
comments into `docs/` before any refactor touches those files. They are currently one
careless edit from being lost, and three of the six are the *only* record of their fact.

### Docstrings — 27% on public seams (F-132)

152 of 543 public defs carry a docstring. **40 public classes have none**, including:

`CinePiController` · `CommandExecutor` · `DmesgMonitor` · `AnalogControls` ·
`CinePiProcess` · `BatteryMonitor` · `DynamicResolutionChoice` · …

`CinePiController` having no class docstring is the notable one: it is the object whose
method names are a user-facing contract (F-026), so it is simultaneously the most
externally-coupled and least self-describing class in the system.

The pattern is inverted from the norm — this codebase explains *decisions* well in inline
comments and *interfaces* poorly. For the intermediate reader that is the wrong way round:
they need the interface first.

---

## 5. What to do, in order

1. **Fix CI before any readability work** (F-006). The AUDIO-CORE INVARIANT is guarded by a
   test that never runs; so is everything else. Nothing else on this list is safe to change
   until something can tell you that you broke it.
2. **Make the 15 silent handlers loud** (F-130). Smallest diff with the largest alignment to
   the project's own principle. Each becomes at minimum a `logging.debug`.
3. **Promote the load-bearing comments into `docs/`** (F-133) — before, not after, any
   structural change to `storage_profiles.py`, `ssd_monitor.py` or `sensor_detect.py`.
4. **Add class docstrings to the 40 public classes** (F-132), starting with
   `CinePiController`. Pure addition, zero blast radius.
5. **Then** consider splitting `run_application` and `listen_stats` — the two that most
   obstruct a newcomer. Both are high blast radius and belong after CI exists, not before.

Note the ordering is deliberate: items 1–4 are additive or observational and cannot break a
take. Item 5 touches the boot path and the Redis read path.

---

## 6. Not covered

- **`cinepi_controller.py` internals** (2626 LOC) beyond structure metrics — still untraced
  since S02 deferred it. PI-007 step 1 also wants this read.
- **C++ readability** — only the load-bearing comments found in S03 are carried here. The
  1804-LOC `cinepi_sound.cpp` and 1521-LOC `dng_encoder.cpp` have had no readability pass.
- **HTML/JS** — `settings_editor.html` is 3706 lines and was assessed only for duplication
  (F-256, F-117), not readability.
