# Simple GUI

Simple GUI is available both on the attached HDMI output and through the browser-based web UI.

## Background colours

- **Black:** idle
- **Red:** at least one camera is actively writing frames to disk (`is_writing=1`)
- **Green:** RAM buffer is filling or buffered frames are still flushing after stop (`is_buffering` or `is_writing_buf`)
- **Purple:** live drop-frame alert
- **Magenta:** live frame-count sync mismatch
- **Blue:** storage pre-roll warm-up is running
- **Yellow:** RAM load has passed the safety threshold; the GUI asks the controller to stop recording

The separate `DROP` tile latches after a drop-frame event and stays visible until a new take starts. A crossed magenta `SYNC` tile latches as soon as the live expected-vs-recorded frame slot count is outside the configured live tolerance (default +/- 2 frames), then stays visible through the end of the take and until the next take starts. Dropped-frame holes do not trigger the `SYNC` tile by themselves; they are shown by `DROP`.

## What the GUI shows

- The buffer meter in the lower-left corner shows used vs total frame buffer. Optional hatch lines can be enabled in `settings.json` under `hdmi_gui`.
- During storage pre-roll, the GUI intentionally hides recording time and clip names so the deleted warm-up clip does not appear to be the latest take.
- If zoom is anything other than the configured default, the zoom box is highlighted.
- If dynamic resolution is actively substituting a measured sustainable mode for the current FPS, the resolution numbers turn green. They stay white when Cinemate is showing the user's desired resolution, even if dynamic resolution is enabled.
- When a compatible USB microphone is connected, the right side shows VU meters plus sample rate, bit depth, and a `WAV` badge once the latest take contains both DNG frames and a WAV sidecar.

For redraw timing and performance tuning, see `docs/simple-gui-refresh-tuning.md`.
