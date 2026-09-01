# Kickoff prompt for the implementing session

Note: **two repos** (cinepi-raw and cinemate), four commits, and a C++ change on the recording hot
path. This is Phase 0 — putting an embedded thumbnail into the DNG — which since the 2026-09-01
direction change is the thing that decides C9: with it, reviewing a take is reading a 720p plane
that already exists; without it, every preview demosaics a raw frame. The pane itself is a
separate, later session ([`SONNET-PROMPT-PANE.md`](SONNET-PROMPT-PANE.md)). Gates G10 and G11 run
on hardware after this lands and belong to the operator, not this thread.

Paste everything below the line into a fresh Sonnet thread.

---

Enable the embedded thumbnail in cinepi-raw's DNG writer, behind a toggle that selects off, mono
or colour, and surface that toggle in CineMate. Then land the one-paragraph
`docs/settings-json.md` correction C9 has been carrying on an unpushed branch.

The plan is at:
`/Users/patrikeriksson/Documents/cinemate/cinemate/dev-track/C9-clip-playback/PLAN.md` — read
**Phase 0** in full, plus [`GATES.md`](GATES.md) beside it for G10 and G11, which are what this
work will be judged by. Both are on branch `feature/c9-clip-playback-plan` (PR #181), or on
`dev` once that merges. Do **not** read the copies on `feature/dev-track`: they predate the
correction pass and contain known-bad commands and a wrong `thumbnail_size` design.

Read the plan before touching anything, and read
`/Users/patrikeriksson/Documents/cinemate/cinemate-handbook/README.md` plus
`orientation/the-traps.md` first. Every fact in Phase 0 was read out of the cinepi-raw source at
`774402c` and carries a file:line — verify each against the tip you actually have, and where the
source and the plan disagree, the source wins: say so, and say where.

Ground rules:

- **Two repos.** `cinepi-raw` (`/Users/patrikeriksson/Documents/cinemate/cinepi-raw`), a branch off
  its `dev`, for C9.0a and C9.0b. `cinemate`
  (`/Users/patrikeriksson/Documents/cinemate/cinemate`), a branch off its `dev`, for C9.0c and
  C9.1. `cd` does not persist between shell calls — use `git -C` and absolute paths.
- **Never `git add -A`** in either repo (LFS pointer trap) — stage named files only.
- Do not merge, do not push without asking, and **do not touch the Pi**. You cannot build
  cinepi-raw here and you are not expected to; the operator builds and runs G10/G11.
- CineMate's settings-editor template is ES5 (`var`, `function(){}`) — match it. It embeds base64
  font data: filter greps with `awk 'length($0) < 250'`.
- The cinemate lint gate is **`ruff check src/`**, never `ruff check .` — the latter reports 146
  pre-existing errors on a clean tree.
- Commit messages: `c9.<n>: <scope> — <one-line outcome>`.

Order matters — C9.1 (the docs fix) first and on its own, because it is correct today, independent
of everything else, and currently exists only on an unpushed branch. Then C9.0b (the one-line bug),
then C9.0a (the writer), then C9.0c (the toggle).

Four places will bite you:

1. **The writer is hand-rolled, not libtiff.** `dng_save()` builds exactly one IFD with
   `IFDBuilder` (`cinepi/ifd_builder.hpp`, 221 lines) and patches its offset into the TIFF header
   at byte 4 (`dng_encoder.cpp:1017-1137`). Upstream `image/dng.cpp:418-462` writes a thumbnail
   with libtiff — it is a **design reference, not code to lift**. `IFDBuilder` needs multi-IFD
   support; it already writes a next-IFD pointer, so the mechanism exists and is unused.
2. **The layout is an open decision, not yours to settle silently** (open decision 7). Thumbnail
   as IFD0 with the raw in a SubIFD is the standard DNG shape and what upstream does deliberately
   — *"put it first to help software that only reads the first IFD"* — but it moves the raw out of
   IFD0, where every existing CineMate DNG has it and where the fallback decoder looks. Chaining
   the thumbnail as IFD1 leaves existing readers untouched. **Implement whichever you judge right,
   but make it a one-line switch and say which you chose and why** — G10 tests both against the
   operator's post software, and the answer may come back the other way.
3. **Off must be a genuine no-op.** `thumbnail=0` has to produce a byte-identical frame to today's
   output. That is G10's control, and this code runs per frame inside the encoder threads on the
   recording path — a bug here does not produce a bad preview, it produces a bad take. Prove it at
   the desk: encode the same input twice, once on `dev` and once on your branch with the toggle
   off, and diff the bytes.
4. **The controls already exist and are inert — give them meaning, do not invent keys.**
   `CONTROL_KEY_THUMBNAIL` / `CONTROL_KEY_THUMBNAIL_SIZE` (`cinepi_state.hpp:39-40`) are read at
   startup into `options_->thumbnail` / `thumbnailSize` (`cinepi_controller.cpp:206-207`) and have
   live pub/sub handlers (`:572-579`), and **nothing reads either option**. Make `thumbnail` the
   mode — **0 off, 1 mono, 2 colour** — and implement `thumbnail_size` as a downscale of the Y
   plane **inside `dng_save()`**. Do *not* reuse `thumbnailFactor`: `rpicam_app.cpp:603` sets
   `alias_lores_to_video = have_raw_stream && have_lores_stream`, CineMate always passes
   `--lores-width`/`--lores-height` (`cinepi_multi.py:492-493`) and always records raw, so the
   `alias_lores_to_video` branch at `:647` always wins and the right-shift at `:659-661` is dead on
   this path — and what it sizes is `configuration_->at(0)`, the stream feeding the HDMI and MJPEG
   previews, so driving it from a playback setting would resize the operator's live preview.
   Note too that the live `CONTROL_KEY_THUMBNAIL_SIZE` handler sets `cameraInit_ = true`
   (`cinepi_controller.cpp:580`) — changing the size restarts the camera, and the verb's help text
   must say so.

C9.0b is one line and has hardware evidence behind it: `cinepi_controller.cpp:137` seeds
`CONTROL_KEY_THUMBNAIL` with `thumbnail_size_` where it means `CONTROL_KEY_THUMBNAIL_SIZE`. That is
why the Pi's redis reads `thumbnail=3` — 3 is `CP_DEF_THUMBNAIL_SIZE`, not `CP_DEF_THUMBNAIL`,
which is 1. Fix it in its own commit so the redis behaviour change is attributable.

The source of the pixels is `lo_cfg` / the lores stream, which already reaches the encoder for
every frame (`cinepi_raw.cpp:215` passes `app.LoresStream()` into `EncodeBuffer`, and `dng_save`
already receives it as `lomem` / `loinfo` / `losize`, all three currently `[[maybe_unused]]`).
CineMate launches with `--lores-width`/`--lores-height` from `sensor_detect._calc_lores()`, which
gives **1272×720** for both UHD and 2K. The five `dng_info.thumb*` fields at
`dng_encoder.cpp:781-785` are already assigned from `lo_cfg` and read by nothing — they are where
your IFD entries should come from.

Done means:

1. The four commits match Phase 0 (deviate only where the plan contradicts current source, and say
   exactly where and why), and you have said which IFD layout you implemented and why.
2. The byte-identical proof for `thumbnail=0`, pasted.
3. A decoded sample: take one frame your branch produces at `thumbnail=1` and one at `2`, and show
   the thumbnail extracted and rendered — dimensions, samples per pixel, bit depth, and the image
   itself. If you cannot run cinepi-raw here, say so and construct the IFD in a unit test instead;
   do not claim a rendered thumbnail you did not see.
4. cinemate side green: `ruff check src/` · `python -m pytest _test/ -q -p no:randomly` ·
   `python3 tools/docs_drift_check.py --repo . --strict` ·
   `python3 tools/gui_field_extract.py --repo . --max-unresolved 0`. If the toggle adds a
   settings.jsonc key, nest it under an existing top-level section — a **new** top-level block
   breaks the schema test across three shipped config files and the gated docs `settings` check at
   once.
5. A closing summary listing files touched per commit, the layout decision, and the exact manual Pi
   commands for the operator's Session E — including the **cinepi-raw rebuild**, which is what
   makes this different from every previous C9 step, and G10's and G11's predictions written out so
   pass/fail can be recorded against them.

Stop after that summary. Do not start a Pi session, do not run hardware gates, do not merge. Stop
and ask if a plan assumption fails — in particular, if `IFDBuilder` turns out not to support a
second IFD without a larger change than Phase 0 describes, stop and tell me rather than
restructuring the writer on your own judgement.
