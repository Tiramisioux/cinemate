# C9 · Clip playback — review takes on the camera

Play a recorded take back in the web GUI, at the speed it will run in post, without taking the
card out. Explored and prototyped 2026-08-27 (Fable session) against `dev` tip `714ef7b4`.

This is a **project, not a patch**: the first increment is written and desk-verified, but the
question that decides how far it can go — how fast the Pi decodes, and how fast it can read the
card — has not been measured on hardware. The phases below are ordered so that measurement comes
before any further build.

!!! note "Status 2026-09-01 — the code is written, unlanded and now six days stale; the plan has been re-grounded against the repo"
    A grounding pass read every checkable claim in this plan against `feature/dev-track`
    (`e759f2f`) and `origin/dev` (`c0eb9ff7`). Nine claims were wrong or overstated and are
    corrected in place below. The three that change what happens next:

    | | |
    |---|---|
    | Not done | The `docs/settings-json.md` correction this plan recorded as **done** exists only on the unpushed Mac branch. `b7e5eb43` is not an object in any pushed history and the stale sentence is still live on `dev` at `docs/settings-json.md:214`. It is **outstanding work that must travel with C9**, and it is currently the single most losable artifact of this step |
    | Not established | Whether `dng_preview.py` applies the `LinearizationTable`. `docs/cinemate-log.md:63` names the failure it causes — a log clip renders **solid black** — and no gate as filed looks at a rendered pixel. G9 now does |
    | Refuted | "Reserving 2 of the Pi's 4 cores" is not a budget C9 can claim. The installer isolates core 3, `cinepi-raw` runs `chrt -f 70` + `taskset -c 1-3`, and audio capture holds SCHED_FIFO 80 on core 3. Nothing in C9 reserves anything, and no mechanism exists to. See "What the Pi actually offers" |

    Also: the branch's base is now **1381 commits** behind `dev`, through the files C9 edits
    (`settings_editor.html` alone moved 98 lines, including PR #160's doctype/viewport fix that
    this branch's copy predates). It must be rebased before "556 tests, checks green" means
    anything. Gates moved out to [`GATES.md`](GATES.md), where they carry predictions stated in
    advance; G0 and G9 are new, G1–G8 keep the numbers they were filed under.

!!! note "Direction changed 2026-09-01 — thumbnail-first, with the raw decoder as the fallback"
    Operator steer: *"I am not expecting playback of raw files. I am thinking that the system can
    use the thumbnails instead."* Checked against `cinepi-raw` @ `774402c` rather than assumed —
    the answer is that the thumbnail does not exist yet, but nearly everything needed to make one
    does, and it is a far better basis for this feature than decoding raw.

    | | |
    |---|---|
    | There is no thumbnail today | `dng_encoder.cpp:781-785` assigns `thumbWidth`/`thumbHeight`/`thumbSamplesPerPixel`/`thumbBitsPerSample`/`thumbPhotometric` into `dng_info`, and **nothing reads them** — no TIFF tag is emitted from any of the five. The lores buffer reaches `dng_save` as `lomem`/`loinfo`/`losize`, all three marked `[[maybe_unused]]`. The encoder says so itself at `:842`: "DNG writer: raw-only frames; embedded lores thumbnail disabled" |
    | The frame is already there | `cinepi_raw.cpp:215` passes `app.LoresStream()` into `EncodeBuffer` on every frame — the same lores stream that already feeds the HDMI preview and the MJPEG stream. Nothing new has to be produced, only written |
    | It is already the right size | CineMate launches with `--lores-width`/`--lores-height` from `sensor_detect._calc_lores()`, which caps height at 720 and preserves aspect: **1272×720** for both UHD and 2K. That is *larger* than the 964×545 the raw path strains to produce at 1/4 |
    | The cost collapses | An 8-bit mono 1272×720 plane is ~0.92 MB. At 25 fps that is **~23 MB/s**, against 158 MB/s for the raw path at 1/4 — and no demosaic, no `LinearizationTable`, no bit-unpacking, so the black-log-clip failure (G9) cannot happen on this path at all |

    **So C9 becomes thumbnail-first with the raw decoder retained as the fallback** (operator
    decision, 2026-09-01), which keeps every take reviewable: the thumbnail only ever exists in
    footage shot after the cinepi-raw change lands. Mono and colour both ship, behind a toggle
    (operator decision, same day).

    What that costs, and none of it is free: C9 stops being a cinemate-only Python step and
    becomes a **two-repo step** like C2 and C7, with a cinepi-raw build on the Pi. And the
    writer is hand-rolled — `IFDBuilder` (`ifd_builder.hpp`, 221 lines) emits exactly **one** IFD
    and patches its offset into the header at byte 4 — so this is not a flag flip. See Phase 0.

## Why the raw fallback is possible at all

The decoder stays, because a thumbnail only ever exists in takes shot after Phase 0 lands.
Three properties of what `dng_encoder.cpp` writes, all confirmed against real frames (the six
imx585 mode-matrix samples, a real UHD imx585 still, and a genuine 50-frame imx477 take):

| Property | Consequence |
|---|---|
| The IFD is at the **tail**, with its offset in the 8-byte header | A take's metadata costs ~2 kB to read on a linear take — ~9 kB where a `LinearizationTable` rides along — measured **0.03 ms**. Cheap enough that the clip list can show real frame rates and resolutions without touching pixel data. It is **not** the cost of indexing a card: see the enumeration caveat below |
| One **uncompressed, row-addressable** strip (`StripOffsets == 8`, `RowsPerStrip ==` height) | A downscaled preview unpacks only the rows it needs. Corroborated in-repo, twice: `raw_files.py:165-171` ("`dng_encoder.cpp` hardcodes `COMPRESSION_NONE`") and `sensor_detect.py:40-44`, whose `DNG_COMPRESSION_RATIO = 1.0` names itself the seam to update if that ever changes. **If that constant moves off 1.0, row-addressable decode is dead** — treat it as C9's canary |
| No embedded thumbnail or preview IFD (the writer logs "raw-only frames") | Every preview must demosaic **and apply the `LinearizationTable` where one is present**. There is no shortcut, which is why the decoder had to be proven before anything else — and why skipping the table is not a quality compromise but a black frame (`docs/cinemate-log.md:63`) |

And one that decides the architecture: numpy and Pillow both release the GIL, so a plain
`ThreadPoolExecutor` scales nearly linearly (3.1× on 4 workers). No multiprocessing needed. This
holds only because the app is served by the threaded Werkzeug server — `src/main.py:937` passes
`allow_unsafe_werkzeug=True` and no `async_mode` is set (`app/__init__.py:14`), and neither
eventlet nor gevent is a dependency, so requests are real OS threads. Under a monkey-patched
async server the same code would serialise.

**What is *not* free: enumerating the card.** `raw_files._take_info()` does one `iterdir()` with a
`stat()` per entry, i.e. thousands of `stat()` calls per take. The clip index is dominated by
filesystem metadata, not by 2 kB tail reads, and that cost is filesystem-dependent — which G2 now
measures alongside bandwidth.

## Measured, on an Apple Silicon Mac — **not** on the Pi

| Mode | Scale | Output | Decode | I/O per frame | Read rate @ 25 fps |
|---|---|---|---|---|---|
| UHD 3856×2180 12-bit | 1/2 | 1928×1090 | 38.4 ms | 12.6 MB | 315 MB/s |
| | **1/4** | **964×545** | **13.9 ms** | **6.3 MB** | **158 MB/s** |
| | 1/8 | 482×272 | 5.3 ms | 3.2 MB | 79 MB/s |
| UHD 16-bit ClearHDR | 1/4 | 964×545 | 10.5 ms | 8.4 MB | 210 MB/s |
| 2K 1928×1090 12-bit | 1/2 | 964×545 | 9.3 ms | 3.2 MB | 79 MB/s |

Threaded, UHD at 1/4: 12.4 ms (1 worker) → 6.7 ms (2) → 3.9 ms (4).

Three things this table does **not** say, all of which it was read as saying:

- **Cost falls with output size but does not track it.** Two rows produce the same 964×545 output
  and differ by 1.49× in decode and 1.97× in I/O. And at scale 1/2 the 12.6 MB read *is* the whole
  frame (3856×2180×12/8 = 12,607,440 B), so nothing is saved on I/O at that scale at all.
- **13.9 ms and 12.4 ms are the same work measured twice**, 11% apart, and were never reconciled.
  Every derived number depends on which is the baseline. The G1 harness must pick one and say so.
- **The I/O column is bytes the decoder consumes, not bytes the drive moves.** Nothing in this
  stack tunes `read_ahead_kb`, so a ~5.8 kB row stride under the 128 kB default readahead may
  transfer the whole file whatever the scale. If it does, UHD at 1/4 needs **315 MB/s, not 158**.
  G2 measures device bytes, not `dd`, precisely because this is the cheapest measurement that can
  invalidate the plan's central storage claim.

**The headline claim to test, restated as a function of the timebase:** at 964×545 for UHD
footage, against the 6.7 ms 2-worker figure, the Pi may be **6.22× slower per core at a 24 fps
conform, 5.97× at 25, 4.97× at 30** and still hold the rate. The plan's original "~6×" is 5.97×,
so a Pi exactly 6× slower *fails* its own gate. And the budget is whole-frame wall clock while
6.7 ms is decode only — JPEG encode, Flask and the network are unbudgeted inside it.

**The likely binding limit is storage, not CPU.** 158 MB/s for UHD at 1/4 is fine on NVMe,
marginal on a USB SATA SSD, out of reach on SD — but on USB SATA the binding constraint is not
raw MB/s: `storage_profiles.py:147-153` records that a shared xHCI controller congests and stalls
ALSA capture, which is why disk workers are capped on Pi 4 and not on Pi 5. A USB SATA SSD on a
CM5 shares that bus with the USB mic exactly as a Pi 4 does; NVMe over PCIe does not. The dev Pi
has **only** NVMe, so the USB-SATA and SD rows of that ordering are not testable on this rig at
all. Delivery over the hotspot is *not* a constraint: a real-scene frame at 964×545 q80 is ~32 kB,
i.e. 6.4 Mbit/s at 25 fps.

## What the Pi actually offers

The plan's original CPU premise was a reservation. There is none, and the shape of what is really
available changes G1's method rather than its verdict:

| | |
|---|---|
| Core 3 | Removed from the schedulable set at boot on a 4-core board — `cinemate-install.sh:1200-1211` appends `isolcpus=managed_irq,domain,3`, `nohz_full=3`, `rcu_nocbs=3`, `irqaffinity=0-2` — and held by `cinepi-audio-capture` at SCHED_FIFO 80 **while recording**. `storage_profiles.py:41-49` states the invariant: no worker affinity may include it |
| `cinepi-raw` | Launched `chrt -f 70` + `ionice -c2 -n0` + `taskset -c 1-3` (`cinepi_multi.py:243-249`). SCHED_FIFO 70 preempts the Flask process unconditionally |
| The decode pool | SCHED_OTHER, unpinned, in the same process as the HDMI GUI's redraw loop and the Socket.IO push. Measured at rest: cinemate 6.3% CPU idle, **31.8→33.5% during a take** (PI-016) |

So: while **not** recording, two cores are genuinely free and the headline claim stands. While
recording, there are none — which is a far sharper reason to refuse playback mid-take than
storage contention, and the reason any future decode-pool affinity must stay within cores 0–2.

## Two facts the DNG does not record

**There is no HDR tag.** Not in the DNG, not in the WAV's iXML (which carries only
`CINEPI_AUDIO_START_OFFSET_*` and `CINEPI_TIMECODE_SOURCE`). It is recoverable because under a
`LinearizationTable` the level tags describe the table's linear *output*: **`WhiteLevel > 4095`
means HDR-range data.** Verified across the three non-log modes the encoder emits —

| BitsPerSample | LinearizationTable | WhiteLevel | BlackLevel | Mode |
|---|---|---|---|---|
| 12 | absent | 4095 | 200 | SDR 12-bit linear |
| 16 | absent | 65535 | 3200 | ClearHDR 16-bit linear |
| 12 | present | 62704 / 63265 | 200 | ClearHDR 12-bit companded |

The 16-bit and 12-bit level pairs are independently corroborated by `docs/clear-hdr.md:3` and
`docs/cinemate-log.md:67`, so only the companded row needs re-verification on hardware. **The
10-bit log output is untested** — `log_encode` targets 10 on every 12-bit mode and 10-or-12 over
ClearHDR 16-bit — which is what G7 exists for. The good news is that the rule survives it:
`docs/cinemate-log.md:67` records that a log-encoded 12-bit SDR source still tags 4095.

What is **not** recoverable is *which curve* a table holds: the CCMP decompand and the CineMate
Log curve share tag 0xC618 and compose into one table when log runs over 12-bit ClearHDR. The UI
therefore badges `CRV` ("a curve is baked in"), never `LOG`. Do not add a `LOG` badge later
without a new signal on disk to justify it.

**Mono is undetectable *from the file*.** Confirmed in source, and worse than the plan said: `mono_`
exists **twice** — a file-scope global at `dng_encoder.cpp:129` (`bool mono_ = false;`, comment "add
as a private member of DngEncoder") shadowing the real member at `dng_encoder.hpp:137` — and neither
is ever assigned, while `mono_formats` at `:124` is deliberately empty. So `phot = mono_ ? PHOTOMETRIC_MINISBLACK : PHOTOMETRIC_CFA` (`:1024`) always takes the CFA branch and every frame carries a
colour CFA even on the mono rig, so demosaicing mono footage through a Bayer pattern produces a
convincing wrong image. It must stay an operator toggle. But the *running system* knows:
`sensor_detect.py:251-256` appends `_mono` when `--list-cameras` reports it, `boot_config.py:35`
carries `imx585_mono` as a distinct model, and the model reaches redis as `sensor`. So the toggle
gets a correct **default** from `redis SENSOR.endswith('_mono')` — labelled as a default, since it
describes the camera you are sitting at, not the one that shot the take.

## Playback speed follows the conform rate

`settings.conform_frame_rate` is the timebase, not the take's recorded rate. A 50 fps take on a
25 fps conform plays at **half speed**, because that is what it will do on the timeline. A toggle
turns it off to watch a take as shot.

This makes C9 the first consumer of that setting **outside the recording timecode tracker** —
which is itself a real, operator-visible consumer (`redis_controller.py:396-411` writes
`RECORDING_TIME`, `RECORDING_TC_REC` and `RECORDING_TC_TOD` from it, and
`web_api_settings.py:22-23` broadcasts one of them). `docs/settings-json.md` says the setting is
"not really used by CineMate except for calculating the recording timecode tracker in redis but
might be used in future updates". **That sentence is still live on `dev` at line 214.** The
correction, and the two undocumented facts it also records — that the timecode base is rounded to
a whole number, and that the setting has no effect on capture at all — exist only on the unpushed
branch. Land them first, as their own commit; they are the one part of C9 that is already correct.

Three consequences worth not rediscovering:

- **Speed ramps replay correctly with no rate logic at all.** In conform mode playback is one
  frame per conform tick, whatever the sensor was doing frame to frame. Since `FrameRate` (51044)
  is written on *every* frame, a ramped take carries its own ramp. Note what the tag is: the
  **requested** rate, written as `round(fps × 1000) / 1000` and deliberately not the sensor's
  achieved rate (`C1-longtake-stability/VERIFICATION-2026-08-26.md:383-385`). Fine for replaying a
  ramp; never present it as a record of what the sensor did.
- **Conforming a high-rate take makes it cheaper**, since cost tracks frames displayed per second.
- **The pane must not do its own SMPTE base rounding.** `redis_controller.py:363-364` rounds with
  Python's banker's rule, and F-253 already records four sites with three different rules. A fifth
  would be a new instance of a confirmed finding. The pane needs a tick *interval*, not a base.

Caveat: `conform_frame_rate` is a known multi-source drift (F-251) — and there are **six** sites,
not four: `settings.schema.json:200` and `config_loader.py:218` and `redis_controller.py:174` and
`main.py:604` all say 24; `settings.jsonc:118` and `resources/settings/settings_default.jsonc:50`
say 25; and the settings tab's `#f-conform` field shows the operator `data-original="25"` (`:1370` on `dev`). The pane reads
the live value and displays it; it must not restate a default. **Name the source:** the value in
effect is `current_app.config['SETTINGS']['settings']['conform_frame_rate']` — the same dict
`main.py:604` constructed `RedisController` from, i.e. the *running* value, which diverges from
the file whenever settings.jsonc was edited without a restart. Reading the file instead would show
an edited-but-unapplied rate, which is exactly the drift the pane exists not to restate. Say
"running value" in the HUD. And clamp: the schema permits `0`, which reaches `1 / rate`.

## Phase 0 — enable the thumbnail in cinepi-raw

New, and now the first thing that happens. Everything else in C9 improves once this lands, and
nothing else in C9 depends on it — the pane works without it, more slowly and only in colour.

**The change.** `dng_save()` builds one IFD with `IFDBuilder` and patches its offset into the TIFF
header (`dng_encoder.cpp:1017-1137`). The thumbnail needs a second IFD carrying the lores plane,
which means `IFDBuilder` grows multi-IFD support — it currently writes one directory and a
next-IFD pointer, so the mechanism is there but unused.

**Layout is a real decision, not a detail.** Upstream `image/dng.cpp:418-462` puts the thumbnail
in IFD0 with the raw in a SubIFD, and says why in its own comment: *"put it first to help software
that only reads the first IFD"*. That is the standard DNG shape and the one post tools expect —
but it **moves the raw image out of IFD0**, which is where every existing CineMate DNG has it and
where `dng_preview.py`, the fallback decoder, currently looks. Chaining the thumbnail as IFD1
instead leaves existing readers untouched and is invisible to tools that stop at IFD0. Decide it
against what the operator's post software does, not from the spec alone (open decision 7), and
note that upstream's writer is **libtiff** while cinepi-raw's is hand-rolled — it is a design
reference, not code to lift.

**The controls already exist and are inert.** `CONTROL_KEY_THUMBNAIL` and
`CONTROL_KEY_THUMBNAIL_SIZE` (`cinepi_state.hpp:39-40`) are read at startup, pushed into
`options_->thumbnail`/`thumbnailSize` (`cinepi_controller.cpp:206-207`), have live pub/sub
handlers (`:572-579`) — and **nothing reads either option**. PI-008 found them resident on the Pi
with real-looking values (`thumbnail=3`, `thumbnail_size=50`), which is why F-027 flagged them as
possibly "a feature someone wants and never finished". This is that feature.

Give them meaning rather than inventing keys: `thumbnail` becomes the mode — **0 off, 1 mono,
2 colour** — which is the toggle the operator asked for, and `thumbnail_size` stays the size knob,
matching the right-shift `thumbnailFactor` already threaded through
`RPiCamApp::ConfigureVideo(flags, thumbnailFactor)` (`rpicam_app.cpp:597,659-661`), which
`cinepi_raw.cpp:71` passes as 0 today.

**One bug to fix on the way past.** `cinepi_controller.cpp:137` seeds `CONTROL_KEY_THUMBNAIL` with
`thumbnail_size_` where it means `CONTROL_KEY_THUMBNAIL_SIZE`. That is why the Pi reads
`thumbnail=3`: 3 is `CP_DEF_THUMBNAIL_SIZE`, not `CP_DEF_THUMBNAIL`, which is 1. One line, and it
has hardware evidence behind it.

| | |
|---|---|
| Repo | `cinepi-raw`, branch off `dev` — plus a matching cinemate commit for the toggle's settings key, CLI verb and settings-editor control |
| Deploy | A cinepi-raw **rebuild** on the Pi, not a Python restart. This is what makes C9 a two-repo step |
| Write cost | ~0.92 MB/frame mono at 1272×720, ~2.7 MB colour — about +7% and +22% on a UHD 12-bit frame, on the *write* path during recording, which is the contended one. G10 measures it |
| Reach | New takes only. Everything already on a card decodes through the fallback |

## Phase 1 — the pane (written, desk-verified, **not landed**)

Branch `feature/clip-playback` off `dev` @ `714ef7b4`. Two commits, **not pushed**. Written as a
raw-decoding pane; it becomes the **fallback half** of a thumbnail-first pane, which is an
addition to it rather than a rewrite of it — the clip index, the player, the HUD, the conform
logic, the 409 lockout and the cache scheme are all indifferent to where the pixels came from.
What changes is one branch in the frame route: serve the embedded thumbnail when the take has
one, decode when it does not, and **say which in the HUD** — an operator must never wonder
whether they are looking at a 720p mono proxy or a demosaiced quarter-res frame.

| Path | What |
|---|---|
| `src/module/app/dng_preview.py` | The decoder: metadata read, mode inference, row-limited and row-selective decode to JPEG. numpy + Pillow + stdlib only — no rawpy, no libraw, no exiftool subprocess |
| `src/module/app/playback.py` | Clip indexing and frame serving. Directory scans cached against take mtime; concurrent decodes capped and **refused** past the cap rather than queued |
| `src/module/app/settings_editor.py` | Three endpoints under `/settings-editor/api/playback/` — clip index (also reports `conform_frame_rate` and recording state), one frame, the WAV |
| `src/module/app/templates/settings_editor.html` | The **fifth page tab**, the player, the clip HUD and the playback settings |
| `_test/test_dng_preview.py` | 9 tests pinning the scale semantics and the HDR inference against synthesised DNGs |

The dependency constraint costs nothing and is load-bearing rather than stylistic: numpy and
Pillow are already unconditional runtime dependencies (`requirements.txt`, imported on
`main.py`'s own boot path) and already land on every camera (`cinemate-install.sh:970`) — but
**`cinemate-update.sh` never re-runs pip**, it only runs `make install`, which installs systemd
units. Any pip dependency C9 ever adds breaks every deployed camera on update with an ImportError
and no diagnostic. `ffmpeg` *is* already installed (`cinemate-install.sh:527`), so Phase 4's
rejection of the proxy path rests on cost alone, not on tooling.

Placement follows the handbook's state model: a playback pane is **file-backed**, which puts it
with the settings editor — surface 3 — not in `populate_values()`/Socket.IO. Frame serving is
*data*, so plain Flask routes are correct; any future *action* the pane grows must route through
`POST /api/v1/cmd` like everything else.

Verified end to end through the **real** blueprint via `development/playback-pane/harness.py`
(:8798) — which stubs redis, redirects `/media/RAW` to a fake card built from a genuine 50-frame
imx477 take plus symlinked UHD SDR and UHD ClearHDR takes, and exposes a recording toggle.
Confirmed: mode inference on real tags, per-take scale sizes, the 409 recording lockout and
recovery, the 503 back-off, and that the other four tabs still behave. ruff clean, 556 tests,
design-token / GUI-field / docs-drift checks green.

**What that verification does not prove**, and the plan should not have implied it did:

- `ruff clean` means `ruff check src/` — CI runs nothing else, and `_test/` carries 11
  pre-existing violations, so the new test file is not linted at all.
- "556 tests" reconciles exactly (547 collected at `714ef7b4` + 9), but it is a number about a
  base that is now 1381 commits stale. Post-rebase the figure is ~697, and 556 is not an
  acceptance criterion.
- "design-token check green" proves nothing here: `tools/design_token_diff.py:39-40` reads
  `template.html` only and never opens `settings_editor.html`. Neither does `gui_field_extract.py`
  beyond its action-catalogue regex. **The fifth tab therefore lands with no drift check of any
  kind** — against ADR-001's standing rule that no GUI step lands without its check landing on the
  same commit. C9 owes that check (C9.4 below).
- "docs-drift green" cannot speak to the `conform_frame_rate` sentence: `docs_drift_check.py`
  says so itself — a name in prose is not proof it is documented correctly.

### Two bugs that only appeared once it ran

Recorded because both failed *silently* — neither raised anything:

| Bug | Why it mattered |
|---|---|
| **`scale` was incoherent.** Collapsing a 2×2 Bayer cell already halves both dimensions, so `scale=4` produced half width, not a quarter — every size label in the UI was one step off | A wrong preview size does not throw, it just looks plausible. Now a plain linear divisor, with per-take pixel sizes on each option, pinned by a test that fails on the old behaviour |
| **`immutable` caching was wrong across an update.** A frame is a pure function of (take, index, scale, mono) and takes never change — but it is *not* a pure function of the decoder | After a cinemate update the browser would serve frames rendered by the old code for the rest of the cache lifetime. Fixed with a render token derived from `dng_preview.py`'s own mtime, mixed into the frame URL. Caught in the browser, where changing scale kept returning the previous size |

Note there is **no cache-control precedent anywhere in this codebase** — a repo-wide grep for
`Cache-Control`/`max_age`/`etag`/`immutable` over `src/` returns nothing, and the take-download
route is a bare `send_file`. The render token is the only mechanism; there is no ETag machinery
behind it.

### Six defects the re-grounding found, to fix on the rebase

None of these were visible in the harness. Each is one line to a few lines, and each is the kind
of thing that reads as working:

1. **`syncTopbarForPage` will offer Save / Revert / Upload / Download on the playback tab.**
   `syncTopbarForPage()` reads `var noFilePage = activePage === 'live' || activePage === 'raw';` (`settings_editor.html:4574` on `dev` @ `c0eb9ff7` — grep the symbol, the line moves)
   — a `playback` page falls through as a *file* page and claims to edit settings.jsonc.
2. **`playback.py` must not re-scan directories.** `raw_files.py` already has `_media_roots()`,
   `_is_take_dir()`, `_take_info()`, `list_takes()` (mtime-sorted, `has_wav` per take) and a
   traversal-hardened `resolve_take()`. This repo has already shipped the failure of duplicating a
   settings-editor catalogue — three copies that agree perfectly, including on the same wrong
   entry (F-218/219/220). Extend the one enumerator; do not build a second.
3. **Take mtime is not a sufficient cache key.** `storage-automount` promotes a standby with
   `mount --move`, so a take's path changes from `/media/RAW1/<take>` to `/media/RAW/<take>`
   without its mtime moving. Key on resolved path *and* mtime, and re-resolve per request.
4. **`"value"` is a reserved key in `settings_editor.py`.** `tools/gui_field_extract.py:190` and
   `_test/test_action_catalogues_agree.py:42` both regex `"value":\s*"([a-z0-9_]+)"` over the whole
   file and treat every hit as an offered controller action. A scale-option list written as
   `{"value": "quarter"}` fails CI twice, with a message pointing at the JS catalogue. Use `id`,
   `divisor` or `scale`, or keep option lists in `playback.py`.
5. **The Live tab's MJPEG stream never stops.** the template embeds `<iframe id="liveEmbedFrame" … src="/">` (`:2226` on `dev`) and nothing
   ever clears its `src` — `setActivePage` only hides it. Once the
   operator has visited Live view, playback competes with a live MJPEG stream on the same Wi-Fi
   link for the rest of the session, which is most of G6's margin. Clear the src on leave, restore
   on entry.
6. **The 409 is edge-driven, not live.** This page has no polling loop and no Socket.IO — the pane
   learns the recording state only from what it last fetched. Gate the refusal on
   `IS_RECORDING or IS_WRITING_BUF or IS_BUFFERING or STORAGE_PREROLL_ACTIVE` (the flush window and
   pre-roll are exactly the contention windows the lockout is for), check `listener_alive()` before
   trusting a "not recording" answer, and return `{"ok": false, "message": …}` in the body — the
   pane's fetch idiom reads `res.ok` from JSON and ignores the HTTP status entirely.

## Phase 2 — hardware gates (none run; `cinepi.local` was unreachable)

**Full gate definitions, with predictions stated in advance: [`GATES.md`](GATES.md)** in this
directory. Ten gates grouped into four sessions, because four of them cannot run against the dev
Pi as last recorded without a hardware change first.

| Gate | Tests | Session |
|---|---|---|
| **G0** | Baseline and preconditions — board, RAM, kernel, sensor, filesystem, PCIe link, numpy and werkzeug versions, both repo tips | A |
| **G1** | Decode throughput, isolated **and** with CineMate running | A, re-run in B on fresh UHD takes |
| **G2** | Storage read bandwidth — sequential ceiling *and* device bytes per decoded frame, per filesystem | C (destructive) |
| **G3** | Flask streaming under load: client fps, Socket.IO round-trip, HDMI GUI cadence | A |
| **G4** | Playback during recording — silence-fill lines, frames written, thread placement | C |
| **G5** | Memory headroom, and what the ring leaves behind for the next take | A (4 GB), D if a 2 GB board appears |
| **G6** | Hotspot throughput with the MJPEG stream running | A |
| **G7** | Mode inference on fresh takes, including a log take | B |
| **G8** | CFA orientation under flips | B |
| **G9** | **Rendered-pixel correctness** — the `LinearizationTable` is actually applied | B |
| **G10** | **The thumbnail lands** — present, right size, readable by the pane *and* by the operator's post software | E (after Phase 0) |
| **G11** | **What the thumbnail costs to write** — frames written and audio, mono and colour, against a control take | E |

The order of what gates what has changed with the direction. **G10 and G11 now decide the
feature**: if the thumbnail lands and is cheap, playback is a solved problem and the pane's
default path never demosaics anything. G1 and G2 drop from go/no-go to **fallback-quality gates**
— they decide how well older footage reviews, not whether C9 works. G9 likewise only ever applies
to the fallback path; a thumbnail cannot render black, because there is no table to skip.

## Phase 3 — after the gates

Not started. The design is deliberately not fixed before G1/G2 report — but the **rules** that
will fix it are, so the answers are read off the measurements rather than argued afterwards:

- **Default scale — fallback path only.** The thumbnail has one size, so this is now a question
  about older footage alone. Set it to the largest scale whose G1 decode time is ≤ `1000 /
  conform_frame_rate` ms at 2 workers **and** whose G2 device-bytes figure is ≤ 70% of the
  measured sequential ceiling. If no scale satisfies both for UHD, UHD defaults to scrub-only and
  2K keeps a real-time default — the pane already shows the achieved rate and the skip count, so
  it degrades honestly either way.
- **Decode-ahead** — a bounded prefetch ring, sized in **frames** with a comment naming the
  worst-case frame size, evicting the oldest and never blocking the decode worker, in the shape of
  `logger.py`'s bounded queue and pinned by a test in the shape of `test_log_queue_is_bounded.py`.
  Expose the cap the way `api.py:186-192` exposes `max_sse_clients`, not as a bare literal. **The
  ring must be released on tab-leave and when `is_recording` goes 1** — a retained ring raises the
  RSS the next take starts from, and the 80% guard fires 0.25 s into that take with no way to
  attribute it to playback. Build it only if G1 shows decode, not I/O, is the binding limit.
- **Playback-while-recording** — refuse (current behaviour) or degrade to metadata-only, per G4.
  Note the asymmetry: *refuse* keeps the decode ring and the RAM guard permanently disjoint;
  *degrade* makes the playback pane able to auto-stop a take, which is the failure an operator
  would least forgive.
- **A `docs/` page.** There is **no documentation of the settings editor at all** today — a grep
  for `settings.editor|settings_editor|/settings-editor` across `docs/`, `mkdocs.yml` and
  `README.md` returns nothing, so C0's shipped format-drive feature is undocumented too. Decide
  deliberately: a `docs/settings-editor.md` covering the surface with a playback section, or a
  playback-only page. Either way it goes in `mkdocs.yml`'s "Using the camera" group — the `nav`
  drift check is a ratchet, so **nothing will fail if the nav line is forgotten**; and it must land
  in the same commit as the code or later, because the gated `cites` check requires every
  backticked `path.py` to exist and every `:NNN` to be in range.
- **Reachability** — whether the shooting screen gets a REVIEW button deep-linking to the last
  take. It cannot mean the HDMI GUI: `simple_gui.py` is a PIL renderer to `/dev/fb0` with no input
  path of any kind. It means `template.html`'s `#button-row`, where a fifth button wraps rather
  than overflows. Cheaper than the plan implied in one way — it is *navigation*, not an action, so
  no controller method, no `/api/v1/cmd` verb, no `methods` drift entry — and dearer in another:
  the settings editor has no URL routing at all (`var activePage = 'settings'`, no hash, no query
  param), so a deep link needs a small `location.hash` reader first. Resolve "the last take"
  server-side from `raw_files.list_takes()` (already mtime-sorted) rather than passing an id: the
  browser's `clip_name` cannot be turned into a take directory, because `_format_last_dng` strips
  the `_cam0`/`_cam1` the directory *has* and keeps the frame counter it *has not*
  (`simple_gui.py:1194-1224`). Operator decision, and it is the first link of any kind from
  surface 2 into surface 3's URL space — state that trade rather than treating the button as free.
- **Persistence.** If the pane's preferences are stored, nest them under the existing `settings`
  block beside `conform_frame_rate`. A **new top-level block in `settings.jsonc` breaks three
  things at once** (verified by experiment): the schema test across three shipped config files
  (`additionalProperties: false` at the root), and the gated docs `settings` check, which demands a
  matching `##` heading in `settings-json.md`.

## Phase 4 — audio, and the path deliberately not taken

**Audio is not played.** The pane serves the take's WAV at
`/settings-editor/api/playback/clips/<take>/audio`, but nothing in the UI consumes it — there is
no `<audio>` element and no audio control. (The standalone mockup had a "Play audio" toggle; the
integrated pane does not, and the docs must not promise one.) Deciding what audio should do is
part of this phase, not something already answered.

Four facts the decision has to survive, none of them in the original plan:

- **The offset is ~5 frames, not ~1.** The only measurement in this repo is
  `audio start offset +0.192830s (5 frames, 9256 samples)` (PI-VERIFICATION-QUEUE.md:401-403).
  At 25 fps that is a visible lip-sync error from frame one, not a rounding detail — which makes
  applying it worthwhile even in the cheap option, and makes an unlabelled free-run indefensible.
- **Nothing server-side can fix it.** `audio_capture.{24bit,16bit}.timecode_offset_frames` shifts
  only the embedded BWF/iXML timecode; the PCM is never moved (`docs/audio-sync.md:19`). The pane
  would have to apply the shift itself in `audio.currentTime`.
- **The WAV shape varies per take.** 24-bit `S24_3LE` stereo or 16-bit `S16_LE` mono, 48 kHz
  (`usb_monitor.py:322-345`), and the packed-3-byte 24-bit case is the less universally supported
  in browsers. Read the format from the take's own header — the live mic probe describes the mic
  attached now, not the one that shot the take.
- **A hard-aborted take leaves an unfinalised WAV** whose data-chunk size is still 0, so `<audio>`
  reads duration 0 and refuses to play (`C1 RUNBOOK.md:305-322`). That is precisely the take an
  operator most wants to review. Decide what the pane shows for it — silence, or an explicit
  "audio present, unfinalised" state. It is also an independent argument for open decision 2: an
  in-progress take's WAV is unfinalised by construction, so audio during recording is impossible
  whatever G4 says about frames.

The obvious cheap option — play the WAV free-running alongside the frames — is honest only if the
UI says the two are not locked together: skipped video frames do not move the audio clock, so the
two drift apart under load. Resolve the path as `<take_dir>/<take_dir.name>.wav` (what
`cinepi_sound.cpp` writes) and fall back to the first `*.wav` with a log line when they disagree —
`simple_gui.py` globs, and on a dual-cam rig a silent glob is a wrong-file bug that returns 200.
Reading `CINEPI_AUDIO_START_OFFSET_*` needs a small RIFF chunk walker: stdlib `wave` will not
expose it, because the iXML chunk is appended *after* the data chunk.

Frame-accurate A/V sync needs a **proxy transcode** (ffmpeg → H.264 once per take, then a native
`<video>`), which was evaluated and **rejected for now**:

- the Pi 5 has no hardware H.264 encoder, so a software transcode of a UHD DNG sequence costs
  minutes per take;
- it doubles disk usage on a card that is often nearly full;
- and it inverts the point of reviewing on the camera, which is to see the take *now*.

It remains the right answer for "make a viewing copy before I strike the set" — a separate
feature, not a way to review between setups.

## Open decisions

| # | Question | Current state | What settles it |
|---|---|---|---|
| 1 | ~~Tab or a section on the RAW page?~~ | **Settled 2026-08-27: a fifth tab, and built** | — |
| 2 | Refuse or degrade while recording? | Refuses (409, stage greys out) | G4. Note the prior has weakened: the ALSA-contention root cause is recorded as *fixed*, and NVMe does not share the mic's bus. The stronger arguments for refusing are now that no core is free during a take, that every media profile sets the I/O scheduler to `none` (no kernel arbitration between the read and write streams), and that the WAV is unfinalised mid-take anyway |
| 3 | Default preview scale, fallback path | 1/4, a guess | The G1/G2 rule in Phase 3. Applies only to takes with no thumbnail |
| 4 | REVIEW button on the shooting screen? | Not built | Operator decision. Costs a `location.hash` reader and the first surface-2 → surface-3 link; costs no controller method |
| 5 | Audio — play it at all, and how? | **Not played.** The WAV endpoint exists; nothing consumes it | Operator decision, informed by the four facts above. Free-running is cheap but must apply the 5-frame offset and be labelled as unlocked; sync needs Phase 4's proxy path |
| 6 | Does the decoder apply the `LinearizationTable`? | **Not established** | G9. Until it reports, the *fallback* path's behaviour on every companded and log take is unknown, and the failure mode is a black frame. The thumbnail path is immune |
| 7 | Thumbnail as IFD0 (raw to a SubIFD) or chained as IFD1? | **Open, and it decides Phase 0's shape** | What the operator's post software actually does with each. IFD0 is the standard DNG shape and what upstream does deliberately; IFD1 leaves every existing reader — including `dng_preview.py` — untouched. Test both against Resolve before choosing |
| 8 | Does the pane say which path a frame came from? | **Yes** — decided with the direction | Not a question, recorded so it is not dropped: a 720p mono proxy and a demosaiced quarter-res frame must never be indistinguishable in the HUD |

## Risks

- **The headline risk has moved.** It used to be G1: if the Pi were worse than ~6× this Mac,
  real-time UHD playback dropped to 1/8 or scrub-only. On the thumbnail path that risk is gone —
  ~23 MB/s and no demosaic. It is replaced by two smaller ones: that Phase 0's second IFD is more
  work than it looks in a hand-rolled TIFF writer on the per-frame encode path, and that the
  thumbnail's write cost is not free on a system whose binding constraint is already storage. G1
  still matters, but only for how well *older* footage reviews.
- **Phase 0 writes to the recording hot path.** `dng_save` runs per frame in the encoder threads,
  and this adds bytes to it. A bug there does not produce a bad preview — it produces a bad take.
  That asymmetry is why G11 compares against a control take and why the toggle's off position must
  be a genuine no-op, byte-identical to today's output.
- **G1 as filed measures a box the process never is.** The isolated decoder on an idle Pi is a
  ceiling, not a prediction: the same process is measured at 31.8–33.5% CPU during a take and its
  HDMI GUI redraw already runs at ~7.5 Hz against a 12 fps target. A playback feature that drops
  the on-camera GUI to 3 Hz is a regression on the primary surface, and nothing today would catch
  it — hence G3's third observable.
- **Storage contention is a known failure shape here**, not a hypothetical: long-take 24-bit drift
  is the recorded historical root cause of ALSA capture xruns under storage contention
  (`C1 RUNBOOK.md:136-143`) — never re-measured, and the specific ext4 disk-worker/audio-core
  collision behind it is recorded as *fixed*. G4 tests whether a read stream reintroduces it by
  another route. **It must not grep for "xrun":** a recovered xrun logs nothing at all, and the two
  lines containing the word both mean the opposite. The signal is
  `Inserted <N> silent frame(s) to cover a capture shortfall`.
- **RAM.** ADR-001 records that the **2 GB variant is unmeasured** (:14-21, :444) — but peak record
  load itself *was* measured, on the 4 GB unit that actually exists, at ~2970 MB available of 4048
  (PI-016). So the risk is specifically the 2 GB board, which the operator does not currently have
  plugged in. Cap in frames, not bytes. And note the guard C9 was written against is not armed
  during playback at all: `RAM_LIMIT_PERCENT = 80` lives in `_recording_worker`, started only by
  `start_recording()` — the real exposure is what the ring leaves behind for the *next* take.
- **Colour is approximate — and permanently so in the mode C9 most wants to preview.**
  `AsShotNeutral` on the test frame is `[1, 1, 0.303]`, which looks like unset AWB defaults
  because it is: `docs/clear-hdr.md:13,19` records that ISP statistics are invalid at 16-bit, so
  auto white balance *cannot run* in the ClearHDR modes. This is a review preview for framing,
  focus and motion; the UI must not imply it is a grading reference, and the docs page must say
  that magenta highlights near the HG→LG hand-off are the sensor, not the decoder — or the first
  ClearHDR review session generates a bug report against `dng_preview.py`.

| commit | change |
|---|---|
| C9.0a | **cinepi-raw** · `IFDBuilder` gains multi-IFD support; `dng_save` emits the lores plane as a thumbnail IFD, mono or colour per `thumbnail` (0 off / 1 mono / 2 colour), sized by `thumbnail_size`. Off is byte-identical to today |
| C9.0b | **cinepi-raw** · fix `cinepi_controller.cpp:137` seeding `CONTROL_KEY_THUMBNAIL` with `thumbnail_size_` |
| C9.0c | **cinemate** · the toggle: a settings key, a CLI verb, a settings-editor control, writing the `thumbnail` redis key |
| C9.1 | `docs/settings-json.md` · `conform_frame_rate` is used, by the timecode tracker and now by playback; the timecode base is a whole number; no effect on capture. **Lands first and on its own** — it is correct today, it is the one piece of C9 that exists in a single place, and it does not depend on the rebase |
| C9.2 | Rebase `feature/clip-playback` onto current `dev`; re-run the full check set; re-report the count |
| C9.3 | The six defects above — topbar predicate, `raw_files` reuse, cache key, the `"value"` collision, the Live iframe, the 409 signal set |
| C9.4 | The check C9 owes ADR-001: a test asserting every `data-page-tab` has matching `.group[data-page]`, `[data-page-lede]` and `.rail-group[data-page]` markup, and that the topbar's page predicate covers it |
| C9.5 | `tools/playback_bench.py` — the G1/G2 harness: per-scale decode medians at 1/2/4 workers, device bytes per frame from `/proc/diskstats`, and a rendered-luma check for G9. Runs on the Pi from the repo checkout with no new dependencies |
| C9.6 | Gate outcomes recorded: `GATES.md` verdicts, Phase 3's default scale set from the G1/G2 rule, Phase 3 items struck where a gate cancels them |

**Branch:** `feature/clip-playback` off `dev` @ `714ef7b4` (cinemate, cut 2026-08-27, 2 commits,
**not pushed** and 1381 commits behind `dev`), plus a cinepi-raw branch off its `dev` for Phase 0,
still to be cut — C9 is a two-repo step as of 2026-09-01. The gates need it on the Pi, so it has to
be pushed before Session A — which is also the only way the `conform_frame_rate` docs fix stops
living in one place. Planning commits stay here on `feature/dev-track` as `c9:`; the hardware
session reports as `c9-pi:`.

**Verification.** Desk — done at `714ef7b4`: 9 tests in `_test/test_dng_preview.py`, the real
blueprint through `harness.py`, ruff and the drift checks; **stale**, and re-grounding found six
defects and one unestablished behaviour (G9) that the harness could not see. Hardware — nothing.
None of G0–G9 has run; `cinepi.local` was unreachable on the day.

**Hardware needed:** the dev Pi for every gate, and for Phase 0 a **cinepi-raw build on it** —
the first C9 step that is not a Python restart. An **imx585** for G1's UHD/ClearHDR figures and for
G7/G9 entirely — the attached sensor of record is an imx477, which has no 3856×2180 mode, no
ClearHDR and no log support, so those gates are not merely unrun but unrunnable as filed. A phone
on the hotspot for G6. A **2 GB CM5** for G5 as written; ADR-001 records the dev unit is 4 GB, so
G5 otherwise runs on 4 GB and states its 2 GB verdict as derived, not measured.
