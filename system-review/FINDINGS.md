# FINDINGS — append-only index

One line per finding. Detail files live in `findings/F-###.md` where the finding needs
more than three lines. Schema and severity/confidence definitions: `CONVENTIONS.md` §5.1.

**Do not renumber. Do not reuse IDs. Append only.**

| id | severity | confidence | repo | category | summary | evidence |
|---|---|---|---|---|---|---|
| F-001 | medium | confirmed | cinemate | dead-code | Four unreferenced HTML templates, 928 LOC total; no code reference, not copied by installer | `src/module/templates/`, `src/module/app/template.html` |
| F-002 | high | confirmed | cinemate | standards | `requirements.txt` lists stdlib `wave` as a package; duplicates `sugarpie`/`flask_socketio`; lists both `Pillow` and `pillow`; mixes docs-build deps into runtime deps | `requirements.txt:1-22` |
| F-003 | high | confirmed | install | install-drift | `requirements.txt` is never referenced by the installer; the two dep lists have diverged by 11+4 packages; `flask` is never installed directly | `cinemate-install.sh:922-927`, `requirements.txt` |
| F-004 | medium | confirmed | docs | docs-drift | Five 0-byte docs + two 1-line stubs; six commented-out nav lines; 15 of 50 docs unreachable from nav — incl. `image-circle.md` (159 LOC of real content) | `mkdocs.yml:23,57-62`, `deliverables/CENSUS.md` §9 |
| F-005 | high | confirmed | cinemate | standards | No Python lint/format/type config anywhere; cinepi-raw has `.clang-format`, cinemate has nothing | repo root |
| F-006 | high | confirmed | cinemate | test-gap | No CI runs on PRs or on `dev` at all — the sole workflow triggers only on push to `main`, and development happens on `dev`. 27 pytest files never run | `.github/workflows/docs.yml:9-13`, PR #129 (0 checks) |
| F-007 | high | confirmed | cinemate | gui | Colour constants hand-duplicated between `simple_gui.py` Python tuples and `template.html` CSS custom properties, synced only by comment | `simple_gui.py:21-45`, `app/templates/template.html:23-40` |
| F-008 | high | confirmed | cinemate | gui | HDMI GUI lays out from 1920-reference absolute pixel constants, proportionally scaled — not adaptive layout | `simple_gui.py:27-45`, `simple_gui.py:1657-1658` |
| F-009 | low | confirmed | cinemate | structure | `_test/` mixes 27 pytest files with 3 non-test utilities and 4 underscore-prefixed probable-dead files | `_test/` |
| F-010 | medium | confirmed | both | structure | Nine Python modules and four C++ sources exceed 850 LOC; five exceed 1300 | `deliverables/CENSUS.md` §2 |
| F-011 | — | refuted | cinemate | — | **Not reproducible.** KICKOFF §6.4 claimed 8 uncommitted files; working tree is clean and `origin/dev == 02b5a39 == branch base`. See `findings/F-011.md` | `git status` |
| F-012 | low | confirmed | cinepi-raw | dead-code | `cinepi/_mjpegPreviewStage.cpp` (240 LOC) is not in the meson source list and is included by nothing | `cinepi/meson.build:24-34` |
| F-013 | medium | confirmed | cinemate | dead-code | `src/stream.py` is a dead second Flask entry point with a broken import and a wrong-arity `create_app` call | `src/stream.py:2`, `src/module/app/__init__.py:6` |
| F-014 | medium | confirmed | docs | docs-drift | 18 of 84 `ParameterKey` members are absent from `docs/redis-keys.md`; every documented key does exist in code | `redis_controller.py:18-113`, `docs/redis-keys.md` |
| F-015 | medium | confirmed | cinemate | standards | `ParameterKey` is convention, not enforcement — `set_value` accepts any string; 3 live keys bypass the enum, one in SCREAMING_CASE | `redis_controller.py:235`, `ssd_monitor.py:44` |
| F-016 | high | confirmed | both | redundancy | Redis key `audio_vu` is hand-duplicated across the repo boundary — same constant name and value declared independently in C++ and Python | `cinepi_sound.cpp:22`, `simple_gui.py:21` |
| F-017 | medium | confirmed | cinemate | dead-code | `src/module/timekeeper.py` (243 LOC) is entirely dead — `Timekeeper(` appears nowhere in the repo; `main.py` pins `timekeeper = None` | `main.py:658,1026-1027`, `timekeeper.py` |
| F-018 | low | confirmed | cinemate | dead-code | `handle_vu_output()` (main.py:633-644) is dead — its only call site is commented out; contains the commented-out write that makes `vu_meter` a phantom key | `main.py:633-644,743` |
| F-019 | medium | confirmed | cinemate | dead-code | Two write-only Redis keys: `FSCK_STATUS` (3 writes, sole reader commented out) and `user_changing_fps` (sole reader is dead `timekeeper.py`) | `ssd_monitor.py:260,804,816`, `simple_gui.py:2123`, `timekeeper.py:224` |
| F-020 | low | confirmed | cinemate | structure | `simple_gui` reaches through `redis_controller.r` to the raw redis client, bypassing `get_value()` and its cache — a fourth Redis access pattern | `simple_gui.py:1166-1172` |
| F-021 | low | confirmed | cinemate | standards | Bare `set` on its own line in the boot path — a no-op expression statement, the only one in `src/`. Any linter catches this instantly (see F-005) | `main.py:685` |
| F-022 | medium | confirmed | cinemate | dead-code | `RedisController.stop_listener()` is never called; the pub/sub `_listen` thread started in `__init__` has no shutdown path | `redis_controller.py:188,410` |
| F-023 | high | confirmed | cinemate | correctness | `cleanup()` never calls `usb_monitor.stop()` or `ssd_monitor.stop()` although both exist; `redis_listener` (2084 LOC) and `storage_preroll` define no `stop()` at all | `main.py:954-1046`, `usb_monitor.py:528`, `ssd_monitor.py:152` |
| F-024 | low | confirmed | cinemate | structure | The Flask/SocketIO `stream` thread is the only ad-hoc thread in `main.py` not marked `daemon=True`, and cleanup neither stops nor joins it | `main.py:935`, cf. `main.py:467,806` |
