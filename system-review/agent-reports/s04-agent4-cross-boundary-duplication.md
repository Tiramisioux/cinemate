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

### F-251 — Configuration defaults stated FOUR times; already DRIFTED on at least 11 keys

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-251 | **high** | high | cinemate | 4 independent registries | The same default values are declared in Python `setdefault` calls, a JSON Schema `default` keyword, a shipped JSONC template, and the live JSONC config — and they already disagree | `src/module/config_loader.py:149-410`, `settings.schema.json` (59 `default` keys), `resources/settings/settings_default.jsonc`, `settings.jsonc` |

**(a) The four registries**

1. `/home/user/cinemate/src/module/config_loader.py:149` — `_apply_settings_defaults()`, ~90 `setdefault` calls (enumerated `config_loader.py:151-410`). This runs on **every launch** (`config_loader.py:588`) and fills any gap in the live file, so it is the *effective* default at runtime.
2. `/home/user/cinemate/settings.schema.json` — 59 `"default"` keywords (first at `settings.schema.json:13`). Consumed by the schema-driven web settings editor.
3. `/home/user/cinemate/resources/settings/settings_default.jsonc` — the shipped template. Its role is stated at `src/module/app/settings_editor.py:50-53`: it is "(a) the `GET /api/settings` fallback when the live file is missing, and (b) the source for the **'revert to defaults'** action", loaded at `settings_editor.py:145`.
4. `/home/user/cinemate/settings.jsonc` — the in-repo live config that ships to the device (`cinemate-install.sh:1618` treats `$CINEMATE_DIR/settings.jsonc` as the installed file and `cinemate-install.sh:1621` hard-fails if it is absent).

Registries 1–3 are all *statements of the default*. Registry 4 is nominally user config, but it ships in-repo and is what an installed camera actually runs, so a value there that contradicts 1–3 is still a fourth answer to "what is the default?".

**(b) Agree or drifted: DRIFTED.** Mechanically diffed (script kept at `/tmp/claude-0/-home-user-cinemate/e9147460-fa59-5689-ad3d-06b8d32b2fc0/scratchpad/diff_defaults.py` and `schema_defaults.py`). Schema vs code agree on all 41 comparable paths — but the JSONC template and the live file disagree with the code on the following. Every line number below is from `grep -n`:

| key | schema | `config_loader` | `settings_default.jsonc` | `settings.jsonc` | verdict |
|---|---|---|---|---|---|
| `settings.conform_frame_rate` | `24` (`settings.schema.json:132`) | `24` (`config_loader.py:218`) | `25` (`resources/settings/settings_default.jsonc:50`) | `25` (`settings.jsonc:118`) | **split 2–2, no arbiter** |
| `settings.sync_tolerances.live_sync_warning_frames` | `5` (`settings.schema.json:141`) | `5` (`config_loader.py:223`) | `2` (`settings_default.jsonc:53`) | `5` (`settings.jsonc:121`) | template is the outlier |
| `audio_capture.24bit.capture_gain_db` | `0.0` (`settings.schema.json:197`) | `0.0` (`config_loader.py:324`) | `6.0` (`settings_default.jsonc:111`) | `6.0` (`settings.jsonc:208`) | **split 2–2** |
| `audio_capture.16bit.capture_gain_db` | `0.0` (`settings.schema.json:205`) | `0.0` (`config_loader.py:327`) | `6.0` (`settings_default.jsonc:115`) | `6.0` (`settings.jsonc:213`) | **split 2–2** |
| `audio_capture.24bit.timecode_offset_frames` | `0` (`settings.schema.json:198`) | `0` (`config_loader.py:325`) | `-1` (`settings_default.jsonc:112`) | `2` (`settings.jsonc:209`) | **three different values** |
| `audio_capture.16bit.timecode_offset_frames` | `0` (`settings.schema.json:206`) | `0` (`config_loader.py:328`) | `0` (`settings_default.jsonc:116`) | `2` (`settings.jsonc:214`) | live file is the outlier |
| `hdmi_display.overlays.buffer_vu_meter` | `true` (`settings.schema.json:226`) | `True` (`config_loader.py:342`) | `false` (`settings_default.jsonc:124`) | `true` (`settings.jsonc:227`) | template is the outlier |
| `hdmi_display.preview.zoom_steps` | *(no default)* | `[1.0, 1.5, 2.0]` (`config_loader.py:348`) | `[1.0, 2.0]` (`settings_default.jsonc:129`) | `[1.0, 2.0]` (`settings.jsonc:232`) | code is the outlier |
| `hardware_outputs.rec_out_pin` | *(no default)* | `[6, 21]` (`config_loader.py:394`) | `[21]` (`settings_default.jsonc:236`) | `[21]` (`settings.jsonc:367`) | code is the outlier — **GPIO pin 6 is driven by the code default only** |
| `arrays.fps.steps` | *(no default)* | `[1,2,4,8,12,16,18,24,25,30]` (`config_loader.py:255`) | `[1,2,4,8,12,16,18,24,25,33,40,50]` (`settings_default.jsonc:70`) | `[25,33,50]` (`settings.jsonc:147`) | **three different tables** |
| `arrays.fps.free` | *(no default)* | `False` (`config_loader.py:256`) | `true` (`settings_default.jsonc:71`) | `false` (`settings.jsonc:148`) | template is the outlier |
| `arrays.shutter_a.steps` | *(no default)* | 10 entries, no `346.6` (`config_loader.py:254` block) | 11 entries incl. `346.6` | 11 entries incl. `346.6` | code is the outlier |

`timecode_offset_frames` is the sharpest case: **three different values for the same key** (`0` / `-1` / `2`), and it is an audio-to-video sync offset — a wrong value silently misaligns recorded audio against the DNG sequence. `rec_out_pin` is the most dangerous: the code default asserts GPIO **6** is a rec-out pin while both JSONC files say only 21. On a rig with something else wired to pin 6, a config file that merely omits `rec_out_pin` gets pin 6 driven.

**(c) What breaks / what catches it:** the user-visible break is the web editor's **"revert to defaults"** button (`settings_editor.py:145`, backed by `STOCK_SETTINGS_FILE` at `settings_editor.py:54`): it hands the operator `settings_default.jsonc`, which is *not* what the runtime would have produced from an empty config. An operator who reverts to defaults gets `conform_frame_rate` 25, `capture_gain_db` +6 dB and `buffer_vu_meter` off — none of which are the code's defaults. Nothing catches this. There is no CI. Two tests touch this area (`_test/test_camera_log_encode_defaults.py:35` reads the stock file, `_test/test_arrays_free_increment_defaults.py:32` reads the code defaults) but neither compares the two registries against each other, and the 27 test files have no runner.

**(d) Single source of truth feasible?** **Yes, and cheaply — this is entirely inside one repo, one language boundary at most.** `settings.schema.json` already carries `default` keywords that agree with the code 41/41, so the schema is the natural source: `_apply_settings_defaults` can be generated from (or asserted against) the schema, and `settings_default.jsonc` can be generated from it too. The minimum viable fix, needing no refactor, is a test that asserts `_apply_settings_defaults({}) == load(settings_default.jsonc)` for every scalar leaf — that single assertion would have caught all 11 drifts above. No hardware needed; `unverified` does not apply.

---

### F-252 — Schema declares 18 defaults `_apply_settings_defaults` never applies; two modules re-declare them a third time

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-252 | medium | high | cinemate | 3 registries per block | `system.web_api.*` and `system.recovery.*` defaults live in the schema, in a module-level dict, and in `settings.jsonc` — outside the central loader entirely | `settings.schema.json:38-56`, `src/module/web_api_settings.py:10-25`, `services/cinemate-recovery/cinemate-recovery.py:78-84`, `settings.jsonc:18-53` |

**(a) Locations.** The central loader `_apply_settings_defaults` (`config_loader.py:149`) sets **no** `system.web_api` or `system.recovery` key — confirmed by diffing its output against the schema's default paths (18 schema defaults have no corresponding leaf in `_apply_settings_defaults({})`). Instead:

- `web_api`: `settings.schema.json:38-56` (`enabled`, `token`, `allow_destructive`, `max_commands_per_sec`, `max_sse_clients`, `broadcast.{enabled,port,hz,keys}`) **and** `src/module/web_api_settings.py:10` `DEFAULT_WEB_API_SETTINGS = {...}` (values at `web_api_settings.py:11-24`) **and** `settings.jsonc:18-37`.
- `recovery`: `settings.schema.json:50-52` and around `settings.schema.json:84-93` **and** `services/cinemate-recovery/cinemate-recovery.py:78` `DEFAULTS = {...}` (values at `cinemate-recovery.py:79-84`) **and** `settings.jsonc:38-53`.
- `image_capture.hdr.{blend,gain_adder,threshold_high,threshold_low}` have schema defaults with no loader counterpart at all.

**(b) Agree or drifted:** currently **AGREE** on every key. `enabled/true`, `token/""`, `allow_destructive/false`, `max_commands_per_sec/20`, `max_sse_clients/4`, `broadcast.port/8888`, `broadcast.hz/5`, and the 8-key `broadcast.keys` list all match across schema, module dict and `settings.jsonc`; recovery's `port/8080`, `token/""`, `allow_config_txt/false`, `config_confirm_timeout_s/300` likewise. Note the `broadcast.keys` list is an 8-element string list written out **twice** verbatim (`web_api_settings.py:21-23` and `settings.jsonc:32-34`) plus a third time in the schema (`settings.schema.json:56`).

**(c) What breaks / what catches it:** these two blocks are the two that *must* work when everything else is broken — the recovery console exists precisely for when CineMate will not start (`cinemate-recovery.py:4`). Its own comment at `cinemate-recovery.py:76-77` justifies the duplication ("requiring an edit to settings.jsonc to get a working recovery console would be circular"), which is a legitimate reason for the *module* copy to exist standalone. It is not a reason for the schema to state the values a third time. If someone changes the recovery port in the schema and `settings.jsonc` but not in `cinemate-recovery.py:80`, the console silently binds the old port and the operator's documented URL (`cinemate-recovery.py:6`, `http://10.42.0.1:8080`) stops working — with no error, because the service starts fine. Nothing catches this.

**(d) Single source of truth feasible?** Partially. The recovery service's standalone dict is a deliberate, defensible bootstrap copy — keep it, but make the schema generate it or assert against it. The `web_api` copy in `web_api_settings.py:10` has no such justification and should be folded into `_apply_settings_defaults` like every other block, which would also bring it under whatever assertion F-251's fix introduces.

### F-253 — "Nominal integer timecode fps" derived FOUR times with THREE different rounding rules — already numerically divergent

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-253 | **high** | high (code) / `unverified` (field impact) | both | 4 derivations, 3 rounding modes | The same rule "SMPTE base = round(fps)" is implemented in two Python and two C++ sites; Python uses banker's rounding, C++ uses half-away-from-zero and half-up, so they disagree at half-integer fps | `src/module/redis_controller.py:334`, `src/module/simple_gui.py:794`, `cinepi-raw/cinepi/cinepi_sound.cpp:154`, `cinepi-raw/cinepi/dng_encoder.cpp:1178` |

**(a) The four derivations of the same fact**

| # | site | expression | rounding mode | clamp / fallback |
|---|---|---|---|---|
| 1 | `/home/user/cinemate/src/module/redis_controller.py:334` | `rate = int(round(rate))` | Python `round` = **half-to-even** | none — `frames = total_frames % rate` at `redis_controller.py:337` raises `ZeroDivisionError` if `rate` rounds to 0 |
| 2 | `/home/user/cinemate/src/module/simple_gui.py:794` | `round(float(...FPS_USER...))` | **half-to-even** | none |
| 3 | `/workspace/tiramisioux/cinepi-raw/cinepi/cinepi_sound.cpp:154` | `std::max(1.0, std::round(framerate))` (fn declared `cinepi_sound.cpp:149`) | C++ `std::round` = **half-away-from-zero** | clamped `>= 1`; returns `0.0` for non-finite/≤0 at `cinepi_sound.cpp:151-152` |
| 4 | `/workspace/tiramisioux/cinepi-raw/cinepi/dng_encoder.cpp:1178` | `static_cast<int>(1'000'000.0 / frame_duration + 0.5)` | **half-up** (add-0.5-then-truncate) | falls back to `24` at `dng_encoder.cpp:1171` and again at `dng_encoder.cpp:1179` |

Site 1 formats the time-of-day timecode CineMate publishes and the GUI shows (`redis_controller.py:303` `nanoseconds_to_timecode` → `redis_controller.py:323` → `_format_timecode` at `redis_controller.py:325`, output string built at `redis_controller.py:345`). Site 4 seeds the timecode actually **written into the DNG** (`dng_encoder.cpp:1205-1208`: `tc_start_hh_/mm_/ss_`, `tc_fps_`). Site 3 computes the BWF `timeReference` sample offset written into the **WAV** (`cinepi_sound.cpp:192`, used at `cinepi_sound.cpp:202-205`). These are three renderings of one fact — "which frame of which second is this" — for the same take.

**(b) Agree or drifted: DRIFTED — numerically, today.** Verified by executing both languages (Python 3 `int(round(x))` vs a compiled `std::max(1.0, std::round(x))`):

| fps | Python (sites 1, 2) | C++ `cinepi_sound` (site 3) | C++ `dng_encoder` (site 4) |
|---|---|---|---|
| 23.5 | 24 | 24 | 24 |
| **24.5** | **24** | **25** | **25** |
| 29.5 | 30 | 30 | 30 |
| 23.976 | 24 | 24 | 24 |
| 0.4 | **0 → `ZeroDivisionError`** | 1 | 24 (fallback) |

At **24.5 fps the DNG and WAV are stamped on a 25-frame base while CineMate's on-screen and Redis-published timecode counts on a 24-frame base.** The divergence is not hypothetical-only: half-integer fps is reachable through a documented command — `cli_commands.py:59` registers `'set fps'` with a **`float`** parser, and in free mode `cinepi_controller.py:962` clamps only with `max(1, min(fps_max, requested_user_fps))`, preserving the fraction. Free mode is on by default in the shipped template (`resources/settings/settings_default.jsonc:71`, `"free": true`).

**Compounding:** the *fallback* rate is also multiply stated and inconsistent with F-251. `redis_controller.py:162` declares `conform_frame_rate: int = 24` as a constructor default (a **fifth** statement of the value already found in four places in F-251), `dng_encoder.cpp:1171`/`:1179` falls back to `24`, while `settings.jsonc:118` and `resources/settings/settings_default.jsonc:50` both say `25`. So on a config that omits the key, the display base and the DNG base agree at 24 — but the shipped config says 25, and there is no code path that reconciles them.

**(c) What breaks / what catches it:** an operator shooting at a half-integer rate gets a picture file, an audio file and an on-screen readout that do not agree on frame numbering — the exact failure timecode exists to prevent, and one that is invisible until the material reaches an NLE. Nothing catches it: no CI; `_test/` has no runner; and no test compares Python's timecode output against C++'s for any fps. The two languages cannot even see each other's rounding rule.

**(d) Single source of truth feasible?** The *rule* can be unified even though the code cannot: pick one definition ("nominal base = floor(fps + 0.5), clamped to >= 1") and write it identically in both languages with a shared comment naming the other site, plus a table-driven test that pins the mapping for a fixed list of fps values in each language. That is achievable with no shared build. Unifying the *implementation* is not feasible — the DNG stamp must be produced inside the C++ encoder thread.

**`unverified` (no hardware):** the end-to-end user-visible symptom. **Test that would settle it:** on a Pi, `set fps free 1` then `set fps 24.5`, record ~5 s with audio, then compare (i) the `tc_cam0` / `recording_tc_tod` Redis values against (ii) the SMPTE timecode in the first DNG's TIFF tag and (iii) the BWF `TimeReference` in the WAV. The prediction is that the DNG/WAV frame field reaches 24 while the Redis/GUI field wraps at 23.

### F-254 — "Which strings mean true" written out verbatim in 7 files; 2 of them disagree on unrecognised input

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-254 | medium | high | cinemate | 8 helpers, 7 verbatim copies of the literal set | The truth-set `("1","true","yes","on")` is re-typed in seven files; the two helpers that also carry a false-set return the *default* for an unknown string while the other five return `False` | `src/module/config_loader.py:10`, `simple_gui.py:50`, `mediator.py:80`, `cinepi_controller.py:345`, `dynamic_resolution.py:43`, `gpio_input.py:163`, `services/cinemate-recovery/cinemate-recovery.py:125` |

**(a) Locations** — eight independent coercion helpers, seven containing the same four-string literal:

| site | literal | unknown string → |
|---|---|---|
| `src/module/config_loader.py:10` `_TRUE_VALUES` / `config_loader.py:11` `_FALSE_VALUES`, used by `_coerce_bool_setting` at `config_loader.py:118` (test at `config_loader.py:127`) | both sets | **`default`** |
| `src/module/simple_gui.py:50` `_to_bool` (`simple_gui.py:53`) | true-set only | `False` |
| `src/module/mediator.py:80` `_as_bool` (`mediator.py:85`) | true-set only | `False` |
| `src/module/cinepi_controller.py:345` `_as_bool` (`cinepi_controller.py:348`) | true-set only | `False` |
| `src/module/dynamic_resolution.py:43` `_as_bool` (`dynamic_resolution.py:46`) | true-set only | `False` |
| `src/module/gpio_input.py:163` `_as_bool` (`gpio_input.py:171`) | true-set only | `False` (despite taking a `default` param) |
| `services/cinemate-recovery/cinemate-recovery.py:125` `_as_bool` (`cinemate-recovery.py:131`, `cinemate-recovery.py:133`) | both sets | **`default`** |
| `src/module/redis_controller.py:221` — inline, inside `_storage_preroll_active` rather than a helper | true-set only | falls through to `int()` at `redis_controller.py:224` |

**(b) Agree or drifted: agree on the literal, DRIFTED on semantics.** All seven copies of the true-set are byte-identical, so no drift there. But `_coerce_bool_setting("maybe", True)` returns `True` (`config_loader.py:131` — unmatched strings fall through to `return default`) while `_to_bool("maybe")` returns `False` (`simple_gui.py:53`). `gpio_input._as_bool` accepts a `default` parameter (`gpio_input.py:163`) but ignores it for strings (`gpio_input.py:171`), so it is the odd one out in its own signature. Two helpers therefore answer differently for the same input — a semantic drift that exists today, not a hypothetical one.

**(c) What breaks / what catches it:** adding a new accepted spelling (`"enabled"`, `"y"`) requires editing seven files; miss one and a setting silently behaves as `False` in exactly one subsystem. Nothing catches it — no CI, no runner for `_test/`, and no test exercises more than one helper. The recovery console's copy (`cinemate-recovery.py:125`) is a separate root service that cannot import from `src/module` at all, so its copy is structurally forced.

**(d) Single source of truth feasible?** Yes for six of the eight — a single `module/utils.py` coercion function replaces them with no cross-repo coordination. The recovery service's copy must stay (it is deliberately dependency-free, `cinemate-recovery.py:4`), so the honest end state is *two* copies with a comment in each naming the other, not one.

---

### F-255 — `storage_preroll_active` decoded SIX times with THREE incompatible rules, in one repo, one language

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-255 | medium | high | cinemate | 6 readers, 3 rules | One Redis boolean is re-decoded in six places; three accept `"true"/"yes"/"on"`, two accept only integers, one accepts only the exact string `"1"` | `redis_controller.py:218`, `redis_listener.py:557`, `ssd_monitor.py:1181`, `simple_gui.py:937`, `simple_gui.py:1707`, `cinepi_controller.py:1235` |

**(a) Locations and the three rules.** The key is declared once at `src/module/redis_controller.py:48` (`STORAGE_PREROLL_ACTIVE = "storage_preroll_active"`) — that part is clean. Its *decoding* is not:

- **Rule A — string-set then int** (accepts `"true"`, `"yes"`, `"on"`, `"1"`): `redis_controller.py:218-226`; `redis_listener.py:557-575`; `ssd_monitor.py:1181-1190`. `redis_listener._storage_preroll_active` is a near-verbatim retype of `redis_controller._storage_preroll_active` — same name, same logic, different class.
- **Rule B — `int()` only** (raises on `"true"`, caught, yielding **False**): `simple_gui.py:937-945` and `simple_gui.py:1707-1714`. Note `simple_gui.py` defines `_to_bool` at `simple_gui.py:50` and then does not use it in either place.
- **Rule C — exact string compare `== "1"`**: `cinepi_controller.py:1235`.

**(b) Agree or drifted:** they **agree in practice but not in specification**. The only writers are `storage_preroll.py:52`, `storage_preroll.py:226` and `storage_preroll.py:282`, which write the integers `0` and `1`, so all six rules currently return the same answer. They are *specified* differently: three readers explicitly handle `"true"/"yes"/"on"`, which is proof that someone anticipated that form — and the other three would silently read it as `False`. The divergence is latent, one writer away.

**(c) What breaks / what catches it:** if any future writer (the web API, a CLI handler, an ESP32 client) writes `"true"`, the HDMI GUI stops turning blue during pre-roll (`simple_gui.py:1730-1731`) and the pre-roll suppression at `cinepi_controller.py:1235` stops suppressing, while `ssd_monitor` and `redis_listener` continue to treat pre-roll as active. The system would be half in pre-roll. Nothing catches it: the failure is a wrong colour and a spurious clip, not an exception.

**(d) Single source of truth feasible?** Yes, trivially: `RedisController` already owns the canonical reader at `redis_controller.py:218`; the other five sites should call it. Entirely within one repo and one language. No hardware needed.

### F-256 — The parameter step tables are stated SEVEN times across FOUR languages; the shutter table has already DRIFTED

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-256 | **high** | high | cinemate | 7 statements, 4 languages | `arrays.iso.steps` and `arrays.shutter_a.steps` are written out in Python (×2), JSONC (×2), HTML data-attributes, HTML DOM text, and JavaScript — and the shutter table is missing `346.6` in exactly one of them | `config_loader.py:246`, `settings.jsonc:138`, `settings_default.jsonc:64`, `settings_editor.py:72`, `settings_editor.html:1302`, `settings_editor.html:1303-1313`, `settings_editor.html:3268` |

**(a) Locations.** The **shutter-angle step table** — one fact, "which shutter angles the operator can select" — appears at:

| # | language | site | value |
|---|---|---|---|
| 1 | Python (loader default) | `src/module/config_loader.py:246` | `[1, 45, 90, 135, 172.8, 180, 225, 270, 315, 360]` — **10 entries** |
| 2 | JSONC (live config) | `settings.jsonc:138` | `[1, 45, 90, 135, 172.8, 180, 225, 270, 315, 346.6, 360]` — 11 |
| 3 | JSONC (shipped template) | `resources/settings/settings_default.jsonc:64` | 11 entries, identical to #2 |
| 4 | Python (web action catalogue) | `src/module/app/settings_editor.py:72` | 11 entries, `"suffix": "°"` |
| 5 | HTML data-attribute | `src/module/app/templates/settings_editor.html:1302` | `data-chip-original="[1,45,90,135,172.8,180,225,270,315,346.6,360]"` |
| 6 | HTML DOM text | `settings_editor.html:1303-1313` | eleven literal `<span class="step-chip">` elements, one per angle (`346.6` at `settings_editor.html:1312`) |
| 7 | JavaScript | `settings_editor.html:3268` | `options: [1,45,90,135,172.8,180,225,270,315,346.6,360]` inside `ACTION_METHODS` (declared `settings_editor.html:3261`) |

The **ISO step table** is stated the same seven times: `config_loader.py:241`, `settings.jsonc:133`, `settings_default.jsonc:59`, `settings_editor.py:66`, `settings_editor.html:1272` (data-attribute), `settings_editor.html:1273-1281` (nine literal chips), `settings_editor.html:3263` (JS).

**(b) Agree or drifted: the ISO table AGREES across all seven; the shutter table has DRIFTED.** Site #1 (`config_loader.py:246`) is missing `346.6` — the 1/50 s-at-24fps flicker-free angle — that all six other sites carry. Six sources say `346.6` is a selectable shutter angle; the runtime default says it is not. Sites #5 and #6 are a second-order duplication *within one file*: the data-attribute at `settings_editor.html:1302` and the eleven DOM chips at `settings_editor.html:1303-1313` restate each other, so the shutter table is written twice inside a single HTML element's subtree.

**(c) What breaks / what catches it:** an operator whose `settings.jsonc` omits `arrays.shutter_a.steps` (a fresh install, a hand-trimmed config, or a config written by the settings editor's "revert to defaults" path — see F-251) gets a shutter table without `346.6`, while the web settings editor continues to render a `346.6` chip and the GPIO action dropdown continues to offer `346.6` as a bindable argument. Binding a button to `set_shutter_a 346.6` then produces a value not in the table. Adding a new angle requires seven coordinated edits in four languages; the HTML chips (site #6) are hand-written DOM with no generation step, so they are the most likely to be forgotten. Nothing catches any of it — no CI, `_test/` has no runner, and no test compares any two of the seven sites.

**(d) Single source of truth feasible?** **Yes, and this is the clearest case in the review.** All seven sites are in one repo. `settings.schema.json` or a single `resources/parameters.json` could be the origin: the loader reads it, the settings-editor page is served by Flask (`src/module/app/settings_editor.py`) and can therefore have its chips and its `ACTION_METHODS` rendered from the same data rather than typed into the template. Nothing here crosses the cinepi-raw boundary or needs hardware. The 40-line fix is to delete sites #4–#7 and serve them from #1.

---

### F-257 — HDMI-GUI labels published as data by Python, then re-typed as literal HTML

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-257 | low | high | cinemate | 2 statements + a live-but-unused channel | `populate_values()` publishes `iso_label`/`fps_label`/… for the web GUI, but `template.html` hardcodes the same strings and never reads them | `src/module/simple_gui.py:789-833`, `src/module/app/templates/template.html:429-491` |

**(a) Locations.** `simple_gui.populate_values()` emits label strings into the shared `values` dict: `"iso_label": "EI"` (`simple_gui.py:789`), `"shutter_label": "SHUTTER"` (`simple_gui.py:791`), `"fps_label": "FPS"` (`simple_gui.py:793`), `"wb_label": "WB"` (`simple_gui.py:795`), `"res_label": "RES"` (`simple_gui.py:798`), `"exposure_label": "EXP"` (`simple_gui.py:807`), and `"ram_label"`/`"cpu_label"`/`"cpu_temp_label"`/`"media_label"` at `simple_gui.py:831-833`. The web GUI restates every one as literal markup: `EI` at `template.html:440`, `SHUTTER` at `template.html:433`, `FPS` at `template.html:429`, `WB` at `template.html:444`, `RES` at `template.html:448`, `EXP` at `template.html:437`, `MEDIA` at `template.html:470`, `BUF` at `template.html:472`, `CPU` at `template.html:488`, `TEMP` at `template.html:489`, `RAM` at `template.html:490`. Grepping `template.html` for `_label` returns **nothing** — the published channel exists and is unused. The status-badge captions `DROP` and `SYNC` are likewise duplicated: `template.html:605` / `template.html:606` against `simple_gui.py:1298` / `simple_gui.py:1443` (and again at `simple_gui.py:1305`).

**(b) Agree or drifted:** currently **AGREE**, string for string.

**(c) What breaks / what catches it:** renaming a label (e.g. `EI` → `ISO`) changes the HDMI overlay and leaves the browser showing the old caption, or vice versa. Purely cosmetic, hence `low` — but it is the same structural defect as the already-confirmed **F-007** (colours duplicated between `simple_gui.py:21-45` and `template.html:23-40`), on the same file pair. Nothing catches it.

**(d) Single source of truth feasible?** Yes and nearly free — the transport already exists. `template.html` should read `V.iso_label` etc. from the dict `simple_gui.py:789` already populates. This is a one-sided edit to the template.

---

### F-258 — Supported-filesystem set stated three times, in three languages

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-258 | low | high | cinemate | 3 statements | The `{ext4, exfat, ntfs}` set is a Python guard, a JS display map and a JS dropdown option list | `src/module/ssd_monitor.py:997`, `src/module/app/templates/template.html:643`, `src/module/app/templates/settings_editor.html:3301` |

**(a) Locations.** The authoritative guard is `ssd_monitor.py:997` — `if fs not in {"ext4", "exfat", "ntfs"}` — backed by the mkfs branches at `ssd_monitor.py:1121` (`exfat`), `ssd_monitor.py:1128-1134` (`ntfs`) and the mount-option map at `ssd_monitor.py:602-603`. The web GUI restates the set as a display map at `template.html:643` (`{ exfat: 'exFAT', ntfs: 'NTFS' }[fs] || fs`), and the settings editor restates it a third time as the argument options for `format_drive` at `settings_editor.html:3301` (`options: ['exfat','ext4','ntfs']`).

**(b) Agree or drifted:** **AGREE on membership.** `template.html:643` lists only two because it falls back to the raw string for `ext4`, which is the intended rendering — not drift.

**(c) What breaks / what catches it:** adding a filesystem (e.g. `f2fs`) requires three edits; miss `settings_editor.html:3301` and the option is unbindable from the web editor while working everywhere else. Note that the JS list at `settings_editor.html:3301` is inside the same `ACTION_METHODS` array as F-256, whose Python twin (`settings_editor.py`) also carries a `format_drive` entry — so this set is effectively stated a fourth time in Python. Nothing catches any of it.

**(d) Single source of truth feasible?** Yes — same fix as F-256: render the editor's option lists server-side from the Python constant rather than typing them into the template.

### F-259 — The ISO↔analogue-gain unit convention lives only in C++, stated twice, and its own fallback contradicts it

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-259 | medium | high (code) / `unverified` (field impact) | both | 2 statements + 1 contradicting fallback | "Redis `iso` ÷ 100 = libcamera `AnalogueGain`" is written twice in cinepi-raw and nowhere in CineMate; the cold-start fallback skips the division | `cinepi-raw/cinepi/cinepi_controller.cpp:74`, `cinepi_controller.cpp:403`, `cinepi_controller.cpp:76-77` |

**(a) Locations.** CineMate publishes ISO in ISO units — `cinepi_controller.py:1863` writes `safe_value` drawn from the `iso` step table (`config_loader.py:241`, values `100…3200`). cinepi-raw converts on read, and states the conversion twice:
- `/workspace/tiramisioux/cinepi-raw/cinepi/cinepi_controller.cpp:74` — `iso_ = stoi(*iso)/100;` (integer division, startup path)
- `/workspace/tiramisioux/cinepi-raw/cinepi/cinepi_controller.cpp:403` — `iso_ = (unsigned int)(stoi(*r)/100.0);` (floating division, live-update path)

`iso_` is then applied as a gain at `cinepi_controller.cpp:213` (`options_->gain = iso_`) and `cinepi_controller.cpp:405` (`cl.set(libcamera::controls::AnalogueGain, iso_)`). The factor `100` appears nowhere in cinemate — the Python side does not know the convention exists.

**(b) Agree or drifted:** the two conversion sites agree on the factor but differ in type (`/100` truncates, `/100.0` rounds toward zero after a float divide — for the shipped step table all values are exact multiples of 100, so no divergence today). The **fallback contradicts both**: `cinepi_controller.cpp:76` assigns `iso_ = CP_DEF_ISO` where `CP_DEF_ISO` is `400` (`cinepi_controller.cpp:15`) *without* dividing, then `cinepi_controller.cpp:77` writes that same `400` back into Redis as the `iso` key. So one number is used as a gain and published as an ISO in adjacent lines — the unit convention is violated by the code that defines it.

**(c) What breaks / what catches it:** this fires only when the `iso` Redis key is absent. CineMate writes `iso` **only** inside `set_iso` (`cinepi_controller.py:1863` is the sole writer in `src/`) — there is no startup write — and nothing in the repo flushes Redis. So on a first boot against a fresh Redis, cinepi-raw takes the fallback and configures a gain of 400 rather than 4, then publishes `iso=400` so every CineMate surface displays a plausible "400" while the sensor is at maximum gain. Nothing catches it: the value shown is correct, only the picture is wrong. If the factor ever changes, three C++ sites and the Python step table must move together with nothing linking them.

**(d) Single source of truth feasible?** The conversion must live on the C++ side (it feeds a libcamera control), but it should be one function called from both `cinepi_controller.cpp:74` and `cinepi_controller.cpp:403`, with `CP_DEF_ISO` expressed in the same unit as the Redis key. Across the boundary, the honest fix is for CineMate to write `iso` at startup so the C++ fallback is never reached — a cinemate-only change requiring no cinepi-raw coordination.

**`unverified` (no hardware): TEST** — on a Pi, `redis-cli DEL iso`, restart cinepi-raw, then read `redis-cli GET iso` and the reported analogue gain from libcamera metadata (or simply observe whether the first frames are grossly overexposed). Prediction: `iso` reads `400` while the applied gain is 400×, not 4×.

---

### F-260 — The settings.jsonc absolute path hardcoded in 7 files; the comment that documents the duplication is itself out of date

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-260 | low | high | cinemate | 7 statements | `"/home/pi/cinemate/settings.jsonc"` is re-typed in seven files, and the in-code inventory of those copies lists four of them, one with a wrong line number | `settings_editor.py:45-47`, `main.py:51`, `wifi_hotspot.py:44`, `settings_editor.py:48`, `cinepi_controller.py:27`, `cinepi_multi.py:27`, `simple_gui.py:155`, `cinemate-recovery.py:64` |

**(a) Locations.** Seven independent declarations of the same absolute path: `src/main.py:51`, `src/module/wifi_hotspot.py:44`, `src/module/app/settings_editor.py:48`, `src/module/cinepi_controller.py:27`, `src/module/cinepi_multi.py:27`, `src/module/simple_gui.py:155` (inline, not a constant — `load_settings("/home/pi/cinemate/settings.jsonc")`), and `services/cinemate-recovery/cinemate-recovery.py:64`.

**(b) Agree or drifted:** the **paths agree**; the **documentation of the duplication has drifted.** The comment at `src/module/app/settings_editor.py:45-47` states "Every settings.jsonc caller in this codebase hardcodes this same absolute path (`src/main.py:51`, `cinepi_multi.py:27`, `cinepi_controller.py:27`, `wifi_hotspot.py:37`)". It names **four** of the seven — omitting `simple_gui.py:155`, `cinemate-recovery.py:64` and its own `settings_editor.py:48` — and its `wifi_hotspot.py:37` reference is wrong: the declaration is at `wifi_hotspot.py:44`. This is the review's clearest demonstration of the failure mode, because the drifted artefact is a hand-maintained index *of a duplication*.

**(c) What breaks / what catches it:** relocating the install prefix requires seven edits. `simple_gui.py:155` is the likeliest miss — it is an inline string argument, not a named constant, so a grep for `SETTINGS_FILE` will not find it. Nothing catches it; the symptom would be one subsystem silently falling back to defaults.

**(d) Single source of truth feasible?** Six of the seven can import one constant. `services/cinemate-recovery/cinemate-recovery.py:64` cannot (deliberately dependency-free, `cinemate-recovery.py:4`), so two copies is the honest floor — the same shape as F-254.

### F-261 — Sensor packing table duplicated as a lossy Python fallback that silently drops the Pi-4 rule

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-261 | medium | high | cinemate | 2 statements, one lossy | `FALLBACK_PACKING_INFO` restates `sensors.json`'s `packing` values but carries no `packing_by_platform`, so a missing database silently un-packs imx477/imx296 on Pi 4 | `src/module/sensor_detect.py:12-19`, `resources/sensors.json:7-8`, `sensors.json:40-41`, `sensor_detect.py:647-654` |

**Good news first:** the sensor mode tables are **not** triply duplicated. `resources/sensors.json` is the single source for modes/resolutions/bit-depths/max-fps; `settings.jsonc:113` only points at it (`"database_file": "resources/sensors.json"`), and cinepi-raw encodes **no** sensor table at all — grepping the whole C++ tree for `imx477|imx296|imx283|imx519|imx585` returns exactly one hit, a tuning comment at `cinepi-raw/cinepi/cinepi_controller.hpp:288`. The "three copies of a sensor table" hypothesis is **disproved**; this is the one residue.

**(a) Locations.** `src/module/sensor_detect.py:12` declares `FALLBACK_PACKING_INFO` with six entries (`sensor_detect.py:13-18`). `resources/sensors.json` declares the same `packing` values plus platform overrides: `sensors.json:7-8` (imx477 `"U"` + `"packing_by_platform": {"pi4": "P"}`), `sensors.json:40-41` (imx296, same), `sensors.json:57` (imx585 `"U"`), `sensors.json:88` (imx283 `"U"`), `sensors.json:150` (imx519 `"P"`).

**(b) Agree or drifted: the base values agree; the fallback is DRIFTED by omission.**
- `FALLBACK_PACKING_INFO` encodes **no** `packing_by_platform`. `get_packing_for_platform` (`sensor_detect.py:620`) sources the override exclusively from the database (`sensor_detect.py:647-653`) and otherwise returns `base` (`sensor_detect.py:654`), which comes from the fallback. When `sensors.json` is missing or malformed, `_load_sensor_database` returns an empty sensors object (`sensor_detect.py:111`, `:114`, `:118`) and `_packing_info_from_database` degrades to the bare fallback (`sensor_detect.py:122`). **Result: on a Pi 4, imx477 and imx296 resolve to `U` where the database says `P`.**
- The alias sets disagree too: the fallback lists `imx585_mono` (`sensor_detect.py:18`) but not `imx296_mono`, which `sensors.json:42` declares.

This directly contradicts the comment at `sensor_detect.py:20-27`, which calls the Pi-4 check "the single canonical platform check" that "`cinepi_multi` and `cinepi_controller` both reach ... so the launch command and the GUI/telemetry agree".

**(c) What breaks / what catches it:** packed vs unpacked CSI2 is a DMA/CMA-pressure decision — the comment at `sensor_detect.py:21-23` says packed modes are preferred on Pi 4 for exactly that reason. Losing the override sends `--mode W:H:B:U` to cinepi-raw (`cinepi_multi.py:467`, see F-250) on a platform that needs `P`, which is a capture-failure or dropped-frame class of problem, not a cosmetic one. It fires only when `sensors.json` is unreadable — but that is precisely the degraded state the fallback exists to survive, and the failure is silent: `sensor_detect.py:110` logs a `warning` and carries on. Nothing else catches it.

**(d) Single source of truth feasible?** Yes. Either delete `FALLBACK_PACKING_INFO` and make a missing `sensors.json` a hard startup error (the database is a repo file, not user data — its absence is a broken install), or make the fallback a full mirror including `packing_by_platform`. The first is better: it removes the second copy rather than doubling it. Cinemate-only, no hardware needed to implement.

---
## Summary table

| ID | severity | confidence | repo | redundancy | summary | evidence |
|---|---|---|---|---|---|---|
| F-250 | medium | high | both | 4 sites | `--mode W:H:B:{P\|U}` grammar built in 3 Python sites, parsed by `sscanf` in C++ | `cinepi_controller.py:1465`, `cinepi_multi.py:467`, `cinepi_multi.py:787`, `cinepi-raw/core/options.cpp:55` |
| F-251 | **high** | high | cinemate | 4 registries | Config defaults declared four times; **11 keys already disagree** | `config_loader.py:149`, `settings.schema.json:13+`, `settings_default.jsonc`, `settings.jsonc` |
| F-252 | medium | high | cinemate | 3 per block | `web_api` / `recovery` defaults live outside the central loader, stated 3× each | `web_api_settings.py:10`, `cinemate-recovery.py:78`, `settings.schema.json:38` |
| F-253 | **high** | high / `unverified` field | both | 4 derivations | Nominal timecode fps computed 4× with **3 different rounding rules**; Python and C++ disagree at half-integer fps | `redis_controller.py:334`, `simple_gui.py:794`, `cinepi_sound.cpp:154`, `dng_encoder.cpp:1178` |
| F-254 | medium | high | cinemate | 8 helpers | `("1","true","yes","on")` retyped in 7 files; 2 helpers disagree on unknown input | `config_loader.py:10`, `simple_gui.py:50`, `mediator.py:80`, +5 |
| F-255 | medium | high | cinemate | 6 readers | One Redis boolean decoded 6× with 3 incompatible rules | `redis_controller.py:218`, `redis_listener.py:557`, `simple_gui.py:937`, +3 |
| F-256 | **high** | high | cinemate | 7 statements, 4 languages | ISO/shutter step tables stated 7×; **shutter table missing `346.6` in one** | `config_loader.py:246`, `settings.jsonc:138`, `settings_editor.py:72`, `settings_editor.html:1302` |
| F-257 | low | high | cinemate | 2 + unused channel | GUI labels published as data by Python, re-typed as literal HTML | `simple_gui.py:789-833`, `template.html:429-491` |
| F-258 | low | high | cinemate | 3 statements | Supported-filesystem set in Python guard, JS map, JS dropdown | `ssd_monitor.py:997`, `template.html:643`, `settings_editor.html:3301` |
| F-259 | medium | high / `unverified` field | both | 2 + contradicting fallback | ISO÷100→gain convention stated twice in C++, violated by its own fallback | `cinepi_controller.cpp:74`, `:403`, `:76-77` |
| F-260 | low | high | cinemate | 7 statements | settings.jsonc path hardcoded 7×; the comment indexing the copies is itself stale | `settings_editor.py:45-47`, +6 |
| F-261 | medium | high | cinemate | 2, one lossy | Packing fallback table drops `packing_by_platform`, un-packing imx477/imx296 on Pi 4 | `sensor_detect.py:12-19`, `sensors.json:7-8`, `sensor_detect.py:647-654` |

**By severity: high 3, medium 6, low 3 — 12 new findings** (plus the 4 pre-confirmed: F-007, F-016, F-027/F-028).
- **high (3):** F-251, F-253, F-256
- **medium (6):** F-250, F-252, F-254, F-255, F-259, F-261
- **low (3):** F-257, F-258, F-260

**Already drifted (not merely redundant):** F-251, F-253, F-256, F-259, F-261 — and F-254/F-255 have drifted in *specification* while agreeing in current practice.

---

## VERDICT — for ADR-001

### Is this a systemic pattern or a few coincidences?

**Systemic, and not close.** Sixteen distinct instances (12 new + 4 pre-confirmed), spanning every boundary the project has:

| boundary | instances |
|---|---|
| Python ↔ C++ (cross-repo) | F-016, F-027/F-028, F-250, F-253, F-259 |
| Python ↔ HTML/CSS | F-007, F-257 |
| Python ↔ JavaScript | F-256, F-258 |
| Python ↔ JSON/JSONC | F-251, F-252, F-256, F-261 |
| Python ↔ Python (same repo, same language) | F-254, F-255, F-260 |

The decisive evidence is not the count, it is that **three of the copies are hand-maintained indexes of the duplication itself, and two of those are already wrong**: the CSS comments in `template.html:23-40` that name the Python constants they mirror (F-007); the comment at `settings_editor.py:45-47` that inventories the settings-path copies and gets both the count and a line number wrong (F-260); and the comment at `cinepi_multi.py:774` asserting its mode string "matches what `CinePiProcess._build_args` launches" (F-250). When a codebase starts writing prose to keep its duplicates aligned, and that prose drifts too, the pattern is structural rather than incidental.

Note also that duplication is **not** uniform — where the project has one source of truth it works. `resources/sensors.json` really is the single sensor database (F-261), and `populate_values()` really does feed both GUI surfaces one dict of derived state. The failures cluster in exactly two places: **defaults** and **enumerations of selectable values**.

### What it implies for "one source of truth, N renderers"

**The pattern is viable, but only for a strict subset of the truth — and the ADR must draw that line explicitly rather than assume it generalises.**

**1. Within cinemate, it is viable today and mostly cheap.** Nine of the twelve findings (F-251, F-252, F-254, F-255, F-256, F-257, F-258, F-260, F-261) never cross a repo boundary. All three `high` findings are in this group. The two highest-value fixes are ordinary refactors:
- **Serve the settings editor's enumerations instead of typing them.** `settings_editor.html` is rendered by Flask (`src/module/app/settings_editor.py`); its step chips (`settings_editor.html:1272`, `:1302`), its `data-chip-original` attributes and its `ACTION_METHODS` array (`settings_editor.html:3261`) can all be emitted from the Python catalogue and the schema. This alone kills F-256 and F-258.
- **Pick one defaults registry.** `settings.schema.json` already agrees with `config_loader.py` on all 41 comparable paths — it is the natural origin, with `_apply_settings_defaults` and `settings_default.jsonc` generated from or asserted against it. This kills F-251 and most of F-252.

**2. Across the cinemate↔cinepi-raw boundary, "one source of truth" is not achievable, and the ADR should not promise it.** The repos version independently, share no build, and the C++ side owns facts that must be computed inside the encoder thread (F-253's DNG timecode) or fed to libcamera (F-259's gain). What is achievable is weaker and should be named as such: **one *specification*, N implementations, plus a conformance test per language.** F-253 is the model case — the rounding rule cannot be shared as code, but it can be pinned by a table of (fps → nominal base) assertions written once and executed in both languages.

**3. The binding constraint is not language count — it is that nothing verifies anything.** Every finding here ends with the same sentence: nothing would catch it. There is no CI, and the 27 files in `_test/` have no runner. Two tests already read the two defaults registries separately (`_test/test_camera_log_encode_defaults.py:35`, `_test/test_arrays_free_increment_defaults.py:32`) and simply never compare them. **A GUI unification that does not ship a test runner will re-grow these duplicates within a release.** Conversely, a runner plus roughly five cross-registry assertions would have caught F-251, F-253, F-255, F-256 and F-261 — five of the six drifted findings — *without any architectural change at all*.

**Recommendation for ADR-001, in priority order:**
1. **Ship a test runner first.** It is a precondition for every other item and independently catches five of six drifts. Nothing about the GUI architecture needs to be decided to do this.
2. **Adopt "one source of truth, N renderers" for cinemate-internal data** — defaults, enumerations, labels, colours. Scope it to `settings.schema.json` + a generated defaults module + server-rendered editor enumerations.
3. **Explicitly scope it OUT for the cinepi-raw boundary,** and substitute "one specification, N implementations, conformance-tested per language" for the five cross-repo instances (F-016, F-027/F-028, F-250, F-253, F-259).
4. **Accept two deliberate copies** where isolation is the point: the recovery console (`cinemate-recovery.py:4`) must stay dependency-free. Two documented copies with reciprocal comments is the honest floor — but only if a test pins them together, since F-260 proves comments alone do not hold.

### Hardware-dependent claims

Nothing in this report *requires* a Pi to establish the duplication — every finding is static and cited. Two field impacts are `unverified` and carry their settling test inline: **F-253** (half-integer-fps timecode divergence between DNG/WAV and GUI) and **F-259** (cold-start ISO/gain unit violation). Both would be settled in under ten minutes on a camera.
