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
| F-006 | high | confirmed | cinemate | test-gap | CI contains only `docs.yml`; 27 pytest files in `_test/` never run automatically | `.github/workflows/docs.yml`, `_test/` |
| F-007 | high | confirmed | cinemate | gui | Colour constants hand-duplicated between `simple_gui.py` Python tuples and `template.html` CSS custom properties, synced only by comment | `simple_gui.py:21-45`, `app/templates/template.html:23-40` |
| F-008 | high | confirmed | cinemate | gui | HDMI GUI lays out from 1920-reference absolute pixel constants, proportionally scaled — not adaptive layout | `simple_gui.py:27-45`, `simple_gui.py:1657-1658` |
| F-009 | low | confirmed | cinemate | structure | `_test/` mixes 27 pytest files with 3 non-test utilities and 4 underscore-prefixed probable-dead files | `_test/` |
| F-010 | medium | confirmed | both | structure | Nine Python modules and four C++ sources exceed 850 LOC; five exceed 1300 | `deliverables/CENSUS.md` §2 |
| F-011 | — | refuted | cinemate | — | **Not reproducible.** KICKOFF §6.4 claimed 8 uncommitted files; working tree is clean and `origin/dev == 02b5a39 == branch base`. See `findings/F-011.md` | `git status` |
| F-012 | low | confirmed | cinepi-raw | dead-code | `cinepi/_mjpegPreviewStage.cpp` (240 LOC) is not in the meson source list and is included by nothing | `cinepi/meson.build:24-34` |
| F-013 | medium | confirmed | cinemate | dead-code | `src/stream.py` is a dead second Flask entry point with a broken import and a wrong-arity `create_app` call | `src/stream.py:2`, `src/module/app/__init__.py:6` |
