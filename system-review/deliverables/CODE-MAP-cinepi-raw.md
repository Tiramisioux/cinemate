# CODE MAP — cinepi-raw (C++)

**Session:** S03 · **Snapshot:** `main` @ `774402c` (shallow, read-only — **not `dev`**)
**Audience:** a competent C/C++ developer who has never seen this repo.

> ⚠ **This is not the branch KICKOFF §6.2 describes.** That table was taken from `dev` @
> `ea96f2d`; several LOC figures differ materially. Use `CENSUS.md` §2 for `main`. No
> history is available (shallow clone), so no blame, log or `-S` searches were possible.

---

> ## ⚠ CORRECTION — this map was built against `main`; both repos are now on `dev`
>
> **Added 2026-08-23 on operator instruction (see `STATE.md` D2, F-225).** S03 read
> cinepi-raw `main` @ `774402c`. The applicable branch is **`dev` @ `ea96f2d`**, which is
> **45 files / +7164 lines** ahead. Re-verified against `dev` so far:
>
> | Section | Status on `dev` |
> |---|---|
> | §2 build targets | **Changed** — 7 `meson test` targets, not 1 (F-228) |
> | §5 key contract | **Changed** — 84 / 36 / **23** shared / 12 unreferenced (F-226) |
> | §7 display ownership | **Holds.** The `dualHdmiPreviewStage.cpp` DRM-master comment is byte-identical on `dev`. But `dev` adds plane-level DRM composition to `drm_preview.cpp` (F-227) — read that before using §7 for ADR-001 |
> | RAM auto-stop citation | **Stale** — `cinepi_raw.cpp:225-229` on `dev`, not `:200-212` (F-230) |
>
> **Not yet re-verified:** §4's frame lifecycle (`dng_encoder.cpp` changed by 687 lines — a
> near rewrite), and the entirely new CCMP preview stage and LOG-LUT subsystem, which §2
> and §4 do not mention at all. Treat those sections as `main`-only until re-read.

## 1. The one-paragraph version

cinepi-raw is a **fork of `rpicam-apps`** with a CineMate-specific application layered on
top. Upstream supplies the camera plumbing (`core/`, `preview/`, `encoder/`, `apps/`);
the fork adds `cinepi/`, which is the actual product: a capture loop that writes CinemaDNG
frames, a supervised audio child process, and preview stages that composite one or two
sensors to HDMI. It takes **all** its runtime direction from Redis, on the same
`cp_controls` channel cinemate publishes to. There is one long-lived loop
(`event_loop`), two thread pools inside the DNG encoder, and one forked child for audio.

---

## 2. Build targets — three executables, not one

`cinepi/meson.build` produces three binaries. S01's census saw only the first source list
and missed this.

| Target | Sources | Line |
|---|---|---|
| **`cinepi-raw`** | 10 files: `cinepi_raw`, `dng_encoder`, `sharedContextStage`, `mjpegPreviewStage`, `dualHdmiPreviewStage`, `cinepi_controller`, `cinepi_sound`, `cinepi_state`, `utils`, `cinepi_options` | `meson.build:24-34,50` |
| **`cinepi-audio-capture`** | `cinepi_audio_capture.cpp` alone, ALSA only | `meson.build:56-59` |
| **`phase_lock_core_test`** | `../tests/phase_lock_core_test.cpp`, wired into `meson test` | `meson.build:62-67` |

`apps/meson.build` additionally builds six inherited upstream binaries (`rpicam-still`,
`-vid`, `-hello`, `-raw`, `-jpeg`, `-detect`). Whether the CineMate install needs any of
them is an open question for S10.

**Two build facts worth carrying forward:**

- **Audio capture is a separate process**, not a thread. See §6.
- **`cinepi-raw` has a working unit test in the build** (`test('phase_lock_core', …)`),
  while cinemate's 27 pytest files have no runner at all. The pattern cinemate needs
  already exists in the sibling repo — F-030.

### Dead build artifacts

- `cinepi/lj92.c` + `lj92.h` — **1218 LOC, entirely dead.** In no source list; the only
  `#include "lj92.h"` is inside `lj92.c` itself; `lj92_encode` / `lj92_open` /
  `lj92_decode` have zero callers. A vendored lossless-JPEG codec that nothing reaches.
  F-029, and the largest dead file in either repo.
- `cinepi/_mjpegPreviewStage.cpp` — 240 LOC, underscore-prefixed, not built. F-012.
- `cinepi/meson.build:8,16` — literal `/path/to/hiredis/includes` placeholder paths in the
  pkg-config fallback branches. PI-005.

---

## 3. Entry and the capture loop

```
main()                                   cinepi_raw.cpp:229
  └ CinePIRecorder app                   :233     (subclass of RPiCamApp, upstream)
    CinePiOptions *options               :235
    options->Parse(argc, argv)           :237
      CinePISound   sound(&app)          :239
      CinePIController controller(&app)  :240
      options->mediaDest = "/media/RAW"  :242     ← hardcoded destination
      event_loop(app, controller, sound) :251
```

`event_loop` (`cinepi_raw.cpp:30`) is the whole program:

```
controller.start(); controller.sync();   :32-33
sound.start();                           :35
Output::Create(options)                  :41
app.OpenCamera(); app.StartEncoder();    :46,48
for (unsigned int count = 0; ; count++)  :53
```

### One iteration

| Step | Line | What |
|---|---|---|
| reconfigure check | `:55` | `controller.configChanged()` → restart camera; splits the take first if recording |
| announce readiness | `:118-126` | sets `cinepi_ready_<camPort>` — see §5 |
| **block for a frame** | `:148` | `app.WaitFor(3000ms)` |
| quit | `:151` | `MsgType::Quit` → return |
| **timeout recovery** | `:154-160` | 3 s with no frame → `StopCamera()` + `StartCamera()` + `continue` |
| metadata + stats | `:169` | `controller.process(completed_request)` |
| record edge | `:171` | `controller.triggerRec()` → ±1 |
| start edge | `:173-191` | create clip folder from wall-clock µs, `sound.record_start()`, reset encoder |
| stop edge | `:192-195` | `sound.record_stop()` |
| **RAM guard** | `:200-212` | `if (encoder->buffer_full())` → `setRecording(false)`, "RAM pool exhausted — recording stopped" |
| encode | `:213` | `app.EncodeBuffer(completed_request, RawStream(), LoresStream())` |
| preview | `:222` | `app.ShowPreview(completed_request, LoresStream())` |

**The RAM auto-stop KICKOFF §7 constraint 3 refers to is `cinepi_raw.cpp:200-212`**
(the stop is at `:210`, the warning at `:212`)**.** It is
a hard stop on the record path, not a warning. S08 should cite this line when arguing
about the memory cost of any resident renderer.

### A load-bearing comment — preserve it

`cinepi_raw.cpp:175-184` explains why nothing is dropped when a take starts while the
previous take is still flushing: the old take's `encode_queue_` and `disk_buffer_` drain
into their own clip folder, and **cinemate blocks the rec trigger while `is_writing_buf`
is green**, so by the time a start edge arrives the RAM buffer is empty. That is a
cross-repo interlock documented only in this comment. S05 must flag it for promotion into
docs; nothing else records it.

---

## 4. Frame lifecycle — capture to disk

```
libcamera (forked)
   │  CompletedRequestPtr
   ▼
event_loop  ──▶ controller.process()      metadata, stats → Redis
   │
   ├──▶ app.EncodeBuffer(raw, lores)
   │        ▼
   │    DngEncoder
   │      encode_queue_        (std::queue<EncodeItem>)   dng_encoder.hpp:286
   │        ▼  encode_threads_  (pool)                     :262,190
   │      dng_save(thread_num, …)                          :56
   │        ▼  disk_buffer_
   │        ▼  disk_threads_    (pool)                     :263,191
   │      → CinemaDNG files in the clip folder
   │
   └──▶ app.ShowPreview(lores)  ──▶ preview stage (§7)
```

`frames_in_flight_` (`dng_encoder.hpp:164`) is an atomic counting
`encode_queue_ + mid-encode + disk_buffer_` — capture through written. The header comments
at `:106-110` are explicit that it covers both halves and that the disk half zeroes while
the encode queue is still draining. This counter is what the RAM guard and cinemate's
`is_writing_buf` indicator are ultimately reading.

Thread naming and scheduling are handled by `configureThreadContext()`
(`dng_encoder.hpp:193`); `dng_encoder.cpp:567` notes the audio child runs at SCHED_FIFO 80
and that DNG encode is deliberately kept below it.

**Not traced in S03:** the DNG writer itself (`dng_save`, 1521-LOC file) and the
timing → DNG-tag metadata path. Both are real gaps — see §9.

---

## 5. The Redis bridge — and the cross-repo key contract

cinepi-raw connects to Redis and subscribes to **`cp_controls`**
(`cinepi_controller.hpp:30`), the exact channel cinemate's `RedisController` publishes on
(`redis_controller.py:162`). Two further channels are declared: `cp_stats` (`:31`) and
`cp_histogram` (`:32`).

Dispatch is a handler map, not a switch:

```
cinepi_controller.cpp:353   std::unordered_map<std::string, MessageHandler> handlers = { … }
cinepi_controller.cpp:663   sub.on_message([this,&handlers](channel, msg){ … handlers.find(msg) … })
cinepi_controller.cpp:676   sub.subscribe(CHANNEL_CONTROLS)
```

The published message **is the key name**; the handler then reads that key's value. So the
contract is exactly the set of keys both sides agree on.

### The registry mismatch (F-027, F-028)

| | cinemate | cinepi-raw |
|---|---|---|
| mechanism | `ParameterKey(Enum)` | `#define CONTROL_KEY_*` |
| location | `redis_controller.py:18-113` | `cinepi_state.hpp:23-52` |
| count | 84 | 24 |
| enforced? | no — `set_value` takes any string | no — macros are plain strings |

**19 keys are genuinely shared. 12 C++ key strings have no reference anywhere in
cinemate** (11 distinct concerns — `raw_crop`/`rawCrop` are one feature)**:**
six registered pub/sub handlers that can never fire (`awb`, `shutter_s`, `compress`, `thumbnail`,
`thumbnail_size`, `raw_crop`/`rawCrop`), three PLL tuning knobs never set (`pll_kp`,
`pll_ki`, `pll_deadband_us`), and two telemetry keys nobody reads (`pll_phase_err_us`,
`pll_req_dur_us`). **PI-008 (hardware) found these are not dead**: 8 of the 12 strings are
also read by cinepi-raw itself as an undocumented launch-config contract at every process
start, and the 2 telemetry keys are written ~1401×/60s each with zero reader — live, not
vestigial. Full analysis in `findings/F-027.md`; reproducible with `harness/redis_key_diff.py`.

`awb` is the trap: it looks like the white-balance control, but cinemate sends `wb` /
`wb_user` and drives colour through `cg_rb` plus `--awb`/`--awbgains` launch flags
(`cinepi_multi.py:478-479`). The handler at `cinepi_controller.cpp:409` is unreachable.

### Method caveat — the counts are lower bounds

Both registries were extracted by pattern matching, which **cannot see dynamically
constructed keys**. At least one exists and is load-bearing:

```
cinepi_raw.cpp:124    std::string key = "cinepi_ready_" + options->CamPort();
cinepi_multi.py:812   self.redis_controller.r.keys("cinepi_ready_*")
```

`cinepi_ready_<port>` is a real, live cross-repo handshake — cinemate glob-scans for it to
learn when each camera instance is up. It is in **neither** registry and in neither set of
docs, and it is reached on the Python side through the raw client (`redis_controller.r`),
a fifth access pattern beyond the four catalogued in `CODE-MAP-cinemate.md` §6.

Treat "19 shared / 11 orphaned" as *at least* that much drift, not an exact census.

---

## 6. Audio — a supervised child process

This is the part most likely to surprise a reader: **audio is not captured in-process.**

`CinePISound` (`cinepi_sound.cpp`, 1804 LOC, in the main binary) is a supervisor. It
locates the `cinepi-audio-capture` executable by searching, in order
(`cinepi_sound.cpp:58-62`):

1. `<dir of own exe>/cinepi-audio-capture`
2. `/usr/local/bin/cinepi-audio-capture`
3. `/usr/bin/cinepi-audio-capture`

and launches it via `popen` (`:87`) or a `fork`/`execl` pair through the local `popen2()`
helper (`:504-537`), which runs the command under `/bin/sh -c`.

Teardown is a **pattern-based kill** (`:619`):

```
pkill -f "cinepi-audio-capture.*--discard-output"
```

That matches on any process whose command line fits the pattern, not specifically the
child this instance forked — F-033. On a single-camera rig the distinction is academic;
with two cinepi-raw instances it is not obviously safe, and it cannot be settled without
hardware.

`cinepi_audio_capture.cpp` itself (744 LOC) depends only on ALSA and runs at SCHED_FIFO
priority 80 (per `dng_encoder.cpp:567`), above the DNG encode threads.

The VU contract back to cinemate is `audio_vu` (`cinepi_sound.cpp:22`) — hand-duplicated
in `simple_gui.py:21`, F-016.

---

## 7. Preview and display ownership — decisive for ADR-001

Three post-processing stages self-register:

| Stage | File | Registration |
|---|---|---|
| MJPEG preview (`:8000`/`:8001`) | `mjpegPreviewStage.cpp` | `:245` |
| Dual-HDMI composite | `dualHdmiPreviewStage.cpp` | `:638` |
| Shared context | `sharedContextStage.cpp` | `:304` |

(plus the dead `_mjpegPreviewStage.cpp`, F-012.)

### DRM master is exclusive — confirmed from source, in the code's own words

`preview/drm_preview.cpp` opens the vc4 DRM device and checks mastership:

```
preview/drm_preview.cpp:337    drmfd_ = drmOpen("vc4", NULL);
preview/drm_preview.cpp:350    if (!drmIsMaster(drmfd_))
```

`dualHdmiPreviewStage.cpp:5-18` states the constraint and the workaround explicitly:

> *"the on-camera HDMI preview is drawn by libcamera's DRM preview, and DRM master is
> exclusive per GPU. Two independent cinepi-raw processes (one per sensor) therefore
> cannot both draw to the display — the second is forced to `--nopreview`. […] The
> SECONDARY instance publishes its lores YUV420 frame […] into a small System-V
> shared-memory segment. It never touches DRM. The PRIMARY instance owns the DRM preview
> directly […] composites the two lores images side-by-side […] and shows that canvas via
> DRM."*

**This settles KICKOFF §7 constraint 1 from source.** DRM master is exclusive, cinepi-raw
claims it, and the project has *already* had to engineer around that exclusivity once —
with SysV shared memory — rather than by sharing the display. Any ADR-001 option that
introduces a second DRM client (D: kiosk browser, E: HTML→raster to DRM) has to explain
why it does not hit the same wall the second sensor hit.

The same comment also flags itself: *"This is a first, hardware-untested cut (the 2-sensor
beam-splitter rig is future hardware)."* 638 LOC that has never run. S05 should preserve
this comment; S12 should not schedule changes to this file without hardware.

### How the GUI overlays live video — partially answered

cinepi-raw draws preview through **DRM/KMS**. cinemate's HDMI GUI writes the **legacy
fbdev node** directly — `framebuffer.py:84` builds `/dev/fb{device_no}` and `:136` does
`open(self.path, "wb")`.

So the two surfaces reach the display through *two different kernel interfaces*, which is
why they can coexist at all: on the Pi, fbdev is emulated over DRM/KMS. **What S03 can
confirm is the two interfaces. Exactly how the two images compose — z-order, whether the
GUI is a true overlay plane or is racing the same scanout buffer — is not determinable
from source and needs the Pi.** Queued as PI-009; it is a prerequisite for ADR-001
constraint 2, and S08 must not answer that constraint from reasoning alone.

---

## 8. Dependency on the forked libcamera

Noted, not audited (KICKOFF §3 puts libcamera out of scope).

- `cinepi_controller.cpp` sets standard controls: `AnalogueGain` (`:405`), `AwbEnable`
  (`:413`), `ColourGains` (`:430`).
- `cinepi_raw.cpp:105-106` uses **Raspberry Pi vendor controls** —
  `controls::rpi::ScalerCrops` and `controls::rpi::StatsOutputEnable`. These are not
  upstream libcamera; they tie the build to the RPi fork.
- `dualHdmiPreviewStage.cpp` includes `<linux/dma-buf.h>` and uses DMA-BUF ioctls
  directly.

Any libcamera bump has to preserve `controls::rpi::ScalerCrops` semantics — that is the
zoom/crop path.

---

## 9. What S03 did not establish

- **`dng_save()` and the DNG writer** — the 1521-LOC core of the write path, untraced.
- **The metadata path (timing → DNG tags)** — explicitly in S03's brief, not done. The
  clip-folder naming comment (`cinepi_raw.cpp:181-184`) shows a relationship between
  `wall_ts_us`, `sub_frames` and the TC origin that deserves its own pass.
- **`cinepi_sound.cpp` internals** — 1804 LOC; only the supervisor/child boundary mapped.
- **`cinepi_state.cpp` / `cinepi_manager.*`** — the state object was read only for its key
  macros.
- **Whether the six inherited `rpicam-*` binaries are used or installed** — S10.
- **Anything runtime** — DRM compositing, thread timing, the RAM guard's real threshold.
  See `PI-VERIFICATION-QUEUE.md`.
