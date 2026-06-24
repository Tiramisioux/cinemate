# Changelog

Release notes for Cinemate. For downloads, see the [releases page](https://github.com/Tiramisioux/cinemate/releases).

## Version 3.3.2

### Headline features

- **Frame-rate phase lock** — closed-loop control (sigma-delta VBLANK dither) keeps long takes locked to the Pi's wall clock; pre-converges during preview. Per-sensor, off by default.
- **Reliable audio sync on 4K / exFAT** — the capture path was reworked (protected helper, dedicated writer thread, wall-clock reconciliation, RT scheduling) so the WAV stays in sync on demanding modes.
- **Accurate embedded timecode** — TC derived from elapsed microseconds with sub-second origin, anchored to the first-frame wall clock, and routed per camera for dual-sensor rigs.
- **Correct Pi 4 RAW** — CSI2-packed frames decode correctly instead of garbling on Pi 4-family boards; raw packing (P/U) is chosen per Pi model automatically.

### Full list

**CinePi-RAW recorder:**

- **Phase lock:** closed-loop frame-rate phase lock; PI control law (was an undamped integral); pre-converges during preview; re-arms on preview reconfigure and absorbs reconfigure/drop gaps; role-gated and referenced to the Pi wall clock for dual-sensor rigs; Pi-verified default gains; core extracted with unit tests.
- **Timecode:** derive TC from elapsed µs to preserve dropped-frame holes; anchor HH:MM:SS to the first-frame wall clock; remove TC jitter/duplicates; preserve sub-second TC origin for external sync; fix `tc_fps` unit (µs not ns); eliminate phantom TC holes from a wall-clock race; publish `tcFrameCount`; align the `FXX` filename index with the DNG TC origin.
- **Per-camera timecode:** tag `cp_stats` with the camera port.
- **Audio capture:** protected helper for 16- and 24-bit paths; decouple capture from disk I/O via a writer thread; large capture ring buffer; reconcile capture length to wall-clock each read; remove pre-start dsnoop backlog; SCHED_FIFO + xrun silence-fill; CPU isolation + priority 80 on 4K exFAT; remove the ALSA drain tail; dispatch WAV timecode offset by mic bit-depth; add `--audio-timecode-offset-frames`.
- **DNG metadata:** add `--unique-camera-model`; default model `cinepi`; set DNG `Model` from the attached sensor.
- **Pi 4 RAW:** decode CSI2-packed raw correctly.
- **Recording robustness:** publish `framesInFlight` and gate a new take until buffered frames flush; clear the disk buffer before recording; a throwing `dng_save()` no longer jams the rec-gate; count + publish disk-write failures (`writeFailures`); keep DNG workers off the audio core.
- **Stats / misc:** publish unbiased `droppedFrames` and peak disk-backlog (`bufferSizeMax`); silence all compiler warnings; fix DrmPreview initializer order.

**Cinemate workflow:**

- **Phase lock:** per-sensor `phase_lock` setting driving the recorder; removed the old `sensor_fps_correction` factor mechanism.
- **Raw packing:** data-driven P/U selection per Pi model from `sensors.json`.
- **Per-camera timecode:** route `tc_cam0` / `tc_cam1` by camera port.
- **Storage / media:** multi-drive RAW hotswap with standby + promotion; isolate non-RAW drives from write-tuning; promotion waits out async lazy-unmount; don't unmount a healthy drive on a corrupt clip dir (NTFS hotswap flap); live disk-write-failure warning + NTFS flagged not-recommended; default format exFAT (macOS-compatible, GUID, 1 MB clusters); harden erase/format against disk-busy with NTFS quick format; skip fsck on NTFS; repartition undersized partitions to full capacity; robust unmount; per-storage-profile raw-buffer headroom.
- **Audio:** fix mic hotswap and enlarge the 24-bit dsnoop buffer; nested `24bit`/`16bit` settings with per-path `capture_gain_db`; stock gain/offset defaults calibrated from measurements (2-frame offset); ensure 16-bit settings reach Redis; keep DNG workers off the audio core on ext4/NTFS.
- **Drop / sync detection:** TC-based slot counting replaces the FPS-deviation detector; split TC holes from missing files; harden against TC-rounding bias; clearer live sync tolerances/latch; precise post-take TC/file-integrity verdict; suppress stale-counter startup false positives.
- **Recording GUI:** drive `is_writing_buf` / `is_buffering` from compression backlog; block start while buffered frames flush; buffer VU from peak backlog; RAM-buffer watchdog auto-stop; fix recording-time indicator freezing.
- **Camera model / settings:** `override_camera_name` / `camera_name` (on by default) with per-camera DNG model override; consolidate per-cam settings under `camera.cam0`/`cam1`; per-cam tuning-file override; remove deprecated `show_startup_message`.
- **Preview / resolution:** lores dimensions from the sensor aspect ratio; preview guide aligned to the displayed stream; show pending resolution while switching; keep dynamic resolution below the desired mode.
- **Boot / console:** boot-to-preview ~10 s on Pi 4/5; clean console handoff between GUI and terminal; service RT priority raised (`LimitRTPRIO` 80); SCHED_FIFO for manual runs.
- **Single instance:** detect a running instance and auto-stop it instead of exiting.

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
