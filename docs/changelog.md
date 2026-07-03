# Changelog

Release notes for Cinemate. For downloads, see the [releases page](https://github.com/Tiramisioux/cinemate/releases).

## Version 3.3.2

**libcamera:**

- Cinemate now uses its own fork of libcamera.

**CinePi-RAW recorder:**

- **Frame-rate phase lock** — closed-loop control (sigma-delta VBLANK dither) keeps long takes locked to the Pi's wall clock and pre-converges during preview. On by default.
- **More reliable audio sync on 4K / exFAT** — the capture path was reworked (protected helper, dedicated writer thread, wall-clock reconciliation, real-time scheduling) for more reliable WAV sync on demanding modes.
- **Wall clock embedded timecode** — timecode is anchored to the first frame's wall-clock time and follows the Pi's real-time clock, so it reflects the actual time of day rather than a plain sequential frame count; routed per camera for dual-sensor rigs.
- **Correct Pi 4 RAW** — CSI2-packed frames decode correctly on Pi 4-family boards; raw packing (P/U) is chosen per Pi model automatically.
- **Camera model** — set the camera model manually for each attached sensor.
- **Recording robustness** — a new take waits for buffered frames to finish flushing; disk-write failures are counted and reported; DNG workers are kept off the audio core.
- **Stats** — unbiased dropped-frame and peak disk-backlog reporting.

**Cinemate workflow:**

- **Frame-rate phase lock** — per-sensor `phase_lock` setting drives the recorder, replacing the old frame-rate-correction mechanism.
- **Storage / media** — multi-drive RAW hot-swap with a standby drive and automatic promotion; default exFAT formatting (macOS-compatible); live disk-write-failure warning; NTFS flagged as not recommended.
- **Audio** — mic hot-swap fixes; separate 16-bit / 24-bit settings with per-path gain; stock offsets calibrated from measurements.
- **Drop / sync detection** — timecode-based detection replaces the old frame-rate-deviation check, with a precise post-take integrity verdict.
- **Recording GUI** — buffer- and flush-aware recording start; RAM-buffer watchdog auto-stop; correct bit depth and frame rate shown on mode switch.
- **Preview / resolution** — preview rebuilds on aspect-ratio change (no black bars); shows the pending resolution while switching; dynamic resolution tracks the sustainable frame rate.
- **Camera settings** — name each camera and set its DNG model; per-camera settings and tuning-file override; per-camera timecode routing.
- **Boot / install** — faster boot-to-preview on Pi 4/5; raised real-time priority; builds libcamera from CineMate's own fork with tuning overrides scoped to the correct pipeline; auto-stops an already-running instance.

## Version 3.3.1

**CinePi-RAW recorder:**

- New Cinemate fork, reducing CPU load and temperature dramatically and reducing dropped frames.
- Resolution can now be changed without restarting the recorder process, enabling faster mode changes and dynamic resolution switching.
- Better USB microphone sync.

**Cinemate workflow:**

- exFAT support and filesystem-aware storage profiles for efficient media writes, including IMX585 25 fps at 4K to SSD without frame drops.
- Dynamic resolution switching to match the observed sustainable frame rate for the attached sensor and storage media — for example, IMX585 automatically switches to HD above 25 fps when an SSD is used.
- Hot-swapping between 16-bit and 24-bit USB microphones.
- 4K-class recording modes are visible by default.
- Automatic storage pre-roll can be disabled in `settings.json`.
