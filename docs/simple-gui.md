# Simple GUI

Simple GUI is available both on the attached HDMI. 

The browser-based web UI featurer basic settings and interactive controls.



## Indicators

- The buffer meter in the lower-left corner shows used vs total frame buffer. Optional hatch lines can be enabled in `settings.json` under `hdmi_gui`.
- During storage pre-roll, the GUI hides recording time and clip names.
- If zoom is anything other than the configured default, the zoom box is highlighted yellow.
- If dynamic resolution is substituting a measured sustainable mode for the current FPS, the resolution numbers turn green.
- If shutter angle sync is activated, the shutter value is green.
- If fps is modified by double fps being activated, the number turns green.
- When a compatible USB microphone is connected, the right side shows VU meters plus sample rate, bit depth, and a `WAV` badge once the latest take contains both DNG frames and a WAV sidecar.

### Background colors

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

For redraw timing and performance tuning, see [Simple GUI refresh tuning](simple-gui-refresh-tuning.md).
