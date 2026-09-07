# Timing
<!-- sidebar group `timing` · tab: settings.jsonc -->

Edit the headings and the paragraphs. Leave the `<!-- key: ... -->` lines alone —
they are what the GUI looks each string up by when CineMate starts.

---

## Timing & sync
<!-- key: pane.sync -->

How strictly the recorder watches frame timing before it warns you or flags a take.

### Auto storage pre‑roll
<!-- key: card.system.storage.auto_preroll -->

Lets the storage device settle before recording is allowed to start, avoiding a rocky first few frames.

### Local mains frequency
<!-- key: card.sync.1 -->

Frequencies considered when computing flicker‑free shutter angles for artificial light.

### Conform frame rate
<!-- key: card.settings.conform_frame_rate -->

The project frame rate everything is timecode‑conformed to, regardless of the capture rate.

### Live sync warning tolerance
<!-- key: card.settings.sync_tolerances.live_sync_warning_frames -->

How many frames audio and video may drift apart during a take before the on‑screen sync warning appears.

### Startup guard
<!-- key: card.settings.sync_tolerances.live_sync_startup_guard_frames -->

Frames of extra tolerance right at the start of a take, while sync is still settling in.

### Final sync tolerance
<!-- key: card.settings.sync_tolerances.final_sync_analysis_frames -->

How much drift is allowed in the end‑of‑take analysis before a clip is flagged as out of sync.

### Timecode jitter tolerance
<!-- key: card.settings.sync_tolerances.tc_drop_jitter_frames -->

Small timecode hiccups within this many frames are ignored instead of logged as a drop.
