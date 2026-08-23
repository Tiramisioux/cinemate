# CENSUS — deterministic inventory

**Session:** S01 · **Date:** 2026-08-17 · **Opinion-free by design.**
Everything here is a counted or grepped fact. Interpretation belongs in later sessions.

**Snapshot points:**

| Repo | Ref | SHA | Notes |
|---|---|---|---|
| cinemate | `claude/cinemate-system-review-kickoff-cilicc` (= `origin/dev`) | `02b5a39` | clean tree |
| cinepi-raw | `main` | `774402c` | shallow read-only clone; **not `dev`** — see STATE.md D2 |

> ⚠ cinepi-raw figures below are for **`main` @ 774402c**, not `dev` @ `ea96f2d` as in
> KICKOFF §6.2. Several counts differ materially. Do not compare the two tables directly.

---

## 1. File inventory

### cinemate

| Category | Count | Notes |
|---|---|---|
| Python files under `src/` | 47 | excludes `__pycache__` |
| Python LOC under `src/` | 19,794 | |
| Files under `src/` total | 62 | incl. 2 fonts, 1 vendored JS, 6 HTML, 5 stale `.pyc` |
| Test files in `_test/` | 34 | 27 `test_*.py`, 3 utilities, 4 underscore-prefixed |
| Markdown docs in `docs/` | 50 | 4,741 LOC; 5 are 0 bytes |
| Service units/scripts in `services/` | 22 | 5 subsystems + 2 Makefiles |
| Shell: installer | 1,916 LOC | `cinemate-install.sh` |
| Shell: updater | 68 LOC | `cinemate-update.sh` |

**Stale bytecode committed or left in tree** — `src/module/__pycache__/` holds 5
`.cpython-39.pyc` files (`keyboard`, `simple_gui`, `framebuffer`, `adc`, `__init__`).
Note `adc.cpython-39.pyc` has **no corresponding `adc.py`** in `src/module/` — evidence
of a deleted module. Flagged for S04.

### cinepi-raw

| Category | Count |
|---|---|
| C/C++/hpp sources | 24,051 LOC total — **`main` figure; `dev` is 29,438** (F-231) |
| Files in `cinepi/` | 29 |
| Patch files at root | 2 (`add-redis-timecode.patch`, `add-tc.patch`) |

---

> **⚠ `main` figures.** Every cinepi-raw number in §1 and §2 was measured on `main` @
> `774402c`. Both repos are now on `dev` (`STATE.md` D2). cinepi-raw `dev` @ `ea96f2d` is
> **29,438** C/C++ LOC, not 24,051 — +22% (F-231). **KICKOFF §6.2's C++ table describes
> `dev` and is now the applicable one.**

## 2. Size census — files over 200 LOC

### cinemate Python

| File | LOC |
|---|---|
| `src/module/cinepi_controller.py` | 2626 |
| `src/module/simple_gui.py` | 2129 |
| `src/module/redis_listener.py` | 2084 |
| `src/module/ssd_monitor.py` | 1323 |
| `src/main.py` | 1089 |
| `src/module/cinepi_multi.py` | 878 |
| `src/module/usb_monitor.py` | 877 |
| `src/module/sensor_detect.py` | 853 |
| `src/module/wifi_hotspot.py` | 753 |
| `src/module/gpio_input.py` | 656 |
| `src/module/config_loader.py` | 588 |
| `src/module/storage_preroll.py` | 487 |
| `src/module/redis_controller.py` | 411 |
| `src/module/cli_commands.py` | 362 |
| `src/module/app/settings_editor.py` | 355 |
| `src/module/analog_controls.py` | 299 |
| `src/module/serial_handler.py` | 272 |
| `src/module/i2c/quad_rotary_controller.py` | 269 |
| `src/module/timekeeper.py` | 243 |
| `src/module/app/api.py` | 225 |
| `src/module/dynamic_resolution.py` | 211 |
| `src/module/app/boot_config.py` | 210 |
| `src/module/parameters.py` | 206 |
| `src/module/gpio_output.py` | 203 |

Nine modules ≥ 850 LOC; five ≥ 1300. (F-010)

### cinepi-raw C/C++ (`main` @ 774402c)

| File | LOC | vs KICKOFF §6.2 (`dev`) |
|---|---|---|
| `cinepi/cinepi_sound.cpp` | 1804 | same |
| `cinepi/dng_encoder.cpp` | 1521 | −149 |
| `core/rpicam_app.cpp` | 1364 | −11 |
| `cinepi/lj92.c` | 1218 | not listed in KICKOFF |
| `encoder/libav_encoder.cpp` | 768 | same |
| `cinepi/cinepi_audio_capture.cpp` | 744 | same |
| `cinepi/cinepi_controller.cpp` | 743 | −151 |
| `cinepi/dualHdmiPreviewStage.cpp` | 638 | same |
| `image/jpeg.cpp` | 636 | — |
| `cinepi/cinepi_options.cpp` | 621 | −44 |
| `preview/drm_preview.cpp` | 542 | −114 |
| `image/dng.cpp` | 538 | — |
| `core/options.cpp` | 530 | — |
| `post_processing_stages/hdr_stage.cpp` | 524 | — |
| `preview/egl_preview.cpp` | 454 | — |
| `encoder/h264_encoder.cpp` | 378 | — |
| `apps/rpicam_still.cpp` | 361 | — |
| `core/options.hpp` | 323 | — |
| `cinepi/cinepi_controller.hpp` | 315 | — |
| `tests/phase_lock_core_test.cpp` | 313 | — |
| `cinepi/dng_encoder.hpp` | 305 | — |
| `cinepi/sharedContextStage.cpp` | 304 | — |
| `core/rpicam_app.hpp` | 290 | — |
| `core/video_options.hpp` | 282 | — |
| `cinepi/cinepi_raw.cpp` | 260 | — |
| `post_processing_stages/post_processing_stage.cpp` | 258 | — |
| `cinepi/mjpegPreviewStage.cpp` | 245 | — |
| `cinepi/_mjpegPreviewStage.cpp` | 240 | **dead — F-012** |
| `preview/qt_preview.cpp` | 226 | — |

`lj92.c` (1218 LOC) is a vendored lossless-JPEG codec, absent from KICKOFF's table.
Whether it is a pristine upstream vendor drop or locally modified is **unverified** —
queued for S03/S04.

---

## 3. cinemate module list — `cinepi/` and `src/module/`

`src/module/` (47 Python files):

`analog_controls` · `app/` (`__init__`, `api`, `boot_config`, `raw_files`,
`settings_editor`, `main/routes`, `main/events`) · `battery_monitor` ·
`cinepi_controller` · `cinepi_multi` · `cli_commands` · `config_loader` ·
`console_display` · `dmesg_monitor` · `dynamic_resolution` · `framebuffer` ·
`gpio_input` · `gpio_output` · `grove_base_hat_adc` · `i2c/i2c_oled` ·
`i2c/quad_rotary_controller` · `ir_filter` · `logger` · `mediator` · `parameters` ·
`redis_controller` · `redis_listener` · `rotary_encoder` · `rpi_gpio_wrapper` ·
`sensor_detect` · `serial_handler` · `simple_gui` · `ssd_monitor` ·
`status_broadcast` · `storage_preroll` · `storage_profiles` · `timekeeper` · `usb_monitor` ·
`utils` · `web_api_settings` · `wifi_hotspot`

`cinepi-raw` `cinepi/` (29 files): `cinepi_raw` · `cinepi_manager` · `cinepi_controller` ·
`cinepi_state` · `cinepi_recorder` (hpp) · `cinepi_options` · `cinepi_frameinfo` (hpp) ·
`cinepi_sound` · `cinepi_audio_capture` · `dng_encoder` · `ifd_builder` (hpp) · `lj92` ·
`mjpegPreviewStage` · `_mjpegPreviewStage` (dead) · `dualHdmiPreviewStage` ·
`sharedContextStage` · `phase_lock_core` (hpp) · `raw_options` (hpp) · `utils` ·
`yuv2rgb` (hpp)

Meson build source list (`cinepi/meson.build:24-34`) — 10 translation units:
`cinepi_raw`, `dng_encoder`, `sharedContextStage`, `mjpegPreviewStage`,
`dualHdmiPreviewStage`, `cinepi_controller`, `cinepi_sound`, `cinepi_state`, `utils`,
`cinepi_options`.

Note: `cinepi_audio_capture.cpp` (744 LOC) is **not** in this list, and neither is
`lj92.c`. They may be pulled in by another meson file or by `#include`. Not resolved in
S01 — flagged for S03.

---

## 4. Python internal import graph (cinemate)

Stdlib and third-party edges removed; `module.*` and relative edges only.

```
src/main.py
  └→ analog_controls, app, battery_monitor, cinepi_controller, cinepi_multi,
     cli_commands, config_loader, console_display, dmesg_monitor, framebuffer,
     gpio_input, gpio_output, i2c.i2c_oled, i2c.quad_rotary_controller, logger,
     mediator, redis_controller, redis_listener, sensor_detect, serial_handler,
     simple_gui, ssd_monitor, status_broadcast, storage_preroll, usb_monitor,
     web_api_settings, wifi_hotspot            [27 direct module imports]

app/__init__      → .api, .main.events, .main.routes, .settings_editor, web_api_settings
app/api           → redis_controller, web_api_settings
app/main/events   → redis_controller
app/main/routes   → web_api_settings
app/settings_editor → module.app, config_loader
analog_controls   → grove_base_hat_adc, redis_controller
cinepi_controller → config_loader, dynamic_resolution, ir_filter, redis_controller,
                    sensor_detect, storage_profiles
cinepi_multi      → config_loader, framebuffer, redis_controller, sensor_detect,
                    storage_profiles
gpio_output       → rpi_gpio_wrapper
i2c/i2c_oled      → utils
ir_filter         → redis_controller
mediator          → redis_controller
redis_listener    → redis_controller
simple_gui        → config_loader, console_display, dynamic_resolution, framebuffer,
                    redis_controller, utils
ssd_monitor       → redis_controller, storage_profiles
storage_preroll   → redis_controller
timekeeper        → redis_controller
wifi_hotspot      → config_loader
stream.py         → app (BROKEN), cinepi_controller, redis_controller, simple_gui  [F-013]
```

### Observations (mechanical, not yet findings)

- **`redis_controller` is the hub:** imported by 10 modules. Consistent with KICKOFF §9
  principle 1 ("Redis is the single source of live state") — to be tested in S02/S11.
- **`main.py` imports 27 modules directly.** No intermediate composition layer.
- **Not imported by `main.py` or any other module** — candidate dead or
  externally-invoked: `parameters`, `rotary_encoder`, `timekeeper`, `storage_profiles`
  (imported by 3 others, so live), `battery_monitor` (imported by main), `raw_files`,
  `boot_config`. Precisely: `parameters.py`, `rotary_encoder.py`, `timekeeper.py` have
  **no inbound internal edge** in this graph. `app/raw_files.py` and `app/boot_config.py`
  likewise show no inbound edge — but they may be imported dynamically or by the HTML
  layer. **All flagged for S04; none asserted dead here.**
- Leaf modules with no internal deps: `dynamic_resolution`, `parameters`,
  `redis_controller`, `storage_profiles`, `status_broadcast`, `web_api_settings`,
  `app/boot_config`, `app/raw_files`. These are the cheapest units to test.

> ### ⚠ CORRECTION (S04) — this graph had a real bug, not just the caveat below
>
> The regex read `from module import parameters` as an edge to **`module`**, not to
> `module.parameters`. Three live modules therefore appeared to have no inbound edge
> (`cinepi_controller.py:25`, `quad_rotary_controller.py:14`, `analog_controls.py:10` all
> import `parameters` that way). A second miss: `app/raw_files.py` and `app/boot_config.py`
> are reached by **relative** imports inside `create_app`.
>
> **`parameters.py`, `app/raw_files.py`, `app/boot_config.py`, `mediator.py` and `utils.py`
> are LIVE.** The "candidate dead" list below is wrong about all five.
> The corrected result is F-122: exactly **4 of 48** modules are unreachable from
> `main.py`. Use that, not this section.

**Method caveat:** graph built by regex over `import`/`from` lines. It misses dynamic
imports (`importlib`, `__import__`), imports inside function bodies, relative imports, and
— as the correction above records — `from <pkg> import <module>` form. `stream.py`'s
function-body imports were caught only because they are `from module.x import Y` at
column 4. Treat absence of an edge as *suggestive*, not proof.

---

## 5. Entry points

| Path | Line | Kind |
|---|---|---|
| `src/main.py` | 1088 | **the** CineMate entry point |
| `src/stream.py` | 20 | dead — F-013 |
| `src/module/wifi_hotspot.py` | 749 | module self-test / standalone |
| `src/module/battery_monitor.py` | 93 | module self-test / standalone |
| `src/module/grove_base_hat_adc.py` | 155 | module self-test / standalone |
| `src/module/framebuffer.py` | 173 | **commented out** `# if __name__ == "__main__":` |
| `services/wifi-hotspot/wifi-hotspot.py` | 52 | systemd service |
| `services/cinemate-recovery/cinemate-recovery.py` | 1182 | systemd service |
| `services/redis-log-maintenance/redis-log-maintenance.py` | 131 | systemd timer |
| `services/storage-automount/storage-automount.py` | 1123 | systemd service |

Note `services/storage-automount/storage-automount.py` is ~1123+ LOC — a large module
not counted in KICKOFF §6.2's Python table, which covered only `src/`. Two `wifi_hotspot`
implementations exist (`src/module/wifi_hotspot.py` 753 LOC and
`services/wifi-hotspot/wifi-hotspot.py` 52 LOC) plus a fourth underscore-prefixed copy in
`_test/_wifi_hotspot_service.py`. Relationship unresolved — S04.

---

## 6. Network ports bound

| Port | Bound by | Evidence |
|---|---|---|
| 5000 | Flask + SocketIO web GUI & settings editor & API | `src/main.py:935` |
| 5000 | (dead duplicate) | `src/stream.py:4,18` — F-013 |
| 8888 | status broadcast, UDP/TCP, default overridable by settings | `src/module/status_broadcast.py:63`, `src/main.py:819` |
| 8080 | recovery console (stdlib HTTP) | `services/cinemate-recovery/cinemate-recovery.py:4,152` |
| 8000 | cam0 MJPEG preview (consumed, not bound, by cinemate) | `src/module/app/main/routes.py:8` |
| 8001 | cam1 MJPEG preview (consumed, not bound, by cinemate) | `src/module/app/main/routes.py:9` |
| 6379 | Redis client connections (not a bind) | `redis_controller.py:162-163`, `redis_listener.py:22-30`, `usb_monitor.py:141,439,458,581` |
| 8423 | battery HAT TCP client (not a bind) | `src/module/battery_monitor.py:14` |

Confirms KICKOFF §6.3 ports. **`usb_monitor.py` opens its own `StrictRedis` client at
four separate call sites** rather than reusing the injected controller — noted, not yet
judged. S04/S06.

---

## 7. Redis keys — PARTIAL, method insufficient

**This section is incomplete and must be redone in S02.** Recorded so the next session
does not repeat the failed approach.

Direct string-literal keys found by grepping `get_value|set_value|hget|hset` call sites
in `src/` — **13 only**:

`FSCK_STATUS` · `bit_depth` · `fps` · `fps_actual` · `fps_user` · `framecount` ·
`height` · `is_buffering` · `is_recording` · `rec` · `user_changing_fps` · `vu_meter` ·
`width`

`docs/redis-keys.md` documents **69** keys:

`anamorphic_factor` `bit_depth` `buffer` `buffer_size` `cam_init` `cameras` `cg_rb`
`drop_frame` `drop_frame_count` `drop_frame_during_last_take` `drop_frame_relay`
`exposure_time` `file_size` `fps` `fps_actual` `fps_last` `fps_max` `fps_user`
`framecount` `frames_in_sync` `gui_layout` `hdmi_preview_source` `hdr` `hdr_blend`
`hdr_gain_adder` `hdr_threshold_high` `hdr_threshold_low` `ir_filter` `is_buffering`
`is_mounted` `is_recording` `is_writing` `is_writing_buf` `iso` `last_dng_cam0`
`log_encode_cam0` `log_encode_request` `lores_width` `memory_alert`
`missing_frame_count` `pi_model` `rec` `record_cams` `recording_tc_rec`
`recording_time` `recording_time_tod` `sensor` `sensor_mode` `shutter_a`
`shutter_a_sync_mode` `shutter_angle_actual` `shutter_angle_nom`
`shutter_angle_transient` `space_left` `storage_filesystem` `storage_mount_options`
`storage_preroll_active` `storage_recorder_profile` `storage_type` `tc_cam0`
`tc_hole_count` `wb` `wb_user` `width` `write_speed_to_drive` `zoom`

**Why the grep failed:** key names are evidently passed as variables, built dynamically
(`tc_cam0`, `log_encode_cam0`, `last_dng_cam0` are clearly `f"{base}_cam{n}"` patterns),
or accessed through wrapper methods on `RedisController` rather than at literal call
sites. The 13 found are only those spelled inline.

**Correct method for S02:** read `src/module/redis_controller.py` (411 LOC) in full to
learn the access API, then trace callers of that API. Cross-reference against
`redis_listener.py` (2084 LOC) which is the read side. Only then diff against
`docs/redis-keys.md` — that diff is an S09 deliverable, not S01's.

---

## 8. Settings keys

`settings.jsonc` — 386 LOC, 12 top-level sections:

| Line | Section |
|---|---|
| 2 | `$schema` → `./settings.schema.json` |
| 5 | `system` |
| 62 | `sensors` |
| 117 | `settings` |
| 131 | `arrays` |
| 182 | `image_capture` |
| 205 | `audio_capture` |
| 219 | `hdmi_display` |
| 250 | `hardware_controls` |
| 312 | `input_peripherals` |
| 366 | `hardware_outputs` |
| 377 | `output_peripherals` |

`settings.schema.json` is 393 LOC — nearly 1:1 with the settings file, suggesting the
schema is maintained alongside it. Whether every schema key is actually *read* by code is
an S09 question.

---

## 9. Docs inventory

**50 files, 4,741 LOC.**

| LOC | File | LOC | File |
|---|---|---|---|
| 1061 | `installation-steps.md` | 41 | `ssh.md` |
| 611 | `settings-json.md` | 35 | `speed-ramping.md` |
| 331 | `building-control-units.md` | 35 | `audio-recording.md` |
| 236 | `overclocking.md` | 32 | `web-gui.md` |
| 201 | `web-api.md` | 32 | `hotspot-logic.md` |
| 175 | `hardware-controls.md` | 31 | `simple-gui.md` |
| 173 | `clear-hdr.md` | 30 | `system-services.md` |
| 159 | `image-circle.md` | 30 | `cinepi-multi.md` |
| 143 | `cli-user-guide.md` | 27 | `acknowledgments.md` |
| 131 | `sensors.md` | 23 | `digital-zoom.md` |
| 111 | `recovery-console.md` | 21 | `storage-preroll.md` |
| 109 | `config-txt.md` | 19 | `audio-sync.md` |
| 98 | `cli-commands.md` | 17 | `troubleshooting.md` |
| 95 | `redis-guide.md` | 15 | `compiling-cinepi-raw.md` |
| 88 | `simple-gui-refresh-tuning.md` | 11 | `overview.md` |
| 74 | `redis-keys.md` | 8 | `preinstalled-hardware.md` |
| 73 | `controller-methods.md` | 7 | `index.md` |
| 71 | `cinemate-log.md` | 7 | `coverpage.md` |
| 66 | `changelog.md` | 1 | `hardware-introduction.md` |
| 62 | `todo.md` | 1 | `brick.md` |
| 56 | `readme.md` | 0 | `links.md` |
| 54 | `backing-up-sd-card.md` | 0 | `known-issues.md` |
| 50 | `dual-sensors.md` | 0 | `contributors.md` |
| 46 | `sensor.sizes.md` | 0 | `contributing.md` |
| 44 | `getting-started.md` | 0 | `bare-bones-build.md` |

### Empty and near-empty (F-004)

**Five 0-byte files:** `bare-bones-build.md` · `contributing.md` · `contributors.md` ·
`known-issues.md` · `links.md`
**Two 1-line stubs:** `hardware-introduction.md` · `brick.md`

### mkdocs nav

35 active nav entries against 50 files → **15 docs are not reachable from the nav.**
Six nav lines are explicitly commented out (`mkdocs.yml:23,57,58,60,61,62`):

| Line | Commented-out entry | File LOC |
|---|---|---|
| 23 | Lenses and image circles → `image-circle.md` | **159** — real content, hidden "until manually reviewed" |
| 57 | Bare bones build → `bare-bones-build.md` | 0 |
| 58 | Box build → `brick.md` | 1 |
| 60 | Todo → `todo.md` | 62 |
| 61 | Contributors → `contributors.md` | 0 |
| 62 | Contributing to the project → `contributing.md` | 0 |

`image-circle.md` is the notable one: 159 lines of written documentation that no reader
can reach.

### Coverage-to-surface ratios for S09

- `web-gui.md` — 32 LOC for a 965-LOC template
- `simple-gui.md` — **31 LOC for a 2129-LOC module** (exists; KICKOFF §8 S09 is correct)
- `compiling-cinepi-raw.md` — 15 LOC for a 24k-LOC C++ repo

> **Correction:** an earlier draft of this section listed 30 docs and asserted
> `simple-gui.md` was absent. Both were wrong — an artifact of a truncated `head -30` on
> the file listing. The table above is the complete 50-file inventory.

---

## 10. Test inventory

`_test/` — 34 files.

**27 pytest files:** `test_analog_controls_dispatch` · `test_arrays_free_increment_defaults` ·
`test_camera_log_encode_defaults` · `test_cinepi_controller_resolution_gui` ·
`test_cinepi_controller_startup_sensor_mode` · `test_command_executor_dispatch` ·
`test_dynamic_resolution` · `test_free_mode_steps` · `test_increment_decrement_setting` ·
`test_log_encode_badge` · `test_log_encode_live_control` · `test_parameters` ·
`test_quad_rotary_controller_setting_names` · `test_recovery_console` ·
`test_recovery_jsonc_golden` · `test_resolution_defaults` · `test_sensor_database` ·
`test_settings_jsonc` · `test_shutter_a_nom_get_setting_key` ·
`test_simple_gui_preview_guide` · `test_ssd_monitor_format` · `test_status_broadcast` ·
`test_storage_preroll` · `test_storage_profiles` · `test_web_api_blueprint` ·
`test_web_api_settings` · `test_wifi_hotspot_ladder`

**3 non-test utilities:** `analyze_logs.py` · `automount.py` · `i2c_scan_all.py`

**4 underscore-prefixed (probable dead):** `__gpio_output.py` · `_gpio_output.py` ·
`_mediator.py` · `_wifi_hotspot_service.py`

No `conftest.py`, no `pytest.ini`, no test config of any kind. None of these run in CI
(F-006 — `.github/workflows/` contains only `docs.yml`).

Notably `test_simple_gui_preview_guide.py` already exercises `simple_gui` off-hardware —
**this is a working precedent for the S07 offscreen-render harness** and should be read
first in that session.

---

## 11. cinepi-raw build & patches

Root-level patch files, purpose unresolved:

- `add-redis-timecode.patch`
- `add-tc.patch`

Both names suggest timecode features that may already be merged into the tree. Whether
they are pending, applied, or vestigial is **unverified** — S04.

`cinepi/meson.build` contains two hardcoded placeholder paths that would break a
from-source build if `pkg-config` fails to find hiredis or redis++:

```
cinepi/meson.build   include_directories('/path/to/hiredis/includes')
                     include_directories('/path/to/redis++/includes')
```

These are literal `/path/to/...` strings in the fallback branches. Confirmed present;
whether the fallback branch is ever taken on a real Pi build is **unverified** (PI-005).

---

## 12. What S01 did NOT establish

Recorded so later sessions don't assume coverage that isn't there:

- **Redis key census** — incomplete (§7). S02 owns it.
- **C++ include graph** — not built. S03 owns it.
- **Which settings keys code actually reads** — not traced. S09.
- **Whether `parameters.py` / `rotary_encoder.py` / `timekeeper.py` / `raw_files.py` /
  `boot_config.py` are dead** — no inbound import edge found, but dynamic import not
  ruled out. S04.
- **`cinepi_audio_capture.cpp` and `lj92.c` build inclusion** — absent from the meson
  source list; mechanism unknown. S03.
- **Anything requiring hardware** — see `PI-VERIFICATION-QUEUE.md`.
