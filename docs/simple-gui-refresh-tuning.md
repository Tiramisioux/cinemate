# Simple GUI Refresh Tuning

This page explains the timing-related settings in `src/module/simple_gui.py` that control how responsive the HDMI Simple GUI feels and how much work it asks the Pi to do.

The current redraw model is event-driven:

- fast-changing UI state is redrawn on demand when Redis values change
- redraws are capped so the GUI does not repaint faster than the configured frame rate
- expensive system stats are refreshed on a slower interval

That means the main tuning goal is to balance responsiveness against framebuffer bandwidth and CPU use.

## The main timing settings

These values live near the top of `SimpleGUI.__init__()`.

 `self.target_fps = 12`

This is the maximum redraw rate for the GUI fast path.

- Higher values make frame count, timecode, buffer state, recording state, and VU motion feel more immediate.
- Lower values reduce CPU load and reduce full-screen framebuffer writes.
- The GUI will still redraw on demand, but never faster than this cap.

Recommended range on the Pi:

- `10` to `12`: good default balance
- `15`: snappier, but worth testing for thermals and CPU load
- above `15`: usually not recommended with the current full-screen PIL-to-framebuffer path

`self.min_frame_interval = 1 / self.target_fps`

This is the derived minimum time between redraws.

- At `12 FPS`, the minimum interval is about `0.083 s`
- At `10 FPS`, it is `0.100 s`
- At `15 FPS`, it is `0.067 s`

You normally should not edit this directly. Change `target_fps` instead.

`self.slow_refresh_interval = 1.0`

This controls how often the GUI refreshes the heavy, slow-changing values.

These currently include:

- CPU load
- CPU temperature
- latest recording info from the storage scan

Effects:

- Lower values make system stats and latest-recording status update sooner.
- Higher values reduce background work and keep the hot redraw path lighter.

Recommended range:

- `1.0`: good default
- `0.5`: more live system stats, slightly more overhead
- `1.5` to `2.0`: lighter background load if you only care about fast camera-state updates

## Audio meter timing

These values affect how the right-side VU meter feels.

`self.vu_decay_factor = 0.2`

The runtime loop currently sets `self.vu_decay_factor = 0.2` in `run()`, and that is the value that controls how quickly the displayed VU bars fall when the signal drops.

- Higher value: faster fall
- Lower value: slower fall, more lingering meter

Practical examples:

- `0.1`: slower, smoother decay
- `0.2`: current behavior
- `0.3`: faster, more reactive falloff

## Advanced timing knob

`self._redraw_event.wait(timeout=0.1)`

Inside `run()`, the GUI waits up to `0.1` seconds when no work is queued. Redis changes wake the loop immediately, so this is mostly a fallback sleep while idle.

- Lower: slightly tighter idle polling
- Higher: a little less background wake activity

Tune `target_fps` and `slow_refresh_interval` first; they matter much more.
