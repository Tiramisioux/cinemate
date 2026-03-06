# Simple GUI

Simple GUI is available via browser and/or attached HDMI monitor.

- Red color means camera is recording.
- Purple color means camera detected a drop frame 
- Green color means camera is writing buffered frames to disk. You can still start recording at this stage, but any buffered frames from the last recording will be lost.

Buffer meter in the lower left indicates number of frames in buffer. Useful when testing storage media.

When a compatible USB microphone is connected, VU meters appear on the right side of the GUI so you can monitor audio levels.
## Improving real-time GUI rendering

To make `simple_gui` feel more real-time on HDMI output, you can tune the `hdmi_gui` settings in `settings.json`:

```json
{
  "hdmi_gui": {
    "target_fps": 15,
    "max_frame_skip_ms": 5
  }
}
```

- `target_fps`: GUI refresh target. Higher values improve responsiveness at the cost of CPU usage.
- `max_frame_skip_ms`: how far behind a frame may fall before the renderer resynchronizes, which helps avoid accumulating lag and stutter.

The renderer now also caches font objects to reduce per-frame overhead, which improves frame consistency when many text elements are redrawn.
