# S04 Agent 4 — Cross-Boundary Duplication (duplicated *truth*)

**Scope:** the same fact stated more than once, in more than one language/file, with no shared source of truth.
Not dead code. Not coincidental similarity. Duplicated *truth* that must stay in sync and has nothing enforcing it.

**Repos:** `cinemate` @ `/home/user/cinemate`; `cinepi-raw` @ `/workspace/tiramisioux/cinepi-raw` (read-only, shallow `main`).
**Finding-ID block:** F-250..F-299.
**Hardware:** none available. Anything requiring a Pi is marked `unverified` with the test that would settle it.

## Already-confirmed instances (cited, not re-derived)

- **F-007** — colour constants duplicated: `src/module/simple_gui.py:21-45` (Python tuples) vs `src/module/app/templates/template.html:23-40` (CSS custom properties); CSS comments name the Python constants they mirror.
- **F-016** — Redis key `audio_vu` declared as `RECORDER_VU_REDIS_KEY` in both `/workspace/tiramisioux/cinepi-raw/cinepi/cinepi_sound.cpp:22` and `/home/user/cinemate/src/module/simple_gui.py:21`.
- **F-027/F-028** — two independent Redis key registries: 84-member `ParameterKey` enum at `src/module/redis_controller.py:18` vs `#define CONTROL_KEY_*` at `cinepi-raw/cinepi/cinepi_state.hpp:23-52`. Tool: `system-review/harness/redis_key_diff.py`.

---

## Findings

<!-- appended incrementally -->
### F-250 — `--mode` wire format `W:H:B:{P|U}` built in 3 Python sites, parsed in C++

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-250 | medium | high | both | 4 sites (3 producers + 1 parser) | The cinepi-raw `--mode` string grammar is re-implemented independently at three Python call sites and parsed by `sscanf` in C++ | `src/module/cinepi_controller.py:1465`, `src/module/cinepi_multi.py:467`, `src/module/cinepi_multi.py:787`, `cinepi-raw/core/options.cpp:55` |

**(a) Locations**

Producers (Python, cinemate):
- `/home/user/cinemate/src/module/cinepi_controller.py:1465` — `return f"{width}:{height}:{bit_depth}:{packing}"` inside `_mode_string()` (declared `cinepi_controller.py:1458`), whose packing fallback is `str(packing or info.get("packing") or "U").upper()[0]` at `cinepi_controller.py:1464`.
- `/home/user/cinemate/src/module/cinepi_multi.py:467` — `"--mode", f"{width}:{height}:{bit_depth}:{packing}"` built inline in `_build_args`; does **not** call `_mode_string`.
- `/home/user/cinemate/src/module/cinepi_multi.py:787` — a third inline copy, `f"{res.get('width')}:{res.get('height')}:{res.get('bit_depth')}:{packing}"`, written to the `MODE` Redis key (`cinepi_multi.py:786`).

Parser (C++, cinepi-raw):
- `/workspace/tiramisioux/cinepi-raw/core/options.cpp:55` — `sscanf(mode_string.c_str(), "%u:%u:%u:%c", &width, &height, &bit_depth, &p)`; the packing char is validated at `core/options.cpp:62-67`, and anything that is not `P`/`U` raises `throw std::runtime_error("Packing indicator should be P or U")` (`core/options.cpp:66`).
- The inverse serialiser `Mode::ToString()` at `/workspace/tiramisioux/cinepi-raw/core/options.cpp:70-79` is a *fifth* statement of the same grammar (`ss << width << ":" << height << ":" << bit_depth << ":" << (packed ? "P" : "U")`, `core/options.cpp:76`).

**(b) Agree or drifted:** currently **AGREE**. All three producers emit the same four-field colon grammar with a `P`/`U` token, which the parser accepts. No drift found. But `cinepi_multi.py:787` writes the string to Redis for GUI/telemetry consumption while `cinepi_multi.py:467` writes it to the launch argv — two copies whose only guarantee of matching is that a human wrote them the same way. `cinepi_multi.py:774` carries a comment ("matches what `CinePiProcess._build_args` launches") that is itself an admission the sync is manual.

**(c) What breaks / what catches it:** if cinepi-raw ever adds a fifth field (e.g. a framerate suffix — `Mode::ToString` already emits `(framerate)` at `core/options.cpp:78`, which the `sscanf` parser cannot read back), all three Python producers must change together. Nothing catches a partial change: the failure mode on the argv path is a `std::runtime_error` thrown inside the C++ process at launch, surfacing to CineMate only as a dead child process; the failure on the Redis path (`cinepi_multi.py:787`) is silent — a wrong `mode` string reaches the GUI and no exception is raised anywhere. There is no CI and the 27 test files have no runner.

**(d) Single source of truth feasible?** Partially. Within cinemate, the three producers should all route through `cinepi_controller._mode_string()` (`cinepi_controller.py:1458`) — that is a pure refactor with no cross-repo coordination and should be done. Across the repo boundary the grammar remains a wire contract with no shared artefact; the realistic mitigation is a single Python emitter plus a round-trip assertion, not a shared schema.

**Verdict on this instance:** the *cross-language* half is an unavoidable wire protocol; the *intra-Python* half (three copies of one f-string) is gratuitous and fixable today.

