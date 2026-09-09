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

Which resolutions and bit depths are offered, and the startup values for imx585 ClearHDR.

### Resolutions offered
<!-- key: card.resolution.0 -->

Which resolutions (in "K") the resolution control offers. Turning one off hides every mode at that size; a size this sensor has no mode for stays hidden either way.

### Bit depths offered
<!-- key: card.resolution.1 -->

Which raw capture bit depths the resolution control offers. 16‑bit is imx585 ClearHDR only.

### Dynamic resolution
<!-- key: card.image_capture.dynamic_resolution -->

When the requested frame rate is higher than the selected mode can sustain, drop to the best mode that can. GUI show RES in green while one is held.

### Dynamic resolution priority
<!-- key: card.image_capture.dynamic_resolution_priority -->

**Follow mode** holds the class and drops resolution first: 16‑bit 4K, then 16‑bit HD, then 4K SDR, then HD SDR. 
**Follow resolution** holds the frame size and drops the class first: 16‑bit 4K, then 4K SDR, then HD SDR. 
**Never leave the mode** – resolution is the only thing that changes.

### Expose plain (SDR) modes
<!-- key: card.image_capture.hdr.sdr -->

Show the sensor's non‑HDR modes on the resolution control.

### Expose 12‑bit ClearHDR modes
<!-- key: card.image_capture.hdr.imx585_clear_hdr_12bit -->

Companded capture — cinepi‑raw applies the CCMP decompand.

### Expose 16‑bit ClearHDR modes
<!-- key: card.image_capture.hdr.imx585_clear_hdr_16bit -->

Delivered linear, with no compander in the path. Both off keeps the sensor SDR‑only.

### ClearHDR startup knobs
<!-- key: card.image_capture.hdr.threshold_low -->

Applied when a ClearHDR mode is selected. Adjust live afterwards with `set hdr …` or a pot/quad‑rotary channel.

<!-- key: caption.image_capture.hdr.threshold_low · one per control, separated by ' · ' -->
*Threshold low · Threshold high · Blend · Gain adder*

### Sensor database
<!-- key: card.sensors.database_file -->

Source file describing every supported sensor's modes. Edit only if you're adding hardware support.

---

## Per-mode fps ceilings
<!-- key: pane.fpsceilings -->

If you are making your own test on what your storage can sustain, these values can be added here. Defaults are what `cinepi-raw --list-cameras` reported on this board,
### (help text not attached to a card)
<!-- key: help.fpsceilings.0 -->

Loading detected modes…
