# Simple GUI Refresh Tuning

This page explains the timing-related settings in `src/module/simple_gui.py` that control how responsive the HDMI Simple GUI feels and how much work it asks the Pi to do.

The current redraw model is event-driven:

- fast-changing UI state is redrawn on demand when Redis values change
- redraws are capped so the GUI does not repaint faster than the configured frame rate
- expensive system stats are refreshed on a slower interval

That means the main tuning goal is to balance responsiveness against framebuffer bandwidth and CPU use.

## The main timing settings

These values live near the top of `SimpleGUI.__init__()`.

### `self.target_fps = 12`

This is the maximum redraw rate for the GUI fast path.

- Higher values make frame count, timecode, buffer state, recording state, and VU motion feel more immediate.
- Lower values reduce CPU load and reduce full-screen framebuffer writes.
- The GUI will still redraw on demand, but never faster than this cap.

Recommended range on the Pi:

- `10` to `12`: good default balance
- `15`: snappier, but worth testing for thermals and CPU load
- above `15`: usually not recommended with the current full-screen PIL-to-framebuffer path

### `self.min_frame_interval = 1 / self.target_fps`

This is the derived minimum time between redraws.

- At `12 FPS`, the minimum interval is about `0.083 s`
- At `10 FPS`, it is `0.100 s`
- At `15 FPS`, it is `0.067 s`

You normally should not edit this directly. Change `target_fps` instead.

### `self.slow_refresh_interval = 1.0`

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

### `self.vu_decay_factor = 0.2`

The runtime loop currently sets `self.vu_decay_factor = 0.2` in `run()`, and that is the value that controls how quickly the displayed VU bars fall when the signal drops.

- Higher value: faster fall
- Lower value: slower fall, more lingering meter

Practical examples:

- `0.1`: slower, smoother decay
- `0.2`: current behavior
- `0.3`: faster, more reactive falloff

### `self.vu_smoothing_alpha = 0.4`

This value is defined in `__init__()`, but the current `update_smoothed_vu_levels()` implementation does not use it.

Right now:

- changing `vu_smoothing_alpha` does not change GUI behavior
- only `vu_decay_factor` affects the displayed smoothing/decay feel

If the VU algorithm is expanded later, this would be the likely place to control how quickly rising levels are smoothed.

## Advanced timing knob

### `self._redraw_event.wait(timeout=0.1)`

Inside `run()`, the GUI waits up to `0.1` seconds when there is no work queued.

In normal use, Redis changes wake the loop immediately, so this timeout is mostly just a fallback sleep while idle.

- Lowering it can make idle polling a little tighter
- raising it can reduce tiny amounts of background wake activity

This is usually not the first thing to tune. `target_fps` and `slow_refresh_interval` matter much more.

## What to change for common goals

### Make the GUI feel more live

Try:

```python
self.target_fps = 15
self.slow_refresh_interval = 1.0
```

Use this if framecount, buffer, and timecode updates still feel a little too stepped.

### Reduce CPU and framebuffer pressure

Try:

```python
self.target_fps = 8
self.slow_refresh_interval = 1.5
```

Use this if the Pi is busy and the GUI does not need to feel as immediate.

### Keep camera-state updates fast, but make system stats more live

Try:

```python
self.target_fps = 12
self.slow_refresh_interval = 0.5
```

Use this if you want CPU temp/load and recording-info updates more often without pushing the redraw cap much higher.

## Suggested workflow when tuning

1. Change `target_fps` first.
2. Test for a few minutes while watching CPU load and overall UI smoothness.
3. Adjust `slow_refresh_interval` only if the system-stat freshness is not where you want it.
4. Adjust `vu_decay_factor` only if the audio meter feel needs changing.

## Where to edit

File:

- `src/module/simple_gui.py`

Primary timing lines:

- `self.target_fps = 12`
- `self.min_frame_interval = 1 / self.target_fps`
- `self.slow_refresh_interval = 1.0`
- `self.vu_smoothing_alpha = 0.4`
- `self.vu_decay_factor = 0.2` inside `run()`

## Important note

The current GUI still redraws the whole PIL image and writes the whole framebuffer for each draw. Because of that, increasing `target_fps` always has a real cost. Small increases are usually fine, but very high values are likely to give diminishing returns on the Pi.
