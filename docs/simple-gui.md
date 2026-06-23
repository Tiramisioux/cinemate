# Simple GUI

Simple GUI is available both on the attached HDMI output and through the browser-based web UI.

## Background colour

The whole screen changes colour to tell you what the camera is doing.

- **Black:** idle.
- **Red:** recording (writing frames to disk).
- **Any other colour:** a warning or attention state. Check the indicator reference below.

## What the GUI shows

- The buffer meter in the lower-left corner shows used vs total frame buffer. Optional hatch lines can be enabled in `settings.json` under `hdmi_gui`.
- During storage pre-roll, the GUI hides recording time and clip names so the deleted warm-up clip does not appear to be the latest take.
- If zoom is anything other than the configured default, the zoom box is highlighted.
- If dynamic resolution is substituting a measured sustainable mode for the current FPS, the resolution numbers turn green. They stay white when Cinemate is showing your desired resolution, even if dynamic resolution is enabled.
- When a compatible USB microphone is connected, the right side shows VU meters plus sample rate, bit depth, and a `WAV` badge once the latest take contains both DNG frames and a WAV sidecar.

??? note "Full colour & indicator reference"

    | Colour | Meaning |
    | --- | --- |
    | **Black** | Idle. |
    | **Red** | At least one camera is actively writing frames to disk. |
    | **Green** | RAM buffer is filling, or buffered frames are still flushing after stop. |
    | **Purple** | Live drop-frame alert. |
    | **Magenta** | Live frame-count sync mismatch. |
    | **Blue** | Storage pre-roll warm-up is running. |
    | **Yellow** | RAM load has passed the safety threshold; the GUI asks the controller to stop recording. |

    **Latching tiles.** The `DROP` tile latches after a drop-frame event and stays visible until a new take starts. A crossed magenta `SYNC` tile latches as soon as the live expected-vs-recorded frame slot count is outside the configured live tolerance (default +/- 2 frames), then stays visible through the end of the take and until the next take starts. Dropped-frame holes do not trigger the `SYNC` tile by themselves; they are shown by `DROP`.

    **WAV badge greying.** The `WAV` badge dims to **light grey** while the previous take's WAV is being resampled for ADC clock correction (typically a few seconds); it returns to normal grey once the correction is complete. See `docs/audio-recording.md` for details on ADC clock correction.

For redraw timing and performance tuning, see `docs/simple-gui-refresh-tuning.md`.
