# Exposure & steps
<!-- sidebar group `exposure-and-steps` · tab: settings.jsonc -->

Edit the headings and the paragraphs. Leave the `<!-- key: ... -->` lines alone —
they are what the GUI looks each string up by when CineMate starts.

---

## Value steps
<!-- key: pane.steps -->

The click‑stops each control cycles through, and — for the four with a pot channel assigned in Pots below — the free‑running range between the lowest and highest stop.

### ISO steps
<!-- key: card.arrays.iso.free -->

Values the ISO control steps through, in order. Free stepping lets an assigned pot sweep ISO continuously between the lowest and highest stop here instead of snapping to one — Increment sets how finely it quantizes while sweeping.

<!-- key: caption.arrays.iso.free · one per control, separated by ' · ' -->
*Free stepping · Increment*

### Shutter angle steps
<!-- key: card.arrays.shutter_a.free -->

Values the shutter angle control steps through, in degrees. Free stepping sweeps continuously between the lowest and highest stop here — Increment sets the degree step while sweeping.

<!-- key: caption.arrays.shutter_a.free · one per control, separated by ' · ' -->
*Free stepping · Increment*

### Frame‑rate steps
<!-- key: card.arrays.fps.free -->

Values the FPS control steps through. Free stepping sweeps continuously between the lowest and highest stop here — Increment sets the fps step while sweeping.

<!-- key: caption.arrays.fps.free · one per control, separated by ' · ' -->
*Free stepping · Increment*

### White balance steps
<!-- key: card.arrays.wb.free -->

Values the WB control steps through, in Kelvin. Free stepping (on by default) sweeps continuously between the lowest and highest stop here — Increment sets the Kelvin step while sweeping.

<!-- key: caption.arrays.wb.free · one per control, separated by ' · ' -->
*Free stepping · Increment*

### Anamorphic desqueeze steps
<!-- key: card.steps.4 -->

Preview desqueeze factors available on the anamorphic control. No pot or free stepping — this one's step‑only.

---

## Resolution & sensor
<!-- key: pane.resolution -->

Automatic resolution behaviour, ClearHDR's startup knobs, DNG thumbnails and the active sensor database. Which driver modes are offered is now chosen per camera, from the recording-mode table on each Camera pane.

### Dynamic resolution
<!-- key: card.image_capture.dynamic_resolution -->

When the requested frame rate is higher than the selected mode can sustain, drop to the best mode that can. GUI show RES in green while one is held.

### Dynamic resolution priority
<!-- key: card.image_capture.dynamic_resolution_priority -->

**Follow mode** holds the class and drops resolution first: 16‑bit 4K, then 16‑bit HD, then 4K SDR, then HD SDR. 
**Follow resolution** holds the frame size and drops the class first: 16‑bit 4K, then 4K SDR, then HD SDR. 
**Never leave the mode** – resolution is the only thing that changes.

### ClearHDR startup knobs
<!-- key: card.image_capture.hdr.threshold_low -->

Applied when a ClearHDR mode is selected. Adjust live afterwards with `set hdr …` or a pot/quad‑rotary channel. Leave a threshold blank to keep the driver's own pair (low 0, high 4095). Set both or neither — equal thresholds flatten the image.

<!-- key: caption.image_capture.hdr.threshold_low · one per control, separated by ' · ' -->
*Threshold low · Threshold high · Blend · Gain adder*

### DNG thumbnails
<!-- key: card.image_capture.thumbnail -->

By default DNGs carry a small preview image, used by the Playback pane for renderless playback.

<!-- key: caption.image_capture.thumbnail · shown under the measured cost line, which the route renders per camera -->
Disable to slightly increase write speed and reduce cpu load during recording (disables web GUI playback).

### Sensor database
<!-- key: card.sensors.database_file -->

Source file describing every supported sensor's modes. Edit only if you're adding hardware support.
