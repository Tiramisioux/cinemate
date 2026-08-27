# C9 · Clip playback — review takes on the camera

Play a recorded take back in the web GUI, at the speed it will run in post, without taking the
card out. Explored and prototyped 2026-08-27 (Fable session) against `dev` tip `714ef7b4`.

This is a **project, not a patch**: the first increment is written and desk-verified, but the
question that decides how far it can go — how fast the Pi decodes, and how fast it can read the
card — has not been measured on hardware. The phases below are ordered so that measurement comes
before any further build.

Scratch work, the feasibility study and the standalone design mockup are in the external
workspace `Documents/cinemate/development/playback-pane/` (`FEASIBILITY.md`, `DESIGN.md`,
`harness.py`, `mockup/`).

## Why it is possible at all

Three properties of what `dng_encoder.cpp` writes, all confirmed against real frames (the six
imx585 mode-matrix samples, a real UHD imx585 still, and a genuine 50-frame imx477 take):

| Property | Consequence |
|---|---|
| The IFD is at the **tail**, with its offset in the 8-byte header | A take's metadata costs ~2 kB to read, measured **0.03 ms** — so indexing a whole card is free, and the clip list can show real frame rates and resolutions without touching pixel data |
| One **uncompressed, row-addressable** strip (`StripOffsets == 8`, `RowsPerStrip ==` height) | A downscaled preview reads and unpacks only the rows it needs. Cost tracks the *output* size, not the sensor size |
| No embedded thumbnail or preview IFD (the writer logs "raw-only frames") | Every preview must demosaic. There is no shortcut, which is why the decoder had to be proven before anything else |

And one that decides the architecture: numpy and Pillow both release the GIL, so a plain
`ThreadPoolExecutor` scales nearly linearly (3.1× on 4 workers). No multiprocessing needed.

## Measured, on an Apple Silicon Mac — **not** on the Pi

| Mode | Scale | Output | Decode | I/O per frame | Read rate @ 25 fps |
|---|---|---|---|---|---|
| UHD 3856×2180 12-bit | 1/2 | 1928×1090 | 38.4 ms | 12.6 MB | 315 MB/s |
| | **1/4** | **964×545** | **13.9 ms** | **6.3 MB** | **158 MB/s** |
| | 1/8 | 482×272 | 5.3 ms | 3.2 MB | 79 MB/s |
| UHD 16-bit ClearHDR | 1/4 | 964×545 | 10.5 ms | 8.4 MB | 210 MB/s |
| 2K 1928×1090 12-bit | 1/2 | 964×545 | 9.3 ms | 3.2 MB | 79 MB/s |

Threaded, UHD at 1/4: 12.4 ms (1 worker) → 6.7 ms (2) → 3.9 ms (4).

**The headline claim to test: reserving 2 of the Pi's 4 cores, the Pi may be up to ~6× slower
than this Mac per core and still hold 25 fps at 964×545 for UHD footage** (40 ms budget against
6.7 ms measured). Everything downstream depends on that number.

**The likely binding limit is storage, not CPU.** 158 MB/s for UHD at 1/4 is fine on NVMe,
marginal on a USB SATA SSD, out of reach on SD. 2K is comfortable everywhere. Delivery over the
hotspot is *not* a constraint: a real-scene frame at 964×545 q80 is ~32 kB, i.e. 6.4 Mbit/s at
25 fps.

## Two facts the DNG does not record

**There is no HDR tag.** Not in the DNG, not in the WAV's iXML (which carries only
`CINEPI_AUDIO_START_OFFSET_*` and `CINEPI_TIMECODE_SOURCE`). It is recoverable because under a
`LinearizationTable` the level tags describe the table's linear *output*: **`WhiteLevel > 4095`
means HDR-range data.** Verified across every mode the encoder emits —

| BitsPerSample | LinearizationTable | WhiteLevel | BlackLevel | Mode |
|---|---|---|---|---|
| 12 | absent | 4095 | 200 | SDR 12-bit linear |
| 16 | absent | 65535 | 3200 | ClearHDR 16-bit linear |
| 12 | present | 62704 / 63265 | 200 | ClearHDR 12-bit companded |

What is **not** recoverable is *which curve* a table holds: the CCMP decompand and the CineMate
Log curve share tag 0xC618 and compose into one table when log runs over 12-bit ClearHDR. The UI
therefore badges `CRV` ("a curve is baked in"), never `LOG`. Do not add a `LOG` badge later
without a new signal on disk to justify it.

**Mono is undetectable.** `mono_` is hardcoded false and every frame carries a colour CFA even on
the mono rig, so demosaicing mono footage through a Bayer pattern produces a convincing wrong
image. It is an operator toggle, and must stay one until something on disk says otherwise.

## Playback speed follows the conform rate

`settings.conform_frame_rate` is the timebase, not the take's recorded rate. A 50 fps take on a
25 fps conform plays at **half speed**, because that is what it will do on the timeline. A toggle
turns it off to watch a take as shot.

This makes C9 the **first real consumer** of that setting. `docs/settings-json.md` used to say it
was "not really used by CineMate except for calculating the recording timecode tracker in redis
but might be used in future updates" — **corrected on the implementation branch** (`b7e5eb43`),
which also records two things that were true but undocumented: the timecode base is rounded to a
whole number (23.976 → a 24-frame base), and the setting has no effect on capture at all.

Two consequences worth not rediscovering:

- **Speed ramps replay correctly with no rate logic at all.** In conform mode playback is one
  frame per conform tick, whatever the sensor was doing frame to frame. Since `FrameRate` (51044)
  is written on *every* frame, a ramped take carries its own ramp.
- **Conforming a high-rate take makes it cheaper**, since cost tracks frames displayed per second.

Caveat: `conform_frame_rate` is a known multi-source drift (F-251 — schema and `config_loader`
default to 24, shipped configs say 25). The pane reads the live value and displays it; it must not
restate a default.

## Phase 1 — the first increment (written, desk-verified)

Branch `feature/clip-playback` off `dev` @ `714ef7b4`. Two commits, **not pushed**.

| Path | What |
|---|---|
| `src/module/app/dng_preview.py` | The decoder: metadata read, mode inference, row-limited and row-selective decode to JPEG. numpy + Pillow + stdlib only — no rawpy, no libraw, no exiftool subprocess |
| `src/module/app/playback.py` | Clip indexing and frame serving. Directory scans cached against take mtime; concurrent decodes capped and **refused** past the cap rather than queued |
| `src/module/app/settings_editor.py` | Three endpoints under `/api/playback/` — clip index (also reports `conform_frame_rate` and recording state), one frame, the WAV |
| `src/module/app/templates/settings_editor.html` | The **fifth page tab**, the player, the clip HUD and the playback settings |
| `_test/test_dng_preview.py` | 9 tests pinning the scale semantics and the HDR inference against synthesised DNGs |

Placement follows the handbook's state model: a playback pane is **file-backed**, which puts it
with the settings editor and recovery console (surfaces 3/4), not in
`populate_values()`/Socket.IO. Frame serving is *data*, so plain Flask routes are correct; any
future *action* the pane grows must route through `POST /api/v1/cmd` like everything else.

Verified end to end through the **real** blueprint via `development/playback-pane/harness.py`
(:8798) — which stubs redis, redirects `/media/RAW` to a fake card built from a genuine 50-frame
imx477 take plus symlinked UHD SDR and UHD ClearHDR takes, and exposes a recording toggle.
Confirmed: mode inference on real tags, per-take scale sizes, the 409 recording lockout and
recovery, the 503 back-off, and that the other four tabs still behave. ruff clean, 556 tests,
design-token / GUI-field / docs-drift checks green.

### Two bugs that only appeared once it ran

Recorded because both failed *silently* — neither raised anything:

| Bug | Why it mattered |
|---|---|
| **`scale` was incoherent.** Collapsing a 2×2 Bayer cell already halves both dimensions, so `scale=4` produced half width, not a quarter — every size label in the UI was one step off | A wrong preview size does not throw, it just looks plausible. Now a plain linear divisor, with per-take pixel sizes on each option, pinned by a test that fails on the old behaviour |
| **`immutable` caching was wrong across an update.** A frame is a pure function of (take, index, scale, mono) and takes never change — but it is *not* a pure function of the decoder | After a cinemate update the browser would serve frames rendered by the old code for the rest of the cache lifetime. Fixed with a render token derived from `dng_preview.py`'s own mtime, mixed into the frame URL. Caught in the browser, where changing scale kept returning the previous size |

## Phase 2 — hardware gates (none run; `cinepi.local` was unreachable)

**Check `free -g` and `uname -r` first** — `cinepi.local` is whichever CM5 is plugged in, and
16-bit work needs ≥ 6.12.93.

| # | Gate | Method | Passes if |
|---|---|---|---|
| **G1** | Decode throughput | Copy `dng_preview.py` + a UHD and a 2K take; 15-iteration median at 1/2, 1/4, 1/8 with 1/2/4 threads | UHD at 1/4 with 2 workers ≤ 40 ms/frame |
| **G2** | Storage read bandwidth | Sequential read of a take from `/media/RAW`, per filesystem | ≥ 160 MB/s for UHD at 1/4; ≥ 80 MB/s for 2K |
| **G3** | Flask streaming under load | Serve frames through the real route; measure client-side fps alongside a live Socket.IO push | Holds the conform rate with the decode cap in place |
| **G4** | Playback during recording | Attempt playback mid-take on ext4 and exFAT; watch for xruns and drops | Settles whether refusing is necessary or merely cautious |
| **G5** | RAM on a 2 GB board | Playback at each scale with `free -m` sampled | Never approaches the 80% auto-stop |
| **G6** | Hotspot throughput | `iperf3` from a phone on the AP | ≥ 10 Mbit/s sustained (6.4 needed at 1/4) |
| **G7** | Mode inference on fresh takes | Shoot SDR, 12-bit ClearHDR, 16-bit ClearHDR **and a log take** on current `dev`; run `describe_mode()` | Classifies all four; confirms the log/CCMP case is genuinely ambiguous |
| **G8** | CFA orientation | Whether flips change `CFAPattern` | Colour is correct across flip settings |

G1 and G2 gate everything after them: together they decide which modes get real-time playback and
therefore what the default preview scale should be.

## Phase 3 — after the gates

Not started, and deliberately not designed in detail before G1/G2 report:

- **Default scale** set from measurement rather than the current guess (1/4).
- **Decode-ahead** — a bounded prefetch ring, sized in frames rather than bytes so the 2 GB board
  cannot be pushed into the auto-stop.
- **Playback-while-recording** — refuse (current behaviour) or degrade to metadata-only, per G4.
- **A `docs/` page** for the pane itself (the `docs/settings-json.md` correction is already done).
- **Reachability** — whether the HUD gets a REVIEW button deep-linking to the last take. It would
  make the pane one tap from the shooting screen, at the cost of a link between two surfaces that
  currently have none. Operator decision.

## Phase 4 — audio, and the path deliberately not taken

Audio currently plays free-running: the WAV is served, drift against skipped video frames is not
corrected, and the UI says so. Frame-accurate A/V sync needs a **proxy transcode** (ffmpeg →
H.264 once per take, then a native `<video>`), which was evaluated and **rejected for now**:

- the Pi 5 has no hardware H.264 encoder, so a software transcode of a UHD DNG sequence costs
  minutes per take;
- it doubles disk usage on a card that is often nearly full;
- and it inverts the point of reviewing on the camera, which is to see the take *now*.

It remains the right answer for "make a viewing copy before I strike the set" — a separate
feature, not a way to review between setups.

## Open decisions

| # | Question | Current state |
|---|---|---|
| 1 | ~~Tab or a section on the RAW page?~~ | **Settled 2026-08-27: a fifth tab, and built** |
| 2 | Refuse or degrade while recording? | Refuses (409, stage greys out). G4 decides whether that was necessary |
| 3 | Default preview scale | 1/4. Set it from G1/G2 |
| 4 | REVIEW button on the HUD? | Not built. Operator decision |
| 5 | Audio in scope beyond free-running? | Only via Phase 4, which is deferred |

## Risks

- **The verdict rests on one unmeasured number** (G1). If the Pi is worse than ~6× this Mac,
  real-time UHD playback drops to 1/8 or to scrub-only. The pane degrades honestly either way —
  it shows the achieved rate and the skip count rather than running slow — but the feature's
  value changes.
- **Storage contention is a known failure shape here**, not a hypothetical: long-take 24-bit
  drift was traced to ALSA capture xruns under storage contention. That is why playback is
  refused while recording, and why G4 exists.
- **2 GB RAM is unmeasured under this load.** ADR-001 says so explicitly for peak record load;
  a decode cache makes it worse. Cap in frames, not bytes.
- **Colour is approximate.** `AsShotNeutral` on the test frame is `[1, 1, 0.303]` — a 3.3× blue
  gain with R and G at exactly 1.0, which looks like unset AWB defaults. This is a review preview
  for framing, focus and motion; the UI must not imply it is a grading reference.
