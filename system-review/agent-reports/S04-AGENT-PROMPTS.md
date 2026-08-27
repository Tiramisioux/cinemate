# S04 agent prompts — ready to re-run

**Why this file exists:** the S04 fan-out was launched and all four agents died on an
account session limit before producing any output. The prompts were the session's real
planning work; storing them means the retry is copy-paste rather than re-derivation.

**Status:** all four UNRUN. No agent report files exist.

## Shared preamble — put in every prompt verbatim (CONVENTIONS.md §5.2)

1. Your assigned finding-ID block is **F-xxx..F-yyy**. Use only IDs in that range.
2. Write your full report to exactly: `system-review/agent-reports/<slug>.md`
3. Cite `path:line` for every claim. No claim without evidence.
4. You have no Raspberry Pi. Anything needing hardware is `unverified` — say what test
   would settle it.
5. Do not modify any file outside `system-review/`.
6. Return at most 20 lines: counts by severity, your finding IDs, and anything that blocks
   other agents. Your full report goes in your file, not your reply.

## Shared method warnings — also verbatim in every prompt

- **"Unreferenced" is NOT "dead."** Things may be reachable dynamically (importlib,
  `getattr`, Flask decorators, systemd, C++ self-registering factories) or driven by hand
  with `redis-cli`. Classify as *unreferenced* and state what would settle it.
- **This codebase resolves methods reflectively** — `getattr(cinepi_controller, name)`
  where `name` is a string in `settings.jsonc`. A controller method with no static caller
  may still be live. Check `settings.jsonc` before calling one dead.
- **Citation discipline.** Line numbers from `grep -n` ONLY. Never derive them by
  arithmetic on a `sed -n 'A,Bp'` window — S02 and S03 both shipped off-by-one citations
  that way and had to correct them. Re-grep every citation before writing it.
- Counts involving keys or symbols are **lower bounds** — pattern matching cannot see
  dynamically constructed names. Say "at least N".

## Shared "already confirmed — do not re-investigate, just cite"

`timekeeper.py` 243 LOC (F-017) · `keyboard.py` (F-031) · `src/stream.py` (F-013) ·
`handle_vu_output()` main.py:633-644 (F-018) · `lj92.c`+`lj92.h` 1218 LOC (F-029) ·
`_mjpegPreviewStage.cpp` (F-012) · 4 unreferenced HTML templates (F-001) ·
requirements/installer divergence (F-003) · 7 unused installer packages (F-032) ·
no CI on PRs or `dev` (F-006) · the cross-repo key diff (F-027, `findings/F-027.md`)

---

## Agent 1 — cinemate `src/` · IDs F-100..F-149
**Output:** `system-review/agent-reports/s04-agent1-cinemate-src.md`

Scope: dead/redundant code in `src/` (47 Python files, ~19,794 LOC). Unreferenced modules,
unreachable code, dead branches, large commented-out blocks, never-called functions,
duplicated logic, drifted parallel implementations.

Priority targets: `parameters.py` · `rotary_encoder.py` · `app/raw_files.py` ·
`app/boot_config.py` (all have no inbound import edge; check Flask route registration for
the last two) · `__pycache__/adc.cpython-39.pyc` and other orphan bytecode ·
`usb_monitor.py` opening its own `StrictRedis` at lines 141, 439, 458, 581.

## Agent 2 — services, tests, installer, config · IDs F-150..F-199
**Output:** `system-review/agent-reports/s04-agent2-services-tests-install.md`

Scope: `services/`, `_test/`, `cinemate-install.sh` (1916 LOC), `cinemate-update.sh`,
`settings.jsonc`, `settings.schema.json`, `Makefile`, `CMakeLists.txt`, `scripts/`,
`resources/`. Dead config keys, dead CLI commands, unused units, duplicated logic between
services and `src/`, unreachable installer branches.

Priority targets: three-way `wifi_hotspot` duplication (`src/module/` 753 LOC,
`services/wifi-hotspot/` 52 LOC, `_test/_wifi_hotspot_service.py`) · whether
`services/storage-automount/storage-automount.py` (~1123 LOC) duplicates `usb_monitor.py`
or `ssd_monitor.py` · settings keys defined but never read, and keys read but absent from
the schema · the 4 underscore `_test/` files and 3 non-test utilities · installer
idempotency **by reading, not running** · `shellcheck cinemate-install.sh` warning classes.

## Agent 3 — cinepi-raw · IDs F-200..F-249
**Output:** `system-review/agent-reports/s04-agent3-cinepi-raw.md`
**Subject repo:** `/workspace/tiramisioux/cinepi-raw` (read-only, shallow, `main`, no
history — no `git log`/blame/`-S`). Re-clone if absent:
`GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/Tiramisioux/cinepi-raw /workspace/tiramisioux/cinepi-raw`
Writes go only to `/home/user/cinemate/system-review/`.

Weight effort toward `cinepi/` — `core/`, `preview/`, `encoder/`, `apps/` are upstream
rpicam-apps and far less interesting.

Priority targets: the two root patch files (`add-redis-timecode.patch`, `add-tc.patch`) —
check whether their added lines already exist in the tree, since `git apply --check` is
meaningless on a shallow clone · `cinepi_state.cpp` and `cinepi_manager.{cpp,hpp}`, never
read by any session · every `cinepi/` source NOT in the meson list, classified · large
commented-out blocks (a known one at `cinepi_controller.cpp:~380-405`, a superseded
`CONTROL_KEY_RECORD` handler beside the live one) · the six inherited `rpicam-*` apps ·
`utils.cpp`, `yuv2rgb.hpp`, `ifd_builder.hpp`, `raw_options.hpp`, `cinepi_frameinfo.hpp`,
`cinepi_recorder.hpp`.

**C++-specific warning:** `RegisterStage(NAME, &Create)` at file scope means a stage with
no static caller IS live (`mjpegPreviewStage.cpp:245`). Check before calling anything dead.

## Agent 4 — cross-boundary duplicated truth · IDs F-250..F-299
**Output:** `system-review/agent-reports/s04-agent4-cross-boundary-duplication.md`
**The most valuable brief.** Not dead code — *the same fact stated twice, in two languages,
with no shared source.* Feeds ADR-001 directly.

Three instances already confirmed; find the rest and decide whether they form a pattern:
F-007 (colours, `simple_gui.py:21-45` ↔ `template.html:23-40`) · F-016 (`audio_vu`,
`cinepi_sound.cpp:22` ↔ `simple_gui.py:21`) · F-027/F-028 (the two key registries).

Hunt: sensor specs (`sensor_detect.py` 853 LOC vs `settings.jsonc` `sensors` §line 62 vs
anything in cinepi-raw — three copies of a sensor table would be major) · resolution/mode
tables, frame-rate limits, bit-depth and packing rules · defaults stated in
`settings.jsonc` AND hardcoded as `setdefault` fallbacks in `config_loader.py` (~340-345),
especially where they **disagree** · timecode maths (`redis_controller.py:303-346` vs
cinepi-raw's `phase_lock_core.hpp` and the two tc patches) · the 3+ GUI surfaces restating
labels/thresholds/units/state-derivation · "is writing / buffering / dropping" computed in
more than one place.

For each: (a) locations with `path:line`; (b) **do the copies AGREE or have they already
DRIFTED** — drift is much more severe, rate it `high` at minimum; (c) what breaks if one
side changes and whether anything would catch it (nothing would: no CI, no test runner);
(d) is a single source of truth feasible given the repos version independently with no
shared build.

**End with a verdict section:** is this a systemic pattern or three coincidences? Count the
instances and say plainly what it implies for ADR-001 — specifically whether "one source of
truth, N renderers" is viable when the truth spans Python, C++, HTML/CSS and JSON.

Be strict: duplicated *truth* (must stay in sync) is a finding; coincidental similarity
(two unrelated uses of 1920) is not. A padded report is worse than a short one.
