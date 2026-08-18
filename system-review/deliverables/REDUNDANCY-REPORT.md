# REDUNDANCY REPORT — S04

**Session:** S04 (attempt 2) · **Snapshots:** cinemate `origin/dev` @ `02b5a39`,
cinepi-raw `main` @ `774402c` (shallow, read-only)

**Method:** two subagents (cinemate `src/`, cross-boundary duplication) plus one scope run
inline by the coordinator (cinepi-raw). A third scope — services/tests/installer — was not
run; see §7. Every finding carries `path:line`. Coordinator corrections to agent output are
marked and explained.

**Yield:** 41 net new findings (43 raised, 2 merged as duplicates). Ledger total: 76.

---

## 1. The headline: duplicated truth is systemic, and it has already broken things

Going into S04 the review had three instances of "the same fact stated twice, in two
languages, with no shared source" — F-007 (colours), F-016 (`audio_vu`), F-027/F-028 (the
Redis key registries). The open question was whether that was a pattern or a coincidence.

**It is a pattern.** S04 raised the count to 16 instances spanning every boundary in the
system, and — the part that matters — **nine of them have already drifted.** These are not
tidiness observations; they are latent or shipped defects:

| Finding | What disagrees | Consequence |
|---|---|---|
| **F-251** | Config defaults in 4 registries; **11 keys disagree** | Which default applies depends on load order |
| **F-253** | "SMPTE base = round(fps)" derived 4× under **3 rounding rules** | Python and C++ disagree at half-integer fps |
| **F-256** | ISO/shutter step tables stated 7× in 4 languages | Shutter table **missing `346.6`** in exactly one |
| **F-259** | "ISO ÷ 100 = AnalogueGain" stated 2× in C++ | Its own cold-start fallback skips the division |
| **F-261** | Packing fallback restates `sensors.json` | Silently un-packs imx477/imx296 on Pi 4 |
| **F-118** | 46-entry action catalogue duplicated Python↔JS | Offers `set_log`; real method is `set_log_encode` — **button silently no-ops** |
| **F-126** | Four `_as_bool` implementations | `_as_bool(2)` is `True` in one, `False` in three |
| **F-116** | Sensor accessor wrappers | `get_packing` silently wrong on Pi 4 |
| **F-202** | `tc_cam0`/`tc_cam1` written by **both repos** | Two algorithms, one key, last write wins |

F-118 is the clearest single argument in the whole review: a duplication that **already
shipped a user-visible dead button**, in the settings editor, where the only thing that
could have validated it (`GET /api/actions`) has no consumer.

### The self-referential detail

Three of the duplicated copies are **hand-maintained comments indexing the duplication**
— and two of those comments are themselves already wrong (F-260's path inventory lists 4
of 7 copies, one with a wrong line number). The codebase has tried manual synchronisation
and the manual synchronisation has itself drifted. That is about as direct a verdict as
evidence gets.

### Cross-repo instances specifically (feeds ADR-001)

| # | Finding | Fact duplicated across the C++/Python boundary |
|---|---|---|
| 1 | F-016 | `audio_vu` key name — same constant name both sides |
| 2 | F-027/F-028 | The whole key registry: 84-member enum vs 24 macros |
| 3 | F-202 | `tc_cam0`/`tc_cam1` — two independent writers |
| 4 | F-107 | Five `MIC_*` keys published by both, **read by neither**, debug string copied verbatim |
| 5 | F-253 | Timecode frame-base rounding rule |
| 6 | F-250 | The `--mode W:H:B:{P\|U}` string grammar — built 3× in Python, parsed by `sscanf` |
| 7 | F-259 | The ISO→gain convention |

---

## 2. Dead code — what can actually be deleted

**Confirmed dead, no hardware needed to remove:**

| Item | LOC | Finding |
|---|---|---|
| `cinepi/lj92.c` + `lj92.h` | 1218 | F-029 |
| `src/module/templates/` + `app/template.html` (4 files) | 928 | F-001 |
| `src/module/timekeeper.py` | 243 | F-017 |
| `cinepi/_mjpegPreviewStage.cpp` | 240 | F-012 |
| `src/module/keyboard.py` | ~90 | F-031 |
| `ssd_monitor._journal_loop` | 70 | F-109 |
| `src/module/rotary_encoder.py` | ~43 | F-100 |
| `src/stream.py` | 21 | F-013 |
| `handle_vu_output()` | 12 | F-018 |
| `cinepi_manager.cpp` (0 bytes) + `.hpp` | 37 | F-200 |
| 5 committed `.pyc` files | — | F-101 |
| One of the two identical patch files | 354 | F-201 |

**≈3,250 LOC of confirmed-dead source**, plus scattered unreferenced methods (F-102,
F-119, F-120, F-121, F-125, F-115) and at least 8 multi-line commented-out blocks (F-111).

**Module reachability is now exhausted.** F-122 gives the corrected result: exactly **4 of
48** modules in `src/` are unreachable from `main.py`, totalling 376 LOC of which 352 was
already known. Do not re-run that analysis.

---

## 3. Two corrections the coordinator made to agent output

Recorded because the ledger's value depends on findings being right, not merely numerous.

**F-112 downgraded high → medium.** The real defect is confirmed: the
`if self.ssd_monitor.is_mounted:` guard at `cinepi_controller.py:2033` is commented out, so
`unmount_drive()` now runs unconditionally. But the agent's added claim — that the CFE-HAT
branch calls a non-existent `mount_cfe` — is **wrong**: that entire `else` branch, including
the `mount_cfe()` call, is commented out too. It calls nothing.

**F-107 upgraded low/probable → medium/confirmed, and re-scoped to both repos.** The agent
reported "five `MIC_*` keys with no in-repo reader". Checking the other side showed
cinepi-raw publishes *the same five keys* at `cinepi_sound.cpp:1783-1789` — duplicating even
the debug string `"Published MIC_* to Redis"`. It is not a dead-key finding; it is a
**two-writer, zero-reader cross-repo duplication**, the fifth of its kind.

Also merged as duplicates: **F-110 → F-017**, **F-113 → F-019** (keeping the agent's
preferred remediation for the latter: *add* `FSCK_STATUS` to `ParameterKey` and wire a
reader, rather than delete it).

---

## 4. A correction to the review's own earlier work

Agent 1 cleared four of the targets S01 handed it. **`parameters.py`, `app/raw_files.py`,
`app/boot_config.py`, `mediator.py` and `utils.py` are all LIVE.**

The cause was a genuine bug in the S01 import graph, not merely its stated caveat: the
regex read `from module import parameters` as an edge to **`module`**, missing three live
importers (`cinepi_controller.py:25`, `quad_rotary_controller.py:14`,
`analog_controls.py:10`). The `app/*` files are reached by *relative* imports inside
`create_app`.

`CENSUS.md` §4 now carries this correction at the top and defers to F-122.

**The lesson generalises:** every "no inbound reference" claim in this review rests on
pattern matching. S03 found the same class of error twice with dynamically-built Redis keys
(`cinepi_ready_<port>`, then `tc_key`). Treat absence of a grep hit as a hypothesis.

---

## 5. Useful negative results

Worth as much as the findings, because they close avenues:

- **There is no triple sensor table.** `resources/sensors.json` is a genuine single source;
  `settings.jsonc:113` only points at it; cinepi-raw encodes no sensor data at all (one
  grep hit repo-wide, a comment). This was the review's biggest duplication hypothesis and
  it is **disproved**. The only residue is F-261's lossy `FALLBACK_PACKING_INFO`.
- **`settings.schema.json` agrees with `config_loader.py` on all 41 comparable default
  paths.** It is therefore the viable origin for any defaults-unification work (F-251).
- **Module reachability in `src/` is exhausted** (F-122).

---

## 6. What this means for ADR-001

S04 was not supposed to decide the GUI question, but it has materially constrained it.

1. **"One source of truth, N renderers" is viable for cinemate-internal data** — 9 of
   agent 4's 12 findings, including all three highs, are Python/JSON/HTML only. Those can
   share a source without crossing a repo boundary.
2. **It should be scoped explicitly OUT for the cinepi-raw boundary.** Seven duplications
   cross it, the repos version independently, and they share no build. The realistic form
   there is *"one specification, N implementations, conformance-tested per language"*.
3. **The binding constraint is not language count — it is that nothing verifies anything.**
   A test runner plus roughly five cross-registry assertions would catch five of the six
   drifts **with no architectural change at all**. `harness/redis_key_diff.py` is the first
   such assertion and it already caught an error in F-027.
4. **Therefore: a GUI unification shipped without a verification layer will re-grow these
   duplicates within a release.** The codebase has already demonstrated this — it tried
   comments as the synchronisation mechanism, and the comments drifted.

That is the strongest input ADR-001 could have, and it points at sequencing: **verification
before unification**, not after.

---

## 7. Agent 2's scope — PARTIALLY covered (added after the S05 session)

Agent 2 was re-run and died on a usage limit again, but its incremental-write
discipline preserved **16 findings, F-150..F-165**, before it stopped. They are merged.

**What it found is significant — a whole second duplication cluster around storage:**

| Finding | What |
|---|---|
| **F-160** (high) | **Two processes independently mount, fsck and unmount `/media/RAW`** — the recording target — with no lock or ownership protocol |
| **F-156** (high) | The filesystem→mount-options table is duplicated across those two processes and **the copies disagree** |
| **F-155** (high) | `YANK_ERRNOS` defined byte-identically in both, no shared module |
| **F-161** (high) | `services/cinemate-services.Makefile` recurses into three **deleted** directories |
| **F-164** | **The root cause:** the intended service↔app coupling is a dead `journalctl` tail, so the app re-implements mount detection by polling |
| **F-165** | Root `CMakeLists.txt` references a non-existent directory — `cmake .` fails immediately |

F-164 is the insight that ties the cluster together: F-155..F-160 are not six independent
copy-pastes, they are the **symptom of one severed link**. Fixing the coupling collapses
five findings at once. That reframes the remediation for this cluster entirely.

This also raises the duplicated-truth count and adds F-156 to the already-drifted list
(now **10 drifted**, not 9).

### Still not covered by agent 2 before it stopped

- Settings keys defined but never read; keys read but absent from the schema
- Installer idempotency by reading; `shellcheck` warning classes
- Three-way `wifi_hotspot` duplication — only the `_test/` copy was reached (F-150)
- IDs F-166..F-199 remain free for the remainder

### Originally unscoped (unchanged) `services/`, `_test/`, `cinemate-install.sh` (1916 LOC),
`cinemate-update.sh`, `settings.jsonc`/`settings.schema.json` as config-key sources,
`Makefile`, `scripts/`, `resources/`. Its prompt is ready in
`agent-reports/S04-AGENT-PROMPTS.md`. Specifically still open:

- Three-way `wifi_hotspot` duplication (`src/module/` 753 LOC, `services/` 52 LOC, `_test/`)
- Whether `services/storage-automount/storage-automount.py` (~1123 LOC) duplicates
  `usb_monitor.py` / `ssd_monitor.py`
- Settings keys defined but never read, and keys read but absent from the schema
- The 4 underscore `_test/` files and 3 non-test utilities
- Installer idempotency (by reading) and `shellcheck` warning classes
- **New from agent 1:** `python3-systemd` (`cinemate-install.sh:523`) becomes an unused
  install dependency once F-109 lands — add to the F-032 list

**Also uncovered in cinepi-raw** (from the inline scope): commented-out blocks beyond the
known one, the six inherited `rpicam-*` binaries, `cinepi_state.cpp`, and the liveness of
`utils.cpp` / `yuv2rgb.hpp` / `ifd_builder.hpp` / `raw_options.hpp` /
`cinepi_frameinfo.hpp` / `cinepi_recorder.hpp`.

**New Pi queue entries:** PI-010 (F-253 timecode rounding, with a concrete prediction),
PI-011 (F-259 ISO cold-start gain).
